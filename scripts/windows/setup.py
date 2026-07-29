#!/usr/bin/env python3
"""Idempotent setup for the native Windows x64 Core local-lab preview."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Iterator, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(WINDOWS_SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(WINDOWS_SCRIPT_DIRECTORY))

from lifecycle_lock import (  # noqa: E402
    LifecycleLockError,
    lifecycle_lock,
    lifecycle_lock_path,
)

VENV_DIRECTORY = Path(
    os.environ.get("PIXEAGLE_VENV_DIR", str(PROJECT_ROOT / ".venv"))
)
if not VENV_DIRECTORY.is_absolute():
    VENV_DIRECTORY = PROJECT_ROOT / VENV_DIRECTORY
VENV_PYTHON = VENV_DIRECTORY / "Scripts" / "python.exe"
REQUIREMENTS = PROJECT_ROOT / "requirements-core.txt"
PYTHON_POLICY = PROJECT_ROOT / "scripts" / "setup" / "pytorch_matrix.json"
PYTHON_COMPATIBILITY = (
    PROJECT_ROOT / "scripts" / "setup" / "check-python-compatibility.py"
)
VERIFY_REQUIREMENTS = (
    PROJECT_ROOT / "scripts" / "setup" / "verify-installed-requirements.py"
)
PIP_CHECK_POLICY = PROJECT_ROOT / "scripts" / "setup" / "pip_check_policy.py"
OPENCV_PROBE = PROJECT_ROOT / "scripts" / "setup" / "opencv_provider_probe.py"
CONFIG_SYNC = PROJECT_ROOT / "scripts" / "setup" / "config-sync-status.py"
BROWSER_PROFILE = (
    PROJECT_ROOT / "scripts" / "setup" / "apply-setup-profile.py"
)
CONFIG_FILE = PROJECT_ROOT / "configs" / "config.yaml"
DEFAULT_CONFIG_FILE = PROJECT_ROOT / "configs" / "config_default.yaml"
DEFAULT_BROWSER_USER_FILE = (
    PROJECT_ROOT / "configs" / "secrets" / "demo-browser-users.json"
)
SECURE_FILE_ACL = PROJECT_ROOT / "scripts" / "windows" / "secure-file.ps1"
ENSURE_DASHBOARD_ENV = (
    PROJECT_ROOT / "scripts" / "setup" / "ensure-dashboard-env.py"
)
DASHBOARD_DIRECTORY = PROJECT_ROOT / "dashboard"
DASHBOARD_DEFAULT_ENV = DASHBOARD_DIRECTORY / "env_default.yaml"
DASHBOARD_ENV = DASHBOARD_DIRECTORY / ".env"
DASHBOARD_CONTRACT = PROJECT_ROOT / "scripts" / "lib" / "dashboard_contract.js"
NODE_VERSION_FILE = PROJECT_ROOT / ".nvmrc"
DEPENDENCY_RECEIPT = VENV_DIRECTORY / ".pixeagle-core-contract.json"
DASHBOARD_CACHE_DIRECTORY = DASHBOARD_DIRECTORY / ".pixeagle_cache"
DASHBOARD_DEPENDENCY_RECEIPT = DASHBOARD_CACHE_DIRECTORY / "deps_hash"
DASHBOARD_BUILD_RECEIPT = DASHBOARD_CACHE_DIRECTORY / "build_hash"
LIFECYCLE_LOCK_FILE = lifecycle_lock_path(PROJECT_ROOT)
RUNTIME_CONTROLLER = PROJECT_ROOT / "scripts" / "windows" / "runtime.py"
SUPPORTED_PYTHON_SERIES = {(3, 11), (3, 12)}


class SetupError(RuntimeError):
    """Raised when a setup postcondition cannot be established."""


BROWSER_PROFILE_PROBE = r"""
import pathlib
import sys
import yaml

project_root = pathlib.Path(sys.argv[1]).resolve()
config_path = pathlib.Path(sys.argv[2])
src_root = project_root / "src"
sys.path.insert(0, str(src_root))

from classes.browser_user_store import (
    BrowserUserStore,
    validate_required_invariants,
)

config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
streaming = config.get("Streaming") if isinstance(config, dict) else None
if not isinstance(streaming, dict):
    raise SystemExit(2)
if streaming.get("API_EXPOSURE_MODE") != "local_only":
    raise SystemExit(3)
if streaming.get("API_AUTH_MODE") != "browser_session":
    raise SystemExit(4)
if streaming.get("API_SYSTEM_RESTART_POLICY") != "lab_admin_browser":
    raise SystemExit(5)
if str(streaming.get("HTTP_STREAM_HOST", "")).lower() not in {
    "127.0.0.1", "localhost", "::1"
}:
    raise SystemExit(6)
if streaming.get("API_ALLOWED_HOSTS") != []:
    raise SystemExit(7)
expected_origins = {
    "http://127.0.0.1:3040",
    "http://localhost:3040",
    "http://127.0.0.1:5077",
    "http://localhost:5077",
}
if set(streaming.get("API_CORS_ALLOWED_ORIGINS") or []) != expected_origins:
    raise SystemExit(8)
if streaming.get("API_SESSION_COOKIE_SECURE") is not False:
    raise SystemExit(9)
if streaming.get("ENABLE_STREAMING", True) is not True:
    raise SystemExit(10)

raw_user_file = str(streaming.get("API_SESSION_USER_FILE") or "").strip()
if not raw_user_file:
    raise SystemExit(11)
user_file = pathlib.Path(raw_user_file).expanduser()
if not user_file.is_absolute():
    user_file = project_root / user_file
user_file = user_file.resolve(strict=False)
expected_user_file = pathlib.Path(sys.argv[3]).resolve(strict=False)
if user_file != expected_user_file:
    raise SystemExit(12)
snapshot = BrowserUserStore(user_file).load_snapshot()
validate_required_invariants(snapshot.records, require_enabled_admin=True)
print(user_file)
"""


def _require_supported_host() -> None:
    if os.name != "nt" or platform.system() != "Windows":
        raise SetupError("native Windows setup must run on Windows")
    if os.environ.get("PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS") != "1":
        raise SetupError(
            "set PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1 after reviewing "
            "docs/WINDOWS_SETUP.md"
        )
    machine = platform.machine().strip().lower()
    interpreter_bits = struct.calcsize("P") * 8
    if machine not in {"amd64", "x86_64"} or interpreter_bits != 64:
        raise SetupError(
            "the Windows Core preview requires an x64 interpreter "
            f"(detected {machine or 'unknown'}, {interpreter_bits}-bit)"
        )
    selected = (sys.version_info.major, sys.version_info.minor)
    if selected not in SUPPORTED_PYTHON_SERIES:
        raise SetupError(
            "the Windows Core preview requires CPython 3.11 or 3.12 "
            f"(selected {sys.version_info.major}.{sys.version_info.minor})"
        )


@contextlib.contextmanager
def _setup_lock(timeout_seconds: float = 15.0) -> Iterator[None]:
    try:
        with lifecycle_lock(PROJECT_ROOT, timeout_seconds=timeout_seconds):
            yield
    except LifecycleLockError as exc:
        raise SetupError(str(exc)) from exc


def _normalize_path(value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(Path(value).resolve(strict=False))))


def _venv_interpreter_identity() -> dict[str, Any]:
    if not VENV_PYTHON.is_file():
        raise SetupError("virtual environment interpreter is missing")
    probe = (
        "import json,platform,struct,sys;"
        "print(json.dumps({"
        "'version':[sys.version_info.major,sys.version_info.minor,sys.version_info.micro],"
        "'machine':platform.machine(),"
        "'bits':struct.calcsize('P')*8,"
        "'prefix':sys.prefix,"
        "'base_prefix':sys.base_prefix,"
        "'cache_tag':getattr(sys.implementation,'cache_tag','')"
        "},sort_keys=True))"
    )
    completed = _run([VENV_PYTHON, "-c", probe], capture=True)
    try:
        identity = json.loads(completed.stdout)
        version = tuple(int(value) for value in identity["version"])
        machine = str(identity["machine"]).strip().lower()
        bits = int(identity["bits"])
        prefix = str(identity["prefix"])
        base_prefix = str(identity["base_prefix"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SetupError("virtual environment identity is invalid") from exc

    if len(version) != 3 or version[:2] not in SUPPORTED_PYTHON_SERIES:
        raise SetupError(
            "existing virtual environment uses unsupported Python "
            f"{'.'.join(map(str, version))}; rename it and rerun setup"
        )
    if machine not in {"amd64", "x86_64"} or bits != 64:
        raise SetupError(
            "existing virtual environment is not an x64 interpreter; "
            "rename it and rerun setup"
        )
    if _normalize_path(prefix) != _normalize_path(VENV_DIRECTORY):
        raise SetupError(
            "virtual environment interpreter reports an unrelated prefix"
        )
    if _normalize_path(base_prefix) == _normalize_path(prefix):
        raise SetupError("selected interpreter is not an isolated virtual environment")
    return identity


def _validate_venv_python_policy() -> dict[str, Any]:
    identity = _venv_interpreter_identity()
    _run(
        [
            VENV_PYTHON,
            PYTHON_COMPATIBILITY,
            "--policy",
            PYTHON_POLICY,
            "--runtime-role",
            "core",
        ]
    )
    return identity


def _run(
    command: Sequence[str | Path],
    *,
    cwd: Path = PROJECT_ROOT,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    normalized = [str(value) for value in command]
    completed = subprocess.run(
        normalized,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=capture,
    )
    if check and completed.returncode != 0:
        detail = ""
        if capture:
            detail = (completed.stderr or completed.stdout).strip()
        raise SetupError(
            f"command failed ({completed.returncode}): {' '.join(normalized)}"
            + (f"\n{detail}" if detail else "")
        )
    return completed


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _digest_files(paths: Sequence[Path], extra: Sequence[str]) -> str:
    digest = hashlib.sha256()
    digest.update(b"pixeagle-windows-core-contract-v1\0")
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise SetupError(f"setup contract input is not a regular file: {path}")
        relative = path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    for value in extra:
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _load_receipt(path: Path) -> dict[str, Any] | None:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _write_receipt(path: Path, value: dict[str, Any]) -> None:
    _atomic_write_text(
        path,
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
    )


def _validate_python_policy() -> None:
    _run(
        [
            sys.executable,
            PYTHON_COMPATIBILITY,
            "--policy",
            PYTHON_POLICY,
            "--runtime-role",
            "core",
        ]
    )


def _venv_validators() -> list[tuple[str, list[str | Path]]]:
    return [
        (
            "direct requirements",
            [
                VENV_PYTHON,
                VERIFY_REQUIREMENTS,
                "--requirements",
                REQUIREMENTS,
            ],
        ),
        ("dependency graph", [VENV_PYTHON, PIP_CHECK_POLICY]),
        ("OpenCV provider", [VENV_PYTHON, OPENCV_PROBE]),
    ]


def _validate_venv(*, quiet: bool) -> bool:
    if not VENV_PYTHON.is_file():
        return False
    for label, command in _venv_validators():
        completed = _run(command, capture=quiet, check=False)
        if completed.returncode != 0:
            if not quiet:
                print(f"   [!] {label} validation failed")
            return False
    return True


def _ensure_venv() -> None:
    if VENV_PYTHON.is_file():
        identity = _validate_venv_python_policy()
        print(
            "   [OK] Virtual environment: "
            f"{VENV_DIRECTORY} (Python {'.'.join(map(str, identity['version']))} x64)"
        )
        return
    if VENV_DIRECTORY.exists():
        raise SetupError(
            f"incomplete virtual environment exists at {VENV_DIRECTORY}; "
            "rename or remove that environment explicitly, then rerun setup"
        )
    print(f"   [*] Creating virtual environment: {VENV_DIRECTORY}")
    _run([sys.executable, "-m", "venv", VENV_DIRECTORY])
    if not VENV_PYTHON.is_file():
        raise SetupError("virtual environment creation did not publish python.exe")
    _validate_venv_python_policy()


def _python_contract_fingerprint() -> str:
    identity = _venv_interpreter_identity()
    return _digest_files(
        [
            REQUIREMENTS,
            VERIFY_REQUIREMENTS,
            PIP_CHECK_POLICY,
            OPENCV_PROBE,
            PYTHON_POLICY,
        ],
        [
            platform.platform(),
            str(identity["machine"]),
            ".".join(map(str, identity["version"])),
            str(identity.get("cache_tag", "")),
        ],
    )


def _ensure_python_dependencies(force: bool) -> None:
    fingerprint = _python_contract_fingerprint()
    receipt = _load_receipt(DEPENDENCY_RECEIPT)
    receipt_matches = bool(
        receipt
        and receipt.get("schema_version") == 1
        and receipt.get("fingerprint") == fingerprint
    )
    if not force and _validate_venv(quiet=True):
        status = "unchanged" if receipt_matches else "revalidated"
        print(f"   [OK] Core Python dependencies {status}; install skipped")
        _write_receipt(
            DEPENDENCY_RECEIPT,
            {
                "schema_version": 1,
                "fingerprint": fingerprint,
                "python": ".".join(
                    map(str, _venv_interpreter_identity()["version"])
                ),
                "validated_at": time.time(),
            },
        )
        return

    print("   [*] Reconciling Core Python dependencies")
    _run([VENV_PYTHON, "-m", "pip", "install", "--upgrade", "pip", "wheel"])
    _run(
        [
            VENV_PYTHON,
            "-m",
            "pip",
            "install",
            "--prefer-binary",
            "-r",
            REQUIREMENTS,
        ]
    )
    if not _validate_venv(quiet=False):
        raise SetupError("Core Python dependency postconditions failed")
    _write_receipt(
        DEPENDENCY_RECEIPT,
        {
            "schema_version": 1,
            "fingerprint": fingerprint,
            "python": ".".join(
                map(str, _venv_interpreter_identity()["version"])
            ),
            "validated_at": time.time(),
        },
    )
    print("   [OK] Core Python dependency contract verified")


def _command_version(executable: str, *arguments: str) -> str:
    completed = _run([executable, *arguments], capture=True)
    return completed.stdout.strip()


def _npm_command(npm: str, *arguments: str) -> list[str]:
    if os.name != "nt":
        return [npm, *arguments]

    command_processor = os.environ.get("COMSPEC") or shutil.which("cmd.exe")
    if not command_processor:
        raise SetupError("Windows command processor is unavailable for npm")
    npm_command_line = subprocess.list2cmdline([npm, *arguments])
    return [
        command_processor,
        "/d",
        "/s",
        "/c",
        npm_command_line,
    ]


def _ensure_node_toolchain() -> tuple[str, str]:
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise SetupError(
            "Node.js/npm are required. Install Node 24 LTS, reopen the terminal, "
            "and rerun scripts\\init.bat"
        )
    required_text = NODE_VERSION_FILE.read_text(encoding="ascii").strip()
    try:
        required_major = int(required_text.split(".", 1)[0])
        node_version = _command_version(node, "--version").lstrip("v")
        node_major = int(node_version.split(".", 1)[0])
        npm_version = _run(
            _npm_command(npm, "--version"),
            capture=True,
        ).stdout.strip()
        npm_major = int(npm_version.split(".", 1)[0])
    except (OSError, UnicodeError, ValueError) as exc:
        raise SetupError(f"cannot validate Node/npm versions: {exc}") from exc
    if node_major != required_major:
        raise SetupError(
            f"Node {required_major}.x is required by .nvmrc (found {node_version})"
        )
    if npm_major not in {10, 11}:
        raise SetupError(
            f"npm >=10 <12 is required by dashboard/package.json (found {npm_version})"
        )
    print(f"   [OK] Node {node_version}; npm {npm_version}")
    return node, npm


def _dashboard_contract_value(node: str, operation: str) -> str:
    completed = _run(
        [node, DASHBOARD_CONTRACT, operation, DASHBOARD_DIRECTORY, NODE_VERSION_FILE],
        capture=True,
    )
    return completed.stdout.strip()


def _dashboard_dependencies_ready(node: str, npm: str) -> bool:
    if not (DASHBOARD_DIRECTORY / "node_modules").is_dir():
        return False
    if not DASHBOARD_DEPENDENCY_RECEIPT.is_file():
        return False
    try:
        expected = _dashboard_contract_value(node, "dependency-fingerprint")
        recorded = DASHBOARD_DEPENDENCY_RECEIPT.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError, SetupError):
        return False
    if expected != recorded:
        return False
    return (
        _run(
            _npm_command(npm, "ls", "--all", "--silent"),
            cwd=DASHBOARD_DIRECTORY,
            capture=True,
            check=False,
        ).returncode
        == 0
    )


def _ensure_dashboard_dependencies(node: str, npm: str, force: bool) -> None:
    if not force and _dashboard_dependencies_ready(node, npm):
        print("   [OK] Dashboard dependencies unchanged; npm ci skipped")
        return
    print("   [*] Reconciling dashboard dependencies from package-lock.json")
    _run(_npm_command(npm, "ci"), cwd=DASHBOARD_DIRECTORY)
    if not _dashboard_dependencies_ready_after_install(node, npm):
        raise SetupError("dashboard dependency postconditions failed")
    print("   [OK] Dashboard dependency contract verified")


def _dashboard_dependencies_ready_after_install(node: str, npm: str) -> bool:
    if (
        _run(
            _npm_command(npm, "ls", "--all", "--silent"),
            cwd=DASHBOARD_DIRECTORY,
            capture=True,
            check=False,
        ).returncode
        != 0
    ):
        return False
    fingerprint = _dashboard_contract_value(node, "dependency-fingerprint")
    DASHBOARD_CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(DASHBOARD_DEPENDENCY_RECEIPT, f"{fingerprint}\n")
    return _dashboard_dependencies_ready(node, npm)


def _dashboard_build_ready(node: str, fingerprint: str) -> bool:
    if not DASHBOARD_BUILD_RECEIPT.is_file():
        return False
    try:
        recorded = DASHBOARD_BUILD_RECEIPT.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return False
    if recorded != fingerprint:
        return False
    return (
        _run(
            [
                node,
                DASHBOARD_CONTRACT,
                "build-complete",
                DASHBOARD_DIRECTORY,
            ],
            capture=True,
            check=False,
        ).returncode
        == 0
    )


def _ensure_dashboard_build(node: str, npm: str, force: bool) -> None:
    fingerprint = _dashboard_contract_value(node, "build-fingerprint")
    if not force and _dashboard_build_ready(node, fingerprint):
        print("   [OK] Dashboard build unchanged; rebuild skipped")
        return
    print("   [*] Building dashboard production assets")
    _run(_npm_command(npm, "run", "build"), cwd=DASHBOARD_DIRECTORY)
    if not _dashboard_build_ready_after_build(node, fingerprint):
        raise SetupError("dashboard build postconditions failed")
    print("   [OK] Dashboard build verified")


def _dashboard_build_ready_after_build(node: str, fingerprint: str) -> bool:
    completed = _run(
        [node, DASHBOARD_CONTRACT, "build-complete", DASHBOARD_DIRECTORY],
        capture=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    DASHBOARD_CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(DASHBOARD_BUILD_RECEIPT, f"{fingerprint}\n")
    return _dashboard_build_ready(node, fingerprint)


def _ensure_config_lifecycle() -> None:
    staged = PROJECT_ROOT / "configs" / ".config_default_preupdate.yaml"
    if not os.path.lexists(staged):
        _run([VENV_PYTHON, CONFIG_SYNC, "--initialize-baseline"])
        print("   [OK] Runtime config metadata verified")
        return

    try:
        before = os.lstat(staged)
    except OSError as exc:
        raise SetupError(f"cannot inspect staged config defaults: {exc}") from exc
    if staged.is_symlink() or not staged.is_file():
        raise SetupError(
            "staged config defaults must be a regular non-symlink file"
        )

    _run(
        [
            VENV_PYTHON,
            CONFIG_SYNC,
            "--initialize-baseline-from",
            staged,
        ]
    )
    try:
        after = os.lstat(staged)
    except OSError as exc:
        raise SetupError(
            "staged config defaults changed before setup could retire them"
        ) from exc
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if (
        staged.is_symlink()
        or not staged.is_file()
        or before_identity != after_identity
    ):
        raise SetupError(
            "staged config defaults changed during reconciliation; "
            "the replacement was preserved"
        )
    staged.unlink()
    if os.path.lexists(staged):
        raise SetupError(
            "pre-update config baseline remains pending after reconciliation"
        )
    print("   [OK] Runtime config metadata verified")


def _browser_profile_user_file() -> Path | None:
    config_path = CONFIG_FILE if CONFIG_FILE.is_file() else DEFAULT_CONFIG_FILE
    completed = _run(
        [
            VENV_PYTHON,
            "-c",
            BROWSER_PROFILE_PROBE,
            PROJECT_ROOT,
            config_path,
            DEFAULT_BROWSER_USER_FILE,
        ],
        capture=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    raw_path = completed.stdout.strip()
    return Path(raw_path) if raw_path else None


def _secure_owner_only_path(path: Path, *, directory: bool = False) -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell or not SECURE_FILE_ACL.is_file():
        raise SetupError("Windows owner-only credential ACL helper is unavailable")
    command: list[str | Path] = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        SECURE_FILE_ACL,
        "-Path",
        path,
    ]
    if directory:
        command.append("-Directory")
    _run(command)


def _ensure_browser_profile(*, non_interactive: bool) -> None:
    DEFAULT_BROWSER_USER_FILE.parent.mkdir(parents=True, exist_ok=True)
    _secure_owner_only_path(DEFAULT_BROWSER_USER_FILE.parent, directory=True)
    user_file = _browser_profile_user_file()
    if user_file is not None:
        _secure_owner_only_path(user_file)
        print("   [OK] Dashboard login unchanged; existing account preserved")
        return

    credential_mode = "default" if non_interactive else "prompt"
    print("   [*] Configuring the loopback dashboard login")
    _run(
        [
            VENV_PYTHON,
            BROWSER_PROFILE,
            "--profile",
            "demo_lan_browser",
            "--lan-host",
            "127.0.0.1",
            "--session-user-file",
            DEFAULT_BROWSER_USER_FILE,
            "--demo-credential-mode",
            credential_mode,
            "--quiet",
        ]
    )
    user_file = _browser_profile_user_file()
    if user_file is None:
        raise SetupError(
            "authenticated loopback browser profile failed its postcondition"
        )
    _secure_owner_only_path(user_file)
    if non_interactive:
        print("   [OK] Dashboard login: admin / admin (local preview default)")
    else:
        print("   [OK] Dashboard login configured; use the credentials selected above")


def _ensure_dashboard_environment() -> None:
    completed = _run(
        [
            VENV_PYTHON,
            ENSURE_DASHBOARD_ENV,
            "--defaults",
            DASHBOARD_DEFAULT_ENV,
            "--output",
            DASHBOARD_ENV,
        ],
        capture=True,
    )
    print(f"   [OK] Dashboard environment {completed.stdout.strip()}")


def _runtime_active() -> bool:
    if not VENV_PYTHON.is_file() or not RUNTIME_CONTROLLER.is_file():
        return False
    completed = _run(
        [VENV_PYTHON, RUNTIME_CONTROLLER, "status", "--quiet"],
        capture=True,
        check=False,
    )
    if completed.returncode == 3:
        return False
    if completed.returncode in {0, 4}:
        return True
    detail = (completed.stderr or completed.stdout).strip()
    raise SetupError(
        "the existing Windows runtime receipt could not be validated"
        + (f": {detail}" if detail else "")
    )


def _assert_no_runtime_receipt() -> None:
    state_file = PROJECT_ROOT / ".pixeagle_runtime" / "windows" / "runtime.json"
    if os.path.lexists(state_file):
        raise SetupError(
            "a Windows runtime became active before setup acquired the lifecycle "
            "lock; no dependencies or config were changed"
        )


def _stop_runtime() -> None:
    _run([VENV_PYTHON, RUNTIME_CONTROLLER, "stop"])


def _download_sidecars() -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    script = PROJECT_ROOT / "scripts" / "setup" / "download-binaries.ps1"
    if not powershell or not script.is_file():
        raise SetupError("hardened PowerShell binary downloader is unavailable")
    _run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script,
            "-All",
        ]
    )


def _choose_sidecars(args: argparse.Namespace) -> bool:
    if args.with_sidecars:
        return True
    if args.without_sidecars or args.non_interactive:
        return False
    response = input(
        "   Download optional MAVSDK/MAVLink2REST sidecars? [y/N]: "
    ).strip()
    return response.lower() in {"y", "yes"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Set up the PixEagle native-Windows x64 Core preview",
    )
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--with-sidecars", action="store_true")
    parser.add_argument("--without-sidecars", action="store_true")
    parser.add_argument("--force-python", action="store_true")
    parser.add_argument("--force-dashboard", action="store_true")
    parser.add_argument(
        "--stop-runtime",
        action="store_true",
        help="stop an exact receipt-owned Windows runtime before reconciliation",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.with_sidecars and args.without_sidecars:
        parser.error("--with-sidecars and --without-sidecars are mutually exclusive")
    try:
        _require_supported_host()
        os.chdir(PROJECT_ROOT)
        print("PixEagle Windows x64 Core preview setup")
        print("Scope: bundled-video local lab; AI, services, and flight are excluded")
        _validate_python_policy()
        if _runtime_active():
            if args.stop_runtime:
                print("   [*] Stopping the exact receipt-owned runtime")
                _stop_runtime()
            else:
                raise SetupError(
                    "PixEagle is running. Stop it with scripts\\stop.bat, "
                    "or rerun setup with --stop-runtime"
                )
        with _setup_lock():
            _assert_no_runtime_receipt()
            _ensure_venv()
            _ensure_python_dependencies(args.force_python)
            _ensure_dashboard_environment()
            node, npm = _ensure_node_toolchain()
            if not DASHBOARD_CONTRACT.is_file():
                raise SetupError("shared dashboard contract helper is missing")
            _ensure_dashboard_dependencies(node, npm, args.force_dashboard)
            _ensure_dashboard_build(node, npm, args.force_dashboard)
            _ensure_config_lifecycle()
            _ensure_browser_profile(non_interactive=args.non_interactive)
            sidecars = _choose_sidecars(args)
            if sidecars:
                _download_sidecars()

        print("")
        print("[OK] Windows Core setup postconditions passed")
        print("Start:   scripts\\run.bat")
        print("Status:  scripts\\status.bat")
        print("Stop:    scripts\\stop.bat")
        print("Open:    http://127.0.0.1:3040 (dashboard login required)")
        if sidecars:
            print("PX4 sidecar binaries: acquired only; runtime orchestration excluded")
        else:
            print("PX4 lab sidecars: not installed/selected")
        print("Guide:   docs\\WINDOWS_SETUP.md")
        return 0
    except (OSError, SetupError, subprocess.SubprocessError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("[ERROR] setup input was interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
