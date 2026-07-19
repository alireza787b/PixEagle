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
    """Evaluate the explicit local replay-to-intent preview contract.

    This deliberately does not reuse autonomous Following readiness: replay is
    prohibited there.  Preview requires an active, available circuit breaker,
    a video-file source, and an active tracker output.  It never authorizes a
    PX4/MAVSDK command path.
    """
    if app_controller is None:
        return {
            "execution_mode": COMMAND_PREVIEW_EXECUTION_MODE,
            "configured": False,
            "ready": False,
            "usable_for_command_preview": False,
            "autonomous_following_authorized": False,
            "commands_sent_to_px4": False,
            "safety_checks_enabled": True,
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

    safety_bypass_active = bool(
        getattr(Parameters, "CIRCUIT_BREAKER_DISABLE_SAFETY", False)
    )
    missing_safety_modules_bypass_active = bool(
        getattr(
            Parameters,
            "FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES",
            False,
        )
    )
    warnings = []
    if execution_mode == COMMAND_PREVIEW_EXECUTION_MODE and safety_bypass_active:
        warnings.append(
            "Follower calculation safety checks are bypassed for this local test; "
            "PX4/MAVSDK command publication remains disabled."
        )
    if (
        execution_mode == COMMAND_PREVIEW_EXECUTION_MODE
        and missing_safety_modules_bypass_active
    ):
        warnings.append(
            "The dangerous safety-module failure bypass is enabled. It can permit "
            "live PX4 commands when safety infrastructure fails, but this local "
            "COMMAND_PREVIEW session has no PX4/MAVSDK publisher."
        )

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
        "safety_bypass_active": safety_bypass_active,
        "missing_safety_modules_bypass_active": (
            missing_safety_modules_bypass_active
        ),
        "safety_checks_enabled": not safety_bypass_active,
        "warnings": warnings,
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
    if frame_status.get("replay_source") is not True:
        result["reason"] = (
            "Command preview requires VideoSource.VIDEO_SOURCE_TYPE=VIDEO_FILE; "
            "live sources remain on the PX4 readiness path."
        )
        return result
    if frame_status.get("source") != "fresh":
        result["reason"] = (
            "The replay source has not produced a fresh frame; cached or EOF "
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
            "reason": (
                "Video replay is ready for a local follower test only. "
                "Diagnostic bypasses are enabled, but this COMMAND_PREVIEW "
                "session has no PX4/MAVSDK publisher."
                if warnings
                else "Video replay is ready for a local follower test only."
            ),
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
