"""
Unit tests for MCVelocityPositionFollower control command logic.

Tests verify the yaw error calculation, altitude error sign convention, and
that set_command_fields is called with finite (non-NaN) values. All tests use
the __new__ stub pattern to bypass full follower initialization, keeping them
fast and independent of PX4 controllers, config files, or PID subsystems.

Control conventions (mc_velocity_position profile):
- Image X and MAVSDK yaw rate use the same horizontal sign:
  target_x > setpoint (target right) → positive clockwise yaw command.
- Altitude PID output is positive-up and is converted once to body-down.
  A target below the aim point produces positive body-down velocity (descent).
  A target above the aim point produces negative body-down velocity (climb).
- Commands are sent via one atomic set_command_fields(...) intent containing
  'yawspeed_deg_s' and 'vel_body_down', both finite floats.
"""

import math
import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.followers.mc_velocity_position_follower import MCVelocityPositionFollower


# ---------------------------------------------------------------------------
# Stub builder
# ---------------------------------------------------------------------------

def _build_position_stub(
    setpoint_x: float = 0.0,
    setpoint_y: float = 0.0,
    yaw_control_threshold: float = 0.05,
    altitude_control_enabled: bool = True,
    command_smoothing_enabled: bool = False,
    max_yaw_rate: float = 0.785,
    max_vertical_velocity: float = 3.0,
    min_descent_height: float = 5.0,
    max_climb_height: float = 120.0,
    smoothing_factor: float = 0.8,
) -> MCVelocityPositionFollower:
    """
    Create a minimal MCVelocityPositionFollower stub for control-logic testing.

    Uses __new__ to skip __init__, then manually wires the attributes that are
    read by calculate_control_commands() and the yaw_error / altitude calculation
    branches. PID controllers are replaced with simple lambda callables so tests
    can predict outputs without tuning real gains.
    """
    follower = MCVelocityPositionFollower.__new__(MCVelocityPositionFollower)

    # --- PID stubs --------------------------------------------------------
    # CustomPID calls return (setpoint - measurement) * 1.0 for a P-gain of 1.
    # The .setpoint attribute is read directly by calculate_control_commands.
    pid_yaw = MagicMock()
    pid_yaw.setpoint = setpoint_x
    # When called with target_x, return (setpoint_x - target_x) × 1 (unit P-gain)
    pid_yaw.side_effect = lambda measurement: (setpoint_x - measurement) * 1.0
    follower.pid_yaw_rate = pid_yaw

    pid_z = MagicMock()
    pid_z.setpoint = setpoint_y
    # When called with target_y, return (setpoint_y - target_y) × 1 (unit P-gain)
    pid_z.side_effect = lambda measurement: (setpoint_y - measurement) * 1.0
    follower.pid_z = pid_z

    # --- Control flags ----------------------------------------------------
    follower.yaw_control_enabled = True
    follower.altitude_control_enabled = altitude_control_enabled
    follower.yaw_control_threshold = yaw_control_threshold
    follower.command_smoothing_enabled = command_smoothing_enabled
    follower.smoothing_factor = smoothing_factor
    follower._last_yaw_command = 0.0
    follower._last_vertical_velocity_up_m_s = 0.0
    follower._last_update_time = time.time()

    # YawRateSmoother stub (disabled — tests verify PID/threshold logic, not smoother)
    from classes.followers.yaw_rate_smoother import YawRateSmoother
    follower.yaw_smoother = YawRateSmoother(enabled=False)

    # --- Velocity limits --------------------------------------------------
    follower.max_yaw_rate = max_yaw_rate
    follower.max_vertical_velocity = max_vertical_velocity
    follower.min_descent_height = min_descent_height
    follower.max_climb_height = max_climb_height

    # --- Statistics dict --------------------------------------------------
    follower._control_statistics = {'pid_updates': 0, 'last_update_time': None,
                                     'commands_sent': 0, 'initialization_time': None}

    # --- set_command_fields: mock it so we can inspect the atomic command ---
    follower.set_command_fields = MagicMock(return_value=True)

    # --- Helper methods used inside calculate_control_commands ------------
    # update_telemetry_metadata is called for stats; it does nothing in tests.
    follower.update_telemetry_metadata = MagicMock()

    # --- PID gain update: always succeeds (no-op in stub) -----------------
    follower._update_pid_gains = MagicMock(return_value=True)

    # --- Target coordinate extraction and validation ----------------------
    # extract_target_coordinates returns the bbox.center from TrackerOutput.
    # For simplicity, we monkeypatch it to return fixed coords below per-test.

    # --- px4_controller stub (for altitude safety in _calculate_altitude_command)
    px4 = MagicMock()
    px4.current_altitude = 50.0  # within min/max range → no safety cutoff
    follower.px4_controller = px4

    return follower


def _make_tracker_output(target_x: float, target_y: float):
    """
    Build a minimal TrackerOutput-like MagicMock with coords (target_x, target_y).

    extract_target_coordinates and validate_target_coordinates are patched per test,
    so only the MagicMock identity matters here.
    """
    mock_output = MagicMock()
    mock_output.bbox = MagicMock()
    mock_output.bbox.center = (target_x, target_y)
    return mock_output


def _last_command_fields(follower: MCVelocityPositionFollower) -> dict:
    return follower.set_command_fields.call_args.args[0]


# ---------------------------------------------------------------------------
# Helper: run calculate_control_commands with patched extraction methods
# ---------------------------------------------------------------------------

def _run_control(follower: MCVelocityPositionFollower,
                 target_x: float, target_y: float):
    """
    Patch extract/validate on the stub so calculate_control_commands runs cleanly,
    then call it and return the stub for inspection.
    """
    tracker_data = _make_tracker_output(target_x, target_y)

    with patch.object(follower, 'extract_target_coordinates',
                      return_value=(target_x, target_y)), \
         patch.object(follower, 'validate_target_coordinates',
                      return_value=True):
        follower.calculate_control_commands(tracker_data)

    return follower


# ---------------------------------------------------------------------------
# Tests: yaw error sign
# ---------------------------------------------------------------------------

def test_yaw_command_follows_signed_image_error():
    """
    The signed image error is target_x - pid_setpoint.

    With the default setpoint=0.0 (image center) and target_x=0.3 (right of center):
        yaw_error = 0.3 - 0.0 = +0.3

    MAVSDK body yaw rate is positive clockwise, so image-right requires a
    positive command. The shared helper mirrors the PID measurement so its
    proportional output follows this signed image error.
    """
    follower = _build_position_stub(setpoint_x=0.0, yaw_control_threshold=0.0,
                                    command_smoothing_enabled=False)
    _run_control(follower, target_x=0.3, target_y=0.0)

    expected_yaw_deg_s = math.degrees(0.3)
    commands = _last_command_fields(follower)
    assert 'yawspeed_deg_s' in commands
    actual = commands['yawspeed_deg_s']
    assert abs(actual - expected_yaw_deg_s) < 1e-9, (
        f"Expected yawspeed_deg_s={expected_yaw_deg_s:.6f}, got {actual:.6f}. "
        "Yaw error sign convention is broken."
    )


def test_positive_target_x_produces_positive_clockwise_yaw_command():
    """
    A target to the right of center generates the MAVSDK-positive clockwise yaw
    command needed to turn the camera toward it.

    Verifies the sign relationship, not a specific magnitude.
    """
    follower = _build_position_stub(setpoint_x=0.0, yaw_control_threshold=0.0,
                                    command_smoothing_enabled=False)
    _run_control(follower, target_x=0.5, target_y=0.0)

    yaw_command = _last_command_fields(follower)['yawspeed_deg_s']
    assert yaw_command > 0.0, (
        "Expected positive yaw command for positive target_x (target right of center). "
        f"Got yawspeed_deg_s={yaw_command:.4f}"
    )


def test_negative_target_x_produces_negative_counterclockwise_yaw_command():
    """
    A target to the left of center generates a negative yaw command.
    """
    follower = _build_position_stub(setpoint_x=0.0, yaw_control_threshold=0.0,
                                    command_smoothing_enabled=False)
    _run_control(follower, target_x=-0.5, target_y=0.0)

    yaw_command = _last_command_fields(follower)['yawspeed_deg_s']
    assert yaw_command < 0.0, (
        "Expected negative yaw command for negative target_x (target left of center). "
        f"Got yawspeed_deg_s={yaw_command:.4f}"
    )


def test_enabled_yaw_smoother_receives_degrees_per_second():
    """The shared smoother must not compare a deg/s deadzone with rad/s input."""
    from classes.followers.yaw_rate_smoother import YawRateSmoother

    follower = _build_position_stub(
        setpoint_x=0.0,
        yaw_control_threshold=0.0,
        command_smoothing_enabled=False,
    )
    follower.yaw_smoother = YawRateSmoother(
        enabled=True,
        deadzone_deg_s=0.5,
        max_rate_change_deg_s2=10_000.0,
        smoothing_alpha=1.0,
        enable_speed_scaling=False,
    )
    follower._last_update_time = time.time() - 0.1

    _run_control(follower, target_x=0.3, target_y=0.0)

    yaw_command = _last_command_fields(follower)['yawspeed_deg_s']
    assert yaw_command == pytest.approx(
        math.degrees(0.3) - 0.5,
        abs=1e-6,
    )


def test_custom_horizontal_aim_point_is_not_ignored():
    """The command follows target minus the configured non-zero aim point."""
    follower = _build_position_stub(
        setpoint_x=0.2,
        yaw_control_threshold=0.0,
        command_smoothing_enabled=False,
    )

    _run_control(follower, target_x=0.5, target_y=0.0)

    assert _last_command_fields(follower)['yawspeed_deg_s'] == pytest.approx(
        math.degrees(0.3)
    )


def test_yaw_within_dead_zone_decays_to_zero_when_smoothing_disabled():
    """
    When |yaw_error| <= yaw_control_threshold and smoothing is disabled,
    the yaw command must be 0.0 (dead zone suppresses the command).
    """
    follower = _build_position_stub(setpoint_x=0.0, yaw_control_threshold=0.1,
                                    command_smoothing_enabled=False)
    # target_x=0.05, yaw_error = 0.0 - 0.05 = -0.05 → inside dead zone (< 0.1)
    _run_control(follower, target_x=0.05, target_y=0.0)

    yaw_command = _last_command_fields(follower)['yawspeed_deg_s']
    assert yaw_command == 0.0, (
        f"Expected 0.0 yaw command inside dead zone, got {yaw_command:.6f}"
    )


# ---------------------------------------------------------------------------
# Tests: altitude error sign convention
# ---------------------------------------------------------------------------

def test_altitude_error_positive_means_target_below_setpoint():
    """
    Altitude error = pid_z.setpoint - target_y.
    When target_y < setpoint (target appears above image center in normalized coords),
    the error is positive. With unit P-gain the internal positive-up velocity is
    positive, then converted to the body-FRD positive-down command field.

    target_y=-0.4 (above center) -> upward velocity = +0.4 m/s
    -> vel_body_down = -0.4 (upward, because body-FRD down is positive)
    """
    follower = _build_position_stub(setpoint_y=0.0, altitude_control_enabled=True,
                                    yaw_control_threshold=1.0,  # suppress yaw branch
                                    command_smoothing_enabled=False)
    _run_control(follower, target_x=0.0, target_y=-0.4)

    down_command = _last_command_fields(follower)['vel_body_down']
    # Positive-up internal velocity converts to negative vel_body_down.
    assert down_command < 0.0, (
        "Expected negative vel_body_down (climb) when target is above center. "
        f"Got vel_body_down={down_command:.4f}"
    )


def test_altitude_error_negative_means_target_above_setpoint():
    """
    When target_y > setpoint (target appears below image center), altitude error is
    negative, so vel_body_down is positive (descend).
    """
    follower = _build_position_stub(setpoint_y=0.0, altitude_control_enabled=True,
                                    yaw_control_threshold=1.0,
                                    command_smoothing_enabled=False)
    _run_control(follower, target_x=0.0, target_y=0.4)

    down_command = _last_command_fields(follower)['vel_body_down']
    assert down_command > 0.0, (
        "Expected positive vel_body_down (descend) when target is below center. "
        f"Got vel_body_down={down_command:.4f}"
    )


def test_altitude_disabled_sends_zero_vel_body_down():
    """
    When altitude_control_enabled=False, vel_body_down must be 0.0 regardless of
    where the target appears vertically.
    """
    follower = _build_position_stub(setpoint_y=0.0, altitude_control_enabled=False,
                                    yaw_control_threshold=1.0,
                                    command_smoothing_enabled=False)
    _run_control(follower, target_x=0.0, target_y=0.9)

    down_command = _last_command_fields(follower)['vel_body_down']
    assert down_command == 0.0, (
        f"Expected 0.0 vel_body_down when altitude_control_enabled=False, "
        f"got {down_command:.4f}"
    )


# ---------------------------------------------------------------------------
# Tests: finite-value guarantee (WP9 guard integration)
# ---------------------------------------------------------------------------

def test_set_command_fields_called_with_finite_yaw_value():
    """
    set_command_fields must always receive a finite float for yawspeed_deg_s.
    Non-finite values (NaN, Inf) would corrupt the setpoint and cause undefined
    drone behaviour; the atomic command-intent path rejects them.
    This test verifies that the follower never generates a non-finite yaw command
    under normal operating conditions.
    """
    follower = _build_position_stub(setpoint_x=0.0, yaw_control_threshold=0.0,
                                    command_smoothing_enabled=False)
    _run_control(follower, target_x=0.7, target_y=0.0)

    value = _last_command_fields(follower)['yawspeed_deg_s']
    assert math.isfinite(value), (
        f"yawspeed_deg_s command is not finite: {value!r}"
    )


def test_set_command_fields_called_with_finite_vel_body_down():
    """
    set_command_fields must receive a finite float for vel_body_down under
    normal operating conditions.
    """
    follower = _build_position_stub(setpoint_y=0.0, altitude_control_enabled=True,
                                    yaw_control_threshold=1.0,
                                    command_smoothing_enabled=False)
    _run_control(follower, target_x=0.0, target_y=0.3)

    value = _last_command_fields(follower)['vel_body_down']
    assert math.isfinite(value), (
        f"vel_body_down command is not finite: {value!r}"
    )


def test_both_commands_are_always_sent_regardless_of_control_flags():
    """
    calculate_control_commands must always call set_command_fields for both
    'vel_body_down' and 'yawspeed_deg_s', even when altitude control is disabled.
    This ensures the setpoint handler always receives a complete command frame.
    """
    follower = _build_position_stub(altitude_control_enabled=False,
                                    yaw_control_threshold=0.0,
                                    command_smoothing_enabled=False)
    _run_control(follower, target_x=0.2, target_y=0.5)

    field_names = _last_command_fields(follower).keys()
    assert 'vel_body_down' in field_names, (
        "set_command_fields was not called with 'vel_body_down'"
    )
    assert 'yawspeed_deg_s' in field_names, (
        "set_command_fields was not called with 'yawspeed_deg_s'"
    )
