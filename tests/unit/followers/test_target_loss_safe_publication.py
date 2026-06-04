"""Regression tests for target-loss command publication opt-ins."""

import os
import sys
import time
from unittest.mock import MagicMock


sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.safety_types import TargetLossAction
from classes.followers.fw_attitude_rate_follower import FWAttitudeRateFollower
from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower, Vector3D
from classes.followers.mc_attitude_rate_follower import MCAttitudeRateFollower
from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower
from classes.followers.mc_velocity_distance_follower import MCVelocityDistanceFollower
from classes.followers.mc_velocity_ground_follower import MCVelocityGroundFollower
from classes.followers.mc_velocity_position_follower import MCVelocityPositionFollower
from classes.tracker_output import TrackerDataType, TrackerOutput


def _inactive_position_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=False,
        tracker_id='vision_tracker',
        position_2d=(2.0, 0.0),
        confidence=0.1,
    )


def _inactive_multi_target_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.MULTI_TARGET,
        timestamp=time.time(),
        tracking_active=False,
        tracker_id='smart_tracker',
        position_2d=(0.2, -0.1),
        targets=[
            {
                'target_id': 7,
                'bbox': (100, 100, 50, 50),
                'center': (125, 125),
                'confidence': 0.8,
                'is_selected': True,
            }
        ],
        raw_data={
            'usable_for_following': False,
            'data_is_stale': True,
            'freshness_reason': 'prediction_only',
        },
    )


def _inactive_gimbal_output() -> TrackerOutput:
    return TrackerOutput(
        data_type=TrackerDataType.GIMBAL_ANGLES,
        timestamp=time.time(),
        tracking_active=False,
        tracker_id='gimbal_tracker',
        angular=(12.0, -4.0, 0.0),
        raw_data={'usable_for_following': True, 'data_is_stale': False},
    )


def _capture_atomic_commands(follower):
    follower.set_command_fields = MagicMock(return_value=True)
    return follower.set_command_fields


def _last_atomic_command(follower):
    return follower.set_command_fields.call_args.args[0]


def test_mc_velocity_chase_routes_inactive_output_to_target_loss_commands():
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    tracker_output = _inactive_position_output()
    follower.target_lost = False
    follower.target_loss_start_time = None
    follower.target_loss_stop_velocity = 0.0
    follower.current_forward_velocity = 3.0
    follower.validate_tracker_compatibility = MagicMock(return_value=False)
    follower._check_altitude_safety = MagicMock(return_value=True)
    follower.calculate_control_commands = MagicMock()
    _capture_atomic_commands(follower)
    follower.update_telemetry_metadata = MagicMock()

    assert follower.should_process_inactive_tracker_output(tracker_output) is True
    assert follower.follow_target(tracker_output) is True
    follower.calculate_control_commands.assert_not_called()

    commands = _last_atomic_command(follower)
    assert commands["vel_body_fwd"] == 0.0
    assert commands["vel_body_right"] == 0.0
    assert commands["vel_body_down"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0


def test_mc_velocity_distance_inactive_output_stops_without_pursuit_math():
    follower = MCVelocityDistanceFollower.__new__(MCVelocityDistanceFollower)
    tracker_output = _inactive_position_output()
    follower._last_vel_right = 1.2
    follower._last_vel_down = -0.4
    follower._last_update_time = 0.0
    follower.validate_tracker_compatibility = MagicMock(return_value=False)
    follower.extract_target_coordinates = MagicMock()
    follower.calculate_control_commands = MagicMock()
    _capture_atomic_commands(follower)
    follower.update_telemetry_metadata = MagicMock()

    assert follower.should_process_inactive_tracker_output(tracker_output) is True
    assert follower.follow_target(tracker_output) is True
    follower.extract_target_coordinates.assert_not_called()
    follower.calculate_control_commands.assert_not_called()

    commands = _last_atomic_command(follower)
    assert commands["vel_body_fwd"] == 0.0
    assert commands["vel_body_right"] == 0.0
    assert commands["vel_body_down"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0
    assert follower._last_vel_right == 0.0
    assert follower._last_vel_down == 0.0


def test_mc_velocity_position_inactive_output_holds_without_pursuit_math():
    follower = MCVelocityPositionFollower.__new__(MCVelocityPositionFollower)
    tracker_output = _inactive_position_output()
    follower._last_yaw_command = 0.8
    follower._last_vel_z_command = -0.3
    follower._last_update_time = 0.0
    follower.validate_tracker_compatibility = MagicMock(return_value=False)
    follower.extract_target_coordinates = MagicMock()
    follower.calculate_control_commands = MagicMock()
    _capture_atomic_commands(follower)
    follower.update_telemetry_metadata = MagicMock()

    assert follower.should_process_inactive_tracker_output(tracker_output) is True
    assert follower.follow_target(tracker_output) is True
    follower.extract_target_coordinates.assert_not_called()
    follower.calculate_control_commands.assert_not_called()

    commands = _last_atomic_command(follower)
    assert commands["vel_body_down"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0
    assert follower._last_yaw_command == 0.0
    assert follower._last_vel_z_command == 0.0


def test_mc_velocity_position_inactive_multi_target_output_holds_without_pursuit_math():
    """SmartTracker stale MULTI_TARGET output must still publish a hold command."""
    follower = MCVelocityPositionFollower.__new__(MCVelocityPositionFollower)
    tracker_output = _inactive_multi_target_output()
    follower._last_yaw_command = 0.8
    follower._last_vel_z_command = -0.3
    follower._last_update_time = 0.0
    follower.validate_tracker_compatibility = MagicMock(return_value=False)
    follower.extract_target_coordinates = MagicMock()
    follower.calculate_control_commands = MagicMock()
    _capture_atomic_commands(follower)
    follower.update_telemetry_metadata = MagicMock()

    assert follower.should_process_inactive_tracker_output(tracker_output) is True
    assert follower.follow_target(tracker_output) is True
    follower.extract_target_coordinates.assert_not_called()
    follower.calculate_control_commands.assert_not_called()

    commands = _last_atomic_command(follower)
    assert commands["vel_body_down"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0


def test_mc_velocity_ground_inactive_output_stops_without_pursuit_math():
    follower = MCVelocityGroundFollower.__new__(MCVelocityGroundFollower)
    tracker_output = _inactive_position_output()
    follower.validate_tracker_compatibility = MagicMock(return_value=False)
    follower.extract_target_coordinates = MagicMock()
    follower.calculate_control_commands = MagicMock()
    _capture_atomic_commands(follower)
    follower.update_telemetry_metadata = MagicMock()

    assert follower.should_process_inactive_tracker_output(tracker_output) is True
    assert follower.follow_target(tracker_output) is True
    follower.extract_target_coordinates.assert_not_called()
    follower.calculate_control_commands.assert_not_called()

    commands = _last_atomic_command(follower)
    assert commands["vel_body_fwd"] == 0.0
    assert commands["vel_body_right"] == 0.0
    assert commands["vel_body_down"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0


def test_mc_attitude_rate_routes_inactive_output_to_hover_commands():
    follower = MCAttitudeRateFollower.__new__(MCAttitudeRateFollower)
    tracker_output = _inactive_position_output()
    follower.emergency_stop_active = False
    follower.target_lost = False
    follower.target_loss_start_time = None
    follower.target_loss_events = 0
    follower.hover_thrust = 0.55
    follower.validate_tracker_compatibility = MagicMock(return_value=False)
    follower._check_altitude_safety = MagicMock(return_value=True)
    follower.calculate_control_commands = MagicMock()
    _capture_atomic_commands(follower)
    follower.update_telemetry_metadata = MagicMock()

    assert follower.should_process_inactive_tracker_output(tracker_output) is True
    assert follower.follow_target(tracker_output) is True
    follower.calculate_control_commands.assert_not_called()

    commands = _last_atomic_command(follower)
    assert commands["rollspeed_deg_s"] == 0.0
    assert commands["pitchspeed_deg_s"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0
    assert commands["thrust"] == 0.55


def test_fw_attitude_rate_inactive_output_immediately_publishes_orbit_command():
    follower = FWAttitudeRateFollower.__new__(FWAttitudeRateFollower)
    tracker_output = _inactive_position_output()
    follower.target_lost = False
    follower.target_loss_start_time = None
    follower.target_loss_timeout = 60.0
    follower.target_loss_action = TargetLossAction.ORBIT
    follower.rtl_triggered = False
    follower.validate_tracker_compatibility = MagicMock(return_value=False)
    follower.extract_target_coordinates = MagicMock()
    follower.calculate_control_commands = MagicMock()
    _capture_atomic_commands(follower)
    follower.update_telemetry_metadata = MagicMock()
    follower.log_follower_event = MagicMock()
    follower.orbit_mode_active = False
    follower.orbit_start_time = None
    follower.orbit_radius = 100.0
    follower.min_airspeed = 12.0
    follower.cruise_airspeed = 18.0
    follower.max_yaw_rate = 25.0
    follower.max_roll_rate = 30.0
    follower.max_bank_angle = 35.0
    follower.max_load_factor = 2.5
    follower.turn_coordination_gain = 1.0
    follower.enable_coordinated_turn = True
    follower.cruise_thrust = 0.6
    follower.pid_bank_angle = MagicMock(return_value=5.0)
    follower.px4_controller = type(
        'PX4',
        (),
        {'current_airspeed': 18.0, 'current_roll': 0.0},
    )()

    assert follower.should_process_inactive_tracker_output(tracker_output) is True
    assert follower.follow_target(tracker_output) is True
    follower.extract_target_coordinates.assert_not_called()
    follower.calculate_control_commands.assert_not_called()

    commands = _last_atomic_command(follower)
    assert commands["yawspeed_deg_s"] > 0.0
    assert commands["rollspeed_deg_s"] == 5.0
    assert commands["pitchspeed_deg_s"] == 0.0
    assert commands["thrust"] == 0.6


def test_fw_attitude_rate_continue_inactive_output_publishes_wings_level_cruise():
    follower = FWAttitudeRateFollower.__new__(FWAttitudeRateFollower)
    tracker_output = _inactive_position_output()
    follower.target_lost = False
    follower.target_loss_start_time = None
    follower.target_loss_timeout = 60.0
    follower.target_loss_action = TargetLossAction.CONTINUE
    follower.rtl_triggered = False
    follower.validate_tracker_compatibility = MagicMock(return_value=False)
    follower.extract_target_coordinates = MagicMock()
    follower.calculate_control_commands = MagicMock()
    _capture_atomic_commands(follower)
    follower.update_telemetry_metadata = MagicMock()
    follower.cruise_thrust = 0.6
    follower.orbit_mode_active = True

    assert follower.should_process_inactive_tracker_output(tracker_output) is True
    assert follower.follow_target(tracker_output) is True
    follower.extract_target_coordinates.assert_not_called()
    follower.calculate_control_commands.assert_not_called()

    commands = _last_atomic_command(follower)
    assert commands["rollspeed_deg_s"] == 0.0
    assert commands["pitchspeed_deg_s"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0
    assert commands["thrust"] == 0.6


def test_gm_velocity_chase_fails_closed_when_loss_action_has_no_callback():
    follower = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    tracker_output = _inactive_gimbal_output()
    follower.total_follow_calls = 0
    follower.debug_logging_enabled = False
    follower.last_update_time = time.time()
    follower._perform_safety_checks = MagicMock(
        return_value={'safe_to_proceed': True, 'reason': 'test'}
    )
    follower.log_follower_event = MagicMock()
    follower.target_loss_handler = MagicMock()
    follower.target_loss_handler.update_tracker_status.return_value = {
        'tracking_active': False,
        'target_state': 'LOST',
        'recommended_actions': ['SEARCH_PATTERN'],
    }
    follower._apply_velocity_command = MagicMock()

    assert follower.should_process_inactive_tracker_output(tracker_output) is True
    assert follower.follow_target(tracker_output) is True
    follower.target_loss_handler.update_tracker_status.assert_called_once_with(tracker_output)
    follower._apply_velocity_command.assert_called_once()
    velocity_command = follower._apply_velocity_command.call_args.args[0]
    assert velocity_command.forward == 0.0
    assert velocity_command.right == 0.0
    assert velocity_command.down == 0.0
    assert velocity_command.yaw_rate == 0.0


def test_gm_velocity_chase_stops_publication_when_rtl_requested():
    follower = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    tracker_output = _inactive_gimbal_output()
    follower.total_follow_calls = 0
    follower.debug_logging_enabled = False
    follower.last_update_time = time.time()
    follower._perform_safety_checks = MagicMock(
        return_value={'safe_to_proceed': True, 'reason': 'test'}
    )
    follower.log_follower_event = MagicMock()
    follower.target_loss_handler = MagicMock()
    follower.target_loss_handler.update_tracker_status.return_value = {
        'tracking_active': False,
        'target_state': 'TIMEOUT',
        'recommended_actions': ['RETURN_TO_LAUNCH'],
        'trigger_rtl': True,
    }
    follower._apply_velocity_command = MagicMock()

    assert follower.follow_target(tracker_output) is False
    follower._apply_velocity_command.assert_not_called()


def test_gm_velocity_vector_timeout_zero_command_is_publishable():
    follower = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)
    tracker_output = _inactive_gimbal_output()
    follower.target_loss_timeout = 0.0
    follower.last_valid_time = time.time() - 1.0
    follower.enable_velocity_decay = True
    follower.velocity_decay_rate = 1.0
    follower.last_velocity_vector = Vector3D(3.0, 0.0, 0.0)
    follower.last_update_time = time.time() - 0.1
    follower.current_velocity_magnitude = 3.0
    _capture_atomic_commands(follower)

    assert follower.should_process_inactive_tracker_output(tracker_output) is True
    assert follower._handle_target_loss(time.time()) is True

    commands = _last_atomic_command(follower)
    assert commands["vel_body_fwd"] == 0.0
    assert commands["vel_body_right"] == 0.0
    assert commands["vel_body_down"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0
    assert follower.current_velocity_magnitude == 0.0


def test_gm_velocity_vector_stale_input_public_path_zeroes_commands_without_failed_updates_attr():
    follower = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)
    follower.total_follow_calls = 0
    follower.successful_updates = 0
    follower.current_velocity_magnitude = 4.0
    follower.last_velocity_vector = Vector3D(4.0, 0.0, 0.0)
    follower.following_active = True
    follower._perform_safety_checks = MagicMock(
        return_value={'safe_to_proceed': True, 'reason': 'test'}
    )
    _capture_atomic_commands(follower)
    follower.log_follower_event = MagicMock()

    tracker_output = TrackerOutput(
        data_type=TrackerDataType.GIMBAL_ANGLES,
        timestamp=time.time(),
        tracking_active=False,
        tracker_id='gimbal_tracker',
        angular=(12.0, -4.0, 0.0),
        raw_data={'usable_for_following': False, 'data_is_stale': True},
    )

    assert follower.follow_target(tracker_output) is True

    commands = _last_atomic_command(follower)
    assert commands["vel_body_fwd"] == 0.0
    assert commands["vel_body_right"] == 0.0
    assert commands["vel_body_down"] == 0.0
    assert commands["yawspeed_deg_s"] == 0.0
    assert follower.failed_updates == 1
