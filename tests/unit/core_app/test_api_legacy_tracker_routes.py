"""Tests for legacy tracker route helper extraction."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from classes import api_legacy_tracker_routes as routes
from classes.parameters import Parameters


pytestmark = [pytest.mark.unit]


class FakeRequest:
    def __init__(self, payload) -> None:
        self.payload = payload

    async def json(self):
        return self.payload


class FakeTracker:
    pass


class FakeSchemaManager:
    def __init__(self, *, valid=True, tracker_info=None) -> None:
        self.valid = valid
        self.tracker_info = tracker_info
        self.validation_calls = []

    def get_available_classic_trackers(self):
        return {
            "CSRT": {"display_name": "CSRT Tracker"},
            "Gimbal": {"display_name": "Gimbal Tracker"},
        }

    def get_tracker_info(self, tracker_name):
        if self.tracker_info is not None:
            return self.tracker_info
        return {
            "description": "Classic tracker",
            "supported_schemas": ["position_2d"],
            "capabilities": ["manual_bbox"],
            "performance": {"fps": "medium"},
            "ui_metadata": {
                "display_name": f"{tracker_name} Display",
                "short_description": "Short tracker description",
                "performance_category": "balanced",
                "suitable_for": ["single target"],
            },
        }

    def validate_tracker_for_ui(self, tracker_name):
        self.validation_calls.append(tracker_name)
        if self.valid:
            return True, None
        return False, f"Invalid tracker {tracker_name}"


def response_body(response):
    return json.loads(response.body.decode("utf-8"))


def runtime_status(**overrides):
    data = {
        "has_output": True,
        "active_tracking": True,
        "usable_for_following": True,
        "data_is_stale": False,
        "status": "active_usable",
        "consumer_guidance": "usable",
        "reason": None,
        "claim_boundary": "process-local tracker status only",
    }
    data.update(overrides)
    return data


def make_handler(
    *,
    app_controller=None,
    config_rate_limiter=None,
    runtime=None,
):
    app_controller = app_controller or SimpleNamespace(
        current_tracker_type="CSRT",
        tracking_started=False,
        smart_mode_active=False,
        following_active=False,
        tracking_active=False,
        tracker=None,
        switch_tracker_type=AsyncMock(return_value={"success": True}),
    )
    return SimpleNamespace(
        app_controller=app_controller,
        config_rate_limiter=(
            config_rate_limiter
            or SimpleNamespace(is_allowed=lambda bucket: (True, None))
        ),
        logger=logging.getLogger("test.api_legacy_tracker_routes"),
        _get_tracker_runtime_status_snapshot=lambda: runtime or runtime_status(),
    )


def _raises(exc):
    def raise_exc(*_args, **_kwargs):
        raise exc

    return raise_exc


@pytest.fixture(autouse=True)
def restore_tracker_parameters(monkeypatch):
    monkeypatch.setattr(
        Parameters,
        "DEFAULT_TRACKING_ALGORITHM",
        "CSRT",
        raising=False,
    )


@pytest.fixture
def schema_manager(monkeypatch):
    manager = FakeSchemaManager()
    monkeypatch.setattr(
        "classes.schema_manager.get_schema_manager",
        lambda: manager,
    )
    return manager


@pytest.mark.asyncio
async def test_available_trackers_returns_legacy_selector_payload(schema_manager):
    handler = make_handler(
        app_controller=SimpleNamespace(
            current_tracker_type="Gimbal",
            tracking_started=True,
            smart_mode_active=True,
        )
    )

    payload = response_body(await routes.get_available_trackers(handler))

    assert payload["available_trackers"] == {
        "CSRT": {"display_name": "CSRT Tracker"},
        "Gimbal": {"display_name": "Gimbal Tracker"},
    }
    assert payload["current_configured"] == "Gimbal"
    assert payload["tracking_active"] is True
    assert payload["smart_mode_active"] is True
    assert payload["total_trackers"] == 2


@pytest.mark.asyncio
async def test_available_trackers_uses_default_parameter_fallback(monkeypatch):
    monkeypatch.setattr(
        "classes.schema_manager.get_schema_manager",
        lambda: FakeSchemaManager(),
    )
    handler = make_handler(
        app_controller=SimpleNamespace(
            tracking_started=False,
            smart_mode_active=False,
        )
    )

    payload = response_body(await routes.get_available_trackers(handler))

    assert payload["current_configured"] == "CSRT"
    assert payload["tracking_active"] is False


@pytest.mark.asyncio
async def test_available_trackers_exception_maps_to_legacy_http_500(monkeypatch):
    monkeypatch.setattr(
        "classes.schema_manager.get_schema_manager",
        _raises(RuntimeError("schema unavailable")),
    )

    with pytest.raises(HTTPException) as exc:
        await routes.get_available_trackers(make_handler())

    assert exc.value.status_code == 500
    assert exc.value.detail == "schema unavailable"


@pytest.mark.asyncio
async def test_current_tracker_embeds_runtime_status(schema_manager):
    handler = make_handler(
        app_controller=SimpleNamespace(
            current_tracker_type="CSRT",
            tracking_started=True,
            smart_mode_active=False,
            following_active=True,
        ),
        runtime=runtime_status(
            has_output=False,
            active_tracking=False,
            usable_for_following=False,
            data_is_stale=True,
            status="stale_output",
            consumer_guidance="stale",
            reason="tracker_output_stale",
        ),
    )

    payload = response_body(await routes.get_current_tracker(handler))

    assert payload["status"] == "tracking"
    assert payload["active"] is True
    assert payload["tracker_type"] == "CSRT"
    assert payload["display_name"] == "CSRT Display"
    assert payload["icon"] == "\U0001f3af"
    assert payload["following_active"] is True
    assert payload["has_output"] is False
    assert payload["runtime_state"] == "stale_output"
    assert payload["consumer_guidance"] == "stale"
    assert payload["runtime_reason"] == "tracker_output_stale"
    assert payload["claim_boundary"] == "process-local tracker status only"


@pytest.mark.asyncio
async def test_current_tracker_exception_maps_to_legacy_http_500(monkeypatch):
    monkeypatch.setattr(
        "classes.schema_manager.get_schema_manager",
        _raises(RuntimeError("current schema failed")),
    )

    with pytest.raises(HTTPException) as exc:
        await routes.get_current_tracker(make_handler())

    assert exc.value.status_code == 500
    assert exc.value.detail == "current schema failed"


@pytest.mark.asyncio
async def test_current_tracker_unknown_schema_preserves_error_shape(monkeypatch):
    monkeypatch.setattr(
        "classes.schema_manager.get_schema_manager",
        lambda: FakeSchemaManager(tracker_info=None),
    )
    handler = make_handler(
        app_controller=SimpleNamespace(
            current_tracker_type="UnknownTracker",
            tracking_started=False,
            smart_mode_active=False,
            following_active=False,
        ),
        runtime=runtime_status(has_output=False, active_tracking=False),
    )
    monkeypatch.setattr(
        FakeSchemaManager,
        "get_tracker_info",
        lambda self, tracker_name: None,
    )

    payload = response_body(await routes.get_current_tracker(handler))

    assert payload["status"] == "unknown"
    assert payload["active"] is False
    assert payload["tracker_type"] == "UnknownTracker"
    assert payload["error"] == 'Tracker type "UnknownTracker" not found in schema'


@pytest.mark.asyncio
async def test_switch_tracker_validation_and_success(monkeypatch):
    manager = FakeSchemaManager(valid=True)
    monkeypatch.setattr("classes.schema_manager.get_schema_manager", lambda: manager)
    app_controller = SimpleNamespace(
        current_tracker_type="CSRT",
        switch_tracker_type=AsyncMock(
            return_value={
                "success": True,
                "message": "switched",
                "requires_restart": True,
            }
        ),
    )
    handler = make_handler(app_controller=app_controller)

    payload = response_body(
        await routes.switch_tracker(handler, FakeRequest({"tracker_type": "Gimbal"}))
    )

    assert manager.validation_calls == ["Gimbal"]
    app_controller.switch_tracker_type.assert_awaited_once_with("Gimbal")
    assert payload["status"] == "success"
    assert payload["action"] == "tracker_switched"
    assert payload["old_tracker"] == "CSRT"
    assert payload["new_tracker"] == "Gimbal"
    assert payload["message"] == "switched"
    assert payload["requires_restart"] is True


@pytest.mark.asyncio
async def test_switch_tracker_missing_invalid_and_failed_result(monkeypatch):
    invalid_manager = FakeSchemaManager(valid=False)
    monkeypatch.setattr(
        "classes.schema_manager.get_schema_manager",
        lambda: invalid_manager,
    )
    app_controller = SimpleNamespace(
        current_tracker_type="CSRT",
        switch_tracker_type=AsyncMock(
            return_value={"success": False, "error": "hardware unavailable"}
        ),
    )
    handler = make_handler(app_controller=app_controller)

    with pytest.raises(HTTPException) as missing_exc:
        await routes.switch_tracker(handler, FakeRequest({}))
    with pytest.raises(HTTPException) as invalid_exc:
        await routes.switch_tracker(handler, FakeRequest({"tracker_type": "Bad"}))

    invalid_manager.valid = True
    failed = await routes.switch_tracker(
        handler,
        FakeRequest({"tracker_type": "Gimbal"}),
    )
    failed_body = response_body(failed)

    assert missing_exc.value.status_code == 400
    assert missing_exc.value.detail == "tracker_type is required"
    assert invalid_exc.value.status_code == 400
    assert invalid_exc.value.detail == "Invalid tracker Bad"
    assert failed.status_code == 500
    assert failed_body["status"] == "error"
    assert failed_body["action"] == "switch_failed"
    assert failed_body["old_tracker"] == "CSRT"
    assert failed_body["requested_tracker"] == "Gimbal"
    assert failed_body["error"] == "hardware unavailable"


@pytest.mark.asyncio
async def test_restart_tracker_rate_limit_and_success(monkeypatch):
    reload_calls = []
    monkeypatch.setattr(Parameters, "reload_config", lambda: reload_calls.append(True))
    app_controller = SimpleNamespace(
        current_tracker_type="Gimbal",
        switch_tracker_type=AsyncMock(
            return_value={"success": True, "message": "reinitialized"}
        ),
    )
    allowed_handler = make_handler(app_controller=app_controller)
    denied_handler = make_handler(
        app_controller=app_controller,
        config_rate_limiter=SimpleNamespace(is_allowed=lambda bucket: (False, 12)),
    )

    denied = await routes.restart_tracker(denied_handler)
    success = response_body(await routes.restart_tracker(allowed_handler))

    assert denied.status_code == 429
    assert denied.headers["Retry-After"] == "12"
    assert response_body(denied)["error"] == "Too many restart requests"
    assert reload_calls == [True]
    app_controller.switch_tracker_type.assert_awaited_once_with("Gimbal")
    assert success["success"] is True
    assert success["action"] == "tracker_restarted"
    assert success["tracker_type"] == "Gimbal"
    assert success["config_reloaded"] is True


@pytest.mark.asyncio
async def test_restart_tracker_failure_preserves_legacy_500(monkeypatch):
    monkeypatch.setattr(Parameters, "reload_config", lambda: None)
    handler = make_handler(
        app_controller=SimpleNamespace(
            current_tracker_type="CSRT",
            switch_tracker_type=AsyncMock(
                return_value={"success": False, "error": "restart failed"}
            ),
        )
    )

    response = await routes.restart_tracker(handler)
    payload = response_body(response)

    assert response.status_code == 500
    assert payload["success"] is False
    assert payload["action"] == "restart_failed"
    assert payload["tracker_type"] == "CSRT"
    assert payload["error"] == "restart failed"
    assert payload["config_reloaded"] is True


@pytest.mark.asyncio
async def test_restart_tracker_reload_exception_maps_to_legacy_http_500(monkeypatch):
    monkeypatch.setattr(
        Parameters,
        "reload_config",
        _raises(RuntimeError("reload failed")),
    )

    with pytest.raises(HTTPException) as exc:
        await routes.restart_tracker(make_handler())

    assert exc.value.status_code == 500
    assert exc.value.detail == "reload failed"


@pytest.mark.asyncio
async def test_current_tracker_config_reports_expected_data_type():
    handler = make_handler(
        app_controller=SimpleNamespace(
            current_tracker_type="SmartTracker",
            smart_mode_active=True,
            tracking_active=True,
            tracker=FakeTracker(),
        )
    )

    payload = response_body(await routes.get_current_tracker_config(handler))

    assert payload["configured_tracker"] == "SmartTracker"
    assert payload["smart_mode_active"] is True
    assert payload["tracking_active"] is True
    assert payload["expected_data_type"] == "BBOX_CONFIDENCE"
    assert payload["active_tracker_class"] == "FakeTracker"
    assert payload["status"] == "active"
