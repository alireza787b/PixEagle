"""Tests for the explicit component rebuild policy."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HELPER = PROJECT_ROOT / "scripts" / "lib" / "component_reuse.sh"


def _run(expression: str, *, value: str = "") -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PIXEAGLE_REBUILD_COMPONENTS"] = value
    return subprocess.run(
        ["bash", "-c", f"source {shlex.quote(str(HELPER))}; {expression}"],
        cwd=PROJECT_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_empty_policy_reuses_components():
    result = _run("pixeagle_component_rebuild_requested dlib")

    assert result.returncode == 1


def test_named_and_all_rebuild_requests_are_recognized():
    named = _run(
        "pixeagle_component_rebuild_requested opencv",
        value=" dlib, OpenCV ",
    )
    all_components = _run(
        "pixeagle_component_rebuild_requested dashboard",
        value="all",
    )

    assert named.returncode == 0
    assert all_components.returncode == 0


def test_unknown_component_fails_closed():
    result = _run(
        "pixeagle_validate_rebuild_components",
        value="opencv,typo",
    )

    assert result.returncode == 1
    assert "Unknown PIXEAGLE_REBUILD_COMPONENTS item: typo" in result.stderr
