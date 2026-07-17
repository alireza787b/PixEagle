"""Failure-state and destination tests for setup evidence reports."""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_HELPER = PROJECT_ROOT / "scripts" / "setup" / "evidence_path.py"
AI_INSTALLER = PROJECT_ROOT / "scripts" / "setup" / "install-ai-deps.sh"
OPENCV_BUILDER = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"

pytestmark = [pytest.mark.unit]


def test_evidence_preflight_returns_canonical_target_without_residue(tmp_path):
    target = tmp_path / "nested" / "report.json"
    result = subprocess.run(
        ["python3", str(EVIDENCE_HELPER), str(target)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == str(target.resolve())
    assert target.parent.is_dir()
    assert not target.exists()
    assert list(target.parent.glob("*.preflight")) == []


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory"])
def test_evidence_preflight_rejects_unsafe_existing_target(tmp_path, kind):
    target = tmp_path / "report.json"
    victim = tmp_path / "victim"
    victim.write_text("preserve", encoding="utf-8")
    if kind == "symlink":
        target.symlink_to(victim)
    elif kind == "hardlink":
        os.link(victim, target)
    else:
        target.mkdir()

    result = subprocess.run(
        ["python3", str(EVIDENCE_HELPER), str(target)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert victim.read_text(encoding="utf-8") == "preserve"


def test_evidence_preflight_rejects_group_writable_parent(tmp_path):
    parent = tmp_path / "shared"
    parent.mkdir(mode=0o770)
    parent.chmod(0o770)
    target = parent / "report.json"

    result = subprocess.run(
        ["python3", str(EVIDENCE_HELPER), str(target)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "group/world-writable" in result.stderr or "owner-controlled" in result.stderr
    assert result.stderr.startswith("Error: ")
    assert "Traceback" not in result.stderr
    assert not target.exists()


def test_evidence_helper_publishes_owner_only_json_without_temp_residue(tmp_path):
    target = tmp_path / "private" / "report.json"
    script = f'''
import json
import sys
sys.path.insert(0, {str(EVIDENCE_HELPER.parent)!r})
from evidence_path import atomic_write_json
atomic_write_json({str(target)!r}, {{"status": "ok", "items": list(range(100))}})
'''
    result = subprocess.run(
        ["python3", "-c", script],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(target.read_text(encoding="utf-8"))["status"] == "ok"
    assert target.stat().st_mode & 0o777 == 0o600
    assert list(target.parent.glob(f".{target.name}.*")) == []


def _post_commit_report_failure(script: Path, committed_assignment: str):
    shell = f'''
set -euo pipefail
source "{script}"
trap - EXIT
cleanup() {{ return 0; }}
pixeagle_finalize_venv_transaction() {{ return 0; }}
pixeagle_release_setup_lock() {{ return 0; }}
write_report_json() {{ return 1; }}
REPORT_JSON="/unwritable/evidence.json"
REPORT_STATUS="success"
{committed_assignment}
on_exit
'''
    return subprocess.run(
        ["bash", "-c", shell],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_ai_report_failure_after_commit_has_explicit_retained_state():
    result = _post_commit_report_failure(AI_INSTALLER, "AI_INSTALL_COMMITTED=true")
    assert result.returncode == 74
    assert "committed, but evidence publication failed" in result.stdout
    assert "does not mean rollback occurred" in result.stdout


def test_ai_cleanup_failure_still_finalizes_transaction_and_releases_lock(tmp_path):
    constraints = tmp_path / "constraints.txt"
    constraints.write_text("numpy==2\n", encoding="utf-8")
    finalized = tmp_path / "finalized"
    released = tmp_path / "released"
    shell = f'''
set -euo pipefail
source "{AI_INSTALLER}"
trap - EXIT
rm() {{ return 71; }}
pixeagle_finalize_venv_transaction() {{ printf finalized > "{finalized}"; }}
pixeagle_release_setup_lock() {{ printf released > "{released}"; }}
CONSTRAINTS_FILE="{constraints}"
REPORT_STATUS="running"
REPORT_JSON=""
AI_INSTALL_COMMITTED=false
on_exit
'''
    result = subprocess.run(
        ["bash", "-c", shell],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert finalized.read_text(encoding="utf-8") == "finalized"
    assert released.read_text(encoding="utf-8") == "released"
    assert constraints.exists()
    assert "cleanup failed before the AI transaction committed" in result.stdout


@pytest.mark.parametrize("script", [AI_INSTALLER, OPENCV_BUILDER])
def test_large_provider_evidence_is_not_passed_through_argv(tmp_path, script):
    report = tmp_path / script.stem / "report.json"
    large_assignment = """
large_evidence=$(python3 - <<'PY'
import json
print(json.dumps({"files": ["x" * 256 for _ in range(900)]}))
PY
)
"""
    if script == AI_INSTALLER:
        assignments = '''
REPORT_STATUS="success"
OPENCV_BEFORE="$large_evidence"
OPENCV_AFTER="$large_evidence"
PYTORCH_BEFORE='{}'
PYTORCH_AFTER='{}'
RUNTIME_EVIDENCE="$large_evidence"
'''
    else:
        assignments = '''
REPORT_STATUS="success"
RUNTIME_EVIDENCE="$large_evidence"
SOURCE_EVIDENCE='{}'
BUILD_EVIDENCE='{}'
OPENCV_WORK_ROOT=""
'''
    shell = f'''
set -euo pipefail
source "{script}"
trap - EXIT
{large_assignment}
REPORT_JSON="{report}"
{assignments}
write_report_json 0
'''
    result = subprocess.run(
        ["bash", "-c", shell],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "success"


def test_opencv_report_failure_after_commit_has_explicit_retained_state():
    result = _post_commit_report_failure(
        OPENCV_BUILDER, "OPENCV_REPLACEMENT_COMMITTED=true"
    )
    assert result.returncode == 74
    assert "committed, but evidence publication failed" in result.stdout
    assert "does not mean rollback occurred" in result.stdout


def test_opencv_cleanup_failure_after_commit_is_not_reported_as_rollback(tmp_path):
    status_file = tmp_path / "status"
    shell = f'''
set -euo pipefail
source "{OPENCV_BUILDER}"
trap - EXIT
cleanup() {{ return 1; }}
pixeagle_release_setup_lock() {{ return 0; }}
write_report_json() {{ printf '%s' "$REPORT_STATUS" > "{status_file}"; }}
REPORT_JSON="{tmp_path / 'report.json'}"
REPORT_STATUS="success"
OPENCV_REPLACEMENT_COMMITTED=true
on_exit
'''
    result = subprocess.run(
        ["bash", "-c", shell],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert status_file.read_text(encoding="utf-8") == "installed_cleanup_failed"
    assert "runtime was retained" in result.stdout
