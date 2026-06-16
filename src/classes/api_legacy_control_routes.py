"""Internal compatibility executors for typed Offboard/operator actions.

The former `/commands/start_offboard_mode`, `/commands/stop_offboard_mode`, and
`/commands/cancel_activities` HTTP aliases are retired. These helpers preserve
the existing execution bodies and result payloads behind typed `/api/v1/actions`
resources until the lower-level control executor is fully refactored.
"""

from __future__ import annotations

import time
import traceback
from typing import Any

from fastapi import HTTPException


async def cancel_activities(owner: Any) -> Any:
    """Execute the internal operator-cancel compatibility handler."""
    following_before = bool(getattr(owner.app_controller, "following_active", False))
    try:
        result = await owner.app_controller.cancel_activities_async()
        following_after = bool(getattr(owner.app_controller, "following_active", False))
        return owner._attach_legacy_action_audit(
            {"status": "success", "result": result},
            action_type="operator_abort",
            internal_handler="api_legacy_control_routes.cancel_activities",
            following_active_before=following_before,
            following_active_after=following_after,
        )
    except Exception as e:
        following_after = bool(getattr(owner.app_controller, "following_active", False))
        owner.logger.error(f"Error in cancel_activities: {e}")
        owner._attach_legacy_action_audit(
            {"status": "failure", "error": str(e)},
            action_type="operator_abort",
            internal_handler="api_legacy_control_routes.cancel_activities",
            following_active_before=following_before,
            following_active_after=following_after,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


async def start_offboard_mode(owner: Any) -> Any:
    """Execute the internal Offboard-start compatibility handler."""
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
                internal_handler="api_legacy_control_routes.start_offboard_mode",
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
                internal_handler="api_legacy_control_routes.start_offboard_mode",
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
            internal_handler="api_legacy_control_routes.start_offboard_mode",
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
            internal_handler="api_legacy_control_routes.start_offboard_mode",
            following_active_before=following_before,
            following_active_after=(
                None if final_state == "unknown" else final_state == "active"
            ),
            error=error_msg,
        )


async def stop_offboard_mode(owner: Any) -> Any:
    """Execute the internal Offboard-stop compatibility handler."""
    start_time = time.time()
    following_before = bool(getattr(owner.app_controller, "following_active", False))

    try:
        initial_state = "active" if owner.app_controller.following_active else "inactive"
        was_active = owner.app_controller.following_active

        owner.logger.info(
            f"📥 API: Stop offboard mode requested (current state: {initial_state})"
        )

        if not was_active:
            owner.logger.info("ℹ️ API: Follower already inactive, nothing to stop")
            return owner._attach_legacy_action_audit(
                {
                    "status": "success",
                    "details": {
                        "steps": ["Follower was already inactive"],
                        "errors": [],
                        "initial_state": initial_state,
                        "final_state": "inactive",
                        "execution_time_ms": round(
                            (time.time() - start_time) * 1000,
                            2,
                        ),
                        "was_active": False,
                    },
                },
                action_type="offboard_stop",
                internal_handler="api_legacy_control_routes.stop_offboard_mode",
                following_active_before=following_before,
                following_active_after=False,
            )

        result = await owner.app_controller.disconnect_px4()

        final_state = "active" if owner.app_controller.following_active else "inactive"
        execution_time_ms = (time.time() - start_time) * 1000

        result["initial_state"] = initial_state
        result["final_state"] = final_state
        result["execution_time_ms"] = round(execution_time_ms, 2)
        result["was_active"] = was_active

        owner.logger.info(
            f"✅ API: Offboard mode stop completed "
            f"({initial_state} → {final_state}, {execution_time_ms:.0f}ms)"
        )

        following_after = bool(getattr(owner.app_controller, "following_active", False))
        errors = result.get("errors") or []
        legacy_error = None

        if following_after:
            legacy_error = "Offboard stop command returned with following still active."
            owner.logger.warning(
                "⚠️ Warning: following_active flag is still True after disconnect. "
                "This may indicate incomplete cleanup."
            )

        if errors:
            legacy_error = "; ".join(str(error) for error in errors)
            owner.logger.warning(
                f"⚠️ Disconnect completed with {len(errors)} warnings. "
                f"Follower state may need verification."
            )

        status_value = "failure" if legacy_error else "success"
        payload = {"status": status_value, "details": result}
        if legacy_error:
            payload["error"] = legacy_error

        return owner._attach_legacy_action_audit(
            payload,
            action_type="offboard_stop",
            internal_handler="api_legacy_control_routes.stop_offboard_mode",
            following_active_before=following_before,
            following_active_after=following_after,
            error=legacy_error,
        )

    except Exception as e:
        execution_time_ms = (time.time() - start_time) * 1000
        error_msg = str(e)

        owner.logger.error(f"❌ API: Error in stop_offboard_mode: {error_msg}")
        owner.logger.error(f"Exception type: {type(e).__name__}")
        owner.logger.debug(f"Stack trace:\n{traceback.format_exc()}")

        cleanup_errors = []
        try:
            if (
                hasattr(owner.app_controller, "offboard_commander")
                and owner.app_controller.offboard_commander
            ):
                owner.logger.warning(
                    "⚠️ Attempting emergency cleanup of OffboardCommander..."
                )
                await owner.app_controller.offboard_commander.stop(publish_final=True)
                owner.app_controller.offboard_commander = None

            if (
                hasattr(owner.app_controller, "setpoint_sender")
                and owner.app_controller.setpoint_sender
            ):
                owner.logger.warning(
                    "⚠️ Attempting emergency cleanup of setpoint sender..."
                )
                owner.app_controller.setpoint_sender.stop()
                owner.app_controller.setpoint_sender = None

            if (
                hasattr(owner.app_controller, "follower")
                and owner.app_controller.follower
            ):
                owner.logger.warning("⚠️ Attempting emergency cleanup of follower...")
                owner.app_controller.follower = None

            owner.app_controller.following_active = False
            owner.logger.warning(
                "⚠️ Emergency cleanup completed, state forced to inactive"
            )

        except Exception as cleanup_error:
            cleanup_error_msg = f"Emergency cleanup failed: {cleanup_error}"
            cleanup_errors.append(cleanup_error_msg)
            owner.logger.error(f"❌ {cleanup_error_msg}")

        try:
            final_state = "active" if owner.app_controller.following_active else "inactive"
        except BaseException:
            final_state = "unknown"

        errors = [error_msg, *cleanup_errors]
        returned_error = "; ".join(errors)
        return owner._attach_legacy_action_audit(
            {
                "status": "failure",
                "error": returned_error,
                "details": {
                    "steps": [],
                    "errors": errors,
                    "cleanup_errors": cleanup_errors,
                    "initial_state": (
                        initial_state if "initial_state" in locals() else "unknown"
                    ),
                    "final_state": final_state,
                    "execution_time_ms": round(execution_time_ms, 2),
                    "was_active": was_active if "was_active" in locals() else False,
                    "exception_type": type(e).__name__,
                },
            },
            action_type="offboard_stop",
            internal_handler="api_legacy_control_routes.stop_offboard_mode",
            following_active_before=following_before,
            following_active_after=(
                None if final_state == "unknown" else final_state == "active"
            ),
            error=returned_error,
        )
