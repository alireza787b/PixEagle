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
VALID_REVIEW_DISPOSITIONS = {
    "approved_for_review_only",
    "blocked",
    "deferred",
}


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
        "src/classes/api_v1_auth_routes.py",
        "src/classes/api_v1_log_routes.py",
        "src/classes/api_legacy_control_routes.py",
        "src/classes/api_legacy_config_sync.py",
        "src/classes/api_legacy_config_routes.py",
        "src/classes/api_legacy_follower_routes.py",
        "src/classes/api_legacy_gstreamer_routes.py",
        "src/classes/api_legacy_media_routes.py",
        "src/classes/api_legacy_model_routes.py",
        "src/classes/api_legacy_osd_routes.py",
        "src/classes/api_legacy_recording_routes.py",
        "src/classes/api_legacy_safety_routes.py",
        "src/classes/api_legacy_tracker_routes.py",
        "src/classes/webrtc_manager.py",
        "src/classes/api_v1_read_routes.py",
        "src/classes/api_v1_snapshots.py",
        "src/classes/api_v1_telemetry.py",
        "src/classes/api_v1_streams.py",
        "src/classes/api_v1_sitl.py",
        "src/classes/api_exposure_policy.py",
        "src/classes/api_auth_runtime.py",
        "src/classes/api_security_audit.py",
        "src/classes/api_security_types.py",
        "src/classes/api_security_policy.py",
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
        "src/classes/api_v1_auth_routes.py": 64,
        "src/classes/api_v1_log_routes.py": 64,
        "src/classes/api_legacy_control_routes.py": 64,
        "src/classes/api_legacy_config_sync.py": 64,
        "src/classes/api_legacy_config_routes.py": 64,
        "src/classes/api_legacy_follower_routes.py": 64,
        "src/classes/api_legacy_gstreamer_routes.py": 64,
        "src/classes/api_legacy_media_routes.py": 64,
        "src/classes/api_legacy_model_routes.py": 64,
        "src/classes/api_legacy_osd_routes.py": 64,
        "src/classes/api_legacy_recording_routes.py": 64,
        "src/classes/api_legacy_safety_routes.py": 64,
        "src/classes/api_legacy_tracker_routes.py": 64,
        "src/classes/webrtc_manager.py": 64,
        "src/classes/api_v1_read_routes.py": 64,
        "src/classes/api_v1_snapshots.py": 64,
        "src/classes/api_v1_telemetry.py": 64,
        "src/classes/api_v1_streams.py": 64,
        "src/classes/api_v1_sitl.py": 64,
        "src/classes/api_exposure_policy.py": 64,
        "src/classes/api_auth_runtime.py": 64,
        "src/classes/api_security_audit.py": 64,
        "src/classes/api_security_types.py": 64,
        "src/classes/api_security_policy.py": 64,
    }
    assert inventory["summary"]["callable_tools"] == 0
    assert inventory["summary"]["mcp_exposed_tools"] == 0
    assert inventory["summary"]["curated_registry_present"] is True
    coverage = inventory["summary"]["registry_coverage"]
    assert coverage["registry_present"] is True
    assert coverage["policy_present"] is True
    assert coverage["registry_path"] == "docs/agent-context/agent_tools.yaml"
    assert coverage["policy_path"] == "docs/agent-context/agent_policy.yaml"
    assert coverage["docs_registered_read_only_candidates"] == 8
    assert coverage["registry_metadata_safe"] is True
    assert coverage["registry_tools_safe"] is True
    assert coverage["policy_safe"] is True
    assert coverage["registered_eligible_read_only_candidate_count"] == 8
    assert coverage["unregistered_eligible_read_only_candidate_count"] == 0
    assert coverage["runtime_promoted_candidates"] == 0
    assert coverage["callable_registry_matches"] == 0
    assert coverage["mcp_exposed_registry_matches"] == 0
    assert coverage["invalid_registered_route_count"] == 0
    assert coverage["unsafe_registry_metadata_count"] == 0
    assert coverage["unsafe_registry_tool_count"] == 0
    assert coverage["unsafe_policy_setting_count"] == 0
    assert coverage["status"] == "review_registry_complete_no_mcp_exposure"
    disposition = inventory["summary"]["review_disposition"]
    assert inventory["summary"]["disposition_coverage_complete"] is True
    assert disposition["complete"] is True
    assert disposition["approved_for_review_only"] == 8
    assert disposition["blocked"] == 22
    assert disposition["deferred"] == 5
    assert (
        disposition["valid_disposition_count"]
        == inventory["summary"]["candidate_count"]
    )
    assert disposition["missing_disposition_count"] == 0
    assert disposition["invalid_disposition_count"] == 0
    assert disposition["unsafe_disposition_boundary_count"] == 0
    assert "not an MCP tool registry" in inventory["claim_boundary"]
    assert "not permission" in inventory["claim_boundary"]
    for candidate in inventory["candidates"]:
        review_disposition = candidate["review_disposition"]
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
        assert review_disposition["state"] in VALID_REVIEW_DISPOSITIONS
        assert review_disposition["owner"] == "pixeagle-api-governance"
        assert review_disposition["reviewed_on"]
        assert review_disposition["rationale"]
        assert review_disposition["evidence"]
        assert review_disposition["next_gate"]
        assert review_disposition["does_not_imply_mcp_exposure"] is True
        assert review_disposition["runtime_promotion"] == "not_promoted"


def test_initial_read_only_candidates_are_limited_to_typed_process_local_gets():
    inventory = _load_inventory()
    candidates = _candidate_by_path_method(inventory)
    expected_paths = {
        "/api/v1/runtime/status",
        "/api/v1/system/about",
        "/api/v1/streams/media-health",
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
        assert candidate["review_disposition"]["state"] == "approved_for_review_only"
        assert candidate["callable"] is False
        assert candidate["mcp_exposure"] == "none"
        assert candidate["promotion_status"] == "unpromoted"
        assert len(candidate["registry_matches"]) == 1
        assert candidate["registry_matches"][0]["valid_review_only_match"] is True
        assert (
            candidate["registry_matches"][0]["review_disposition_state"]
            == "approved_for_review_only"
        )
        assert any("process-local" in note for note in candidate["safety_notes"])

    media_candidate = candidates[("GET", "/api/v1/streams/media-health")]
    assert media_candidate["sensitivity"] == "media_transport_health"
    assert media_candidate["registry_matches"][0]["id"] == (
        "pixeagle.streams.media_health.read"
    )
    system_candidate = candidates[("GET", "/api/v1/system/about")]
    assert system_candidate["sensitivity"] == "system_metadata"
    assert system_candidate["registry_matches"][0]["id"] == (
        "pixeagle.system.about.read"
    )


def test_log_entry_candidate_does_not_treat_query_params_as_request_model():
    inventory = _load_inventory()
    candidates = _candidate_by_path_method(inventory)

    candidate = candidates[("GET", "/api/v1/logs/sessions/{run_id}")]

    assert candidate["response_model"] == "APILogSessionEntriesResponse"
    assert candidate["request_model"] is None
    assert candidate["callable"] is False
    assert candidate["mcp_exposure"] == "none"
    assert candidate["review_disposition"]["state"] == "blocked"


def test_action_and_sitl_routes_are_blocked_from_read_only_promotion():
    inventory = _load_inventory()
    candidates = _candidate_by_path_method(inventory)
    blocked_or_deferred_routes = {
        ("POST", "/api/v1/actions/offboard-start"): (
            "guarded_control_action",
            "blocked",
        ),
        ("POST", "/api/v1/actions/offboard-stop"): (
            "guarded_control_action",
            "blocked",
        ),
        ("POST", "/api/v1/actions/operator-abort"): (
            "guarded_control_action",
            "blocked",
        ),
        ("POST", "/api/v1/actions/segmentation-toggle"): (
            "guarded_control_action",
            "blocked",
        ),
        ("POST", "/api/v1/actions/smart-click"): (
            "guarded_control_action",
            "blocked",
        ),
        ("POST", "/api/v1/actions/smart-mode-toggle"): (
            "guarded_control_action",
            "blocked",
        ),
        ("POST", "/api/v1/actions/tracker-restart"): (
            "guarded_control_action",
            "blocked",
        ),
        ("POST", "/api/v1/actions/tracker-switch"): (
            "guarded_control_action",
            "blocked",
        ),
        ("POST", "/api/v1/actions/tracking-redetect"): (
            "guarded_control_action",
            "blocked",
        ),
        ("POST", "/api/v1/actions/tracking-start"): (
            "guarded_control_action",
            "blocked",
        ),
        ("POST", "/api/v1/actions/tracking-stop"): (
            "guarded_control_action",
            "blocked",
        ),
        ("GET", "/api/v1/actions/{action_id}"): (
            "control_audit_observe",
            "blocked",
        ),
        ("POST", "/api/v1/sitl/injections/tracker-output"): (
            "validation_stimulus",
            "deferred",
        ),
        ("POST", "/api/v1/sitl/injections/video-stall"): (
            "validation_stimulus",
            "deferred",
        ),
        ("POST", "/api/v1/sitl/injections/commander-publish-failure"): (
            "validation_stimulus",
            "deferred",
        ),
        ("POST", "/api/v1/sitl/injections/mavsdk-disconnect"): (
            "validation_stimulus",
            "deferred",
        ),
        ("POST", "/api/v1/sitl/injections/mavlink2rest-timeout"): (
            "validation_stimulus",
            "deferred",
        ),
        ("GET", "/api/v1/sitl/status"): (
            "validation_evidence_observe",
            "blocked",
        ),
    }

    for route, (risk_class, disposition) in blocked_or_deferred_routes.items():
        candidate = candidates[route]
        assert candidate["risk_class"] == risk_class
        assert candidate["review_disposition"]["state"] == disposition
        assert candidate["eligible_read_only_mcp_candidate"] is False
        assert candidate["blocked_reasons"] != []
        assert candidate["mcp_exposure"] == "none"
        assert candidate["registry_matches"] == []
        assert candidate["registry_review_status"] == "unregistered"


def test_auth_routes_are_blocked_from_mcp_promotion():
    inventory = _load_inventory()
    candidates = _candidate_by_path_method(inventory)
    blocked_routes = {
        ("GET", "/api/v1/auth/session"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/logout"),
    }

    for route in blocked_routes:
        candidate = candidates[route]
        assert candidate["risk_class"] == "auth_session_boundary"
        assert candidate["review_disposition"]["state"] == "blocked"
        assert candidate["eligible_read_only_mcp_candidate"] is False
        assert candidate["blocked_reasons"] != []
        assert candidate["mcp_exposure"] == "none"
        assert candidate["registry_matches"] == []
        assert candidate["registry_review_status"] == "unregistered"


def test_tracking_catalog_is_blocked_until_agent_review():
    inventory = _load_inventory()
    candidates = _candidate_by_path_method(inventory)
    candidate = candidates[("GET", "/api/v1/tracking/catalog")]

    assert candidate["risk_class"] == "unreviewed_observe"
    assert candidate["review_disposition"]["state"] == "blocked"
    assert candidate["review_disposition"]["reviewed_on"] == "2026-06-30"
    assert candidate["eligible_read_only_mcp_candidate"] is False
    assert candidate["read_only"] is True
    assert candidate["typed_api_contract"] is True
    assert candidate["blocked_reasons"] != []
    assert candidate["mcp_exposure"] == "none"
    assert candidate["registry_matches"] == []
    assert candidate["registry_review_status"] == "unregistered"


def test_sitl_validation_status_is_blocked_with_current_review_date():
    inventory = _load_inventory()
    candidates = _candidate_by_path_method(inventory)
    candidate = candidates[("GET", "/api/v1/sitl/status")]

    assert candidate["risk_class"] == "validation_evidence_observe"
    assert candidate["review_disposition"]["state"] == "blocked"
    assert candidate["review_disposition"]["reviewed_on"] == "2026-07-07"
    assert candidate["eligible_read_only_mcp_candidate"] is False
    assert candidate["mcp_exposure"] == "none"
    assert candidate["registry_matches"] == []
    assert candidate["registry_review_status"] == "unregistered"


def test_api_tool_candidate_summary_matches_current_api_v1_inventory():
    inventory = _load_inventory()
    expected_routes = {
        ("GET", "/api/v1/actions/{action_id}"),
        ("GET", "/api/v1/auth/session"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/logout"),
        ("POST", "/api/v1/actions/offboard-start"),
        ("POST", "/api/v1/actions/offboard-stop"),
        ("POST", "/api/v1/actions/operator-abort"),
        ("POST", "/api/v1/actions/segmentation-toggle"),
        ("POST", "/api/v1/actions/smart-click"),
        ("POST", "/api/v1/actions/smart-mode-toggle"),
        ("POST", "/api/v1/actions/tracker-restart"),
        ("POST", "/api/v1/actions/tracker-switch"),
        ("POST", "/api/v1/actions/tracking-redetect"),
        ("POST", "/api/v1/actions/tracking-start"),
        ("POST", "/api/v1/actions/tracking-stop"),
        ("GET", "/api/v1/following/status"),
        ("GET", "/api/v1/following/telemetry"),
        ("GET", "/api/v1/logs/sessions"),
        ("GET", "/api/v1/logs/sessions/{run_id}"),
        ("GET", "/api/v1/logs/sessions/{run_id}/export"),
        ("GET", "/api/v1/logs/status"),
        ("POST", "/api/v1/logs/frontend-errors"),
        ("GET", "/api/v1/runtime/status"),
        ("GET", "/api/v1/system/about"),
        ("GET", "/api/v1/streams/media-health"),
        ("POST", "/api/v1/sitl/injections/commander-publish-failure"),
        ("POST", "/api/v1/sitl/injections/mavlink2rest-timeout"),
        ("POST", "/api/v1/sitl/injections/mavsdk-disconnect"),
        ("POST", "/api/v1/sitl/injections/tracker-output"),
        ("POST", "/api/v1/sitl/injections/video-stall"),
        ("GET", "/api/v1/sitl/status"),
        ("GET", "/api/v1/telemetry/health"),
        ("GET", "/api/v1/tracking/catalog"),
        ("GET", "/api/v1/tracking/runtime-status"),
        ("GET", "/api/v1/tracking/telemetry"),
    }
    candidate_routes = {
        (candidate["method"], candidate["path"])
        for candidate in inventory["candidates"]
    }

    assert inventory["summary"]["api_v1_routes"] == 35
    assert inventory["summary"]["candidate_count"] == 35
    assert len(inventory["candidates"]) == 35
    assert inventory["summary"]["blocked_or_guarded_candidates"] == 27
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
    assert len(tools) == 8
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
        assert (
            tool["review_disposition"]["state"]
            == candidate["review_disposition"]["state"]
        )
        assert tool["review_disposition"]["state"] == "approved_for_review_only"
        assert tool["review_disposition"]["does_not_imply_mcp_exposure"] is True
        assert tool["review_disposition"]["runtime_promotion"] == "not_promoted"
        assert tool["risk_class"] == "observe"
        assert tool["candidate_risk_class"] == candidate["risk_class"]
        if tool["path"] == "/api/v1/streams/media-health":
            assert candidate["sensitivity"] == "media_transport_health"
            assert "media_transport_health" in tool["sensitivity"]
            assert "frame_publisher_status" in tool["sensitivity"]
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
    assert policy["review_disposition"]["required_for_all_candidates"] is True
    assert set(policy["review_disposition"]["valid_states"]) == VALID_REVIEW_DISPOSITIONS
    assert policy["review_disposition"]["default_missing_disposition_policy"] == "deny"
    assert policy["review_disposition"]["completion_allows_runtime_promotion"] is False
    assert (
        policy["review_disposition"]["approved_for_review_only_allows_callable"]
        is False
    )
    assert policy["review_disposition"]["blocked_allows_callable"] is False
    assert policy["review_disposition"]["deferred_allows_callable"] is False

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
