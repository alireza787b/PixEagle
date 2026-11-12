"""Native lifecycle composition; no PX4 movement is inferred from commands."""

import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.command_dispatch_guard import DispatchRefused
from classes.aircraft_state import AircraftKind, AircraftLayout, AircraftStateOwner, AirframePhase
from classes.native_follow_binding import NativeFollowBinding, requires_native_guidance
from classes.native_guidance import NativeGuidanceError
from classes.target_continuity import ContinuityContext, ContinuityPolicy, TargetContinuitySupervisor
from tests.unit.core_app.test_fixed_wing_continuity import evidence
from tests.unit.followers.test_vector_guidance_session import session
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.fixtures.native_ownership import acquisition, release_receipt


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
    client = SimpleNamespace(session_identity=None, acquisition_token=None, acquisition_context=None,
                             abort=Mock(), submit=AsyncMock(), handoff=AsyncMock())

    async def engage(identity, **kwargs):
        from classes.command_dispatch_guard import validate_before_dispatch
        validate_before_dispatch(kwargs.get("before_dispatch"))
        validate_before_dispatch(kwargs.get("on_mode_dispatch"))
        client.session_identity = identity
        client.acquisition_token = kwargs["ownership_token"]
        client.acquisition_context = acquisition(identity, runtime_id=guidance.phase_owner.capabilities.runtime_id,
                                                 token=client.acquisition_token)
        client.handoff.return_value = release_receipt(client.acquisition_context)
        client.observe_after_release.return_value = release_receipt(client.acquisition_context, outcome="owner_already_released", nav_state=5)
        return {"owner_confirmed": True, "runtime_id": client.acquisition_context.runtime_id,
                "acquisition": client.acquisition_context.wire_payload()}

    def abort():
        client.session_identity = None

    def packet():
        return {"aircraft_state": asdict(connection.get_aircraft_state()), "owner_confirmed": True,
                "fresh": True, "rescue_active": False, "nav_state": 23, "nav_state_timestamp": 300, "release_receipt": None}

    client.engage = AsyncMock(side_effect=engage)
    client.observe = AsyncMock(side_effect=packet)
    client.abort.side_effect = abort
    client.matches_acquisition = lambda identity, runtime, token, known=None: (
        client.acquisition_context is not None and client.acquisition_context.identity == identity
        and client.acquisition_context.runtime_id == runtime and client.acquisition_token == token
        and (known is None or client.acquisition_context == known))
    client.observe_after_release = AsyncMock()
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
                                         "fixed_wing": "fixed_wing_external"}}
    assert requires_native_guidance(profile, kind) is required
    assert requires_native_guidance({}, kind) is False


def test_unknown_aircraft_cannot_be_assumed_to_be_a_multicopter():
    with pytest.raises(ValueError, match="aircraft_kind_unavailable"):
        requires_native_guidance({"native_phase_contracts": {"fixed_wing": "fixed_wing_external"}}, AircraftKind.UNKNOWN)
    with pytest.raises(ValueError, match="strategy_unavailable"):
        requires_native_guidance({"native_phase_contracts": {"vtol_transition": "vtol_transition_external"}}, AircraftKind.VTOL)


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
                                                             "fixed_wing": "fixed_wing_external"}},
                                 kind, expected_layout=layout)


async def test_engagement_binds_one_generation_and_starts_with_a_phase_safe_objective():
    f = fixture()
    baseline = await f.binding.engage()
    assert f.client.engage.await_count == 1
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


@pytest.mark.parametrize("phase", [AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING])
async def test_transition_ends_one_owner_and_does_not_reacquire_or_rebind(phase):
    f = fixture(phase=phase)
    original = f.guidance.identity
    await f.binding.engage()
    with pytest.raises(DispatchRefused, match="aircraft_transition_observed"):
        await f.observation(AirframePhase.VTOL_TRANSITION)
    assert f.binding.terminal_reason == "aircraft_transition_observed"
    assert not f.binding.owner_confirmed
    assert f.guidance.identity.guidance_generation == original.guidance_generation + 1
    assert f.binding.transport.identity == original
    f.client.engage.assert_awaited_once()
    with pytest.raises(DispatchRefused, match="follow_stopping"):
        await f.binding.on_observation(f.state, f.packet(), None)
    result = await f.binding.stop("transition_cleanup")
    assert result["local_sender_quiesced"]
    f.client.handoff.assert_not_called()
    assert f.binding.release_receipt.released


async def test_phase_packet_before_next_pose_ends_without_refreshing_old_pose():
    f = fixture(phase=AirframePhase.MULTICOPTER)
    await f.binding.engage()
    previous = f.connection.get_aircraft_state()
    f.clock[0] += .1
    changed = replace(previous, sequence=previous.sequence + 1, phase=AirframePhase.VTOL_TRANSITION)
    assert f.connection.commit_aircraft_state(changed)
    with pytest.raises(DispatchRefused, match="aircraft_transition_observed"):
        await f.binding.on_observation(changed, f.packet(), None)
    assert f.connection.get_aircraft_state().observed_at_monotonic_s == previous.observed_at_monotonic_s
    f.clock[0] += .8
    assert f.connection.get_aircraft_state() is None


async def test_retarget_loss_uses_frozen_configuration_without_phase_rebinding():
    f = fixture()
    baseline = await f.binding.engage()
    f.target[0] = evidence(False)
    f.continuity.evaluate(f.target[0], f.binding.context(f.base), baseline)
    f.config["MAX_COAST_TIME_S"] = 50.
    f.clock[0] += .1
    await f.observation()
    assert f.continuity.policy.max_coast_time_s == 8.
    f.continuity.evaluate(f.target[0], f.binding.context(f.base), f.guidance.baseline())
    assert f.continuity.get_status()["loss_elapsed_s"] == pytest.approx(.2)


async def test_stop_revokes_controls_before_awaiting_handoff_and_never_reengages():
    f = fixture()
    await f.binding.engage()
    captured = f.client.session_identity
    entered, finish = asyncio.Event(), asyncio.Event()

    async def handoff(*_, **__):
        entered.set()
        await finish.wait()
        return release_receipt(f.client.acquisition_context)

    f.client.handoff.side_effect = handoff
    task = asyncio.create_task(f.binding.stop("operator_stop"))
    await entered.wait()
    assert not f.binding.owner_confirmed
    assert f.binding.guidance.controls.current_control is None
    with pytest.raises(DispatchRefused, match="stopping"):
        await f.binding.on_observation(f.state, f.packet(), None)
    finish.set()
    assert (await task)["executed"]
    f.client.handoff.assert_awaited_once_with(captured, reason="operator_stop",
        ownership_token=f.binding._ownership_token, acquisition=f.binding._acquisition)
    assert f.client.engage.await_count == 1


async def test_stop_confirms_abort_handoff_without_sending_a_second_mode_command():
    f = fixture()
    await f.binding.engage()
    f.client.abort()
    f.client.observe_after_release.return_value = release_receipt(f.client.acquisition_context)
    result = await f.binding.stop("operator_stop")
    assert result["executed"]
    assert result["reason"] == "operator_stop"
    f.client.observe_after_release.assert_awaited_once_with(
        f.binding._acquisition_identity, runtime_id=f.guidance.phase_owner.capabilities.runtime_id,
        ownership_token=f.binding._ownership_token, mode_id=23, acquisition=f.client.acquisition_context,
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
    with pytest.raises(DispatchRefused):
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


async def test_ack_activation_is_frozen_before_a_later_observation_epoch():
    f = fixture()
    await f.binding.engage()
    assert f.binding._acquisition.activation_timestamp == 200
    assert f.packet()['nav_state_timestamp'] == 300
    f.client.abort()
    f.client.observe_after_release.return_value = release_receipt(f.client.acquisition_context)
    assert (await f.binding.stop('operator_stop'))['executed']
    expected = f.client.observe_after_release.call_args.kwargs['acquisition']
    assert expected.activation_timestamp == 200


async def test_lost_ack_binding_retains_predispatch_token_for_read_only_cleanup():
    f = fixture()
    original = f.client.engage.side_effect

    async def lost_ack(identity, **kwargs):
        await original(identity, **kwargs)
        raise NativeGuidanceError('native_reply_missing')

    f.client.engage.side_effect = lost_ack
    with pytest.raises(NativeGuidanceError, match='reply_missing'):
        await f.binding.engage()
    token = f.binding._ownership_token
    assert token == f.client.acquisition_context.token
    assert f.binding._acquisition is None
    result = await f.binding.stop('start_failed')
    assert not result['executed']
    assert result['reason'] == 'native_owner_already_released'
    f.client.observe_after_release.assert_awaited_once_with(
        f.binding._acquisition_identity, runtime_id=f.binding._runtime_id,
        ownership_token=token, mode_id=23, acquisition=None)
    f.client.handoff.assert_not_called()


async def test_duplicate_concurrent_cleanup_uses_one_correlated_handoff():
    f = fixture()
    await f.binding.engage()
    entered, release = asyncio.Event(), asyncio.Event()

    async def handoff(*_, **__):
        entered.set()
        await release.wait()
        return release_receipt(f.client.acquisition_context)

    f.client.handoff.side_effect = handoff
    first = asyncio.create_task(f.binding.stop('operator_stop'))
    await entered.wait()
    second = asyncio.create_task(f.binding.stop('operator_stop'))
    await asyncio.sleep(0)
    assert f.client.handoff.await_count == 1
    release.set()
    assert (await first)['executed']
    assert (await second)['executed']
    assert (await f.binding.stop('operator_stop'))['executed']
    assert f.client.handoff.await_count == 1
    f.client.observe_after_release.assert_not_called()


async def test_unconfirmed_cleanup_can_only_retry_read_only():
    f = fixture()
    await f.binding.engage()
    f.client.handoff.return_value = release_receipt(f.client.acquisition_context, outcome='unconfirmed')
    with pytest.raises(NativeGuidanceError, match='release_unconfirmed'):
        await f.binding.stop('operator_stop')
    assert f.binding._release_receipt is None
    f.client.observe_after_release.return_value = release_receipt(f.client.acquisition_context)
    assert (await f.binding.stop('operator_stop'))['executed']
    assert f.client.handoff.await_count == 1
    assert f.client.observe_after_release.await_count == 1


async def test_same_identity_replacement_acquisition_is_not_aborted_or_confirmed():
    f = fixture()
    await f.binding.engage()
    f.client.acquisition_context = replace(f.client.acquisition_context, firmware_incarnation='e' * 32)
    with pytest.raises(NativeGuidanceError, match='session_replaced'):
        await f.binding.stop('old_cleanup')
    f.binding.abort('obsolete_abort')
    f.client.abort.assert_not_called()
    f.client.handoff.assert_not_called()
    f.client.observe_after_release.assert_not_called()


async def test_stop_during_delayed_engage_ack_cannot_revive_binding():
    f = fixture()
    original = f.client.engage.side_effect
    entered, release = asyncio.Event(), asyncio.Event()

    async def delayed_ack(identity, **kwargs):
        result = await original(identity, **kwargs)
        entered.set()
        await release.wait()
        return result

    f.client.engage.side_effect = delayed_ack
    task = asyncio.create_task(f.binding.engage())
    await entered.wait()
    result = await f.binding.stop('operator_stop')
    assert not result['executed']
    assert result['local_sender_quiesced']
    assert f.client.session_identity is None
    f.client.abort.assert_called()
    release.set()
    with pytest.raises(NativeGuidanceError, match='follow_stopping'):
        await task
    assert not f.binding.owner_confirmed
    f.client.observe.assert_not_called()
    f.client.submit.assert_not_called()
    f.client.handoff.assert_not_called()


async def test_stop_while_acquisition_is_queued_refuses_write_before_dispatch():
    f = fixture()
    original = f.client.engage.side_effect
    entered, release = asyncio.Event(), asyncio.Event()

    async def queued(identity, **kwargs):
        entered.set()
        await release.wait()
        return await original(identity, **kwargs)

    f.client.engage.side_effect = queued
    task = asyncio.create_task(f.binding.engage())
    await entered.wait()
    result = await f.binding.stop('operator_stop')
    assert result['reason'] == 'native_acquire_not_dispatched'
    release.set()
    with pytest.raises(DispatchRefused, match='follow_stopping'):
        await task
    assert not f.binding.acquire_dispatched
    assert f.client.acquisition_context is None
    f.client.observe.assert_not_called()
    f.client.handoff.assert_not_called()


@pytest.mark.parametrize("invalid", [False, "fixed_wing", "multicopter", 1, object()])
def test_initial_phase_is_typed_before_start(invalid):
    from classes.guidance_phase_session import GuidancePhaseSession
    f = fixture()
    with pytest.raises(ValueError, match="initial_aircraft_phase_unavailable"):
        GuidancePhaseSession(f.guidance.identity, f.guidance.phase_owner.capabilities,
            confirmation_s=.5, observation_timeout_s=.75, initial_phase=invalid)


async def test_cached_release_property_rejects_wrong_binding_and_unreleased_receipt():
    f = fixture()
    await f.binding.engage()
    f.binding._release_receipt = release_receipt(f.client.acquisition_context, outcome="unconfirmed")
    with pytest.raises(NativeGuidanceError, match="release_unconfirmed"):
        f.binding.release_receipt
    f.binding._release_receipt = release_receipt(replace(f.client.acquisition_context, token="e" * 32))
    with pytest.raises(NativeGuidanceError):
        f.binding.release_receipt
    with pytest.raises(NativeGuidanceError):
        await f.binding.stop("cleanup")


async def test_actual_transition_reason_survives_coincident_owner_release():
    f = fixture()
    await f.binding.engage()
    state = replace(f.state, sequence=f.state.sequence + 1, phase=AirframePhase.VTOL_TRANSITION)
    assert f.connection.commit_aircraft_state(state)
    packet = f.packet() | {"owner_confirmed": False}
    with pytest.raises(DispatchRefused, match="aircraft_transition_observed"):
        await f.binding.on_observation(state, packet, None)
    assert f.connection.get_aircraft_state().phase is AirframePhase.VTOL_TRANSITION
    assert f.binding.terminal_reason == "aircraft_transition_observed"
    f.client.engage.assert_awaited_once()
