"""Installer policy tests for the executable-model store."""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = PROJECT_ROOT / "scripts" / "init.sh"


def _run_prepare_model_store(project_root: Path) -> subprocess.CompletedProcess[str]:
    command = (
        f"source {shlex.quote(str(INIT_SCRIPT))}; "
        f"PIXEAGLE_DIR={shlex.quote(str(project_root))}; "
        "prepare_model_store"
    )
    return subprocess.run(
        ["bash", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )


def test_prepare_model_store_normalizes_root_to_owner_only(tmp_path):
    models_root = tmp_path / "models"
    models_root.mkdir(mode=0o777)
    models_root.chmod(0o777)
    existing_model = models_root / "existing.pt"
    existing_model.write_bytes(b"operator-data")
    existing_model.chmod(0o640)

    result = _run_prepare_model_store(tmp_path)

    assert result.returncode == 0, result.stderr
    assert models_root.stat().st_mode & 0o777 == 0o700
    assert existing_model.read_bytes() == b"operator-data"
    assert existing_model.stat().st_mode & 0o777 == 0o640


def test_prepare_model_store_refuses_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, tmp_path / "models")

    result = _run_prepare_model_store(tmp_path)

    assert result.returncode != 0
    assert "must not be a symbolic link" in result.stdout
    assert (tmp_path / "models").is_symlink()
