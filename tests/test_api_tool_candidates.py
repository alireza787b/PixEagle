import subprocess
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = (
    PROJECT_ROOT
    / "docs"
    / "agent-context"
    / "generated"
    / "pixeagle-openapi-tool-candidates.yaml"
)


def _load_inventory():
    return yaml.safe_load(INVENTORY_PATH.read_text(encoding="utf-8"))


def _candidate_by_path_method(inventory):
    return {
        (candidate["method"], candidate["path"]): candidate
        for candidate in inventory["candidates"]
    }


def test_api_tool_candidate_inventory_is_current():
    """Generated candidate inventory must drift with the route inventory."""
    result = subprocess.run(
        [sys.executable, "tools/generate_api_tool_candidates.py", "--check"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_api_tool_candidate_inventory_is_non_callable():
    """This slice must not accidentally create an MCP tool surface."""
    inventory = _load_inventory()

    assert inventory["artifact"] == "pixeagle-openapi-tool-candidates"
    assert inventory["source"]["file"] == "src/classes/fastapi_handler.py"
    assert len(inventory["source"]["sha256"]) == 64
    assert inventory["summary"]["callable_tools"] == 0
    assert inventory["summary"]["mcp_exposed_tools"] == 0
    assert inventory["summary"]["curated_registry_present"] is False
    assert inventory["summary"]["registry_coverage"] == {
        "registry_present": False,
        "promoted_candidates": 0,
        "unpromoted_eligible_read_only_candidates": 6,
        "status": "candidate_inventory_only",
    }
    assert "not an MCP tool registry" in inventory["claim_boundary"]
    assert "not permission" in inventory["claim_boundary"]
    for candidate in inventory["candidates"]:
        assert candidate["id"]
        assert candidate["id"] == candidate["candidate_id"]
        assert candidate["callable"] is False
        assert candidate["mcp_exposure"] == "none"
        assert candidate["default_registry_exposure"] == "exclude"
        assert candidate["review_status"] == "generated_unreviewed"
        assert candidate["promotion_status"] == "unpromoted"
        assert candidate["claim_boundary"] == inventory["claim_boundary"]


def test_initial_read_only_candidates_are_limited_to_typed_process_local_gets():
    inventory = _load_inventory()
    candidates = _candidate_by_path_method(inventory)
    expected_paths = {
        "/api/v1/runtime/status",
        "/api/v1/following/status",
        "/api/v1/following/telemetry",
        "/api/v1/telemetry/health",
        "/api/v1/tracking/runtime-status",
        "/api/v1/tracking/telemetry",
    }

    eligible = {
        candidate["path"]
        for candidate in inventory["candidates"]
        if candidate["eligible_read_only_mcp_candidate"]
    }

    assert eligible == expected_paths
    assert inventory["summary"]["eligible_read_only_candidates"] == len(expected_paths)
    assert inventory["summary"]["unpromoted_read_only_candidates"] == len(expected_paths)

    for path in expected_paths:
        candidate = candidates[("GET", path)]
        assert candidate["read_only"] is True
        assert candidate["typed_api_contract"] is True
        assert candidate["risk_class"] == "process_local_observe"
        assert candidate["classification"] == "process_local_observe"
        assert candidate["side_effects"] == "none_expected"
        assert candidate["blocked_reasons"] == []
        assert any("process-local" in note for note in candidate["safety_notes"])


def test_action_and_sitl_routes_are_blocked_from_read_only_promotion():
    inventory = _load_inventory()
    candidates = _candidate_by_path_method(inventory)
    blocked_routes = {
        ("POST", "/api/v1/actions/offboard-start"): "guarded_control_action",
        ("POST", "/api/v1/actions/operator-abort"): "guarded_control_action",
        ("GET", "/api/v1/actions/{action_id}"): "control_audit_observe",
        ("POST", "/api/v1/sitl/injections/tracker-output"): "validation_stimulus",
        ("POST", "/api/v1/sitl/injections/video-stall"): "validation_stimulus",
        (
            "POST",
            "/api/v1/sitl/injections/commander-publish-failure",
        ): "validation_stimulus",
        ("POST", "/api/v1/sitl/injections/mavsdk-disconnect"): "validation_stimulus",
        (
            "POST",
            "/api/v1/sitl/injections/mavlink2rest-timeout",
        ): "validation_stimulus",
    }

    for route, risk_class in blocked_routes.items():
        candidate = candidates[route]
        assert candidate["risk_class"] == risk_class
        assert candidate["eligible_read_only_mcp_candidate"] is False
        assert candidate["blocked_reasons"] != []
        assert candidate["mcp_exposure"] == "none"


def test_api_tool_candidate_summary_matches_current_api_v1_inventory():
    inventory = _load_inventory()
    expected_routes = {
        ("GET", "/api/v1/actions/{action_id}"),
        ("POST", "/api/v1/actions/offboard-start"),
        ("POST", "/api/v1/actions/operator-abort"),
        ("GET", "/api/v1/following/status"),
        ("GET", "/api/v1/following/telemetry"),
        ("GET", "/api/v1/runtime/status"),
        ("POST", "/api/v1/sitl/injections/commander-publish-failure"),
        ("POST", "/api/v1/sitl/injections/mavlink2rest-timeout"),
        ("POST", "/api/v1/sitl/injections/mavsdk-disconnect"),
        ("POST", "/api/v1/sitl/injections/tracker-output"),
        ("POST", "/api/v1/sitl/injections/video-stall"),
        ("GET", "/api/v1/telemetry/health"),
        ("GET", "/api/v1/tracking/runtime-status"),
        ("GET", "/api/v1/tracking/telemetry"),
    }
    candidate_routes = {
        (candidate["method"], candidate["path"])
        for candidate in inventory["candidates"]
    }

    assert inventory["summary"]["api_v1_routes"] == 14
    assert inventory["summary"]["candidate_count"] == 14
    assert len(inventory["candidates"]) == 14
    assert inventory["summary"]["blocked_or_guarded_candidates"] == 8
    assert candidate_routes == expected_routes
    assert all(path.startswith("/api/v1/") for _method, path in candidate_routes)
    assert inventory["promotion_path"][-1] == "MCP tools/list and tools/call exposure"


def test_api_tool_candidate_docs_state_candidate_inventory_only():
    docs = [
        PROJECT_ROOT / "docs" / "agent-context" / "README.md",
        PROJECT_ROOT / "docs" / "apis" / "api-modernization-blueprint.md",
        PROJECT_ROOT / "docs" / "core-app" / "03-api" / "README.md",
    ]

    for path in docs:
        text = " ".join(path.read_text(encoding="utf-8").lower().split())
        assert "candidate" in text
        assert "not mcp execution" in text
        assert "mcp" in text
