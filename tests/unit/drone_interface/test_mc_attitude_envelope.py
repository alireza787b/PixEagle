"""Measured attitude, body/Euler coupling and publisher-independent protection."""

import asyncio
import math
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from classes.attitude_envelope import guard_body_rates
from classes.command_intent import CommandIntent
from classes.command_safety import CommandValidationError
from classes.follower import FollowerFactory
from classes.mavlink_data_manager import MavlinkDataManager
from classes.offboard_commander import OffboardCommander
from classes.parameters import Parameters
from classes.px4_interface_manager import PX4InterfaceManager
from classes.setpoint_handler import SetpointHandler
from classes.tracker_output import TrackerDataType, TrackerOutput


def fields(p=0.0, q=0.0, r=0.0):
    return {
        "rollspeed_deg_s": p,
        "pitchspeed_deg_s": q,
        "yawspeed_deg_s": r,
        "thrust": 0.57,
    }


@pytest.mark.parametrize("sign", [-1, 1])
def test_pitch_envelope_includes_body_yaw_at_nonzero_roll(sign):
    before = fields(r=-45 * sign)
    guarded, status = guard_body_rates(
        before,
        roll_deg=30,
        pitch_deg=34 * sign,
        max_roll_deg=35,
        max_pitch_deg=35,
        horizon_s=0.5,
    )
    assert 0 < status["scale"] < 1
    assert status["euler_pitch_rate_deg_s"] * sign == pytest.approx(2)
    assert guarded["thrust"] == before["thrust"]
    assert abs(guarded["yawspeed_deg_s"]) < 45


def test_roll_envelope_includes_yaw_at_nonzero_pitch():
    guarded, status = guard_body_rates(
        fields(r=45),
        roll_deg=34,
        pitch_deg=30,
        max_roll_deg=35,
        max_pitch_deg=35,
        horizon_s=0.5,
    )
    assert status["euler_roll_rate_deg_s"] == pytest.approx(2)
    assert guarded["yawspeed_deg_s"] < 45


def test_inward_motion_at_boundary_remains_available():
    guarded, status = guard_body_rates(
        fields(q=-20),
        roll_deg=0,
        pitch_deg=35,
        max_roll_deg=35,
        max_pitch_deg=35,
        horizon_s=0.5,
    )
    assert status["scale"] == 1
    assert guarded["pitchspeed_deg_s"] == -20


@pytest.mark.parametrize(
    "override",
    [
        {"roll_deg": None},
        {"pitch_deg": math.nan},
        {"pitch_deg": 36},
        {"roll_deg": -36},
        {"max_pitch_deg": 90},
        {"max_roll_deg": 0},
        {"horizon_s": -1},
    ],
)
def test_invalid_geometry_and_envelope_fail_closed(override):
    kwargs = {
        "roll_deg": 0,
        "pitch_deg": 0,
        "max_roll_deg": 35,
        "max_pitch_deg": 35,
        "horizon_s": 0.5,
    }
    kwargs.update(override)
    with pytest.raises(CommandValidationError):
        guard_body_rates(fields(q=10), **kwargs)


def interface(monkeypatch):
    monkeypatch.setattr(Parameters, "FOLLOWER_MODE", "mc_attitude_rate")
    controller = PX4InterfaceManager.__new__(PX4InterfaceManager)
    controller.current_roll = 0.0
    controller.current_pitch = 34.0
    controller.current_altitude = 20.0
    controller.current_ground_speed = 1.0
    controller.current_yaw = 0.0
    controller._attitude_receipt_monotonic_s = time.monotonic()
    controller._telemetry_source_active = "mavsdk"
    controller._last_attitude_guard = None
    controller._terminal_attitude_guard_reason = None
    controller.get_telemetry_readiness = lambda: {"ready": True}
    controller.is_command_connection_ready = lambda **_: True
    controller.setpoint_handler = SetpointHandler("mc_attitude_rate")
    controller.drone = SimpleNamespace(
        offboard=SimpleNamespace(set_attitude_rate=AsyncMock())
    )
    controller._safe_mavsdk_call = AsyncMock(return_value=True)
    controller.quiesce_offboard_sender = AsyncMock(
        return_value={"local_sender_quiesced": True}
    )
    controller.send_commands_unified = controller.send_attitude_rate_commands
    controller._begin_sender_quiesce = lambda reason: asyncio.create_task(
        controller.quiesce_offboard_sender(reason=reason)
    )
    return controller


def test_stale_attitude_rejected_despite_other_fresh_snapshot_fields(monkeypatch):
    controller = interface(monkeypatch)
    controller._attitude_receipt_monotonic_s = time.monotonic() - 2.1
    with pytest.raises(CommandValidationError, match="attitude_sample_stale"):
        controller.guard_mc_attitude_command(fields(q=45))


def test_follower_guard_runs_after_ema_and_preserves_thrust(monkeypatch):
    controller = interface(monkeypatch)
    follower = FollowerFactory.create_follower("mc_attitude_rate", controller, (0, 0))
    follower.smoothed_pitch_rate = math.radians(45)
    follower._calculate_tracking_rates = lambda _: (0, 0)
    follower._calculate_coordinated_roll_rate = lambda *_: 0
    follower._calculate_thrust_command = lambda *_: 0.57
    output = TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        position_2d=(0.0, 0.0),
    )
    assert follower.follow_target(output)
    command = follower.get_last_command_intent().fields
    assert 0 < command["pitchspeed_deg_s"] < 3
    assert command["thrust"] == 0.57


@pytest.mark.asyncio
async def test_repeated_heartbeat_rechecks_attitude_without_new_frame(monkeypatch):
    controller = interface(monkeypatch)
    controller.current_pitch = 10
    handler = controller.setpoint_handler
    handler.set_fields(fields(q=40))
    events = []
    commander = OffboardCommander(controller, handler, on_publish_result=events.append)
    commander.submit_intent(
        CommandIntent(
            profile_name="mc_attitude_rate",
            control_type="attitude_rate",
            fields=fields(q=40),
            source="unit_test",
        )
    )
    assert await commander.publish_once()
    first = events[-1]["command_intent"].fields["pitchspeed_deg_s"]
    controller.current_pitch = 34
    assert await commander.publish_once()
    effective = events[-1]["command_intent"].fields
    assert 0 < effective["pitchspeed_deg_s"] < first
    sent = controller._safe_mavsdk_call.call_args.args[1]
    assert sent.pitch_deg_s == pytest.approx(effective["pitchspeed_deg_s"])
    assert effective["thrust"] == 0.57


@pytest.mark.asyncio
@pytest.mark.parametrize("age", [None, 2.1])
async def test_frozen_frame_heartbeat_rejects_missing_or_old_attitude(monkeypatch, age):
    controller = interface(monkeypatch)
    commander = OffboardCommander(
        controller, controller.setpoint_handler, command_ttl_s=0.5
    )
    commander.submit_intent(
        CommandIntent(
            profile_name="mc_attitude_rate",
            control_type="attitude_rate",
            fields=fields(q=40),
            source="frozen_frame",
        )
    )
    assert await commander.publish_once()
    controller._attitude_receipt_monotonic_s = (
        None if age is None else time.monotonic() - age
    )
    assert not await commander.publish_once()
    assert commander.terminal_failure_reason in {
        "attitude_sample_unavailable",
        "attitude_sample_stale",
    }
    assert controller._safe_mavsdk_call.await_count == 1
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_first_hard_attitude_rejection_trips_handoff_without_three_failures(
    monkeypatch,
):
    controller = interface(monkeypatch)
    controller.current_pitch = 36
    callback = AsyncMock()
    commander = OffboardCommander(
        controller,
        controller.setpoint_handler,
        command_failure_threshold=3,
        on_failure_threshold=callback,
    )
    assert not await commander.publish_once()
    assert commander.failed_publishes == 1
    assert commander.terminal_failure_reason == "attitude_envelope_exceeded"
    callback.assert_awaited_once()
    controller._safe_mavsdk_call.assert_not_awaited()
    await asyncio.sleep(0)
    controller.quiesce_offboard_sender.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_cached_rest_counter_does_not_refresh_angle_receipt():
    manager = MavlinkDataManager("127.0.0.1", 8088, 0.1, {}, enabled=True)
    payload = {"message": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0, "time_boot_ms": 100}}
    manager.fetch_data_from_uri = AsyncMock(side_effect=lambda _: dict(payload))
    _, first = await manager.fetch_attitude_observation()
    assert first == (100, None)
    payload["message"] = {**payload["message"], "time_boot_ms": 110}
    _, advanced = await manager.fetch_attitude_observation()
    assert advanced[1] is not None
    _, cached = await manager.fetch_attitude_observation()
    assert cached == advanced
    assert first == (100, None)  # Later fetches cannot mutate this evidence.
    payload["message"] = {**payload["message"], "time_boot_ms": 105}
    _, reordered = await manager.fetch_attitude_observation()
    assert reordered[1] is None
    manager.reset_attitude_receipt()
    _, reset = await manager.fetch_attitude_observation()
    assert reset[1] is None


def test_new_sdk_position_does_not_rejuvenate_attitude(monkeypatch):
    monkeypatch.setattr(Parameters, "FOLLOWER_MODE", "mc_attitude_rate")
    controller = PX4InterfaceManager()
    controller.active_mode = True
    controller._reset_telemetry_health("mavsdk")
    now = time.monotonic()
    for status in controller._telemetry_stream_status.values():
        status["last_update_monotonic_s"] = now
    controller._telemetry_stream_status["attitude"]["last_update_monotonic_s"] = (
        now - 0.1
    )
    controller._telemetry_pending_values = {
        "roll_deg": 0,
        "pitch_deg": 0,
        "yaw_deg": 0,
        "relative_altitude_m": 20,
        "ground_speed_m_s": 1,
    }
    assert controller._try_commit_mavsdk_telemetry_snapshot()
    assert controller._attitude_receipt_monotonic_s == now - 0.1
    controller._telemetry_stream_status["position"]["last_update_monotonic_s"] = (
        now + 0.1
    )
    assert controller._try_commit_mavsdk_telemetry_snapshot()
    assert controller._attitude_receipt_monotonic_s == now - 0.1


@pytest.mark.asyncio
async def test_actual_publisher_timing_and_ttl_are_used(monkeypatch):
    controller = interface(monkeypatch)
    commander = OffboardCommander(
        controller,
        controller.setpoint_handler,
        command_rate_hz=10,
        publish_timeout_s=0.7,
        command_ttl_s=1.5,
    )
    commander.submit_intent(
        CommandIntent(
            profile_name="mc_attitude_rate",
            control_type="attitude_rate",
            fields=fields(q=40),
            source="test",
        )
    )
    assert await commander.publish_once()
    guard = commander.get_status()["attitude_guard"]
    assert guard["horizon_s"] >= 1.5
    assert guard["effective_fields"]["pitchspeed_deg_s"] <= 1 / 1.5


@pytest.mark.asyncio
async def test_terminal_handoff_is_not_delayed_by_blocked_stop_rpc(monkeypatch):
    controller = interface(monkeypatch)
    controller.current_pitch = 36
    release = asyncio.Event()
    started = asyncio.Event()

    async def blocked(**_):
        started.set()
        await release.wait()
        return {"local_sender_quiesced": True}

    controller.quiesce_offboard_sender = blocked
    callback = AsyncMock()
    commander = OffboardCommander(
        controller, controller.setpoint_handler, on_failure_threshold=callback
    )
    assert not await asyncio.wait_for(commander.publish_once(), timeout=0.1)
    callback.assert_awaited_once()
    await started.wait()
    release.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_new_session_does_not_reuse_previous_attitude_guard_reason(monkeypatch):
    controller = interface(monkeypatch)
    controller.current_pitch = 36
    old = OffboardCommander(controller, controller.setpoint_handler)
    assert not await old.publish_once()
    assert old.terminal_failure_reason == "attitude_envelope_exceeded"
    await asyncio.sleep(0)
    controller.current_pitch = 0
    controller._safe_mavsdk_call.return_value = False
    new = OffboardCommander(
        controller, controller.setpoint_handler, command_failure_threshold=3
    )
    assert not await new.publish_once()
    assert new.terminal_failure_reason is None
    assert new.consecutive_failures == 1
    assert controller._terminal_attitude_guard_reason is None


@pytest.mark.asyncio
async def test_cross_profile_failure_does_not_reuse_mc_attitude_reason(monkeypatch):
    controller = interface(monkeypatch)
    controller._terminal_attitude_guard_reason = "attitude_envelope_exceeded"
    controller.setpoint_handler = SetpointHandler("fw_attitude_rate")
    controller.send_commands_unified = AsyncMock(return_value=False)
    commander = OffboardCommander(
        controller, controller.setpoint_handler, command_failure_threshold=3
    )
    assert not await commander.publish_once()
    assert commander.terminal_failure_reason is None
    assert commander.consecutive_failures == 1


@pytest.mark.asyncio
async def test_quiesce_is_owned_and_coalesced_until_manager_shutdown(monkeypatch):
    monkeypatch.setattr(Parameters, "FOLLOWER_MODE", "mc_attitude_rate")
    controller = PX4InterfaceManager()
    controller._mavsdk_offboard_sender_state = "primed"
    release = asyncio.Event()
    entered = asyncio.Event()

    async def blocked():
        entered.set()
        await release.wait()

    controller.drone = SimpleNamespace(
        offboard=SimpleNamespace(stop=AsyncMock(side_effect=blocked))
    )
    first = controller._begin_sender_quiesce("attitude_guard")
    assert controller._begin_sender_quiesce("teardown") is first
    await entered.wait()
    assert controller._get_owned_task_status()["sender_quiesce_alive"]
    shutdown = asyncio.create_task(controller.stop())
    await asyncio.sleep(0)
    assert not shutdown.done()
    release.set()
    outcome = await shutdown
    assert outcome["owned_tasks"]["all_stopped"]
    controller.drone.offboard.stop.assert_awaited_once()
