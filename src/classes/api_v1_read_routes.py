"""Typed /api/v1 read-route dispatch and error-boundary helpers."""

from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.api_v1_actions import get_system_restart_availability
from classes.api_v1_paths import (
    API_V1_FOLLOWING_STATUS_PATH,
    API_V1_FOLLOWING_TELEMETRY_PATH,
    API_V1_CONFIG_RUNTIME_STATUS_PATH,
    API_V1_RUNTIME_STATUS_PATH,
    API_V1_SYSTEM_ABOUT_PATH,
    API_V1_STREAMING_CLIENT_CONFIG_PATH,
    API_V1_STREAMING_MEDIA_HEALTH_PATH,
    API_V1_TELEMETRY_HEALTH_PATH,
    API_V1_TRACKING_CATALOG_PATH,
    API_V1_TRACKING_RUNTIME_STATUS_PATH,
    API_V1_TRACKING_TELEMETRY_PATH,
)
from classes.api_v1_contracts import APIStreamingClientConfigResponse
from classes.api_v1_streams import (
    get_streaming_client_config_snapshot,
    get_streaming_media_health_snapshot,
)
from classes.api_v1_telemetry import get_telemetry_health_snapshot


def _log_route_error(owner: Any, route_name: str, error: Exception) -> None:
    logger = getattr(owner, "logger", None)
    if logger is not None:
        logger.error(f"Error in {route_name}: {error}")


async def get_runtime_status(owner: Any) -> Any:
    """Return typed PixEagle runtime status for API/MCP/dashboard consumers."""
    try:
        return owner._get_runtime_status_snapshot()
    except Exception as error:
        _log_route_error(owner, "get_runtime_status", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="runtime_status_error",
            detail=str(error),
            path=API_V1_RUNTIME_STATUS_PATH,
        )


async def get_config_runtime_status(owner: Any, http_request: Any) -> Any:
    """Return redacted persisted changes awaiting a process restart."""
    try:
        service = owner._get_config_service()
        payload = await run_in_threadpool(service.get_runtime_config_status)
        payload["restart_action"] = get_system_restart_availability(
            owner,
            http_request,
            config_status=payload,
        )
        return payload
    except Exception as error:
        _log_route_error(owner, "get_config_runtime_status", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="config_runtime_status_error",
            detail=str(error),
            path=API_V1_CONFIG_RUNTIME_STATUS_PATH,
        )


async def get_system_about(owner: Any) -> Any:
    """Return typed system/about metadata for dashboard and agent context."""
    try:
        return owner._get_system_about_snapshot()
    except Exception as error:
        _log_route_error(owner, "get_system_about", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="system_about_error",
            detail=str(error),
            path=API_V1_SYSTEM_ABOUT_PATH,
        )


async def get_following_status(owner: Any) -> Any:
    """Return typed following status for API/MCP/dashboard consumers."""
    try:
        return owner._get_following_status_snapshot()
    except Exception as error:
        _log_route_error(owner, "get_following_status", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="following_status_error",
            detail=str(error),
            path=API_V1_FOLLOWING_STATUS_PATH,
        )


async def get_following_telemetry(owner: Any) -> Any:
    """Return typed follower telemetry/setpoint snapshot for consumers."""
    try:
        return owner._get_following_telemetry_snapshot()
    except Exception as error:
        _log_route_error(owner, "get_following_telemetry", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="following_telemetry_error",
            detail=str(error),
            path=API_V1_FOLLOWING_TELEMETRY_PATH,
        )


async def get_telemetry_health(owner: Any) -> Any:
    """Return typed MAVLink2REST health for API/MCP/dashboard consumers."""
    try:
        return get_telemetry_health_snapshot(owner)
    except Exception as error:
        _log_route_error(owner, "get_telemetry_health", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="telemetry_health_error",
            detail=str(error),
            path=API_V1_TELEMETRY_HEALTH_PATH,
        )


async def get_streaming_media_health(owner: Any) -> Any:
    """Return typed media transport health for API/MCP/dashboard consumers."""
    try:
        return await get_streaming_media_health_snapshot(owner)
    except Exception as error:
        _log_route_error(owner, "get_streaming_media_health", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="streaming_media_health_error",
            detail=str(error),
            path=API_V1_STREAMING_MEDIA_HEALTH_PATH,
        )


async def get_streaming_client_config(owner: Any) -> Any:
    """Return no-store browser media configuration to authorized clients."""
    try:
        payload = APIStreamingClientConfigResponse(
            **get_streaming_client_config_snapshot(owner)
        )
        content = (
            payload.model_dump(mode="json")
            if hasattr(payload, "model_dump")
            else payload.dict()
        )
        return JSONResponse(
            content=content,
            headers={"Cache-Control": "no-store"},
        )
    except Exception as error:
        _log_route_error(owner, "get_streaming_client_config", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="streaming_client_config_error",
            detail=str(error),
            path=API_V1_STREAMING_CLIENT_CONFIG_PATH,
        )


async def get_tracking_runtime_status(owner: Any) -> Any:
    """Return typed tracker runtime status for API/MCP/dashboard consumers."""
    try:
        runtime_status = owner._get_tracker_runtime_status_snapshot()
        readiness = owner._get_tracker_following_readiness(
            runtime_status=runtime_status,
        )
        return {
            **runtime_status,
            "following_readiness": {
                "usable_for_following": bool(
                    readiness.get("usable_for_following", False)
                ),
                "reason": readiness.get("reason"),
                "tracker_requires_video": bool(
                    readiness.get("tracker_requires_video", True)
                ),
                "video_frame_status": dict(
                    readiness.get("video_frame_status") or {}
                ),
            },
        }
    except Exception as error:
        _log_route_error(owner, "get_tracking_runtime_status", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="tracking_runtime_status_error",
            detail=str(error),
            path=API_V1_TRACKING_RUNTIME_STATUS_PATH,
        )


async def get_tracking_catalog(owner: Any) -> Any:
    """Return typed tracker catalog/configuration metadata for consumers."""
    try:
        return owner._get_tracking_catalog_snapshot()
    except Exception as error:
        _log_route_error(owner, "get_tracking_catalog", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="tracking_catalog_error",
            detail=str(error),
            path=API_V1_TRACKING_CATALOG_PATH,
        )


async def get_tracking_telemetry(owner: Any) -> Any:
    """Return typed tracker telemetry/geometry for API/MCP/dashboard consumers."""
    try:
        return owner._get_tracking_telemetry_snapshot()
    except Exception as error:
        _log_route_error(owner, "get_tracking_telemetry", error)
        return owner._api_v1_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="tracking_telemetry_error",
            detail=str(error),
            path=API_V1_TRACKING_TELEMETRY_PATH,
        )


__all__ = [
    "get_config_runtime_status",
    "get_following_status",
    "get_following_telemetry",
    "get_runtime_status",
    "get_system_about",
    "get_streaming_media_health",
    "get_telemetry_health",
    "get_tracking_catalog",
    "get_tracking_runtime_status",
    "get_tracking_telemetry",
]
