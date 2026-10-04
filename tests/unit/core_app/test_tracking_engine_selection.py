"""Native engine round trips use shared tracker lifecycle and no hardware IO."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Response

from classes.app_controller import AppController
from classes.api_v1_contracts import APITrackerSwitchRequest
from classes.api_v1_native_targets import TARGET_SCOPES, native_target_action, target_state
from classes.api_security_types import APIPrincipal
from classes.parameters import Parameters
from classes.camera_runtime import CameraRuntime
from tests.unit.core_app.test_native_target_operations import owner as target_owner


pytestmark = pytest.mark.unit


def manual_gesture():
    manual = SimpleNamespace(active=True, snapshot=lambda: {"reason": None})

    def stop(**_):
        manual.active = False
        return True, manual.snapshot()

    manual.stop = Mock(side_effect=stop)
    return manual


@pytest.fixture
def owner(target_owner, monkeypatch):
    app = AppController.__new__(AppController)
    app.__dict__.update(vars(target_owner.app_controller))
    target_owner.app_controller = app
    app.current_tracker_type = "KCF"
    app.video_handler = SimpleNamespace(width=96, height=96)
    app.detector = None
    app.setpoint_sender = None
    app.control = SimpleNamespace(selection_mode="classic")
    app.tracker = SimpleNamespace(is_external_tracker=False, stop_tracking=Mock(), reset=Mock())
    monkeypatch.setattr(Parameters, "DEFAULT_TRACKING_ALGORITHM", "KCF")
    monkeypatch.setattr(Parameters, "SmartTracker", {"SMART_TRACKER_GPU_MODEL_PATH": "models/selected-model.pt"})
    monkeypatch.setattr("classes.app_controller.SMART_TRACKER_AVAILABLE", True)
    monkeypatch.setattr("classes.app_controller.SmartTracker",
                        lambda **kwargs: SimpleNamespace(clear_selection=Mock(),
                            model_path=Parameters.SmartTracker["SMART_TRACKER_GPU_MODEL_PATH"]))

    def create(factory_key, *_):
        tracker = SimpleNamespace(is_external_tracker=factory_key == "Gimbal",
                                  stop_tracking=Mock(), reset=Mock(), monitoring_active=False,
                                  gimbal_provider=SimpleNamespace(manual_control=app.control))
        tracker.start_tracking = lambda *_: setattr(tracker, "monitoring_active", True)
        return tracker

    monkeypatch.setattr("classes.app_controller.create_tracker", create)
    monkeypatch.setattr("classes.api_v1_native_targets.classic_tracker_availability",
                        lambda _: dict(available=True, reason=None))
    monkeypatch.setattr("classes.api_v1_native_targets.external_selection_availability",
                        lambda _: dict(available=True, reason=None))
    monkeypatch.setattr("classes.api_v1_native_targets.get_gimbal_control_status",
                        lambda _: dict(available=True, enabled=True, connected=True,
                                       tracking_state="disabled", selection_mode=app.control.selection_mode,
                                       capabilities=["select", "cancel", "set_mode"]))

    async def restore_camera(_, request, **kwargs):
        assert app._follower_state_lock.locked()
        app.control.selection_mode = request.selection_mode
        return dict(success=True)

    target_owner.restore_camera = AsyncMock(side_effect=restore_camera)
    monkeypatch.setattr("classes.gimbal_control.execute_gimbal_control", target_owner.restore_camera)
    return target_owner


async def switch(owner, tracker, *, restore=False, dry_run=False, persist=False, attempt="first"):
    request = APITrackerSwitchRequest(
        tracker_type=tracker, restore_engine_selection=restore, confirm=True, dry_run=dry_run, persist=persist,
        idempotency_key=f"switch-{tracker}-{owner.app_controller._tracking_session_generation}-{restore}-{persist}-{attempt}",
        native_context=dict(binding_mode="companion_only", guard=target_state(owner, owner.principal_test)["guard"]),
    )
    return await native_target_action(owner, request, Response(),
                                     SimpleNamespace(state=SimpleNamespace(api_principal=owner.principal_test)),
                                     "tracker_switch")


async def test_smart_camera_local_roundtrip_restores_local_tracker_and_smart_mode(owner):
    app = owner.app_controller
    app.smart_mode_active = True
    app.smart_tracker = SimpleNamespace(clear_selection=Mock())
    saved_model = dict(Parameters.SmartTracker)
    result = await switch(owner, "Gimbal", restore=True)
    assert result["status"] == "success"
    assert not app.smart_mode_active and app.tracker.is_external_tracker
    result = await switch(owner, "CSRT", restore=True)
    assert result["status"] == "success"
    assert app.current_tracker_type == "KCFKalmanTracker"
    assert app.smart_mode_active
    assert Parameters.SmartTracker == saved_model
    assert app.smart_tracker.model_path == saved_model["SMART_TRACKER_GPU_MODEL_PATH"]


async def test_camera_mode_restored_without_old_target_and_explicit_tracker_wins(owner):
    app = owner.app_controller
    await switch(owner, "Gimbal", restore=True)
    app.control.selection_mode = "smart"
    await switch(owner, "CSRT", restore=False)
    assert app.current_tracker_type == "CSRTTracker"
    result = await switch(owner, "Gimbal", restore=True)
    assert result["status"] == "success"
    owner.restore_camera.assert_awaited_once()
    assert owner.restore_camera.call_args.args[1].selection_mode == "smart"
    assert not app.tracking_started


async def test_engine_restore_dry_run_keeps_current_mode_and_memory(owner):
    app = owner.app_controller
    result = await switch(owner, "Gimbal", restore=True, dry_run=True)
    assert result["status"] == "validated"
    assert app.current_tracker_type == "KCF"
    assert not hasattr(app, "_tracking_engine_selections")
    owner.restore_camera.assert_not_called()


async def test_unavailable_remembered_tracker_refuses_without_silent_fallback(owner, monkeypatch):
    app = owner.app_controller
    await switch(owner, "Gimbal", restore=True)
    monkeypatch.setattr("classes.api_v1_native_targets.classic_tracker_availability",
                        lambda _: dict(available=False, reason="Previously selected tracker is unavailable"))
    result = await switch(owner, "CSRT", restore=True)
    assert result.status_code == 409
    assert app.current_tracker_type == "GimbalTracker"


@pytest.mark.parametrize("extra", [{}, {"persist": True}])
def test_restore_flag_requires_native_context(extra):
    with pytest.raises(ValueError, match="Engine restoration"):
        APITrackerSwitchRequest(tracker_type="CSRT", restore_engine_selection=True, **extra)


async def test_advanced_engine_switch_applies_and_saves_through_native_guard(owner, monkeypatch):
    owner.principal_test = APIPrincipal.bearer(
        subject="operator-a", token_id="a", scopes=TARGET_SCOPES | {"config:write"},
    )
    saved = Mock(return_value={"saved_value": "Gimbal"})
    monkeypatch.setattr("classes.api_legacy_tracker_routes._persist_tracker_selection", saved)
    result = await switch(owner, "Gimbal", restore=True, persist=True)
    assert result["status"] == "success"
    assert result["result"]["legacy_result"]["runtime_applied"] is True
    assert result["result"]["legacy_result"]["saved"] is True
    saved.assert_called_once_with(owner, "Gimbal")


async def test_advanced_engine_reports_partial_state_when_save_fails(owner, monkeypatch):
    owner.principal_test = APIPrincipal.bearer(
        subject="operator-a", token_id="a", scopes=TARGET_SCOPES | {"config:write"},
    )
    monkeypatch.setattr("classes.api_legacy_tracker_routes._persist_tracker_selection",
                        Mock(side_effect=RuntimeError("disk failed")))
    result = await switch(owner, "Gimbal", restore=True, persist=True)
    assert result["status"] == "failure"
    assert result["result"]["legacy_result"]["runtime_applied"] is True
    assert result["result"]["legacy_result"]["saved"] is False
    assert "disk failed" not in str(result)


async def test_retry_save_keeps_current_target_and_manual_control(owner, monkeypatch):
    owner.principal_test = APIPrincipal.bearer(
        subject="operator-a", token_id="a", scopes=TARGET_SCOPES | {"config:write"},
    )
    saved = Mock(side_effect=[RuntimeError("disk failed"), {"saved_value": "Gimbal"}])
    monkeypatch.setattr("classes.api_legacy_tracker_routes._persist_tracker_selection", saved)
    first = await switch(owner, "Gimbal", restore=True, persist=True)
    assert first["status"] == "failure"
    app = owner.app_controller
    app.tracking_started = True
    runtime = app.camera_runtime = CameraRuntime(app, {"ENABLED": False})
    runtime._manual = manual_gesture()
    retry = await switch(owner, "Gimbal", restore=True, persist=True, attempt="retry")
    assert retry["status"] == "success"
    assert retry["result"]["legacy_result"]["saved"] is True
    assert app.tracking_started
    runtime._manual.stop.assert_not_called()
    assert saved.call_count == 2


async def test_valid_engine_change_stops_manual_motion_and_reserves_entire_mutation(owner, monkeypatch):
    app = owner.app_controller
    runtime = app.camera_runtime = CameraRuntime(app, {"ENABLED": False})
    manual = runtime._manual = manual_gesture()
    original = app._switch_tracker_type_with_follower_barrier

    def checked_switch(tracker):
        assert runtime._lifecycle_users > 0
        assert manual.active is False
        return original(tracker)

    monkeypatch.setattr(app, "_switch_tracker_type_with_follower_barrier", checked_switch)
    result = await switch(owner, "Gimbal", restore=True)
    assert result["status"] == "success"
    manual.stop.assert_called_once_with(reason="lifecycle_changed")
    assert runtime._lifecycle_users == 0


async def test_engine_dry_run_does_not_interrupt_manual_camera_motion(owner):
    app = owner.app_controller
    runtime = app.camera_runtime = CameraRuntime(app, {"ENABLED": False})
    runtime._manual = manual_gesture()
    result = await switch(owner, "Gimbal", restore=True, dry_run=True)
    assert result["status"] == "validated"
    runtime._manual.stop.assert_not_called()
    assert runtime._lifecycle_users == 0


async def test_camera_engine_cannot_accidentally_enable_local_smart(owner):
    await switch(owner, "Gimbal", restore=True)
    assert owner.app_controller.toggle_smart_mode() is False
    assert not owner.app_controller.smart_mode_active
    assert "PixEagle tracking engine" in owner.app_controller.last_smart_mode_error


async def test_follow_start_reports_manual_control_conflict_before_aircraft_commands(owner, monkeypatch):
    app = owner.app_controller
    runtime = app.camera_runtime = CameraRuntime(app, {"ENABLED": False})
    runtime._manual = manual_gesture()
    app._is_command_preview_configured = lambda: False
    monkeypatch.setattr(Parameters, "FOLLOWER_MODE", "mc_velocity_chase")
    result = await app.connect_px4()
    assert result["precondition"]["code"] == "camera_control_active"
    assert result["errors"]
    app.px4_interface.connect.assert_not_called()
    runtime._manual.stop.assert_not_called()
    assert runtime._lifecycle_users == 0


async def test_stale_engine_request_does_not_stop_current_camera_gesture(owner):
    app = owner.app_controller
    runtime = app.camera_runtime = CameraRuntime(app, {"ENABLED": False})
    runtime._manual = manual_gesture()
    request = APITrackerSwitchRequest(
        tracker_type="Gimbal", restore_engine_selection=True, confirm=True, idempotency_key="stale-engine",
        native_context=dict(binding_mode="companion_only", guard=target_state(owner, owner.principal_test)["guard"]),
    )
    app._tracking_session_generation += 1
    result = await native_target_action(owner, request, Response(),
                                       SimpleNamespace(state=SimpleNamespace(api_principal=owner.principal_test)),
                                       "tracker_switch")
    assert result.status_code == 409
    runtime._manual.stop.assert_not_called()


async def test_unconfirmed_camera_stop_blocks_engine_mutation_with_actionable_conflict(owner):
    app = owner.app_controller
    runtime = app.camera_runtime = CameraRuntime(app, {"ENABLED": False})
    runtime._manual = manual_gesture()
    runtime._manual.snapshot = lambda: {"reason": "stop_transmission_failed"}
    result = await switch(owner, "Gimbal", restore=True)
    assert result.status_code == 409
    assert b"camera_control_active" in result.body
    assert app.current_tracker_type == "KCF"
