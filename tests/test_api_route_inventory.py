"""Static inventory of the current FastAPIHandler route surface.

This intentionally parses route declarations instead of instantiating the app.
Constructing AppController/FastAPIHandler can start runtime subsystems or create
local artifacts, while Phase 0 only needs a frozen route baseline.
"""

import ast
from collections import Counter
from types import SimpleNamespace
from pathlib import Path

from classes.fastapi_api_v1_routes import API_V1_ROUTE_SPECS, register_api_v1_routes
from classes.api_v1_paths import (
    API_V1_ACTION_OFFBOARD_START_PATH,
    API_V1_ACTION_OPERATOR_ABORT_PATH,
    API_V1_ACTION_RESOURCE_PATH,
    API_V1_PROCESS_LOCAL_READ_ONLY_PATHS,
    SITL_VALIDATION_INJECTION_PATHS,
    uses_typed_api_error_envelope,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FASTAPI_HANDLER = REPO_ROOT / "src" / "classes" / "fastapi_handler.py"
API_V1_ROUTE_REGISTRY = REPO_ROOT / "src" / "classes" / "fastapi_api_v1_routes.py"
API_V1_CONTRACTS = REPO_ROOT / "src" / "classes" / "api_v1_contracts.py"
API_V1_PATHS = REPO_ROOT / "src" / "classes" / "api_v1_paths.py"
API_V1_ERRORS = REPO_ROOT / "src" / "classes" / "api_v1_errors.py"
API_V1_ACTIONS = REPO_ROOT / "src" / "classes" / "api_v1_actions.py"
API_V1_SNAPSHOTS = REPO_ROOT / "src" / "classes" / "api_v1_snapshots.py"
API_V1_TELEMETRY = REPO_ROOT / "src" / "classes" / "api_v1_telemetry.py"
API_V1_SITL = REPO_ROOT / "src" / "classes" / "api_v1_sitl.py"

API_V1_CONTRACT_CLASS_NAMES = {
    "APIActionAuditEvent",
    "APIActionRequest",
    "APIActionResponse",
    "APIErrorResponse",
    "APIFollowingCommandPublicationStatus",
    "APIFollowingProfileStatus",
    "APIFollowingStatusResponse",
    "APIFollowingTelemetryResponse",
    "APIRuntimeModesStatus",
    "APIRuntimeStatusResponse",
    "APIRuntimeSubsystemStatus",
    "APITrackingRuntimeStatusResponse",
    "APITrackingTelemetryResponse",
    "APITelemetryHealthResponse",
    "APITelemetryPayloadHealth",
    "APITelemetryRequestFreshness",
    "APITelemetryTransportHealth",
    "SITLCommandIntentSummary",
    "SITLCommanderPublishFailureInjection",
    "SITLCommanderPublishFailureResponse",
    "SITLCommanderPublishFailureSummary",
    "SITLDisconnectResultSummary",
    "SITLFrameStatusSummary",
    "SITLMavlink2RestTimeoutInjection",
    "SITLMavlink2RestTimeoutResponse",
    "SITLMavlink2RestTimeoutSummary",
    "SITLMavlinkTelemetrySummary",
    "SITLMavsdkDisconnectInjection",
    "SITLMavsdkDisconnectResponse",
    "SITLMavsdkDisconnectSummary",
    "SITLOffboardCommanderSummary",
    "SITLPX4ConnectionSummary",
    "SITLTrackerInjectionResponse",
    "SITLTrackerInjectionSummary",
    "SITLTrackerOutputInjection",
    "SITLVideoStallInjection",
    "SITLVideoStallResponse",
    "SITLVideoStallSummary",
}


EXPECTED_ROUTES = {
    ("DELETE", "/api/models/{model_id}"),
    ("DELETE", "/api/recordings/{filename}"),
    ("GET", "/api/circuit-breaker/statistics"),
    ("GET", "/api/circuit-breaker/status"),
    ("GET", "/api/compatibility/report"),
    ("GET", "/api/config/audit"),
    ("GET", "/api/config/categories"),
    ("GET", "/api/config/current"),
    ("GET", "/api/config/current/{section}"),
    ("GET", "/api/config/default"),
    ("GET", "/api/config/default/{section}"),
    ("GET", "/api/config/defaults-sync"),
    ("GET", "/api/config/diff"),
    ("GET", "/api/config/effective-limits"),
    ("GET", "/api/config/export"),
    ("GET", "/api/config/history"),
    ("GET", "/api/config/schema"),
    ("GET", "/api/config/schema/{section}"),
    ("GET", "/api/config/search"),
    ("GET", "/api/config/sections"),
    ("GET", "/api/config/sections/relevant"),
    ("GET", "/api/follower/config/general"),
    ("GET", "/api/follower/config/{follower_name}"),
    ("GET", "/api/follower/configured-mode"),
    ("GET", "/api/follower/current-mode"),
    ("GET", "/api/follower/current-profile"),
    ("GET", "/api/follower/health"),
    ("GET", "/api/follower/profiles"),
    ("GET", "/api/follower/schema"),
    ("GET", "/api/follower/setpoints-status"),
    ("GET", "/api/gstreamer/status"),
    ("GET", "/api/models"),
    ("GET", "/api/models/active"),
    ("GET", "/api/models/{model_id}/file"),
    ("GET", "/api/models/{model_id}/labels"),
    ("GET", "/api/osd/color-modes"),
    ("GET", "/api/osd/modes"),
    ("GET", "/api/osd/presets"),
    ("GET", "/api/osd/status"),
    ("GET", "/api/recording/status"),
    ("GET", "/api/recordings"),
    ("GET", "/api/recordings/{filename}"),
    ("GET", "/api/safety/config"),
    ("GET", "/api/safety/limits/{follower_name}"),
    ("GET", "/api/storage/status"),
    ("GET", "/api/streaming/status"),
    ("GET", "/api/system/config"),
    ("GET", "/api/system/schema_info"),
    ("GET", "/api/system/status"),
    ("GET", "/api/tracker/available"),
    ("GET", "/api/tracker/available-types"),
    ("GET", "/api/tracker/capabilities"),
    ("GET", "/api/tracker/current"),
    ("GET", "/api/tracker/current-config"),
    ("GET", "/api/tracker/current-status"),
    ("GET", "/api/tracker/output"),
    ("GET", "/api/tracker/schema"),
    ("GET", "/api/video/health"),
    ("GET", "/api/v1/actions/{action_id}"),
    ("GET", "/api/v1/following/status"),
    ("GET", "/api/v1/following/telemetry"),
    ("GET", "/api/v1/runtime/status"),
    ("GET", "/api/v1/telemetry/health"),
    ("GET", "/api/v1/tracking/runtime-status"),
    ("GET", "/api/v1/tracking/telemetry"),
    ("GET", "/api/yolo/active-model"),
    ("GET", "/api/yolo/models"),
    ("GET", "/api/yolo/models/{model_id}/labels"),
    ("GET", "/debug/coordinate_mapping"),
    ("GET", "/stats"),
    ("GET", "/status"),
    ("GET", "/telemetry/follower_data"),
    ("GET", "/telemetry/tracker_data"),
    ("GET", "/video_feed"),
    ("POST", "/api/circuit-breaker/reset-statistics"),
    ("POST", "/api/circuit-breaker/toggle"),
    ("POST", "/api/circuit-breaker/toggle-safety"),
    ("POST", "/api/config/defaults-sync/apply"),
    ("POST", "/api/config/defaults-sync/plan"),
    ("POST", "/api/config/diff"),
    ("POST", "/api/config/import"),
    ("POST", "/api/config/restore/{backup_id}"),
    ("POST", "/api/config/revert"),
    ("POST", "/api/config/revert/{section}"),
    ("POST", "/api/config/revert/{section}/{parameter}"),
    ("POST", "/api/config/validate"),
    ("POST", "/api/follower/restart"),
    ("POST", "/api/follower/switch-profile"),
    ("POST", "/api/gstreamer/toggle"),
    ("POST", "/api/models/download"),
    ("POST", "/api/models/switch"),
    ("POST", "/api/models/upload"),
    ("POST", "/api/osd/color-mode/{mode}"),
    ("POST", "/api/osd/preset/{preset_name}"),
    ("POST", "/api/osd/toggle"),
    ("POST", "/api/recording/include-osd/{enabled}"),
    ("POST", "/api/recording/pause"),
    ("POST", "/api/recording/resume"),
    ("POST", "/api/recording/start"),
    ("POST", "/api/recording/stop"),
    ("POST", "/api/recording/toggle"),
    ("POST", "/api/system/restart"),
    ("POST", "/api/tracker/restart"),
    ("POST", "/api/tracker/set-type"),
    ("POST", "/api/tracker/switch"),
    ("POST", "/api/video/reconnect"),
    ("POST", "/api/v1/actions/offboard-start"),
    ("POST", "/api/v1/actions/operator-abort"),
    ("POST", "/api/v1/sitl/injections/commander-publish-failure"),
    ("POST", "/api/v1/sitl/injections/mavlink2rest-timeout"),
    ("POST", "/api/v1/sitl/injections/mavsdk-disconnect"),
    ("POST", "/api/v1/sitl/injections/tracker-output"),
    ("POST", "/api/v1/sitl/injections/video-stall"),
    ("POST", "/api/yolo/delete/{model_id}"),
    ("POST", "/api/yolo/download"),
    ("POST", "/api/yolo/switch-model"),
    ("POST", "/api/yolo/upload"),
    ("POST", "/commands/cancel_activities"),
    ("POST", "/commands/quit"),
    ("POST", "/commands/redetect"),
    ("POST", "/commands/smart_click"),
    ("POST", "/commands/start_offboard_mode"),
    ("POST", "/commands/start_tracking"),
    ("POST", "/commands/stop_offboard_mode"),
    ("POST", "/commands/stop_tracking"),
    ("POST", "/commands/toggle_segmentation"),
    ("POST", "/commands/toggle_smart_mode"),
    ("PUT", "/api/config/{section}"),
    ("PUT", "/api/config/{section}/{parameter}"),
    ("WEBSOCKET", "/ws/video_feed"),
    ("WEBSOCKET", "/ws/webrtc_signaling"),
}


def _load_string_constants(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {}

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


def _expr_to_data(node, constants=None):
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


def _collect_inline_route_metadata():
    tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    routes = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Call):
            continue

        route_call = node.func
        route_func = route_call.func
        if not isinstance(route_func, ast.Attribute):
            continue
        if route_func.attr not in {"get", "post", "put", "delete", "patch", "websocket"}:
            continue
        if not isinstance(route_func.value, ast.Attribute) or route_func.value.attr != "app":
            continue
        if not route_call.args or not isinstance(route_call.args[0], ast.Constant):
            continue

        keywords = {keyword.arg: keyword.value for keyword in route_call.keywords}
        method = "WEBSOCKET" if route_func.attr == "websocket" else route_func.attr.upper()
        routes.append(
            {
                "method": method,
                "path": route_call.args[0].value,
                "operation_id": _expr_to_data(keywords.get("operation_id")),
                "response_model": _expr_to_data(keywords.get("response_model")),
                "responses": _expr_to_data(keywords.get("responses")),
                "status_code": _expr_to_data(keywords.get("status_code")),
                "tags": _expr_to_data(keywords.get("tags")) or [],
                "deprecated": _expr_to_data(keywords.get("deprecated")),
            }
        )

    return routes


def _collect_api_v1_route_spec_metadata():
    tree = ast.parse(API_V1_ROUTE_REGISTRY.read_text(encoding="utf-8"))
    path_constants = _load_string_constants(API_V1_PATHS)
    routes = []

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
            routes.append(
                {
                    "method": _expr_to_data(keywords.get("method")),
                    "path": _expr_to_data(keywords.get("path"), path_constants),
                    "operation_id": _expr_to_data(keywords.get("operation_id")),
                    "response_model": _expr_to_data(keywords.get("response_model")),
                    "responses": _expr_to_data(keywords.get("responses")),
                    "status_code": _expr_to_data(keywords.get("status_code")),
                    "tags": _expr_to_data(keywords.get("tags")) or [],
                    "deprecated": False,
                }
            )

    return routes


def _collect_route_metadata():
    return _collect_inline_route_metadata() + _collect_api_v1_route_spec_metadata()


def _collect_declared_routes():
    return [
        (route["method"], route["path"])
        for route in _collect_route_metadata()
    ]


def _route_metadata(path):
    for route in _collect_route_metadata():
        if route["path"] == path:
            return route

    raise AssertionError(f"Route registration not found for {path}")


def test_current_route_inventory_is_frozen():
    """Any public route change should be intentional and update this inventory."""
    assert set(_collect_declared_routes()) == EXPECTED_ROUTES


def test_current_route_inventory_has_no_duplicate_method_path_pairs():
    """Duplicate route declarations create ambiguous public API behavior."""
    route_counts = Counter(_collect_declared_routes())
    duplicates = sorted(route for route, count in route_counts.items() if count > 1)

    assert duplicates == []


def test_current_route_inventory_counts_by_method():
    """Method counts document the current pre-/api/v1 surface area."""
    counts = Counter(method for method, _path in _collect_declared_routes())

    assert counts == {
        "DELETE": 2,
        "GET": 72,
        "POST": 53,
        "PUT": 2,
        "WEBSOCKET": 2,
    }


def test_fastapi_handler_delegates_to_api_v1_route_registry_once():
    """Runtime route setup must use the same registry parsed by guardrails."""
    tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    define_routes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "define_routes"
    ]
    assert len(define_routes) == 1

    registry_calls = [
        node
        for node in ast.walk(define_routes[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "register_api_v1_routes"
    ]
    assert len(registry_calls) == 1

    call = registry_calls[0]
    assert len(call.args) == 2
    assert isinstance(call.args[0], ast.Name)
    assert call.args[0].id == "self"
    assert isinstance(call.args[1], ast.Call)
    assert isinstance(call.args[1].func, ast.Name)
    assert call.args[1].func.id == "globals"
    assert call.args[1].args == []
    assert call.keywords == []


def test_api_v1_contracts_are_not_defined_in_fastapi_handler():
    """Typed API/SITL contracts should stay out of the route handler monolith."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    contracts_tree = ast.parse(API_V1_CONTRACTS.read_text(encoding="utf-8"))

    handler_contract_classes = {
        node.name
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.ClassDef)
        and (node.name.startswith("API") or node.name.startswith("SITL"))
    }
    contracts_classes = {
        node.name for node in ast.walk(contracts_tree) if isinstance(node, ast.ClassDef)
    }

    assert handler_contract_classes == set()
    assert API_V1_CONTRACT_CLASS_NAMES <= contracts_classes


def test_api_v1_paths_and_error_builders_are_not_defined_in_fastapi_handler():
    """Route paths and envelope builders should stay out of the handler monolith."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    errors_tree = ast.parse(API_V1_ERRORS.read_text(encoding="utf-8"))
    path_constants = _load_string_constants(API_V1_PATHS)

    handler_assigned_names = {
        target.id
        for node in ast.walk(handler_tree)
        for target in getattr(node, "targets", [])
        if isinstance(target, ast.Name)
    } | {
        target.attr
        for node in ast.walk(handler_tree)
        for target in getattr(node, "targets", [])
        if isinstance(target, ast.Attribute)
    }
    handler_error_model_calls = {
        node.func.id
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "APIErrorResponse"
    }
    error_helper_functions = {
        node.name for node in ast.walk(errors_tree) if isinstance(node, ast.FunctionDef)
    }

    assert handler_assigned_names.isdisjoint(path_constants)
    assert handler_error_model_calls == set()
    assert {
        "build_api_v1_error_response",
        "build_sitl_error_response",
    } <= error_helper_functions


def test_api_v1_action_store_implementation_is_not_defined_in_fastapi_handler():
    """Action storage and typed action bodies should stay out of the handler monolith."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    actions_tree = ast.parse(API_V1_ACTIONS.read_text(encoding="utf-8"))
    legacy_action_state_names = {
        "_action_records",
        "_action_idempotency_index",
        "_action_history_order",
        "_action_store_lock",
        "_action_key_locks",
    }

    handler_assigned_names = {
        target.id
        for node in ast.walk(handler_tree)
        for target in getattr(node, "targets", [])
        if isinstance(target, ast.Name)
    } | {
        target.attr
        for node in ast.walk(handler_tree)
        for target in getattr(node, "targets", [])
        if isinstance(target, ast.Attribute)
    }
    handler_uuid_calls = [
        node
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "uuid4"
    ]
    action_classes = {
        node.name for node in ast.walk(actions_tree) if isinstance(node, ast.ClassDef)
    }
    action_functions = {
        node.name
        for node in ast.walk(actions_tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }
    handler_functions = {
        node.name: node
        for node in ast.walk(handler_tree)
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }
    wrapper_targets = {
        "start_offboard_action": "dispatch_start_offboard_action",
        "_start_offboard_action_unlocked": "dispatch_start_offboard_action_unlocked",
        "operator_abort_action": "dispatch_operator_abort_action",
        "_operator_abort_action_unlocked": "dispatch_operator_abort_action_unlocked",
        "get_action_resource": "dispatch_get_action_resource",
    }

    assert handler_assigned_names.isdisjoint(legacy_action_state_names)
    assert handler_uuid_calls == []
    assert "ApiActionStore" in action_classes
    assert {
        "attach_legacy_action_audit",
        "build_action_precondition_failed_response",
        "ensure_api_action_store",
        "get_action_resource",
        "new_api_action_record",
        "operator_abort_action",
        "operator_abort_action_unlocked",
        "start_offboard_action",
        "start_offboard_action_unlocked",
    } <= action_functions
    for wrapper_name, target_name in wrapper_targets.items():
        wrapper = handler_functions[wrapper_name]
        assert len(wrapper.body) == 1
        statement = wrapper.body[0]
        assert isinstance(statement, ast.Return)
        call = statement.value
        if isinstance(call, ast.Await):
            call = call.value
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Name)
        assert call.func.id == target_name


def test_api_v1_snapshot_builders_are_not_defined_in_fastapi_handler():
    """Read-state snapshot construction should stay out of the route handler."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    snapshots_tree = ast.parse(API_V1_SNAPSHOTS.read_text(encoding="utf-8"))
    expected_snapshot_functions = {
        "classify_following_commander_degradation",
        "classify_inactive_following_commander_issue",
        "classify_runtime_status",
        "coerce_mapping",
        "first_present",
        "get_active_following_setpoint_handler",
        "get_circuit_breaker_snapshot",
        "get_following_command_publication_status",
        "get_following_profile_status",
        "get_following_status_snapshot",
        "get_following_telemetry_snapshot",
        "get_legacy_follower_telemetry_snapshot",
        "get_legacy_runtime_status_snapshot",
        "get_legacy_tracker_telemetry_snapshot",
        "get_runtime_status_snapshot",
        "get_tracker_following_readiness",
        "get_tracker_runtime_status_snapshot",
        "get_tracking_telemetry_snapshot",
        "optional_float_list",
        "position_3d_projection",
        "sanitize_tracking_field_value",
        "serialize_command_intent",
        "tracker_output_to_field_map",
    }
    wrapper_targets = {
        "_classify_following_commander_degradation": (
            "classify_following_commander_degradation"
        ),
        "_classify_inactive_following_commander_issue": (
            "classify_inactive_following_commander_issue"
        ),
        "_classify_runtime_status": "classify_runtime_status",
        "_coerce_mapping": "coerce_mapping",
        "_first_present": "first_present",
        "_get_active_following_setpoint_handler": (
            "get_active_following_setpoint_handler"
        ),
        "_get_circuit_breaker_snapshot": "get_circuit_breaker_snapshot",
        "_get_following_command_publication_status": (
            "get_following_command_publication_status"
        ),
        "_get_following_profile_status": "get_following_profile_status",
        "_get_following_status_snapshot": "get_following_status_snapshot",
        "_get_following_telemetry_snapshot": "get_following_telemetry_snapshot",
        "_get_legacy_follower_telemetry_snapshot": (
            "get_legacy_follower_telemetry_snapshot"
        ),
        "_get_legacy_runtime_status_snapshot": "get_legacy_runtime_status_snapshot",
        "_get_legacy_tracker_telemetry_snapshot": (
            "get_legacy_tracker_telemetry_snapshot"
        ),
        "_get_runtime_status_snapshot": "get_runtime_status_snapshot",
        "_get_tracker_following_readiness": "get_tracker_following_readiness",
        "_get_tracker_runtime_status_snapshot": "get_tracker_runtime_status_snapshot",
        "_get_tracking_telemetry_snapshot": "get_tracking_telemetry_snapshot",
        "_optional_float_list": "optional_float_list",
        "_position_3d_projection": "position_3d_projection",
        "_sanitize_tracking_field_value": "sanitize_tracking_field_value",
        "_serialize_command_intent": "serialize_command_intent",
        "_tracker_output_to_field_map": "tracker_output_to_field_map",
    }
    snapshot_claim_constants = {
        "FOLLOWING_STATUS_CLAIM_BOUNDARY",
        "FOLLOWING_TELEMETRY_CLAIM_BOUNDARY",
        "RUNTIME_STATUS_CLAIM_BOUNDARY",
        "TRACKING_TELEMETRY_CLAIM_BOUNDARY",
    }

    snapshot_functions = {
        node.name for node in ast.walk(snapshots_tree) if isinstance(node, ast.FunctionDef)
    }
    handler_imported_contract_names = {
        alias.name
        for node in handler_tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "classes.api_v1_contracts"
        for alias in node.names
    }

    assert expected_snapshot_functions <= snapshot_functions
    assert handler_imported_contract_names.isdisjoint(snapshot_claim_constants)

    handler_functions = {
        node.name: node for node in ast.walk(handler_tree) if isinstance(node, ast.FunctionDef)
    }
    for wrapper_name, target_name in wrapper_targets.items():
        wrapper = handler_functions[wrapper_name]
        assert len(wrapper.body) == 1
        return_stmt = wrapper.body[0]
        assert isinstance(return_stmt, ast.Return)
        assert isinstance(return_stmt.value, ast.Call)
        assert isinstance(return_stmt.value.func, ast.Name)
        assert return_stmt.value.func.id == target_name


def test_api_v1_telemetry_health_helper_is_not_defined_in_fastapi_handler():
    """Typed telemetry-health fallback payloads should stay out of the handler."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    telemetry_tree = ast.parse(API_V1_TELEMETRY.read_text(encoding="utf-8"))

    handler_imported_contract_names = {
        alias.name
        for node in handler_tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "classes.api_v1_contracts"
        for alias in node.names
    }
    telemetry_functions = {
        node.name for node in ast.walk(telemetry_tree) if isinstance(node, ast.FunctionDef)
    }
    handler_functions = {
        node.name: node for node in ast.walk(handler_tree) if isinstance(node, ast.AsyncFunctionDef)
    }
    get_telemetry_health = handler_functions["get_telemetry_health"]
    telemetry_helper_calls = [
        node
        for node in ast.walk(get_telemetry_health)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_telemetry_health_snapshot"
    ]
    handler_string_literals = {
        node.value
        for node in ast.walk(get_telemetry_health)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert "get_telemetry_health_snapshot" in telemetry_functions
    assert "MAVLINK_TELEMETRY_CLAIM_BOUNDARY" not in handler_imported_contract_names
    assert len(telemetry_helper_calls) == 1
    assert "MAVLink data manager is not configured" not in handler_string_literals


def test_api_v1_sitl_injection_helpers_are_not_defined_in_fastapi_handler():
    """Validation-stimulus construction and dispatch should stay out of the handler."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    sitl_tree = ast.parse(API_V1_SITL.read_text(encoding="utf-8"))
    expected_sitl_functions = {
        "frame_status_from_sitl_video_stall",
        "inject_sitl_commander_publish_failure",
        "inject_sitl_mavlink2rest_timeout",
        "inject_sitl_mavsdk_disconnect",
        "inject_sitl_tracker_output",
        "inject_sitl_video_stall",
        "parse_tracker_data_type",
        "sitl_error_response",
        "sitl_injections_enabled",
        "tracker_output_from_sitl_injection",
    }
    wrapper_targets = {
        "_sitl_injections_enabled": "sitl_injections_enabled",
        "_sitl_error_response": "sitl_error_response",
        "_parse_tracker_data_type": "parse_tracker_data_type",
        "_tracker_output_from_sitl_injection": "tracker_output_from_sitl_injection",
        "_frame_status_from_sitl_video_stall": "frame_status_from_sitl_video_stall",
        "inject_sitl_tracker_output": "dispatch_sitl_tracker_output",
        "inject_sitl_video_stall": "dispatch_sitl_video_stall",
        "inject_sitl_commander_publish_failure": (
            "dispatch_sitl_commander_publish_failure"
        ),
        "inject_sitl_mavsdk_disconnect": "dispatch_sitl_mavsdk_disconnect",
        "inject_sitl_mavlink2rest_timeout": "dispatch_sitl_mavlink2rest_timeout",
    }
    disallowed_handler_strings = {
        "PIXEAGLE_ENABLE_SITL_INJECTIONS",
        "SITL_INJECTIONS_DISABLED",
        "SITL_INJECTION_UNAVAILABLE",
        "SITL_INJECTION_REJECTED",
        "inject_tracker_output_for_validation",
        "inject_video_stall_for_validation",
        "inject_commander_publish_failure_for_validation",
        "inject_mavsdk_disconnect_for_validation",
        "inject_mavlink2rest_timeout_for_validation",
        "pixeagle_local_only",
    }

    sitl_functions = {
        node.name for node in ast.walk(sitl_tree) if isinstance(node, ast.FunctionDef)
    } | {
        node.name for node in ast.walk(sitl_tree) if isinstance(node, ast.AsyncFunctionDef)
    }
    handler_functions = {
        node.name: node
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    handler_string_literals = {
        node.value
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    handler_tracker_output_calls = [
        node
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "TrackerOutput"
    ]

    assert expected_sitl_functions <= sitl_functions
    assert handler_string_literals.isdisjoint(disallowed_handler_strings)
    assert handler_tracker_output_calls == []

    for wrapper_name, target_name in wrapper_targets.items():
        wrapper = handler_functions[wrapper_name]
        assert len(wrapper.body) == 1
        return_stmt = wrapper.body[0]
        assert isinstance(return_stmt, ast.Return)
        value = return_stmt.value
        if isinstance(value, ast.Await):
            value = value.value
        assert isinstance(value, ast.Call)
        assert isinstance(value.func, ast.Name)
        assert value.func.id == target_name


def test_api_v1_route_registry_uses_canonical_path_constants():
    """Typed route specs should not duplicate /api/v1 path strings inline."""
    tree = ast.parse(API_V1_ROUTE_REGISTRY.read_text(encoding="utf-8"))
    path_constants = _load_string_constants(API_V1_PATHS)
    path_names = {
        name for name, value in path_constants.items() if value.startswith("/api/v1/")
    }
    route_path_keywords = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "ApiV1RouteSpec":
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        route_path_keywords.append(keywords.get("path"))

    assert len(route_path_keywords) == len(API_V1_ROUTE_SPECS)
    assert route_path_keywords
    for path_keyword in route_path_keywords:
        assert isinstance(path_keyword, ast.Name)
        assert path_keyword.id in path_names


def test_api_v1_error_envelope_path_predicate_matches_current_route_families():
    """Validation errors should use typed envelopes only for reviewed /api/v1 paths."""
    expected_typed_paths = (
        set(API_V1_PROCESS_LOCAL_READ_ONLY_PATHS)
        | set(SITL_VALIDATION_INJECTION_PATHS)
        | {
            API_V1_ACTION_OFFBOARD_START_PATH,
            API_V1_ACTION_OPERATOR_ABORT_PATH,
            API_V1_ACTION_RESOURCE_PATH,
        }
    )

    for path in expected_typed_paths:
        assert uses_typed_api_error_envelope(path) is True

    assert uses_typed_api_error_envelope("/status") is False
    assert uses_typed_api_error_envelope("/telemetry/follower_data") is False


def test_api_v1_action_routes_have_typed_api_metadata():
    """Typed control actions must be explicit /api/v1 resources."""
    expectations = {
        "/api/v1/actions/offboard-start": (
            "start_offboard_action",
            "APIActionResponse",
            True,
            "ACTION_ROUTE_RESPONSES",
        ),
        "/api/v1/actions/operator-abort": (
            "operator_abort_action",
            "APIActionResponse",
            True,
            "ACTION_ROUTE_RESPONSES",
        ),
        "/api/v1/actions/{action_id}": (
            "get_action_resource",
            "APIActionResponse",
            False,
            "ACTION_ERROR_RESPONSES",
        ),
    }
    for path, (
        operation_id,
        response_model,
        expects_accepted,
        responses_name,
    ) in expectations.items():
        route = _route_metadata(path)

        assert route["operation_id"] == operation_id
        assert route["response_model"] == response_model
        assert route["responses"] == responses_name
        assert route["tags"] == ["actions"]
        if expects_accepted:
            assert route["status_code"] == "status.HTTP_202_ACCEPTED"
        else:
            assert route["status_code"] is None


def test_api_v1_route_registry_registers_specs_without_runtime_app():
    """Registry helper should preserve route order and resolve metadata names."""

    class FakeApp:
        def __init__(self):
            self.routes = []

        def get(self, path, **kwargs):
            return self._register("GET", path, kwargs)

        def post(self, path, **kwargs):
            return self._register("POST", path, kwargs)

        def _register(self, method, path, kwargs):
            def decorator(handler):
                self.routes.append((method, path, kwargs, handler.__name__))
                return handler

            return decorator

    class FakeHandler:
        def __init__(self):
            self.app = FakeApp()

    def make_handler(name):
        def handler():
            return name

        handler.__name__ = name
        return handler

    handler = FakeHandler()
    for spec in API_V1_ROUTE_SPECS:
        setattr(handler, spec.handler, make_handler(spec.handler))

    namespace = {
        "status": SimpleNamespace(HTTP_202_ACCEPTED=202),
    }
    for spec in API_V1_ROUTE_SPECS:
        namespace[spec.response_model] = object()
        namespace[spec.responses] = object()

    register_api_v1_routes(handler, namespace)

    assert [
        (method, path, route_handler)
        for method, path, _kwargs, route_handler in handler.app.routes
    ] == [
        (spec.method, spec.path, spec.handler)
        for spec in API_V1_ROUTE_SPECS
    ]
    for spec, (_method, _path, kwargs, _handler) in zip(
        API_V1_ROUTE_SPECS,
        handler.app.routes,
        strict=True,
    ):
        assert kwargs["response_model"] is namespace[spec.response_model]
        assert kwargs["responses"] is namespace[spec.responses]
        assert kwargs["operation_id"] == spec.operation_id
        assert kwargs["tags"] == list(spec.tags)
        if spec.status_code is None:
            assert "status_code" not in kwargs
        else:
            assert kwargs["status_code"] == 202


def test_api_v1_telemetry_health_route_has_typed_api_metadata():
    """Typed telemetry health must be an explicit /api/v1 resource."""
    route = _route_metadata("/api/v1/telemetry/health")

    assert route["operation_id"] == "get_telemetry_health"
    assert route["response_model"] == "APITelemetryHealthResponse"
    assert route["responses"] == "TELEMETRY_HEALTH_ERROR_RESPONSES"
    assert route["tags"] == ["telemetry"]
    assert route["status_code"] is None


def test_api_v1_runtime_status_route_has_typed_api_metadata():
    """Typed runtime status must be an explicit /api/v1 resource."""
    route = _route_metadata("/api/v1/runtime/status")

    assert route["operation_id"] == "get_runtime_status"
    assert route["response_model"] == "APIRuntimeStatusResponse"
    assert route["responses"] == "RUNTIME_STATUS_ERROR_RESPONSES"
    assert route["tags"] == ["runtime"]
    assert route["status_code"] is None


def test_api_v1_following_status_route_has_typed_api_metadata():
    """Typed following status must be an explicit /api/v1 resource."""
    route = _route_metadata("/api/v1/following/status")

    assert route["operation_id"] == "get_following_status"
    assert route["response_model"] == "APIFollowingStatusResponse"
    assert route["responses"] == "FOLLOWING_STATUS_ERROR_RESPONSES"
    assert route["tags"] == ["following"]
    assert route["status_code"] is None


def test_api_v1_following_telemetry_route_has_typed_api_metadata():
    """Typed following telemetry must be an explicit /api/v1 resource."""
    route = _route_metadata("/api/v1/following/telemetry")

    assert route["operation_id"] == "get_following_telemetry"
    assert route["response_model"] == "APIFollowingTelemetryResponse"
    assert route["responses"] == "FOLLOWING_TELEMETRY_ERROR_RESPONSES"
    assert route["tags"] == ["following"]
    assert route["status_code"] is None


def test_api_v1_tracking_runtime_status_route_has_typed_api_metadata():
    """Typed tracker runtime status must be an explicit /api/v1 resource."""
    route = _route_metadata("/api/v1/tracking/runtime-status")

    assert route["operation_id"] == "get_tracking_runtime_status"
    assert route["response_model"] == "APITrackingRuntimeStatusResponse"
    assert route["responses"] == "TRACKING_RUNTIME_STATUS_ERROR_RESPONSES"
    assert route["tags"] == ["tracking"]
    assert route["status_code"] is None


def test_api_v1_tracking_telemetry_route_has_typed_api_metadata():
    """Typed tracker telemetry must be an explicit /api/v1 resource."""
    route = _route_metadata("/api/v1/tracking/telemetry")

    assert route["operation_id"] == "get_tracking_telemetry"
    assert route["response_model"] == "APITrackingTelemetryResponse"
    assert route["responses"] == "TRACKING_TELEMETRY_ERROR_RESPONSES"
    assert route["tags"] == ["tracking"]
    assert route["status_code"] is None


def test_legacy_control_routes_are_deprecated_compatibility_aliases():
    """Legacy dangerous command routes must be visibly deprecated."""
    expectations = {
        "/commands/start_offboard_mode": "legacy_start_offboard_mode",
        "/commands/cancel_activities": "legacy_cancel_activities",
    }
    for path, operation_id in expectations.items():
        route = _route_metadata(path)

        assert route["deprecated"] is True
        assert route["operation_id"] == operation_id
        assert route["tags"] == ["legacy-commands"]


def test_sitl_injection_route_has_typed_api_metadata():
    """The validation-only /api/v1 route must keep its typed contract metadata."""
    expectations = {
        "/api/v1/sitl/injections/tracker-output": (
            "inject_sitl_tracker_output",
            "SITLTrackerInjectionResponse",
        ),
        "/api/v1/sitl/injections/video-stall": (
            "inject_sitl_video_stall",
            "SITLVideoStallResponse",
        ),
        "/api/v1/sitl/injections/commander-publish-failure": (
            "inject_sitl_commander_publish_failure",
            "SITLCommanderPublishFailureResponse",
        ),
        "/api/v1/sitl/injections/mavlink2rest-timeout": (
            "inject_sitl_mavlink2rest_timeout",
            "SITLMavlink2RestTimeoutResponse",
        ),
        "/api/v1/sitl/injections/mavsdk-disconnect": (
            "inject_sitl_mavsdk_disconnect",
            "SITLMavsdkDisconnectResponse",
        ),
    }
    for path, (operation_id, response_model) in expectations.items():
        route = _route_metadata(path)

        assert route["operation_id"] == operation_id
        assert route["response_model"] == response_model
        assert route["status_code"] == "status.HTTP_202_ACCEPTED"
        assert route["responses"] == "SITL_ERROR_RESPONSES"
        assert route["tags"] == ["sitl-validation"]
