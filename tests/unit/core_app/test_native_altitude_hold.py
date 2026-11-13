"""Native altitude hold is an explicit objective, never an inferred zero rate."""

from dataclasses import replace
from types import SimpleNamespace
import math

import pytest

from classes.aircraft_state import AirframePhase, Vector3
from classes.command_intent import CommandIntent
from classes.command_preview import CommandPreviewCommander
from classes.following_readiness import evaluate_following_start_altitude
from classes.gimbal_guidance import GimbalObservationLimits
from classes.native_command_transport import NativeCommandTransport
from classes.offboard_commander import OffboardCommander
from classes.px4_interface_manager import PX4InterfaceManager
from classes.safety_types import AltitudeLimits
from classes.target_continuity import ContinuityContext, ContinuityPolicy, TargetContinuitySupervisor
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.unit.followers.test_vector_guidance_session import session, settle
from tests.unit.core_app.test_fixed_wing_continuity import evidence
from tests.unit.core_app.test_native_follow_binding import fixture
from tests.unit.drone_interface.test_offboard_commander import _handler


def mc_session(*, altitude=False):
    return session(altitude=altitude, state=aircraft_state(
        phase=AirframePhase.MULTICOPTER, is_vtol=True, is_tailsitter=True))


def test_altitude_off_commands_hold_the_original_height_without_scaling_horizontal_motion():
    owner, clock, state = mc_session()
    state = settle(owner, clock, state)
    nominal = CommandIntent('gm_velocity_vector', 'velocity_body_offboard', dict(
        vel_body_fwd=3., vel_body_right=1., vel_body_down=0., yawspeed_deg_s=10.), 'test')
    intent = owner.calculate(Vector3(1., 0., 0.), observation_limits=GimbalObservationLimits(),
                             multicopter_calculate=lambda _: nominal)
    hold = getattr(intent, 'altitude_hold', None)
    assert hold is not None
    assert hold.altitude_amsl_m == state.altitude_amsl_m
    assert hold.reference_generation == state.altitude_reference_generation
    assert intent.fields == nominal.fields


def test_engagement_reference_is_frozen_before_acquisition_and_not_recaptured_after_motion():
    owner, clock, state = mc_session()
    prepare = getattr(owner, 'prepare_engagement_reference', None)
    assert callable(prepare)
    reference = prepare(state)
    clock[0] += .1
    moved = replace(state, sequence=state.sequence + 1, altitude_amsl_m=state.altitude_amsl_m - .2,
                    relative_altitude_m=state.relative_altitude_m - .2, observed_at_monotonic_s=clock[0])
    owner.observe(moved, owner_confirmed=True, target_confirmed=True)
    assert owner.baseline().altitude_hold == reference
    assert owner.baseline().altitude_hold.altitude_amsl_m == state.altitude_amsl_m


def nominal(*, down=0.):
    return CommandIntent('gm_velocity_vector', 'velocity_body_offboard', dict(
        vel_body_fwd=.5, vel_body_right=.2, vel_body_down=down, yawspeed_deg_s=10.), 'test')


@pytest.mark.parametrize('altitude', [False, True])
def test_startup_holds_height_but_explicit_vertical_pursuit_uses_rate(altitude):
    owner, clock, state = mc_session(altitude=altitude)
    owner.observe(state, owner_confirmed=True, target_confirmed=True)
    assert owner.baseline().altitude_hold is not None
    clock[0] += .31
    state = replace(state, sequence=state.sequence + 1, observed_at_monotonic_s=clock[0])
    owner.observe(state, owner_confirmed=True, target_confirmed=True)
    intent = owner.calculate(Vector3(1., 0., 0.), observation_limits=GimbalObservationLimits(),
                             multicopter_calculate=lambda _: nominal(down=1. if altitude else 0.))
    assert (intent.altitude_hold is None) == altitude
    assert intent.fields['vel_body_down'] == (1. if altitude else 0.)


def test_disabled_altitude_does_not_silently_discard_a_vertical_command():
    owner, clock, state = mc_session()
    settle(owner, clock, state)
    with pytest.raises(ValueError, match='native_vertical_contract_invalid'):
        owner.calculate(Vector3(1., 0., 0.), observation_limits=GimbalObservationLimits(),
                        multicopter_calculate=lambda _: nominal(down=1.))


@pytest.mark.parametrize('failure', ['stale', 'reference', 'binding', 'rescue', 'capability', 'ended'])
def test_missing_or_changed_reference_never_reanchors(failure):
    owner, clock, state = mc_session()
    original = owner.prepare_engagement_reference(state)
    if failure == 'stale':
        clock[0] += 1.
    elif failure == 'reference':
        state = replace(state, altitude_reference_generation=state.altitude_reference_generation + 1)
    elif failure == 'binding':
        state = replace(state, binding=replace(state.binding, connection_generation='replacement'))
    elif failure == 'rescue':
        state = replace(state, rescue_active=True)
    elif failure == 'capability':
        owner.phase_owner.capabilities = replace(owner.phase_owner.capabilities, multicopter_altitude_hold_supported=False)
    else:
        owner.end('operator_stop')
    with pytest.raises(ValueError):
        owner.prepare_engagement_reference(state)
    if failure != 'ended':
        assert owner._engagement_altitude_reference.altitude_amsl_m == original.altitude_amsl_m


def test_reference_survives_retarget_and_clears_at_session_end():
    owner, clock, state = mc_session()
    state = settle(owner, clock, state)
    original = owner.baseline().altitude_hold
    owner.reset_target_state()
    assert owner.baseline().altitude_hold == original
    owner.end('operator_stop')
    assert owner._engagement_altitude_reference is None
    with pytest.raises(ValueError, match='guidance_session_ended'):
        owner.baseline()


def test_continuity_keeps_absolute_height_through_loss_and_restoration():
    owner, clock, state = mc_session()
    state = settle(owner, clock, state)
    intent = replace(nominal(), guidance_identity=owner.identity, altitude_hold=owner.baseline().altitude_hold)
    context = ContinuityContext('PX4_NATIVE', AirframePhase.MULTICOPTER, 'velocity_body_offboard',
                                True, True, True, vehicle_yaw_deg=0., guidance_identity=owner.identity)
    continuity = TargetContinuitySupervisor(ContinuityPolicy.from_mapping(dict(
        MODE='bounded_decay', MAX_COAST_TIME_S=8., MAX_COAST_DISTANCE_M=4.,
        MAX_RETARGET_TIME_S=8., REACQUIRE_CONFIRMATION_S=.5, AUTHORITY_RESTORE_TIME_S=.5)), clock=lambda: clock[0])
    continuity.reset_session(session_epoch=1, reason='start')
    continuity.evaluate(evidence(), context, intent, now_monotonic_s=0.)
    for now, confirmed in ((.1, False), (.2, True), (.8, True), (1.1, True), (1.4, True)):
        decision = continuity.evaluate(evidence(confirmed), context, intent if confirmed else None,
                                       now_monotonic_s=now)
        assert decision.authorized_intent is not None
        assert decision.authorized_intent.altitude_hold == intent.altitude_hold
        assert decision.authorized_intent.fields['vel_body_down'] == 0.
    incompatible = replace(intent, altitude_hold=replace(intent.altitude_hold, reference_generation=99))
    with pytest.raises(ValueError, match='incompatible'):
        continuity._blend_intents(intent, incompatible, .5)


def test_native_conversion_keeps_heading_projection_and_one_vertical_contract():
    owner, clock, state = mc_session()
    settle(owner, clock, state)
    state = replace(state, navigation_heading_rad=math.pi / 2)
    intent = replace(nominal(), guidance_identity=owner.identity, altitude_hold=owner.baseline().altitude_hold)
    client = SimpleNamespace(capabilities=owner.phase_owner.capabilities)
    transport = NativeCommandTransport(client, None, owner.identity, circuit_breaker=lambda: False,
                                       altitude_limits=owner.altitude_limits)
    command = transport._command(intent, state)
    assert command.velocity_ned_m_s.x == pytest.approx(-.2)
    assert command.velocity_ned_m_s.y == pytest.approx(.5)
    assert command.altitude_hold == intent.altitude_hold
    assert 'velocity_down_m_s' not in command.wire_payload()
    with pytest.raises(ValueError, match='altitude_reference_changed'):
        transport._command(intent, replace(state, altitude_reference_generation=99))
    manager = SimpleNamespace(setpoint_handler=SimpleNamespace(profile_name=intent.profile_name))
    with pytest.raises(ValueError, match='altitude_hold_transport_unsupported'):
        PX4InterfaceManager._command_dispatch_fields(manager, intent, intent.control_type)


async def test_acquisition_and_later_baseline_use_the_same_preacquisition_reference():
    f = fixture(phase=AirframePhase.MULTICOPTER)
    initial = f.state.altitude_amsl_m
    original_engage = f.client.engage.side_effect

    async def engage_after_moving(identity, **kwargs):
        moved = replace(f.state, sequence=f.state.sequence + 1, altitude_amsl_m=initial - .2)
        f.connection.commit_aircraft_state(moved)
        return await original_engage(identity, **kwargs)

    f.client.engage.side_effect = engage_after_moving
    baseline = await f.binding.engage()
    supplied = f.client.engage.call_args.kwargs['altitude_reference']
    assert baseline.altitude_hold == supplied
    assert supplied.altitude_amsl_m == initial
    assert f.connection.get_aircraft_state().altitude_amsl_m == initial - .2


@pytest.mark.parametrize('preview', [False, True])
def test_schema_staging_keeps_the_same_hold_reference_and_session_identity(preview):
    owner, clock, state = mc_session()
    settle(owner, clock, state)
    intent = replace(nominal(), profile_name='test_profile', guidance_identity=owner.identity,
                     altitude_hold=owner.baseline().altitude_hold)
    handler = _handler()
    commander = CommandPreviewCommander(handler) if preview else OffboardCommander(None, handler)
    commander.running = True
    assert commander.submit_intent(intent)
    retained = commander._last_intent
    assert retained.altitude_hold == intent.altitude_hold
    assert retained.guidance_identity == intent.guidance_identity
    assert retained.created_at_monotonic_s == intent.created_at_monotonic_s


@pytest.mark.parametrize('phase', [AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING])
@pytest.mark.parametrize('native_height', [4., 121.])
async def test_native_hold_bounds_reject_before_acquisition_even_when_legacy_height_allows_start(phase, native_height):
    f = fixture(phase=phase)
    f.connection.current_altitude = 30.
    assert evaluate_following_start_altitude(
        SimpleNamespace(px4_interface=f.connection), limits=f.guidance.altitude_limits)['ready']
    outside = replace(f.state, sequence=f.state.sequence + 1, relative_altitude_m=native_height,
                      altitude_amsl_m=500. + native_height)
    assert f.connection.commit_aircraft_state(outside)

    with pytest.raises(ValueError, match='altitude_hard_limit'):
        await f.binding.engage()

    f.client.engage.assert_not_awaited()
    f.client.submit.assert_not_awaited()
    f.client.handoff.assert_not_awaited()
    assert f.guidance._engagement_altitude_reference is None


@pytest.mark.parametrize('target_height', [4., 121.])
async def test_native_hold_bounds_reject_retained_target_at_publication(target_height):
    f = fixture(phase=AirframePhase.MULTICOPTER)
    assert f.binding.transport.altitude_limits is f.guidance.altitude_limits
    f.guidance.fixed_wing.enable_altitude_control = False
    await f.binding.engage()
    f.clock[0] += .31
    state = replace(f.connection.get_aircraft_state(), sequence=f.state.sequence + 1,
                    observed_at_monotonic_s=f.clock[0])
    assert f.connection.commit_aircraft_state(state)
    baseline = await f.binding.on_observation(state, f.packet(), None)
    assert not f.binding.pursuit_paused
    offset = state.altitude_amsl_m - state.relative_altitude_m
    retained = replace(baseline, altitude_hold=replace(
        baseline.altitude_hold, altitude_amsl_m=offset + target_height))

    with pytest.raises(ValueError, match='altitude_hold_target_outside_limits'):
        await f.binding.transport.publish(retained, reason='heartbeat', ttl_s=1.)

    f.client.submit.assert_not_awaited()
    f.client.handoff.assert_not_awaited()


def test_native_hold_bounds_require_captured_limits_without_changing_rate_commands():
    owner, clock, state = mc_session()
    settle(owner, clock, state)
    transport = NativeCommandTransport(SimpleNamespace(capabilities=owner.phase_owner.capabilities), None,
                                       owner.identity, circuit_breaker=lambda: False)
    hold = replace(nominal(), guidance_identity=owner.identity, altitude_hold=owner.baseline().altitude_hold)
    with pytest.raises(ValueError, match='native_mc_altitude_hold_unavailable'):
        transport._command(hold, state)
    rate = replace(nominal(down=1.), guidance_identity=owner.identity)
    assert transport._command(rate, state).wire_payload()['velocity_down_m_s'] == 1.


@pytest.mark.parametrize('limits,height', [
    (AltitudeLimits(5., 120., 2.), 30.),
    (AltitudeLimits(5., None, 2.), 200.),
    (AltitudeLimits(5., 120., 2., safety_enabled=False), 1.),
])
@pytest.mark.parametrize('phase', [AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING])
def test_hold_bounds_keep_relative_offset_optional_ceiling_and_safety_opt_out(limits, height, phase):
    state = aircraft_state(phase=phase, is_vtol=True, is_tailsitter=True,
                           relative_altitude_m=height, altitude_amsl_m=500. + height)
    owner, clock, _ = session(altitude=False, state=state)
    owner.altitude_limits = limits
    reference = owner.prepare_engagement_reference(state)
    assert reference.altitude_amsl_m == 500. + height
    settle(owner, clock, state)
    baseline = owner.baseline()
    if phase is AirframePhase.MULTICOPTER:
        transport = NativeCommandTransport(SimpleNamespace(capabilities=owner.phase_owner.capabilities), None,
                                           owner.identity, circuit_breaker=lambda: False, altitude_limits=limits)
        command = transport._command(baseline, state)
        assert command.altitude_hold == reference
        assert command.wire_payload()['altitude_amsl_m'] == reference.altitude_amsl_m
    else:
        assert baseline.fields['altitude_amsl_m'] == reference.altitude_amsl_m


@pytest.mark.parametrize('native_height', [4., 121.])
async def test_hold_bounds_refuse_current_native_excursion_after_acquisition(native_height):
    f = fixture(phase=AirframePhase.MULTICOPTER)
    f.guidance.fixed_wing.enable_altitude_control = False
    baseline = await f.binding.engage()
    state = f.connection.get_aircraft_state()
    offset = state.altitude_amsl_m - state.relative_altitude_m
    outside = replace(state, sequence=state.sequence + 1, relative_altitude_m=native_height,
                      altitude_amsl_m=offset + native_height)
    assert f.connection.commit_aircraft_state(outside)

    with pytest.raises(ValueError, match='altitude_hard_limit'):
        await f.binding.transport.publish(baseline, reason='heartbeat', ttl_s=1.)

    f.client.submit.assert_not_awaited()
    assert f.guidance.phase_owner.reason == 'altitude_hard_limit'
