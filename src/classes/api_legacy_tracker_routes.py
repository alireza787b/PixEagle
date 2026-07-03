"""Legacy tracker route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from classes.api_v1_contracts import LEGACY_TRACKER_COMPATIBILITY_CLAIM_BOUNDARY
from classes.api_v1_paths import (
    API_V1_TRACKING_CATALOG_PATH,
)
from classes.parameters import Parameters


LEGACY_TRACKER_ROUTE_METADATA = {
    "capabilities": {
        "method": "GET",
        "path": "/api/tracker/capabilities",
        "replacement_path": API_V1_TRACKING_CATALOG_PATH,
        "deprecated": False,
        "compatibility_alias": True,
    },
    "schema": {
        "method": "GET",
        "path": "/api/tracker/schema",
        "replacement_path": API_V1_TRACKING_CATALOG_PATH,
        "deprecated": False,
        "compatibility_alias": True,
    },
}

_LEGACY_TRACKER_ROUTE_USAGE_LOCK = threading.Lock()
_LEGACY_TRACKER_ROUTE_USAGE = {
    route_key: {
        "count": 0,
        "last_used_at": None,
    }
    for route_key in LEGACY_TRACKER_ROUTE_METADATA
}


def record_legacy_tracker_route_usage(
    route_key: str,
    *,
    logger: Any = None,
) -> None:
    """Record process-local usage of a public legacy tracker route."""
    if route_key not in LEGACY_TRACKER_ROUTE_METADATA:
        if logger is not None:
            logger.warning("Unknown legacy tracker route usage key: %s", route_key)
        return

    now = time.time()
    with _LEGACY_TRACKER_ROUTE_USAGE_LOCK:
        usage = _LEGACY_TRACKER_ROUTE_USAGE[route_key]
        usage["count"] += 1
        usage["last_used_at"] = now

    if logger is not None:
        logger.debug("Legacy tracker compatibility route used: %s", route_key)


def reset_legacy_tracker_route_usage() -> None:
    """Reset process-local counters for tests and explicit maintenance checks."""
    with _LEGACY_TRACKER_ROUTE_USAGE_LOCK:
        for usage in _LEGACY_TRACKER_ROUTE_USAGE.values():
            usage["count"] = 0
            usage["last_used_at"] = None


def get_legacy_tracker_route_usage_snapshot() -> dict[str, Any]:
    """Return a JSON-safe snapshot of legacy tracker compatibility usage."""
    with _LEGACY_TRACKER_ROUTE_USAGE_LOCK:
        routes = {
            route_key: {
                "route_key": route_key,
                **LEGACY_TRACKER_ROUTE_METADATA[route_key],
                "count": int(usage["count"]),
                "last_used_at": usage["last_used_at"],
            }
            for route_key, usage in _LEGACY_TRACKER_ROUTE_USAGE.items()
        }

    return {
        "schema_version": 1,
        "source": "tracker_legacy_compatibility_usage",
        "total_calls": sum(route["count"] for route in routes.values()),
        "routes": routes,
        "claim_boundary": LEGACY_TRACKER_COMPATIBILITY_CLAIM_BOUNDARY,
        "timestamp": time.time(),
    }


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


async def get_tracker_capabilities(handler: Any) -> JSONResponse:
    """Get legacy tracker capabilities diagnostics."""
    record_legacy_tracker_route_usage("capabilities", logger=handler.logger)
    try:
        handler.logger.debug("Received request at /api/tracker/capabilities")

        if not hasattr(handler.app_controller, "get_tracker_capabilities"):
            return JSONResponse(
                content={
                    "error": "Capabilities API not available",
                    "legacy_mode": True,
                }
            )

        capabilities = handler.app_controller.get_tracker_capabilities()
        if not capabilities:
            return JSONResponse(
                content={
                    "error": "No active tracker",
                    "tracker_active": False,
                }
            )

        result = {
            "tracker_capabilities": capabilities,
            "system_info": {
                "tracker_active": bool(handler.app_controller.tracker),
                "tracker_class": (
                    handler.app_controller.tracker.__class__.__name__
                    if handler.app_controller.tracker
                    else None
                ),
                "api_version": "2.0",
                "timestamp": time.time(),
            },
        }

        handler.logger.debug("Returning tracker capabilities")
        return JSONResponse(content=result)

    except Exception as exc:
        handler.logger.error(f"Error in /api/tracker/capabilities: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_tracker_schema(handler: Any) -> JSONResponse:
    """Get the legacy tracker data schema file."""
    record_legacy_tracker_route_usage("schema", logger=handler.logger)
    try:
        import yaml

        with open("configs/tracker_schemas.yaml", "r") as schema_file:
            schema = yaml.safe_load(schema_file)
        return JSONResponse(content=schema)

    except Exception as exc:
        handler.logger.error(f"Error getting tracker schema: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


__all__ = [
    "LEGACY_TRACKER_COMPATIBILITY_CLAIM_BOUNDARY",
    "LEGACY_TRACKER_ROUTE_METADATA",
    "get_legacy_tracker_route_usage_snapshot",
    "get_tracker_capabilities",
    "get_tracker_schema",
    "record_legacy_tracker_route_usage",
    "restart_tracker",
    "reset_legacy_tracker_route_usage",
]
