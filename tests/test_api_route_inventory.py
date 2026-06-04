"""Static inventory of the current FastAPIHandler route surface.

This intentionally parses route declarations instead of instantiating the app.
Constructing AppController/FastAPIHandler can start runtime subsystems or create
local artifacts, while Phase 0 only needs a frozen route baseline.
"""

import ast
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FASTAPI_HANDLER = REPO_ROOT / "src" / "classes" / "fastapi_handler.py"


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


def _collect_declared_routes():
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

        method = "WEBSOCKET" if route_func.attr == "websocket" else route_func.attr.upper()
        routes.append((method, route_call.args[0].value))

    return routes


def _find_route_registration(path):
    tree = ast.parse(FASTAPI_HANDLER.read_text(encoding="utf-8"))

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
        if route_call.args and isinstance(route_call.args[0], ast.Constant):
            if route_call.args[0].value == path:
                return route_call

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
        "GET": 66,
        "POST": 53,
        "PUT": 2,
        "WEBSOCKET": 2,
    }


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
        route_call = _find_route_registration(path)
        keywords = {keyword.arg: keyword.value for keyword in route_call.keywords}

        assert keywords["operation_id"].value == operation_id
        assert keywords["response_model"].id == response_model
        assert keywords["responses"].id == responses_name
        assert keywords["tags"].elts[0].value == "actions"
        if expects_accepted:
            assert keywords["status_code"].attr == "HTTP_202_ACCEPTED"
        else:
            assert "status_code" not in keywords


def test_legacy_control_routes_are_deprecated_compatibility_aliases():
    """Legacy dangerous command routes must be visibly deprecated."""
    expectations = {
        "/commands/start_offboard_mode": "legacy_start_offboard_mode",
        "/commands/cancel_activities": "legacy_cancel_activities",
    }
    for path, operation_id in expectations.items():
        route_call = _find_route_registration(path)
        keywords = {keyword.arg: keyword.value for keyword in route_call.keywords}

        assert keywords["deprecated"].value is True
        assert keywords["operation_id"].value == operation_id
        assert keywords["tags"].elts[0].value == "legacy-commands"


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
        route_call = _find_route_registration(path)
        keywords = {keyword.arg: keyword.value for keyword in route_call.keywords}

        assert keywords["operation_id"].value == operation_id
        assert keywords["response_model"].id == response_model
        assert keywords["status_code"].attr == "HTTP_202_ACCEPTED"
        assert keywords["responses"].id == "SITL_ERROR_RESPONSES"
        assert keywords["tags"].elts[0].value == "sitl-validation"
