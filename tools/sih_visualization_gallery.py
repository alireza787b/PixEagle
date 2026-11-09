#!/usr/bin/env python3
"""Build a read-only visual contract gallery for every PixEagle follower."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import math
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CASE_LABELS = {
    "nominal": "Nominal · altitude guidance off",
    "altitude": "Altitude guidance on",
    "target_loss": "Target loss",
    "pilot_takeover": "Pilot takeover",
    "stale_telemetry": "Stale telemetry",
    "retarget": "Retarget",
}
RAW_TRACES = (
    "px4/pose_trace.jsonl", "trace/target_truth.jsonl",
    "trace/tracker_command_trace.jsonl", "trace/offboard_publish_trace.jsonl",
    "trace/follower_state.jsonl",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def relative_link(path: Path, base_path: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base_path.resolve())).as_posix()


def baseline_identity(path: Path) -> dict:
    """Check recorded identity against the existing build authority, without Docker."""
    try:
        from tools.sih_baseline import IMAGE_ID, authority, recipe_fingerprint
    except ModuleNotFoundError:
        from sih_baseline import IMAGE_ID, authority, recipe_fingerprint

    manifest = read_json(path)
    firmware, spec = authority()
    if (manifest.get("kind") != "pixeagle_sih_build" or manifest.get("schema_version") != 1
            or manifest.get("firmware") != firmware or manifest.get("build") != spec
            or manifest.get("recipe_sha256") != recipe_fingerprint(firmware, spec)
            or not IMAGE_ID.fullmatch(manifest.get("image_id", ""))):
        raise ValueError("Selected SIH manifest differs from the reviewed build authority")
    return {"kind": "verified_source_build", "image_id": manifest["image_id"],
            "manifest_sha256": sha256(path), "recipe_sha256": manifest["recipe_sha256"],
            "firmware": firmware, "binary_sha256": manifest["artifacts"]["binary_sha256"]}


def inspect_run(run: Path, manifest: dict, base_path: Path) -> dict:
    """Validate recorded inputs and replay verdict; never recompute flight acceptance."""
    issues, stale, hashes = [], [], {}
    result = read_json(run / "result.json")
    scenario = yaml.safe_load((run / "scenario.yaml").read_text(encoding="utf-8"))
    profile = manifest["follower"]
    if result.get("follower") != profile or scenario["follower"]["profile"] != profile:
        issues.append("Profile identity mismatch")
    if result.get("altitude_guidance") is not scenario["follower"].get("altitude_control"):
        issues.append("Scenario and result altitude settings disagree")
    faults = sorted({fault["kind"] for fault in scenario.get("faults", [])})
    case = "+".join(faults) if faults else "altitude" if result.get("altitude_guidance") else "nominal"
    failed = [name for name, passed in result.get("checks", {}).items() if passed is not True]
    if (not result.get("checks") or not isinstance(result.get("passed"), bool)
            or result["passed"] != (not failed)):
        issues.append("Raw verdict and checks disagree or are incomplete")
    if (result.get("scope") != "actual_mc_follower_component_only"
            or manifest.get("network") != "none" or manifest.get("host_ports") != []
            or manifest.get("simulator_model") != "sihsim_quadx"
            or result.get("physical_camera") is not False
            or any(result.get(key) is not False for key in
                   ("release_qualified", "hardware_qualified", "application_startup_qualified"))):
        issues.append("Unexpected qualification scope")
    for name, expected in (("scenario.yaml", result.get("executed_scenario_sha256")),
                           ("configs/config.yaml", manifest.get("config_sha256")),
                           ("driver.py", manifest.get("driver_sha256"))):
        path = run / name
        if not path.is_file() or not expected or sha256(path) != expected:
            issues.append(f"Recorded input checksum mismatch: {name}")
    for name, expected in manifest.get("source_checksums", {}).items():
        path = run / "backend" / name
        if (not path.resolve().is_relative_to((run / "backend").resolve())
                or not path.is_file() or sha256(path) != expected):
            issues.append(f"Captured source checksum mismatch: {name}")
    if not manifest.get("source_checksums"):
        issues.append("Captured source checksums missing")
    capture_end = None
    counts = {}
    for name in RAW_TRACES:
        path = run / name
        if not path.is_file():
            issues.append(f"Missing raw trace: {name}")
            continue
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        counts[name] = len(records)
        if not records:
            issues.append(f"Empty raw trace: {name}")
        if name == RAW_TRACES[0]:
            times = [record.get("timestamp") for record in records]
            if (not times or any(not isinstance(t, (float, int)) or not math.isfinite(t) for t in times)
                    or times != sorted(times)):
                issues.append("Invalid observed pose capture times")
            else:
                capture_end = times[-1]
            if any(not isinstance(record.get("vehicle_ned"), list)
                   or len(record["vehicle_ned"]) != 3
                   or any(not isinstance(v, (float, int)) or not math.isfinite(v)
                          for v in record["vehicle_ned"]) for record in records):
                issues.append("Invalid observed pose coordinates")
    capture_basis = "last raw PX4 pose timestamp (Unix seconds)"
    if capture_end is None:
        # Keep a newer failed attempt visible even if it lost its observation trace.
        capture_end = (run / "result.json").stat().st_mtime
        capture_basis = "result.json modification time fallback; no valid observed capture time"
        issues.append("Capture order uses file time because observed pose time is unavailable")
    replay = run / "visualization/index.html"
    summary_path = run / "visualization/summary.json"
    if replay.is_file() and summary_path.is_file():
        summary = read_json(summary_path)
        if summary.get("qualification_result") != result:
            stale.append("Replay verdict differs from raw result.json")
        if summary.get("evidence_kind") != "px4_sih" or summary.get("pose_observed_samples", 0) <= 0:
            stale.append("Replay lacks observed PX4 pose provenance")
        try:
            payload, _ = json.JSONDecoder().raw_decode(replay.read_text().partition("const PAYLOAD=")[2])
            if payload.get("summary") != summary:
                stale.append("Replay HTML differs from its saved summary")
        except (ValueError, AttributeError):
            stale.append("Replay HTML payload missing or invalid")
    else:
        replay = None
    for path in (run / "manifest.json", run / "result.json", run / "scenario.yaml",
                 run / "configs/config.yaml", *(run / name for name in RAW_TRACES), summary_path):
        if path.is_file():
            hashes[relative_link(path, base_path)] = sha256(path)
    if replay:
        hashes[relative_link(replay, base_path)] = sha256(replay)
    follower_source = f"src/classes/followers/{profile}_follower.py"
    follower_hash = manifest.get("source_checksums", {}).get(follower_source)
    if not follower_hash:
        issues.append("Captured follower source checksum missing")
    source_differs = (ROOT / follower_source).is_file() and sha256(ROOT / follower_source) != follower_hash
    config_path = run / "configs/config.yaml"
    config = yaml.safe_load(config_path.read_text()) if config_path.is_file() else {}
    use_rest = config.get("Follower", {}).get("USE_MAVLINK2REST")
    telemetry = "mavlink2rest" if use_rest is True else "mavsdk" if use_rest is False else "unspecified"
    return {"run": run.name, "profile": profile, "case": case, "passed": result.get("passed"),
            "control_telemetry_source": telemetry,
            "pre_submission_rejection_count": result.get("metrics", {}).get("pre_submission_rejection_count"),
            "failed_checks": failed, "issues": issues, "stale": stale,
            "capture_end": capture_end, "capture_time_basis": capture_basis,
            "raw_counts": counts, "source_head": manifest.get("source_head"),
            "worktree_dirty": manifest.get("worktree_dirty"),
            "follower_source_sha256": follower_hash, "follower_source_differs": source_differs,
            "result": relative_link(run / "result.json", base_path),
            "manifest": relative_link(run / "manifest.json", base_path),
            "replay": relative_link(replay, base_path) if replay else None, "sha256": hashes}


def collect_evidence(catalog: dict, evidence_root: Path, build_manifest: Path, base_path: Path) -> dict:
    identity = baseline_identity(build_manifest)
    profiles = {item["profile"] for item in catalog["followers"] if item["profile"].startswith("mc_")}
    runs, excluded = [], []
    for path in sorted(evidence_root.glob("*/manifest.json")):
        manifest = read_json(path)
        if manifest.get("kind") != "mc-fixed-camera-world-target-component" or manifest.get("follower") not in profiles:
            continue
        if not (path.parent / "result.json").is_file():
            excluded.append({"run": path.parent.name, "reason": "No completed raw result"})
            continue
        baseline = manifest.get("sih_baseline", {})
        if (any(baseline.get(key) != value for key, value in identity.items())
                or manifest.get("px4_image") != identity["image_id"]):
            excluded.append({"run": path.parent.name, "reason": "Different or unverified SIH baseline"})
            continue
        runs.append(inspect_run(path.parent, manifest, base_path))
    groups = {}
    for run in sorted(runs, key=lambda item: (item["capture_end"], item["run"])):
        groups.setdefault(run["profile"], {}).setdefault(run["case"], []).append(run)
    comparison = evidence_root / "baseline-comparison/index.html"
    inventory = ROOT / "docs/followers/05-development/follower-sih-validation-matrix.md"
    return {"schema_version": 1, "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "selection": "Latest completed raw PX4 pose capture per profile/case, including failures; flagged file-time fallback if pose time is unavailable; no pass filtering",
            "validation_scope": "Offline recorded-input checksums, raw verdict consistency and replay agreement; flight metrics are not rerun",
            "baseline": identity, "build_manifest": relative_link(build_manifest, base_path),
            "qualification_inventory": relative_link(inventory, base_path),
            "baseline_comparison": relative_link(comparison, base_path) if comparison.is_file() else None,
            "profiles": groups, "excluded_runs": excluded}


def evidence_rows(cases: dict, *, experimental_rates: bool = False) -> str:
    rows = []
    for case in dict.fromkeys((*CASE_LABELS, *cases)):
        attempts = cases.get(case, [])
        label = html.escape(CASE_LABELS.get(case, case.replace("_", " ")))
        if not attempts:
            missing = '<span class="badge warning">Not run / unqualified</span>'
            if experimental_rates and case == "retarget":
                missing = '<span class="badge warning">Unsupported live retarget · Stop required</span>'
            elif experimental_rates and case == "altitude":
                missing = ('<span class="badge warning">No target-vertical guidance</span>'
                           '<div class="muted">Engagement-height hold plus optional offset; no altitude-chase qualification.</div>')
            rows.append(f'<tr><td>{label}</td><td colspan="2">{missing}</td></tr>')
            continue
        current = attempts[-1]
        verdict = "PASS" if current["passed"] is True else "FAIL"
        badges = f'<span class="badge {"accepted" if current["passed"] else "failed"}">Raw {verdict}</span>'
        if current["issues"]:
            badges += '<span class="badge failed">Invalid evidence</span>'
        if current["stale"]:
            badges += '<span class="badge warning">Stale replay</span>'
        if current["follower_source_differs"]:
            badges += '<span class="badge warning">Follower source differs</span>'
        if not current["replay"]:
            badges += '<span class="badge warning">Replay unavailable</span>'
        links = (f'<a href="{html.escape(current["result"], quote=True)}">Raw result</a> · '
                 f'<a href="{html.escape(current["manifest"], quote=True)}">Manifest</a>')
        if current["replay"]:
            links = f'<a href="{html.escape(current["replay"], quote=True)}">Replay</a> · ' + links
        notes = current["failed_checks"] + current["issues"] + current["stale"]
        if experimental_rates and case == "stale_telemetry":
            notes.append(f'{current["pre_submission_rejection_count"]} pre-submission rejections observed; an earlier stop may avoid this guard path')
        detail = f'<div class="muted">{html.escape("; ".join(notes))}</div>' if notes else ""
        if len(attempts) > 1:
            history = "".join(
                f'<li><a href="{html.escape(old["result"], quote=True)}">{html.escape(old["run"])}</a>'
                f' · raw {"PASS" if old["passed"] else "FAIL"}'
                f'{" · stale replay" if old["stale"] else ""}'
                f'{" · invalid evidence" if old["issues"] else ""}</li>'
                for old in reversed(attempts[:-1]))
            detail += f'<details><summary>Earlier attempts ({len(attempts) - 1})</summary><ul>{history}</ul></details>'
        rows.append(f'<tr><td>{label}</td><td>{badges}</td><td>{links}'
                    f'<div class="muted">{html.escape(current["run"])}'
                    f' · control telemetry: {html.escape(current["control_telemetry_source"])}</div>'
                    f'{detail}</td></tr>')
    return '<table><thead><tr><th>Case</th><th>Recorded status</th><th>Evidence</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table>'


COLORS = {
    "image_position_2d": "#68b5ff",
    "gimbal_angles": "#ffbd69",
    "attitude_rate_image_position": "#c49cff",
}

INPUT_LABELS = {
    "image_position_2d": "image position (2D)",
    "gimbal_angles": "gimbal angles",
    "attitude_rate_image_position": "image + airframe state",
}


def build_gallery(catalog: dict, base_path: Path, evidence: dict | None = None) -> str:
    cards = []
    options = []
    for item in catalog["followers"]:
        profile = html.escape(str(item["profile"]))
        input_contract = str(item["input"])
        input_label = html.escape(INPUT_LABELS.get(input_contract, input_contract.replace("_", " ")))
        command = html.escape(str(item["command"]).replace("_", " "))
        purpose = html.escape(str(item["purpose"]))
        behavior = html.escape(str(item["behavior"]))
        color = COLORS.get(input_contract, "#9fb3c8")
        report = item.get("report")
        evidence_kind = str(item.get("evidence", "contract_only"))
        status = html.escape(str(item.get("status", evidence_kind.replace("_", " "))))
        note = html.escape(str(item.get("note", "")))
        options.append(f'<option value="{profile}">{profile}</option>')
        report_link = (
            f'<a class="report" href="{html.escape(str(report))}">Open interactive replay</a> '
            f'<span class="muted">({html.escape(evidence_kind.replace("_", " "))})</span>'
            if report
            else '<span class="muted">Contract guide only; no synthetic vehicle claim</span>'
        )
        if evidence:
            cases = evidence["profiles"].get(item["profile"], {})
            if item["profile"].startswith("mc_"):
                status = "Actual PX4 SIH component cases · recorded results below"
                note = "Independent moving target projected into simulated camera measurements"
                experimental_rates = item["command"] == "attitude_rate"
                if experimental_rates:
                    note += "; experimental MC rates: direct-rate cases only, PNG and field tuning unqualified"
                report_link = evidence_rows(cases, experimental_rates=experimental_rates)
            else:
                status = "Outside this MC evidence snapshot · current mode unqualified"
                note = "Historical catalog evidence does not qualify the current implementation"
                report_link = '<span class="muted">Synthetic fixtures and historical FW/VTOL results remain in the qualification inventory.</span>'
        cards.append(f'''<article class="card">
  <h2>{profile}</h2>
  <p class="purpose">{purpose}</p>
  <p class="status"><strong>Evidence:</strong> {status}{f' · {note}' if note else ''}</p>
  <svg viewBox="0 0 520 116" role="img" aria-label="{input_label} to {command}">
    <rect x="8" y="25" width="166" height="62" rx="10" fill="#1c2b3a" stroke="{color}" stroke-width="2"/>
    <text x="91" y="52" text-anchor="middle" fill="#eef4f8">Input</text>
    <text x="91" y="73" text-anchor="middle" fill="{color}">{input_label}</text>
    <path d="M190 56h122" stroke="#8ca2b2" stroke-width="2" marker-end="url(#arrow)"/>
    <rect x="338" y="25" width="174" height="62" rx="10" fill="#1c2b3a" stroke="#8ca2b2" stroke-width="2"/>
    <text x="425" y="52" text-anchor="middle" fill="#eef4f8">Command intent</text>
    <text x="425" y="73" text-anchor="middle" fill="#ffb0b0">{command}</text>
  </svg>
  <p>{behavior}</p>
  {report_link}
</article>''')
    snapshot = ""
    if evidence:
        comparison = evidence.get("baseline_comparison")
        comparison_link = f'<a href="{html.escape(comparison, quote=True)}">Observed baseline comparison</a> · ' if comparison else ""
        snapshot = f'''<section class="snapshot"><p><strong>Current MC evidence snapshot</strong> · {html.escape(evidence["generated_at_utc"])}. Latest completed capture per case, including failures. Stale replay badges mean the replay disagrees with the raw result or saved summary; invalid evidence cannot establish a pass. Follower source differences are byte comparisons, including comments, and do not assert a behavior change. Results apply to captured revisions; subsequent algorithm changes need affected cases rerun.</p><p>{comparison_link}<a href="{html.escape(evidence["build_manifest"], quote=True)}">Canonical source-build manifest</a> · <a href="evidence.json">Selection, hashes and capture revisions</a> · <a href="{html.escape(evidence["qualification_inventory"], quote=True)}">Qualification inventory / remaining gates</a></p><p>Actual PX4 SIH pose and publications; camera measurements are simulated from independent moving world targets. Component evidence only: physical camera/tracker, application startup, hardware, release, gimbal modes, FW and VTOL remain unqualified by this snapshot. Direct MC rates has its own altitude hold; a missing shared-altitude case is not a universal altitude-hold result. The baseline candidate includes the native extension; the one-run-each comparison does not identify a specific upstream cause.</p></section>'''
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PixEagle follower visual contracts</title>
<style>
:root {{ color-scheme: dark; --bg:#111820; --panel:#1d2732; --line:#3b4b5b; --muted:#9aaebe; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--bg); color:#eef4f8; font:15px system-ui,sans-serif }}
header {{ padding:22px max(20px,calc((100vw - 1200px)/2)); border-bottom:1px solid var(--line) }}
h1 {{ margin:0 0 6px; font-size:25px }} .muted {{ color:var(--muted) }}
main {{ max-width:1200px; margin:0 auto; padding:18px; display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:14px }}
.card {{ grid-column:1/-1; background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:14px; min-height:285px }}
h2 {{ margin:0 0 4px; font-size:18px }} .purpose {{ color:#d5e3ed; min-height:40px }}
.selector {{ grid-column:1/-1; display:flex; align-items:center; gap:10px; padding:12px 14px; background:var(--panel); border:1px solid var(--line); border-radius:10px }}
select {{ color:#eef4f8; background:#2d4051; border:1px solid #557087; border-radius:5px; padding:7px 10px }} .status {{ color:#d1e5ef; font-size:13px; min-height:36px }}
svg {{ width:100%; height:auto; margin:2px 0 2px }} p {{ line-height:1.4 }} a {{ color:#9ed0ff }}
.card svg {{ max-width:520px; display:block }}
.report {{ display:inline-block; margin-top:4px }}
.snapshot {{ grid-column:1/-1; padding:0 14px; border:1px solid var(--line); border-radius:10px }}
table {{ width:100%; border-collapse:collapse; font-size:12px }} th,td {{ padding:7px 3px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top }}
.badge {{ display:inline-block; border:1px solid #557087; border-radius:5px; padding:2px 4px; margin:1px; white-space:nowrap }}
.accepted {{ color:#9ce6ba; border-color:#5fba8e }} .failed {{ color:#ffaaaa; border-color:#ed7373 }} .warning {{ color:#ffd38d; border-color:#d98b3d }}
td .muted {{ overflow-wrap:anywhere }} details {{ margin-top:4px }} summary {{ cursor:pointer }}
</style></head><body><header><h1>PixEagle follower visual contracts</h1>
<div class="muted">Read-only input-to-command guide. It explains each follower’s contract; linked replays are synthetic unless explicitly marked with observed PX4 pose. No card sends commands, and this gallery does not claim moving-target SIH acceptance.</div></header>
<main>{snapshot}<section class="selector"><label for="followerSelect">Follower evidence</label><select id="followerSelect">{''.join(options)}</select><span class="muted">Select one profile to see its contract, evidence level, and report.</span></section><svg width="0" height="0"><defs><marker id="arrow" markerWidth="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8z" fill="#8ca2b2"/></marker></defs></svg>{''.join(cards)}</main><script>const select=document.getElementById('followerSelect'),cards=[...document.querySelectorAll('.card')];function show(){{cards.forEach(card=>card.hidden=card.querySelector('h2').textContent!==select.value)}}select.onchange=show;show();</script></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("tools/sih_visualization_scenarios/follower-contracts.yaml"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, help="Scan completed actual MC runs under this directory")
    parser.add_argument("--sih-build-manifest", type=Path, help="Require this canonical source-build identity")
    args = parser.parse_args()
    catalog = yaml.safe_load(args.catalog.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or not isinstance(catalog.get("followers"), list):
        raise SystemExit("catalog must contain a followers list")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if bool(args.evidence_root) != bool(args.sih_build_manifest):
        parser.error("--evidence-root and --sih-build-manifest must be supplied together")
    evidence = None
    if args.evidence_root:
        evidence = collect_evidence(catalog, args.evidence_root, args.sih_build_manifest, args.output.parent)
        evidence.update(generator_sha256=sha256(Path(__file__)),
                        catalog_source=relative_link(args.catalog, args.output.parent),
                        catalog_file_sha256=sha256(args.catalog))
        (args.output.parent / "evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    args.output.write_text(build_gallery(catalog, args.output.parent, evidence), encoding="utf-8")
    print(f"Wrote follower contract gallery to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
