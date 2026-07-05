"""Guards for PixEagle setup-helper virtualenv discovery."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMMON_SH = PROJECT_ROOT / "scripts" / "lib" / "common.sh"
OPTIONAL_SETUP_SCRIPTS = [
    PROJECT_ROOT / "scripts" / "setup" / "check-ai-runtime.sh",
    PROJECT_ROOT / "scripts" / "setup" / "install-ai-deps.sh",
    PROJECT_ROOT / "scripts" / "setup" / "setup-pytorch.sh",
    PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh",
    PROJECT_ROOT / "scripts" / "setup" / "install-dlib.sh",
    PROJECT_ROOT / "scripts" / "lib" / "reset-config.sh",
]


pytestmark = [pytest.mark.unit]


def _make_executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)


def _resolve_with_common(project_root: Path, *, override: str | None = None) -> list[str]:
    env = os.environ.copy()
    env.pop("PIXEAGLE_VENV_DIR", None)
    if override is not None:
        env["PIXEAGLE_VENV_DIR"] = override

    command = (
        f"source {COMMON_SH}; "
        f"resolve_pixeagle_venv_dir {project_root}; "
        f"resolve_pixeagle_venv_python {project_root}; "
        f"resolve_pixeagle_venv_pip {project_root}"
    )
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip().splitlines()


def test_shared_venv_resolver_prefers_dot_venv_over_legacy_venv(tmp_path):
    _make_executable(tmp_path / "venv" / "bin" / "python")
    _make_executable(tmp_path / "venv" / "bin" / "pip")
    _make_executable(tmp_path / ".venv" / "bin" / "python")
    _make_executable(tmp_path / ".venv" / "bin" / "pip")

    resolved_dir, resolved_python, resolved_pip = _resolve_with_common(tmp_path)

    assert resolved_dir == str(tmp_path / ".venv")
    assert resolved_python == str(tmp_path / ".venv" / "bin" / "python")
    assert resolved_pip == str(tmp_path / ".venv" / "bin" / "pip")


def test_shared_venv_resolver_supports_absolute_override(tmp_path):
    custom_venv = tmp_path / "custom-env"

    resolved_dir, resolved_python, resolved_pip = _resolve_with_common(
        tmp_path,
        override=str(custom_venv),
    )

    assert resolved_dir == str(custom_venv)
    assert resolved_python == str(custom_venv / "bin" / "python")
    assert resolved_pip == str(custom_venv / "bin" / "pip")


def test_shared_venv_resolver_supports_project_relative_override(tmp_path):
    resolved_dir, resolved_python, resolved_pip = _resolve_with_common(
        tmp_path,
        override=".venv",
    )

    assert resolved_dir == str(tmp_path / ".venv")
    assert resolved_python == str(tmp_path / ".venv" / "bin" / "python")
    assert resolved_pip == str(tmp_path / ".venv" / "bin" / "pip")


@pytest.mark.parametrize("script_path", OPTIONAL_SETUP_SCRIPTS)
def test_optional_setup_helpers_do_not_pin_legacy_venv(script_path):
    text = script_path.read_text(encoding="utf-8")

    assert 'VENV_DIR="$PIXEAGLE_DIR/venv"' not in text
    assert 'VENV_PYTHON="$PIXEAGLE_DIR/venv/bin/python"' not in text
    assert 'VENV_PIP="$PIXEAGLE_DIR/venv/bin/pip"' not in text
    assert "source venv/bin/activate" not in text
