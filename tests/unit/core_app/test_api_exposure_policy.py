"""Tests for the fail-closed PixEagle API exposure policy."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.responses import Response

from classes.api_auth_runtime import (
    API_AUTH_MODE_BROWSER_SESSION,
    API_AUTH_MODE_LOCAL_COMPAT,
    API_AUTH_MODE_MACHINE_BEARER,
    APIAuthRuntime,
    BearerTokenRecord,
    hash_bearer_token,
)
from classes.api_security_audit import APISecurityAuditLogger
from classes.api_exposure_policy import (
    APIExposurePolicyError,
    DEFAULT_LOCAL_CORS_ORIGINS,
    LOCAL_ONLY,
    TRUSTED_LAN_LEGACY,
    is_http_browser_request_allowed,
    is_http_host_allowed,
    is_loopback_host,
    is_websocket_origin_allowed,
    is_websocket_request_allowed,
    resolve_api_exposure_policy,
    resolve_api_exposure_policy_from_parameters,
)
from classes.api_security_types import APIAuditPolicy, APIPrincipal, APISensitivity, STATUS_READ
from classes.fastapi_handler import FastAPIHandler
from classes.webrtc_manager import WebRTCManager


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _machine_bearer_runtime():
    token_hash = hash_bearer_token("secret-token")
    return APIAuthRuntime(
        mode=API_AUTH_MODE_MACHINE_BEARER,
        bearer_tokens_by_hash={
            token_hash: BearerTokenRecord(
                token_id="token-1",
                subject="ci-client",
                token_sha256=token_hash,
                scopes=frozenset({STATUS_READ}),
            )
        },
    )


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "[::1]", "localhost"])
def test_loopback_hosts_are_recognized(host):
    assert is_loopback_host(host)


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "pixeagle.local", ""])
def test_remote_or_ambiguous_hosts_are_not_loopback(host):
    assert not is_loopback_host(host)


def test_local_only_policy_accepts_explicit_loopback_origins():
    policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=[
            "http://127.0.0.1:3040",
            "http://localhost:3040",
            "http://localhost:3040",
        ],
    )

    assert policy.bind_host == "127.0.0.1"
    assert policy.cors_allowed_origins == (
        "http://127.0.0.1:3040",
        "http://localhost:3040",
    )
    assert policy.allow_credentials is False
    assert policy.is_legacy_remote_exposure is False


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "pixeagle.local"])
def test_local_only_policy_rejects_non_loopback_bind(host):
    with pytest.raises(APIExposurePolicyError, match="requires an explicit loopback"):
        resolve_api_exposure_policy(
            bind_host=host,
            mode=LOCAL_ONLY,
            cors_allowed_origins=[],
        )


def test_local_only_policy_rejects_remote_cors_origin():
    with pytest.raises(APIExposurePolicyError, match="only loopback CORS origins"):
        resolve_api_exposure_policy(
            bind_host="127.0.0.1",
            mode=LOCAL_ONLY,
            cors_allowed_origins=["https://operator.example"],
        )


def test_trusted_lan_legacy_allows_explicit_remote_bind_and_origin():
    policy = resolve_api_exposure_policy(
        bind_host="0.0.0.0",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["http://192.168.1.20:3040"],
        api_port=5077,
    )

    assert policy.is_legacy_remote_exposure is True
    assert policy.cors_allowed_origins == ("http://192.168.1.20:3040",)


def test_trusted_lan_legacy_keeps_backend_hosts_separate_from_browser_origins():
    policy = resolve_api_exposure_policy(
        bind_host="0.0.0.0",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["https://gcs.example"],
        allowed_hosts=["pixeagle-pi.local", "192.168.10.42"],
        api_port=5077,
    )

    assert policy.allowed_hosts == ("pixeagle-pi.local", "192.168.10.42")
    assert is_http_host_allowed("pixeagle-pi.local:5077", policy) is True
    assert is_http_host_allowed("192.168.10.42:5077", policy) is True
    assert is_http_host_allowed("gcs.example:5077", policy) is False
    assert is_http_host_allowed("evil.example:5077", policy) is False


def test_trusted_lan_legacy_allows_external_reverse_proxy_authority_port():
    policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["https://pixeagle.example:8443"],
        allowed_hosts=["pixeagle.example:8443"],
        api_port=5077,
    )

    assert policy.allowed_hosts == ("pixeagle.example:8443",)
    assert is_http_host_allowed("pixeagle.example:8443", policy) is True
    assert is_http_host_allowed("pixeagle.example:5077", policy) is False
    assert is_http_host_allowed("pixeagle.example:9443", policy) is False
    assert is_http_host_allowed("evil.example:8443", policy) is False
    assert is_http_host_allowed("127.0.0.1:5078", policy) is False


def test_trusted_lan_legacy_matches_omitted_default_https_authority_port_only():
    policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["https://pixeagle.example"],
        allowed_hosts=["pixeagle.example:443"],
        api_port=5077,
    )

    assert is_http_host_allowed("pixeagle.example", policy) is True
    assert is_http_host_allowed("pixeagle.example:443", policy) is True
    assert is_http_host_allowed("pixeagle.example:5077", policy) is False
    assert is_http_host_allowed("pixeagle.example:8443", policy) is False


def test_trusted_lan_legacy_rejects_empty_bind_host():
    with pytest.raises(APIExposurePolicyError, match="HTTP_STREAM_HOST must be explicit"):
        resolve_api_exposure_policy(
            bind_host="",
            mode=TRUSTED_LAN_LEGACY,
            cors_allowed_origins=["http://192.168.1.20:3040"],
        )


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1:5077", True),
        ("localhost:5077", True),
        ("[::1]:5077", True),
        ("127.0.0.1:5078", False),
        ("attacker.example:5077", False),
        ("", False),
        (None, False),
    ],
)
def test_local_only_http_host_requires_loopback_authority(host, expected):
    policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=DEFAULT_LOCAL_CORS_ORIGINS,
        api_port=5077,
    )

    assert is_http_host_allowed(host, policy) is expected


def test_trusted_lan_legacy_http_host_uses_configured_hosts_not_wildcard():
    policy = resolve_api_exposure_policy(
        bind_host="0.0.0.0",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["http://192.168.1.20:3040"],
        api_port=5077,
    )

    assert is_http_host_allowed("192.168.1.20:5077", policy) is True
    assert is_http_host_allowed("evil.example:5077", policy) is False
    assert is_http_host_allowed("0.0.0.0:5077", policy) is False


@pytest.mark.parametrize(
    "allowed_host",
    ["*", "https://pixeagle.local", "user:secret@pixeagle.local", "0.0.0.0"],
)
def test_policy_rejects_unsafe_or_invalid_allowed_hosts(allowed_host):
    with pytest.raises(APIExposurePolicyError):
        resolve_api_exposure_policy(
            bind_host="0.0.0.0",
            mode=TRUSTED_LAN_LEGACY,
            cors_allowed_origins=["https://gcs.example"],
            allowed_hosts=[allowed_host],
        )


def test_local_only_policy_rejects_remote_allowed_host():
    with pytest.raises(APIExposurePolicyError, match="only loopback API_ALLOWED_HOSTS"):
        resolve_api_exposure_policy(
            bind_host="127.0.0.1",
            mode=LOCAL_ONLY,
            cors_allowed_origins=["http://localhost:3040"],
            allowed_hosts=["pixeagle-pi.local"],
        )


@pytest.mark.parametrize("origin", [None, "", "http://evil.example", "null", "*"])
def test_websocket_origin_requires_an_explicit_allowlist_match(origin):
    policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
    )

    assert is_websocket_origin_allowed(origin, policy) is False
    assert is_websocket_origin_allowed("http://localhost:3040", policy) is True


def test_websocket_request_requires_allowed_host_and_origin():
    policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )

    assert is_websocket_request_allowed(
        host="127.0.0.1:5077",
        origin="http://localhost:3040",
        policy=policy,
    )
    assert not is_websocket_request_allowed(
        host="attacker.example:5077",
        origin="http://localhost:3040",
        policy=policy,
    )
    assert not is_websocket_request_allowed(
        host="127.0.0.1:5077",
        origin=None,
        policy=policy,
    )
    assert is_websocket_request_allowed(
        host="127.0.0.1:5077",
        origin=None,
        client_host="127.0.0.1",
        policy=policy,
    )
    assert not is_websocket_request_allowed(
        host="192.168.1.20:5077",
        origin=None,
        client_host="192.168.1.20",
        policy=policy,
    )


@pytest.mark.parametrize(
    ("host", "origin", "sec_fetch_site", "expected"),
    [
        ("127.0.0.1:5077", "http://localhost:3040", "same-site", True),
        ("localhost:5077", "http://localhost:5077", "same-origin", True),
        ("attacker.example:5077", None, "same-origin", False),
        ("attacker.example:5077", "http://attacker.example:5077", "same-origin", False),
        ("127.0.0.1:5077", "http://evil.example", "same-origin", False),
        ("127.0.0.1:5077", "http://evil.example", "cross-site", False),
        ("127.0.0.1:5077", None, "cross-site", False),
        ("127.0.0.1:5077", "null", "same-site", False),
        ("127.0.0.1:5077", None, None, True),
    ],
)
def test_http_browser_origin_policy(host, origin, sec_fetch_site, expected):
    policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040", "http://localhost:5077"],
        api_port=5077,
    )

    assert is_http_browser_request_allowed(
        host=host,
        origin=origin,
        sec_fetch_site=sec_fetch_site,
        policy=policy,
    ) is expected


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "null",
        "ftp://localhost:3040",
        "http://localhost:3040/path",
        "http://user:secret@localhost:3040",
    ],
)
def test_policy_rejects_unsafe_or_invalid_cors_origins(origin):
    with pytest.raises(APIExposurePolicyError):
        resolve_api_exposure_policy(
            bind_host="127.0.0.1",
            mode=LOCAL_ONLY,
            cors_allowed_origins=[origin],
        )


def test_unsupported_exposure_mode_fails_closed():
    with pytest.raises(APIExposurePolicyError, match="Unsupported API exposure mode"):
        resolve_api_exposure_policy(
            bind_host="0.0.0.0",
            mode="authenticated_remote",
            cors_allowed_origins=[],
        )


def test_fastapi_middleware_uses_validated_explicit_cors_policy():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.app = FastAPI()
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)

    handler._setup_middleware()

    cors = next(
        middleware
        for middleware in handler.app.user_middleware
        if getattr(middleware.cls, "__name__", "") == "CORSMiddleware"
    )
    assert cors.kwargs["allow_origins"] == ["http://localhost:3040"]
    assert cors.kwargs["allow_credentials"] is False
    assert "Cache-Control" in cors.kwargs["allow_headers"]
    assert "Pragma" in cors.kwargs["allow_headers"]
    assert "Expires" in cors.kwargs["allow_headers"]


def test_fastapi_middleware_rejects_dns_rebinding_preflight_before_cors():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.app = FastAPI()
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)

    @handler.app.get("/probe")
    async def probe():
        return {"ok": True}

    handler._setup_middleware()

    response = TestClient(handler.app).options(
        "/probe",
        headers={
            "Host": "attacker.example:5077",
            "Origin": "http://localhost:3040",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 403


def test_checked_in_defaults_are_local_only_and_have_no_wildcard_origin():
    defaults = yaml.safe_load(
        (PROJECT_ROOT / "configs" / "config_default.yaml").read_text(encoding="utf-8")
    )
    streaming = defaults["Streaming"]

    policy = resolve_api_exposure_policy(
        bind_host=streaming["HTTP_STREAM_HOST"],
        mode=streaming["API_EXPOSURE_MODE"],
        cors_allowed_origins=streaming["API_CORS_ALLOWED_ORIGINS"],
    )

    assert policy.mode == LOCAL_ONLY
    assert is_loopback_host(policy.bind_host)
    assert "*" not in policy.cors_allowed_origins


def test_missing_exposure_mode_migrates_legacy_remote_bind_to_loopback():
    parameters = SimpleNamespace(
        HTTP_STREAM_HOST="0.0.0.0",
        _raw_config={"Streaming": {"HTTP_STREAM_HOST": "0.0.0.0"}},
    )

    policy = resolve_api_exposure_policy_from_parameters(parameters)

    assert policy.bind_host == "127.0.0.1"
    assert policy.mode == LOCAL_ONLY
    assert policy.legacy_remote_bind_migrated is True
    assert policy.cors_allowed_origins == DEFAULT_LOCAL_CORS_ORIGINS


def test_browser_session_auth_mode_enables_exact_origin_credentials():
    parameters = SimpleNamespace(
        HTTP_STREAM_HOST="127.0.0.1",
        HTTP_STREAM_PORT=5077,
        API_AUTH_MODE=API_AUTH_MODE_BROWSER_SESSION,
        _raw_config={
            "Streaming": {
                "API_EXPOSURE_MODE": LOCAL_ONLY,
                "API_AUTH_MODE": API_AUTH_MODE_BROWSER_SESSION,
                "API_CORS_ALLOWED_ORIGINS": ["http://localhost:3040"],
            }
        },
    )

    policy = resolve_api_exposure_policy_from_parameters(parameters)

    assert policy.allow_credentials is True
    assert policy.cors_allowed_origins == ("http://localhost:3040",)


def test_parameters_policy_loads_explicit_allowed_hosts():
    parameters = SimpleNamespace(
        HTTP_STREAM_HOST="0.0.0.0",
        HTTP_STREAM_PORT=5077,
        _raw_config={
            "Streaming": {
                "API_EXPOSURE_MODE": TRUSTED_LAN_LEGACY,
                "HTTP_STREAM_HOST": "0.0.0.0",
                "API_CORS_ALLOWED_ORIGINS": ["https://gcs.example"],
                "API_ALLOWED_HOSTS": ["pixeagle-pi.local"],
            }
        },
    )

    policy = resolve_api_exposure_policy_from_parameters(parameters)

    assert policy.allowed_hosts == ("pixeagle-pi.local",)
    assert is_http_host_allowed("pixeagle-pi.local:5077", policy) is True
    assert is_http_host_allowed("gcs.example:5077", policy) is False


def test_explicit_local_only_remote_bind_still_fails_closed():
    parameters = SimpleNamespace(
        HTTP_STREAM_HOST="0.0.0.0",
        _raw_config={
            "Streaming": {
                "API_EXPOSURE_MODE": LOCAL_ONLY,
                "HTTP_STREAM_HOST": "0.0.0.0",
                "API_CORS_ALLOWED_ORIGINS": ["http://localhost:3040"],
            }
        },
    )

    with pytest.raises(APIExposurePolicyError, match="requires an explicit loopback"):
        resolve_api_exposure_policy_from_parameters(parameters)


@pytest.mark.asyncio
async def test_server_start_rejects_remote_override_before_background_tasks(monkeypatch):
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler._start_background_tasks = AsyncMock()

    monkeypatch.setattr("classes.fastapi_handler.Parameters.API_EXPOSURE_MODE", LOCAL_ONLY)
    monkeypatch.setattr(
        "classes.fastapi_handler.Parameters.API_CORS_ALLOWED_ORIGINS",
        ["http://localhost:3040"],
    )
    monkeypatch.setattr(
        "classes.fastapi_handler.Parameters._raw_config",
        {
            "Streaming": {
                "API_EXPOSURE_MODE": LOCAL_ONLY,
                "API_CORS_ALLOWED_ORIGINS": ["http://localhost:3040"],
            }
        },
    )
    monkeypatch.setattr("classes.fastapi_handler.Parameters.HTTP_STREAM_PORT", 5077)

    with pytest.raises(APIExposurePolicyError, match="requires an explicit loopback"):
        await handler.start(host="0.0.0.0")

    handler._start_background_tasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_video_websocket_rejects_unapproved_origin_before_accept():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    websocket = SimpleNamespace(
        headers={"host": "127.0.0.1:5077", "origin": "http://evil.example"},
        accept=AsyncMock(),
        close=AsyncMock(),
    )

    await handler.video_feed_websocket_optimized(websocket)

    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(code=1008, reason="WebSocket Host or Origin not allowed")


@pytest.mark.asyncio
async def test_streaming_disabled_rejects_http_video_route(monkeypatch):
    handler = FastAPIHandler.__new__(FastAPIHandler)
    monkeypatch.setattr("classes.fastapi_handler.Parameters.ENABLE_STREAMING", False)
    request = SimpleNamespace(
        state=SimpleNamespace(api_principal=APIPrincipal.anonymous()),
    )

    with pytest.raises(HTTPException) as exc_info:
        await handler.video_feed(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Streaming is disabled"


@pytest.mark.asyncio
async def test_streaming_disabled_rejects_video_websocket_before_accept(monkeypatch):
    handler = FastAPIHandler.__new__(FastAPIHandler)
    monkeypatch.setattr("classes.fastapi_handler.Parameters.ENABLE_STREAMING", False)
    websocket = SimpleNamespace(
        headers={},
        accept=AsyncMock(),
        close=AsyncMock(),
    )

    await handler.video_feed_websocket_optimized(websocket)

    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(code=1008, reason="Streaming is disabled")


@pytest.mark.asyncio
async def test_streaming_disabled_rejects_webrtc_signaling_before_accept(monkeypatch):
    manager = WebRTCManager.__new__(WebRTCManager)
    monkeypatch.setattr("classes.webrtc_manager.Parameters.ENABLE_STREAMING", False)
    websocket = SimpleNamespace(
        headers={},
        accept=AsyncMock(),
        close=AsyncMock(),
    )

    await manager.signaling_handler(websocket)

    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(code=1008, reason="Streaming is disabled")


@pytest.mark.asyncio
async def test_video_websocket_rejects_unapproved_host_before_accept():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    websocket = SimpleNamespace(
        headers={"host": "attacker.example:5077", "origin": "http://localhost:3040"},
        accept=AsyncMock(),
        close=AsyncMock(),
    )

    await handler.video_feed_websocket_optimized(websocket)

    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(code=1008, reason="WebSocket Host or Origin not allowed")


@pytest.mark.asyncio
async def test_video_websocket_allows_same_host_native_missing_origin_before_accept(monkeypatch):
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    handler._record_security_audit_event = lambda **_: True
    handler.connection_lock = asyncio.Lock()
    handler.ws_connections = {}
    monkeypatch.setattr("classes.fastapi_handler.Parameters.WS_MAX_CONNECTIONS", 0)
    websocket = SimpleNamespace(
        headers={"host": "127.0.0.1:5077"},
        client=SimpleNamespace(host="127.0.0.1"),
        url=SimpleNamespace(query=""),
        accept=AsyncMock(),
        close=AsyncMock(),
    )

    await handler.video_feed_websocket_optimized(websocket)

    websocket.accept.assert_awaited_once()
    websocket.close.assert_awaited_once_with(code=1008, reason="Max connections reached")


@pytest.mark.asyncio
async def test_webrtc_signaling_rejects_unapproved_origin_before_accept():
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
    )
    manager.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    websocket = SimpleNamespace(
        headers={"host": "127.0.0.1:5077"},
        accept=AsyncMock(),
        close=AsyncMock(),
    )

    await manager.signaling_handler(websocket)

    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(code=1008, reason="WebSocket Host or Origin not allowed")


@pytest.mark.asyncio
async def test_webrtc_signaling_rejects_unapproved_host_before_accept():
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    manager.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    websocket = SimpleNamespace(
        headers={"host": "attacker.example:5077", "origin": "http://localhost:3040"},
        accept=AsyncMock(),
        close=AsyncMock(),
    )

    await manager.signaling_handler(websocket)

    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(code=1008, reason="WebSocket Host or Origin not allowed")


@pytest.mark.asyncio
async def test_http_middleware_rejects_cross_site_request_before_handler():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    request = SimpleNamespace(
        headers={
            "host": "127.0.0.1:5077",
            "origin": "http://evil.example",
            "sec-fetch-site": "cross-site",
        },
        base_url="http://localhost:5077/",
    )
    call_next = AsyncMock(return_value=Response())

    response = await handler._enforce_http_browser_origin(request, call_next)

    assert response.status_code == 403
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_middleware_allows_machine_client_and_adds_security_headers():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/status"),
        query_params={},
        headers={"host": "127.0.0.1:5077"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
        base_url="http://localhost:5077/",
    )
    call_next = AsyncMock(return_value=Response())

    response = await handler._enforce_http_browser_origin(request, call_next)

    call_next.assert_awaited_once_with(request)
    assert response.headers["cross-origin-resource-policy"] == "same-site"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.asyncio
async def test_http_middleware_rejects_dns_rebinding_host_without_origin():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    request = SimpleNamespace(
        headers={"host": "attacker.example:5077", "sec-fetch-site": "same-origin"},
        base_url="http://attacker.example:5077/",
    )
    call_next = AsyncMock(return_value=Response())

    response = await handler._enforce_http_browser_origin(request, call_next)

    assert response.status_code == 403
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_middleware_rejects_unclassified_route_before_handler():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/unclassified"),
        query_params={},
        headers={"host": "127.0.0.1:5077"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
    )
    call_next = AsyncMock(return_value=Response())

    response = await handler._enforce_http_browser_origin(request, call_next)

    assert response.status_code == 403
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_middleware_uses_typed_error_envelope_for_api_v1_auth_failure():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="0.0.0.0",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["http://192.168.1.20:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = _machine_bearer_runtime()
    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/api/v1/runtime/status"),
        query_params={},
        headers={"host": "192.168.1.20:5077"},
        client=SimpleNamespace(host="192.168.1.20"),
        state=SimpleNamespace(),
    )
    call_next = AsyncMock(return_value=Response())

    response = await handler._enforce_http_browser_origin(request, call_next)
    payload = json.loads(response.body)

    assert response.status_code == 401
    assert payload["error"] == "authentication_required"
    assert payload["path"] == "/api/v1/runtime/status"
    assert payload["detail"]["reason"] == "authentication_required"
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_middleware_records_denied_auth_event(tmp_path):
    audit_path = tmp_path / "security_audit.jsonl"
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="0.0.0.0",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["http://192.168.1.20:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = _machine_bearer_runtime()
    handler.security_audit_logger = APISecurityAuditLogger(log_path=audit_path)
    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/api/v1/runtime/status"),
        query_params={},
        headers={"host": "192.168.1.20:5077"},
        client=SimpleNamespace(host="192.168.1.20"),
        state=SimpleNamespace(),
    )
    call_next = AsyncMock(return_value=Response())

    response = await handler._enforce_http_browser_origin(request, call_next)

    assert response.status_code == 401
    events = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["event_type"] == "api.http.authorization"
    assert events[0]["outcome"] == "denied"
    assert events[0]["reason"] == "authentication_required"
    assert events[0]["actor"]["kind"] == "anonymous"
    assert events[0]["path"] == "/api/v1/runtime/status"
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_middleware_blocks_allowed_security_critical_without_audit(tmp_path):
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    handler.security_audit_logger = APISecurityAuditLogger(log_path=tmp_path)
    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/api/v1/actions/offboard-stop"),
        query_params={},
        headers={"host": "127.0.0.1:5077"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
        base_url="http://localhost:5077/",
    )
    call_next = AsyncMock(return_value=Response())

    response = await handler._enforce_http_browser_origin(request, call_next)
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["error"] == "security_audit_unavailable"
    call_next.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_middleware_blocks_allowed_security_critical_when_audit_disabled(tmp_path):
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    handler.security_audit_logger = APISecurityAuditLogger(
        enabled=False,
        log_path=tmp_path / "security_audit.jsonl",
    )
    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/api/v1/actions/offboard-stop"),
        query_params={},
        headers={"host": "127.0.0.1:5077"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
        base_url="http://localhost:5077/",
    )
    call_next = AsyncMock(return_value=Response())

    response = await handler._enforce_http_browser_origin(request, call_next)
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["error"] == "security_audit_unavailable"
    call_next.assert_not_awaited()


def test_webrtc_audit_disabled_blocks_allowed_security_critical(tmp_path):
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.security_audit_logger = APISecurityAuditLogger(
        enabled=False,
        log_path=tmp_path / "security_audit.jsonl",
    )
    websocket = SimpleNamespace(
        headers={"host": "127.0.0.1:5077", "origin": "http://localhost:3040"},
        client=SimpleNamespace(host="127.0.0.1"),
    )

    audit_ok = manager._record_security_audit_event(
        event_type="api.websocket.authorization",
        outcome="allowed",
        reason="allowed",
        websocket=websocket,
        status_code=101,
        principal=APIPrincipal.local_compat(),
        audit_policy=APIAuditPolicy.SECURITY_CRITICAL,
        sensitivity=APISensitivity.MEDIA,
    )

    assert audit_ok is False


@pytest.mark.asyncio
async def test_webrtc_signaling_audit_disabled_media_read_reaches_capacity_gate(
    tmp_path,
):
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    manager.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    manager.security_audit_logger = APISecurityAuditLogger(
        enabled=False,
        log_path=tmp_path / "security_audit.jsonl",
    )
    manager.max_connections = 0
    manager.logger = SimpleNamespace(error=lambda *_args, **_kwargs: None)
    websocket = SimpleNamespace(
        headers={"host": "127.0.0.1:5077", "origin": "http://localhost:3040"},
        client=SimpleNamespace(host="127.0.0.1"),
        url=SimpleNamespace(query=""),
        accept=AsyncMock(),
        close=AsyncMock(),
        send_text=AsyncMock(),
    )

    await manager.signaling_handler(websocket)

    websocket.accept.assert_awaited_once_with()
    websocket.send_text.assert_awaited_once()
    websocket.close.assert_awaited_once_with(
        code=1008,
        reason="Max connections reached",
    )


@pytest.mark.asyncio
async def test_http_middleware_accepts_valid_bearer_and_stores_principal():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="0.0.0.0",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["http://192.168.1.20:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = _machine_bearer_runtime()
    request = SimpleNamespace(
        method="GET",
        url=SimpleNamespace(path="/status"),
        query_params={},
        headers={
            "host": "192.168.1.20:5077",
            "authorization": "Bearer secret-token",
        },
        client=SimpleNamespace(host="192.168.1.20"),
        state=SimpleNamespace(),
    )
    call_next = AsyncMock(return_value=Response())

    response = await handler._enforce_http_browser_origin(request, call_next)

    assert response.status_code == 200
    call_next.assert_awaited_once_with(request)
    assert request.state.api_principal.credential_id == "token-1"


@pytest.mark.asyncio
async def test_video_websocket_rejects_missing_bearer_before_accept():
    handler = FastAPIHandler.__new__(FastAPIHandler)
    handler.exposure_policy = resolve_api_exposure_policy(
        bind_host="0.0.0.0",
        mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=["http://192.168.1.20:3040"],
        api_port=5077,
    )
    handler.api_auth_runtime = _machine_bearer_runtime()
    websocket = SimpleNamespace(
        headers={"host": "192.168.1.20:5077", "origin": "http://192.168.1.20:3040"},
        client=SimpleNamespace(host="192.168.1.20"),
        url=SimpleNamespace(query=""),
        accept=AsyncMock(),
        close=AsyncMock(),
    )

    await handler.video_feed_websocket_optimized(websocket)

    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(
        code=1008,
        reason="WebSocket API request not authorized",
    )


@pytest.mark.asyncio
async def test_webrtc_signaling_rejects_query_token_before_accept():
    manager = WebRTCManager.__new__(WebRTCManager)
    manager.exposure_policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1",
        mode=LOCAL_ONLY,
        cors_allowed_origins=["http://localhost:3040"],
        api_port=5077,
    )
    manager.api_auth_runtime = APIAuthRuntime(mode=API_AUTH_MODE_LOCAL_COMPAT)
    websocket = SimpleNamespace(
        headers={"host": "127.0.0.1:5077", "origin": "http://localhost:3040"},
        client=SimpleNamespace(host="127.0.0.1"),
        url=SimpleNamespace(query="access_token=leaky"),
        accept=AsyncMock(),
        close=AsyncMock(),
    )

    await manager.signaling_handler(websocket)

    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once_with(
        code=1008,
        reason="WebSocket API request not authorized",
    )
