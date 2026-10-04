"""Regressions for v12 retarget command steps, cadence and measurement wrapping."""

import math
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from classes.followers.base_follower import BaseFollower
from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower, Vector3D
from classes.followers.yaw_rate_smoother import YawRateSmoother
from classes.gimbal_geometry import resolve_angle_geometry
from classes.gimbal_transforms import VelocityCommand
from classes.safety_types import AltitudeLimits, RateLimits, VelocityLimits
from classes.tracker_output import TrackerDataType, TrackerOutput
from tests.unit.followers.test_gm_velocity_vector_control import _build_follower_stub


FIELDS = ('vel_body_fwd', 'vel_body_right', 'vel_body_down', 'yawspeed_deg_s')


def output(angles):
    return TrackerOutput(
        data_type=TrackerDataType.GIMBAL_ANGLES, timestamp=1000.0,
        tracking_active=True, angular=angles,
    )


@pytest.mark.parametrize('mount,neutral', [('HORIZONTAL', (0, 0, 0)), ('VERTICAL', (0, 90, 0))])
def test_vector_startup_and_stalls_cannot_accumulate_connection_delay(monkeypatch, mount, neutral):
    follower = _build_follower_stub(False, 0.0)
    follower.mount_type = mount
    follower.update_rate = 20
    follower.max_velocity = 0.5
    follower.ramp_acceleration = 0.25
    now = [1000.0]
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: now[0])
    follower.last_update_time = -1000000.0
    follower.calculate_control_commands(output(neutral))
    assert follower.current_velocity_magnitude == pytest.approx(0.0125)
    now[0] += 10.0
    follower.calculate_control_commands(output(neutral))
    assert follower.current_velocity_magnitude == pytest.approx(0.025)


@pytest.mark.parametrize('cadence', [20, 30, 60])
def test_body_ray_filter_has_same_elapsed_time_response(cadence):
    follower = _build_follower_stub(False, 0.5)
    follower.update_rate = 20
    follower.angle_smoothing_alpha = 0.2
    follower._filter_body_ray(Vector3D(1, 0, 0), 0.05)
    target = Vector3D(math.cos(math.radians(60)), math.sin(math.radians(60)), 0)
    for _ in range(cadence):
        result = follower._filter_body_ray(target, 1.0 / cadence)
    expected_degrees = 60 * (1 - 0.8 ** 20)
    assert math.degrees(math.atan2(result.y, result.x)) == pytest.approx(expected_degrees, abs=1e-8)


def test_wrap_crossing_uses_short_ray_path_with_expert_zero_offset(monkeypatch):
    follower = _build_follower_stub(False, 0.5)
    follower.update_rate = 20
    follower.angle_smoothing_alpha = 0.5
    follower.angle_geometry = resolve_angle_geometry({
        'GEOMETRY_OVERRIDE': {'AZIMUTH_ZERO_ADJUST_DEG': 180.0},
    }, 'HORIZONTAL')
    now = [100.0]
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: now[0])
    follower.calculate_control_commands(output((179, 0, 0)))
    now[0] += 0.05
    follower.calculate_control_commands(output((-179, 0, 0)))
    command = follower.set_command_fields.call_args.args[0]
    assert command['vel_body_fwd'] > 0.49
    assert abs(command['vel_body_right']) < 1e-9


def test_invalid_raw_ray_cannot_be_hidden_by_old_valid_filter_state():
    follower = _build_follower_stub(False, 0.5)
    follower.update_rate = 20
    follower.angle_smoothing_alpha = 0.01
    follower.calculate_control_commands(output((0, 0, 0)))
    with pytest.raises(RuntimeError, match='forward hemisphere'):
        follower.calculate_control_commands(output((179, 0, 0)))
    assert follower.set_command_fields.call_count == 1


def guidance_follower(cls):
    follower = cls.__new__(cls)
    follower._follower_config_name = 'GM_VELOCITY_CHASE' if cls is GMVelocityChaseFollower else 'GM_VELOCITY_VECTOR'
    follower.update_rate = 20
    follower.forward_acceleration = 2.0
    follower.ramp_acceleration = 0.25
    follower.enable_altitude_control = True
    follower.px4_controller = SimpleNamespace(current_altitude=20.0, is_command_connection_ready=lambda **_: True)
    follower.safety_manager = SimpleNamespace(
        get_velocity_limits=lambda _: VelocityLimits(0.5, 0.5, 0.5, 1.0),
        get_rate_limits=lambda _: RateLimits(math.radians(45), 0, 0),
        get_altitude_limits=lambda _: AltitudeLimits(3, 120, 2),
    )
    follower.yaw_smoother = YawRateSmoother()
    return follower


@pytest.mark.parametrize('cls,acceleration', [(GMVelocityChaseFollower, 2), (GMVelocityVectorFollower, 0.25)])
def test_retarget_halving_slews_from_submitted_motion(monkeypatch, cls, acceleration):
    follower = guidance_follower(cls)
    now = [100.0]
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: now[0])
    previous = dict(zip(FIELDS, (0.48, 0, 0, 10)))
    follower.record_submitted_command(previous)
    now[0] += 0.03
    next_command = follower.limit_authorized_command(dict(zip(FIELDS, (0.24, 0.2, 0.1, -10))))
    delta = math.sqrt(sum((next_command[name] - previous[name]) ** 2 for name in FIELDS[:3]))
    assert delta == pytest.approx(acceleration * 0.03)
    assert abs(next_command['yawspeed_deg_s'] - previous['yawspeed_deg_s']) <= 90 * 0.03 + 1e-9
    assert follower._submitted_command_fields == previous


@pytest.mark.parametrize('cls', [GMVelocityChaseFollower, GMVelocityVectorFollower])
def test_final_altitude_guard_overrides_retained_smoothed_descent(monkeypatch, cls):
    follower = guidance_follower(cls)
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: 100.0)
    follower.record_submitted_command(dict(zip(FIELDS, (0.4, 0, 0.4, 0))))
    follower.px4_controller.current_altitude = 4.0
    shaped = follower.limit_authorized_command(dict(zip(FIELDS, (0.4, 0, 0.2, 0))))
    assert shaped['vel_body_down'] == 0.0
    assert follower._vertical_limit_status == 'descent_limited'
    follower.px4_controller.current_altitude = None
    with pytest.raises(ValueError, match='altitude'):
        follower.limit_authorized_command(dict(zip(FIELDS, (0.4, 0, 0.2, 0))))


@pytest.mark.parametrize('cadence', [20, 30, 60])
def test_yaw_filter_preserves_reference_coefficient_meaning(cadence):
    smoother = YawRateSmoother(
        deadzone_deg_s=0, enable_speed_scaling=False,
        max_rate_change_deg_s2=1e6, smoothing_alpha=0.2, reference_rate_hz=20,
    )
    for _ in range(cadence):
        actual = smoother.apply(10, 1.0 / cadence)
    assert actual == pytest.approx(10 * (1 - 0.8 ** 20), abs=1e-8)


@pytest.mark.parametrize('cadence', [20, 30, 60])
def test_chase_velocity_filter_preserves_elapsed_time_response(cadence):
    follower = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    follower.last_velocity_command = VelocityCommand()
    follower.update_rate = 20
    follower.smoothing_factor = 0.2
    for _ in range(cadence):
        follower.last_velocity_command = follower._apply_velocity_smoothing(VelocityCommand(0.5, 0.25, -0.25, 0), 1 / cadence)
    assert follower.last_velocity_command.forward == pytest.approx(0.5 * (1 - 0.8 ** 20))


def test_chase_normal_guidance_honors_smoothing_switch(monkeypatch):
    follower = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    follower.debug_logging_enabled = False
    follower.update_rate = 20
    follower.last_ramp_update_time = None
    follower._calculate_forward_velocity = Mock(return_value=0.5)
    follower._transform_gimbal_to_control_frame = Mock(return_value=(0.25, 0.25))
    follower._get_active_lateral_mode = Mock(return_value='sideslip')
    follower.active_lateral_mode = 'sideslip'
    follower.pid_right = SimpleNamespace(setpoint=0, __call__=None)
    follower.positive_error_pid_command = Mock(return_value=0.25)
    follower.enable_altitude_control = False
    follower.command_smoothing_enabled = True
    follower.smoothing_factor = 0.2
    follower.last_velocity_command = VelocityCommand()
    follower.set_command_fields = Mock(return_value=True)
    follower._log_velocity_changes = Mock()
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: 100.0)
    follower.calculate_control_commands(output((0, 0, 0)))
    smoothed = follower.set_command_fields.call_args.args[0]
    assert smoothed['vel_body_fwd'] == pytest.approx(0.1)
    assert smoothed['vel_body_right'] == pytest.approx(0.05)
    follower.command_smoothing_enabled = False
    follower.calculate_control_commands(output((0, 0, 0)))
    assert follower.set_command_fields.call_args.args[0]['vel_body_fwd'] == 0.5


def test_time_filter_rejects_invalid_coefficients():
    with pytest.raises(ValueError):
        BaseFollower.time_normalized_alpha(math.nan, 0.05, 20)


@pytest.mark.parametrize('cls', [GMVelocityChaseFollower, GMVelocityVectorFollower])
@pytest.mark.parametrize('mode,cleared', [('sideslip', 'yawspeed_deg_s'), ('coordinated_turn', 'vel_body_right')])
def test_final_shaping_cannot_reintroduce_previous_lateral_owner(cls, mode, cleared):
    follower = guidance_follower(cls)
    follower.active_lateral_mode = mode
    previous_right = 0.4 if mode == 'sideslip' else 0.0
    follower.record_submitted_command(dict(zip(FIELDS, (0.4, previous_right, 0.1, 15))))
    shaped = follower.limit_authorized_command(dict(zip(FIELDS, (0.4, 0, 0.1, 0))))
    assert shaped[cleared] == 0.0


@pytest.mark.parametrize('cls,acceleration', [(GMVelocityChaseFollower, 2), (GMVelocityVectorFollower, 0.25)])
def test_coast_lateral_zeroing_reserves_three_axis_slew_budget(monkeypatch, cls, acceleration):
    follower = guidance_follower(cls)
    follower.active_lateral_mode = 'coordinated_turn'
    now = [100.0]
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: now[0])
    maximum = acceleration / follower.update_rate
    previous = dict(zip(FIELDS, (0.4, maximum * 0.4, 0.1, 0)))
    follower.record_submitted_command(previous)
    now[0] += 0.05
    shaped = follower.limit_authorized_command(dict(zip(FIELDS, (0.1, 0, -0.1, 2))))
    delta = math.sqrt(sum((shaped[name] - previous[name]) ** 2 for name in FIELDS[:3]))
    assert shaped['vel_body_right'] == 0.0
    assert delta == pytest.approx(maximum, abs=1e-10)
    assert shaped['yawspeed_deg_s'] <= follower.yaw_smoother.max_rate_change_deg_s2 / follower.update_rate


@pytest.mark.parametrize('cls,acceleration', [(GMVelocityChaseFollower, 2), (GMVelocityVectorFollower, 0.25)])
def test_large_coast_lateral_motion_unwinds_before_turn_guidance(monkeypatch, cls, acceleration):
    follower = guidance_follower(cls)
    follower.active_lateral_mode = 'coordinated_turn'
    now = [100.0]
    monkeypatch.setattr('classes.followers.base_follower.time.monotonic', lambda: now[0])
    maximum = acceleration / follower.update_rate
    previous = dict(zip(FIELDS, (0.4, -2.5 * maximum, 0.1, 0)))
    for index in range(3):
        follower.record_submitted_command(previous)
        now[0] += 0.05
        shaped = follower.limit_authorized_command(dict(zip(FIELDS, (0.1, 0, -0.1, 2))))
        delta = math.sqrt(sum((shaped[name] - previous[name]) ** 2 for name in FIELDS[:3]))
        assert delta <= maximum + 1e-10
        if index < 2:
            assert shaped['vel_body_right'] < 0.0
            assert shaped['vel_body_fwd'] == previous['vel_body_fwd']
            assert shaped['vel_body_down'] == previous['vel_body_down']
            assert shaped['yawspeed_deg_s'] == 0.0
        else:
            assert shaped['vel_body_right'] == 0.0
            assert shaped['yawspeed_deg_s'] > 0.0
        previous = shaped


@pytest.mark.parametrize('cls', [GMVelocityChaseFollower, GMVelocityVectorFollower])
def test_safety_refusal_is_not_reported_as_ordinary_tracking_loss(cls):
    follower = cls.__new__(cls)
    follower.total_follow_calls = 0
    follower.debug_logging_enabled = False
    follower.safety_interventions = 0
    follower._perform_safety_checks = Mock(return_value={
        'safe_to_proceed': False, 'reason': 'stale_aircraft_altitude',
    })
    follower.log_follower_event = Mock()
    assert follower.follow_target(output((0, 0, 0))) is False
    assert follower._safety_rejection == 'stale_aircraft_altitude'
    assert follower._geometry_invalid is None


@pytest.mark.parametrize('cls', [GMVelocityChaseFollower, GMVelocityVectorFollower])
def test_loss_safety_guard_preserves_inertial_course_compensation(cls):
    follower = guidance_follower(cls)
    follower.active_lateral_mode = 'coordinated_turn'
    guarded = follower.guard_authorized_command(dict(zip(FIELDS, (0.3, 0.1, 0, 0))))
    assert guarded['vel_body_right'] == 0.1
    assert guarded['yawspeed_deg_s'] == 0.0
