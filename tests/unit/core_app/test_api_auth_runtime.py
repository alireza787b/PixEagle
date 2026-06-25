"""Tests for PixEagle API runtime authentication helpers."""

import base64
import hashlib
import json
import os
from types import SimpleNamespace

import pytest
from fastapi import Response
from fastapi.responses import JSONResponse

import classes.api_auth_runtime as auth_runtime
from classes.api_auth_runtime import (
    API_AUTH_MODE_BROWSER_SESSION,
    API_AUTH_MODE_LOCAL_COMPAT,
    API_AUTH_MODE_MACHINE_BEARER,
    APIAuthConfigurationError,
    APIAuthRuntime,
    APILoginFailureLimiter,
    APIUserRecord,
    BearerTokenRecord,
    MAX_AUTH_RECORD_FILE_BYTES,
    MAX_PBKDF2_ITERATIONS,
    MAX_SESSION_TTL_SECONDS,
    MIN_PBKDF2_ITERATIONS,
    MIN_SESSION_TTL_SECONDS,
    authorize_http_request,
    has_proxy_forwarded_client_headers,
    hash_bearer_token,
    hash_password_pbkdf2_sha256,
    is_loopback_transport_client,
    load_bearer_token_records,
    load_user_records,
    make_token_record,
    make_user_record,
    resolve_api_auth_runtime_from_parameters,
    verify_password_pbkdf2_sha256,
)
from classes.api_exposure_policy import (
    LOCAL_ONLY,
    TRUSTED_LAN_LEGACY,
    resolve_api_exposure_policy,
)
from classes.api_security_types import (
    ALL_API_SCOPES,
    ACTIONS_EXECUTE,
    APIPrincipal,
    APIPrincipalKind,
    CONFIG_READ,
    MEDIA_READ,
    STATUS_READ,
)
from classes.api_v1_auth_routes import get_auth_session, login_auth_session, logout_auth_session
from classes.api_v1_contracts import APIAuthLoginRequest


def _local_policy():
    return resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )


@pytest.fixture(autouse=True)
def _owner_only_auth_test_files():
    previous_umask = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(previous_umask)


def _trusted_lan_policy():
    return resolve_api_exposure_policy(
        bind_host="0.0.0.0",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["http://192.168.1.20:3040"],
        api_port=5077,
    )


def _runtime_with_token(token="secret-token", scopes=frozenset({STATUS_READ})):
    token_hash = hash_bearer_token(token)
    return APIAuthRuntime(
        mode=API_AUTH_MODE_MACHINE_BEARER,
        bearer_tokens_by_hash={
            token_hash: BearerTokenRecord(
                token_id="token-1",
                subject="ci-client",
                token_sha256=token_hash,
                scopes=frozenset(scopes),
            )
        },
    )


def _runtime_with_session_user(password="correct-horse"):
    password_hash = hash_password_pbkdf2_sha256(password)
    return APIAuthRuntime(
        mode=API_AUTH_MODE_BROWSER_SESSION,
        users_by_username={
            "operator": APIUserRecord(
                username="operator",
                role="operator",
                password_pbkdf2_sha256=password_hash,
            )
        },
    )


def _encoded_password_hash(
    *,
    password: str = "correct-horse",
    iterations: int = MIN_PBKDF2_ITERATIONS,
    salt: bytes = b"1234567890abcdef",
    digest: bytes | None = None,
) -> str:
    digest = digest or hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(iterations),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def test_token_file_loads_hashed_named_records(tmp_path):
    token_file = tmp_path / "api_tokens.json"
    token_file.write_text(
        json.dumps(
            {
                "tokens": [
                    make_token_record(
                        token_id="readonly-ci",
                        plaintext_token="high-entropy-token",
                        subject="ci",
                        scopes=[STATUS_READ],
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    records = load_bearer_token_records(token_file)

    assert len(records) == 1
    assert records[0].token_id == "readonly-ci"
    assert records[0].subject == "ci"
    assert records[0].scopes == frozenset({STATUS_READ})
    assert "high-entropy-token" not in token_file.read_text(encoding="utf-8")


def test_user_file_loads_hashed_session_user_records(tmp_path):
    user_file = tmp_path / "api_users.json"
    user_file.write_text(
        json.dumps(
            {
                "users": [
                    make_user_record(
                        username="Operator",
                        plaintext_password="correct-horse",
                        role="operator",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    records = load_user_records(user_file)

    assert len(records) == 1
    assert records[0].username == "operator"
    assert records[0].role == "operator"
    assert verify_password_pbkdf2_sha256(
        password="correct-horse",
        encoded=records[0].password_pbkdf2_sha256,
    )
    assert "correct-horse" not in user_file.read_text(encoding="utf-8")


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership and mode checks")
@pytest.mark.parametrize(
    ("filename", "payload", "loader"),
    [
        (
            "api_tokens.json",
            {"tokens": [make_token_record(token_id="test", plaintext_token="secret", scopes=[STATUS_READ])]},
            load_bearer_token_records,
        ),
        (
            "api_users.json",
            {"users": [make_user_record(username="operator", plaintext_password="correct-horse")]},
            load_user_records,
        ),
    ],
)
def test_auth_record_files_reject_group_or_other_access(tmp_path, filename, payload, loader):
    auth_file = tmp_path / filename
    auth_file.write_text(json.dumps(payload), encoding="utf-8")
    auth_file.chmod(0o644)

    with pytest.raises(APIAuthConfigurationError, match="inaccessible to group/other"):
        loader(auth_file)


@pytest.mark.skipif(os.name != "posix", reason="POSIX no-follow and hard-link checks")
def test_auth_record_files_reject_symlinks_and_hardlinks(tmp_path):
    token_file = tmp_path / "api_tokens.json"
    token_file.write_text(
        json.dumps(
            {"tokens": [make_token_record(token_id="test", plaintext_token="secret", scopes=[STATUS_READ])]}
        ),
        encoding="utf-8",
    )

    symlink_path = tmp_path / "api_tokens-symlink.json"
    symlink_path.symlink_to(token_file)
    with pytest.raises(APIAuthConfigurationError, match="symbolic link|read safely"):
        load_bearer_token_records(symlink_path)

    hardlink_path = tmp_path / "api_tokens-hardlink.json"
    os.link(token_file, hardlink_path)
    with pytest.raises(APIAuthConfigurationError, match="multiple hard links"):
        load_bearer_token_records(token_file)


def test_auth_record_files_reject_oversized_payload(tmp_path):
    token_file = tmp_path / "api_tokens.json"
    token_file.write_bytes(b"{" + b" " * MAX_AUTH_RECORD_FILE_BYTES + b"}")
    token_file.chmod(0o600)

    with pytest.raises(APIAuthConfigurationError, match="byte limit"):
        load_bearer_token_records(token_file)


@pytest.mark.asyncio
async def test_auth_session_response_reports_configured_csrf_header_name():
    runtime = _runtime_with_session_user()
    runtime = APIAuthRuntime(
        mode=runtime.mode,
        users_by_username=runtime.users_by_username,
        csrf_header_name="X-Custom-CSRF",
    )
    owner = SimpleNamespace(api_auth_runtime=runtime)
    request = SimpleNamespace(state=SimpleNamespace())

    response = await get_auth_session(owner, request)

    assert response.auth_mode == API_AUTH_MODE_BROWSER_SESSION
    assert response.csrf_required is True
    assert response.csrf_header_name == "x-custom-csrf"


@pytest.mark.asyncio
async def test_login_success_rolls_back_session_when_security_audit_fails():
    runtime = _runtime_with_session_user()

    def error_response(*, status_code, code, detail, path):
        return JSONResponse(
            status_code=status_code,
            content={"error": code, "detail": detail, "path": path},
        )

    owner = SimpleNamespace(
        api_auth_runtime=runtime,
        _api_v1_error_response=error_response,
        _record_security_audit_event=lambda **_: False,
    )
    request = SimpleNamespace(
        method="POST",
        headers={"host": "127.0.0.1:5077"},
        client=SimpleNamespace(host="127.0.0.1"),
    )
    response = Response()

    result = await login_auth_session(
        owner,
        request,
        APIAuthLoginRequest(username="operator", password="correct-horse"),
        response,
    )

    assert result.status_code == 503
    assert json.loads(result.body)["error"] == "security_audit_unavailable"
    assert runtime.session_store._records == {}
    returned_set_cookie_headers = [
        value.decode("latin-1")
        for key, value in result.raw_headers
        if key.lower() == b"set-cookie"
    ]
    injected_set_cookie_headers = [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    ]
    assert any("Max-Age=0" in header for header in returned_set_cookie_headers)
    assert any("Max-Age=0" in header for header in injected_set_cookie_headers)
    assert all("correct-horse" not in header for header in returned_set_cookie_headers)


@pytest.mark.asyncio
async def test_logout_revokes_and_clears_cookie_when_security_audit_fails():
    runtime = _runtime_with_session_user()
    session = runtime.create_session_for_user(runtime.users_by_username["operator"])
    principal = APIPrincipal.session(
        username=session.username,
        role=session.role,
        session_id=session.session_id,
    )

    def error_response(*, status_code, code, detail, path):
        return JSONResponse(
            status_code=status_code,
            content={"error": code, "detail": detail, "path": path},
        )

    owner = SimpleNamespace(
        api_auth_runtime=runtime,
        _api_v1_error_response=error_response,
        _record_security_audit_event=lambda **_: False,
    )
    request = SimpleNamespace(
        method="POST",
        headers={"host": "127.0.0.1:5077"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(api_principal=principal),
    )
    response = Response()

    result = await logout_auth_session(owner, request, response)

    assert result.status_code == 503
    assert json.loads(result.body)["error"] == "security_audit_unavailable"
    assert runtime.session_store._records == {}
    set_cookie_headers = [
        value.decode("latin-1")
        for key, value in result.raw_headers
        if key.lower() == b"set-cookie"
    ]
    assert any(runtime.session_cookie_name in header for header in set_cookie_headers)
    assert any("Max-Age=0" in header for header in set_cookie_headers)


def test_user_file_rejects_plaintext_password_fields(tmp_path):
    user_file = tmp_path / "api_users.json"
    user_file.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "username": "operator",
                        "role": "operator",
                        "password": "do-not-store-this",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(APIAuthConfigurationError, match="plaintext"):
        load_user_records(user_file)


def test_user_file_rejects_malformed_password_hash(tmp_path):
    user_file = tmp_path / "api_users.json"
    user_file.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "username": "operator",
                        "role": "operator",
                        "password_pbkdf2_sha256": "pbkdf2_sha256$310000$not-base64!$digest",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(APIAuthConfigurationError, match="invalid password"):
        load_user_records(user_file)


@pytest.mark.parametrize(
    "password_hash",
    [
        _encoded_password_hash(iterations=MIN_PBKDF2_ITERATIONS - 1),
        _encoded_password_hash(
            iterations=MAX_PBKDF2_ITERATIONS + 1,
            digest=b"0" * 32,
        ),
        _encoded_password_hash(salt=b"short-salt"),
        _encoded_password_hash(digest=b"short-digest"),
    ],
)
def test_user_file_rejects_weak_or_abusive_password_hash_parameters(
    tmp_path,
    password_hash,
):
    user_file = tmp_path / "api_users.json"
    user_file.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "username": "operator",
                        "role": "operator",
                        "password_pbkdf2_sha256": password_hash,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(APIAuthConfigurationError, match="invalid password"):
        load_user_records(user_file)


def test_user_file_rejects_string_enabled_values(tmp_path):
    user_file = tmp_path / "api_users.json"
    user_file.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "username": "operator",
                        "role": "operator",
                        "password_pbkdf2_sha256": hash_password_pbkdf2_sha256(
                            "correct-horse"
                        ),
                        "enabled": "false",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(APIAuthConfigurationError, match="JSON boolean"):
        load_user_records(user_file)


def test_token_file_rejects_string_enabled_values(tmp_path):
    token_file = tmp_path / "api_tokens.json"
    record = make_token_record(
        token_id="readonly-ci",
        plaintext_token="secret-token",
        scopes=[STATUS_READ],
    )
    record["enabled"] = "false"
    token_file.write_text(json.dumps({"tokens": [record]}), encoding="utf-8")

    with pytest.raises(APIAuthConfigurationError, match="JSON boolean"):
        load_bearer_token_records(token_file)


def test_token_file_rejects_unknown_scope(tmp_path):
    token_file = tmp_path / "api_tokens.json"
    token_file.write_text(
        json.dumps(
            {
                "tokens": [
                    {
                        "token_id": "bad",
                        "token_sha256": "0" * 64,
                        "scopes": ["flight:everything"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(APIAuthConfigurationError, match="Unsupported"):
        load_bearer_token_records(token_file)


def test_resolve_runtime_from_parameters_loads_external_token_file(tmp_path):
    token_file = tmp_path / "api_tokens.json"
    token_file.write_text(
        json.dumps(
            {
                "tokens": [
                    make_token_record(
                        token_id="readonly-ci",
                        plaintext_token="secret-token",
                        scopes=[STATUS_READ],
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    parameters = SimpleNamespace(
        API_AUTH_MODE=API_AUTH_MODE_MACHINE_BEARER,
        API_BEARER_TOKEN_FILE=str(token_file),
        _raw_config={},
    )

    runtime = resolve_api_auth_runtime_from_parameters(parameters)

    assert runtime.mode == API_AUTH_MODE_MACHINE_BEARER
    assert len(runtime.bearer_tokens_by_hash) == 1
    assert runtime.token_file == token_file


def test_resolve_runtime_from_parameters_loads_external_session_user_file(tmp_path):
    user_file = tmp_path / "api_users.json"
    user_file.write_text(
        json.dumps(
            {
                "users": [
                    make_user_record(
                        username="operator",
                        plaintext_password="correct-horse",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    parameters = SimpleNamespace(
        API_AUTH_MODE=API_AUTH_MODE_BROWSER_SESSION,
        API_SESSION_USER_FILE=str(user_file),
        API_SESSION_TTL_SECONDS=120,
        API_SESSION_COOKIE_NAME="pix_session",
        API_SESSION_COOKIE_SECURE=True,
        API_CSRF_HEADER_NAME="X-Test-CSRF",
        _raw_config={},
    )

    runtime = resolve_api_auth_runtime_from_parameters(parameters)

    assert runtime.mode == API_AUTH_MODE_BROWSER_SESSION
    assert runtime.user_file == user_file
    assert runtime.session_ttl_seconds == 120
    assert runtime.session_cookie_name == "pix_session"
    assert runtime.session_cookie_secure is True
    assert runtime.csrf_header_name == "x-test-csrf"
    assert runtime.authenticate_user(
        username="operator",
        password="correct-horse",
    )


def test_machine_bearer_mode_requires_token_records():
    with pytest.raises(APIAuthConfigurationError, match="requires at least one"):
        APIAuthRuntime(mode=API_AUTH_MODE_MACHINE_BEARER)

    token_hash = hash_bearer_token("disabled-token")
    with pytest.raises(APIAuthConfigurationError, match="requires at least one"):
        APIAuthRuntime(
            mode=API_AUTH_MODE_MACHINE_BEARER,
            bearer_tokens_by_hash={
                token_hash: BearerTokenRecord(
                    token_id="disabled",
                    subject="ci-client",
                    token_sha256=token_hash,
                    scopes=frozenset({STATUS_READ}),
                    enabled=False,
                )
            },
        )


def test_browser_session_mode_requires_enabled_user_records():
    with pytest.raises(APIAuthConfigurationError, match="requires at least one"):
        APIAuthRuntime(mode=API_AUTH_MODE_BROWSER_SESSION)

    with pytest.raises(APIAuthConfigurationError, match="requires at least one"):
        APIAuthRuntime(
            mode=API_AUTH_MODE_BROWSER_SESSION,
            users_by_username={
                "operator": APIUserRecord(
                    username="operator",
                    role="operator",
                    password_pbkdf2_sha256=hash_password_pbkdf2_sha256("secret"),
                    enabled=False,
                )
            },
        )


def test_browser_session_ttl_matches_schema_bounds():
    users = {
        "operator": APIUserRecord(
            username="operator",
            role="operator",
            password_pbkdf2_sha256=hash_password_pbkdf2_sha256("secret"),
        )
    }

    with pytest.raises(APIAuthConfigurationError, match="between"):
        APIAuthRuntime(
            mode=API_AUTH_MODE_BROWSER_SESSION,
            users_by_username=users,
            session_ttl_seconds=MIN_SESSION_TTL_SECONDS - 1,
        )

    with pytest.raises(APIAuthConfigurationError, match="between"):
        APIAuthRuntime(
            mode=API_AUTH_MODE_BROWSER_SESSION,
            users_by_username=users,
            session_ttl_seconds=MAX_SESSION_TTL_SECONDS + 1,
        )

    runtime = APIAuthRuntime(
        mode=API_AUTH_MODE_BROWSER_SESSION,
        users_by_username=users,
        session_ttl_seconds=MIN_SESSION_TTL_SECONDS,
    )
    assert runtime.session_ttl_seconds == MIN_SESSION_TTL_SECONDS


def test_login_failure_limiter_throttles_and_clears_keys():
    limiter = APILoginFailureLimiter(max_failures=2, window_seconds=60)

    assert limiter.is_allowed("host:user") == (True, None)
    limiter.record_failure("host:user")
    assert limiter.is_allowed("host:user") == (True, None)
    limiter.record_failure("host:user")
    allowed, retry_after = limiter.is_allowed("host:user")
    assert allowed is False
    assert retry_after is not None

    limiter.clear("host:user")
    assert limiter.is_allowed("host:user") == (True, None)


def test_login_failure_limiter_caps_global_and_per_client_keys():
    limiter = APILoginFailureLimiter(
        max_failures=2,
        window_seconds=60,
        max_keys=3,
        max_keys_per_client=2,
    )

    limiter.record_failure("host:user1")
    limiter.record_failure("host:user2")
    assert limiter.is_allowed("host:user3")[0] is False

    limiter.record_failure("other:user1")
    assert limiter.is_allowed("third:user1")[0] is False


def test_unknown_user_login_runs_dummy_password_verification(monkeypatch):
    runtime = _runtime_with_session_user()
    real_hash = runtime.users_by_username["operator"].password_pbkdf2_sha256
    calls = []

    def fake_verify(*, password, encoded):
        calls.append((password, encoded))
        return password == "not-the-supplied-password"

    monkeypatch.setattr(auth_runtime, "verify_password_pbkdf2_sha256", fake_verify)

    assert runtime.authenticate_user(username="missing", password="probe") is None
    assert len(calls) == 1
    assert calls[0][0] == "probe"
    assert calls[0][1] != real_hash


def test_local_compat_loopback_allows_declared_routes_without_credentials():
    result = authorize_http_request(
        runtime=APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT),
        method="GET",
        path="/status",
        headers={},
        client_host="127.0.0.1",
        host_header="127.0.0.1:5077",
        exposure_policy=_local_policy(),
    )

    assert result.allowed is True
    assert result.principal.kind == APIPrincipalKind.LOCAL_COMPAT


def test_local_compat_does_not_grant_non_loopback_access():
    result = authorize_http_request(
        runtime=APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT),
        method="GET",
        path="/status",
        headers={},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )

    assert result.allowed is False
    assert result.status_code == 401
    assert result.reason == "authentication_required"


def test_local_compat_does_not_trust_host_header_as_transport_proof():
    result = authorize_http_request(
        runtime=APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT),
        method="GET",
        path="/status",
        headers={},
        client_host=None,
        host_header="127.0.0.1:5077",
        exposure_policy=_local_policy(),
    )

    assert result.allowed is False
    assert result.status_code == 401
    assert result.reason == "authentication_required"


def test_forwarded_proxy_headers_disable_local_compat_on_loopback_peer():
    headers = {"X-Forwarded-For": "203.0.113.10"}

    result = authorize_http_request(
        runtime=APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT),
        method="GET",
        path="/status",
        headers=headers,
        client_host="127.0.0.1",
        host_header="127.0.0.1:5077",
        exposure_policy=_local_policy(),
    )

    assert has_proxy_forwarded_client_headers(headers) is True
    assert is_loopback_transport_client(
        client_host="127.0.0.1",
        host_header="127.0.0.1:5077",
        exposure_policy=_local_policy(),
        headers=headers,
    ) is False
    assert result.allowed is False
    assert result.status_code == 401
    assert result.reason == "proxy_forwarded_local_compat_not_allowed"


def test_bearer_token_authorizes_only_exact_scopes():
    runtime = _runtime_with_token(scopes={STATUS_READ})

    status_result = authorize_http_request(
        runtime=runtime,
        method="GET",
        path="/status",
        headers={"authorization": "Bearer secret-token"},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )
    config_result = authorize_http_request(
        runtime=runtime,
        method="GET",
        path="/api/config/current",
        headers={"authorization": "Bearer secret-token"},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )

    assert status_result.allowed is True
    assert status_result.principal.kind == APIPrincipalKind.BEARER
    assert config_result.allowed is False
    assert config_result.reason == "insufficient_scope"
    assert config_result.missing_scopes == (CONFIG_READ,)


def test_browser_session_cookie_authorizes_reads_and_requires_csrf_for_mutations():
    runtime = _runtime_with_session_user()
    user = runtime.authenticate_user(username="operator", password="correct-horse")
    assert user is not None
    session = runtime.create_session_for_user(user)
    cookie_header = f"{runtime.session_cookie_name}={session.session_id}"

    read_result = authorize_http_request(
        runtime=runtime,
        method="GET",
        path="/api/v1/runtime/status",
        headers={"cookie": cookie_header},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )
    missing_csrf_result = authorize_http_request(
        runtime=runtime,
        method="POST",
        path="/api/v1/actions/offboard-stop",
        headers={"cookie": cookie_header},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )
    csrf_result = authorize_http_request(
        runtime=runtime,
        method="POST",
        path="/api/v1/actions/offboard-stop",
        headers={
            "cookie": cookie_header,
            runtime.csrf_header_name: session.csrf_token,
        },
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )

    assert read_result.allowed is True
    assert read_result.principal.kind == APIPrincipalKind.SESSION
    assert read_result.principal.scopes >= frozenset({STATUS_READ, ACTIONS_EXECUTE})
    assert missing_csrf_result.allowed is False
    assert missing_csrf_result.status_code == 403
    assert missing_csrf_result.reason == "csrf_required"
    assert csrf_result.allowed is True


def test_expired_browser_session_cookie_is_public_anonymous_but_media_denied(monkeypatch):
    """Expired cookies may not keep protected media access alive."""
    runtime = _runtime_with_session_user()
    user = runtime.authenticate_user(username="operator", password="correct-horse")
    assert user is not None
    session = runtime.create_session_for_user(user)
    cookie_header = f"{runtime.session_cookie_name}={session.session_id}"
    monkeypatch.setattr(auth_runtime.time, "time", lambda: session.expires_at + 1.0)

    public_result = authorize_http_request(
        runtime=runtime,
        method="GET",
        path="/api/v1/auth/session",
        headers={"cookie": cookie_header},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )
    protected_media_result = authorize_http_request(
        runtime=runtime,
        method="GET",
        path="/api/v1/streams/media-health",
        headers={"cookie": cookie_header},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )

    assert public_result.allowed is True
    assert public_result.principal.kind == APIPrincipalKind.ANONYMOUS
    assert runtime.session_store._records == {}
    assert protected_media_result.allowed is False
    assert protected_media_result.status_code == 401
    assert protected_media_result.reason == "invalid_session"


@pytest.mark.asyncio
async def test_logout_revokes_same_session_for_other_browser_tabs():
    """Logout must invalidate sibling tabs that still hold the old cookie."""
    runtime = _runtime_with_session_user()
    session = runtime.create_session_for_user(runtime.users_by_username["operator"])
    cookie_header = f"{runtime.session_cookie_name}={session.session_id}"
    principal = APIPrincipal.session(
        username=session.username,
        role=session.role,
        session_id=session.session_id,
    )
    owner = SimpleNamespace(
        api_auth_runtime=runtime,
        _record_security_audit_event=lambda **_: True,
    )
    request = SimpleNamespace(
        method="POST",
        headers={"host": "192.168.1.20:5077"},
        client=SimpleNamespace(host="192.168.1.20"),
        state=SimpleNamespace(api_principal=principal),
    )
    response = Response()

    before_logout = authorize_http_request(
        runtime=runtime,
        method="GET",
        path="/api/v1/streams/media-health",
        headers={"cookie": cookie_header},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )
    result = await logout_auth_session(owner, request, response)
    sibling_tab_after_logout = authorize_http_request(
        runtime=runtime,
        method="GET",
        path="/api/v1/streams/media-health",
        headers={"cookie": cookie_header},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )

    assert before_logout.allowed is True
    assert result.revoked is True
    assert runtime.session_store._records == {}
    assert sibling_tab_after_logout.allowed is False
    assert sibling_tab_after_logout.status_code == 401
    assert sibling_tab_after_logout.reason == "invalid_session"


def test_viewer_browser_session_can_read_media_but_cannot_execute_actions():
    """Viewer role keeps media read-only and cannot mutate action resources."""
    runtime = APIAuthRuntime(
        mode=API_AUTH_MODE_BROWSER_SESSION,
        users_by_username={
            "viewer": APIUserRecord(
                username="viewer",
                role="viewer",
                password_pbkdf2_sha256=hash_password_pbkdf2_sha256("viewer-password"),
            )
        },
    )
    session = runtime.create_session_for_user(runtime.users_by_username["viewer"])
    cookie_header = f"{runtime.session_cookie_name}={session.session_id}"

    media_result = authorize_http_request(
        runtime=runtime,
        method="GET",
        path="/api/v1/streams/media-health",
        headers={"cookie": cookie_header},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )
    action_result = authorize_http_request(
        runtime=runtime,
        method="POST",
        path="/api/v1/actions/tracking-stop",
        headers={
            "cookie": cookie_header,
            runtime.csrf_header_name: session.csrf_token,
        },
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )

    assert media_result.allowed is True
    assert media_result.principal.kind == APIPrincipalKind.SESSION
    assert MEDIA_READ in media_result.principal.scopes
    assert ACTIONS_EXECUTE not in media_result.principal.scopes
    assert action_result.allowed is False
    assert action_result.status_code == 403
    assert action_result.reason == "insufficient_scope"
    assert action_result.missing_scopes == (ACTIONS_EXECUTE,)


def test_unknown_session_cookie_is_ignored_on_public_auth_status_only():
    runtime = _runtime_with_session_user()
    headers = {"cookie": f"{runtime.session_cookie_name}=missing-session"}

    public_result = authorize_http_request(
        runtime=runtime,
        method="GET",
        path="/api/v1/auth/session",
        headers=headers,
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )
    protected_result = authorize_http_request(
        runtime=runtime,
        method="GET",
        path="/api/v1/runtime/status",
        headers=headers,
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )

    assert public_result.allowed is True
    assert public_result.principal.kind == APIPrincipalKind.ANONYMOUS
    assert protected_result.allowed is False
    assert protected_result.status_code == 401
    assert protected_result.reason == "invalid_session"


def test_local_only_route_rejects_remote_bearer_even_with_all_scopes():
    runtime = _runtime_with_token(scopes=ALL_API_SCOPES)

    result = authorize_http_request(
        runtime=runtime,
        method="POST",
        path="/api/system/restart",
        headers={"authorization": "Bearer secret-token"},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=_trusted_lan_policy(),
    )

    assert result.allowed is False
    assert result.status_code == 403
    assert result.reason == "route_is_local_only"


def test_local_only_route_rejects_forwarded_proxy_peer_even_with_all_scopes():
    runtime = _runtime_with_token(scopes=ALL_API_SCOPES)

    result = authorize_http_request(
        runtime=runtime,
        method="POST",
        path="/api/system/restart",
        headers={
            "authorization": "Bearer secret-token",
            "forwarded": "for=203.0.113.10;proto=https",
        },
        client_host="127.0.0.1",
        host_header="127.0.0.1:5077",
        exposure_policy=_local_policy(),
    )

    assert result.allowed is False
    assert result.status_code == 403
    assert result.reason == "route_is_local_only"


def test_invalid_bearer_does_not_fall_back_to_local_compat():
    result = authorize_http_request(
        runtime=APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT),
        method="GET",
        path="/status",
        headers={"authorization": "Bearer wrong-token"},
        client_host="127.0.0.1",
        host_header="127.0.0.1:5077",
        exposure_policy=_local_policy(),
    )

    assert result.allowed is False
    assert result.status_code == 401
    assert result.reason == "invalid_bearer_token"


def test_query_string_tokens_are_rejected():
    result = authorize_http_request(
        runtime=APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT),
        method="GET",
        path="/status",
        headers={},
        client_host="127.0.0.1",
        host_header="127.0.0.1:5077",
        exposure_policy=_local_policy(),
        query_params={"access_token": "leaky"},
    )

    assert result.allowed is False
    assert result.status_code == 401
    assert result.reason == "query_token_not_supported"


def test_unknown_routes_fail_closed_before_fastapi_handler_execution():
    result = authorize_http_request(
        runtime=APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT),
        method="GET",
        path="/unclassified",
        headers={},
        client_host="127.0.0.1",
        host_header="127.0.0.1:5077",
        exposure_policy=_local_policy(),
    )

    assert result.allowed is False
    assert result.status_code == 403
    assert result.reason == "route_policy_denied"
