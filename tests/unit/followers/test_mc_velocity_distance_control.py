"""Focused MC velocity-distance command and telemetry regressions."""

from __future__ import annotations

import math
import time
from unittest.mock import MagicMock

import pytest

from classes.followers.mc_velocity_distance_follower import MCVelocityDistanceFollower
from classes.tracker_output import TrackerDataType, TrackerOutput


pytestmark = [pytest.mark.unit]


def test_active_yaw_telemetry_uses_the_final_smoothed_command():
    follower = MCVelocityDistanceFollower.__new__(MCVelocityDistanceFollower)
    follower.extract_target_coordinates = MagicMock(return_value=(0.2, -0.1))
    follower.validate_target_coordinates = MagicMock(return_value=True)
    follower._update_pid_gains = MagicMock()
    follower.pid_y = MagicMock(setpoint=0.0)
    follower.pid_y.return_value = 0.25
    follower.pid_z = MagicMock(setpoint=0.0)
    follower._control_altitude_bidirectional = MagicMock(return_value=-0.1)
    follower._calculate_yaw_control = MagicMock(
        return_value=math.radians(6.0)
    )
    follower.command_smoothing_enabled = False
    follower._last_update_time = time.time() - 0.05
    follower.yaw_smoother = MagicMock()
    follower.yaw_smoother.apply.return_value = 4.0
    follower.set_command_fields = MagicMock(return_value=True)
    follower.update_telemetry_metadata = MagicMock()
    follower.reset_command_fields = MagicMock()

    tracker_output = TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        timestamp=time.time(),
        tracking_active=True,
        position_2d=(0.2, -0.1),
    )

    follower.calculate_control_commands(tracker_output)

    command = follower.set_command_fields.call_args.args[0]
    assert command["yawspeed_deg_s"] == pytest.approx(4.0)
    follower.update_telemetry_metadata.assert_any_call("yaw_active", True)
    follower.reset_command_fields.assert_not_called()
