#!/usr/bin/env python3
"""Derive synthetic camera angles from a PX4 SIH pose and fixed NED target.

The quaternion is the PX4 vehicle-attitude body-FRD to world-NED rotation
(w, x, y, z). A MAVSDK NED-to-body quaternion must be inverted first. This
fixture is independent of the production camera-to-body transform.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from collections.abc import Sequence
from pathlib import Path


def _finite_vector(values: Sequence[float], length: int, name: str) -> tuple[float, ...]:
    if len(values) != length:
        raise ValueError(f"{name} requires {length} values")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise ValueError(f"{name} must be finite")
    return result


def _world_to_body(
    world_vector: tuple[float, float, float],
    body_to_ned_quaternion: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    w, x, y, z = body_to_ned_quaternion
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm < 1e-9:
        raise ValueError("body-to-NED quaternion has zero length")
    w, x, y, z = (part / norm for part in (w, x, y, z))
    north, east, down = world_vector

    # Dot each body axis (the rotation-matrix columns) with the world ray.
    forward = (1 - 2 * (y * y + z * z)) * north + 2 * (x * y + w * z) * east + 2 * (x * z - w * y) * down
    right = 2 * (x * y - w * z) * north + (1 - 2 * (x * x + z * z)) * east + 2 * (y * z + w * x) * down
    body_down = 2 * (x * z + w * y) * north + 2 * (y * z - w * x) * east + (1 - 2 * (x * x + y * y)) * down
    return forward, right, body_down


def camera_angles_for_world_target(
    vehicle_position_ned: Sequence[float],
    target_position_ned: Sequence[float],
    body_to_ned_quaternion: Sequence[float],
    mount_type: str,
) -> tuple[float, float, float]:
    """Return synthetic raw (yaw, pitch, roll) for a target in front of SIH."""
    vehicle = _finite_vector(vehicle_position_ned, 3, "vehicle position")
    target = _finite_vector(target_position_ned, 3, "target position")
    quaternion = _finite_vector(body_to_ned_quaternion, 4, "body-to-NED quaternion")
    relative_ned = tuple(end - start for start, end in zip(vehicle, target))
    forward, right, down = _world_to_body(relative_ned, quaternion)
    if forward <= 1e-6:
        raise ValueError("world target must be inside the aircraft forward hemisphere")
    azimuth = math.degrees(math.atan2(right, forward))
    depression = math.degrees(math.atan2(down, math.hypot(forward, right)))
    if mount_type == "HORIZONTAL":
        return azimuth, depression, 0.0
    if mount_type == "VERTICAL":
        return 0.0, 90.0 + depression, -azimuth
    raise ValueError(f"unsupported mount type: {mount_type}")


def pose_from_mavlink2rest(
    snapshot: dict,
    system_id: int,
    *,
    now: dt.datetime | None = None,
    max_age_s: float = 0.5,
) -> tuple[tuple[float, float, float], tuple[float, float, float, float]]:
    """Read one fresh, same-system PX4 pose from a MAVLink2REST snapshot."""
    if not isinstance(system_id, int) or isinstance(system_id, bool) or not 1 <= system_id <= 255:
        raise ValueError("an explicit MAVLink system ID from 1 to 255 is required")
    if not math.isfinite(max_age_s) or max_age_s <= 0:
        raise ValueError("max pose age must be finite and positive")
    try:
        vehicle = snapshot["vehicles"][str(system_id)]
        if vehicle["id"] != system_id:
            raise ValueError("MAVLink vehicle identity does not match the selected system")
        component = vehicle["components"]["1"]
        if component["id"] != 1:
            raise ValueError("PX4 autopilot component identity does not match")
        messages = component["messages"]
        position = messages["LOCAL_POSITION_NED"]
        attitude = messages["ATTITUDE_QUATERNION"]
        euler = messages["ATTITUDE"]
    except (KeyError, TypeError) as exc:
        raise ValueError("selected PX4 pose messages are missing") from exc

    observed_at = now or dt.datetime.now(dt.timezone.utc)
    if observed_at.tzinfo is None:
        raise ValueError("pose observation time must include a timezone")
    for name, entry in (("position", position), ("quaternion", attitude), ("Euler attitude", euler)):
        try:
            updated = dt.datetime.fromisoformat(entry["status"]["time"]["last_update"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{name} update timestamp is missing or invalid") from exc
        if updated.tzinfo is None:
            raise ValueError(f"{name} update timestamp must include a timezone")
        age = (observed_at - updated).total_seconds()
        if age < -0.1 or age > max_age_s:
            raise ValueError(f"{name} pose is stale or from a different clock")
    position_message = position["message"]
    attitude_message = attitude["message"]
    euler_message = euler["message"]
    if (position_message.get("type") != "LOCAL_POSITION_NED"
            or attitude_message.get("type") != "ATTITUDE_QUATERNION"
            or euler_message.get("type") != "ATTITUDE"):
        raise ValueError("PX4 pose message types do not match")
    boot_times = [int(message["time_boot_ms"]) for message in (
        position_message, attitude_message, euler_message
    )]
    if max(boot_times) - min(boot_times) > 250:
        raise ValueError("PX4 position and attitude observations are not synchronized")
    position_ned = _finite_vector(
        (position_message["x"], position_message["y"], position_message["z"]),
        3, "PX4 position",
    )
    quaternion = _finite_vector(
        tuple(attitude_message[f"q{index}"] for index in range(1, 5)),
        4, "PX4 attitude quaternion",
    )
    w, x, y, z = quaternion
    norm = math.sqrt(sum(value * value for value in quaternion))
    if norm < 1e-9:
        raise ValueError("PX4 attitude quaternion has zero length")
    w, x, y, z = (value / norm for value in (w, x, y, z))
    quaternion_yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    reported_yaw = _finite_vector((euler_message["yaw"],), 1, "PX4 Euler yaw")[0]
    yaw_difference = math.atan2(
        math.sin(quaternion_yaw - reported_yaw),
        math.cos(quaternion_yaw - reported_yaw),
    )
    if abs(yaw_difference) > math.radians(10):
        raise ValueError("PX4 quaternion and Euler yaw disagree; check frame convention")
    return position_ned, quaternion


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vehicle-ned", nargs=3, type=float, metavar=("N", "E", "D"))
    parser.add_argument("--target-ned", nargs=3, type=float, required=True, metavar=("N", "E", "D"))
    parser.add_argument("--body-to-ned-quaternion", nargs=4, type=float, metavar=("W", "X", "Y", "Z"))
    parser.add_argument("--mavlink2rest-json", type=Path)
    parser.add_argument("--system-id", type=int)
    parser.add_argument("--mount-type", choices=("HORIZONTAL", "VERTICAL"), required=True)
    args = parser.parse_args()
    if args.mavlink2rest_json is not None:
        if args.vehicle_ned is not None or args.body_to_ned_quaternion is not None or args.system_id is None:
            parser.error("--mavlink2rest-json requires --system-id and excludes manual pose fields")
        vehicle, quaternion = pose_from_mavlink2rest(
            json.loads(args.mavlink2rest_json.read_text(encoding="utf-8")), args.system_id,
        )
    else:
        if args.vehicle_ned is None or args.body_to_ned_quaternion is None or args.system_id is not None:
            parser.error("manual pose requires --vehicle-ned and --body-to-ned-quaternion")
        vehicle, quaternion = args.vehicle_ned, args.body_to_ned_quaternion
    angles = camera_angles_for_world_target(
        vehicle, args.target_ned, quaternion,
        args.mount_type,
    )
    print(json.dumps({
        "injection_id": "sih_world_target",
        "source": "sih_world_target_fixture",
        "data_type": "gimbal_angles",
        "tracker_id": "sih_world_target_fixture",
        "angular": angles,
        "tracking_active": True,
        "usable_for_following": True,
        "has_output": True,
    }))


if __name__ == "__main__":
    main()
