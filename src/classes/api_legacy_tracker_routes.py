"""Legacy tracker route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from classes.parameters import Parameters


def _tracking_started(app_controller: Any) -> bool:
    return bool(
        hasattr(app_controller, "tracking_started")
        and app_controller.tracking_started
    )


def _tracking_active(app_controller: Any) -> bool:
    return bool(
        hasattr(app_controller, "tracker")
        and app_controller.tracker is not None
        and getattr(app_controller, "tracking_active", False)
    )


async def get_available_trackers(handler: Any) -> JSONResponse:
    """Get available UI-selectable classic trackers."""
    try:
        from classes.schema_manager import get_schema_manager

        schema_manager = get_schema_manager()
        classic_trackers = schema_manager.get_available_classic_trackers()
        current_tracker_type = getattr(
            handler.app_controller,
            "current_tracker_type",
            Parameters.DEFAULT_TRACKING_ALGORITHM,
        )

        return JSONResponse(
            content={
                "available_trackers": classic_trackers,
                "current_configured": current_tracker_type,
                "tracking_active": _tracking_started(handler.app_controller),
                "smart_mode_active": getattr(
                    handler.app_controller,
                    "smart_mode_active",
                    False,
                ),
                "total_trackers": len(classic_trackers),
                "timestamp": time.time(),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error getting available trackers: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_current_tracker(handler: Any) -> JSONResponse:
    """Get current tracker information and runtime status."""
    try:
        from classes.schema_manager import get_schema_manager

        schema_manager = get_schema_manager()
        current_tracker_type = getattr(
            handler.app_controller,
            "current_tracker_type",
            Parameters.DEFAULT_TRACKING_ALGORITHM,
        )
        tracking_active = _tracking_started(handler.app_controller)

        tracker_info = schema_manager.get_tracker_info(current_tracker_type)

        if tracker_info:
            ui_metadata = tracker_info.get("ui_metadata", {})
            tracker_details = {
                "status": "tracking" if tracking_active else "configured",
                "active": tracking_active,
                "tracker_type": current_tracker_type,
                "display_name": ui_metadata.get(
                    "display_name",
                    current_tracker_type,
                ),
                "description": tracker_info.get("description", ""),
                "short_description": ui_metadata.get("short_description", ""),
                "icon": ui_metadata.get("icon", "\U0001f3af"),
                "performance_category": ui_metadata.get(
                    "performance_category",
                    "unknown",
                ),
                "supported_schemas": tracker_info.get("supported_schemas", []),
                "capabilities": tracker_info.get("capabilities", []),
                "performance": tracker_info.get("performance", {}),
                "suitable_for": ui_metadata.get("suitable_for", []),
                "message": (
                    "Tracker actively tracking target"
                    if tracking_active
                    else "Tracker configured. Start tracking to activate."
                ),
            }
        else:
            tracker_details = {
                "status": "unknown",
                "active": tracking_active,
                "tracker_type": current_tracker_type,
                "display_name": current_tracker_type,
                "description": "Unknown tracker type",
                "error": (
                    f'Tracker type "{current_tracker_type}" not found in schema'
                ),
            }

        tracker_details["smart_mode_active"] = getattr(
            handler.app_controller,
            "smart_mode_active",
            False,
        )
        tracker_details["following_active"] = getattr(
            handler.app_controller,
            "following_active",
            False,
        )
        runtime_status = handler._get_tracker_runtime_status_snapshot()
        tracker_details["runtime_status"] = runtime_status
        tracker_details["has_output"] = runtime_status["has_output"]
        tracker_details["active_tracking"] = runtime_status["active_tracking"]
        tracker_details["usable_for_following"] = runtime_status[
            "usable_for_following"
        ]
        tracker_details["data_is_stale"] = runtime_status["data_is_stale"]
        tracker_details["runtime_state"] = runtime_status["status"]
        tracker_details["consumer_guidance"] = runtime_status["consumer_guidance"]
        tracker_details["runtime_reason"] = runtime_status["reason"]
        tracker_details["claim_boundary"] = runtime_status["claim_boundary"]
        tracker_details["timestamp"] = time.time()

        return JSONResponse(content=tracker_details)

    except Exception as exc:
        handler.logger.error(f"Error getting current tracker: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def switch_tracker(handler: Any, request: Request) -> JSONResponse:
    """Switch tracker type dynamically through the legacy route."""
    try:
        data = await request.json()
        new_tracker_type = data.get("tracker_type")

        if not new_tracker_type:
            raise HTTPException(status_code=400, detail="tracker_type is required")

        from classes.schema_manager import get_schema_manager

        schema_manager = get_schema_manager()
        is_valid, error_msg = schema_manager.validate_tracker_for_ui(new_tracker_type)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        old_tracker_type = getattr(
            handler.app_controller,
            "current_tracker_type",
            Parameters.DEFAULT_TRACKING_ALGORITHM,
        )
        result = await handler.app_controller.switch_tracker_type(new_tracker_type)

        if result["success"]:
            handler.logger.info(
                f"Tracker switched via API: {old_tracker_type} \u2192 {new_tracker_type}"
            )

            return JSONResponse(
                content={
                    "status": "success",
                    "action": "tracker_switched",
                    "old_tracker": old_tracker_type,
                    "new_tracker": new_tracker_type,
                    "message": result.get(
                        "message",
                        f"Tracker switched to {new_tracker_type}",
                    ),
                    "requires_restart": result.get("requires_restart", False),
                    "details": result,
                }
            )

        error_detail = result.get("error", "Unknown error during tracker switch")
        handler.logger.error(f"Tracker switch failed: {error_detail}")

        return JSONResponse(
            content={
                "status": "error",
                "action": "switch_failed",
                "old_tracker": old_tracker_type,
                "requested_tracker": new_tracker_type,
                "error": error_detail,
                "details": result,
            },
            status_code=500,
        )

    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error switching tracker: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def restart_tracker(handler: Any) -> JSONResponse:
    """Restart the configured tracker with fresh config through the legacy route."""
    allowed, retry_after = handler.config_rate_limiter.is_allowed("config_write")
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": "Too many restart requests",
                "retry_after": retry_after,
                "timestamp": time.time(),
            },
            headers={"Retry-After": str(retry_after)},
        )

    try:
        Parameters.reload_config()
        handler.logger.info("Config reloaded for tracker restart")

        current_tracker_type = getattr(
            handler.app_controller,
            "current_tracker_type",
            Parameters.DEFAULT_TRACKING_ALGORITHM,
        )
        result = await handler.app_controller.switch_tracker_type(current_tracker_type)

        if result.get("success"):
            handler.logger.info(f"Tracker reinitialized: {current_tracker_type}")

            return JSONResponse(
                content={
                    "success": True,
                    "action": "tracker_restarted",
                    "tracker_type": current_tracker_type,
                    "message": (
                        f"Tracker {current_tracker_type} reinitialized with fresh config"
                    ),
                    "config_reloaded": True,
                    "details": result,
                }
            )

        error_detail = result.get("error", "Unknown error during tracker restart")
        handler.logger.error(f"Tracker restart failed: {error_detail}")

        return JSONResponse(
            content={
                "success": False,
                "action": "restart_failed",
                "tracker_type": current_tracker_type,
                "error": error_detail,
                "config_reloaded": True,
                "details": result,
            },
            status_code=500,
        )

    except Exception as exc:
        handler.logger.error(f"Error restarting tracker: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_current_tracker_config(handler: Any) -> JSONResponse:
    """Get the current legacy tracker configuration summary."""
    try:
        current_type = getattr(handler.app_controller, "current_tracker_type", "CSRT")
        is_smart_active = getattr(handler.app_controller, "smart_mode_active", False)
        is_tracking_active = _tracking_active(handler.app_controller)
        expected_data_type = "BBOX_CONFIDENCE" if is_smart_active else "POSITION_2D"

        return JSONResponse(
            content={
                "configured_tracker": current_type,
                "smart_mode_active": is_smart_active,
                "tracking_active": is_tracking_active,
                "expected_data_type": expected_data_type,
                "active_tracker_class": (
                    handler.app_controller.tracker.__class__.__name__
                    if handler.app_controller.tracker
                    else None
                ),
                "status": "active" if is_tracking_active else "configured",
                "timestamp": time.time(),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error getting current tracker config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


__all__ = [
    "get_available_trackers",
    "get_current_tracker",
    "get_current_tracker_config",
    "restart_tracker",
    "switch_tracker",
]
