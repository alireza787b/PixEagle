"""Qualified native FW boresight input; synthetic component evidence only."""

from dataclasses import replace
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from classes.aircraft_state import AirframePhase, GuidanceSessionIdentity, Quaternion
from classes.config_service import ConfigService
from classes.follower import FollowerFactory
from classes.gimbal_geometry import resolve_angle_geometry
from classes.parameters import Parameters
from classes.native_guidance import NativeCapabilities
from tests.fixtures.native_bearing import associated_gimbal_output
from tests.unit.drone_interface.test_aircraft_state import aircraft_state, attitude_timing
from tests.unit.followers.test_vector_guidance_session import observe, session, settle
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target


@pytest.fixture
def environment(monkeypatch):
    before = Parameters.get_runtime_config_snapshot()
    defaults = yaml.safe_load((Path(__file__).resolve().parents[3] / 'configs/config_default.yaml').read_text())
    Parameters.publish_config_mapping(defaults)
    monkeypatch.setattr(ConfigService, 'get_gimbal_guidance_migration', lambda *_: None)

    def build(mount='HORIZONTAL', *, altitude=True, resolver=True, prepare_only=False):
        controller = SimpleNamespace(current_altitude=50., current_yaw=0., current_roll=0., current_pitch=0.,
                                     is_command_connection_ready=lambda **_: True)
        follower = FollowerFactory.create_follower('gm_velocity_vector', controller, (0., 0.))
        follower.mount_type = mount
        follower.angle_geometry = resolve_angle_geometry({}, mount)
        state = aircraft_state(attitude_timing=attitude_timing(),
            attitude_body_to_ned=Quaternion.from_euler(.2, -.1, .4))
        result = SimpleNamespace(follower=follower, owner=None, state=state, now=None,
                                 output=None, aligned=None, target=(60., 20., 10.))
        if resolver:
            follower.bind_guidance_input_resolver(lambda *_: result.aligned)
        if prepare_only:
            now = [100.]
            owner = follower.create_airframe_session(GuidanceSessionIdentity('prepared-session', state.binding, 0),
                NativeCapabilities('native', 'test', 2, True, True, False), confirmation_s=.3,
                observation_timeout_s=.75, clock=lambda: now[0])
        else:
            owner, now, state = session(altitude=altitude, state=state)
            state = settle(owner, now, state)
            follower.bind_airframe_session(owner)
        result.owner, result.now, result.state = owner, now, state
        project(result)
        return result

    yield build
    Parameters.publish_config_mapping(before)


def project(env):
    q = env.state.attitude_body_to_ned
    angles = camera_angles_for_world_target((0., 0., 0.), env.target, (q.w, q.x, q.y, q.z), env.follower.mount_type)
    env.output, env.aligned = associated_gimbal_output(env.follower, env.owner, env.state, angles,
        receipt=env.now[0], sequence=env.state.sequence)


def advance(env, *, attitude=None):
    env.now[0] += .05
    timing = replace(env.state.attitude_timing,
        publication_timestamp_us=env.state.attitude_timing.publication_timestamp_us+50_000,
        sample_timestamp_us=env.state.attitude_timing.sample_timestamp_us+50_000,
        publication_received_at_monotonic_s=env.now[0], sample_received_at_monotonic_s=env.now[0])
    env.state = replace(env.state, attitude_timing=timing,
        attitude_body_to_ned=attitude or env.state.attitude_body_to_ned)
    _, env.state = observe(env.owner, env.now, env.state)


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('altitude', [False, True])
def test_native_vector_uses_exact_world_bearing_and_correct_altitude_contract(environment, mount, altitude):
    env = environment(mount, altitude=altitude)
    env.follower.require_guidance_input(env.output, env.state)
    env.follower.calculate_control_commands(env.output)
    intent = env.follower.get_last_command_intent()
    assert intent.control_type == 'fixed_wing_external'
    assert intent.fields['course_rad'] == pytest.approx(math.atan2(20., 60.))
    if altitude:
        assert intent.fields['height_rate_m_s'] < 0.
    else:
        assert intent.fields['altitude_amsl_m'] == 550.
        assert 'height_rate_m_s' not in intent.fields
    assert not any(name.startswith('vel_body') for name in intent.fields)
    assert env.follower.filtered_body_ray is None


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_polling_keeps_command_age_but_real_state_progress_recalculates_without_rotating_the_ray(environment, mount):
    env = environment(mount)
    env.follower.calculate_control_commands(env.output)
    first = env.follower.get_last_command_intent()
    env.now[0] += .01
    env.follower.calculate_control_commands(env.output)
    assert env.follower.get_last_command_intent() is first
    retained = env.output.gimbal_observation
    advance(env, attitude=Quaternion.from_euler(-.3, .2, -.5))
    env.follower.calculate_control_commands(env.output)
    updated = env.follower.get_last_command_intent()
    assert updated.created_at_monotonic_s > first.created_at_monotonic_s
    assert updated.fields['course_rad'] == first.fields['course_rad']
    assert env.output.gimbal_observation is retained
    control = env.owner.controls.current_control
    env.follower.update_session_control('requested_speed', 22., control.revision)
    env.follower.calculate_control_commands(env.output)
    assert env.follower.get_last_command_intent().fields['equivalent_airspeed_m_s'] == 22.
    assert env.output.gimbal_observation is retained


@pytest.mark.parametrize('bad', ['missing', 'untyped', 'wrong_provider', 'wrong_ray', 'wrong_mapping', 'reset', 'stale'])
def test_unqualified_or_rewritten_native_input_refuses_before_new_intent(environment, bad):
    env = environment(resolver=bad != 'missing')
    if bad == 'untyped':
        env.aligned = {}
    elif bad == 'wrong_provider':
        env.output.gimbal_observation = replace(env.output.gimbal_observation, provider_id='other-provider')
    elif bad == 'wrong_ray':
        # An internally consistent association for another measured direction.
        env.target = (60., -20., 10.)
        original = env.output
        project(env)
        env.output = original
    elif bad == 'wrong_mapping':
        from classes.aircraft_state import Vector3
        bearing = replace(env.aligned.bearing, direction_body_frd=Vector3(1., 0., 0.))
        env.aligned = replace(env.aligned, bearing=bearing,
            direction_ned=env.state.attitude_body_to_ned.rotate(bearing.direction_body_frd))
    elif bad == 'reset':
        env.state = replace(env.state, sequence=env.state.sequence+1, attitude_timing=replace(
            env.state.attitude_timing, quat_reset_counter=0))
        env.owner.observe(env.state, owner_confirmed=True, target_confirmed=True)
    elif bad == 'stale':
        env.now[0] += .8
    with pytest.raises(ValueError):
        env.follower.require_guidance_input(env.output, env.state)
    assert env.follower.get_last_command_intent() is None


def test_stop_ends_native_binding_and_prevents_resolver_replacement(environment):
    env = environment()
    env.follower.calculate_control_commands(env.output)
    env.follower.emergency_stop()
    assert env.follower.get_last_command_intent() is None
    assert env.follower._native_guidance_input_resolver is None
    assert env.follower.session_controls() == []
    with pytest.raises(ValueError, match='guidance_session_ended'):
        env.follower.require_guidance_input(env.output, env.state)
    with pytest.raises(ValueError):
        env.follower.bind_guidance_input_resolver(lambda *_: env.aligned)


def test_resolver_cannot_be_replaced_or_bound_after_session_acquisition(environment):
    env = environment()
    with pytest.raises(ValueError, match='binding_invalid'):
        env.follower.bind_guidance_input_resolver(lambda *_: env.aligned)


@pytest.mark.parametrize('state', [None, {}, SimpleNamespace(phase=AirframePhase.FIXED_WING)])
def test_bound_native_session_requires_current_typed_aircraft_state(environment, state):
    env = environment()
    with pytest.raises(ValueError, match='native_aircraft_state_unavailable'):
        env.follower.require_guidance_input(env.output, state)


def test_mutable_angle_view_cannot_disagree_with_its_original_typed_observation(environment):
    env = environment()
    env.output.angular = (1., 2., 3.)
    with pytest.raises(ValueError, match='angle_observation_changed'):
        env.follower.require_guidance_input(env.output, env.state)


def test_prepared_session_validates_input_before_acquisition_but_cannot_calculate(environment):
    env = environment(prepare_only=True)
    assert env.owner.phase is AirframePhase.UNKNOWN
    assert env.follower._airframe_session is env.owner
    env.follower.require_guidance_input(env.output, env.state)
    assert env.follower.get_last_command_intent() is None
    with pytest.raises(ValueError, match='session_unbound'):
        env.follower.calculate_control_commands(env.output)
    with pytest.raises(ValueError, match='already_bound'):
        env.follower.create_airframe_session(env.owner.identity, env.owner.phase_owner.capabilities)
    env.state = settle(env.owner, env.now, env.state)
    env.follower.bind_airframe_session(env.owner)
    project(env)
    assert env.follower.follow_target(env.output)
    with pytest.raises(ValueError, match='binding_invalid'):
        env.follower.bind_airframe_session(env.owner)


def test_native_input_expiry_invalidates_intent_without_mc_emergency_stop(environment):
    env = environment()
    assert env.follower.follow_target(env.output)
    for _ in range(17):
        advance(env)
    assert env.owner.require_state() is env.state
    assert not env.follower.follow_target(env.output)
    assert env.follower.get_last_command_intent() is None
    assert env.owner.phase_owner.state.value == 'pursuit'
    assert env.follower.emergency_stop_active is False
    assert env.follower._safety_rejection is None
    assert env.follower._geometry_invalid is None
    assert env.follower._telemetry_metadata['guidance_input_reason'] == 'guidance_input_stale'
    project(env)
    assert env.follower.follow_target(env.output)
    assert env.follower._telemetry_metadata['guidance_input_reason'] is None
    assert env.follower.emergency_stop_active is False


def test_expired_input_uses_the_existing_fw_recovery_deadline_without_budget_reset(environment):
    from classes.target_continuity import (
        ContinuityContext, ContinuityPolicy, IdentityVerdict, TargetContinuitySupervisor,
        TargetEvidenceSnapshot, TargetEvidenceState,
    )
    env = environment()
    assert env.follower.follow_target(env.output)
    supervisor = TargetContinuitySupervisor(ContinuityPolicy.resolve(
        Parameters.TargetContinuity, 'gm_velocity_vector', AirframePhase.FIXED_WING), clock=lambda: env.now[0])
    supervisor.reset_session(session_epoch=0, reason='qualified_component')
    context = ContinuityContext('PX4_NATIVE', AirframePhase.FIXED_WING, 'fixed_wing_external',
        True, True, True, guidance_identity=env.owner.identity)
    confirmed = TargetEvidenceSnapshot(TargetEvidenceState.CONFIRMED, env.now[0], 0, 'component-target',
        IdentityVerdict.CONFIRMED, 'component_observed')
    first = supervisor.evaluate(confirmed, context, env.follower.get_last_command_intent())
    assert first.handoff_request is None
    for _ in range(17):
        advance(env)
    assert not env.follower.follow_target(env.output)
    uncertain = replace(confirmed, state=TargetEvidenceState.UNCERTAIN,
        identity_verdict=IdentityVerdict.UNCONFIRMED, reason_code='guidance_input_stale')
    decision = supervisor.evaluate(uncertain, context, None)
    assert decision.handoff_request is None
    assert decision.authorized_intent.fields['height_rate_m_s'] == 0.
    assert decision.authorized_intent.fields['equivalent_airspeed_m_s'] > 0.
    deadline = supervisor._loss_deadline
    while env.now[0] < deadline+.05:
        advance(env)
        assert not env.follower.follow_target(env.output)
        decision = supervisor.evaluate(replace(uncertain, observed_at_monotonic_s=env.now[0]), context, None)
        assert supervisor._loss_deadline == deadline
        if decision.handoff_request is not None:
            break
    assert decision.handoff_request is not None
    assert decision.handoff_request.action.value == 'hold'
    assert env.follower.emergency_stop_active is False


def test_pure_mc_keeps_its_existing_angle_input_without_native_association(environment):
    environment()  # Establish the same isolated public-default environment.
    controller = SimpleNamespace(current_altitude=50., current_yaw=0., current_roll=0., current_pitch=0.,
        get_guidance_attitude=lambda: (Quaternion(1., 0., 0., 0.), 0.),
        is_command_connection_ready=lambda **_: True)
    follower = FollowerFactory.create_follower('gm_velocity_vector', controller, (0., 0.))
    from classes.tracker_output import TrackerDataType, TrackerOutput
    output = TrackerOutput(TrackerDataType.GIMBAL_ANGLES, 100., True, angular=(0., 0., 0.))
    follower.require_guidance_input(output, aircraft_state(phase=AirframePhase.MULTICOPTER))
    follower.calculate_control_commands(output)
    assert follower.get_last_command_intent().control_type == 'velocity_body_offboard'
    assert follower._native_guidance_input_resolver is None
