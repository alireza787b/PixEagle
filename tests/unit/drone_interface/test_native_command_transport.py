from dataclasses import asdict, replace
import asyncio
import math
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from classes.aircraft_state import AirframePhase, GuidanceSessionIdentity
from classes.command_intent import CommandIntent
from classes.fixed_wing_vector_guidance import FixedWingCommand
from classes.native_command_transport import NativeCommandTransport
from classes.offboard_commander import OffboardCommander
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.fixtures.native_ownership import acquisition, release_receipt


def setup_transport(state=None):
    state = state or aircraft_state()
    identity = GuidanceSessionIdentity("follow", state.binding, 1)
    client = SimpleNamespace(session_identity=identity, submit=AsyncMock(), advance_generation=AsyncMock(),
                             handoff=AsyncMock(return_value=release_receipt(acquisition(identity))), observe=AsyncMock(return_value={
                                 "aircraft_state": asdict(state), "owner_confirmed": True,
                                 "fresh": True, "rescue_active": False,
                             }))
    client.acquisition_context = acquisition(identity)
    client.acquisition_token = client.acquisition_context.token
    client.matches_acquisition = lambda original, runtime, token, known=None: (
        original == client.acquisition_context.identity and runtime == client.acquisition_context.runtime_id
        and token == client.acquisition_context.token and (known is None or known == client.acquisition_context))
    connection = SimpleNamespace(get_aircraft_state=lambda: state, commit_aircraft_state=lambda value: value == state)
    transport = NativeCommandTransport(client, connection, identity, circuit_breaker=lambda: False, clock=lambda: 100.1)
    transport.bind_acquisition(client.acquisition_context)
    return transport, client, identity


async def test_published_snapshot_requires_current_contract_owner_and_intent_freshness():
    transport, client, identity = setup_transport()
    intent = replace(FixedWingCommand(.3, 18., 0., None).intent(identity, profile_name="gm_velocity_vector", source="test"),
                     created_at_monotonic_s=100.)
    assert transport.published_intent(ttl_s=.5) is None
    await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    snapshot = transport.published_intent(ttl_s=.5)
    assert snapshot.fields == intent.fields
    snapshot.fields["course_rad"] = 100.
    assert transport.published_intent(ttl_s=.5).fields["course_rad"] == .3
    old = transport.connection.get_aircraft_state()
    transport.connection.get_aircraft_state = lambda: replace(old, phase=AirframePhase.MULTICOPTER, is_vtol=True)
    assert transport.published_intent(ttl_s=.5) is None
    transport.connection.get_aircraft_state = lambda: old
    transport.clock = lambda: 100.6
    assert transport.published_intent(ttl_s=.5) is None
    transport.clock = lambda: 100.2
    client.session_identity = None
    assert transport.published_intent(ttl_s=.5) is None


async def test_native_publication_count_excludes_previous_owners_and_local_acks_alone():
    transport, client, identity = setup_transport()
    intent = replace(FixedWingCommand(.3, 18., 0., None).intent(identity, profile_name="gm_velocity_vector", source="test"),
                     created_at_monotonic_s=100.)
    await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    assert transport.observed_publications is None
    client.observe.return_value["publications"] = 145
    await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    assert transport.observed_publications == 0
    client.observe.return_value["publications"] = 148
    await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    assert transport.observed_publications == 3
    client.session_identity = None
    assert transport.observed_publications is None


@pytest.mark.parametrize("bad", [True, False, -1, 1.5, None])
async def test_missing_or_invalid_native_count_is_unknown_without_blocking_control(bad):
    transport, client, identity = setup_transport()
    client.observe.return_value["publications"] = bad
    intent = replace(FixedWingCommand(.3, 18., 0., None).intent(identity, profile_name="gm_velocity_vector", source="test"),
                     created_at_monotonic_s=100.)
    assert await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    assert transport.observed_publications is None


async def test_a_counter_reset_cannot_be_reported_as_current_session_publication():
    transport, client, identity = setup_transport()
    intent = replace(FixedWingCommand(.3, 18., 0., None).intent(identity, profile_name="gm_velocity_vector", source="test"),
                     created_at_monotonic_s=100.)
    for count in (20, 21, 0, 30):
        client.observe.return_value["publications"] = count
        assert await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    assert transport.observed_publications is None


@pytest.mark.asyncio
async def test_native_start_requires_an_explicit_complete_initial_objective():
    transport, client, _ = setup_transport()
    commander = OffboardCommander(None, None, command_transport=transport)
    assert await commander.start() is False
    assert "fresh native objective" in commander.last_error
    client.submit.assert_not_called()
    client.handoff.assert_not_called()


@pytest.mark.asyncio
async def test_shared_commander_uses_native_fw_contract_without_mavsdk_or_zero_defaults(monkeypatch):
    transport, client, identity = setup_transport()
    monkeypatch.setattr("classes.offboard_commander.time.monotonic", lambda: 100.1)
    commander = OffboardCommander(None, None, command_transport=transport, command_ttl_s=.5)
    command = FixedWingCommand(.3, 18., None, 550.).intent(identity, profile_name="gm_velocity_vector", source="test")
    command = replace(command, created_at_monotonic_s=100.)
    assert commander.submit_intent(command)
    assert await commander.publish_once()
    external = client.submit.call_args.args[0]
    assert external.command == FixedWingCommand(.3, 18., None, 550.)
    assert external.expires_at_monotonic_s == 100.5
    assert commander.get_status()["sends_mavsdk_commands"] is False
    assert commander.get_status()["command_publication_source"] == "px4_native_external_mode"
    await commander.stop()
    assert client.submit.await_count == 1
    client.handoff.assert_awaited_once_with(identity, reason="operator_stop", before_dispatch=None,
        ownership_token=client.acquisition_token, acquisition=client.acquisition_context)


@pytest.mark.asyncio
async def test_publication_refresh_does_not_extend_the_original_intent_deadline():
    transport, client, identity = setup_transport()
    intent = replace(FixedWingCommand(0., 18., 0., None).intent(identity, profile_name="gm_velocity_vector", source="test"), created_at_monotonic_s=100.)
    intent = transport.accept_intent(intent)
    await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    transport.clock = lambda: 100.4
    await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    assert [call.args[0].sequence for call in client.submit.call_args_list] == [0, 1]
    assert [call.args[0].expires_at_monotonic_s for call in client.submit.call_args_list] == [100.5, 100.5]
    transport.clock = lambda: 100.6
    with pytest.raises(ValueError, match="expiry"):
        await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    assert client.submit.await_count == 2


@pytest.mark.asyncio
async def test_takeover_prevents_publication_and_never_sends_hold():
    transport, client, identity = setup_transport()
    intent = replace(FixedWingCommand(0., 18., 0., None).intent(identity, profile_name="gm_velocity_vector", source="test"), created_at_monotonic_s=100.)
    client.observe.return_value["owner_confirmed"] = False
    with pytest.raises(ValueError, match="owner_unavailable"):
        await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    client.submit.assert_not_called()
    client.handoff.assert_not_called()


@pytest.mark.asyncio
async def test_rejected_source_cannot_supply_native_command_geometry():
    transport, client, identity = setup_transport()
    intent = replace(FixedWingCommand(0., 18., 0., None).intent(identity, profile_name="gm_velocity_vector", source="test"), created_at_monotonic_s=100.)
    client.observe.return_value["aircraft_state"]["source"] = "superseded_source"
    with pytest.raises(ValueError, match="state_rejected"):
        await transport.publish(intent, reason="heartbeat", ttl_s=.5)
    client.submit.assert_not_called()


def test_mc_velocity_boundary_rotates_heading_only_and_keeps_ned_vertical():
    state = aircraft_state(phase=AirframePhase.MULTICOPTER, is_vtol=True, navigation_heading_rad=math.pi / 2)
    transport, _, identity = setup_transport(state)
    intent = CommandIntent("gm_velocity_vector", "velocity_body_offboard", {
        "vel_body_fwd": 2., "vel_body_right": 3., "vel_body_down": -1., "yawspeed_deg_s": 30.,
    }, "test", created_at_monotonic_s=100., guidance_identity=identity)
    command = transport._command(transport.accept_intent(intent), state)
    assert command.velocity_ned_m_s.x == pytest.approx(-3.)
    assert command.velocity_ned_m_s.y == pytest.approx(2.)
    assert command.velocity_ned_m_s.z == -1.
    assert command.yaw_rate_rad_s == pytest.approx(math.pi / 6)


def test_native_phase_contract_and_old_generation_cannot_mix():
    transport, _, identity = setup_transport()
    intent = FixedWingCommand(0., 18., 0., None).intent(identity, profile_name="gm_velocity_vector", source="test")
    intent = replace(intent, created_at_monotonic_s=100.)
    with pytest.raises(ValueError, match="identity_stale"):
        transport.accept_intent(replace(intent, guidance_identity=replace(identity, guidance_generation=0)))
    with pytest.raises(ValueError, match="fixed_wing_intent_invalid"):
        transport.accept_intent(replace(intent, control_type="velocity_body_offboard"))
    transport.accept_intent(intent)
    with pytest.raises(ValueError, match="obsolete"):
        transport.accept_intent(replace(intent, created_at_monotonic_s=99.9))
    assert transport._command(intent, aircraft_state()).height_rate_m_s == 0.


@pytest.mark.asyncio
async def test_phase_callback_rebinds_before_publication_and_records_the_effective_contract(monkeypatch):
    transport, client, identity = setup_transport()
    monkeypatch.setattr("classes.offboard_commander.time.monotonic", lambda: 100.1)
    state = aircraft_state(phase=AirframePhase.VTOL_TRANSITION, is_vtol=True)
    box = [aircraft_state()]
    transport.connection = SimpleNamespace(get_aircraft_state=lambda: box[0],
                                           commit_aircraft_state=lambda value: box.__setitem__(0, value))
    client.observe.return_value['aircraft_state'] = asdict(state)
    next_identity = replace(identity, guidance_generation=2)

    async def acknowledge_phase(updated, **_):
        client.session_identity = updated

    client.advance_generation.side_effect = acknowledge_phase
    baseline = CommandIntent("gm_velocity_vector", "vtol_transition_external",
                             dict(course_rad=.2, equivalent_airspeed_m_s=18.), "phase_owner",
                             guidance_identity=next_identity, created_at_monotonic_s=100.1)

    async def on_observation(actual, observation, old):
        assert actual is box[0] and actual.phase is AirframePhase.VTOL_TRANSITION
        assert observation['owner_confirmed'] is True
        assert old.guidance_identity == identity
        await transport.advance_generation(next_identity)
        return baseline

    transport.on_observation = on_observation
    events = []
    commander = OffboardCommander(None, None, command_transport=transport, on_publish_result=events.append)
    previous = replace(FixedWingCommand(0., 18., 0., None).intent(identity, profile_name="gm_velocity_vector", source="old_fw"),
                       created_at_monotonic_s=100.)
    assert commander.submit_intent(previous)
    assert await commander.publish_once()
    assert client.submit.await_count == 1
    submitted = client.submit.call_args.args[0]
    assert submitted.identity == next_identity
    assert submitted.phase is AirframePhase.VTOL_TRANSITION
    assert submitted.sequence == 0
    assert events[-1]['command_intent'].fields == baseline.fields
    assert commander._last_intent.guidance_identity == next_identity
    assert commander.consecutive_failures == 0


@pytest.mark.asyncio
async def test_new_generation_intent_is_accepted_during_ack_without_overwriting_it_afterward(monkeypatch):
    transport, client, identity = setup_transport()
    client.abort = Mock()
    monkeypatch.setattr("classes.offboard_commander.time.monotonic", lambda: 100.1)
    requested, release = asyncio.Event(), asyncio.Event()
    next_identity = replace(identity, guidance_generation=2)
    baseline = replace(FixedWingCommand(.2, 18., 0., None).intent(next_identity, profile_name="gm_velocity_vector", source="phase_owner"),
                       created_at_monotonic_s=100.05)
    newer = replace(baseline, fields=baseline.fields | {"course_rad": .4}, created_at_monotonic_s=100.08)

    async def acknowledge_phase(updated, **_):
        requested.set()
        await release.wait()
        client.session_identity = updated

    client.advance_generation.side_effect = acknowledge_phase

    async def on_observation(*_):
        await transport.advance_generation(next_identity)
        return baseline

    transport.on_observation = on_observation
    commander = OffboardCommander(None, None, command_transport=transport)
    previous = replace(FixedWingCommand(0., 18., 0., None).intent(identity, profile_name="gm_velocity_vector", source="old"),
                       created_at_monotonic_s=100.)
    assert commander.submit_intent(previous)
    pending = asyncio.create_task(commander.publish_once())
    await asyncio.wait_for(requested.wait(), timeout=1.)
    assert commander.submit_intent(newer)
    assert not commander.submit_intent(previous)
    release.set()
    assert await pending
    assert commander._last_intent.fields['course_rad'] == .4
    assert transport._last_created == 100.08
    assert client.submit.call_args.args[0].command.course_rad == .2
    assert commander.consecutive_failures == 0


@pytest.mark.asyncio
async def test_failed_phase_binding_revokes_the_native_owner_without_submission():
    transport, client, identity = setup_transport()
    client.abort = Mock(side_effect=lambda: setattr(client, 'session_identity', None))
    client.advance_generation.side_effect = RuntimeError("phase_ack_failed")
    with pytest.raises(RuntimeError, match="phase_ack_failed"):
        await transport.advance_generation(replace(identity, guidance_generation=2))
    client.abort.assert_called_once()
    assert not transport.ready()
    assert transport._pending_identity is None
    client.submit.assert_not_called()


async def test_transport_without_explicit_engage_ack_cannot_adopt_client_owner():
    _, client, identity = setup_transport()
    transport = NativeCommandTransport(client, SimpleNamespace(get_aircraft_state=lambda: aircraft_state()),
                                       identity, circuit_breaker=lambda: False)
    assert not transport.ready()
    with pytest.raises(ValueError, match='acquisition_context_missing'):
        await transport.publish(None, reason='operator_stop', ttl_s=.5)
    client.handoff.assert_not_called()
    client.submit.assert_not_called()


async def test_transport_replacement_with_equal_session_identity_cannot_publish():
    transport, client, identity = setup_transport()
    original = client.acquisition_context
    client.acquisition_context = replace(original, token='f' * 32)
    assert not transport.ready()
    intent = replace(FixedWingCommand(0., 18., 0., None).intent(identity, profile_name='gm_velocity_vector', source='test'),
                     created_at_monotonic_s=100.)
    with pytest.raises(ValueError, match='state_stale'):
        await transport.publish(intent, reason='heartbeat', ttl_s=.5)
    client.submit.assert_not_called()
    with pytest.raises(ValueError, match='context_changed'):
        transport.bind_acquisition(client.acquisition_context)
