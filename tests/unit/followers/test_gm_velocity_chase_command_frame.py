"""Real PID constructors separate physical camera rays from heading commands."""

from copy import deepcopy
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from classes.aircraft_state import Quaternion
from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.parameters import Parameters
from classes.tracker_output import TrackerDataType, TrackerOutput
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target


@pytest.fixture
def environment(monkeypatch):
    previous = Parameters.get_runtime_config_snapshot()
    defaults = yaml.safe_load((Path(__file__).resolve().parents[3] / 'configs/config_default.yaml').read_text())
    now = [100.]
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: now[0])
    followers = []

    def build(mount, *, euler=(0., 0., 0.), mode=None, altitude=None,
              forward='CONSTANT', smoothing=None):
        config = deepcopy(defaults)
        config['GimbalTracker']['MOUNT_TYPE'] = mount
        config['GM_VELOCITY_CHASE']['FORWARD_VELOCITY_MODE'] = forward
        overrides = config['Follower']['FollowerOverrides'].setdefault('GM_VELOCITY_CHASE', {})
        for name, value in (('LATERAL_GUIDANCE_MODE', mode), ('ENABLE_ALTITUDE_CONTROL', altitude),
                            ('COMMAND_SMOOTHING_ENABLED', smoothing)):
            if value is not None:
                overrides[name] = value
        Parameters.publish_config_mapping(config)
        attitude = Quaternion.from_euler(*(math.radians(value) for value in euler))
        controller = SimpleNamespace(
            current_altitude=50., current_roll=euler[0], current_pitch=euler[1], current_yaw=euler[2],
            is_command_preview=False, is_command_connection_ready=lambda **_: True,
            get_guidance_attitude=Mock(return_value=(attitude, math.radians(euler[2]))),
        )
        follower = GMVelocityChaseFollower(controller, (0., 0.))
        followers.append(follower)
        return follower, attitude

    try:
        yield build, now
    finally:
        for follower in followers:
            follower.release_session_controls()
        Parameters.publish_config_mapping(previous)


def observation(follower, attitude, target):
    angles = camera_angles_for_world_target(
        (0., 0., 0.), target, (attitude.w, attitude.x, attitude.y, attitude.z), follower.mount_type,
    )
    return TrackerOutput(TrackerDataType.GIMBAL_ANGLES, 1_700_000_000., True, angular=angles)


def calculate(follower, attitude, target):
    follower.calculate_control_commands(observation(follower, attitude, target))
    return follower.get_last_command_intent().fields


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
def test_default_roll_does_not_turn_toward_a_target_at_the_current_heading(environment, mount):
    build, _ = environment
    follower, attitude = build(mount, euler=(30., 0., 0.))
    command = calculate(follower, attitude, (20., 0., 8.))
    assert follower.active_lateral_mode == 'coordinated_turn'
    assert not follower.enable_altitude_control
    assert command['yawspeed_deg_s'] == pytest.approx(0., abs=1e-12)
    assert command['vel_body_down'] == command['vel_body_right'] == 0.
    assert command['vel_body_fwd'] == pytest.approx(.1)


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('mode', ['sideslip', 'coordinated_turn'])
@pytest.mark.parametrize('altitude', [False, True])
@pytest.mark.parametrize('euler', [(0., 30., 0.), (30., 0., 0.), (20., 35., 179.), (-25., -15., -179.)])
def test_world_target_errors_are_independent_of_roll_pitch_and_heading_wrap(environment, mount, mode, altitude, euler):
    build, _ = environment
    heading = math.radians(euler[2])
    # Independent heading-only fixture: this target is forward, right and down.
    target = (20. * math.cos(heading) - 8. * math.sin(heading),
              20. * math.sin(heading) + 8. * math.cos(heading), 6.)
    level, level_attitude = build(mount, euler=(0., 0., euler[2]), mode=mode, altitude=altitude)
    tilted, tilted_attitude = build(mount, euler=euler, mode=mode, altitude=altitude)
    reference = calculate(level, level_attitude, target)
    command = calculate(tilted, tilted_attitude, target)
    assert command == pytest.approx(reference, abs=1e-12)
    assert command['vel_body_fwd'] == pytest.approx(.1)
    assert command['vel_body_right' if mode == 'sideslip' else 'yawspeed_deg_s'] > 0.
    assert command['yawspeed_deg_s' if mode == 'sideslip' else 'vel_body_right'] == 0.
    if altitude:
        assert command['vel_body_down'] > 0.
    else:
        assert command['vel_body_down'] == 0.
    tilted.px4_controller.get_guidance_attitude.assert_called_once_with()


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('euler,target,zero_field', [
    ((0., 30., 0.), (20., 0., 0.), 'vel_body_down'),
    ((30., 0., 0.), (20., 8., 0.), 'vel_body_down'),
    ((30., 0., 0.), (20., 0., 8.), 'vel_body_right'),
])
def test_tilt_does_not_mix_lateral_and_vertical_pid_errors(environment, mount, euler, target, zero_field):
    build, _ = environment
    follower, attitude = build(mount, euler=euler, mode='sideslip', altitude=True)
    command = calculate(follower, attitude, target)
    assert command[zero_field] == pytest.approx(0., abs=1e-12)


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('mode', ['sideslip', 'coordinated_turn'])
@pytest.mark.parametrize('altitude', [False, True])
@pytest.mark.parametrize('forward', ['CONSTANT', 'PITCH_BASED'])
@pytest.mark.parametrize('smoothing', [False, True])
def test_level_attitude_preserves_existing_pid_ramp_and_filter_behavior(environment, mount, mode, altitude, forward, smoothing):
    build, now = environment
    follower, attitude = build(mount, mode=mode, altitude=altitude, forward=forward, smoothing=smoothing)
    reference, reference_attitude = build(mount, mode=mode, altitude=altitude, forward=forward, smoothing=smoothing)
    target = [20., 8., 6.]

    def previous_level_errors(*_):
        # The previous physical-ray law at level attitude, independently from NED truth.
        return (math.degrees(math.atan2(target[1], target[0])) / reference.max_roll_angle,
                math.degrees(math.atan2(target[2], math.hypot(*target[:2]))) / reference.max_pitch_angle)

    reference._transform_gimbal_to_control_frame = previous_level_errors
    settings = [(pid.tunings, pid.output_limits) for pid in
                (follower.pid_right, follower.pid_yaw_speed, follower.pid_down) if pid is not None]
    for point in ((20., 8., 6.), (20., -4., -3.), (20., 0., 0.)):
        target[:] = point
        assert calculate(follower, attitude, target) == pytest.approx(calculate(reference, reference_attitude, target))
        now[0] += .05
    assert settings == [(pid.tunings, pid.output_limits) for pid in
                        (follower.pid_right, follower.pid_yaw_speed, follower.pid_down) if pid is not None]


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('target,reason', [
    ((10., 0., 30.), 'outside the forward hemisphere'),
    ((-10., 0., -30.), 'outside the heading-frame forward hemisphere'),
])
def test_physical_and_heading_forward_checks_cannot_replace_each_other(environment, mount, target, reason):
    build, _ = environment
    follower, attitude = build(mount, euler=(0., 60., 0.))
    with pytest.raises(RuntimeError, match=reason):
        calculate(follower, attitude, target)
    assert follower.get_last_command_intent() is None
    assert follower._geometry_invalid == f'Target ray is {reason}'


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('mode', ['sideslip', 'coordinated_turn'])
@pytest.mark.parametrize('altitude', [False, True])
def test_stale_attitude_refuses_new_pursuit_and_normal_tracking_zeros_old_intent(environment, mount, mode, altitude):
    build, _ = environment
    follower, attitude = build(mount, mode=mode, altitude=altitude)
    target = (20., 8., 6.)
    assert calculate(follower, attitude, target)['vel_body_fwd'] > 0.
    follower.px4_controller.get_guidance_attitude.side_effect = ValueError('attitude_stale')
    with pytest.raises(RuntimeError, match='attitude_stale'):
        calculate(follower, attitude, target)
    assert follower._safety_rejection == 'attitude_stale'
    assert not follower._process_normal_tracking(observation(follower, attitude, target), 1_700_000_000.)
    assert all(value == 0. for value in follower.get_last_command_intent().fields.values())
    assert not follower.following_active
