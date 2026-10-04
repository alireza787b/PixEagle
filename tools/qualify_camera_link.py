#!/usr/bin/env python3
"""Record camera-free authenticated HTTP link qualification and source hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    "tests/integration/core_app/test_camera_link_envelope.py",
    "tests/integration/core_app/test_camera_shared_link_production.py",
    "tests/unit/streaming/test_shared_link_relay.py",
    "tests/unit/core_app/test_camera_manual_executor.py",
    "tests/unit/trackers/test_gimbal_tracker.py::test_video_processing_preserves_camera_measurement_identity",
    "tests/unit/trackers/test_gimbal_interface_status_freshness.py",
    "tests/unit/core_app/test_target_continuity.py::test_camera_provisional_angles_require_current_selection_and_no_manual_takeover",
    "tests/unit/core_app/test_target_continuity.py::test_continuity_watchdog_dispatches_loss_only_when_updates_stop",
    "tests/unit/drone_interface/test_offboard_commander.py",
    "tests/unit/streaming/test_streaming_lifecycle.py::test_video_websocket_waits_for_render_ack_before_sampling_next_frame",
    "tests/unit/streaming/test_native_frame_provenance.py::test_delivered_selection_survives_capture_ring_pressure_until_release",
    "tests/unit/streaming/test_native_frame_provenance.py::test_websocket_pins_sampled_selection_before_slow_encoding",
    "tests/unit/streaming/test_native_frame_provenance.py::test_source_changed_while_encoding_never_sends_retired_frame",
]
SOURCES = [
    "src/classes/camera_manual_executor.py", "src/classes/camera_runtime.py",
    "src/classes/api_v1_native_camera.py", "src/classes/offboard_commander.py",
    "src/classes/trackers/gimbal_tracker.py", "tools/native_integration_fixture.py",
    "tests/integration/core_app/test_camera_link_envelope.py", "tools/qualify_camera_link.py",
    "tests/integration/core_app/test_camera_shared_link_production.py",
    "tools/shared_link_relay.py", "tests/unit/streaming/test_shared_link_relay.py",
    "tests/unit/core_app/test_camera_manual_executor.py",
    "tests/unit/trackers/test_gimbal_tracker.py",
    "tests/unit/drone_interface/test_offboard_commander.py",
    "src/classes/gimbal_interface.py", "src/classes/target_continuity.py",
    "src/classes/app_controller.py",
    "tests/unit/trackers/test_gimbal_interface_status_freshness.py",
    "tests/unit/core_app/test_target_continuity.py",
    "src/classes/flow_controller.py", "src/classes/fastapi_handler.py",
    "src/classes/frame_publisher.py",
    "tests/unit/streaming/test_streaming_lifecycle.py",
    "tests/unit/streaming/test_native_frame_provenance.py",
]


def source_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "manifest.json").exists():
        parser.error("Use a fresh output directory to retain earlier evidence.")
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    command = [sys.executable, "-m", "pytest", "-q", "-s", *CASES]
    sources_before = source_hashes()
    log_path = output / "tests.log"
    with log_path.open("w") as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    log = log_path.read_text()
    records = [json.loads(match.group(1)) for match in re.finditer(r"(?:CAMERA_LINK|CAMERA_TIMING) (\{[^\n]+\})", log)]
    sources = source_hashes()
    source_stable = sources == sources_before
    exit_code = result.returncode if source_stable else 2
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
        "command": command, "exit_code": exit_code, "source_sha256": sources,
        "source_stable": source_stable,
        "packages": {name: version(name) for name in ("pytest", "httpx", "uvicorn", "fastapi")},
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "transport": "authenticated real loopback HTTP plus owned loopback TCP relay tests; synthetic movement provider",
        "impairment": "HTTP sender scheduling delays/drops; relay aggregate byte budget/latency/reset; no kernel network shaping",
        "renewal_ms": 100, "lease_ms": 350, "watchdog_poll_ms": 20,
        "delay_schedule_ms": [20, 60, 40], "isolated_drop_sequences": [5, 9],
        "software_gates": {"stop_dispatch_from_route_receipt_ms": 100,
                           "expiry_stop_from_last_accepted_update_ms": 400},
        "observations": records,
        "limitations": ["The production relay test is a short sustained synthetic fixture; it is not QGC desktop or Dashboard UI evidence",
                     "No radio throughput/bitrate qualification", "No camera UDP transmission or physical motor stopping",
                     "No process-death/device watchdog proof", "No full QGC client transport qualification",
                        "No CPU starvation or real-time scheduling guarantee"],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Qualification {'passed' if exit_code == 0 else 'failed'}: {output / 'manifest.json'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
