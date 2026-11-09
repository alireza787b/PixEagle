"""Native lifecycle composition; no PX4 movement is inferred from commands."""

import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.aircraft_state import AircraftKind, AircraftLayout, AircraftStateOwner, AirframePhase
from classes.native_follow_binding import NativeFollowBinding, requires_native_guidance
from classes.native_guidance import NativeGuidanceError
from classes.target_continuity import ContinuityContext, ContinuityPolicy, TargetContinuitySupervisor
from tests.unit.core_app.test_fixed_wing_continuity import evidence
from tests.unit.followers.test_gimbal_vector_session import session
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


CONFIG = dict(MODE="bounded_decay", MAX_COAST_TIME_S=8., MAX_COAST_DISTANCE_M=4.,
              MAX_RETARGET_TIME_S=8., REACQUIRE_CONFIRMATION_S=.5, AUTHORITY_RESTORE_TIME_S=.5,
              PhaseOverrides={"fixed_wing": dict(MODE="bounded_flight")})


def fixture(*, phase=AirframePhase.FIXED_WING, is_vtol=True):
    guidance, clock, state = session(state=aircraft_state(phase=phase, is_vtol=is_vtol, is_tailsitter=is_vtol))
    states = AircraftStateOwner(clock=lambda: clock[0])
    states.bind(state.binding)
    states.commit(state)
    connection = SimpleNamespace(get_aircraft_state=lambda: states.snapshot(timeout_s=.75),
                                 commit_aircraft_state=states.commit)
    client = SimpleNamespace(session_identity=None, abort=Mock(), submit=AsyncMock(),
                             handoff=AsyncMock(return_value={"hold_observed": True}))

    async def engage(identity, **_):
        client.session_identity = identity

    async def advance(identity):
        client.session_identity = identity

    def abort():
        client.session_identity = None

    def packet():
        return {"aircraft_state": asdict(connection.get_aircraft_state()), "owner_confirmed": True,
                "fresh": True, "rescue_active": False, "nav_state": 23, "nav_state_timestamp": 100}

    client.engage = AsyncMock(side_effect=engage)
    client.advance_generation = AsyncMock(side_effect=advance)
    client.observe = AsyncMock(side_effect=packet)
    client.abort.side_effect = abort
    client.observe_after_release = AsyncMock(return_value={"nav_state": 5, "rescue_active": False})
    config = deepcopy(CONFIG)
    continuity = TargetContinuitySupervisor(ContinuityPolicy.from_mapping(config), clock=lambda: clock[0])
    continuity.reset_session(session_epoch=1, reason="start")
    target = [evidence()]
    base = ContinuityContext("COMMAND_PREVIEW", phase, "fixed_wing_external", True, True, True,
                             vehicle_yaw_deg=0.)
    binding = NativeFollowBinding(
        guidance, connection, client, continuity, profile_name="gm_velocity_vector",
        continuity_config=config, target_evidence=lambda: target[0], context=lambda: base,
        circuit_breaker=lambda: False, clock=lambda: clock[0],
    )

    async def observation(phase=None, **changes):
        clock[0] += .1
        previous = connection.get_aircraft_state()
        next_state = replace(previous, sequence=previous.sequence + 1,
                             observed_at_monotonic_s=clock[0],
                             phase=phase or previous.phase, **changes)
        states.commit(next_state)
        payload = packet()
        return await binding.on_observation(next_state, payload, guidance.baseline())

    return SimpleNamespace(binding=binding, guidance=guidance, clock=clock, state=state,
                           connection=connection, client=client, continuity=continuity,
                           target=target, base=base, observation=observation, packet=packet, config=config)


@pytest.mark.parametrize("kind,required", [(AircraftKind.MULTICOPTER, False),
                                         (AircraftKind.FIXED_WING, True), (AircraftKind.VTOL, True)])
def test_transport_choice_uses_capabilities_and_actual_aircraft_kind(kind, required):
    profile = {"native_phase_contracts": {"multicopter": "velocity_body_offboard",
                                         "fixed_wing": "fixed_wing_external", "vtol_transition": "vtol_transition_external"}}
    assert requires_native_guidance(profile, kind) is required
    assert requires_native_guidance({}, kind) is False


def test_unknown_aircraft_cannot_be_assumed_to_be_a_multicopter():
    with pytest.raises(ValueError, match="aircraft_kind_unavailable"):
        requires_native_guidance({"native_phase_contracts": {"fixed_wing": "fixed_wing_external"}}, AircraftKind.UNKNOWN)
    with pytest.raises(ValueError, match="strategy_unavailable"):
        requires_native_guidance({"native_phase_contracts": {"fixed_wing": "fixed_wing_external"}}, AircraftKind.VTOL)


def test_legacy_recovery_configuration_is_not_silently_changed_after_engagement():
    f = fixture()
    with pytest.raises(ValueError, match="native_fixed_wing_continuity_not_configured"):
        NativeFollowBinding(
            f.guidance, f.connection, f.client, f.continuity, profile_name="gm_velocity_vector",
            continuity_config={"MODE": "immediate_handoff"}, target_evidence=lambda: evidence(),
            context=lambda: f.base, circuit_breaker=lambda: False,
        )
    f.client.engage.assert_not_called()


@pytest.mark.parametrize("layout,kind", [(AircraftLayout.VTOL_TAILSITTER, AircraftKind.MULTICOPTER),
                                       (AircraftLayout.FIXED_WING, AircraftKind.VTOL),
                                       (AircraftLayout.MULTICOPTER, AircraftKind.FIXED_WING)])
def test_wrong_explicit_layout_is_refused_before_any_command_owner_is_acquired(layout, kind):
    with pytest.raises(ValueError, match="aircraft_layout_mismatch"):
        requires_native_guidance({"native_phase_contracts": {"multicopter": "velocity_body_offboard",
                                                             "fixed_wing": "fixed_wing_external", "vtol_transition": "vtol_transition_external"}},
                                 kind, expected_layout=layout)


async def test_engagement_binds_one_generation_and_starts_with_a_phase_safe_objective():
    f = fixture()
    baseline = await f.binding.engage()
    assert f.client.engage.await_count == 1
    assert f.client.advance_generation.await_count == 1
    assert baseline.guidance_identity == f.client.session_identity
    assert baseline.control_type == "fixed_wing_external"
    assert baseline.fields["height_rate_m_s"] == 0.
    assert f.binding.owner_confirmed
    assert f.binding.context(replace(f.base, execution_mode="PX4")).execution_mode == "PX4_NATIVE"
    assert f.binding.context(f.base).pursuit_paused
    assert f.binding.paused_baseline().control_type == "fixed_wing_external"
    f.client.submit.assert_not_called()
    with pytest.raises(NativeGuidanceError, match="already_started"):
        await f.binding.engage()


async def test_both_transition_directions_use_one_owner_and_phase_specific_contracts():
    f = fixture(phase=AirframePhase.MULTICOPTER)
    await f.binding.engage()
    identities = [f.guidance.identity]
    for phase, contract in ((AirframePhase.VTOL_TRANSITION, "vtol_transition_external"),
                            (AirframePhase.FIXED_WING, "fixed_wing_external"),
                            (AirframePhase.VTOL_TRANSITION, "vtol_transition_external"),
                            (AirframePhase.MULTICOPTER, "velocity_body_offboard")):
        baseline = await f.observation(phase)
        assert baseline.control_type == contract
        assert f.binding.context(f.base).pursuit_paused
        identities.append(f.guidance.identity)
    assert len(set(identities)) == 5
    assert f.client.engage.await_count == 1
    assert f.client.advance_generation.await_count == 5
    assert f.guidance.controls.current_control.value == 0.


async def test_phase_packet_before_next_pose_advances_binding_without_refreshing_old_pose():
    f = fixture(phase=AirframePhase.MULTICOPTER)
    await f.binding.engage()
    previous = f.connection.get_aircraft_state()
    f.clock[0] += .1
    changed = replace(previous, sequence=previous.sequence + 1, phase=AirframePhase.VTOL_TRANSITION)
    assert f.connection.commit_aircraft_state(changed)
    intent = await f.binding.on_observation(changed, f.packet(), None)
    assert intent.control_type == "vtol_transition_external"
    assert intent.guidance_identity == f.client.session_identity
    assert f.connection.get_aircraft_state().observed_at_monotonic_s == previous.observed_at_monotonic_s
    assert f.client.engage.await_count == 1
    f.clock[0] += .8
    assert f.connection.get_aircraft_state() is None


async def test_transition_keeps_original_target_loss_deadline_and_frozen_configuration():
    f = fixture()
    baseline = await f.binding.engage()
    f.target[0] = evidence(False)
    f.continuity.evaluate(f.target[0], f.binding.context(f.base), baseline)
    started = f.continuity.get_status()["loss_elapsed_s"]
    assert started == 0.
    f.clock[0] += .1
    await f.observation(AirframePhase.VTOL_TRANSITION)
    # Editing the source mapping does not alter an already frozen session.
    f.config["MAX_COAST_TIME_S"] = 50.
    f.continuity.evaluate(f.target[0], f.binding.context(f.base), f.guidance.baseline())
    assert f.continuity.get_status()["loss_elapsed_s"] == pytest.approx(.2)
    for _ in range(77):
        await f.observation()
        result = f.continuity.evaluate(f.target[0], f.binding.context(f.base), f.guidance.baseline())
        assert result.handoff_request is None
    assert f.continuity.policy.max_coast_time_s == 8.
    f.clock[0] += .1
    with pytest.raises(NativeGuidanceError, match="maximum_coast_time_reached"):
        await f.observation(AirframePhase.FIXED_WING)
    f.client.abort.assert_called()
    f.client.submit.assert_not_called()


async def test_stop_revokes_controls_before_awaiting_handoff_and_never_reengages():
    f = fixture()
    await f.binding.engage()
    captured = f.client.session_identity
    entered, finish = asyncio.Event(), asyncio.Event()

    async def handoff(*_, **__):
        entered.set()
        await finish.wait()
        return {"hold_observed": True}

    f.client.handoff.side_effect = handoff
    task = asyncio.create_task(f.binding.stop("operator_stop"))
    await entered.wait()
    assert not f.binding.owner_confirmed
    assert f.binding.guidance.controls.current_control is None
    with pytest.raises(NativeGuidanceError, match="stopping"):
        await f.binding.on_observation(f.state, f.packet(), None)
    finish.set()
    assert (await task)["executed"]
    f.client.handoff.assert_awaited_once_with(captured, reason="operator_stop")
    assert f.client.engage.await_count == 1


async def test_stop_confirms_abort_handoff_without_sending_a_second_mode_command():
    f = fixture()
    await f.binding.engage()
    f.client.abort()
    f.client.observe_after_release.return_value = {"nav_state": 4, "rescue_active": False}
    result = await f.binding.stop("operator_stop")
    assert result["executed"]
    assert result["reason"] == "operator_stop"
    f.client.observe_after_release.assert_awaited_once_with(
        f.state.binding, runtime_id=f.guidance.phase_owner.capabilities.runtime_id,
        activation_timestamp=100,
    )
    f.client.handoff.assert_not_called()
    assert f.client.engage.await_count == 1


async def test_release_confirmation_failure_does_not_claim_success():
    f = fixture()
    await f.binding.engage()
    f.client.abort()
    f.client.observe_after_release.side_effect = NativeGuidanceError("native_release_unconfirmed")
    with pytest.raises(NativeGuidanceError, match="release_unconfirmed"):
        await f.binding.stop("operator_stop")
    f.client.handoff.assert_not_called()


async def test_stale_cleanup_never_closes_a_replacement_session_socket():
    f = fixture()
    await f.binding.engage()
    replacement = replace(f.client.session_identity, follow_session_id="new-follow")
    f.client.session_identity = replacement
    with pytest.raises(NativeGuidanceError, match="session_replaced"):
        await f.binding.stop("late_cleanup")
    assert f.client.session_identity == replacement
    f.client.abort.assert_not_called()
    f.client.observe_after_release.assert_not_called()
    f.client.handoff.assert_not_called()


@pytest.mark.parametrize("failure", ["takeover", "rescue", "binding"])
async def test_terminal_observations_cannot_resume_old_pursuit_or_issue_a_later_hold(failure):
    f = fixture()
    await f.binding.engage()
    packet = f.packet()
    state = f.state
    if failure == "takeover":
        packet["owner_confirmed"] = False
        f.client.session_identity = None
    elif failure == "rescue":
        state = replace(state, rescue_active=True)
    else:
        state = replace(state, binding=replace(state.binding, connection_generation="other"))
    with pytest.raises(NativeGuidanceError):
        await f.binding.on_observation(state, packet, None)
    result = await f.binding.stop("late_cleanup")
    assert result["local_sender_quiesced"]
    assert not result["executed"]
    f.client.handoff.assert_not_called()
    f.client.submit.assert_not_called()


@pytest.mark.parametrize("fresh,rescue", [(False, False), (True, True)])
async def test_failed_initial_observation_revokes_partial_engagement(fresh, rescue):
    f = fixture()
    packet = f.packet() | {"fresh": fresh, "rescue_active": rescue}
    f.client.observe.side_effect = None
    f.client.observe.return_value = packet
    with pytest.raises(NativeGuidanceError, match="state_unavailable"):
        await f.binding.engage()
    assert not f.binding.owner_confirmed
    f.client.abort.assert_called_once()
    f.client.advance_generation.assert_not_called()
