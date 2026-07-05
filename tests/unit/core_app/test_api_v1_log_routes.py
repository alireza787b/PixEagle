"""Tests for typed /api/v1 runtime log dispatchers."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse

from classes.api_v1_errors import build_api_v1_error_response
from classes.api_security_types import APIPrincipal
from classes.api_v1_contracts import APIFrontendErrorReportRequest
from classes.api_v1_log_routes import (
    export_log_session_bundle,
    get_log_session_entries,
    get_log_sessions,
    get_logs_status,
    record_frontend_error,
    reset_frontend_error_rate_limiter_for_tests,
)
from classes.runtime_logging import (
    RuntimeLogSessionManager,
    reset_runtime_log_manager_for_tests,
)


pytestmark = [pytest.mark.unit]


def _owner() -> SimpleNamespace:
    return SimpleNamespace(
        logger=logging.getLogger("tests.api_v1_log_routes"),
        _api_v1_error_response=lambda **kwargs: build_api_v1_error_response(**kwargs),
    )


def _payload(response: JSONResponse) -> dict:
    return json.loads(response.body.decode("utf-8"))


def _request(principal=None) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            api_principal=principal
            or APIPrincipal.session(
                username="admin",
                role="admin",
                session_id="session-admin",
            )
        )
    )


@pytest.fixture
def runtime_log_manager(tmp_path):
    manager = RuntimeLogSessionManager(base_dir=tmp_path, run_id="pixeagle_api_test")
    manager.initialize_session()
    reset_runtime_log_manager_for_tests(manager)
    reset_frontend_error_rate_limiter_for_tests()
    try:
        yield manager
    finally:
        reset_runtime_log_manager_for_tests(None)
        reset_frontend_error_rate_limiter_for_tests()


@pytest.mark.asyncio
async def test_get_logs_status_returns_active_session(runtime_log_manager):
    response = await get_logs_status(_owner())

    assert response["enabled"] is True
    assert response["active_run_id"] == "pixeagle_api_test"
    assert response["manifest"]["run_id"] == "pixeagle_api_test"


@pytest.mark.asyncio
async def test_get_log_sessions_lists_active_session(runtime_log_manager):
    response = await get_log_sessions(_owner())

    assert response["active_run_id"] == "pixeagle_api_test"
    assert response["sessions"][0]["run_id"] == "pixeagle_api_test"
    assert response["sessions"][0]["components"] == ["backend"]


@pytest.mark.asyncio
async def test_get_log_sessions_lists_sidecar_components(runtime_log_manager):
    runtime_log_manager.register_component("dashboard")

    response = await get_log_sessions(_owner())

    assert response["sessions"][0]["components"] == ["backend", "dashboard"]


@pytest.mark.asyncio
async def test_get_log_session_entries_filters_and_caps(runtime_log_manager):
    log_path = runtime_log_manager.component_path("backend")
    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "ts": "2026-07-04T00:00:00.000Z",
                        "level": "INFO",
                        "component": "backend",
                        "logger": "a",
                        "run_id": "pixeagle_api_test",
                        "pid": 1,
                        "thread": "MainThread",
                        "module": "m",
                        "function": "f",
                        "line": 1,
                        "message": "hello",
                    }
                ),
                json.dumps(
                    {
                        "ts": "2026-07-04T00:00:01.000Z",
                        "level": "ERROR",
                        "component": "backend",
                        "logger": "a",
                        "run_id": "pixeagle_api_test",
                        "pid": 1,
                        "thread": "MainThread",
                        "module": "m",
                        "function": "f",
                        "line": 2,
                        "message": "boom",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    response = await get_log_session_entries(
        _owner(),
        "pixeagle_api_test",
        level="ERROR",
        limit=5000,
    )

    assert response["count"] == 1
    assert response["limit"] == 1000
    assert response["entries"][0]["message"] == "boom"


@pytest.mark.asyncio
async def test_get_log_session_entries_returns_sidecar_stream_fields(runtime_log_manager):
    runtime_log_manager.append_component_message(
        "dashboard",
        "dashboard served password=swordfish",
        stream="combined",
        source="launcher-pipe",
    )

    response = await get_log_session_entries(
        _owner(),
        "pixeagle_api_test",
        component="dashboard",
    )

    assert response["count"] == 1
    entry = response["entries"][0]
    assert entry["component"] == "dashboard"
    assert entry["stream"] == "combined"
    assert entry["source"] == "launcher-pipe"
    assert "swordfish" not in entry["message"]


@pytest.mark.asyncio
async def test_get_log_session_entries_returns_typed_404(runtime_log_manager):
    response = await get_log_session_entries(_owner(), "missing_run")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404
    payload = _payload(response)
    assert payload["code"] == "log_session_not_found"
    assert payload["path"] == "/api/v1/logs/sessions/{run_id}"


@pytest.mark.asyncio
async def test_get_log_session_entries_rejects_invalid_level(runtime_log_manager):
    response = await get_log_session_entries(
        _owner(),
        "pixeagle_api_test",
        level="verbose",
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    payload = _payload(response)
    assert payload["code"] == "logs_query_invalid"
    assert "level" in payload["detail"]


@pytest.mark.asyncio
async def test_export_log_session_bundle_returns_file_response(runtime_log_manager):
    runtime_log_manager.append_component_message(
        "backend",
        "export probe token=secret-token",
    )

    response = await export_log_session_bundle(_owner(), "pixeagle_api_test")

    assert response.status_code == 200
    assert response.media_type == "application/gzip"
    assert response.headers["x-pixeagle-run-id"] == "pixeagle_api_test"
    assert len(response.headers["x-pixeagle-log-export-sha256"]) == 64
    assert response.headers["cache-control"] == "no-store"
    assert "runtime-logs.tar.gz" in response.headers["content-disposition"]
    assert response.path.endswith(".tar.gz")
    if response.background is not None:
        await response.background()


@pytest.mark.asyncio
async def test_export_log_session_bundle_returns_typed_404(runtime_log_manager):
    response = await export_log_session_bundle(_owner(), "missing_run")

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404
    payload = _payload(response)
    assert payload["code"] == "log_session_not_found"
    assert payload["path"] == "/api/v1/logs/sessions/{run_id}/export"


@pytest.mark.asyncio
async def test_record_frontend_error_appends_redacted_frontend_component(
    runtime_log_manager,
):
    response = await record_frontend_error(
        _owner(),
        _request(),
        APIFrontendErrorReportRequest(
            source="dashboard",
            level="ERROR",
            name="TypeError",
            message="render failed password=swordfish",
            stack="Authorization: Basic dXNlcjpwYXNz",
            url="http://operator.example/dashboard?token=abc123456",
            route="/dashboard",
            user_agent="test-agent",
            context={"Cookie": "sid=abc"},
        ),
    )

    assert response["accepted"] is True
    assert response["component"] == "frontend"
    entries = runtime_log_manager.read_entries(
        "pixeagle_api_test",
        component="frontend",
    )
    assert entries is not None
    assert len(entries) == 1
    entry = entries[0]
    assert entry["stream"] == "browser"
    assert entry["source"] == "dashboard"
    assert "swordfish" not in entry["message"]
    assert "dXNlcjpwYXNz" not in entry["extra"]["stack"]
    assert "abc123456" not in entry["extra"]["url"]
    assert entry["extra"]["context"]["Cookie"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_record_frontend_error_rejects_oversized_context(runtime_log_manager):
    response = await record_frontend_error(
        _owner(),
        _request(),
        APIFrontendErrorReportRequest(
            message="too much context",
            context={"blob": "x" * 5000},
        ),
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 422
    payload = _payload(response)
    assert payload["code"] == "frontend_error_report_invalid"
    assert "context" in payload["detail"]


@pytest.mark.asyncio
async def test_record_frontend_error_rate_limits_per_principal(runtime_log_manager):
    request = _request(
        APIPrincipal.session(
            username="viewer",
            role="viewer",
            session_id="session-viewer",
        )
    )

    last_response = None
    for index in range(31):
        last_response = await record_frontend_error(
            _owner(),
            request,
            APIFrontendErrorReportRequest(message=f"frontend error {index}"),
        )

    assert isinstance(last_response, JSONResponse)
    assert last_response.status_code == 429
    payload = _payload(last_response)
    assert payload["code"] == "frontend_error_rate_limited"
