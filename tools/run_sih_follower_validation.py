#!/usr/bin/env python3
"""Run or validate a follower's isolated PX4-SIH qualification evidence.

The default operation is a side-effect-free contract check. ``--execute`` is
an explicit opt-in; ``--validate-existing`` reads a captured run and refreshes
only derived reports. MC profiles use the PixEagle-owned world-target worker;
the legacy direct-rate FW driver remains separate. The visualizer remains read-only:
it never starts following, sends a target, or integrates a command into a
vehicle pose. A run is accepted only when the evidence contains independent
target truth, PX4-observed pose, and successful publication records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from classes.sih_visualization import (  # noqa: E402
    VisualizationScenario,
    VisualizationValidationError,
    analyze_timeline,
    build_timeline,
    load_evidence,
    read_jsonl,
)
try:
    from tools.sih_visualizer import build_html, write_csv, write_png  # noqa: E402
except ModuleNotFoundError:
    from sih_visualizer import build_html, write_csv, write_png  # noqa: E402
from tools.fixed_camera_world_target import mc_input_family


PROFILE_SCENARIOS = {
    "mc_velocity_chase": "mc_velocity_chase-qualification.yaml",
    "mc_velocity_ground": "mc_velocity_ground-qualification.yaml",
    "mc_velocity_distance": "mc_velocity_distance-qualification.yaml",
    "mc_velocity_position": "mc_velocity_position-qualification.yaml",
    "mc_attitude_rate": "mc_attitude_rate-qualification.yaml",
    "fw_attitude_rate": "fw-attitude-rate.yaml",
    "gm_velocity_chase": "gimbal-chase-horizontal.yaml",
    "gm_velocity_vector": "gimbal-vector-combined-catchup.yaml",
}

MC_PROFILES = frozenset(profile for profile in PROFILE_SCENARIOS if mc_input_family(profile) == 'image')


def scenario_path(profile: str, altitude_control: bool = False) -> Path:
    if mc_input_family(profile) == 'angles':
        suffix = 'on' if altitude_control else 'off'
        return PROJECT_ROOT / 'tools/sih_visualization_scenarios' / f'{profile}-qualification-horizontal-{suffix}.yaml'
    try:
        name = PROFILE_SCENARIOS[profile]
    except KeyError as exc:
        raise VisualizationValidationError(f"unsupported follower profile: {profile}") from exc
    if altitude_control and profile in MC_PROFILES - {"mc_attitude_rate"}:
        name = f"{profile}-qualification-altitude.yaml"
    return PROJECT_ROOT / "tools" / "sih_visualization_scenarios" / name


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
    if destination.is_file():
        with destination.open(encoding="utf-8") as stream:
            return sum(bool(line.strip()) for line in stream)
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


def _evidence_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise VisualizationValidationError(f"native acceptance requires valid {path.name}") from exc
    if not isinstance(value, dict):
        raise VisualizationValidationError(f"native acceptance requires an object in {path.name}")
    return value


def _native_response_result(root: Path, scenario: VisualizationScenario, evidence) -> dict[str, Any]:
    result = _evidence_object(root / "result.json")
    manifest = _evidence_object(root / "manifest.json")
    if (result.get("passed") is not True or result.get("scope") != "native_guidance_component_only"
            or result.get("follower") != scenario.follower_profile
            or result.get("input_contract") != scenario.input_contract
            or result.get("application_startup_qualified") is not False):
        raise VisualizationValidationError("native component response/authority acceptance did not pass")
    if (manifest.get("evidence_kind") != "px4_observed_sih"
            or manifest.get("qualification") != "native_guidance_component"
            or manifest.get("application_startup_qualified") is not False
            or manifest.get("simulated_tracker_input") is not True
            or manifest.get("follower") != scenario.follower_profile
            or manifest.get("input_contract") != scenario.input_contract
            or manifest.get("mount") != scenario.mount_type
            or manifest.get("altitude_guidance") is not scenario.altitude_control):
        raise VisualizationValidationError("native manifest and scenario contracts differ")
    captured = root / "scenario.yaml"
    if not captured.is_file() or VisualizationScenario.from_yaml(captured) != scenario:
        raise VisualizationValidationError("native acceptance requires the matching captured scenario")
    required = {"range_decreased", "altitude_floor", "finite_observed_response", "no_publication_after_stop",
                "hold_confirmed", "no_publication_failure", "expected_handoff",
                "altitude_guidance_response" if scenario.altitude_control else "altitude_hold"}
    checks = result.get("response_checks")
    if not isinstance(checks, dict) or not required.issubset(checks) or any(value is not True for value in checks.values()):
        raise VisualizationValidationError("native response checks are missing or failed")
    handoff = result.get("handoff")
    if (not isinstance(handoff, dict) or handoff.get("executed") is not True
            or handoff.get("local_sender_quiesced") is not True
            or type(result.get("successful_publications")) is not int or result["successful_publications"] <= 0
            or type(result.get("failed_publications")) is not int or result["failed_publications"] != 0
            or any(row.get("publish_success") is False for row in evidence["published"])):
        raise VisualizationValidationError("native result contradicts publication or handoff evidence")
    configuration = manifest.get("configuration")
    for name in ("config.yaml", "config_schema.yaml", "follower_commands.yaml"):
        artifact = configuration.get(name) if isinstance(configuration, dict) else None
        path = root / name
        if (not isinstance(artifact, dict) or artifact.get("path") != name or not path.is_file()
                or artifact.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest()):
            raise VisualizationValidationError(f"native configuration checksum mismatch: {name}")
    return result


def validate_px4_evidence(root: Path, scenario: VisualizationScenario, *, normalize: bool = True) -> dict[str, Any]:
    """Validate observed response; normalize=False preserves captured raw files."""
    counts = normalize_harness_evidence(root) if normalize else None
    evidence = load_evidence(root)
    if counts is None:
        counts = {name: len(records) for name, records in evidence.items()}
    if not evidence["target"]:
        raise VisualizationValidationError(
            "PX4 acceptance requires an independent trace/target_truth.jsonl; command records alone are insufficient"
        )
    if not evidence["pose"]:
        raise VisualizationValidationError("PX4 acceptance requires a non-empty PX4 pose trace")
    if not evidence["published"] or not any(row.get("publish_success") is True for row in evidence["published"]):
        raise VisualizationValidationError("PX4 acceptance requires successful Offboard publication records")
    native = scenario.command_contract in {"fixed_wing_external", "vtol_external"}
    result = _native_response_result(root, scenario, evidence) if native else None
    if not native and mc_input_family(scenario.follower_profile) is not None:
        result = json.loads((root / "result.json").read_text(encoding="utf-8"))
        if (result.get("passed") is not True or result.get("scope") != "actual_mc_follower_component_only"
                or result.get("follower") != scenario.follower_profile):
            raise VisualizationValidationError("MC response/authority acceptance did not pass")
        if scenario.faults:
            import yaml
            from tools.mc_follower_sih import validate_retained_fault_outcome
            captured = yaml.safe_load((root / 'scenario.yaml').read_text())
            qualification = captured.get('qualification')
            if not isinstance(qualification, dict):
                raise VisualizationValidationError('captured_mc_fault_outcome_unproven')
            try:
                validate_retained_fault_outcome(scenario, result, evidence,
                    expected_handoff=qualification.get('expected_handoff'),
                    fault_events=read_jsonl(root / 'fault-events.jsonl'),
                    takeover_cleanup=(_evidence_object(root / 'takeover-cleanup.json')
                                      if (root / 'takeover-cleanup.json').exists() else None),
                    pre_cleanup=(_evidence_object(root / 'fault-outcome-before-cleanup.json')
                                 if (root / 'fault-outcome-before-cleanup.json').exists() else None),
                    mode_calls=(read_jsonl(root / 'sdk-mode-calls.jsonl')
                                if (root / 'sdk-mode-calls.jsonl').exists() else None))
            except ValueError as exc:
                raise VisualizationValidationError(str(exc)) from exc
    samples = build_timeline(scenario, evidence)
    summary = analyze_timeline(scenario, samples)
    if result is not None:
        summary["qualification_result"] = result
    summary["evidence_kind"] = "px4_sih"
    summary["evidence_counts"] = counts
    summary["claims"] = ("PX4-observed native guidance component with synthetic tracker input; "
                         "not HTTP/App startup, optical tracking or physical-aircraft qualification" if native else
                         "PX4-observed pose, independent target truth, and publication trace only")
    if native:
        summary["qualification_scope"] = result["scope"]
    if summary.get("stale_after_fresh_samples", 0) or any(
        flag.get("type") in {"pose_unavailable", "command_or_pose_gap", "publication_after_authority_release"}
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


def write_failed_visualization(root: Path, scenario: VisualizationScenario, failure: Exception) -> Path | None:
    """Render retained failed-run data without granting response acceptance."""
    captured = root / "scenario.yaml"
    if captured.is_file():
        scenario = VisualizationScenario.from_yaml(captured)
    evidence = load_evidence(root)
    if not evidence["pose"]:
        return None
    result_path = root / "result.json"
    try:
        result = _evidence_object(result_path)
    except VisualizationValidationError:
        result = {}
    result = {**result, "passed": False}
    result.setdefault("reason", str(failure))
    result["validation_failure"] = str(failure)
    summary = analyze_timeline(scenario, build_timeline(scenario, evidence))
    summary.update(evidence_kind="px4_sih", qualification_result=result)
    if scenario.command_contract in {"fixed_wing_external", "vtol_external"}:
        summary.update(qualification_scope="native_guidance_component_only",
                       claims="Retained failed native-component evidence; no response or physical-aircraft qualification")
    (root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return write_visualization(root, scenario, summary)


def run_external(args: argparse.Namespace, scenario: VisualizationScenario) -> None:
    if mc_input_family(scenario.follower_profile) is not None:
        from tools.mc_follower_sih import run_host
        run_host(args, args.scenario or scenario_path(args.follower, args.enable_altitude_control))
        return
    qgc_root = args.qgc_repo.resolve()
    if not qgc_root.is_dir():
        raise SystemExit(f"QGC validation checkout is missing: {qgc_root}")
    driver = qgc_root / "custom-pixeagle" / "validation" / "run-normal-sih-evidence.py"
    command = ["--follower", scenario.follower_profile]
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
    parser.add_argument("--follower", help="Required for dry-run/execute; must match the capture when validating existing evidence")
    parser.add_argument("--evidence-root", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--validate-existing", action="store_true", help="Read captured scenario and regenerate its validated report without running SIH")
    parser.add_argument("--enable-altitude-control", action="store_true")
    parser.add_argument("--scenario", type=Path, help="Explicit supported world-target YAML for this profile")
    parser.add_argument("--simulation-build-manifest", type=Path,
                        help="Verified source-build manifest for isolated MC SIH; omission retains compatibility baseline")
    parser.add_argument("--telemetry-source", choices=("mavlink2rest", "mavsdk"), default="mavlink2rest",
                        help="Stage the existing MC follower telemetry setting; independent evidence still uses REST")
    parser.add_argument("--qgc-repo", type=Path, default=Path.home() / "qgroundcontrol-pixeagle")
    parser.add_argument("--backend-repo", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--bin-dir", type=Path, default=PROJECT_ROOT / "bin")
    parser.add_argument("--opencv-lib", type=Path, default=PROJECT_ROOT / ".venv/lib")
    args = parser.parse_args()
    if args.validate_existing:
        if args.evidence_root is None or not args.evidence_root.is_dir():
            parser.error("--validate-existing requires --evidence-root pointing to an existing run directory")
        if (args.scenario is not None or args.enable_altitude_control or args.simulation_build_manifest is not None
                or args.telemetry_source != "mavlink2rest"):
            parser.error("--validate-existing uses the captured scenario; run/configuration overrides are unavailable")
        scenario = VisualizationScenario.from_yaml(args.evidence_root / "scenario.yaml")
        if args.follower is not None and args.follower != scenario.follower_profile:
            parser.error("Captured scenario profile differs from --follower")
        try:
            summary = validate_px4_evidence(args.evidence_root, scenario, normalize=False)
            (args.evidence_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            output = write_visualization(args.evidence_root, scenario, summary)
        except Exception as failure:
            try:
                write_failed_visualization(args.evidence_root, scenario, failure)
            except Exception as report_error:
                print(f"Failed-run visualization unavailable: {report_error}", file=sys.stderr)
            raise
        print(json.dumps({"passed": True, "mode": "validate_existing", "follower": scenario.follower_profile,
                          "evidence_root": str(args.evidence_root), "visualization": str(output)}, indent=2))
        return 0
    if args.follower is None:
        parser.error("--follower is required for dry-run or --execute")
    if args.follower not in PROFILE_SCENARIOS and mc_input_family(args.follower) is None:
        parser.error(f"Unsupported dry-run/execute follower: {args.follower}; use the native runner for native capture")
    selected_path = args.scenario or scenario_path(args.follower, args.enable_altitude_control)
    scenario = VisualizationScenario.from_yaml(selected_path)
    if scenario.follower_profile != args.follower:
        parser.error("Scenario profile differs from --follower")
    if mc_input_family(args.follower) is not None:
        from tools.fixed_camera_world_target import MCScenario
        MCScenario.from_yaml(selected_path)
        if args.enable_altitude_control and args.follower != "mc_attitude_rate" and not scenario.altitude_control:
            parser.error("--enable-altitude-control requires an altitude-enabled velocity scenario with vertical stimulus")
    elif args.scenario is not None:
        parser.error("Custom scenarios are supported by the MC runner only; use the native FW runner separately")
    if args.simulation_build_manifest is not None and mc_input_family(args.follower) is None:
        parser.error("--simulation-build-manifest is supported by the isolated MC runner only")
    if args.telemetry_source != "mavlink2rest" and mc_input_family(args.follower) is None:
        parser.error("--telemetry-source is supported by the isolated MC runner only")
    if args.execute and mc_input_family(args.follower) == 'angles' and args.simulation_build_manifest is None:
        parser.error('Gimbal MC renewal requires --simulation-build-manifest before execution')
    if args.enable_altitude_control:
        scenario = replace(scenario, altitude_control=True)
    plan = validate_scenario(scenario)
    if args.execute:
        if args.evidence_root is None:
            parser.error("--execute requires --evidence-root")
        if args.evidence_root.exists():
            parser.error("evidence root already exists; use a new run directory")
        try:
            run_external(args, scenario)
            args.evidence_root.mkdir(parents=True, exist_ok=True)
            (args.evidence_root / "scenario.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
            captured_scenario = args.evidence_root / "scenario.yaml"
            if mc_input_family(args.follower) is not None:
                scenario = VisualizationScenario.from_yaml(captured_scenario)
            summary = validate_px4_evidence(args.evidence_root, scenario)
            (args.evidence_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
            write_visualization(args.evidence_root, scenario, summary)
        except Exception as failure:
            try:
                write_failed_visualization(args.evidence_root, scenario, failure)
            except Exception as report_error:
                print(f"Failed-run visualization unavailable: {report_error}", file=sys.stderr)
            raise
        print(json.dumps({"passed": True, "evidence_root": str(args.evidence_root), "summary": summary}, indent=2))
        return 0
    print(json.dumps({"passed": True, "mode": "dry_run", "scenario": plan}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
