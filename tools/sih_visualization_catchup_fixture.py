#!/usr/bin/env python3
"""Create deterministic, synthetic catch-up evidence for the SIH visualizer.

This fixture is a report test only. It creates an observed-pose trace from a
simple bounded integrator so the report can show whether a faster requested
command closes the target range. It never contacts PX4, MAVLink, a camera, or
an action endpoint.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from classes.sih_visualization import VisualizationScenario  # noqa: E402


def _unit(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 1e-9:
        return (0.0, 0.0, 0.0)
    return tuple(value / norm for value in vector)


def _difference(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(a - b for a, b in zip(left, right))


def _wrap_angle(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def _yaw_quaternion(yaw: float) -> list[float]:
    return [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)]


def write_catchup_evidence(scenario: VisualizationScenario, output: Path) -> dict[str, float | int | str]:
    is_2d = scenario.follower_profile.startswith("mc_")
    is_attitude = scenario.command_contract == "attitude_rate"
    requested_speed = scenario.requested_speed
    if requested_speed is None and is_attitude:
        requested_speed = 2.0 if scenario.airframe == "multicopter" else 15.0
    if requested_speed is None and is_2d:
        if scenario.follower_profile == "mc_velocity_chase" and scenario.lateral_guidance_mode == "coordinated_turn":
            requested_speed = scenario.limits.get("velocity_forward", 2.0)
        else:
            requested_speed = math.hypot(
                scenario.limits.get("velocity_forward", 2.0),
                scenario.limits.get("velocity_right", 1.0),
            )
    if requested_speed is None or requested_speed <= 0.0:
        raise ValueError("catch-up scenario requires a positive speed or 2D velocity limits")
    if len(scenario.target_waypoints) < 2:
        raise ValueError("catch-up scenario requires moving target waypoints")
    output.mkdir(parents=True, exist_ok=True)
    for relative in ("px4", "trace"):
        (output / relative).mkdir(parents=True, exist_ok=True)
    for relative in (
        "px4/pose_trace.jsonl",
        "trace/target_truth.jsonl",
        "trace/tracker_command_trace.jsonl",
        "trace/offboard_publish_trace.jsonl",
        "trace/follower_state.jsonl",
    ):
        (output / relative).write_text("", encoding="utf-8")
    dt = 1.0 / scenario.rate_hz
    end_time = scenario.target_waypoints[-1].time_s
    position = scenario.initial_vehicle_ned
    hold_duration_s = 1.0
    yaw = 0.0
    rows: list[dict[str, object]] = []
    ranges: list[float] = []
    target_speeds: list[float] = []
    previous_target = scenario.target_at(0.0)
    for index in range(round(end_time / dt) + 1):
        timestamp = round(index * dt, 6)
        target = scenario.target_at(timestamp)
        if target is None:
            break
        target_delta = _difference(target, previous_target) if previous_target else (0.0, 0.0, 0.0)
        target_velocity = tuple(value / dt for value in target_delta)
        if previous_target is not None:
            target_speeds.append(math.sqrt(sum(value * value for value in target_velocity)))
        active_fault = next(
            (
                fault for fault in scenario.faults
                if float(fault.get("at_s", math.inf)) <= timestamp < float(fault.get("at_s", math.inf)) + float(fault.get("duration_s", 0.0))
            ),
            None,
        )
        fault_kind = str(active_fault.get("kind")) if active_fault else None
        yaw_rate_deg = 0.0
        if timestamp < hold_duration_s:
            distance = math.sqrt(sum((target[axis] - position[axis]) ** 2 for axis in range(3)))
            command = (0.0, 0.0, 0.0)
            state = "hold"
            reason = "hold_before_offboard"
            body_command = (0.0, 0.0, 0.0)
        elif fault_kind in ("target_loss", "delayed_observation"):
            distance = math.sqrt(sum((target[axis] - position[axis]) ** 2 for axis in range(3)))
            command = (0.0, 0.0, 0.0)
            state = "target_lost" if fault_kind == "target_loss" else "reacquiring"
            reason = fault_kind
            body_command = (0.0, 0.0, 0.0)
        else:
            delta = _difference(target, position)
            distance = math.sqrt(sum(value * value for value in delta))
            direction = _unit(delta)
            command_speed = min(requested_speed, distance / dt) if distance > 1e-9 else math.sqrt(sum(value * value for value in target_velocity))
            if is_2d and not is_attitude:
                direction = (direction[0], direction[1], 0.0)
                horizontal_distance = math.hypot(delta[0], delta[1])
                horizontal_unit = _unit((delta[0], delta[1], 0.0))
                command_speed = min(requested_speed, horizontal_distance / dt) if horizontal_distance > 1e-9 else 0.0
                command = tuple(part * command_speed for part in horizontal_unit)
                if scenario.follower_profile == "mc_velocity_position":
                    forward_limit = scenario.limits.get("velocity_forward", math.inf)
                    right_limit = scenario.limits.get("velocity_right", math.inf)
                    command = (
                        max(-forward_limit, min(forward_limit, command[0])),
                        max(-right_limit, min(right_limit, command[1])),
                        0.0,
                    )
                    command_speed = math.hypot(command[0], command[1])
            else:
                command = tuple(direction_part * command_speed for direction_part in direction)
            if distance <= 1e-9:
                command = target_velocity if not is_2d else (0.0, 0.0, 0.0)
            horizontal = math.hypot(delta[0], delta[1])
            bearing = math.atan2(delta[1], delta[0]) if horizontal > 1e-9 else yaw
            yaw_error = _wrap_angle(bearing - yaw)
            yaw_limit = scenario.limits.get("rate_yaw", 45.0)
            yaw_rate_deg = 0.0 if (
                is_2d
                and scenario.follower_profile == "mc_velocity_position"
                and scenario.lateral_guidance_mode == "sideslip"
            ) else max(-yaw_limit, min(yaw_limit, math.degrees(yaw_error) * 1.5))
            yaw = _wrap_angle(yaw + math.radians(yaw_rate_deg) * dt)
            horizontal_speed = command_speed * horizontal / max(distance, 1e-9)
            if is_attitude:
                # The fixture keeps a simple observed-pose integrator for
                # visualization, while exposing the actual attitude-rate
                # command contract instead of inventing body velocity fields.
                command = tuple(direction_part * command_speed for direction_part in direction)
                body_command = (0.0, 0.0, 0.0)
                yaw_rate_deg = max(-yaw_limit, min(yaw_limit, math.degrees(yaw_error) * 0.8))
            elif is_2d and scenario.follower_profile == "mc_velocity_chase" and scenario.lateral_guidance_mode == "coordinated_turn":
                # Coordinated-turn chase keeps forward velocity non-negative;
                # yaw rotates that body-forward command into the NED trace.
                body_command = (command_speed, 0.0, 0.0)
                command = (command_speed * math.cos(yaw), command_speed * math.sin(yaw), 0.0)
            elif is_2d and scenario.follower_profile == "mc_velocity_position":
                body_command = (command[0], command[1], 0.0)
            elif scenario.lateral_guidance_mode == "coordinated_turn":
                body_command = (horizontal_speed * math.cos(_wrap_angle(bearing - yaw)), 0.0, command[2])
            else:
                body_command = (
                    horizontal_speed * math.cos(yaw) * direction[0] + horizontal_speed * math.sin(yaw) * direction[1],
                    -horizontal_speed * math.sin(yaw) * direction[0] + horizontal_speed * math.cos(yaw) * direction[1],
                    command[2],
                )
            state = "target_caught" if distance <= max(0.25, math.sqrt(3.0) * requested_speed * dt) else ("vertical" if scenario.mount_type == "VERTICAL" else "forward")
            reason = fault_kind if fault_kind == "retarget" else ("offboard_started" if abs(timestamp - hold_duration_s) < dt / 2 else "synthetic_catchup")
            position = tuple(position[axis] + command[axis] * dt for axis in range(3))
            if is_2d and not is_attitude:
                position = (position[0], position[1], scenario.initial_vehicle_ned[2])
            observed_distance = math.sqrt(sum((target[axis] - position[axis]) ** 2 for axis in range(3)))
            if state in {"forward", "vertical"} and observed_distance <= max(0.25, math.sqrt(3.0) * requested_speed * dt):
                state = "target_caught"
        ranges.append(math.sqrt(sum((target[axis] - position[axis]) ** 2 for axis in range(3))))
        if is_attitude:
            fields = {
                "rollspeed_deg_s": max(-45.0, min(45.0, body_command[1] * 5.0)),
                "pitchspeed_deg_s": max(-30.0, min(30.0, -body_command[2] * 5.0)),
                "yawspeed_deg_s": yaw_rate_deg,
                "thrust": 0.6,
            }
        else:
            fields = {
                "vel_body_fwd": body_command[0],
                "vel_body_right": body_command[1],
                "vel_body_down": body_command[2],
                "yawspeed_deg_s": yaw_rate_deg,
            }
        tracker = {
            "record_type": "tracker_command",
            "timestamp": timestamp,
            "tracker_output": {"metadata": {"guidance_state": state}},
            "command_intent": {"reason": reason, "fields": fields},
            "requested_speed": scenario.requested_speed,
        }
        rows.append(tracker)
        (output / "trace" / "tracker_command_trace.jsonl").open("a", encoding="utf-8").write(json.dumps(tracker) + "\n")
        publish = {"record_type": "offboard_publish", "timestamp": timestamp, "publish_success": True}
        (output / "trace" / "offboard_publish_trace.jsonl").open("a", encoding="utf-8").write(json.dumps(publish) + "\n")
        state_record = {"timestamp": timestamp, "state": state}
        (output / "trace" / "follower_state.jsonl").open("a", encoding="utf-8").write(json.dumps(state_record) + "\n")
        pose = {"timestamp": timestamp, "vehicle_ned": position, "vehicle_quaternion": _yaw_quaternion(yaw)}
        (output / "px4" / "pose_trace.jsonl").open("a", encoding="utf-8").write(json.dumps(pose) + "\n")
        target_record = {"timestamp": timestamp, "target_ned": target}
        (output / "trace" / "target_truth.jsonl").open("a", encoding="utf-8").write(json.dumps(target_record) + "\n")
        previous_target = target
    result = {
        "synthetic": True,
        "requested_speed_m_s": requested_speed,
        "target_speed_m_s": max(target_speeds) if target_speeds else 0.0,
        "range_start_m": ranges[0],
        "range_end_m": ranges[-1],
        "range_min_m": min(ranges),
        "samples": len(rows),
    }
    (output / "fixture_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenario = VisualizationScenario.from_yaml(args.scenario)
    result = write_catchup_evidence(scenario, args.output)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
