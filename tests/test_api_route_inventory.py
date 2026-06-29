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
    API_V1_ACTION_OFFBOARD_STOP_PATH,
    API_V1_ACTION_OPERATOR_ABORT_PATH,
    API_V1_ACTION_RESOURCE_PATH,
    API_V1_ACTION_SEGMENTATION_TOGGLE_PATH,
    API_V1_ACTION_SMART_CLICK_PATH,
    API_V1_ACTION_SMART_MODE_TOGGLE_PATH,
    API_V1_ACTION_TRACKING_REDETECT_PATH,
    API_V1_ACTION_TRACKING_START_PATH,
    API_V1_ACTION_TRACKING_STOP_PATH,
    API_V1_AUTH_LOGIN_PATH,
    API_V1_AUTH_LOGOUT_PATH,
    API_V1_AUTH_PATHS,
    API_V1_AUTH_SESSION_PATH,
    API_V1_PROCESS_LOCAL_READ_ONLY_PATHS,
    API_V1_STREAMING_MEDIA_HEALTH_PATH,
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
API_V1_AUTH_ROUTES = REPO_ROOT / "src" / "classes" / "api_v1_auth_routes.py"
API_LEGACY_CONTROL_ROUTES = (
    REPO_ROOT / "src" / "classes" / "api_legacy_control_routes.py"
)
API_LEGACY_CONFIG_SYNC = REPO_ROOT / "src" / "classes" / "api_legacy_config_sync.py"
API_LEGACY_CONFIG_ROUTES = (
    REPO_ROOT / "src" / "classes" / "api_legacy_config_routes.py"
)
API_LEGACY_FOLLOWER_ROUTES = (
    REPO_ROOT / "src" / "classes" / "api_legacy_follower_routes.py"
)
API_LEGACY_GSTREAMER_ROUTES = (
    REPO_ROOT / "src" / "classes" / "api_legacy_gstreamer_routes.py"
)
API_LEGACY_MEDIA_ROUTES = (
    REPO_ROOT / "src" / "classes" / "api_legacy_media_routes.py"
)
API_LEGACY_MODEL_ROUTES = (
    REPO_ROOT / "src" / "classes" / "api_legacy_model_routes.py"
)
API_LEGACY_OSD_ROUTES = (
    REPO_ROOT / "src" / "classes" / "api_legacy_osd_routes.py"
)
API_LEGACY_RECORDING_ROUTES = (
    REPO_ROOT / "src" / "classes" / "api_legacy_recording_routes.py"
)
API_LEGACY_SAFETY_ROUTES = (
    REPO_ROOT / "src" / "classes" / "api_legacy_safety_routes.py"
)
API_V1_READ_ROUTES = REPO_ROOT / "src" / "classes" / "api_v1_read_routes.py"
API_V1_SNAPSHOTS = REPO_ROOT / "src" / "classes" / "api_v1_snapshots.py"
API_V1_TELEMETRY = REPO_ROOT / "src" / "classes" / "api_v1_telemetry.py"
API_V1_STREAMS = REPO_ROOT / "src" / "classes" / "api_v1_streams.py"
API_V1_SITL = REPO_ROOT / "src" / "classes" / "api_v1_sitl.py"

API_V1_CONTRACT_CLASS_NAMES = {
    "APIActionAuditEvent",
    "APIActionRequest",
    "APIActionResponse",
    "APITrackingBoundingBox",
    "APITrackingClickPosition",
    "APITrackingSmartClickRequest",
    "APITrackingStartRequest",
    "APIAuthLoginRequest",
    "APIAuthLoginResponse",
    "APIAuthLogoutResponse",
    "APIAuthPrincipal",
    "APIAuthSessionResponse",
    "APIErrorResponse",
    "APIFollowingCommandPublicationStatus",
    "APIFollowingProfileStatus",
    "APIFollowingStatusResponse",
    "APIFollowingTelemetryResponse",
    "APIRuntimeModesStatus",
    "APIRuntimeStatusResponse",
    "APIRuntimeSubsystemStatus",
    "APIStreamingConfigSummary",
    "APIStreamingFrameHealth",
    "APIStreamingMediaHealthResponse",
    "APIStreamingSecurityBoundary",
    "APIStreamingTransportHealth",
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
    ("GET", "/api/v1/auth/session"),
    ("GET", "/api/v1/actions/{action_id}"),
    ("GET", "/api/v1/following/status"),
    ("GET", "/api/v1/following/telemetry"),
    ("GET", "/api/v1/runtime/status"),
    ("GET", "/api/v1/streams/media-health"),
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
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/actions/offboard-start"),
    ("POST", "/api/v1/actions/offboard-stop"),
    ("POST", "/api/v1/actions/operator-abort"),
    ("POST", "/api/v1/actions/segmentation-toggle"),
    ("POST", "/api/v1/actions/smart-click"),
    ("POST", "/api/v1/actions/smart-mode-toggle"),
    ("POST", "/api/v1/actions/tracking-redetect"),
    ("POST", "/api/v1/actions/tracking-start"),
    ("POST", "/api/v1/actions/tracking-stop"),
    ("POST", "/api/v1/sitl/injections/commander-publish-failure"),
    ("POST", "/api/v1/sitl/injections/mavlink2rest-timeout"),
    ("POST", "/api/v1/sitl/injections/mavsdk-disconnect"),
    ("POST", "/api/v1/sitl/injections/tracker-output"),
    ("POST", "/api/v1/sitl/injections/video-stall"),
    ("POST", "/api/yolo/delete/{model_id}"),
    ("POST", "/api/yolo/download"),
    ("POST", "/api/yolo/switch-model"),
    ("POST", "/api/yolo/upload"),
    ("POST", "/commands/quit"),
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
        "GET": 74,
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
        "stop_offboard_action": "dispatch_stop_offboard_action",
        "_stop_offboard_action_unlocked": "dispatch_stop_offboard_action_unlocked",
        "operator_abort_action": "dispatch_operator_abort_action",
        "_operator_abort_action_unlocked": "dispatch_operator_abort_action_unlocked",
        "segmentation_toggle_action": "dispatch_segmentation_toggle_action",
        "_segmentation_toggle_action_unlocked": (
            "dispatch_segmentation_toggle_action_unlocked"
        ),
        "smart_click_action": "dispatch_smart_click_action",
        "_smart_click_action_unlocked": "dispatch_smart_click_action_unlocked",
        "smart_mode_toggle_action": "dispatch_smart_mode_toggle_action",
        "_smart_mode_toggle_action_unlocked": (
            "dispatch_smart_mode_toggle_action_unlocked"
        ),
        "tracking_redetect_action": "dispatch_tracking_redetect_action",
        "_tracking_redetect_action_unlocked": (
            "dispatch_tracking_redetect_action_unlocked"
        ),
        "tracking_start_action": "dispatch_tracking_start_action",
        "_tracking_start_action_unlocked": "dispatch_tracking_start_action_unlocked",
        "tracking_stop_action": "dispatch_tracking_stop_action",
        "_tracking_stop_action_unlocked": "dispatch_tracking_stop_action_unlocked",
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
        "segmentation_toggle_action",
        "segmentation_toggle_action_unlocked",
        "smart_click_action",
        "smart_click_action_unlocked",
        "smart_mode_toggle_action",
        "smart_mode_toggle_action_unlocked",
        "start_offboard_action",
        "start_offboard_action_unlocked",
        "stop_offboard_action",
        "stop_offboard_action_unlocked",
        "tracking_redetect_action",
        "tracking_redetect_action_unlocked",
        "tracking_start_action",
        "tracking_start_action_unlocked",
        "tracking_stop_action",
        "tracking_stop_action_unlocked",
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
        assert len(call.args) >= 1
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


def test_legacy_control_route_bodies_are_not_defined_in_fastapi_handler():
    """Legacy Offboard/cancel route execution should stay out of the handler."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    legacy_routes_tree = ast.parse(
        API_LEGACY_CONTROL_ROUTES.read_text(encoding="utf-8")
    )
    expected_legacy_functions = {
        "cancel_activities",
        "start_offboard_mode",
        "stop_offboard_mode",
    }
    wrapper_targets = {
        "_execute_operator_abort_action": "dispatch_operator_abort_executor",
        "_execute_offboard_start_action": "dispatch_offboard_start_executor",
        "_execute_offboard_stop_action": "dispatch_offboard_stop_executor",
    }
    disallowed_handler_strings = {
        "Attempting emergency cleanup of OffboardCommander",
        "Error in cancel_activities",
        "Error in stop_offboard_mode",
        "Follower was already inactive",
        "Offboard mode stop completed",
        "Offboard stop command returned with following still active",
        "PX4 interface not initialized",
        "Tracker output is not usable for following",
        "Pre-flight validation failed",
        "Offboard mode did not become active",
    }

    legacy_functions = {
        node.name
        for node in ast.walk(legacy_routes_tree)
        if isinstance(node, ast.AsyncFunctionDef)
    }
    legacy_string_literals = {
        node.value
        for node in ast.walk(legacy_routes_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
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

    assert expected_legacy_functions <= legacy_functions
    for marker in disallowed_handler_strings:
        assert any(marker in literal for literal in legacy_string_literals)
        assert not any(marker in literal for literal in handler_string_literals)

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
        assert len(call.args) == 1
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


def test_legacy_config_sync_helpers_are_not_defined_in_fastapi_handler():
    """Defaults-sync report/plan helpers should stay out of the handler monolith."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    config_sync_tree = ast.parse(API_LEGACY_CONFIG_SYNC.read_text(encoding="utf-8"))
    config_routes_tree = ast.parse(API_LEGACY_CONFIG_ROUTES.read_text(encoding="utf-8"))
    expected_classes = {
        "ConfigSyncOperation",
        "ConfigSyncPlanRequest",
    }
    expected_functions = {
        "build_defaults_sync_report",
        "build_defaults_sync_plan",
    }
    disallowed_handler_functions = {
        "_build_defaults_sync_report",
        "_build_defaults_sync_plan",
    }
    disallowed_handler_strings = {
        "Unsupported op_type",
        "already exists; skipping ADD_NEW",
        "No default value found for",
        "is not in schema or defaults",
        "missing in current config; skipping ARCHIVE_REMOVE",
        "defaults_snapshot_saved_at",
    }

    config_sync_classes = {
        node.name for node in ast.walk(config_sync_tree) if isinstance(node, ast.ClassDef)
    }
    config_sync_functions = {
        node.name
        for node in ast.walk(config_sync_tree)
        if isinstance(node, ast.FunctionDef)
    }
    handler_functions = {
        node.name
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    handler_string_literals = {
        node.value
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert expected_classes <= config_sync_classes
    assert expected_functions <= config_sync_functions
    assert handler_functions.isdisjoint(disallowed_handler_functions)
    for marker in disallowed_handler_strings:
        assert not any(marker in literal for literal in handler_string_literals)

    handler_helper_calls = [
        node
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in expected_functions
    ]
    config_route_helper_calls = [
        node
        for node in ast.walk(config_routes_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in expected_functions
    ]
    assert not handler_helper_calls
    assert {call.func.id for call in config_route_helper_calls} == expected_functions


def test_legacy_config_route_bodies_are_not_defined_in_fastapi_handler():
    """Legacy config route bodies should stay out of the handler."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    config_routes_tree = ast.parse(API_LEGACY_CONFIG_ROUTES.read_text(encoding="utf-8"))
    expected_classes = {
        "ConfigParameterUpdate",
        "ConfigSectionUpdate",
        "ConfigImportRequest",
    }
    expected_functions = {
        "get_config_schema",
        "get_config_section_schema",
        "get_config_sections",
        "get_config_categories",
        "get_current_config",
        "get_current_config_section",
        "get_default_config",
        "get_default_config_section",
        "update_config_parameter",
        "update_config_section",
        "validate_config_value",
        "get_config_diff",
        "compare_configs",
        "get_defaults_sync",
        "plan_defaults_sync",
        "apply_defaults_sync",
        "revert_config_to_default",
        "revert_section_to_default",
        "revert_parameter_to_default",
        "get_config_backup_history",
        "restore_config_backup",
        "export_config",
        "import_config",
        "search_config_parameters",
        "get_config_audit_log",
    }
    wrapper_targets = {
        "get_config_schema": "dispatch_get_config_schema",
        "get_config_section_schema": "dispatch_get_config_section_schema",
        "get_config_sections": "dispatch_get_config_sections",
        "get_config_categories": "dispatch_get_config_categories",
        "get_current_config": "dispatch_get_current_config",
        "get_current_config_section": "dispatch_get_current_config_section",
        "get_default_config": "dispatch_get_default_config",
        "get_default_config_section": "dispatch_get_default_config_section",
        "update_config_parameter": "dispatch_update_config_parameter",
        "update_config_section": "dispatch_update_config_section",
        "validate_config_value": "dispatch_validate_config_value",
        "get_config_diff": "dispatch_get_config_diff",
        "compare_configs": "dispatch_compare_configs",
        "get_defaults_sync": "dispatch_get_defaults_sync",
        "plan_defaults_sync": "dispatch_plan_defaults_sync",
        "apply_defaults_sync": "dispatch_apply_defaults_sync",
        "revert_config_to_default": "dispatch_revert_config_to_default",
        "revert_section_to_default": "dispatch_revert_section_to_default",
        "revert_parameter_to_default": "dispatch_revert_parameter_to_default",
        "get_config_backup_history": "dispatch_get_config_backup_history",
        "restore_config_backup": "dispatch_restore_config_backup",
        "export_config": "dispatch_export_config",
        "import_config": "dispatch_import_config",
        "search_config_parameters": "dispatch_search_config_parameters",
        "get_config_audit_log": "dispatch_get_config_audit_log",
    }
    disallowed_handler_strings = {
        "Error getting config schema",
        "Section '",
        "Error getting section schema",
        "Error getting config diff",
        "compare_config",
        "baseline_initialized",
        "Error planning defaults sync",
        "Config hot-reloaded after updating",
        "highest reload_tier",
        "section and parameter are required",
        "Failed to save config after applying sync plan",
        "Config sync applied but reload failed",
        "Error applying defaults sync",
        "Parameter reverted to default",
        "Error getting backup history",
        "Failed to reload after backup restore",
        "changes_only",
        "Error importing config",
        "modified_only",
        "Error getting audit log",
    }

    config_route_classes = {
        node.name
        for node in ast.walk(config_routes_tree)
        if isinstance(node, ast.ClassDef)
    }
    config_route_functions = {
        node.name
        for node in ast.walk(config_routes_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    config_route_strings = {
        node.value
        for node in ast.walk(config_routes_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    handler_functions = {
        node.name: node
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    handler_classes = {
        node.name for node in ast.walk(handler_tree) if isinstance(node, ast.ClassDef)
    }
    handler_string_literals = {
        node.value
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert expected_classes <= config_route_classes
    assert expected_functions <= config_route_functions
    assert not (expected_classes & handler_classes)
    for marker in disallowed_handler_strings:
        assert any(marker in literal for literal in config_route_strings)
        assert not any(marker in literal for literal in handler_string_literals)

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
        assert call.args
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


def test_legacy_safety_route_bodies_are_not_defined_in_fastapi_handler():
    """Legacy safety and read-only circuit-breaker bodies stay out of the handler."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    safety_routes_tree = ast.parse(API_LEGACY_SAFETY_ROUTES.read_text(encoding="utf-8"))
    expected_functions = {
        "_safety_manager_or_none",
        "get_circuit_breaker_status",
        "get_circuit_breaker_statistics",
        "get_safety_config",
        "get_follower_safety_limits",
        "get_effective_limits",
        "get_relevant_sections",
    }
    wrapper_targets = {
        "get_circuit_breaker_status": "dispatch_get_circuit_breaker_status",
        "get_circuit_breaker_statistics": (
            "dispatch_get_circuit_breaker_statistics"
        ),
        "get_safety_config": "dispatch_get_safety_config",
        "get_follower_safety_limits": "dispatch_get_follower_safety_limits",
        "get_effective_limits": "dispatch_get_effective_limits",
        "get_relevant_sections": "dispatch_get_relevant_sections",
    }
    disallowed_handler_strings = {
        "FollowerCircuitBreaker module could not be imported",
        "Circuit breaker active - commands logged not executed",
        "data_freshness",
        "unique_followers_tested",
        "Error getting circuit breaker statistics",
        "SafetyManager not available",
        "Error getting safety config",
        "MAX_VELOCITY_FORWARD",
        "altitude_safety_enabled",
        "Error getting follower safety limits",
        "available_followers",
        "Error getting effective limits",
        "gm_velocity_vector",
        "Error getting relevant sections",
    }

    safety_route_functions = {
        node.name
        for node in ast.walk(safety_routes_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    safety_route_strings = {
        node.value
        for node in ast.walk(safety_routes_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
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

    assert expected_functions <= safety_route_functions
    for marker in disallowed_handler_strings:
        assert any(marker in literal for literal in safety_route_strings)
        assert not any(marker in literal for literal in handler_string_literals)

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
        assert call.args
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


def test_legacy_media_route_bodies_are_not_defined_in_fastapi_handler():
    """Legacy bounded media route bodies should stay out of the handler."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    media_routes_tree = ast.parse(API_LEGACY_MEDIA_ROUTES.read_text(encoding="utf-8"))
    expected_functions = {
        "get_streaming_status",
        "get_streaming_stats",
        "get_video_health",
        "reconnect_video",
        "video_feed",
    }
    wrapper_targets = {
        "get_streaming_status": "dispatch_get_streaming_status",
        "get_streaming_stats": "dispatch_get_streaming_stats",
        "get_video_health": "dispatch_get_video_health",
        "reconnect_video": "dispatch_reconnect_video",
        "video_feed": "dispatch_video_feed",
    }
    disallowed_handler_strings = {
        "active_method",
        "adaptive_quality_enabled",
        "websocket_clients",
        "Could not read OSD pipeline stats",
        "obb_pipeline",
        "Error in get_video_health",
        "Video handler not initialized",
        "Video reconnect succeeded",
        "Video reconnect attempted but source still unavailable",
        "Error in reconnect_video",
        "Frame generator using FramePublisher and AdaptiveQualityEngine",
        "Frame encoding error",
        "multipart/x-mixed-replace; boundary=frame",
    }

    media_route_functions = {
        node.name
        for node in ast.walk(media_routes_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    media_route_classes = {
        node.name for node in ast.walk(media_routes_tree) if isinstance(node, ast.ClassDef)
    }
    media_route_strings = {
        node.value
        for node in ast.walk(media_routes_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    handler_functions = {
        node.name: node
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    handler_classes = {
        node.name for node in ast.walk(handler_tree) if isinstance(node, ast.ClassDef)
    }
    handler_string_literals = {
        node.value
        for node in ast.walk(handler_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert expected_functions <= media_route_functions
    assert "SessionBoundStreamingResponse" in media_route_classes
    assert "SessionBoundStreamingResponse" not in handler_classes
    assert "video_feed_websocket_optimized" not in media_route_functions
    for marker in disallowed_handler_strings:
        assert any(marker in literal for literal in media_route_strings)
        assert not any(marker in literal for literal in handler_string_literals)

    for wrapper_name, target_name in wrapper_targets.items():
        wrapper = handler_functions[wrapper_name]
        body = wrapper.body
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        assert len(body) == 1
        statement = body[0]
        assert isinstance(statement, ast.Return)
        call = statement.value
        if isinstance(call, ast.Await):
            call = call.value
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Name)
        assert call.func.id == target_name
        assert call.args
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


def test_legacy_model_route_bodies_are_not_defined_in_fastapi_handler():
    """Legacy model/yolo route bodies should stay out of the handler monolith."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    model_routes_tree = ast.parse(API_LEGACY_MODEL_ROUTES.read_text(encoding="utf-8"))
    expected_model_functions = {
        "get_models",
        "get_active_model",
        "get_model_labels",
        "download_model_file",
        "switch_model",
        "upload_model",
        "download_model",
        "delete_model",
    }
    expected_helper_functions = {
        "resolve_runtime_model_name",
        "get_smart_tracker_runtime_context",
        "get_configured_yolo_models",
        "resolve_model_entry",
        "build_active_model_summary",
        "resolve_standby_cpu_model_path",
        "persist_standby_model_selection",
    }
    disallowed_handler_functions = {
        f"_{name}" for name in expected_helper_functions
    }
    wrapper_targets = {
        "get_models": "dispatch_get_models",
        "get_active_model": "dispatch_get_active_model",
        "get_model_labels": "dispatch_get_model_labels",
        "download_model_file": "dispatch_download_model_file",
        "switch_model": "dispatch_switch_model",
        "upload_model": "dispatch_upload_model",
        "download_model": "dispatch_download_model",
        "delete_model": "dispatch_delete_model",
    }
    disallowed_handler_strings = {
        "SMART_TRACKER_GPU_MODEL_PATH",
        "SMART_TRACKER_CPU_MODEL_PATH",
        "Standby model configured via API",
        "Model validation failed",
        "Only .pt files are allowed",
        "Detection model upload failed",
        "Detection model download failed",
        "Detection model deletion failed",
        "offset and limit must be integers",
    }

    model_route_functions = {
        node.name
        for node in ast.walk(model_routes_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    model_route_strings = {
        node.value
        for node in ast.walk(model_routes_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
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

    assert expected_model_functions <= model_route_functions
    assert expected_helper_functions <= model_route_functions
    assert not (set(handler_functions) & disallowed_handler_functions)
    for marker in disallowed_handler_strings:
        assert any(marker in literal for literal in model_route_strings)
        assert not any(marker in literal for literal in handler_string_literals)

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
        assert call.args
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


def test_legacy_recording_route_bodies_are_not_defined_in_fastapi_handler():
    """Legacy recording route bodies should stay out of the handler monolith."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    recording_routes_tree = ast.parse(
        API_LEGACY_RECORDING_ROUTES.read_text(encoding="utf-8")
    )
    expected_functions = {
        "_get_recording_manager",
        "_recording_source_dimensions",
        "start_recording",
        "pause_recording",
        "resume_recording",
        "stop_recording",
        "get_recording_status",
        "toggle_recording",
        "list_recordings",
        "download_recording",
        "delete_recording_file",
        "get_storage_status",
        "set_recording_include_osd",
    }
    wrapper_targets = {
        "start_recording": "dispatch_start_recording",
        "pause_recording": "dispatch_pause_recording",
        "resume_recording": "dispatch_resume_recording",
        "stop_recording": "dispatch_stop_recording",
        "get_recording_status": "dispatch_get_recording_status",
        "toggle_recording": "dispatch_toggle_recording",
        "list_recordings": "dispatch_list_recordings",
        "download_recording": "dispatch_download_recording",
        "delete_recording_file": "dispatch_delete_recording_file",
        "get_storage_status": "dispatch_get_storage_status",
        "set_recording_include_osd": "dispatch_set_recording_include_osd",
    }
    disallowed_handler_strings = {
        "Recording not available (ENABLE_RECORDING is false)",
        "Error starting recording",
        "Error pausing recording",
        "Error resuming recording",
        "Error stopping recording",
        "Error getting recording status",
        "Error toggling recording",
        "Error listing recordings",
        "Recording not found:",
        "Content-Range",
        "Accept-Ranges",
        "Error deleting recording",
        "Error getting storage status",
        "OSD recording",
        "Error setting recording OSD",
    }

    recording_route_functions = {
        node.name
        for node in ast.walk(recording_routes_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    recording_route_strings = {
        node.value
        for node in ast.walk(recording_routes_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
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

    assert expected_functions <= recording_route_functions
    assert "_get_recording_manager" not in handler_functions
    assert "_recording_source_dimensions" not in handler_functions
    for marker in disallowed_handler_strings:
        assert any(marker in literal for literal in recording_route_strings)
        assert not any(marker in literal for literal in handler_string_literals)

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
        assert call.args
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


def test_legacy_osd_route_bodies_are_not_defined_in_fastapi_handler():
    """Legacy OSD route bodies should stay out of the handler monolith."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    osd_routes_tree = ast.parse(API_LEGACY_OSD_ROUTES.read_text(encoding="utf-8"))
    expected_functions = {
        "get_osd_status",
        "toggle_osd",
        "get_osd_presets",
        "load_osd_preset",
        "get_osd_color_modes",
        "set_osd_color_mode",
        "get_osd_modes",
    }
    wrapper_targets = {
        "get_osd_status": "dispatch_get_osd_status",
        "toggle_osd": "dispatch_toggle_osd",
        "get_osd_presets": "dispatch_get_osd_presets",
        "load_osd_preset": "dispatch_load_osd_preset",
        "get_osd_color_modes": "dispatch_get_osd_color_modes",
        "set_osd_color_mode": "dispatch_set_osd_color_mode",
        "get_osd_modes": "dispatch_get_osd_modes",
    }
    disallowed_handler_strings = {
        "OSD system not available",
        "presets_location",
        "Error toggling OSD",
        "Error getting OSD presets",
        "Invalid preset name",
        "OSD renderer reinitialized",
        "Failed to reinitialize OSD renderer",
        "OSD mode manager not available",
        "Failed to switch color mode",
    }

    osd_route_functions = {
        node.name
        for node in ast.walk(osd_routes_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    osd_route_strings = {
        node.value
        for node in ast.walk(osd_routes_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
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

    assert expected_functions <= osd_route_functions
    for marker in disallowed_handler_strings:
        assert any(marker in literal for literal in osd_route_strings)
        assert not any(marker in literal for literal in handler_string_literals)

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
        assert call.args
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


def test_legacy_gstreamer_route_bodies_are_not_defined_in_fastapi_handler():
    """Legacy GStreamer route bodies should stay out of the handler monolith."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    gstreamer_routes_tree = ast.parse(
        API_LEGACY_GSTREAMER_ROUTES.read_text(encoding="utf-8")
    )
    expected_functions = {
        "_new_gstreamer_handler",
        "_is_gstreamer_active",
        "_qgc_setup_hint",
        "get_gstreamer_status",
        "toggle_gstreamer",
    }
    wrapper_targets = {
        "get_gstreamer_status": "dispatch_get_gstreamer_status",
        "toggle_gstreamer": "dispatch_toggle_gstreamer",
    }
    disallowed_handler_strings = {
        "GStreamer QGC output stopped via API",
        "GStreamer QGC output stream stopped",
        "GStreamer QGC output started",
        "GStreamer pipeline failed to open",
        "Error toggling GStreamer",
        "Error getting GStreamer status",
        "In QGC: Application Settings > Video > UDP Video Stream, port",
    }

    gstreamer_route_functions = {
        node.name
        for node in ast.walk(gstreamer_routes_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    gstreamer_route_strings = {
        node.value
        for node in ast.walk(gstreamer_routes_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
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

    assert expected_functions <= gstreamer_route_functions
    assert "_is_gstreamer_active" not in handler_functions
    for marker in disallowed_handler_strings:
        assert any(marker in literal for literal in gstreamer_route_strings)
        assert not any(marker in literal for literal in handler_string_literals)

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
        assert call.args
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


def test_legacy_follower_profile_route_bodies_are_not_defined_in_fastapi_handler():
    """Legacy follower profile/setpoint route bodies should stay out of the handler."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    follower_routes_tree = ast.parse(
        API_LEGACY_FOLLOWER_ROUTES.read_text(encoding="utf-8")
    )
    expected_functions = {
        "_follower_schema_path",
        "_has_active_follower",
        "get_follower_schema",
        "get_follower_profiles",
        "get_current_follower_profile",
        "switch_follower_profile",
        "get_follower_health",
        "restart_follower",
        "get_configured_follower_mode",
        "get_follower_setpoints_with_status",
        "get_current_follower_mode",
        "get_follower_config_general",
        "get_follower_config_effective",
    }
    wrapper_targets = {
        "get_follower_schema": "dispatch_get_follower_schema",
        "get_follower_profiles": "dispatch_get_follower_profiles",
        "get_current_follower_profile": "dispatch_get_current_follower_profile",
        "switch_follower_profile": "dispatch_switch_follower_profile",
        "get_follower_health": "dispatch_get_follower_health",
        "restart_follower": "dispatch_restart_follower",
        "get_configured_follower_mode": "dispatch_get_configured_follower_mode",
        "get_follower_setpoints_with_status": (
            "dispatch_get_follower_setpoints_with_status"
        ),
        "get_current_follower_mode": "dispatch_get_current_follower_mode",
        "get_follower_config_general": "dispatch_get_follower_config_general",
        "get_follower_config_effective": "dispatch_get_follower_config_effective",
    }
    disallowed_handler_strings = {
        "Profile configured but not engaged. Start offboard mode to activate.",
        "Profile not found in schema:",
        "profile_name is required",
        "Follower marked active but instance is None",
        "OffboardCommander has transient publish failures",
        "State lock not initialized - thread safety compromised",
        "Config reloaded. No active follower to restart.",
        "Config reloaded for follower restart",
        "Configured follower mode set to",
        "Follower has no setpoint handler",
        "commands_allowed_by_circuit_breaker",
        "Error getting follower config general",
        "Error getting follower config for",
        "Error getting follower setpoints with status",
        "Error getting current follower mode",
    }

    follower_route_functions = {
        node.name
        for node in ast.walk(follower_routes_tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    follower_route_strings = {
        node.value
        for node in ast.walk(follower_routes_tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
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

    assert expected_functions <= follower_route_functions
    assert "_has_active_follower" not in handler_functions
    for marker in disallowed_handler_strings:
        assert any(marker in literal for literal in follower_route_strings)
        assert not any(marker in literal for literal in handler_string_literals)

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
        assert call.args
        assert isinstance(call.args[0], ast.Name)
        assert call.args[0].id == "self"


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
    """Typed telemetry-health fallback payloads should stay out of route dispatch."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    telemetry_tree = ast.parse(API_V1_TELEMETRY.read_text(encoding="utf-8"))
    read_routes_tree = ast.parse(API_V1_READ_ROUTES.read_text(encoding="utf-8"))

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
    read_route_functions = {
        node.name
        for node in ast.walk(read_routes_tree)
        if isinstance(node, ast.AsyncFunctionDef)
    }
    get_telemetry_health = next(
        node
        for node in ast.walk(read_routes_tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_telemetry_health"
    )
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
    assert "get_telemetry_health" in read_route_functions
    assert "MAVLINK_TELEMETRY_CLAIM_BOUNDARY" not in handler_imported_contract_names
    assert len(telemetry_helper_calls) == 1
    assert "MAVLink data manager is not configured" not in handler_string_literals


def test_api_v1_streaming_media_helper_is_not_defined_in_fastapi_handler():
    """Typed streaming-media health payloads should stay out of route dispatch."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    streams_tree = ast.parse(API_V1_STREAMS.read_text(encoding="utf-8"))
    read_routes_tree = ast.parse(API_V1_READ_ROUTES.read_text(encoding="utf-8"))

    handler_imported_contract_names = {
        alias.name
        for node in handler_tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "classes.api_v1_contracts"
        for alias in node.names
    }
    handler_imported_stream_names = {
        alias.name
        for node in handler_tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "classes.api_v1_streams"
        for alias in node.names
    }
    handler_function_names = {
        node.name for node in ast.walk(handler_tree) if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
    }
    stream_functions = {
        node.name
        for node in ast.walk(streams_tree)
        if isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef)
    }
    read_route_functions = {
        node.name
        for node in ast.walk(read_routes_tree)
        if isinstance(node, ast.AsyncFunctionDef)
    }
    get_streaming_media_health = next(
        node
        for node in ast.walk(read_routes_tree)
        if (
            isinstance(node, ast.AsyncFunctionDef)
            and node.name == "get_streaming_media_health"
        )
    )
    stream_helper_calls = [
        node
        for node in ast.walk(get_streaming_media_health)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_streaming_media_health_snapshot"
    ]
    handler_string_literals = {
        node.value
        for node in ast.walk(get_streaming_media_health)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert "get_streaming_media_health_snapshot" in stream_functions
    assert "get_streaming_media_health" in read_route_functions
    assert "STREAMING_MEDIA_CLAIM_BOUNDARY" not in handler_imported_contract_names
    assert handler_imported_stream_names == set()
    assert "_get_streaming_media_health_snapshot" not in handler_function_names
    assert len(stream_helper_calls) == 1
    assert "gstreamer_config_enabled_handler_missing" not in handler_string_literals


def test_api_v1_read_route_error_boundaries_are_not_defined_in_fastapi_handler():
    """Typed read-route error boundaries should stay out of the handler monolith."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    read_routes_tree = ast.parse(API_V1_READ_ROUTES.read_text(encoding="utf-8"))
    expected_read_route_functions = {
        "get_following_status",
        "get_following_telemetry",
        "get_runtime_status",
        "get_streaming_media_health",
        "get_telemetry_health",
        "get_tracking_runtime_status",
        "get_tracking_telemetry",
    }
    wrapper_targets = {
        "get_runtime_status": "dispatch_get_runtime_status",
        "get_following_status": "dispatch_get_following_status",
        "get_following_telemetry": "dispatch_get_following_telemetry",
        "get_streaming_media_health": "dispatch_get_streaming_media_health",
        "get_telemetry_health": "dispatch_get_telemetry_health",
        "get_tracking_runtime_status": "dispatch_get_tracking_runtime_status",
        "get_tracking_telemetry": "dispatch_get_tracking_telemetry",
    }
    disallowed_handler_strings = {
        "runtime_status_error",
        "following_status_error",
        "following_telemetry_error",
        "streaming_media_health_error",
        "telemetry_health_error",
        "tracking_runtime_status_error",
        "tracking_telemetry_error",
    }

    read_route_functions = {
        node.name
        for node in ast.walk(read_routes_tree)
        if isinstance(node, ast.AsyncFunctionDef)
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

    assert expected_read_route_functions <= read_route_functions
    assert handler_string_literals.isdisjoint(disallowed_handler_strings)

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


def test_api_v1_auth_route_bodies_are_not_defined_in_fastapi_handler():
    """Browser-session auth dispatch should stay out of the handler monolith."""
    handler_tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))
    auth_routes_tree = ast.parse(API_V1_AUTH_ROUTES.read_text(encoding="utf-8"))
    expected_auth_functions = {
        "get_auth_session",
        "login_auth_session",
        "logout_auth_session",
    }
    wrapper_targets = {
        "get_auth_session": "dispatch_get_auth_session",
        "login_auth_session": "dispatch_login_auth_session",
        "logout_auth_session": "dispatch_logout_auth_session",
    }
    disallowed_handler_strings = {
        "browser_session_auth_not_configured",
        "invalid_credentials",
        "session_required",
    }

    auth_functions = {
        node.name
        for node in ast.walk(auth_routes_tree)
        if isinstance(node, ast.AsyncFunctionDef)
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

    assert expected_auth_functions <= auth_functions
    assert handler_string_literals.isdisjoint(disallowed_handler_strings)

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
        set(API_V1_AUTH_PATHS)
        | set(API_V1_PROCESS_LOCAL_READ_ONLY_PATHS)
        | set(SITL_VALIDATION_INJECTION_PATHS)
        | {
            API_V1_ACTION_OFFBOARD_START_PATH,
            API_V1_ACTION_OFFBOARD_STOP_PATH,
            API_V1_ACTION_OPERATOR_ABORT_PATH,
            API_V1_ACTION_SEGMENTATION_TOGGLE_PATH,
            API_V1_ACTION_SMART_CLICK_PATH,
            API_V1_ACTION_SMART_MODE_TOGGLE_PATH,
            API_V1_ACTION_TRACKING_REDETECT_PATH,
            API_V1_ACTION_TRACKING_START_PATH,
            API_V1_ACTION_TRACKING_STOP_PATH,
            API_V1_ACTION_RESOURCE_PATH,
        }
    )

    for path in expected_typed_paths:
        assert uses_typed_api_error_envelope(path) is True

    assert uses_typed_api_error_envelope("/status") is False
    assert uses_typed_api_error_envelope("/telemetry/follower_data") is False


def test_api_v1_auth_routes_have_typed_api_metadata():
    """Browser-session auth endpoints must keep explicit typed contracts."""
    expectations = {
        API_V1_AUTH_SESSION_PATH: (
            "get_auth_session",
            "APIAuthSessionResponse",
            "GET",
        ),
        API_V1_AUTH_LOGIN_PATH: (
            "login_auth_session",
            "APIAuthLoginResponse",
            "POST",
        ),
        API_V1_AUTH_LOGOUT_PATH: (
            "logout_auth_session",
            "APIAuthLogoutResponse",
            "POST",
        ),
    }
    for path, (operation_id, response_model, method) in expectations.items():
        route = _route_metadata(path)

        assert route["method"] == method
        assert route["operation_id"] == operation_id
        assert route["response_model"] == response_model
        assert route["responses"] == "AUTH_ROUTE_RESPONSES"
        assert route["tags"] == ["auth"]
        assert route["status_code"] is None


def test_api_v1_action_routes_have_typed_api_metadata():
    """Typed control actions must be explicit /api/v1 resources."""
    expectations = {
        "/api/v1/actions/offboard-start": (
            "start_offboard_action",
            "APIActionResponse",
            True,
            "ACTION_ROUTE_RESPONSES",
        ),
        "/api/v1/actions/offboard-stop": (
            "stop_offboard_action",
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
        "/api/v1/actions/segmentation-toggle": (
            "segmentation_toggle_action",
            "APIActionResponse",
            True,
            "ACTION_ROUTE_RESPONSES",
        ),
        "/api/v1/actions/smart-click": (
            "smart_click_action",
            "APIActionResponse",
            True,
            "ACTION_ROUTE_RESPONSES",
        ),
        "/api/v1/actions/smart-mode-toggle": (
            "smart_mode_toggle_action",
            "APIActionResponse",
            True,
            "ACTION_ROUTE_RESPONSES",
        ),
        "/api/v1/actions/tracking-redetect": (
            "tracking_redetect_action",
            "APIActionResponse",
            True,
            "ACTION_ROUTE_RESPONSES",
        ),
        "/api/v1/actions/tracking-start": (
            "tracking_start_action",
            "APIActionResponse",
            True,
            "ACTION_ROUTE_RESPONSES",
        ),
        "/api/v1/actions/tracking-stop": (
            "tracking_stop_action",
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


def test_api_v1_streaming_media_health_route_has_typed_api_metadata():
    """Typed streaming-media health must be an explicit /api/v1 resource."""
    route = _route_metadata(API_V1_STREAMING_MEDIA_HEALTH_PATH)

    assert route["operation_id"] == "get_streaming_media_health"
    assert route["response_model"] == "APIStreamingMediaHealthResponse"
    assert route["responses"] == "STREAMING_MEDIA_HEALTH_ERROR_RESPONSES"
    assert route["tags"] == ["streams"]
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


def test_retired_control_aliases_are_not_registered_as_http_routes():
    """Typed action replacements must be the public Offboard/cancel surface."""
    retired_paths = {
        "/commands/start_offboard_mode",
        "/commands/stop_offboard_mode",
        "/commands/cancel_activities",
    }
    current_paths = {route["path"] for route in _collect_route_metadata()}

    assert retired_paths.isdisjoint(current_paths)


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
