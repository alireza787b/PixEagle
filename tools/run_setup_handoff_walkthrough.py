#!/usr/bin/env python3
"""Clean-checkout setup/update handoff walkthrough for PixEagle.

This harness is intentionally conservative. It clones the current repository to
a temporary clean checkout, exercises documented beginner and senior-dev setup
paths with dry-run or check-only commands, and records evidence artifacts. It
does not install services, change firewall rules, download MAVSDK/MAVLink2REST
binaries, start PX4, start SITL/HIL, or claim field/aircraft readiness. Optional
dashboard evidence may run npm ci and fetch npm package artifacts.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = (
    PROJECT_ROOT
    / "docs"
    / "reporting"
    / "agent-ops"
    / "codex-modernization"
    / "evidence"
)
DEFAULT_RUN_ID = datetime.now(timezone.utc).strftime(
    "%Y-%m-%d-pxe0074-clean-handoff-walkthrough-%H%M%SZ"
)
CLAIM_BOUNDARY = (
    "Clean-checkout setup/update dry-run and check-only evidence. Default mode "
    "does not install system services, change firewall rules, download "
    "MAVSDK/MAVLink2REST binaries, install npm packages, start PX4/SITL/HIL, "
    "validate QGC playback, validate real video tracking, or claim field/"
    "real-aircraft readiness. Optional --include-dashboard may run npm ci and "
    "fetch dashboard package artifacts from the configured npm registry."
)
FORBIDDEN_COMMAND_TERMS = (
    "sudo",
    "ufw",
    "systemctl",
    "service-install",
    "service-enable",
    "make init",
    "make download-binaries",
    "ALLOW_LOCAL_SELF_SIGNED_TLS=1",
    "sitl-sih-execute-px4",
    "sitl-gazebo-execute-px4",
)
REQUIRED_FILES = (
    "README.md",
    "docs/README.md",
    "docs/INSTALLATION.md",
    "docs/CONFIGURATION.md",
    "docs/CONFIG_SYNC.md",
    "docs/setup/setup-profiles.md",
    "docs/setup/binary-download-policy.md",
    "Makefile",
    "install.sh",
    "install.ps1",
    "scripts/init.sh",
    "scripts/run.sh",
    "scripts/stop.sh",
    "scripts/update.sh",
    "scripts/lib/sync.sh",
    "scripts/setup/apply-setup-profile.py",
    "scripts/setup/config-sync-status.py",
    "scripts/setup/download-binaries.sh",
    "scripts/setup/quick-browser-demo.sh",
    "scripts/setup/quick-browser-demo-cleanup.sh",
    "configs/config_default.yaml",
    "configs/config_schema.yaml",
    "configs/config_retirements.yaml",
    "dashboard/package.json",
    "dashboard/package-lock.json",
)


@dataclass(frozen=True)
class CommandSpec:
    name: str
    command: tuple[str, ...]
    cwd: str = "."
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 120
    required: bool = True

    def printable(self) -> str:
        return " ".join(self.command)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_dumps(payload), encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def command_output(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except Exception as exc:  # pragma: no cover - defensive metadata path
        return {"command": command, "error": str(exc)}
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def current_branch(source_repo: Path) -> str:
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=source_repo,
        text=True,
        capture_output=True,
        check=False,
    )
    branch = result.stdout.strip()
    if not branch:
        raise RuntimeError("Cannot determine current branch for handoff clone")
    return branch


def source_is_clean(source_repo: Path) -> tuple[bool, str]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=source_repo,
        text=True,
        capture_output=True,
        check=False,
    )
    status = result.stdout.strip()
    return result.returncode == 0 and not status, status


def prepare_artifact_dir(artifact_root: Path, run_id: str) -> Path:
    artifact_dir = artifact_root.resolve() / run_id
    if artifact_dir.exists() and any(artifact_dir.iterdir()):
        raise RuntimeError(f"Refusing to reuse non-empty artifact directory: {artifact_dir}")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def clone_checkout(
    *,
    source_repo: Path,
    branch: str,
    temp_root: Path | None,
    keep_checkout: bool,
) -> tuple[Path, Path | None]:
    checkout_parent = Path(
        tempfile.mkdtemp(prefix="pixeagle-handoff-", dir=str(temp_root) if temp_root else None)
    )
    checkout = checkout_parent / "checkout"
    command = [
        "git",
        "clone",
        "--local",
        "--no-hardlinks",
        "--branch",
        branch,
        str(source_repo.resolve()),
        str(checkout),
    ]
    result = subprocess.run(
        command,
        cwd=source_repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        if not keep_checkout:
            shutil.rmtree(checkout_parent, ignore_errors=True)
        raise RuntimeError(
            "Failed to create clean handoff checkout:\n"
            f"command: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return checkout, checkout_parent if not keep_checkout else None


def build_command_plan(
    *,
    python_bin: str,
    include_phase0: bool,
    include_update_check: bool,
    include_dashboard: bool,
    demo_host: str,
    gcs_host: str,
    public_host: str,
) -> list[CommandSpec]:
    demo_user_file = "/tmp/pixeagle-handoff-demo-users.json"
    demo_handoff_file = "/tmp/pixeagle-handoff-demo-handoff.json"
    prod_user_file = "/tmp/pixeagle-handoff-prod-users.json"
    prod_handoff_file = "/tmp/pixeagle-handoff-prod-handoff.json"
    qgc_token_file = "/tmp/pixeagle-handoff-qgc-tokens.json"
    qgc_handoff_file = "/tmp/pixeagle-handoff-qgc-handoff.json"

    commands: list[CommandSpec] = [
        CommandSpec("git_head", ("git", "rev-parse", "HEAD")),
        CommandSpec("git_status_initial", ("git", "status", "--short", "--branch")),
        CommandSpec("make_help", ("make", "help")),
        CommandSpec("shell_syntax_install", ("bash", "-n", "install.sh")),
        CommandSpec("shell_syntax_init", ("bash", "-n", "scripts/init.sh")),
        CommandSpec("shell_syntax_run", ("bash", "-n", "scripts/run.sh")),
        CommandSpec("shell_syntax_stop", ("bash", "-n", "scripts/stop.sh")),
        CommandSpec("shell_syntax_update", ("bash", "-n", "scripts/update.sh")),
        CommandSpec(
            "shell_syntax_quick_demo",
            ("bash", "-n", "scripts/setup/quick-browser-demo.sh"),
        ),
        CommandSpec(
            "shell_syntax_quick_demo_cleanup",
            ("bash", "-n", "scripts/setup/quick-browser-demo-cleanup.sh"),
        ),
        CommandSpec("shell_syntax_sync", ("bash", "-n", "scripts/lib/sync.sh")),
        CommandSpec(
            "config_sync_redacted_status",
            (python_bin, "scripts/setup/config-sync-status.py", "--json"),
            env={"PYTHONPATH": "src"},
        ),
        CommandSpec(
            "binary_download_plan",
            ("bash", "scripts/setup/download-binaries.sh", "--all", "--dry-run"),
        ),
        CommandSpec(
            "local_dev_profile_dry_run",
            (python_bin, "scripts/setup/apply-setup-profile.py", "--profile", "local_dev", "--dry-run"),
            env={"PYTHONPATH": "src"},
        ),
        CommandSpec(
            "field_qgc_video_profile_dry_run",
            (
                python_bin,
                "scripts/setup/apply-setup-profile.py",
                "--profile",
                "field_qgc_video",
                "--gcs-host",
                gcs_host,
                "--dry-run",
            ),
            env={"PYTHONPATH": "src"},
        ),
        CommandSpec(
            "demo_lan_browser_profile_dry_run",
            (
                python_bin,
                "scripts/setup/apply-setup-profile.py",
                "--profile",
                "demo_lan_browser",
                "--lan-host",
                demo_host,
                "--session-user-file",
                demo_user_file,
                "--credential-handoff-file",
                demo_handoff_file,
                "--dry-run",
            ),
            env={"PYTHONPATH": "src"},
        ),
        CommandSpec(
            "qgc_direct_media_profile_dry_run",
            (
                python_bin,
                "scripts/setup/apply-setup-profile.py",
                "--profile",
                "qgc_direct_media",
                "--public-host",
                public_host,
                "--bearer-token-file",
                qgc_token_file,
                "--qgc-handoff-file",
                qgc_handoff_file,
                "--dry-run",
            ),
            env={"PYTHONPATH": "src"},
        ),
        CommandSpec(
            "production_remote_profile_dry_run",
            (
                python_bin,
                "scripts/setup/apply-setup-profile.py",
                "--profile",
                "production_remote",
                "--public-host",
                public_host,
                "--session-user-file",
                prod_user_file,
                "--credential-handoff-file",
                prod_handoff_file,
                "--dry-run",
            ),
            env={"PYTHONPATH": "src"},
        ),
        CommandSpec(
            "make_quick_browser_demo_dry_run",
            (
                "make",
                "quick-browser-demo",
                f"PYTHON={python_bin}",
                f"LAN_HOST={demo_host}",
                "DRY_RUN=1",
                "START_DEMO=0",
                "OPEN_FIREWALL=0",
                f"SESSION_USER_FILE={demo_user_file}",
                f"CREDENTIAL_HANDOFF_FILE={demo_handoff_file}",
            ),
        ),
        CommandSpec(
            "make_quick_browser_demo_cleanup_dry_run",
            (
                "make",
                "quick-browser-demo-cleanup",
                f"PYTHON={python_bin}",
                f"LAN_HOST={demo_host}",
                "DRY_RUN=1",
                "STOP_DEMO=0",
                "CLOSE_FIREWALL=0",
                f"SESSION_USER_FILE={demo_user_file}",
                f"CREDENTIAL_HANDOFF_FILE={demo_handoff_file}",
            ),
        ),
    ]

    if include_update_check:
        commands.append(
            CommandSpec(
                "stopped_runtime_update_dry_run",
                ("bash", "scripts/update.sh", "--dry-run"),
                timeout_seconds=180,
            )
        )

    if include_phase0:
        commands.extend(
            [
                CommandSpec(
                    "schema_check",
                    ("bash", "scripts/check_schema.sh"),
                    env={"PYTHON": python_bin, "PYTHONPATH": "src"},
                ),
                CommandSpec(
                    "minimum_backend_api_tests",
                    (
                        python_bin,
                        "-m",
                        "pytest",
                        "tests/test_api_route_inventory.py",
                        "tests/unit/core_app/test_parameters_reload.py",
                        "-q",
                    ),
                    env={"PYTHONPATH": "src"},
                    timeout_seconds=240,
                ),
            ]
        )

    if include_dashboard:
        commands.extend(
            [
                CommandSpec(
                    "dashboard_npm_ci",
                    ("npm", "ci", "--no-audit", "--fund=false"),
                    cwd="dashboard",
                    timeout_seconds=600,
                ),
                CommandSpec(
                    "dashboard_tests",
                    ("npm", "test", "--", "--runInBand", "--watchAll=false"),
                    cwd="dashboard",
                    timeout_seconds=600,
                ),
                CommandSpec(
                    "dashboard_build",
                    ("npm", "run", "build"),
                    cwd="dashboard",
                    env={"CI": "true"},
                    timeout_seconds=600,
                ),
            ]
        )

    commands.append(CommandSpec("git_status_final", ("git", "status", "--short", "--branch")))
    return commands


def assert_safe_plan(commands: list[CommandSpec]) -> None:
    for spec in commands:
        printable = spec.printable()
        for term in FORBIDDEN_COMMAND_TERMS:
            if term in printable:
                raise RuntimeError(
                    f"Unsafe handoff command plan includes forbidden term {term!r}: {printable}"
                )
        if spec.name == "binary_download_plan" and "--dry-run" not in spec.command:
            raise RuntimeError("Binary download plan must always use --dry-run")
        if "quick_browser_demo" in spec.name and "DRY_RUN=1" not in spec.command:
            raise RuntimeError(f"Quick demo command must be dry-run only: {printable}")


def verify_required_files(checkout: Path) -> dict[str, Any]:
    files = []
    missing = []
    for relative in REQUIRED_FILES:
        exists = (checkout / relative).is_file()
        files.append({"path": relative, "exists": exists})
        if not exists:
            missing.append(relative)
    return {
        "passed": not missing,
        "missing": missing,
        "files": files,
    }


def git_status_stdout_is_clean(stdout: str) -> bool:
    """Return True when `git status --short --branch` has no file changes."""
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("## "):
            continue
        return False
    return True


def run_command(
    spec: CommandSpec,
    *,
    checkout: Path,
    logs_dir: Path,
) -> dict[str, Any]:
    cwd = checkout / spec.cwd
    env = os.environ.copy()
    env.update(spec.env)
    env.setdefault("PYTHONUNBUFFERED", "1")
    start = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            list(spec.command),
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=spec.timeout_seconds,
            check=False,
        )
        returncode = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = 124
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + f"\nTimed out after {spec.timeout_seconds}s"

    duration_seconds = round(time.monotonic() - start, 3)
    stdout_path = logs_dir / f"{spec.name}.stdout.log"
    stderr_path = logs_dir / f"{spec.name}.stderr.log"
    write_text(stdout_path, stdout)
    write_text(stderr_path, stderr)

    passed = returncode == 0
    extra: dict[str, Any] = {}
    if spec.name in {"git_status_initial", "git_status_final"}:
        clean = git_status_stdout_is_clean(stdout)
        extra["git_worktree_clean"] = clean
        passed = passed and clean

    return {
        "name": spec.name,
        "command": list(spec.command),
        "cwd": spec.cwd,
        "required": spec.required,
        "returncode": returncode,
        "passed": passed,
        "timed_out": timed_out,
        "duration_seconds": duration_seconds,
        "stdout_log": str(stdout_path.relative_to(logs_dir.parent)),
        "stderr_log": str(stderr_path.relative_to(logs_dir.parent)),
        "stdout_sha256": sha256_text(stdout),
        "stderr_sha256": sha256_text(stderr),
        **extra,
    }


def summarize_results(results: list[dict[str, Any]], required_files: dict[str, Any]) -> dict[str, Any]:
    failed = [
        result["name"]
        for result in results
        if result.get("required", True) and not result.get("passed", False)
    ]
    if not required_files["passed"]:
        failed.insert(0, "required_files")
    return {
        "passed": not failed,
        "failed": failed,
        "command_count": len(results),
        "passed_command_count": sum(1 for result in results if result.get("passed")),
    }


def build_metadata(
    args: argparse.Namespace,
    source_repo: Path,
    branch: str,
    *,
    source_clean_at_start: bool,
    source_status_at_start: str,
) -> dict[str, Any]:
    return {
        "created_at_utc": utc_now(),
        "claim_boundary": CLAIM_BOUNDARY,
        "source_repo": str(source_repo),
        "branch": branch,
        "python": sys.version,
        "platform": platform.platform(),
        "tool_args": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
        "source_git_head": command_output(["git", "rev-parse", "HEAD"], cwd=source_repo),
        "source_git_status_at_start": {
            "command": ["git", "status", "--short", "--branch"],
            "returncode": 0,
            "stdout": source_status_at_start,
            "stderr": "",
        },
        "source_clean_at_start": source_clean_at_start,
    }


def run_walkthrough(args: argparse.Namespace) -> dict[str, Any]:
    source_repo = Path(args.source_repo).resolve()
    branch = args.branch or current_branch(source_repo)
    cleanup_parent: Path | None = None
    checkout: Path | None = None

    source_clean, source_status = source_is_clean(source_repo)
    if not source_clean and not args.allow_dirty_source:
        raise RuntimeError(
            "Source worktree is not clean; refusing clean handoff evidence run.\n"
            f"{source_status}\n"
            "Commit or stash local changes first, or use --allow-dirty-source only for "
            "non-handoff diagnostics."
        )

    artifact_dir = prepare_artifact_dir(Path(args.artifact_root), args.run_id)
    logs_dir = artifact_dir / "logs"

    commands = build_command_plan(
        python_bin=args.python,
        include_phase0=not args.skip_phase0,
        include_update_check=not args.skip_update_check,
        include_dashboard=args.include_dashboard,
        demo_host=args.demo_host,
        gcs_host=args.gcs_host,
        public_host=args.public_host,
    )
    assert_safe_plan(commands)

    if args.plan_only:
        manifest = {
            "metadata": build_metadata(
                args,
                source_repo,
                branch,
                source_clean_at_start=source_clean,
                source_status_at_start=source_status,
            ),
            "summary": {
                "passed": True,
                "plan_only": True,
                "command_count": len(commands),
            },
            "commands": [
                {
                    "name": spec.name,
                    "command": list(spec.command),
                    "cwd": spec.cwd,
                    "env": spec.env,
                    "timeout_seconds": spec.timeout_seconds,
                }
                for spec in commands
            ],
        }
        write_json(artifact_dir / "manifest.json", manifest)
        return manifest

    try:
        checkout, cleanup_parent = clone_checkout(
            source_repo=source_repo,
            branch=branch,
            temp_root=Path(args.temp_root).resolve() if args.temp_root else None,
            keep_checkout=args.keep_checkout,
        )
        required_files = verify_required_files(checkout)
        write_json(artifact_dir / "required-files.json", required_files)

        results = []
        if required_files["passed"]:
            for spec in commands:
                results.append(run_command(spec, checkout=checkout, logs_dir=logs_dir))
                if args.stop_on_failure and not results[-1]["passed"]:
                    break

        manifest = {
            "metadata": {
                **build_metadata(
                    args,
                    source_repo,
                    branch,
                    source_clean_at_start=source_clean,
                    source_status_at_start=source_status,
                ),
                "checkout": str(checkout),
                "checkout_preserved": bool(args.keep_checkout),
            },
            "required_files": required_files,
            "summary": summarize_results(results, required_files),
            "commands": results,
        }
        write_json(artifact_dir / "manifest.json", manifest)
        return manifest
    finally:
        if cleanup_parent is not None:
            shutil.rmtree(cleanup_parent, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", default=str(PROJECT_ROOT), help="Repository to clone")
    parser.add_argument("--branch", default="", help="Branch to check out; defaults to current")
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--temp-root", default="", help="Optional temp root for the clean checkout")
    parser.add_argument("--python", default=sys.executable, help="Python executable for checks")
    parser.add_argument("--demo-host", default="192.168.10.42")
    parser.add_argument("--gcs-host", default="192.168.10.20")
    parser.add_argument("--public-host", default="pixeagle.example")
    parser.add_argument("--include-dashboard", action="store_true", help="Run npm ci/test/build in clean checkout")
    parser.add_argument("--skip-phase0", action="store_true", help="Skip schema/minimum backend tests")
    parser.add_argument(
        "--skip-update-check",
        action="store_true",
        help="Skip the stopped-runtime updater dry-run",
    )
    parser.add_argument("--stop-on-failure", action="store_true")
    parser.add_argument("--keep-checkout", action="store_true", help="Preserve temporary checkout")
    parser.add_argument("--allow-dirty-source", action="store_true", help="Diagnostic mode only")
    parser.add_argument("--plan-only", action="store_true", help="Write planned command manifest without cloning")
    parser.add_argument("--json", action="store_true", help="Print manifest JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = run_walkthrough(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json_dumps(manifest))
    else:
        summary = manifest["summary"]
        print(f"PixEagle setup handoff walkthrough: {'PASS' if summary['passed'] else 'FAIL'}")
        print(f"Claim boundary: {CLAIM_BOUNDARY}")
        print(f"Manifest: {Path(args.artifact_root).resolve() / args.run_id / 'manifest.json'}")
        if summary.get("failed"):
            print("Failed checks: " + ", ".join(summary["failed"]))
    return 0 if manifest["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
