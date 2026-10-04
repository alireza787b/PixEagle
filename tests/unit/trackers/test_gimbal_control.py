"""Manual control protocol and lifecycle tests; no camera/network required."""
import asyncio
from datetime import datetime
from types import SimpleNamespace
import struct
import time
import threading
from contextlib import contextmanager
from unittest.mock import AsyncMock, Mock

import pytest

from classes.gimbal_control import (
    SipGimbalControl, execute_gimbal_control, get_gimbal_control_status,
    inverse_video_point, sip_frame,
)
from classes.gimbal_provider import create_gimbal_provider
from classes.gimbal_types import CoordinateSystem, GimbalAngles, TrackingState, TrackingStatus


def _record_transmission(sent):
    def send(frame):
        sent.append(frame)
        return True
    return send


@pytest.fixture
def camera():
    provider = create_gimbal_provider({"CONTROL_ENABLED": True})
    provider.running = True
    provider.current_angles = GimbalAngles(0, 0, 0, CoordinateSystem.GIMBAL_BODY, datetime.now())
    provider.last_data_time = time.time()
    provider.current_tracking_status = TrackingStatus(TrackingState.DISABLED, timestamp=datetime.now())
    provider.last_tracking_update_time = time.time()
    sent = []

    def send(frame):
        if isinstance(frame, str):
            frame = frame.encode()
        sent.append(frame)
        if frame[6:10] == b"wTRC":
            state = TrackingState.DISABLED if frame[10:12] == b"00" else TrackingState.TARGET_SELECTION
            provider.current_tracking_status = TrackingStatus(state, timestamp=datetime.now())
            provider.last_tracking_update_time = time.time()
        return True

    provider._send_command = send
    return provider, sent


def test_default_factory_has_no_control_capability_or_network():
    provider = create_gimbal_provider({})
    assert provider.manual_control is None
    assert not provider.running
    assert provider.control_socket is None


async def test_native_frame_guard_rechecked_after_handshake_before_location(camera):
    provider, sent = camera
    def expired():
        assert any(frame[6:10] == b"wTRC" for frame in sent)
        raise ValueError("Displayed frame expired during camera handshake")
    with pytest.raises(ValueError, match="expired"):
        await provider.manual_control.execute("select", x=.5, y=.5, selection_guard=expired)
    assert not any(frame.startswith(b"#tpPDAwLOC") for frame in sent)
    assert sip_frame(b"#TPPG2wPTZ00") in sent


async def test_native_final_location_send_is_inside_source_transaction(camera):
    provider, sent = camera
    transaction = threading.RLock()
    send = provider._send_command
    guarded = []

    def checked_send(frame):
        if isinstance(frame, str):
            frame = frame.encode()
        if frame.startswith(b"#tpPDAwLOC"):
            assert transaction._is_owned()
            guarded.append(True)
        return send(frame)

    @contextmanager
    def guard():
        assert any(frame[6:10] == b"wTRC" for frame in sent)
        with transaction:
            yield

    provider._send_command = checked_send
    result = await provider.manual_control.execute("select", x=.5, y=.5, selection_guard=guard)
    assert result["success"] and guarded == [True]


async def test_legacy_camera_mode_changes_advance_shared_target_revision(camera):
    provider, _ = camera
    app = make_app(provider)
    app._tracking_session_generation = 4
    def advance():
        app._tracking_session_generation += 1
    app._advance_tracking_session_generation = advance
    result = await execute_gimbal_control(app, request("set_mode", selection_mode="smart"))
    assert result["success"]
    assert app._tracking_session_generation == 5
    assert provider.manual_control.selection_mode == "smart"


@pytest.mark.parametrize("operation,axis,source", [("pan", "GSY", "U"), ("tilt", "GSP", "U"), ("roll", "GSR", "P")])
async def test_custom_pulse_encodes_speed_and_honors_duration_with_stop(camera, monkeypatch, operation, axis, source):
    provider, sent = camera
    sleeps = []
    original_sleep = asyncio.sleep

    async def fast_sleep(seconds):
        sleeps.append(seconds)
        await original_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    result = await provider.manual_control.execute(operation, direction=-1, speed_deg_s=30, duration_ms=1000)
    assert result["speed_deg_s"] == 30 and result["duration_ms"] == 1000
    assert sip_frame(f"#TP{source}G2w{axis}E2".encode()) in sent
    assert sleeps[-1] == 1.0
    assert sent[-2:] == [sip_frame(b"#TPPG2wPTZ00"), sip_frame(b"#TPPM2wZMC00")]


@pytest.mark.parametrize("kwargs", [
    {"speed_deg_s": 31}, {"speed_deg_s": 0}, {"speed_deg_s": True},
    {"duration_ms": 99}, {"duration_ms": 1001}, {"duration_ms": 250.5},
])
async def test_invalid_motion_cannot_cancel_target_or_send_a_pulse(camera, kwargs):
    provider, sent = camera
    provider.manual_control.owns_tracking = True
    provider.current_tracking_status.state = TrackingState.TRACKING_ACTIVE
    with pytest.raises(ValueError):
        await provider.manual_control.execute("pan", direction=1, **kwargs)
    assert not sent
    assert provider.manual_control.owns_tracking


async def test_motion_settings_reach_provider_and_status(camera):
    provider, sent = camera
    app = make_app(provider)
    status = get_gimbal_control_status(app)
    assert status["motion_settings"]["default_speed_deg_s"] == 10
    assert status["motion_settings"]["default_duration_ms"] == 250
    result = await execute_gimbal_control(app, request("pan", direction=1, speed_deg_s=5, duration_ms=100))
    assert result["success"]
    assert sip_frame(b"#TPUG2wGSY05") in sent
    assert result["duration_ms"] == 100


async def test_explicit_stop_interrupts_long_custom_pulse(camera):
    provider, sent = camera
    app = make_app(provider)
    task = asyncio.create_task(execute_gimbal_control(app, request("pan", direction=1, speed_deg_s=20, duration_ms=1000)))
    for _ in range(50):
        if any(b[7:10] == b"GSY" for b in sent):
            break
        await asyncio.sleep(.01)
    assert any(b[7:10] == b"GSY" for b in sent)
    assert (await execute_gimbal_control(app, request("stop")))["success"]
    index = len(sent)
    await task
    assert not any(b[7:10] == b"GSY" for b in sent[index:])


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("flip", ["none", "horizontal", "vertical", "both"])
def test_inverse_orientation_round_trip(rotation, flip):
    x, y = 0.2, 0.7
    dx, dy = {0: (x,y), 90: (1-y,x), 180: (1-x,1-y), 270: (y,1-x)}[rotation]
    if flip in ("horizontal", "both"):
        dx = 1-dx
    if flip in ("vertical", "both"):
        dy = 1-dy
    assert inverse_video_point(dx, dy, rotation, flip) == pytest.approx((x,y))


async def test_retarget_establishes_inactive_barrier_then_manual_loc(camera):
    provider, sent = camera
    provider.current_tracking_status.state = TrackingState.TRACKING_ACTIVE
    result = await provider.manual_control.execute("select", x=.7, y=.6)
    assert result["success"]
    controls = [b for b in sent if b[6:7] == b"w"]
    assert [b[7:12] for b in controls[:3]] == [b"TRC01", b"TRC00", b"TRC02"]
    assert controls[-1] == sip_frame(b"#tpPDAwLOC" + struct.pack(">hhhhH", 400, 200, 67, 119, 0))
    assert provider.current_tracking_status.state == TrackingState.TARGET_SELECTION
    await provider.manual_control.execute("cancel")
    assert provider.current_tracking_status.state == TrackingState.DISABLED


async def test_old_active_status_cannot_satisfy_prepare(camera):
    provider, sent = camera
    provider.current_tracking_status.state = TrackingState.TRACKING_ACTIVE
    provider.last_tracking_update_time = time.time()-1
    provider._send_command = _record_transmission(sent)
    provider.manual_control.STATUS_TIMEOUT = .02
    with pytest.raises(RuntimeError, match="did not report"):
        await provider.manual_control.execute("select", x=.5, y=.5)
    assert not any(b[7:10] == b"LOC" for b in sent)
    assert sip_frame(b"#TPPD2wTRC00") in sent


async def test_cancelled_pulse_sends_stops(camera):
    provider, sent = camera
    task = asyncio.create_task(provider.manual_control.execute("pan", direction=1))
    for _ in range(50):
        if any(b[7:10] == b"GSY" for b in sent):
            break
        await asyncio.sleep(.01)
    assert any(b[7:10] == b"GSY" for b in sent)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sent[-2:] == [sip_frame(b"#TPPG2wPTZ00"), sip_frame(b"#TPPM2wZMC00")]


async def test_explicit_stop_reports_transport_failure(camera):
    provider, _ = camera
    provider._send_command = lambda _: False
    assert not (await provider.manual_control.execute("stop"))["success"]


@pytest.mark.parametrize("operation", ["pan", "tilt", "roll", "zoom"])
async def test_pulse_reports_failed_final_stop_and_allows_explicit_retry(camera, operation):
    provider, sent = camera
    send = provider._send_command
    stops = {sip_frame(b"#TPPG2wPTZ00"), sip_frame(b"#TPPM2wZMC00")}

    def reject_stops(frame):
        accepted = send(frame)
        return accepted and frame not in stops

    provider._send_command = reject_stops
    app = make_app(provider)
    result = await execute_gimbal_control(app, request(operation, direction=1))
    assert not result["success"]
    assert "stop transmission failed" in result["message"]
    assert any(frame not in stops and frame[7:10] in (b"GSY", b"GSP", b"GSR", b"ZMC") for frame in sent)
    assert sent[-4:] == [sip_frame(b"#TPPG2wPTZ00"), sip_frame(b"#TPPM2wZMC00")] * 2
    provider._send_command = send
    assert (await execute_gimbal_control(app, request("stop")))["success"]


async def test_stop_preempts_pending_selection_without_waiting_for_barrier(camera):
    provider, sent = camera
    provider._send_command = _record_transmission(sent)
    app = make_app(provider)
    task = asyncio.create_task(execute_gimbal_control(app, request("select", x=.5, y=.5)))
    await asyncio.sleep(.01)
    assert app._follower_state_lock.locked()
    assert (await execute_gimbal_control(app, request("stop")))["success"]
    result = await task
    assert not result["success"]
    assert "interrupted" in result["message"]
    assert not any(b[7:10] == b"LOC" for b in sent)


@pytest.mark.parametrize("direction", [-1, 1])
async def test_roll_uses_documented_speed_command_and_bounded_stop(camera, direction):
    provider, sent = camera
    assert (await provider.manual_control.execute("roll", direction=direction))["success"]
    assert sip_frame(f"#TPPG2wGSR{(direction*10)&255:02X}".encode()) in sent
    assert sent[-2:] == [sip_frame(b"#TPPG2wPTZ00"), sip_frame(b"#TPPM2wZMC00")]


async def test_cancel_from_active_uses_ready_then_disabled(camera):
    provider, sent = camera
    provider.current_tracking_status.state = TrackingState.TRACKING_ACTIVE
    assert (await provider.manual_control.execute("cancel"))["success"]
    writes = [b[7:12] for b in sent if b[6:7] == b"w"]
    assert writes[:2] == [b"TRC01", b"TRC00"]


def make_app(provider):
    async def owner_loop(operation):
        return await operation()
    return SimpleNamespace(
        tracker=SimpleNamespace(is_external_tracker=True, gimbal_provider=provider),
        following_active=False, _follower_state_lock=asyncio.Lock(),
        _run_on_flight_event_loop=owner_loop,
        _advance_tracking_session_generation=lambda **_: None,
        _get_target_continuity_supervisor=lambda: SimpleNamespace(
            get_status=lambda: {"target_transition_pending": True}
        ),
        video_handler=SimpleNamespace(
            selection_source={"type":"RTSP_OPENCV", "url":"rtsp://192.168.0.108:554/stream=0"},
            _frame_rotation_deg=180, _frame_flip_mode="none",
            get_frame_status=lambda: {"source":"fresh", "last_successful_frame_time":time.time()},
        ),
    )


def request(op, **kwargs):
    return SimpleNamespace(operation=op, x=kwargs.get("x"), y=kwargs.get("y"), width=kwargs.get("width"), height=kwargs.get("height"), direction=kwargs.get("direction"), selection_mode=kwargs.get("selection_mode"), speed_deg_s=kwargs.get("speed_deg_s"), duration_ms=kwargs.get("duration_ms"))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("flip", ["none", "horizontal", "vertical", "both"])
async def test_rectangle_undoes_display_orientation_and_uses_qt_drag_descriptor(camera, rotation, flip):
    provider, sent = camera
    app = make_app(provider)
    app.video_handler._frame_rotation_deg = rotation
    app.video_handler._frame_flip_mode = flip
    # Native center (.3,.4), dimensions (.2,.1), rotated into display space.
    x, y = {0:(.3,.4), 90:(.6,.3), 180:(.7,.6), 270:(.4,.7)}[rotation]
    width, height = (.1,.2) if rotation in (90,270) else (.2,.1)
    if flip in ("horizontal", "both"):
        x = 1-x
    if flip in ("vertical", "both"):
        y = 1-y
    result = await execute_gimbal_control(app, request("select", x=x, y=y, width=width, height=height))
    assert result["success"]
    assert sent[-1] == sip_frame(b"#tpPDAwLOC" + struct.pack(">hhhhH", -400, -200, 400, 200, 1))


@pytest.mark.parametrize("geometry", [
    dict(x=.5,y=.5,width=.2), dict(x=.5,y=.5,width=float("nan"),height=.1),
    dict(x=.5,y=.5,width=.1,height=0), dict(x=.95,y=.5,width=.2,height=.1),
    dict(x=.5,y=.5,width=.00001,height=.1),
])
async def test_bad_rectangle_does_not_cancel_existing_target(camera, geometry):
    provider, sent = camera
    provider.manual_control.owns_tracking = True
    provider.current_tracking_status.state = TrackingState.TRACKING_ACTIVE
    with pytest.raises(ValueError):
        await provider.manual_control.execute("select", **geometry)
    assert not sent
    assert provider.manual_control.owns_tracking
    assert provider.current_tracking_status.state == TrackingState.TRACKING_ACTIVE


async def test_smart_rejects_rectangle_without_touching_camera(camera):
    provider, sent = camera
    provider.manual_control.selection_mode = "smart"
    result = await execute_gimbal_control(make_app(provider), request("select", x=.5,y=.5,width=.2,height=.1))
    assert not result["success"]
    assert "Classic" in result["message"]
    assert not sent


async def test_smart_prepare_preserves_detections_on_click_and_uses_qt_fuzzy_bytes(camera):
    provider, sent = camera
    app = make_app(provider)
    assert (await execute_gimbal_control(app, request("set_mode", selection_mode="smart")))["success"]
    assert get_gimbal_control_status(app)["selection_mode"] == "smart"
    assert provider.current_tracking_status.state == TrackingState.TARGET_SELECTION
    sent.clear()
    assert (await execute_gimbal_control(app, request("select", x=.3, y=.4)))["success"]
    writes = [b for b in sent if b[6:7] == b"w"]
    assert writes == [sip_frame(b"#tpPDAwLOC" + struct.pack(">hhhhH",400,200,62,111,9))]


async def test_smart_retarget_cancels_to_ready_without_disabling_detection(camera):
    provider, sent = camera
    provider.manual_control.selection_mode = "smart"
    provider.current_tracking_status.state = TrackingState.TRACKING_ACTIVE
    await provider.manual_control.execute("select", x=.5, y=.5)
    writes = [b[7:12] for b in sent if b[6:7] == b"w"]
    assert writes[0] == b"TRC01"
    assert b"TRC00" not in writes


async def test_classic_mode_cancels_smart_and_returns_to_non_fuzzy_selection(camera):
    provider, sent = camera
    await provider.manual_control.execute("set_mode", selection_mode="smart")
    await provider.manual_control.execute("set_mode", selection_mode="classic")
    assert provider.current_tracking_status.state == TrackingState.DISABLED
    assert not provider.manual_control.owns_tracking
    await provider.manual_control.execute("select", x=.5, y=.5)
    assert sent[-1] == sip_frame(b"#tpPDAwLOC" + struct.pack(">hhhhH",0,0,67,119,0))


async def test_failed_mode_prepare_does_not_publish_new_mode(camera):
    provider, sent = camera
    provider._send_command = _record_transmission(sent)
    provider.manual_control.STATUS_TIMEOUT = .02
    with pytest.raises(RuntimeError):
        await provider.manual_control.execute("set_mode", selection_mode="smart")
    assert provider.manual_control.selection_mode == "classic"
    assert not provider.manual_control.owns_tracking


async def test_following_blocks_camera_mode_change(camera):
    provider, sent = camera
    app = make_app(provider)
    app.following_active = True
    assert not (await execute_gimbal_control(app, request("set_mode", selection_mode="smart")))["success"]
    assert not sent


@pytest.mark.parametrize("operation,kwargs", [
    ("select", {"x": .5, "y": .5}),
    ("set_mode", {"selection_mode": "smart"}),
    ("pan", {"direction": 1}),
])
async def test_shutdown_blocks_new_camera_work_but_allows_stop(camera, operation, kwargs):
    provider, sent = camera
    app = make_app(provider)
    app.shutdown_flag = True
    result = await execute_gimbal_control(app, request(operation, **kwargs))
    assert result["reason"] == "application_shutting_down"
    assert not sent
    assert (await execute_gimbal_control(app, request("stop")))["success"]


async def test_following_retarget_pauses_commands_but_not_best_effort_stop(camera):
    provider, sent = camera
    app = make_app(provider)
    app.following_active = True
    transitions = []
    app._prepare_following_target_transition = lambda reason: (
        transitions.append(reason) or {"prepared": True, "bounded_transition_applied": True,
                                       "following_continued": True, "execution_mode": "PX4"}
    )
    result = await execute_gimbal_control(app, request("select", x=.5, y=.5))
    assert result["success"] and result["target_transition"]["bounded_transition_applied"]
    assert transitions == ["operator_camera_target_retarget"]
    assert any(frame[7:10] == b"LOC" for frame in sent)
    assert app.following_active
    provider.last_data_time = time.time()-100
    provider.last_tracking_update_time = time.time()-100
    assert not get_gimbal_control_status(app)["connected"]
    assert (await execute_gimbal_control(app, request("stop")))["success"]


@pytest.mark.parametrize("mode", ["classic", "smart"])
@pytest.mark.parametrize("barrier_held", [False, True])
async def test_rejected_edge_retarget_preserves_following_and_target_generation(camera, mode, barrier_held):
    provider, sent = camera
    provider.manual_control.selection_mode = mode
    provider.manual_control.owns_tracking = True
    provider.current_tracking_status.state = TrackingState.TRACKING_ACTIVE
    app = make_app(provider)
    app.following_active = True
    app._tracking_session_generation = 4
    app._prepare_following_target_transition = Mock(side_effect=AssertionError("Must validate before transition"))
    app._advance_tracking_session_generation = Mock(side_effect=AssertionError("Invalid tap cannot change generation"))
    app._disconnect_px4_internal = AsyncMock()
    if barrier_held:
        async with app._follower_state_lock:
            result = await execute_gimbal_control(app, request("select", x=.99, y=.5), barrier_held=True)
    else:
        result = await execute_gimbal_control(app, request("select", x=.99, y=.5))
    assert not result["success"] and "image edge" in result["message"]
    assert app.following_active and app._tracking_session_generation == 4
    assert provider.manual_control.owns_tracking
    assert provider.current_tracking_status.state == TrackingState.TRACKING_ACTIVE
    assert not sent
    app._disconnect_px4_internal.assert_not_awaited()


async def test_following_retarget_commits_with_its_reserved_target_revision(camera):
    provider, sent = camera
    provider.current_tracking_status.state = TrackingState.TRACKING_ACTIVE
    app = make_app(provider)
    app.following_active = True
    app._tracking_session_generation = 7

    def advance(**_):
        app._tracking_session_generation += 1

    app._advance_tracking_session_generation = advance
    app._prepare_following_target_transition = lambda _: {
        "prepared": True, "bounded_transition_applied": True,
    }
    revisions = []

    @contextmanager
    def admitted(revision):
        revisions.append(revision)
        assert not any(frame[7:10] == b"LOC" for frame in sent)
        yield

    async with app._follower_state_lock:
        result = await execute_gimbal_control(
            app, request("select", x=.5, y=.5), barrier_held=True,
            selection_guard=admitted,
        )
    assert result["success"]
    assert revisions == ["8"]
    assert any(frame[7:10] == b"LOC" for frame in sent)


async def test_late_camera_selection_guard_failure_stops_following_without_location(camera):
    provider, sent = camera
    provider.current_tracking_status.state = TrackingState.TRACKING_ACTIVE
    app = make_app(provider)
    app.following_active = True
    app._tracking_session_generation = 7
    app._advance_tracking_session_generation = lambda **_: setattr(
        app, "_tracking_session_generation", app._tracking_session_generation + 1,
    )
    app._prepare_following_target_transition = lambda _: {
        "prepared": True, "bounded_transition_applied": True,
    }
    app._disconnect_px4_internal = AsyncMock(return_value={"offboard_stop_action": {"executed": True}})

    @contextmanager
    def changed_source(_):
        raise ValueError("The displayed video source changed")
        yield

    async with app._follower_state_lock:
        result = await execute_gimbal_control(
            app, request("select", x=.5, y=.5), barrier_held=True,
            selection_guard=changed_source,
        )
    assert not result["success"] and result["reason"] == "camera_control_failed"
    assert not any(frame[7:10] == b"LOC" for frame in sent)
    app._disconnect_px4_internal.assert_awaited_once()


async def test_failed_camera_retarget_stops_following_after_command_pause(camera):
    provider, _ = camera
    app = make_app(provider)
    app.following_active = True
    app._prepare_following_target_transition = lambda reason: {
        "prepared": True, "bounded_transition_applied": True,
        "following_continued": True, "execution_mode": "PX4",
    }
    app._disconnect_px4_internal = AsyncMock(return_value={"errors": [], "offboard_stop_action": {"executed": True}})
    provider.manual_control.execute = AsyncMock(return_value={"success": False, "reason": "camera_rejected_selection"})

    result = await execute_gimbal_control(app, request("select", x=.5, y=.5))

    assert not result["success"]
    app._disconnect_px4_internal.assert_awaited_once_with(
        commander_publish_final=False, reset_continuity=False,
        reason_code="camera_selection_failed",
    )


async def test_backend_unrotates_displayed_click(camera):
    provider, sent = camera
    assert (await execute_gimbal_control(make_app(provider), request("select", x=.3, y=.4)))["success"]
    loc = next(b for b in sent if b[7:10] == b"LOC")
    assert struct.unpack(">hhhhH", loc[10:20]) == (400, 200, 67, 119, 0)


@pytest.mark.parametrize("fault", ["wrong_camera", "cached", "old_fresh"])
async def test_selection_rejects_unrelated_or_stale_video(camera, fault):
    provider, sent = camera
    app = make_app(provider)
    if fault == "wrong_camera":
        app.video_handler.selection_source["url"] = "rtsp://192.168.0.99/stream=0"
    else:
        app.video_handler.get_frame_status = lambda: {
            "source":"cached" if fault == "cached" else "fresh",
            "last_successful_frame_time":time.time()-10,
        }
    assert not (await execute_gimbal_control(app, request("select", x=.5, y=.5)))["success"]
    assert not sent


def test_shutdown_disables_only_control_owned_tracking(camera):
    provider, sent = camera
    provider.manual_control.owns_tracking = True
    provider.stop_listening()
    assert sip_frame(b"#TPPD2wTRC00") in sent
    assert provider.current_tracking_status is None
    assert not provider.running


@pytest.mark.parametrize("operation", ["pan", "home"])
async def test_camera_guard_rechecked_after_handshake_before_motion(camera, operation):
    provider, sent = camera
    @contextmanager
    def expired():
        if any(frame[6:10] == b"wTRC" for frame in sent):
            raise ValueError("Camera context changed during handshake")
        yield
    with pytest.raises(ValueError, match="context changed"):
        await provider.manual_control.execute(operation, direction=1 if operation == "pan" else None,
                                              selection_guard=expired)
    assert not any(frame.startswith(b"#TPUG2wGSY") for frame in sent)
    assert sip_frame(b"#TPPG2wPTZ05") not in sent
    assert sip_frame(b"#TPPG2wPTZ00") in sent


async def test_continuous_manual_takeover_once_and_magnitude_encoding(camera):
    from contextlib import nullcontext
    provider, sent = camera
    control = provider.manual_control
    await control.prepare_manual(nullcontext)
    handshakes = sum(frame[6:10] == b"wTRC" for frame in sent)
    control.send_manual_intent("pan", 0.5)
    control.send_manual_intent("pan", -1)
    assert sip_frame(b"#TPUG2wGSY0F") in sent
    assert sip_frame(b"#TPUG2wGSYE2") in sent
    assert sum(frame[6:10] == b"wTRC" for frame in sent) == handshakes == 1
    control.send_manual_intent("roll", 0.2)
    assert sip_frame(b"#TPPG2wPTZ00") in sent
    assert sent[-1] == sip_frame(b"#TPPG2wGSR06")
    control.send_manual_intent("roll", 0)
    assert sent[-1] == sip_frame(b"#TPPM2wZMC00")


async def test_continuous_preparation_checks_cancel_before_any_write(camera):
    provider, sent = camera
    @contextmanager
    def ended():
        raise RuntimeError("Gesture ended")
        yield
    with pytest.raises(RuntimeError, match="Gesture ended"):
        await provider.manual_control.prepare_manual(ended)
    assert sent == []
