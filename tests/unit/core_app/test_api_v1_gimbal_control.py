"""Camera API contracts and action guards; no sockets or hardware involved."""

import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import Response
from pydantic import ValidationError
import pytest

from classes import api_v1_actions as actions
from classes.api_v1_contracts import APIGimbalControlRequest, APIGimbalControlStatus, APIActionResponse
from classes.api_v1_paths import (
    API_V1_ACTION_GIMBAL_CONTROL_PATH, API_V1_GIMBAL_CONTROL_PATH,
    uses_typed_api_error_envelope,
)
from classes.api_v1_read_routes import get_gimbal_control_status
from classes.gimbal_motion import SIP_MOTION_SETTINGS


@pytest.fixture
def setup_camera(monkeypatch):
    snapshot = dict(enabled=True, available=True, connected=True,
                    following_active=False, tracking_state="disabled",
                    capabilities=["select", "cancel", "pan", "tilt", "roll", "zoom", "home", "stop", "set_mode"],
                    reason=None)
    executor = AsyncMock(return_value=dict(success=True, message="Command sent."))
    # Isolate API tests from camera implementation and its provider dependencies.
    monkeypatch.setitem(sys.modules, "classes.gimbal_control", SimpleNamespace(
        get_gimbal_control_status=lambda app: dict(snapshot),
        execute_gimbal_control=executor,
    ))
    store = actions.ApiActionStore()
    owner = SimpleNamespace(app_controller=SimpleNamespace(following_active=False),
                            _api_action_store=store)
    owner._action_lock_for_key = store.action_lock_for_key
    owner._lookup_idempotent_action = store.lookup_idempotent_action
    owner._new_api_action_record = actions.new_api_action_record
    owner._store_action_record = store.store_action_record

    def reject(code, **kwargs):
        return actions.build_action_precondition_failed_response(
            store=store, code=code, message=code,
            following_active=snapshot["following_active"], **kwargs,
        )
    owner._confirmation_required_response = lambda **kw: reject("ACTION_CONFIRMATION_REQUIRED", **kw)
    owner._idempotency_key_required_response = lambda **kw: reject("ACTION_IDEMPOTENCY_KEY_REQUIRED", **kw)
    return owner, snapshot, executor


@pytest.mark.parametrize("payload", [
    {"operation": "select"}, {"operation": "select", "x": 0.2},
    {"operation": "select", "x": float("nan"), "y": 0.5},
    {"operation": "select", "x": 1.01, "y": 0.5},
    {"operation": "select", "x": 0.5, "y": float("inf")},
    {"operation": "select", "x": 0.5, "y": 0.5, "direction": 1},
    {"operation": "pan"}, {"operation": "tilt", "direction": 0},
    {"operation": "zoom", "direction": 1, "x": 0.5},
    {"operation": "home", "x": 0.5}, {"operation": "unknown", "direction": 1},
    {"operation": "roll"}, {"operation": "roll", "direction": 0},
    {"operation": "roll", "direction": 1, "x": 0.5},
    {"operation": "stop", "duration": 1000},
])
def test_invalid_control_arguments_rejected(payload):
    with pytest.raises(ValidationError):
        APIGimbalControlRequest(**payload)


@pytest.mark.parametrize("fields", [
    {"speed_deg_s": 0}, {"speed_deg_s": 100}, {"speed_deg_s": 1.5},
    {"speed_deg_s": "10"}, {"speed_deg_s": True}, {"speed_deg_s": None},
    {"duration_ms": 49}, {"duration_ms": 1001}, {"duration_ms": float("nan")},
    {"duration_ms": None},
])
def test_invalid_movement_fields_rejected(fields):
    with pytest.raises(ValidationError):
        APIGimbalControlRequest(operation="pan", direction=1, **fields)


@pytest.mark.parametrize("operation", ["zoom", "cancel", "stop", "home", "set_mode", "select"])
def test_movement_fields_are_exclusive_to_axes(operation):
    with pytest.raises(ValidationError):
        APIGimbalControlRequest(operation=operation, speed_deg_s=10)


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("settings,fields", [
    (None, {"speed_deg_s": 10}),
    (SIP_MOTION_SETTINGS, {"speed_deg_s": 31}),
    (SIP_MOTION_SETTINGS, {"duration_ms": 99}),
])
async def test_provider_motion_bounds_apply_to_preview_and_execution(setup_camera, dry_run, settings, fields):
    owner, snapshot, executor = setup_camera
    snapshot["motion_settings"] = settings
    result = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation="pan", direction=1, dry_run=dry_run, confirm=True, idempotency_key="motion-bound", **fields,
    ), Response())
    assert result.status_code == 409
    executor.assert_not_called()


async def test_custom_movement_audit_and_idempotency(setup_camera):
    owner, snapshot, executor = setup_camera
    snapshot["motion_settings"] = SIP_MOTION_SETTINGS
    assert APIGimbalControlStatus(**snapshot).motion_settings.max_duration_ms == 1000
    request = APIGimbalControlRequest(operation="roll", direction=-1, speed_deg_s=20,
                                     duration_ms=500, confirm=True, idempotency_key="custom-step")
    first = await actions.gimbal_control_action(owner, request, Response())
    second = await actions.gimbal_control_action(owner, request, Response())
    assert first["result"]["speed_deg_s"] == 20
    assert first["result"]["duration_ms"] == 500
    assert second["idempotent_replay"]
    executor.assert_awaited_once_with(owner.app_controller, request)


@pytest.mark.parametrize("geometry", [
    {"width": .2}, {"width": None, "height": None},
    {"width": .2, "height": 0}, {"width": .2, "height": float("inf")},
    {"width": .9, "height": .2},
])
def test_invalid_rectangle_rejected(geometry):
    with pytest.raises(ValidationError):
        APIGimbalControlRequest(operation="select", x=.3, y=.4, **geometry)


@pytest.mark.parametrize("operation", ["cancel", "stop", "home", "pan", "set_mode"])
def test_rectangle_fields_rejected_for_other_operations(operation):
    with pytest.raises(ValidationError):
        APIGimbalControlRequest(operation=operation, width=.2, height=.1,
                               direction=1 if operation == "pan" else None,
                               selection_mode="classic" if operation == "set_mode" else None)


async def test_rectangle_dimensions_survive_action_and_replay(setup_camera):
    owner, _, executor = setup_camera
    request = APIGimbalControlRequest(operation="select", x=.3, y=.4, width=.2, height=.1,
                                     confirm=True, idempotency_key="rectangle")
    first = await actions.gimbal_control_action(owner, request, Response())
    second = await actions.gimbal_control_action(owner, request, Response())
    assert first["status"] == "success"
    assert first["result"]["width"] == .2
    assert first["result"]["height"] == .1
    assert second["idempotent_replay"]
    executor.assert_awaited_once_with(owner.app_controller, request)


@pytest.mark.parametrize("dry_run", [False, True])
async def test_smart_rectangle_rejected_before_execution(setup_camera, dry_run):
    owner, snapshot, executor = setup_camera
    snapshot["selection_mode"] = "smart"
    result = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation="select", x=.5,y=.5,width=.2,height=.1, confirm=True,
        idempotency_key="smart-rectangle", dry_run=dry_run,
    ), Response())
    assert result.status_code == 409
    executor.assert_not_called()


async def test_status_and_dry_run_send_nothing(setup_camera):
    owner, snapshot, executor = setup_camera
    assert await get_gimbal_control_status(owner) == snapshot
    response = Response()
    result = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation="select", x=0, y=1, dry_run=True,
    ), response)
    assert response.status_code == 200
    assert result["status"] == "validated"
    assert not result["executed"]
    APIActionResponse(**result)
    executor.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"enabled": False, "available": False},
    {"connected": False, "available": False},
    {"following_active": True, "available": False},
    {"capabilities": ["stop"]},
])
async def test_dry_run_rejects_unavailable_without_sending(setup_camera, overrides):
    owner, snapshot, executor = setup_camera
    snapshot.update(overrides)
    result = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation="select", x=0.4, y=0.5, dry_run=True,
    ), Response())
    assert result.status_code == 409
    assert json.loads(result.body)["code"] == "gimbal_control_unavailable"
    executor.assert_not_called()
    assert len(owner._api_action_store.records) == 1


@pytest.mark.parametrize("confirm,key,code", [
    (False, None, "ACTION_CONFIRMATION_REQUIRED"),
    (True, None, "ACTION_IDEMPOTENCY_KEY_REQUIRED"),
])
async def test_execution_requires_confirmation_and_key(setup_camera, confirm, key, code):
    owner, _, executor = setup_camera
    result = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation="home", confirm=confirm, idempotency_key=key,
    ), Response())
    assert result.status_code == 409
    assert json.loads(result.body)["code"] == code
    executor.assert_not_called()


async def test_concurrent_replay_sends_only_once(setup_camera):
    owner, _, executor = setup_camera
    request = APIGimbalControlRequest(operation="select", x=0.3, y=0.7,
                                     confirm=True, idempotency_key="same-click")
    first, second = await asyncio.gather(*[
        actions.gimbal_control_action(owner, request, Response()) for _ in range(2)
    ])
    assert first["action_id"] == second["action_id"]
    assert second["idempotent_replay"]
    assert first["result"]["x"] == 0.3
    APIActionResponse(**first)
    executor.assert_awaited_once_with(owner.app_controller, request)


async def test_failure_is_audited_and_replayed_without_repeat(setup_camera):
    owner, _, executor = setup_camera
    executor.return_value = dict(success=False, message="Readiness timed out.")
    request = APIGimbalControlRequest(operation="home", confirm=True, idempotency_key="failed")
    first = await actions.gimbal_control_action(owner, request, Response())
    second = await actions.gimbal_control_action(owner, request, Response())
    assert first["status"] == "failure"
    assert first["error"] == "Readiness timed out."
    assert second["idempotent_replay"]
    executor.assert_awaited_once()


async def test_following_allows_only_movement_stop(setup_camera):
    owner, snapshot, executor = setup_camera
    snapshot.update(following_active=True, available=False)
    for operation in ("cancel", "home"):
        rejected = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
            operation=operation, confirm=True, idempotency_key=operation,
        ), Response())
        assert rejected.status_code == 409
    accepted = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation="stop", confirm=True, idempotency_key="stop",
    ), Response())
    assert accepted["status"] == "success"
    executor.assert_awaited_once()


def test_both_routes_use_structured_errors():
    assert uses_typed_api_error_envelope(API_V1_GIMBAL_CONTROL_PATH)
    assert uses_typed_api_error_envelope(API_V1_ACTION_GIMBAL_CONTROL_PATH)


@pytest.mark.parametrize("overrides", [
    {"enabled": False}, {"capabilities": []},
])
async def test_following_stop_still_requires_enabled_supported_camera(setup_camera, overrides):
    owner, snapshot, executor = setup_camera
    snapshot.update(following_active=True, available=False, **overrides)
    result = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation="stop", confirm=True, idempotency_key="stop",
    ), Response())
    assert result.status_code == 409
    executor.assert_not_called()


@pytest.mark.parametrize("operation,following", [("stop", True), ("cancel", False)])
async def test_abort_attempts_transport_when_telemetry_disconnected(setup_camera, operation, following):
    owner, snapshot, executor = setup_camera
    snapshot.update(connected=False, available=False, following_active=following)
    executor.return_value = dict(success=False, message="Transport unavailable.")
    result = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation=operation, confirm=True, idempotency_key=operation,
    ), Response())
    assert result["status"] == "failure"
    assert result["error"] == "Transport unavailable."
    executor.assert_awaited_once()


@pytest.mark.parametrize("direction", [-1, 1])
async def test_roll_dispatches_direction_through_action_contract(setup_camera, direction):
    owner, _, executor = setup_camera
    request = APIGimbalControlRequest(
        operation="roll", direction=direction, confirm=True, idempotency_key="roll",
    )
    result = await actions.gimbal_control_action(owner, request, Response())
    assert result["status"] == "success"
    assert result["result"]["operation"] == "roll"
    assert result["result"]["direction"] == direction
    executor.assert_awaited_once_with(owner.app_controller, request)


@pytest.mark.parametrize("payload", [
    {"operation": "set_mode"},
    {"operation": "set_mode", "selection_mode": None},
    {"operation": "set_mode", "selection_mode": "unknown"},
    {"operation": "set_mode", "selection_mode": "smart", "x": 0.5},
    {"operation": "set_mode", "selection_mode": "smart", "direction": 1},
    {"operation": "select", "x": 0.5, "y": 0.5, "selection_mode": "smart"},
    {"operation": "cancel", "selection_mode": "classic"},
    {"operation": "stop", "selection_mode": None},
])
def test_mode_change_arguments_are_exclusive(payload):
    with pytest.raises(ValidationError):
        APIGimbalControlRequest(**payload)


@pytest.mark.parametrize("mode", ["classic", "smart"])
async def test_mode_change_uses_action_replay_and_provider_intent(setup_camera, mode):
    owner, snapshot, executor = setup_camera
    snapshot["selection_mode"] = mode
    status = APIGimbalControlStatus(**await get_gimbal_control_status(owner))
    assert status.selection_mode == mode
    request = APIGimbalControlRequest(
        operation="set_mode", selection_mode=mode, confirm=True,
        idempotency_key="camera-mode",
    )
    first = await actions.gimbal_control_action(owner, request, Response())
    second = await actions.gimbal_control_action(owner, request, Response())
    assert first["status"] == "success"
    assert second["idempotent_replay"]
    assert first["result"]["camera_status"]["selection_mode"] == mode
    assert first["result"]["selection_mode"] == mode
    executor.assert_awaited_once_with(owner.app_controller, request)


async def test_camera_mode_status_defaults_to_classic(setup_camera):
    owner, _, _ = setup_camera
    assert APIGimbalControlStatus(**await get_gimbal_control_status(owner)).selection_mode == "classic"


@pytest.mark.parametrize("dry_run", [False, True])
async def test_mode_change_blocked_while_following(setup_camera, dry_run):
    owner, snapshot, executor = setup_camera
    snapshot.update(following_active=True, available=False)
    result = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation="set_mode", selection_mode="smart", dry_run=dry_run,
        confirm=True, idempotency_key="camera-mode",
    ), Response())
    assert result.status_code == 409
    executor.assert_not_called()


async def test_mode_change_dry_run_sends_nothing(setup_camera):
    owner, _, executor = setup_camera
    result = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation="set_mode", selection_mode="smart", dry_run=True,
    ), Response())
    assert result["status"] == "validated"
    assert not result["executed"]
    executor.assert_not_called()


async def test_mode_change_requires_provider_capability(setup_camera):
    owner, snapshot, executor = setup_camera
    snapshot["capabilities"].remove("set_mode")
    result = await actions.gimbal_control_action(owner, APIGimbalControlRequest(
        operation="set_mode", selection_mode="smart", confirm=True,
        idempotency_key="camera-mode",
    ), Response())
    assert result.status_code == 409
    executor.assert_not_called()
