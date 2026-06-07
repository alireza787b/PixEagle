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
REGISTRY_PATH = PROJECT_ROOT / "docs" / "agent-context" / "agent_tools.yaml"
POLICY_PATH = PROJECT_ROOT / "docs" / "agent-context" / "agent_policy.yaml"


def _load_inventory():
    return yaml.safe_load(INVENTORY_PATH.read_text(encoding="utf-8"))


def _load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _candidate_by_path_method(inventory):
    return {
        (candidate["method"], candidate["path"]): candidate
        for candidate in inventory["candidates"]
    }


def _candidate_by_id(inventory):
    return {candidate["id"]: candidate for candidate in inventory["candidates"]}


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
    assert inventory["source"]["primary_file"] == "src/classes/fastapi_handler.py"
    assert inventory["generated_from"] == [
        "src/classes/fastapi_handler.py",
        "src/classes/fastapi_api_v1_routes.py",
        "src/classes/api_v1_contracts.py",
        "src/classes/api_v1_paths.py",
        "src/classes/api_v1_actions.py",
    ]
    assert {
        source["file"]: len(source["sha256"])
        for source in inventory["source"]["files"]
    } == {
        "src/classes/fastapi_handler.py": 64,
        "src/classes/fastapi_api_v1_routes.py": 64,
        "src/classes/api_v1_contracts.py": 64,
        "src/classes/api_v1_paths.py": 64,
        "src/classes/api_v1_actions.py": 64,
    }
    assert inventory["summary"]["callable_tools"] == 0
    assert inventory["summary"]["mcp_exposed_tools"] == 0
    assert inventory["summary"]["curated_registry_present"] is True
    coverage = inventory["summary"]["registry_coverage"]
    assert coverage["registry_present"] is True
    assert coverage["policy_present"] is True
    assert coverage["registry_path"] == "docs/agent-context/agent_tools.yaml"
    assert coverage["policy_path"] == "docs/agent-context/agent_policy.yaml"
    assert coverage["docs_registered_read_only_candidates"] == 6
    assert coverage["registry_metadata_safe"] is True
    assert coverage["registry_tools_safe"] is True
    assert coverage["policy_safe"] is True
    assert coverage["registered_eligible_read_only_candidate_count"] == 6
    assert coverage["unregistered_eligible_read_only_candidate_count"] == 0
    assert coverage["runtime_promoted_candidates"] == 0
    assert coverage["callable_registry_matches"] == 0
    assert coverage["mcp_exposed_registry_matches"] == 0
    assert coverage["invalid_registered_route_count"] == 0
    assert coverage["unsafe_registry_metadata_count"] == 0
    assert coverage["unsafe_registry_tool_count"] == 0
    assert coverage["unsafe_policy_setting_count"] == 0
    assert coverage["status"] == "review_registry_complete_no_mcp_exposure"
    assert "not an MCP tool registry" in inventory["claim_boundary"]
    assert "not permission" in inventory["claim_boundary"]
    for candidate in inventory["candidates"]:
        assert candidate["id"]
        assert candidate["id"] == candidate["candidate_id"]
        assert candidate["callable"] is False
        assert candidate["mcp_exposure"] == "none"
        assert candidate["default_registry_exposure"] == "exclude"
        assert candidate["review_status"] in {
            "generated_unreviewed",
            "registry_reviewed_unexposed",
        }
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
    assert inventory["summary"]["docs_registered_read_only_candidates"] == len(expected_paths)
    assert inventory["summary"]["runtime_promoted_candidates"] == 0

    for path in expected_paths:
        candidate = candidates[("GET", path)]
        assert candidate["read_only"] is True
        assert candidate["typed_api_contract"] is True
        assert candidate["risk_class"] == "process_local_observe"
        assert candidate["classification"] == "process_local_observe"
        assert candidate["side_effects"] == "none_expected"
        assert candidate["blocked_reasons"] == []
        assert candidate["review_status"] == "registry_reviewed_unexposed"
        assert candidate["registry_review_status"] == "registered_unexposed"
        assert len(candidate["registry_matches"]) == 1
        assert candidate["registry_matches"][0]["valid_review_only_match"] is True
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
        assert candidate["registry_matches"] == []
        assert candidate["registry_review_status"] == "unregistered"


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


def test_docs_stage_agent_registry_only_registers_eligible_read_only_candidates():
    inventory = _load_inventory()
    candidates = _candidate_by_id(inventory)
    registry = _load_yaml(REGISTRY_PATH)
    tools = registry["tools"]
    registered_routes = {(tool["method"], tool["path"]) for tool in tools}
    eligible_routes = {
        (candidate["method"], candidate["path"])
        for candidate in inventory["candidates"]
        if candidate["eligible_read_only_mcp_candidate"]
    }

    assert registry["metadata"]["registry_stage"] == "docs_review_only"
    assert registry["metadata"]["runtime_loaded"] is False
    assert registry["metadata"]["mcp_exposed"] is False
    assert registry["metadata"]["default_registry_exposure"] == "exclude"
    assert len(tools) == 6
    assert registered_routes == eligible_routes

    for tool in tools:
        candidate = candidates[tool["candidate_id"]]
        assert tool["id"] == candidate["id"]
        assert tool["method"] == candidate["method"]
        assert tool["path"] == candidate["path"]
        assert tool["operation_id"] == candidate["operation_id"]
        assert tool["response_model"] == candidate["response_model"]
        assert tool["route"]["method"] == candidate["method"]
        assert tool["route"]["path"] == candidate["path"]
        assert tool["route"]["operation_id"] == candidate["operation_id"]
        assert tool["read_only"] is True
        assert tool["callable"] is False
        assert tool["mcp_exposure"] == "none"
        assert tool["exposure"] == "review_only"
        assert tool["default_registry_exposure"] == "exclude"
        assert tool["promotion_status"] == "unpromoted"
        assert tool["risk_class"] == "observe"
        assert tool["candidate_risk_class"] == candidate["risk_class"]
        assert tool["side_effects"] == []
        assert tool["boundary"] == "pixeagle-process-local"
        assert tool["required_role"] == "viewer"
        assert "tests/test_api_tool_candidates.py" in tool["tests"]


def test_docs_stage_agent_policy_denies_execution_and_actions():
    policy = _load_yaml(POLICY_PATH)

    assert policy["metadata"]["policy_stage"] == "docs_review_only"
    assert policy["defaults"]["agent_enabled"] is False
    assert policy["defaults"]["mcp_enabled"] is False
    assert policy["defaults"]["registry_runtime_loaded"] is False
    assert policy["defaults"]["unknown_tool_policy"] == "deny"
    assert policy["defaults"]["action_circuit_breaker_enabled"] is True
    assert policy["defaults"]["always_confirm_before_action"] is True
    assert policy["defaults"]["allow_drone_api_exposure"] is False
    assert policy["defaults"]["allow_px4_or_drone_api_exposure"] is False
    assert policy["defaults"]["allow_openapi_autopromotion"] is False
    assert policy["defaults"]["allow_action_tools"] is False
    assert policy["defaults"]["allow_sitl_injection_tools"] is False
    assert policy["defaults"]["auto_promote_generated_candidates"] is False

    denied_risks = set(policy["denied_risks"])
    assert {"simulate", "operate", "admin", "destructive"}.issubset(denied_risks)
    assert {
        "guarded_control_action",
        "validation_stimulus",
        "unreviewed_mutation",
    }.issubset(denied_risks)
    assert "/api/v1/actions/" in policy["denied_route_prefixes"]
    assert "/api/v1/sitl/injections/" in policy["denied_route_prefixes"]


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
