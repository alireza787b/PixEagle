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
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "docs"
    / "agent-context"
    / "generated"
    / "pixeagle-openapi-tool-candidates.yaml"
)

INVENTORY_CLAIM_BOUNDARY = (
    "Generated non-callable reviewer inventory only. This file is not an MCP "
    "tool registry, not a tools/list response, and not permission for an AI "
    "agent or client to execute any PixEagle API route. PixEagle status and "
    "telemetry routes are process-local snapshots unless separate PX4/SITL/HIL/"
    "field evidence artifacts prove a specific scenario."
)

READ_ONLY_ELIGIBLE_PATHS = {
    "/api/v1/runtime/status",
    "/api/v1/following/status",
    "/api/v1/following/telemetry",
    "/api/v1/telemetry/health",
    "/api/v1/tracking/runtime-status",
    "/api/v1/tracking/telemetry",
}


def _expr_to_data(node: ast.AST | None) -> Any:
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _expr_to_data(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.List | ast.Tuple):
        return [_expr_to_data(item) for item in node.elts]
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


def collect_declared_routes() -> list[dict[str, Any]]:
    tree = _load_fastapi_handler_tree()
    request_models = _handler_request_models(tree)
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


def _classify_candidate(route: dict[str, Any]) -> dict[str, Any]:
    method = route["method"]
    path = route["path"]
    read_only = method == "GET"
    typed_api_contract = _typed_contract(route)
    eligible = path in READ_ONLY_ELIGIBLE_PATHS and read_only and typed_api_contract

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
        sensitivity = "runtime_status"
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
        side_effects = "can_start_or_stop_following_offboard_path"
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

    return {
        "id": _candidate_id(path, method),
        "candidate_id": _candidate_id(path, method),
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
    }


def build_inventory() -> dict[str, Any]:
    routes = collect_declared_routes()
    api_v1_routes = [route for route in routes if route["path"].startswith("/api/v1/")]
    candidates = [_classify_candidate(route) for route in api_v1_routes]
    read_only_candidates = [
        candidate
        for candidate in candidates
        if candidate["eligible_read_only_mcp_candidate"]
    ]

    return {
        "schema_version": 1,
        "artifact": "pixeagle-openapi-tool-candidates",
        "kind": "pixeagle_api_tool_candidate_inventory",
        "source": {
            "file": str(FASTAPI_HANDLER.relative_to(PROJECT_ROOT)),
            "sha256": hashlib.sha256(
                FASTAPI_HANDLER.read_bytes(),
            ).hexdigest(),
        },
        "generated_from": str(FASTAPI_HANDLER.relative_to(PROJECT_ROOT)),
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
            "blocked_or_guarded_candidates": len(candidates) - len(read_only_candidates),
            "curated_registry_present": False,
            "registry_coverage_status": "candidate_inventory_only",
            "registry_coverage": {
                "registry_present": False,
                "promoted_candidates": 0,
                "unpromoted_eligible_read_only_candidates": len(read_only_candidates),
                "status": "candidate_inventory_only",
            },
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
