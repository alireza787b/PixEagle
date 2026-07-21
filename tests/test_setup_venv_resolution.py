"""Guards for PixEagle setup-helper virtualenv discovery."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile
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


@pytest.fixture
def opencv_backup_dir():
    result = subprocess.run(
        ["mktemp", "-d", "/var/tmp/pixeagle-opencv-backup.XXXXXX"],
        text=True,
        capture_output=True,
        check=True,
    )
    backup_dir = Path(result.stdout.strip())
    try:
        yield backup_dir
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)


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

    compile_step = script.index('if cmake --build "$OPENCV_BUILD_DIR"')
    staging_step = script.index("stage_opencv_installation", compile_step)
    replacement_step = script.index("prepare_opencv_replacement", staging_step)
    install_step = script.index(
        'if cp -a "${OPENCV_STAGE_DIR}${VENV_DIR}/."',
        replacement_step,
    )

    assert compile_step < staging_step < replacement_step < install_step
    assert "restore_previous_opencv" in script
    assert "OPENCV_REPLACEMENT_COMMITTED=true" in script
    assert "trap on_exit EXIT" in script
    assert "opencv_interrupted INT 130" in script
    assert "opencv_interrupted TERM 143" in script
    assert "opencv_interrupted HUP 129" in script
    assert "start_build_heartbeat" in script
    assert "stop_build_heartbeat" in script
    assert "[alive] OpenCV build running" in script
    assert "make setup-status" in script
    heartbeat_start = script.index(
        'start_build_heartbeat "$build_log" "$start_time"'
    )
    heartbeat_stop = script.index("stop_build_heartbeat", compile_step)
    assert heartbeat_start < compile_step < heartbeat_stop < staging_step
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


def test_opencv_builder_pins_sources_and_requires_swap_opt_in():
    script = (PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh").read_text(
        encoding="utf-8"
    )

    assert 'OPENCV_SOURCE_COMMIT="fe38fc608f6acb8b68953438a62305d8318f4fcd"' in script
    assert (
        'OPENCV_CONTRIB_SOURCE_COMMIT="d99ad2a188210cc35067c2e60076eed7c2442bc3"'
        in script
    )
    assert 'fetch --force --no-tags --depth=1' in script
    assert 'fetch --all' not in script
    assert 'archive --format=tar' in script
    assert "validate_and_extract_opencv_archive" in script
    assert "OPENCV_WORK_ROOT=\"$(mktemp -d /var/tmp/pixeagle-opencv-build.XXXXXX)\"" in script
    assert 'core.hooksPath=$OPENCV_HOOKS_DIR' in script
    assert 'GIT_CONFIG_NOSYSTEM=1' in script
    assert "GIT_CONFIG_PARAMETERS" in script
    assert 'GIT_ALLOW_PROTOCOL=https' in script
    assert 'OPENCV_EXPECTED_ARCHIVE_SHA256="a422fc0ce3ee59a4b970ce1c5e8849ac9d6940be4a431960e13f7181f0e955e7"' in script
    assert 'OPENCV_EXPECTED_TREE_SHA256="d5d748793ff5357e36932a1c2e851df4ef68575c97653128ef67279b0b22d570"' in script
    assert 'OPENCV_CONTRIB_EXPECTED_ARCHIVE_SHA256="3fc521a16314978de02d5b33e657a09a9567429d5801d3fb94e35581ea44d729"' in script
    assert 'OPENCV_CONTRIB_EXPECTED_TREE_SHA256="920a1c5aaaa62f7b5110b85043cc4120079e5a5af9865fab59208cce6259f7bd"' in script
    assert 'cmake -S "$OPENCV_SOURCE_DIR" -B "$OPENCV_BUILD_DIR"' in script
    assert 'OPENCV_DOWNLOAD_PATH="$OPENCV_DOWNLOAD_DIR"' in script
    assert "assert_opencv_sources_unchanged" in script
    assert "git clone" not in script
    assert "git checkout" not in script
    assert 'OPENCV_ALLOW_TEMP_SWAP="${OPENCV_ALLOW_TEMP_SWAP:-0}"' in script
    assert 'OPENCV_ALLOW_TEMP_SWAP=1 bash scripts/setup/build-opencv.sh' in script
    assert "export PYTHONDONTWRITEBYTECODE=1" in script


def test_opencv_builder_prevents_python_imports_from_mutating_source(tmp_path):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    module_root = tmp_path / "source"
    package = module_root / "pixeagle_build_probe"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    env = os.environ.copy()
    env.update({"BUILDER": str(builder), "MODULE_ROOT": str(module_root)})

    result = subprocess.run(
        [
            "bash",
            "-c",
            r'''
set -euo pipefail
source "$BUILDER"
trap - EXIT
PYTHONPATH="$MODULE_ROOT" python3 -c 'import pixeagle_build_probe; assert pixeagle_build_probe.VALUE == 1'
[[ ! -e "$MODULE_ROOT/pixeagle_build_probe/__pycache__" ]]
''',
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_opencv_git_ignores_inherited_command_scoped_configuration(tmp_path):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    work_root = tmp_path / "work"
    for relative in ("git-home", "git-config", "hooks-disabled", "empty-template"):
        (work_root / relative).mkdir(parents=True)
    command = f'''
set -euo pipefail
source "{builder}"
trap - EXIT
OPENCV_WORK_ROOT="$1"
OPENCV_HOOKS_DIR="$1/hooks-disabled"
OPENCV_EMPTY_TEMPLATE_DIR="$1/empty-template"
export GIT_CONFIG_PARAMETERS="'core.attributesFile'='/tmp/injected-attributes'"
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=core.pager
export GIT_CONFIG_VALUE_0=forbidden-pager
if opencv_git config --get core.attributesFile; then exit 41; fi
if opencv_git config --get core.pager; then exit 42; fi
'''
    result = subprocess.run(
        ["bash", "-c", command, "test", str(work_root)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_opencv_builder_low_memory_swap_is_fail_closed_by_default():
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    command = f"""
set -euo pipefail
source {builder}
free() {{
    printf '%s\n' \
        '              total        used        free      shared  buff/cache   available' \
        'Mem:           2048         256        1024           0         768        1792' \
        'Swap:             0           0           0'
}}
OPENCV_ALLOW_TEMP_SWAP=0
if ensure_build_memory; then
    exit 41
fi
[[ -z "$TEMP_SWAP_FILE" ]]
"""
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "explicitly allow a temporary file" in result.stdout


def test_opencv_builder_temp_swap_uses_private_descriptor_not_predictable_path(
    tmp_path,
):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    swap_dir = tmp_path / "swap"
    swap_dir.mkdir()
    victim = tmp_path / "victim"
    victim.write_text("do-not-touch", encoding="utf-8")
    legacy_path = swap_dir / ".opencv_build_swap_12345"
    legacy_path.symlink_to(victim)

    env = os.environ.copy()
    env.update(
        {
            "BUILDER": str(builder),
            "SWAP_DIR": str(swap_dir),
            "LEGACY_PATH": str(legacy_path),
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            """
set -euo pipefail
source "$BUILDER"
create_temp_swap_backing_file "$SWAP_DIR"
[[ "$TEMP_SWAP_FILE" != "$LEGACY_PATH" ]]
[[ "$TEMP_SWAP_FILE" -ef "$TEMP_SWAP_FD_PATH" ]]
[[ -f "$TEMP_SWAP_FD_PATH" ]]
[[ "$(stat -Lc '%u:%a:%h' "$TEMP_SWAP_FD_PATH")" == "$(id -u):600:1" ]]
created="$TEMP_SWAP_FILE"
cleanup_temp_swap
[[ ! -e "$created" ]]
[[ -z "$TEMP_SWAP_FILE" && -z "$TEMP_SWAP_FD" && -z "$TEMP_SWAP_FD_PATH" ]]
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert legacy_path.is_symlink()
    assert victim.read_text(encoding="utf-8") == "do-not-touch"


def test_opencv_archive_export_is_private_bounded_and_detects_mutation(tmp_path):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    env = os.environ.copy()
    env.update({"BUILDER": str(builder)})
    result = subprocess.run(
        [
            "bash",
            "-c",
            r"""
set -euo pipefail
source "$BUILDER"
trap - EXIT
create_opencv_work_root
archive="$OPENCV_WORK_ROOT/archives/safe.tar"
python3 - "$archive" <<'PY'
import io
import sys
import tarfile

with tarfile.open(sys.argv[1], "w") as archive:
    directory = tarfile.TarInfo("module")
    directory.type = tarfile.DIRTYPE
    directory.mode = 0o755
    archive.addfile(directory)
    payload = b"int main() { return 0; }\n"
    source = tarfile.TarInfo("module/source.cpp")
    source.size = len(payload)
    source.mode = 0o644
    archive.addfile(source, io.BytesIO(payload))
PY
validate_and_extract_opencv_archive "$archive" "$OPENCV_SOURCE_DIR"
before="$(opencv_source_tree_digest "$OPENCV_SOURCE_DIR")"
printf poison >> "$OPENCV_SOURCE_DIR/module/source.cpp"
after="$(opencv_source_tree_digest "$OPENCV_SOURCE_DIR")"
[[ "$before" != "$after" ]]
assert_opencv_work_root
remove_opencv_work_root
[[ "$OPENCV_WORK_CLEANUP_STATUS" == removed ]]
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_opencv_archive_rejects_escaping_symlink_and_preserves_victim(tmp_path):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    victim = tmp_path / "victim"
    victim.write_text("preserve", encoding="utf-8")
    env = os.environ.copy()
    env.update({"BUILDER": str(builder), "VICTIM": str(victim)})
    result = subprocess.run(
        [
            "bash",
            "-c",
            r"""
set -euo pipefail
source "$BUILDER"
trap - EXIT
create_opencv_work_root
archive="$OPENCV_WORK_ROOT/archives/hostile.tar"
python3 - "$archive" <<'PY'
import sys
import tarfile

with tarfile.open(sys.argv[1], "w") as archive:
    link = tarfile.TarInfo("escape")
    link.type = tarfile.SYMTYPE
    link.linkname = "../../victim"
    archive.addfile(link)
PY
if validate_and_extract_opencv_archive "$archive" "$OPENCV_SOURCE_DIR"; then
    exit 9
fi
remove_opencv_work_root
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert victim.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize(
    "hostile_kind",
    ["absolute", "parent", "hardlink", "fifo", "duplicate", "oversized"],
)
def test_opencv_archive_rejects_unsupported_or_unbounded_entries(
    tmp_path, hostile_kind
):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    archive_path = tmp_path / f"{hostile_kind}.tar"
    with tarfile.open(archive_path, "w") as archive:
        if hostile_kind in {"absolute", "parent"}:
            payload = b"unsafe"
            member = tarfile.TarInfo(
                "/absolute" if hostile_kind == "absolute" else "../parent"
            )
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
        elif hostile_kind == "hardlink":
            member = tarfile.TarInfo("hardlink")
            member.type = tarfile.LNKTYPE
            member.linkname = "target"
            archive.addfile(member)
        elif hostile_kind == "fifo":
            member = tarfile.TarInfo("fifo")
            member.type = tarfile.FIFOTYPE
            archive.addfile(member)
        elif hostile_kind == "duplicate":
            for _ in range(2):
                member = tarfile.TarInfo("duplicate")
                member.type = tarfile.DIRTYPE
                archive.addfile(member)
        else:
            member = tarfile.TarInfo("oversized")
            member.size = 1_000_000_001
            archive.addfile(member)

    env = os.environ.copy()
    env.update({"BUILDER": str(builder), "ARCHIVE": str(archive_path)})
    result = subprocess.run(
        [
            "bash",
            "-c",
            r"""
set -euo pipefail
source "$BUILDER"
trap - EXIT
create_opencv_work_root
if validate_and_extract_opencv_archive "$ARCHIVE" "$OPENCV_SOURCE_DIR"; then
    exit 9
fi
[[ ! -e "$OPENCV_SOURCE_DIR" && ! -L "$OPENCV_SOURCE_DIR" ]]
remove_opencv_work_root
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_opencv_backup_cleanup_refuses_replaced_path_and_preserves_victim(tmp_path):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    victim = tmp_path / "victim"
    victim.mkdir()
    marker = victim / "marker"
    marker.write_text("preserve", encoding="utf-8")
    env = os.environ.copy()
    env.update({"BUILDER": str(builder), "VICTIM": str(victim)})
    result = subprocess.run(
        [
            "bash",
            "-c",
            r"""
set -euo pipefail
source "$BUILDER"
trap - EXIT
OPENCV_BACKUP_DIR="$(mktemp -d /var/tmp/pixeagle-opencv-backup.XXXXXX)"
chmod 0700 -- "$OPENCV_BACKUP_DIR"
OPENCV_BACKUP_IDENTITY="$(stat -Lc '%d:%i:%u:%a' -- "$OPENCV_BACKUP_DIR")"
original="${OPENCV_BACKUP_DIR}.original"
mv -- "$OPENCV_BACKUP_DIR" "$original"
ln -s -- "$VICTIM" "$OPENCV_BACKUP_DIR"
if remove_opencv_backup_dir; then
    exit 9
fi
[[ -f "$VICTIM/marker" ]]
rm -- "$OPENCV_BACKUP_DIR"
rm -rf -- "$original"
OPENCV_BACKUP_DIR=""
OPENCV_BACKUP_IDENTITY=""
""",
        ],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_opencv_rollback_restores_wheel_owned_runtime_libraries(
    tmp_path,
    opencv_backup_dir,
):
    builder = PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh"
    venv_dir = tmp_path / "venv"
    site_packages = venv_dir / "lib" / "python3.12" / "site-packages"
    backup_dir = opencv_backup_dir
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
OPENCV_BACKUP_IDENTITY="$(stat -Lc '%d:%i:%u:%a' -- "$TEST_BACKUP")"
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
