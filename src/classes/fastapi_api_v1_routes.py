"""Typed /api/v1 FastAPI route metadata and registration helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal


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
        path="/api/v1/runtime/status",
        handler="get_runtime_status",
        response_model="APIRuntimeStatusResponse",
        responses="RUNTIME_STATUS_ERROR_RESPONSES",
        operation_id="get_runtime_status",
        tags=("runtime",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path="/api/v1/following/status",
        handler="get_following_status",
        response_model="APIFollowingStatusResponse",
        responses="FOLLOWING_STATUS_ERROR_RESPONSES",
        operation_id="get_following_status",
        tags=("following",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path="/api/v1/following/telemetry",
        handler="get_following_telemetry",
        response_model="APIFollowingTelemetryResponse",
        responses="FOLLOWING_TELEMETRY_ERROR_RESPONSES",
        operation_id="get_following_telemetry",
        tags=("following",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path="/api/v1/telemetry/health",
        handler="get_telemetry_health",
        response_model="APITelemetryHealthResponse",
        responses="TELEMETRY_HEALTH_ERROR_RESPONSES",
        operation_id="get_telemetry_health",
        tags=("telemetry",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path="/api/v1/tracking/runtime-status",
        handler="get_tracking_runtime_status",
        response_model="APITrackingRuntimeStatusResponse",
        responses="TRACKING_RUNTIME_STATUS_ERROR_RESPONSES",
        operation_id="get_tracking_runtime_status",
        tags=("tracking",),
    ),
    ApiV1RouteSpec(
        method="GET",
        path="/api/v1/tracking/telemetry",
        handler="get_tracking_telemetry",
        response_model="APITrackingTelemetryResponse",
        responses="TRACKING_TELEMETRY_ERROR_RESPONSES",
        operation_id="get_tracking_telemetry",
        tags=("tracking",),
    ),
    ApiV1RouteSpec(
        method="POST",
        path="/api/v1/actions/offboard-start",
        handler="start_offboard_action",
        response_model="APIActionResponse",
        responses="ACTION_ROUTE_RESPONSES",
        operation_id="start_offboard_action",
        tags=("actions",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path="/api/v1/actions/operator-abort",
        handler="operator_abort_action",
        response_model="APIActionResponse",
        responses="ACTION_ROUTE_RESPONSES",
        operation_id="operator_abort_action",
        tags=("actions",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="GET",
        path="/api/v1/actions/{action_id}",
        handler="get_action_resource",
        response_model="APIActionResponse",
        responses="ACTION_ERROR_RESPONSES",
        operation_id="get_action_resource",
        tags=("actions",),
    ),
    ApiV1RouteSpec(
        method="POST",
        path="/api/v1/sitl/injections/tracker-output",
        handler="inject_sitl_tracker_output",
        response_model="SITLTrackerInjectionResponse",
        responses="SITL_ERROR_RESPONSES",
        operation_id="inject_sitl_tracker_output",
        tags=("sitl-validation",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path="/api/v1/sitl/injections/video-stall",
        handler="inject_sitl_video_stall",
        response_model="SITLVideoStallResponse",
        responses="SITL_ERROR_RESPONSES",
        operation_id="inject_sitl_video_stall",
        tags=("sitl-validation",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path="/api/v1/sitl/injections/commander-publish-failure",
        handler="inject_sitl_commander_publish_failure",
        response_model="SITLCommanderPublishFailureResponse",
        responses="SITL_ERROR_RESPONSES",
        operation_id="inject_sitl_commander_publish_failure",
        tags=("sitl-validation",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path="/api/v1/sitl/injections/mavsdk-disconnect",
        handler="inject_sitl_mavsdk_disconnect",
        response_model="SITLMavsdkDisconnectResponse",
        responses="SITL_ERROR_RESPONSES",
        operation_id="inject_sitl_mavsdk_disconnect",
        tags=("sitl-validation",),
        status_code="status.HTTP_202_ACCEPTED",
    ),
    ApiV1RouteSpec(
        method="POST",
        path="/api/v1/sitl/injections/mavlink2rest-timeout",
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
