"""Manual control protocol and lifecycle tests; no camera/network required."""
import asyncio
from datetime import datetime
from types import SimpleNamespace
import struct
import time

import pytest

from classes.gimbal_control import (
    SipGimbalControl, execute_gimbal_control, get_gimbal_control_status,
    inverse_video_point, sip_frame,
)
from classes.gimbal_provider import create_gimbal_provider
from classes.gimbal_types import CoordinateSystem, GimbalAngles, TrackingState, TrackingStatus


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
    provider._send_command = lambda frame: sent.append(frame) or True
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


async def test_stop_preempts_pending_selection_without_waiting_for_barrier(camera):
    provider, sent = camera
    provider._send_command = lambda frame: sent.append(frame) or True
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
        _advance_tracking_session_generation=lambda: None,
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
    provider._send_command = lambda frame: sent.append(frame) or True
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


async def test_following_blocks_selection_but_not_best_effort_stop(camera):
    provider, sent = camera
    app = make_app(provider)
    app.following_active = True
    assert not (await execute_gimbal_control(app, request("select", x=.5, y=.5)))["success"]
    assert not sent
    provider.last_data_time = time.time()-100
    provider.last_tracking_update_time = time.time()-100
    assert not get_gimbal_control_status(app)["connected"]
    assert (await execute_gimbal_control(app, request("stop")))["success"]


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
