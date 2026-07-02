"""Legacy tracker route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from classes.api_v1_contracts import LEGACY_TRACKER_COMPATIBILITY_CLAIM_BOUNDARY
from classes.api_v1_paths import (
    API_V1_ACTION_TRACKER_RESTART_PATH,
    API_V1_ACTION_TRACKER_SWITCH_PATH,
    API_V1_TRACKING_CATALOG_PATH,
    API_V1_TRACKING_RUNTIME_STATUS_PATH,
    API_V1_TRACKING_TELEMETRY_PATH,
)
from classes.model_manager import AI_AVAILABLE
from classes.parameters import Parameters


LEGACY_TRACKER_ROUTE_METADATA = {
    "available": {
        "method": "GET",
        "path": "/api/tracker/available",
        "replacement_path": API_V1_TRACKING_CATALOG_PATH,
        "deprecated": False,
        "compatibility_alias": True,
    },
    "current": {
        "method": "GET",
        "path": "/api/tracker/current",
        "replacement_path": API_V1_TRACKING_CATALOG_PATH,
        "deprecated": False,
        "compatibility_alias": True,
    },
    "available_types": {
        "method": "GET",
        "path": "/api/tracker/available-types",
        "replacement_path": API_V1_TRACKING_CATALOG_PATH,
        "deprecated": False,
        "compatibility_alias": True,
    },
    "current_config": {
        "method": "GET",
        "path": "/api/tracker/current-config",
        "replacement_path": API_V1_TRACKING_CATALOG_PATH,
        "deprecated": False,
        "compatibility_alias": True,
    },
    "switch": {
        "method": "POST",
        "path": "/api/tracker/switch",
        "replacement_path": API_V1_ACTION_TRACKER_SWITCH_PATH,
        "deprecated": False,
        "compatibility_alias": True,
    },
    "restart": {
        "method": "POST",
        "path": "/api/tracker/restart",
        "replacement_path": API_V1_ACTION_TRACKER_RESTART_PATH,
        "deprecated": False,
        "compatibility_alias": True,
    },
    "output": {
        "method": "GET",
        "path": "/api/tracker/output",
        "replacement_path": API_V1_TRACKING_TELEMETRY_PATH,
        "deprecated": False,
        "compatibility_alias": True,
    },
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
    "current_status": {
        "method": "GET",
        "path": "/api/tracker/current-status",
        "replacement_path": API_V1_TRACKING_RUNTIME_STATUS_PATH,
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
    record_legacy_tracker_route_usage("available", logger=handler.logger)
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
    record_legacy_tracker_route_usage("current", logger=handler.logger)
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
    record_legacy_tracker_route_usage("switch", logger=handler.logger)
    try:
        data = await request.json()
        new_tracker_type = data.get("tracker_type")
        return await switch_tracker_to_type(handler, new_tracker_type)

    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error switching tracker: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def switch_tracker_to_type(
    handler: Any,
    new_tracker_type: str | None,
) -> JSONResponse:
    """Switch tracker type dynamically for legacy and typed action callers."""
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


async def restart_tracker(
    handler: Any,
    *,
    record_compatibility_usage: bool = True,
) -> JSONResponse:
    """Restart the configured tracker with fresh config through the legacy route."""
    if record_compatibility_usage:
        record_legacy_tracker_route_usage("restart", logger=handler.logger)

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
    record_legacy_tracker_route_usage("current_config", logger=handler.logger)
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


async def get_available_tracker_types(handler: Any) -> JSONResponse:
    """Get the legacy hardcoded tracker type/capability list."""
    record_legacy_tracker_route_usage("available_types", logger=handler.logger)
    try:
        available_trackers = {
            "CSRT": {
                "name": "CSRT",
                "display_name": "CSRT Tracker",
                "description": (
                    "Channel and Spatial Reliability Tracker - Classical CV algorithm"
                ),
                "data_type": "POSITION_2D",
                "smart_mode": False,
                "suitable_for": [
                    "Single target",
                    "Stable tracking",
                    "Classical computer vision",
                ],
            },
            "ParticleFilter": {
                "name": "ParticleFilter",
                "display_name": "Particle Filter",
                "description": "Particle Filter Tracker - Probabilistic tracking",
                "data_type": "POSITION_2D",
                "smart_mode": False,
                "suitable_for": [
                    "Complex movements",
                    "Occlusions",
                    "Probabilistic tracking",
                ],
            },
            "Gimbal": {
                "name": "Gimbal",
                "display_name": "Gimbal Tracker",
                "description": (
                    "External gimbal UDP angle tracker - Real-time gimbal angle data"
                ),
                "data_type": "GIMBAL_ANGLES",
                "smart_mode": False,
                "suitable_for": [
                    "External gimbal",
                    "Real-time angles",
                    "High precision tracking",
                ],
            },
            "SmartTracker": {
                "name": "SmartTracker",
                "display_name": "Smart Tracker (AI)",
                "description": "AI-powered multi-backend smart tracking system",
                "data_type": "BBOX_CONFIDENCE",
                "smart_mode": True,
                "suitable_for": [
                    "Multiple targets",
                    "AI detection",
                    "Complex scenarios",
                ],
                "available": AI_AVAILABLE,
                "unavailable_reason": (
                    None
                    if AI_AVAILABLE
                    else "AI packages (ultralytics/torch) not installed"
                ),
            },
        }

        for info in available_trackers.values():
            if "available" not in info:
                info["available"] = True
                info["unavailable_reason"] = None

        current_tracker = getattr(handler.app_controller, "current_tracker_type", "CSRT")

        return JSONResponse(
            content={
                "available_trackers": available_trackers,
                "current_configured": current_tracker,
                "current_active": (
                    handler.app_controller.tracker.__class__.__name__
                    if handler.app_controller.tracker
                    else None
                ),
                "smart_mode_active": getattr(
                    handler.app_controller,
                    "smart_mode_active",
                    False,
                ),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error getting available tracker types: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_tracker_output(handler: Any) -> JSONResponse:
    """Get the legacy structured tracker output diagnostic payload."""
    record_legacy_tracker_route_usage("output", logger=handler.logger)
    try:
        handler.logger.debug("Received request at /api/tracker/output")

        if not hasattr(handler.app_controller, "get_tracker_output"):
            raise HTTPException(
                status_code=501,
                detail="Enhanced tracker schema not available",
            )

        tracker_output = handler.app_controller.get_tracker_output()
        if not tracker_output:
            return JSONResponse(
                content={
                    "error": "No tracker output available",
                    "tracking_active": False,
                    "timestamp": time.time(),
                }
            )

        output_dict = tracker_output.to_dict()
        output_dict["api_version"] = "2.0"
        output_dict["schema_version"] = "flexible"

        handler.logger.debug(
            f"Returning structured tracker output: {tracker_output.data_type.value}"
        )
        return JSONResponse(content=output_dict)

    except Exception as exc:
        handler.logger.error(f"Error in /api/tracker/output: {exc}")
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


async def get_current_tracker_status(handler: Any) -> JSONResponse:
    """Get current legacy tracker status with schema-driven field information."""
    record_legacy_tracker_route_usage("current_status", logger=handler.logger)
    try:
        tracker_output = handler.app_controller.get_tracker_output()

        if not tracker_output:
            runtime_status = handler._get_tracker_runtime_status_snapshot(
                tracker_output=None
            )
            return JSONResponse(
                content={
                    "active": False,
                    "active_tracking": False,
                    "has_output": False,
                    "usable_for_following": False,
                    "data_is_stale": False,
                    "status": runtime_status["status"],
                    "consumer_guidance": runtime_status["consumer_guidance"],
                    "reason": runtime_status["reason"],
                    "tracker_type": None,
                    "data_type": None,
                    "fields": {},
                    "runtime_status": runtime_status,
                    "smart_mode": getattr(
                        handler.app_controller,
                        "smart_mode_active",
                        False,
                    ),
                    "inference": None,
                    "claim_boundary": runtime_status["claim_boundary"],
                    "timestamp": time.time(),
                }
            )

        data_type = tracker_output.data_type.value
        available_fields = {}
        output_dict = tracker_output.to_dict()

        system_fields = {
            "timestamp",
            "tracking_active",
            "tracker_id",
            "data_type",
            "metadata",
        }
        for key, value in output_dict.items():
            if key not in system_fields and value is not None:
                available_fields[key] = _get_enhanced_field_info(
                    key,
                    value,
                    data_type,
                )

        if tracker_output.raw_data:
            important_raw_fields = [
                "tracking",
                "tracking_status",
                "system",
                "coordinate_system",
                "yaw",
                "pitch",
                "roll",
                "provider",
                "protocol",
                "usable_for_following",
                "gimbal_tracking_active",
                "has_output",
                "data_is_stale",
                "freshness_reason",
                "connection_status",
            ]
            for raw_field in important_raw_fields:
                if (
                    raw_field in tracker_output.raw_data
                    and tracker_output.raw_data[raw_field] is not None
                ):
                    available_fields[raw_field] = _get_enhanced_field_info(
                        raw_field,
                        tracker_output.raw_data[raw_field],
                        data_type,
                    )

        tracker_class = (
            handler.app_controller.tracker.__class__.__name__
            if handler.app_controller.tracker
            else "Unknown"
        )
        inference_info = None
        if getattr(handler.app_controller, "smart_mode_active", False):
            smart_tracker = getattr(handler.app_controller, "smart_tracker", None)
            if smart_tracker and hasattr(smart_tracker, "get_runtime_info"):
                try:
                    inference_info = smart_tracker.get_runtime_info()
                except Exception as runtime_error:
                    handler.logger.debug(
                        f"Could not fetch smart tracker inference info: {runtime_error}"
                    )

        runtime_status = handler._get_tracker_runtime_status_snapshot(tracker_output)

        return JSONResponse(
            content={
                "active": runtime_status["active_tracking"],
                "active_tracking": runtime_status["active_tracking"],
                "has_output": runtime_status["has_output"],
                "usable_for_following": runtime_status["usable_for_following"],
                "data_is_stale": runtime_status["data_is_stale"],
                "status": runtime_status["status"],
                "consumer_guidance": runtime_status["consumer_guidance"],
                "reason": runtime_status["reason"],
                "tracker_type": tracker_class,
                "data_type": data_type,
                "fields": available_fields,
                "raw_data": tracker_output.raw_data,
                "runtime_status": runtime_status,
                "smart_mode": getattr(
                    handler.app_controller,
                    "smart_mode_active",
                    False,
                ),
                "inference": inference_info,
                "claim_boundary": runtime_status["claim_boundary"],
                "timestamp": time.time(),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error getting current tracker status: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _get_enhanced_field_info(field_name: str, value: Any, data_type: str) -> dict:
    """Get enhanced legacy field information for tracker status display."""
    base_type = type(value).__name__

    if (
        field_name == "angular"
        and isinstance(value, (tuple, list))
        and len(value) == 3
    ):
        return {
            "value": value,
            "type": "angular_3d",
            "display_name": "Gimbal Angles (Y, P, R)",
            "description": "Gimbal yaw, pitch, roll angles in degrees",
            "units": "\u00b0",
            "format": "tuple_3d",
            "components": ["yaw", "pitch", "roll"],
        }

    if (
        field_name in ["position_2d", "normalized_position"]
        and isinstance(value, (tuple, list))
        and len(value) == 2
    ):
        return {
            "value": value,
            "type": "position_2d",
            "display_name": "Target Position (X, Y)",
            "description": "Normalized 2D position coordinates",
            "units": "normalized",
            "format": "tuple_2d",
            "components": ["x", "y"],
        }

    if (
        field_name in ["bbox", "normalized_bbox"]
        and isinstance(value, (tuple, list))
        and len(value) == 4
    ):
        return {
            "value": value,
            "type": "bbox",
            "display_name": "Bounding Box",
            "description": "Target bounding box coordinates",
            "units": "pixels" if "normalized" not in field_name else "normalized",
            "format": "bbox",
            "components": ["x", "y", "width", "height"],
        }

    if field_name == "confidence":
        return {
            "value": value,
            "type": "confidence",
            "display_name": "Tracking Confidence",
            "description": "Tracker confidence score",
            "units": "%" if isinstance(value, (int, float)) else "",
            "format": "percentage",
            "range": [0.0, 1.0] if isinstance(value, (int, float)) else None,
        }

    if field_name == "velocity" and isinstance(value, (tuple, list)):
        return {
            "value": value,
            "type": "velocity",
            "display_name": "Target Velocity",
            "description": "Target velocity vector",
            "units": "px/s" if len(value) == 2 else "units/s",
            "format": f"tuple_{len(value)}d",
            "components": ["vx", "vy"] if len(value) == 2 else ["vx", "vy", "vz"],
        }

    if isinstance(value, (tuple, list)):
        return {
            "value": value,
            "type": f"{base_type}_{len(value)}d",
            "display_name": field_name.replace("_", " ").title(),
            "description": f"{len(value)}-dimensional {field_name} data",
            "format": f"{base_type}_{len(value)}d",
            "components": [f"component_{index}" for index in range(len(value))],
        }

    if field_name in ["tracking", "tracking_status"] and isinstance(value, str):
        return {
            "value": value,
            "type": "tracking_status",
            "display_name": "Tracking Status",
            "description": "Current gimbal tracking state",
            "format": "status_string",
            "status_color": (
                "success"
                if "ACTIVE" in value.upper()
                else "warning"
                if "SELECTION" in value.upper()
                else "error"
            ),
        }

    if field_name == "system" and isinstance(value, str):
        return {
            "value": value,
            "type": "coordinate_system",
            "display_name": "Coordinate System",
            "description": "Gimbal coordinate reference system",
            "format": "system_string",
        }

    return {
        "value": value,
        "type": base_type.lower(),
        "display_name": field_name.replace("_", " ").title(),
        "description": f"{field_name} field data",
        "format": base_type.lower(),
    }


__all__ = [
    "LEGACY_TRACKER_COMPATIBILITY_CLAIM_BOUNDARY",
    "LEGACY_TRACKER_ROUTE_METADATA",
    "get_available_tracker_types",
    "get_available_trackers",
    "get_current_tracker_status",
    "get_current_tracker",
    "get_current_tracker_config",
    "get_legacy_tracker_route_usage_snapshot",
    "get_tracker_capabilities",
    "get_tracker_output",
    "get_tracker_schema",
    "record_legacy_tracker_route_usage",
    "restart_tracker",
    "reset_legacy_tracker_route_usage",
    "switch_tracker",
]
