"""Independent world-target stimulus for gimbal/PX4 SIH qualification."""

import math
import datetime as dt

import pytest

from tools.sitl_gimbal_geometry_fixture import (
    camera_angles_for_world_target,
    pose_from_mavlink2rest,
)


def _pose_snapshot(updated: str) -> dict:
    return {"vehicles": {"1": {"id": 1, "components": {"1": {"id": 1, "messages": {
        "LOCAL_POSITION_NED": {
            "message": {"type": "LOCAL_POSITION_NED", "time_boot_ms": 1000, "x": 2, "y": 3, "z": -4},
            "status": {"time": {"last_update": updated}},
        },
        "ATTITUDE_QUATERNION": {
            "message": {"type": "ATTITUDE_QUATERNION", "time_boot_ms": 1005,
                        "q1": 1, "q2": 0, "q3": 0, "q4": 0},
            "status": {"time": {"last_update": updated}},
        },
        "ATTITUDE": {
            "message": {"type": "ATTITUDE", "time_boot_ms": 1006, "yaw": 0},
            "status": {"time": {"last_update": updated}},
        },
    }}}}}}


def test_level_north_target_is_forward_for_both_mounts():
    assert camera_angles_for_world_target((0, 0, 0), (20, 0, 0), (1, 0, 0, 0), "HORIZONTAL") == pytest.approx((0, 0, 0))
    assert camera_angles_for_world_target((0, 0, 0), (20, 0, 0), (1, 0, 0, 0), "VERTICAL") == pytest.approx((0, 90, 0))


def test_yawed_aircraft_observes_fixed_world_target_to_its_left():
    turn = math.sqrt(0.5)
    quaternion = (turn, 0, 0, turn)  # Aircraft faces east.
    horizontal = camera_angles_for_world_target((0, 0, 0), (10, 10, 0), quaternion, "HORIZONTAL")
    vertical = camera_angles_for_world_target((0, 0, 0), (10, 10, 0), quaternion, "VERTICAL")
    assert horizontal == pytest.approx((-45, 0, 0))
    assert vertical == pytest.approx((0, 90, 45))


def test_vehicle_pitch_changes_body_depression_of_fixed_world_target():
    nose_up = (math.cos(math.pi / 12), 0, math.sin(math.pi / 12), 0)
    assert camera_angles_for_world_target((0, 0, 0), (20, 0, 0), nose_up, "VERTICAL") == pytest.approx((0, 120, 0))


def test_moving_world_target_crosses_camera_center_without_sign_reversal():
    left = camera_angles_for_world_target((0, 0, 0), (20, -10, 0), (1, 0, 0, 0), "VERTICAL")
    center = camera_angles_for_world_target((0, 0, 0), (20, 0, 0), (1, 0, 0, 0), "VERTICAL")
    right = camera_angles_for_world_target((0, 0, 0), (20, 10, 0), (1, 0, 0, 0), "VERTICAL")
    assert left[2] > center[2] == 0 > right[2]


def test_target_must_be_finite_and_in_front_of_vehicle():
    for target in ((0, 0, 0), (-10, 0, 0), (math.nan, 0, 0)):
        with pytest.raises(ValueError):
            camera_angles_for_world_target((0, 0, 0), target, (1, 0, 0, 0), "VERTICAL")
    with pytest.raises(ValueError, match="quaternion"):
        camera_angles_for_world_target((0, 0, 0), (10, 0, 0), (0, 0, 0, 0), "VERTICAL")


def test_mavlink2rest_pose_requires_matching_fresh_system_and_component():
    now = dt.datetime(2026, 10, 1, 12, 0, 0, tzinfo=dt.timezone.utc)
    snapshot = _pose_snapshot("2026-10-01T12:00:00+00:00")
    assert pose_from_mavlink2rest(snapshot, 1, now=now) == ((2, 3, -4), (1, 0, 0, 0))
    with pytest.raises(ValueError, match="missing"):
        pose_from_mavlink2rest(snapshot, 2, now=now)
    snapshot["vehicles"]["1"]["components"]["1"]["id"] = 2
    with pytest.raises(ValueError, match="component identity"):
        pose_from_mavlink2rest(snapshot, 1, now=now)


def test_mavlink2rest_pose_rejects_old_or_desynchronized_samples():
    now = dt.datetime(2026, 10, 1, 12, 0, 2, tzinfo=dt.timezone.utc)
    snapshot = _pose_snapshot("2026-10-01T12:00:00+00:00")
    with pytest.raises(ValueError, match="stale"):
        pose_from_mavlink2rest(snapshot, 1, now=now)
    snapshot = _pose_snapshot("2026-10-01T12:00:02+00:00")
    snapshot["vehicles"]["1"]["components"]["1"]["messages"]["ATTITUDE_QUATERNION"]["message"]["time_boot_ms"] = 2000
    with pytest.raises(ValueError, match="synchronized"):
        pose_from_mavlink2rest(snapshot, 1, now=now)


def test_mavlink2rest_pose_rejects_reversed_quaternion_convention():
    now = dt.datetime(2026, 10, 1, 12, 0, 2, tzinfo=dt.timezone.utc)
    snapshot = _pose_snapshot("2026-10-01T12:00:02+00:00")
    quaternion = snapshot["vehicles"]["1"]["components"]["1"]["messages"]["ATTITUDE_QUATERNION"]["message"]
    quaternion.update(q1=math.sqrt(0.5), q4=-math.sqrt(0.5))
    snapshot["vehicles"]["1"]["components"]["1"]["messages"]["ATTITUDE"]["message"]["yaw"] = math.pi / 2
    with pytest.raises(ValueError, match="frame convention"):
        pose_from_mavlink2rest(snapshot, 1, now=now)
