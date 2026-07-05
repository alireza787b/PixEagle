"""Canonical path constants and route predicates for typed /api/v1 APIs."""

from __future__ import annotations

from typing import Literal

SITL_TRACKER_OUTPUT_INJECTION_PATH = "/api/v1/sitl/injections/tracker-output"
SITL_VIDEO_STALL_INJECTION_PATH = "/api/v1/sitl/injections/video-stall"
SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH = (
    "/api/v1/sitl/injections/commander-publish-failure"
)
SITL_MAVSDK_DISCONNECT_INJECTION_PATH = "/api/v1/sitl/injections/mavsdk-disconnect"
SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH = (
    "/api/v1/sitl/injections/mavlink2rest-timeout"
)

API_V1_ACTION_OFFBOARD_START_PATH = "/api/v1/actions/offboard-start"
API_V1_ACTION_OFFBOARD_STOP_PATH = "/api/v1/actions/offboard-stop"
API_V1_ACTION_OPERATOR_ABORT_PATH = "/api/v1/actions/operator-abort"
API_V1_ACTION_TRACKING_START_PATH = "/api/v1/actions/tracking-start"
API_V1_ACTION_TRACKING_STOP_PATH = "/api/v1/actions/tracking-stop"
API_V1_ACTION_TRACKING_REDETECT_PATH = "/api/v1/actions/tracking-redetect"
API_V1_ACTION_SEGMENTATION_TOGGLE_PATH = "/api/v1/actions/segmentation-toggle"
API_V1_ACTION_SMART_MODE_TOGGLE_PATH = "/api/v1/actions/smart-mode-toggle"
API_V1_ACTION_SMART_CLICK_PATH = "/api/v1/actions/smart-click"
API_V1_ACTION_TRACKER_SWITCH_PATH = "/api/v1/actions/tracker-switch"
API_V1_ACTION_TRACKER_RESTART_PATH = "/api/v1/actions/tracker-restart"
API_V1_ACTION_RESOURCE_PREFIX = "/api/v1/actions"
API_V1_ACTION_RESOURCE_PATH = "/api/v1/actions/{action_id}"
API_V1_AUTH_SESSION_PATH = "/api/v1/auth/session"
API_V1_AUTH_LOGIN_PATH = "/api/v1/auth/login"
API_V1_AUTH_LOGOUT_PATH = "/api/v1/auth/logout"
API_V1_RUNTIME_STATUS_PATH = "/api/v1/runtime/status"
API_V1_STREAMING_MEDIA_HEALTH_PATH = "/api/v1/streams/media-health"
API_V1_FOLLOWING_STATUS_PATH = "/api/v1/following/status"
API_V1_FOLLOWING_TELEMETRY_PATH = "/api/v1/following/telemetry"
API_V1_TELEMETRY_HEALTH_PATH = "/api/v1/telemetry/health"
API_V1_LOGS_STATUS_PATH = "/api/v1/logs/status"
API_V1_LOGS_SESSIONS_PATH = "/api/v1/logs/sessions"
API_V1_LOGS_SESSION_PATH = "/api/v1/logs/sessions/{run_id}"
API_V1_LOGS_SESSION_EXPORT_PATH = "/api/v1/logs/sessions/{run_id}/export"
API_V1_LOGS_FRONTEND_ERRORS_PATH = "/api/v1/logs/frontend-errors"
API_V1_TRACKING_CATALOG_PATH = "/api/v1/tracking/catalog"
API_V1_TRACKING_RUNTIME_STATUS_PATH = "/api/v1/tracking/runtime-status"
API_V1_TRACKING_TELEMETRY_PATH = "/api/v1/tracking/telemetry"

SITL_VALIDATION_INJECTION_PATHS = frozenset(
    {
        SITL_TRACKER_OUTPUT_INJECTION_PATH,
        SITL_VIDEO_STALL_INJECTION_PATH,
        SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH,
        SITL_MAVSDK_DISCONNECT_INJECTION_PATH,
        SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH,
    }
)

API_V1_PROCESS_LOCAL_READ_ONLY_PATHS = frozenset(
    {
        API_V1_RUNTIME_STATUS_PATH,
        API_V1_STREAMING_MEDIA_HEALTH_PATH,
        API_V1_FOLLOWING_STATUS_PATH,
        API_V1_FOLLOWING_TELEMETRY_PATH,
        API_V1_TELEMETRY_HEALTH_PATH,
        API_V1_LOGS_STATUS_PATH,
        API_V1_LOGS_SESSIONS_PATH,
        API_V1_LOGS_SESSION_PATH,
        API_V1_LOGS_SESSION_EXPORT_PATH,
        API_V1_TRACKING_RUNTIME_STATUS_PATH,
        API_V1_TRACKING_TELEMETRY_PATH,
    }
)

API_V1_AUTH_PATHS = frozenset(
    {
        API_V1_AUTH_SESSION_PATH,
        API_V1_AUTH_LOGIN_PATH,
        API_V1_AUTH_LOGOUT_PATH,
    }
)

API_V1_TYPED_ERROR_ENVELOPE_PATHS = frozenset(
    set(API_V1_AUTH_PATHS)
    | set(API_V1_PROCESS_LOCAL_READ_ONLY_PATHS)
    | {API_V1_LOGS_FRONTEND_ERRORS_PATH}
    | {API_V1_TRACKING_CATALOG_PATH}
    | set(SITL_VALIDATION_INJECTION_PATHS)
)


def is_api_v1_action_resource_path(path: str) -> bool:
    """Return True for typed action collection and resource routes."""
    return path.startswith(f"{API_V1_ACTION_RESOURCE_PREFIX}/")


def is_api_v1_logs_resource_path(path: str) -> bool:
    """Return True for typed runtime log routes with path parameters."""
    normalized_path = str(path or "").split("?", 1)[0]
    return normalized_path.startswith("/api/v1/logs/sessions/")


def uses_typed_api_error_envelope(path: str) -> bool:
    """Return True when validation errors should use the /api/v1 envelope."""
    return (
        path in API_V1_TYPED_ERROR_ENVELOPE_PATHS
        or is_api_v1_action_resource_path(path)
        or is_api_v1_logs_resource_path(path)
    )


def api_v1_request_id_prefix(path: str) -> Literal["pixeagle-action", "pixeagle-sitl", "pixeagle-api"]:
    """Return the request-id namespace for a typed /api/v1 error path."""
    if is_api_v1_action_resource_path(path):
        return "pixeagle-action"
    if path in SITL_VALIDATION_INJECTION_PATHS:
        return "pixeagle-sitl"
    return "pixeagle-api"


__all__ = [
    "API_V1_ACTION_OFFBOARD_START_PATH",
    "API_V1_ACTION_OFFBOARD_STOP_PATH",
    "API_V1_ACTION_OPERATOR_ABORT_PATH",
    "API_V1_ACTION_SEGMENTATION_TOGGLE_PATH",
    "API_V1_ACTION_SMART_CLICK_PATH",
    "API_V1_ACTION_SMART_MODE_TOGGLE_PATH",
    "API_V1_ACTION_TRACKER_RESTART_PATH",
    "API_V1_ACTION_TRACKER_SWITCH_PATH",
    "API_V1_ACTION_TRACKING_REDETECT_PATH",
    "API_V1_ACTION_TRACKING_START_PATH",
    "API_V1_ACTION_TRACKING_STOP_PATH",
    "API_V1_ACTION_RESOURCE_PREFIX",
    "API_V1_ACTION_RESOURCE_PATH",
    "API_V1_AUTH_LOGIN_PATH",
    "API_V1_AUTH_LOGOUT_PATH",
    "API_V1_AUTH_PATHS",
    "API_V1_AUTH_SESSION_PATH",
    "API_V1_FOLLOWING_STATUS_PATH",
    "API_V1_FOLLOWING_TELEMETRY_PATH",
    "API_V1_LOGS_SESSION_PATH",
    "API_V1_LOGS_SESSION_EXPORT_PATH",
    "API_V1_LOGS_SESSIONS_PATH",
    "API_V1_LOGS_FRONTEND_ERRORS_PATH",
    "API_V1_LOGS_STATUS_PATH",
    "API_V1_PROCESS_LOCAL_READ_ONLY_PATHS",
    "API_V1_RUNTIME_STATUS_PATH",
    "API_V1_STREAMING_MEDIA_HEALTH_PATH",
    "API_V1_TELEMETRY_HEALTH_PATH",
    "API_V1_TRACKING_CATALOG_PATH",
    "API_V1_TRACKING_RUNTIME_STATUS_PATH",
    "API_V1_TRACKING_TELEMETRY_PATH",
    "API_V1_TYPED_ERROR_ENVELOPE_PATHS",
    "SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH",
    "SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH",
    "SITL_MAVSDK_DISCONNECT_INJECTION_PATH",
    "SITL_TRACKER_OUTPUT_INJECTION_PATH",
    "SITL_VALIDATION_INJECTION_PATHS",
    "SITL_VIDEO_STALL_INJECTION_PATH",
    "api_v1_request_id_prefix",
    "is_api_v1_action_resource_path",
    "is_api_v1_logs_resource_path",
    "uses_typed_api_error_envelope",
]
