"""Legacy command-route execution helpers.

These functions keep dangerous compatibility-route bodies out of the large
FastAPI handler while preserving the existing route methods and payload shapes.
New control-plane integrations should use the typed /api/v1 action routes.
"""

from __future__ import annotations

import time
import traceback
from typing import Any

from fastapi import HTTPException


async def cancel_activities(owner: Any) -> Any:
    """Execute the legacy operator-cancel compatibility route."""
    following_before = bool(getattr(owner.app_controller, "following_active", False))
    try:
        result = await owner.app_controller.cancel_activities_async()
        following_after = bool(getattr(owner.app_controller, "following_active", False))
        return owner._attach_legacy_action_audit(
            {"status": "success", "result": result},
            action_type="operator_abort",
            route="/commands/cancel_activities",
            following_active_before=following_before,
            following_active_after=following_after,
        )
    except Exception as e:
        following_after = bool(getattr(owner.app_controller, "following_active", False))
        owner.logger.error(f"Error in cancel_activities: {e}")
        owner._attach_legacy_action_audit(
            {"status": "failure", "error": str(e)},
            action_type="operator_abort",
            route="/commands/cancel_activities",
            following_active_before=following_before,
            following_active_after=following_after,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


async def start_offboard_mode(owner: Any) -> Any:
    """Execute the legacy Offboard-start compatibility route."""
    start_time = time.time()
    following_before = bool(getattr(owner.app_controller, "following_active", False))

    try:
        initial_state = "active" if owner.app_controller.following_active else "inactive"
        owner.logger.info(
            f"📥 API: Start offboard mode requested (current state: {initial_state})"
        )

        validation_errors = []

        if not hasattr(owner.app_controller, "px4_interface"):
            validation_errors.append("PX4 interface not initialized")

        if not hasattr(owner.app_controller, "tracker"):
            validation_errors.append("Tracker not initialized")

        if not hasattr(owner.app_controller, "video_handler"):
            validation_errors.append("Video handler not initialized")

        tracker_runtime = owner._get_tracker_following_readiness()
        if not tracker_runtime.get("usable_for_following", False):
            validation_errors.append(
                tracker_runtime.get(
                    "reason",
                    "Tracker output is not usable for following",
                )
            )

        if validation_errors:
            error_msg = f"Pre-flight validation failed: {', '.join(validation_errors)}"
            owner.logger.error(f"❌ {error_msg}")
            return owner._attach_legacy_action_audit(
                {
                    "status": "failure",
                    "error": error_msg,
                    "details": {
                        "steps": [],
                        "errors": validation_errors,
                        "auto_stopped": False,
                        "initial_state": initial_state,
                        "final_state": initial_state,
                        "tracker_runtime": tracker_runtime,
                    },
                },
                action_type="offboard_start",
                route="/commands/start_offboard_mode",
                following_active_before=following_before,
                following_active_after=following_before,
                error=error_msg,
            )

        result = await owner.app_controller.connect_px4()

        final_state = "active" if owner.app_controller.following_active else "inactive"
        execution_time_ms = (time.time() - start_time) * 1000

        result["initial_state"] = initial_state
        result["final_state"] = final_state
        result["execution_time_ms"] = round(execution_time_ms, 2)

        if result.get("errors") or final_state != "active":
            error_msg = (
                "; ".join(result.get("errors", []))
                or "Offboard mode did not become active"
            )
            owner.logger.error(
                f"❌ API: Offboard mode start failed "
                f"({initial_state} → {final_state}, {execution_time_ms:.0f}ms): {error_msg}"
            )
            return owner._attach_legacy_action_audit(
                {
                    "status": "failure",
                    "error": error_msg,
                    "details": result,
                },
                action_type="offboard_start",
                route="/commands/start_offboard_mode",
                following_active_before=following_before,
                following_active_after=bool(
                    getattr(owner.app_controller, "following_active", False)
                ),
                error=error_msg,
            )

        if result.get("auto_stopped", False):
            owner.logger.info(
                f"✅ API: Offboard mode restarted successfully "
                f"({initial_state} → {final_state}, {execution_time_ms:.0f}ms)"
            )
        else:
            owner.logger.info(
                f"✅ API: Offboard mode started successfully "
                f"({initial_state} → {final_state}, {execution_time_ms:.0f}ms)"
            )

        return owner._attach_legacy_action_audit(
            {"status": "success", "details": result},
            action_type="offboard_start",
            route="/commands/start_offboard_mode",
            following_active_before=following_before,
            following_active_after=bool(
                getattr(owner.app_controller, "following_active", False)
            ),
        )

    except Exception as e:
        execution_time_ms = (time.time() - start_time) * 1000
        error_msg = str(e)

        owner.logger.error(f"❌ API: Error in start_offboard_mode: {error_msg}")
        owner.logger.error(f"Exception type: {type(e).__name__}")
        owner.logger.debug(f"Stack trace:\n{traceback.format_exc()}")

        try:
            final_state = "active" if owner.app_controller.following_active else "inactive"
        except BaseException:
            final_state = "unknown"

        return owner._attach_legacy_action_audit(
            {
                "status": "failure",
                "error": error_msg,
                "details": {
                    "steps": [],
                    "errors": [error_msg],
                    "auto_stopped": False,
                    "initial_state": (
                        initial_state if "initial_state" in locals() else "unknown"
                    ),
                    "final_state": final_state,
                    "execution_time_ms": round(execution_time_ms, 2),
                    "exception_type": type(e).__name__,
                },
            },
            action_type="offboard_start",
            route="/commands/start_offboard_mode",
            following_active_before=following_before,
            following_active_after=(
                None if final_state == "unknown" else final_state == "active"
            ),
            error=error_msg,
        )
