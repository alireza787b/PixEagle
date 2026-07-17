"""Canonical live tracker/video readiness for autonomous Following startup."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

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


__all__ = [
    "evaluate_following_start_readiness",
    "get_controller_tracker_runtime_status",
]
