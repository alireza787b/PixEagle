"""Legacy safety/config route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import json
import time
from math import degrees
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.parameters import Parameters


try:
    from classes.circuit_breaker import FollowerCircuitBreaker

    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False


def _safety_manager_or_none():
    try:
        from classes.safety_manager import SafetyManager, get_safety_manager

        _ = SafetyManager
        return True, get_safety_manager()
    except ImportError:
        return False, None


async def _persist_runtime_safety_boolean(
    handler: Any,
    parameter: str,
    value: bool,
    *,
    source: str,
) -> dict:
    """Persist one immediate safety boolean while follower lifecycle is stable."""
    app_controller = getattr(handler, "app_controller", None)
    follower_lock = getattr(app_controller, "_follower_state_lock", None)
    if follower_lock is None:
        raise HTTPException(
            status_code=503,
            detail="Follower lifecycle barrier is unavailable; safety change refused",
        )

    async with follower_lock:
        if bool(getattr(app_controller, "following_active", False)):
            raise HTTPException(
                status_code=409,
                detail="Circuit-breaker settings cannot change while following is active",
            )
        service = handler._get_config_service()
        result = await run_in_threadpool(
            service.persist_and_apply_runtime_config_path,
            [parameter],
            bool(value),
            source=source,
            allowed_reload_tiers=("immediate",),
        )

    requested_value = bool(value)
    applied_value = getattr(Parameters, parameter, None)
    if type(applied_value) is not bool or applied_value != requested_value:
        raise RuntimeError(
            f"Persisted {parameter} did not become the active runtime value"
        )
    persisted_value = service.get_path_value([parameter], default=None)
    if type(persisted_value) is not bool or persisted_value != requested_value:
        raise RuntimeError(
            f"Persisted {parameter} could not be verified after the update"
        )
    result["persisted_value"] = persisted_value
    return result


async def set_circuit_breaker_state(
    handler: Any,
    enabled: bool,
) -> JSONResponse:
    """Set the durable command circuit-breaker state explicitly."""
    if not CIRCUIT_BREAKER_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Circuit breaker system not available",
        )

    old_state = FollowerCircuitBreaker.is_active()
    persistence = await _persist_runtime_safety_boolean(
        handler,
        "FOLLOWER_CIRCUIT_BREAKER",
        bool(enabled),
        source="circuit_breaker_set",
    )
    new_state = FollowerCircuitBreaker.is_active()
    if type(new_state) is not bool or new_state != bool(enabled):
        raise RuntimeError("Circuit breaker runtime state did not match requested state")

    statistics_reset = new_state and not old_state
    if statistics_reset:
        FollowerCircuitBreaker.reset_statistics()
        handler.logger.info(
            "Circuit breaker ENABLED - follower commands will be logged instead of executed"
        )
    elif not new_state and old_state:
        handler.logger.warning(
            "Circuit breaker DISABLED - reviewed live follower command dispatch is permitted"
        )

    return JSONResponse(
        content={
            "status": "success",
            "action": "enabled" if new_state else "disabled",
            "active": new_state,
            "old_state": old_state,
            "new_state": new_state,
            "message": f'Circuit breaker {"enabled" if new_state else "disabled"}',
            "statistics_reset": statistics_reset,
            "persisted": True,
            "persisted_changed": bool(persistence.get("changed")),
            "runtime_applied": True,
            "runtime_changed": bool(persistence.get("applied")),
            "reload_tier": persistence.get("reload_tier"),
            "backup_id": persistence.get("backup_id"),
            "timestamp": time.time(),
        }
    )


async def get_circuit_breaker_status(handler: Any) -> JSONResponse:
    """Get legacy circuit-breaker status and configuration."""
    try:
        if not CIRCUIT_BREAKER_AVAILABLE:
            return JSONResponse(
                content={
                    "available": False,
                    "error": "Circuit breaker system not available",
                    "message": (
                        "FollowerCircuitBreaker module could not be imported"
                    ),
                }
            )

        activation_state = FollowerCircuitBreaker.get_activation_state()
        is_active = activation_state["active"]
        statistics = FollowerCircuitBreaker.get_statistics()
        service = handler._get_config_service()
        persisted_active = service.get_path_value(
            ["FOLLOWER_CIRCUIT_BREAKER"],
            default=None,
        )
        runtime_execution_mode = str(
            getattr(Parameters, "FOLLOWER_EXECUTION_MODE", "PX4")
        ).strip().upper()
        persisted_execution_mode = service.get_path_value(
            ["Follower", "FOLLOWER_EXECUTION_MODE"],
            default=None,
        )
        if isinstance(persisted_execution_mode, str):
            persisted_execution_mode = persisted_execution_mode.strip().upper()
        following_active = bool(
            getattr(handler.app_controller, "following_active", False)
        )
        active_session_execution_mode = None
        if following_active:
            active_mode = getattr(
                handler.app_controller,
                "following_execution_mode",
                None,
            )
            if active_mode is not None:
                active_session_execution_mode = str(active_mode).strip().upper()
        effective_execution_mode = (
            active_session_execution_mode
            if following_active and active_session_execution_mode
            else runtime_execution_mode
        )
        command_preview_configured = runtime_execution_mode == "COMMAND_PREVIEW"
        command_preview_enabled = effective_execution_mode == "COMMAND_PREVIEW"

        return JSONResponse(
            content={
                "available": activation_state["available"],
                "active": is_active,
                "status": "testing" if is_active else "operational",
                "semantics": "px4_command_dispatch_inhibit",
                "state_reason": activation_state["reason"],
                "configuration": {
                    "parameter_name": "FOLLOWER_CIRCUIT_BREAKER",
                    "current_value": is_active,
                    "persisted_value": persisted_active,
                    "runtime_matches_persisted": (
                        type(persisted_active) is bool
                        and persisted_active == is_active
                    ),
                    "description": "Global fail-closed PX4 command-dispatch inhibit",
                },
                "follower_test": {
                    "enabled": command_preview_enabled,
                    "configured": command_preview_configured,
                    "execution_mode": effective_execution_mode,
                    "configured_execution_mode": runtime_execution_mode,
                    "active_session_execution_mode": active_session_execution_mode,
                    "persisted_execution_mode": persisted_execution_mode,
                    "runtime_matches_persisted": (
                        persisted_execution_mode == runtime_execution_mode
                    ),
                    "following_active": following_active,
                    "configurable": not following_active,
                    "requires_circuit_breaker": True,
                    "commands_sent_to_px4": False if command_preview_enabled else None,
                },
                "statistics": statistics,
                "message": (
                    (
                        "Circuit breaker active - PX4 command dispatch is inhibited; "
                        "local follower test is enabled"
                        if command_preview_enabled
                        else "Circuit breaker active - PX4 command dispatch is inhibited"
                    )
                    if is_active
                    else "Circuit breaker disabled - normal operation"
                ),
                "timestamp": time.time(),
            }
        )

    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error getting circuit breaker status: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_circuit_breaker_statistics(handler: Any) -> JSONResponse:
    """Get legacy circuit-breaker statistics and telemetry."""
    try:
        if not CIRCUIT_BREAKER_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Circuit breaker system not available",
            )

        statistics = FollowerCircuitBreaker.get_statistics()

        response_data = {
            "circuit_breaker": statistics,
            "api_info": {
                "endpoint": "/api/circuit-breaker/statistics",
                "api_version": "2.0",
                "timestamp": time.time(),
                "data_freshness": "real-time",
            },
            "usage_summary": {
                "testing_mode": statistics["circuit_breaker_active"],
                "total_intercepted_commands": statistics["total_commands"],
                "unique_followers_tested": len(statistics["followers_tested"]),
                "command_diversity": len(statistics["command_types"]),
            },
        }

        if statistics["circuit_breaker_active"]:
            if statistics["command_rate_hz"] > 0:
                response_data["performance"] = {
                    "commands_per_second": statistics["command_rate_hz"],
                    "testing_efficiency": (
                        "high"
                        if statistics["command_rate_hz"] > 5
                        else (
                            "medium"
                            if statistics["command_rate_hz"] > 1
                            else "low"
                        )
                    ),
                    "last_activity": statistics["last_command_time"],
                }

        return JSONResponse(content=response_data)

    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error getting circuit breaker statistics: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def toggle_circuit_breaker(handler: Any) -> JSONResponse:
    """Deprecated compatibility toggle; typed clients should set explicit state."""
    try:
        if not CIRCUIT_BREAKER_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Circuit breaker system not available",
            )
        old_state = FollowerCircuitBreaker.is_active()
        response = await set_circuit_breaker_state(handler, not old_state)
        payload = json.loads(response.body.decode("utf-8"))
        payload["deprecated"] = True
        payload["canonical_action"] = "/api/v1/actions/circuit-breaker-set"
        return JSONResponse(content=payload)

    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error toggling circuit breaker: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def reset_circuit_breaker_statistics(handler: Any) -> JSONResponse:
    """Reset legacy circuit-breaker statistics and counters."""
    try:
        if not CIRCUIT_BREAKER_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Circuit breaker system not available",
            )

        old_stats = FollowerCircuitBreaker.get_statistics()

        FollowerCircuitBreaker.reset_statistics()

        new_stats = FollowerCircuitBreaker.get_statistics()

        handler.logger.info("Circuit breaker statistics reset")

        return JSONResponse(
            content={
                "status": "success",
                "action": "statistics_reset",
                "message": "Circuit breaker statistics have been reset",
                "old_statistics": {
                    "total_commands": old_stats["total_commands"],
                    "followers_tested": len(old_stats["followers_tested"]),
                    "elapsed_time": old_stats["elapsed_time_seconds"],
                },
                "new_statistics": new_stats,
                "reset_timestamp": time.time(),
            }
        )

    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error resetting circuit breaker statistics: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_safety_config(handler: Any) -> JSONResponse:
    """Get complete legacy safety configuration from SafetyManager."""
    try:
        safety_available, safety_manager = _safety_manager_or_none()

        if not safety_available or safety_manager is None:
            return JSONResponse(
                content={
                    "available": False,
                    "message": "SafetyManager not available",
                    "timestamp": time.time(),
                }
            )

        summary = safety_manager.get_all_limits_summary()
        config = {
            "available": True,
            "global_limits": summary["global_limits"],
            "follower_overrides": summary["follower_overrides"],
            "timestamp": time.time(),
        }

        return JSONResponse(content=config)

    except Exception as exc:
        handler.logger.error(f"Error getting safety config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_follower_safety_limits(
    handler: Any,
    follower_name: str,
) -> JSONResponse:
    """Get legacy effective safety limits for a specific follower."""
    try:
        safety_available, safety_manager = _safety_manager_or_none()

        if not safety_available or safety_manager is None:
            limits = {
                "follower_name": follower_name,
                "velocity": {
                    "forward": Parameters.get_effective_limit(
                        "MAX_VELOCITY_FORWARD",
                        follower_name,
                    ),
                    "lateral": Parameters.get_effective_limit(
                        "MAX_VELOCITY_LATERAL",
                        follower_name,
                    ),
                    "vertical": Parameters.get_effective_limit(
                        "MAX_VELOCITY_VERTICAL",
                        follower_name,
                    ),
                },
                "altitude": {
                    "min": Parameters.get_effective_limit(
                        "MIN_ALTITUDE",
                        follower_name,
                    ),
                    "max": Parameters.get_effective_limit(
                        "MAX_ALTITUDE",
                        follower_name,
                    ),
                    "warning_buffer": Parameters.get_effective_limit(
                        "ALTITUDE_WARNING_BUFFER",
                        follower_name,
                    ),
                },
                "rates": {
                    "yaw_deg": Parameters.get_effective_limit(
                        "MAX_YAW_RATE",
                        follower_name,
                    ),
                    "pitch_deg": Parameters.get_effective_limit(
                        "MAX_PITCH_RATE",
                        follower_name,
                    )
                    or 45.0,
                    "roll_deg": Parameters.get_effective_limit(
                        "MAX_ROLL_RATE",
                        follower_name,
                    )
                    or 45.0,
                },
                "altitude_safety_enabled": True,
                "timestamp": time.time(),
            }
            return JSONResponse(content=limits)

        velocity_limits = safety_manager.get_velocity_limits(follower_name)
        altitude_limits = safety_manager.get_altitude_limits(follower_name)
        rate_limits = safety_manager.get_rate_limits(follower_name)

        limits_summary = safety_manager.get_effective_limits_summary(follower_name)

        def is_group_overridden(param_names):
            return any(
                limits_summary.get(param, {}).get("is_overridden", False)
                for param in param_names
            )

        def get_group_source(param_names):
            for param in param_names:
                if limits_summary.get(param, {}).get("is_overridden", False):
                    return limits_summary[param].get("source", "GlobalLimits")
            return "GlobalLimits"

        velocity_params = [
            "MAX_VELOCITY",
            "MAX_VELOCITY_FORWARD",
            "MAX_VELOCITY_LATERAL",
            "MAX_VELOCITY_VERTICAL",
        ]
        altitude_params = [
            "MIN_ALTITUDE",
            "MAX_ALTITUDE",
            "ALTITUDE_WARNING_BUFFER",
            "ALTITUDE_SAFETY_ENABLED",
        ]
        rate_params = ["MAX_YAW_RATE", "MAX_PITCH_RATE", "MAX_ROLL_RATE"]

        velocity_overridden = is_group_overridden(velocity_params)
        altitude_overridden = is_group_overridden(altitude_params)
        rates_overridden = is_group_overridden(rate_params)
        has_any_overrides = (
            velocity_overridden or altitude_overridden or rates_overridden
        )

        limits = {
            "follower_name": follower_name,
            "velocity": {
                "forward": velocity_limits.forward,
                "lateral": velocity_limits.lateral,
                "vertical": velocity_limits.vertical,
                "max_magnitude": velocity_limits.max_magnitude,
                "source": get_group_source(velocity_params),
                "is_overridden": velocity_overridden,
            },
            "altitude": {
                "min": altitude_limits.min_altitude,
                "max": altitude_limits.max_altitude,
                "warning_buffer": altitude_limits.warning_buffer,
                "safety_enabled": altitude_limits.safety_enabled,
                "source": get_group_source(altitude_params),
                "is_overridden": altitude_overridden,
            },
            "rates": {
                "yaw_deg": degrees(rate_limits.yaw),
                "pitch_deg": degrees(rate_limits.pitch),
                "roll_deg": degrees(rate_limits.roll),
                "source": get_group_source(rate_params),
                "is_overridden": rates_overridden,
            },
            "altitude_safety_enabled": safety_manager.is_altitude_safety_enabled(
                follower_name
            ),
            "has_any_overrides": has_any_overrides,
            "timestamp": time.time(),
        }

        return JSONResponse(content=limits)

    except Exception as exc:
        handler.logger.error(f"Error getting follower safety limits: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_effective_limits(
    handler: Any,
    follower_name: str | None = None,
) -> JSONResponse:
    """Get legacy effective safety limits with resolution chain."""
    try:
        safety_available, safety_manager = _safety_manager_or_none()

        if not safety_available or safety_manager is None:
            return JSONResponse(
                content={
                    "available": False,
                    "message": "SafetyManager not available",
                    "timestamp": time.time(),
                }
            )

        limits_summary = safety_manager.get_effective_limits_summary(follower_name)
        available_followers = safety_manager.get_available_followers()

        return JSONResponse(
            content={
                "success": True,
                "follower_name": follower_name,
                "limits": limits_summary,
                "available_followers": available_followers,
                "timestamp": time.time(),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error getting effective limits: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_relevant_sections(
    handler: Any,
    follower_mode: str | None = None,
) -> JSONResponse:
    """Get legacy configuration sections relevant to the current follower mode."""
    try:
        mode_sections = {
            "mc_velocity_chase": [
                "Follower",
                "MC_VELOCITY_CHASE",
                "Safety",
                "PID",
                "Tracking",
                "OSD",
            ],
            "mc_velocity_position": [
                "Follower",
                "MC_VELOCITY_POSITION",
                "Safety",
                "PID",
                "Tracking",
                "OSD",
            ],
            "mc_velocity_distance": [
                "Follower",
                "MC_VELOCITY_DISTANCE",
                "Safety",
                "PID",
                "Tracking",
                "OSD",
            ],
            "mc_velocity_ground": [
                "Follower",
                "MC_VELOCITY_GROUND",
                "Safety",
                "PID",
                "Tracking",
                "OSD",
            ],
            "mc_attitude_rate": [
                "Follower",
                "MC_ATTITUDE_RATE",
                "Safety",
                "PID",
                "Tracking",
                "OSD",
            ],
            "gm_velocity_chase": [
                "Follower",
                "GM_VELOCITY_CHASE",
                "Safety",
                "GimbalTracker",
                "PID",
                "Tracking",
                "Gimbal",
                "OSD",
            ],
            "gm_velocity_vector": [
                "Follower",
                "GM_VELOCITY_VECTOR",
                "Safety",
                "GimbalTracker",
                "PID",
                "Tracking",
                "Gimbal",
                "OSD",
            ],
            "fw_attitude_rate": [
                "Follower",
                "FW_ATTITUDE_RATE",
                "Safety",
                "PID",
                "Tracking",
                "OSD",
            ],
        }

        global_sections = [
            "VideoSource",
            "PX4",
            "MAVLink",
            "Streaming",
            "Debugging",
        ]

        mode = (
            follower_mode.lower()
            if follower_mode
            else Parameters.FOLLOWER_MODE.lower()
        )
        mode_specific = mode_sections.get(
            mode,
            ["Follower", "Safety", "PID", "Tracking", "OSD"],
        )

        try:
            service = handler._get_config_service()
            all_sections = list(service.get_schema().get("sections", {}).keys())
        except Exception:
            all_sections = []

        active_sections = list(set(mode_specific + global_sections))
        other_sections = [section for section in all_sections if section not in active_sections]

        return JSONResponse(
            content={
                "success": True,
                "current_mode": mode,
                "active_sections": active_sections,
                "other_sections": other_sections,
                "mode_specific_sections": mode_specific,
                "global_sections": global_sections,
                "timestamp": time.time(),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error getting relevant sections: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
