"""Session speed changes retain geometry, timing and final altitude guards."""

import math
from types import SimpleNamespace

import pytest
from unittest.mock import Mock

from classes.follower_session_controls import SessionControl
from classes.safety_manager import SafetyManager
from tests.unit.followers.test_gm_velocity_vector_control import _build_follower_stub, _run_normalization
from tools.sitl_gimbal_geometry_fixture import camera_angles_for_world_target

pytestmark = pytest.mark.unit


def follower_with_control(speed=3.0):
    follower = _build_follower_stub(True, speed)
    follower.update_rate = 20
    follower.max_velocity = 5
    follower._session_controls = {
        'requested_speed': SessionControl('requested_speed', 'Requested speed', 'm/s', 0, 5, .5, speed)
    }
    return follower


@pytest.mark.parametrize('mount', ['HORIZONTAL', 'VERTICAL'])
@pytest.mark.parametrize('altitude_enabled', [True, False])
@pytest.mark.parametrize('target', [(20, 0, -10), (20, 0, 10), (20, -10, 0), (20, 10, 0)])
def test_speed_change_keeps_independent_world_direction(mount, altitude_enabled, target):
    follower = follower_with_control()
    follower.mount_type = mount
    follower.enable_altitude_control = altitude_enabled
    follower.update_session_control('requested_speed', 1.5, 0)
    angles = camera_angles_for_world_target((0, 0, 0), target, (1, 0, 0, 0), mount)
    commands = _run_normalization(follower, *angles)
    speed = math.sqrt(sum(commands[name] ** 2 for name in ('vel_body_fwd', 'vel_body_right', 'vel_body_down')))
    assert speed == pytest.approx(1.5)
    assert commands['vel_body_right'] * target[1] >= 0
    if altitude_enabled:
        assert commands['vel_body_down'] * target[2] >= 0
    else:
        assert commands['vel_body_down'] == 0


@pytest.mark.parametrize('rate', [5, 20, 30, 60])
def test_speed_ramps_both_directions_without_connection_time_catchup(rate):
    follower = follower_with_control(0)
    follower.ramp_acceleration = .5
    follower.update_session_control('requested_speed', 2, 0)
    for _ in range(rate * 2):
        follower._update_velocity_magnitude(1 / rate)
    assert follower.current_velocity_magnitude == pytest.approx(1)
    follower.update_session_control('requested_speed', 0, 1)
    for _ in range(rate * 2):
        follower._update_velocity_magnitude(1 / rate)
    assert follower.current_velocity_magnitude == pytest.approx(0, abs=.01)


def test_lower_request_caps_retained_continuity_command_without_increasing_it(monkeypatch):
    follower = follower_with_control()
    follower.ramp_acceleration = 1
    follower._submitted_command_timestamp = 100
    follower._submitted_command_fields = dict(vel_body_fwd=3, vel_body_right=0, vel_body_down=0, yawspeed_deg_s=0)
    follower.update_session_control('requested_speed', 1, 0)
    monkeypatch.setattr('classes.followers.gm_velocity_vector_follower.time.monotonic', lambda: 100.05)
    retained = follower.limit_session_control_command(follower._submitted_command_fields)
    assert retained['vel_body_fwd'] == pytest.approx(2.95)
    follower._submitted_command_fields = dict(retained, vel_body_fwd=1)
    result = follower.limit_session_control_command(dict(retained, vel_body_fwd=4))
    assert result['vel_body_fwd'] == pytest.approx(1)


@pytest.mark.parametrize(('altitude', 'pitch'), [(4, 30), (119, -30)])
def test_altitude_guard_does_not_redistribute_blocked_vertical_speed(altitude, pitch):
    follower = follower_with_control(2)
    follower.px4_controller.current_altitude = altitude
    commands = _run_normalization(follower, 0, pitch)
    assert commands['vel_body_down'] == 0
    assert commands['vel_body_fwd'] == pytest.approx(2 * math.cos(math.radians(pitch)))


def test_zero_request_and_session_reset():
    follower = follower_with_control()
    follower.config = {'INITIAL_VELOCITY': 0}
    follower.yaw_smoother = Mock()
    follower.safety_manager.get_velocity_limits = lambda _: SimpleNamespace(forward=5, max_magnitude=6)
    follower.setpoint_handler = SimpleNamespace(profile_config={'session_controls': {'requested_speed': {
        'label': 'Requested speed', 'unit': 'm/s', 'step': .5}}})
    follower.update_session_control('requested_speed', 0, 0)
    commands = _run_normalization(follower, 20, 10)
    assert all(commands[name] == 0 for name in ('vel_body_fwd', 'vel_body_right', 'vel_body_down'))
    follower.reset_control_session()
    assert follower.session_controls()[0]['value'] == 5
    assert follower.session_controls()[0]['revision'] == 0
    assert follower.current_velocity_magnitude == 0


def test_saved_startup_request_is_validated_against_existing_ceiling():
    follower = follower_with_control()
    follower.config = {'REQUESTED_SPEED': 6}
    follower.safety_manager.get_velocity_limits = lambda _: SimpleNamespace(forward=5, max_magnitude=7)
    follower.setpoint_handler = SimpleNamespace(profile_config={'session_controls': {'requested_speed': {
        'label': 'Requested speed', 'unit': 'm/s', 'step': .5}}})
    with pytest.raises(ValueError, match='out_of_range'):
        follower.create_session_controls()


@pytest.mark.parametrize(('global_ceiling', 'follower_ceiling', 'expected'), [
    (8, None, 8), (12, 9, 9), (8, 10, 8),
])
def test_requested_speed_uses_configured_envelope_without_a_second_fixed_ceiling(global_ceiling, follower_ceiling, expected):
    follower = follower_with_control()
    follower.config = {'REQUESTED_SPEED': None}
    follower.safety_manager = SafetyManager()
    follower.safety_manager.load_from_config({'Safety': {
        'GlobalLimits': {'MAX_VELOCITY': global_ceiling, 'MAX_VELOCITY_FORWARD': global_ceiling},
        'FollowerOverrides': {'GM_VELOCITY_VECTOR': {} if follower_ceiling is None else {
            'MAX_VELOCITY_FORWARD': follower_ceiling,
        }},
    }})
    follower.setpoint_handler = SimpleNamespace(profile_config={'session_controls': {'requested_speed': {
        'label': 'Requested speed', 'unit': 'm/s', 'step': .5}}})
    follower._session_controls = follower.create_session_controls()
    control = follower.session_controls()[0]
    assert control['maximum'] is None
    assert control['configured_maximum'] == expected
    assert control['value'] == expected
    follower.update_session_control('requested_speed', expected - .5, 0)
    assert follower.session_controls()[0]['value'] == expected - .5


def override_follower():
    follower = follower_with_control(0)
    follower.config = {}
    follower.max_velocity = 1
    follower.safety_manager = SafetyManager()
    follower.safety_manager.load_from_config({'Safety': {'GlobalLimits': {
        'MAX_VELOCITY': 1, 'MAX_VELOCITY_FORWARD': 1,
        'MAX_VELOCITY_LATERAL': .2, 'MAX_VELOCITY_VERTICAL': .25,
    }}})
    follower.setpoint_handler = SimpleNamespace(profile_config={'session_controls': {'requested_speed': {
        'label': 'Requested speed', 'unit': 'm/s', 'step': .5}}})
    follower._session_controls = follower.create_session_controls()
    return follower


def test_operator_override_replaces_all_velocity_caps_at_the_final_command_boundary(monkeypatch):
    from classes.command_safety import validate_and_clamp_command_values

    follower = override_follower()
    monkeypatch.setattr(SafetyManager, '_instance', follower.safety_manager)
    monkeypatch.setattr('classes.parameters._safety_manager', follower.safety_manager)
    follower.update_session_control('requested_speed', 4, 0)
    follower.current_velocity_magnitude = 4
    commands = _run_normalization(follower, 40, 30)
    validated = validate_and_clamp_command_values('velocity_body_offboard', commands, follower_name='GM_VELOCITY_VECTOR')
    assert validated == commands
    assert math.hypot(*(commands[name] for name in ('vel_body_fwd', 'vel_body_right', 'vel_body_down'))) == pytest.approx(4)
    assert commands['vel_body_right'] > .2
    assert commands['vel_body_down'] > .25
    assert follower.session_controls()[0]['override_active'] is True
    # Non-velocity protections and other follower profiles are untouched.
    assert follower.safety_manager.get_limit('MAX_YAW_RATE', 'GM_VELOCITY_VECTOR') == 45
    assert follower.safety_manager.get_velocity_limits('GM_VELOCITY_CHASE').forward == 1
    assert follower.altitude_limits.safety_enabled is True
    summary = follower.safety_manager.get_effective_limits_summary('GM_VELOCITY_VECTOR')
    assert summary['MAX_VELOCITY_VERTICAL']['source'] == 'FollowSession'
    assert summary['MAX_VELOCITY_VERTICAL']['configured_value'] == .25
    assert summary['MAX_VELOCITY_VERTICAL']['effective_value'] == 4
    follower.update_session_control('requested_speed', None, 1)
    assert follower.session_controls()[0]['override_active'] is False
    assert follower.session_controls()[0]['value'] == 1
    restored = validate_and_clamp_command_values('velocity_body_offboard', commands, follower_name='GM_VELOCITY_VECTOR')
    assert 0 < restored['vel_body_fwd'] <= 1
    assert 0 < restored['vel_body_right'] <= .2
    assert 0 < restored['vel_body_down'] <= .25
    assert math.hypot(*(restored[name] for name in ('vel_body_fwd', 'vel_body_right', 'vel_body_down'))) == pytest.approx(1)
    follower.safety_manager.load_from_config({'Safety': {'GlobalLimits': {
        'MAX_VELOCITY': 1, 'MAX_VELOCITY_FORWARD': 5, 'MAX_VELOCITY_LATERAL': 5, 'MAX_VELOCITY_VERTICAL': 5,
    }}})
    restored = validate_and_clamp_command_values('velocity_body_offboard', commands, follower_name='GM_VELOCITY_VECTOR')
    assert math.hypot(*(restored[name] for name in ('vel_body_fwd', 'vel_body_right', 'vel_body_down'))) == pytest.approx(1)


def test_override_decelerates_then_cannot_survive_session_end_or_clear_a_new_owner():
    follower = override_follower()
    follower.ramp_acceleration = 1
    follower.update_session_control('requested_speed', 5, 0)
    follower.current_velocity_magnitude = 4
    follower.update_session_control('requested_speed', 0, 1)
    follower._update_velocity_magnitude(.1)
    assert follower.current_velocity_magnitude == pytest.approx(3.9)
    assert follower.velocity_limits.forward == pytest.approx(3.9)
    replacement = override_follower()
    replacement.safety_manager = follower.safety_manager
    replacement.update_session_control('requested_speed', 6, 0)
    follower.release_session_controls()
    assert replacement.velocity_limits.forward == 6
    replacement.release_session_controls()
    assert replacement.velocity_limits.forward == 1
