#!/usr/bin/env python3
"""Build a read-only interactive SIH guidance report.

Examples:
  PYTHONPATH=src python tools/sih_visualizer.py \
    --scenario tools/sih_visualization_scenarios/gimbal-vector-vertical.yaml \
    --evidence-root reports/sitl/run --output-dir reports/sitl/run/visualization

  PYTHONPATH=src python tools/sih_visualizer.py \
    --scenario tools/sih_visualization_scenarios/gimbal-vector-vertical.yaml \
    --live-url http://127.0.0.1:8080/v1/mavlink --system-id 1 --duration-s 30 \
    --output-dir reports/sitl/live/visualization
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from classes.sih_visualization import (  # noqa: E402
    VisualizationSample,
    VisualizationScenario,
    analyze_timeline,
    build_timeline,
    load_evidence,
    write_csv,
)
try:
    from tools.sitl_gimbal_geometry_fixture import pose_from_mavlink2rest  # noqa: E402
except ModuleNotFoundError:
    from sitl_gimbal_geometry_fixture import pose_from_mavlink2rest  # noqa: E402


def _json_script(value: Any) -> str:
    return json.dumps(value, separators=(",", ":")).replace("</", "<\\/")


def build_html(scenario: VisualizationScenario, samples: list[VisualizationSample], summary: dict[str, Any]) -> str:
    qualification = summary.get("qualification_result", {}).get("passed")
    verdict = "Scenario passed" if qualification is True else "Scenario failed" if qualification is False else "Replay only"
    verdict_class = "accepted" if qualification is True else "failed" if qualification is False else "warning"
    payload = {
        "scenario": {
            "name": scenario.name,
            "rate_hz": scenario.rate_hz,
            "frame": scenario.frame,
            "mount_type": scenario.mount_type,
            "airframe": scenario.airframe,
            "follower_profile": scenario.follower_profile,
            "follower_purpose": scenario.follower_purpose,
            "input_contract": scenario.input_contract,
            "command_contract": scenario.command_contract,
            "lateral_guidance_mode": scenario.lateral_guidance_mode,
            "altitude_control": scenario.altitude_control,
            "speed_source_policy": scenario.speed_source_policy,
            "evidence_provenance": scenario.evidence_provenance,
            "stable_flight": scenario.stable_flight,
            "acceptance": scenario.acceptance,
            "requested_speed": scenario.requested_speed,
            "initial_vehicle_ned": scenario.initial_vehicle_ned,
            "limits": scenario.limits,
        },
        "samples": [sample.to_dict() for sample in samples],
        "summary": summary,
    }
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PixEagle SIH guidance report</title>
<style>
:root {{ color-scheme: dark; --bg:#111820; --panel:#1d2732; --muted:#98a8b7; --line:#3b4b5b; --target:#ffbd69; --drone:#68b5ff; --cmd:#ff6b6b; }}
* {{ box-sizing:border-box }} body {{ margin:0; font:14px system-ui,sans-serif; background:var(--bg); color:#eef4f8 }}
header {{ padding:14px 18px; border-bottom:1px solid var(--line); display:flex; gap:20px; align-items:baseline; flex-wrap:wrap }}
h1 {{ font-size:19px; margin:0 }} .muted {{ color:var(--muted) }} main {{ display:grid; grid-template-columns:minmax(520px,2fr) minmax(300px,1fr); gap:12px; padding:12px }}
.panel {{ background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:10px; min-width:0 }} aside {{ min-width:0 }} canvas {{ width:100%; display:block; background:#0b1117; border-radius:5px }}
#scene {{ height:min(66vh,650px); touch-action:none; cursor:grab }} #scene:active {{ cursor:grabbing }} #timeline {{ height:300px; margin-top:10px }} button,input {{ font:inherit }} button {{ color:#eef4f8; background:#2d4051; border:1px solid #557087; border-radius:5px; padding:6px 9px; cursor:pointer }} button:hover {{ background:#3b566c }}
.controls {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin-bottom:8px }} .control-group {{ display:inline-flex; align-items:center; gap:4px; padding-right:4px; border-right:1px solid var(--line) }} .control-label {{ color:var(--muted); margin-right:2px }} .layers {{ margin:3px 0 8px; color:var(--muted) }} .layers summary {{ cursor:pointer; padding:4px 0 }} label {{ color:var(--muted); margin-right:6px }}
.badge {{ display:inline-block; border:1px solid #557087; border-radius:12px; padding:3px 8px; margin:2px; font-size:12px }} .warning {{ border-color:#d98b3d; color:#ffd38d }}
.accepted {{ border-color:#5fba8e; color:#9ce6ba }} .failed {{ border-color:#ed7373; color:#ffaaaa }}
.legend {{ display:flex; flex-wrap:wrap; gap:8px; padding:6px 0; color:var(--muted); font-size:12px }} .legend span {{ display:inline-flex; align-items:center; gap:4px }} .swatch {{ width:12px; height:3px; display:inline-block }}
pre {{ white-space:pre-wrap; max-height:280px; overflow:auto; color:#d8e3ec }} table {{ width:100%; border-collapse:collapse }} td {{ padding:4px 2px; border-bottom:1px solid #2d3a47; overflow-wrap:anywhere }}
@media(max-width:900px) {{ main {{ grid-template-columns:minmax(0,1fr) }} #scene {{ height:56vh }} }}
</style></head><body>
<header><h1>PixEagle follower replay</h1><span class="badge {verdict_class}" id="qualification">{verdict}</span><span class="muted" id="scenario"></span><span class="badge" id="coverage"></span><span class="badge warning" id="evidenceKind">Read-only evidence viewer</span><div class="muted" id="motionSummary"></div></header>
<main><section class="panel"><div class="controls primary-controls"><button id="play" aria-label="Play or pause evidence">Play</button><button id="reset" aria-label="Reset evidence playback">Reset</button><button id="resetView" aria-label="Reset 3D view">Reset 3D</button><span class="control-group"><span class="control-label">View</span><button data-view="iso">3D</button><button data-view="top">Top</button><button data-view="front">Front</button><button data-view="side">Side</button></span><label>speed <select id="rate"><option>0.25</option><option>0.5</option><option selected>1</option><option>2</option><option>4</option></select>x</label></div><details class="layers"><summary>Layers</summary><div class="controls layer-controls"><label><input id="targetHistory" type="checkbox" checked> target path</label><label><input id="droneHistory" type="checkbox" checked> PX4 path</label><label><input id="losToggle" type="checkbox" checked> line of sight</label><label><input id="commandToggle" type="checkbox" checked> command intent</label></div></details><canvas id="scene" width="1000" height="650"></canvas><div class="legend"><span><i class="swatch" style="background:#ffbd69"></i> target truth</span><span><i class="swatch" style="background:#68b5ff"></i> PX4 pose (observed)</span><span><i class="swatch" style="background:#ff6b6b"></i> command intent · phase-specific</span><span class="muted">Solid marker = now · dashed line = history · 3D = draggable N/E/D orbit</span></div><input id="scrub" type="range" min="0" max="0" value="0" style="width:100%"><div class="muted" id="time"></div></section>
<aside><section class="panel"><h3>Current sample</h3><div id="badges"></div><table id="values"></table></section><section class="panel"><h3>Timeline</h3><canvas id="timeline" width="700" height="300"></canvas></section><section class="panel"><h3>Validation</h3><pre id="summary"></pre></section></aside></main>
<script>const PAYLOAD={_json_script(payload)};{(PROJECT_ROOT / "tools/sih_visualization_report.js").read_text(encoding="utf-8")}</script></body></html>'''


def write_png(path: Path, scenario: VisualizationScenario, samples: list[VisualizationSample]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    native = scenario.command_contract in {"fixed_wing_external", "vtol_external"}
    attitude = scenario.command_contract == "attitude_rate"
    groups = [
        ("course (degrees)", [("course_rad", "course", 180 / math.pi)]),
        ("equivalent airspeed (m/s)", [("equivalent_airspeed_m_s", "EAS request", 1)]),
    ] if native else [
        ("rate (degrees/s)", [("rollspeed_deg_s", "roll", 1), ("pitchspeed_deg_s", "pitch", 1),
                              ("yawspeed_deg_s", "yaw", 1)]),
        ("normalized thrust", [("thrust", "thrust", 1)]),
    ] if attitude else [
        ("heading-frame velocity (m/s)", [("vel_body_fwd", "forward", 1), ("vel_body_right", "right", 1),
                                          ("vel_body_down", "down", 1)]),
    ]
    if native:
        for key, label, unit in (("height_rate_m_s", "height rate", "m/s (up +)"),
                                  ("altitude_amsl_m", "altitude hold", "m AMSL")):
            if any(key in sample.command for sample in samples):
                groups.append((unit, [(key, label, 1)]))
    figure, axes = plt.subplots(len(groups) + 1, 1, figsize=(12, 3 * (len(groups) + 1)), constrained_layout=True)
    times = [sample.timestamp for sample in samples]
    for axis, (ylabel, fields) in zip(axes, groups):
        for key, label, factor in fields:
            values = [sample.command.get(key, math.nan) * factor for sample in samples]
            if key == "course_rad":
                values = [math.nan if index and abs(value - values[index - 1]) > 180 else value
                          for index, value in enumerate(values)]
            axis.plot(times, values, label=label)
        if native and ylabel == "equivalent airspeed (m/s)":
            for key, label in (("observed_eas_m_s", "observed EAS"), ("native_effective_eas_m_s", "native EAS ref")):
                axis.plot(times, [getattr(sample, key) if getattr(sample, key) is not None else math.nan
                                  for sample in samples], label=label, linestyle="--")
        axis.set_ylabel(ylabel)
        axis.set_xlabel("time (s)")
        axis.legend()
    axes[0].set_title(f"{scenario.follower_profile}: {scenario.name} · {scenario.evidence_provenance}")
    for key, label, color in (("target_ned", "independent target truth", "#d18b24"),
                               ("vehicle_ned", "PX4-observed pose", "#2584c4")):
        points = [getattr(sample, key) for sample in samples]
        axes[-1].plot([point[0] if point else math.nan for point in points],
                      [point[1] if point else math.nan for point in points], label=label, color=color)
    axes[-1].set_xlabel("north (m)")
    axes[-1].set_ylabel("east (m)")
    axes[-1].set_aspect("equal", adjustable="datalim")
    axes[-1].legend()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def poll_live_pose(url: str, system_id: int, duration_s: float, token: str | None, output: Path, interval_s: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    started = time.monotonic()
    with output.open("w", encoding="utf-8") as stream:
        while time.monotonic() - started < duration_s:
            request = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(request, timeout=max(2.0, interval_s * 4.0)) as response:
                    snapshot = json.loads(response.read().decode("utf-8"))
                position, quaternion = pose_from_mavlink2rest(snapshot, system_id)
                record = {
                    "timestamp": dt.datetime.now(dt.timezone.utc).timestamp(),
                    "vehicle_ned": position,
                    "vehicle_quaternion": quaternion,
                    "source": "read_only_mavlink2rest",
                }
                stream.write(json.dumps(record) + "\n")
                stream.flush()
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                stream.write(json.dumps({"timestamp": dt.datetime.now(dt.timezone.utc).timestamp(), "error": str(exc)}) + "\n")
                stream.flush()
            time.sleep(interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--live-url")
    parser.add_argument("--system-id", type=int, default=1)
    parser.add_argument("--duration-s", type=float, default=30.0)
    parser.add_argument("--interval-s", type=float, default=0.1)
    parser.add_argument("--token")
    args = parser.parse_args()
    if not args.evidence_root and not args.live_url:
        parser.error("one of --evidence-root or --live-url is required")
    scenario = VisualizationScenario.from_yaml(args.scenario)
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    evidence_root = args.evidence_root or output / "evidence"
    if args.live_url:
        poll_live_pose(args.live_url, args.system_id, args.duration_s, args.token, evidence_root / "px4" / "pose_trace.jsonl", args.interval_s)
    evidence = load_evidence(evidence_root)
    samples = build_timeline(scenario, evidence)
    summary = analyze_timeline(scenario, samples)
    fixture_summary = evidence_root / "fixture_summary.json"
    summary["evidence_kind"] = "synthetic_fixture" if fixture_summary.exists() else "imported_trace"
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "trace.json").write_text(json.dumps([sample.to_dict() for sample in samples], indent=2) + "\n", encoding="utf-8")
    write_csv(output / "trace.csv", samples)
    (output / "index.html").write_text(build_html(scenario, samples, summary), encoding="utf-8")
    write_png(output / "summary.png", scenario, samples)
    print(f"Wrote read-only SIH visualization to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
