"""Legacy config helpers used by FastAPI compatibility routes."""

from __future__ import annotations

import copy
import hashlib
import hmac
import secrets
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Dict, Iterator, List, Literal, Optional, Tuple

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from classes.api_execution import offload_blocking_route
from classes.config_sync import (
    ConfigSyncApplyRequest,
    ConfigSyncPlanRequest,
    SYNC_CONTRACT_VERSION,
    build_defaults_sync_plan,
    build_defaults_sync_report,
)
from classes.parameters import Parameters


_CONFIG_SYNC_PLAN_TOKEN_KEY = secrets.token_bytes(32)


class ConfigParameterUpdate(BaseModel):
    """Request model for updating a single parameter."""

    model_config = ConfigDict(extra="forbid")
    value: Optional[str | int | float | bool | list | dict] = None


class ConfigSectionUpdate(BaseModel):
    """Request model for updating multiple parameters in a section."""

    model_config = ConfigDict(extra="forbid")
    parameters: Dict[str, Optional[str | int | float | bool | list | dict]]


class ConfigImportRequest(BaseModel):
    """Request model for importing configuration."""

    model_config = ConfigDict(extra="forbid")
    data: Dict[str, Any]
    merge_mode: Literal["merge", "replace"] = "merge"


class ConfigMutationRollbackError(RuntimeError):
    """A failed config mutation could not be fully rolled back without data loss."""


@dataclass
class ConfigMutationTransaction:
    """Track exact persistence artifacts owned by one config mutation."""

    source_digests: Dict[str, str]
    persistence_snapshot: Dict[str, Dict[str, Any]]
    owned_state: Dict[str, Any] = field(default_factory=dict)

    def record_write_receipt(self, receipt: Dict[str, Any]) -> None:
        """Record exact digests produced by service write operations."""
        for name in ("runtime_config", "sync_meta", "audit_log", "backups"):
            if name in receipt:
                self.owned_state[name] = copy.deepcopy(receipt[name])


def guarded_config_mutation_route(function):
    """Serialize one blocking config transaction with follower state changes."""

    @wraps(function)
    async def wrapper(handler: Any, *args: Any, **kwargs: Any) -> JSONResponse:
        app_controller = getattr(handler, "app_controller", None)
        follower_lock = getattr(app_controller, "_follower_state_lock", None)
        if follower_lock is None:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": (
                        "Configuration mutation state barrier is unavailable; "
                        "change refused"
                    ),
                    "error_code": "CONFIG_MUTATION_STATE_BARRIER_UNAVAILABLE",
                    "timestamp": time.time(),
                },
            )

        async with follower_lock:
            return await run_in_threadpool(function, handler, *args, **kwargs)

    return wrapper


def _config_write_rate_limit_response(handler: Any) -> Optional[JSONResponse]:
    app_controller = getattr(handler, "app_controller", None)
    if bool(getattr(app_controller, "following_active", False)):
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "error": "Configuration changes are blocked while following is active",
                "error_code": "CONFIG_MUTATION_FOLLOWING_ACTIVE",
                "timestamp": time.time(),
            },
        )
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


def _public_sync_operation(service: Any, operation: Dict[str, Any]) -> Dict[str, Any]:
    """Return a response-safe copy of a config-sync operation."""
    result = copy.deepcopy(operation)
    path = result.get("path", [])
    result["target_value"] = service.redact_value(result.get("target_value"), path)
    return result


def _public_sync_plan(service: Any, plan: Dict[str, Any]) -> Dict[str, Any]:
    """Return a redacted plan with an opaque process-local confirmation token."""
    result = copy.deepcopy(plan)
    result["operations"] = [
        _public_sync_operation(service, operation)
        for operation in result.get("operations", [])
    ]
    for internal_field in (
        "config_digest",
        "defaults_digest",
        "schema_digest",
        "source_state_digests",
    ):
        result.pop(internal_field, None)
    result["plan_digest"] = _config_sync_plan_token(plan)
    return result


def _config_sync_plan_token(plan: Dict[str, Any]) -> str:
    """Bind a public confirmation token to an internal plan without a hash oracle."""
    internal_digest = str(plan["plan_digest"]).encode("ascii")
    return hmac.new(
        _CONFIG_SYNC_PLAN_TOKEN_KEY,
        internal_digest,
        hashlib.sha256,
    ).hexdigest()


@contextmanager
def _config_mutation_transaction(
    handler: Any,
) -> Iterator[Tuple[Any, ConfigMutationTransaction]]:
    """Guard one persisted mutation and roll back only transaction-owned state."""
    service = handler._get_config_service()
    with service.mutation_guard():
        service.reload()
        service.reload_audit_log(strict=True, lock_acquired=True)
        transaction = ConfigMutationTransaction(
            source_digests=service.get_source_state_digests(),
            persistence_snapshot=service.capture_persistence_snapshot(),
        )
        try:
            yield service, transaction
        except Exception as exc:
            rollback_error: Optional[Exception] = None
            try:
                service.restore_persistence_snapshot(
                    transaction.persistence_snapshot,
                    lock_acquired=True,
                    expected_current_state=transaction.owned_state,
                )
            except Exception as restore_exc:
                rollback_error = restore_exc
                handler.logger.critical(
                    "Config mutation persistence rollback was incomplete: %s",
                    restore_exc,
                )

            try:
                service.reload()
                service.reload_audit_log(strict=True, lock_acquired=True)
                if not Parameters.reload_config(strict_dependents=True):
                    raise RuntimeError("Restored config could not be reloaded")
            except Exception as reload_exc:
                rollback_error = rollback_error or reload_exc
                handler.logger.critical(
                    "Config mutation rollback reload failed: %s",
                    reload_exc,
                )

            if rollback_error is not None:
                raise ConfigMutationRollbackError(
                    "Config mutation failed; rollback requires operator recovery"
                ) from exc
            raise


def _persist_config(
    service: Any,
    transaction: ConfigMutationTransaction,
    *,
    backup: bool = True,
) -> None:
    """Persist with CAS without publishing runtime state yet."""
    write_receipt: Dict[str, Any] = {}
    try:
        saved = service.save_config(
            backup=backup,
            lock_acquired=True,
            expected_config_digest=transaction.source_digests["runtime_config"],
            write_receipt=write_receipt,
        )
    finally:
        transaction.record_write_receipt(write_receipt)
    if not saved:
        raise RuntimeError("Could not persist configuration")
    if "runtime_config" not in write_receipt:
        raise RuntimeError("Config persistence did not return a write receipt")


def _publish_runtime_config() -> None:
    """Publish only after config, metadata, and audit state are durable."""
    if not Parameters.reload_config(strict_dependents=True):
        raise RuntimeError("Strict runtime config reload failed")


def _assert_audit_source_unchanged(
    service: Any,
    transaction: ConfigMutationTransaction,
) -> None:
    current = service.get_source_state_digests()
    if current["audit_log"] != transaction.source_digests["audit_log"]:
        raise RuntimeError("Config audit log changed during mutation")


def _log_config_audit(
    service: Any,
    transaction: ConfigMutationTransaction,
    **entry: Any,
) -> None:
    """Persist one audit entry and record its exact rollback ownership."""
    write_receipt: Dict[str, Any] = {}
    expected_digest = transaction.owned_state.get(
        "audit_log",
        transaction.source_digests["audit_log"],
    )
    try:
        service.log_audit_entry(
            lock_acquired=True,
            expected_digest=expected_digest,
            write_receipt=write_receipt,
            **entry,
        )
    finally:
        transaction.record_write_receipt(write_receipt)
    if "audit_log" not in write_receipt:
        raise RuntimeError("Config audit persistence did not return a write receipt")


def _create_config_backup(
    service: Any,
    transaction: ConfigMutationTransaction,
) -> Optional[str]:
    """Create a backup while recording only the resulting inventory as owned."""
    write_receipt: Dict[str, Any] = {}
    try:
        return service.create_backup(
            lock_acquired=True,
            write_receipt=write_receipt,
        )
    finally:
        transaction.record_write_receipt(write_receipt)


def _persist_sync_meta(
    service: Any,
    transaction: ConfigMutationTransaction,
    meta: Dict[str, Any],
) -> None:
    """Persist config-sync metadata with CAS and rollback ownership."""
    write_receipt: Dict[str, Any] = {}
    try:
        saved = service.save_sync_meta(
            meta,
            lock_acquired=True,
            expected_digest=transaction.source_digests["sync_meta"],
            write_receipt=write_receipt,
        )
    finally:
        transaction.record_write_receipt(write_receipt)
    if not saved:
        raise RuntimeError("Failed to persist config migration metadata")
    if "sync_meta" not in write_receipt:
        raise RuntimeError("Config metadata persistence did not return a write receipt")


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
                "config": service.redact_value(config),
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
                "config": service.redact_value(config, [section]),
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
                "config": service.redact_value(config),
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
                "config": service.redact_value(config, [section]),
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
                "differences": [service.redact_diff_entry(diff) for diff in diffs],
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
                "differences": [service.redact_diff_entry(diff) for diff in diffs],
                "count": len(diffs),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error comparing configs: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@offload_blocking_route
def get_defaults_sync(handler: Any) -> JSONResponse:
    """Get sync information between current config and defaults."""
    try:
        service = handler._get_config_service()
        with service.mutation_guard():
            service.reload()
            report = build_defaults_sync_report(service)
        # This read route is side-effect free. Bootstrap/update tooling owns
        # defaults-baseline snapshots so a dashboard refresh cannot erase
        # upgrade history by initializing against already-updated defaults.
        report.update({"success": True, "timestamp": time.time()})
        return JSONResponse(content=report)
    except Exception as exc:
        handler.logger.error(f"Error getting defaults sync: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@offload_blocking_route
def plan_defaults_sync(
    handler: Any,
    body: ConfigSyncPlanRequest,
) -> JSONResponse:
    """Validate selected sync operations and return a dry-run plan."""
    try:
        service = handler._get_config_service()
        with service.mutation_guard():
            service.reload()
            plan = build_defaults_sync_plan(service, body.operations)
        return JSONResponse(
            content={
                "success": True,
                "contract_version": SYNC_CONTRACT_VERSION,
                "plan": _public_sync_plan(service, plan),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error planning defaults sync: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@guarded_config_mutation_route
def update_config_parameter(
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
        with _config_mutation_transaction(handler) as (service, transaction):
            old_value = copy.deepcopy(service.get_parameter(section, parameter))
            result = service.set_parameter(
                section,
                parameter,
                body.value,
                audit=False,
            )

            if not result.valid:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "validation": result.to_dict(),
                        "timestamp": time.time(),
                    },
                )

            _persist_config(service, transaction)
            _assert_audit_source_unchanged(service, transaction)
            _log_config_audit(
                service,
                transaction,
                action="update",
                section=section,
                parameter=parameter,
                old_value=old_value,
                new_value=body.value,
                source="api",
            )
            _publish_runtime_config()

        reload_tier = service.get_reload_tier(section, parameter)
        reload_message = service.get_reload_message(reload_tier)
        effective_applied = reload_tier == "immediate"
        if not effective_applied:
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
                "value": service.redact_value(body.value, [section, parameter]),
                "validation": result.to_dict(),
                "saved": True,
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


@guarded_config_mutation_route
def update_config_section(
    handler: Any,
    section: str,
    body: ConfigSectionUpdate,
) -> JSONResponse:
    """Update multiple parameters in a section."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited

    try:
        with _config_mutation_transaction(handler) as (service, transaction):
            old_values = {
                parameter: copy.deepcopy(service.get_parameter(section, parameter))
                for parameter in body.parameters
            }
            result = service.set_section(
                section,
                body.parameters,
                audit=False,
            )

            if not result.valid:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "validation": result.to_dict(),
                        "timestamp": time.time(),
                    },
                )

            _persist_config(service, transaction)
            _assert_audit_source_unchanged(service, transaction)
            for parameter, value in body.parameters.items():
                _log_config_audit(
                    service,
                    transaction,
                    action="update",
                    section=section,
                    parameter=parameter,
                    old_value=old_values[parameter],
                    new_value=value,
                    source="api",
                )
            _publish_runtime_config()

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
        effective_applied = max_tier == "immediate"
        if not effective_applied:
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
                "parameters": {
                    parameter: service.redact_value(value, [section, parameter])
                    for parameter, value in body.parameters.items()
                },
                "validation": result.to_dict(),
                "saved": True,
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
                "value": service.redact_value(value, [section, parameter]),
                "validation": result.to_dict(),
                "timestamp": time.time(),
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        handler.logger.error(f"Error validating config value: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@guarded_config_mutation_route
def apply_defaults_sync(
    handler: Any,
    body: ConfigSyncApplyRequest,
) -> JSONResponse:
    """Apply an explicitly confirmed, unchanged defaults-sync plan."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited

    def set_snapshot_value(snapshot: Dict[str, Any], path: List[str], value: Any) -> None:
        if len(path) == 1:
            snapshot[path[0]] = copy.deepcopy(value)
            return
        section = snapshot.setdefault(path[0], {})
        if not isinstance(section, dict):
            raise ValueError(f"Baseline shape conflict at {path[0]}")
        section[path[1]] = copy.deepcopy(value)

    def remove_snapshot_value(snapshot: Dict[str, Any], path: List[str]) -> None:
        if len(path) == 1:
            snapshot.pop(path[0], None)
            return
        section = snapshot.get(path[0])
        if isinstance(section, dict):
            section.pop(path[1], None)
            if not section:
                snapshot.pop(path[0], None)

    try:
        with _config_mutation_transaction(handler) as (service, transaction):
            plan = build_defaults_sync_plan(service, body.operations)
            public_plan_token = _config_sync_plan_token(plan)
            if not body.confirm:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "contract_version": SYNC_CONTRACT_VERSION,
                        "error": "Explicit confirmation is required",
                        "plan": _public_sync_plan(service, plan),
                        "timestamp": time.time(),
                    },
                )
            if not plan["valid"]:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "contract_version": SYNC_CONTRACT_VERSION,
                        "plan": _public_sync_plan(service, plan),
                        "timestamp": time.time(),
                    },
                )
            if not hmac.compare_digest(body.plan_digest, public_plan_token):
                return JSONResponse(
                    status_code=409,
                    content={
                        "success": False,
                        "contract_version": SYNC_CONTRACT_VERSION,
                        "error": "Config migration sources changed after preview",
                        "plan": _public_sync_plan(service, plan),
                        "timestamp": time.time(),
                    },
                )

            applied_ops: List[Dict[str, Any]] = []
            skipped_ops = [op for op in plan["operations"] if op["skip"]]
            applicable_ops = [op for op in plan["operations"] if not op["skip"]]
            if not applicable_ops:
                return JSONResponse(
                    content={
                        "success": True,
                        "contract_version": SYNC_CONTRACT_VERSION,
                        "applied_count": 0,
                        "skipped_count": len(skipped_ops),
                        "applied_operations": [],
                        "skipped_operations": [
                            _public_sync_operation(service, op) for op in skipped_ops
                        ],
                        "backup_id": None,
                        "runtime_reloaded": False,
                        "sync_metadata_persisted": False,
                        "plan_digest": public_plan_token,
                        "timestamp": time.time(),
                    }
                )

            if plan["source_state_digests"] != transaction.source_digests:
                raise RuntimeError("Config migration sources changed during apply")
            old_values = {
                tuple(op["path"]): copy.deepcopy(
                    service.get_path_value(op["path"], default=None)
                )
                for op in applicable_ops
            }

            backup_path = None
            if service.runtime_config_exists():
                backup_path = _create_config_backup(service, transaction)
                if backup_path is None:
                    raise RuntimeError("Could not create required config backup")

            for op in applicable_ops:
                path = list(op["path"])
                path_label = ".".join(path)
                if op["op_type"] in {"ADD_NEW", "ADOPT_DEFAULT"}:
                    result = service.set_path(
                        path,
                        op["target_value"],
                        validate=True,
                        audit=False,
                        source="config_sync",
                    )
                    if not result.valid:
                        raise ValueError(
                            f"Validation failed for {path_label}: {result.errors}"
                        )
                    if len(path) == 2:
                        op["reload_tier"] = service.get_reload_tier(path[0], path[1])
                    else:
                        op["reload_tier"] = "system_restart"
                elif op["op_type"] == "REMOVE_RETIRED":
                    if not service.remove_registered_retirement(path):
                        raise ValueError(
                            f"Failed to remove registered retirement {path_label}"
                        )
                    op["reload_tier"] = "immediate"
                applied_ops.append(op)

            _persist_config(service, transaction, backup=False)

            sync_meta = service.get_sync_meta()
            defaults_snapshot = sync_meta.get("defaults_snapshot")
            defaults_snapshot = (
                copy.deepcopy(defaults_snapshot)
                if isinstance(defaults_snapshot, dict)
                else {}
            )
            current_defaults = service.get_effective_defaults()

            for op in applied_ops:
                path = list(op["path"])
                if op["op_type"] in {"ADD_NEW", "ADOPT_DEFAULT"}:
                    default_value = current_defaults
                    for part in path:
                        if not isinstance(default_value, dict) or part not in default_value:
                            raise ValueError(
                                f"Default disappeared while applying {'.'.join(path)}"
                            )
                        default_value = default_value[part]
                    set_snapshot_value(defaults_snapshot, path, default_value)
                else:
                    remove_snapshot_value(defaults_snapshot, path)

            applied_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            sync_meta["defaults_snapshot"] = defaults_snapshot
            sync_meta["defaults_snapshot_saved_at"] = applied_at
            sync_meta["schema_version"] = service.get_schema_version()
            sync_meta["defaults_snapshot_mode"] = (
                "full" if defaults_snapshot == current_defaults else "incremental"
            )
            if sync_meta["defaults_snapshot_mode"] == "full":
                sync_meta["defaults_snapshot_provenance"] = "config_sync_apply_full"
                sync_meta["defaults_snapshot_source_digest"] = transaction.source_digests[
                    "defaults"
                ]
            else:
                sync_meta["defaults_snapshot_provenance"] = (
                    "config_sync_apply_incremental"
                )
                sync_meta.pop("defaults_snapshot_source_digest", None)
            applied_retirements = sync_meta.get("applied_retirements", {})
            if not isinstance(applied_retirements, dict):
                raise ValueError("applied_retirements metadata must be an object")
            for op in applied_ops:
                retirement_id = op.get("retirement_id")
                if retirement_id:
                    applied_retirements[retirement_id] = {
                        "applied_at": applied_at,
                        "registry_version": plan["retirement_registry_version"],
                    }
            sync_meta["applied_retirements"] = applied_retirements
            _persist_sync_meta(service, transaction, sync_meta)

            _assert_audit_source_unchanged(service, transaction)
            for op in applied_ops:
                path = list(op["path"])
                _log_config_audit(
                    service,
                    transaction,
                    action=f"config_sync_{op['op_type'].lower()}",
                    section=path[0],
                    parameter=path[1] if len(path) == 2 else None,
                    old_value=old_values[tuple(path)],
                    new_value=service.get_path_value(path, default=None),
                    source="config_sync",
                )
            _publish_runtime_config()

            backup_id = Path(backup_path).stem if backup_path else None
            return JSONResponse(
                content={
                    "success": True,
                    "contract_version": SYNC_CONTRACT_VERSION,
                    "applied_count": len(applied_ops),
                    "skipped_count": len(skipped_ops),
                    "applied_operations": [
                        _public_sync_operation(service, op) for op in applied_ops
                    ],
                    "skipped_operations": [
                        _public_sync_operation(service, op) for op in skipped_ops
                    ],
                    "backup_id": backup_id,
                    "runtime_reloaded": True,
                    "sync_metadata_persisted": True,
                    "plan_digest": public_plan_token,
                    "timestamp": time.time(),
                }
            )
    except ConfigMutationRollbackError as exc:
        handler.logger.error("Error applying defaults sync: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Config migration failed; rollback requires operator recovery",
        ) from exc
    except Exception as exc:
        handler.logger.error("Error applying defaults sync: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Config migration failed and was rolled back",
        ) from exc


@guarded_config_mutation_route
def revert_config_to_default(handler: Any) -> JSONResponse:
    """Revert all configuration to defaults."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited
    try:
        with _config_mutation_transaction(handler) as (service, transaction):
            success = service.revert_to_default()
            if success:
                _persist_config(service, transaction)
                _assert_audit_source_unchanged(service, transaction)
                _log_config_audit(
                    service,
                    transaction,
                    action="revert_all",
                    section="*",
                    old_value=None,
                    new_value=None,
                    source="api",
                )
                _publish_runtime_config()

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


@guarded_config_mutation_route
def revert_section_to_default(handler: Any, section: str) -> JSONResponse:
    """Revert a section to defaults."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited
    try:
        with _config_mutation_transaction(handler) as (service, transaction):
            success = service.revert_to_default(section=section)
            if success:
                _persist_config(service, transaction)
                _assert_audit_source_unchanged(service, transaction)
                _log_config_audit(
                    service,
                    transaction,
                    action="revert_section",
                    section=section,
                    old_value=None,
                    new_value=None,
                    source="api",
                )
                _publish_runtime_config()

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


@guarded_config_mutation_route
def revert_parameter_to_default(
    handler: Any,
    section: str,
    parameter: str,
) -> JSONResponse:
    """Revert a single parameter to default."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited
    try:
        with _config_mutation_transaction(handler) as (service, transaction):
            old_value = copy.deepcopy(service.get_parameter(section, parameter))
            success = service.revert_to_default(section=section, param=parameter)
            default_value = service.get_default_parameter(section, parameter)
            if success:
                _persist_config(service, transaction)
                _assert_audit_source_unchanged(service, transaction)
                _log_config_audit(
                    service,
                    transaction,
                    action="revert",
                    section=section,
                    parameter=parameter,
                    old_value=old_value,
                    new_value=default_value,
                    source="api",
                )
                _publish_runtime_config()

        return JSONResponse(
            content={
                "success": success,
                "section": section,
                "parameter": parameter,
                "default_value": service.redact_value(
                    default_value,
                    [section, parameter],
                ),
                "message": "Parameter reverted to default" if success else "Failed to revert",
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error reverting parameter: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@guarded_config_mutation_route
def restore_config_backup(handler: Any, backup_id: str) -> JSONResponse:
    """Restore configuration from a backup."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited
    try:
        with _config_mutation_transaction(handler) as (service, transaction):
            write_receipt: Dict[str, Any] = {}
            try:
                success = service.restore_backup(
                    backup_id,
                    lock_acquired=True,
                    expected_config_digest=transaction.source_digests["runtime_config"],
                    write_receipt=write_receipt,
                )
            finally:
                transaction.record_write_receipt(write_receipt)
            if not success:
                raise RuntimeError("Could not restore config backup")
            if "runtime_config" not in write_receipt:
                raise RuntimeError("Backup restore did not return a write receipt")
            _assert_audit_source_unchanged(service, transaction)
            _log_config_audit(
                service,
                transaction,
                action="restore",
                section="*",
                old_value=None,
                new_value=None,
                source="restore",
            )
            _publish_runtime_config()

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


@guarded_config_mutation_route
def import_config(handler: Any, body: ConfigImportRequest) -> JSONResponse:
    """Import configuration."""
    rate_limited = _config_write_rate_limit_response(handler)
    if rate_limited is not None:
        return rate_limited

    try:
        with _config_mutation_transaction(handler) as (service, transaction):
            success, diffs = service.import_config(body.data, body.merge_mode)
            if success:
                _persist_config(service, transaction)
                _assert_audit_source_unchanged(service, transaction)
                _log_config_audit(
                    service,
                    transaction,
                    action="import",
                    section="*",
                    old_value=None,
                    new_value=None,
                    source="import",
                )
                _publish_runtime_config()

        return JSONResponse(
            content={
                "success": success,
                "merge_mode": body.merge_mode,
                "changes": [service.redact_diff_entry(diff) for diff in diffs],
                "changes_count": len(diffs),
                "timestamp": time.time(),
            }
        )
    except Exception as exc:
        handler.logger.error(f"Error importing config: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@offload_blocking_route
def get_config_backup_history(handler: Any, request: Request) -> JSONResponse:
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
                "config": service.redact_value(exported),
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
