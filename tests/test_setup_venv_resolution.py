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
    PROJECT_ROOT / "scripts" / "setup" / "check-gstreamer-runtime.sh",
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


def test_shared_venv_resolver_uses_dot_venv_for_fresh_install(tmp_path):
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


def test_opencv_builder_defers_replacement_and_has_rollback_guard():
    script = (PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh").read_text(
        encoding="utf-8"
    )

    compile_step = script.index('if make -j"$make_jobs"')
    staging_step = script.index("stage_opencv_installation", compile_step)
    replacement_step = script.index("prepare_opencv_replacement", staging_step)
    install_step = script.index(
        'if cp -a "${OPENCV_STAGE_DIR}${VENV_DIR}/."',
        replacement_step,
    )

    assert compile_step < staging_step < replacement_step < install_step
    assert "restore_previous_opencv" in script
    assert "OPENCV_REPLACEMENT_COMMITTED=true" in script
    assert "trap cleanup EXIT" in script
    assert "trap 'exit 130' INT" in script
    assert script.count('"$site_packages"/opencv*.libs') >= 3
    assert "preserving backup at $OPENCV_BACKUP_DIR" in script
    assert "Retained OpenCV recovery backup: $OPENCV_BACKUP_DIR" in script
    assert "GStreamer development metadata is unavailable to pkg-config" in script
    assert "CMake completed without enabling the required GStreamer backend" in script
    assert "install-targets.txt" in script
    assert '"$OPENCV_BACKUP_DIR/manifest/." "$VENV_DIR/"' in script
    assert '"$OPENCV_BACKUP_DIR/venv-layout/." "$VENV_DIR/"' in script
    assert script.count('"$VENV_DIR/include/opencv4"') >= 2
    commit_step = script.index("OPENCV_REPLACEMENT_COMMITTED=true", install_step)
    for verification in (
        "PATH_IN_VENV",
        "VERSION_MATCH",
        "GSTREAMER",
        "FFMPEG",
        "TRACKER_CSRT_INSTANTIATED",
        "TRACKER_KCF_INSTANTIATED",
        "GSTREAMER_SINK_OBSERVED",
    ):
        assert script.index(verification, install_step) < commit_step
    assert "module_path.is_relative_to(expected_venv)" in script
    assert "assert_venv_destination_path" in script
    assert "remove_existing_opencv_artifacts" in script
    replacement_body = script[replacement_step:install_step]
    assert "2>/dev/null || true" not in replacement_body
    assert "sed -i.bak" not in script
    assert "TemporaryDirectory" in script
    assert "filesink location=" in script
    assert "sink_path.stat().st_size > 0" in script
    assert 'factory() is not None' in script
    assert 'if [[ "${BASH_SOURCE[0]}" == "$0" ]]' in script


def test_opencv_rollback_restores_wheel_owned_runtime_libraries(tmp_path):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    venv_dir = tmp_path / "venv"
    site_packages = venv_dir / "lib" / "python3.12" / "site-packages"
    backup_dir = tmp_path / "backup"
    fake_script_dir = tmp_path / "no-build-tree"

    fake_python = venv_dir / "bin" / "python"
    fake_python.parent.mkdir(parents=True)
    fake_python.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$FAKE_SITE_PACKAGES"\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    (venv_dir / "lib").mkdir(parents=True)

    (site_packages / "cv2").mkdir(parents=True)
    (site_packages / "cv2" / "marker.txt").write_text("replacement", encoding="utf-8")
    replacement_wheel_libs = site_packages / "opencv_contrib_python_headless.libs"
    replacement_wheel_libs.mkdir()
    (replacement_wheel_libs / "replacement.so").write_text("replacement", encoding="utf-8")
    (venv_dir / "lib" / "libopencv_replacement.so").write_text("replacement", encoding="utf-8")
    replacement_header = venv_dir / "include" / "opencv4" / "opencv2" / "core.hpp"
    replacement_header.parent.mkdir(parents=True)
    replacement_header.write_text("replacement", encoding="utf-8")

    backup_site = backup_dir / "site-packages"
    (backup_site / "cv2").mkdir(parents=True)
    (backup_site / "cv2" / "marker.txt").write_text("original", encoding="utf-8")
    backup_wheel_libs = backup_site / "opencv_contrib_python_headless.libs"
    backup_wheel_libs.mkdir()
    (backup_wheel_libs / "original.so").write_text("original", encoding="utf-8")
    (backup_dir / "lib").mkdir()
    (backup_dir / "lib" / "libopencv_original.so").write_text("original", encoding="utf-8")
    backup_header = backup_dir / "manifest" / "include" / "opencv4" / "opencv2" / "core.hpp"
    backup_header.parent.mkdir(parents=True)
    backup_header.write_text("original", encoding="utf-8")
    backup_tool = backup_dir / "venv-layout" / "bin" / "opencv_version"
    backup_tool.parent.mkdir(parents=True)
    backup_tool.write_text("original-tool", encoding="utf-8")
    (backup_dir / "install-targets.txt").write_text(
        f"{replacement_header}\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "BUILDER": str(builder),
            "TEST_VENV": str(venv_dir),
            "TEST_SCRIPT_DIR": str(fake_script_dir),
            "TEST_BACKUP": str(backup_dir),
            "FAKE_SITE_PACKAGES": str(site_packages),
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
source "$BUILDER"
VENV_DIR="$TEST_VENV"
SCRIPT_DIR="$TEST_SCRIPT_DIR"
OPENCV_BACKUP_DIR="$TEST_BACKUP"
OPENCV_REPLACEMENT_STARTED=true
OPENCV_REPLACEMENT_COMMITTED=false
restore_previous_opencv
OPENCV_REPLACEMENT_COMMITTED=true
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (site_packages / "cv2" / "marker.txt").read_text(encoding="utf-8") == "original"
    assert not (replacement_wheel_libs / "replacement.so").exists()
    assert (replacement_wheel_libs / "original.so").read_text(encoding="utf-8") == "original"
    assert not (venv_dir / "lib" / "libopencv_replacement.so").exists()
    assert (venv_dir / "lib" / "libopencv_original.so").read_text(encoding="utf-8") == "original"
    assert replacement_header.read_text(encoding="utf-8") == "original"
    assert (venv_dir / "bin" / "opencv_version").read_text(encoding="utf-8") == "original-tool"


def test_opencv_builder_rejects_symlinked_destination_escape(tmp_path):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    venv_dir = tmp_path / "venv"
    outside_dir = tmp_path / "outside"
    (venv_dir / "bin").mkdir(parents=True)
    outside_dir.mkdir()
    (venv_dir / "include").symlink_to(outside_dir, target_is_directory=True)

    env = os.environ.copy()
    env.update(
        {
            "BUILDER": str(builder),
            "TEST_VENV": str(venv_dir),
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
source "$BUILDER"
VENV_DIR="$TEST_VENV"
if assert_venv_destination_path "$VENV_DIR/include/opencv4/core.hpp"; then
    exit 9
fi
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "resolves outside the selected venv" in result.stdout
    assert list(outside_dir.iterdir()) == []


@pytest.mark.parametrize(
    "relative_alias",
    [".", "lib/..", "include/./opencv4", "include//opencv4"],
)
def test_opencv_builder_rejects_venv_root_and_component_aliases(
    tmp_path,
    relative_alias,
):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    venv_dir = tmp_path / "venv"
    (venv_dir / "bin").mkdir(parents=True)

    env = os.environ.copy()
    env.update(
        {
            "BUILDER": str(builder),
            "TEST_VENV": str(venv_dir),
            "RELATIVE_ALIAS": relative_alias,
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
source "$BUILDER"
VENV_DIR="$TEST_VENV"
if assert_venv_destination_path "$VENV_DIR/$RELATIVE_ALIAS"; then
    exit 9
fi
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "unsafe venv-relative path" in result.stdout


def test_opencv_builder_stops_when_previous_artifact_removal_fails(tmp_path):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    venv_dir = tmp_path / "venv"
    site_packages = venv_dir / "lib" / "python3.12" / "site-packages"
    stale_artifact = site_packages / "cv2" / "marker.txt"
    stale_artifact.parent.mkdir(parents=True)
    stale_artifact.write_text("stale", encoding="utf-8")
    (venv_dir / "bin").mkdir(parents=True)

    env = os.environ.copy()
    env.update(
        {
            "BUILDER": str(builder),
            "TEST_VENV": str(venv_dir),
            "TEST_SITE_PACKAGES": str(site_packages),
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
source "$BUILDER"
VENV_DIR="$TEST_VENV"
rm() { return 1; }
if remove_existing_opencv_artifacts "$TEST_SITE_PACKAGES"; then
    exit 9
fi
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Could not remove the previous OpenCV artifact" in result.stdout
    assert stale_artifact.read_text(encoding="utf-8") == "stale"


def test_gstreamer_checker_validates_effective_encoder_and_software_fallback():
    script = (
        PROJECT_ROOT / "scripts" / "setup" / "check-gstreamer-runtime.sh"
    ).read_text(encoding="utf-8")

    assert "from classes.parameters import Parameters" in script
    assert "ENABLE_HARDWARE_ENCODING" in script
    assert "required_elements=(appsrc videoconvert x264enc rtph264pay udpsink)" in script
    assert 'selected_encoder="nvh264enc"' in script
    assert 'selected_encoder="vaapih264enc"' in script
    assert '"$gst_inspect" h264parse' in script
