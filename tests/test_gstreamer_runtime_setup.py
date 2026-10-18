"""Optional media installation uses one path and never mutates the Core provider."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/setup/reconcile-gstreamer-runtime.sh"


def executable(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env bash\nset -eu\n" + source)
    path.chmod(0o755)


@pytest.fixture
def sandbox(tmp_path):
    commands = tmp_path / "bin"
    commands.mkdir()
    venv = tmp_path / "venv"
    log = tmp_path / "commands.log"
    ready = tmp_path / "ready"
    bindings = tmp_path / "bindings"
    executable(venv / "bin/python", '''
case "$*" in
    *check-native-media-runtime.py*)
        echo '{"runtime_ready":false}'
        [[ "${ALWAYS_FAIL_PROBE:-0}" != 1 ]] || exit 1
        [[ -f "$READY" || -f "$TEST_VENV/lib/gstreamer-1.0/libgstrsrtp.so" ]] ;;
    '-c import gi') [[ -f "$BINDINGS" ]] ;;
    *sys.version_info*) echo 3.12 ;;
    *sys.prefix*) echo "$TEST_VENV" ;;
    '-m pip install '*)
        echo "pip $*" >> "$COMMANDS"
        if [[ "${FAIL_PIP:-0}" == 1 ]]; then
            echo changed > "$TEST_VENV/working-opencv-provider"
            exit 1
        fi
        touch "$BINDINGS" "$READY" ;;
    *) exit 3 ;;
esac
''')
    executable(commands / "sudo", '''
if [[ "$*" == '-n -v' ]]; then exit 0; fi
[[ "${1:-}" != '-n' ]] || shift
exec "$@"
''')
    executable(commands / "dpkg-query", "exit 1\n")
    executable(commands / "apt-cache", '[[ "${PACKAGE_AVAILABLE:-0}" == 1 ]]\n')
    executable(commands / "apt-get", '''
echo "apt-get $*" >> "$COMMANDS"
[[ "${FAIL_APT:-0}" != 1 ]] || exit 1
if [[ "${PREPARE_AT_APT:-1}" == 1 ]]; then touch "$READY"; fi
''')
    executable(commands / "gst-inspect-1.0", '[[ -f "$READY" ]]\n')
    executable(commands / "rustc", 'echo "rustc ${TEST_RUST_VERSION:-1.75.0}"\n')
    executable(commands / "git", '''
echo "git $*" >> "$COMMANDS"
if [[ "$*" == *'rev-parse HEAD' ]]; then echo cdec77cad2d9b7348d800507bc6eeec5039717eb; fi
''')
    executable(commands / "cargo", '''
echo "cargo $*" >> "$COMMANDS"
mkdir -p "$CARGO_TARGET_DIR/release"
echo fixture > "$CARGO_TARGET_DIR/release/libgstrsrtp.so"
''')
    env = {**os.environ, "PATH": f"{commands}:{os.environ['PATH']}", "NO_COLOR": "1",
           "PIXEAGLE_VENV_DIR": str(venv), "PIXEAGLE_NONINTERACTIVE": "1",
           "COMMANDS": str(log), "READY": str(ready), "BINDINGS": str(bindings),
           "TEST_VENV": str(venv), "XDG_CACHE_HOME": str(tmp_path / "cache")}
    return env, log, ready, bindings, venv


def run(sandbox, *arguments):
    return subprocess.run(["bash", str(SCRIPT), *arguments], env=sandbox[0],
                          text=True, capture_output=True, check=False)


def test_verify_only_and_preview_never_install_or_build(sandbox):
    assert run(sandbox, "--verify-only").returncode == 1
    preview = run(sandbox, "--dry-run")
    assert preview.returncode == 0
    assert "Cargo --locked" in preview.stdout
    assert not sandbox[1].exists()


def test_ready_runtime_is_reused_without_package_changes(sandbox):
    sandbox[2].touch()
    result = run(sandbox)
    assert result.returncode == 0, result.stderr
    assert "reusing" in result.stdout
    assert not sandbox[1].exists()


def test_missing_runtime_installs_ice_and_typelibs_without_touching_opencv(sandbox):
    sandbox[3].touch()
    result = run(sandbox)
    assert result.returncode == 0, result.stderr
    commands = sandbox[1].read_text()
    assert "gstreamer1.0-nice" in commands
    assert "gir1.2-gst-plugins-bad-1.0" in commands
    assert "cargo" not in commands and "pip" not in commands
    assert "opencv" not in commands


def test_missing_python_bindings_are_isolated_to_selected_interpreter(sandbox):
    result = run(sandbox)
    assert result.returncode == 0, result.stderr
    commands = sandbox[1].read_text()
    assert "python3.12-dev" in commands
    assert "requirements-gstreamer.txt" in commands
    assert "system-site-packages" not in commands
    assert "opencv" not in commands


def test_package_failure_does_not_remove_working_provider(sandbox):
    sandbox[0]["FAIL_APT"] = "1"
    sentinel = sandbox[4] / "working-opencv-provider"
    sentinel.write_text("preserved")
    assert run(sandbox).returncode != 0
    assert sentinel.read_text() == "preserved"
    assert "cargo" not in sandbox[1].read_text()


def test_source_plugin_build_is_pinned_locked_and_installed_inside_venv(sandbox):
    sandbox[0]["PREPARE_AT_APT"] = "0"
    sandbox[3].touch()
    result = run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    commands = sandbox[1].read_text()
    assert "cdec77cad2d9b7348d800507bc6eeec5039717eb" in commands
    assert "cargo build --locked --release --jobs 2" in commands
    assert "-p gst-plugin-rtp" in commands
    assert (sandbox[4] / "lib/gstreamer-1.0/libgstrsrtp.so").read_text() == "fixture\n"
    assert not list(Path(sandbox[0]["XDG_CACHE_HOME"]).rglob("source.*"))
    before = commands
    assert run(sandbox).returncode == 0
    assert sandbox[1].read_text() == before


def test_unsupported_distro_compiler_leaves_fallback_without_installing_rustup(sandbox):
    sandbox[0].update(PREPARE_AT_APT="0", TEST_RUST_VERSION="1.63.0")
    sandbox[3].touch()
    result = run(sandbox)
    assert result.returncode == 1
    assert "Browser WebRTC and JPEG remain available" in result.stdout
    assert "cargo build" not in sandbox[1].read_text()
    assert not (sandbox[4] / "lib/gstreamer-1.0").exists()


def test_core_requirements_do_not_install_optional_bindings():
    core = (ROOT / "requirements-core.txt").read_text()
    assert "requirements-gstreamer" not in core
    assert "PyGObject" not in core
    initializer = (ROOT / "scripts/init.sh").read_text()
    builder = (ROOT / "scripts/setup/build-opencv.sh").read_text()
    updater = (ROOT / "scripts/update.sh").read_text()
    assert "reconcile-gstreamer-runtime.sh" in initializer
    assert "reconcile-gstreamer-runtime.sh" in builder
    assert 'PIXEAGLE_SETUP_ACTION=update-repair bash "$INIT_SCRIPT"' in updater


def test_partial_binding_failure_rolls_back_prior_python_environment(sandbox):
    sandbox[0]["FAIL_PIP"] = "1"
    sentinel = sandbox[4] / "working-opencv-provider"
    sentinel.write_text("preserved")
    result = run(sandbox)
    assert result.returncode != 0
    assert sentinel.read_text() == "preserved"
    assert not list(sandbox[4].parent.glob(".pixeagle-venv-backup.*"))


def test_failed_native_plugin_verification_restores_prior_plugin(sandbox):
    sandbox[0].update(PREPARE_AT_APT="0", ALWAYS_FAIL_PROBE="1")
    sandbox[3].touch()
    plugin = sandbox[4] / "lib/gstreamer-1.0/libgstrsrtp.so"
    plugin.parent.mkdir(parents=True)
    plugin.write_text("prior-plugin")
    result = run(sandbox)
    assert result.returncode != 0
    assert "incomplete" in result.stdout
    assert plugin.read_text() == "prior-plugin"
    assert not list(Path(sandbox[0]["XDG_CACHE_HOME"]).rglob("source.*"))
