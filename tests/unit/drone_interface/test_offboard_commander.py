"""Unit tests for the async OffboardCommander heartbeat boundary."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from classes.command_intent import CommandIntent
from classes.offboard_commander import OffboardCommander


def _handler(fields=None, control_type="velocity_body_offboard"):
    state = fields or {
        "vel_body_fwd": 0.0,
        "vel_body_right": 0.0,
        "vel_body_down": 0.0,
        "yawspeed_deg_s": 0.0,
    }

    def reset_setpoints():
        for key in state:
            state[key] = 0.0

    def set_fields(fields, **_kwargs):
        expected = set(state.keys())
        provided = set(fields.keys())
        if provided != expected:
            raise ValueError("fields do not match active profile")
        for key, value in fields.items():
            state[key] = float(value)
        return CommandIntent(
            profile_name="test_profile",
            control_type=control_type,
            fields=state.copy(),
            source=_kwargs.get("source", "unit_test"),
            reason=_kwargs.get("reason"),
        )

    return SimpleNamespace(
        get_control_type=MagicMock(return_value=control_type),
        get_fields=MagicMock(side_effect=lambda: state.copy()),
        set_fields=MagicMock(side_effect=set_fields),
        reset_setpoints=MagicMock(side_effect=reset_setpoints),
    )


def _intent(fields=None, control_type="velocity_body_offboard", created_at=None):
    return CommandIntent(
        profile_name="test_profile",
        control_type=control_type,
        fields=fields or {
            "vel_body_fwd": 1.0,
            "vel_body_right": 0.0,
            "vel_body_down": 0.0,
            "yawspeed_deg_s": 0.0,
        },
        source="unit_test",
        reason="test",
        created_at_monotonic_s=created_at if created_at is not None else time.monotonic(),
    )


@pytest.mark.asyncio
async def test_offboard_commander_transient_publish_failure_recovers_before_threshold():
    px4 = SimpleNamespace(
        send_commands_unified=AsyncMock(side_effect=[RuntimeError("temporary"), True])
    )
    failure_callback = MagicMock()
    commander = OffboardCommander(
        px4,
        _handler(),
        command_rate_hz=20.0,
        command_ttl_s=0.5,
        command_failure_threshold=2,
        on_failure_threshold=failure_callback,
    )

    assert await commander.publish_once(reason="unit_test") is False
    assert commander.get_status()["last_error"] == "temporary"
    assert commander.get_status()["health_state"] == "stopped"
    assert await commander.publish_once(reason="unit_test") is True

    status = commander.get_status()
    assert status["consecutive_failures"] == 0
    assert status["last_error"] is None
    assert status["failure_policy_triggered"] is False
    failure_callback.assert_not_called()


@pytest.mark.asyncio
async def test_offboard_commander_publish_and_final_stop_are_bounded():
    async def never_finishes():
        await asyncio.Event().wait()

    px4 = SimpleNamespace(send_commands_unified=never_finishes)
    commander = OffboardCommander(
        px4,
        _handler(),
        command_failure_threshold=1,
        publish_timeout_s=0.01,
    )

    assert await commander.publish_once(reason="unit_test") is False
    assert "deadline" in commander.get_status()["last_error"]

    await asyncio.wait_for(
        commander.stop(publish_final=True),
        timeout=0.2,
    )


@pytest.mark.asyncio
async def test_offboard_commander_publish_failure_threshold_triggers_local_policy_once():
    px4 = SimpleNamespace(send_commands_unified=AsyncMock(return_value=False))
    failure_events = []

    def on_failure(status):
        failure_events.append(status)

    commander = OffboardCommander(
        px4,
        _handler(),
        command_rate_hz=20.0,
        command_ttl_s=0.5,
        command_failure_threshold=2,
        on_failure_threshold=on_failure,
    )
    commander.running = True

    assert await commander.publish_once(reason="unit_test") is False
    assert commander.get_status()["failure_policy_triggered"] is False

    assert await commander.publish_once(reason="unit_test") is False
    assert await commander.publish_once(reason="unit_test") is False

    status = commander.get_status()
    assert status["running"] is False
    assert status["health_state"] == "failed"
    assert status["failure_policy_triggered"] is True
    assert status["failure_policy_trigger_count"] == 1
    assert status["consecutive_failures"] == 3
    assert len(failure_events) == 1
    assert failure_events[0]["consecutive_failures"] == 2


@pytest.mark.asyncio
async def test_offboard_commander_validation_failure_injection_trips_policy_without_mavsdk():
    px4 = SimpleNamespace(send_commands_unified=AsyncMock(return_value=True))
    failure_callback = MagicMock()
    commander = OffboardCommander(
        px4,
        _handler(),
        command_rate_hz=20.0,
        command_ttl_s=0.5,
        command_failure_threshold=3,
        on_failure_threshold=failure_callback,
    )
    commander.running = True

    result = await commander.inject_publish_failures_for_validation(
        failure_count=3,
        reason="sitl_commander_publish_failure",
        invoke_failure_callback=False,
    )

    px4.send_commands_unified.assert_not_awaited()
    failure_callback.assert_not_called()
    assert result["applied_failure_count"] == 3
    assert result["failure_policy_triggered"] is True
    status = result["offboard_commander"]
    assert status["running"] is False
    assert status["health_state"] == "failed"
    assert status["consecutive_failures"] == 3
    assert status["command_failure_threshold"] == 3
    assert status["last_publish_success"] is False
    assert status["last_publish_reason"] == "sitl_commander_publish_failure"
    assert status["failure_policy_trigger_count"] == 1


@pytest.mark.asyncio
async def test_offboard_commander_validation_failure_blocks_waiting_heartbeat_publish():
    """A heartbeat waiting on the publish lock must not send after failure injection."""
    px4 = SimpleNamespace(send_commands_unified=AsyncMock(return_value=True))
    commander = OffboardCommander(
        px4,
        _handler(),
        command_rate_hz=20.0,
        command_ttl_s=0.5,
        command_failure_threshold=3,
    )
    commander.running = True

    await commander._publish_lock.acquire()
    inject_task = asyncio.create_task(
        commander.inject_publish_failures_for_validation(
            failure_count=3,
            reason="sitl_commander_publish_failure",
            invoke_failure_callback=False,
        )
    )
    await asyncio.sleep(0)
    heartbeat_task = asyncio.create_task(commander._publish_once(reason="heartbeat"))
    await asyncio.sleep(0)

    commander._publish_lock.release()
    injection_result = await inject_task
    heartbeat_result = await heartbeat_task

    px4.send_commands_unified.assert_not_awaited()
    assert injection_result["failure_policy_triggered"] is True
    assert heartbeat_result is False
    assert commander.running is False
    assert commander.get_status()["health_state"] == "failed"


@pytest.mark.asyncio
async def test_offboard_commander_operator_stop_final_publish_does_not_trigger_failure_policy():
    px4 = SimpleNamespace(send_commands_unified=AsyncMock(return_value=False))
    failure_callback = MagicMock()
    commander = OffboardCommander(
        px4,
        _handler(),
        command_rate_hz=20.0,
        command_ttl_s=0.5,
        command_failure_threshold=1,
        on_failure_threshold=failure_callback,
    )
    commander.running = True

    await commander.stop(publish_final=True)

    status = commander.get_status()
    assert status["failed_publishes"] == 1
    assert status["failure_policy_triggered"] is False
    failure_callback.assert_not_called()


@pytest.mark.asyncio
async def test_offboard_commander_validation_failures_trigger_threshold_policy():
    px4 = SimpleNamespace()
    failure_events = []
    commander = OffboardCommander(
        px4,
        _handler(),
        command_rate_hz=20.0,
        command_ttl_s=0.5,
        command_failure_threshold=2,
        on_failure_threshold=lambda status: failure_events.append(status),
    )
    commander.running = True

    assert await commander.publish_once(reason="unit_test") is False
    assert await commander.publish_once(reason="unit_test") is False

    status = commander.get_status()
    assert status["failure_policy_triggered"] is True
    assert status["health_state"] == "failed"
    assert status["running"] is False
    assert status["consecutive_failures"] == 2
    assert len(failure_events) == 1
    assert "send_commands_unified" in status["last_error"]


@pytest.mark.asyncio
async def test_offboard_commander_stop_serializes_final_publish_after_heartbeat():
    events = []
    first_publish_started = asyncio.Event()
    release_first_publish = asyncio.Event()
    active_publishes = 0
    max_active_publishes = 0

    async def send_commands_unified():
        nonlocal active_publishes, max_active_publishes
        active_publishes += 1
        max_active_publishes = max(max_active_publishes, active_publishes)
        events.append("send")
        if len(events) == 1:
            first_publish_started.set()
            await release_first_publish.wait()
        await asyncio.sleep(0)
        active_publishes -= 1
        return 1

    px4 = SimpleNamespace(
        send_commands_unified=AsyncMock(side_effect=send_commands_unified)
    )
    commander = OffboardCommander(
        px4,
        _handler(),
        command_rate_hz=50.0,
        command_ttl_s=1.0,
        command_failure_threshold=2,
    )

    assert await commander.start() is True
    await asyncio.wait_for(first_publish_started.wait(), timeout=1.0)

    stop_task = asyncio.create_task(commander.stop(publish_final=True))
    await asyncio.sleep(0.05)
    assert not stop_task.done()

    release_first_publish.set()
    await stop_task

    assert max_active_publishes == 1
    assert events == ["send", "send"]
    assert commander.get_status()["running"] is False


@pytest.mark.asyncio
async def test_offboard_commander_publishes_independently_until_stopped():
    px4 = SimpleNamespace(send_commands_unified=AsyncMock(return_value=True))
    commander = OffboardCommander(
        px4,
        _handler(),
        command_rate_hz=50.0,
        command_ttl_s=1.0,
    )

    assert await commander.start() is True
    await asyncio.sleep(0.07)
    await commander.stop(publish_final=False)

    assert px4.send_commands_unified.await_count >= 2
    status = commander.get_status()
    assert status["running"] is False
    assert status["sends_mavsdk_commands"] is True
    assert status["command_publication_source"] == "offboard_commander"


def test_offboard_commander_accepts_matching_command_intent():
    handler = _handler()
    commander = OffboardCommander(
        SimpleNamespace(send_commands_unified=AsyncMock(return_value=True)),
        handler,
        command_rate_hz=20.0,
        command_ttl_s=0.5,
    )

    intent = _intent()
    assert commander.submit_intent(intent) is True
    handler.set_fields.assert_called_once_with(
        intent.fields,
        source=intent.source,
        reason=intent.reason,
    )
    assert handler.get_fields() == intent.fields
    assert commander.get_status()["last_intent_fresh"] is True
    assert commander.get_status()["rejected_intents"] == 0


def test_offboard_commander_failsafe_defaults_invalidate_prior_intent():
    handler = _handler()
    commander = OffboardCommander(
        SimpleNamespace(send_commands_unified=AsyncMock(return_value=True)),
        handler,
    )
    assert commander.submit_intent(_intent()) is True

    commander.activate_failsafe_defaults("tracker_output_rejected")

    assert handler.get_fields() == {
        "vel_body_fwd": 0.0,
        "vel_body_right": 0.0,
        "vel_body_down": 0.0,
        "yawspeed_deg_s": 0.0,
    }
    status = commander.get_status()
    assert status["last_intent_fresh"] is False
    assert status["failsafe_defaults_active"] is True


@pytest.mark.asyncio
async def test_offboard_commander_publishes_applied_command_intent_fields():
    handler = _handler()

    async def send_commands_unified():
        assert handler.get_fields()["vel_body_fwd"] == 3.0
        assert handler.get_fields()["vel_body_right"] == -1.0
        return 1

    px4 = SimpleNamespace(send_commands_unified=AsyncMock(side_effect=send_commands_unified))
    commander = OffboardCommander(
        px4,
        handler,
        command_rate_hz=20.0,
        command_ttl_s=0.5,
    )

    assert commander.submit_intent(
        _intent(fields={
            "vel_body_fwd": 3.0,
            "vel_body_right": -1.0,
            "vel_body_down": 0.0,
            "yawspeed_deg_s": 0.0,
        })
    ) is True

    assert await commander.publish_once(reason="unit_test") is True
    px4.send_commands_unified.assert_awaited_once()


@pytest.mark.asyncio
async def test_offboard_commander_publish_callback_uses_completed_send_evidence():
    events = []
    px4 = SimpleNamespace(
        send_commands_unified=AsyncMock(side_effect=[True, False])
    )
    commander = OffboardCommander(
        px4,
        _handler(),
        command_rate_hz=20.0,
        command_ttl_s=0.5,
        on_publish_result=lambda event: events.append(event),
    )
    intent = _intent()

    assert commander.submit_intent(intent) is True
    assert await commander.publish_once(reason="fresh_intent") is True

    commander.activate_failsafe_defaults("tracker_output_rejected")
    assert await commander.publish_once(reason="failsafe_default") is False

    assert len(events) == 2
    assert events[0]["reason"] == "fresh_intent"
    assert events[0]["command_intent"].fields == intent.fields
    assert events[0]["publish_status"]["last_publish_success"] is True
    assert events[1]["reason"] == "failsafe_default"
    assert events[1]["command_intent"] is None
    assert events[1]["publish_status"]["last_publish_success"] is False


def test_offboard_commander_rejects_mismatched_command_intent():
    commander = OffboardCommander(
        SimpleNamespace(send_commands_unified=AsyncMock(return_value=True)),
        _handler(control_type="velocity_body_offboard"),
        command_rate_hz=20.0,
        command_ttl_s=0.5,
    )

    assert commander.submit_intent(_intent(control_type="attitude_rate")) is False
    assert commander.get_status()["rejected_intents"] == 1


@pytest.mark.asyncio
async def test_offboard_commander_stale_intent_applies_default_setpoints():
    handler = _handler()
    px4 = SimpleNamespace(send_commands_unified=AsyncMock(return_value=True))
    commander = OffboardCommander(
        px4,
        handler,
        command_rate_hz=20.0,
        command_ttl_s=0.1,
    )
    stale_intent = _intent(created_at=time.monotonic() - 1.0)

    assert commander.submit_intent(stale_intent) is True
    assert await commander.publish_once(reason="unit_test") is True

    handler.reset_setpoints.assert_called_once()
    px4.send_commands_unified.assert_awaited_once()
    status = commander.get_status()
    assert status["failsafe_defaults_active"] is True
    assert status["stale_intent_resets"] == 1


@pytest.mark.asyncio
async def test_offboard_commander_records_publish_failures():
    px4 = SimpleNamespace(send_commands_unified=AsyncMock(return_value=False))
    commander = OffboardCommander(
        px4,
        _handler(),
        command_rate_hz=20.0,
        command_ttl_s=0.5,
    )

    assert await commander.publish_once(reason="unit_test") is False

    status = commander.get_status()
    assert status["publish_count"] == 1
    assert status["failed_publishes"] == 1
    assert status["consecutive_failures"] == 1
    assert status["last_publish_success"] is False


@pytest.mark.asyncio
async def test_offboard_commander_rejects_stale_connection_generation():
    state = {"generation": 4, "ready": True}
    send = AsyncMock(return_value=True)

    def is_ready(*, expected_generation):
        return state["ready"] and expected_generation == state["generation"]

    px4 = SimpleNamespace(
        connection_generation=state["generation"],
        is_command_connection_ready=MagicMock(side_effect=is_ready),
        send_commands_unified=send,
    )
    commander = OffboardCommander(px4, _handler())
    state["generation"] += 1

    assert await commander.publish_once(reason="unit_test") is False
    send.assert_not_awaited()
    assert "generation changed" in commander.get_status()["last_error"]
