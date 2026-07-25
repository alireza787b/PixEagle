"""Internal tracker helpers retained for typed tracker actions."""

from __future__ import annotations

import copy
import time
from typing import Any, Dict

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.parameters import Parameters


def _persist_tracker_selection(
    handler: Any,
    factory_key: str,
) -> Dict[str, Any]:
    """Persist and publish one validated tracker startup selection."""
    from classes.api_legacy_config_routes import (
        _assert_audit_source_unchanged,
        _config_mutation_transaction,
        _log_config_audit,
        _persist_config,
    )

    with _config_mutation_transaction(handler) as (service, transaction):
        old_value = copy.deepcopy(
            service.get_parameter("Tracking", "DEFAULT_TRACKING_ALGORITHM")
        )
        validation = service.set_parameter(
            "Tracking",
            "DEFAULT_TRACKING_ALGORITHM",
            factory_key,
            audit=False,
        )
        if not validation.valid:
            detail = "; ".join(
                validation.errors
                or validation.warnings
                or ["validation failed"]
            )
            raise HTTPException(
                status_code=400,
                detail=f"Tracker selection could not be persisted: {detail}",
            )

        _persist_config(service, transaction)
        _assert_audit_source_unchanged(service, transaction)
        _log_config_audit(
            service,
            transaction,
            action="update",
            section="Tracking",
            parameter="DEFAULT_TRACKING_ALGORITHM",
            old_value=old_value,
            new_value=factory_key,
            source="tracker_api",
        )

        runtime_config = service.get_applied_runtime_config()
        candidate = copy.deepcopy(runtime_config)
        tracking_config = candidate.get("Tracking")
        if not isinstance(tracking_config, dict):
            raise RuntimeError("Applied Tracking runtime config is unavailable")
        tracking_config["DEFAULT_TRACKING_ALGORITHM"] = factory_key
        service.publish_runtime_config_snapshot(
            candidate,
            source="tracker_api_selection_apply",
        )

    return {
        "old_value": old_value,
        "saved_value": factory_key,
        "reload_tier": service.get_reload_tier(
            "Tracking",
            "DEFAULT_TRACKING_ALGORITHM",
        ),
    }


async def switch_tracker_to_type(
    handler: Any,
    new_tracker_type: str | None,
    *,
    persist: bool = False,
) -> JSONResponse:
    """Switch tracker type and optionally save it as the startup selection."""
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
    old_factory_key = str(Parameters.DEFAULT_TRACKING_ALGORITHM)

    async def rollback_runtime_switch() -> Dict[str, Any]:
        """Restore runtime and in-memory startup state after a partial switch."""
        rollback = await handler.app_controller.switch_tracker_type(
            str(old_tracker_type)
        )
        if rollback.get("success", False):
            Parameters.DEFAULT_TRACKING_ALGORITHM = old_factory_key
        return rollback

    result = await handler.app_controller.switch_tracker_type(new_tracker_type)

    if result["success"]:
        persistence: Dict[str, Any] | None = None
        if persist:
            factory_key = result.get("factory_key")
            if not factory_key:
                rollback = await rollback_runtime_switch()
                if not rollback.get("success", False):
                    handler.logger.critical(
                        "Tracker switch returned no factory key and runtime rollback "
                        "failed: %s",
                        rollback.get("error", "unknown rollback failure"),
                    )
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "action": "switch_failed",
                        "error_code": (
                            "TRACKER_SWITCH_ROLLBACK_FAILED"
                            if not rollback.get("success", False)
                            else "TRACKER_SWITCH_PERSISTENCE_STATE_INVALID"
                        ),
                        "error": (
                            "Tracker switched without a resolved factory key; "
                            "runtime was restored"
                            if rollback.get("success", False)
                            else "Tracker switched without a resolved factory key "
                            "and runtime rollback failed"
                        ),
                        "old_tracker": old_tracker_type,
                        "requested_tracker": new_tracker_type,
                        "details": result,
                        "rollback": rollback,
                    },
                )
            try:
                persistence = await run_in_threadpool(
                    _persist_tracker_selection,
                    handler,
                    str(factory_key),
                )
            except Exception as persist_error:
                rollback = await rollback_runtime_switch()
                if not rollback.get("success", False):
                    handler.logger.critical(
                        "Tracker persistence failed and runtime rollback failed: %s",
                        rollback.get("error", "unknown rollback failure"),
                    )
                    return JSONResponse(
                        status_code=500,
                        content={
                            "status": "error",
                            "action": "switch_failed",
                            "error_code": "TRACKER_SWITCH_ROLLBACK_FAILED",
                            "error": (
                                "Tracker selection was not saved and the previous "
                                "runtime tracker could not be restored"
                            ),
                            "old_tracker": old_tracker_type,
                            "requested_tracker": new_tracker_type,
                            "details": result,
                            "rollback": rollback,
                        },
                    )

                handler.logger.error(
                    "Tracker runtime switch rolled back because persistence failed: %s",
                    persist_error,
                )
                status_code = (
                    persist_error.status_code
                    if isinstance(persist_error, HTTPException)
                    else 500
                )
                return JSONResponse(
                    status_code=status_code,
                    content={
                        "status": "error",
                        "action": "switch_failed",
                        "error_code": "TRACKER_SWITCH_PERSISTENCE_FAILED",
                        "error": (
                            "Tracker switch was rolled back because the startup "
                            "selection could not be saved"
                        ),
                        "old_tracker": old_tracker_type,
                        "requested_tracker": new_tracker_type,
                        "details": result,
                        "rollback": rollback,
                    },
                )

        handler.logger.info(
            "Tracker switched via API: %s \u2192 %s (saved=%s)",
            old_tracker_type,
            new_tracker_type,
            persist,
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
                "saved": bool(persist),
                "persistence": persistence,
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
