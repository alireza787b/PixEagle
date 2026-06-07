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


REPO_ROOT = Path(__file__).resolve().parents[1]
FASTAPI_HANDLER = REPO_ROOT / "src" / "classes" / "fastapi_handler.py"
API_V1_ROUTE_REGISTRY = REPO_ROOT / "src" / "classes" / "fastapi_api_v1_routes.py"
API_V1_CONTRACTS = REPO_ROOT / "src" / "classes" / "api_v1_contracts.py"

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


def _expr_to_data(node):
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
                    "path": _expr_to_data(keywords.get("path")),
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
