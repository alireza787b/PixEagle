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


def make_handler(
    *,
    app_controller=None,
    config_rate_limiter=None,
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
async def test_typed_action_helpers_do_not_expose_legacy_route_counters(monkeypatch):
    monkeypatch.setattr(Parameters, "reload_config", lambda: None)
    manager = FakeSchemaManager(valid=True)
    monkeypatch.setattr("classes.schema_manager.get_schema_manager", lambda: manager)
    app_controller = SimpleNamespace(
        current_tracker_type="CSRT",
        switch_tracker_type=AsyncMock(return_value={"success": True}),
    )
    handler = make_handler(app_controller=app_controller)

    await routes.switch_tracker_to_type(handler, "Gimbal")
    await routes.restart_tracker(handler)

    assert not hasattr(routes, "get_legacy_tracker_route_usage_snapshot")
    assert not hasattr(routes, "reset_legacy_tracker_route_usage")
    assert not hasattr(routes, "record_legacy_tracker_route_usage")
    assert not hasattr(routes, "LEGACY_TRACKER_ROUTE_METADATA")
    assert app_controller.switch_tracker_type.await_count == 2


@pytest.mark.asyncio
async def test_switch_tracker_to_type_validation_and_success(monkeypatch):
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

    payload = response_body(await routes.switch_tracker_to_type(handler, "Gimbal"))

    assert manager.validation_calls == ["Gimbal"]
    app_controller.switch_tracker_type.assert_awaited_once_with("Gimbal")
    assert payload["status"] == "success"
    assert payload["action"] == "tracker_switched"
    assert payload["old_tracker"] == "CSRT"
    assert payload["new_tracker"] == "Gimbal"
    assert payload["message"] == "switched"
    assert payload["requires_restart"] is True


@pytest.mark.asyncio
async def test_switch_tracker_to_type_missing_invalid_and_failed_result(monkeypatch):
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
        await routes.switch_tracker_to_type(handler, None)
    with pytest.raises(HTTPException) as invalid_exc:
        await routes.switch_tracker_to_type(handler, "Bad")

    invalid_manager.valid = True
    failed = await routes.switch_tracker_to_type(handler, "Gimbal")
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
