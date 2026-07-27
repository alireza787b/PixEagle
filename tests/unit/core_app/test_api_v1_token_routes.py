"""Typed bearer-token administration route contracts."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

from fastapi import Response
from fastapi.responses import JSONResponse
import pytest

from classes.api_auth_runtime import API_AUTH_MODE_BROWSER_SESSION, APIAuthRuntime
from classes.api_exposure_policy import TRUSTED_LAN_LEGACY, resolve_api_exposure_policy
from classes.api_security_types import (
    ALL_API_SCOPES,
    APIPrincipal,
    APIPrincipalKind,
    MEDIA_READ,
)
from classes.api_v1_auth_routes import (
    create_auth_token,
    get_auth_tokens,
    revoke_auth_token,
)
from classes.api_v1_contracts import APIAuthTokenCreateRequest
from classes.api_v1_paths import API_V1_AUTH_TOKENS_PATH
from classes.bearer_token_store import BearerTokenStore
from classes.browser_user_store import make_browser_user_record
from classes.api_auth_runtime import authorize_http_request


@pytest.fixture(autouse=True)
def _owner_only_auth_test_files():
    previous_umask = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(previous_umask)


def _runtime(tmp_path):
    admin = make_browser_user_record(
        username="admin",
        plaintext_password="admin-password",
        role="admin",
    )
    token_file = tmp_path / "tokens.json"
    return APIAuthRuntime(
        mode=API_AUTH_MODE_BROWSER_SESSION,
        token_file=token_file,
        token_store=BearerTokenStore(token_file),
        users_by_username={admin.username: admin},
    )


def _request(principal, *, method="GET", csrf_token=None):
    headers = {"host": "192.168.1.20:5077"}
    if csrf_token is not None:
        headers["x-pixeagle-csrf"] = csrf_token
    return SimpleNamespace(
        method=method,
        headers=headers,
        client=SimpleNamespace(host="192.168.1.20"),
        state=SimpleNamespace(api_principal=principal),
    )


def _owner(runtime, audit_events, *, audit_available=True):
    def error_response(*, status_code, code, detail, path):
        return JSONResponse(
            status_code=status_code,
            content={"code": code, "detail": detail, "path": path},
        )

    def record_audit(**event):
        audit_events.append(event)
        return audit_available

    return SimpleNamespace(
        api_auth_runtime=runtime,
        _api_v1_error_response=error_response,
        _record_security_audit_event=record_audit,
    )


def _admin_session(runtime):
    session = runtime.create_session_for_user(runtime.users_by_username["admin"])
    principal = APIPrincipal.session(
        username=session.username,
        role=session.role,
        session_id=session.session_id,
    )
    return session, principal


@pytest.mark.asyncio
async def test_admin_create_list_and_revoke_returns_plaintext_once(tmp_path):
    runtime = _runtime(tmp_path)
    session, principal = _admin_session(runtime)
    audit_events = []
    owner = _owner(runtime, audit_events)
    response = Response()

    created = await create_auth_token(
        owner,
        _request(principal, method="POST", csrf_token=session.csrf_token),
        APIAuthTokenCreateRequest(name="QGC video"),
        response,
    )

    plaintext = created.access_token
    assert plaintext.startswith("pxe_")
    assert created.token.name == "QGC video"
    assert created.token.scopes == [MEDIA_READ]
    assert created.token.state == "active"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert plaintext not in runtime.token_file.read_text(encoding="utf-8")
    assert plaintext not in repr(created)

    listed = await get_auth_tokens(owner, _request(principal))
    assert listed.tokens == [created.token]
    bearer, reason = runtime.principal_from_authorization_header(
        f"Bearer {plaintext}"
    )
    assert reason is None
    assert bearer.kind == APIPrincipalKind.BEARER
    used = await get_auth_tokens(owner, _request(principal))
    assert used.tokens[0].last_used_at is not None

    revoked = await revoke_auth_token(
        owner,
        created.token.token_id,
        _request(principal, method="DELETE", csrf_token=session.csrf_token),
    )
    repeated = await revoke_auth_token(
        owner,
        created.token.token_id,
        _request(principal, method="DELETE", csrf_token=session.csrf_token),
    )
    assert revoked.changed is True
    assert revoked.token.state == "revoked"
    assert repeated.changed is False
    assert runtime.principal_is_active(bearer) is False
    assert plaintext not in repr(audit_events)


@pytest.mark.asyncio
async def test_admin_can_create_and_revoke_a_nonexpiring_token(tmp_path):
    runtime = _runtime(tmp_path)
    session, principal = _admin_session(runtime)
    owner = _owner(runtime, [])

    created = await create_auth_token(
        owner,
        _request(principal, method="POST", csrf_token=session.csrf_token),
        APIAuthTokenCreateRequest(
            name="Lab lifetime token",
            expires_in_days=None,
        ),
        Response(),
    )
    assert created.token.expires_at is None
    assert created.token.state == "active"

    revoked = await revoke_auth_token(
        owner,
        created.token.token_id,
        _request(principal, method="DELETE", csrf_token=session.csrf_token),
    )
    assert revoked.token.state == "revoked"


@pytest.mark.asyncio
async def test_bearer_with_system_admin_cannot_administer_tokens(tmp_path):
    runtime = _runtime(tmp_path)
    created = runtime.create_bearer_token(
        display_name="Powerful integration",
        scopes=ALL_API_SCOPES,
        subject="integration",
        expires_at=None,
    )
    bearer, reason = runtime.principal_from_authorization_header(
        f"Bearer {created.plaintext_token}"
    )
    assert reason is None
    audit_events = []

    result = await get_auth_tokens(
        _owner(runtime, audit_events),
        _request(bearer),
    )

    assert result.status_code == 403
    assert json.loads(result.body)["code"] == "browser_admin_session_required"
    assert audit_events[-1]["reason"] == "browser_admin_session_required"


@pytest.mark.asyncio
async def test_failed_security_audit_prevents_token_generation(tmp_path):
    runtime = _runtime(tmp_path)
    session, principal = _admin_session(runtime)
    audit_events = []

    result = await create_auth_token(
        _owner(runtime, audit_events, audit_available=False),
        _request(principal, method="POST", csrf_token=session.csrf_token),
        APIAuthTokenCreateRequest(name="QGC video"),
        Response(),
    )

    assert result.status_code == 503
    assert json.loads(result.body)["code"] == "security_audit_unavailable"
    assert not runtime.token_file.exists()


def test_token_route_policy_requires_admin_scope_and_session_csrf(tmp_path):
    runtime = _runtime(tmp_path)
    session, _principal = _admin_session(runtime)
    cookie = f"{runtime.session_cookie_name}={session.session_id}"
    policy = resolve_api_exposure_policy(
        bind_host="0.0.0.0",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["http://192.168.1.20:3040"],
        api_port=5077,
    )

    missing_csrf = authorize_http_request(
        runtime=runtime,
        method="POST",
        path=API_V1_AUTH_TOKENS_PATH,
        headers={"cookie": cookie},
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=policy,
    )
    allowed = authorize_http_request(
        runtime=runtime,
        method="POST",
        path=API_V1_AUTH_TOKENS_PATH,
        headers={
            "cookie": cookie,
            runtime.csrf_header_name: session.csrf_token,
        },
        client_host="192.168.1.20",
        host_header="192.168.1.20:5077",
        exposure_policy=policy,
    )

    assert missing_csrf.allowed is False
    assert missing_csrf.reason == "csrf_required"
    assert allowed.allowed is True
