"""Legacy config mutation helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from classes.api_legacy_config_sync import (
    ConfigSyncPlanRequest,
    build_defaults_sync_plan,
)
from classes.parameters import Parameters


class ConfigParameterUpdate(BaseModel):
    """Request model for updating a single parameter."""

    value: Optional[str | int | float | bool | list | dict] = None


class ConfigSectionUpdate(BaseModel):
    """Request model for updating multiple parameters in a section."""

    parameters: Dict[str, Optional[str | int | float | bool | list | dict]]


class ConfigImportRequest(BaseModel):
    """Request model for importing configuration."""

    data: Dict[str, Any]
    merge_mode: str = "merge"


def _config_write_rate_limit_response(handler: Any) -> Optional[JSONResponse]:
    allowed, retry_after = handler.config_rate_limiter.is_allowed("config_write")
    if allowed:
        return None
    return JSONResponse(
        status_code=429,
        content={
            "success": False,
            "error": "Too many requests",
            "retry_after": retry_after,
            "timestamp": time.time(),
        },
        headers={"Retry-After": str(retry_after)},
    )


async def update_config_parameter(
    handler: Any,
    section: str,
    parameter: str,
    body: ConfigParameterUpdate,
) -> JSONResponse:
    """Update a single configuration parameter."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited

    try:
        service = handler._get_config_service()
        result = service.set_parameter(section, parameter, body.value)

        if not result.valid:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "validation": result.to_dict(),
                    "timestamp": time.time(),
                },
            )

        saved = service.save_config()

        applied = False
        if saved:
            try:
                reload_success = Parameters.reload_config()
                if reload_success:
                    applied = True
                    handler.logger.info(
                        f"Config hot-reloaded after updating {section}.{parameter}"
                    )
                else:
                    handler.logger.warning(
                        f"Config reload returned False for {section}.{parameter}"
                    )
            except Exception as reload_error:
                handler.logger.error(f"Config reload failed: {reload_error}")

        reload_tier = service.get_reload_tier(section, parameter)
        reload_message = service.get_reload_message(reload_tier)
        effective_applied = applied and reload_tier == "immediate"
        if applied and not effective_applied:
            handler.logger.info(
                "Config reload succeeded for %s.%s, but reload_tier=%s requires restart; reporting applied=false",
                section,
                parameter,
                reload_tier,
            )

        return JSONResponse(
            content={
                "success": True,
                "section": section,
                "parameter": parameter,
                "value": body.value,
                "validation": result.to_dict(),
                "saved": saved,
                "applied": effective_applied,
                "reload_tier": reload_tier,
                "reload_message": reload_message,
                "reboot_required": service.is_reboot_required(section, parameter),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error updating config parameter: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def update_config_section(
    handler: Any,
    section: str,
    body: ConfigSectionUpdate,
) -> JSONResponse:
    """Update multiple parameters in a section."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited

    try:
        service = handler._get_config_service()
        result = service.set_section(section, body.parameters)

        if not result.valid:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "validation": result.to_dict(),
                    "timestamp": time.time(),
                },
            )

        saved = service.save_config()

        applied = False
        if saved:
            try:
                reload_success = Parameters.reload_config()
                if reload_success:
                    applied = True
                    handler.logger.info(
                        f"Config hot-reloaded after updating section {section}"
                    )
                else:
                    handler.logger.warning(
                        f"Config reload returned False for section {section}"
                    )
            except Exception as reload_error:
                handler.logger.error(f"Config reload failed: {reload_error}")

        reload_tiers = {
            param: service.get_reload_tier(section, param)
            for param in body.parameters.keys()
        }

        tier_priority = {
            "system_restart": 4,
            "tracker_restart": 3,
            "follower_restart": 2,
            "immediate": 1,
        }
        if reload_tiers:
            max_tier = max(reload_tiers.values(), key=lambda t: tier_priority.get(t, 4))
        else:
            max_tier = "immediate"
        reload_message = service.get_reload_message(max_tier)
        effective_applied = applied and max_tier == "immediate"
        if applied and not effective_applied:
            handler.logger.info(
                "Config reload succeeded for section %s, but highest reload_tier=%s requires restart; reporting applied=false",
                section,
                max_tier,
            )

        reboot_required = any(
            service.is_reboot_required(section, param)
            for param in body.parameters.keys()
        )

        return JSONResponse(
            content={
                "success": True,
                "section": section,
                "parameters": body.parameters,
                "validation": result.to_dict(),
                "saved": saved,
                "applied": effective_applied,
                "reload_tiers": reload_tiers,
                "reload_tier": max_tier,
                "reload_message": reload_message,
                "reboot_required": reboot_required,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error updating config section: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def validate_config_value(handler: Any, request: Request) -> JSONResponse:
    """Validate a configuration value without saving."""
    try:
        body = await request.json()
        section = body.get("section")
        parameter = body.get("parameter")
        value = body.get("value")

        if not section or not parameter:
            raise HTTPException(
                status_code=400,
                detail="section and parameter are required",
            )

        service = handler._get_config_service()
        result = service.validate_value(section, parameter, value)

        return JSONResponse(
            content={
                "success": True,
                "section": section,
                "parameter": parameter,
                "value": value,
                "validation": result.to_dict(),
                "timestamp": time.time(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error validating config value: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def apply_defaults_sync(
    handler: Any,
    body: ConfigSyncPlanRequest,
) -> JSONResponse:
    """Apply validated defaults-sync operations atomically."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited

    service = handler._get_config_service()
    plan = build_defaults_sync_plan(service, body.operations)
    if not plan["valid"]:
        return JSONResponse(
            status_code=400,
            content={"success": False, "plan": plan, "timestamp": time.time()},
        )

    backup_path = None
    applied_ops: List[Dict[str, Any]] = []
    skipped_ops: List[Dict[str, Any]] = []

    try:
        backup_path = service._create_backup()

        for op in plan["operations"]:
            if op["skip"]:
                skipped_ops.append(op)
                continue

            op_type = op["op_type"]
            section = op["section"]
            parameter = op["parameter"]

            if op_type in {"ADD_NEW", "ADOPT_DEFAULT"}:
                result = service.set_parameter(
                    section,
                    parameter,
                    op["target_value"],
                    validate=True,
                )
                if not result.valid:
                    raise ValueError(
                        f"Validation failed for {section}.{parameter}: {result.errors}"
                    )
                op["reload_tier"] = service.get_reload_tier(section, parameter)
                applied_ops.append(op)
            elif op_type == "ARCHIVE_REMOVE":
                archived = service.archive_and_remove_parameter(section, parameter)
                if not archived:
                    raise ValueError(f"Failed to archive/remove {section}.{parameter}")
                op["reload_tier"] = "immediate"
                applied_ops.append(op)

        saved = service.save_config(backup=False)
        if not saved:
            raise RuntimeError("Failed to save config after applying sync plan")

        try:
            Parameters.reload_config()
        except Exception as reload_error:
            handler.logger.warning(
                f"Config sync applied but reload failed: {reload_error}"
            )

        service.refresh_defaults_snapshot()

        backup_id = None
        if backup_path:
            try:
                backup_id = Path(backup_path).stem
            except Exception:
                backup_id = None

        return JSONResponse(
            content={
                "success": True,
                "applied_count": len(applied_ops),
                "skipped_count": len(skipped_ops),
                "applied_operations": applied_ops,
                "skipped_operations": skipped_ops,
                "backup_id": backup_id,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        try:
            service.reload()
        except Exception:
            pass
        handler.logger.error(f"Error applying defaults sync: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def revert_config_to_default(handler: Any) -> JSONResponse:
    """Revert all configuration to defaults."""
    try:
        service = handler._get_config_service()
        success = service.revert_to_default()
        if success:
            service.save_config()

        return JSONResponse(
            content={
                "success": success,
                "message": (
                    "Configuration reverted to defaults" if success else "Failed to revert"
                ),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error reverting config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def revert_section_to_default(handler: Any, section: str) -> JSONResponse:
    """Revert a section to defaults."""
    try:
        service = handler._get_config_service()
        success = service.revert_to_default(section=section)
        if success:
            service.save_config()

        return JSONResponse(
            content={
                "success": success,
                "section": section,
                "message": (
                    f"Section '{section}' reverted to defaults"
                    if success
                    else "Failed to revert"
                ),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error reverting section: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def revert_parameter_to_default(
    handler: Any,
    section: str,
    parameter: str,
) -> JSONResponse:
    """Revert a single parameter to default."""
    try:
        service = handler._get_config_service()
        success = service.revert_to_default(section=section, param=parameter)
        if success:
            service.save_config()

        default_value = service.get_default_parameter(section, parameter)

        return JSONResponse(
            content={
                "success": success,
                "section": section,
                "parameter": parameter,
                "default_value": default_value,
                "message": "Parameter reverted to default" if success else "Failed to revert",
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error reverting parameter: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def restore_config_backup(handler: Any, backup_id: str) -> JSONResponse:
    """Restore configuration from a backup."""
    try:
        service = handler._get_config_service()
        success = service.restore_backup(backup_id)

        if success:
            try:
                Parameters.reload_config()
            except Exception as exc:
                handler.logger.error(f"Failed to reload after backup restore: {exc}")

        return JSONResponse(
            content={
                "success": success,
                "backup_id": backup_id,
                "message": (
                    "Configuration restored from backup"
                    if success
                    else "Failed to restore backup"
                ),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error restoring backup: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def import_config(handler: Any, body: ConfigImportRequest) -> JSONResponse:
    """Import configuration."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited

    try:
        service = handler._get_config_service()
        success, diffs = service.import_config(body.data, body.merge_mode)

        if success:
            service.save_config()

        return JSONResponse(
            content={
                "success": success,
                "merge_mode": body.merge_mode,
                "changes": [d.to_dict() for d in diffs],
                "changes_count": len(diffs),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error importing config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
