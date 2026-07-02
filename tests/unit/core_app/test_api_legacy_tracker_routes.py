"""Tests for legacy tracker route helper extraction."""

from __future__ import annotations

import io
import json
import logging
from dataclasses import dataclass
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


@dataclass
class FakeTrackerOutput:
    data_type: SimpleNamespace
    raw_data: dict
    payload: dict

    def to_dict(self):
        return dict(self.payload)


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
        _get_tracker_runtime_status_snapshot=(
            lambda *_args, **_kwargs: runtime or runtime_status()
        ),
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


@pytest.fixture(autouse=True)
def reset_legacy_tracker_route_usage():
    routes.reset_legacy_tracker_route_usage()
    yield
    routes.reset_legacy_tracker_route_usage()


@pytest.fixture
def schema_manager(monkeypatch):
    manager = FakeSchemaManager()
    monkeypatch.setattr(
        "classes.schema_manager.get_schema_manager",
        lambda: manager,
    )
    return manager


@pytest.mark.asyncio
async def test_legacy_tracker_routes_record_process_local_usage(schema_manager):
    handler = make_handler()

    await routes.get_available_trackers(handler)
    await routes.get_current_tracker(handler)
    await routes.get_current_tracker_config(handler)
    await routes.get_available_tracker_types(handler)

    snapshot = routes.get_legacy_tracker_route_usage_snapshot()

    assert snapshot["schema_version"] == 1
    assert snapshot["source"] == "tracker_legacy_compatibility_usage"
    assert snapshot["total_calls"] == 4
    assert snapshot["routes"]["available"]["count"] == 1
    assert snapshot["routes"]["current"]["count"] == 1
    assert snapshot["routes"]["current_config"]["count"] == 1
    assert snapshot["routes"]["available_types"]["count"] == 1
    assert snapshot["routes"]["available"]["path"] == "/api/tracker/available"
    assert (
        snapshot["routes"]["available"]["replacement_path"]
        == "/api/v1/tracking/catalog"
    )
    assert snapshot["routes"]["set_type"]["deprecated"] is True
    assert snapshot["routes"]["available"]["last_used_at"] is not None
    assert snapshot["claim_boundary"].startswith(
        "Process-local legacy tracker compatibility route usage counters"
    )


@pytest.mark.asyncio
async def test_legacy_tracker_usage_counts_attempts_and_excludes_internal_helpers(
    monkeypatch,
):
    monkeypatch.setattr(Parameters, "reload_config", lambda: None)
    manager = FakeSchemaManager(valid=True)
    monkeypatch.setattr("classes.schema_manager.get_schema_manager", lambda: manager)
    app_controller = SimpleNamespace(
        current_tracker_type="CSRT",
        switch_tracker_type=AsyncMock(return_value={"success": True}),
    )
    handler = make_handler(app_controller=app_controller)

    with pytest.raises(HTTPException):
        await routes.switch_tracker(handler, FakeRequest({}))
    await routes.switch_tracker_to_type(handler, "Gimbal")
    await routes.restart_tracker(handler, record_compatibility_usage=False)
    await routes.restart_tracker(handler)
    with pytest.raises(HTTPException):
        await routes.set_tracker_type(handler, {})

    snapshot = routes.get_legacy_tracker_route_usage_snapshot()

    assert snapshot["routes"]["switch"]["count"] == 1
    assert snapshot["routes"]["restart"]["count"] == 1
    assert snapshot["routes"]["set_type"]["count"] == 1
    assert snapshot["total_calls"] == 3
    assert app_controller.switch_tracker_type.await_count == 3


@pytest.mark.asyncio
async def test_legacy_tracker_diagnostics_record_process_local_usage(monkeypatch):
    monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: io.StringIO("{}"))
    handler = make_handler(
        app_controller=SimpleNamespace(
            tracker=FakeTracker(),
            get_tracker_output=lambda: None,
            get_tracker_capabilities=lambda: {"data_types": ["POSITION_2D"]},
            smart_mode_active=False,
        )
    )

    await routes.get_tracker_output(handler)
    await routes.get_tracker_capabilities(handler)
    await routes.get_tracker_schema(handler)
    await routes.get_current_tracker_status(handler)

    snapshot = routes.get_legacy_tracker_route_usage_snapshot()

    assert snapshot["routes"]["output"]["count"] == 1
    assert snapshot["routes"]["capabilities"]["count"] == 1
    assert snapshot["routes"]["schema"]["count"] == 1
    assert snapshot["routes"]["current_status"]["count"] == 1
    assert snapshot["routes"]["current_status"]["replacement_path"] == (
        "/api/v1/tracking/runtime-status"
    )
    assert snapshot["total_calls"] == 4


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


@pytest.mark.asyncio
async def test_available_tracker_types_returns_legacy_hardcoded_payload(monkeypatch):
    monkeypatch.setattr(routes, "AI_AVAILABLE", False)
    handler = make_handler(
        app_controller=SimpleNamespace(
            current_tracker_type="Gimbal",
            smart_mode_active=True,
            tracker=FakeTracker(),
        )
    )

    payload = response_body(await routes.get_available_tracker_types(handler))

    assert set(payload["available_trackers"]) == {
        "CSRT",
        "ParticleFilter",
        "Gimbal",
        "SmartTracker",
    }
    assert payload["available_trackers"]["CSRT"]["available"] is True
    assert payload["available_trackers"]["Gimbal"]["data_type"] == "GIMBAL_ANGLES"
    assert payload["available_trackers"]["SmartTracker"]["available"] is False
    assert (
        payload["available_trackers"]["SmartTracker"]["unavailable_reason"]
        == "AI packages (ultralytics/torch) not installed"
    )
    assert payload["current_configured"] == "Gimbal"
    assert payload["current_active"] == "FakeTracker"
    assert payload["smart_mode_active"] is True


@pytest.mark.asyncio
async def test_available_tracker_types_exception_maps_to_legacy_http_500():
    handler = make_handler(app_controller=SimpleNamespace())

    with pytest.raises(HTTPException) as exc:
        await routes.get_available_tracker_types(handler)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_set_tracker_type_validates_missing_invalid_and_ai_unavailable(monkeypatch):
    monkeypatch.setattr(routes, "AI_AVAILABLE", False)
    handler = make_handler()

    with pytest.raises(HTTPException) as missing_exc:
        await routes.set_tracker_type(handler, {})
    with pytest.raises(HTTPException) as invalid_exc:
        await routes.set_tracker_type(handler, {"tracker_type": "Bad"})
    with pytest.raises(HTTPException) as ai_exc:
        await routes.set_tracker_type(handler, {"tracker_type": "SmartTracker"})

    assert missing_exc.value.status_code == 400
    assert missing_exc.value.detail == "tracker_type is required"
    assert invalid_exc.value.status_code == 400
    assert invalid_exc.value.detail == (
        "Invalid tracker type 'Bad'. Available: "
        "['CSRT', 'ParticleFilter', 'Gimbal', 'SmartTracker']"
    )
    assert ai_exc.value.status_code == 400
    assert "SmartTracker requires AI packages" in ai_exc.value.detail


@pytest.mark.asyncio
async def test_set_tracker_type_configures_smart_and_already_smart(monkeypatch):
    monkeypatch.setattr(routes, "AI_AVAILABLE", True)
    app_controller = SimpleNamespace(
        current_tracker_type="CSRT",
        smart_mode_active=False,
        tracking_active=False,
        tracker=None,
    )
    handler = make_handler(app_controller=app_controller)

    configured = response_body(
        await routes.set_tracker_type(handler, {"tracker_type": "SmartTracker"})
    )
    already = response_body(
        await routes.set_tracker_type(handler, {"tracker_type": "SmartTracker"})
    )

    assert configured["_deprecated"] is True
    assert configured["_sunset"] == "v5.0.0"
    assert configured["action"] == "configured_smart"
    assert configured["old_tracker"] == "CSRT"
    assert configured["new_tracker"] == "SmartTracker"
    assert app_controller.smart_mode_active is True
    assert app_controller.current_tracker_type == "SmartTracker"
    assert already["action"] == "already_smart"
    assert already["message"] == "Smart tracker already active"


@pytest.mark.asyncio
async def test_set_tracker_type_smart_active_requires_restart(monkeypatch):
    monkeypatch.setattr(routes, "AI_AVAILABLE", True)
    app_controller = SimpleNamespace(
        current_tracker_type="CSRT",
        smart_mode_active=False,
        tracking_active=True,
        tracker=FakeTracker(),
    )
    handler = make_handler(app_controller=app_controller)

    payload = response_body(
        await routes.set_tracker_type(handler, {"tracker_type": "SmartTracker"})
    )

    assert payload["action"] == "smart_mode_enabled"
    assert payload["requires_restart"] is True
    assert app_controller.smart_mode_active is True
    assert app_controller.current_tracker_type == "SmartTracker"


@pytest.mark.asyncio
async def test_set_tracker_type_configures_classic_and_disables_smart_mode():
    app_controller = SimpleNamespace(
        current_tracker_type="SmartTracker",
        smart_mode_active=True,
        tracking_active=False,
        tracker=None,
    )
    handler = make_handler(app_controller=app_controller)

    payload = response_body(
        await routes.set_tracker_type(handler, {"tracker_type": "Gimbal"})
    )

    assert payload["action"] == "configured_classic"
    assert payload["old_tracker"] == "SmartTracker"
    assert payload["new_tracker"] == "Gimbal"
    assert app_controller.smart_mode_active is False
    assert app_controller.current_tracker_type == "Gimbal"


@pytest.mark.asyncio
async def test_set_tracker_type_classic_active_requires_restart():
    app_controller = SimpleNamespace(
        current_tracker_type="CSRT",
        smart_mode_active=False,
        tracking_active=True,
        tracker=FakeTracker(),
    )
    handler = make_handler(app_controller=app_controller)

    payload = response_body(
        await routes.set_tracker_type(handler, {"tracker_type": "ParticleFilter"})
    )

    assert payload["action"] == "classic_tracker_set"
    assert payload["requires_restart"] is True
    assert app_controller.current_tracker_type == "ParticleFilter"


@pytest.mark.asyncio
async def test_set_tracker_type_exception_maps_to_legacy_http_500():
    handler = make_handler()

    with pytest.raises(HTTPException) as exc:
        await routes.set_tracker_type(handler, None)

    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_tracker_output_no_method_maps_to_legacy_http_500():
    handler = make_handler(app_controller=SimpleNamespace())

    with pytest.raises(HTTPException) as exc:
        await routes.get_tracker_output(handler)

    assert exc.value.status_code == 500
    assert "Enhanced tracker schema not available" in exc.value.detail


@pytest.mark.asyncio
async def test_tracker_output_empty_and_success_payloads():
    empty_handler = make_handler(
        app_controller=SimpleNamespace(get_tracker_output=lambda: None)
    )
    tracker_output = FakeTrackerOutput(
        data_type=SimpleNamespace(value="POSITION_2D"),
        raw_data={},
        payload={
            "data_type": "POSITION_2D",
            "timestamp": 123.0,
            "tracking_active": True,
            "position_2d": (0.25, -0.1),
        },
    )
    success_handler = make_handler(
        app_controller=SimpleNamespace(get_tracker_output=lambda: tracker_output)
    )

    empty = response_body(await routes.get_tracker_output(empty_handler))
    success = response_body(await routes.get_tracker_output(success_handler))

    assert empty["error"] == "No tracker output available"
    assert empty["tracking_active"] is False
    assert success["data_type"] == "POSITION_2D"
    assert success["position_2d"] == [0.25, -0.1]
    assert success["api_version"] == "2.0"
    assert success["schema_version"] == "flexible"


@pytest.mark.asyncio
async def test_tracker_capabilities_legacy_fallbacks_and_success():
    no_method = make_handler(app_controller=SimpleNamespace())
    no_caps = make_handler(
        app_controller=SimpleNamespace(
            tracker=None,
            get_tracker_capabilities=lambda: None,
        )
    )
    success = make_handler(
        app_controller=SimpleNamespace(
            tracker=FakeTracker(),
            get_tracker_capabilities=lambda: {"data_types": ["POSITION_2D"]},
        )
    )

    no_method_payload = response_body(await routes.get_tracker_capabilities(no_method))
    no_caps_payload = response_body(await routes.get_tracker_capabilities(no_caps))
    success_payload = response_body(await routes.get_tracker_capabilities(success))

    assert no_method_payload == {
        "error": "Capabilities API not available",
        "legacy_mode": True,
    }
    assert no_caps_payload == {
        "error": "No active tracker",
        "tracker_active": False,
    }
    assert success_payload["tracker_capabilities"] == {"data_types": ["POSITION_2D"]}
    assert success_payload["system_info"]["tracker_active"] is True
    assert success_payload["system_info"]["tracker_class"] == "FakeTracker"
    assert success_payload["system_info"]["api_version"] == "2.0"


@pytest.mark.asyncio
async def test_tracker_capabilities_exception_maps_to_legacy_http_500():
    handler = make_handler(
        app_controller=SimpleNamespace(
            get_tracker_capabilities=_raises(RuntimeError("capabilities failed"))
        )
    )

    with pytest.raises(HTTPException) as exc:
        await routes.get_tracker_capabilities(handler)

    assert exc.value.status_code == 500
    assert exc.value.detail == "capabilities failed"


@pytest.mark.asyncio
async def test_tracker_schema_loads_yaml_and_errors(monkeypatch):
    import io

    opened_paths = []

    def fake_open(path, mode):
        opened_paths.append((path, mode))
        return io.StringIO("schema_version: test\ntrackers:\n  CSRT: {}\n")

    monkeypatch.setattr("builtins.open", fake_open)
    payload = response_body(await routes.get_tracker_schema(make_handler()))

    assert opened_paths == [("configs/tracker_schemas.yaml", "r")]
    assert payload == {"schema_version": "test", "trackers": {"CSRT": {}}}

    monkeypatch.setattr(
        "builtins.open",
        _raises(OSError("schema missing")),
    )
    with pytest.raises(HTTPException) as exc:
        await routes.get_tracker_schema(make_handler())

    assert exc.value.status_code == 500
    assert exc.value.detail == "schema missing"


@pytest.mark.asyncio
async def test_current_tracker_status_without_output_uses_runtime_snapshot():
    handler = make_handler(
        app_controller=SimpleNamespace(
            get_tracker_output=lambda: None,
            smart_mode_active=True,
        ),
        runtime=runtime_status(
            has_output=False,
            active_tracking=False,
            usable_for_following=False,
            data_is_stale=False,
            status="no_output",
            consumer_guidance="wait",
            reason="tracker_not_started",
        ),
    )

    payload = response_body(await routes.get_current_tracker_status(handler))

    assert payload["active"] is False
    assert payload["active_tracking"] is False
    assert payload["has_output"] is False
    assert payload["usable_for_following"] is False
    assert payload["status"] == "no_output"
    assert payload["consumer_guidance"] == "wait"
    assert payload["tracker_type"] is None
    assert payload["data_type"] is None
    assert payload["fields"] == {}
    assert payload["smart_mode"] is True
    assert payload["inference"] is None
    assert payload["claim_boundary"] == "process-local tracker status only"


@pytest.mark.asyncio
async def test_current_tracker_status_formats_output_fields_and_inference():
    tracker_output = FakeTrackerOutput(
        data_type=SimpleNamespace(value="GIMBAL_ANGLES"),
        raw_data={
            "tracking_status": "ACTIVE_TRACKING",
            "system": "NED",
            "provider": "sip_udp",
            "yaw": 12.5,
            "data_is_stale": False,
        },
        payload={
            "data_type": "GIMBAL_ANGLES",
            "timestamp": 123.0,
            "tracking_active": True,
            "tracker_id": "gimbal",
            "metadata": {"ignored": True},
            "position_2d": (0.2, -0.1),
            "angular": (12.5, -3.0, 0.0),
            "normalized_bbox": (0.1, 0.2, 0.3, 0.4),
            "confidence": 0.8,
            "velocity": (1.0, 2.0),
            "raw_data": {
                "provider": "sip_udp",
            },
        },
    )
    smart_tracker = SimpleNamespace(get_runtime_info=lambda: {"fps": 12.0})
    handler = make_handler(
        app_controller=SimpleNamespace(
            tracker=FakeTracker(),
            get_tracker_output=lambda: tracker_output,
            smart_mode_active=True,
            smart_tracker=smart_tracker,
        ),
        runtime=runtime_status(status="active_usable", reason="fresh"),
    )

    payload = response_body(await routes.get_current_tracker_status(handler))

    assert payload["active"] is True
    assert payload["tracker_type"] == "FakeTracker"
    assert payload["data_type"] == "GIMBAL_ANGLES"
    assert payload["smart_mode"] is True
    assert payload["inference"] == {"fps": 12.0}
    assert payload["raw_data"]["tracking_status"] == "ACTIVE_TRACKING"
    assert payload["fields"]["position_2d"]["type"] == "position_2d"
    assert payload["fields"]["angular"]["type"] == "angular_3d"
    assert payload["fields"]["angular"]["units"] == "\u00b0"
    assert payload["fields"]["normalized_bbox"]["units"] == "normalized"
    assert payload["fields"]["confidence"]["range"] == [0.0, 1.0]
    assert payload["fields"]["velocity"]["components"] == ["vx", "vy"]
    assert payload["fields"]["tracking_status"]["status_color"] == "success"
    assert payload["fields"]["system"]["type"] == "coordinate_system"
    assert payload["fields"]["provider"]["type"] == "str"
    assert payload["runtime_status"]["status"] == "active_usable"


@pytest.mark.asyncio
async def test_current_tracker_status_inference_failure_is_nonfatal():
    tracker_output = FakeTrackerOutput(
        data_type=SimpleNamespace(value="POSITION_2D"),
        raw_data={},
        payload={
            "data_type": "POSITION_2D",
            "timestamp": 123.0,
            "tracking_active": True,
            "position_2d": (0.2, -0.1),
        },
    )
    smart_tracker = SimpleNamespace(
        get_runtime_info=_raises(RuntimeError("runtime info failed"))
    )
    handler = make_handler(
        app_controller=SimpleNamespace(
            tracker=None,
            get_tracker_output=lambda: tracker_output,
            smart_mode_active=True,
            smart_tracker=smart_tracker,
        )
    )

    payload = response_body(await routes.get_current_tracker_status(handler))

    assert payload["tracker_type"] == "Unknown"
    assert payload["inference"] is None


@pytest.mark.asyncio
async def test_current_tracker_status_exception_maps_to_legacy_http_500():
    handler = make_handler(
        app_controller=SimpleNamespace(
            get_tracker_output=_raises(RuntimeError("status failed"))
        )
    )

    with pytest.raises(HTTPException) as exc:
        await routes.get_current_tracker_status(handler)

    assert exc.value.status_code == 500
    assert exc.value.detail == "status failed"
