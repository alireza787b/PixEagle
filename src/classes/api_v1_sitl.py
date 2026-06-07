"""Validation-only SITL injection helpers for typed /api/v1 routes."""

from __future__ import annotations

import os
import time
from typing import Any, Dict

from fastapi import status
from fastapi.responses import JSONResponse, Response

from classes.api_v1_contracts import (
    SITLCommanderPublishFailureInjection,
    SITLMavlink2RestTimeoutInjection,
    SITLMavsdkDisconnectInjection,
    SITLTrackerOutputInjection,
    SITLVideoStallInjection,
)
from classes.api_v1_errors import build_sitl_error_response
from classes.api_v1_paths import (
    SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH,
    SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH,
    SITL_MAVSDK_DISCONNECT_INJECTION_PATH,
    SITL_TRACKER_OUTPUT_INJECTION_PATH,
    SITL_VIDEO_STALL_INJECTION_PATH,
)
from classes.tracker_output import TrackerDataType, TrackerOutput


def sitl_injections_enabled() -> bool:
    """Return True only when validation-only mutation routes are enabled."""
    return os.getenv("PIXEAGLE_ENABLE_SITL_INJECTIONS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def sitl_error_response(
    *,
    status_code: int,
    code: str,
    detail: Any,
    path: str = SITL_TRACKER_OUTPUT_INJECTION_PATH,
) -> JSONResponse:
    """Build a typed /api/v1 error envelope for SITL validation routes."""
    return build_sitl_error_response(
        status_code=status_code,
        code=code,
        detail=detail,
        path=path,
    )


def _disabled_response(path: str = SITL_TRACKER_OUTPUT_INJECTION_PATH) -> JSONResponse:
    return sitl_error_response(
        status_code=status.HTTP_403_FORBIDDEN,
        code="SITL_INJECTIONS_DISABLED",
        detail={
            "message": (
                "Set PIXEAGLE_ENABLE_SITL_INJECTIONS=1 only for an "
                "operator-approved validation stack."
            ),
        },
        path=path,
    )


def parse_tracker_data_type(value: str) -> TrackerDataType:
    token = str(value).strip()
    if token in TrackerDataType.__members__:
        return TrackerDataType[token]

    upper_token = token.upper()
    if upper_token in TrackerDataType.__members__:
        return TrackerDataType[upper_token]

    try:
        return TrackerDataType(token)
    except ValueError:
        try:
            return TrackerDataType(upper_token)
        except ValueError as exc:
            valid = ", ".join(item.value for item in TrackerDataType)
            raise ValueError(
                f"Unsupported tracker data_type {value!r}. Valid values: {valid}"
            ) from exc


def tracker_output_from_sitl_injection(
    injection: SITLTrackerOutputInjection,
) -> TrackerOutput:
    """Build TrackerOutput from the typed validation injection request."""
    raw_data = dict(injection.raw_data or {})
    metadata = dict(injection.metadata or {})

    freshness_fields = {
        "usable_for_following": injection.usable_for_following,
        "data_is_stale": injection.data_is_stale,
        "freshness_reason": injection.freshness_reason,
        "has_output": injection.has_output,
    }
    for key, value in freshness_fields.items():
        if value is not None:
            raw_data.setdefault(key, value)
            metadata.setdefault(key, value)

    raw_data.setdefault("sitl_injection", True)
    raw_data.setdefault("sitl_injection_id", injection.injection_id)
    metadata.setdefault("source", injection.source)
    metadata.setdefault("sitl_injection", True)
    metadata.setdefault("sitl_injection_id", injection.injection_id)

    return TrackerOutput(
        data_type=parse_tracker_data_type(injection.data_type),
        timestamp=injection.timestamp or time.time(),
        tracking_active=injection.tracking_active,
        tracker_id=injection.tracker_id,
        position_2d=injection.position_2d,
        position_3d=injection.position_3d,
        angular=injection.angular,
        bbox=injection.bbox,
        normalized_bbox=injection.normalized_bbox,
        confidence=injection.confidence,
        quality_metrics=dict(injection.quality_metrics or {}),
        velocity=injection.velocity,
        acceleration=injection.acceleration,
        target_id=injection.target_id,
        targets=injection.targets,
        raw_data=raw_data,
        metadata=metadata,
    )


def frame_status_from_sitl_video_stall(
    injection: SITLVideoStallInjection,
) -> Dict[str, Any]:
    """Build frame freshness metadata from a validation video-stall request."""
    frame_status = {
        "source": injection.frame_source,
        "status": injection.frame_status,
        "usable_for_following": injection.usable_for_following,
        "reason": injection.reason,
        "timestamp": injection.timestamp or time.time(),
        "sitl_injection": True,
        "sitl_injection_id": injection.injection_id,
    }
    if injection.consecutive_failures is not None:
        frame_status["consecutive_failures"] = injection.consecutive_failures
    if injection.metadata:
        frame_status["metadata"] = dict(injection.metadata)
    return frame_status


async def inject_sitl_tracker_output(
    owner: Any,
    injection: SITLTrackerOutputInjection,
    response: Response,
) -> Any:
    """
    Validation-only handler for injecting TrackerOutput into follow mode.

    The route is disabled by default and exists for operator-gated SITL runs.
    It never starts PX4, routing, video, Docker, or Offboard mode.
    """
    if not sitl_injections_enabled():
        return _disabled_response()

    try:
        tracker_output = tracker_output_from_sitl_injection(injection)
    except ValueError as exc:
        return sitl_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="INVALID_TRACKER_OUTPUT",
            detail={"message": str(exc)},
        )

    app_controller = owner.app_controller
    if injection.dry_run:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "validated",
            "accepted": False,
            "reason": "dry_run",
            "following_active": bool(getattr(app_controller, "following_active", False)),
            "injection": {
                "source": injection.source,
                "tracker_id": tracker_output.tracker_id,
                "data_type": tracker_output.data_type.value,
                "input_tracking_active": tracker_output.tracking_active,
            },
            "command_intent": None,
            "offboard_commander": None,
            "timestamp": time.time(),
        }

    if not hasattr(app_controller, "inject_tracker_output_for_validation"):
        return sitl_error_response(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="SITL_INJECTION_UNAVAILABLE",
            detail={
                "message": "AppController validation injection hook is unavailable.",
            },
        )

    result = await app_controller.inject_tracker_output_for_validation(
        tracker_output,
        source=injection.source,
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED
        if result.get("accepted") is True
        else status.HTTP_409_CONFLICT
    )
    if result.get("accepted") is not True:
        return sitl_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SITL_INJECTION_REJECTED",
            detail=result,
        )
    return result


async def inject_sitl_video_stall(
    owner: Any,
    injection: SITLVideoStallInjection,
    response: Response,
) -> Any:
    """
    Validation-only handler for injecting video-frame stall metadata.

    The route is disabled by default and uses the same fail-closed path as the
    main frame loop when VideoHandler cannot provide a fresh frame.
    """
    if not sitl_injections_enabled():
        return _disabled_response(SITL_VIDEO_STALL_INJECTION_PATH)

    app_controller = owner.app_controller
    frame_status = frame_status_from_sitl_video_stall(injection)

    if injection.dry_run:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "validated",
            "accepted": False,
            "reason": "dry_run",
            "following_active": bool(getattr(app_controller, "following_active", False)),
            "injection": {
                "source": injection.source,
                "tracker_requires_video": bool(
                    app_controller._tracker_requires_video_for_following()
                )
                if hasattr(app_controller, "_tracker_requires_video_for_following")
                else True,
                "frame_status": frame_status,
            },
            "command_intent": None,
            "offboard_commander": None,
            "timestamp": time.time(),
        }

    if not hasattr(app_controller, "inject_video_stall_for_validation"):
        return sitl_error_response(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="SITL_INJECTION_UNAVAILABLE",
            detail={
                "message": "AppController video-stall validation hook is unavailable.",
            },
            path=SITL_VIDEO_STALL_INJECTION_PATH,
        )

    result = await app_controller.inject_video_stall_for_validation(
        frame_status,
        source=injection.source,
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED
        if result.get("accepted") is True
        else status.HTTP_409_CONFLICT
    )
    if result.get("accepted") is not True:
        return sitl_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SITL_INJECTION_REJECTED",
            detail=result,
            path=SITL_VIDEO_STALL_INJECTION_PATH,
        )
    return result


async def inject_sitl_commander_publish_failure(
    owner: Any,
    injection: SITLCommanderPublishFailureInjection,
    response: Response,
) -> Any:
    """
    Validation-only handler for commander publish-failure policy checks.

    The route records bounded synthetic publish failures inside the active
    OffboardCommander and exercises local fail-closed cleanup without sending
    synthetic MAVSDK setpoints, stopping services, or changing MAVLink routing.
    """
    if not sitl_injections_enabled():
        return _disabled_response(SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH)

    app_controller = owner.app_controller
    if injection.dry_run:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "validated",
            "accepted": False,
            "reason": "dry_run",
            "following_active": bool(getattr(app_controller, "following_active", False)),
            "injection": {
                "source": injection.source,
                "failure_mode": injection.failure_mode,
                "requested_failure_count": injection.failure_count,
                "applied_failure_count": 0,
                "failure_reason": injection.reason,
                "metadata": dict(injection.metadata or {}),
            },
            "offboard_commander": None,
            "offboard_commander_before": None,
            "offboard_commander_after": None,
            "offboard_commander_failure": None,
            "disconnect_result": None,
            "timestamp": time.time(),
        }

    if not hasattr(
        app_controller,
        "inject_commander_publish_failure_for_validation",
    ):
        return sitl_error_response(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="SITL_INJECTION_UNAVAILABLE",
            detail={
                "message": (
                    "AppController commander publish-failure validation "
                    "hook is unavailable."
                ),
            },
            path=SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH,
        )

    result = await app_controller.inject_commander_publish_failure_for_validation(
        failure_count=injection.failure_count,
        reason=injection.reason,
        source=injection.source,
        metadata={
            **dict(injection.metadata or {}),
            "sitl_injection": True,
            "sitl_injection_id": injection.injection_id,
        },
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED
        if result.get("accepted") is True
        else status.HTTP_409_CONFLICT
    )
    if result.get("accepted") is not True:
        return sitl_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SITL_INJECTION_REJECTED",
            detail=result,
            path=SITL_COMMANDER_PUBLISH_FAILURE_INJECTION_PATH,
        )
    return result


async def inject_sitl_mavsdk_disconnect(
    owner: Any,
    injection: SITLMavsdkDisconnectInjection,
    response: Response,
) -> Any:
    """
    Validation-only handler for local MAVSDK command-path disconnect.

    This marks PixEagle's local PX4/MAVSDK command path disconnected, records
    bounded OffboardCommander publish failures, then awaits the existing
    fail-closed cleanup path. It does not stop PX4, Docker, MavlinkAnywhere,
    MAVLink2REST, network interfaces, MAVSDK server, or MAVLink routes.
    """
    if not sitl_injections_enabled():
        return _disabled_response(SITL_MAVSDK_DISCONNECT_INJECTION_PATH)

    app_controller = owner.app_controller
    if injection.dry_run:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "validated",
            "accepted": False,
            "reason": "dry_run",
            "following_active": bool(getattr(app_controller, "following_active", False)),
            "injection": {
                "source": injection.source,
                "failure_mode": injection.failure_mode,
                "requested_failure_count": injection.failure_count,
                "applied_failure_count": 0,
                "failure_reason": injection.reason,
                "metadata": dict(injection.metadata or {}),
            },
            "px4_connection_before": None,
            "px4_connection_after": None,
            "offboard_commander": None,
            "offboard_commander_before": None,
            "offboard_commander_after": None,
            "offboard_commander_failure": None,
            "disconnect_result": None,
            "timestamp": time.time(),
        }

    if not hasattr(app_controller, "inject_mavsdk_disconnect_for_validation"):
        return sitl_error_response(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="SITL_INJECTION_UNAVAILABLE",
            detail={
                "message": (
                    "AppController MAVSDK disconnect validation hook is unavailable."
                ),
            },
            path=SITL_MAVSDK_DISCONNECT_INJECTION_PATH,
        )

    result = await app_controller.inject_mavsdk_disconnect_for_validation(
        failure_count=injection.failure_count,
        reason=injection.reason,
        source=injection.source,
        failure_mode=injection.failure_mode,
        metadata={
            **dict(injection.metadata or {}),
            "sitl_injection": True,
            "sitl_injection_id": injection.injection_id,
            "stimulus": "mavsdk_disconnect",
            "transport_scope": "pixeagle_local_only",
        },
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED
        if result.get("accepted") is True
        else status.HTTP_409_CONFLICT
    )
    if result.get("accepted") is not True:
        return sitl_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SITL_INJECTION_REJECTED",
            detail=result,
            path=SITL_MAVSDK_DISCONNECT_INJECTION_PATH,
        )
    return result


async def inject_sitl_mavlink2rest_timeout(
    owner: Any,
    injection: SITLMavlink2RestTimeoutInjection,
    response: Response,
) -> Any:
    """
    Validation-only handler for MAVLink2REST client timeout freshness.

    The route records local telemetry transport timeout state in
    MavlinkDataManager without stopping MAVLink2REST, Docker, PX4, MAVLink
    routing, or network interfaces.
    """
    if not sitl_injections_enabled():
        return _disabled_response(SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH)

    app_controller = owner.app_controller
    if injection.dry_run:
        response.status_code = status.HTTP_200_OK
        return {
            "status": "validated",
            "accepted": False,
            "reason": "dry_run",
            "injection": {
                "source": injection.source,
                "requested_failure_count": injection.failure_count,
                "applied_failure_count": 0,
                "failure_reason": injection.reason,
                "force_stale": injection.force_stale,
                "timeout_window_s": injection.timeout_window_s,
                "metadata": dict(injection.metadata or {}),
            },
            "mavlink_telemetry": None,
            "timestamp": time.time(),
        }

    if not hasattr(app_controller, "inject_mavlink2rest_timeout_for_validation"):
        return sitl_error_response(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="SITL_INJECTION_UNAVAILABLE",
            detail={
                "message": (
                    "AppController MAVLink2REST timeout validation hook is unavailable."
                ),
            },
            path=SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH,
        )

    result = await app_controller.inject_mavlink2rest_timeout_for_validation(
        failure_count=injection.failure_count,
        reason=injection.reason,
        force_stale=injection.force_stale,
        timeout_window_s=injection.timeout_window_s,
        source=injection.source,
        metadata={
            **dict(injection.metadata or {}),
            "sitl_injection": True,
            "sitl_injection_id": injection.injection_id,
        },
    )
    response.status_code = (
        status.HTTP_202_ACCEPTED
        if result.get("accepted") is True
        else status.HTTP_409_CONFLICT
    )
    if result.get("accepted") is not True:
        return sitl_error_response(
            status_code=status.HTTP_409_CONFLICT,
            code="SITL_INJECTION_REJECTED",
            detail=result,
            path=SITL_MAVLINK2REST_TIMEOUT_INJECTION_PATH,
        )
    return result


__all__ = [
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
]
