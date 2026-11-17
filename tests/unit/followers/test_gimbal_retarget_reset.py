"""Real GM controllers reset target memory without renewing session ownership."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from classes.aircraft_state import AirframePhase, GuidanceSessionIdentity, Quaternion, Vector3
from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower
from classes.gimbal_guidance import VECTOR_MC_MANOEUVRES, GuidanceState
from classes.guidance_phase_session import PhaseSessionState
from classes.native_guidance import NativeCapabilities
from classes.parameters import Parameters
from classes.target_continuity import (
    ContinuityContext, ContinuityPolicy, IdentityVerdict, TargetContinuitySupervisor,
    TargetEvidenceSnapshot, TargetEvidenceState,
)
from classes.tracker_output import TrackerDataType, TrackerOutput
from tests.unit.drone_interface.test_aircraft_state import aircraft_state


@pytest.fixture
def environment(monkeypatch):
    previous = Parameters.get_runtime_config_snapshot()
    defaults = yaml.safe_load((Path(__file__).resolve().parents[3] / 'configs/config_default.yaml').read_text())
    defaults['Safety']['ALLOW_SESSION_VELOCITY_OVERRIDE'] = True
    now = [100.]
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: now[0])
    followers = []

    def build(cls, mount='HORIZONTAL', mode='coordinated_turn'):
        config = deepcopy(defaults)
        config['GimbalTracker']['MOUNT_TYPE'] = mount
        section = 'GM_VELOCITY_CHASE' if cls is GMVelocityChaseFollower else 'GM_VELOCITY_VECTOR'
        config['Follower']['FollowerOverrides'].setdefault(section, {})['LATERAL_GUIDANCE_MODE'] = mode
        Parameters.publish_config_mapping(config)
        controller = SimpleNamespace(current_altitude=50., current_yaw=0., current_pitch=0., current_roll=0.,
            is_command_preview=False, is_command_connection_ready=lambda **_: True,
            get_guidance_attitude=lambda: (Quaternion(1., 0., 0., 0.), 0.))
        follower = cls(controller, (0., 0.))
        followers.append(follower)
        return follower

    try:
        yield build, now
    finally:
        for follower in followers:
            follower.release_session_controls()
        Parameters.publish_config_mapping(previous)


def observation(mount, *, neutral=False):
    yaw, pitch, roll = (0., 0., 0.) if neutral else (20., 15., 0.)
    if mount == 'VERTICAL':
        yaw, pitch, roll = (0., 90., 0.) if neutral else (0., 105., -20.)
    return TrackerOutput(TrackerDataType.GIMBAL_ANGLES, 1_700_000_000., True, angular=(yaw, pitch, roll))


def submitted_history(follower):
    fields = dict(vel_body_fwd=.4, vel_body_right=0., vel_body_down=0., yawspeed_deg_s=5.)
    follower.record_submitted_command(fields)
    return follower._submitted_command_fields, follower._submitted_command_timestamp


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('mode', ['sideslip', 'coordinated_turn'])
def test_pid_retarget_clears_target_memory_and_preserves_gains_limits_and_submitted_history(environment, mount, mode):
    build, now = environment
    follower = build(GMVelocityChaseFollower, mount, mode)
    old = observation(mount)
    follower.calculate_control_commands(old)
    follower.last_tracker_output = old
    follower.current_forward_velocity = 1.
    follower.yaw_smoother.apply(10., .1, 2.)
    controllers = [pid for pid in (follower.pid_right, follower.pid_yaw_speed, follower.pid_down) if pid is not None]
    settings = [(pid.tunings, pid.output_limits, pid.setpoint) for pid in controllers]
    for pid in controllers:
        pid(-.5, dt=.1)
        assert pid._last_input is not None and pid.last_output != 0.
    history = submitted_history(follower)
    follower.following_active = True
    for _ in range(3):
        assert follower.prepare_for_target_transition('camera_retarget')
        assert follower.get_last_command_intent() is None
        assert follower.current_forward_velocity == 0.
        assert follower.last_ramp_update_time is None
        assert follower.last_velocity_command is None and follower.last_tracker_output is None
        assert follower.yaw_smoother.last_yaw_rate == follower.yaw_smoother.filtered_yaw_rate == 0.
        assert [(pid.tunings, pid.output_limits, pid.setpoint) for pid in controllers] == settings
        for pid in controllers:
            assert pid.components == (0., 0., 0.)
            assert pid._last_input is None and pid.last_output == 0.
        assert (follower._submitted_command_fields, follower._submitted_command_timestamp) == history
        assert follower.following_active and not follower.emergency_stop_active
    now[0] += .05
    follower.calculate_control_commands(observation(mount, neutral=True))
    assert follower.get_last_command_intent().fields['vel_body_right'] == 0.
    assert follower.get_last_command_intent().fields['yawspeed_deg_s'] == 0.
    shaped = follower.prepare_authorized_command(follower.get_last_command_intent().fields, loss_decay=False)
    assert shaped['vel_body_fwd'] >= history[0]['vel_body_fwd'] - follower.forward_acceleration * .05 - 1e-9


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_vector_retarget_discards_filter_classifier_and_ramp_but_keeps_acknowledged_speed(environment, mount):
    build, _ = environment
    follower = build(GMVelocityVectorFollower, mount)
    control = follower._requested_speed_control()
    follower.update_session_control('requested_speed', 2., control.revision)
    control = follower._requested_speed_control()
    follower.calculate_control_commands(observation(mount))
    history = submitted_history(follower)
    follower.guidance_classifier.manoeuvres = VECTOR_MC_MANOEUVRES
    follower.guidance_classifier.update(Vector3(-1., 0., 0.), now=100.)
    follower.guidance_classifier.update(Vector3(-1., 0., 0.), now=100.31)
    assert follower.guidance_classifier.state is GuidanceState.REARWARD_GRACE
    for _ in range(3):
        assert follower.prepare_for_target_transition('camera_retarget')
        assert follower.get_last_command_intent() is None
        assert follower.filtered_body_ray is None
        assert follower.last_command_vector is None and follower.last_velocity_vector is None
        assert follower.current_velocity_magnitude == follower.config['INITIAL_VELOCITY']
        assert follower.guidance_classifier.last_decision is None
        assert follower.guidance_classifier.state is GuidanceState.FORWARD
        assert follower.yaw_smoother.last_yaw_rate == follower.yaw_smoother.filtered_yaw_rate == 0.
        assert follower._requested_speed_control() is control
        assert (follower._submitted_command_fields, follower._submitted_command_timestamp) == history


def bind_native(follower, now, phase=AirframePhase.FIXED_WING):
    from tests.unit.drone_interface.test_aircraft_state import attitude_timing
    from tests.fixtures.native_bearing import associated_gimbal_output
    state = aircraft_state(phase=phase, attitude_timing=attitude_timing())
    identity = GuidanceSessionIdentity('gm_follow', state.binding, 1)
    pair = [None]
    if phase is AirframePhase.FIXED_WING:
        follower.bind_guidance_input_resolver(lambda *_: pair[0])
    session = follower.create_airframe_session(identity, NativeCapabilities('native', 'fixture', 2, True, True, False,
        multicopter_altitude_hold_supported=True),
        confirmation_s=0., observation_timeout_s=.75, clock=lambda: now[0])
    assert session.observe(state, owner_confirmed=True, target_confirmed=True).pursuit_allowed
    follower.bind_airframe_session(session)
    output = observation(follower.mount_type)
    if phase is AirframePhase.FIXED_WING:
        output, pair[0] = associated_gimbal_output(follower, session, state, output.angular, receipt=now[0])
    follower.calculate_control_commands(output)
    return session


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('phase', [AirframePhase.MULTICOPTER, AirframePhase.FIXED_WING])
def test_native_vector_retarget_uses_canonical_planner_reset_without_new_session(environment, mount, phase):
    build, now = environment
    follower = build(GMVelocityVectorFollower, mount)
    session = bind_native(follower, now, phase)
    current = session.controls.current_control
    follower.update_session_control('requested_speed', 2. if phase is AirframePhase.MULTICOPTER else 15., current.revision)
    control = session.controls.current_control
    identity, reference = session.identity, session._engagement_altitude_reference
    history = submitted_history(follower)
    session.fixed_wing._vertical = True
    session.fixed_wing._rearward_turn_sign = 1.
    reset = Mock(wraps=session.reset_target_state)
    session.reset_target_state = reset
    for _ in range(3):
        assert follower.prepare_for_target_transition('camera_retarget')
        assert follower._airframe_session is session and session.identity is identity
        assert follower._guidance_state_identity is identity
        assert session._engagement_altitude_reference is reference
        assert session.phase_owner.state is PhaseSessionState.PURSUIT
        assert session.controls.current_control is control
        assert session.last_guidance is None
        assert session.fixed_wing._vertical is False and session.fixed_wing._rearward_turn_sign is None
        assert (follower._submitted_command_fields, follower._submitted_command_timestamp) == history
    assert reset.call_count == 3


@pytest.mark.parametrize('cls', [GMVelocityChaseFollower, GMVelocityVectorFollower])
def test_reset_failure_propagates_after_invalidating_old_intent(environment, monkeypatch, cls):
    build, _ = environment
    follower = build(cls)
    follower.calculate_control_commands(observation('HORIZONTAL'))
    assert follower.get_last_command_intent() is not None
    history = submitted_history(follower)
    target = follower.pid_down if cls is GMVelocityChaseFollower else follower.guidance_classifier
    monkeypatch.setattr(target, 'reset', Mock(side_effect=RuntimeError('reset_refused')))
    assert follower.prepare_for_target_transition('camera_retarget') is False
    assert follower.get_last_command_intent() is None
    assert (follower._submitted_command_fields, follower._submitted_command_timestamp) == history


@pytest.mark.parametrize('ended', [False, True])
def test_native_reset_refuses_stale_or_ended_owner_and_cannot_revive_it(environment, ended):
    build, now = environment
    follower = build(GMVelocityVectorFollower)
    session = bind_native(follower, now)
    if ended:
        follower.emergency_stop()
    else:
        now[0] += 1.
    identity, controls = session.identity, session.controls.current_control
    assert follower.prepare_for_target_transition('camera_retarget') is False
    assert follower.get_last_command_intent() is None
    assert session.identity is identity and session.controls.current_control is controls
    if ended:
        assert session.phase_owner.state is PhaseSessionState.ENDED
        assert follower.emergency_stop_active and not follower.following_active


@pytest.mark.parametrize('cls', [GMVelocityChaseFollower, GMVelocityVectorFollower])
@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_retarget_after_stop_never_clears_stop_latch(environment, cls, mount):
    build, _ = environment
    follower = build(cls, mount)
    follower.calculate_control_commands(observation(mount))
    follower.emergency_stop()
    assert follower.prepare_for_target_transition('late_camera_retarget')
    assert follower.emergency_stop_active and not follower.following_active
    assert follower.follow_target(observation(mount)) is False


@pytest.mark.parametrize('cls', [GMVelocityChaseFollower, GMVelocityVectorFollower])
def test_repeated_gm_resets_leave_single_shared_recovery_budget(environment, cls):
    build, now = environment
    follower = build(cls)
    follower.calculate_control_commands(observation('HORIZONTAL'))
    prior = follower.get_last_command_intent()
    supervisor = TargetContinuitySupervisor(ContinuityPolicy.from_mapping(dict(
        MODE='bounded_decay', MAX_COAST_TIME_S=2., MAX_RETARGET_TIME_S=1., MAX_COAST_DISTANCE_M=100.,
        REACQUIRE_CONFIRMATION_S=.2, AUTHORITY_RESTORE_TIME_S=.5, TERMINAL_ACTION='hold')), clock=lambda: now[0])
    supervisor.reset_session(session_epoch=1, reason='gm_follow_started')
    context = ContinuityContext('PX4', AirframePhase.MULTICOPTER, 'velocity_body_offboard', True, True, True, 0.)

    def evidence(epoch, state):
        verdict = IdentityVerdict.CONFIRMED if state is TargetEvidenceState.CONFIRMED else IdentityVerdict.UNCONFIRMED
        return TargetEvidenceSnapshot(state, now[0], epoch, 'target', verdict, 'fixture_evidence')

    supervisor.evaluate(evidence(1, TargetEvidenceState.CONFIRMED), context, prior)
    deadline = episode = None
    for epoch in (2, 3, 4):
        assert follower.prepare_for_target_transition('camera_retarget')
        assert supervisor.begin_target_transition(session_epoch=epoch, previous_intent=prior)
        decision = supervisor.evaluate(evidence(epoch, TargetEvidenceState.UNCERTAIN), context)
        if deadline is None:
            deadline, episode = supervisor._loss_deadline, decision.episode_id
        assert supervisor._loss_deadline == deadline and decision.episode_id == episode
        now[0] += .1
    now[0] = deadline
    expired = supervisor.evaluate(evidence(4, TargetEvidenceState.ABSENT), context)
    assert expired.handoff_request.reason_code == 'maximum_retarget_time_reached'
