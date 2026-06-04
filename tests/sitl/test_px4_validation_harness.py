"""Operator-gated PX4/SITL validation entry point.

These tests are intentionally skipped unless PIXEAGLE_RUN_SITL=1 is set. They
are here so CI and local developers have a stable marker/command surface for
future PX4-in-loop evidence runs without accidentally launching simulators.
"""

import os
import json
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = PROJECT_ROOT / "tools" / "run_sitl_validation_suite.py"

pytestmark = [pytest.mark.sitl, pytest.mark.px4, pytest.mark.e2e]


@pytest.mark.skipif(
    os.environ.get("PIXEAGLE_RUN_SITL") != "1",
    reason="PX4/SITL validation is operator-gated; set PIXEAGLE_RUN_SITL=1",
)
def test_phase2_probe_only_harness_against_running_stack(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--plan-name",
            "phase2_follower_validation",
            "--probe-only",
            "--artifact-root",
            str(tmp_path),
            "--run-id",
            "pytest-sitl",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode in {0, 3}, result.stderr + result.stdout
    payload = json.loads(result.stdout)
    if result.returncode == 3:
        assert payload["result"] == "incomplete"
        assert any(
            artifact in payload.get("missing_or_placeholder_artifacts", [])
            for artifact in (
                "px4/params.txt",
                "px4/ulog_manifest.json",
                "px4/tlog_manifest.json",
            )
        )
        pytest.xfail(
            "Probe-only requires a complete route/profile/probe/scenario and "
            "PX4 artifact package before it can be required to return pass."
        )
    assert payload["result"] == "pass"
