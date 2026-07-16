"""Internal tracker helpers retained for typed tracker actions."""

from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.parameters import Parameters


async def switch_tracker_to_type(
    handler: Any,
    new_tracker_type: str | None,
) -> JSONResponse:
    """Switch tracker type dynamically for typed action callers."""
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
                "new_tracker": result.get("new_tracker", new_tracker_type),
                "requested_tracker": result.get("requested_tracker", new_tracker_type),
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


async def restart_tracker(handler: Any) -> JSONResponse:
    """Restart the configured tracker with fresh config for typed action callers."""
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
        app_controller = handler.app_controller
        follower_lock = getattr(app_controller, "_follower_state_lock", None)
        if follower_lock is None:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error_code": "TRACKER_RESTART_STATE_BARRIER_UNAVAILABLE",
                    "error": "Follower state barrier is unavailable; restart refused",
                },
            )

        async with follower_lock:
            if bool(getattr(app_controller, "following_active", False)):
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "action": "tracker_restart_blocked",
                        "error_code": "TRACKER_RESTART_WHILE_FOLLOWING",
                        "error": "Stop follow mode before restarting the tracker",
                    },
                )

            service_getter = getattr(handler, "_get_config_service", None)
            if not callable(service_getter):
                return JSONResponse(
                    status_code=503,
                    content={
                        "success": False,
                        "error_code": "CONFIG_SERVICE_UNAVAILABLE",
                        "error": "Configuration service is unavailable",
                    },
                )
            service = service_getter()
            previous_runtime = await run_in_threadpool(
                service.get_applied_runtime_config
            )
            publication = await run_in_threadpool(
                service.apply_runtime_config_tiers,
                {"immediate", "tracker_restart"},
                source="tracker_restart_action",
            )

            configured_tracker_type = str(Parameters.DEFAULT_TRACKING_ALGORITHM)
            switch_under_barrier = getattr(
                app_controller,
                "_switch_tracker_type_with_follower_barrier",
                None,
            )
            if callable(switch_under_barrier):
                result = switch_under_barrier(configured_tracker_type)
            else:
                # Test doubles and legacy embedders may provide only the public
                # async method. Production AppController always uses the owned
                # barrier path above.
                result = await app_controller.switch_tracker_type(configured_tracker_type)

        if result.get("success"):
            tracker_type = result.get("new_tracker", configured_tracker_type)
            handler.logger.info(f"Tracker reinitialized: {tracker_type}")

            return JSONResponse(
                content={
                    "success": True,
                    "action": "tracker_restarted",
                    "tracker_type": tracker_type,
                    "requested_tracker": result.get(
                        "requested_tracker",
                        configured_tracker_type,
                    ),
                    "message": (
                        f"Tracker {tracker_type} reinitialized with fresh config"
                    ),
                    "config_reloaded": True,
                    "runtime_publication": publication,
                    "details": result,
                }
            )

        await run_in_threadpool(
            service.publish_runtime_config_snapshot,
            previous_runtime,
            source="tracker_restart_rollback",
        )
        error_detail = result.get("error", "Unknown error during tracker restart")
        handler.logger.error(f"Tracker restart failed: {error_detail}")

        return JSONResponse(
            content={
                "success": False,
                "action": "restart_failed",
                "tracker_type": configured_tracker_type,
                "error": error_detail,
                "config_reloaded": False,
                "runtime_rolled_back": True,
                "details": result,
            },
            status_code=500,
        )

    except Exception as exc:
        handler.logger.error(f"Error restarting tracker: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


__all__ = [
    "restart_tracker",
    "switch_tracker_to_type",
]
