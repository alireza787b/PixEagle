"""Policy tests for the optional deterministic dlib installer."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "install-dlib.sh"


def test_dlib_installer_is_pinned_and_never_manages_swap():
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'DLIB_VERSION="20.0.1"' in source
    assert len(source.split('DLIB_ARCHIVE_SHA256="', 1)[1].split('"', 1)[0]) == 64
    assert "--no-deps --no-build-isolation" in source
    assert "dphys-swapfile" not in source
    assert "swapon" not in source
    assert "swapoff" not in source
    assert 'if [[ "${BASH_SOURCE[0]}" == "$0" ]]' in source


def test_dlib_dry_run_is_no_touch_and_reports_selected_venv(tmp_path):
    isolated_venv = tmp_path / "dlib-policy-venv"
    bin_dir = isolated_venv / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").symlink_to(sys.executable)
    pip_stub = bin_dir / "pip"
    pip_stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    pip_stub.chmod(0o700)
    env = os.environ.copy()
    env["PIXEAGLE_VENV_DIR"] = str(isolated_venv)

    result = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--skip-system-packages"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert "Version:             20.0.1" in result.stdout
    assert f"Python environment:  {isolated_venv}" in result.stdout
    assert "Swap changes:        never" in result.stdout
    assert "no packages or files were changed" in result.stdout
