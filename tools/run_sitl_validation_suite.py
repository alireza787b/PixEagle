#!/usr/bin/env python3
"""PX4-in-loop validation harness for PixEagle.

The harness validates checked-in SITL plans, supports side-effect-free dry-runs,
collects probe artifacts from an already running stack, and can optionally
start only a pinned PX4 SITL container when explicitly guarded by
``--execute --allow-process-start``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from classes.setpoint_handler import (  # noqa: E402
    SetpointHandler,
    command_intent_contract_errors as runtime_command_intent_contract_errors,
)


PLAN_DIR = PROJECT_ROOT / "tools" / "sitl_plans"
DEFAULT_ARTIFACT_ROOT = PROJECT_ROOT / "reports" / "sitl"
FOLLOWER_COMMAND_SCHEMA_PATH = PROJECT_ROOT / "configs" / "follower_commands.yaml"
DEFAULT_MANAGED_PX4_LOG_LIMIT_BYTES = 4 * 1024 * 1024
MAX_MANAGED_PX4_PENDING_BYTES = 64 * 1024
ANSI_ESCAPE_RE = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]")

REQUIRED_PHASE2_SCENARIOS = {
    "offboard_entry",
    "offboard_heartbeat",
    "follower_setpoints",
    "target_loss",
    "video_stall",
    "mavsdk_disconnect",
    "mavlink2rest_timeout",
    "operator_abort",
    "commander_publish_failure",
}

REQUIRED_EVIDENCE_ARTIFACTS = {
    "manifest.json",
    "plan.json",
    "config/config_default.yaml",
    "config/config_schema.yaml",
    "config/config.yaml",
    "versions/git.json",
    "versions/runtime.json",
    "versions/mavlink_anywhere_dashboard.json",
    "route_map/mavlink_anywhere_status.json",
    "route_map/mavlink_anywhere_diagnostics.json",
    "route_map/mavlink_anywhere_endpoints.json",
    "route_map/mavlink_anywhere_profiles_summary.json",
    "route_map/mavlink_anywhere_config.json",
    "security/secret_scan.json",
    "probes/pixeagle_status.json",
    "probes/pixeagle_current_config.json",
    "probes/pixeagle_follower_setpoints_status.json",
    "probes/mavlink2rest_mavlink.json",
    "scenarios/scenario_results.json",
    "logs/harness.log",
    "logs/px4_sitl.log",
    "logs/pixeagle.log",
    "px4/params.txt",
    "px4/container_metadata.json",
    "px4/ulog_manifest.json",
    "px4/tlog_manifest.json",
    "px4/offboard_observation.json",
}

MANAGED_CONTAINER_LABEL = "org.pixeagle.sitl.managed"
RUN_ID_CONTAINER_LABEL = "org.pixeagle.sitl.run_id"
DEFAULT_PX4_ARTIFACT_COLLECTION = {
    "container_roots": [
        "/root",
        "/home",
        "/tmp",
        "/workspace",
        "/PX4-Autopilot",
        "/src/PX4-Autopilot",
    ],
    "params_names": [
        "params.txt",
        "*.params",
        "parameters*.txt",
        "parameters*.bson",
    ],
    "ulog_names": ["*.ulg"],
    "tlog_names": ["*.tlog"],
    "max_files_per_kind": 20,
}
SUPPORTED_SCENARIO_ACTION_TYPES = {
    "http_request",
    "wait",
    "manual_fault",
    "operator_note",
}
SUPPORTED_SCENARIO_TARGETS = {
    "pixeagle",
    "mavlink2rest",
    "mavlink_anywhere",
}
MAVLINK_ANYWHERE_ENDPOINT_REQUIRED_FIELDS = {
    "name",
    "type",
    "mode",
    "address",
    "port",
    "category",
    "enabled",
}
MAVLINK_ANYWHERE_REQUIRED_API_PATHS = [
    "/api/v1/status",
    "/api/v1/diagnostics",
    "/api/v1/endpoints",
    "/api/v1/profiles/summary",
    "/api/v1/config",
]
MAVLINK_ANYWHERE_API_ARTIFACTS = {
    "/api/v1/status": "route_map/mavlink_anywhere_status.json",
    "/api/v1/diagnostics": "route_map/mavlink_anywhere_diagnostics.json",
    "/api/v1/endpoints": "route_map/mavlink_anywhere_endpoints.json",
    "/api/v1/profiles/summary": "route_map/mavlink_anywhere_profiles_summary.json",
    "/api/v1/config": "route_map/mavlink_anywhere_config.json",
}
MAVLINK_ANYWHERE_COMPATIBILITY_CLASSIFICATIONS = {
    "unavailable",
    "unexpected_auth",
    "unsupported_contract_version",
    "unprepared_config",
    "prepared_routing",
}
SECRET_SCAN_MAX_FILE_BYTES = 2 * 1024 * 1024
SECRET_SCAN_TEXT_SUFFIXES = {
    "",
    ".conf",
    ".env",
    ".ini",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".service",
    ".sh",
    ".txt",
    ".yaml",
    ".yml",
}
SECRET_SCAN_SKIP_SUFFIXES = {
    ".avi",
    ".bin",
    ".bmp",
    ".bson",
    ".engine",
    ".gz",
    ".jpeg",
    ".jpg",
    ".mkv",
    ".mp4",
    ".ncnn",
    ".onnx",
    ".pt",
    ".png",
    ".tlog",
    ".ulg",
    ".zip",
}
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |DSA |EC |OPENSSH |)?PRIVATE KEY-----",
    re.IGNORECASE,
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    ["']?
    (?P<key>[A-Z0-9_.-]*
      (?:password|passwd|token|api[_-]?key|secret|private[_-]?key|psk|ssid)
      [A-Z0-9_.-]*)
    ["']?
    \s*[:=]\s*
    ["']?(?P<value>[^"',\s#}\]]+)
    """
)
URI_CREDENTIAL_RE = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^@\s/]+@"
)
AUTHORIZATION_SECRET_RE = re.compile(
    r"(?i)\bauthorization\s*[:=]\s*(?:bearer|basic)\s+[^\s,;]+"
)
QUERY_SECRET_RE = re.compile(
    r"(?i)(?:[?&]|\\b)(?:access_token|api[_-]?key|password|passwd|token|client_secret)=([^&\s]+)"
)
API_V1_ACTION_OFFBOARD_START_PATH = "/api/v1/actions/offboard-start"
PX4_OFFBOARD_CUSTOM_MODE = 393216
PX4_AUTOPILOT_COMPONENT_ID = 1
PX4_MAV_AUTOPILOT_PX4 = 12
MAV_MODE_FLAG_CUSTOM_MODE_ENABLED = 1
PX4_OBSERVATION_WINDOW_PADDING_S = 0.5
PX4_SETPOINT_MESSAGE_TYPES = {
    "SET_POSITION_TARGET_LOCAL_NED",
    "SET_POSITION_TARGET_GLOBAL_INT",
    "SET_ATTITUDE_TARGET",
}
PX4_MIN_OFFBOARD_SETPOINT_RATE_HZ = 2.0
PX4_MIN_OFFBOARD_SETPOINT_DURATION_S = 1.0
PX4_MIN_OFFBOARD_SETPOINT_COUNT = 3
GAZEBO_VISUAL_EVIDENCE_PATHS = {
    "generated_receiver_proof_manifest": "video/generated_receiver_proof_manifest.json",
    "gazebo_receiver_pipeline": "video/gazebo_receiver_pipeline.txt",
    "gazebo_frame_hashes": "video/gazebo_frame_hashes.json",
    "tracker_command_trace": "trace/tracker_command_trace.jsonl",
    "offboard_publish_trace": "trace/offboard_publish_trace.jsonl",
}


def action_has_substantive_assertion(action: dict[str, Any]) -> bool:
    """Return True when an action checks a concrete runtime value."""
    for expectation in action.get("expect_json", []):
        if isinstance(expectation, dict) and "equals" in expectation:
            return True
    return False


class PlanError(ValueError):
    """Raised when a SITL plan does not match the PixEagle contract."""


def load_follower_command_contract(
    path: Path = FOLLOWER_COMMAND_SCHEMA_PATH,
) -> dict[str, Any]:
    """Load and validate the command contract used by strict SITL traces."""
    try:
        return SetpointHandler.load_and_validate_schema(path)
    except FileNotFoundError as exc:
        raise PlanError(f"follower command schema is missing: {path}") from exc
    except Exception as exc:
        raise PlanError(f"follower command schema is invalid: {exc}") from exc


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def json_dumps(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def plan_files() -> list[Path]:
    return sorted(
        path
        for path in PLAN_DIR.glob("*.json")
        if path.name not in {"schema.json"}
    )


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanError(f"{path} is not valid JSON: {exc}") from exc


def resolve_plan(plan_name: str | None, plan_file: str | None) -> Path:
    if plan_file:
        path = Path(plan_file)
        return path if path.is_absolute() else (PROJECT_ROOT / path)

    selected_name = plan_name or "phase2_follower_validation"
    path = PLAN_DIR / f"{selected_name}.json"
    if not path.exists():
        available = ", ".join(path.stem for path in plan_files())
        raise PlanError(f"Unknown plan {selected_name!r}. Available: {available}")
    return path


def parse_semver(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"\bv?(\d+)\.(\d+)\.(\d+)\b", value.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def semver_meets_minimum(value: Any, minimum: Any) -> bool:
    parsed = parse_semver(value)
    minimum_parsed = parse_semver(minimum)
    return bool(parsed is not None and minimum_parsed is not None and parsed >= minimum_parsed)


def validate_mavlink_anywhere_compatibility_policy(
    plan: dict[str, Any],
    source: Path,
) -> None:
    routing = ((plan.get("stack") or {}).get("routing") or {})
    if routing.get("provider") != "mavlink-anywhere":
        return

    policy = routing.get("compatibility_policy")
    if not isinstance(policy, dict):
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy must define the "
            "MavlinkAnywhere version and capability contract"
        )

    required_keys = {
        "schema_version",
        "provider",
        "reviewed_source_ref",
        "reviewed_version",
        "minimum_dashboard_semver",
        "required_api_paths",
        "required_status_fields",
        "required_endpoint_fields",
        "required_profile_metadata",
        "auth_expectation",
    }
    missing = sorted(required_keys - set(policy))
    if missing:
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy missing keys: "
            f"{', '.join(missing)}"
        )
    if policy.get("schema_version") != 1:
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.schema_version must be 1"
        )
    if policy.get("provider") != "mavlink-anywhere":
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.provider must be mavlink-anywhere"
        )
    if not isinstance(policy.get("reviewed_source_ref"), str) or len(
        policy["reviewed_source_ref"]
    ) < 12:
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.reviewed_source_ref "
            "must be a concrete commit/ref"
        )
    if parse_semver(policy.get("minimum_dashboard_semver")) is None:
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.minimum_dashboard_semver "
            "must contain major.minor.patch"
        )

    required_api_paths = policy.get("required_api_paths")
    if not isinstance(required_api_paths, list):
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.required_api_paths "
            "must be a list"
        )
    missing_api_paths = [
        path for path in MAVLINK_ANYWHERE_REQUIRED_API_PATHS if path not in required_api_paths
    ]
    if missing_api_paths:
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.required_api_paths "
            f"missing: {', '.join(missing_api_paths)}"
        )

    required_status_fields = policy.get("required_status_fields")
    if not isinstance(required_status_fields, list) or "version" not in required_status_fields:
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.required_status_fields "
            "must include version"
        )

    endpoint_fields = {str(item) for item in policy.get("required_endpoint_fields", [])}
    missing_endpoint_fields = sorted(
        MAVLINK_ANYWHERE_ENDPOINT_REQUIRED_FIELDS - endpoint_fields
    )
    if missing_endpoint_fields:
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.required_endpoint_fields "
            f"missing: {', '.join(missing_endpoint_fields)}"
        )

    profile_metadata = policy.get("required_profile_metadata")
    if not isinstance(profile_metadata, dict):
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.required_profile_metadata "
            "must be an object"
        )
    if profile_metadata.get("backend") != "mavlink-anywhere" or profile_metadata.get("present") is not True:
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.required_profile_metadata "
            "must require backend=mavlink-anywhere and present=true"
        )
    if policy.get("auth_expectation") != "loopback_read_without_credentials":
        raise PlanError(
            f"{source}: stack.routing.compatibility_policy.auth_expectation "
            "must be loopback_read_without_credentials for maintained SITL plans"
        )


def validate_plan(plan: dict[str, Any], source: Path) -> None:
    required_top = {
        "schema_version",
        "name",
        "title",
        "level",
        "description",
        "stack",
        "evidence_contract",
        "scenarios",
    }
    missing = sorted(required_top - set(plan))
    if missing:
        raise PlanError(f"{source}: missing top-level keys: {', '.join(missing)}")

    if plan["schema_version"] != 1:
        raise PlanError(f"{source}: unsupported schema_version {plan['schema_version']!r}")

    if not isinstance(plan["scenarios"], list) or not plan["scenarios"]:
        raise PlanError(f"{source}: scenarios must be a non-empty list")

    scenario_ids: set[str] = set()
    for index, scenario in enumerate(plan["scenarios"]):
        if not isinstance(scenario, dict):
            raise PlanError(f"{source}: scenario {index} must be an object")
        missing_scenario = sorted(
            {"id", "title", "objective", "stimulus", "probes", "acceptance", "evidence"}
            - set(scenario)
        )
        if missing_scenario:
            raise PlanError(
                f"{source}: scenario {index} missing keys: {', '.join(missing_scenario)}"
            )
        scenario_id = scenario["id"]
        if scenario_id in scenario_ids:
            raise PlanError(f"{source}: duplicate scenario id {scenario_id!r}")
        scenario_ids.add(scenario_id)

        for list_key in ("probes", "acceptance", "evidence"):
            if not isinstance(scenario[list_key], list) or not scenario[list_key]:
                raise PlanError(f"{source}: scenario {scenario_id} has empty {list_key}")

        actions = scenario.get("actions")
        if not isinstance(actions, list) or not actions:
            raise PlanError(f"{source}: scenario {scenario_id} must define non-empty actions")
        action_ids: set[str] = set()
        for action_index, action in enumerate(actions):
            if not isinstance(action, dict):
                raise PlanError(
                    f"{source}: scenario {scenario_id} action {action_index} must be an object"
                )
            missing_action = sorted({"id", "type"} - set(action))
            if missing_action:
                raise PlanError(
                    f"{source}: scenario {scenario_id} action {action_index} "
                    f"missing keys: {', '.join(missing_action)}"
                )
            action_id = action["id"]
            if action_id in action_ids:
                raise PlanError(
                    f"{source}: scenario {scenario_id} has duplicate action id {action_id!r}"
                )
            action_ids.add(action_id)
            action_type = action["type"]
            if action_type not in SUPPORTED_SCENARIO_ACTION_TYPES:
                raise PlanError(
                    f"{source}: scenario {scenario_id} action {action_id!r} "
                    f"has unsupported type {action_type!r}"
                )
            if action_type == "http_request":
                missing_http = sorted({"method", "target", "path"} - set(action))
                if missing_http:
                    raise PlanError(
                        f"{source}: scenario {scenario_id} action {action_id!r} "
                        f"missing HTTP keys: {', '.join(missing_http)}"
                    )
                method = str(action["method"]).upper()
                if method not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                    raise PlanError(
                        f"{source}: scenario {scenario_id} action {action_id!r} "
                        f"has unsupported HTTP method {method!r}"
                    )
                if action["target"] not in SUPPORTED_SCENARIO_TARGETS:
                    raise PlanError(
                        f"{source}: scenario {scenario_id} action {action_id!r} "
                        f"has unsupported target {action['target']!r}"
                    )
                if not str(action["path"]).startswith("/"):
                    raise PlanError(
                        f"{source}: scenario {scenario_id} action {action_id!r} "
                        "path must start with /"
                    )
            elif action_type == "wait":
                seconds = action.get("seconds")
                if not isinstance(seconds, (int, float)) or seconds < 0 or seconds > 60:
                    raise PlanError(
                        f"{source}: scenario {scenario_id} action {action_id!r} "
                        "wait seconds must be between 0 and 60"
                    )
            elif action_type in {"manual_fault", "operator_note"}:
                if not action.get("description"):
                    raise PlanError(
                        f"{source}: scenario {scenario_id} action {action_id!r} "
                        "must include a description"
                    )

        has_manual_fault_blocker = any(
            action.get("type") == "manual_fault" for action in actions
        )
        has_substantive_assertion = any(
            action_has_substantive_assertion(action)
            for action in actions
            if action.get("type") == "http_request"
        )
        if not has_manual_fault_blocker and not has_substantive_assertion:
            raise PlanError(
                f"{source}: scenario {scenario_id} must include at least one "
                "HTTP JSON equality assertion or a manual_fault blocker. "
                "HTTP status/existence checks alone are not accepted flight-adjacent evidence."
            )

    stack = plan["stack"]
    for stack_key in ("px4", "routing", "mavlink2rest", "pixeagle"):
        if stack_key not in stack:
            raise PlanError(f"{source}: stack missing {stack_key}")

    validate_mavlink_anywhere_compatibility_policy(plan, source)

    evidence_contract = plan["evidence_contract"]
    if not isinstance(evidence_contract, list) or not evidence_contract:
        raise PlanError(f"{source}: evidence_contract must be a non-empty list")

    missing_evidence = sorted(REQUIRED_EVIDENCE_ARTIFACTS - set(evidence_contract))
    if missing_evidence:
        raise PlanError(
            f"{source}: evidence_contract missing required artifacts: "
            f"{', '.join(missing_evidence)}"
        )

    if plan_requires_gazebo_visual_evidence(plan):
        missing_visual_evidence = sorted(
            set(GAZEBO_VISUAL_EVIDENCE_PATHS.values()) - set(evidence_contract)
        )
        if missing_visual_evidence:
            raise PlanError(
                f"{source}: Gazebo visual evidence_contract missing artifacts: "
                f"{', '.join(missing_visual_evidence)}"
            )


def load_plan(path: Path) -> dict[str, Any]:
    plan = load_json(path)
    validate_plan(plan, path)
    return plan


def plan_hash(plan: dict[str, Any]) -> str:
    encoded = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json_dumps(data), encoding="utf-8")


def write_placeholder_json(path: Path, reason: str) -> None:
    write_json(
        path,
        {
            "collected": False,
            "placeholder": True,
            "reason": reason,
        },
    )


def write_placeholder_text(path: Path, reason: str) -> None:
    ensure_dir(path.parent)
    path.write_text(
        f"collected=false\nplaceholder=true\nreason={reason}\n",
        encoding="utf-8",
    )


def copy_if_exists(source: Path, target: Path) -> bool:
    ensure_dir(target.parent)
    if source.exists():
        shutil.copy2(source, target)
        return True
    write_placeholder_json(
        target,
        f"Source file did not exist when evidence was collected: {source}",
    )
    return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_to_run_dir(path: Path, run_dir: Path) -> str:
    try:
        return str(path.relative_to(run_dir))
    except ValueError:
        return str(path)


def resolve_input_file(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path)


def evidence_entry(source_path: str, target: Path, run_dir: Path) -> dict[str, Any]:
    stat = target.stat()
    return {
        "source_path": source_path,
        "artifact_path": relative_to_run_dir(target, run_dir),
        "size_bytes": stat.st_size,
        "sha256": sha256_file(target),
        "modified_at": dt.datetime.fromtimestamp(
            stat.st_mtime,
            tz=dt.timezone.utc,
        ).isoformat(),
    }


def file_evidence_entry(source: Path, target: Path, run_dir: Path) -> dict[str, Any]:
    return evidence_entry(str(source), target, run_dir)


def copy_named_evidence_file(source: Path, target: Path, run_dir: Path) -> dict[str, Any]:
    ensure_dir(target.parent)
    shutil.copy2(source, target)
    return file_evidence_entry(source, target, run_dir)


def px4_artifact_collection_config(plan: dict[str, Any]) -> dict[str, Any]:
    configured = (
        ((plan.get("stack") or {}).get("px4") or {}).get("artifact_collection") or {}
    )
    collection = dict(DEFAULT_PX4_ARTIFACT_COLLECTION)
    for key in ("container_roots", "params_names", "ulog_names", "tlog_names"):
        values = configured.get(key)
        if isinstance(values, list) and all(isinstance(item, str) and item for item in values):
            collection[key] = values
    max_files = configured.get("max_files_per_kind")
    if isinstance(max_files, int):
        collection["max_files_per_kind"] = max(1, min(max_files, 100))
    return collection


def px4_container_artifact_names(plan: dict[str, Any], kind: str) -> list[str]:
    collection = px4_artifact_collection_config(plan)
    key = "params_names" if kind == "params" else f"{kind}_names"
    values = collection.get(key, [])
    return values if isinstance(values, list) else []


def px4_container_artifact_roots(plan: dict[str, Any]) -> list[str]:
    values = px4_artifact_collection_config(plan).get("container_roots", [])
    return values if isinstance(values, list) else []


def px4_container_artifact_limit(plan: dict[str, Any]) -> int:
    value = px4_artifact_collection_config(plan).get("max_files_per_kind", 20)
    return int(value) if isinstance(value, int) else 20


def find_px4_container_artifacts(
    plan: dict[str, Any],
    *,
    container_ref: str,
    kind: str,
    timeout_s: float = 10.0,
) -> tuple[list[str], dict[str, Any]]:
    roots = px4_container_artifact_roots(plan)
    names = px4_container_artifact_names(plan, kind)
    max_files = px4_container_artifact_limit(plan)
    if not roots or not names:
        return [], {
            "returncode": None,
            "error": f"No PX4 container artifact search roots or names configured for {kind}.",
        }

    root_args = " ".join(shlex.quote(root) for root in roots)
    name_expr = " -o ".join(f"-name {shlex.quote(name)}" for name in names)
    script = (
        f"for root in {root_args}; do "
        '[ -e "$root" ] || continue; '
        f"find \"$root\" -type f \\( {name_expr} \\) -print; "
        f"done | sort -u | head -n {max_files}"
    )
    result = run_command(
        ["docker", "exec", container_ref, "sh", "-lc", script],
        PROJECT_ROOT,
        timeout_s=timeout_s,
    )
    if result.get("returncode") != 0:
        return [], result
    files = [
        line.strip()
        for line in str(result.get("stdout") or "").splitlines()
        if line.strip().startswith("/")
    ]
    return files[:max_files], result


def safe_artifact_name(prefix: str, index: int, source_path: str) -> str:
    source_name = Path(source_path).name or "artifact"
    safe_name = "".join(
        char if char.isalnum() or char in {".", "-", "_"} else "_"
        for char in source_name
    )
    return f"{index:03d}-{prefix}-{safe_name}"


def copy_container_evidence_file(
    *,
    container_ref: str,
    source_path: str,
    target: Path,
    run_dir: Path,
    timeout_s: float = 20.0,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    ensure_dir(target.parent)
    copy_result = run_command(
        ["docker", "cp", f"{container_ref}:{source_path}", str(target)],
        PROJECT_ROOT,
        timeout_s=timeout_s,
    )
    if copy_result.get("returncode") != 0 or not target.exists():
        return None, copy_result
    return evidence_entry(f"{container_ref}:{source_path}", target, run_dir), copy_result


def px4_params_artifact_metadata(source_path: str) -> dict[str, Any]:
    suffix = Path(source_path).suffix.lower()
    is_bson = suffix == ".bson"
    return {
        "parameter_format": "bson" if is_bson else "text",
        "readable_text_export": not is_bson,
        "format_note": (
            "PX4 parameters were discovered as binary BSON; use a text params "
            "export for reviewer-readable accepted evidence."
            if is_bson
            else "PX4 parameters were collected as a reviewer-readable text export."
        ),
    }


def collect_px4_params_artifact(
    run_dir: Path,
    plan: dict[str, Any],
    params_file: str | None,
    *,
    container_ref: str | None = None,
    auto_container_artifacts: bool = False,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    target = run_dir / "px4" / "params.txt"

    if params_file:
        source = resolve_input_file(params_file)
        if not source.exists() or not source.is_file():
            write_placeholder_text(
                target,
                f"PX4 parameter export input did not exist: {source}",
            )
            return {
                "collected": False,
                "placeholder": True,
                "reason": f"PX4 parameter export input did not exist: {source}",
            }

        entry = copy_named_evidence_file(source, target, run_dir)
        return {
            "collected": True,
            "placeholder": False,
            "reason": None,
            "collection_source": "explicit_file",
            **px4_params_artifact_metadata(str(source)),
            "artifact": entry,
        }

    if auto_container_artifacts and container_ref:
        found_files, find_result = find_px4_container_artifacts(
            plan,
            container_ref=container_ref,
            kind="params",
            timeout_s=timeout_s,
        )
        if not found_files:
            write_placeholder_text(
                target,
                "PX4 parameter export was not found by container artifact discovery.",
            )
            return {
                "collected": False,
                "placeholder": True,
                "reason": "PX4 parameter export was not found by container artifact discovery.",
                "collection_source": "container_discovery",
                "container_ref": container_ref,
                "find_result": find_result,
            }
        entry, copy_result = copy_container_evidence_file(
            container_ref=container_ref,
            source_path=found_files[0],
            target=target,
            run_dir=run_dir,
            timeout_s=timeout_s,
        )
        if entry is None:
            write_placeholder_text(
                target,
                f"PX4 parameter export could not be copied from container path: {found_files[0]}",
            )
            return {
                "collected": False,
                "placeholder": True,
                "reason": f"PX4 parameter export could not be copied from container path: {found_files[0]}",
                "collection_source": "container_discovery",
                "container_ref": container_ref,
                "find_result": find_result,
                "copy_result": copy_result,
            }
        return {
            "collected": True,
            "placeholder": False,
            "reason": None,
            "collection_source": "container_discovery",
            "container_ref": container_ref,
            "container_path": found_files[0],
            "find_result": find_result,
            "copy_result": copy_result,
            **px4_params_artifact_metadata(found_files[0]),
            "artifact": entry,
        }

    write_placeholder_text(
        target,
        "PX4 parameter export was not provided. Use --px4-params-file with an exported params.txt for accepted evidence.",
    )
    return {
        "collected": False,
        "placeholder": True,
        "reason": "PX4 parameter export was not provided.",
    }


def collect_px4_log_manifest(
    run_dir: Path,
    plan: dict[str, Any],
    *,
    kind: str,
    input_files: list[str],
    container_ref: str | None = None,
    auto_container_artifacts: bool = False,
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    manifest_path = run_dir / "px4" / f"{kind}_manifest.json"
    copied_entries = []
    missing_entries = []
    container_find_result = None
    container_copy_results = []

    for index, file_value in enumerate(input_files):
        source = resolve_input_file(file_value)
        if not source.exists() or not source.is_file():
            missing_entries.append(
                {
                    "source_path": str(source),
                    "reason": "Input file did not exist or was not a regular file.",
                }
            )
            continue
        target_name = f"{index:03d}-{source.name}"
        target = run_dir / "px4" / kind / target_name
        copied_entries.append(copy_named_evidence_file(source, target, run_dir))

    if auto_container_artifacts and container_ref:
        found_files, container_find_result = find_px4_container_artifacts(
            plan,
            container_ref=container_ref,
            kind=kind,
            timeout_s=timeout_s,
        )
        for source_path in found_files:
            target_name = safe_artifact_name(
                "container",
                len(copied_entries) + len(missing_entries),
                source_path,
            )
            target = run_dir / "px4" / kind / target_name
            entry, copy_result = copy_container_evidence_file(
                container_ref=container_ref,
                source_path=source_path,
                target=target,
                run_dir=run_dir,
                timeout_s=timeout_s,
            )
            container_copy_results.append(
                {
                    "source_path": source_path,
                    "target_path": relative_to_run_dir(target, run_dir),
                    "copy_result": copy_result,
                }
            )
            if entry is None:
                missing_entries.append(
                    {
                        "source_path": f"{container_ref}:{source_path}",
                        "reason": "Container artifact was found but docker cp did not produce a regular artifact file.",
                    }
                )
            else:
                copied_entries.append(entry)

    if not input_files and not copied_entries:
        reason = (
            f"No PX4 {kind} files were found by container artifact discovery."
            if auto_container_artifacts and container_ref
            else f"No PX4 {kind} files were provided. Use --px4-{kind} for accepted evidence."
        )
        write_placeholder_json(
            manifest_path,
            reason,
        )
        return {
            "collected": False,
            "placeholder": True,
            "reason": reason,
            "collection_sources": {
                "explicit_files": bool(input_files),
                "container_discovery": bool(auto_container_artifacts and container_ref),
            },
            "container_ref": container_ref,
            "container_find_result": container_find_result,
        }

    manifest = {
        "schema_version": 1,
        "kind": kind,
        "generated_at": utc_now().isoformat(),
        "collected": bool(copied_entries) and not missing_entries,
        "collection_sources": {
            "explicit_files": bool(input_files),
            "container_discovery": bool(auto_container_artifacts and container_ref),
        },
        "container_ref": container_ref if auto_container_artifacts else None,
        "container_find_result": container_find_result,
        "container_copy_results": container_copy_results,
        "entries": copied_entries,
        "missing_inputs": missing_entries,
    }
    write_json(manifest_path, manifest)
    return {
        "collected": manifest["collected"],
        "placeholder": False,
        "reason": None if manifest["collected"] else f"One or more PX4 {kind} inputs were missing.",
        "entries": copied_entries,
        "missing_inputs": missing_entries,
    }


def collect_px4_container_metadata(
    plan: dict[str, Any],
    run_dir: Path,
    *,
    image_override: str | None,
    container_name: str | None,
    container_id: str | None,
) -> dict[str, Any]:
    image = image_override or plan["stack"]["px4"]["recommended_image"]
    image_result = run_command(
        ["docker", "image", "inspect", image],
        PROJECT_ROOT,
        timeout_s=10.0,
    )
    container_result = None
    if container_id or container_name:
        container_result = run_command(
            ["docker", "inspect", container_id or container_name],
            PROJECT_ROOT,
            timeout_s=10.0,
        )

    image_ok = image_result.get("returncode") == 0
    container_ok = (
        True
        if not (container_id or container_name)
        else container_result is not None and container_result.get("returncode") == 0
    )
    payload = {
        "schema_version": 1,
        "generated_at": utc_now().isoformat(),
        "image": image,
        "container_name": container_name,
        "container_id": container_id,
        "collected": image_ok and container_ok,
        "image_inspect": image_result,
        "container_inspect": container_result,
    }
    write_json(run_dir / "px4" / "container_metadata.json", payload)
    return {
        "collected": payload["collected"],
        "placeholder": False,
        "reason": None if payload["collected"] else "PX4 image/container metadata could not be collected.",
    }


def collect_log_artifact(
    run_dir: Path,
    *,
    relative_path: str,
    log_file: str | None,
    existing_source: str | None = None,
) -> dict[str, Any]:
    target = run_dir / relative_path
    if log_file:
        source = resolve_input_file(log_file)
        if not source.exists() or not source.is_file():
            write_placeholder_text(
                target,
                f"Log input did not exist or was not a regular file: {source}",
            )
            return {
                "collected": False,
                "placeholder": True,
                "reason": f"Log input did not exist or was not a regular file: {source}",
                "collection_source": "explicit_file",
            }
        entry = copy_named_evidence_file(source, target, run_dir)
        return {
            "collected": True,
            "placeholder": False,
            "reason": None,
            "collection_source": "explicit_file",
            "artifact": entry,
        }

    if target.exists() and target.is_file():
        return {
            "collected": True,
            "placeholder": False,
            "reason": None,
            "collection_source": existing_source or "existing_artifact",
            "artifact": evidence_entry(existing_source or str(target), target, run_dir),
        }

    write_placeholder_text(
        target,
        f"{relative_path} was not produced by this run and no explicit log import was provided.",
    )
    return {
        "collected": False,
        "placeholder": True,
        "reason": f"{relative_path} was not produced by this run and no explicit log import was provided.",
    }


def collect_named_artifact(
    run_dir: Path,
    *,
    relative_path: str,
    input_file: str | None,
    description: str,
) -> dict[str, Any]:
    target = run_dir / relative_path
    if input_file:
        source = resolve_input_file(input_file)
        if not source.exists() or not source.is_file():
            reason = f"{description} input did not exist or was not a regular file: {source}"
            if target.suffix in {".log", ".txt", ".jsonl"}:
                write_placeholder_text(target, reason)
            else:
                write_placeholder_json(target, reason)
            return {
                "collected": False,
                "placeholder": True,
                "reason": reason,
                "collection_source": "explicit_file",
            }
        entry = copy_named_evidence_file(source, target, run_dir)
        return {
            "collected": True,
            "placeholder": False,
            "reason": None,
            "collection_source": "explicit_file",
            "artifact": entry,
        }

    if target.exists() and target.is_file():
        return {
            "collected": True,
            "placeholder": False,
            "reason": None,
            "collection_source": "existing_artifact",
            "artifact": evidence_entry(str(target), target, run_dir),
        }

    reason = f"{description} was not produced by this run and no explicit import was provided."
    if target.suffix in {".log", ".txt", ".jsonl"}:
        write_placeholder_text(target, reason)
    else:
        write_placeholder_json(target, reason)
    return {
        "collected": False,
        "placeholder": True,
        "reason": reason,
    }


def plan_requires_gazebo_visual_evidence(plan: dict[str, Any]) -> bool:
    video = ((plan.get("stack") or {}).get("video") or {})
    return video.get("source") == "gazebo_rtp_h264_udp"


def read_json_file(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "file is missing"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def validate_h264_rtp_pipeline_text(
    pipeline: str,
    *,
    expected_udp_port: int | None = None,
) -> dict[str, Any]:
    normalized = " ".join(pipeline.split())
    lower = normalized.lower()
    ordered_terms = [
        "udpsrc",
        "application/x-rtp",
        "media=video",
        "encoding-name=h264",
        "payload=96",
        "clock-rate=90000",
        "rtph264depay",
        "h264parse",
        "avdec_h264",
        "videoconvert",
        "video/x-raw,format=bgr",
        "videoscale",
        "appsink",
        "drop=true",
        "max-buffers=1",
        "sync=false",
    ]
    missing = [term for term in ordered_terms if term not in lower]
    order_errors = []
    last_index = -1
    for term in ordered_terms:
        index = lower.find(term)
        if index == -1:
            continue
        if index < last_index:
            order_errors.append({"term": term, "index": index, "previous_index": last_index})
        last_index = index

    port_ok = True
    if expected_udp_port is not None:
        port_terms = [f":{expected_udp_port}", f"port={expected_udp_port}"]
        port_ok = any(term in lower for term in port_terms)

    return {
        "ok": not missing and not order_errors and port_ok,
        "missing_terms": missing,
        "order_errors": order_errors,
        "expected_udp_port": expected_udp_port,
        "port_ok": port_ok,
    }


def validate_generated_receiver_proof_manifest(path: Path) -> dict[str, Any]:
    payload, error = read_json_file(path)
    if error:
        return {"ok": False, "reason": error}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "receiver proof manifest must be a JSON object"}

    required_true = ["fresh_ok", "stale_unusable_ok", "dimensions_ok"]
    false_flags = [key for key in required_true if payload.get(key) is not True]
    fresh_count = payload.get("fresh_frame_count")
    pipeline = str(payload.get("receiver_pipeline") or "")
    pipeline_check = validate_h264_rtp_pipeline_text(pipeline)
    status_ok = payload.get("status") == "passed"
    mode_ok = payload.get("mode") == "execute"
    fresh_count_ok = isinstance(fresh_count, int) and fresh_count > 0
    return {
        "ok": (
            status_ok
            and mode_ok
            and fresh_count_ok
            and not false_flags
            and pipeline_check["ok"]
        ),
        "status": payload.get("status"),
        "mode": payload.get("mode"),
        "fresh_frame_count": fresh_count,
        "status_ok": status_ok,
        "mode_ok": mode_ok,
        "fresh_count_ok": fresh_count_ok,
        "false_flags": false_flags,
        "pipeline_check": pipeline_check,
    }


def frame_hash_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("all", "frames", "frame_hashes", "entries"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def validate_frame_hashes(path: Path) -> dict[str, Any]:
    payload, error = read_json_file(path)
    if error:
        return {"ok": False, "reason": error}
    entries = frame_hash_entries(payload)
    hashes = [
        item.get("sha256")
        for item in entries
        if isinstance(item.get("sha256"), str) and len(item["sha256"]) == 64
    ]
    shapes = [item.get("shape") for item in entries if isinstance(item.get("shape"), list)]
    unique_hashes = sorted(set(hashes))
    valid_shapes = [
        shape
        for shape in shapes
        if len(shape) == 3
        and all(isinstance(value, int) and value > 0 for value in shape)
    ]
    return {
        "ok": len(entries) >= 2 and len(unique_hashes) >= 2 and len(valid_shapes) >= 2,
        "entry_count": len(entries),
        "valid_hash_count": len(hashes),
        "unique_hash_count": len(unique_hashes),
        "valid_shape_count": len(valid_shapes),
    }


def validate_text_pipeline_file(path: Path, *, expected_udp_port: int | None) -> dict[str, Any]:
    try:
        pipeline = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"ok": False, "reason": "file is missing"}
    if not pipeline.strip():
        return {"ok": False, "reason": "pipeline file is empty"}
    return validate_h264_rtp_pipeline_text(pipeline, expected_udp_port=expected_udp_port)


def validate_trace_jsonl(
    path: Path,
    *,
    expected_record_type: str | None = None,
    follower_command_schema_path: Path = FOLLOWER_COMMAND_SCHEMA_PATH,
) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"ok": False, "reason": "file is missing"}
    lines = [line for line in text.splitlines() if line.strip()]
    records = []
    errors = []
    for index, line in enumerate(lines, start=1):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append({"line": index, "error": str(exc)})
            continue
        if not isinstance(parsed, dict):
            errors.append({"line": index, "error": "trace line must be a JSON object"})
            continue
        records.append(parsed)
    time_keys = {"timestamp", "timestamp_s", "time", "time_s", "frame_time", "frame_index"}
    records_with_time = [
        record for record in records if any(key in record for key in time_keys)
    ]
    schema_errors = []
    command_contract = None
    command_contract_error = None
    if expected_record_type in {"tracker_command", "offboard_publish"}:
        try:
            command_contract = load_follower_command_contract(
                follower_command_schema_path
            )
        except PlanError as exc:
            command_contract_error = str(exc)
            schema_errors.append(
                {"line": 0, "error": f"follower command contract: {exc}"}
            )
    if expected_record_type == "tracker_command":
        for index, record in enumerate(records, start=1):
            tracker_output = record.get("tracker_output")
            command_intent = record.get("command_intent")
            freshness_fields = {}
            if isinstance(tracker_output, dict):
                freshness_fields = {
                    key: tracker_output.get(key)
                    for key in (
                        "has_output",
                        "tracking_active",
                        "usable_for_following",
                        "data_is_stale",
                        "freshness_reason",
                    )
                }
            geometry_present = bool(
                isinstance(tracker_output, dict)
                and any(
                    tracker_output.get(key) is not None
                    for key in (
                        "bbox",
                        "normalized_bbox",
                        "oriented_bbox",
                        "polygon",
                        "normalized_polygon",
                        "angular",
                        "position_2d",
                        "targets",
                    )
                )
            )
            if record.get("schema_version") != 1:
                schema_errors.append({"line": index, "error": "schema_version must be 1"})
            if record.get("record_type") != "tracker_command":
                schema_errors.append({"line": index, "error": "record_type must be tracker_command"})
            if not isinstance(record.get("frame_index"), int):
                schema_errors.append({"line": index, "error": "frame_index must be an integer"})
            if not isinstance(tracker_output, dict):
                schema_errors.append({"line": index, "error": "tracker_output must be an object"})
            elif not geometry_present:
                schema_errors.append(
                    {"line": index, "error": "tracker_output must include bbox, angles, position, or targets"}
                )
            if not any(value is not None for value in freshness_fields.values()):
                schema_errors.append(
                    {"line": index, "error": "tracker_output must include freshness metadata"}
                )
            if not isinstance(command_intent, dict):
                schema_errors.append({"line": index, "error": "command_intent must be an object"})
            else:
                fields = command_intent.get("fields")
                if not command_intent.get("reason"):
                    schema_errors.append({"line": index, "error": "command_intent.reason is required"})
                if not isinstance(fields, dict) or not fields:
                    schema_errors.append({"line": index, "error": "command_intent.fields must be a non-empty object"})
                if command_contract is not None:
                    schema_errors.extend(
                        {"line": index, "error": error}
                        for error in runtime_command_intent_contract_errors(
                            command_intent,
                            command_contract,
                        )
                    )
    elif expected_record_type == "offboard_publish":
        for index, record in enumerate(records, start=1):
            command_intent = record.get("command_intent")
            if record.get("schema_version") != 1:
                schema_errors.append({"line": index, "error": "schema_version must be 1"})
            if record.get("record_type") != "offboard_publish":
                schema_errors.append({"line": index, "error": "record_type must be offboard_publish"})
            if not isinstance(record.get("sequence"), int):
                schema_errors.append({"line": index, "error": "sequence must be an integer"})
            if not isinstance(command_intent, dict):
                schema_errors.append({"line": index, "error": "command_intent must be an object"})
            else:
                fields = command_intent.get("fields")
                if not command_intent.get("reason"):
                    schema_errors.append({"line": index, "error": "command_intent.reason is required"})
                if not isinstance(fields, dict) or not fields:
                    schema_errors.append({"line": index, "error": "command_intent.fields must be a non-empty object"})
                if command_contract is not None:
                    schema_errors.extend(
                        {"line": index, "error": error}
                        for error in runtime_command_intent_contract_errors(
                            command_intent,
                            command_contract,
                        )
                    )
            if record.get("publish_success") is not True:
                schema_errors.append(
                    {
                        "line": index,
                        "error": "publish_success must be exactly true for accepted evidence",
                    }
                )
    return {
        "ok": bool(records) and not errors and bool(records_with_time) and not schema_errors,
        "line_count": len(lines),
        "record_count": len(records),
        "records_with_time_count": len(records_with_time),
        "errors": errors[:10],
        "schema_errors": schema_errors[:10],
        "expected_record_type": expected_record_type,
        "follower_command_schema_path": str(follower_command_schema_path),
        "follower_command_schema_version": (
            command_contract.get("schema_version") if command_contract else None
        ),
        "follower_command_contract_error": command_contract_error,
    }


def parse_docker_inspect_stdout(result: dict[str, Any] | None) -> tuple[list[dict[str, Any]], str | None]:
    if not result:
        return [], "docker inspect was not run"
    if result.get("returncode") != 0:
        return [], result.get("error") or result.get("stderr") or "docker inspect failed"
    stdout = str(result.get("stdout") or "")
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return [], f"docker inspect output was invalid JSON: {exc}"
    if not isinstance(payload, list):
        return [], "docker inspect output must be a list"
    return [item for item in payload if isinstance(item, dict)], None


def validate_px4_container_metadata_for_plan(plan: dict[str, Any], path: Path) -> dict[str, Any]:
    payload, error = read_json_file(path)
    if error:
        return {"ok": False, "reason": error}
    if not isinstance(payload, dict):
        return {"ok": False, "reason": "container metadata must be a JSON object"}

    px4 = (plan.get("stack") or {}).get("px4") or {}
    require_container = bool(px4.get("require_container_metadata"))
    require_digest = bool(px4.get("require_image_repo_digest"))
    expected_digest = px4.get("expected_repo_digest")

    image_items, image_error = parse_docker_inspect_stdout(payload.get("image_inspect"))
    container_items, container_error = parse_docker_inspect_stdout(payload.get("container_inspect"))
    image_item = image_items[0] if image_items else {}
    container_item = container_items[0] if container_items else {}
    repo_digests = image_item.get("RepoDigests") if isinstance(image_item, dict) else []
    if not isinstance(repo_digests, list):
        repo_digests = []
    image_id = image_item.get("Id") if isinstance(image_item, dict) else None
    container_image_id = (
        container_item.get("Image") if isinstance(container_item, dict) else None
    )
    image_matches_container = (
        True
        if not (require_container and image_id and container_image_id)
        else image_id == container_image_id
    )
    expected_digest_ok = (
        True
        if not expected_digest
        else expected_digest in repo_digests
    )
    container_required_ok = not require_container or not container_error
    digest_required_ok = not require_digest or bool(repo_digests)
    return {
        "ok": (
            payload.get("collected") is True
            and not image_error
            and container_required_ok
            and digest_required_ok
            and expected_digest_ok
            and image_matches_container
        ),
        "require_container_metadata": require_container,
        "require_image_repo_digest": require_digest,
        "expected_repo_digest": expected_digest,
        "image_error": image_error,
        "container_error": container_error,
        "repo_digests": repo_digests,
        "digest_required_ok": digest_required_ok,
        "expected_digest_ok": expected_digest_ok,
        "image_matches_container": image_matches_container,
        "image_id": image_id,
        "container_image_id": container_image_id,
    }


def secret_value_is_safe_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return True
    text = str(value).strip().strip("\"'")
    if not text:
        return True
    lower = text.lower()
    if lower in {
        "0",
        "false",
        "none",
        "null",
        "redacted",
        "<redacted>",
        "<redacted_token>",
        "<redacted_password>",
        "<redacted_private_key>",
        "<redacted_wifi_psk>",
        "placeholder",
        "dummy",
        "example",
        "not-a-secret",
        "not_a_secret",
        "test-only",
        "test_only",
    }:
        return True
    if text.startswith("<") and text.endswith(">"):
        return True
    if len(text) >= 4 and set(text) <= {"*", "x", "X", "."}:
        return True
    return False


def secret_key_is_exempt(key: Any) -> bool:
    normalized = str(key).strip().lower().replace("-", "_").replace(".", "_")
    if not normalized:
        return True
    exempt_fragments = {
        "idempotency_key",
        "csrf_header",
        "header_name",
        "token_id",
        "hash",
        "digest",
        "sha256",
        "checksum",
        "image_id",
        "run_id",
        "action_id",
        "repo_digests",
        "source_ref",
        "git_ref",
        "build_ref",
    }
    if any(fragment in normalized for fragment in exempt_fragments):
        return True
    if normalized.endswith(("_file", "_path", "_dir", "_directory")):
        return True
    if "ssid" in normalized and not any(
        fragment in normalized for fragment in ("password", "passphrase", "psk")
    ):
        return True
    return False


def secret_key_is_sensitive(key: Any) -> bool:
    if secret_key_is_exempt(key):
        return False
    normalized = str(key).strip().lower().replace("-", "_").replace(".", "_")
    sensitive_terms = {
        "password",
        "passwd",
        "passphrase",
        "psk",
        "wpa_psk",
        "wifi_password",
        "token",
        "api_key",
        "client_secret",
        "private_key",
        "secret_key",
        "mavlink_anywhere_api_token",
        "smart_wifi_manager_api_token",
        "webrtc_turn_credential",
    }
    return any(term in normalized for term in sensitive_terms)


def secret_scan_finding(
    *,
    detector: str,
    artifact_path: str,
    severity: str = "high",
    line: int | None = None,
    column: int | None = None,
    json_path: str | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    finding = {
        "detector": detector,
        "severity": severity,
        "artifact_path": artifact_path,
        "action": "blocked",
    }
    if line is not None:
        finding["line"] = line
    if column is not None:
        finding["column"] = column
    if json_path is not None:
        finding["json_path"] = json_path
    if key is not None:
        finding["key"] = key
    return finding


def scan_text_for_secret_findings(text: str, artifact_path: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for detector, pattern in (
        ("private_key_block", PRIVATE_KEY_RE),
        ("uri_userinfo_credentials", URI_CREDENTIAL_RE),
        ("authorization_header_secret", AUTHORIZATION_SECRET_RE),
    ):
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            column = match.start() - text.rfind("\n", 0, match.start())
            findings.append(
                secret_scan_finding(
                    detector=detector,
                    artifact_path=artifact_path,
                    line=line,
                    column=column,
                )
            )

    for match in QUERY_SECRET_RE.finditer(text):
        value = match.group(1)
        if secret_value_is_safe_placeholder(value):
            continue
        line = text.count("\n", 0, match.start()) + 1
        column = match.start() - text.rfind("\n", 0, match.start())
        findings.append(
            secret_scan_finding(
                detector="query_parameter_secret",
                artifact_path=artifact_path,
                line=line,
                column=column,
            )
        )

    for line_number, line_text in enumerate(text.splitlines(), start=1):
        for match in SENSITIVE_ASSIGNMENT_RE.finditer(line_text):
            key = match.group("key")
            value = match.group("value")
            if not secret_key_is_sensitive(key) or secret_value_is_safe_placeholder(value):
                continue
            findings.append(
                secret_scan_finding(
                    detector="sensitive_assignment",
                    artifact_path=artifact_path,
                    line=line_number,
                    column=match.start("value") + 1,
                    key=key,
                )
            )
    return findings


def json_scalar_secret_findings(
    data: Any,
    artifact_path: str,
    *,
    path: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            next_path = (*path, str(key))
            if secret_key_is_sensitive(key) and not isinstance(value, (dict, list)):
                if not secret_value_is_safe_placeholder(value):
                    findings.append(
                        secret_scan_finding(
                            detector="structured_sensitive_key",
                            artifact_path=artifact_path,
                            json_path=".".join(next_path),
                            key=str(key),
                        )
                    )
            if isinstance(value, str):
                for detector, pattern in (
                    ("private_key_block", PRIVATE_KEY_RE),
                    ("uri_userinfo_credentials", URI_CREDENTIAL_RE),
                    ("authorization_header_secret", AUTHORIZATION_SECRET_RE),
                    ("query_parameter_secret", QUERY_SECRET_RE),
                ):
                    if pattern.search(value) and not secret_value_is_safe_placeholder(value):
                        findings.append(
                            secret_scan_finding(
                                detector=detector,
                                artifact_path=artifact_path,
                                json_path=".".join(next_path),
                                key=str(key),
                            )
                        )
            findings.extend(json_scalar_secret_findings(value, artifact_path, path=next_path))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            findings.extend(
                json_scalar_secret_findings(value, artifact_path, path=(*path, str(index)))
            )
    return findings


def scan_json_for_secret_findings(text: str, artifact_path: str, suffix: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if suffix == ".jsonl":
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            for finding in json_scalar_secret_findings(parsed, artifact_path):
                finding.setdefault("line", line_number)
                findings.append(finding)
        return findings
    if suffix == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        return json_scalar_secret_findings(parsed, artifact_path)
    return []


def dedupe_secret_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    deduped = []
    for finding in findings:
        key = (
            finding.get("detector"),
            finding.get("artifact_path"),
            finding.get("line"),
            finding.get("column"),
            finding.get("json_path"),
            finding.get("key"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def read_text_artifact_for_secret_scan(path: Path) -> tuple[str | None, dict[str, Any] | None]:
    suffix = path.suffix.lower()
    size = path.stat().st_size
    relative = str(path)
    if suffix in SECRET_SCAN_SKIP_SUFFIXES:
        return None, {
            "artifact_path": relative,
            "size_bytes": size,
            "sha256": sha256_file(path),
            "reason": f"binary_or_large_artifact_suffix:{suffix}",
        }
    if suffix not in SECRET_SCAN_TEXT_SUFFIXES:
        return None, {
            "artifact_path": relative,
            "size_bytes": size,
            "sha256": sha256_file(path),
            "reason": f"unsupported_text_suffix:{suffix or '<none>'}",
        }
    if size > SECRET_SCAN_MAX_FILE_BYTES:
        return None, {
            "artifact_path": relative,
            "size_bytes": size,
            "sha256": sha256_file(path),
            "reason": "text_artifact_too_large",
        }
    sample = path.read_bytes()[:4096]
    if b"\x00" in sample:
        return None, {
            "artifact_path": relative,
            "size_bytes": size,
            "sha256": sha256_file(path),
            "reason": "nul_byte_binary_content",
        }
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError:
        return None, {
            "artifact_path": relative,
            "size_bytes": size,
            "sha256": sha256_file(path),
            "reason": "non_utf8_text_artifact",
        }


def scan_evidence_artifacts_for_secrets(run_dir: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    scanned_artifacts = 0
    secret_report_path = run_dir / "security" / "secret_scan.json"
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
        if path == secret_report_path:
            continue
        relative_path = relative_to_run_dir(path, run_dir)
        text, skip = read_text_artifact_for_secret_scan(path)
        if skip is not None:
            skip["artifact_path"] = relative_path
            skipped.append(skip)
            continue
        if text is None:
            continue
        scanned_artifacts += 1
        findings.extend(scan_text_for_secret_findings(text, relative_path))
        findings.extend(
            scan_json_for_secret_findings(text, relative_path, path.suffix.lower())
        )

    findings = dedupe_secret_findings(findings)
    high_confidence = [item for item in findings if item.get("severity") == "high"]
    report = {
        "schema_version": 1,
        "generated_at": utc_now().isoformat(),
        "ok": not high_confidence,
        "status": "pass" if not high_confidence else "blocked",
        "high_confidence_findings": len(high_confidence),
        "warning_findings": 0,
        "scanned_artifact_count": scanned_artifacts,
        "skipped_binary_count": len(skipped),
        "findings": findings[:100],
        "skipped_artifacts": skipped[:100],
        "max_file_bytes": SECRET_SCAN_MAX_FILE_BYTES,
        "detectors": [
            "private_key_block",
            "uri_userinfo_credentials",
            "authorization_header_secret",
            "query_parameter_secret",
            "sensitive_assignment",
            "structured_sensitive_key",
        ],
        "claim_boundary": (
            "Findings intentionally omit matched values and context lines. A "
            "blocked scan means the copied evidence bundle is not acceptable "
            "until sanitized artifacts are re-collected."
        ),
    }
    write_json(secret_report_path, report)
    return report


def artifact_content_checks(plan: dict[str, Any], run_dir: Path) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    checks["px4_container_metadata"] = validate_px4_container_metadata_for_plan(
        plan,
        run_dir / "px4" / "container_metadata.json",
    )
    checks["secret_scan"] = scan_evidence_artifacts_for_secrets(run_dir)
    if not plan_requires_gazebo_visual_evidence(plan):
        return checks

    video_port = (
        ((plan.get("stack") or {}).get("video") or {}).get("udp_port")
        or (((plan.get("stack") or {}).get("px4") or {}).get("ports") or {}).get("gazebo_video_udp")
    )
    expected_port = video_port if isinstance(video_port, int) else None
    checks["generated_receiver_proof_manifest"] = (
        validate_generated_receiver_proof_manifest(
            run_dir / GAZEBO_VISUAL_EVIDENCE_PATHS["generated_receiver_proof_manifest"]
        )
    )
    checks["gazebo_receiver_pipeline"] = validate_text_pipeline_file(
        run_dir / GAZEBO_VISUAL_EVIDENCE_PATHS["gazebo_receiver_pipeline"],
        expected_udp_port=expected_port,
    )
    checks["gazebo_frame_hashes"] = validate_frame_hashes(
        run_dir / GAZEBO_VISUAL_EVIDENCE_PATHS["gazebo_frame_hashes"]
    )
    checks["tracker_command_trace"] = validate_trace_jsonl(
        run_dir / GAZEBO_VISUAL_EVIDENCE_PATHS["tracker_command_trace"],
        expected_record_type="tracker_command",
    )
    checks["offboard_publish_trace"] = validate_trace_jsonl(
        run_dir / GAZEBO_VISUAL_EVIDENCE_PATHS["offboard_publish_trace"],
        expected_record_type="offboard_publish",
    )
    return checks


def run_command(command: list[str], cwd: Path, timeout_s: float = 10.0) -> dict[str, Any]:
    started_at = utc_now()
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return {
            "command": command,
            "cwd": str(cwd),
            "started_at": started_at.isoformat(),
            "finished_at": utc_now().isoformat(),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except FileNotFoundError as exc:
        return {
            "command": command,
            "cwd": str(cwd),
            "started_at": started_at.isoformat(),
            "finished_at": utc_now().isoformat(),
            "returncode": None,
            "error": str(exc),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "cwd": str(cwd),
            "started_at": started_at.isoformat(),
            "finished_at": utc_now().isoformat(),
            "returncode": None,
            "timeout_s": timeout_s,
            "stdout": exc.stdout,
            "stderr": exc.stderr,
            "error": "timeout",
        }


def http_request_json(
    url: str,
    *,
    method: str = "GET",
    json_body: Any | None = None,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    started_at = utc_now()
    body = None
    headers = {"Accept": "application/json"}
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method.upper(),
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            response_body = response.read()
            text = response_body.decode("utf-8", errors="replace")
            try:
                parsed: Any = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            return {
                "method": method.upper(),
                "url": url,
                "started_at": started_at.isoformat(),
                "finished_at": utc_now().isoformat(),
                "ok": 200 <= response.status < 300,
                "status": response.status,
                "headers": dict(response.headers.items()),
                "json": parsed,
                "text": text if parsed is None else None,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read()
        text = body.decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        return {
            "method": method.upper(),
            "url": url,
            "started_at": started_at.isoformat(),
            "finished_at": utc_now().isoformat(),
            "ok": False,
            "status": exc.code,
            "headers": dict(exc.headers.items()),
            "json": parsed,
            "text": text if parsed is None else None,
            "error": str(exc),
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "method": method.upper(),
            "url": url,
            "started_at": started_at.isoformat(),
            "finished_at": utc_now().isoformat(),
            "ok": False,
            "error": str(exc),
        }


def http_get_json(url: str, timeout_s: float = 5.0) -> dict[str, Any]:
    return http_request_json(url, method="GET", timeout_s=timeout_s)


def current_git_metadata() -> dict[str, Any]:
    commands = {
        "head": ["git", "rev-parse", "HEAD"],
        "branch": ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        "status_short": ["git", "status", "--short"],
        "remote": ["git", "remote", "-v"],
    }
    return {name: run_command(command, PROJECT_ROOT) for name, command in commands.items()}


def runtime_metadata() -> dict[str, Any]:
    commands = {
        "python": [sys.executable, "--version"],
        "docker": ["docker", "version", "--format", "{{json .}}"],
        "mavlink_routerd": ["mavlink-routerd", "--version"],
        "mavlink2rest": [str(PROJECT_ROOT / "bin" / "mavlink2rest"), "--version"],
    }
    return {
        "generated_at": utc_now().isoformat(),
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "commands": {
            name: run_command(command, PROJECT_ROOT)
            for name, command in commands.items()
        },
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utc_now().isoformat()
    write_json(path, manifest)


def create_run_dir(artifact_root: Path, plan_name: str, run_id: str | None) -> Path:
    safe_plan = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in plan_name)
    selected_id = run_id or utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    return artifact_root / f"{selected_id}-{safe_plan}"


def build_px4_container_command(
    plan: dict[str, Any],
    run_id: str,
    image_override: str | None,
    model_override: str | None,
    container_name_override: str | None,
) -> tuple[str, list[str]]:
    px4 = plan["stack"]["px4"]
    image = image_override or px4["recommended_image"]
    model = model_override or px4["vehicle_model"]
    container_name = container_name_override or f"pixeagle-px4-sitl-{run_id}"
    network_mode = px4.get("network_mode", "host")
    environment = dict(px4.get("environment") or {})
    environment["PX4_SIM_MODEL"] = model
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        network_mode,
        "--pull=never",
        "--label",
        f"{MANAGED_CONTAINER_LABEL}=true",
        "--label",
        f"{RUN_ID_CONTAINER_LABEL}={run_id}",
    ]
    for key in sorted(environment):
        command.extend(["-e", f"{key}={environment[key]}"])
    command.append(image)
    return container_name, command


def docker_container_name_exists(container_name: str) -> bool:
    result = run_command(
        ["docker", "ps", "-a", "--format", "{{.Names}}"],
        PROJECT_ROOT,
        timeout_s=10.0,
    )
    if result.get("returncode") != 0:
        return False
    names = {line.strip() for line in str(result.get("stdout") or "").splitlines()}
    return container_name in names


def inspect_docker_container(container_name: str) -> dict[str, Any] | None:
    result = run_command(
        ["docker", "inspect", "--format", "{{json .}}", container_name],
        PROJECT_ROOT,
        timeout_s=10.0,
    )
    if result.get("returncode") != 0:
        return None
    output = str(result.get("stdout") or "").strip()
    if not output:
        return None
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def owned_px4_container_id(container_name: str, run_id: str) -> str | None:
    info = inspect_docker_container(container_name)
    if not info:
        return None
    labels = (((info.get("Config") or {}).get("Labels")) or {})
    if labels.get(MANAGED_CONTAINER_LABEL) != "true":
        return None
    if labels.get(RUN_ID_CONTAINER_LABEL) != run_id:
        return None
    container_id = info.get("Id")
    return str(container_id) if container_id else None


def managed_px4_log_limit_bytes() -> int:
    raw_value = os.environ.get("PIXEAGLE_SITL_MAX_PX4_LOG_BYTES")
    if not raw_value:
        return DEFAULT_MANAGED_PX4_LOG_LIMIT_BYTES
    try:
        parsed = int(raw_value)
    except ValueError:
        return DEFAULT_MANAGED_PX4_LOG_LIMIT_BYTES
    return max(1024, parsed)


def scrub_managed_px4_stdout_chunk(
    pending: bytes,
    chunk: bytes,
    *,
    final: bool = False,
) -> tuple[bytes, bytes, int, int]:
    payload = ANSI_ESCAPE_RE.sub(b"", pending + chunk).replace(b"\r", b"\n")
    if final:
        lines = payload.split(b"\n")
        next_pending = b""
    else:
        lines = payload.split(b"\n")
        next_pending = lines.pop()

    output_lines: list[bytes] = []
    filtered_prompt_lines = 0
    forced_pending_flushes = 0
    for line in lines:
        stripped = line.strip()
        if stripped == b"pxh>":
            filtered_prompt_lines += 1
            continue
        if not stripped and not output_lines:
            continue
        output_lines.append(line.rstrip() + b"\n")

    if not final and len(next_pending) > MAX_MANAGED_PX4_PENDING_BYTES:
        flush_size = len(next_pending) - MAX_MANAGED_PX4_PENDING_BYTES
        output_lines.append(next_pending[:flush_size] + b"\n")
        next_pending = next_pending[flush_size:]
        forced_pending_flushes = 1

    return (
        b"".join(output_lines),
        next_pending,
        filtered_prompt_lines,
        forced_pending_flushes,
    )


class ManagedPx4LogCapture:
    def __init__(self, path: Path, max_bytes: int) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.raw_bytes_read = 0
        self.bytes_written = 0
        self.filtered_prompt_lines = 0
        self.forced_pending_flushes = 0
        self.truncated = False
        self.reader_error: str | None = None
        self._pending = b""
        self._handle = path.open("wb")
        self._thread: threading.Thread | None = None

    def start(self, pipe: Any) -> None:
        self._thread = threading.Thread(
            target=self._reader,
            args=(pipe,),
            name="pixeagle-px4-log-capture",
            daemon=True,
        )
        self._thread.start()

    def _reader(self, pipe: Any) -> None:
        try:
            for chunk in iter(lambda: pipe.read(64 * 1024), b""):
                if not isinstance(chunk, bytes):
                    chunk = bytes(chunk)
                self.raw_bytes_read += len(chunk)
                output, self._pending, filtered, forced_flushes = scrub_managed_px4_stdout_chunk(
                    self._pending,
                    chunk,
                )
                self.filtered_prompt_lines += filtered
                self.forced_pending_flushes += forced_flushes
                self._write_bounded(output)

            output, self._pending, filtered, forced_flushes = scrub_managed_px4_stdout_chunk(
                self._pending,
                b"",
                final=True,
            )
            self.filtered_prompt_lines += filtered
            self.forced_pending_flushes += forced_flushes
            self._write_bounded(output)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            self.reader_error = repr(exc)
        finally:
            try:
                pipe.close()
            except OSError:
                pass

    def _write_bounded(self, payload: bytes) -> None:
        if not payload:
            return
        remaining = self.max_bytes - self.bytes_written
        if remaining <= 0:
            self.truncated = True
            return
        if len(payload) > remaining:
            marker = self._truncation_marker()
            if remaining > len(marker):
                self._handle.write(payload[: remaining - len(marker)])
                self._handle.write(marker)
            else:
                self._handle.write(marker[:remaining])
            self._handle.flush()
            self.bytes_written += remaining
            self.truncated = True
            return
        self._handle.write(payload)
        self._handle.flush()
        self.bytes_written += len(payload)

    def _truncation_marker(self) -> bytes:
        return (
            b"\n[PixEagle harness truncated managed PX4 stdout at "
            + str(self.max_bytes).encode("ascii")
            + b" bytes]\n"
        )

    def close(self) -> dict[str, Any]:
        if self._thread is not None:
            self._thread.join(timeout=10.0)
        thread_alive = bool(self._thread and self._thread.is_alive())
        if self._pending:
            output, self._pending, filtered, forced_flushes = scrub_managed_px4_stdout_chunk(
                self._pending,
                b"",
                final=True,
            )
            self.filtered_prompt_lines += filtered
            self.forced_pending_flushes += forced_flushes
            self._write_bounded(output)
        self._handle.close()
        try:
            reported_path = str(self.path.relative_to(PROJECT_ROOT))
        except ValueError:
            reported_path = str(self.path)
        return {
            "path": reported_path,
            "ok": not thread_alive and self.reader_error is None,
            "max_bytes": self.max_bytes,
            "raw_bytes_read": self.raw_bytes_read,
            "bytes_written": self.bytes_written,
            "filtered_prompt_lines": self.filtered_prompt_lines,
            "forced_pending_flushes": self.forced_pending_flushes,
            "reader_error": self.reader_error,
            "thread_finished": not thread_alive,
            "truncated": self.truncated,
        }


def start_px4_container(
    container_name: str,
    command: list[str],
    run_dir: Path,
) -> tuple[subprocess.Popen[Any], ManagedPx4LogCapture]:
    if docker_container_name_exists(container_name):
        raise RuntimeError(
            "Refusing to start PX4 SITL because a Docker container already "
            f"uses the requested name: {container_name}"
        )
    ensure_dir(run_dir / "logs")
    ensure_dir(run_dir / "commands")
    command_file = run_dir / "commands" / "start_px4_sitl.command"
    command_file.write_text(" ".join(subprocess.list2cmdline([part]) for part in command) + "\n")
    log_capture = ManagedPx4LogCapture(
        run_dir / "logs" / "px4_sitl.log",
        managed_px4_log_limit_bytes(),
    )
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
    )
    if process.stdout is None:
        raise RuntimeError("PX4 SITL stdout pipe was not created")
    log_capture.start(process.stdout)
    return process, log_capture


def stop_px4_container(
    container_id: str | None,
    process: subprocess.Popen[Any] | None,
) -> dict[str, Any]:
    if container_id:
        stop_result = run_command(["docker", "stop", container_id], PROJECT_ROOT, timeout_s=20.0)
    else:
        stop_result = {
            "skipped": True,
            "reason": "No harness-owned PX4 container id was verified; docker stop was not run.",
        }
    if process is not None:
        try:
            process.wait(timeout=20.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)
            stop_result["forced_kill"] = True
    return stop_result


def should_auto_collect_px4_container_artifacts(
    *,
    execute_mode: bool,
    probe_only_mode: bool,
    requested_auto_collection: bool,
    px4_container_id: str | None,
    px4_container_name: str | None,
) -> bool:
    """Return True only when container artifact discovery is allowed.

    Execute mode starts a harness-owned container and may only inspect/copy from
    it after the ownership labels were verified and an immutable container ID is
    known. Probe-only mode may inspect an operator-selected container by name or
    ID, but only when the operator explicitly opted in.
    """
    if execute_mode:
        return bool(px4_container_id)
    if probe_only_mode:
        return bool(requested_auto_collection and (px4_container_id or px4_container_name))
    return False


def get_nested(data: Any, dotted_path: str) -> Any:
    current = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def result_payload(probe_results: dict[str, dict[str, Any]], relative_path: str) -> dict[str, Any]:
    result = probe_results.get(relative_path, {}).get("raw")
    return result if isinstance(result, dict) else {}


def mavlink_anywhere_policy(plan: dict[str, Any]) -> dict[str, Any]:
    policy = (
        ((plan.get("stack") or {}).get("routing") or {}).get("compatibility_policy")
        or {}
    )
    return policy if isinstance(policy, dict) else {}


def first_string_field(data: Any, names: set[str]) -> tuple[str | None, str | None]:
    if isinstance(data, dict):
        for key, value in data.items():
            normalized = str(key).lower()
            if normalized in names and isinstance(value, str) and value.strip():
                return value.strip(), str(key)
            found, found_path = first_string_field(value, names)
            if found is not None:
                return found, f"{key}.{found_path}" if found_path else str(key)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            found, found_path = first_string_field(value, names)
            if found is not None:
                return found, f"{index}.{found_path}" if found_path else str(index)
    return None, None


def mavlink_anywhere_dashboard_version_evidence(
    plan: dict[str, Any],
    probe_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    policy = mavlink_anywhere_policy(plan)
    status_payload = result_payload(probe_results, "route_map/mavlink_anywhere_status.json")
    diagnostics_payload = result_payload(
        probe_results, "route_map/mavlink_anywhere_diagnostics.json"
    )
    profile_payload = result_payload(
        probe_results, "route_map/mavlink_anywhere_profiles_summary.json"
    )
    status_json = status_payload.get("json") if isinstance(status_payload, dict) else None
    version = status_json.get("version") if isinstance(status_json, dict) else None
    required_status_fields = policy.get("required_status_fields") or ["version"]
    missing_status_fields = [
        field
        for field in required_status_fields
        if not isinstance(status_json, dict) or status_json.get(field) in (None, "")
    ]

    installed_ref = None
    installed_ref_path = None
    for payload_name, payload in (
        ("status", status_json),
        ("diagnostics", diagnostics_payload.get("json")),
        ("profiles_summary", profile_payload.get("json")),
    ):
        installed_ref, installed_ref_path = first_string_field(
            payload,
            {"source_ref", "git_ref", "commit", "revision", "build_ref"},
        )
        if installed_ref is not None:
            installed_ref_path = f"{payload_name}.{installed_ref_path}"
            break

    minimum_semver = policy.get("minimum_dashboard_semver")
    version_ok = semver_meets_minimum(version, minimum_semver)
    collected = bool(status_payload.get("ok") and isinstance(version, str) and version.strip())
    return {
        "schema_version": 1,
        "generated_at": utc_now().isoformat(),
        "provider": "mavlink-anywhere",
        "source_artifact": "route_map/mavlink_anywhere_status.json",
        "status_probe_ok": bool(status_payload.get("ok")),
        "status_code": status_payload.get("status"),
        "collected": collected,
        "installed_dashboard_version": version if isinstance(version, str) else None,
        "installed_source_ref": installed_ref,
        "installed_source_ref_path": installed_ref_path,
        "reviewed_source_ref": policy.get("reviewed_source_ref"),
        "reviewed_version": policy.get("reviewed_version"),
        "minimum_dashboard_semver": minimum_semver,
        "version_meets_policy": version_ok,
        "missing_status_fields": missing_status_fields,
        "required_api_paths": policy.get("required_api_paths", []),
        "claim_boundary": (
            "This records the MavlinkAnywhere dashboard read-contract evidence "
            "for this SITL artifact set only. It does not install, update, or "
            "mutate the sidecar."
        ),
    }


def mavlink_anywhere_auth_failure(payload: dict[str, Any]) -> bool:
    status = payload.get("status")
    if status in {401, 403}:
        return True
    text = str(payload.get("text") or "").lower()
    return bool(
        status == 200
        and payload.get("json") is None
        and any(term in text for term in ("login", "unauthorized", "forbidden", "authentication"))
    )


def mavlink_anywhere_required_probe_payloads(
    plan: dict[str, Any],
    probe_results: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    policy = mavlink_anywhere_policy(plan)
    required_paths = policy.get("required_api_paths")
    if not isinstance(required_paths, list):
        required_paths = MAVLINK_ANYWHERE_REQUIRED_API_PATHS
    payloads: dict[str, dict[str, Any]] = {}
    for api_path in required_paths:
        artifact = MAVLINK_ANYWHERE_API_ARTIFACTS.get(str(api_path))
        if artifact is None:
            continue
        payloads[str(api_path)] = result_payload(probe_results, artifact)
    return payloads


def mavlink_anywhere_compatibility_check(
    plan: dict[str, Any],
    probe_results: dict[str, dict[str, Any]],
    route_check: dict[str, Any],
) -> dict[str, Any]:
    policy = mavlink_anywhere_policy(plan)
    version_evidence = mavlink_anywhere_dashboard_version_evidence(plan, probe_results)
    probe_payloads = mavlink_anywhere_required_probe_payloads(plan, probe_results)
    reasons: list[dict[str, Any]] = []

    auth_failures = [
        {"api_path": api_path, "status": payload.get("status")}
        for api_path, payload in probe_payloads.items()
        if mavlink_anywhere_auth_failure(payload)
    ]
    if auth_failures:
        classification = "unexpected_auth"
        reasons.append(
            {
                "reason": "read_probe_required_authentication",
                "details": auth_failures,
            }
        )
    else:
        status_payload = probe_payloads.get("/api/v1/status", {})
        status_code = status_payload.get("status")
        if not status_payload.get("ok") and status_code is None:
            classification = "unavailable"
            reasons.append(
                {
                    "reason": "status_probe_transport_unavailable",
                    "error": status_payload.get("error"),
                }
            )
        else:
            unsupported: list[dict[str, Any]] = []
            unprepared: list[dict[str, Any]] = []
            for api_path, payload in probe_payloads.items():
                status = payload.get("status")
                if payload.get("ok"):
                    if payload.get("json") is None:
                        unsupported.append(
                            {
                                "api_path": api_path,
                                "status": status,
                                "reason": "json_contract_missing",
                            }
                        )
                    continue
                if status in {404, 405}:
                    unsupported.append(
                        {
                            "api_path": api_path,
                            "status": status,
                            "reason": "required_api_path_missing",
                        }
                    )
                elif status is None:
                    unsupported.append(
                        {
                            "api_path": api_path,
                            "status": status,
                            "reason": "required_api_path_unreadable",
                        }
                    )
                elif isinstance(status, int) and status >= 500 and api_path != "/api/v1/status":
                    unprepared.append(
                        {
                            "api_path": api_path,
                            "status": status,
                            "reason": "sidecar_config_unprepared",
                        }
                    )
                else:
                    unsupported.append(
                        {
                            "api_path": api_path,
                            "status": status,
                            "reason": "required_api_path_unexpected_status",
                        }
                    )

            if not version_evidence.get("collected"):
                unsupported.append(
                    {
                        "api_path": "/api/v1/status",
                        "reason": "dashboard_version_missing",
                        "missing_status_fields": version_evidence.get(
                            "missing_status_fields", []
                        ),
                    }
                )
            elif not version_evidence.get("version_meets_policy"):
                unsupported.append(
                    {
                        "api_path": "/api/v1/status",
                        "reason": "dashboard_version_below_policy",
                        "installed_dashboard_version": version_evidence.get(
                            "installed_dashboard_version"
                        ),
                        "minimum_dashboard_semver": version_evidence.get(
                            "minimum_dashboard_semver"
                        ),
                    }
                )

            if unsupported:
                classification = "unsupported_contract_version"
                reasons.extend(unsupported)
            elif unprepared or not route_check.get("ok"):
                classification = "unprepared_config"
                reasons.extend(unprepared)
                if not route_check.get("ok"):
                    reasons.append(
                        {
                            "reason": "required_outputs_or_profile_not_prepared",
                            "missing_outputs": route_check.get("missing_outputs", []),
                            "profile_metadata_mismatches": route_check.get(
                                "profile_metadata_mismatches", []
                            ),
                        }
                    )
            else:
                classification = "prepared_routing"

    if classification not in MAVLINK_ANYWHERE_COMPATIBILITY_CLASSIFICATIONS:
        classification = "unsupported_contract_version"
        reasons.append({"reason": "internal_unknown_classification"})

    return {
        "ok": classification == "prepared_routing",
        "classification": classification,
        "reasons": reasons,
        "policy": {
            "provider": policy.get("provider"),
            "reviewed_source_ref": policy.get("reviewed_source_ref"),
            "reviewed_version": policy.get("reviewed_version"),
            "minimum_dashboard_semver": policy.get("minimum_dashboard_semver"),
            "auth_expectation": policy.get("auth_expectation"),
            "required_api_paths": policy.get("required_api_paths", []),
        },
        "version_evidence": version_evidence,
        "required_probe_status": {
            api_path: {
                "ok": bool(payload.get("ok")),
                "status": payload.get("status"),
                "error": payload.get("error"),
            }
            for api_path, payload in probe_payloads.items()
        },
    }


def iter_json_paths(data: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Any]]:
    items = [(path, data)]
    if isinstance(data, dict):
        for key, value in data.items():
            items.extend(iter_json_paths(value, (*path, str(key))))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            items.extend(iter_json_paths(value, (*path, str(index))))
    return items


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, dict):
        for key in ("value", "raw", "number", "id", "bits", "bitmask"):
            parsed = _int_or_none(value.get(key))
            if parsed is not None:
                return parsed
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _path_int_after(path: tuple[str, ...], marker: str) -> int | None:
    marker_lower = marker.lower()
    for index, part in enumerate(path[:-1]):
        if part.lower() == marker_lower:
            return _int_or_none(path[index + 1])
    return None


def _is_px4_autopilot(value: Any) -> bool:
    parsed = _int_or_none(value)
    if parsed is not None:
        return parsed == PX4_MAV_AUTOPILOT_PX4
    if isinstance(value, dict):
        text_values = [
            str(item)
            for item in value.values()
            if isinstance(item, (str, int, float))
        ]
        return any("PX4" in item.upper() for item in text_values)
    if isinstance(value, str):
        return "PX4" in value.upper()
    return False


def mavlink_message_targets_px4_autopilot(
    message: Any,
    *,
    target_system_ids: set[int] | None = None,
) -> bool:
    target_system = _int_or_none(getattr(message, "target_system", None))
    target_component = _int_or_none(getattr(message, "target_component", None))
    if (
        target_system is None
        or target_system <= 0
        or target_component != PX4_AUTOPILOT_COMPONENT_ID
    ):
        return False
    if target_system_ids is not None and target_system not in target_system_ids:
        return False
    return True


def heartbeat_custom_mode_observations(mavlink_payload: Any) -> list[dict[str, Any]]:
    """Extract HEARTBEAT custom_mode observations from a MAVLink2REST payload."""
    observations: list[dict[str, Any]] = []
    for path, value in iter_json_paths(mavlink_payload):
        if not isinstance(value, dict):
            continue

        path_has_heartbeat = any(part.upper() == "HEARTBEAT" for part in path)
        declared_type = str(
            value.get("message_type")
            or value.get("type")
            or value.get("name")
            or value.get("msgid")
            or ""
        ).upper()
        path_is_heartbeat_record = bool(path) and path[-1].upper() == "HEARTBEAT"
        if path_has_heartbeat and not path_is_heartbeat_record and declared_type != "HEARTBEAT":
            continue
        if not path_has_heartbeat and declared_type != "HEARTBEAT":
            continue

        message = value.get("message") if isinstance(value.get("message"), dict) else value
        custom_mode = _int_or_none(message.get("custom_mode"))
        if custom_mode is None:
            continue
        component_id = (
            _int_or_none(message.get("component_id"))
            or _int_or_none(message.get("component"))
            or _int_or_none(value.get("component_id"))
            or _int_or_none(value.get("component"))
            or _path_int_after(path, "components")
        )
        system_id = (
            _int_or_none(message.get("system_id"))
            or _int_or_none(message.get("system"))
            or _int_or_none(value.get("system_id"))
            or _int_or_none(value.get("system"))
            or _path_int_after(path, "vehicles")
        )
        autopilot = message.get("autopilot", value.get("autopilot"))
        base_mode = message.get("base_mode", value.get("base_mode"))
        base_mode_value = _int_or_none(base_mode)
        custom_mode_flag_set = (
            base_mode_value is not None
            and bool(base_mode_value & MAV_MODE_FLAG_CUSTOM_MODE_ENABLED)
        )
        identity_failures = []
        if component_id != PX4_AUTOPILOT_COMPONENT_ID:
            identity_failures.append(
                f"component_id must be {PX4_AUTOPILOT_COMPONENT_ID}, got {component_id!r}"
            )
        if not _is_px4_autopilot(autopilot):
            identity_failures.append(
                f"autopilot must identify PX4 ({PX4_MAV_AUTOPILOT_PX4}), got {autopilot!r}"
            )
        if base_mode_value is None:
            identity_failures.append("base_mode is missing or not numeric")
        elif not custom_mode_flag_set:
            identity_failures.append(
                "base_mode must include MAV_MODE_FLAG_CUSTOM_MODE_ENABLED"
            )
        eligible = not identity_failures
        observations.append(
            {
                "path": ".".join(path),
                "system_id": system_id,
                "component_id": component_id,
                "autopilot": autopilot,
                "base_mode": base_mode,
                "base_mode_value": base_mode_value,
                "custom_mode_flag_set": custom_mode_flag_set,
                "custom_mode": custom_mode,
                "is_offboard": custom_mode == PX4_OFFBOARD_CUSTOM_MODE,
                "eligible_px4_autopilot_heartbeat": eligible,
                "identity_failures": identity_failures,
            }
        )
    return observations


def tlog_files_from_manifest(run_dir: Path) -> list[Path]:
    manifest_path = run_dir / "px4" / "tlog_manifest.json"
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    files: list[Path] = []
    for entry in manifest.get("entries", []):
        artifact_path = entry.get("artifact_path") if isinstance(entry, dict) else None
        if not artifact_path:
            continue
        path = run_dir / str(artifact_path)
        if path.exists() and path.is_file():
            files.append(path)
    return files


def _parse_iso_epoch_seconds(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.timestamp()


def offboard_start_observation_windows(run_dir: Path) -> dict[str, Any]:
    """Return epoch-second windows following accepted Offboard-start actions."""
    scenario_path = run_dir / "scenarios" / "scenario_results.json"
    if not scenario_path.exists():
        return {
            "required": True,
            "enforced": False,
            "reason": "scenarios/scenario_results.json was not available.",
            "windows": [],
            "padding_s": PX4_OBSERVATION_WINDOW_PADDING_S,
        }
    try:
        payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "required": True,
            "enforced": False,
            "reason": f"scenarios/scenario_results.json could not be parsed: {exc}",
            "windows": [],
            "padding_s": PX4_OBSERVATION_WINDOW_PADDING_S,
        }

    windows: list[dict[str, Any]] = []
    for scenario in payload.get("scenarios", []):
        if not isinstance(scenario, dict):
            continue
        scenario_finished = _parse_iso_epoch_seconds(scenario.get("finished_at"))
        for action in scenario.get("actions", []):
            if not isinstance(action, dict):
                continue
            if action.get("path") != API_V1_ACTION_OFFBOARD_START_PATH:
                continue
            if action.get("result") != "pass":
                continue
            started = _parse_iso_epoch_seconds(action.get("started_at"))
            action_finished = _parse_iso_epoch_seconds(action.get("finished_at"))
            window_end = scenario_finished or action_finished
            if started is None or window_end is None or window_end < started:
                continue
            windows.append(
                {
                    "scenario_id": scenario.get("id"),
                    "action_id": action.get("id"),
                    "start_timestamp": round(
                        started - PX4_OBSERVATION_WINDOW_PADDING_S,
                        6,
                    ),
                    "end_timestamp": round(
                        window_end + PX4_OBSERVATION_WINDOW_PADDING_S,
                        6,
                    ),
                }
            )

    return {
        "required": True,
        "enforced": bool(windows),
        "reason": None if windows else "No passed /api/v1/actions/offboard-start scenario window was available.",
        "windows": windows,
        "padding_s": PX4_OBSERVATION_WINDOW_PADDING_S,
    }


def timestamp_in_observation_windows(
    timestamp: float,
    observation_windows: list[dict[str, Any]],
) -> bool:
    return any(
        float(window["start_timestamp"]) <= timestamp <= float(window["end_timestamp"])
        for window in observation_windows
    )


def analyze_tlog_setpoint_cadence(
    run_dir: Path,
    *,
    target_system_ids: set[int] | None = None,
    observation_window: dict[str, Any] | None = None,
    require_observation_window: bool = False,
) -> dict[str, Any]:
    """Analyze PX4-observed setpoint cadence from copied MAVLink tlogs."""
    observation_window = observation_window or {
        "required": require_observation_window,
        "enforced": False,
        "reason": None,
        "windows": [],
        "padding_s": PX4_OBSERVATION_WINDOW_PADDING_S,
    }
    observation_windows = observation_window.get("windows", [])
    tlog_files = tlog_files_from_manifest(run_dir)
    if not tlog_files:
        return {
            "ok": False,
            "source": "px4/tlog_manifest.json",
            "reason": "No tlog files were available for PX4-observed setpoint cadence analysis.",
            "message_types": sorted(PX4_SETPOINT_MESSAGE_TYPES),
            "min_rate_hz": PX4_MIN_OFFBOARD_SETPOINT_RATE_HZ,
            "min_duration_s": PX4_MIN_OFFBOARD_SETPOINT_DURATION_S,
            "min_message_count": PX4_MIN_OFFBOARD_SETPOINT_COUNT,
            "target_system_ids": sorted(target_system_ids or []),
            "observation_window": observation_window,
        }

    try:
        from pymavlink import mavutil  # type: ignore
    except Exception as exc:
        return {
            "ok": False,
            "source": "px4/tlog_manifest.json",
            "reason": "pymavlink is not installed, so tlog cadence could not be parsed.",
            "import_error": str(exc),
            "files": [relative_to_run_dir(path, run_dir) for path in tlog_files],
            "message_types": sorted(PX4_SETPOINT_MESSAGE_TYPES),
            "min_rate_hz": PX4_MIN_OFFBOARD_SETPOINT_RATE_HZ,
            "min_duration_s": PX4_MIN_OFFBOARD_SETPOINT_DURATION_S,
            "min_message_count": PX4_MIN_OFFBOARD_SETPOINT_COUNT,
            "target_system_ids": sorted(target_system_ids or []),
            "observation_window": observation_window,
        }

    per_file: list[dict[str, Any]] = []
    all_timestamps: list[float] = []
    rejected_target_count = 0
    rejected_window_count = 0
    for path in tlog_files:
        timestamps: list[float] = []
        rejected_targets = 0
        rejected_outside_window = 0
        parse_error = None
        try:
            connection = mavutil.mavlink_connection(str(path), robust_parsing=True)
            while True:
                message = connection.recv_match(
                    type=sorted(PX4_SETPOINT_MESSAGE_TYPES),
                    blocking=False,
                )
                if message is None:
                    break
                timestamp = getattr(message, "_timestamp", None)
                if not mavlink_message_targets_px4_autopilot(
                    message,
                    target_system_ids=target_system_ids,
                ):
                    rejected_targets += 1
                    continue
                if isinstance(timestamp, (int, float)) and math.isfinite(timestamp):
                    timestamp_f = float(timestamp)
                    if require_observation_window and (
                        not observation_window.get("enforced")
                        or not timestamp_in_observation_windows(
                            timestamp_f,
                            observation_windows,
                        )
                    ):
                        rejected_outside_window += 1
                        continue
                    timestamps.append(timestamp_f)
        except Exception as exc:
            parse_error = str(exc)
        all_timestamps.extend(timestamps)
        rejected_target_count += rejected_targets
        rejected_window_count += rejected_outside_window
        per_file.append(
            {
                "artifact_path": relative_to_run_dir(path, run_dir),
                "setpoint_message_count": len(timestamps),
                "rejected_non_px4_target_messages": rejected_targets,
                "rejected_outside_observation_window_messages": rejected_outside_window,
                "parse_error": parse_error,
            }
        )

    all_timestamps = sorted(all_timestamps)
    parse_errors = [
        {"artifact_path": item["artifact_path"], "parse_error": item["parse_error"]}
        for item in per_file
        if item.get("parse_error")
    ]
    duration_s = (
        all_timestamps[-1] - all_timestamps[0]
        if len(all_timestamps) >= 2
        else 0.0
    )
    observed_rate_hz = (
        (len(all_timestamps) - 1) / duration_s
        if len(all_timestamps) >= 2 and duration_s > 0
        else 0.0
    )
    ok = (
        not parse_errors
        and (not require_observation_window or observation_window.get("enforced"))
        and len(all_timestamps) >= PX4_MIN_OFFBOARD_SETPOINT_COUNT
        and duration_s >= PX4_MIN_OFFBOARD_SETPOINT_DURATION_S
        and observed_rate_hz >= PX4_MIN_OFFBOARD_SETPOINT_RATE_HZ
    )
    if parse_errors:
        reason = "One or more PX4 tlog files could not be fully parsed."
    elif require_observation_window and not observation_window.get("enforced"):
        reason = observation_window.get("reason") or "Offboard-start observation window was not available."
    elif ok:
        reason = None
    elif require_observation_window and rejected_window_count:
        reason = "PX4-observed setpoint cadence was not proven inside the Offboard-start scenario window."
    else:
        reason = "PX4-observed setpoint cadence was not proven from tlog data."
    return {
        "ok": ok,
        "source": "px4/tlog_manifest.json",
        "reason": reason,
        "message_types": sorted(PX4_SETPOINT_MESSAGE_TYPES),
        "min_rate_hz": PX4_MIN_OFFBOARD_SETPOINT_RATE_HZ,
        "min_duration_s": PX4_MIN_OFFBOARD_SETPOINT_DURATION_S,
        "min_message_count": PX4_MIN_OFFBOARD_SETPOINT_COUNT,
        "target_system_ids": sorted(target_system_ids or []),
        "setpoint_message_count": len(all_timestamps),
        "rejected_non_px4_target_messages": rejected_target_count,
        "rejected_outside_observation_window_messages": rejected_window_count,
        "duration_s": round(duration_s, 6),
        "observed_rate_hz": round(observed_rate_hz, 6),
        "observation_window": observation_window,
        "parse_errors": parse_errors,
        "files": per_file,
    }


def collect_px4_offboard_observation_artifact(
    run_dir: Path,
    probe_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Write PX4-observed Offboard mode and setpoint cadence evidence."""
    target = run_dir / "px4" / "offboard_observation.json"
    mavlink_probe = result_payload(probe_results, "probes/mavlink2rest_mavlink.json")
    mavlink_payload = mavlink_probe.get("json")
    heartbeat_observations = heartbeat_custom_mode_observations(mavlink_payload)
    accepted_heartbeat_observations = [
        item
        for item in heartbeat_observations
        if item["is_offboard"] and item["eligible_px4_autopilot_heartbeat"]
    ]
    target_system_ids = {
        int(item["system_id"])
        for item in accepted_heartbeat_observations
        if isinstance(item.get("system_id"), int)
    }
    offboard_mode_ok = bool(accepted_heartbeat_observations)
    observation_window = offboard_start_observation_windows(run_dir)
    cadence = analyze_tlog_setpoint_cadence(
        run_dir,
        target_system_ids=target_system_ids,
        observation_window=observation_window,
        require_observation_window=True,
    )
    checks = {
        "offboard_mode_from_mavlink2rest": {
            "ok": offboard_mode_ok,
            "source": "probes/mavlink2rest_mavlink.json",
            "required_custom_mode": PX4_OFFBOARD_CUSTOM_MODE,
            "required_base_mode_flag": "MAV_MODE_FLAG_CUSTOM_MODE_ENABLED",
            "accepted_system_ids": sorted(target_system_ids),
            "observations": heartbeat_observations,
            "reason": (
                None
                if offboard_mode_ok
                else "MAVLink2REST HEARTBEAT custom_mode did not show PX4 Offboard."
            ),
        },
        "setpoint_cadence_from_tlog": cadence,
    }
    accepted = all(item.get("ok") for item in checks.values())
    reason = None
    if not mavlink_probe.get("ok"):
        reason = "MAVLink2REST MAVLink probe was unavailable."
    elif not offboard_mode_ok:
        reason = checks["offboard_mode_from_mavlink2rest"]["reason"]
    elif not cadence.get("ok"):
        reason = cadence.get("reason")

    evidence = {
        "schema_version": 1,
        "generated_at": utc_now().isoformat(),
        "accepted": accepted,
        "result": "pass" if accepted else "incomplete",
        "claim_boundary": (
            "This artifact is PX4/SITL telemetry evidence only. It does not "
            "claim HIL, field, deployment, or real-aircraft success."
        ),
        "checks": checks,
        "reason": reason,
    }
    write_json(target, evidence)
    return {
        "collected": accepted,
        "placeholder": False,
        "reason": reason,
        "accepted": accepted,
        "artifact": evidence_entry("generated:px4_offboard_observation", target, run_dir),
    }


def endpoint_field(candidate: dict[str, Any], name: str, default: Any = None) -> Any:
    return candidate.get(name, candidate.get(name[:1].upper() + name[1:], default))


def parse_boolish(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}
    return bool(value)


def parse_required_endpoint(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        address = value.get("address")
        port = value.get("port")
        raw = value
        endpoint_type = str(value.get("type", "UdpEndpoint") or "UdpEndpoint")
        mode = str(value.get("mode", "normal") or "normal")
    else:
        raw = value
        text = str(value).strip()
        if "://" in text:
            text = text.split("://", 1)[1]
        if ":" not in text:
            return {"raw": raw, "valid": False, "reason": "missing host:port separator"}
        address, port = text.rsplit(":", 1)
        endpoint_type = "UdpEndpoint"
        mode = "normal"

    try:
        parsed_port = int(port)
    except (TypeError, ValueError):
        return {"raw": raw, "valid": False, "reason": f"invalid port: {port!r}"}

    if not isinstance(address, str) or not address.strip():
        return {"raw": raw, "valid": False, "reason": "missing address"}
    return {
        "raw": raw,
        "valid": True,
        "address": address.strip(),
        "port": parsed_port,
        "type": endpoint_type.strip().lower(),
        "mode": mode.strip().lower(),
    }


def endpoint_like(candidate: Any) -> bool:
    if not isinstance(candidate, dict):
        return False
    keys = {str(key).lower() for key in candidate.keys()}
    return MAVLINK_ANYWHERE_ENDPOINT_REQUIRED_FIELDS <= keys


def iter_endpoint_candidates(data: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() == "endpoints" and isinstance(value, list):
                candidates.extend(item for item in value if endpoint_like(item))
            else:
                candidates.extend(iter_endpoint_candidates(value))
    elif isinstance(data, list):
        for item in data:
            if endpoint_like(item):
                candidates.append(item)
            else:
                candidates.extend(iter_endpoint_candidates(item))
    return candidates


def normalize_endpoint(candidate: dict[str, Any], source: str) -> dict[str, Any] | None:
    if not endpoint_like(candidate):
        return None
    address = endpoint_field(candidate, "address")
    port = endpoint_field(candidate, "port")
    try:
        parsed_port = int(port)
    except (TypeError, ValueError):
        return None
    if not isinstance(address, str) or not address.strip():
        return None
    return {
        "source": source,
        "name": str(endpoint_field(candidate, "name", "") or ""),
        "type": str(endpoint_field(candidate, "type", "") or ""),
        "mode": str(endpoint_field(candidate, "mode", "") or "").strip().lower(),
        "address": address.strip(),
        "port": parsed_port,
        "category": str(endpoint_field(candidate, "category", "") or ""),
        "enabled": parse_boolish(endpoint_field(candidate, "enabled", True), default=True),
    }


def structured_endpoints_from_payload(
    probe_results: dict[str, dict[str, Any]],
    relative_path: str,
    source: str,
) -> list[dict[str, Any]]:
    payload = result_payload(probe_results, relative_path)
    structured = payload.get("json")
    if not isinstance(structured, (dict, list)):
        return []
    endpoints: list[dict[str, Any]] = []
    for candidate in iter_endpoint_candidates(structured):
        endpoint = normalize_endpoint(candidate, source)
        if endpoint is not None:
            endpoints.append(endpoint)
    return endpoints


def endpoint_matches_required(endpoint: dict[str, Any], required: dict[str, Any]) -> bool:
    if not endpoint.get("enabled", True):
        return False
    if str(endpoint.get("type", "")).lower() != required.get("type", "udpendpoint"):
        return False
    if endpoint.get("mode") != required.get("mode", "normal"):
        return False
    return (
        endpoint.get("address") == required.get("address")
        and endpoint.get("port") == required.get("port")
    )


def mavlink_anywhere_endpoint_check(
    plan: dict[str, Any],
    probe_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source_paths = {
        "endpoints": "route_map/mavlink_anywhere_endpoints.json",
        "config": "route_map/mavlink_anywhere_config.json",
        "profiles_summary": "route_map/mavlink_anywhere_profiles_summary.json",
    }
    endpoints_by_source = {
        source: structured_endpoints_from_payload(probe_results, path, source)
        for source, path in source_paths.items()
    }
    required_outputs = plan["stack"]["routing"].get("required_outputs", [])
    parsed_required = [parse_required_endpoint(value) for value in required_outputs]

    invalid_required = [
        {"endpoint": item.get("raw"), "reason": item.get("reason")}
        for item in parsed_required
        if not item.get("valid")
    ]
    matched_outputs: list[dict[str, Any]] = []
    missing_outputs: list[dict[str, Any]] = []
    for required in parsed_required:
        if not required.get("valid"):
            continue
        per_source_matches = {}
        missing_sources = []
        for source, endpoints in endpoints_by_source.items():
            match = next(
                (
                    endpoint
                    for endpoint in endpoints
                    if endpoint_matches_required(endpoint, required)
                ),
                None,
            )
            if match is None:
                missing_sources.append(source)
            else:
                per_source_matches[source] = {
                    "name": match["name"],
                    "type": match["type"],
                    "mode": match["mode"],
                    "category": match["category"],
                    "enabled": match["enabled"],
                }
        if missing_sources:
            missing_outputs.append(
                {
                    "endpoint": required["raw"],
                    "address": required["address"],
                    "port": required["port"],
                    "missing_from_sources": missing_sources,
                }
            )
        else:
            matched_outputs.append(
                {
                    "endpoint": required["raw"],
                    "address": required["address"],
                    "port": required["port"],
                    "matches": per_source_matches,
                }
            )

    profile_payload = result_payload(
        probe_results, "route_map/mavlink_anywhere_profiles_summary.json"
    )
    profile_json = profile_payload.get("json") if isinstance(profile_payload, dict) else {}
    profile_metadata = {}
    if isinstance(profile_json, dict):
        profile_metadata = {
            "schema": profile_json.get("schema"),
            "backend": profile_json.get("backend"),
            "source": profile_json.get("source"),
            "present": profile_json.get("present"),
            "hash": profile_json.get("hash"),
            "profile_count": profile_json.get("profile_count"),
        }
    profile_metadata_mismatches = []
    required_profile_metadata = mavlink_anywhere_policy(plan).get(
        "required_profile_metadata",
        {"backend": "mavlink-anywhere", "present": True},
    )
    if not isinstance(required_profile_metadata, dict):
        required_profile_metadata = {"backend": "mavlink-anywhere", "present": True}
    for key, expected in required_profile_metadata.items():
        if profile_metadata.get(key) != expected:
            profile_metadata_mismatches.append(
                {
                    "path": f"route_map/mavlink_anywhere_profiles_summary.json.{key}",
                    "expected": expected,
                    "actual": profile_metadata.get(key),
                }
            )

    return {
        "ok": (
            not invalid_required
            and not missing_outputs
            and not profile_metadata_mismatches
        ),
        "required_outputs": required_outputs,
        "matched_outputs": matched_outputs,
        "missing_outputs": missing_outputs,
        "invalid_required_outputs": invalid_required,
        "source_paths": source_paths,
        "parsed_endpoint_counts": {
            source: len(endpoints) for source, endpoints in endpoints_by_source.items()
        },
        "profile_metadata": profile_metadata,
        "profile_metadata_mismatches": profile_metadata_mismatches,
        "validation": "structured_endpoint_objects",
    }


def semantic_stack_checks(
    plan: dict[str, Any],
    probe_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    route_check = mavlink_anywhere_endpoint_check(
        plan, probe_results
    )
    checks["mavlink_anywhere_required_outputs"] = route_check
    checks["mavlink_anywhere_compatibility"] = mavlink_anywhere_compatibility_check(
        plan,
        probe_results,
        route_check,
    )

    config_payload = result_payload(probe_results, "probes/pixeagle_current_config.json")
    runtime_config = {}
    if isinstance(config_payload.get("json"), dict):
        runtime_config = config_payload["json"].get("config") or {}
    required_config = plan["stack"]["pixeagle"].get("required_config", {})
    config_mismatches = []
    for dotted_path, expected in required_config.items():
        actual = get_nested(runtime_config, dotted_path)
        if actual != expected:
            config_mismatches.append(
                {
                    "path": dotted_path,
                    "expected": expected,
                    "actual": actual,
                }
            )
    checks["pixeagle_required_config"] = {
        "ok": not config_mismatches,
        "required_config": required_config,
        "mismatches": config_mismatches,
    }

    return checks


def scenario_target_base_urls(plan: dict[str, Any]) -> dict[str, str]:
    return {
        "pixeagle": plan["stack"]["pixeagle"]["base_url"].rstrip("/"),
        "mavlink2rest": plan["stack"]["mavlink2rest"]["url"].rstrip("/"),
        "mavlink_anywhere": plan["stack"]["routing"]["dashboard_url"].rstrip("/"),
    }


def is_control_action(action: dict[str, Any]) -> bool:
    if bool(action.get("control_action")):
        return True
    if action.get("type") == "http_request":
        return str(action.get("method", "GET")).upper() != "GET"
    return False


def normalize_expected_status(action: dict[str, Any]) -> set[int] | None:
    expected = action.get("expect_status")
    if expected is None:
        return None
    if isinstance(expected, int):
        return {expected}
    if isinstance(expected, list) and all(isinstance(item, int) for item in expected):
        return set(expected)
    return set()


def evaluate_json_expectations(payload: dict[str, Any], expectations: list[Any]) -> list[dict[str, Any]]:
    results = []
    json_payload = payload.get("json")
    for expectation in expectations:
        if not isinstance(expectation, dict):
            results.append(
                {
                    "ok": False,
                    "reason": "Expectation must be an object.",
                    "expectation": expectation,
                }
            )
            continue
        path = expectation.get("path")
        if not isinstance(path, str) or not path:
            results.append(
                {
                    "ok": False,
                    "reason": "Expectation path must be a non-empty string.",
                    "expectation": expectation,
                }
            )
            continue
        actual = get_nested(json_payload, path) if isinstance(json_payload, dict) else None
        if "equals" in expectation:
            expected = expectation["equals"]
            ok = actual == expected
            results.append(
                {
                    "ok": ok,
                    "path": path,
                    "operator": "equals",
                    "expected": expected,
                    "actual": actual,
                }
            )
        elif expectation.get("exists") is True:
            ok = actual is not None
            results.append(
                {
                    "ok": ok,
                    "path": path,
                    "operator": "exists",
                    "actual": actual,
                }
            )
        elif expectation.get("is_finite") is True:
            ok = isinstance(actual, (int, float)) and math.isfinite(float(actual))
            results.append(
                {
                    "ok": ok,
                    "path": path,
                    "operator": "is_finite",
                    "actual": actual,
                }
            )
        elif "greater_than_or_equal" in expectation:
            expected = expectation["greater_than_or_equal"]
            ok = (
                isinstance(actual, (int, float))
                and isinstance(expected, (int, float))
                and actual >= expected
            )
            results.append(
                {
                    "ok": ok,
                    "path": path,
                    "operator": "greater_than_or_equal",
                    "expected": expected,
                    "actual": actual,
                }
            )
        elif "less_than_or_equal" in expectation:
            expected = expectation["less_than_or_equal"]
            ok = (
                isinstance(actual, (int, float))
                and isinstance(expected, (int, float))
                and actual <= expected
            )
            results.append(
                {
                    "ok": ok,
                    "path": path,
                    "operator": "less_than_or_equal",
                    "expected": expected,
                    "actual": actual,
                }
            )
        else:
            results.append(
                {
                    "ok": False,
                    "path": path,
                    "reason": (
                        "Unsupported expectation. Use equals, exists=true, "
                        "is_finite=true, greater_than_or_equal, or less_than_or_equal."
                    ),
                    "expectation": expectation,
                }
            )
    return results


def summarize_scenario_actions(plan: dict[str, Any]) -> dict[str, Any]:
    scenarios = []
    total_actions = 0
    control_actions = 0
    manual_fault_actions = 0
    for scenario in plan["scenarios"]:
        action_summaries = []
        for action in scenario.get("actions", []):
            total_actions += 1
            control = is_control_action(action)
            control_actions += 1 if control else 0
            manual_fault_actions += 1 if action.get("type") == "manual_fault" else 0
            action_summaries.append(
                {
                    "id": action["id"],
                    "type": action["type"],
                    "control_action": control,
                    "target": action.get("target"),
                    "method": action.get("method"),
                    "path": action.get("path"),
                }
            )
        scenarios.append(
            {
                "id": scenario["id"],
                "title": scenario["title"],
                "actions": action_summaries,
            }
        )
    return {
        "scenario_count": len(scenarios),
        "total_actions": total_actions,
        "control_actions": control_actions,
        "manual_fault_actions": manual_fault_actions,
        "scenarios": scenarios,
    }


def execute_scenario_actions(
    plan: dict[str, Any],
    run_dir: Path,
    timeout_s: float,
    allow_control_actions: bool,
) -> dict[str, Any]:
    base_urls = scenario_target_base_urls(plan)
    started_at = utc_now()
    scenario_results = []
    summary = {
        "result": "pass",
        "scenario_count": 0,
        "passed_scenarios": 0,
        "incomplete_scenarios": 0,
        "failed_scenarios": 0,
        "blocked_actions": 0,
        "failed_actions": 0,
        "manual_fault_actions": 0,
        "control_actions_allowed": allow_control_actions,
    }

    for scenario in plan["scenarios"]:
        scenario_result = {
            "id": scenario["id"],
            "title": scenario["title"],
            "started_at": utc_now().isoformat(),
            "actions": [],
            "result": "pass",
        }
        for action in scenario.get("actions", []):
            action_result: dict[str, Any] = {
                "id": action["id"],
                "type": action["type"],
                "control_action": is_control_action(action),
                "started_at": utc_now().isoformat(),
            }

            if action["type"] == "operator_note":
                action_result.update(
                    {
                        "result": "recorded",
                        "description": action["description"],
                    }
                )
            elif action["type"] == "manual_fault":
                summary["manual_fault_actions"] += 1
                summary["blocked_actions"] += 1
                action_result.update(
                    {
                        "result": "blocked",
                        "description": action["description"],
                        "reason": (
                            "Manual fault action is documented but not yet automated; "
                            "PXE-0037 cannot pass accepted SITL evidence until this "
                            "action has an automated executor or explicit evidence import."
                        ),
                    }
                )
            elif action["type"] == "wait":
                seconds = float(action["seconds"])
                time.sleep(seconds)
                action_result.update(
                    {
                        "result": "pass",
                        "seconds": seconds,
                    }
                )
            elif action["type"] == "http_request":
                if action_result["control_action"] and not allow_control_actions:
                    summary["blocked_actions"] += 1
                    action_result.update(
                        {
                            "result": "blocked",
                            "reason": (
                                "Control action was not executed because "
                                "--allow-control-actions was not provided."
                            ),
                            "method": str(action["method"]).upper(),
                            "target": action["target"],
                            "path": action["path"],
                        }
                    )
                else:
                    method = str(action["method"]).upper()
                    url = f"{base_urls[action['target']]}{action['path']}"
                    response = http_request_json(
                        url,
                        method=method,
                        json_body=action.get("json_body"),
                        timeout_s=timeout_s,
                    )
                    expected_status = normalize_expected_status(action)
                    if expected_status is None:
                        status_ok = bool(response.get("ok"))
                    else:
                        status_ok = response.get("status") in expected_status
                    expectation_results = evaluate_json_expectations(
                        response,
                        action.get("expect_json", []),
                    )
                    expectations_ok = all(item.get("ok") for item in expectation_results)
                    action_ok = status_ok and expectations_ok
                    if not action_ok:
                        summary["failed_actions"] += 1
                    action_result.update(
                        {
                            "result": "pass" if action_ok else "failed",
                            "method": method,
                            "target": action["target"],
                            "path": action["path"],
                            "url": url,
                            "expected_status": sorted(expected_status) if expected_status else None,
                            "status_ok": status_ok,
                            "json_expectations": expectation_results,
                            "response": response,
                        }
                    )
            else:
                summary["failed_actions"] += 1
                action_result.update(
                    {
                        "result": "failed",
                        "reason": f"Unsupported action type: {action['type']}",
                    }
                )

            action_result["finished_at"] = utc_now().isoformat()
            scenario_result["actions"].append(action_result)

        action_results = {action["result"] for action in scenario_result["actions"]}
        if "failed" in action_results:
            scenario_result["result"] = "failed"
            summary["failed_scenarios"] += 1
        elif "blocked" in action_results:
            scenario_result["result"] = "incomplete"
            summary["incomplete_scenarios"] += 1
        else:
            scenario_result["result"] = "pass"
            summary["passed_scenarios"] += 1
        scenario_result["finished_at"] = utc_now().isoformat()
        scenario_results.append(scenario_result)
        summary["scenario_count"] += 1

    if summary["failed_scenarios"] or summary["failed_actions"]:
        summary["result"] = "failed"
    elif summary["incomplete_scenarios"] or summary["blocked_actions"]:
        summary["result"] = "incomplete"

    payload = {
        "schema_version": 1,
        "generated_at": utc_now().isoformat(),
        "started_at": started_at.isoformat(),
        "finished_at": utc_now().isoformat(),
        "claim_boundary": (
            "Scenario execution evidence applies only to this SITL stack, "
            "plan, commands, and artifact directory."
        ),
        "summary": summary,
        "scenarios": scenario_results,
    }
    write_json(run_dir / "scenarios" / "scenario_results.json", payload)
    return payload


def collect_probe_artifacts(
    plan: dict[str, Any],
    run_dir: Path,
    manifest: dict[str, Any],
    timeout_s: float,
    *,
    px4_params_file: str | None = None,
    px4_ulog_files: list[str] | None = None,
    px4_tlog_files: list[str] | None = None,
    px4_image_override: str | None = None,
    px4_container_name: str | None = None,
    px4_container_id: str | None = None,
    auto_px4_container_artifacts: bool = False,
    px4_log_file: str | None = None,
    pixeagle_log_file: str | None = None,
    generated_receiver_proof_manifest_file: str | None = None,
    gazebo_receiver_pipeline_file: str | None = None,
    gazebo_frame_hashes_file: str | None = None,
    tracker_command_trace_file: str | None = None,
    offboard_publish_trace_file: str | None = None,
) -> bool:
    harness_log = run_dir / "logs" / "harness.log"
    ensure_dir(harness_log.parent)
    harness_log.write_text(
        f"PixEagle SITL {manifest['mode']} run started {utc_now().isoformat()}\n",
        encoding="utf-8",
    )

    artifact_status: dict[str, dict[str, Any]] = {}

    write_json(run_dir / "versions" / "git.json", current_git_metadata())
    artifact_status["versions/git.json"] = {"collected": True, "placeholder": False}
    write_json(run_dir / "versions" / "runtime.json", runtime_metadata())
    artifact_status["versions/runtime.json"] = {"collected": True, "placeholder": False}

    for source, relative_path in (
        (
            PROJECT_ROOT / "configs" / "config_default.yaml",
            "config/config_default.yaml",
        ),
        (
            PROJECT_ROOT / "configs" / "config_schema.yaml",
            "config/config_schema.yaml",
        ),
        (
            PROJECT_ROOT / "configs" / "config.yaml",
            "config/config.yaml",
        ),
    ):
        copied = copy_if_exists(source, run_dir / relative_path)
        artifact_status[relative_path] = {
            "collected": copied,
            "placeholder": not copied,
            "reason": None if copied else f"Source file missing: {source}",
        }

    pixeagle_base = plan["stack"]["pixeagle"]["base_url"].rstrip("/")
    mavlink2rest_base = plan["stack"]["mavlink2rest"]["url"].rstrip("/")
    mavlink_anywhere_base = plan["stack"]["routing"]["dashboard_url"].rstrip("/")

    probes = {
        "probes/pixeagle_status.json": f"{pixeagle_base}/status",
        "probes/pixeagle_follower_setpoints_status.json": f"{pixeagle_base}/api/follower/setpoints-status",
        "probes/pixeagle_current_config.json": f"{pixeagle_base}/api/config/current",
        "probes/mavlink2rest_mavlink.json": f"{mavlink2rest_base}/v1/mavlink",
        "route_map/mavlink_anywhere_status.json": f"{mavlink_anywhere_base}/api/v1/status",
        "route_map/mavlink_anywhere_diagnostics.json": f"{mavlink_anywhere_base}/api/v1/diagnostics",
        "route_map/mavlink_anywhere_endpoints.json": f"{mavlink_anywhere_base}/api/v1/endpoints",
        "route_map/mavlink_anywhere_profiles_summary.json": f"{mavlink_anywhere_base}/api/v1/profiles/summary",
        "route_map/mavlink_anywhere_config.json": f"{mavlink_anywhere_base}/api/v1/config",
    }

    probe_results: dict[str, dict[str, Any]] = {}
    for relative_path, url in probes.items():
        result = http_get_json(url, timeout_s=timeout_s)
        write_json(run_dir / relative_path, result)
        artifact_status[relative_path] = {
            "collected": bool(result.get("ok")),
            "placeholder": False,
            "reason": result.get("error"),
        }
        probe_results[relative_path] = {
            "url": url,
            "ok": bool(result.get("ok")),
            "status": result.get("status"),
            "error": result.get("error"),
            "raw": result,
        }

    dashboard_version_evidence = mavlink_anywhere_dashboard_version_evidence(
        plan,
        probe_results,
    )
    write_json(
        run_dir / "versions" / "mavlink_anywhere_dashboard.json",
        dashboard_version_evidence,
    )
    artifact_status["versions/mavlink_anywhere_dashboard.json"] = {
        "collected": bool(dashboard_version_evidence.get("collected")),
        "placeholder": False,
        "reason": (
            None
            if dashboard_version_evidence.get("collected")
            else "MavlinkAnywhere dashboard version could not be collected from /api/v1/status."
        ),
    }

    px4_container_ref = px4_container_id or px4_container_name
    px4_artifact_collection_mode = None
    if auto_px4_container_artifacts and px4_container_ref:
        px4_artifact_collection_mode = (
            "harness_owned_container"
            if manifest.get("mode") == "execute" and px4_container_id
            else "operator_selected_container"
        )
    manifest["px4_artifact_collection"] = {
        "auto_container_artifacts": bool(auto_px4_container_artifacts),
        "container_ref": px4_container_ref,
        "collection_mode": px4_artifact_collection_mode,
        "explicit_imports": {
            "params_file": bool(px4_params_file),
            "ulog_count": len(px4_ulog_files or []),
            "tlog_count": len(px4_tlog_files or []),
            "px4_log": bool(px4_log_file),
            "pixeagle_log": bool(pixeagle_log_file),
            "generated_receiver_proof_manifest": bool(
                generated_receiver_proof_manifest_file
            ),
            "gazebo_receiver_pipeline": bool(gazebo_receiver_pipeline_file),
            "gazebo_frame_hashes": bool(gazebo_frame_hashes_file),
            "tracker_command_trace": bool(tracker_command_trace_file),
            "offboard_publish_trace": bool(offboard_publish_trace_file),
        },
    }

    artifact_status["px4/params.txt"] = collect_px4_params_artifact(
        run_dir,
        plan,
        px4_params_file,
        container_ref=px4_container_ref,
        auto_container_artifacts=auto_px4_container_artifacts,
        timeout_s=timeout_s,
    )
    artifact_status["px4/ulog_manifest.json"] = collect_px4_log_manifest(
        run_dir,
        plan,
        kind="ulog",
        input_files=px4_ulog_files or [],
        container_ref=px4_container_ref,
        auto_container_artifacts=auto_px4_container_artifacts,
        timeout_s=timeout_s,
    )
    artifact_status["px4/tlog_manifest.json"] = collect_px4_log_manifest(
        run_dir,
        plan,
        kind="tlog",
        input_files=px4_tlog_files or [],
        container_ref=px4_container_ref,
        auto_container_artifacts=auto_px4_container_artifacts,
        timeout_s=timeout_s,
    )
    artifact_status["px4/offboard_observation.json"] = (
        collect_px4_offboard_observation_artifact(run_dir, probe_results)
    )
    artifact_status["px4/container_metadata.json"] = collect_px4_container_metadata(
        plan,
        run_dir,
        image_override=px4_image_override,
        container_name=px4_container_name,
        container_id=px4_container_id,
    )
    artifact_status["logs/px4_sitl.log"] = collect_log_artifact(
        run_dir,
        relative_path="logs/px4_sitl.log",
        log_file=px4_log_file,
        existing_source="harness_owned_px4_container_stdout",
    )
    artifact_status["logs/pixeagle.log"] = collect_log_artifact(
        run_dir,
        relative_path="logs/pixeagle.log",
        log_file=pixeagle_log_file,
    )
    visual_inputs = {
        GAZEBO_VISUAL_EVIDENCE_PATHS["generated_receiver_proof_manifest"]: (
            generated_receiver_proof_manifest_file,
            "Generated RTP/UDP receiver proof manifest",
        ),
        GAZEBO_VISUAL_EVIDENCE_PATHS["gazebo_receiver_pipeline"]: (
            gazebo_receiver_pipeline_file,
            "Gazebo RTP/H.264 receiver pipeline",
        ),
        GAZEBO_VISUAL_EVIDENCE_PATHS["gazebo_frame_hashes"]: (
            gazebo_frame_hashes_file,
            "Gazebo decoded frame hash evidence",
        ),
        GAZEBO_VISUAL_EVIDENCE_PATHS["tracker_command_trace"]: (
            tracker_command_trace_file,
            "Tracker command trace JSONL",
        ),
        GAZEBO_VISUAL_EVIDENCE_PATHS["offboard_publish_trace"]: (
            offboard_publish_trace_file,
            "Offboard publish trace JSONL",
        ),
    }
    if plan_requires_gazebo_visual_evidence(plan) or any(
        input_file for input_file, _description in visual_inputs.values()
    ):
        for relative_path, (input_file, description) in visual_inputs.items():
            artifact_status[relative_path] = collect_named_artifact(
                run_dir,
                relative_path=relative_path,
                input_file=input_file,
                description=description,
            )

    secret_scan = scan_evidence_artifacts_for_secrets(run_dir)
    artifact_status["security/secret_scan.json"] = {
        "collected": True,
        "placeholder": False,
        "reason": None if secret_scan.get("ok") else "Evidence secret scan blocked this artifact set.",
    }

    missing_or_placeholder_artifacts = []
    for relative_path in plan["evidence_contract"]:
        artifact_path = run_dir / relative_path
        status = artifact_status.get(relative_path)
        if not artifact_path.exists():
            reason = "Artifact was required by the plan but this run did not create it."
            if artifact_path.suffix in {".log", ".txt"}:
                write_placeholder_text(artifact_path, reason)
            else:
                write_placeholder_json(artifact_path, reason)
            status = {
                "collected": False,
                "placeholder": True,
                "reason": reason,
            }
            artifact_status[relative_path] = status
        elif status is None:
            artifact_status[relative_path] = {
                "collected": True,
                "placeholder": False,
                "reason": None,
            }
            continue

        if status and (not status.get("collected") or status.get("placeholder")):
            missing_or_placeholder_artifacts.append(relative_path)

    semantic_checks = semantic_stack_checks(plan, probe_results)
    semantic_failures = [
        name for name, status in semantic_checks.items() if not status.get("ok")
    ]
    content_checks = artifact_content_checks(plan, run_dir)
    content_failures = [
        name for name, status in content_checks.items() if not status.get("ok")
    ]

    manifest["probe_results"] = {
        key: {field: value for field, value in result.items() if field != "raw"}
        for key, result in probe_results.items()
    }
    manifest["artifact_status"] = artifact_status
    manifest["missing_or_placeholder_artifacts"] = missing_or_placeholder_artifacts
    manifest["semantic_checks"] = semantic_checks
    manifest["semantic_failures"] = semantic_failures
    manifest["artifact_content_checks"] = content_checks
    manifest["artifact_content_failures"] = content_failures
    all_core_probes_ok = all(
        probe_results[path]["ok"]
        for path in (
            "probes/pixeagle_status.json",
            "probes/pixeagle_current_config.json",
            "probes/mavlink2rest_mavlink.json",
            "route_map/mavlink_anywhere_status.json",
            "route_map/mavlink_anywhere_diagnostics.json",
            "route_map/mavlink_anywhere_endpoints.json",
            "route_map/mavlink_anywhere_profiles_summary.json",
            "route_map/mavlink_anywhere_config.json",
        )
    )
    complete_artifacts = not missing_or_placeholder_artifacts
    semantic_ok = not semantic_failures
    content_ok = not content_failures
    ok = all_core_probes_ok and complete_artifacts and semantic_ok and content_ok

    if ok:
        manifest["result"] = "pass"
        manifest["result_reason"] = (
            "Core probes, required artifacts, route/config semantic checks, and artifact content checks succeeded."
        )
    elif not all_core_probes_ok:
        manifest["result"] = "incomplete"
        manifest["result_reason"] = (
            "One or more core runtime probes failed; inspect probe artifacts."
        )
    elif not complete_artifacts:
        manifest["result"] = "incomplete"
        manifest["result_reason"] = (
            "One or more required artifacts are missing or placeholders; this is not accepted SITL evidence."
        )
    else:
        manifest["result"] = "incomplete"
        if not semantic_ok:
            manifest["result_reason"] = (
                "Route/config semantic checks failed; the running stack does not match the plan."
            )
        else:
            manifest["result_reason"] = (
                "Required artifact content checks failed; this is not accepted SITL evidence."
            )
    harness_log.write_text(
        harness_log.read_text(encoding="utf-8")
        + f"Run finished {utc_now().isoformat()} with {manifest['result']}\n",
        encoding="utf-8",
    )
    return ok


def build_summary(plan: dict[str, Any], source: Path) -> dict[str, Any]:
    scenario_ids = [scenario["id"] for scenario in plan["scenarios"]]
    tags = set(plan.get("tags") or [])
    phase2_required_applicable = "phase2" in tags or plan["name"] == "phase2_follower_validation"
    return {
        "plan": {
            "name": plan["name"],
            "title": plan["title"],
            "level": plan["level"],
            "source": str(source.relative_to(PROJECT_ROOT) if source.is_relative_to(PROJECT_ROOT) else source),
            "hash": plan_hash(plan),
        },
        "scenarios": scenario_ids,
        "required_phase2_applicable": phase2_required_applicable,
        "required_phase2_scenarios_present": sorted(
            REQUIRED_PHASE2_SCENARIOS.intersection(scenario_ids)
            if phase2_required_applicable
            else []
        ),
        "required_phase2_scenarios_missing": sorted(
            REQUIRED_PHASE2_SCENARIOS - set(scenario_ids)
            if phase2_required_applicable
            else []
        ),
        "evidence_contract": plan["evidence_contract"],
        "sidecar_compatibility_policy": (
            {
                "routing_provider": plan["stack"]["routing"].get("provider"),
                "policy": mavlink_anywhere_policy(plan),
            }
            if plan["stack"]["routing"].get("provider") == "mavlink-anywhere"
            else None
        ),
    }


def list_plans(as_json: bool) -> int:
    plans = []
    for path in plan_files():
        plan = load_plan(path)
        plans.append(build_summary(plan, path))
    if as_json:
        print(json_dumps(plans), end="")
    else:
        for item in plans:
            plan = item["plan"]
            missing = item["required_phase2_scenarios_missing"]
            status = "complete" if not missing else f"missing: {', '.join(missing)}"
            print(f"{plan['name']}: {plan['title']} [{status}]")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate PixEagle PX4/SITL plans and collect evidence probes."
    )
    parser.add_argument("--list-plans", action="store_true", help="List checked-in plans")
    parser.add_argument("--plan-name", help="Plan name under tools/sitl_plans without .json")
    parser.add_argument("--plan-file", help="Explicit plan JSON path")
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    parser.add_argument("--run-id", help="Override artifact run id")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--run-scenarios",
        action="store_true",
        help=(
            "Execute checked-in scenario actions against the running stack and "
            "write scenarios/scenario_results.json."
        ),
    )
    parser.add_argument(
        "--allow-control-actions",
        action="store_true",
        help=(
            "Allow scenario actions that can mutate PixEagle/PX4 state. Without "
            "this flag, non-GET/control actions are recorded as blocked."
        ),
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate only; no artifacts")
    mode.add_argument(
        "--probe-only",
        action="store_true",
        help="Collect probes from an already running stack; do not start services",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Start a managed PX4 SITL container, collect probes, then stop it",
    )
    parser.add_argument(
        "--allow-process-start",
        action="store_true",
        help="Required with --execute to start the PX4 SITL Docker container",
    )
    parser.add_argument("--px4-image", help="Override the plan's PX4 container image")
    parser.add_argument("--px4-model", help="Override the plan's PX4_SIM_MODEL")
    parser.add_argument(
        "--px4-container-name",
        help=(
            "Override the Docker container name in --execute, or identify an "
            "operator-managed PX4 container for probe-only metadata collection."
        ),
    )
    parser.add_argument(
        "--px4-container-id",
        help=(
            "Identify an operator-managed PX4 container by id/name for "
            "probe-only metadata collection; never stopped by the harness."
        ),
    )
    parser.add_argument(
        "--auto-px4-container-artifacts",
        action="store_true",
        help=(
            "Best-effort read-only PX4 params/ULog/tlog discovery using "
            "docker exec/find plus docker cp. In probe-only this requires "
            "--px4-container-name or --px4-container-id; in --execute it is "
            "enabled only after harness-owned container labels are verified."
        ),
    )
    parser.add_argument(
        "--px4-params-file",
        help="Import an exported PX4 params.txt into the evidence directory",
    )
    parser.add_argument(
        "--px4-ulog",
        action="append",
        default=[],
        help="Import a PX4 .ulg file into px4/ulog_manifest.json; repeatable",
    )
    parser.add_argument(
        "--px4-tlog",
        action="append",
        default=[],
        help="Import a MAVLink telemetry .tlog file into px4/tlog_manifest.json; repeatable",
    )
    parser.add_argument(
        "--px4-log",
        help="Import a PX4 SITL stdout/log file into logs/px4_sitl.log for probe-only evidence",
    )
    parser.add_argument(
        "--pixeagle-log",
        help="Import a PixEagle backend log file into logs/pixeagle.log for accepted evidence",
    )
    parser.add_argument(
        "--generated-receiver-proof-manifest",
        help=(
            "Import the generated RTP/UDP receiver proof manifest into "
            "video/generated_receiver_proof_manifest.json"
        ),
    )
    parser.add_argument(
        "--gazebo-receiver-pipeline",
        help="Import the Gazebo RTP/H.264 receiver pipeline text artifact",
    )
    parser.add_argument(
        "--gazebo-frame-hashes",
        help="Import decoded Gazebo frame hashes into video/gazebo_frame_hashes.json",
    )
    parser.add_argument(
        "--tracker-command-trace",
        help="Import tracker/follower command trace JSONL into trace/tracker_command_trace.jsonl",
    )
    parser.add_argument(
        "--offboard-publish-trace",
        help="Import Offboard publication trace JSONL into trace/offboard_publish_trace.jsonl",
    )
    parser.add_argument(
        "--startup-wait-s",
        type=float,
        default=15.0,
        help="Seconds to wait after starting PX4 before collecting probes",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    try:
        if args.list_plans:
            return list_plans(args.json)

        source = resolve_plan(args.plan_name, args.plan_file)
        plan = load_plan(source)
        summary = build_summary(plan, source)

        if args.execute and not args.allow_process_start:
            print("--execute requires --allow-process-start", file=sys.stderr)
            return 2

        if args.execute and args.px4_container_id:
            print(
                "--px4-container-id identifies an existing operator-managed container "
                "and cannot be combined with --execute",
                file=sys.stderr,
            )
            return 2

        if args.probe_only and args.px4_container_name and args.px4_container_id:
            print(
                "Use only one PX4 container selector in probe-only: "
                "--px4-container-name or --px4-container-id",
                file=sys.stderr,
            )
            return 2

        if (
            args.probe_only
            and args.auto_px4_container_artifacts
            and not (args.px4_container_name or args.px4_container_id)
        ):
            print(
                "--probe-only --auto-px4-container-artifacts requires "
                "--px4-container-name or --px4-container-id",
                file=sys.stderr,
            )
            return 2

        if args.probe_only or args.execute:
            artifact_root = Path(args.artifact_root)
            if not artifact_root.is_absolute():
                artifact_root = PROJECT_ROOT / artifact_root
            run_dir = create_run_dir(artifact_root, plan["name"], args.run_id)
            if run_dir.exists():
                print(
                    f"Artifact directory already exists, refusing to reuse evidence: {run_dir}",
                    file=sys.stderr,
                )
                return 2
            ensure_dir(run_dir)
            write_json(run_dir / "plan.json", plan)
            mode_name = "execute" if args.execute else "probe_only"
            manifest = {
                "schema_version": 1,
                "run_id": run_dir.name,
                "mode": mode_name,
                "started_at": utc_now().isoformat(),
                "plan": summary["plan"],
                "scenario_ids": summary["scenarios"],
                "required_phase2_scenarios_missing": summary[
                    "required_phase2_scenarios_missing"
                ],
                "artifact_dir": str(run_dir),
                "operator_claim_boundary": (
                    f"{mode_name} SITL evidence does not imply HIL, field, or real-aircraft success."
                ),
                "scenario_execution": {
                    "enabled": bool(args.run_scenarios),
                    "control_actions_allowed": bool(args.allow_control_actions),
                    "artifact": "scenarios/scenario_results.json",
                },
            }
            write_manifest(run_dir / "manifest.json", manifest)

            px4_process: subprocess.Popen[Any] | None = None
            px4_log_capture: ManagedPx4LogCapture | None = None
            px4_container_name = args.px4_container_name if args.probe_only else None
            px4_container_id: str | None = args.px4_container_id if args.probe_only else None
            ok = False
            try:
                if args.execute:
                    px4_container_name, px4_command = build_px4_container_command(
                        plan,
                        run_dir.name,
                        args.px4_image,
                        args.px4_model,
                        args.px4_container_name,
                    )
                    manifest["managed_processes"] = {
                        "px4": {
                            "container_name": px4_container_name,
                            "command": px4_command,
                            "startup_wait_s": args.startup_wait_s,
                        }
                    }
                    write_manifest(run_dir / "manifest.json", manifest)
                    px4_process, px4_log_capture = start_px4_container(
                        px4_container_name,
                        px4_command,
                        run_dir,
                    )
                    manifest["managed_processes"]["px4"]["pid"] = px4_process.pid
                    write_manifest(run_dir / "manifest.json", manifest)
                    time.sleep(max(0.0, args.startup_wait_s))
                    px4_container_id = owned_px4_container_id(
                        px4_container_name,
                        run_dir.name,
                    )
                    manifest["managed_processes"]["px4"][
                        "verified_container_id"
                    ] = px4_container_id
                    startup_returncode = px4_process.poll()
                    manifest["managed_processes"]["px4"][
                        "returncode_after_startup_wait"
                    ] = startup_returncode
                    if px4_container_id is None:
                        manifest.setdefault("preflight_failures", []).append(
                            "PX4 SITL container ownership could not be verified by label."
                        )
                    if startup_returncode is not None:
                        manifest.setdefault("preflight_failures", []).append(
                            "PX4 SITL container exited before probes were collected."
                        )
                    write_manifest(run_dir / "manifest.json", manifest)

                scenario_payload = None
                if args.run_scenarios:
                    scenario_payload = execute_scenario_actions(
                        plan,
                        run_dir,
                        args.timeout_s,
                        args.allow_control_actions,
                    )
                    manifest["scenario_execution"] = {
                        "enabled": True,
                        "control_actions_allowed": bool(args.allow_control_actions),
                        "artifact": "scenarios/scenario_results.json",
                        "summary": scenario_payload["summary"],
                    }
                    write_manifest(run_dir / "manifest.json", manifest)

                auto_collect_px4_container_artifacts = (
                    should_auto_collect_px4_container_artifacts(
                        execute_mode=bool(args.execute),
                        probe_only_mode=bool(args.probe_only),
                        requested_auto_collection=bool(args.auto_px4_container_artifacts),
                        px4_container_id=px4_container_id,
                        px4_container_name=px4_container_name,
                    )
                )

                ok = collect_probe_artifacts(
                    plan,
                    run_dir,
                    manifest,
                    args.timeout_s,
                    px4_params_file=args.px4_params_file,
                    px4_ulog_files=args.px4_ulog,
                    px4_tlog_files=args.px4_tlog,
                    px4_image_override=args.px4_image,
                    px4_container_name=px4_container_name,
                    px4_container_id=px4_container_id,
                    auto_px4_container_artifacts=auto_collect_px4_container_artifacts,
                    px4_log_file=args.px4_log,
                    pixeagle_log_file=args.pixeagle_log,
                    generated_receiver_proof_manifest_file=(
                        args.generated_receiver_proof_manifest
                    ),
                    gazebo_receiver_pipeline_file=args.gazebo_receiver_pipeline,
                    gazebo_frame_hashes_file=args.gazebo_frame_hashes,
                    tracker_command_trace_file=args.tracker_command_trace,
                    offboard_publish_trace_file=args.offboard_publish_trace,
                )
                if manifest.get("preflight_failures") and ok:
                    manifest["result"] = "incomplete"
                    manifest["result_reason"] = (
                        "Managed PX4 process preflight failed; inspect managed_processes."
                    )
                    ok = False
                if scenario_payload:
                    scenario_result = scenario_payload["summary"]["result"]
                    if scenario_result == "failed":
                        manifest["result"] = "failed"
                        manifest["result_reason"] = (
                            "One or more scenario actions failed; inspect "
                            "scenarios/scenario_results.json. Scenario failures "
                            "take precedence over incomplete artifacts."
                        )
                        ok = False
                    elif scenario_result != "pass" and ok:
                        manifest["result"] = "incomplete"
                        manifest["result_reason"] = (
                            "Scenario execution actions did not all pass; inspect "
                            "scenarios/scenario_results.json."
                        )
                        ok = False
            except FileNotFoundError as exc:
                manifest["result"] = "failed"
                manifest["result_reason"] = str(exc)
                ok = False
            except RuntimeError as exc:
                manifest["result"] = "failed"
                manifest["result_reason"] = str(exc)
                ok = False
            finally:
                if args.execute and px4_container_name:
                    manifest.setdefault("managed_processes", {}).setdefault("px4", {})[
                        "stop_result"
                    ] = stop_px4_container(px4_container_id, px4_process)
                if px4_log_capture is not None:
                    capture_status = px4_log_capture.close()
                    manifest.setdefault("managed_processes", {}).setdefault("px4", {})[
                        "stdout_log_capture"
                    ] = capture_status
                    if capture_status.get("ok") is True:
                        log_status = collect_log_artifact(
                            run_dir,
                            relative_path="logs/px4_sitl.log",
                            log_file=None,
                            existing_source="harness_owned_px4_container_stdout",
                        )
                    else:
                        reason = "Managed PX4 stdout capture did not finish cleanly."
                        if capture_status.get("reader_error"):
                            reason += f" reader_error={capture_status['reader_error']}"
                        if capture_status.get("thread_finished") is False:
                            reason += " reader thread did not finish before timeout."
                        target = run_dir / "logs" / "px4_sitl.log"
                        log_status = {
                            "collected": False,
                            "placeholder": False,
                            "reason": reason,
                            "collection_source": "harness_owned_px4_container_stdout",
                        }
                        if target.exists() and target.is_file():
                            log_status["artifact"] = evidence_entry(
                                "harness_owned_px4_container_stdout",
                                target,
                                run_dir,
                            )
                        manifest.setdefault("preflight_failures", []).append(reason)
                        missing = manifest.setdefault("missing_or_placeholder_artifacts", [])
                        if "logs/px4_sitl.log" not in missing:
                            missing.append("logs/px4_sitl.log")
                        if manifest.get("result") != "failed":
                            manifest["result"] = "incomplete"
                            manifest["result_reason"] = reason
                        ok = False
                    manifest.setdefault("artifact_status", {})[
                        "logs/px4_sitl.log"
                    ] = log_status
                manifest["finished_at"] = utc_now().isoformat()
                write_manifest(run_dir / "manifest.json", manifest)

            if args.json:
                print(json_dumps(manifest), end="")
            else:
                print(f"Evidence directory: {run_dir}")
                print(f"Result: {manifest['result']}")
            return 0 if ok else 3

        # Dry-run is the default because it has no runtime side effects.
        output = {
            "mode": "dry_run",
            "summary": summary,
            "would_create_artifact_root": str(Path(args.artifact_root)),
            "would_start_processes": False,
            "would_run_scenarios_in_runtime_mode": bool(args.run_scenarios),
            "control_actions_allowed": bool(args.allow_control_actions),
            "scenario_action_summary": summarize_scenario_actions(plan),
            "operator_claim_boundary": (
                "Dry-run validates the plan only; it is not runtime evidence."
            ),
        }
        if args.json:
            print(json_dumps(output), end="")
        else:
            print(json_dumps(output), end="")
        return 0
    except PlanError as exc:
        print(f"Plan error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
