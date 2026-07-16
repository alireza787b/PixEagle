from pathlib import Path
import os
import pwd
import shlex
import shutil
import subprocess
import time
import uuid

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HELPER = PROJECT_ROOT / "scripts" / "lib" / "runtime_ownership.sh"
PIDFD_HELPER = PROJECT_ROOT / "scripts" / "lib" / "terminate_owned_process.py"


def _run_helper(
    command: str,
    *,
    env=None,
    helper: Path = HELPER,
    cwd: Path = PROJECT_ROOT,
):
    return subprocess.run(
        ["bash", "-c", f'source "{helper}"; {command}'],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _isolated_runtime_checkout(tmp_path: Path) -> Path:
    runtime_root = tmp_path / "PixEagle"
    for relative_path in (
        Path("scripts/run.sh"),
        Path("scripts/stop.sh"),
        Path("scripts/service/run.sh"),
        Path("scripts/service/utils.sh"),
        Path("scripts/lib/common.sh"),
        Path("scripts/lib/ports.sh"),
        Path("scripts/lib/runtime_ownership.sh"),
        Path("scripts/lib/terminate_owned_process.py"),
        Path("scripts/lib/setup_lock.sh"),
        Path("scripts/lib/setup_lock_supervisor.py"),
    ):
        destination = runtime_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative_path, destination)
    return runtime_root


@pytest.fixture
def isolated_runtime_env(tmp_path: Path):
    env = os.environ.copy()
    lock_dir = tmp_path / "locks"
    # Keep the tmux socket root short enough for Unix-domain socket limits while
    # still giving every test an isolated, disposable server namespace.
    tmux_dir = Path("/tmp") / f"pe-tmux-{uuid.uuid4().hex[:10]}"
    fake_bin = tmp_path / "bin"
    lock_dir.mkdir(exist_ok=True)
    tmux_dir.mkdir(mode=0o700)
    fake_bin.mkdir(exist_ok=True)
    fake_lsof = fake_bin / "lsof"
    fake_lsof.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    fake_lsof.chmod(0o755)
    env["TMPDIR"] = str(lock_dir)
    env["TMUX_TMPDIR"] = str(tmux_dir)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env.pop("TMUX", None)
    for key in (
        "PIXEAGLE_RESOURCE_LOCK_MODE",
        "PIXEAGLE_RESOURCE_LOCK_SET",
        "PIXEAGLE_RESOURCE_LOCK_STATE_PATH",
        "PIXEAGLE_RESOURCE_LOCK_TOKEN",
        "PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_PID",
        "PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_START_TOKEN",
        "PIXEAGLE_RESOURCE_LOCK_SESSION_ID",
        "PIXEAGLE_ENVIRONMENT_LOCK_MODE",
        "PIXEAGLE_ENVIRONMENT_LOCK_PATH",
        "PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_PID",
        "PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_START_TOKEN",
        "PIXEAGLE_ENVIRONMENT_LOCK_SESSION_ID",
        "PIXEAGLE_SETUP_LOCK_PATH",
        "PIXEAGLE_SETUP_LOCK_STATE_PATH",
        "PIXEAGLE_SETUP_LOCK_TOKEN",
        "PIXEAGLE_SETUP_LOCK_SUPERVISOR_PID",
        "PIXEAGLE_SETUP_LOCK_SUPERVISOR_START_TOKEN",
        "PIXEAGLE_SETUP_LOCK_SESSION_ID",
    ):
        env.pop(key, None)
    try:
        yield env
    finally:
        shutil.rmtree(tmux_dir, ignore_errors=True)


def _fake_process(proc_root: Path, pid: int, environment: dict[str, str]):
    process_dir = proc_root / str(pid)
    process_dir.mkdir(parents=True)
    payload = b"\0".join(
        f"{key}={value}".encode("utf-8") for key, value in environment.items()
    ) + b"\0"
    (process_dir / "environ").write_bytes(payload)


def _fake_process_stat(proc_root: Path, pid: int, start_token: int = 4242):
    process_dir = proc_root / str(pid)
    process_dir.mkdir(parents=True, exist_ok=True)
    fields_after_comm = ["S"] + ["0"] * 18 + [str(start_token)] + ["0"] * 5
    (process_dir / "stat").write_text(
        f"{pid} (test process) {' '.join(fields_after_comm)}\n",
        encoding="utf-8",
    )


def test_pid_ownership_requires_exact_project_marker(tmp_path):
    proc_root = tmp_path / "proc"
    _fake_process(proc_root, 123, {"PIXEAGLE_PROJECT_ROOT": str(PROJECT_ROOT)})
    env = os.environ.copy()
    env["PIXEAGLE_PROC_ROOT"] = str(proc_root)

    result = _run_helper(
        f'pixeagle_pid_is_owned 123 "{PROJECT_ROOT}"',
        env=env,
    )

    assert result.returncode == 0, result.stderr


def test_pid_ownership_rejects_prefix_and_missing_markers(tmp_path):
    proc_root = tmp_path / "proc"
    _fake_process(
        proc_root,
        123,
        {"PIXEAGLE_PROJECT_ROOT": f"{PROJECT_ROOT}-other"},
    )
    _fake_process(proc_root, 456, {"OTHER": "value"})
    env = os.environ.copy()
    env["PIXEAGLE_PROC_ROOT"] = str(proc_root)

    prefix = _run_helper(
        f'pixeagle_pid_is_owned 123 "{PROJECT_ROOT}"',
        env=env,
    )
    missing = _run_helper(
        f'pixeagle_pid_is_owned 456 "{PROJECT_ROOT}"',
        env=env,
    )

    assert prefix.returncode != 0
    assert missing.returncode != 0


def test_pid_ownership_supports_explicit_service_uid(tmp_path):
    proc_root = tmp_path / "proc"
    _fake_process(proc_root, 123, {"PIXEAGLE_PROJECT_ROOT": str(PROJECT_ROOT)})
    env = os.environ.copy()
    env["PIXEAGLE_PROC_ROOT"] = str(proc_root)

    result = _run_helper(
        f'pixeagle_pid_is_owned 123 "{PROJECT_ROOT}" "$(id -u)"',
        env=env,
    )

    assert result.returncode == 0, result.stderr


def test_owned_pid_inventory_returns_only_exact_marked_processes(tmp_path):
    proc_root = tmp_path / "proc"
    _fake_process(proc_root, 123, {"PIXEAGLE_PROJECT_ROOT": str(PROJECT_ROOT)})
    _fake_process(
        proc_root,
        456,
        {"PIXEAGLE_PROJECT_ROOT": f"{PROJECT_ROOT}-other"},
    )
    _fake_process(proc_root, 789, {"OTHER": "value"})
    env = os.environ.copy()
    env["PIXEAGLE_PROC_ROOT"] = str(proc_root)

    result = _run_helper(
        f'pixeagle_owned_pids "{PROJECT_ROOT}"',
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["123"]


def test_pid_ownership_can_require_runtime_mode_and_run_id(tmp_path):
    proc_root = tmp_path / "proc"
    _fake_process(
        proc_root,
        123,
        {
            "PIXEAGLE_PROJECT_ROOT": str(PROJECT_ROOT),
            "PIXEAGLE_RUNTIME_MODE": "manual",
            "PIXEAGLE_RUN_ID": "run-123",
        },
    )
    _fake_process_stat(proc_root, 123)
    env = os.environ.copy()
    env["PIXEAGLE_PROC_ROOT"] = str(proc_root)

    accepted = _run_helper(
        f'pixeagle_pid_is_owned 123 "{PROJECT_ROOT}" "$(id -u)" manual run-123',
        env=env,
    )
    wrong_mode = _run_helper(
        f'pixeagle_pid_is_owned 123 "{PROJECT_ROOT}" "$(id -u)" service run-123',
        env=env,
    )
    identity = _run_helper(
        f'pixeagle_pid_identity_is_unchanged 123 4242 "{PROJECT_ROOT}" '
        '"$(id -u)" manual run-123',
        env=env,
    )

    assert accepted.returncode == 0
    assert wrong_mode.returncode != 0
    assert identity.returncode == 0


def test_manual_and_service_tmux_sockets_are_distinct():
    result = _run_helper(
        f'manual=$(pixeagle_tmux_socket_name "{PROJECT_ROOT}" manual); '
        f'service=$(pixeagle_tmux_socket_name "{PROJECT_ROOT}" service); '
        '[[ "$manual" != "$service" ]]; printf "%s\n%s\n" "$manual" "$service"'
    )

    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 2


def test_tmux_session_lookup_is_exact_and_checks_all_identity_markers(
    tmp_path, isolated_runtime_env
):
    if shutil.which("tmux") is None:
        return
    runtime_root = _isolated_runtime_checkout(tmp_path)
    socket_name = f"pixeagle-test-{uuid.uuid4().hex}"
    helper = runtime_root / "scripts" / "lib" / "runtime_ownership.sh"
    command = f'''
set -uo pipefail
source "{helper}"
trap 'tmux -L "{socket_name}" kill-server 2>/dev/null || true' EXIT
tmux -L "{socket_name}" new-session -d -s pixeagle-other
if pixeagle_tmux_session_exists "{socket_name}" pixeagle; then exit 41; fi
tmux -L "{socket_name}" new-session -d -s pixeagle
tmux -L "{socket_name}" set-environment -t =pixeagle PIXEAGLE_PROJECT_ROOT "{runtime_root}"
tmux -L "{socket_name}" set-environment -t =pixeagle PIXEAGLE_RUNTIME_MODE manual
tmux -L "{socket_name}" set-environment -t =pixeagle PIXEAGLE_RUN_ID run-a
pixeagle_tmux_session_is_owned "{socket_name}" pixeagle "{runtime_root}" manual run-a
if pixeagle_tmux_session_is_owned "{socket_name}" pixeagle "{runtime_root}" service run-a; then exit 42; fi
if pixeagle_tmux_session_is_owned "{socket_name}" pixeagle "{runtime_root}" manual run-b; then exit 43; fi
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=runtime_root,
        env=isolated_runtime_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_default_tmux_lookup_ignores_inherited_tmux(tmp_path):
    if shutil.which("tmux") is None:
        return
    env = os.environ.copy()
    env["TMUX_TMPDIR"] = str(tmp_path)
    env.pop("TMUX", None)
    subprocess.run(
        ["tmux", "new-session", "-d", "-s", "default-server-session"],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        inherited = env.copy()
        inherited["TMUX"] = "/definitely/not/the/default/tmux/socket,1,0"
        result = _run_helper(
            "pixeagle_default_tmux list-sessions -F '#{session_name}'",
            env=inherited,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == ["default-server-session"]
    finally:
        subprocess.run(
            ["tmux", "kill-server"],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )


def test_legacy_migration_stops_a_signal_ignoring_verified_pane(
    tmp_path, isolated_runtime_env
):
    if shutil.which("tmux") is None:
        return
    runtime_root = _isolated_runtime_checkout(tmp_path)
    env = isolated_runtime_env.copy()
    env["TMUX"] = "/not/the/default/server,1,0"
    command = (
        "exec python3 -c \"import signal,time; "
        "signal.signal(signal.SIGINT, signal.SIG_IGN); "
        "signal.signal(signal.SIGHUP, signal.SIG_IGN); "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(120)\""
    )
    default_env = env.copy()
    default_env.pop("TMUX", None)
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            "pixeagle",
            "-c",
            str(runtime_root),
            command,
        ],
        env=default_env,
        check=True,
        capture_output=True,
        text=True,
    )
    pane_pid = int(
        subprocess.check_output(
            ["tmux", "list-panes", "-t", "pixeagle", "-F", "#{pane_pid}"],
            env=default_env,
            text=True,
        ).strip()
    )
    try:
        result = subprocess.run(
            [
                "bash",
                str(runtime_root / "scripts" / "stop.sh"),
                "--legacy-default-session",
                "--yes",
            ],
            cwd=runtime_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert not Path(f"/proc/{pane_pid}").exists()
        listed = subprocess.run(
            ["tmux", "has-session", "-t", "=pixeagle"],
            env=default_env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert listed.returncode != 0
    finally:
        subprocess.run(
            ["tmux", "kill-server"],
            env=default_env,
            check=False,
            capture_output=True,
            text=True,
        )


def test_runtime_entrypoints_use_non_leaking_resource_supervision():
    launcher = (PROJECT_ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")
    stopper = (PROJECT_ROOT / "scripts" / "stop.sh").read_text(encoding="utf-8")
    supervisor = (PROJECT_ROOT / "scripts" / "service" / "run.sh").read_text(
        encoding="utf-8"
    )

    combined = "\n".join((launcher, stopper, supervisor))
    assert "pixeagle_acquire_lifecycle_lock" not in combined
    assert "PIXEAGLE_LIFECYCLE_LOCK_FD" not in combined
    assert "pixeagle_run_with_resource_lock_preserving_descendants" in launcher
    assert "--internal-lifecycle-start" in launcher
    assert "pixeagle_run_with_resource_lock" in stopper
    assert "--internal-lifecycle-stop" in stopper
    assert 'bash "$RUN_SCRIPT" --no-attach' in supervisor
    assert 'bash "$STOP_SCRIPT" --mode service' in supervisor


def test_run_id_generator_is_collision_resistant_and_well_formed():
    result = _run_helper(
        "first=$(pixeagle_generate_run_id pixeagle_manual); "
        "second=$(pixeagle_generate_run_id pixeagle_manual); "
        '[[ "$first" != "$second" ]]; '
        '[[ "$first" =~ ^pixeagle_manual_[A-Fa-f0-9-]{32,36}$ ]]; '
        '[[ "$second" =~ ^pixeagle_manual_[A-Fa-f0-9-]{32,36}$ ]]; '
        'printf "%s\\n%s\\n" "$first" "$second"'
    )

    assert result.returncode == 0, result.stderr
    assert len(result.stdout.splitlines()) == 2


def test_run_id_validation_rejects_unbounded_or_shell_unsafe_values():
    result = _run_helper(
        "pixeagle_run_id_is_valid run-safe_123; "
        "if pixeagle_run_id_is_valid 'run unsafe'; then exit 41; fi; "
        "if pixeagle_run_id_is_valid '../run'; then exit 42; fi; "
        "too_long=$(printf 'x%.0s' {1..129}); "
        'if pixeagle_run_id_is_valid "$too_long"; then exit 43; fi'
    )

    assert result.returncode == 0, result.stderr


def test_systemd_runtime_channel_scrubber_removes_every_watchdog_key(tmp_path):
    marker = tmp_path / "scrubbed"
    env = os.environ.copy()
    env.update(
        {
            "NOTIFY_SOCKET": "/tmp/forbidden",
            "WATCHDOG_PID": "123",
            "WATCHDOG_USEC": "1000000",
            "WATCHDOG_FUTURE_CHANNEL": "forbidden",
            "PIXEAGLE_KEEP_ME": "kept",
        }
    )
    command = (
        "pixeagle_without_systemd_runtime_channels bash -c "
        + shlex.quote(
            f"printf '%s|%s|%s|%s|%s' "
            '"${NOTIFY_SOCKET-}" "${WATCHDOG_PID-}" '
            '"${WATCHDOG_USEC-}" "${WATCHDOG_FUTURE_CHANNEL-}" '
            f'"${{PIXEAGLE_KEEP_ME-}}" > {shlex.quote(str(marker))}'
        )
    )
    result = _run_helper(command, env=env)

    assert result.returncode == 0, result.stderr
    assert marker.read_text(encoding="utf-8") == "||||kept"


def test_launcher_can_publish_tmux_supervision_contract(
    tmp_path, isolated_runtime_env
):
    if shutil.which("tmux") is None:
        return
    runtime_root = _isolated_runtime_checkout(tmp_path)
    component = tmp_path / "component.sh"
    exec_wrapper = tmp_path / "runtime-log-exec.sh"
    marker = tmp_path / "component-started"
    notifier_marker = tmp_path / "component-systemd-environment"
    exec_wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "shift\n"
        "[[ ${1:-} == -- ]] && shift\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    exec_wrapper.chmod(0o755)
    component.write_text(
        "#!/usr/bin/env bash\n"
        f"printf started > {shlex.quote(str(marker))}\n"
        "lock_fd_state=closed\n"
        "for fd in /proc/$$/fd/*; do "
        "target=$(readlink -f \"$fd\" 2>/dev/null || true); "
        "[[ $target != /var/tmp/pixeagle-locks-*/*.lock ]] || lock_fd_state=inherited; "
        "done\n"
        "printf '%s|%s|%s|%s|%s|%s' \"${NOTIFY_SOCKET-}\" \"${WATCHDOG_PID-}\" "
        "\"${WATCHDOG_USEC-}\" \"${WATCHDOG_CUSTOM_CHANNEL-}\" "
        "\"${PIXEAGLE_RESOURCE_LOCK_MODE-}\" \"$lock_fd_state\" "
        f"> {shlex.quote(str(notifier_marker))}\n"
        "exec sleep 30\n",
        encoding="utf-8",
    )
    socket_name = f"pixeagle-launch-test-{uuid.uuid4().hex}"
    session_name = f"pixeagle-test-{uuid.uuid4().hex[:8]}"
    command = f'''
set -uo pipefail
export NOTIFY_SOCKET="/tmp/forbidden-notify-socket"
export WATCHDOG_PID="123"
export WATCHDOG_USEC="1000000"
export WATCHDOG_CUSTOM_CHANNEL="forbidden"
source "{runtime_root / 'scripts' / 'run.sh'}"
TMUX_SOCKET_NAME="{socket_name}"
SESSION_NAME="{session_name}"
PIXEAGLE_TMUX_SOCKET_NAME="$TMUX_SOCKET_NAME"
PIXEAGLE_SESSION_NAME="$SESSION_NAME"
PIXEAGLE_RUN_ID="run-test"
PIXEAGLE_RUNTIME_LOG_DIR="{tmp_path / 'runtime-logs'}"
RUN_MAIN_APP=true
RUN_MAVLINK2REST=false
RUN_DASHBOARD=false
RUN_MAVSDK_SERVER=false
MAIN_APP_SCRIPT="{component}"
RUNTIME_LOG_PIPE_TOOL="/nonexistent"
RUNTIME_LOG_EXEC_TOOL="{exec_wrapper}"
trap 'tmux -L "$TMUX_SOCKET_NAME" kill-server 2>/dev/null || true' EXIT
start_services
for _attempt in $(seq 1 50); do
[[ -f "{marker}" ]] && break
    sleep 0.1
done
[[ "$(cat "{marker}" 2>/dev/null || true)" == started ]]
[[ "$(cat "{notifier_marker}" 2>/dev/null || true)" == '||||shared|closed' ]]
pixeagle_tmux_session_is_owned "$TMUX_SOCKET_NAME" "$SESSION_NAME" \
    "{runtime_root}" manual run-test
[[ "$(tmux -L "$TMUX_SOCKET_NAME" show-window-options -v \
    -t "=$SESSION_NAME:0" remain-on-exit)" == on ]]
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=runtime_root,
        env=isolated_runtime_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_launcher_fails_readiness_and_does_not_keep_component_shells():
    source = (PROJECT_ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")

    assert "; bash\"" not in source
    assert "clear; $(component_wrapped_command" in source
    assert 'unset NOTIFY_SOCKET; unset \\\"\\${!WATCHDOG_@}\\\"; exec env' in source
    assert "strip_tmux_systemd_runtime_channels" in source
    assert 'set-window-option -t "=$SESSION_NAME:0" remain-on-exit on' in source
    assert "@pixeagle_component" in source
    assert "cleanup_failed_startup" in source
    assert "if ! wait_for_services" in source
    assert 'PIXEAGLE_PROJECT_ROOT="$project_root_arg"' not in source
    assert "PIXEAGLE_EXPECTED_COMPONENTS" in source
    assert 'PIXEAGLE_READY "1"' in source
    assert "PIXEAGLE_RUNTIME_MODE" in source
    assert "pixeagle_tmux_socket_name" in source
    assert "Launcher cleanup refused a mode-wide signal operation" in source


def test_launcher_refuses_mode_wide_orphan_cleanup(
    tmp_path, isolated_runtime_env
):
    runtime_root = _isolated_runtime_checkout(tmp_path)
    signal_marker = tmp_path / "signal-attempted"
    command = f'''
set -uo pipefail
source "{runtime_root / 'scripts' / 'run.sh'}"
pixeagle_tmux_session_exists() {{ return 1; }}
pixeagle_owned_pids() {{ printf '%s\n' 4242; }}
terminate_owned_pid() {{ printf signalled > "{signal_marker}"; }}
cleanup_previous_sessions
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=runtime_root,
        env=isolated_runtime_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "without an exact tmux run" in result.stdout
    assert not signal_marker.exists()


def test_generated_service_contract_uses_readiness_and_launcher_owned_lifecycle():
    utils_source = (PROJECT_ROOT / "scripts" / "service" / "utils.sh").read_text(
        encoding="utf-8"
    )
    supervisor_source = (PROJECT_ROOT / "scripts" / "service" / "run.sh").read_text(
        encoding="utf-8"
    )

    assert "Type=notify" in utils_source
    assert "NotifyAccess=all" in utils_source
    assert "Delegate=yes" in utils_source
    assert "ExecStop=" not in utils_source
    assert "KillMode=mixed" in utils_source
    assert "TimeoutStartSec=300" in utils_source
    assert "Group=$SERVICE_GROUP" in utils_source
    assert "systemd-notify --ready" in supervisor_source
    assert "notify_service_ready" in supervisor_source
    assert "pixeagle_without_systemd_runtime_channels" in supervisor_source
    assert "pixeagle_acquire_lifecycle_lock" not in supervisor_source
    assert 'bash "$RUN_SCRIPT" --no-attach' in supervisor_source
    assert 'bash "$STOP_SCRIPT" --mode service' in supervisor_source


def test_service_unit_is_verified_before_atomic_publication(tmp_path):
    if shutil.which("systemd-analyze") is None:
        pytest.skip("systemd-analyze is not installed")

    utils = PROJECT_ROOT / "scripts" / "service" / "utils.sh"
    service_file = tmp_path / "pixeagle.service"
    command = f'''
set -uo pipefail
source {shlex.quote(str(utils))}
detect_service_user() {{
    SERVICE_USER=$(id -un)
    SERVICE_GROUP=$(id -gn)
    SERVICE_HOME={shlex.quote(str(tmp_path))}
    USER_PIXEAGLE_DIR={shlex.quote(str(tmp_path))}
    SERVICE_RUN_SCRIPT=/bin/true
}}
SERVICE_FILE={shlex.quote(str(service_file))}
create_service_file
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert service_file.is_file()
    assert service_file.stat().st_mode & 0o777 == 0o644
    unit = service_file.read_text(encoding="utf-8")
    assert "ExecStart=/bin/true" in unit
    assert unit.count("Delegate=yes") == 1
    assert f"User={pwd.getpwuid(os.getuid()).pw_name}" in unit
    assert "User=root" not in unit
    assert "AmbientCapabilities=" not in unit
    assert "CapabilityBoundingSet=" not in unit
    assert not list(tmp_path.glob(".pixeagle.tmp.*"))


def test_service_unit_verify_failure_preserves_existing_file(tmp_path):
    utils = PROJECT_ROOT / "scripts" / "service" / "utils.sh"
    service_file = tmp_path / "pixeagle.service"
    service_file.write_text("existing-unit\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_verify = fake_bin / "systemd-analyze"
    fake_verify.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    fake_verify.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    command = f'''
set -uo pipefail
source {shlex.quote(str(utils))}
detect_service_user() {{
    SERVICE_USER=$(id -un)
    SERVICE_GROUP=$(id -gn)
    SERVICE_HOME={shlex.quote(str(tmp_path))}
    USER_PIXEAGLE_DIR={shlex.quote(str(tmp_path))}
    SERVICE_RUN_SCRIPT=/bin/true
}}
SERVICE_FILE={shlex.quote(str(service_file))}
if create_service_file; then exit 41; fi
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert service_file.read_text(encoding="utf-8") == "existing-unit\n"
    assert not list(tmp_path.glob(".pixeagle.tmp.*"))


def test_service_unit_generation_rejects_unsafe_path_before_write(tmp_path):
    utils = PROJECT_ROOT / "scripts" / "service" / "utils.sh"
    service_file = tmp_path / "pixeagle.service"
    command = f'''
set -uo pipefail
source {shlex.quote(str(utils))}
detect_service_user() {{
    SERVICE_USER=$(id -un)
    SERVICE_GROUP=$(id -gn)
    SERVICE_HOME={shlex.quote(str(tmp_path))}
    USER_PIXEAGLE_DIR={shlex.quote(str(tmp_path / 'unsafe path'))}
    SERVICE_RUN_SCRIPT=/bin/true
}}
SERVICE_FILE={shlex.quote(str(service_file))}
if create_service_file; then exit 41; fi
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "cannot contain whitespace" in result.stdout
    assert not service_file.exists()


def test_service_supervisor_does_not_retain_lifecycle_lock_while_monitoring():
    source = (PROJECT_ROOT / "scripts" / "service" / "run.sh").read_text(
        encoding="utf-8"
    )

    assert "pixeagle_acquire_lifecycle_lock" not in source
    assert "pixeagle_release_lifecycle_lock" not in source
    assert source.index("start_stack") < source.index("monitor_tmux_session")


def test_service_cli_fails_when_systemctl_succeeds_without_runtime_readiness():
    cli = PROJECT_ROOT / "scripts" / "service" / "cli.sh"
    command = f'''
set -euo pipefail
source "{cli}"
check_prerequisites() {{ return 0; }}
is_service_installed() {{ return 0; }}
service_active_state() {{ printf '%s\n' inactive; }}
runtime_run_id_for_mode() {{ printf '%s\\n' stale-run; }}
run_systemctl() {{ return 0; }}
wait_for_runtime_ready_for_mode() {{ return 1; }}
if start_command; then
    exit 42
fi
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "did not become ready" in result.stdout


def test_stop_script_never_signals_unowned_listener():
    source = (PROJECT_ROOT / "scripts" / "stop.sh").read_text(encoding="utf-8")

    start = source.index("terminate_owned_pid()")
    end = source.index("stop_marked_processes()", start)
    marked_termination = source[start:end]
    ownership_check = marked_termination.index(
        'pixeagle_pid_is_owned "$pid" "$PIXEAGLE_DIR"'
    )
    pidfd_termination = marked_termination.index("pixeagle_terminate_owned_pid")
    assert ownership_check < pidfd_termination
    assert 'kill -TERM "$pid"' not in marked_termination
    assert 'kill -KILL "$pid"' not in marked_termination
    assert "pixeagle_owned_pids" in source
    assert "--legacy-default-session" in source
    assert "legacy_session_matches_checkout" in source
    assert "Stop incomplete" in source


def _process_start_token(pid: int) -> str:
    line = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    return line.rsplit(") ", 1)[1].split()[19]


def test_pidfd_terminator_signals_only_exact_marked_process(tmp_path):
    project_root = tmp_path / "checkout"
    project_root.mkdir()
    run_id = "pixeagle_test_exact"
    environment = os.environ.copy()
    environment.update(
        {
            "PIXEAGLE_PROJECT_ROOT": str(project_root.resolve()),
            "PIXEAGLE_RUNTIME_MODE": "manual",
            "PIXEAGLE_RUN_ID": run_id,
        }
    )
    process = subprocess.Popen(["sleep", "60"], env=environment)
    try:
        result = subprocess.run(
            [
                "python3",
                str(PIDFD_HELPER),
                "--pid",
                str(process.pid),
                "--start-token",
                _process_start_token(process.pid),
                "--expected-uid",
                str(os.getuid()),
                "--project-root",
                str(project_root),
                "--runtime-mode",
                "manual",
                "--run-id",
                run_id,
                "--term-timeout",
                "1",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert process.wait(timeout=3) == -15
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)


def test_pidfd_terminator_refuses_mismatched_run_id(tmp_path):
    project_root = tmp_path / "checkout"
    project_root.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "PIXEAGLE_PROJECT_ROOT": str(project_root.resolve()),
            "PIXEAGLE_RUNTIME_MODE": "manual",
            "PIXEAGLE_RUN_ID": "pixeagle_test_actual",
        }
    )
    process = subprocess.Popen(["sleep", "60"], env=environment)
    try:
        result = subprocess.run(
            [
                "python3",
                str(PIDFD_HELPER),
                "--pid",
                str(process.pid),
                "--start-token",
                _process_start_token(process.pid),
                "--expected-uid",
                str(os.getuid()),
                "--project-root",
                str(project_root),
                "--runtime-mode",
                "manual",
                "--run-id",
                "pixeagle_test_other",
                "--term-timeout",
                "0",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 73
        assert "run ID does not match" in result.stderr
        assert process.poll() is None
    finally:
        process.kill()
        process.wait(timeout=3)


def test_runtime_health_rejects_stale_ready_marker_after_component_exit(
    tmp_path, isolated_runtime_env
):
    if shutil.which("tmux") is None:
        pytest.skip("tmux is unavailable")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    env = isolated_runtime_env.copy()
    socket_name = _run_helper(
        f'pixeagle_tmux_socket_name "{checkout}" manual', env=env, cwd=checkout
    ).stdout.strip()
    run_id = "pixeagle_health_test"
    try:
        subprocess.run(
            [
                "tmux",
                "-L",
                socket_name,
                "new-session",
                "-d",
                "-s",
                "pixeagle",
                "sleep 60",
            ],
            cwd=checkout,
            env=env,
            check=True,
        )
        subprocess.run(
            [
                "tmux",
                "-L",
                socket_name,
                "set-option",
                "-w",
                "-t",
                "=pixeagle:0",
                "remain-on-exit",
                "on",
            ],
            env=env,
            check=True,
        )
        for key, value in (
            ("PIXEAGLE_PROJECT_ROOT", str(checkout.resolve())),
            ("PIXEAGLE_RUNTIME_MODE", "manual"),
            ("PIXEAGLE_RUN_ID", run_id),
            ("PIXEAGLE_READY", "1"),
            ("PIXEAGLE_EXPECTED_COMPONENTS", "backend"),
        ):
            subprocess.run(
                ["tmux", "-L", socket_name, "set-environment", "-t", "=pixeagle", key, value],
                env=env,
                check=True,
            )
        subprocess.run(
            [
                "tmux",
                "-L",
                socket_name,
                "set-option",
                "-p",
                "-t",
                "=pixeagle:0.0",
                "@pixeagle_component",
                "backend",
            ],
            env=env,
            check=True,
        )
        healthy = _run_helper(
            f'pixeagle_tmux_runtime_is_healthy "{socket_name}" pixeagle "{checkout}" manual "{run_id}"',
            env=env,
            cwd=checkout,
        )
        assert healthy.returncode == 0, healthy.stdout + healthy.stderr

        subprocess.run(
            ["tmux", "-L", socket_name, "send-keys", "-t", "=pixeagle:0.0", "C-c"],
            env=env,
            check=True,
        )
        for _ in range(30):
            dead = subprocess.check_output(
                ["tmux", "-L", socket_name, "display-message", "-p", "-t", "=pixeagle:0.0", "#{pane_dead}"],
                env=env,
                text=True,
            ).strip()
            if dead == "1":
                break
            time.sleep(0.1)
        unhealthy = _run_helper(
            f'pixeagle_tmux_runtime_is_healthy "{socket_name}" pixeagle "{checkout}" manual "{run_id}"',
            env=env,
            cwd=checkout,
        )
        assert unhealthy.returncode != 0
    finally:
        subprocess.run(
            ["tmux", "-L", socket_name, "kill-server"],
            env=env,
            check=False,
            capture_output=True,
        )


def test_stop_refuses_owned_session_without_exact_run_id(
    tmp_path, isolated_runtime_env
):
    runtime_root = _isolated_runtime_checkout(tmp_path)
    env = isolated_runtime_env.copy()
    ownership_helper = runtime_root / "scripts" / "lib" / "runtime_ownership.sh"
    socket_name = _run_helper(
        f'pixeagle_tmux_socket_name "{runtime_root}" manual',
        env=env,
        helper=ownership_helper,
        cwd=runtime_root,
    ).stdout.strip()
    assert socket_name

    subprocess.run(
        ["tmux", "-L", socket_name, "new-session", "-d", "-s", "pixeagle"],
        cwd=runtime_root,
        env=env,
        check=True,
    )
    orphan_env = env.copy()
    orphan_env.update(
        {
            "PIXEAGLE_PROJECT_ROOT": str(runtime_root),
            "PIXEAGLE_RUNTIME_MODE": "manual",
            "PIXEAGLE_RUN_ID": "other-run",
        }
    )
    orphan = subprocess.Popen(["sleep", "120"], cwd=runtime_root, env=orphan_env)
    try:
        for key, value in (
            ("PIXEAGLE_PROJECT_ROOT", str(runtime_root)),
            ("PIXEAGLE_RUNTIME_MODE", "manual"),
        ):
            subprocess.run(
                [
                    "tmux",
                    "-L",
                    socket_name,
                    "set-environment",
                    "-t",
                    "=pixeagle",
                    key,
                    value,
                ],
                env=env,
                check=True,
            )

        result = subprocess.run(
            ["bash", str(runtime_root / "scripts" / "stop.sh"), "--mode", "manual"],
            cwd=runtime_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0
        assert "without an exact run identity" in result.stdout
        still_present = subprocess.run(
            ["tmux", "-L", socket_name, "has-session", "-t", "=pixeagle"],
            env=env,
            check=False,
        )
        assert still_present.returncode == 0
        assert orphan.poll() is None
    finally:
        subprocess.run(
            ["tmux", "-L", socket_name, "kill-server"],
            env=env,
            check=False,
            capture_output=True,
        )
        orphan.terminate()
        try:
            orphan.wait(timeout=5)
        except subprocess.TimeoutExpired:
            orphan.kill()
            orphan.wait(timeout=5)


def test_launcher_serializes_yaml_booleans_for_shell_comparisons(
    tmp_path, isolated_runtime_env
):
    runtime_root = _isolated_runtime_checkout(tmp_path)
    config_file = tmp_path / "config.yaml"
    config_file.write_text("PX4:\n  EXTERNAL_MAVSDK_SERVER: true\n", encoding="utf-8")
    command = f'''
source "{runtime_root / 'scripts' / 'run.sh'}"
VENV_DIR="{PROJECT_ROOT / '.venv'}"
CONFIG_FILE="{config_file}"
DEFAULT_CONFIG_FILE="{config_file}"
[[ "$(get_config_value PX4 EXTERNAL_MAVSDK_SERVER false)" == true ]]
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=runtime_root,
        env=isolated_runtime_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_wait_for_services_returns_failure_for_unready_owned_component(
    tmp_path, isolated_runtime_env
):
    runtime_root = _isolated_runtime_checkout(tmp_path)
    command = f'''
source "{runtime_root / "scripts" / "run.sh"}"
RUN_MAVLINK2REST=false
RUN_MAIN_APP=true
RUN_DASHBOARD=false
RUN_MAVSDK_SERVER=false
BACKEND_PORT=5077
PIXEAGLE_BACKEND_READY_RETRIES=1
check_port_ready() {{ return 1; }}
tmux_has_dead_component() {{ return 1; }}
sleep() {{ :; }}
wait_for_services
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=runtime_root,
        env=isolated_runtime_env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Backend failed readiness" in result.stdout



def test_service_cli_propagates_systemctl_failures():
    cli = PROJECT_ROOT / "scripts" / "service" / "cli.sh"
    command = f'''
set -euo pipefail
source "{cli}"
check_prerequisites() {{ return 0; }}
is_service_installed() {{ return 0; }}
service_active_state() {{ printf '%s\n' active; }}
is_tmux_session_active_for_mode() {{ return 1; }}
run_systemctl() {{ return 23; }}
if start_command; then exit 41; fi
if stop_command; then exit 42; fi
if restart_command; then exit 43; fi
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "systemd failed to start" in result.stdout
    assert "systemd failed to stop" in result.stdout
    assert "systemd failed to restart" in result.stdout


def test_installed_disabled_service_never_falls_back_to_unmanaged_runtime(tmp_path):
    cli = PROJECT_ROOT / "scripts" / "service" / "cli.sh"
    systemctl_marker = tmp_path / "systemctl"
    unmanaged_marker = tmp_path / "unmanaged"
    command = f'''
set -euo pipefail
source "{cli}"
check_prerequisites() {{ return 0; }}
is_service_installed() {{ return 0; }}
service_active_state() {{ printf '%s\n' inactive; }}
service_enabled_state() {{ printf '%s\n' disabled; }}
runtime_run_id_for_mode() {{ return 1; }}
run_systemctl() {{ printf '%s\n' "$*" > "{systemctl_marker}"; }}
wait_for_runtime_ready_for_mode() {{ return 0; }}
start_unmanaged_stack() {{ touch "{unmanaged_marker}"; return 0; }}
start_command
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert systemctl_marker.read_text(encoding="utf-8").strip() == "start pixeagle.service"
    assert not unmanaged_marker.exists()


def test_service_state_query_failure_is_fail_closed(tmp_path):
    cli = PROJECT_ROOT / "scripts" / "service" / "cli.sh"
    mutation_marker = tmp_path / "mutation"
    command = f'''
set -euo pipefail
source "{cli}"
check_prerequisites() {{ return 0; }}
is_service_installed() {{ return 0; }}
service_active_state() {{ return 2; }}
run_systemctl() {{ touch "{mutation_marker}"; }}
start_unmanaged_stack() {{ touch "{mutation_marker}"; }}
if start_command; then exit 41; fi
if stop_command; then exit 42; fi
if restart_command; then exit 43; fi
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not mutation_marker.exists()
    assert "Could not determine pixeagle.service state" in result.stdout


def test_service_removal_refuses_unknown_state_without_mutation(tmp_path):
    utils = PROJECT_ROOT / "scripts" / "service" / "utils.sh"
    service_file = tmp_path / "pixeagle.service"
    service_file.write_text("keep\n", encoding="utf-8")
    mutation_marker = tmp_path / "systemctl-mutation"
    command = f'''
set -euo pipefail
source "{utils}"
SERVICE_FILE="{service_file}"
have_systemd() {{ return 0; }}
service_load_state() {{ printf '%s\n' loaded; }}
service_active_state() {{ return 2; }}
systemctl() {{ touch "{mutation_marker}"; }}
if remove_service; then exit 41; fi
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert service_file.read_text(encoding="utf-8") == "keep\n"
    assert not mutation_marker.exists()
    assert "service active state" in result.stdout


def test_service_removal_stops_disables_and_reloads_before_deleting(tmp_path):
    utils = PROJECT_ROOT / "scripts" / "service" / "utils.sh"
    service_file = tmp_path / "pixeagle.service"
    service_file.write_text("remove\n", encoding="utf-8")
    actions = tmp_path / "actions"
    command = f'''
set -euo pipefail
source "{utils}"
SERVICE_FILE="{service_file}"
have_systemd() {{ return 0; }}
service_load_state() {{ printf '%s\n' loaded; }}
service_active_state() {{
    if [[ -f "{actions}" ]] && grep -q '^stop ' "{actions}"; then
        printf '%s\n' inactive
    else
        printf '%s\n' active
    fi
}}
service_enabled_state() {{
    if [[ -f "{actions}" ]] && grep -q '^disable ' "{actions}"; then
        printf '%s\n' disabled
    else
        printf '%s\n' enabled
    fi
}}
systemctl() {{ printf '%s\n' "$*" >> "{actions}"; }}
remove_service
'''
    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not service_file.exists()
    assert actions.read_text(encoding="utf-8").splitlines() == [
        "stop pixeagle.service",
        "disable pixeagle.service",
        "daemon-reload",
    ]


def test_public_service_uninstall_keeps_wrapper_when_removal_contract_fails(tmp_path):
    installer = PROJECT_ROOT / "scripts" / "service" / "install.sh"
    wrapper = tmp_path / "pixeagle-service"
    wrapper.write_text("keep\n", encoding="utf-8")
    failing_utils = tmp_path / "utils.sh"
    failing_utils.write_text(
        "remove_service() { return 42; }\n", encoding="utf-8"
    )
    command = f'''
set -euo pipefail
source "{installer}"
INSTALL_PATH="{wrapper}"
UTILS_SCRIPT="{failing_utils}"
if uninstall_service; then exit 41; fi
'''

    result = subprocess.run(
        ["bash", "-c", command],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert wrapper.read_text(encoding="utf-8") == "keep\n"
    source = installer.read_text(encoding="utf-8")
    assert "systemctl is-active" not in source
    assert "systemctl is-enabled" not in source
    assert "remove_service || return 1" in source


def test_service_supervisor_rejects_removed_or_replaced_component_panes():
    source = (PROJECT_ROOT / "scripts" / "service" / "run.sh").read_text(
        encoding="utf-8"
    )

    assert "PIXEAGLE_EXPECTED_COMPONENTS" in source
    assert "actual_components" in source
    assert 'if [ "$actual_components" != "$expected_components" ]' in source
    assert "PIXEAGLE_RUN_ID" in source
    assert "PIXEAGLE_TMUX_SOCKET_NAME" in source
