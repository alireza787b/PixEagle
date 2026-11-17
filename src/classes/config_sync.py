"""Versioned config defaults-sync contracts and migration planning."""

from __future__ import annotations

import copy
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
    path: List[str] = Field(min_length=1, max_length=16)
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


def _leaf_values(mapping: Dict[str, Any], path: Optional[List[str]] = None):
    """Enumerate exact mapping leaves; arrays and empty mappings stay atomic."""
    for key, value in mapping.items():
        child_path = [*(path or []), key]
        if isinstance(value, dict) and value:
            yield from _leaf_values(value, child_path)
        else:
            yield child_path, value


def build_defaults_sync_report(service: ConfigService) -> Dict[str, Any]:
    """Build a redacted path-based defaults and retirement report."""
    current_config = service.get_sync_config()
    default_config = service.get_effective_defaults()
    sync_meta = service.get_sync_meta()
    defaults_snapshot = sync_meta.get("defaults_snapshot", {})
    baseline_available = isinstance(defaults_snapshot, dict) and bool(defaults_snapshot)

    new_parameters = []
    changed_defaults = []
    registered_retirements = []
    unknown_extensions = []
    registry = service.get_retirement_registry()
    guidance_migration = service.get_gimbal_guidance_migration()
    retirements_by_path = {
        tuple(retirement["path"]): retirement
        for retirement in registry["retirements"]
    }

    for path, new_default in sorted(
        _leaf_values(default_config), key=lambda item: tuple(item[0])
    ):
        param_schema = service.get_path_schema(path)
        public_new_default = service.redact_value(new_default, path)
        sensitive = (
            service.is_sensitive_path(path)
            or public_new_default != new_default
        )
        current_value = ConfigService._get_mapping_path(current_config, path, _MISSING)
        if current_value is _MISSING:
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

        old_default = ConfigService._get_mapping_path(defaults_snapshot, path, _MISSING)
        if baseline_available and old_default is not _MISSING and old_default != new_default:
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

    for retirement in registry["retirements"]:
        path = retirement["path"]
        if ConfigService._mapping_path_exists(current_config, path):
            migration = (guidance_migration if guidance_migration is not None
                         and guidance_migration["path"] == path else None)
            registered_retirements.append(
                {
                    **_display_path(path),
                    **({"migration": migration} if migration is not None else {}),
                    "id": retirement["id"],
                    "retired_in_schema_version": retirement["retired_in_schema_version"],
                    "reason": retirement["reason"],
                    "replacement": retirement["replacement"],
                }
            )

    for path, value in _leaf_values(current_config):
        if any(tuple(path[:len(retired)]) == retired for retired in retirements_by_path):
            continue
        if (
            not ConfigService._mapping_path_exists(default_config, path)
            and not service.get_path_schema(path)
        ):
            unknown_extensions.append({"path": list(path), "value_type": _value_type(value)})

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
    current_config = service.get_sync_config()
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
    candidate = copy.deepcopy(current_config)

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
        if any(
            operation_path[:len(seen)] == seen or seen[:len(operation_path)] == operation_path
            for seen in seen_paths
        ):
            errors.append({"index": idx, "error": f"Overlapping operation for {path_label}"})
            continue
        seen_paths.add(operation_path)

        explicit_value = "value" in op.model_fields_set
        if op_type != "ADD_NEW" and op.value is not None:
            errors.append(
                {
                    "index": idx,
                    "error": f"{op_type} does not accept an explicit value",
                }
            )
            continue

        has_current = ConfigService._mapping_path_exists(current_config, path)
        default_value = ConfigService._get_mapping_path(default_config, path, _MISSING)
        is_known_param = default_value is not _MISSING or bool(service.get_path_schema(path))

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
                if not explicit_value and default_value is _MISSING:
                    errors.append(
                        {
                            "index": idx,
                            "error": f"No default value found for {path_label}",
                        }
                    )
                    continue
                normalized["target_value"] = op.value if explicit_value else default_value

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
            try:
                ConfigService._set_mapping_path(candidate, path, normalized["target_value"])
            except ValueError as exc:
                errors.append({"index": idx, "error": str(exc)})
                continue

        if op_type == "REMOVE_RETIRED" and not normalized["skip"]:
            ConfigService._remove_mapping_path(candidate, path)
        plan_operations.append(normalized)

    guidance_migration = None
    try:
        from classes.gimbal_guidance_config_migration import canonical_guidance_restrictions
        canonical_guidance_restrictions(candidate)
        guidance_migration = service.get_gimbal_guidance_migration(candidate=candidate)
        if guidance_migration is not None:
            from classes.gimbal_guidance_config_migration import LEGACY_PATH, ALLOWED_PATH, LIMITS_PATH
            related = any(op["path"][:2] == LEGACY_PATH[:2] for op in plan_operations)
            if related:
                before = guidance_migration["effective_before"]
                after = guidance_migration["effective_after"]
                warnings.append({"warning": (
                    f"Gimbal guidance: before ({before['origin']}) special manoeuvres "
                    f"{before['special_manoeuvres']}, observed-ray windows {before['observation_limits']}; "
                    f"after special manoeuvres {after['special_manoeuvres']}, "
                    f"observed-ray windows {after['observation_limits']}. "
                    "Camera mechanics, target-centre alignment and exposure timing remain unqualified."
                )})
            if guidance_migration["review_required"] and guidance_migration["legacy_removed_in_candidate"]:
                explicit = guidance_migration["canonical_choices_present"]
                for choice in (ALLOWED_PATH, LIMITS_PATH):
                    if not ConfigService._mapping_path_exists(current_config, choice):
                        explicit = explicit and any(
                            op.path == choice and op.op_type == "ADD_NEW" and "value" in op.model_fields_set
                            for op in operations)
                if not explicit:
                    errors.append({"error": "Custom gimbal retirement requires explicit ALLOWED_MANOEUVRES and complete OBSERVATION_LIMITS choices."})
                errors.extend({"error": error} for error in guidance_migration["restriction_errors"])
                if guidance_migration["recommendation_error"]:
                    errors.append({"error": guidance_migration["recommendation_error"]})
    except (TypeError, ValueError) as exc:
        errors.append({"error": f"Gimbal guidance migration cannot be previewed: {exc}"})

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
        "gimbal_guidance_migration": guidance_migration,
    }
    return {
        "contract_version": SYNC_CONTRACT_VERSION,
        "valid": len(errors) == 0,
        "gimbal_guidance_migration": guidance_migration,
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
