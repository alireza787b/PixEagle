"""Focused MC velocity-distance command and telemetry regressions."""

from __future__ import annotations

import math
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from classes.followers.mc_velocity_distance_follower import MCVelocityDistanceFollower
from classes.tracker_output import TrackerDataType, TrackerOutput


pytestmark = [pytest.mark.unit]


def test_absent_ceiling_does_not_silently_halt_distance_climb(caplog):
    follower = MCVelocityDistanceFollower.__new__(MCVelocityDistanceFollower)
    follower.px4_controller = SimpleNamespace(current_altitude=1000.)
    follower.min_descent_height = 3.
    follower.max_climb_height = None
    follower.pid_z = MagicMock(return_value=-.4)
    assert follower._control_altitude_bidirectional(-.4) == -.4
    assert not [record for record in caplog.records if record.levelname == "ERROR"]


@pytest.mark.parametrize("altitude_control_enabled", [True, False])
def test_active_yaw_telemetry_uses_the_final_smoothed_command(altitude_control_enabled):
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
    follower.altitude_control_enabled = altitude_control_enabled
    follower.px4_controller = SimpleNamespace(current_altitude=None)
    follower.control_update_rate = 20.0
    follower._last_update_time = time.monotonic() - 0.05
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
    if not altitude_control_enabled:
        follower._control_altitude_bidirectional.assert_not_called()
        assert command["vel_body_down"] == 0.
    follower.update_telemetry_metadata.assert_any_call("yaw_active", True)
    follower.reset_command_fields.assert_not_called()
