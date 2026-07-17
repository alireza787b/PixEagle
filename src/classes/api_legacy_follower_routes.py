"""Legacy follower route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from classes.follower import FollowerFactory
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler


def _follower_schema_path() -> Path:
    return Path(__file__).parent.parent.parent / "configs" / "follower_commands.yaml"


def _has_active_follower(handler: Any) -> bool:
    return (
        hasattr(handler.app_controller, "follower")
        and handler.app_controller.follower is not None
        and handler.app_controller.following_active
    )


def _get_persisted_follower_mode(handler: Any) -> str:
    """Read the operator-selected profile from the canonical persisted config."""
    service_getter = getattr(handler, "_get_config_service", None)
    if callable(service_getter):
        configured = service_getter().get_parameter("Follower", "FOLLOWER_MODE")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
    return str(Parameters.FOLLOWER_MODE)


async def get_follower_schema(handler: Any) -> JSONResponse:
    """Get the complete follower command schema."""
    try:
        with open(_follower_schema_path(), "r") as schema_file:
            schema = yaml.safe_load(schema_file)
        return JSONResponse(content=schema)
    except Exception as exc:
        handler.logger.error(f"Error getting follower schema: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_follower_profiles(handler: Any) -> JSONResponse:
    """Get available follower profiles with implementation status."""
    try:
        profiles = {}
        available_modes = FollowerFactory.get_available_modes()

        for mode in available_modes:
            profiles[mode] = FollowerFactory.get_follower_info(mode)

        return JSONResponse(content=profiles)
    except Exception as exc:
        handler.logger.error(f"Error getting follower profiles: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_current_follower_profile(handler: Any) -> JSONResponse:
    """Get current follower profile information."""
    try:
        has_active_follower = _has_active_follower(handler)
        configured_mode = _get_persisted_follower_mode(handler)
        runtime_mode = str(Parameters.FOLLOWER_MODE)

        if has_active_follower:
            follower = handler.app_controller.follower
            profile_info = {
                "status": "engaged",
                "active": True,
                "mode": follower.mode,
                "display_name": follower.get_display_name(),
                "description": follower.get_description(),
                "control_type": follower.get_control_type(),
                "available_fields": follower.get_available_fields(),
                "current_field_values": follower.get_follower_telemetry().get(
                    "fields",
                    {},
                ),
                "validation_status": follower.validate_current_mode(),
                "configured_mode": configured_mode,
                "runtime_mode": runtime_mode,
            }
        else:
            try:
                profile_config = SetpointHandler.get_profile_info(configured_mode)
                profile_info = {
                    "status": "configured",
                    "active": False,
                    "mode": configured_mode,
                    "display_name": profile_config.get(
                        "display_name",
                        configured_mode.replace("_", " ").title(),
                    ),
                    "description": profile_config.get("description", "Not engaged"),
                    "control_type": profile_config.get("control_type", "unknown"),
                    "available_fields": profile_config.get("required_fields", []),
                    "current_field_values": {},
                    "validation_status": True,
                    "configured_mode": configured_mode,
                    "runtime_mode": runtime_mode,
                    "activation_pending": configured_mode != runtime_mode,
                    "message": (
                        "Profile is saved but not engaged. It will be applied by "
                        "a follower restart or the next guarded follow session."
                    ),
                }
            except Exception as exc:
                handler.logger.warning(
                    "Could not get schema info for configured mode "
                    f"'{configured_mode}': {exc}"
                )
                profile_info = {
                    "status": "unknown",
                    "active": False,
                    "mode": configured_mode,
                    "display_name": configured_mode.replace("_", " ").title(),
                    "description": "Unknown profile",
                    "control_type": "unknown",
                    "available_fields": [],
                    "current_field_values": {},
                    "validation_status": False,
                    "configured_mode": configured_mode,
                    "runtime_mode": runtime_mode,
                    "error": f"Profile not found in schema: {configured_mode}",
                }

        return JSONResponse(content=profile_info)

    except Exception as exc:
        handler.logger.error(f"Error getting current follower profile: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def switch_follower_profile(handler: Any, request: Request) -> JSONResponse:
    """Persist the profile for the next inactive follower generation."""
    try:
        data = await request.json()
        new_profile = data.get("profile_name")

        if not new_profile:
            raise HTTPException(status_code=400, detail="profile_name is required")

        try:
            available_profiles = SetpointHandler.get_available_profiles()
            if new_profile not in available_profiles:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid profile '{new_profile}'. "
                        f"Available: {available_profiles}"
                    ),
                )
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Schema validation failed: {exc}",
            ) from exc

        if _has_active_follower(handler):
            return JSONResponse(
                status_code=409,
                content={
                    "status": "error",
                    "action": "profile_change_blocked",
                    "error_code": "FOLLOWER_PROFILE_CHANGE_WHILE_ACTIVE",
                    "message": (
                        "Stop follow mode before changing the follower profile. "
                        "Live profile switching is intentionally disabled because "
                        "it would change the PX4 command contract in Offboard."
                    ),
                },
            )

        old_configured_mode = _get_persisted_follower_mode(handler)
        from classes.api_legacy_config_routes import (
            ConfigParameterUpdate,
            update_config_parameter,
        )

        update_response = await update_config_parameter(
            handler,
            "Follower",
            "FOLLOWER_MODE",
            ConfigParameterUpdate(value=new_profile),
        )
        if update_response.status_code >= 400:
            return update_response

        handler.logger.info(
            "Configured follower profile persisted: "
            f"{old_configured_mode} \u2192 {new_profile}"
        )

        return JSONResponse(
            content={
                "status": "success",
                "action": "profile_saved",
                "old_profile": old_configured_mode,
                "new_profile": new_profile,
                "saved": True,
                "applied": False,
                "reload_tier": "follower_restart",
                "message": (
                    f"Follower profile {new_profile} is saved. It will activate "
                    "after a follower restart or at the next follow session."
                ),
            }
        )

    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error switching follower profile: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_configured_follower_mode(handler: Any) -> JSONResponse:
    """Get the canonical persisted follower mode."""
    try:
        configured_mode = _get_persisted_follower_mode(handler)

        try:
            profile_config = SetpointHandler.get_profile_info(configured_mode)
            return JSONResponse(
                content={
                    "configured_mode": configured_mode,
                    "profile_info": profile_config,
                    "status": "valid",
                }
            )
        except Exception as exc:
            return JSONResponse(
                content={
                    "configured_mode": configured_mode,
                    "profile_info": None,
                    "status": "invalid",
                    "error": str(exc),
                }
            )

    except Exception as exc:
        handler.logger.error(f"Error getting configured follower mode: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_follower_setpoints_with_status(handler: Any) -> JSONResponse:
    """Get current follower setpoints with circuit-breaker status."""
    try:
        has_active_follower = _has_active_follower(handler)

        if not has_active_follower:
            try:
                from classes.circuit_breaker import FollowerCircuitBreaker

                circuit_breaker_active = FollowerCircuitBreaker.is_active()
            except ImportError:
                circuit_breaker_active = True

            return JSONResponse(
                content={
                    "follower_active": False,
                    "message": "No active follower",
                    "configured_mode": Parameters.FOLLOWER_MODE,
                    "circuit_breaker": {
                        "active": circuit_breaker_active,
                        "status": (
                            "SAFE_MODE" if circuit_breaker_active else "LIVE_MODE"
                        ),
                    },
                    "timestamp": time.time(),
                }
            )

        follower = handler.app_controller.follower
        concrete_follower = getattr(follower, "follower", None)
        setpoint_handler = (
            getattr(follower, "setpoint_handler", None)
            or getattr(concrete_follower, "setpoint_handler", None)
        )

        if setpoint_handler:
            setpoint_data = setpoint_handler.get_fields_with_status()
            commander = getattr(handler.app_controller, "offboard_commander", None)
            commander_status = (
                commander.get_status()
                if commander and hasattr(commander, "get_status")
                else {"exists": False, "running": False}
            )
            commands_sent_to_px4 = bool(
                commander_status.get("running", False)
                and commander_status.get("successful_publishes", 0) > 0
            )
            setpoint_data["command_publication"] = {
                "source": "offboard_commander",
                "offboard_commander": commander_status,
                "commands_sent_to_px4": commands_sent_to_px4,
                "last_intent_fresh": commander_status.get("last_intent_fresh"),
                "failsafe_defaults_active": commander_status.get(
                    "failsafe_defaults_active"
                ),
            }
            circuit_breaker = setpoint_data.get("circuit_breaker", {})
            circuit_breaker["commands_allowed_by_circuit_breaker"] = (
                not circuit_breaker.get("active", True)
            )
            circuit_breaker["commands_sent_to_px4"] = commands_sent_to_px4
            setpoint_data["circuit_breaker"] = circuit_breaker

            setpoint_data.update(
                {
                    "follower_active": True,
                    "follower_type": (
                        concrete_follower.__class__.__name__
                        if concrete_follower
                        else follower.__class__.__name__
                    ),
                    "configured_mode": Parameters.FOLLOWER_MODE,
                    "following_engaged": handler.app_controller.following_active,
                }
            )

            return JSONResponse(content=setpoint_data)

        return JSONResponse(
            content={
                "follower_active": True,
                "follower_type": follower.__class__.__name__,
                "error": "Follower has no setpoint handler",
                "timestamp": time.time(),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error getting follower setpoints with status: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_current_follower_mode(handler: Any) -> JSONResponse:
    """Get the currently active follower mode with detailed status."""
    try:
        configured_mode = Parameters.FOLLOWER_MODE
        is_active = (
            handler.app_controller.following_active
            if handler.app_controller
            else False
        )

        try:
            from classes.safety_manager import get_safety_manager

            safety_manager = get_safety_manager()
            limits_summary = safety_manager.get_effective_limits_summary(
                configured_mode.upper()
            )
            limits_available = True
        except Exception:
            limits_summary = {}
            limits_available = False

        try:
            profile_config = SetpointHandler.get_profile_info(configured_mode)
            profile_valid = True
        except Exception:
            profile_config = None
            profile_valid = False

        return JSONResponse(
            content={
                "success": True,
                "mode": configured_mode,
                "mode_upper": configured_mode.upper(),
                "is_active": is_active,
                "profile_valid": profile_valid,
                "profile_info": profile_config,
                "limits_available": limits_available,
                "effective_limits": limits_summary if limits_available else None,
                "timestamp": time.time(),
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error getting current follower mode: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_follower_health(handler: Any) -> JSONResponse:
    """Get legacy follower subsystem health details."""
    try:
        health_status = {
            "timestamp": time.time(),
            "overall_status": "healthy",
            "components": {},
            "metrics": {},
            "issues": [],
        }

        follower_component = {
            "active": handler.app_controller.following_active,
            "status": (
                "active" if handler.app_controller.following_active else "inactive"
            ),
        }

        if handler.app_controller.following_active:
            if (
                hasattr(handler.app_controller, "follower")
                and handler.app_controller.follower
            ):
                follower = handler.app_controller.follower
                follower_component["has_instance"] = True
                follower_component["type"] = (
                    follower.get_display_name()
                    if hasattr(follower, "get_display_name")
                    else "unknown"
                )
                follower_component["control_type"] = (
                    follower.get_control_type()
                    if hasattr(follower, "get_control_type")
                    else "unknown"
                )
                follower_component["mode_valid"] = (
                    follower.validate_current_mode()
                    if hasattr(follower, "validate_current_mode")
                    else False
                )
            else:
                follower_component["has_instance"] = False
                health_status["issues"].append(
                    "Follower marked active but instance is None"
                )
                health_status["overall_status"] = "degraded"

            if (
                hasattr(handler.app_controller, "offboard_commander")
                and handler.app_controller.offboard_commander
            ):
                commander = handler.app_controller.offboard_commander
                commander_status = (
                    commander.get_status()
                    if hasattr(commander, "get_status")
                    else {"exists": True, "running": False}
                )
                follower_component["offboard_commander"] = commander_status

                commander_health = commander_status.get("health_state")
                if not commander_status.get("running", False) or (
                    commander_health == "failed"
                ):
                    health_status["issues"].append("OffboardCommander is not running")
                    health_status["overall_status"] = "unhealthy"
                elif commander_health == "degraded":
                    health_status["issues"].append(
                        "OffboardCommander has transient publish failures"
                    )
                    if health_status["overall_status"] == "healthy":
                        health_status["overall_status"] = "degraded"
            else:
                follower_component["offboard_commander"] = {"exists": False}
                health_status["issues"].append(
                    "Follower active but OffboardCommander is None"
                )
                health_status["overall_status"] = "unhealthy"

            follower_component["setpoint_sender"] = {
                "exists": bool(
                    hasattr(handler.app_controller, "setpoint_sender")
                    and handler.app_controller.setpoint_sender
                ),
                "role": "legacy_monitor",
            }
        else:
            follower_component["has_instance"] = bool(
                hasattr(handler.app_controller, "follower")
                and handler.app_controller.follower
            )
            follower_component["offboard_commander"] = {
                "exists": bool(
                    hasattr(handler.app_controller, "offboard_commander")
                    and handler.app_controller.offboard_commander
                )
            }
            follower_component["setpoint_sender"] = {
                "exists": bool(
                    hasattr(handler.app_controller, "setpoint_sender")
                    and handler.app_controller.setpoint_sender
                )
            }

            if (
                follower_component["has_instance"]
                or follower_component["offboard_commander"]["exists"]
                or follower_component["setpoint_sender"]["exists"]
            ):
                health_status["issues"].append(
                    "Follower inactive but resources not cleaned up"
                )
                health_status["overall_status"] = "degraded"

        health_status["components"]["follower"] = follower_component

        px4_component = {
            "initialized": hasattr(handler.app_controller, "px4_interface"),
            "status": "unknown",
        }

        if px4_component["initialized"]:
            px4_interface = handler.app_controller.px4_interface
            if hasattr(px4_interface, "is_connected"):
                px4_component["connected"] = px4_interface.is_connected()
                px4_component["status"] = (
                    "connected" if px4_component["connected"] else "disconnected"
                )
            elif hasattr(px4_interface, "connection"):
                px4_component["has_connection"] = px4_interface.connection is not None
                px4_component["status"] = (
                    "ready" if px4_component["has_connection"] else "not_ready"
                )

        health_status["components"]["px4_interface"] = px4_component

        tracker_component = {
            "initialized": hasattr(handler.app_controller, "tracker"),
            "tracking_active": getattr(handler.app_controller, "tracking_started", False),
        }

        if tracker_component["initialized"]:
            tracker = handler.app_controller.tracker
            tracker_component["type"] = tracker.__class__.__name__ if tracker else "None"

        health_status["components"]["tracker"] = tracker_component

        follower_state_lock = getattr(
            handler.app_controller,
            "_follower_state_lock",
            None,
        )
        lock_component = {
            "initialized": follower_state_lock is not None,
            "type": (
                type(follower_state_lock).__name__
                if follower_state_lock is not None
                else "None"
            ),
        }
        health_status["components"]["state_lock"] = lock_component

        if not lock_component["initialized"]:
            health_status["issues"].append(
                "State lock not initialized - thread safety compromised"
            )
            health_status["overall_status"] = "unhealthy"

        config_component = {
            "follower_mode": Parameters.FOLLOWER_MODE,
            "valid": False,
        }

        try:
            available_profiles = SetpointHandler.get_available_profiles()
            config_component["valid"] = Parameters.FOLLOWER_MODE in available_profiles
            config_component["available_profiles"] = available_profiles

            if not config_component["valid"]:
                health_status["issues"].append(
                    f"Invalid follower mode: {Parameters.FOLLOWER_MODE}"
                )
                if health_status["overall_status"] == "healthy":
                    health_status["overall_status"] = "degraded"

        except Exception as exc:
            config_component["error"] = str(exc)
            health_status["issues"].append(f"Configuration validation error: {exc}")

        health_status["components"]["configuration"] = config_component

        metrics = {}

        if (
            hasattr(handler.app_controller, "following_active")
            and handler.app_controller.following_active
        ):
            if hasattr(handler.app_controller, "_following_start_time"):
                uptime = time.time() - handler.app_controller._following_start_time
                metrics["follower_uptime_seconds"] = round(uptime, 2)

        health_status["metrics"] = metrics

        commander_for_summary = follower_component.get("offboard_commander", {})
        health_status["summary"] = {
            "components_checked": len(health_status["components"]),
            "issues_found": len(health_status["issues"]),
            "follower_operational": (
                (
                    handler.app_controller.following_active
                    and follower_component.get("has_instance", False)
                    and commander_for_summary.get("running", False)
                    and commander_for_summary.get("health_state") != "failed"
                )
                if handler.app_controller.following_active
                else True
            ),
        }

        return JSONResponse(content=health_status)

    except Exception as exc:
        handler.logger.error(f"Error in follower health check: {exc}")
        return JSONResponse(
            content={
                "timestamp": time.time(),
                "overall_status": "error",
                "error": str(exc),
                "exception_type": type(exc).__name__,
            },
            status_code=500,
        )


async def restart_follower(handler: Any) -> JSONResponse:
    """Apply pending follower-tier config while following is inactive."""
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
                    "error_code": "FOLLOWER_STATE_BARRIER_UNAVAILABLE",
                    "error": "Follower state barrier is unavailable; restart refused",
                },
            )

        async with follower_lock:
            if bool(getattr(app_controller, "following_active", False)):
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "action": "follower_restart_blocked",
                        "error_code": "FOLLOWER_RESTART_WHILE_ACTIVE",
                        "error": "Stop follow mode before applying follower configuration",
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

            publication = await run_in_threadpool(
                service_getter().apply_runtime_config_tiers,
                {"immediate", "follower_restart"},
                source="follower_restart_action",
            )
            current_profile = str(Parameters.FOLLOWER_MODE)
            handler.logger.info(
                "Follower configuration generation applied: profile=%s paths=%s",
                current_profile,
                publication["applied_count"],
            )

        return JSONResponse(
            content={
                "success": True,
                "action": "follower_config_applied",
                "profile": current_profile,
                "message": (
                    "Follower configuration is ready for the next follow session "
                    f"(profile: {current_profile})."
                ),
                "config_reloaded": bool(publication["applied"]),
                "runtime_publication": publication,
            }
        )

    except Exception as exc:
        handler.logger.error(f"Error restarting follower: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_follower_config_general(handler: Any) -> JSONResponse:
    """Get legacy general follower config values."""
    try:
        from classes.follower_config_manager import get_follower_config_manager

        fcm = get_follower_config_manager()
        summary = fcm.get_all_config_summary()
        return JSONResponse(
            content={
                "available": True,
                "general": summary["general"],
                "follower_overrides": summary["follower_overrides"],
                "available_followers": list(summary["follower_overrides"]),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting follower config general: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_follower_config_effective(
    handler: Any,
    follower_name: str,
) -> JSONResponse:
    """Get legacy per-parameter provenance for a specific follower."""
    try:
        from classes.follower_config_manager import get_follower_config_manager

        fcm = get_follower_config_manager()
        summary = fcm.get_effective_config_summary(follower_name)

        return JSONResponse(
            content={
                "follower_name": follower_name,
                "params": summary,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting follower config for {follower_name}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
