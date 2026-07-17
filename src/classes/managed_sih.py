"""Guarded lifecycle for one pinned, PixEagle-owned official PX4 SIH container."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, Optional
import uuid

from fastapi import status

from classes.api_security_types import (
    APIAuditPolicy,
    APIPrincipal,
    APIPrincipalKind,
    APISensitivity,
    SYSTEM_ADMIN,
)
from classes.api_v1_actions import get_control_activity_state
from classes.api_v1_contracts import SITLManagedLifecycleRequest
from classes.api_v1_paths import (
    API_V1_ACTION_MANAGED_SIH_START_PATH,
    API_V1_ACTION_MANAGED_SIH_STOP_PATH,
)
from classes.parameters import Parameters


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITL_PLAN_PATH = (
    PROJECT_ROOT / "tools" / "sitl_plans" / "phase2_follower_validation.json"
)
MANAGED_CONTAINER_NAME = "pixeagle-managed-px4-sih"
MANAGED_CONTAINER_LABEL = "org.pixeagle.sitl.managed"
MANAGED_PROFILE_LABEL = "org.pixeagle.sitl.profile"
MANAGED_RUN_ID_LABEL = "org.pixeagle.sitl.run_id"
MANAGED_MODEL_LABEL = "org.pixeagle.sitl.model"
MANAGED_IMAGE_DIGEST_LABEL = "org.pixeagle.sitl.image_digest"
MANAGED_PROFILE = "official_px4_sih"
DOCKER_PROBE_TIMEOUT_S = 2.0
DOCKER_MUTATION_TIMEOUT_S = 20.0
MAX_DOCKER_OUTPUT_CHARS = 2048
MAX_DOCKER_PARSE_OUTPUT_CHARS = 16384
MANAGED_CPU_LIMIT = "1.5"
MANAGED_MEMORY_LIMIT = "1g"
MANAGED_PID_LIMIT = "256"
MANAGED_LOG_MAX_SIZE = "10m"
MANAGED_LOG_MAX_FILES = "2"
MANAGED_LEDGER_PATH = PROJECT_ROOT / "logs" / "managed_sih_actions.json"
MANAGED_LEDGER_MAX_ENTRIES = 100
SAFE_IMAGE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,299}$")
SAFE_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
SAFE_IMAGE_ID_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_REPO_DIGEST_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,260}@sha256:[0-9a-f]{64}$")

_IMAGE_INSPECT_FORMAT = "{{json .RepoDigests}}\n{{json .Id}}"
_CONTAINER_INSPECT_FORMAT = "\n".join(
    (
        "{{json .Id}}",
        "{{json .Image}}",
        "{{json .State.Running}}",
        "{{json .Config.Image}}",
        "{{json .HostConfig.NetworkMode}}",
        "{{json .Config.Labels}}",
        "{{json .Config.Env}}",
    )
)
_LEDGER_LOCK = threading.RLock()


class ManagedSIHError(RuntimeError):
    """Typed fail-closed managed-SIH lifecycle failure."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = dict(details or {})


@dataclass(frozen=True)
class ManagedSIHSpec:
    """Immutable process inputs derived from the checked-in validation plan."""

    image: str
    model: str
    expected_repo_digest: str
    network_mode: str


def _image_repository(image: str) -> str:
    """Return the repository portion of a tagged Docker image reference."""
    without_digest = image.split("@", 1)[0]
    final_slash = without_digest.rfind("/")
    final_colon = without_digest.rfind(":")
    return (
        without_digest[:final_colon]
        if final_colon > final_slash
        else without_digest
    )


def load_managed_sih_spec(
    plan_path: Path = DEFAULT_SITL_PLAN_PATH,
) -> ManagedSIHSpec:
    """Load and strictly validate the only browser-manageable SIH profile."""
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    px4 = payload.get("stack", {}).get("px4", {}) if isinstance(payload, dict) else {}
    image = str(px4.get("recommended_image") or "")
    model = str(px4.get("vehicle_model") or "")
    expected_digest = str(px4.get("expected_repo_digest") or "")
    network_mode = str(px4.get("network_mode") or "")

    if not SAFE_IMAGE_PATTERN.fullmatch(image):
        raise ValueError("The managed SIH plan contains an invalid PX4 image reference.")
    if not SAFE_MODEL_PATTERN.fullmatch(model):
        raise ValueError("The managed SIH plan contains an invalid PX4 model.")
    if (
        not SAFE_REPO_DIGEST_PATTERN.fullmatch(expected_digest)
        or not expected_digest.startswith(f"{_image_repository(image)}@sha256:")
    ):
        raise ValueError("The managed SIH plan requires a valid immutable image digest.")
    if network_mode != "host":
        raise ValueError("The managed SIH browser profile requires Linux host networking.")
    return ManagedSIHSpec(
        image=image,
        model=model,
        expected_repo_digest=expected_digest,
        network_mode=network_mode,
    )


def _bounded_text(value: Any, *, limit: int = MAX_DOCKER_OUTPUT_CHARS) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value or "").strip()[:limit]


def _run_docker(
    args: list[str],
    *,
    timeout_s: float,
    max_output_chars: int = MAX_DOCKER_OUTPUT_CHARS,
) -> Dict[str, Any]:
    """Run one fixed Docker argv without a shell and return bounded diagnostics."""
    try:
        completed = subprocess.run(
            ["docker", *args],
            cwd=str(PROJECT_ROOT),
            text=True,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "docker executable not found",
            "timed_out": False,
            "stdout_truncated": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "stdout": _bounded_text(exc.stdout, limit=max_output_chars),
            "stderr": "docker command timed out",
            "timed_out": True,
            "stdout_truncated": bool(
                exc.stdout and len(str(exc.stdout)) > max_output_chars
            ),
        }
    except OSError as exc:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": _bounded_text(exc),
            "timed_out": False,
            "stdout_truncated": False,
        }
    stdout = str(completed.stdout or "").strip()
    return {
        "returncode": completed.returncode,
        "stdout": _bounded_text(stdout, limit=max_output_chars),
        "stderr": _bounded_text(completed.stderr),
        "timed_out": False,
        "stdout_truncated": len(stdout) > max_output_chars,
    }


def _json_lines(text: str, *, expected_count: int) -> Optional[list[Any]]:
    lines = str(text or "").splitlines()
    if len(lines) != expected_count:
        return None
    try:
        return [json.loads(line) for line in lines]
    except (TypeError, json.JSONDecodeError):
        return None


def _inspect_image(spec: ManagedSIHSpec) -> Dict[str, Any]:
    result = _run_docker(
        ["image", "inspect", "--format", _IMAGE_INSPECT_FORMAT, spec.image],
        timeout_s=DOCKER_PROBE_TIMEOUT_S,
        max_output_chars=MAX_DOCKER_PARSE_OUTPUT_CHARS,
    )
    parsed = None if result.get("stdout_truncated") else _json_lines(
        result.get("stdout", ""),
        expected_count=2,
    )
    if result.get("returncode") != 0 or parsed is None:
        return {"result": result, "repo_digests": None, "image_id": None}
    repo_digests, image_id = parsed
    if not isinstance(repo_digests, list) or not isinstance(image_id, str):
        return {"result": result, "repo_digests": None, "image_id": None}
    return {
        "result": result,
        "repo_digests": repo_digests,
        "image_id": image_id if SAFE_IMAGE_ID_PATTERN.fullmatch(image_id) else None,
    }


def _inspect_container(reference: str) -> Dict[str, Any]:
    result = _run_docker(
        ["container", "inspect", "--format", _CONTAINER_INSPECT_FORMAT, reference],
        timeout_s=DOCKER_PROBE_TIMEOUT_S,
        max_output_chars=MAX_DOCKER_PARSE_OUTPUT_CHARS,
    )
    parsed = None if result.get("stdout_truncated") else _json_lines(
        result.get("stdout", ""),
        expected_count=7,
    )
    if result.get("returncode") != 0 or parsed is None:
        return {"result": result, "container": None}
    (
        container_id,
        image_id,
        running,
        config_image,
        network_mode,
        labels,
        environment,
    ) = parsed
    if not (
        isinstance(container_id, str)
        and isinstance(image_id, str)
        and isinstance(running, bool)
        and isinstance(config_image, str)
        and isinstance(network_mode, str)
        and isinstance(labels, dict)
        and isinstance(environment, list)
    ):
        return {"result": result, "container": None}
    return {
        "result": result,
        "container": {
            "Id": container_id,
            "Image": image_id,
            "State": {"Running": running},
            "Config": {
                "Image": config_image,
                "Labels": labels,
                "Env": environment,
            },
            "HostConfig": {"NetworkMode": network_mode},
        },
    }


def _container_ownership(
    inspect_payload: Dict[str, Any],
    spec: ManagedSIHSpec,
    *,
    expected_image_id: Optional[str],
    expected_run_id: Optional[str] = None,
) -> bool:
    config = inspect_payload.get("Config")
    host_config = inspect_payload.get("HostConfig")
    if not isinstance(config, dict) or not isinstance(host_config, dict):
        return False
    labels = config.get("Labels")
    environment = config.get("Env")
    if not isinstance(labels, dict) or not isinstance(environment, list):
        return False
    return bool(
        labels.get(MANAGED_CONTAINER_LABEL) == "true"
        and labels.get(MANAGED_PROFILE_LABEL) == MANAGED_PROFILE
        and str(labels.get(MANAGED_RUN_ID_LABEL) or "")
        and (
            expected_run_id is None
            or labels.get(MANAGED_RUN_ID_LABEL) == expected_run_id
        )
        and labels.get(MANAGED_MODEL_LABEL) == spec.model
        and labels.get(MANAGED_IMAGE_DIGEST_LABEL) == spec.expected_repo_digest
        and config.get("Image") == spec.expected_repo_digest
        and expected_image_id is not None
        and inspect_payload.get("Image") == expected_image_id
        and f"PX4_SIM_MODEL={spec.model}" in environment
        and host_config.get("NetworkMode") == spec.network_mode
    )


def _runtime_summary(owner: Optional[Any]) -> Dict[str, Any]:
    summary = {
        "px4_connected": None,
        "system_address": None,
        "control_active": False,
        "activity_available": owner is not None,
    }
    if owner is None:
        return summary

    try:
        activity = get_control_activity_state(owner)
        summary["control_active"] = bool(activity.get("control_active"))
    except Exception:
        summary["activity_available"] = False

    app_controller = getattr(owner, "app_controller", None)
    px4 = getattr(app_controller, "px4_interface", None)
    status_getter = getattr(px4, "get_connection_status", None)
    if callable(status_getter):
        try:
            connection = status_getter()
        except Exception:
            connection = None
        if isinstance(connection, dict):
            connected = connection.get("connected")
            summary["px4_connected"] = connected if isinstance(connected, bool) else None
            system_address = connection.get("system_address")
            summary["system_address"] = (
                str(system_address) if system_address is not None else None
            )
    return summary


def probe_managed_sih(
    owner: Optional[Any] = None,
    runtime_override: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return private readiness state used by status and guarded mutations."""
    feature_enabled = bool(getattr(Parameters, "ENABLE_MANAGED_SIH", False))
    runtime = dict(runtime_override) if runtime_override is not None else _runtime_summary(owner)
    probe: Dict[str, Any] = {
        "feature_enabled": feature_enabled,
        "readiness": "unavailable" if feature_enabled else "disabled",
        "docker_cli_available": shutil.which("docker") is not None,
        "docker_daemon_accessible": False,
        "docker_server_version": None,
        "image_available": False,
        "image_id": None,
        "container_name": MANAGED_CONTAINER_NAME,
        "container_state": "unknown",
        "container_id": None,
        "full_container_id": None,
        "ownership_verified": False,
        "start_available": False,
        "stop_available": False,
        "start_path": API_V1_ACTION_MANAGED_SIH_START_PATH,
        "stop_path": API_V1_ACTION_MANAGED_SIH_STOP_PATH,
        "px4_connected": runtime["px4_connected"],
        "system_address": runtime["system_address"],
        "control_state_available": runtime["activity_available"],
        "control_active": runtime["control_active"],
        "routing_managed_by_dashboard": False,
        "start_requires_no_real_aircraft_confirmation": True,
        "stop_requires_no_real_aircraft_confirmation": False,
        "reasons": [],
        "warnings": [
            "The dashboard manages only the pinned PX4 SIH container; routing, "
            "MAVLink2REST, and PixEagle remain independently supervised."
        ],
        "spec": None,
    }
    try:
        spec = load_managed_sih_spec()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        probe["reasons"].append(f"managed_sih_plan_invalid:{type(exc).__name__}")
        return probe
    probe["spec"] = spec

    if not probe["docker_cli_available"]:
        probe["reasons"].append("docker_cli_missing")
        return probe

    daemon = _run_docker(
        ["version", "--format", "{{.Server.Version}}"],
        timeout_s=DOCKER_PROBE_TIMEOUT_S,
    )
    if daemon["returncode"] != 0 or not daemon["stdout"]:
        probe["reasons"].append("docker_daemon_unavailable")
        return probe
    probe["docker_daemon_accessible"] = True
    probe["docker_server_version"] = daemon["stdout"].splitlines()[0]

    image_probe = _inspect_image(spec)
    repo_digests = image_probe["repo_digests"]
    image_id = image_probe["image_id"]
    if image_probe["result"].get("returncode") == 0:
        digest_ok = bool(
            isinstance(repo_digests, list)
            and spec.expected_repo_digest in repo_digests
            and image_id is not None
        )
        probe["image_available"] = digest_ok
        probe["image_id"] = image_id if digest_ok else None
        if not digest_ok:
            probe["reasons"].append("pinned_image_digest_mismatch")
    else:
        probe["reasons"].append("pinned_image_missing")

    container_probe = _inspect_container(MANAGED_CONTAINER_NAME)
    container_result = container_probe["result"]
    if container_result["returncode"] == 0:
        container = container_probe["container"]
        if container is None:
            probe["reasons"].append("container_inspect_invalid")
        else:
            container_id = str(container.get("Id") or "")
            running = bool((container.get("State") or {}).get("Running"))
            owned = _container_ownership(
                container,
                spec,
                expected_image_id=probe["image_id"],
            )
            probe["full_container_id"] = container_id or None
            probe["container_id"] = container_id[:12] or None
            probe["ownership_verified"] = owned
            if not owned:
                probe["container_state"] = "conflict"
                probe["reasons"].append("container_name_owned_by_another_process")
            else:
                probe["container_state"] = "running" if running else "stopped"
    elif "no such" in container_result["stderr"].lower():
        probe["container_state"] = "absent"
    else:
        probe["reasons"].append("container_inspect_failed")

    if not runtime["activity_available"]:
        probe["reasons"].append("control_activity_state_unavailable")
    elif runtime["control_active"]:
        probe["reasons"].append("following_or_offboard_active")

    if runtime["px4_connected"] is None:
        probe["reasons"].append("px4_connection_state_unavailable")
    elif runtime["px4_connected"] is True and probe["container_state"] != "running":
        probe["reasons"].append("px4_already_connected")

    audit_logger = getattr(owner, "security_audit_logger", None) if owner else None
    audit_available = bool(
        audit_logger is not None and getattr(audit_logger, "enabled", False)
    )
    if owner is not None and not audit_available:
        probe["reasons"].append("durable_audit_unavailable")

    can_mutate = bool(
        feature_enabled
        and probe["docker_daemon_accessible"]
        and runtime["activity_available"]
        and not runtime["control_active"]
        and audit_available
    )
    probe["start_available"] = bool(
        can_mutate
        and probe["image_available"]
        and probe["container_state"] == "absent"
        and runtime["px4_connected"] is False
    )
    probe["stop_available"] = bool(
        can_mutate
        and probe["container_state"] == "running"
        and probe["ownership_verified"]
    )

    if not feature_enabled:
        probe["readiness"] = "disabled"
    elif probe["container_state"] == "conflict":
        probe["readiness"] = "conflict"
    elif not probe["docker_daemon_accessible"]:
        probe["readiness"] = "unavailable"
    elif probe["container_state"] == "running" and probe["ownership_verified"]:
        probe["readiness"] = "running"
    elif probe["image_available"] and probe["container_state"] == "absent":
        probe["readiness"] = "ready"
    else:
        probe["readiness"] = "setup_required"

    return probe


def public_managed_sih_status(owner: Optional[Any] = None) -> Dict[str, Any]:
    """Return the typed public subset of the managed-SIH probe."""
    probe = probe_managed_sih(owner)
    return {
        key: value
        for key, value in probe.items()
        if key not in {"full_container_id", "image_id", "spec"}
    }


def _request_principal(http_request: Any) -> Optional[APIPrincipal]:
    principal = getattr(getattr(http_request, "state", None), "api_principal", None)
    return principal if isinstance(principal, APIPrincipal) else None


def _principal_can_manage_sih(principal: Optional[APIPrincipal]) -> bool:
    return bool(
        principal is not None
        and SYSTEM_ADMIN in principal.scopes
        and principal.kind in {APIPrincipalKind.SESSION, APIPrincipalKind.BEARER}
        and (
            principal.kind != APIPrincipalKind.SESSION
            or principal.role == "admin"
        )
    )


def _idempotency_digest(idempotency_key: str) -> str:
    return hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()


def _lifecycle_ledger_path(path: Optional[Path]) -> Path:
    return MANAGED_LEDGER_PATH if path is None else path


def _load_lifecycle_ledger(path: Optional[Path] = None) -> Dict[str, Any]:
    path = _lifecycle_ledger_path(path)
    if not path.exists():
        return {"schema_version": 1, "entries": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManagedSIHError(
            "ACTION_MANAGED_SIH_LEDGER_UNAVAILABLE",
            "The durable managed-SIH lifecycle ledger could not be read.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != 1
        or not isinstance(entries, list)
    ):
        raise ManagedSIHError(
            "ACTION_MANAGED_SIH_LEDGER_INVALID",
            "The durable managed-SIH lifecycle ledger is invalid.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return {"schema_version": 1, "entries": entries[-MANAGED_LEDGER_MAX_ENTRIES:]}


def _write_lifecycle_ledger(
    payload: Dict[str, Any],
    path: Optional[Path] = None,
) -> None:
    path = _lifecycle_ledger_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ManagedSIHError(
            "ACTION_MANAGED_SIH_LEDGER_UNAVAILABLE",
            "The durable managed-SIH lifecycle ledger could not be written.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc


def _find_lifecycle_entry(
    action_type: str,
    idempotency_key: str,
    *,
    path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    path = _lifecycle_ledger_path(path)
    digest = _idempotency_digest(idempotency_key)
    with _LEDGER_LOCK:
        ledger = _load_lifecycle_ledger(path)
        for entry in reversed(ledger["entries"]):
            if (
                isinstance(entry, dict)
                and entry.get("action_type") == action_type
                and entry.get("idempotency_key_sha256") == digest
            ):
                return dict(entry)
    return None


def _begin_lifecycle_entry(
    action_type: str,
    idempotency_key: str,
    operation_id: str,
    *,
    path: Optional[Path] = None,
) -> None:
    path = _lifecycle_ledger_path(path)
    now = time.time()
    entry = {
        "operation_id": operation_id,
        "action_type": action_type,
        "idempotency_key_sha256": _idempotency_digest(idempotency_key),
        "status": "in_progress",
        "started_at": now,
        "updated_at": now,
        "result": {},
        "error": None,
    }
    with _LEDGER_LOCK:
        ledger = _load_lifecycle_ledger(path)
        ledger["entries"].append(entry)
        ledger["entries"] = ledger["entries"][-MANAGED_LEDGER_MAX_ENTRIES:]
        _write_lifecycle_ledger(ledger, path)


def _finish_lifecycle_entry(
    operation_id: str,
    *,
    status_value: str,
    result: Dict[str, Any],
    error: Optional[str],
    path: Optional[Path] = None,
) -> None:
    path = _lifecycle_ledger_path(path)
    if status_value not in {"success", "failure", "unknown"}:
        raise ValueError(f"Unsupported managed-SIH ledger status: {status_value!r}")
    with _LEDGER_LOCK:
        ledger = _load_lifecycle_ledger(path)
        for entry in reversed(ledger["entries"]):
            if isinstance(entry, dict) and entry.get("operation_id") == operation_id:
                entry["status"] = status_value
                entry["updated_at"] = time.time()
                entry["result"] = {
                    str(key)[:80]: value
                    for key, value in result.items()
                    if isinstance(value, (str, int, float, bool)) or value is None
                }
                entry["error"] = str(error)[:512] if error else None
                _write_lifecycle_ledger(ledger, path)
                return
    raise ManagedSIHError(
        "ACTION_MANAGED_SIH_LEDGER_UNAVAILABLE",
        "The durable managed-SIH lifecycle operation could not be finalized.",
        status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _durable_replay(
    owner: Any,
    request: SITLManagedLifecycleRequest,
    *,
    action_type: str,
) -> Optional[Dict[str, Any]]:
    if not request.idempotency_key:
        return None
    entry = _find_lifecycle_entry(action_type, request.idempotency_key)
    if entry is None:
        return None
    ledger_status = str(entry.get("status") or "unknown")
    status_value = "success" if ledger_status == "success" else "failure"
    record = _store_action(
        owner,
        request,
        action_type=action_type,
        status_value=status_value,
        accepted=True,
        executed=True,
        result={
            "durable_replay": True,
            "operation_id": entry.get("operation_id"),
            "lifecycle_status": ledger_status,
            **dict(entry.get("result") or {}),
        },
        error=entry.get("error"),
    )
    record["idempotent_replay"] = True
    owner._store_action_record(record)
    return record


def _record_pre_execution_audit(
    owner: Any,
    http_request: Any,
    *,
    action_type: str,
    path: str,
    probe: Dict[str, Any],
    operation_id: str,
) -> None:
    principal = _request_principal(http_request)
    audit_logger = getattr(owner, "security_audit_logger", None)
    if (
        not _principal_can_manage_sih(principal)
        or audit_logger is None
        or not getattr(audit_logger, "enabled", False)
    ):
        raise ManagedSIHError(
            "ACTION_MANAGED_SIH_AUDIT_UNAVAILABLE",
            "A durable managed-SIH audit event is unavailable.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    headers = getattr(http_request, "headers", {})
    recorded = audit_logger.record_event(
        event_type=f"api.action.{action_type}.pre_execute",
        outcome="allowed",
        reason="managed_sih_pre_execute_accepted",
        transport="http",
        method="POST",
        path=path,
        status_code=status.HTTP_202_ACCEPTED,
        principal=principal,
        audit_policy=APIAuditPolicy.SECURITY_CRITICAL,
        sensitivity=APISensitivity.SYSTEM,
        client_host=getattr(getattr(http_request, "client", None), "host", None),
        host_header=headers.get("host"),
        origin=headers.get("origin"),
        sec_fetch_site=headers.get("sec-fetch-site"),
        request_id=headers.get("x-request-id"),
        metadata={
            "profile": MANAGED_PROFILE,
            "container_name": MANAGED_CONTAINER_NAME,
            "container_state": probe["container_state"],
            "image": probe["spec"].image,
            "model": probe["spec"].model,
            "operation_id": operation_id,
        },
    )
    if not recorded:
        raise ManagedSIHError(
            "ACTION_MANAGED_SIH_AUDIT_UNAVAILABLE",
            "The durable managed-SIH audit event was not recorded.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def _record_execution_audit(
    owner: Any,
    http_request: Any,
    *,
    action_type: str,
    path: str,
    operation_id: str,
    outcome: str,
    reason: str,
    status_code: int,
    result: Dict[str, Any],
) -> None:
    principal = _request_principal(http_request)
    audit_logger = getattr(owner, "security_audit_logger", None)
    if (
        not _principal_can_manage_sih(principal)
        or audit_logger is None
        or not getattr(audit_logger, "enabled", False)
    ):
        raise ManagedSIHError(
            "ACTION_MANAGED_SIH_AUDIT_UNAVAILABLE",
            "A durable managed-SIH completion audit event is unavailable.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    headers = getattr(http_request, "headers", {})
    recorded = audit_logger.record_event(
        event_type=f"api.action.{action_type}.complete",
        outcome=outcome,
        reason=reason,
        transport="http",
        method="POST",
        path=path,
        status_code=status_code,
        principal=principal,
        audit_policy=APIAuditPolicy.SECURITY_CRITICAL,
        sensitivity=APISensitivity.SYSTEM,
        client_host=getattr(getattr(http_request, "client", None), "host", None),
        host_header=headers.get("host"),
        origin=headers.get("origin"),
        sec_fetch_site=headers.get("sec-fetch-site"),
        request_id=headers.get("x-request-id"),
        metadata={
            "profile": MANAGED_PROFILE,
            "container_name": MANAGED_CONTAINER_NAME,
            "operation_id": operation_id,
            "lifecycle_status": result.get("lifecycle_status"),
            "ownership_verified": result.get("ownership_verified"),
            "stopped": result.get("stopped"),
        },
    )
    if not recorded:
        raise ManagedSIHError(
            "ACTION_MANAGED_SIH_AUDIT_UNAVAILABLE",
            "The durable managed-SIH completion audit event was not recorded.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def _reconciled_container(
    spec: ManagedSIHSpec,
    *,
    expected_image_id: str,
    expected_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    inspected = _inspect_container(MANAGED_CONTAINER_NAME)
    container = inspected["container"]
    owned = bool(
        container is not None
        and _container_ownership(
            container,
            spec,
            expected_image_id=expected_image_id,
            expected_run_id=expected_run_id,
        )
    )
    return {
        "result": inspected["result"],
        "container": container,
        "owned": owned,
        "running": bool(container and (container.get("State") or {}).get("Running")),
    }


def _run_managed_start(probe: Dict[str, Any]) -> Dict[str, Any]:
    spec: ManagedSIHSpec = probe["spec"]
    expected_image_id = str(probe.get("image_id") or "")
    if not SAFE_IMAGE_ID_PATTERN.fullmatch(expected_image_id):
        raise ManagedSIHError(
            "ACTION_MANAGED_SIH_IMAGE_ID_UNAVAILABLE",
            "The verified immutable PX4 image ID is unavailable.",
            status.HTTP_409_CONFLICT,
        )
    run_id = str(probe.get("operation_id") or f"managed-{uuid.uuid4()}")
    result = _run_docker(
        [
            "run",
            "-d",
            "--rm",
            "--init",
            "--name",
            MANAGED_CONTAINER_NAME,
            "--network",
            spec.network_mode,
            "--pull=never",
            "--cpus",
            MANAGED_CPU_LIMIT,
            "--memory",
            MANAGED_MEMORY_LIMIT,
            "--pids-limit",
            MANAGED_PID_LIMIT,
            "--log-driver",
            "local",
            "--log-opt",
            f"max-size={MANAGED_LOG_MAX_SIZE}",
            "--log-opt",
            f"max-file={MANAGED_LOG_MAX_FILES}",
            "--label",
            f"{MANAGED_CONTAINER_LABEL}=true",
            "--label",
            f"{MANAGED_PROFILE_LABEL}={MANAGED_PROFILE}",
            "--label",
            f"{MANAGED_RUN_ID_LABEL}={run_id}",
            "--label",
            f"{MANAGED_MODEL_LABEL}={spec.model}",
            "--label",
            f"{MANAGED_IMAGE_DIGEST_LABEL}={spec.expected_repo_digest}",
            "-e",
            f"PX4_SIM_MODEL={spec.model}",
            spec.expected_repo_digest,
        ],
        timeout_s=DOCKER_MUTATION_TIMEOUT_S,
    )
    if result["returncode"] != 0:
        reconciled = _reconciled_container(
            spec,
            expected_image_id=expected_image_id,
            expected_run_id=run_id,
        )
        container = reconciled["container"]
        if reconciled["owned"] and reconciled["running"] and container is not None:
            container_id = str(container.get("Id") or "")
            return {
                "container_id": container_id[:12],
                "container_name": MANAGED_CONTAINER_NAME,
                "image": spec.expected_repo_digest,
                "model": spec.model,
                "ownership_verified": True,
                "reconciled_after_timeout": bool(result.get("timed_out")),
            }
        raise ManagedSIHError(
            (
                "ACTION_MANAGED_SIH_START_OUTCOME_UNKNOWN"
                if result.get("timed_out")
                and reconciled["result"].get("returncode") != 0
                else "ACTION_MANAGED_SIH_START_FAILED"
            ),
            (
                "Docker start timed out and the managed container state could not be reconciled."
                if result.get("timed_out")
                and reconciled["result"].get("returncode") != 0
                else "Docker did not start the pinned PX4 SIH container."
            ),
            status.HTTP_503_SERVICE_UNAVAILABLE,
            details={
                "docker_error": result["stderr"],
                "outcome_unknown": bool(
                    result.get("timed_out")
                    and reconciled["result"].get("returncode") != 0
                ),
            },
        )

    container_id = result["stdout"].splitlines()[-1] if result["stdout"] else ""
    inspect_probe = _inspect_container(container_id)
    inspect_result = inspect_probe["result"]
    inspected = inspect_probe["container"]
    verified = bool(
        container_id
        and inspect_result["returncode"] == 0
        and inspected is not None
        and _container_ownership(
            inspected,
            spec,
            expected_image_id=expected_image_id,
            expected_run_id=run_id,
        )
        and bool((inspected.get("State") or {}).get("Running"))
    )
    if not verified:
        rollback = (
            _run_docker(
                ["stop", "--time", "10", container_id],
                timeout_s=DOCKER_MUTATION_TIMEOUT_S,
            )
            if container_id
            else {"returncode": None, "stderr": "container id unavailable"}
        )
        raise ManagedSIHError(
            "ACTION_MANAGED_SIH_START_UNVERIFIED",
            "The started container could not be ownership-verified and rollback was attempted.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
            details={
                "rollback_succeeded": rollback.get("returncode") == 0,
                "rollback_error": rollback.get("stderr"),
            },
        )
    return {
        "container_id": container_id[:12],
        "container_name": MANAGED_CONTAINER_NAME,
        "image": spec.expected_repo_digest,
        "model": spec.model,
        "ownership_verified": True,
        "reconciled_after_timeout": False,
    }


def _run_managed_stop(probe: Dict[str, Any]) -> Dict[str, Any]:
    container_id = str(probe.get("full_container_id") or "")
    if not container_id or not probe.get("ownership_verified"):
        raise ManagedSIHError(
            "ACTION_MANAGED_SIH_OWNERSHIP_UNVERIFIED",
            "PixEagle will not stop a container whose ownership is not verified.",
            status.HTTP_409_CONFLICT,
        )
    result = _run_docker(
        ["stop", "--time", "10", container_id],
        timeout_s=DOCKER_MUTATION_TIMEOUT_S,
    )
    if result["returncode"] != 0:
        spec: ManagedSIHSpec = probe["spec"]
        expected_image_id = str(probe.get("image_id") or "")
        reconciled = _reconciled_container(
            spec,
            expected_image_id=expected_image_id,
        )
        inspect_result = reconciled["result"]
        absent = (
            inspect_result.get("returncode") != 0
            and "no such" in str(inspect_result.get("stderr") or "").lower()
        )
        stopped = bool(
            reconciled["owned"]
            and reconciled["container"] is not None
            and not reconciled["running"]
        )
        if absent or stopped:
            return {
                "container_id": container_id[:12],
                "container_name": MANAGED_CONTAINER_NAME,
                "ownership_verified": True,
                "stopped": True,
                "reconciled_after_timeout": bool(result.get("timed_out")),
            }
        raise ManagedSIHError(
            (
                "ACTION_MANAGED_SIH_STOP_OUTCOME_UNKNOWN"
                if result.get("timed_out")
                and inspect_result.get("returncode") != 0
                else "ACTION_MANAGED_SIH_STOP_FAILED"
            ),
            (
                "Docker stop timed out and the managed container state could not be reconciled."
                if result.get("timed_out")
                and inspect_result.get("returncode") != 0
                else "Docker did not stop the verified PX4 SIH container."
            ),
            status.HTTP_503_SERVICE_UNAVAILABLE,
            details={
                "docker_error": result["stderr"],
                "outcome_unknown": bool(
                    result.get("timed_out")
                    and inspect_result.get("returncode") != 0
                ),
            },
        )
    return {
        "container_id": container_id[:12],
        "container_name": MANAGED_CONTAINER_NAME,
        "ownership_verified": True,
        "stopped": True,
        "reconciled_after_timeout": False,
    }


def _store_action(
    owner: Any,
    request: SITLManagedLifecycleRequest,
    *,
    action_type: str,
    status_value: str,
    accepted: bool,
    executed: bool,
    result: Dict[str, Any],
    error: Optional[str] = None,
) -> Dict[str, Any]:
    following = bool(getattr(owner.app_controller, "following_active", False))
    return owner._store_action_record(
        owner._new_api_action_record(
            action_type=action_type,
            request=request,
            status_value=status_value,
            accepted=accepted,
            executed=executed,
            following_active_before=following,
            following_active_after=following,
            result=result,
            error=error,
        )
    )


def _rejection(
    owner: Any,
    request: SITLManagedLifecycleRequest,
    *,
    action_type: str,
    path: str,
    code: str,
    message: str,
    status_code: int,
    result: Optional[Dict[str, Any]] = None,
    accepted: bool = False,
    executed: bool = False,
) -> Any:
    record = _store_action(
        owner,
        request,
        action_type=action_type,
        status_value="failure",
        accepted=accepted,
        executed=executed,
        result={"precondition": code, **dict(result or {})},
        error=message,
    )
    return owner._api_v1_error_response(
        status_code=status_code,
        code=code,
        detail={
            "message": message,
            "action_type": action_type,
            "action_id": record["action_id"],
        },
        path=path,
    )


async def _await_managed_mutation(
    operation: str,
    probe: Dict[str, Any],
) -> tuple[Dict[str, Any], bool]:
    mutation = _run_managed_start if operation == "start" else _run_managed_stop
    task = asyncio.create_task(
        asyncio.to_thread(mutation, probe),
        name=f"pixeagle-managed-sih-{operation}",
    )
    cancellation_requested = False
    while True:
        try:
            result = await asyncio.shield(task)
            return result, cancellation_requested
        except asyncio.CancelledError:
            cancellation_requested = True
            current = asyncio.current_task()
            if current is not None and hasattr(current, "uncancel"):
                current.uncancel()


async def _managed_sih_action_on_flight_loop(
    owner: Any,
    request: SITLManagedLifecycleRequest,
    response: Any,
    http_request: Any,
    *,
    operation: str,
) -> Any:
    action_type = f"managed_sih_{operation}"
    path = (
        API_V1_ACTION_MANAGED_SIH_START_PATH
        if operation == "start"
        else API_V1_ACTION_MANAGED_SIH_STOP_PATH
    )
    principal = _request_principal(http_request)
    if not _principal_can_manage_sih(principal):
        return _rejection(
            owner,
            request,
            action_type=action_type,
            path=path,
            code="ACTION_MANAGED_SIH_ADMIN_REQUIRED",
            message=(
                "Managed SIH lifecycle actions require an attributable admin "
                "browser session or dedicated system:admin bearer principal."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if not request.dry_run and not request.confirm:
        return owner._confirmation_required_response(
            action_type=action_type,
            request=request,
            path=path,
        )
    if (
        operation == "start"
        and not request.dry_run
        and not request.no_real_aircraft_confirmed
    ):
        return _rejection(
            owner,
            request,
            action_type=action_type,
            path=path,
            code="ACTION_MANAGED_SIH_REAL_AIRCRAFT_CONFIRMATION_REQUIRED",
            message=(
                "Confirm that no real aircraft, HIL rig, or motor-enabled hardware "
                "is connected before starting SIH."
            ),
            status_code=status.HTTP_409_CONFLICT,
        )
    if not request.dry_run:
        replay = owner._lookup_idempotent_action(action_type, request.idempotency_key)
        if replay:
            response.status_code = status.HTTP_200_OK
            return replay
        durable_replay = _durable_replay(
            owner,
            request,
            action_type=action_type,
        )
        if durable_replay:
            response.status_code = status.HTTP_200_OK
            return durable_replay

    state_lock = getattr(owner.app_controller, "_follower_state_lock", None)
    if state_lock is None or not all(
        callable(getattr(state_lock, method, None)) for method in ("acquire", "release")
    ):
        return _rejection(
            owner,
            request,
            action_type=action_type,
            path=path,
            code="ACTION_MANAGED_SIH_BARRIER_UNAVAILABLE",
            message="The follower-state barrier is unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    acquired = False
    operation_id: Optional[str] = None
    pre_audited = False
    ledger_started = False
    mutation_started = False
    try:
        await asyncio.wait_for(state_lock.acquire(), timeout=5.0)
        acquired = True
        runtime = _runtime_summary(owner)
        probe = await asyncio.to_thread(probe_managed_sih, owner, runtime)
        if not probe["feature_enabled"]:
            raise ManagedSIHError(
                "ACTION_MANAGED_SIH_DISABLED",
                "Enable Debugging.ENABLE_MANAGED_SIH and restart PixEagle first.",
                status.HTTP_403_FORBIDDEN,
            )
        if probe["control_active"]:
            raise ManagedSIHError(
                "ACTION_MANAGED_SIH_CONTROL_ACTIVE",
                "Stop following and leave Offboard before changing the SIH process state.",
                status.HTTP_409_CONFLICT,
            )
        available_key = f"{operation}_available"
        if not probe[available_key]:
            raise ManagedSIHError(
                "ACTION_MANAGED_SIH_NOT_READY",
                f"Managed SIH {operation} is not available for the current host state.",
                status.HTTP_409_CONFLICT,
                details={
                    "readiness": probe["readiness"],
                    "reasons": probe["reasons"],
                },
            )

        if request.dry_run:
            response.status_code = status.HTTP_200_OK
            return _store_action(
                owner,
                request,
                action_type=action_type,
                status_value="validated",
                accepted=True,
                executed=False,
                result={
                    "message": f"Managed SIH {operation} dry run passed.",
                    "readiness": probe["readiness"],
                    "container_state": probe["container_state"],
                },
            )

        operation_id = f"managed-{uuid.uuid4()}"
        probe = {**probe, "operation_id": operation_id}
        _record_pre_execution_audit(
            owner,
            http_request,
            action_type=action_type,
            path=path,
            probe=probe,
            operation_id=operation_id,
        )
        pre_audited = True
        _begin_lifecycle_entry(
            action_type,
            str(request.idempotency_key),
            operation_id,
        )
        ledger_started = True
        mutation_started = True
        mutation, cancellation_requested = await _await_managed_mutation(operation, probe)
        lifecycle_result = {
            "message": f"Managed SIH {operation} completed.",
            "operation_id": operation_id,
            "lifecycle_status": "success",
            **mutation,
        }
        _finish_lifecycle_entry(
            operation_id,
            status_value="success",
            result=lifecycle_result,
            error=None,
        )
        _record_execution_audit(
            owner,
            http_request,
            action_type=action_type,
            path=path,
            operation_id=operation_id,
            outcome="allowed",
            reason="managed_sih_execution_succeeded",
            status_code=status.HTTP_202_ACCEPTED,
            result=lifecycle_result,
        )
        record = _store_action(
            owner,
            request,
            action_type=action_type,
            status_value="success",
            accepted=True,
            executed=True,
            result=lifecycle_result,
        )
        if cancellation_requested:
            raise asyncio.CancelledError
        return record
    except ManagedSIHError as exc:
        if ledger_started and operation_id is not None:
            lifecycle_status = (
                "unknown" if exc.details.get("outcome_unknown") else "failure"
            )
            _finish_lifecycle_entry(
                operation_id,
                status_value=lifecycle_status,
                result={
                    "operation_id": operation_id,
                    "lifecycle_status": lifecycle_status,
                    **exc.details,
                },
                error=str(exc),
            )
        if pre_audited and operation_id is not None:
            _record_execution_audit(
                owner,
                http_request,
                action_type=action_type,
                path=path,
                operation_id=operation_id,
                outcome="error",
                reason="managed_sih_execution_failed",
                status_code=exc.status_code,
                result={
                    "lifecycle_status": (
                        "unknown" if exc.details.get("outcome_unknown") else "failure"
                    ),
                    **exc.details,
                },
            )
        return _rejection(
            owner,
            request,
            action_type=action_type,
            path=path,
            code=exc.code,
            message=str(exc),
            status_code=exc.status_code,
            result=exc.details,
            accepted=pre_audited,
            executed=mutation_started,
        )
    except asyncio.TimeoutError:
        return _rejection(
            owner,
            request,
            action_type=action_type,
            path=path,
            code="ACTION_MANAGED_SIH_BARRIER_TIMEOUT",
            message="Timed out waiting for the follower-state barrier.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if ledger_started and operation_id is not None:
            _finish_lifecycle_entry(
                operation_id,
                status_value="unknown" if mutation_started else "failure",
                result={
                    "operation_id": operation_id,
                    "lifecycle_status": "unknown" if mutation_started else "failure",
                },
                error=f"{type(exc).__name__}: {exc}",
            )
        if pre_audited and operation_id is not None:
            _record_execution_audit(
                owner,
                http_request,
                action_type=action_type,
                path=path,
                operation_id=operation_id,
                outcome="error",
                reason="managed_sih_execution_state_unavailable",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                result={
                    "lifecycle_status": "unknown" if mutation_started else "failure",
                },
            )
        return _rejection(
            owner,
            request,
            action_type=action_type,
            path=path,
            code="ACTION_MANAGED_SIH_STATE_UNAVAILABLE",
            message="Managed SIH state could not be safely verified.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            accepted=pre_audited,
            executed=mutation_started,
        )
    finally:
        if acquired:
            state_lock.release()


async def _dispatch_managed_sih_action(
    owner: Any,
    request: SITLManagedLifecycleRequest,
    response: Any,
    http_request: Any,
    *,
    operation: str,
) -> Any:
    action_type = f"managed_sih_{operation}"
    path = (
        API_V1_ACTION_MANAGED_SIH_START_PATH
        if operation == "start"
        else API_V1_ACTION_MANAGED_SIH_STOP_PATH
    )
    app_controller = getattr(owner, "app_controller", None)
    run_on_owner = getattr(app_controller, "_run_on_flight_event_loop", None)
    if not callable(run_on_owner):
        return _rejection(
            owner,
            request,
            action_type=action_type,
            path=path,
            code="ACTION_MANAGED_SIH_FLIGHT_OWNER_UNAVAILABLE",
            message="The flight lifecycle owner is unavailable.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return await run_on_owner(
        lambda: _managed_sih_action_on_flight_loop(
            owner,
            request,
            response,
            http_request,
            operation=operation,
        )
    )


async def managed_sih_action(
    owner: Any,
    request: SITLManagedLifecycleRequest,
    response: Any,
    http_request: Any,
    *,
    operation: str,
) -> Any:
    """Execute one idempotent managed-SIH lifecycle action."""
    action_type = f"managed_sih_{operation}"
    path = (
        API_V1_ACTION_MANAGED_SIH_START_PATH
        if operation == "start"
        else API_V1_ACTION_MANAGED_SIH_STOP_PATH
    )
    if operation not in {"start", "stop"}:
        raise ValueError(f"Unsupported managed SIH operation: {operation!r}")
    if not request.dry_run and request.confirm and not request.idempotency_key:
        return owner._idempotency_key_required_response(
            action_type=action_type,
            request=request,
            path=path,
        )
    lock = (
        None
        if request.dry_run or not request.confirm
        else owner._action_lock_for_key(action_type, request.idempotency_key)
    )
    if lock is None:
        return await _dispatch_managed_sih_action(
            owner,
            request,
            response,
            http_request,
            operation=operation,
        )
    async with lock:
        return await _dispatch_managed_sih_action(
            owner,
            request,
            response,
            http_request,
            operation=operation,
        )


__all__ = [
    "MANAGED_CONTAINER_LABEL",
    "MANAGED_CONTAINER_NAME",
    "MANAGED_PROFILE",
    "MANAGED_PROFILE_LABEL",
    "MANAGED_RUN_ID_LABEL",
    "ManagedSIHError",
    "ManagedSIHSpec",
    "load_managed_sih_spec",
    "managed_sih_action",
    "probe_managed_sih",
    "public_managed_sih_status",
]
