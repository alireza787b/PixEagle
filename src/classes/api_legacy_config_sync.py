"""Legacy config defaults-sync helpers used by FastAPI compatibility routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from classes.config_service import ConfigService


class ConfigSyncOperation(BaseModel):
    """Single operation for config defaults sync migration."""

    op_type: str  # ADD_NEW | ADOPT_DEFAULT | ARCHIVE_REMOVE
    section: str
    parameter: str
    value: Optional[Any] = None


class ConfigSyncPlanRequest(BaseModel):
    """Batch operations for sync preview/apply."""

    operations: List[ConfigSyncOperation]


def build_defaults_sync_report(service: ConfigService) -> Dict[str, Any]:
    """Build defaults-sync report with new, changed, and obsolete parameters.

    Uses the union of schema sections and config_default.yaml sections as the
    source of truth, so sections/parameters not yet in the schema but present in
    defaults are never falsely flagged as obsolete.
    """
    schema = service.get_schema()
    current_config = service.get_config()
    default_config = service.get_default()
    sync_meta = service.get_sync_meta()
    defaults_snapshot = sync_meta.get("defaults_snapshot", {})
    baseline_available = isinstance(defaults_snapshot, dict) and bool(defaults_snapshot)

    new_parameters = []
    changed_defaults = []
    removed_parameters = []

    schema_sections = schema.get("sections", {})

    all_section_names = set(schema_sections.keys()) | {
        k for k, v in default_config.items() if isinstance(v, dict)
    }

    for section_name in sorted(all_section_names):
        section_schema = schema_sections.get(section_name, {})
        schema_params = (
            section_schema.get("parameters", {})
            if isinstance(section_schema, dict)
            else {}
        )
        current_section = current_config.get(section_name, {})
        default_section = default_config.get(section_name, {})
        snapshot_section = (
            defaults_snapshot.get(section_name, {}) if baseline_available else {}
        )

        if not isinstance(current_section, dict):
            current_section = {}
        if not isinstance(default_section, dict):
            default_section = {}
        if not isinstance(snapshot_section, dict):
            snapshot_section = {}

        all_param_names = set(schema_params.keys()) | set(default_section.keys())

        for param_name in sorted(all_param_names):
            param_schema = schema_params.get(param_name, {})
            schema_default = param_schema.get("default")
            new_default = default_section.get(param_name, schema_default)
            has_current = param_name in current_section

            if not has_current and param_name in default_section:
                new_parameters.append(
                    {
                        "section": section_name,
                        "parameter": param_name,
                        "default_value": new_default,
                        "description": param_schema.get("description", ""),
                        "type": param_schema.get("type", "string"),
                    }
                )
                continue

            if baseline_available and has_current and param_name in snapshot_section:
                old_default = snapshot_section.get(param_name)
                if old_default != new_default:
                    user_value = current_section.get(param_name)
                    changed_defaults.append(
                        {
                            "section": section_name,
                            "parameter": param_name,
                            "old_default": old_default,
                            "new_default": new_default,
                            "user_value": user_value,
                            "description": param_schema.get("description", ""),
                            "type": param_schema.get("type", "string"),
                            "matches_new_default": user_value == new_default,
                            "impact_level": "warning",
                        }
                    )

        for param_name, current_value in current_section.items():
            if param_name not in default_section and param_name not in schema_params:
                removed_parameters.append(
                    {
                        "section": section_name,
                        "parameter": param_name,
                        "current_value": current_value,
                    }
                )

    for section_name, current_section in current_config.items():
        if section_name in all_section_names or section_name == service.SYNC_ARCHIVE_SECTION:
            continue
        if not isinstance(current_section, dict):
            continue
        for param_name, current_value in current_section.items():
            removed_parameters.append(
                {
                    "section": section_name,
                    "parameter": param_name,
                    "current_value": current_value,
                }
            )

    return {
        "new_parameters": new_parameters,
        "changed_defaults": changed_defaults,
        "removed_parameters": removed_parameters,
        "counts": {
            "new": len(new_parameters),
            "changed": len(changed_defaults),
            "removed": len(removed_parameters),
            "total": len(new_parameters) + len(changed_defaults) + len(removed_parameters),
        },
        "baseline_available": baseline_available,
        "baseline_saved_at": sync_meta.get("defaults_snapshot_saved_at"),
        "schema_version": service.get_schema_version(),
    }


def build_defaults_sync_plan(
    service: ConfigService,
    operations: List[ConfigSyncOperation],
) -> Dict[str, Any]:
    """Validate and normalize defaults-sync operations."""
    schema_sections = service.get_schema().get("sections", {})
    current_config = service.get_config()
    default_config = service.get_default()

    valid_types = {"ADD_NEW", "ADOPT_DEFAULT", "ARCHIVE_REMOVE"}
    plan_operations: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for idx, op in enumerate(operations):
        op_type = str(op.op_type or "").upper().strip()
        section = op.section
        parameter = op.parameter

        if op_type not in valid_types:
            errors.append({"index": idx, "error": f"Unsupported op_type '{op.op_type}'"})
            continue

        section_schema = schema_sections.get(section, {})
        section_params = (
            section_schema.get("parameters", {})
            if isinstance(section_schema, dict)
            else {}
        )

        current_section = current_config.get(section, {})
        if not isinstance(current_section, dict):
            current_section = {}

        default_section = default_config.get(section, {})
        if not isinstance(default_section, dict):
            default_section = {}

        is_known_param = parameter in section_params or parameter in default_section

        current_value = current_section.get(parameter)
        default_value = default_section.get(parameter)

        normalized = {
            "op_type": op_type,
            "section": section,
            "parameter": parameter,
            "current_value": current_value,
            "target_value": op.value,
            "skip": False,
        }

        if op_type in {"ADD_NEW", "ADOPT_DEFAULT"} and not is_known_param:
            errors.append(
                {
                    "index": idx,
                    "error": f"{section}.{parameter} is not in schema or defaults",
                }
            )
            continue

        if op_type == "ADD_NEW":
            if parameter in current_section:
                normalized["skip"] = True
                warnings.append(
                    {
                        "index": idx,
                        "warning": f"{section}.{parameter} already exists; skipping ADD_NEW",
                    }
                )
            else:
                normalized["target_value"] = default_value if op.value is None else op.value

        elif op_type == "ADOPT_DEFAULT":
            if parameter not in default_section:
                errors.append(
                    {
                        "index": idx,
                        "error": f"No default value found for {section}.{parameter}",
                    }
                )
                continue
            normalized["target_value"] = default_value

        elif op_type == "ARCHIVE_REMOVE":
            if parameter not in current_section:
                normalized["skip"] = True
                warnings.append(
                    {
                        "index": idx,
                        "warning": f"{section}.{parameter} missing in current config; skipping ARCHIVE_REMOVE",
                    }
                )

        plan_operations.append(normalized)

    changed_count = sum(1 for op in plan_operations if not op["skip"])
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "operations": plan_operations,
        "summary": {
            "requested": len(operations),
            "applicable": changed_count,
            "skipped": len(plan_operations) - changed_count,
        },
    }
