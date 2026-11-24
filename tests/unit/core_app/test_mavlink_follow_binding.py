"""Stock binding reuses phase ownership and the one FW recovery supervisor."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from classes.aircraft_state import AirframePhase, Vector3
from classes.mavlink_follow_binding import MavlinkFollowBinding
from classes.mavlink_guidance_source import MavlinkGuidanceSource
from classes.target_continuity import ContinuityContext, ContinuityPolicy, TargetContinuitySupervisor
from tests.unit.core_app.test_fixed_wing_continuity import evidence
from tests.unit.core_app.test_native_follow_binding import CONFIG
from tests.unit.drone_interface.test_mavlink_command_transport import Bench


def fixture():
    bench = Bench()
    initial = bench.observe()
    manager = SimpleNamespace(get_guidance_observation=lambda *args, **kwargs: bench.observe())
    source = MavlinkGuidanceSource(manager, initial.state.binding, bench.epoch,
        current_binding=lambda: initial.state.binding if bench.current else None,
        envelope=initial.state.fixed_wing_envelope, tuning=bench.guidance.projection.tuning)
    bench.guidance.phase_owner.capabilities = replace(bench.guidance.phase_owner.capabilities, runtime_id=source.runtime_id)
    connection = SimpleNamespace(connection_generation=1,
        get_aircraft_state=lambda: bench.observe().state if bench.fresh else None,
        get_mavlink_guidance_observation=bench.observe,
        get_mavsdk_command_timeout_s=lambda: .3,
        is_command_connection_ready=lambda **kwargs: bench.current,
        drone=SimpleNamespace(offboard=SimpleNamespace(is_active=AsyncMock(return_value=False)),
            mavlink_direct=SimpleNamespace(send_message=AsyncMock(side_effect=bench.send))))
    continuity = TargetContinuitySupervisor(ContinuityPolicy.from_mapping(CONFIG), clock=lambda: bench.now)
    continuity.reset_session(session_epoch=1, reason="start")
    target = [evidence()]
    base = ContinuityContext("PX4", AirframePhase.FIXED_WING, "fixed_wing_external", True, False, True,
        vehicle_yaw_deg=0.)
    binding = MavlinkFollowBinding(bench.guidance, connection, source, continuity, continuity_config=CONFIG,
        target_evidence=lambda: target[0], context=lambda: base, owns_session=lambda: bench.current,
        circuit_breaker=lambda: bench.breaker, command_period_s=.05, prime_duration_s=.1, clock=lambda: bench.now)
    binding.transport.sleep = bench.sleep
    return SimpleNamespace(bench=bench, binding=binding, source=source, connection=connection, continuity=continuity,
        target=target, base=base, start_context=source.start_context)


async def engage(f):
    baseline = await f.binding.engage(start_context=f.start_context, before_dispatch=lambda: None)
    await f.bench.sleep(.15)
    assert f.binding.transport.ready()
    return baseline


@pytest.mark.asyncio
async def test_stock_start_binds_existing_continuity_and_stop_confirms_only_observed_handoff():
    f = fixture()
    baseline = await engage(f)
    assert baseline.guidance_identity == f.bench.guidance.identity
    assert f.continuity.policy.mode.value == "bounded_flight"
    assert f.binding.owner_confirmed and not f.binding.release_confirmed
    result = await f.binding.stop("operator_stop")
    assert result["executed"] and f.binding.release_confirmed
    assert not f.binding.owner_confirmed
    assert f.binding.context(f.base).offboard_active is False
    assert not hasattr(f.binding, "release_receipt")  # Standard mode observation is not an atomic native receipt.


@pytest.mark.asyncio
async def test_an_sdk_autoresend_owner_cannot_overlap_stock_acquisition():
    f = fixture()
    f.connection.drone.offboard.is_active.return_value = True
    with pytest.raises(ValueError, match="autoresend_owner_active"):
        await engage(f)
    assert not f.bench.sent


@pytest.mark.asyncio
async def test_stale_start_editor_cannot_rebind_new_phase_or_parameter_authority():
    f = fixture()
    with pytest.raises(ValueError, match="start_context_changed"):
        await f.binding.engage(start_context=replace(f.start_context, mode_generation=2), before_dispatch=lambda: None)
    assert not f.bench.sent


@pytest.mark.asyncio
async def test_target_loss_retains_fw_course_and_speed_until_original_eight_second_deadline():
    f = fixture()
    await engage(f)
    nominal = f.bench.guidance.calculate_ned(Vector3(1., .1, .1).normalized(), frame="ned")
    decision = f.continuity.evaluate(evidence(), f.binding.context(f.base), nominal, now_monotonic_s=f.bench.now)
    assert decision.authorized_intent is not None
    f.target[0] = evidence(False)
    began = f.bench.now
    previous = None
    for _ in range(79):
        await f.bench.sleep(.1)
        assert f.binding.transport.ready()
        decision = f.continuity.evaluate(evidence(False), f.binding.context(f.base), now_monotonic_s=f.bench.now)
        assert decision.handoff_request is None
        intent = decision.authorized_intent
        assert intent.fields["equivalent_airspeed_m_s"] == nominal.fields["equivalent_airspeed_m_s"]
        assert intent.fields["course_rad"] == nominal.fields["course_rad"]
        previous = intent
        assert await f.binding.transport.publish(intent, reason="recovery", ttl_s=.5)
    # Retargets use the same episode, never a new timer or MC travel budget.
    assert f.continuity.begin_target_transition(session_epoch=2, previous_intent=previous)
    await f.bench.sleep(.3)
    assert f.binding.transport.ready()
    decision = f.continuity.evaluate(evidence(False, epoch=2), f.binding.context(f.base), now_monotonic_s=f.bench.now)
    assert f.bench.now - began > 8.
    assert decision.handoff_request is not None
    assert (await f.binding.stop(decision.reason_code))["executed"]


@pytest.mark.asyncio
async def test_transition_stops_sender_without_claiming_an_aircraft_side_release_or_replaying_hold():
    f = fixture()
    await engage(f)
    f.bench.phase = AirframePhase.VTOL_TRANSITION
    assert not f.binding.transport.ready()
    assert f.bench.guidance.controls.current_control is None
    result = await f.binding.stop("transition")
    assert result["local_sender_quiesced"] and not result["executed"]
    assert not f.binding.release_confirmed
    assert len(f.bench.mode_packets()) == 1
