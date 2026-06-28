"""Legacy follower route helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

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
        configured_mode = Parameters.FOLLOWER_MODE

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
                    "available_fields": (
                        profile_config.get("required_fields", [])
                        + profile_config.get("optional_fields", [])
                    ),
                    "current_field_values": {},
                    "validation_status": True,
                    "configured_mode": configured_mode,
                    "message": (
                        "Profile configured but not engaged. "
                        "Start offboard mode to activate."
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
                    "error": f"Profile not found in schema: {configured_mode}",
                }

        return JSONResponse(content=profile_info)

    except Exception as exc:
        handler.logger.error(f"Error getting current follower profile: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def switch_follower_profile(handler: Any, request: Request) -> JSONResponse:
    """Switch follower profile or configured future profile."""
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

        has_active_follower = _has_active_follower(handler)
        old_configured_mode = Parameters.FOLLOWER_MODE

        if has_active_follower:
            follower = handler.app_controller.follower
            success = follower.switch_mode(new_profile)

            if success:
                Parameters.FOLLOWER_MODE = new_profile
                handler.logger.info(
                    "Active follower switched: "
                    f"{old_configured_mode} \u2192 {new_profile}"
                )

                return JSONResponse(
                    content={
                        "status": "success",
                        "action": "active_switch",
                        "old_profile": old_configured_mode,
                        "new_profile": new_profile,
                        "message": f"Active follower switched to {new_profile}",
                    }
                )

            return JSONResponse(
                content={
                    "status": "error",
                    "action": "active_switch_failed",
                    "message": f"Failed to switch active follower to {new_profile}",
                },
                status_code=500,
            )

        Parameters.FOLLOWER_MODE = new_profile
        handler.logger.info(
            "Configured follower mode updated: "
            f"{old_configured_mode} \u2192 {new_profile}"
        )

        return JSONResponse(
            content={
                "status": "success",
                "action": "config_update",
                "old_profile": old_configured_mode,
                "new_profile": new_profile,
                "message": (
                    f"Configured follower mode set to {new_profile}. "
                    "Will activate when offboard mode starts."
                ),
            }
        )

    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error switching follower profile: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_configured_follower_mode(handler: Any) -> JSONResponse:
    """Get the currently configured follower mode from Parameters."""
    try:
        configured_mode = Parameters.FOLLOWER_MODE

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
