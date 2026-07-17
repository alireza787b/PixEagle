"""Native Windows checks for setup/launcher contracts."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(os.name != "nt", reason="native Windows contract"),
]
REPO_ROOT = Path(__file__).resolve().parents[1]


def _prepare_launcher_project(root: Path, venv_name: str) -> Path:
    launcher = root / "scripts" / "components" / "main.bat"
    launcher.parent.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts" / "components" / "main.bat", launcher)
    main_script = root / "src" / "main.py"
    main_script.parent.mkdir()
    main_script.write_text("raise SystemExit(0)\n", encoding="utf-8")
    activate = root / venv_name / "Scripts" / "activate.bat"
    activate.parent.mkdir(parents=True)
    activate.write_text("@exit /b 0\r\n", encoding="ascii")
    shutil.copy2(Path(sys.executable), activate.parent / "python.exe")
    return launcher


@pytest.mark.parametrize("venv_name", [".venv", "venv"])
def test_main_launcher_preflight_resolves_canonical_and_legacy_venvs(tmp_path, venv_name):
    launcher = _prepare_launcher_project(tmp_path, venv_name)

    result = subprocess.run(
        [os.environ["COMSPEC"], "/d", "/c", str(launcher), "--check"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_main_launcher_preflight_honors_relative_override(tmp_path):
    launcher = _prepare_launcher_project(tmp_path, "custom-env")
    env = os.environ.copy()
    env["PIXEAGLE_VENV_DIR"] = "custom-env"

    result = subprocess.run(
        [env["COMSPEC"], "/d", "/c", str(launcher), "--check"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_main_launcher_rejects_activation_script_without_interpreter(tmp_path):
    launcher = _prepare_launcher_project(tmp_path, ".venv")
    (tmp_path / ".venv" / "Scripts" / "python.exe").unlink()

    result = subprocess.run(
        [os.environ["COMSPEC"], "/d", "/c", str(launcher), "--check"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "interpreter not found" in (result.stdout + result.stderr)


def test_run_launcher_fails_before_claiming_success_without_backend_venv():
    env = os.environ.copy()
    env["PIXEAGLE_VENV_DIR"] = "definitely-missing-test-venv"

    result = subprocess.run(
        [env["COMSPEC"], "/d", "/c", r"scripts\run.bat", "-m", "-k"],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    combined = result.stdout + result.stderr
    assert result.returncode == 1
    assert "Backend preflight failed" in combined
    assert "All Services Launched" not in combined
