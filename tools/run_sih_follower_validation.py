#!/usr/bin/env python3
"""Run or validate a follower's isolated PX4-SIH qualification evidence.

The default operation is a side-effect-free contract check. ``--execute`` is
an explicit opt-in and delegates to the reviewed, loopback-only QGC SIH
harness when that checkout is available. The visualizer remains read-only:
it never starts following, sends a target, or integrates a command into a
vehicle pose. A run is accepted only when the evidence contains independent
target truth, PX4-observed pose, and successful publication records.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from classes.sih_visualization import (  # noqa: E402
    VisualizationScenario,
    VisualizationValidationError,
    analyze_timeline,
    build_timeline,
    load_evidence,
)
try:
    from tools.sih_visualizer import build_html, write_csv, write_png  # noqa: E402
except ModuleNotFoundError:
    from sih_visualizer import build_html, write_csv, write_png  # noqa: E402


PROFILE_SCENARIOS = {
    "mc_velocity_chase": "camera-chase-2d.yaml",
    "mc_velocity_ground": "camera-ground-2d.yaml",
    "mc_velocity_distance": "camera-distance-2d.yaml",
    "mc_velocity_position": "camera-position-2d.yaml",
    "mc_attitude_rate": "mc-attitude-rate.yaml",
    "fw_attitude_rate": "fw-attitude-rate.yaml",
    "gm_velocity_chase": "gimbal-chase-horizontal.yaml",
    "gm_velocity_vector": "gimbal-vector-combined-catchup.yaml",
}

NORMAL_PROFILES = set(PROFILE_SCENARIOS) - {"gm_velocity_chase", "gm_velocity_vector"}


def scenario_path(profile: str) -> Path:
    try:
        return PROJECT_ROOT / "tools" / "sih_visualization_scenarios" / PROFILE_SCENARIOS[profile]
    except KeyError as exc:
        raise VisualizationValidationError(f"unsupported follower profile: {profile}") from exc


def validate_scenario(scenario: VisualizationScenario) -> dict[str, Any]:
    if scenario.evidence_provenance != "synthetic_fixture":
        raise VisualizationValidationError(
            "checked-in scenarios must remain synthetic until an imported PX4 trace is present"
        )
    if not scenario.stable_flight:
        raise VisualizationValidationError("scenario must declare a stable_flight gate")
    if not scenario.acceptance:
        raise VisualizationValidationError("scenario must declare acceptance requirements")
    return {
        "profile": scenario.follower_profile,
        "purpose": scenario.follower_purpose,
        "airframe": scenario.airframe,
        "simulator_model": "sihsim_airplane" if scenario.airframe == "fixed_wing" else "sihsim_quadx",
        "input_contract": scenario.input_contract,
        "command_contract": scenario.command_contract,
        "mount_type": scenario.mount_type,
        "altitude_control": scenario.altitude_control,
        "speed_source_policy": scenario.speed_source_policy,
        "stable_flight": scenario.stable_flight,
        "acceptance": list(scenario.acceptance),
        "evidence_provenance": scenario.evidence_provenance,
        "claims": "contract only until independent PX4 pose and publication evidence are imported",
    }


def _copy_jsonl(source: Path, destination: Path, transform) -> int:
    if not source.is_file():
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with source.open(encoding="utf-8") as input_stream, destination.open("w", encoding="utf-8") as output_stream:
        for line in input_stream:
            if not line.strip():
                continue
            record = transform(json.loads(line))
            if record is None:
                continue
            output_stream.write(json.dumps(record, sort_keys=True) + "\n")
            count += 1
    return count


def normalize_harness_evidence(root: Path) -> dict[str, int]:
    """Normalize the existing isolated harness names without inventing pose."""
    trace = root / "trace"
    pose = root / "px4" / "pose_trace.jsonl"
    trace.mkdir(parents=True, exist_ok=True)
    pose.parent.mkdir(parents=True, exist_ok=True)
    observations = []
    observations_path = root / "observations.jsonl"
    if observations_path.is_file():
        observations = [json.loads(line) for line in observations_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    observation_by_time = {
        round(float(row["timestamp"]), 3): row for row in observations if row.get("timestamp") is not None
    }

    tracker_count = _copy_jsonl(
        root / "tracker.jsonl",
        trace / "tracker_command_trace.jsonl",
        lambda row: {
            "record_type": "tracker_command",
            "timestamp": row["timestamp"],
            "target_ned": (observation_by_time.get(round(float(row["timestamp"]), 3)) or {}).get("target_ned"),
            "tracker_output": {"metadata": row.get("continuity", {})},
            "command_intent": row.get("command_intent") or {
                "fields": ((row.get("continuity") or {}).get("effective_command_fields") or {}),
                "reason": "sih_dispatch",
            },
        },
    )
    publish_count = _copy_jsonl(
        root / "publish.jsonl",
        trace / "offboard_publish_trace.jsonl",
        lambda row: row if row.get("record_type") == "offboard_publish" else {
            **row,
            "record_type": "offboard_publish",
            "publish_success": bool(row.get("publish_status", {}).get("last_publish_success", False)),
        },
    )
    state_count = _copy_jsonl(
        root / "observations.jsonl",
        trace / "follower_state.jsonl",
        lambda row: {"timestamp": row["timestamp"], **(row.get("continuity") or {})},
    )
    target_count = _copy_jsonl(
        root / "target_truth.jsonl",
        trace / "target_truth.jsonl",
        lambda row: {"timestamp": row["timestamp"], "target_ned": row.get("target_ned")},
    )
    if not pose.is_file() or pose.stat().st_size == 0:
        pose_count = _copy_jsonl(
            root / "observations.jsonl",
            pose,
            lambda row: {
                "timestamp": row["timestamp"],
                "vehicle_ned": row.get("position_ned"),
                "vehicle_quaternion": row.get("body_to_ned_quaternion") or row.get("quaternion"),
            }
            if row.get("position_ned") is not None
            and (row.get("body_to_ned_quaternion") is not None or row.get("quaternion") is not None)
            else None,
        )
    else:
        pose_count = sum(1 for _ in pose.open(encoding="utf-8") if _.strip())
    return {
        "tracker": tracker_count,
        "published": publish_count,
        "state": state_count,
        "target": target_count,
        "pose": pose_count,
    }


def validate_px4_evidence(root: Path, scenario: VisualizationScenario) -> dict[str, Any]:
    counts = normalize_harness_evidence(root)
    evidence = load_evidence(root)
    if not evidence["target"]:
        raise VisualizationValidationError(
            "PX4 acceptance requires an independent trace/target_truth.jsonl; command records alone are insufficient"
        )
    if not evidence["pose"]:
        raise VisualizationValidationError("PX4 acceptance requires a non-empty PX4 pose trace")
    if not evidence["published"] or not any(row.get("publish_success") is True for row in evidence["published"]):
        raise VisualizationValidationError("PX4 acceptance requires successful Offboard publication records")
    samples = build_timeline(scenario, evidence)
    summary = analyze_timeline(scenario, samples)
    summary["evidence_kind"] = "px4_sih"
    summary["evidence_counts"] = counts
    summary["claims"] = "PX4-observed pose, independent target truth, and publication trace only"
    if summary.get("stale_after_fresh_samples", 0) or any(
        flag.get("type") in {"pose_unavailable", "command_or_pose_gap"}
        for flag in summary.get("flags", [])
    ):
        raise VisualizationValidationError("PX4 evidence contains stale pose or command gaps")
    return summary


def write_visualization(root: Path, scenario: VisualizationScenario, summary: dict[str, Any]) -> Path:
    evidence = load_evidence(root)
    samples = build_timeline(scenario, evidence)
    output = root / "visualization"
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "trace.json").write_text(
        json.dumps([sample.to_dict() for sample in samples], indent=2) + "\n", encoding="utf-8"
    )
    write_csv(output / "trace.csv", samples)
    (output / "index.html").write_text(build_html(scenario, samples, summary), encoding="utf-8")
    write_png(output / "summary.png", scenario, samples)
    return output


def run_external(args: argparse.Namespace, scenario: VisualizationScenario) -> None:
    qgc_root = args.qgc_repo.resolve()
    if not qgc_root.is_dir():
        raise SystemExit(f"QGC validation checkout is missing: {qgc_root}")
    if scenario.follower_profile in NORMAL_PROFILES:
        driver = qgc_root / "custom-pixeagle" / "validation" / "run-normal-sih-evidence.py"
        command = ["--follower", scenario.follower_profile]
    else:
        driver = qgc_root / "custom-pixeagle" / "validation" / "run-gimbal-sih-evidence.py"
        command = ["--follower", scenario.follower_profile, "--mount", scenario.mount_type]
    if not driver.is_file():
        raise SystemExit(f"Reviewed SIH driver is missing: {driver}")
    command = [sys.executable, str(driver), "--execute", "--output", str(args.evidence_root), *command]
    if args.enable_altitude_control or scenario.altitude_control:
        command.append("--enable-altitude-control")
    command.extend(["--backend-repo", str(args.backend_repo), "--python", str(args.python), "--bin-dir", str(args.bin_dir)])
    if args.opencv_lib:
        command.extend(["--opencv-lib", str(args.opencv_lib)])
    subprocess.run(command, check=True, cwd=qgc_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--follower", choices=sorted(PROFILE_SCENARIOS), required=True)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--enable-altitude-control", action="store_true")
    parser.add_argument("--qgc-repo", type=Path, default=Path.home() / "qgroundcontrol-pixeagle")
    parser.add_argument("--backend-repo", type=Path, default=Path.home() / "PixEagle-qgc-integration")
    parser.add_argument("--python", type=Path, default=Path.home() / ".cache/pixeagle-qgc-baseline/slice-3b-2026-09-22/runtime/full-ai-venv/bin/python")
    parser.add_argument("--bin-dir", type=Path, default=Path.home() / "PixEagle/bin")
    parser.add_argument("--opencv-lib", type=Path, default=Path.home() / "PixEagle/.venv/lib")
    args = parser.parse_args()
    scenario = VisualizationScenario.from_yaml(scenario_path(args.follower))
    plan = validate_scenario(scenario)
    if args.execute:
        if args.evidence_root is None:
            parser.error("--execute requires --evidence-root")
        if args.evidence_root.exists():
            parser.error("evidence root already exists; use a new run directory")
        run_external(args, scenario)
        args.evidence_root.mkdir(parents=True, exist_ok=True)
        (args.evidence_root / "scenario.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        summary = validate_px4_evidence(args.evidence_root, scenario)
        (args.evidence_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        write_visualization(args.evidence_root, scenario, summary)
        print(json.dumps({"passed": True, "evidence_root": str(args.evidence_root), "summary": summary}, indent=2))
        return 0
    print(json.dumps({"passed": True, "mode": "dry_run", "scenario": plan}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
