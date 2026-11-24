"""Camera-only replay of stock MAVLink VTOL states and provider Home."""

import copy
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import requests

from classes.aircraft_state import AirframePhase
from classes.api_v1_contracts import APIGimbalControlStatus
from classes.camera_runtime import CameraRuntime
from classes.config_service import ConfigService
from classes.gimbal_control import get_gimbal_control_status
from classes.gimbal_transition_view import CameraPhaseObserver, CameraPhaseSample, transition_home_enabled
from classes.gimbal_types import CoordinateSystem, GimbalAngles, GimbalData, TrackingState, TrackingStatus
from classes.mavlink_data_manager import MavlinkDataManager


MC, FW, TRANSITION = AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING, AirframePhase.VTOL_TRANSITION
SETTINGS = {"ENABLED": True, "CONTROL_ENABLED": True, "HOME_AFTER_TRANSITION": True}


def sample(counter, phase, *, aircraft=("101", "1"), eligible=True):
    return CameraPhaseSample(aircraft, counter, phase, eligible)


@pytest.mark.parametrize("initial,settled", [(MC, FW), (FW, MC), (MC, MC), (FW, FW)])
def test_one_view_after_a_settled_transition_or_abort(initial, settled):
    observer = CameraPhaseObserver()
    states = [(0., sample(1, initial)), (.1, sample(2, TRANSITION)), (.2, sample(3, settled)),
              (.8, sample(3, settled)), (.9, sample(4, settled)), (1., sample(5, settled))]
    actions = [observer.update(frame, now, .5, 2.) for now, frame in states]
    assert actions == [None, None, None, None, settled, None]


@pytest.mark.parametrize("bad_sample,now", [
    (None, .8), (sample(4, FW, eligible=False), .8), (sample(4, FW, aircraft=("102", "1")), .8),
    (sample(1, FW), .8), (sample(4, FW), 3.),
])
def test_discontinuity_cannot_complete_transition(bad_sample, now):
    observer = CameraPhaseObserver()
    for index, phase in enumerate((MC, TRANSITION, FW), start=1):
        assert observer.update(sample(index, phase), index / 10, .5, 2.) is None
    assert observer.update(bad_sample, now, .5, 2.) is None
    aircraft = bad_sample.aircraft if bad_sample is not None else ("101", "1")
    assert observer.update(sample(9, FW, aircraft=aircraft), now + .6, .5, 2.) is None


def test_unobserved_or_incomplete_transitions_leave_camera_unchanged():
    observer = CameraPhaseObserver()
    for index, phase in enumerate((TRANSITION, FW, FW, MC, MC, TRANSITION, FW, MC, TRANSITION), start=1):
        assert observer.update(sample(index, phase), index / 10, .5, 2.) is None


def test_transition_home_configuration_uses_existing_camera_controls():
    assert transition_home_enabled(SETTINGS)
    assert not transition_home_enabled({"ENABLED": False, "CONTROL_ENABLED": True})
    assert not transition_home_enabled({"ENABLED": True, "CONTROL_ENABLED": False})
    assert not transition_home_enabled({**SETTINGS, "HOME_AFTER_TRANSITION": False})
    with pytest.raises(ValueError, match="must be boolean"):
        transition_home_enabled({**SETTINGS, "HOME_AFTER_TRANSITION": "true"})


def test_config_validation_preserves_missing_optional_home_and_declares_restart():
    service = ConfigService.get_instance()
    config = copy.deepcopy(service.get_default())
    assert config["GimbalTracker"]["HOME_AFTER_TRANSITION"] is True
    del config["GimbalTracker"]["HOME_AFTER_TRANSITION"]
    assert service.validate_config_mapping(config).valid
    config["GimbalTracker"]["HOME_AFTER_TRANSITION"] = False
    assert service.validate_config_mapping(config).valid
    config["GimbalTracker"]["HOME_AFTER_TRANSITION"] = 1
    assert not service.validate_config_mapping(config).valid
    schema = service.get_parameter_schema("GimbalTracker", "HOME_AFTER_TRANSITION")
    assert schema["reload_tier"] == "system_restart"


def test_only_stock_tailsitter_packets_drive_camera_observer(monkeypatch):
    manager = MavlinkDataManager("127.0.0.1", 8088, .5, {}, enabled=True)
    record = Mock()
    manager.camera_phase_observer = record
    payload = {"vehicles": {str(manager.system_id): {"components": {str(manager.component_id): {"messages": {
        "HEARTBEAT": {"message": {"mavtype": {"type": "MAV_TYPE_VTOL_QUADROTOR"}, "autopilot": 12,
                                   "base_mode": {"bits": "MAV_MODE_FLAG_SAFETY_ARMED"}, "system_status": 4},
                      "status": {"time": {"counter": 1}}},
        "AUTOPILOT_VERSION": {"message": {"uid": 101}},
        "EXTENDED_SYS_STATE": {"message": {"vtol_state": {"type": "MAV_VTOL_STATE_MC"}, "landed_state": 2},
                               "status": {"time": {"counter": 1}}},
    }}}}}}
    http_get = Mock(return_value=Mock(json=lambda: payload))
    monkeypatch.setattr("classes.mavlink_data_manager.requests.get", http_get)
    messages = payload["vehicles"][str(manager.system_id)]["components"][str(manager.component_id)]["messages"]
    manager._fetch_and_parse_all_data()
    assert record.call_args.args == (None,)
    messages["HEARTBEAT"]["status"]["time"]["counter"] += 1
    manager._fetch_and_parse_all_data()
    observed = record.call_args.args[0]
    assert observed.phase is MC and observed.eligible and observed.aircraft[0] == "101"
    messages["HEARTBEAT"]["message"]["system_status"] = {"type": "MAV_STATE_CRITICAL"}
    messages["HEARTBEAT"]["status"]["time"]["counter"] += 1
    manager._fetch_and_parse_all_data()
    assert not record.call_args.args[0].eligible
    messages["HEARTBEAT"]["message"]["mavtype"] = "MAV_TYPE_VTOL_TILTROTOR"
    manager._fetch_and_parse_all_data()
    assert record.call_args.args == (None,)
    http_get.side_effect = requests.ConnectionError()
    manager._fetch_and_parse_all_data()
    assert record.call_args.args == (None,)


@pytest.fixture
def camera():
    sent = threading.Event()
    control = SimpleNamespace(capabilities=("pan", "home", "stop"), stop=Mock(return_value=True),
                              send_home=Mock(),
                              prepare_manual=AsyncMock(), send_manual_intent=Mock())

    def send_view():
        sent.set()
        return True

    control.send_home.side_effect = send_view
    now = time.monotonic()
    observed = GimbalData(
        angles=GimbalAngles(0., 0., 0., CoordinateSystem.GIMBAL_BODY, datetime.now(timezone.utc)),
        tracking_status=TrackingStatus(TrackingState.DISABLED),
        angle_sample_sequence=10, angle_sample_monotonic=now, tracking_sample_monotonic=now,
    )
    provider = SimpleNamespace(running=True, manual_control=control, get_current_data=lambda: observed,
                               stop_listening=Mock())
    app = SimpleNamespace()
    runtime = CameraRuntime(app, SETTINGS)
    app.camera_runtime = runtime
    runtime.provider = provider
    runtime.start()
    try:
        yield runtime, control, observed, sent
    finally:
        runtime.close()


def replay(runtime, initial=MC, settled=FW, counter=1):
    for sequence, phase in enumerate((initial, TRANSITION, settled, settled), start=counter):
        runtime.observe_camera_phase(sample(sequence, phase), confirmation_s=0.)


@pytest.mark.parametrize("initial,settled", [(MC, FW), (FW, MC), (MC, MC), (FW, FW)])
def test_executor_sends_same_home_once_after_each_settled_phase(camera, initial, settled):
    runtime, control, observed, sent = camera
    with runtime._lock:
        replay(runtime, initial, settled)
        assert runtime.transition_view_status()["state"] == "pending"
    assert sent.wait(1.)
    with runtime._lock:
        control.send_home.assert_called_once_with()
        status = APIGimbalControlStatus(**get_gimbal_control_status(runtime.app)).transition_view
        assert status.state == "sent" and status.phase == settled.value
        runtime.observe_camera_phase(sample(5, settled))
        assert not runtime.motion_active
        control.send_home.assert_called_once()


@pytest.mark.parametrize("conflict", ["tracking", "following", "rescue", "manual", "provider", "camera_restarted"])
def test_conflict_consumes_transition_without_a_late_move(camera, conflict):
    runtime, control, observed, _ = camera
    with runtime._lock:
        if conflict == "provider":
            runtime.provider.manual_control = SimpleNamespace(capabilities=("pan", "stop"))
        elif conflict == "tracking":
            observed.tracking_status.state = TrackingState.TRACKING_ACTIVE
        elif conflict == "following":
            runtime.app.following_active = True
        elif conflict == "rescue":
            runtime.app.px4_interface = SimpleNamespace(get_aircraft_state=lambda: SimpleNamespace(rescue_active=True))
        elif conflict == "manual":
            runtime.acquire("operator", "pan")
        replay(runtime)
        if conflict == "camera_restarted":
            runtime._retire_observation_source()
            runtime.advance_transition_view(time.monotonic())
        if conflict == "manual":
            runtime.release()
        if conflict == "provider":
            assert runtime.transition_view_status()["reason"] == "provider_home_unavailable"
        observed.tracking_status.state = TrackingState.DISABLED
        runtime.app.following_active = False
        runtime.app.px4_interface = None
        runtime.observe_camera_phase(sample(5, FW))
        assert runtime._transition_move is None
        control.send_home.assert_not_called()


@pytest.mark.parametrize("reason", ["operator_stop", "operator_override", "stale_aircraft", "timeout"])
def test_pending_home_is_discarded_without_replay(camera, reason):
    runtime, control, observed, _ = camera
    with runtime._lock:
        replay(runtime)
        if reason == "operator_stop":
            runtime._manual.stop()
        elif reason == "operator_override":
            context_before = runtime.guard()
            runtime.acquire("operator", "pan")
            assert runtime.guard() == context_before
            runtime.release()
        elif reason == "timeout":
            runtime._transition_move.admitted_at -= 1.
        else:
            runtime.observe_camera_phase(None)
        runtime.advance_transition_view(time.monotonic())
        control.send_home.assert_not_called()
        assert runtime.transition_view_status()["state"] == "skipped"
        runtime.observe_camera_phase(sample(5, FW))
        assert runtime._transition_move is None


def test_disabled_camera_views_leave_status_and_motion_alone():
    runtime = CameraRuntime(SimpleNamespace(), {**SETTINGS, "HOME_AFTER_TRANSITION": False})
    replay(runtime)
    assert runtime.transition_view_status() is None
    assert not runtime.motion_active
