"""Raspberry Pi CSI GStreamer setup contract tests."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "setup" / "reconcile-rpi-csi-gstreamer.sh"


def _write_inspector(path: Path, *, available: bool) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "[[ \"${1:-}\" == \"libcamerasrc\" ]] || exit 2\n"
        f"exit {0 if available else 1}\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _run_verify(tmp_path: Path, *, model: str, available: bool) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_inspector(bin_dir / "gst-inspect-1.0", available=available)
    model_file = tmp_path / "model"
    model_file.write_text(model, encoding="utf-8")
    os_release = tmp_path / "os-release"
    os_release.write_text("ID=debian\n", encoding="utf-8")

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PIXEAGLE_DEVICE_TREE_MODEL_FILE"] = str(model_file)
    env["PIXEAGLE_OS_RELEASE_FILE"] = str(os_release)
    return subprocess.run(
        ["bash", str(SCRIPT), "--verify-only"],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_raspberry_pi_verify_accepts_discovered_libcamerasrc(tmp_path: Path):
    result = _run_verify(
        tmp_path,
        model="Raspberry Pi Compute Module 5 Rev 1.0\0",
        available=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Raspberry Pi CSI source available: libcamerasrc" in result.stdout


def test_raspberry_pi_verify_reports_actionable_missing_plugin(tmp_path: Path):
    result = _run_verify(
        tmp_path,
        model="Raspberry Pi 5 Model B Rev 1.0\0",
        available=False,
    )

    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "Raspberry Pi CSI source is unavailable: libcamerasrc" in combined
    assert "reconcile-rpi-csi-gstreamer.sh" in combined


def test_non_raspberry_pi_verify_is_a_noop(tmp_path: Path):
    result = _run_verify(tmp_path, model="Generic ARM64 board\0", available=False)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_raspberry_pi_reconcile_installs_plugin_without_opencv_build(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "libcamerasrc-ready"
    apt_log = tmp_path / "apt-get.log"
    model_file = tmp_path / "model"
    model_file.write_text("Raspberry Pi Compute Module 5 Rev 1.0\0", encoding="utf-8")
    os_release = tmp_path / "os-release"
    os_release.write_text("ID=raspbian\n", encoding="utf-8")

    _write_executable(
        bin_dir / "gst-inspect-1.0",
        f"#!/usr/bin/env bash\n[[ -f '{marker}' ]] && exit 0\nexit 1\n",
    )
    _write_executable(bin_dir / "apt-cache", "#!/usr/bin/env bash\nexit 0\n")
    _write_executable(
        bin_dir / "apt-get",
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > '{apt_log}'\ntouch '{marker}'\n",
    )
    _write_executable(
        bin_dir / "sudo",
        "#!/usr/bin/env bash\n"
        "if [[ \"${1:-}\" == '-n' && \"${2:-}\" == '-v' ]]; then exit 0; fi\n"
        "if [[ \"${1:-}\" == '-n' ]]; then shift; fi\n"
        "exec \"$@\"\n",
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PIXEAGLE_DEVICE_TREE_MODEL_FILE"] = str(model_file)
    env["PIXEAGLE_OS_RELEASE_FILE"] = str(os_release)
    result = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert marker.exists()
    assert apt_log.read_text(encoding="utf-8").strip() == (
        "install -y gstreamer1.0-libcamera"
    )
    assert "installed and verified" in result.stdout


def test_initializer_reconciles_pi_plugin_after_opencv_reuse_or_build():
    initializer = (PROJECT_ROOT / "scripts" / "init.sh").read_text(encoding="utf-8")
    builder = (PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh").read_text(
        encoding="utf-8"
    )

    assert "reconcile-rpi-csi-gstreamer.sh" in initializer
    assert "reconcile-rpi-csi-gstreamer.sh" in builder
