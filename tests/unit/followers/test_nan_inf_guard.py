"""
Unit tests for BaseFollower.set_command_field() NaN/Inf guard (WP9).

The guard was introduced in WP9 to prevent non-finite velocity commands from
reaching the setpoint handler and ultimately the flight controller. Non-finite
values (NaN, +Inf, -Inf) can arise from:
  - Division by zero in PID controllers
  - Degenerate geometry (e.g. target directly above, zero-magnitude vectors)
  - Corrupt tracker output or missing telemetry fields

The guard implementation (base_follower.py, set_command_field):

    if not math.isfinite(value):
        logger.error(
            f"Rejecting non-finite command value for {field_name}: {value!r} "
            f"(follower={self.__class__.__name__})"
        )
        return False

These tests use MCVelocityChaseFollower.__new__() to create a concrete but
uninitialized stub (BaseFollower is abstract, so we need a concrete subclass).
The setpoint_handler is mocked so no schema files or hardware are required.
"""

import math
import os
import sys
from unittest.mock import MagicMock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from classes.followers.mc_velocity_chase_follower import MCVelocityChaseFollower


# ---------------------------------------------------------------------------
# Stub builder
# ---------------------------------------------------------------------------

def _make_base_follower_stub() -> MCVelocityChaseFollower:
    """
    Create a minimal MCVelocityChaseFollower instance for set_command_field testing.

    Uses __new__ to bypass __init__ (which requires a live PX4 controller and
    config files). Only the attributes consumed by set_command_field() are set:
      - self.setpoint_handler  (has a .set_field method)
      - self.__class__.__name__  (used in the error log message; provided by __new__)

    The setpoint_handler is a MagicMock so we can verify whether set_field was
    called or correctly suppressed.
    """
    follower = MCVelocityChaseFollower.__new__(MCVelocityChaseFollower)
    follower.setpoint_handler = MagicMock()
    follower.setpoint_handler.set_field = MagicMock()
    follower.setpoint_handler.get_display_name = MagicMock(return_value="MC Velocity Chase")
    return follower


# ---------------------------------------------------------------------------
# Tests: non-finite values are rejected
# ---------------------------------------------------------------------------

def test_nan_is_rejected_and_returns_false():
    """
    set_command_field('field', float('nan')) must return False.

    NaN propagates silently through arithmetic and would corrupt any downstream
    command that adds or multiplies it, leading to undefined flight behaviour.
    """
    follower = _make_base_follower_stub()
    result = follower.set_command_field('vel_body_fwd', float('nan'))
    assert result is False, (
        "set_command_field should return False for NaN but returned "
        f"{result!r}"
    )


def test_nan_does_not_reach_setpoint_handler():
    """
    When value is NaN, setpoint_handler.set_field must NOT be called.

    The guard must intercept before any handler call so the hardware never sees
    the invalid value.
    """
    follower = _make_base_follower_stub()
    follower.set_command_field('vel_body_fwd', float('nan'))
    follower.setpoint_handler.set_field.assert_not_called()


def test_positive_inf_is_rejected_and_returns_false():
    """
    set_command_field('field', float('inf')) must return False.

    Positive infinity could cause integer overflow or saturate actuators if it
    reached the flight controller.
    """
    follower = _make_base_follower_stub()
    result = follower.set_command_field('vel_body_right', float('inf'))
    assert result is False, (
        "set_command_field should return False for +Inf but returned "
        f"{result!r}"
    )


def test_positive_inf_does_not_reach_setpoint_handler():
    """When value is +Inf, setpoint_handler.set_field must NOT be called."""
    follower = _make_base_follower_stub()
    follower.set_command_field('vel_body_right', float('inf'))
    follower.setpoint_handler.set_field.assert_not_called()


def test_negative_inf_is_rejected_and_returns_false():
    """
    set_command_field('field', float('-inf')) must return False.

    Negative infinity has the same risks as positive infinity in the opposite
    direction.
    """
    follower = _make_base_follower_stub()
    result = follower.set_command_field('vel_body_down', float('-inf'))
    assert result is False, (
        "set_command_field should return False for -Inf but returned "
        f"{result!r}"
    )


def test_negative_inf_does_not_reach_setpoint_handler():
    """When value is -Inf, setpoint_handler.set_field must NOT be called."""
    follower = _make_base_follower_stub()
    follower.set_command_field('vel_body_down', float('-inf'))
    follower.setpoint_handler.set_field.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: finite values pass through normally
# ---------------------------------------------------------------------------

def test_finite_positive_value_passes_through():
    """
    set_command_field('field', 5.0) must call setpoint_handler.set_field
    and return True. A normal velocity command must not be blocked.
    """
    follower = _make_base_follower_stub()
    result = follower.set_command_field('vel_body_fwd', 5.0)
    assert result is True, (
        f"set_command_field should return True for finite 5.0 but returned {result!r}"
    )
    follower.setpoint_handler.set_field.assert_called_once_with('vel_body_fwd', 5.0)


def test_finite_zero_passes_through():
    """
    set_command_field('field', 0.0) must pass through. Zero is a valid command
    (e.g. hold position, stop lateral movement).
    """
    follower = _make_base_follower_stub()
    result = follower.set_command_field('yawspeed_deg_s', 0.0)
    assert result is True, (
        f"set_command_field should return True for 0.0 but returned {result!r}"
    )
    follower.setpoint_handler.set_field.assert_called_once_with('yawspeed_deg_s', 0.0)


def test_finite_negative_value_passes_through():
    """
    set_command_field('field', -3.5) must pass through. Negative values are
    valid (e.g. descend, move left, reverse yaw).
    """
    follower = _make_base_follower_stub()
    result = follower.set_command_field('vel_body_down', -3.5)
    assert result is True, (
        f"set_command_field should return True for -3.5 but returned {result!r}"
    )
    follower.setpoint_handler.set_field.assert_called_once_with('vel_body_down', -3.5)


def test_finite_large_value_passes_through():
    """
    Very large but finite values must pass through (clamping, if needed, is the
    setpoint_handler's responsibility, not the NaN guard's).
    """
    follower = _make_base_follower_stub()
    result = follower.set_command_field('vel_body_fwd', 1e10)
    assert result is True, (
        f"set_command_field should return True for large finite 1e10 but returned {result!r}"
    )
    follower.setpoint_handler.set_field.assert_called_once_with('vel_body_fwd', 1e10)


# ---------------------------------------------------------------------------
# Tests: guard is field-name agnostic
# ---------------------------------------------------------------------------

def test_nan_guard_applies_to_any_field_name():
    """
    The NaN guard must reject non-finite values regardless of the field name.
    Tests several field names to confirm the guard is not field-specific.
    """
    field_names = [
        'vel_body_fwd',
        'vel_body_right',
        'vel_body_down',
        'yawspeed_deg_s',
        'rollspeed_deg_s',
        'pitchspeed_deg_s',
        'thrust',
    ]
    for field in field_names:
        follower = _make_base_follower_stub()
        result = follower.set_command_field(field, float('nan'))
        assert result is False, (
            f"Guard failed for field '{field}': expected False, got {result!r}"
        )
        follower.setpoint_handler.set_field.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: setpoint_handler ValueError is handled gracefully
# ---------------------------------------------------------------------------

def test_setpoint_handler_value_error_returns_false():
    """
    If setpoint_handler.set_field raises ValueError (e.g. schema validation
    rejects an out-of-range but finite value), set_command_field must return False
    without propagating the exception.
    """
    follower = _make_base_follower_stub()
    follower.setpoint_handler.set_field.side_effect = ValueError("out of range")

    result = follower.set_command_field('thrust', 999.0)
    assert result is False, (
        f"Expected False when setpoint_handler raises ValueError, got {result!r}"
    )


def test_setpoint_handler_unexpected_exception_returns_false():
    """
    If setpoint_handler.set_field raises an unexpected exception, set_command_field
    must return False without propagating the exception (defensive programming).
    """
    follower = _make_base_follower_stub()
    follower.setpoint_handler.set_field.side_effect = RuntimeError("hardware error")

    result = follower.set_command_field('vel_body_fwd', 3.0)
    assert result is False, (
        f"Expected False when setpoint_handler raises RuntimeError, got {result!r}"
    )
