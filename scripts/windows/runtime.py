#!/usr/bin/env python3
"""Owned native-Windows lifecycle for the PixEagle Core local-lab preview."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Iterator, Sequence

import psutil
import yaml


STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 256 * 1024
DEFAULT_START_TIMEOUT_SECONDS = 45.0
PROCESS_CREATE_TIME_TOLERANCE_SECONDS = 0.05
PROJECT_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(WINDOWS_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(WINDOWS_SCRIPT_DIRECTORY))
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from lifecycle_lock import (  # noqa: E402
    LifecycleLockError,
    lifecycle_lock,
    lifecycle_lock_path,
)
from classes.browser_user_store import (  # noqa: E402
    BrowserUserStore,
    BrowserUserStoreError,
    validate_required_invariants,
)

STATE_DIRECTORY = PROJECT_ROOT / ".pixeagle_runtime" / "windows"
STATE_FILE = STATE_DIRECTORY / "runtime.json"
LIFECYCLE_LOCK_FILE = lifecycle_lock_path(PROJECT_ROOT)
CONFIG_FILE = PROJECT_ROOT / "configs" / "config.yaml"
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "configs" / "config_default.yaml"
DEFAULT_BROWSER_USER_FILE = (
    PROJECT_ROOT / "configs" / "secrets" / "demo-browser-users.json"
)
SECURE_FILE_ACL = PROJECT_ROOT / "scripts" / "windows" / "secure-file.ps1"
DASHBOARD_DIRECTORY = PROJECT_ROOT / "dashboard"
DASHBOARD_ENV_FILE = DASHBOARD_DIRECTORY / ".env"
DASHBOARD_CONTRACT = PROJECT_ROOT / "scripts" / "lib" / "dashboard_contract.js"
MAIN_SCRIPT = PROJECT_ROOT / "src" / "main.py"
RUNTIME_LOG_ROOT = PROJECT_ROOT / "logs" / "runtime"


class RuntimeContractError(RuntimeError):
    """Raised when lifecycle safety or readiness cannot be established."""


def _is_windows() -> bool:
    return os.name == "nt" and platform.system() == "Windows"


def _require_supported_host() -> None:
    if not _is_windows():
        raise RuntimeContractError("native Windows runtime commands require Windows")
    if os.environ.get("PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS") != "1":
        raise RuntimeContractError(
            "set PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1 after reviewing "
            "docs/WINDOWS_SETUP.md"
        )
    machine = platform.machine().strip().lower()
    interpreter_bits = struct.calcsize("P") * 8
    if machine not in {"amd64", "x86_64"} or interpreter_bits != 64:
        raise RuntimeContractError(
            "the Windows Core preview requires an x64 interpreter "
            f"(detected {machine or 'unknown'}, {interpreter_bits}-bit)"
        )
    if sys.version_info[:2] not in {(3, 11), (3, 12)}:
        raise RuntimeContractError(
            "the Windows Core preview requires CPython 3.11 or 3.12"
        )


def _normalize_path(value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(Path(value).resolve(strict=False))))


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_state() -> dict[str, Any] | None:
    if not STATE_FILE.exists():
        return None
    if STATE_FILE.is_symlink() or not STATE_FILE.is_file():
        raise RuntimeContractError("Windows runtime receipt is not a regular file")
    if STATE_FILE.stat().st_size > MAX_STATE_BYTES:
        raise RuntimeContractError("Windows runtime receipt exceeds its size bound")
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeContractError(f"Windows runtime receipt is unreadable: {exc}") from exc
    if not isinstance(state, dict) or state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise RuntimeContractError("Windows runtime receipt schema is invalid")
    receipt_root = state.get("project_root")
    if (
        not isinstance(receipt_root, str)
        or not receipt_root.strip()
        or _normalize_path(receipt_root) != _normalize_path(PROJECT_ROOT)
    ):
        raise RuntimeContractError("Windows runtime receipt belongs to another checkout")
    components = state.get("components")
    if not isinstance(components, list) or len(components) > 8:
        raise RuntimeContractError("Windows runtime receipt component inventory is invalid")
    return state


@contextlib.contextmanager
def _runtime_lock(timeout_seconds: float = 15.0) -> Iterator[None]:
    try:
        with lifecycle_lock(PROJECT_ROOT, timeout_seconds=timeout_seconds):
            yield
    except LifecycleLockError as exc:
        raise RuntimeContractError(str(exc)) from exc


def _read_yaml_config() -> dict[str, Any]:
    path = CONFIG_FILE if CONFIG_FILE.is_file() else DEFAULT_CONFIG_FILE
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise RuntimeContractError(f"cannot load runtime config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeContractError(f"runtime config must be a mapping: {path}")
    return value


def _read_dashboard_env() -> dict[str, str]:
    if not DASHBOARD_ENV_FILE.is_file():
        raise RuntimeContractError(
            "dashboard/.env is missing; run scripts\\init.bat before starting"
        )
    result: dict[str, str] = {}
    for line_number, raw in enumerate(
        DASHBOARD_ENV_FILE.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeContractError(
                f"dashboard/.env:{line_number}: expected NAME=value"
            )
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise RuntimeContractError(
                f"dashboard/.env:{line_number}: variable name is empty"
            )
        result[key] = value.strip().strip('"')
    return result


def _parse_port(value: Any, label: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeContractError(f"{label} must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeContractError(f"{label} must be between 1 and 65535")
    return port


def _loopback_host(value: Any, label: str) -> str:
    host = str(value or "").strip().lower()
    if host == "localhost" or host == "::1" or host.startswith("127."):
        return str(value).strip()
    raise RuntimeContractError(
        f"{label} must stay on loopback for the Windows Core preview (found {value!r})"
    )


def _validate_browser_session_user_file(value: Any) -> Path:
    raw_path = str(value or "").strip()
    if not raw_path:
        raise RuntimeContractError(
            "Streaming.API_SESSION_USER_FILE is required for the Windows Core preview"
        )
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve(strict=False)
    if _normalize_path(path) != _normalize_path(DEFAULT_BROWSER_USER_FILE):
        raise RuntimeContractError(
            "Streaming.API_SESSION_USER_FILE must use the Windows preview "
            "credential store created by scripts\\init.bat"
        )
    _enforce_browser_credential_acl(path)
    try:
        snapshot = BrowserUserStore(path).load_snapshot()
        validate_required_invariants(
            snapshot.records,
            require_enabled_admin=True,
        )
    except BrowserUserStoreError as exc:
        raise RuntimeContractError(
            f"Windows dashboard credential store is invalid: {exc}"
        ) from exc
    return path


def _enforce_browser_credential_acl(path: Path) -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell or not SECURE_FILE_ACL.is_file():
        raise RuntimeContractError(
            "Windows owner-only credential ACL helper is unavailable; "
            "rerun scripts\\init.bat"
        )
    for target, is_directory in ((path.parent, True), (path, False)):
        command = [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SECURE_FILE_ACL),
            "-Path",
            str(target),
        ]
        if is_directory:
            command.append("-Directory")
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeContractError(
                f"Windows dashboard credential ACL validation failed for {target}"
                + (f": {detail}" if detail else "")
            )


def _runtime_settings() -> dict[str, Any]:
    config = _read_yaml_config()
    video_source = config.get("VideoSource")
    streaming = config.get("Streaming")
    if not isinstance(video_source, dict):
        raise RuntimeContractError("config is missing the VideoSource section")
    if not isinstance(streaming, dict):
        raise RuntimeContractError("config is missing the Streaming section")
    dashboard = _read_dashboard_env()

    backend_host = _loopback_host(
        streaming.get("HTTP_STREAM_HOST", "127.0.0.1"),
        "Streaming.HTTP_STREAM_HOST",
    )
    if str(streaming.get("API_EXPOSURE_MODE", "local_only")) != "local_only":
        raise RuntimeContractError(
            "Streaming.API_EXPOSURE_MODE must be local_only for the Windows Core preview"
        )
    if str(streaming.get("API_AUTH_MODE", "local_compat")) != "browser_session":
        raise RuntimeContractError(
            "Streaming.API_AUTH_MODE must be browser_session for the Windows Core preview"
        )
    session_user_file = _validate_browser_session_user_file(
        streaming.get("API_SESSION_USER_FILE")
    )
    if streaming.get("ENABLE_STREAMING", True) is not True:
        raise RuntimeContractError(
            "Streaming.ENABLE_STREAMING must be true for the Windows Core preview"
        )
    if str(video_source.get("VIDEO_SOURCE_TYPE", "")).upper() != "VIDEO_FILE":
        raise RuntimeContractError(
            "VideoSource.VIDEO_SOURCE_TYPE must be VIDEO_FILE for the Windows Core preview"
        )
    video_path_value = str(
        video_source.get("VIDEO_FILE_PATH", "resources/test4.mp4")
    ).strip()
    if not video_path_value:
        raise RuntimeContractError(
            "VideoSource.VIDEO_FILE_PATH is empty for the Windows Core preview"
        )
    video_path = Path(video_path_value)
    if not video_path.is_absolute():
        video_path = PROJECT_ROOT / video_path
    video_path = video_path.resolve(strict=False)
    if video_path.is_symlink() or not video_path.is_file():
        raise RuntimeContractError(
            f"Windows Core preview video file is unavailable: {video_path}"
        )
    dashboard_host = _loopback_host(
        dashboard.get("HOST", "127.0.0.1"),
        "dashboard HOST",
    )
    return {
        "backend_host": backend_host,
        "backend_port": _parse_port(
            streaming.get("HTTP_STREAM_PORT", 5077),
            "Streaming.HTTP_STREAM_PORT",
        ),
        "session_user_file": str(session_user_file),
        "video_path": str(video_path),
        "dashboard_host": dashboard_host,
        "dashboard_port": _parse_port(dashboard.get("PORT", 3040), "dashboard PORT"),
    }


def _find_listener_pids(port: int) -> set[int]:
    listeners: set[int] = set()
    try:
        connections = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, OSError) as exc:
        raise RuntimeContractError(
            f"cannot verify ownership of TCP port {port}: {exc}"
        ) from exc
    for connection in connections:
        if (
            connection.status == psutil.CONN_LISTEN
            and connection.laddr
            and int(connection.laddr.port) == port
        ):
            if not connection.pid:
                raise RuntimeContractError(
                    f"TCP port {port} has a listener whose process identity "
                    "is unavailable; no process was terminated"
                )
            listeners.add(int(connection.pid))
    return listeners


def _process_identity_status(record: dict[str, Any]) -> tuple[str, str]:
    try:
        process = psutil.Process(int(record["pid"]))
        create_time = float(record["create_time"])
        if abs(process.create_time() - create_time) > PROCESS_CREATE_TIME_TOLERANCE_SECONDS:
            return "stale", "PID creation time changed"
        expected_executable = _normalize_path(record["executable"])
        actual_executable = _normalize_path(process.exe())
        if actual_executable != expected_executable:
            return "unknown", "live process executable does not match the receipt"
        expected_anchor = str(record.get("command_anchor") or "")
        if expected_anchor:
            actual_arguments = [_normalize_path(value) for value in process.cmdline()[1:]]
            if _normalize_path(expected_anchor) not in actual_arguments:
                return (
                    "unknown",
                    "live process command line does not match the receipt",
                )
        return "owned", "owned"
    except (KeyError, TypeError, ValueError):
        return "unknown", "receipt fields are invalid"
    except psutil.NoSuchProcess:
        return "stale", "process exited"
    except (psutil.AccessDenied, OSError) as exc:
        return "unknown", f"process identity unavailable: {exc}"


def _process_matches(record: dict[str, Any]) -> tuple[bool, str]:
    status, detail = _process_identity_status(record)
    return status == "owned", detail


def _classify_state(state: dict[str, Any] | None) -> list[dict[str, Any]]:
    if state is None:
        return []
    result = []
    for raw in state["components"]:
        if not isinstance(raw, dict):
            result.append(
                {
                    "name": "invalid",
                    "owned": False,
                    "identity_status": "unknown",
                    "detail": "invalid receipt",
                }
            )
            continue
        identity_status, detail = _process_identity_status(raw)
        result.append(
            {
                **raw,
                "owned": identity_status == "owned",
                "identity_status": identity_status,
                "detail": detail,
            }
        )
    return result


def _state_has_live_components(classified: Sequence[dict[str, Any]]) -> bool:
    return any(bool(record.get("owned")) for record in classified)


def _state_has_unknown_components(classified: Sequence[dict[str, Any]]) -> bool:
    return any(record.get("identity_status") == "unknown" for record in classified)


def _remove_fully_stale_state(
    state: dict[str, Any] | None,
    classified: Sequence[dict[str, Any]],
) -> bool:
    if state is None:
        return False
    if not classified:
        STATE_FILE.unlink(missing_ok=True)
        return True
    if _state_has_unknown_components(classified):
        raise RuntimeContractError(
            "Windows runtime receipt contains an unverifiable live identity; "
            "the receipt was preserved and no process was terminated"
        )
    if _state_has_live_components(classified):
        return False
    STATE_FILE.unlink(missing_ok=True)
    return True


def _dashboard_build_ready(node_executable: str) -> None:
    if not DASHBOARD_CONTRACT.is_file():
        raise RuntimeContractError("dashboard contract helper is missing")
    completed = subprocess.run(
        [
            node_executable,
            str(DASHBOARD_CONTRACT),
            "build-complete",
            str(DASHBOARD_DIRECTORY),
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeContractError(
            "dashboard production build is incomplete; run scripts\\init.bat"
            + (f" ({detail})" if detail else "")
        )


def _component_record(
    *,
    name: str,
    process: subprocess.Popen[bytes],
    command: Sequence[str],
    command_anchor: str | Path | None,
    log_path: Path,
) -> dict[str, Any]:
    inspected = psutil.Process(process.pid)
    return {
        "name": name,
        "pid": process.pid,
        "create_time": inspected.create_time(),
        "executable": _normalize_path(command[0]),
        "command_anchor": (
            _normalize_path(command_anchor) if command_anchor is not None else ""
        ),
        "log_path": str(log_path),
    }


def _spawn_component(
    *,
    name: str,
    command: Sequence[str],
    command_anchor: str | Path | None,
    environment: dict[str, str],
    log_directory: Path,
) -> tuple[subprocess.Popen[bytes], dict[str, Any]]:
    log_path = log_directory / f"windows-{name}.log"
    log_stream = log_path.open("ab", buffering=0)
    creation_flags = 0
    if os.name == "nt":
        creation_flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    try:
        process = subprocess.Popen(
            list(command),
            cwd=PROJECT_ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creation_flags,
        )
        record = _component_record(
            name=name,
            process=process,
            command=command,
            command_anchor=command_anchor,
            log_path=log_path,
        )
        return process, record
    finally:
        log_stream.close()


def _wait_for_http(
    url: str,
    process: subprocess.Popen[bytes],
    deadline: float,
    label: str,
) -> None:
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeContractError(
                f"{label} exited during startup with code {process.returncode}"
            )
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if 200 <= response.status < 400:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.25)
    raise RuntimeContractError(f"{label} readiness failed at {url}")


def _terminate_record(record: dict[str, Any], timeout_seconds: float = 8.0) -> bool:
    owned, _detail = _process_matches(record)
    if not owned:
        return False
    root = psutil.Process(int(record["pid"]))
    try:
        descendants = root.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        descendants = []
    targets = [*reversed(descendants), root]
    for process in targets:
        try:
            process.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _gone, alive = psutil.wait_procs(targets, timeout=timeout_seconds)
    for process in alive:
        try:
            process.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(alive, timeout=2.0)
    return True


def _stop_state(state: dict[str, Any] | None) -> tuple[int, list[str]]:
    classified = _classify_state(state)
    unknown = [
        f"{record.get('name', 'unknown')}: {record.get('detail', 'unverifiable')}"
        for record in classified
        if record.get("identity_status") == "unknown"
    ]
    if unknown:
        return 1, [
            "runtime identity is unverifiable; receipt preserved and no process terminated",
            *unknown,
        ]

    stopped: list[str] = []
    stale: list[str] = []
    for record in reversed(classified):
        name = str(record.get("name", "unknown"))
        if record.get("identity_status") == "stale":
            stale.append(f"{name}: {record.get('detail', 'stale')}")
            continue
        if _terminate_record(record):
            stopped.append(name)
    remaining = _classify_state(state)
    if _state_has_unknown_components(remaining):
        return 1, [
            *stopped,
            "runtime identity became unverifiable; receipt preserved",
        ]
    if _state_has_live_components(remaining):
        return 1, [*stopped, "one or more owned processes did not stop"]
    STATE_FILE.unlink(missing_ok=True)
    if stale and not stopped:
        return 0, ["stale receipt removed; no process was terminated", *stale]
    return 0, stopped


def _preflight_ports(ports: dict[str, int]) -> None:
    conflicts = {
        name: (port, _find_listener_pids(port))
        for name, port in ports.items()
    }
    active = {
        name: (port, pids)
        for name, (port, pids) in conflicts.items()
        if pids
    }
    if active:
        details = "; ".join(
            f"{name} {port} owned by PID(s) {','.join(map(str, sorted(pids)))}"
            for name, (port, pids) in active.items()
        )
        raise RuntimeContractError(
            f"required port conflict: {details}. PixEagle did not terminate any process"
        )


def _publish_starting_state(
    run_id: str,
    components: list[dict[str, Any]],
    log_directory: Path,
) -> dict[str, Any]:
    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "project_root": str(PROJECT_ROOT),
        "run_id": run_id,
        "status": "starting",
        "started_at": time.time(),
        "log_directory": str(log_directory),
        "components": components,
    }
    _atomic_write_json(STATE_FILE, state)
    return state


def _start_locked(args: argparse.Namespace) -> int:
    state = _load_state()
    classified = _classify_state(state)
    if _state_has_live_components(classified):
        names = ", ".join(
            str(item["name"]) for item in classified if item.get("owned")
        )
        raise RuntimeContractError(f"PixEagle is already running ({names})")
    _remove_fully_stale_state(state, classified)

    settings = _runtime_settings()
    venv_python = Path(sys.executable).resolve()
    if venv_python.parent.name.lower() != "scripts":
        raise RuntimeContractError(
            "runtime controller must execute with the PixEagle virtual environment"
        )
    if _normalize_path(venv_python.parent.parent) not in {
        _normalize_path(PROJECT_ROOT / ".venv"),
        _normalize_path(PROJECT_ROOT / "venv"),
        _normalize_path(os.environ.get("PIXEAGLE_VENV_DIR", PROJECT_ROOT / ".venv")),
    }:
        raise RuntimeContractError("runtime controller is using an unrelated Python environment")

    node_executable = shutil.which("node")
    if not node_executable:
        raise RuntimeContractError("Node.js is unavailable; run scripts\\init.bat")
    _dashboard_build_ready(node_executable)
    serve_script = DASHBOARD_DIRECTORY / "node_modules" / "serve" / "build" / "main.js"
    if not serve_script.is_file():
        raise RuntimeContractError("dashboard serve dependency is missing; run scripts\\init.bat")
    if not MAIN_SCRIPT.is_file():
        raise RuntimeContractError(f"backend entry point is missing: {MAIN_SCRIPT}")

    components_to_start: list[
        tuple[str, list[str], str | Path | None, str, int]
    ] = []
    ports = {
        "backend": settings["backend_port"],
        "dashboard": settings["dashboard_port"],
    }
    components_to_start.extend(
        [
            (
                "backend",
                [str(venv_python), str(MAIN_SCRIPT)],
                MAIN_SCRIPT,
                settings["backend_host"],
                settings["backend_port"],
            ),
            (
                "dashboard",
                [
                    node_executable,
                    str(serve_script),
                    "-s",
                    str(DASHBOARD_DIRECTORY / "build"),
                    "-l",
                    (
                        f"tcp://{settings['dashboard_host']}:"
                        f"{settings['dashboard_port']}"
                    ),
                ],
                serve_script,
                settings["dashboard_host"],
                settings["dashboard_port"],
            ),
        ]
    )
    _preflight_ports(ports)

    run_id = f"pixeagle_windows_{uuid.uuid4()}"
    log_directory = RUNTIME_LOG_ROOT / run_id
    log_directory.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    environment.update(
        {
            "PIXEAGLE_RUN_ID": run_id,
            "PIXEAGLE_RUNTIME_MODE": "windows",
            "PIXEAGLE_PROJECT_ROOT": str(PROJECT_ROOT),
            "PIXEAGLE_RUNTIME_LOG_DIR": str(RUNTIME_LOG_ROOT),
            "PYTHONUNBUFFERED": "1",
        }
    )

    records: list[dict[str, Any]] = []
    _publish_starting_state(run_id, records, log_directory)
    deadline = time.monotonic() + float(args.timeout)
    try:
        for name, command, anchor, host, port in components_to_start:
            process, record = _spawn_component(
                name=name,
                command=command,
                command_anchor=anchor,
                environment=environment,
                log_directory=log_directory,
            )
            records.append(record)
            _publish_starting_state(run_id, records, log_directory)
            path = "/api/v1/auth/session" if name == "backend" else "/"
            _wait_for_http(
                f"http://{host}:{port}{path}",
                process,
                deadline,
                name,
            )
        state = _publish_starting_state(run_id, records, log_directory)
        state["status"] = "ready"
        state["ready_at"] = time.time()
        _atomic_write_json(STATE_FILE, state)
    except BaseException:
        _stop_state(_load_state())
        raise

    print("PixEagle Windows Core preview is ready")
    print(f"Dashboard: http://{settings['dashboard_host']}:{settings['dashboard_port']}")
    print(f"Backend:   http://{settings['backend_host']}:{settings['backend_port']}")
    print(f"Logs:      {log_directory}")
    print("PX4/MAVLink sidecars: not started (local bundled-video lab)")
    return 0


def _command_start(args: argparse.Namespace) -> int:
    _require_supported_host()
    with _runtime_lock():
        return _start_locked(args)


def _command_stop(_args: argparse.Namespace) -> int:
    _require_supported_host()
    with _runtime_lock():
        state = _load_state()
        if state is None:
            print("PixEagle Windows runtime is not running")
            return 0
        exit_code, details = _stop_state(state)
        for detail in details:
            print(detail)
        if exit_code == 0:
            print("PixEagle Windows runtime stopped")
        return exit_code


def _command_status(args: argparse.Namespace) -> int:
    _require_supported_host()
    with _runtime_lock():
        state = _load_state()
        classified = _classify_state(state)
        if not classified:
            _remove_fully_stale_state(state, classified)
            payload = {"status": "stopped", "components": []}
            if args.json:
                print(json.dumps(payload, sort_keys=True))
            elif not args.quiet:
                print("PixEagle Windows runtime: stopped")
            return 3
        payload = {
            "status": (
                "ready"
                if state is not None
                and state.get("status") == "ready"
                and all(item.get("owned") for item in classified)
                else "degraded"
            ),
            "run_id": state.get("run_id") if state else None,
            "log_directory": state.get("log_directory") if state else None,
            "components": [
                {
                    "name": item.get("name"),
                    "pid": item.get("pid"),
                    "owned": bool(item.get("owned")),
                    "detail": item.get("detail"),
                }
                for item in classified
            ],
        }
        if args.json:
            print(json.dumps(payload, sort_keys=True))
        elif not args.quiet:
            print(f"PixEagle Windows runtime: {payload['status']}")
            for item in payload["components"]:
                marker = "OK" if item["owned"] else "WARN"
                print(
                    f"[{marker}] {item['name']}: PID {item['pid']} "
                    f"({item['detail']})"
                )
            print(f"Logs: {payload['log_directory']}")
        return 0 if payload["status"] == "ready" else 4


def _command_restart(args: argparse.Namespace) -> int:
    _require_supported_host()
    with _runtime_lock():
        state = _load_state()
        if state is not None:
            exit_code, details = _stop_state(state)
            for detail in details:
                print(detail)
            if exit_code != 0:
                return exit_code
        return _start_locked(args)


def _command_logs(_args: argparse.Namespace) -> int:
    _require_supported_host()
    state = _load_state()
    if state is None:
        print("PixEagle Windows runtime has no active log receipt")
        return 3
    print(state.get("log_directory", ""))
    for component in state.get("components", []):
        print(f"{component.get('name')}: {component.get('log_path')}")
    return 0


def _add_start_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_START_TIMEOUT_SECONDS,
        help="startup readiness deadline in seconds",
    )


def _normalize_start_options(args: argparse.Namespace) -> None:
    if not 5.0 <= args.timeout <= 300.0:
        raise RuntimeContractError("--timeout must be between 5 and 300 seconds")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PixEagle native-Windows Core lifecycle controller",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="start and prove the local runtime")
    _add_start_options(start)
    start.set_defaults(handler=_command_start)

    stop = subparsers.add_parser("stop", help="stop only receipt-owned processes")
    stop.set_defaults(handler=_command_stop)

    status = subparsers.add_parser("status", help="inspect exact process ownership")
    status.add_argument("--json", action="store_true")
    status.add_argument("--quiet", action="store_true")
    status.set_defaults(handler=_command_status)

    restart = subparsers.add_parser("restart", help="owned stop followed by ready start")
    _add_start_options(restart)
    restart.set_defaults(handler=_command_restart)

    logs = subparsers.add_parser("logs", help="print active component log paths")
    logs.set_defaults(handler=_command_logs)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command in {"start", "restart"}:
            _normalize_start_options(args)
        return int(args.handler(args))
    except RuntimeContractError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("[ERROR] interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
