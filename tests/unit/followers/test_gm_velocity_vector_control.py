"""
Unit tests for GMVelocityVectorFollower altitude normalization logic (WP3.8 bug fix).

Tests exercise the REAL production code path through calculate_control_commands()
using a minimal stub that bypasses __init__ while providing all attributes
required by the normalization and velocity command blocks.

Bug #1 fixed in WP3.8:
    After zeroing velocity_vector.z for horizontal-only mode, the original code
    did not re-scale the horizontal components. A 3D unit vector
    (e.g. [0.57, 0.57, 0.57]) would be silently reduced to [0.57, 0.57, 0.0],
    losing horizontal speed proportional to the discarded vertical component.
    The fix re-normalizes x and y so their combined magnitude equals
    current_velocity_magnitude.
"""

import math
import os
import sys
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from unittest.mock import MagicMock
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower, Vector3D
from classes.tracker_output import TrackerOutput, TrackerDataType


# ---------------------------------------------------------------------------
# Gimbal angles for HORIZONTAL mount that produce the 3D diagonal unit vector
# [1/√3, 1/√3, 1/√3].  With HORIZONTAL mount geometry:
#   fwd   = cos(pitch) * cos(yaw)
#   right = sin(yaw)   * cos(pitch)
#   down  = sin(pitch)
# yaw=45° → fwd==right; pitch=arctan(1/√2)≈35.26° → all three components equal.
_DIAGONAL_YAW_DEG = 45.0
_DIAGONAL_PITCH_DEG = math.degrees(math.atan(1.0 / math.sqrt(2.0)))   # ≈35.26°


# ---------------------------------------------------------------------------
# Stub builder
# ---------------------------------------------------------------------------

def _build_follower_stub(
    enable_altitude_control: bool,
    current_velocity_magnitude: float,
    min_velocity: float = 0.0,
) -> GMVelocityVectorFollower:
    """
    Create a fully-attributed GMVelocityVectorFollower stub for production-code testing.

    All attributes consumed by calculate_control_commands() are populated.
    set_command_field is replaced with MagicMock() to capture velocity commands.
    Uses HORIZONTAL mount (project default) with no filtering/offsets for determinism.
    """
    follower = GMVelocityVectorFollower.__new__(GMVelocityVectorFollower)

    # --- _filter_angles() ---
    follower.filtered_angles = None       # None = first call returns raw angles unchanged
    follower.angle_deadzone = 0.0         # no deadzone → deterministic pass-through
    follower.angle_smoothing_alpha = 1.0  # alpha=1 → no EMA smoothing

    # --- _apply_angle_corrections() ---
    follower.mount_yaw_offset = 0.0
    follower.mount_pitch_offset = 0.0
    follower.mount_roll_offset = 0.0
    follower.invert_yaw = False
    follower.invert_pitch = False
    follower.invert_roll = False

    # --- _gimbal_to_body_vector() ---
    follower.mount_type = 'HORIZONTAL'

    # --- _update_velocity_magnitude() ---
    follower.max_velocity = current_velocity_magnitude   # already at target → no ramp
    follower.ramp_acceleration = 1e9                     # instantaneous ramp (irrelevant)

    # --- altitude normalization block ---
    follower.enable_altitude_control = enable_altitude_control
    follower.current_velocity_magnitude = current_velocity_magnitude

    # --- min-velocity threshold ---
    follower.min_velocity = min_velocity

    # --- lateral mode (sideslip → no yaw_smoother needed) ---
    follower.enable_auto_mode_switching = False
    follower.active_lateral_mode = 'sideslip'

    # --- command smoothing ---
    follower.command_smoothing_enabled = False
    follower.last_command_vector = None

    # --- misc state ---
    follower.last_update_time = time.time()
    follower.last_velocity_vector = None

    # --- capture output ---
    follower.set_command_field = MagicMock()

    return follower


def _run_normalization(
    follower: GMVelocityVectorFollower,
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float = 0.0,
) -> dict:
    """
    Drive the real calculate_control_commands() with given gimbal angles.

    Returns a dict {field_name: last_value} for every set_command_field call.
    """
    tracker_data = TrackerOutput(
        data_type=TrackerDataType.GIMBAL_ANGLES,
        timestamp=time.time(),
        tracking_active=True,
        angular=(yaw_deg, pitch_deg, roll_deg),
    )
    follower.calculate_control_commands(tracker_data)

    # Collect the most-recent value for each field
    result: dict = {}
    for call in follower.set_command_field.call_args_list:
        result[call.args[0]] = call.args[1]
    return result


# ---------------------------------------------------------------------------
# Tests: horizontal-only mode (enable_altitude_control=False)
# ---------------------------------------------------------------------------

def test_horizontal_only_maintains_speed_from_3d_unit_vector():
    """
    When enable_altitude_control=False, a 3D unit vector must be re-normalized
    so the horizontal output magnitude equals current_velocity_magnitude.

    Gimbal angles produce [1/√3, 1/√3, 1/√3]; after zeroing z and re-normalizing,
    the combined (forward, right) magnitude must equal the desired speed.
    """
    speed = 3.0
    follower = _build_follower_stub(enable_altitude_control=False,
                                    current_velocity_magnitude=speed)

    cmds = _run_normalization(follower, _DIAGONAL_YAW_DEG, _DIAGONAL_PITCH_DEG)

    fwd = cmds.get("vel_body_fwd", float("nan"))
    right = cmds.get("vel_body_right", float("nan"))
    horiz_magnitude = math.sqrt(fwd ** 2 + right ** 2)
    assert abs(horiz_magnitude - speed) < 1e-6, (
        f"Expected horizontal magnitude {speed:.6f}, got {horiz_magnitude:.6f}. "
        "Horizontal speed was not re-normalized after zeroing z."
    )


def test_horizontal_only_zeroes_z_component():
    """
    When enable_altitude_control=False, vel_body_down must always be 0.0,
    regardless of the original vertical component.
    """
    speed = 5.0
    follower = _build_follower_stub(enable_altitude_control=False,
                                    current_velocity_magnitude=speed)

    cmds = _run_normalization(follower, _DIAGONAL_YAW_DEG, _DIAGONAL_PITCH_DEG)

    down = cmds.get("vel_body_down", float("nan"))
    assert down == 0.0, (
        f"Expected vel_body_down=0.0 in horizontal-only mode, got {down!r}"
    )


def test_horizontal_only_no_division_by_zero_when_target_directly_above():
    """
    When the gimbal points straight up (pitch=90°), both horizontal velocity
    components are zero (horiz_mag = 0 ≤ 1e-6). The branch must handle this
    without raising ZeroDivisionError or producing NaN/Inf values.

    vel_body_down is still zeroed; forward and right remain at ≈0.
    """
    speed = 4.0
    follower = _build_follower_stub(enable_altitude_control=False,
                                    current_velocity_magnitude=speed)

    # pitch=90° → HORIZONTAL mount gives fwd=0, right=0, down=1 → horiz_mag=0
    cmds = _run_normalization(follower, 0.0, 90.0)

    fwd = cmds.get("vel_body_fwd", float("nan"))
    right = cmds.get("vel_body_right", float("nan"))
    down = cmds.get("vel_body_down", float("nan"))

    assert math.isfinite(fwd), f"vel_body_fwd is not finite: {fwd!r}"
    assert math.isfinite(right), f"vel_body_right is not finite: {right!r}"
    assert down == 0.0, (
        f"Expected vel_body_down=0.0 even when horizontal is zero, got {down!r}"
    )
    # horizontal components stay at near-zero (no scaling applied)
    assert abs(fwd) < 1e-9, f"Expected forward≈0 for straight-up target, got {fwd!r}"
    assert abs(right) < 1e-9, f"Expected right≈0 for straight-up target, got {right!r}"


# ---------------------------------------------------------------------------
# Tests: 3D mode (enable_altitude_control=True)
# ---------------------------------------------------------------------------

def test_altitude_control_enabled_preserves_z_component():
    """
    When enable_altitude_control=True, the normalization block must NOT execute.
    vel_body_down must be non-zero (≈speed/√3 for the diagonal unit vector).
    """
    speed = 3.0
    follower = _build_follower_stub(enable_altitude_control=True,
                                    current_velocity_magnitude=speed)

    cmds = _run_normalization(follower, _DIAGONAL_YAW_DEG, _DIAGONAL_PITCH_DEG)

    down = cmds.get("vel_body_down", float("nan"))
    expected_down = speed / math.sqrt(3.0)
    assert abs(down - expected_down) < 1e-3, (
        f"3D mode should preserve z component. Expected down≈{expected_down:.4f}, got {down:.4f}."
    )


def test_altitude_control_enabled_preserves_x_and_y():
    """
    When enable_altitude_control=True, horizontal commands must not be re-scaled.
    Forward and right should each equal speed/√3 for the diagonal unit vector.
    """
    speed = 6.0
    follower = _build_follower_stub(enable_altitude_control=True,
                                    current_velocity_magnitude=speed)

    cmds = _run_normalization(follower, _DIAGONAL_YAW_DEG, _DIAGONAL_PITCH_DEG)

    fwd = cmds.get("vel_body_fwd", float("nan"))
    right = cmds.get("vel_body_right", float("nan"))
    expected = speed / math.sqrt(3.0)

    assert abs(fwd - expected) < 1e-3 and abs(right - expected) < 1e-3, (
        f"3D mode should not modify x or y. "
        f"Expected fwd≈{expected:.4f} right≈{expected:.4f}, "
        f"got fwd={fwd:.4f} right={right:.4f}."
    )


# ---------------------------------------------------------------------------
# Tests: Vector3D helper (sanity checks for the dataclass)
# ---------------------------------------------------------------------------

def test_vector3d_magnitude_calculation():
    """Vector3D.magnitude() must return the Euclidean norm."""
    v = Vector3D(x=3.0, y=4.0, z=0.0)
    assert abs(v.magnitude() - 5.0) < 1e-9


def test_vector3d_normalize_unit_length():
    """Vector3D.normalize() must return a unit vector (magnitude == 1)."""
    v = Vector3D(x=2.0, y=3.0, z=6.0)  # magnitude = 7
    n = v.normalize()
    assert abs(n.magnitude() - 1.0) < 1e-9


def test_vector3d_normalize_zero_vector_returns_zero():
    """Vector3D.normalize() on a zero vector must return (0, 0, 0) without error."""
    v = Vector3D(x=0.0, y=0.0, z=0.0)
    n = v.normalize()
    assert n.x == 0.0 and n.y == 0.0 and n.z == 0.0


def test_horizontal_only_exact_speed_symmetric_vector():
    """
    Regression: for the 3D diagonal vector (equal x=y=z=speed/√3), after
    horizontal-only normalization the horizontal magnitude must exactly equal
    current_velocity_magnitude.
    """
    speed = 7.5
    follower = _build_follower_stub(enable_altitude_control=False,
                                    current_velocity_magnitude=speed)

    cmds = _run_normalization(follower, _DIAGONAL_YAW_DEG, _DIAGONAL_PITCH_DEG)

    fwd = cmds.get("vel_body_fwd", float("nan"))
    right = cmds.get("vel_body_right", float("nan"))
    horiz_mag = math.sqrt(fwd ** 2 + right ** 2)
    assert abs(horiz_mag - speed) < 1e-6, (
        f"Symmetric case: expected horizontal magnitude {speed}, got {horiz_mag}"
    )
