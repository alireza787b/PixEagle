"""Filesystem tests for exact-path virtual-environment transactions."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRANSACTION_HELPER = PROJECT_ROOT / "scripts" / "lib" / "venv_transaction.sh"

pytestmark = [pytest.mark.unit, pytest.mark.skipif(os.name == "nt", reason="POSIX venv")]


def _run(script: str, *args: str):
    return subprocess.run(
        ["bash", "-c", script, "test", *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_failed_transaction_restores_existing_venv_exactly(tmp_path):
    venv = tmp_path / ".venv"
    original = venv / "bin" / "tool"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original\x00bytes")
    original.chmod(0o751)

    result = _run(
        f"""
set -euo pipefail
source {TRANSACTION_HELPER}
pixeagle_begin_venv_transaction "$1" test
rm -f "$1/bin/tool"
printf 'replacement' > "$1/bin/tool"
chmod 0600 "$1/bin/tool"
printf 'new' > "$1/added"
pixeagle_finalize_venv_transaction
""",
        str(venv),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert original.read_bytes() == b"original\x00bytes"
    assert stat.S_IMODE(original.stat().st_mode) == 0o751
    assert not (venv / "added").exists()
    assert not list(tmp_path.glob(".pixeagle-venv-*"))


def test_failed_transaction_removes_new_venv(tmp_path):
    venv = tmp_path / ".venv"

    result = _run(
        f"""
set -euo pipefail
source {TRANSACTION_HELPER}
pixeagle_begin_venv_transaction "$1" test
mkdir -p "$1/bin"
printf 'partial' > "$1/bin/python"
pixeagle_finalize_venv_transaction
""",
        str(venv),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not venv.exists()


def test_committed_transaction_keeps_verified_changes(tmp_path):
    venv = tmp_path / ".venv"
    venv.mkdir()
    marker = venv / "marker"
    marker.write_text("before", encoding="utf-8")

    result = _run(
        f"""
set -euo pipefail
source {TRANSACTION_HELPER}
pixeagle_begin_venv_transaction "$1" test
printf 'after' > "$1/marker"
pixeagle_commit_venv_transaction
pixeagle_finalize_venv_transaction
""",
        str(venv),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.read_text(encoding="utf-8") == "after"
    assert not list(tmp_path.glob(".pixeagle-venv-*"))


def test_nested_helper_cannot_commit_parent_transaction(tmp_path):
    venv = tmp_path / ".venv"
    venv.mkdir()
    marker = venv / "marker"
    marker.write_text("before", encoding="utf-8")

    result = _run(
        f"""
set -euo pipefail
source {TRANSACTION_HELPER}
pixeagle_begin_venv_transaction "$1" parent
bash -c '
    set -euo pipefail
    source "$1"
    pixeagle_begin_venv_transaction "$2" child
    printf after > "$2/marker"
    pixeagle_commit_venv_transaction
    pixeagle_finalize_venv_transaction
' child {TRANSACTION_HELPER} "$1"
pixeagle_finalize_venv_transaction
""",
        str(venv),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.read_text(encoding="utf-8") == "before"


def test_transaction_rejects_symlink_target(tmp_path):
    real_venv = tmp_path / "real"
    real_venv.mkdir()
    linked_venv = tmp_path / ".venv"
    linked_venv.symlink_to(real_venv, target_is_directory=True)

    result = _run(
        f"""
source {TRANSACTION_HELPER}
if pixeagle_begin_venv_transaction "$1" test; then
    exit 9
fi
""",
        str(linked_venv),
    )

    assert result.returncode == 0
    assert "owner-controlled, non-symlink directory" in result.stderr
