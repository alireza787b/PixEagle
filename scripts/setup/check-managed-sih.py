#!/usr/bin/env python3
"""Read-only prerequisite doctor for PixEagle's managed PX4 SIH lifecycle."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from classes.api_auth_runtime import (  # noqa: E402
    APIAuthConfigurationError,
    load_bearer_token_records,
    load_user_records,
)
from classes.api_security_types import SYSTEM_ADMIN  # noqa: E402
from classes.managed_sih import (  # noqa: E402
    MANAGED_LEDGER_PATH,
    load_managed_sih_spec,
    probe_managed_sih,
)


DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "config.yaml"


def _check(
    check_id: str,
    status_value: str,
    message: str,
    *,
    remediation: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": check_id,
        "status": status_value,
        "message": message,
    }
    if remediation:
        payload["remediation"] = remediation
    return payload


def _resolve_project_path(value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _safe_writable_target(path: Path) -> tuple[bool, str]:
    """Check a durable file target without creating or modifying it."""
    path = path.expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = Path(os.path.abspath(path))
    if path.exists():
        try:
            file_status = path.lstat()
        except OSError as exc:
            return False, f"target metadata is unavailable ({type(exc).__name__})"
        if stat.S_ISLNK(file_status.st_mode):
            return False, "target must not be a symbolic link"
        if not stat.S_ISREG(file_status.st_mode):
            return False, "target must be a regular file"
        if file_status.st_uid != os.geteuid():
            return False, "target is not owned by the PixEagle process user"
        if not os.access(path, os.W_OK):
            return False, "target is not writable by the PixEagle process user"
        return True, "existing owner-controlled target is writable"

    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if not parent.is_dir():
        return False, "no existing parent directory is available"
    if not os.access(parent, os.W_OK | os.X_OK):
        return False, "nearest existing parent is not writable"
    return True, "target can be created below an owner-writable directory"


def _load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("configuration root must be a mapping")
    return payload


def _auth_check(streaming: dict[str, Any]) -> dict[str, Any]:
    mode = str(streaming.get("API_AUTH_MODE") or "").strip().lower()
    try:
        if mode == "browser_session":
            user_path = _resolve_project_path(streaming.get("API_SESSION_USER_FILE"))
            if user_path is None:
                raise APIAuthConfigurationError("API_SESSION_USER_FILE is empty")
            users = load_user_records(user_path)
            if not any(user.enabled and user.role == "admin" for user in users):
                raise APIAuthConfigurationError(
                    "no enabled browser-session administrator is configured"
                )
            return _check(
                "attributable_admin_auth",
                "pass",
                "Browser-session auth has at least one enabled administrator.",
            )
        if mode == "machine_bearer":
            token_path = _resolve_project_path(streaming.get("API_BEARER_TOKEN_FILE"))
            if token_path is None:
                raise APIAuthConfigurationError("API_BEARER_TOKEN_FILE is empty")
            records = load_bearer_token_records(token_path)
            if not any(
                record.is_active() and SYSTEM_ADMIN in record.scopes
                for record in records
            ):
                raise APIAuthConfigurationError(
                    "no active bearer principal has system:admin scope"
                )
            return _check(
                "attributable_admin_auth",
                "pass",
                "Machine-bearer auth has an active system administrator principal.",
            )
        raise APIAuthConfigurationError(
            "managed SIH requires browser_session or machine_bearer auth"
        )
    except APIAuthConfigurationError as exc:
        return _check(
            "attributable_admin_auth",
            "fail",
            f"Attributable administrator auth is unavailable: {exc}",
            remediation=(
                "Configure browser_session with an enabled admin user, or "
                "machine_bearer with an active system:admin token. local_compat "
                "is intentionally insufficient."
            ),
        )


def collect_checks(
    config_path: Path,
    *,
    ledger_path: Path = MANAGED_LEDGER_PATH,
) -> dict[str, Any]:
    """Collect side-effect-free host and configuration readiness checks."""
    checks: list[dict[str, Any]] = []
    checks.append(
        _check(
            "linux_host",
            "pass" if sys.platform.startswith("linux") else "fail",
            (
                "Linux host networking is available."
                if sys.platform.startswith("linux")
                else "Managed SIH is supported only on Linux hosts."
            ),
            remediation="Run managed SIH on a reviewed Linux development host.",
        )
    )

    spec = None
    try:
        spec = load_managed_sih_spec()
        checks.append(
            _check(
                "pinned_plan",
                "pass",
                "The checked-in SIH plan has a valid immutable PX4 image digest.",
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        checks.append(
            _check(
                "pinned_plan",
                "fail",
                f"The checked-in SIH plan is invalid ({type(exc).__name__}).",
                remediation="Restore and validate the checked-in Phase 2 SIH plan.",
            )
        )

    config: dict[str, Any] = {}
    try:
        config = _load_config(config_path)
        checks.append(
            _check(
                "runtime_config",
                "pass",
                "The selected PixEagle runtime configuration is readable.",
            )
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        checks.append(
            _check(
                "runtime_config",
                "fail",
                f"The selected runtime configuration is invalid ({type(exc).__name__}).",
                remediation="Run the schema check and repair the selected config first.",
            )
        )

    debugging = config.get("Debugging") if isinstance(config.get("Debugging"), dict) else {}
    enabled = debugging.get("ENABLE_MANAGED_SIH") is True
    checks.append(
        _check(
            "managed_sih_enabled",
            "pass" if enabled else "fail",
            (
                "Managed SIH is explicitly enabled."
                if enabled
                else "Debugging.ENABLE_MANAGED_SIH is not explicitly true."
            ),
            remediation=(
                "Enable Debugging.ENABLE_MANAGED_SIH only on the isolated "
                "validation host, then restart PixEagle."
            ),
        )
    )

    streaming = config.get("Streaming") if isinstance(config.get("Streaming"), dict) else {}
    checks.append(_auth_check(streaming))

    audit_enabled = streaming.get("API_SECURITY_AUDIT_ENABLED") is True
    audit_path = _resolve_project_path(streaming.get("API_SECURITY_AUDIT_LOG_PATH"))
    audit_writable, audit_detail = (
        _safe_writable_target(audit_path)
        if audit_path is not None
        else (False, "API_SECURITY_AUDIT_LOG_PATH is empty")
    )
    audit_ready = audit_enabled and audit_writable
    checks.append(
        _check(
            "durable_security_audit",
            "pass" if audit_ready else "fail",
            (
                f"Durable security audit target is ready: {audit_detail}."
                if audit_ready
                else f"Durable security audit is unavailable: {audit_detail}."
            ),
            remediation=(
                "Enable API_SECURITY_AUDIT_ENABLED and use an owner-controlled, "
                "writable, non-symlink API_SECURITY_AUDIT_LOG_PATH."
            ),
        )
    )

    ledger_writable, ledger_detail = _safe_writable_target(ledger_path)
    checks.append(
        _check(
            "durable_lifecycle_ledger",
            "pass" if ledger_writable else "fail",
            (
                f"Managed lifecycle ledger target is ready: {ledger_detail}."
                if ledger_writable
                else f"Managed lifecycle ledger is unavailable: {ledger_detail}."
            ),
            remediation="Grant the PixEagle process user ownership and write access to logs/.",
        )
    )

    host_probe: dict[str, Any] = {}
    if spec is not None:
        try:
            host_probe = probe_managed_sih(
                None,
                runtime_override={
                    "px4_connected": False,
                    "system_address": None,
                    "control_active": False,
                    "activity_available": True,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            checks.append(
                _check(
                    "docker_probe",
                    "fail",
                    f"Docker prerequisite probing failed ({type(exc).__name__}).",
                    remediation="Inspect Docker access and rerun the doctor.",
                )
            )

    if host_probe:
        cli_ready = bool(host_probe.get("docker_cli_available"))
        daemon_ready = bool(host_probe.get("docker_daemon_accessible"))
        image_ready = bool(host_probe.get("image_available"))
        checks.extend(
            [
                _check(
                    "docker_cli",
                    "pass" if cli_ready else "fail",
                    "Docker CLI is available." if cli_ready else "Docker CLI is missing.",
                    remediation="Install the reviewed Docker Engine/CLI package for this host.",
                ),
                _check(
                    "docker_daemon",
                    "pass" if daemon_ready else "fail",
                    (
                        "Docker daemon is reachable by the PixEagle process user."
                        if daemon_ready
                        else "Docker daemon is not reachable by the PixEagle process user."
                    ),
                    remediation=(
                        "Start Docker and grant the PixEagle process user reviewed daemon "
                        "access; log out/in after group membership changes."
                    ),
                ),
                _check(
                    "pinned_image",
                    "pass" if image_ready else "fail",
                    (
                        "The exact plan-pinned PX4 repository digest is installed locally."
                        if image_ready
                        else "The exact plan-pinned PX4 repository digest is not installed locally."
                    ),
                    remediation=(
                        f"Explicitly pull {spec.image} after operator approval, then rerun "
                        "the doctor and verify the expected digest."
                    ),
                ),
            ]
        )

        container_state = str(host_probe.get("container_state") or "unknown")
        ownership = bool(host_probe.get("ownership_verified"))
        if container_state == "absent":
            container_status = "pass"
            container_message = "The fixed managed-SIH container name is available for start."
        elif container_state == "running" and ownership:
            container_status = "pass"
            container_message = "The fixed managed-SIH container is running with verified ownership."
        else:
            container_status = "fail"
            container_message = (
                f"The fixed managed-SIH container slot is not actionable "
                f"(state={container_state}, ownership_verified={str(ownership).lower()})."
            )
        checks.append(
            _check(
                "managed_container_slot",
                container_status,
                container_message,
                remediation=(
                    "Do not stop an unverified container. Resolve name collisions or inspect "
                    "a stopped owned container from an operator terminal."
                ),
            )
        )

    checks.append(
        _check(
            "runtime_interlocks",
            "warn",
            (
                "PX4-disconnected state, inactive following/Offboard state, durable runtime "
                "audit availability, and explicit operator confirmation are rechecked at action time."
            ),
        )
    )
    ready = all(item["status"] != "fail" for item in checks)
    return {
        "schema_version": 1,
        "ready": ready,
        "config_path": str(config_path.resolve(strict=False)),
        "checks": checks,
        "summary": {
            status_value: sum(1 for item in checks if item["status"] == status_value)
            for status_value in ("pass", "warn", "fail")
        },
        "claim_boundary": (
            "Read-only prerequisite result only; it does not prove PX4, routing, "
            "MAVLink2REST, follower, SITL, HIL, or real-aircraft success."
        ),
    }


def _print_human(report: dict[str, Any]) -> None:
    print("PixEagle managed SIH prerequisite doctor")
    print(f"Config: {report['config_path']}")
    print()
    for item in report["checks"]:
        label = item["status"].upper()
        print(f"[{label:<4}] {item['message']}")
        if item.get("remediation") and item["status"] == "fail":
            print(f"       Next: {item['remediation']}")
    print()
    print("READY" if report["ready"] else "BLOCKED")
    print(report["claim_boundary"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Runtime config to inspect (default: configs/config.yaml)",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    args = parser.parse_args(argv)
    config_path = args.config.expanduser()
    if not config_path.is_absolute():
        config_path = (PROJECT_ROOT / config_path).resolve()
    report = collect_checks(config_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
