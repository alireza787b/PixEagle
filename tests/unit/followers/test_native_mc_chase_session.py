"""Native MC ownership reuses Chase's actual image controller and speed owner."""

from dataclasses import replace
import math
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from classes.aircraft_state import AircraftKind, AircraftLayout, AirframePhase, GuidanceSessionIdentity, Vector3
from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower
from classes.follower_catalog import evaluate_aircraft, get_follower_profile
from classes.guidance_phase_session import PhaseSessionState
from classes.native_command_transport import NativeCommandTransport
from classes.native_follow_binding import NativeFollowBinding, requires_native_guidance
from classes.native_guidance import NativeCapabilities
from classes.tracker_output import TrackerDataType, TrackerOutput
from tests.fixtures.mock_px4 import MockPX4Controller
from tests.unit.drone_interface.test_aircraft_state import aircraft_state
from tests.unit.followers.test_mc_chase_session_speed import chase, command, magnitude


def prepare(chase, *, altitude=False, settle=True, capabilities=None):
    chase.enable_altitude_control = altitude
    chase._initialize_pid_controllers()
    clock = [100.]
    state = aircraft_state(phase=AirframePhase.MULTICOPTER, is_vtol=True, is_tailsitter=False,
                           fixed_wing_envelope=None, velocity_ned_m_s=Vector3(0., 0., 0.),
                           altitude_reference_generation=7)
    identity = GuidanceSessionIdentity('native-chase', state.binding, 1)
    capabilities = capabilities or NativeCapabilities(
        'native', 'test', 2, False, True, False, True, 23,
        multicopter_altitude_hold_supported=True)
    session = chase.create_airframe_session(
        identity, capabilities, confirmation_s=.3, observation_timeout_s=.75,
        clock=lambda: clock[0], expected_layout=AircraftLayout.VTOL,
        initial_phase=AirframePhase.MULTICOPTER,
        fixed_wing_policy=object(),
    )
    session.prepare_engagement_reference(state)
    session.observe(state, owner_confirmed=True, target_confirmed=True)
    chase.bind_airframe_session(session)
    if settle:
        clock[0] += .31
        state = replace(state, sequence=2, observed_at_monotonic_s=clock[0])
        assert session.observe(state, owner_confirmed=True, target_confirmed=True).pursuit_allowed
    return session, clock, state


def output(x=.3, y=-.3):
    return TrackerOutput(TrackerDataType.POSITION_2D, time.time(), True, position_2d=(x, y))


def test_mc_session_constructs_no_fixed_wing_guidance_or_envelope(chase, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail('MC session constructed a FW pursuit controller')

    monkeypatch.setattr('classes.fixed_wing_vector_guidance.FixedWingVectorGuidance.__init__', unexpected)
    session, _, state = prepare(chase)
    assert session.supported_phases == frozenset({AirframePhase.MULTICOPTER})
    assert not session.phase_owner.capabilities.fixed_wing_supported
    assert state.fixed_wing_envelope is None
    assert session.control_type == chase.get_control_type() == 'velocity_body_offboard'


@pytest.mark.parametrize('mode', ['sideslip', 'coordinated_turn'])
@pytest.mark.parametrize('altitude', [False, True])
@pytest.mark.parametrize('sign', [-1., 1.])
def test_native_chase_reuses_legacy_image_pid_ramp_smoothing_and_four_fields(
        chase, monkeypatch, mode, altitude, sign):
    now = [100.]
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: now[0])
    legacy = MCVelocityChaseFollower(MockPX4Controller(), (0., 0.))
    for follower in (chase, legacy):
        follower.enable_altitude_control = altitude
        follower.lateral_guidance_mode = mode
        follower.enable_auto_mode_switching = False
        follower.adaptive_mode_enabled = False
        follower._initialize_pid_controllers()
        follower.last_ramp_update_time = now[0]
    session, _, _ = prepare(chase, altitude=altitude)
    for step in range(1, 6):
        now[0] = 100. + step / 20.
        for follower in (legacy, chase):
            assert follower.calculate_control_commands(output(.3 * sign, -.3 * sign))
        actual, expected = chase.get_last_command_intent(), legacy.get_last_command_intent()
        assert set(actual.fields) == set(command())
        assert actual.fields == pytest.approx(expected.fields)
        assert chase.prepare_authorized_command(actual.fields, loss_decay=False) == pytest.approx(
            legacy.prepare_authorized_command(expected.fields, loss_decay=False))
        assert actual.guidance_identity == session.identity
        assert expected.guidance_identity is None
        assert (actual.altitude_hold is None) is altitude
        if not altitude:
            assert actual.fields['vel_body_down'] == 0.
            assert actual.altitude_hold.altitude_amsl_m == 550.
        for follower in (legacy, chase):
            follower.on_command_submitted(follower.get_last_command_intent().fields)
    assert actual.fields['vel_body_fwd'] > 0.
    if mode == 'sideslip':
        assert actual.fields['vel_body_right'] * sign > 0.
        assert actual.fields['yawspeed_deg_s'] == 0.
    else:
        assert actual.fields['yawspeed_deg_s'] * sign > 0.
        assert actual.fields['vel_body_right'] == 0.
    if altitude:
        assert actual.fields['vel_body_down'] * sign < 0.


def test_phase_confirmation_holds_without_advancing_chase_controller(chase):
    session, _, _ = prepare(chase, settle=False, altitude=True)
    previous = (chase.current_forward_velocity, chase.last_ramp_update_time, chase.pid_down.components)
    assert chase.calculate_control_commands(output())
    intent = chase.get_last_command_intent()
    assert intent.fields == dict.fromkeys(command(), 0.)
    assert intent.altitude_hold.altitude_amsl_m == 550.
    assert intent.guidance_identity == session.identity
    assert (chase.current_forward_velocity, chase.last_ramp_update_time, chase.pid_down.components) == previous


def test_native_initial_editor_revision_does_not_activate_an_unrequested_speed_ramp(chase):
    session, _, _ = prepare(chase)
    assert session.controls.current_control.revision == 1
    assert not session.controls.current_control.override_active
    assert chase.prepare_authorized_command(command(), loss_decay=False) == command()


def test_one_control_owner_handles_edits_restore_and_original_limits(chase, monkeypatch):
    session, clock, _ = prepare(chase)
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: clock[0])
    assert chase._session_controls == {}
    row, = chase.session_controls()
    assert row['guidance_generation'] == session.identity.guidance_generation
    assert row['aircraft_phase'] == 'multicopter' and row['speed_basis'] == 'translation_3d'
    assert session.controls.snapshot(client_contract_version=1) is None
    assert chase._requested_speed_control() is session.controls.current_control
    assert row['value'] == 1. and not row['override_active']
    chase.update_session_control('requested_speed', 3., row['revision'])
    assert chase.velocity_limits.forward == 3.
    assert session.controls.current_control.value == 3.
    with pytest.raises(ValueError, match='revision_stale'):
        chase.update_session_control('requested_speed', 2., row['revision'])
    chase.on_command_submitted(command(2., 1., -2.))
    row, = chase.session_controls()
    chase.update_session_control('requested_speed', 0., row['revision'])
    clock[0] += .05
    limited = chase.prepare_authorized_command(command(2., 1., -2.), loss_decay=True)
    assert magnitude(limited) == pytest.approx(3. - .5 / 20.)
    assert limited['vel_body_fwd'] / 2. == pytest.approx(limited['vel_body_down'] / -2.)
    row, = chase.session_controls()
    chase.update_session_control('requested_speed', None, row['revision'])
    assert chase.velocity_limits.forward == .5
    assert not session.controls.current_control.override_active
    chase.release_session_controls()
    assert chase.session_controls() == []
    with pytest.raises(ValueError, match='identity_stale'):
        chase.update_session_control('requested_speed', 1., row['revision'])


def test_retarget_keeps_frozen_engagement_height_and_control_owner(chase):
    session, clock, state = prepare(chase)
    row, = chase.session_controls()
    chase.update_session_control('requested_speed', 2., row['revision'])
    before = session.controls.current_control
    assert chase.reset_target_state('operator_target_retarget')
    clock[0] += .1
    state = replace(state, sequence=3, observed_at_monotonic_s=clock[0],
                    relative_altitude_m=49., altitude_amsl_m=549.)
    session.observe(state, owner_confirmed=True, target_confirmed=True)
    assert chase.calculate_control_commands(output())
    assert chase.get_last_command_intent().altitude_hold.altitude_amsl_m == 550.
    assert session.controls.current_control is before


@pytest.mark.parametrize('changes,reason', [
    ({'phase': AirframePhase.VTOL_TRANSITION}, 'aircraft_transition_observed'),
    ({'phase': AirframePhase.FIXED_WING}, 'aircraft_phase_changed'),
    ({'rescue_active': True}, 'aircraft_rescue_active'),
])
def test_mc_session_retires_on_phase_or_rescue_and_cannot_resume(chase, changes, reason):
    session, clock, state = prepare(chase)
    assert chase.calculate_control_commands(output())
    clock[0] += .1
    decision = session.observe(replace(state, sequence=3, observed_at_monotonic_s=clock[0], **changes),
                               owner_confirmed=True, target_confirmed=True)
    assert decision.reason == reason and decision.state is PhaseSessionState.ENDED
    assert chase.session_controls() == []
    assert not chase.calculate_control_commands(output())
    assert chase.get_last_command_intent() is None
    clock[0] += .1
    decision = session.observe(replace(state, sequence=4, observed_at_monotonic_s=clock[0]),
                               owner_confirmed=True, target_confirmed=True)
    assert decision.state is PhaseSessionState.ENDED


@pytest.mark.parametrize('fault', ['owner', 'stale', 'binding', 'generation'])
def test_native_mc_refuses_lost_stale_replaced_or_reset_altitude_reference(chase, fault):
    session, clock, state = prepare(chase)
    clock[0] += .1
    next_state = replace(state, sequence=3, observed_at_monotonic_s=clock[0])
    if fault == 'stale':
        clock[0] += 1.
    elif fault == 'binding':
        next_state = replace(next_state, binding=replace(state.binding, telemetry_generation=2))
    elif fault == 'generation':
        next_state = replace(next_state, altitude_reference_generation=8)
    if fault == 'generation':
        with pytest.raises(ValueError, match='altitude_reference_changed'):
            session.observe(next_state, owner_confirmed=True, target_confirmed=True)
    else:
        assert session.observe(next_state, owner_confirmed=fault != 'owner',
                               target_confirmed=True).state is PhaseSessionState.ENDED
    assert not chase.calculate_control_commands(output())
    assert chase.get_last_command_intent() is None


def test_missing_native_hold_capability_refuses_before_binding(chase):
    capabilities = NativeCapabilities('native', 'test', 2, False, True, False, True, 23)
    with pytest.raises(ValueError, match='native_mc_altitude_hold_unavailable'):
        prepare(chase, capabilities=capabilities)
    assert not chase.calculate_control_commands(output())
    assert chase.get_last_command_intent() is None


def test_same_native_transport_converts_chase_heading_and_yaw_once(chase):
    session, _, state = prepare(chase)
    state = replace(state, navigation_heading_rad=math.pi / 2.)
    client = SimpleNamespace(capabilities=session.phase_owner.capabilities)
    transport = NativeCommandTransport(client, SimpleNamespace(), session.identity,
                                       circuit_breaker=lambda: False, altitude_limits=chase.altitude_limits)
    baseline = session.baseline()
    intent = replace(baseline, fields=command(2., 1., 0., 30.))
    native = transport._command(intent, state)
    assert (native.velocity_ned_m_s.x, native.velocity_ned_m_s.y, native.velocity_ned_m_s.z) == pytest.approx((-1., 2., 0.))
    assert native.yaw_rate_rad_s == pytest.approx(math.pi / 6.)
    assert native.altitude_hold == baseline.altitude_hold
    chase.px4_controller.send_velocity_body_offboard.assert_not_called()


def test_mc_only_binding_does_not_require_a_fixed_wing_continuity_policy(chase):
    session, _, _ = prepare(chase)
    binding = NativeFollowBinding(
        session, Mock(), Mock(), Mock(), profile_name=chase.profile_name,
        continuity_config={'MODE': 'immediate_handoff'}, target_evidence=Mock(),
        context=Mock(), circuit_breaker=lambda: False)
    assert binding.guidance is session


def test_native_declaration_preserves_legacy_mc_and_does_not_admit_vtol():
    profile = get_follower_profile('mc_velocity_chase')
    assert dict(profile.native_phase_contracts) == {'multicopter': 'velocity_body_offboard'}
    declaration = {'native_phase_contracts': dict(profile.native_phase_contracts)}
    assert requires_native_guidance(declaration, AircraftKind.MULTICOPTER) is False
    assert requires_native_guidance(declaration, AircraftKind.VTOL) is True
    assert evaluate_aircraft(profile, 'multicopter').eligible
    assert evaluate_aircraft(profile, 'vtol', observed_phase='multicopter').reason_code == 'vtol_transition_release_unqualified'
    with pytest.raises(ValueError, match='follower_airframe_strategy_unavailable'):
        requires_native_guidance(declaration, AircraftKind.FIXED_WING)
