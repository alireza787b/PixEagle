"""Legacy safety/config route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import time
from math import degrees
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse

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

        is_active = FollowerCircuitBreaker.is_active()
        statistics = FollowerCircuitBreaker.get_statistics()
        safety_bypass = getattr(Parameters, "CIRCUIT_BREAKER_DISABLE_SAFETY", False)

        return JSONResponse(
            content={
                "available": True,
                "active": is_active,
                "status": "testing" if is_active else "operational",
                "safety_bypass": safety_bypass,
                "safety_bypass_effective": safety_bypass and is_active,
                "configuration": {
                    "parameter_name": "FOLLOWER_CIRCUIT_BREAKER",
                    "current_value": is_active,
                    "description": "Global circuit breaker for follower testing",
                },
                "statistics": statistics,
                "message": (
                    "Circuit breaker active - commands logged not executed"
                    if is_active
                    else "Circuit breaker disabled - normal operation"
                ),
                "timestamp": time.time(),
            }
        )

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

    except Exception as exc:
        handler.logger.error(f"Error getting circuit breaker statistics: {exc}")
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

        config = {
            "available": True,
            "global_limits": safety_manager._global_limits,
            "follower_overrides": safety_manager._follower_overrides,
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
