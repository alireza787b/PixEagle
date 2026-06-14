"""Typed /api/v1 FastAPI route metadata and registration helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from classes.api_v1_paths import (
    API_V1_ACTION_OFFBOARD_START_PATH,
    API_V1_ACTION_OFFBOARD_STOP_PATH,
    API_V1_ACTION_OPERATOR_ABORT_PATH,
    API_V1_ACTION_RESOURCE_PATH,
    API_V1_AUTH_LOGIN_PATH,
    API_V1_AUTH_LOGOUT_PATH,
    API_V1_AUTH_SESSION_PATH,
    API_V1_FOLLOWING_STATUS_PATH,
    API_V1_FOLLOWING_TELEMETRY_PATH,
    API_V1_RUNTIME_STATUS_PATH,
    API_V1_TELEMETRY_HEALTH_PATH,
    API_V1_TRACKING_RUNTIME_STATUS_PATH,
    API_V1_TRACKING_TELEMETRY_PATH,
    SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH,
    SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH,
    SITL_MAVSDK_DISCONNECT_INJECTION_PATH,
    SITL_TRACKER_OUTPUT_INJECTION_PATH,
    SITL_VIDEO_STALL_INJECTION_PATH,
)


@dataclass(frozen=True)
class ApiV1RouteSpec:
    """Static route contract used by runtime registration and inventory tests."""

    method: Literal["GET", "POST"]
    path: str
    handler: str
    response_model: str
    responses: str
    operation_id: str
    tags: tuple[str, ...]
    status_code: str | None = None


API_V1_ROUTE_SPECS: tuple[ApiV1RouteSpec, ...] = (
    ApiV1RouteSpec(
        method="GET",
        path=API_V1_AUTH_SESSION_PATH,
        handler="get_auth_session",
        response_model="APIAuthSessionResponse",
        responses="AUTH_ROUTE_RESPONSES",
        operation_id="get_auth_session",
        tags=("auth",),
    ),
    ApiV1RouteSpec(
        method="POST",
        path=API_V1_AUTH_LOGIN_PATH,
        handler="login_auth_session",
        response_model="APIAuthLoginResponse",
        responses="AUTH_ROUTE_RESPONSES",
        operation_id="login_auth_session",
        tags=("auth",),
    ),
    ApiV1RouteSpec(
        method="POST",
        path=API_V1_AUTH_LOGOUT_PATH,
        handler="logout_auth_session",
        response_model="APIAuthLogoutResponse",
        responses="AUTH_ROUTE_RESPONSES",
        operation_id="logout_auth_session",
        tags=("auth",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path=API_V1_RUNTIME_STATUS_PATH,
        handler="get_runtime_status",
        response_model="APIRuntimeStatusResponse",
        responses="RUNTIME_STATUS_ERROR_RESPONSES",
        operation_id="get_runtime_status",
        tags=("runtime",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path=API_V1_FOLLOWING_STATUS_PATH,
        handler="get_following_status",
        response_model="APIFollowingStatusResponse",
        responses="FOLLOWING_STATUS_ERROR_RESPONSES",
        operation_id="get_following_status",
        tags=("following",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path=API_V1_FOLLOWING_TELEMETRY_PATH,
        handler="get_following_telemetry",
        response_model="APIFollowingTelemetryResponse",
        responses="FOLLOWING_TELEMETRY_ERROR_RESPONSES",
        operation_id="get_following_telemetry",
        tags=("following",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path=API_V1_TELEMETRY_HEALTH_PATH,
        handler="get_telemetry_health",
        response_model="APITelemetryHealthResponse",
        responses="TELEMETRY_HEALTH_ERROR_RESPONSES",
        operation_id="get_telemetry_health",
        tags=("telemetry",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path=API_V1_TRACKING_RUNTIME_STATUS_PATH,
        handler="get_tracking_runtime_status",
        response_model="APITrackingRuntimeStatusResponse",
        responses="TRACKING_RUNTIME_STATUS_ERROR_RESPONSES",
        operation_id="get_tracking_runtime_status",
        tags=("tracking",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path=API_V1_TRACKING_TELEMETRY_PATH,
        handler="get_tracking_telemetry",
        response_model="APITrackingTelemetryResponse",
        responses="TRACKING_TELEMETRY_ERROR_RESPONSES",
        operation_id="get_tracking_telemetry",
        tags=("tracking",),
    ),
    ApiV1RouteSpec(
        method="POST",
        path=API_V1_ACTION_OFFBOARD_START_PATH,
        handler="start_offboard_action",
        response_model="APIActionResponse",
        responses="ACTION_ROUTE_RESPONSES",
        operation_id="start_offboard_action",
        tags=("actions",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path=API_V1_ACTION_OFFBOARD_STOP_PATH,
        handler="stop_offboard_action",
        response_model="APIActionResponse",
        responses="ACTION_ROUTE_RESPONSES",
        operation_id="stop_offboard_action",
        tags=("actions",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path=API_V1_ACTION_OPERATOR_ABORT_PATH,
        handler="operator_abort_action",
        response_model="APIActionResponse",
        responses="ACTION_ROUTE_RESPONSES",
        operation_id="operator_abort_action",
        tags=("actions",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="GET",
        path=API_V1_ACTION_RESOURCE_PATH,
        handler="get_action_resource",
        response_model="APIActionResponse",
        responses="ACTION_ERROR_RESPONSES",
        operation_id="get_action_resource",
        tags=("actions",),
    ),
    ApiV1RouteSpec(
        method="POST",
        path=SITL_TRACKER_OUTPUT_INJECTION_PATH,
        handler="inject_sitl_tracker_output",
        response_model="SITLTrackerInjectionResponse",
        responses="SITL_ERROR_RESPONSES",
        operation_id="inject_sitl_tracker_output",
        tags=("sitl-validation",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path=SITL_VIDEO_STALL_INJECTION_PATH,
        handler="inject_sitl_video_stall",
        response_model="SITLVideoStallResponse",
        responses="SITL_ERROR_RESPONSES",
        operation_id="inject_sitl_video_stall",
        tags=("sitl-validation",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path=SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH,
        handler="inject_sitl_commander_publish_failure",
        response_model="SITLCommanderPublishFailureResponse",
        responses="SITL_ERROR_RESPONSES",
        operation_id="inject_sitl_commander_publish_failure",
        tags=("sitl-validation",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path=SITL_MAVSDK_DISCONNECT_INJECTION_PATH,
        handler="inject_sitl_mavsdk_disconnect",
        response_model="SITLMavsdkDisconnectResponse",
        responses="SITL_ERROR_RESPONSES",
        operation_id="inject_sitl_mavsdk_disconnect",
        tags=("sitl-validation",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path=SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH,
        handler="inject_sitl_mavlink2rest_timeout",
        response_model="SITLMavlink2RestTimeoutResponse",
        responses="SITL_ERROR_RESPONSES",
        operation_id="inject_sitl_mavlink2rest_timeout",
        tags=("sitl-validation",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
)


def _resolve_route_dependency(name: str, namespace: Mapping[str, Any]) -> Any:
    current: Any = namespace
    try:
        for part in name.split("."):
            current = current[part] if isinstance(current, Mapping) else getattr(current, part)
    except (KeyError, AttributeError) as exc:
        raise RuntimeError(f"Cannot resolve /api/v1 route dependency {name!r}") from exc
    return current


def register_api_v1_routes(handler: Any, namespace: Mapping[str, Any]) -> None:
    """Register typed /api/v1 routes on a FastAPIHandler instance."""

    for spec in API_V1_ROUTE_SPECS:
        route = getattr(handler.app, spec.method.lower())
        route_kwargs: dict[str, Any] = {
            "response_model": _resolve_route_dependency(spec.response_model, namespace),
            "responses": _resolve_route_dependency(spec.responses, namespace),
            "operation_id": spec.operation_id,
            "tags": list(spec.tags),
        }
        if spec.status_code is not None:
            route_kwargs["status_code"] = _resolve_route_dependency(
                spec.status_code,
                namespace,
            )

        route(spec.path, **route_kwargs)(getattr(handler, spec.handler))
