#!/usr/bin/env python3
"""Generate a deterministic visual proof of the gimbal guidance state policy.

This is a software/classifier proof, not a camera or SIH result. It exercises
the same policy class used by the Vector follower and writes a CSV, a 2D state
trace, and an optional animated 3D ray plot for review.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from classes.gimbal_guidance import (
    GimbalGuidanceCapabilities,
    GimbalGuidanceClassifier,
    GimbalGuidancePolicy,
    GuidanceState,
)


class Ray:
    def __init__(self, x: float, y: float, z: float):
        self.x, self.y, self.z = x, y, z


def scenario_ray(t: float) -> Ray:
    """Return a smooth known ray sequence crossing vertical and rearward states."""
    if t < 1.0:
        bearing, depression = 0.0, 0.0
    elif t < 2.0:
        bearing, depression = 0.0, 90.0
    elif t < 3.0:
        bearing, depression = 0.0, 25.0
    elif t < 4.1:
        bearing, depression = 180.0, 0.0
    elif t < 5.5:
        bearing, depression = 75.0, 0.0
    else:
        bearing, depression = 20.0, -10.0
    azimuth = math.radians(bearing)
    down = math.sin(math.radians(depression))
    horizontal = math.cos(math.radians(depression))
    return Ray(horizontal * math.cos(azimuth), horizontal * math.sin(azimuth), down)


def run_trace(rate_hz: float = 20.0, requested_speed: float = 6.0):
    policy = GimbalGuidancePolicy()
    capabilities = GimbalGuidanceCapabilities(
        known=True,
        supports_vertical=True,
        supports_reverse=True,
        supports_yaw_fallback=True,
        azimuth_limits_deg=(-180.0, 180.0),
        depression_limits_deg=(-90.0, 90.0),
    )
    classifier = GimbalGuidanceClassifier(policy, capabilities, clock=lambda: 0.0)
    records = []
    step = 1.0 / rate_hz
    t = 0.0
    while t <= 6.5 + step / 2:
        ray = scenario_ray(t)
        decision = classifier.update(ray, now=t)
        if decision.state == GuidanceState.VERTICAL:
            sign = -1.0 if ray.z < 0.0 else 1.0
            command = (0.0, 0.0, requested_speed * sign)
        elif decision.state in (GuidanceState.YAW_FIRST, GuidanceState.UNREACHABLE):
            command = (0.0, 0.0, 0.0)
        else:
            magnitude = math.sqrt(ray.x * ray.x + ray.y * ray.y + ray.z * ray.z)
            command = tuple(requested_speed * component / magnitude for component in (ray.x, ray.y, ray.z))
        yaw = 0.0 if decision.bearing_deg is None else 0.5 * decision.bearing_deg
        records.append({
            "time_s": t,
            "ray_forward": ray.x,
            "ray_right": ray.y,
            "ray_down": ray.z,
            "state": decision.state.value,
            "bearing_deg": "" if decision.bearing_deg is None else decision.bearing_deg,
            "transition_pending": decision.transition_pending,
            "reason": decision.reason,
            "command_forward_m_s": command[0],
            "command_right_m_s": command[1],
            "command_down_m_s": command[2],
            "effective_speed_m_s": math.sqrt(sum(component * component for component in command)),
            "yaw_rate_deg_s": yaw if decision.state == GuidanceState.YAW_FIRST else 0.0,
        })
        t += step
    return policy, records


def write_outputs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    policy, records = run_trace()
    csv_path = output_dir / "gimbal-guidance-proof.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)

    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    state_colors = {
        "forward": "#4c78a8",
        "vertical": "#59a14f",
        "rearward_grace": "#f28e2b",
        "yaw_first": "#e15759",
        "unreachable": "#7f7f7f",
    }
    times = [row["time_s"] for row in records]
    speed = [row["effective_speed_m_s"] for row in records]
    down = [row["command_down_m_s"] for row in records]
    states = [row["state"] for row in records]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True, constrained_layout=True)
    axes[0].plot(times, speed, color="#333333", label="effective translation speed")
    axes[0].plot(times, down, color="#59a14f", label="down (+) / up (-) command")
    axes[0].set_ylabel("m/s")
    axes[0].legend(loc="upper right")
    for left, right, state in zip(times[:-1], times[1:], states[:-1]):
        axes[0].axvspan(left, right, color=state_colors[state], alpha=0.10)
    axes[1].step(times, [list(state_colors).index(state) for state in states], where="post", color="#222222")
    axes[1].set_yticks(range(len(state_colors)), list(state_colors))
    axes[1].set_xlabel("time (s)")
    axes[1].set_ylabel("classifier state")
    axes[1].grid(axis="x", alpha=0.25)
    fig.suptitle("GM Velocity Vector guidance policy proof (deterministic rays)")
    fig.savefig(output_dir / "gimbal-guidance-proof.png", dpi=150)
    plt.close(fig)

    fig = plt.figure(figsize=(8, 8))
    axis = fig.add_subplot(111, projection="3d")
    axis.set_xlim(-1.1, 1.1)
    axis.set_ylim(-1.1, 1.1)
    axis.set_zlim(-1.1, 1.1)
    axis.set_xlabel("forward")
    axis.set_ylabel("right")
    axis.set_zlabel("down")
    axis.set_title("Displayed body-ray state and command direction")
    ray_line, = axis.plot([], [], [], color="#4c78a8", linewidth=3)
    command_line, = axis.plot([], [], [], color="#e15759", linewidth=3)
    label = axis.text2D(0.02, 0.95, "", transform=axis.transAxes)

    command_scale = 6.0

    def frame(index):
        row = records[index]
        ray_line.set_data_3d([0, row["ray_forward"]], [0, row["ray_right"]], [0, row["ray_down"]])
        command_line.set_data_3d(
            [0, row["command_forward_m_s"] / command_scale],
            [0, row["command_right_m_s"] / command_scale],
            [0, row["command_down_m_s"] / command_scale],
        )
        label.set_text(f"t={row['time_s']:.2f}s  {row['state']}  {row['reason']}")
        return ray_line, command_line, label

    animation = FuncAnimation(fig, frame, frames=len(records), interval=50, blit=False)
    try:
        animation.save(output_dir / "gimbal-guidance-proof.gif", writer="pillow", fps=20)
    except (RuntimeError, ValueError) as exc:
        (output_dir / "animation-unavailable.txt").write_text(
            f"GIF writer unavailable: {exc}\nThe PNG and CSV remain valid.\n", encoding="utf-8"
        )
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    write_outputs(args.output_dir)
    print(f"Wrote deterministic guidance proof to {args.output_dir}")


if __name__ == "__main__":
    main()
