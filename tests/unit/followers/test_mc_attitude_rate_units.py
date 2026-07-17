"""MC attitude-rate unit-contract regression tests."""

import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from classes.followers.mc_attitude_rate_follower import MCAttitudeRateFollower


def _bare_follower() -> MCAttitudeRateFollower:
    return MCAttitudeRateFollower.__new__(MCAttitudeRateFollower)


def test_png_rates_remain_radians_per_second_internally():
    follower = _bare_follower()
    follower.last_los_angle = (0.0, 0.0)
    follower.last_los_time = 9.0
    follower.pn_los_smoothing_alpha = 0.3
    follower.smoothed_los_rate = 0.0
    follower.pn_navigation_constant = 4.0
    follower.max_pitch_rate_rad = 1.0
    follower.max_yaw_rate_rad = 1.0
    follower.los_angle_history = []
    follower._calculate_direct_rates = MagicMock()

    target = (math.tan(0.1), math.tan(-0.05))
    with patch(
        'classes.followers.mc_attitude_rate_follower.time.time',
        return_value=10.0,
    ):
        pitch_rate_rad_s, yaw_rate_rad_s = follower._calculate_png_rates(target)

    assert pitch_rate_rad_s == pytest.approx(-0.2)
    assert yaw_rate_rad_s == pytest.approx(0.4)
    follower._calculate_direct_rates.assert_not_called()


def test_coordinated_turn_uses_radians_until_telemetry_display():
    follower = _bare_follower()
    follower.enable_coordinated_turns = True
    follower.turn_coordination_gain = 1.0
    follower.max_bank_angle = 30.0
    follower.pid_roll_rate = MagicMock(side_effect=lambda error_rad: error_rad)

    roll_rate_rad_s = follower._calculate_coordinated_roll_rate(
        yaw_rate_rad_s=0.1,
        ground_speed=10.0,
        current_roll_deg=2.0,
    )

    target_bank_rad = math.atan((0.1 * 10.0) / 9.81)
    expected_error_rad = -(target_bank_rad - math.radians(2.0))
    assert roll_rate_rad_s == pytest.approx(expected_error_rad)
    follower.pid_roll_rate.assert_called_once_with(
        pytest.approx(expected_error_rad)
    )
    assert follower.last_bank_angle == pytest.approx(math.degrees(target_bank_rad))


def test_command_boundary_converts_internal_rates_to_degrees_once():
    follower = _bare_follower()
    follower.extract_target_coordinates = MagicMock(return_value=(0.1, -0.2))
    follower._update_pid_gains = MagicMock()
    follower._handle_target_loss = MagicMock(return_value=True)
    follower.px4_controller = SimpleNamespace(
        current_altitude=20.0,
        current_pitch=0.0,
        current_roll=0.0,
        current_ground_speed=5.0,
    )
    follower._calculate_tracking_rates = MagicMock(
        return_value=(math.radians(10.0), math.radians(20.0))
    )
    follower._calculate_thrust_command = MagicMock(return_value=0.55)
    follower._apply_yaw_error_gating = MagicMock(
        side_effect=lambda _error, pitch_rate, thrust: (pitch_rate, thrust)
    )
    follower._calculate_coordinated_roll_rate = MagicMock(
        return_value=math.radians(5.0)
    )
    follower.command_smoothing_enabled = False
    follower.emergency_stop_active = False
    follower.dive_started = False
    follower.total_commands_issued = 0
    follower.set_command_fields = MagicMock(return_value=True)
    follower.update_telemetry_metadata = MagicMock()
    follower.hover_thrust = 0.5

    follower.calculate_control_commands(MagicMock())

    fields = follower.set_command_fields.call_args.args[0]
    assert fields == pytest.approx(
        {
            'rollspeed_deg_s': 5.0,
            'pitchspeed_deg_s': 10.0,
            'yawspeed_deg_s': 20.0,
            'thrust': 0.55,
        }
    )
    assert follower.total_commands_issued == 1
