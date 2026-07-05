#!/usr/bin/env python3
"""Generate PixEagle's non-callable API/MCP candidate inventory.

The inventory is a reviewer aid, not a runtime MCP registry. It parses FastAPI
route declarations statically so validation cannot start PixEagle subsystems.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
from pathlib import Path
import sys
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FASTAPI_HANDLER = PROJECT_ROOT / "src" / "classes" / "fastapi_handler.py"
API_V1_ROUTE_REGISTRY = (
    PROJECT_ROOT / "src" / "classes" / "fastapi_api_v1_routes.py"
)
API_V1_CONTRACTS = PROJECT_ROOT / "src" / "classes" / "api_v1_contracts.py"
API_V1_PATHS = PROJECT_ROOT / "src" / "classes" / "api_v1_paths.py"
API_V1_ACTIONS = PROJECT_ROOT / "src" / "classes" / "api_v1_actions.py"
API_V1_AUTH_ROUTES = PROJECT_ROOT / "src" / "classes" / "api_v1_auth_routes.py"
API_V1_LOG_ROUTES = PROJECT_ROOT / "src" / "classes" / "api_v1_log_routes.py"
API_LEGACY_CONTROL_ROUTES = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_control_routes.py"
)
API_LEGACY_CONFIG_SYNC = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_config_sync.py"
)
API_LEGACY_CONFIG_ROUTES = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_config_routes.py"
)
API_LEGACY_FOLLOWER_ROUTES = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_follower_routes.py"
)
API_LEGACY_GSTREAMER_ROUTES = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_gstreamer_routes.py"
)
API_LEGACY_MEDIA_ROUTES = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_media_routes.py"
)
API_LEGACY_MODEL_ROUTES = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_model_routes.py"
)
API_LEGACY_OSD_ROUTES = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_osd_routes.py"
)
API_LEGACY_RECORDING_ROUTES = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_recording_routes.py"
)
API_LEGACY_SAFETY_ROUTES = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_safety_routes.py"
)
API_LEGACY_TRACKER_ROUTES = (
    PROJECT_ROOT / "src" / "classes" / "api_legacy_tracker_routes.py"
)
WEBRTC_MANAGER = PROJECT_ROOT / "src" / "classes" / "webrtc_manager.py"
API_V1_READ_ROUTES = PROJECT_ROOT / "src" / "classes" / "api_v1_read_routes.py"
API_V1_SNAPSHOTS = PROJECT_ROOT / "src" / "classes" / "api_v1_snapshots.py"
API_V1_TELEMETRY = PROJECT_ROOT / "src" / "classes" / "api_v1_telemetry.py"
API_V1_STREAMS = PROJECT_ROOT / "src" / "classes" / "api_v1_streams.py"
API_V1_SITL = PROJECT_ROOT / "src" / "classes" / "api_v1_sitl.py"
API_EXPOSURE_POLICY = PROJECT_ROOT / "src" / "classes" / "api_exposure_policy.py"
API_AUTH_RUNTIME = PROJECT_ROOT / "src" / "classes" / "api_auth_runtime.py"
API_SECURITY_AUDIT = PROJECT_ROOT / "src" / "classes" / "api_security_audit.py"
API_SECURITY_TYPES = PROJECT_ROOT / "src" / "classes" / "api_security_types.py"
API_SECURITY_POLICY = PROJECT_ROOT / "src" / "classes" / "api_security_policy.py"
ROUTE_SOURCE_FILES = (
    FASTAPI_HANDLER,
    API_V1_ROUTE_REGISTRY,
    API_V1_CONTRACTS,
    API_V1_PATHS,
    API_V1_ACTIONS,
    API_V1_AUTH_ROUTES,
    API_V1_LOG_ROUTES,
    API_LEGACY_CONTROL_ROUTES,
    API_LEGACY_CONFIG_SYNC,
    API_LEGACY_CONFIG_ROUTES,
    API_LEGACY_FOLLOWER_ROUTES,
    API_LEGACY_GSTREAMER_ROUTES,
    API_LEGACY_MEDIA_ROUTES,
    API_LEGACY_MODEL_ROUTES,
    API_LEGACY_OSD_ROUTES,
    API_LEGACY_RECORDING_ROUTES,
    API_LEGACY_SAFETY_ROUTES,
    API_LEGACY_TRACKER_ROUTES,
    WEBRTC_MANAGER,
    API_V1_READ_ROUTES,
    API_V1_SNAPSHOTS,
    API_V1_TELEMETRY,
    API_V1_STREAMS,
    API_V1_SITL,
    API_EXPOSURE_POLICY,
    API_AUTH_RUNTIME,
    API_SECURITY_AUDIT,
    API_SECURITY_TYPES,
    API_SECURITY_POLICY,
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "docs"
    / "agent-context"
    / "generated"
    / "pixeagle-openapi-tool-candidates.yaml"
)
DEFAULT_REGISTRY = PROJECT_ROOT / "docs" / "agent-context" / "agent_tools.yaml"
DEFAULT_POLICY = PROJECT_ROOT / "docs" / "agent-context" / "agent_policy.yaml"

INVENTORY_CLAIM_BOUNDARY = (
    "Generated non-callable reviewer inventory only. This file is not an MCP "
    "tool registry, not a tools/list response, and not permission for an AI "
    "agent or client to execute any PixEagle API route. PixEagle status, "
    "telemetry, and media-health routes are process-local snapshots unless "
    "separate PX4/SITL/HIL/field evidence artifacts prove a specific scenario."
)

READ_ONLY_ELIGIBLE_PATH_NAMES = {
    "API_V1_RUNTIME_STATUS_PATH",
    "API_V1_STREAMING_MEDIA_HEALTH_PATH",
    "API_V1_FOLLOWING_STATUS_PATH",
    "API_V1_FOLLOWING_TELEMETRY_PATH",
    "API_V1_TELEMETRY_HEALTH_PATH",
    "API_V1_TRACKING_RUNTIME_STATUS_PATH",
    "API_V1_TRACKING_TELEMETRY_PATH",
}

REQUIRED_REGISTRY_METADATA = {
    "registry_stage": "docs_review_only",
    "runtime_loaded": False,
    "mcp_exposed": False,
    "default_registry_exposure": "exclude",
}

REQUIRED_POLICY_DEFAULTS = {
    "agent_enabled": False,
    "mcp_enabled": False,
    "registry_runtime_loaded": False,
    "action_circuit_breaker_enabled": True,
    "always_confirm_before_action": True,
    "allow_drone_api_exposure": False,
    "allow_px4_or_drone_api_exposure": False,
    "unknown_tool_policy": "deny",
    "allow_openapi_autopromotion": False,
    "allow_action_tools": False,
    "allow_sitl_injection_tools": False,
    "auto_promote_generated_candidates": False,
}

REQUIRED_POLICY_DENIED_RISKS = {
    "simulate",
    "operate",
    "admin",
    "destructive",
    "guarded_control_action",
    "validation_stimulus",
    "unreviewed_mutation",
}

REQUIRED_POLICY_DENIED_ROUTE_PREFIXES = {
    "/api/v1/actions/",
    "/api/v1/sitl/injections/",
}

DISPOSITION_OWNER = "pixeagle-api-governance"
DEFAULT_DISPOSITION_REVIEW_DATE = "2026-06-18"
ROUTE_DISPOSITION_REVIEW_DATES = {
    ("GET", "/api/v1/tracking/catalog"): "2026-06-30",
    ("POST", "/api/v1/actions/tracker-restart"): "2026-07-01",
    ("POST", "/api/v1/actions/tracker-switch"): "2026-07-01",
}
DISPOSITION_STATES = {
    "approved_for_review_only",
    "blocked",
    "deferred",
}
REQUIRED_POLICY_DISPOSITION_DEFAULTS = {
    "required_for_all_candidates": True,
    "completion_allows_runtime_promotion": False,
    "default_missing_disposition_policy": "deny",
    "approved_for_review_only_allows_callable": False,
    "blocked_allows_callable": False,
    "deferred_allows_callable": False,
}


def _relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


_API_V1_PATH_CONSTANTS_CACHE: dict[str, str] | None = None


def _load_string_constants(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants: dict[str, str] = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        else:
            continue

        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value.value

    return constants


def _api_v1_path_constants() -> dict[str, str]:
    global _API_V1_PATH_CONSTANTS_CACHE
    if _API_V1_PATH_CONSTANTS_CACHE is None:
        _API_V1_PATH_CONSTANTS_CACHE = _load_string_constants(API_V1_PATHS)
    return _API_V1_PATH_CONSTANTS_CACHE


def _read_only_eligible_paths() -> set[str]:
    constants = _api_v1_path_constants()
    return {constants[name] for name in READ_ONLY_ELIGIBLE_PATH_NAMES}


def _expr_to_data(node: ast.AST | None, constants: dict[str, str] | None = None) -> Any:
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if constants and node.id in constants:
            return constants[node.id]
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _expr_to_data(node.value, constants)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.List | ast.Tuple):
        return [_expr_to_data(item, constants) for item in node.elts]
    return ast.unparse(node)


def _route_handler_name(node: ast.Call) -> str | None:
    if not node.args:
        return None
    handler = node.args[0]
    if isinstance(handler, ast.Attribute):
        prefix = _expr_to_data(handler.value)
        return f"{prefix}.{handler.attr}" if prefix else handler.attr
    return _expr_to_data(handler)


def _load_fastapi_handler_tree() -> ast.Module:
    return ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))


def _load_api_v1_route_registry_tree() -> ast.Module:
    return ast.parse(API_V1_ROUTE_REGISTRY.read_text(encoding="utf-8"))


def _handler_request_models(tree: ast.Module) -> dict[str, str]:
    request_models: dict[str, str] = {}
    primitive_annotations = {
        "str",
        "int",
        "float",
        "bool",
        "dict",
        "list",
        "Any",
        "Response",
        "Request",
    }

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue

        for arg in node.args.args:
            if arg.arg == "self":
                continue
            annotation = _expr_to_data(arg.annotation)
            if not annotation or annotation in primitive_annotations:
                continue
            request_models[node.name] = annotation
            break

    return request_models


def _collect_inline_routes(
    tree: ast.Module,
    request_models: dict[str, str],
) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Call):
            continue

        route_call = node.func
        route_func = route_call.func
        if not isinstance(route_func, ast.Attribute):
            continue
        if route_func.attr not in {"get", "post", "put", "delete", "patch"}:
            continue
        if not isinstance(route_func.value, ast.Attribute):
            continue
        if route_func.value.attr != "app":
            continue
        if not route_call.args or not isinstance(route_call.args[0], ast.Constant):
            continue

        path = route_call.args[0].value
        if not isinstance(path, str):
            continue

        keywords = {keyword.arg: keyword.value for keyword in route_call.keywords}
        handler = _route_handler_name(node)
        handler_method = handler.removeprefix("self.") if handler else None
        routes.append(
            {
                "method": route_func.attr.upper(),
                "path": path,
                "operation_id": _expr_to_data(keywords.get("operation_id")),
                "tags": _expr_to_data(keywords.get("tags")) or [],
                "response_model": _expr_to_data(keywords.get("response_model")),
                "responses": _expr_to_data(keywords.get("responses")),
                "deprecated": bool(_expr_to_data(keywords.get("deprecated"))),
                "status_code": _expr_to_data(keywords.get("status_code")),
                "handler": handler,
                "request_model": (
                    request_models.get(handler_method) if handler_method else None
                ),
            }
        )

    return routes


def _collect_api_v1_route_specs(
    tree: ast.Module,
    request_models: dict[str, str],
    constants: dict[str, str],
) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []

    for node in tree.body:
        if isinstance(node, ast.Assign):
            is_route_specs = any(
                isinstance(target, ast.Name) and target.id == "API_V1_ROUTE_SPECS"
                for target in node.targets
            )
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            is_route_specs = (
                isinstance(node.target, ast.Name)
                and node.target.id == "API_V1_ROUTE_SPECS"
            )
            value = node.value
        else:
            continue

        if not is_route_specs or not isinstance(value, ast.Tuple):
            continue
        for element in value.elts:
            if not isinstance(element, ast.Call):
                continue
            keywords = {keyword.arg: keyword.value for keyword in element.keywords}
            handler_method = _expr_to_data(keywords.get("handler"))
            handler = f"self.{handler_method}" if handler_method else None
            routes.append(
                {
                    "method": str(_expr_to_data(keywords.get("method"), constants)).upper(),
                    "path": _expr_to_data(keywords.get("path"), constants),
                    "operation_id": _expr_to_data(keywords.get("operation_id"), constants),
                    "tags": _expr_to_data(keywords.get("tags"), constants) or [],
                    "response_model": _expr_to_data(
                        keywords.get("response_model"),
                        constants,
                    ),
                    "responses": _expr_to_data(keywords.get("responses"), constants),
                    "deprecated": False,
                    "status_code": _expr_to_data(keywords.get("status_code"), constants),
                    "handler": handler,
                    "request_model": (
                        request_models.get(handler_method) if handler_method else None
                    ),
                }
            )

    return routes


def collect_declared_routes() -> list[dict[str, Any]]:
    tree = _load_fastapi_handler_tree()
    registry_tree = _load_api_v1_route_registry_tree()
    api_v1_path_constants = _api_v1_path_constants()
    request_models = _handler_request_models(tree)
    routes = _collect_inline_routes(tree, request_models)
    routes.extend(
        _collect_api_v1_route_specs(
            registry_tree,
            request_models,
            api_v1_path_constants,
        )
    )

    return sorted(routes, key=lambda route: (route["path"], route["method"]))


def _candidate_id(path: str, method: str) -> str:
    route_name = (
        path.removeprefix("/api/v1/")
        .replace("/", ".")
        .replace("-", "_")
        .replace("{", "")
        .replace("}", "")
    )
    suffix = "read" if method == "GET" else "submit_candidate"
    return f"pixeagle.{route_name}.{suffix}"


def _typed_contract(route: dict[str, Any]) -> bool:
    return bool(
        route.get("operation_id")
        and route.get("response_model")
        and route.get("responses")
        and route.get("tags")
    )


def _route_key(method: str, path: str) -> tuple[str, str]:
    return (str(method).upper(), str(path))


def _sensitive_candidate_path(path: str) -> bool:
    return (
        path == "/api/v1/actions/{action_id}"
        or path.startswith("/api/v1/actions/")
        or path.startswith("/api/v1/auth/")
        or path.startswith("/api/v1/sitl/injections/")
    )


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _load_registry(path: Path = DEFAULT_REGISTRY) -> dict[str, Any]:
    payload = _load_yaml_file(path)
    tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
    return {
        "path": _relative_path(path),
        "present": path.exists(),
        "payload": payload,
        "tools": [tool for tool in tools if isinstance(tool, dict)],
    }


def _registry_route_index(
    registry: dict[str, Any],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    route_index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for tool in registry.get("tools") or []:
        route = tool.get("route") if isinstance(tool.get("route"), dict) else {}
        method = str(route.get("method") or "").upper()
        path = str(route.get("path") or "")
        if not method or not path:
            continue
        route_index.setdefault(_route_key(method, path), []).append(tool)
    return route_index


def _tool_matches_candidate(tool: dict[str, Any], candidate: dict[str, Any]) -> bool:
    route = tool.get("route") if isinstance(tool.get("route"), dict) else {}
    output_contract = (
        tool.get("output_contract")
        if isinstance(tool.get("output_contract"), dict)
        else {}
    )
    tool_disposition = (
        tool.get("review_disposition")
        if isinstance(tool.get("review_disposition"), dict)
        else {}
    )
    candidate_disposition = candidate.get("review_disposition", {})
    return all(
        [
            tool.get("id") == candidate["id"],
            tool.get("candidate_id") == candidate["id"],
            tool.get("method") == candidate["method"],
            tool.get("path") == candidate["path"],
            tool.get("operation_id") == candidate["operation_id"],
            tool.get("response_model") == candidate["response_model"],
            str(route.get("method") or "").upper() == candidate["method"],
            route.get("path") == candidate["path"],
            route.get("operation_id") == candidate["operation_id"],
            output_contract.get("response_model") == candidate["response_model"],
            tool.get("read_only") is True,
            tool.get("callable") is False,
            tool.get("mcp_exposure") == "none",
            tool.get("exposure") == "review_only",
            tool.get("default_registry_exposure") == "exclude",
            tool.get("promotion_status") == "unpromoted",
            tool.get("risk_class") == "observe",
            tool.get("candidate_risk_class") == candidate["risk_class"],
            tool.get("boundary") == "pixeagle-process-local",
            tool.get("required_role") == "viewer",
            tool.get("side_effects") == [],
            tool_disposition.get("state") == "approved_for_review_only",
            tool_disposition.get("state") == candidate_disposition.get("state"),
            tool_disposition.get("owner") == DISPOSITION_OWNER,
            bool(tool_disposition.get("reviewed_on")),
            bool(tool_disposition.get("rationale")),
            tool_disposition.get("does_not_imply_mcp_exposure") is True,
            tool_disposition.get("runtime_promotion") == "not_promoted",
        ]
    )


def _registry_matches_for_candidate(
    candidate: dict[str, Any],
    registry_index: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    matches = []
    for tool in registry_index.get(_route_key(candidate["method"], candidate["path"]), []):
        route = tool.get("route") if isinstance(tool.get("route"), dict) else {}
        matches.append(
            {
                "id": tool.get("id"),
                "candidate_id": tool.get("candidate_id"),
                "route_operation_id": route.get("operation_id"),
                "exposure": tool.get("exposure"),
                "mcp_exposure": tool.get("mcp_exposure"),
                "callable": tool.get("callable"),
                "default_registry_exposure": tool.get("default_registry_exposure"),
                "promotion_status": tool.get("promotion_status"),
                "read_only": tool.get("read_only"),
                "risk_class": tool.get("risk_class"),
                "review_disposition_state": (
                    tool.get("review_disposition", {}).get("state")
                    if isinstance(tool.get("review_disposition"), dict)
                    else None
                ),
                "valid_review_only_match": _tool_matches_candidate(tool, candidate),
            }
        )
    return matches


def _registry_metadata_problems(registry: dict[str, Any]) -> list[str]:
    payload = registry.get("payload") if isinstance(registry.get("payload"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    problems = []
    for key, expected in REQUIRED_REGISTRY_METADATA.items():
        actual = metadata.get(key)
        if actual != expected:
            problems.append(f"metadata.{key} expected {expected!r}, got {actual!r}")
    return problems


def _policy_problems(policy: dict[str, Any]) -> list[str]:
    payload = policy.get("payload") if isinstance(policy.get("payload"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    defaults = payload.get("defaults") if isinstance(payload.get("defaults"), dict) else {}
    review_disposition = (
        payload.get("review_disposition")
        if isinstance(payload.get("review_disposition"), dict)
        else {}
    )
    denied_risks = set(payload.get("denied_risks") or [])
    denied_prefixes = set(payload.get("denied_route_prefixes") or [])
    problems = []

    if metadata.get("policy_stage") != "docs_review_only":
        problems.append(
            "metadata.policy_stage expected 'docs_review_only', "
            f"got {metadata.get('policy_stage')!r}"
        )

    for key, expected in REQUIRED_POLICY_DEFAULTS.items():
        actual = defaults.get(key)
        if actual != expected:
            problems.append(f"defaults.{key} expected {expected!r}, got {actual!r}")

    missing_risks = sorted(REQUIRED_POLICY_DENIED_RISKS - denied_risks)
    if missing_risks:
        problems.append(f"denied_risks missing {missing_risks!r}")

    missing_prefixes = sorted(REQUIRED_POLICY_DENIED_ROUTE_PREFIXES - denied_prefixes)
    if missing_prefixes:
        problems.append(f"denied_route_prefixes missing {missing_prefixes!r}")

    for key, expected in REQUIRED_POLICY_DISPOSITION_DEFAULTS.items():
        actual = review_disposition.get(key)
        if actual != expected:
            problems.append(
                f"review_disposition.{key} expected {expected!r}, got {actual!r}"
            )

    valid_states = set(review_disposition.get("valid_states") or [])
    missing_states = sorted(DISPOSITION_STATES - valid_states)
    unexpected_states = sorted(valid_states - DISPOSITION_STATES)
    if missing_states:
        problems.append(f"review_disposition.valid_states missing {missing_states!r}")
    if unexpected_states:
        problems.append(
            f"review_disposition.valid_states has unexpected {unexpected_states!r}"
        )

    return problems


def _registry_tool_problems(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates_by_route = {
        _route_key(candidate["method"], candidate["path"]): candidate
        for candidate in candidates
    }
    problems = []

    for index, tool in enumerate(registry.get("tools") or []):
        route = tool.get("route") if isinstance(tool.get("route"), dict) else {}
        method = str(route.get("method") or tool.get("method") or "").upper()
        path = str(route.get("path") or tool.get("path") or "")
        route_key = _route_key(method, path)
        candidate = candidates_by_route.get(route_key)
        reason = None

        if not method or not path:
            reason = "missing route method/path"
        elif candidate is None:
            reason = "route is not in the generated /api/v1 candidate inventory"
        elif not candidate["eligible_read_only_mcp_candidate"]:
            reason = "route is not an eligible read-only candidate"
        elif not _tool_matches_candidate(tool, candidate):
            reason = "tool fields do not match the candidate or review-only boundary"

        if reason:
            problems.append(
                {
                    "index": index,
                    "id": tool.get("id"),
                    "method": method,
                    "path": path,
                    "reason": reason,
                }
            )

    return problems


def _review_disposition(
    *,
    state: str,
    rationale: str,
    evidence: list[str],
    next_gate: str,
    reviewed_on: str = DEFAULT_DISPOSITION_REVIEW_DATE,
) -> dict[str, Any]:
    if state not in DISPOSITION_STATES:
        raise ValueError(f"Unsupported review disposition state: {state}")
    return {
        "state": state,
        "owner": DISPOSITION_OWNER,
        "reviewed_on": reviewed_on,
        "rationale": rationale,
        "evidence": evidence,
        "next_gate": next_gate,
        "does_not_imply_mcp_exposure": True,
        "runtime_promotion": "not_promoted",
    }


def _candidate_review_disposition(
    *,
    method: str,
    path: str,
    eligible: bool,
    risk_class: str,
    blocked_reasons: list[str],
) -> dict[str, Any]:
    reviewed_on = ROUTE_DISPOSITION_REVIEW_DATES.get(
        (method, path),
        DEFAULT_DISPOSITION_REVIEW_DATE,
    )
    if eligible:
        return _review_disposition(
            state="approved_for_review_only",
            rationale=(
                "Reviewed as an initial typed, process-local, read-only "
                "status/telemetry/media-health candidate. This is documentation-stage "
                "approval only and does not make the route callable."
            ),
            evidence=[
                "docs/agent-context/agent_tools.yaml",
                "docs/agent-context/agent_policy.yaml",
                "tests/test_api_tool_candidates.py",
            ],
            next_gate=(
                "Runtime MCP auth, audit, operator docs, evals, and independent "
                "promotion review before any tools/list exposure."
            ),
            reviewed_on=reviewed_on,
        )

    if risk_class == "validation_stimulus":
        return _review_disposition(
            state="deferred",
            rationale=(
                "Validation stimulus routes can mutate validation-only runtime "
                "state when enabled. They are deferred until the guarded SITL "
                "validation stack and evidence contract are complete."
            ),
            evidence=[
                "docs/architecture/pixeagle-modernization-blueprint.md",
                "docs/drone-interface/04-infrastructure/sitl-setup.md",
                "tests/test_api_tool_candidates.py",
            ],
            next_gate=(
                "PXE-0065 sidecar/evidence hardening and a separate SITL-only "
                "agent policy review."
            ),
            reviewed_on=reviewed_on,
        )

    return _review_disposition(
        state="blocked",
        rationale=" ".join(blocked_reasons)
        or "Candidate is outside the approved API/MCP review boundary.",
        evidence=[
            "docs/agent-context/agent_policy.yaml",
            "docs/apis/api-modernization-blueprint.md",
            "tests/test_api_tool_candidates.py",
        ],
        next_gate=(
            "Separate API safety/security design, tests, and independent review "
            "before this candidate can leave blocked state."
        ),
        reviewed_on=reviewed_on,
    )


def _classify_candidate(
    route: dict[str, Any],
    registry_index: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    method = route["method"]
    path = route["path"]
    read_only = method == "GET"
    typed_api_contract = _typed_contract(route)
    eligible = (
        path in _read_only_eligible_paths()
        and read_only
        and typed_api_contract
        and not _sensitive_candidate_path(path)
    )
    candidate_id = _candidate_id(path, method)

    risk_class = "unreviewed"
    sensitivity = "unknown"
    side_effects = "unknown"
    blocked_reasons: list[str] = []
    safety_notes: list[str] = []
    required_review: list[str] = [
        "curated registry entry",
        "operator-facing docs",
        "route contract tests",
        "policy classification",
        "independent safety review",
    ]

    if eligible:
        risk_class = "process_local_observe"
        sensitivity = (
            "media_transport_health"
            if path == "/api/v1/streams/media-health"
            else "runtime_status"
        )
        side_effects = "none_expected"
        safety_notes.extend(
            [
                "Candidate is a PixEagle process-local GET snapshot only.",
                "Candidate does not prove PX4, SITL, HIL, field, tracker, follower, or real-aircraft success.",
                "Promotion still requires a curated registry and policy review.",
            ]
        )
    elif path == "/api/v1/actions/{action_id}" and method == "GET":
        risk_class = "control_audit_observe"
        sensitivity = "action_audit"
        side_effects = "none_expected"
        blocked_reasons.extend(
            [
                "Action resources may expose control-operation audit details.",
                "Promote only through a reviewed action-audit read tool with sensitivity policy.",
            ]
        )
        safety_notes.append(
            "Read-only HTTP semantics are not enough for MCP exposure of control-action records."
        )
    elif path.startswith("/api/v1/actions/"):
        risk_class = "guarded_control_action"
        sensitivity = "flight_control"
        side_effects = "can_mutate_tracking_or_following_control_path"
        blocked_reasons.extend(
            [
                "Control mutation route.",
                "Requires confirmation, idempotency, dry-run/replay semantics, audit records, and policy approval.",
                "Not eligible for read-only MCP promotion.",
            ]
        )
        required_review.extend(
            [
                "action proposal schema",
                "SITL-only callable wrapper",
                "PX4 observation evidence gate",
            ]
        )
    elif path.startswith("/api/v1/auth/"):
        risk_class = "auth_session_boundary"
        sensitivity = "session_auth"
        side_effects = (
            "none_expected"
            if read_only
            else "creates_or_revokes_browser_session_state"
        )
        blocked_reasons.extend(
            [
                "Authentication bootstrap route.",
                "Not eligible for MCP promotion; use typed API/session contracts only.",
            ]
        )
        required_review.extend(
            [
                "credential storage review",
                "browser CSRF review",
                "session lifecycle tests",
            ]
        )
    elif path.startswith("/api/v1/sitl/injections/"):
        risk_class = "validation_stimulus"
        sensitivity = "sitl_fault_injection"
        side_effects = "mutates_validation_only_runtime_state_when_enabled"
        blocked_reasons.extend(
            [
                "Validation-only stimulus route.",
                "Disabled by default and intended only for operator-approved validation stacks.",
                "Not a read-only MCP candidate.",
            ]
        )
        required_review.extend(
            [
                "validation-stack gating review",
                "fault-injection docs",
                "scenario evidence contract",
            ]
        )
    elif read_only:
        risk_class = "unreviewed_observe"
        sensitivity = "unclassified"
        side_effects = "none_expected"
        blocked_reasons.extend(
            [
                "Read-only route is not in the approved initial process-local candidate set.",
                "Requires explicit sensitivity and output-shape review before promotion.",
            ]
        )
    else:
        risk_class = "unreviewed_mutation"
        sensitivity = "unclassified"
        side_effects = "unreviewed_mutation"
        blocked_reasons.extend(
            [
                "Mutation route is outside the reviewed action/SITL candidate policy.",
                "Not eligible for read-only MCP promotion.",
            ]
        )

    if not typed_api_contract:
        blocked_reasons.append(
            "Route is missing complete typed API metadata for MCP candidate review."
        )

    if not eligible and not blocked_reasons:
        blocked_reasons.append("Not approved for MCP promotion in this slice.")

    candidate = {
        "id": candidate_id,
        "candidate_id": candidate_id,
        "method": method,
        "path": path,
        "operation_id": route.get("operation_id"),
        "tags": route.get("tags") or [],
        "response_model": route.get("response_model"),
        "request_model": route.get("request_model"),
        "responses": route.get("responses"),
        "status_code": route.get("status_code"),
        "handler": route.get("handler"),
        "typed_api_contract": typed_api_contract,
        "deprecated": bool(route.get("deprecated")),
        "classification": risk_class,
        "read_only": read_only,
        "callable": False,
        "mcp_exposure": "none",
        "default_registry_exposure": "exclude",
        "review_status": "generated_unreviewed",
        "promotion_status": "unpromoted",
        "eligible_read_only_mcp_candidate": eligible,
        "risk_class": risk_class,
        "sensitivity": sensitivity,
        "side_effects": side_effects,
        "claim_boundary": INVENTORY_CLAIM_BOUNDARY,
        "blocked_reasons": blocked_reasons,
        "required_review": sorted(set(required_review)),
        "safety_notes": safety_notes,
        "review_disposition": _candidate_review_disposition(
            method=method,
            path=path,
            eligible=eligible,
            risk_class=risk_class,
            blocked_reasons=blocked_reasons,
        ),
    }
    matches = _registry_matches_for_candidate(candidate, registry_index or {})
    candidate["registry_matches"] = matches
    if eligible and any(match["valid_review_only_match"] for match in matches):
        candidate["review_status"] = "registry_reviewed_unexposed"
        candidate["registry_review_status"] = "registered_unexposed"
    else:
        candidate["registry_review_status"] = "unregistered"
    return candidate


def _registry_coverage_summary(
    candidates: list[dict[str, Any]],
    registry: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    eligible = [
        candidate
        for candidate in candidates
        if candidate["eligible_read_only_mcp_candidate"]
    ]
    registered = []
    unregistered = []
    for candidate in eligible:
        valid_matches = [
            match
            for match in candidate.get("registry_matches") or []
            if match.get("valid_review_only_match")
        ]
        if valid_matches:
            registered.append(
                {
                    "method": candidate["method"],
                    "path": candidate["path"],
                    "candidate_id": candidate["id"],
                    "tool_ids": sorted(match["id"] for match in valid_matches),
                }
            )
        else:
            unregistered.append(
                {
                    "method": candidate["method"],
                    "path": candidate["path"],
                    "candidate_id": candidate["id"],
                }
            )

    invalid_route_matches = [
        candidate
        for candidate in candidates
        if not candidate["eligible_read_only_mcp_candidate"]
        and candidate.get("registry_matches")
    ]
    exposed_matches = [
        match
        for candidate in candidates
        for match in candidate.get("registry_matches") or []
        if match.get("callable") is not False or match.get("mcp_exposure") != "none"
    ]
    registry_present = bool(registry.get("present"))
    policy_present = bool(policy.get("present"))
    eligible_count = len(eligible)
    registered_count = len(registered)
    registry_metadata_problems = _registry_metadata_problems(registry)
    registry_tool_problems = _registry_tool_problems(candidates, registry)
    policy_problems = _policy_problems(policy)
    registry_metadata_safe = registry_present and not registry_metadata_problems
    registry_tools_safe = registry_present and not registry_tool_problems
    policy_safe = policy_present and not policy_problems
    return {
        "registry_present": registry_present,
        "registry_path": registry.get("path") or "",
        "policy_present": policy_present,
        "policy_path": policy.get("path") or "",
        "registry_tool_count": len(registry.get("tools") or []),
        "docs_registry_present": registry_present,
        "docs_registered_read_only_candidates": registered_count,
        "registry_metadata_safe": registry_metadata_safe,
        "registry_tools_safe": registry_tools_safe,
        "policy_safe": policy_safe,
        "eligible_read_only_candidate_count": eligible_count,
        "registered_eligible_read_only_candidate_count": registered_count,
        "unregistered_eligible_read_only_candidate_count": len(unregistered),
        "unpromoted_eligible_read_only_candidates": len(unregistered),
        "registered_eligible_read_only_ratio": (
            round(registered_count / eligible_count, 4) if eligible_count else 1.0
        ),
        "promoted_candidates": 0,
        "runtime_promoted_candidates": 0,
        "callable_registry_matches": len(
            [match for match in exposed_matches if match.get("callable") is not False]
        ),
        "mcp_exposed_registry_matches": len(
            [match for match in exposed_matches if match.get("mcp_exposure") != "none"]
        ),
        "invalid_registered_route_count": len(invalid_route_matches),
        "unsafe_registry_metadata_count": len(registry_metadata_problems),
        "unsafe_registry_tool_count": len(registry_tool_problems),
        "unsafe_policy_setting_count": len(policy_problems),
        "unregistered_eligible_preview": unregistered[:10],
        "registry_metadata_problem_preview": registry_metadata_problems[:10],
        "registry_tool_problem_preview": registry_tool_problems[:10],
        "policy_problem_preview": policy_problems[:10],
        "status": (
            "review_registry_complete_no_mcp_exposure"
            if registry_present
            and policy_present
            and registry_metadata_safe
            and registry_tools_safe
            and policy_safe
            and registered_count == eligible_count
            and not unregistered
            and not invalid_route_matches
            and not exposed_matches
            else "registry_review_incomplete_or_unsafe"
        ),
    }


def _disposition_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {state: 0 for state in sorted(DISPOSITION_STATES)}
    invalid = []
    missing = []
    unsafe = []

    for candidate in candidates:
        disposition = candidate.get("review_disposition")
        if not isinstance(disposition, dict):
            missing.append(candidate["id"])
            continue

        state = disposition.get("state")
        if state not in DISPOSITION_STATES:
            invalid.append(candidate["id"])
        else:
            counts[state] += 1

        if (
            disposition.get("does_not_imply_mcp_exposure") is not True
            or disposition.get("runtime_promotion") != "not_promoted"
            or candidate.get("callable") is not False
            or candidate.get("mcp_exposure") != "none"
            or candidate.get("promotion_status") != "unpromoted"
        ):
            unsafe.append(candidate["id"])

    total_valid = sum(counts.values())
    return {
        "states": counts,
        "approved_for_review_only": counts["approved_for_review_only"],
        "blocked": counts["blocked"],
        "deferred": counts["deferred"],
        "valid_disposition_count": total_valid,
        "missing_disposition_count": len(missing),
        "invalid_disposition_count": len(invalid),
        "unsafe_disposition_boundary_count": len(unsafe),
        "complete": (
            total_valid == len(candidates)
            and not missing
            and not invalid
            and not unsafe
        ),
        "missing_preview": missing[:10],
        "invalid_preview": invalid[:10],
        "unsafe_preview": unsafe[:10],
    }


def build_inventory() -> dict[str, Any]:
    routes = collect_declared_routes()
    registry = _load_registry()
    policy_payload = _load_yaml_file(DEFAULT_POLICY)
    policy = {
        "path": _relative_path(DEFAULT_POLICY),
        "present": DEFAULT_POLICY.exists(),
        "payload": policy_payload,
    }
    registry_index = _registry_route_index(registry)
    api_v1_routes = [route for route in routes if route["path"].startswith("/api/v1/")]
    candidates = [_classify_candidate(route, registry_index) for route in api_v1_routes]
    read_only_candidates = [
        candidate
        for candidate in candidates
        if candidate["eligible_read_only_mcp_candidate"]
    ]
    registry_coverage = _registry_coverage_summary(candidates, registry, policy)
    disposition_coverage = _disposition_summary(candidates)
    source_files = [
        {
            "file": str(source.relative_to(PROJECT_ROOT)),
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
        for source in ROUTE_SOURCE_FILES
    ]

    return {
        "schema_version": 1,
        "artifact": "pixeagle-openapi-tool-candidates",
        "kind": "pixeagle_api_tool_candidate_inventory",
        "source": {
            "primary_file": str(FASTAPI_HANDLER.relative_to(PROJECT_ROOT)),
            "files": source_files,
        },
        "generated_from": [entry["file"] for entry in source_files],
        "output_path": str(DEFAULT_OUTPUT.relative_to(PROJECT_ROOT)),
        "claim_boundary": INVENTORY_CLAIM_BOUNDARY,
        "promotion_path": [
            "FastAPI route",
            "generated non-callable candidate",
            "curated registry entry",
            "policy classification",
            "typed input/output contract",
            "operator docs and safety notes",
            "tests and evals",
            "independent reviewer approval",
            "MCP tools/list and tools/call exposure",
        ],
        "summary": {
            "total_declared_http_routes": len(routes),
            "api_v1_routes": len(api_v1_routes),
            "candidate_count": len(candidates),
            "eligible_read_only_candidates": len(read_only_candidates),
            "callable_tools": 0,
            "mcp_exposed_tools": 0,
            "unpromoted_read_only_candidates": len(read_only_candidates),
            "docs_registered_read_only_candidates": (
                registry_coverage["docs_registered_read_only_candidates"]
            ),
            "runtime_promoted_candidates": 0,
            "blocked_or_guarded_candidates": len(candidates) - len(read_only_candidates),
            "review_disposition": disposition_coverage,
            "disposition_coverage_complete": disposition_coverage["complete"],
            "curated_registry_present": registry_coverage["registry_present"],
            "registry_coverage_status": registry_coverage["status"],
            "registry_coverage": registry_coverage,
        },
        "candidates": candidates,
    }


def render_inventory(inventory: dict[str, Any]) -> str:
    return yaml.safe_dump(
        inventory,
        sort_keys=False,
        width=88,
        allow_unicode=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path to write or check the generated candidate inventory.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the output file does not match generated content.",
    )
    args = parser.parse_args(argv)

    output = Path(args.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output

    rendered = render_inventory(build_inventory())

    if args.check:
        if not output.exists():
            print(f"Missing generated inventory: {output}", file=sys.stderr)
            return 1
        current = output.read_text(encoding="utf-8")
        if current != rendered:
            diff = difflib.unified_diff(
                current.splitlines(),
                rendered.splitlines(),
                fromfile=str(output),
                tofile="generated",
                lineterm="",
            )
            print("\n".join(diff), file=sys.stderr)
            print(
                "Regenerate with: python tools/generate_api_tool_candidates.py",
                file=sys.stderr,
            )
            return 1
        print(f"API tool candidate inventory is current: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    print(f"Wrote API tool candidate inventory: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
