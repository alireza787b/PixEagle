"""Versioned config defaults-sync contracts and migration planning."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from classes.config_service import ConfigService


_MISSING = object()
SYNC_CONTRACT_VERSION = 2


class ConfigSyncOperation(BaseModel):
    """Single operation for config defaults sync migration."""

    model_config = ConfigDict(extra="forbid")

    op_type: Literal["ADD_NEW", "ADOPT_DEFAULT", "REMOVE_RETIRED"]
    path: List[str] = Field(min_length=1, max_length=2)
    value: Optional[Any] = None

    @field_validator("path")
    @classmethod
    def validate_path_parts(cls, path: List[str]) -> List[str]:
        if not all(isinstance(part, str) and part.strip() == part and part for part in path):
            raise ValueError("path components must be non-empty strings without outer whitespace")
        return path


class ConfigSyncPlanRequest(BaseModel):
    """Batch operations for sync preview/apply."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal[SYNC_CONTRACT_VERSION]
    operations: List[ConfigSyncOperation]


class ConfigSyncApplyRequest(ConfigSyncPlanRequest):
    """Confirmed application of an unchanged dry-run plan."""

    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm: bool = False


def _digest(value: Any) -> str:
    """Return a stable digest without exposing config values in API responses."""
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _value_type(value: Any) -> str:
    """Return a non-sensitive type label for unmanaged extension reporting."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def _display_path(path: List[str]) -> Dict[str, Any]:
    """Serialize the sole v2 path representation."""
    return {"path": list(path)}


def build_defaults_sync_report(service: ConfigService) -> Dict[str, Any]:
    """Build a redacted path-based defaults and retirement report."""
    schema = service.get_schema()
    current_config = service.get_config()
    default_config = service.get_effective_defaults()
    sync_meta = service.get_sync_meta()
    defaults_snapshot = sync_meta.get("defaults_snapshot", {})
    baseline_available = isinstance(defaults_snapshot, dict) and bool(defaults_snapshot)

    new_parameters = []
    changed_defaults = []
    registered_retirements = []
    unknown_extensions = []
    registry = service.get_retirement_registry()
    retirements_by_path = {
        tuple(retirement["path"]): retirement
        for retirement in registry["retirements"]
    }

    schema_sections = schema.get("sections", {})

    def schema_for(path: List[str]) -> Dict[str, Any]:
        root_schema = schema_sections.get(path[0], {})
        if len(path) == 1:
            return root_schema if isinstance(root_schema, dict) else {}
        parameters = (
            root_schema.get("parameters", {}) if isinstance(root_schema, dict) else {}
        )
        value = parameters.get(path[1], {})
        return value if isinstance(value, dict) else {}

    def current_lookup(path: List[str]) -> tuple[bool, Any]:
        if len(path) == 1:
            return path[0] in current_config, current_config.get(path[0])
        section = current_config.get(path[0])
        return (
            isinstance(section, dict) and path[1] in section,
            section.get(path[1]) if isinstance(section, dict) else None,
        )

    def snapshot_lookup(path: List[str]) -> tuple[bool, Any]:
        if len(path) == 1:
            return path[0] in defaults_snapshot, defaults_snapshot.get(path[0])
        section = defaults_snapshot.get(path[0])
        return (
            isinstance(section, dict) and path[1] in section,
            section.get(path[1]) if isinstance(section, dict) else None,
        )

    active_paths: List[tuple[List[str], Any]] = []
    for root_key, root_default in default_config.items():
        if isinstance(root_default, dict):
            active_paths.extend(
                ([root_key, parameter], default_value)
                for parameter, default_value in root_default.items()
            )
        else:
            active_paths.append(([root_key], root_default))

    for path, new_default in sorted(active_paths, key=lambda item: tuple(item[0])):
        param_schema = schema_for(path)
        public_new_default = service.redact_value(new_default, path)
        sensitive = (
            service.is_sensitive_path(path)
            or public_new_default != new_default
        )
        has_current, current_value = current_lookup(path)
        if not has_current:
            new_parameters.append(
                {
                    **_display_path(path),
                    "default_value": public_new_default,
                    "sensitive": sensitive,
                    "description": param_schema.get("description", ""),
                    "type": param_schema.get("type", _value_type(new_default)),
                }
            )
            continue

        has_snapshot, old_default = snapshot_lookup(path)
        if baseline_available and has_snapshot and old_default != new_default:
            changed_defaults.append(
                {
                    **_display_path(path),
                    "old_default": service.redact_value(old_default, path),
                    "new_default": public_new_default,
                    "sensitive": sensitive,
                    "description": param_schema.get("description", ""),
                    "type": param_schema.get("type", _value_type(new_default)),
                    "matches_old_default": current_value == old_default,
                    "matches_new_default": current_value == new_default,
                    "impact_level": "warning",
                }
            )

    active_path_keys = {tuple(path) for path, _ in active_paths}

    def record_inactive(path: List[str], value: Any) -> None:
        retirement = retirements_by_path.get(tuple(path))
        if retirement:
            registered_retirements.append(
                {
                    **_display_path(path),
                    "id": retirement["id"],
                    "retired_in_schema_version": retirement["retired_in_schema_version"],
                    "reason": retirement["reason"],
                    "replacement": retirement["replacement"],
                }
            )
        else:
            unknown_extensions.append(
                {"path": list(path), "value_type": _value_type(value)}
            )

    for root_key, current_value in current_config.items():
        root_path = [root_key]
        if isinstance(current_value, dict):
            if tuple(root_path) not in active_path_keys and tuple(root_path) in retirements_by_path:
                record_inactive(root_path, current_value)
                continue
            for parameter, nested_value in current_value.items():
                path = [root_key, parameter]
                if tuple(path) not in active_path_keys:
                    record_inactive(path, nested_value)
        elif tuple(root_path) not in active_path_keys:
            record_inactive(root_path, current_value)

    return {
        "contract_version": SYNC_CONTRACT_VERSION,
        "new_parameters": new_parameters,
        "changed_defaults": changed_defaults,
        "registered_retirements": registered_retirements,
        "unknown_extensions": unknown_extensions,
        "counts": {
            "new": len(new_parameters),
            "changed": len(changed_defaults),
            "retired": len(registered_retirements),
            "extensions": len(unknown_extensions),
            "actionable": (
                len(new_parameters)
                + len(changed_defaults)
                + len(registered_retirements)
            ),
        },
        "baseline_available": baseline_available,
        "baseline_saved_at": sync_meta.get("defaults_snapshot_saved_at"),
        "schema_version": service.get_schema_version(),
        "retirement_registry_version": registry["registry_version"],
        "retirement_registry_digest": registry["registry_digest"],
    }


def build_defaults_sync_plan(
    service: ConfigService,
    operations: List[ConfigSyncOperation],
) -> Dict[str, Any]:
    """Validate and normalize defaults-sync operations."""
    schema = service.get_schema()
    current_config = service.get_config()
    default_config = service.get_effective_defaults()
    registry = service.get_retirement_registry()
    retirements_by_path = {
        tuple(retirement["path"]): retirement
        for retirement in registry["retirements"]
    }

    plan_operations: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    seen_paths = set()

    for idx, op in enumerate(operations):
        op_type = op.op_type
        path = list(op.path)
        path_label = ".".join(path)

        operation_path = tuple(path)
        if operation_path in seen_paths:
            errors.append(
                {
                    "index": idx,
                    "error": f"Duplicate operation for {path_label}",
                }
            )
            continue
        seen_paths.add(operation_path)

        if op_type != "ADD_NEW" and op.value is not None:
            errors.append(
                {
                    "index": idx,
                    "error": f"{op_type} does not accept an explicit value",
                }
            )
            continue

        if len(path) == 1:
            has_current = path[0] in current_config
            default_value = default_config.get(path[0], _MISSING)
        else:
            current_section = current_config.get(path[0], {})
            default_section = default_config.get(path[0], {})
            has_current = isinstance(current_section, dict) and path[1] in current_section
            default_value = (
                default_section.get(path[1], _MISSING)
                if isinstance(default_section, dict)
                else _MISSING
            )
        is_known_param = default_value is not _MISSING

        normalized = {
            "op_type": op_type,
            **_display_path(path),
            "target_value": op.value,
            "skip": False,
        }

        if op_type in {"ADD_NEW", "ADOPT_DEFAULT"} and not is_known_param:
            errors.append(
                {
                    "index": idx,
                    "error": f"{path_label} is not in schema or defaults",
                }
            )
            continue

        if op_type == "ADD_NEW":
            if has_current:
                normalized["skip"] = True
                warnings.append(
                    {
                        "index": idx,
                        "warning": f"{path_label} already exists; skipping ADD_NEW",
                    }
                )
            else:
                if op.value is None and default_value is _MISSING:
                    errors.append(
                        {
                            "index": idx,
                            "error": f"No default value found for {path_label}",
                        }
                    )
                    continue
                normalized["target_value"] = default_value if op.value is None else op.value

        elif op_type == "ADOPT_DEFAULT":
            if default_value is _MISSING:
                errors.append(
                    {
                        "index": idx,
                        "error": f"No default value found for {path_label}",
                    }
                )
                continue
            normalized["target_value"] = default_value

        elif op_type == "REMOVE_RETIRED":
            retirement = retirements_by_path.get(tuple(path))
            if retirement is None:
                errors.append(
                    {
                        "index": idx,
                        "error": (
                            f"{path_label} is not authorized by the "
                            "config retirement registry"
                        ),
                    }
                )
                continue
            normalized["retirement_id"] = retirement["id"]
            normalized["target_value"] = None
            if not has_current:
                normalized["skip"] = True
                warnings.append(
                    {
                        "index": idx,
                        "warning": (
                            f"{path_label} missing in current config; "
                            "skipping REMOVE_RETIRED"
                        ),
                    }
                )

        if op_type in {"ADD_NEW", "ADOPT_DEFAULT"} and not normalized["skip"]:
            validation = service.validate_path(path, normalized["target_value"])
            if not validation.valid:
                errors.append(
                    {
                        "index": idx,
                        "error": (
                            f"Validation failed for {path_label}: "
                            f"{validation.errors}"
                        ),
                    }
                )
                continue

        plan_operations.append(normalized)

    changed_count = sum(1 for op in plan_operations if not op["skip"])
    config_digest = _digest(current_config)
    defaults_digest = _digest(default_config)
    schema_digest = _digest(schema)
    source_state_digests = service.get_source_state_digests()
    digest_payload = {
        "contract_version": SYNC_CONTRACT_VERSION,
        "operations": plan_operations,
        "config_digest": config_digest,
        "defaults_digest": defaults_digest,
        "schema_digest": schema_digest,
        "registry_digest": registry["registry_digest"],
        "schema_version": service.get_schema_version(),
        "source_state_digests": source_state_digests,
    }
    return {
        "contract_version": SYNC_CONTRACT_VERSION,
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "operations": plan_operations,
        "summary": {
            "requested": len(operations),
            "applicable": changed_count,
            "skipped": len(plan_operations) - changed_count,
        },
        "config_digest": config_digest,
        "defaults_digest": defaults_digest,
        "schema_digest": schema_digest,
        "retirement_registry_version": registry["registry_version"],
        "retirement_registry_digest": registry["registry_digest"],
        "source_state_digests": source_state_digests,
        "plan_digest": _digest(digest_payload),
    }
