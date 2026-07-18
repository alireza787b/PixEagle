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

from classes.circuit_breaker import FollowerCircuitBreaker


def get_offboard_start_preflight(owner: Any) -> dict[str, Any]:
    """Return the canonical local preflight used before any PX4 start work."""
    issues = []
    app_controller = owner.app_controller

    # COMMAND_PREVIEW is an explicit local intent-capture mode.  It shares the
    # typed action surface with Offboard start for UI/API consistency, but it
    # must not inherit the PX4 preflight or circuit-breaker disable semantics.
    preview_checker = getattr(
        app_controller,
        "_is_command_preview_configured",
        None,
    )
    preview_readiness_getter = getattr(
        app_controller,
        "_get_command_preview_readiness",
        None,
    )
    if callable(preview_checker) and preview_checker():
        preview_readiness = (
            preview_readiness_getter()
            if callable(preview_readiness_getter)
            else {
                "ready": False,
                "reason": "Command preview readiness is unavailable",
            }
        )
        if not preview_readiness.get("ready", False):
            reason = str(
                preview_readiness.get("reason")
                or "Command preview readiness failed"
            )
            if "circuit breaker" in reason.lower():
                code = "ACTION_COMMAND_PREVIEW_CIRCUIT_BREAKER_REQUIRED"
            elif "video" in reason.lower() or "replay" in reason.lower():
                code = "ACTION_COMMAND_PREVIEW_VIDEO_NOT_READY"
            elif "tracker" in reason.lower():
                code = "ACTION_COMMAND_PREVIEW_TRACKER_NOT_READY"
            else:
                code = "ACTION_COMMAND_PREVIEW_NOT_READY"
            issues.append({"code": code, "message": reason})
        return {
            "ready": not issues,
            "issues": issues,
            "tracker_runtime": preview_readiness,
            "circuit_breaker": preview_readiness.get("circuit_breaker"),
            "execution_mode": "COMMAND_PREVIEW",
            "command_preview": preview_readiness,
        }

    circuit_state = FollowerCircuitBreaker.get_activation_state()
    if circuit_state["active"]:
        issues.append({
            "code": (
                "ACTION_OFFBOARD_COMMAND_INHIBIT_ACTIVE"
                if circuit_state["available"]
                else "ACTION_OFFBOARD_COMMAND_INHIBIT_UNAVAILABLE"
            ),
            "message": (
                "Circuit breaker is active; disable the PX4 command inhibit "
                "before starting Following. It is not a follower preview or simulator."
                if circuit_state["available"]
                else "Circuit-breaker state is unavailable; PX4 command dispatch "
                "remains inhibited."
            ),
        })

    missing_components = []
    for attribute, label in (
        ("px4_interface", "PX4 interface"),
        ("tracker", "Tracker"),
        ("video_handler", "Video handler"),
    ):
        if not hasattr(app_controller, attribute):
            missing_components.append(f"{label} not initialized")
    if missing_components:
        issues.append({
            "code": "ACTION_OFFBOARD_COMPONENTS_UNAVAILABLE",
            "message": ", ".join(missing_components),
        })

    tracker_runtime = owner._get_tracker_following_readiness()
    if not tracker_runtime.get("usable_for_following", False):
        tracker_reason = tracker_runtime.get(
            "reason",
            "Tracker output is not usable for following",
        )
        frame_status = tracker_runtime.get("video_frame_status") or {}
        if frame_status.get("replay_source") is True:
            code = "ACTION_OFFBOARD_REPLAY_NOT_AUTHORIZED"
        elif tracker_runtime.get("tracker_requires_video"):
            code = "ACTION_OFFBOARD_VIDEO_FRAME_NOT_USABLE"
        else:
            code = "ACTION_OFFBOARD_TRACKER_NOT_USABLE"
        issues.append({"code": code, "message": str(tracker_reason)})

    return {
        "ready": not issues,
        "issues": issues,
        "tracker_runtime": tracker_runtime,
        "circuit_breaker": circuit_state,
    }


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

        preflight = get_offboard_start_preflight(owner)
        validation_errors = [issue["message"] for issue in preflight["issues"]]
        tracker_runtime = preflight["tracker_runtime"]

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
                        "preflight": preflight,
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
