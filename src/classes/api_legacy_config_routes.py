"""Legacy config helpers used by FastAPI compatibility routes."""

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
    build_defaults_sync_report,
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


async def get_config_schema(handler: Any) -> JSONResponse:
    """Get full configuration schema."""
    try:
        service = handler._get_config_service()
        schema = service.get_schema()
        return JSONResponse(
            content={
                "success": True,
                "schema": schema,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting config schema: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_config_section_schema(handler: Any, section: str) -> JSONResponse:
    """Get schema for a specific section."""
    try:
        service = handler._get_config_service()
        schema = service.get_schema(section)
        if not schema:
            raise HTTPException(
                status_code=404,
                detail=f"Section '{section}' not found",
            )
        return JSONResponse(
            content={
                "success": True,
                "section": section,
                "schema": schema,
                "timestamp": time.time(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error getting section schema: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_config_sections(handler: Any) -> JSONResponse:
    """Get list of all configuration sections."""
    try:
        service = handler._get_config_service()
        sections = service.get_sections()
        return JSONResponse(
            content={
                "success": True,
                "sections": sections,
                "count": len(sections),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting config sections: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_config_categories(handler: Any) -> JSONResponse:
    """Get category definitions."""
    try:
        service = handler._get_config_service()
        categories = service.get_categories()
        return JSONResponse(
            content={
                "success": True,
                "categories": categories,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting config categories: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_current_config(handler: Any) -> JSONResponse:
    """Get current configuration."""
    try:
        service = handler._get_config_service()
        config = service.get_config()
        return JSONResponse(
            content={
                "success": True,
                "config": config,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting current config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_current_config_section(handler: Any, section: str) -> JSONResponse:
    """Get current configuration for a specific section."""
    try:
        service = handler._get_config_service()
        config = service.get_config(section)
        return JSONResponse(
            content={
                "success": True,
                "section": section,
                "config": config,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting section config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_default_config(handler: Any) -> JSONResponse:
    """Get default configuration."""
    try:
        service = handler._get_config_service()
        config = service.get_default()
        return JSONResponse(
            content={
                "success": True,
                "config": config,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting default config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_default_config_section(handler: Any, section: str) -> JSONResponse:
    """Get default configuration for a specific section."""
    try:
        service = handler._get_config_service()
        config = service.get_default(section)
        return JSONResponse(
            content={
                "success": True,
                "section": section,
                "config": config,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting default section config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_config_diff(handler: Any) -> JSONResponse:
    """Get differences between current config and defaults."""
    try:
        service = handler._get_config_service()
        diffs = service.get_changed_from_default()
        return JSONResponse(
            content={
                "success": True,
                "differences": [diff.to_dict() for diff in diffs],
                "count": len(diffs),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting config diff: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def compare_configs(handler: Any, request: Request) -> JSONResponse:
    """Compare incoming config against current config or compare two configs."""
    try:
        body = await request.json()
        service = handler._get_config_service()

        if "compare_config" in body:
            compare_config = body.get("compare_config", {})
            current_config = service.get_config()
            diffs = service.get_diff(current_config, compare_config)
        else:
            config1 = body.get("config1", {})
            config2 = body.get("config2", {})
            diffs = service.get_diff(config1, config2)

        return JSONResponse(
            content={
                "success": True,
                "differences": [diff.to_dict() for diff in diffs],
                "count": len(diffs),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error comparing configs: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_defaults_sync(handler: Any) -> JSONResponse:
    """Get sync information between current config and defaults."""
    try:
        service = handler._get_config_service()
        report = build_defaults_sync_report(service)
        if not report["baseline_available"]:
            service.refresh_defaults_snapshot()
            report["baseline_initialized"] = True
        else:
            report["baseline_initialized"] = False

        report.update({"success": True, "timestamp": time.time()})
        return JSONResponse(content=report)
    except Exception as exc:
        handler.logger.error(f"Error getting defaults sync: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def plan_defaults_sync(
    handler: Any,
    body: ConfigSyncPlanRequest,
) -> JSONResponse:
    """Validate selected sync operations and return a dry-run plan."""
    try:
        service = handler._get_config_service()
        plan = build_defaults_sync_plan(service, body.operations)
        return JSONResponse(
            content={
                "success": True,
                "plan": plan,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error planning defaults sync: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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


async def get_config_backup_history(handler: Any, request: Request) -> JSONResponse:
    """Get list of configuration backups."""
    try:
        limit = int(request.query_params.get("limit", 20))
        service = handler._get_config_service()
        backups = service.get_backup_history(limit=limit)

        return JSONResponse(
            content={
                "success": True,
                "backups": [backup.to_dict() for backup in backups],
                "count": len(backups),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting backup history: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def export_config(handler: Any, request: Request) -> JSONResponse:
    """Export configuration."""
    try:
        sections = request.query_params.get("sections")
        changes_only = (
            request.query_params.get("changes_only", "false").lower() == "true"
        )

        sections_list = sections.split(",") if sections else None

        service = handler._get_config_service()
        exported = service.export_config(
            sections=sections_list,
            changes_only=changes_only,
        )

        return JSONResponse(
            content={
                "success": True,
                "config": exported,
                "changes_only": changes_only,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error exporting config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def search_config_parameters(handler: Any, request: Request) -> JSONResponse:
    """Search configuration parameters with filtering and pagination."""
    try:
        query = request.query_params.get("q", "")
        section = request.query_params.get("section")
        param_type = request.query_params.get("type")
        modified_only = (
            request.query_params.get("modified_only", "").lower() == "true"
        )
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))

        service = handler._get_config_service()
        result = service.search_parameters(
            query=query,
            section=section,
            param_type=param_type,
            modified_only=modified_only,
            limit=limit,
            offset=offset,
        )

        return JSONResponse(
            content={
                "success": True,
                "query": query,
                "filters": {
                    "section": section,
                    "type": param_type,
                    "modified_only": modified_only,
                },
                **result,
                "timestamp": time.time(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error searching config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def get_config_audit_log(handler: Any, request: Request) -> JSONResponse:
    """Get configuration change audit log."""
    try:
        limit = int(request.query_params.get("limit", 100))
        offset = int(request.query_params.get("offset", 0))
        section = request.query_params.get("section")
        action = request.query_params.get("action")

        service = handler._get_config_service()
        result = service.get_audit_log(
            limit=limit,
            offset=offset,
            section=section,
            action=action,
        )

        return JSONResponse(
            content={
                "success": True,
                **result,
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error getting audit log: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
