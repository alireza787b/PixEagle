"""Tests for runtime log helpers used by launcher component pipes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from classes.runtime_logging import RuntimeLogSessionManager


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TOOL = PROJECT_ROOT / "tools" / "runtime_log_pipe.py"
EXEC_TOOL = PROJECT_ROOT / "tools" / "runtime_log_exec.sh"


def _env(tmp_path: Path, run_id: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PIXEAGLE_RUNTIME_LOG_DIR"] = str(tmp_path)
    env["PIXEAGLE_RUN_ID"] = run_id
    return env


def test_runtime_log_pipe_prepares_component_files(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--prepare-components",
            "backend",
            "dashboard",
            "mavlink2rest",
        ],
        cwd=PROJECT_ROOT,
        env=_env(tmp_path, "pixeagle_pipe_prepare"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manager = RuntimeLogSessionManager(
        base_dir=tmp_path,
        run_id="pixeagle_pipe_prepare",
    )
    manifest = manager.read_manifest("pixeagle_pipe_prepare")
    assert manifest is not None
    assert set(manifest["component_files"]) == {
        "backend",
        "dashboard",
        "mavlink2rest",
    }


def test_runtime_log_pipe_captures_sanitized_lines(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--component",
            "dashboard",
            "--stream",
            "stdout",
            "--source",
            "test",
        ],
        cwd=PROJECT_ROOT,
        env=_env(tmp_path, "pixeagle_pipe_capture"),
        input="ready password=swordfish\n\nserved /index.html\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    manager = RuntimeLogSessionManager(
        base_dir=tmp_path,
        run_id="pixeagle_pipe_capture",
    )
    entries = manager.read_entries("pixeagle_pipe_capture", component="dashboard")
    assert entries is not None
    assert [entry["message"] for entry in entries] == [
        "ready password=[REDACTED]",
        "served /index.html",
    ]
    assert entries[0]["source"] == "test"


def test_runtime_log_exec_mirrors_output_and_preserves_exit_code(tmp_path):
    result = subprocess.run(
        [
            "bash",
            str(EXEC_TOOL),
            "dashboard",
            "--",
            "bash",
            "-lc",
            "echo ready password=swordfish; exit 7",
        ],
        cwd=PROJECT_ROOT,
        env=_env(tmp_path, "pixeagle_exec_capture"),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 7
    assert "ready password=swordfish" in result.stdout
    assert "Component exited with code 7" in result.stdout

    manager = RuntimeLogSessionManager(
        base_dir=tmp_path,
        run_id="pixeagle_exec_capture",
    )
    entries = manager.read_entries("pixeagle_exec_capture", component="dashboard")
    assert entries is not None
    assert entries[0]["message"] == "ready password=[REDACTED]"
    assert entries[0]["stream"] == "combined"
    assert entries[0]["source"] == "launcher-pipe"
