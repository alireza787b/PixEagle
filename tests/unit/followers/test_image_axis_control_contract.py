"""Normalized image-axis to flight-command direction regressions."""

from unittest.mock import MagicMock, patch

import pytest

from classes.followers.mc_attitude_rate_follower import MCAttitudeRateFollower
from classes.followers.base_follower import BaseFollower
from classes.followers.fw_attitude_rate_follower import FWAttitudeRateFollower
from classes.followers.gm_velocity_chase_follower import GMVelocityChaseFollower
from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower
from classes.followers.mc_velocity_distance_follower import MCVelocityDistanceFollower
from classes.followers.mc_velocity_ground_follower import MCVelocityGroundFollower
from classes.followers.yaw_rate_smoother import YawRateSmoother
from classes.parameters import Parameters
from classes.tracker_output import TrackerDataType


def _unit_pid(setpoint: float = 0.0) -> MagicMock:
    pid = MagicMock()
    pid.setpoint = setpoint
    pid.side_effect = lambda measurement: setpoint - measurement
    return pid


def test_control_delta_is_monotonic_and_discards_stall_catch_up():
    timestamp, dt = BaseFollower.bounded_control_delta(
        10.0,
        20.0,
        current_timestamp=12.0,
    )

    assert timestamp == pytest.approx(12.0)
    assert dt == pytest.approx(0.05)
    assert BaseFollower.bounded_control_delta(
        12.0,
        20.0,
        current_timestamp=11.0,
    )[1] == 0.0


def test_control_delta_rejects_invalid_update_rate():
    with pytest.raises(ValueError, match="finite and positive"):
        BaseFollower.bounded_control_delta(
            10.0,
            0.0,
            current_timestamp=10.1,
        )


def test_gimbal_chase_rejects_unimplemented_forward_mode_before_base_setup():
    with patch.object(
        Parameters,
        'GM_VELOCITY_CHASE',
        {
            'MOUNT_TYPE': 'HORIZONTAL',
            'FORWARD_VELOCITY_MODE': 'PROPORTIONAL_NAV',
        },
        create=True,
    ):
        with pytest.raises(ValueError, match="Unsupported GM chase"):
            GMVelocityChaseFollower(MagicMock(), (0.0, 0.0))


def test_chase_coordinated_turn_maps_image_right_to_clockwise_yaw():
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower._update_pid_gains = MagicMock()
    follower._get_active_lateral_mode = MagicMock(return_value='coordinated_turn')
    follower.active_lateral_mode = 'coordinated_turn'
    follower.pid_right = None
    follower.pid_yaw_speed = _unit_pid(setpoint=0.2)
    follower.pid_down = None
    follower.pitch_compensation_enabled = False
    follower.current_forward_velocity = 1.0
    follower.max_tracking_error = 2.0
    follower.velocity_smoothing_enabled = False

    right, down, yaw = follower._calculate_tracking_commands((0.5, 0.0))

    assert right == 0.0
    assert down == 0.0
    assert yaw == pytest.approx(0.3)


def test_distance_yaw_maps_image_right_to_clockwise_yaw():
    follower = MCVelocityDistanceFollower.__new__(MCVelocityDistanceFollower)
    follower.yaw_enabled = True
    follower.yaw_control_threshold = 0.0
    follower.pid_yaw_rate = _unit_pid(setpoint=-0.1)

    assert follower._calculate_yaw_control(0.4) == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("lateral_mode", "command_field"),
    [
        ("coordinated_turn", "yawspeed_deg_s"),
        ("sideslip", "vel_body_right"),
    ],
)
def test_gimbal_chase_preserves_transformed_command_direction(
    lateral_mode,
    command_field,
):
    follower = GMVelocityChaseFollower.__new__(GMVelocityChaseFollower)
    follower.debug_logging_enabled = False
    follower.last_ramp_update_time = 99.9
    follower.update_rate = 20.0
    follower._calculate_forward_velocity = MagicMock(return_value=1.0)
    follower._transform_gimbal_to_control_frame = MagicMock(
        return_value=(0.4, 0.25)
    )
    follower._get_active_lateral_mode = MagicMock(return_value=lateral_mode)
    follower.active_lateral_mode = lateral_mode
    follower.pid_right = _unit_pid()
    follower.pid_yaw_speed = _unit_pid()
    follower.pid_down = _unit_pid()
    follower.yaw_smoother = YawRateSmoother(enabled=False)
    follower.set_command_fields = MagicMock(return_value=True)
    follower._log_velocity_changes = MagicMock()
    tracker_data = MagicMock(
        data_type=TrackerDataType.GIMBAL_ANGLES,
        angular=(0.0, 0.0, 0.0),
        tracking_active=True,
    )

    with patch('classes.followers.base_follower.time.monotonic', return_value=100.0):
        follower.calculate_control_commands(tracker_data)

    command = follower.set_command_fields.call_args.args[0]
    assert command[command_field] > 0.0
    assert command["vel_body_down"] > 0.0


def test_attitude_rate_maps_image_right_to_clockwise_yaw():
    follower = MCAttitudeRateFollower.__new__(MCAttitudeRateFollower)
    follower.pid_pitch_rate = _unit_pid()
    follower.pid_yaw_rate = _unit_pid(setpoint=0.1)

    pitch, yaw = follower._calculate_direct_rates((0.4, 0.0))

    assert pitch == 0.0
    assert yaw == pytest.approx(0.3)


def test_attitude_rate_honors_nonzero_vertical_aim_point():
    follower = MCAttitudeRateFollower.__new__(MCAttitudeRateFollower)
    follower.pid_pitch_rate = _unit_pid(setpoint=-0.3)
    follower.pid_yaw_rate = _unit_pid(setpoint=0.2)

    pitch, yaw = follower._calculate_direct_rates((0.2, -0.3))

    assert pitch == pytest.approx(0.0)
    assert yaw == pytest.approx(0.0)


def test_chase_pid_initialization_honors_resolved_aim_point():
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower.initial_target_coords = (0.2, -0.3)
    follower._get_active_lateral_mode = MagicMock(return_value='coordinated_turn')
    follower._get_pid_gains = MagicMock(return_value=(1.0, 0.0, 0.0))
    follower.max_yaw_rate_rad = 1.0
    velocity_limits = type(
        'VelocityLimits',
        (),
        {'lateral': 2.0, 'vertical': 1.0},
    )()
    follower.safety_manager = MagicMock()
    follower.safety_manager.get_velocity_limits.return_value = velocity_limits
    follower._follower_config_name = 'mc_velocity_chase'
    follower.enable_altitude_control = True

    follower._initialize_pid_controllers()

    assert follower.pid_yaw_speed.setpoint == pytest.approx(0.2)
    assert follower.pid_down.setpoint == pytest.approx(-0.3)


def test_ground_altitude_scaling_preserves_nonzero_aim_equilibrium():
    follower = MCVelocityGroundFollower.__new__(MCVelocityGroundFollower)
    follower.pid_x = _unit_pid(setpoint=0.2)
    follower.pid_y = _unit_pid(setpoint=-0.3)
    follower.extract_target_coordinates = MagicMock(return_value=(0.2, -0.3))
    follower.validate_target_coordinates = MagicMock(return_value=True)
    follower._update_pid_gains = MagicMock()
    follower._apply_gimbal_corrections = MagicMock(return_value=(0.2, -0.3))
    follower.coordinate_corrections_enabled = True
    follower.base_adjustment_factor_x = 0.1
    follower.base_adjustment_factor_y = 0.1
    follower.altitude_factor = 0.005
    follower.px4_controller = type('PX4', (), {'current_altitude': 50.0})()
    follower._control_descent = MagicMock(return_value=0.0)
    follower.set_command_fields = MagicMock(return_value=True)
    follower.update_telemetry_metadata = MagicMock()

    follower.calculate_control_commands(MagicMock())

    command = follower.set_command_fields.call_args.args[0]
    assert command['vel_body_fwd'] == pytest.approx(0.0)
    assert command['vel_body_right'] == pytest.approx(0.0)


def test_chase_vertical_control_honors_nonzero_aim_point():
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower._update_pid_gains = MagicMock()
    follower._get_active_lateral_mode = MagicMock(return_value='coordinated_turn')
    follower.active_lateral_mode = 'coordinated_turn'
    follower.pid_right = None
    follower.pid_yaw_speed = _unit_pid(setpoint=0.2)
    follower.pid_down = _unit_pid(setpoint=-0.3)
    follower.pitch_compensation_enabled = False
    follower.current_forward_velocity = 1.0
    follower.max_tracking_error = 2.0
    follower.velocity_smoothing_enabled = False

    _, at_aim_down, _ = follower._calculate_tracking_commands((0.2, -0.3))
    _, below_aim_down, _ = follower._calculate_tracking_commands((0.2, 0.1))

    assert at_aim_down == pytest.approx(0.0)
    assert below_aim_down > 0.0


def test_distance_vertical_control_honors_nonzero_aim_point():
    follower = MCVelocityDistanceFollower.__new__(MCVelocityDistanceFollower)
    follower.pid_z = _unit_pid(setpoint=-0.3)
    follower.px4_controller = type('PX4', (), {'current_altitude': 50.0})()
    follower.min_descent_height = 5.0
    follower.max_climb_height = 120.0

    assert follower._control_altitude_bidirectional(-0.3) == pytest.approx(0.0)
    assert follower._control_altitude_bidirectional(0.1) > 0.0


def test_fixed_wing_uses_aim_relative_axes_and_mavsdk_pitch_sign():
    follower = FWAttitudeRateFollower.__new__(FWAttitudeRateFollower)
    follower.initial_target_coords = (0.2, -0.3)
    follower.tecs_altitude_scale = 10.0
    follower.extract_target_coordinates = MagicMock(return_value=(0.5, 0.1))
    follower._get_current_airspeed = MagicMock(return_value=12.0)
    follower._get_current_altitude = MagicMock(return_value=50.0)
    follower._get_current_roll = MagicMock(return_value=0.0)
    follower._calculate_l1_guidance = MagicMock(return_value=3.0)
    follower._calculate_coordinated_bank_angle = MagicMock(return_value=5.0)
    follower._calculate_roll_rate = MagicMock(return_value=1.0)
    follower._calculate_tecs_commands = MagicMock(return_value=(-2.0, 0.5))
    follower._apply_command_smoothing = MagicMock(return_value=(1.0, -2.0, 3.0))
    follower.set_command_fields = MagicMock(return_value=True)

    follower.calculate_control_commands(MagicMock())

    follower._calculate_l1_guidance.assert_called_once_with(
        pytest.approx(0.3),
        12.0,
    )
    follower._calculate_tecs_commands.assert_called_once_with(
        pytest.approx(-4.0),
        12.0,
    )


def test_attitude_yaw_gate_uses_error_from_resolved_aim_point():
    follower = MCAttitudeRateFollower.__new__(MCAttitudeRateFollower)
    follower.extract_target_coordinates = MagicMock(return_value=(0.2, 0.0))
    follower._update_pid_gains = MagicMock()
    follower._handle_target_loss = MagicMock(return_value=True)
    follower.px4_controller = type(
        'PX4',
        (),
        {
            'current_altitude': 20.0,
            'current_pitch': 0.0,
            'current_roll': 0.0,
            'current_ground_speed': 2.0,
        },
    )()
    follower.pid_yaw_rate = _unit_pid(setpoint=0.2)
    follower._calculate_tracking_rates = MagicMock(return_value=(0.1, 0.0))
    follower._calculate_thrust_command = MagicMock(return_value=0.5)
    follower._apply_yaw_error_gating = MagicMock(return_value=(0.1, 0.5))
    follower._calculate_coordinated_roll_rate = MagicMock(return_value=0.0)
    follower.command_smoothing_enabled = False
    follower.emergency_stop_active = False
    follower.set_command_fields = MagicMock(return_value=True)
    follower.total_commands_issued = 0
    follower.dive_started = False
    follower.update_telemetry_metadata = MagicMock()
    follower._set_hover_commands = MagicMock()

    follower.calculate_control_commands(MagicMock())

    assert follower._apply_yaw_error_gating.call_args.args[0] == pytest.approx(0.0)
    follower._set_hover_commands.assert_not_called()


def test_chase_emergency_stop_bypasses_yaw_smoothing_history():
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower.last_ramp_update_time = 99.9
    follower.ramp_update_rate = 10.0
    follower.extract_target_coordinates = MagicMock(return_value=(0.4, 0.0))
    follower._handle_target_loss_enhanced = MagicMock(return_value=True)
    follower.last_valid_target_coords = (0.4, 0.0)
    follower._update_forward_velocity = MagicMock(return_value=3.0)
    follower._calculate_tracking_commands = MagicMock(return_value=(1.0, 0.5, 0.4))
    follower.adaptive_mode_enabled = False
    follower.active_lateral_mode = 'coordinated_turn'
    follower.emergency_stop_active = True
    follower.current_forward_velocity = 3.0
    follower.smoothed_right_velocity = 1.0
    follower.smoothed_down_velocity = 0.5
    follower.smoothed_yaw_speed = 20.0
    follower.yaw_smoother = YawRateSmoother(enabled=True)
    follower.yaw_smoother.last_yaw_rate = 30.0
    follower.yaw_smoother.filtered_yaw_rate = 30.0
    follower.set_command_fields = MagicMock(return_value=True)
    follower.update_telemetry_metadata = MagicMock()

    with patch('classes.followers.base_follower.time.monotonic', return_value=100.0):
        follower.calculate_control_commands(MagicMock())

    command = follower.set_command_fields.call_args.args[0]
    assert command == {
        'vel_body_fwd': 0.0,
        'vel_body_right': 0.0,
        'vel_body_down': 0.0,
        'yawspeed_deg_s': 0.0,
    }
    assert follower.yaw_smoother.last_yaw_rate == 0.0
    assert follower.yaw_smoother.filtered_yaw_rate == 0.0
    assert follower.set_command_fields.call_count == 1


def test_chase_command_path_ramps_forward_and_preserves_yaw_direction():
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower.last_ramp_update_time = 99.0
    follower.ramp_update_rate = 10.0
    follower.extract_target_coordinates = MagicMock(return_value=(0.4, 0.0))
    follower._handle_target_loss_enhanced = MagicMock(return_value=True)
    follower.last_valid_target_coords = (0.4, 0.0)
    follower.emergency_stop_active = False
    follower.target_lost = False
    follower.ramp_down_on_target_loss = True
    follower.target_loss_stop_velocity = 0.0
    follower.max_forward_velocity = 8.0
    follower.forward_ramp_rate = 2.0
    follower.forward_velocity_deadzone = 0.01
    follower.current_forward_velocity = 0.0
    follower._calculate_tracking_commands = MagicMock(
        return_value=(0.0, 0.0, 0.2)
    )
    follower.adaptive_mode_enabled = False
    follower.active_lateral_mode = 'coordinated_turn'
    follower.yaw_smoother = YawRateSmoother(enabled=False)
    follower.smoothed_yaw_speed = 0.0
    follower.set_command_fields = MagicMock(return_value=True)
    follower.update_telemetry_metadata = MagicMock()

    with patch('classes.followers.base_follower.time.monotonic', return_value=100.0):
        follower.calculate_control_commands(MagicMock())

    command = follower.set_command_fields.call_args.args[0]
    assert command['vel_body_fwd'] == pytest.approx(0.2)
    assert command['yawspeed_deg_s'] == pytest.approx(11.4591559026)


def test_chase_altitude_safety_error_fails_closed():
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower._safety_checks_bypassed_for_testing = MagicMock(return_value=False)
    follower.is_altitude_safety_enabled = MagicMock(return_value=True)
    follower.safety_manager = MagicMock()
    follower.safety_manager.get_safety_behavior.side_effect = RuntimeError(
        "safety state unavailable"
    )

    assert follower._check_altitude_safety() is False
