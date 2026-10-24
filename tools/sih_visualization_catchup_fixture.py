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


def write_catchup_evidence(scenario: VisualizationScenario, output: Path) -> dict[str, float | int | str]:
    if scenario.requested_speed is None or scenario.requested_speed <= 0.0:
        raise ValueError("catch-up scenario requires a positive follower.requested_speed")
    if len(scenario.target_waypoints) < 2:
        raise ValueError("catch-up scenario requires moving target waypoints")
    output.mkdir(parents=True, exist_ok=True)
    for relative in ("px4", "trace"):
        (output / relative).mkdir(parents=True, exist_ok=True)
    dt = 1.0 / scenario.rate_hz
    end_time = scenario.target_waypoints[-1].time_s
    position = (0.0, 0.0, 0.0)
    rows: list[dict[str, object]] = []
    ranges: list[float] = []
    previous_target = scenario.target_at(0.0)
    for index in range(round(end_time / dt) + 1):
        timestamp = round(index * dt, 6)
        target = scenario.target_at(timestamp)
        if target is None:
            break
        delta = _difference(target, position)
        distance = math.sqrt(sum(value * value for value in delta))
        direction = _unit(delta)
        target_delta = _difference(target, previous_target) if previous_target else (0.0, 0.0, 0.0)
        target_velocity = tuple(value / dt for value in target_delta)
        command_speed = min(scenario.requested_speed, distance / dt) if distance > 1e-9 else math.sqrt(sum(value * value for value in target_velocity))
        command = tuple(direction_part * command_speed for direction_part in direction)
        if distance <= 1e-9:
            command = target_velocity
        position = tuple(position[axis] + command[axis] * dt for axis in range(3))
        ranges.append(math.sqrt(sum((target[axis] - position[axis]) ** 2 for axis in range(3))))
        state = "target_caught" if ranges[-1] <= max(0.25, math.sqrt(3.0) * scenario.requested_speed * dt) else ("vertical" if scenario.mount_type == "VERTICAL" else "forward")
        fields = {
            "vel_body_fwd": command[0],
            "vel_body_right": command[1],
            "vel_body_down": command[2],
            "yawspeed_deg_s": 0.0,
        }
        tracker = {
            "record_type": "tracker_command",
            "timestamp": timestamp,
            "tracker_output": {"metadata": {"guidance_state": state}},
            "command_intent": {"reason": "synthetic_catchup", "fields": fields},
            "requested_speed": scenario.requested_speed,
        }
        rows.append(tracker)
        (output / "trace" / "tracker_command_trace.jsonl").open("a", encoding="utf-8").write(json.dumps(tracker) + "\n")
        publish = {"record_type": "offboard_publish", "timestamp": timestamp, "publish_success": True}
        (output / "trace" / "offboard_publish_trace.jsonl").open("a", encoding="utf-8").write(json.dumps(publish) + "\n")
        state_record = {"timestamp": timestamp, "state": "following"}
        (output / "trace" / "follower_state.jsonl").open("a", encoding="utf-8").write(json.dumps(state_record) + "\n")
        pose = {"timestamp": timestamp, "vehicle_ned": position, "vehicle_quaternion": [1.0, 0.0, 0.0, 0.0]}
        (output / "px4" / "pose_trace.jsonl").open("a", encoding="utf-8").write(json.dumps(pose) + "\n")
        target_record = {"timestamp": timestamp, "target_ned": target}
        (output / "trace" / "target_truth.jsonl").open("a", encoding="utf-8").write(json.dumps(target_record) + "\n")
        previous_target = target
    result = {
        "synthetic": True,
        "requested_speed_m_s": scenario.requested_speed,
        "target_speed_m_s": math.sqrt(sum(value * value for value in target_velocity)),
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
