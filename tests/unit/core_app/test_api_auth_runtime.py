"""Tests for PixEagle API runtime authentication helpers."""

import json
from types import SimpleNamespace

import pytest

from classes.api_auth_runtime import (
    API_AUTH_MODE_LOCAL_COMPAT,
    API_AUTH_MODE_MACHINE_BEARER,
    APIAuthConfigurationError,
    APIAuthRuntime,
    BearerTokenRecord,
    authorize_http_request,
    has_proxy_forwarded_client_headers,
    hash_bearer_token,
    is_loopback_transport_client,
    load_bearer_token_records,
    make_token_record,
    resolve_api_auth_runtime_from_parameters,
)
from classes.api_exposure_policy import (
    LOCAL_ONLY,
    TRUSTED_LAN_LEGACY,
    resolve_api_exposure_policy,
)
from classes.api_security_types import (
    ALL_API_SCOPES,
    APIPrincipalKind,
    CONFIG_READ,
    STATUS_READ,
)


def _local_policy():
    return resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )


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
