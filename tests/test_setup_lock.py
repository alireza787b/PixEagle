"""Executable policy tests for secure, non-leaking resource serialization."""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCK_HELPER = PROJECT_ROOT / "scripts" / "lib" / "setup_lock.sh"
SUPERVISOR = PROJECT_ROOT / "scripts" / "lib" / "setup_lock_supervisor.py"

pytestmark = [pytest.mark.unit]


def _run(
    script: str,
    *args: str,
    env: dict[str, str] | None = None,
    timeout: float = 20,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script, "test", *args],
        cwd=PROJECT_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _holder(script: str, *args: str) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        ["bash", "-c", script, "holder", *args],
        cwd=PROJECT_ROOT,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "ready"
    return process


def _release(process: subprocess.Popen[str]) -> None:
    assert process.stdin is not None
    process.stdin.write("release\n")
    process.stdin.flush()
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stdout + stderr


def _resource_lock_path(resource: Path) -> Path:
    result = _run(
        f"source {LOCK_HELPER}; pixeagle_resource_lock_path \"$1\"",
        str(resource),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return Path(result.stdout.strip())


def _prepare_resource_lock(resource: Path) -> Path:
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
lock_path="$(pixeagle_resource_lock_path "$1")"
pixeagle_prepare_setup_lock_file "$lock_path"
printf '%s\n' "$lock_path"
""",
        str(resource),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return Path(result.stdout.strip())


def _assert_process_gone(pid: int) -> None:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.02)
    pytest.fail(f"supervised descendant PID {pid} is still present")


def test_resource_identity_is_canonical_full_sha256_and_stable(tmp_path):
    resource = tmp_path / "deployment" / "venv"
    resource.mkdir(parents=True)
    alias = tmp_path / "venv-link"
    alias.symlink_to(resource, target_is_directory=True)
    script = f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_resource_lock_identity "$1"
pixeagle_resource_lock_path "$1"
"""
    first_env = os.environ.copy()
    first_env["TMPDIR"] = str(tmp_path / "ignored-one")
    second_env = os.environ.copy()
    second_env["TMPDIR"] = str(tmp_path / "ignored-two")

    first = _run(script, str(resource), env=first_env)
    second = _run(script, str(alias), env=second_env)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout
    canonical, lock_path = first.stdout.splitlines()
    assert canonical == str(resource.resolve())
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert lock_path == (
        f"/var/tmp/pixeagle-locks-{resource.stat().st_uid}/setup-{digest}.lock"
    )
    assert len(Path(lock_path).stem.removeprefix("setup-")) == 64

    implementation = LOCK_HELPER.read_text(encoding="utf-8") + SUPERVISOR.read_text(
        encoding="utf-8"
    )
    assert "cksum" not in implementation
    assert "id -u" not in implementation
    assert "TMPDIR" not in implementation


def test_nonexistent_resource_uses_canonical_nearest_existing_parent_owner(tmp_path):
    alias_parent = tmp_path / "alias-parent"
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    alias_parent.symlink_to(real_parent, target_is_directory=True)
    resource = alias_parent / "future" / "venv"

    result = _run(
        f"source {LOCK_HELPER}; pixeagle_resource_lock_identity \"$1\"; "
        f"pixeagle_resource_lock_path \"$1\"",
        str(resource),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    canonical, lock_path = result.stdout.splitlines()
    assert canonical == str(real_parent / "future" / "venv")
    assert Path(lock_path).parent.name == f"pixeagle-locks-{real_parent.stat().st_uid}"


def test_prepared_lock_storage_is_owner_controlled(tmp_path):
    resource = tmp_path / "resource"
    lock_path = _prepare_resource_lock(resource)
    directory = lock_path.parent

    directory_metadata = directory.lstat()
    lock_metadata = lock_path.lstat()
    assert directory.is_dir() and not directory.is_symlink()
    assert directory_metadata.st_uid == tmp_path.stat().st_uid
    assert directory_metadata.st_mode & 0o7777 == 0o700
    assert lock_path.is_file() and not lock_path.is_symlink()
    assert lock_metadata.st_uid == tmp_path.stat().st_uid
    assert lock_metadata.st_mode & 0o7777 == 0o600
    assert lock_metadata.st_nlink == 1


def test_exclusive_setup_lock_excludes_concurrent_process(tmp_path):
    holder = _holder(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_setup_lock "$1" holder 0 bash -c 'printf "ready\\n"; read -r _'
""",
        str(tmp_path),
    )

    contender = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_setup_lock "$1" contender 0 true
""",
        str(tmp_path),
    )
    assert contender.returncode != 0
    assert "timed out waiting" in contender.stderr
    _release(holder)


def test_shared_lock_blocks_exclusive_but_allows_another_reader(tmp_path):
    holder = _holder(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_shared_setup_lock "$1" runtime 0 bash -c 'printf "ready\\n"; read -r _'
""",
        str(tmp_path),
    )

    reader = _run(
        f"source {LOCK_HELPER}; pixeagle_run_with_shared_setup_lock \"$1\" read 0 true",
        str(tmp_path),
    )
    writer = _run(
        f"source {LOCK_HELPER}; pixeagle_run_with_setup_lock \"$1\" write 0 true",
        str(tmp_path),
    )

    assert reader.returncode == 0, reader.stdout + reader.stderr
    assert writer.returncode != 0
    assert "timed out waiting" in writer.stderr
    _release(holder)


def test_multiple_resources_are_acquired_in_stable_order_without_deadlock(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    holder = _holder(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_resource_locks exclusive holder 0 "$2" "$1" -- \
    bash -c 'printf "ready\\n"; read -r _'
""",
        str(first),
        str(second),
    )
    contender = _run(
        f"""
source {LOCK_HELPER}
pixeagle_run_with_resource_locks exclusive contender 0 "$1" "$2" -- true
""",
        str(first),
        str(second),
    )
    assert contender.returncode != 0
    assert "timed out waiting" in contender.stderr
    _release(holder)

    script = f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_resource_locks exclusive ordered 5 "$1" "$2" -- sleep 0.15
"""
    forward = subprocess.Popen(
        ["bash", "-c", script, "forward", str(first), str(second)],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    reverse = subprocess.Popen(
        ["bash", "-c", script, "reverse", str(second), str(first)],
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    forward_output = forward.communicate(timeout=10)
    reverse_output = reverse.communicate(timeout=10)
    assert forward.returncode == 0, "".join(forward_output)
    assert reverse.returncode == 0, "".join(reverse_output)


def test_exclusive_lease_records_exact_sorted_resource_set(tmp_path):
    first = tmp_path / "one"
    second = tmp_path / "two"
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_resource_locks exclusive exact-lease 0 "$2" "$1" -- \
    python3 - "$1" "$2" <<'PY'
import json
import os
import sys

expected_resources = {{os.path.realpath(value) for value in sys.argv[1:]}}
resource_set = json.loads(os.environ["PIXEAGLE_RESOURCE_LOCK_SET"])
state_path = os.environ["PIXEAGLE_RESOURCE_LOCK_STATE_PATH"]
with open(state_path, encoding="utf-8") as stream:
    lease = json.load(stream)
assert lease["version"] == 2
assert lease["mode"] == "exclusive"
assert lease["resource_set"] == resource_set
assert lease["lock_paths"] == sorted(lease["lock_paths"])
assert {{entry["resource_path"] for entry in resource_set}} == expected_resources
assert lease["state_path"] == state_path
assert str(lease["supervisor_pid"]) == os.environ["PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_PID"]
assert lease["supervisor_start_token"] == os.environ["PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_START_TOKEN"]
assert lease["session_id"] == os.getsid(0)
assert lease["token"] == os.environ["PIXEAGLE_RESOURCE_LOCK_TOKEN"]
PY
""",
        str(first),
        str(second),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_lifecycle_resource_precedes_resources_acquired_during_startup(tmp_path):
    source = tmp_path / "checkout"
    lifecycle = source / "scripts" / "lib" / "runtime_ownership.sh"
    venv = source / ".venv"
    lifecycle.parent.mkdir(parents=True)
    lifecycle.touch()
    venv.mkdir()
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_resource_locks exclusive lifecycle-order 0 \
    "$1" "$2" "$3" -- python3 - <<'PY'
import json
import os

resources = json.loads(os.environ["PIXEAGLE_RESOURCE_LOCK_SET"])
print(resources[0]["resource_path"])
PY
""",
        str(source),
        str(lifecycle),
        str(venv),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(result.stdout.strip()) == lifecycle.resolve()


def test_nested_exclusive_command_can_use_subsets_but_not_new_resources(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    outside = tmp_path / "outside"
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_resource_locks exclusive parent 0 "$1" "$2" -- bash -c '
    set -euo pipefail
    source "$1"
    pixeagle_run_with_resource_locks exclusive child-exclusive 0 "$2" -- true
    pixeagle_run_with_resource_locks shared child-shared 0 "$3" -- true
    if pixeagle_validate_resource_lock_context exclusive "$4"; then
        exit 9
    fi
' child {LOCK_HELPER} "$2" "$1" "$3"
""",
        str(first),
        str(second),
        str(outside),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "exact subset" in result.stderr


def test_nested_shared_command_cannot_escalate_to_exclusive(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_resource_locks shared parent 0 "$1" "$2" -- bash -c '
    set -euo pipefail
    source "$1"
    pixeagle_run_with_resource_locks shared child 0 "$2" -- true
    if pixeagle_run_with_resource_locks exclusive escalation 0 "$2" -- true; then
        exit 9
    fi
' child {LOCK_HELPER} "$1"
""",
        str(first),
        str(second),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "cannot escalate" in result.stderr


def test_shared_validation_rejects_context_that_omits_a_held_resource(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_resource_locks shared parent 0 "$1" "$2" -- \
    python3 - "{SUPERVISOR}" <<'PY'
import json
import os
import subprocess
import sys

supervisor = sys.argv[1]
held = json.loads(os.environ["PIXEAGLE_RESOURCE_LOCK_SET"])
forged = [held[0]]
environment = os.environ.copy()
environment["PIXEAGLE_RESOURCE_LOCK_SET"] = json.dumps(
    forged, sort_keys=True, separators=(",", ":")
)
environment["PIXEAGLE_ENVIRONMENT_LOCK_PATH"] = forged[0]["lock_path"]
environment["PIXEAGLE_ENVIRONMENT_LOCK_PATHS"] = json.dumps(
    [forged[0]["lock_path"]], separators=(",", ":")
)
validation = subprocess.run(
    [sys.executable, supervisor, "validate", "--mode", "shared",
     "--resource-path", forged[0]["resource_path"]],
    env=environment,
    text=True,
    capture_output=True,
    check=False,
)
assert validation.returncode != 0
assert "actual supervisor flock set" in validation.stderr
PY
""",
        str(first),
        str(second),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_nested_command_validates_without_inheriting_lock_descriptors(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_resource_locks exclusive parent 0 "$1" "$2" -- \
    python3 - "$1" "{LOCK_HELPER}" <<'PY'
import json
import os
import subprocess
import sys

locks = {{entry["lock_path"] for entry in json.loads(os.environ["PIXEAGLE_RESOURCE_LOCK_SET"])}}
for descriptor in os.listdir("/proc/self/fd"):
    try:
        target = os.path.realpath(f"/proc/self/fd/{{descriptor}}")
    except OSError:
        continue
    if target in locks:
        raise SystemExit(f"resource lock descriptor leaked as FD {{descriptor}}")
subprocess.run(
    ["bash", "-c", 'source "$1"; pixeagle_validate_resource_lock_context exclusive "$2"',
     "child", sys.argv[2], sys.argv[1]],
    check=True,
)
PY
""",
        str(first),
        str(second),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_forged_token_is_rejected(tmp_path):
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_setup_lock "$1" parent 0 bash -c '
    set -euo pipefail
    source "$1"
    PIXEAGLE_SETUP_LOCK_TOKEN="$(printf "0%.0s" {{1..64}})"
    export PIXEAGLE_SETUP_LOCK_TOKEN
    if pixeagle_acquire_setup_lock "$2" forged 0; then
        exit 9
    fi
' child {LOCK_HELPER} "$1"
""",
        str(tmp_path),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "context mismatch" in result.stderr


def test_forged_open_but_unlocked_descriptor_and_lease_are_rejected(tmp_path):
    resource = tmp_path / "resource"
    resource.mkdir()
    lock_path = _prepare_resource_lock(resource)
    state_path = Path(f"{lock_path}.state")
    token = "a" * 64
    forge = r'''
import json
import os
import sys

resource = os.path.realpath(sys.argv[1])
lock_path = sys.argv[2]
state_path = lock_path + ".state"
supervisor = sys.argv[3]
descriptor = os.open(lock_path, os.O_RDWR)
os.set_inheritable(descriptor, True)
pid = os.getpid()
session_id = os.getsid(0)
start_token = open(f"/proc/{pid}/stat", encoding="utf-8").read().rsplit(") ", 1)[1].split()[19]
resource_set = [{
    "resource_path": resource,
    "lock_path": lock_path,
    "owner_uid": os.stat(resource).st_uid,
}]
token = "a" * 64
lease = {
    "version": 2,
    "mode": "exclusive",
    "resource_set": resource_set,
    "lock_paths": [lock_path],
    "state_path": state_path,
    "token": token,
    "supervisor_pid": pid,
    "supervisor_start_token": start_token,
    "session_id": session_id,
    "operation": "forged",
}
state_fd = os.open(state_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.write(state_fd, (json.dumps(lease, sort_keys=True, separators=(",", ":")) + "\n").encode())
os.close(state_fd)
lock_paths = json.dumps([lock_path], separators=(",", ":"))
resource_json = json.dumps(resource_set, sort_keys=True, separators=(",", ":"))
environment = os.environ.copy()
environment.update({
    "PIXEAGLE_RESOURCE_LOCK_MODE": "exclusive",
    "PIXEAGLE_RESOURCE_LOCK_SET": resource_json,
    "PIXEAGLE_RESOURCE_LOCK_STATE_PATH": state_path,
    "PIXEAGLE_RESOURCE_LOCK_TOKEN": token,
    "PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_PID": str(pid),
    "PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_START_TOKEN": start_token,
    "PIXEAGLE_RESOURCE_LOCK_SESSION_ID": str(session_id),
    "PIXEAGLE_ENVIRONMENT_LOCK_MODE": "exclusive",
    "PIXEAGLE_ENVIRONMENT_LOCK_PATH": lock_path,
    "PIXEAGLE_ENVIRONMENT_LOCK_PATHS": lock_paths,
    "PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_PID": str(pid),
    "PIXEAGLE_ENVIRONMENT_LOCK_SUPERVISOR_START_TOKEN": start_token,
    "PIXEAGLE_ENVIRONMENT_LOCK_SESSION_ID": str(session_id),
    "PIXEAGLE_SETUP_LOCK_PATH": lock_path,
    "PIXEAGLE_SETUP_LOCK_STATE_PATH": state_path,
    "PIXEAGLE_SETUP_LOCK_TOKEN": token,
    "PIXEAGLE_SETUP_LOCK_SUPERVISOR_PID": str(pid),
    "PIXEAGLE_SETUP_LOCK_SUPERVISOR_START_TOKEN": start_token,
    "PIXEAGLE_SETUP_LOCK_SESSION_ID": str(session_id),
})
os.execve(
    sys.executable,
    [sys.executable, supervisor, "validate", "--mode", "exclusive", "--resource-path", resource],
    environment,
)
'''

    result = subprocess.run(
        [sys.executable, "-c", forge, str(resource), str(lock_path), str(SUPERVISOR)],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    state_path.unlink(missing_ok=True)

    assert result.returncode != 0
    assert "does not hold the expected exclusive flock" in result.stderr


def test_symlink_lock_is_refused(tmp_path):
    resource = tmp_path / "resource"
    lock_path = _resource_lock_path(resource)
    directory_result = _run(
        f"source {LOCK_HELPER}; pixeagle_prepare_setup_lock_directory \"$1\"",
        str(lock_path.parent),
    )
    assert directory_result.returncode == 0, directory_result.stderr
    target = tmp_path / "target"
    target.write_text("not a lock", encoding="utf-8")
    lock_path.symlink_to(target)
    try:
        result = _run(
            f"source {LOCK_HELPER}; pixeagle_run_with_setup_lock \"$1\" unsafe 0 true",
            str(resource),
        )
    finally:
        lock_path.unlink(missing_ok=True)

    assert result.returncode != 0
    assert "resource lock" in result.stderr


def test_hardlinked_lock_is_refused(tmp_path):
    resource = tmp_path / "resource"
    lock_path = _prepare_resource_lock(resource)
    alias = lock_path.with_name(f".{lock_path.name}.{uuid.uuid4().hex}.hardlink")
    os.link(lock_path, alias)
    try:
        result = _run(
            f"source {LOCK_HELPER}; pixeagle_run_with_setup_lock \"$1\" unsafe 0 true",
            str(resource),
        )
    finally:
        alias.unlink(missing_ok=True)

    assert result.returncode != 0
    assert "hard-linked" in result.stderr


@pytest.mark.parametrize("unsafe_kind", ["fifo", "mode"])
def test_unsafe_lock_type_or_mode_is_refused(tmp_path, unsafe_kind):
    resource = tmp_path / unsafe_kind
    if unsafe_kind == "fifo":
        lock_path = _resource_lock_path(resource)
        result = _run(
            f"source {LOCK_HELPER}; pixeagle_prepare_setup_lock_directory \"$1\"",
            str(lock_path.parent),
        )
        assert result.returncode == 0, result.stderr
        os.mkfifo(lock_path, 0o600)
    else:
        lock_path = _prepare_resource_lock(resource)
        lock_path.chmod(0o644)
    try:
        result = _run(
            f"source {LOCK_HELPER}; pixeagle_run_with_setup_lock \"$1\" unsafe 0 true",
            str(resource),
        )
    finally:
        lock_path.unlink(missing_ok=True)

    assert result.returncode != 0
    assert "refusing" in result.stderr


def test_supervisor_terminates_and_reaps_escaped_descendants_before_unlock(tmp_path):
    pid_file = tmp_path / "escaped.pid"
    resource = tmp_path / "resource"
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_setup_lock "$1" parent 0 python3 -c '
import subprocess
import sys
process = subprocess.Popen(
    ["sleep", "60"],
    start_new_session=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    close_fds=True,
)
with open(sys.argv[1], "w", encoding="utf-8") as stream:
    stream.write(str(process.pid))
' "$2"
""",
        str(resource),
        str(pid_file),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    background_pid = int(pid_file.read_text(encoding="utf-8"))
    _assert_process_gone(background_pid)
    contender = _run(
        f"source {LOCK_HELPER}; pixeagle_run_with_setup_lock \"$1\" next 0 true",
        str(resource),
    )
    assert contender.returncode == 0, contender.stdout + contender.stderr


def test_lifecycle_policy_preserves_detached_descendant_only_after_success(tmp_path):
    pid_file = tmp_path / "preserved.pid"
    resource = tmp_path / "lifecycle"
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_resource_lock_preserving_descendants \
    exclusive "$1" lifecycle-start 0 \
    python3 -c '
import subprocess
import sys
process = subprocess.Popen(
    ["sleep", "60"],
    start_new_session=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    close_fds=True,
)
with open(sys.argv[1], "w", encoding="utf-8") as stream:
    stream.write(str(process.pid))
' "$2"
""",
        str(resource),
        str(pid_file),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    background_pid = int(pid_file.read_text(encoding="utf-8"))
    try:
        os.kill(background_pid, 0)
        contender = _run(
            f"source {LOCK_HELPER}; "
            'pixeagle_run_with_resource_lock exclusive "$1" next 0 true',
            str(resource),
        )
        assert contender.returncode == 0, contender.stdout + contender.stderr
    finally:
        try:
            os.kill(background_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    _assert_process_gone(background_pid)


def test_lifecycle_policy_reaps_detached_descendant_when_command_fails(tmp_path):
    pid_file = tmp_path / "failed.pid"
    resource = tmp_path / "lifecycle"
    result = _run(
        f"""
source {LOCK_HELPER}
pixeagle_run_with_resource_lock_preserving_descendants \
    exclusive "$1" lifecycle-failure 0 \
    python3 -c '
import subprocess
import sys
process = subprocess.Popen(["sleep", "60"], start_new_session=True)
with open(sys.argv[1], "w", encoding="utf-8") as stream:
    stream.write(str(process.pid))
raise SystemExit(17)
' "$2"
""",
        str(resource),
        str(pid_file),
    )

    assert result.returncode == 17, result.stdout + result.stderr
    _assert_process_gone(int(pid_file.read_text(encoding="utf-8")))


def test_supervisor_forwards_termination_signal(tmp_path):
    marker = tmp_path / "signal.txt"
    supervisor_file = tmp_path / "supervisor.pid"
    process = _holder(
        f"""
set -euo pipefail
source {LOCK_HELPER}
pixeagle_run_with_setup_lock "$1" signal 0 python3 - "$2" "$3" <<'PY'
from pathlib import Path
import os
import signal
import sys

marker = Path(sys.argv[1])
Path(sys.argv[2]).write_text(
    os.environ["PIXEAGLE_RESOURCE_LOCK_SUPERVISOR_PID"], encoding="utf-8"
)
def terminate(_signum, _frame):
    marker.write_text("term", encoding="utf-8")
    raise SystemExit(0)
signal.signal(signal.SIGTERM, terminate)
print("ready", flush=True)
signal.pause()
PY
""",
        str(tmp_path / "resource"),
        str(marker),
        str(supervisor_file),
    )

    os.kill(int(supervisor_file.read_text(encoding="utf-8")), signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stdout + stderr
    assert marker.read_text(encoding="utf-8") == "term"


def test_exclusive_lease_is_removed_after_supervisor_exit(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_lock = _resource_lock_path(first)
    second_lock = _resource_lock_path(second)
    expected_state = Path(f"{sorted((first_lock, second_lock))[0]}.state")

    result = _run(
        f"""
source {LOCK_HELPER}
pixeagle_run_with_resource_locks exclusive once 0 "$1" "$2" -- true
""",
        str(first),
        str(second),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not expected_state.exists()
    assert not expected_state.is_symlink()


def test_existing_environment_entrypoints_keep_compatibility_api():
    exclusive_paths = [
        PROJECT_ROOT / "scripts" / "init.sh",
        PROJECT_ROOT / "scripts" / "setup" / "setup-pytorch.sh",
        PROJECT_ROOT / "scripts" / "setup" / "install-ai-deps.sh",
        PROJECT_ROOT / "scripts" / "setup" / "build-opencv.sh",
        PROJECT_ROOT / "scripts" / "setup" / "install-dlib.sh",
    ]
    for path in exclusive_paths:
        source = path.read_text(encoding="utf-8")
        assert "lib/setup_lock.sh" in source
        assert "pixeagle_acquire_setup_lock" in source
        assert "pixeagle_run_with_setup_lock" in source

    runtime_check = (
        PROJECT_ROOT / "scripts" / "setup" / "check-ai-runtime.sh"
    ).read_text(encoding="utf-8")
    assert "pixeagle_run_with_shared_setup_lock" in runtime_check
    assert "pixeagle_validate_shared_setup_lock_context" in runtime_check

    launcher = (PROJECT_ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")
    assert "lib/setup_lock.sh" in launcher
    assert "PIXEAGLE_SETUP_LOCK_SUPERVISOR" in launcher
    assert "--mode shared" in launcher
    assert "--resource-path" in launcher
    assert "pixeagle_run_with_resource_lock_preserving_descendants" in launcher
    assert "pixeagle_acquire_lifecycle_lock" not in launcher


def test_legacy_single_lock_path_cli_supports_environment_validation(tmp_path):
    result = _run(
        f"""
set -euo pipefail
source {LOCK_HELPER}
lock_path="$(pixeagle_setup_lock_path "$1")"
pixeagle_prepare_setup_lock_file "$lock_path"
python3 "$PIXEAGLE_SETUP_LOCK_SUPERVISOR" run \
    --mode shared --lock-path "$lock_path" --operation compatibility --timeout 0 -- \
    bash -c 'source "$1"; pixeagle_validate_shared_setup_lock_context "$2"' \
    child {LOCK_HELPER} "$1"
""",
        str(tmp_path / "resource"),
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.geteuid() != 0, reason="cross-UID execution requires root")
def test_root_updater_and_deployment_owner_converge_on_one_lock():
    runuser = shutil.which("runuser")
    if runuser is None:
        pytest.skip("runuser is unavailable")
    account = pwd.getpwnam("nobody")
    resource = Path("/var/tmp") / f"pixeagle-cross-uid-{uuid.uuid4().hex}"
    helper_dir = Path("/var/tmp") / f"pixeagle-cross-uid-helper-{uuid.uuid4().hex}"
    helper_dir.mkdir(mode=0o755)
    helper_copy = helper_dir / LOCK_HELPER.name
    supervisor_copy = helper_dir / SUPERVISOR.name
    shutil.copyfile(LOCK_HELPER, helper_copy)
    shutil.copyfile(SUPERVISOR, supervisor_copy)
    helper_copy.chmod(0o644)
    supervisor_copy.chmod(0o755)
    resource.mkdir(mode=0o700)
    os.chown(resource, account.pw_uid, account.pw_gid)
    script = f"source {helper_copy}; pixeagle_resource_lock_path \"$1\""
    holder: subprocess.Popen[str] | None = None
    try:
        root_result = _run(script, str(resource))
        owner_result = subprocess.run(
            [runuser, "-u", account.pw_name, "--", "bash", "-c", script, "owner", str(resource)],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        assert root_result.returncode == 0, root_result.stderr
        assert owner_result.returncode == 0, owner_result.stderr
        assert root_result.stdout == owner_result.stdout

        holder = _holder(
            f"""
source {helper_copy}
pixeagle_run_with_setup_lock "$1" root-holder 0 bash -c 'printf "ready\\n"; read -r _'
""",
            str(resource),
        )
        contender = subprocess.run(
            [
                runuser,
                "-u",
                account.pw_name,
                "--",
                "bash",
                "-c",
                f"source {helper_copy}; pixeagle_run_with_setup_lock \"$1\" owner 0 true",
                "owner",
                str(resource),
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        assert contender.returncode != 0
        assert "timed out waiting" in contender.stderr
        assert Path(root_result.stdout.strip()).stat().st_uid == account.pw_uid
        _release(holder)
        holder = None
    finally:
        if holder is not None and holder.poll() is None:
            _release(holder)
        if "root_result" in locals() and root_result.returncode == 0:
            Path(root_result.stdout.strip()).unlink(missing_ok=True)
        resource.rmdir()
        helper_copy.unlink(missing_ok=True)
        supervisor_copy.unlink(missing_ok=True)
        helper_dir.rmdir()


def test_supervisor_security_primitives_compile_and_are_standard_library():
    subprocess.run(
        ["python3", "-m", "py_compile", str(SUPERVISOR)],
        cwd=PROJECT_ROOT,
        check=True,
    )
    source = SUPERVISOR.read_text(encoding="utf-8")
    assert "hashlib.sha256" in source
    assert "os.O_NOFOLLOW" in source
    assert "os.O_CLOEXEC" in source
    assert "os.set_inheritable(descriptor, False)" in source
    assert "metadata.st_nlink != 1" in source
    assert "(opened.st_dev, opened.st_ino)" in source
    assert 'parts[2] != "FLOCK"' in source
    assert "os.setsid()" in source
    assert "PR_SET_CHILD_SUBREAPER" in source
