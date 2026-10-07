"""Credentialed HTTP CORS for the explicitly address-agnostic lab profile."""

import pytest
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from classes.api_exposure_policy import (
    LOCAL_ONLY,
    TRUSTED_LAN_LEGACY,
    is_http_browser_request_allowed,
    resolve_api_exposure_policy,
)


def _client(policy):
    async def protected(request):
        return JSONResponse({"error": "authentication_required"}, status_code=401)

    app = Starlette(routes=[Route("/protected", protected)])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(policy.cors_allowed_origins),
        allow_origin_regex=policy.cors_origin_regex,
        allow_credentials=policy.allow_credentials,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-PixEagle-CSRF"],
    )
    return TestClient(app)


@pytest.mark.parametrize("origin", [
    "http://192.168.137.161:3040",
    "http://192.168.0.226:3040",
    "http://new-pi-address.local:3040",
    "https://temporary-gcs.example",
])
def test_empty_trusted_lan_origins_allow_credentialed_preflight_and_denial(origin):
    policy = resolve_api_exposure_policy(
        bind_host="0.0.0.0", mode=TRUSTED_LAN_LEGACY,
        cors_allowed_origins=[], api_port=5077,
    )
    assert is_http_browser_request_allowed(
        host="new-pi-address.local:5077", origin=origin,
        sec_fetch_site="same-site", policy=policy,
    )
    client = _client(policy)
    preflight = client.options("/protected", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-pixeagle-csrf",
    })
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert preflight.headers["access-control-allow-credentials"] == "true"
    response = client.get("/protected", headers={"Origin": origin})
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.parametrize("mode", [LOCAL_ONLY, TRUSTED_LAN_LEGACY])
def test_explicit_origins_keep_exact_cors_boundary(mode):
    policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1", mode=mode,
        cors_allowed_origins=["http://localhost:3040"], allow_credentials=True,
    )
    assert policy.cors_origin_regex is None
    response = _client(policy).options("/protected", headers={
        "Origin": "http://unlisted.example:3040",
        "Access-Control-Request-Method": "GET",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_empty_local_only_origins_do_not_open_cors():
    policy = resolve_api_exposure_policy(
        bind_host="127.0.0.1", mode=LOCAL_ONLY, cors_allowed_origins=[],
    )
    assert policy.cors_origin_regex is None
    assert not policy.allow_credentials


@pytest.mark.parametrize("origin", ["null", "ftp://example.com", "*"])
def test_trusted_lan_rejects_non_web_origins(origin):
    policy = resolve_api_exposure_policy(
        bind_host="0.0.0.0", mode=TRUSTED_LAN_LEGACY, cors_allowed_origins=[],
    )
    response = _client(policy).options("/protected", headers={
        "Origin": origin, "Access-Control-Request-Method": "GET",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
