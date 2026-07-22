"""Canonical live tracker/video readiness for autonomous Following startup."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from classes.circuit_breaker import FollowerCircuitBreaker
from classes.command_preview import (
    COMMAND_PREVIEW_EXECUTION_MODE,
    PX4_EXECUTION_MODE,
    normalize_follower_execution_mode,
)
from classes.parameters import Parameters
from classes.tracker_runtime_status import (
    evaluate_tracker_runtime_status,
    tracker_runtime_unavailable_status,
)


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def get_controller_tracker_runtime_status(app_controller: Any) -> Dict[str, Any]:
    """Evaluate the controller's current tracker output without API-layer state."""
    configured_tracker = getattr(
        app_controller,
        "current_tracker_type",
        getattr(Parameters, "DEFAULT_TRACKING_ALGORITHM", None),
    )
    tracker = getattr(app_controller, "tracker", None)
    tracker_type = tracker.__class__.__name__ if tracker is not None else None
    smart_mode_active = bool(getattr(app_controller, "smart_mode_active", False))
    following_active = bool(getattr(app_controller, "following_active", False))
    output_getter = getattr(app_controller, "get_tracker_output", None)
    if not callable(output_getter):
        return tracker_runtime_unavailable_status(
            "Tracker output API not available.",
            configured_tracker=configured_tracker,
            tracker_type=tracker_type,
            smart_mode_active=smart_mode_active,
            following_active=following_active,
        )

    try:
        tracker_output = output_getter()
    except Exception as exc:
        return tracker_runtime_unavailable_status(
            f"Tracker output unavailable: {type(exc).__name__}: {exc}",
            configured_tracker=configured_tracker,
            tracker_type=tracker_type,
            smart_mode_active=smart_mode_active,
            following_active=following_active,
        )

    return evaluate_tracker_runtime_status(
        tracker_output,
        configured_tracker=configured_tracker,
        tracker_type=tracker_type,
        smart_mode_active=smart_mode_active,
        following_active=following_active,
    )


def evaluate_following_start_readiness(
    app_controller: Any,
    *,
    runtime_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return one fail-closed live readiness result for Following startup."""
    if app_controller is None:
        runtime_status = tracker_runtime_unavailable_status(
            "Application controller is unavailable.",
            configured_tracker=None,
            tracker_type=None,
            smart_mode_active=False,
            following_active=False,
        )
    elif not isinstance(runtime_status, dict):
        runtime_status = get_controller_tracker_runtime_status(app_controller)
    else:
        runtime_status = dict(runtime_status)

    requires_video_getter = getattr(
        app_controller,
        "_tracker_requires_video_for_following",
        None,
    )
    video_handler = getattr(app_controller, "video_handler", None)
    frame_status_getter = getattr(video_handler, "get_frame_status", None)

    tracker_requires_video = True
    if callable(requires_video_getter):
        try:
            tracker_requires_video = bool(requires_video_getter())
        except Exception:
            tracker_requires_video = True

    frame_status: Dict[str, Any] = {}
    frame_status_available = callable(frame_status_getter)
    if frame_status_available:
        try:
            frame_status = _mapping(frame_status_getter())
        except Exception:
            frame_status_available = False

    readiness = {
        **runtime_status,
        "tracking_active": bool(runtime_status.get("active_tracking", False)),
        "tracker_requires_video": tracker_requires_video,
        "video_frame_status": frame_status,
    }

    if not runtime_status.get("usable_for_following", False):
        return readiness
    if not tracker_requires_video:
        return readiness
    if not frame_status_available:
        return {
            **readiness,
            "status": "not_usable",
            "consumer_guidance": "not_usable",
            "usable_for_following": False,
            "reason": "Video frame readiness is unavailable",
        }
    if frame_status.get("replay_source") is True:
        return {
            **readiness,
            "status": "not_usable",
            "consumer_guidance": "not_usable",
            "usable_for_following": False,
            "reason": "Video-file replay is not authorized for autonomous following",
        }
    if frame_status.get("usable_for_following") is not True:
        frame_reason = frame_status.get("reason")
        return {
            **readiness,
            "status": "not_usable",
            "consumer_guidance": "not_usable",
            "usable_for_following": False,
            "reason": (
                f"Video frame is not usable for following: {frame_reason}"
                if frame_reason
                else "Video frame is not fresh and usable for following"
            ),
        }
    return readiness


def get_configured_follower_execution_mode() -> str:
    """Return the validated configured follower execution mode."""
    return normalize_follower_execution_mode(
        getattr(Parameters, "FOLLOWER_EXECUTION_MODE", PX4_EXECUTION_MODE)
    )


def evaluate_command_preview_start_readiness(
    app_controller: Any,
    *,
    runtime_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate the explicit local tracker-to-intent preview contract.

    Preview accepts a fresh live or replay frame and an active, measured target.
    It bypasses operational envelope checks only inside a controller with no
    PX4/MAVSDK publisher.  Target freshness, schema, and finite-value validation
    remain mandatory.
    """
    if app_controller is None:
        return {
            "execution_mode": COMMAND_PREVIEW_EXECUTION_MODE,
            "configured": False,
            "ready": False,
            "usable_for_command_preview": False,
            "autonomous_following_authorized": False,
            "commands_sent_to_px4": False,
            "operational_limits_enforced": False,
            "target_freshness_required": True,
            "finite_validation_required": True,
            "warnings": [],
            "reason": "Application controller is unavailable.",
            "circuit_breaker": None,
            "video_frame_status": {},
        }

    execution_mode = get_configured_follower_execution_mode()
    base_runtime = (
        dict(runtime_status)
        if isinstance(runtime_status, dict)
        else get_controller_tracker_runtime_status(app_controller)
    )
    requires_video_getter = getattr(
        app_controller,
        "_tracker_requires_video_for_following",
        None,
    )
    tracker_requires_video = True
    if callable(requires_video_getter):
        try:
            tracker_requires_video = bool(requires_video_getter())
        except Exception:
            tracker_requires_video = True

    video_handler = getattr(app_controller, "video_handler", None)
    frame_status_getter = getattr(video_handler, "get_frame_status", None)
    frame_status: Dict[str, Any] = {}
    if callable(frame_status_getter):
        try:
            frame_status = _mapping(frame_status_getter())
        except Exception:
            frame_status = {}

    try:
        circuit_state = dict(FollowerCircuitBreaker.get_activation_state())
    except Exception as exc:
        circuit_state = {
            "available": False,
            "active": True,
            "reason": f"circuit_breaker_state_unavailable:{exc}",
        }

    result: Dict[str, Any] = {
        **base_runtime,
        "execution_mode": execution_mode,
        "configured": execution_mode == COMMAND_PREVIEW_EXECUTION_MODE,
        "ready": False,
        "usable_for_command_preview": False,
        "autonomous_following_authorized": False,
        "commands_sent_to_px4": False,
        "tracker_requires_video": tracker_requires_video,
        "video_frame_status": frame_status,
        "circuit_breaker": circuit_state,
        "operational_limits_enforced": False,
        "target_freshness_required": True,
        "finite_validation_required": True,
        "warnings": [],
    }

    if execution_mode != COMMAND_PREVIEW_EXECUTION_MODE:
        result["reason"] = (
            "Command preview is disabled; set "
            "Follower.FOLLOWER_EXECUTION_MODE=COMMAND_PREVIEW explicitly."
        )
        return result

    if circuit_state.get("available") is not True:
        result["reason"] = (
            "Command preview requires an available circuit breaker; "
            "PX4 command dispatch remains fail-closed."
        )
        return result
    if circuit_state.get("active") is not True:
        result["reason"] = (
            "Command preview requires the circuit breaker to remain active."
        )
        return result
    if not base_runtime.get("usable_for_following", False):
        result["reason"] = str(
            base_runtime.get("reason")
            or "Tracker output is not active and usable for command preview."
        )
        return result

    if not frame_status_getter or not frame_status:
        result["reason"] = "Video frame readiness is unavailable."
        return result
    if frame_status.get("source") != "fresh":
        result["reason"] = (
            "The video source has not produced a fresh frame; cached or EOF "
            "frames cannot drive command preview."
        )
        return result
    if frame_status.get("connection_open") is not True:
        result["reason"] = "The configured video-file source is not open."
        return result

    result.update(
        {
            "ready": True,
            "usable_for_command_preview": True,
            "reason": "Fresh target input is ready for local follower intent testing.",
        }
    )
    return result


__all__ = [
    "COMMAND_PREVIEW_EXECUTION_MODE",
    "evaluate_following_start_readiness",
    "evaluate_command_preview_start_readiness",
    "get_configured_follower_execution_mode",
    "get_controller_tracker_runtime_status",
]
