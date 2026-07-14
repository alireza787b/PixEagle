"""Tests for legacy config defaults-sync helper extraction."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from classes.config_sync import (
    ConfigSyncOperation,
    ConfigSyncPlanRequest,
    build_defaults_sync_plan,
    build_defaults_sync_report,
)


pytestmark = [pytest.mark.unit]


class FakeConfigService:
    def __init__(self) -> None:
        self.schema = {
            "sections": {
                "VideoSource": {
                    "parameters": {
                        "VIDEO_SOURCE_TYPE": {
                            "default": "usb",
                            "description": "Source type",
                            "type": "string",
                        },
                        "WIDTH": {
                            "default": 640,
                            "description": "Width",
                            "type": "integer",
                        },
                    }
                }
            }
        }
        self.current = {
            "VideoSource": {
                "VIDEO_SOURCE_TYPE": "csi",
                "OBSOLETE_LOCAL": "remove-me",
            },
            "UnknownSection": {
                "UNKNOWN_PARAM": "archive-me",
            },
        }
        self.defaults = {
            "VideoSource": {
                "VIDEO_SOURCE_TYPE": "usb",
                "WIDTH": 640,
                "DEFAULT_ONLY": True,
            },
            "NewDefaultSection": {
                "ENABLED": False,
            },
        }
        self.sync_meta = {
            "defaults_snapshot": {
                "VideoSource": {
                    "VIDEO_SOURCE_TYPE": "old-usb",
                }
            },
            "defaults_snapshot_saved_at": "2026-06-01T00:00:00Z",
        }

    def get_schema(self):
        return self.schema

    def get_config(self):
        return self.current

    def get_default(self):
        return self.defaults

    def get_effective_defaults(self):
        return self.defaults

    def get_sync_meta(self):
        return self.sync_meta

    def get_schema_version(self):
        return "test-schema"

    def validate_value(self, section, parameter, value):
        valid = not (parameter == "WIDTH" and not isinstance(value, int))
        return SimpleNamespace(
            valid=valid,
            errors=[] if valid else ["Expected integer"],
        )

    def validate_path(self, path, value):
        if len(path) == 1:
            return SimpleNamespace(valid=True, errors=[])
        return self.validate_value(path[0], path[1], value)

    def is_sensitive_path(self, path):
        return path[-1] == "SECRET_TOKEN"

    def redact_value(self, value, path=()):
        if path and self.is_sensitive_path(path):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {
                key: self.redact_value(item, [*path, key])
                for key, item in value.items()
            }
        return value

    def get_source_state_digests(self):
        return {
            "runtime_config": "1" * 64,
            "defaults": "2" * 64,
            "schema": "3" * 64,
            "retirements": "4" * 64,
            "sync_meta": "5" * 64,
            "audit_log": "6" * 64,
        }

    def get_retirement_registry(self):
        return {
            "registry_version": 7,
            "registry_digest": "a" * 64,
            "retirements": [
                {
                    "id": "retire-obsolete-local",
                    "path": ["VideoSource", "OBSOLETE_LOCAL"],
                    "action": "remove",
                    "retired_in_schema_version": "test-schema",
                    "reason": "Test retirement",
                    "replacement": None,
                },
                {
                    "id": "retire-missing-local",
                    "path": ["VideoSource", "MISSING_LOCAL"],
                    "action": "remove",
                    "retired_in_schema_version": "test-schema",
                    "reason": "Test missing retirement",
                    "replacement": None,
                },
            ],
        }


def test_build_defaults_sync_report_uses_schema_and_defaults_union():
    report = build_defaults_sync_report(FakeConfigService())

    assert report["contract_version"] == 2
    assert "removed_parameters" not in report
    assert report["baseline_available"] is True
    assert report["baseline_saved_at"] == "2026-06-01T00:00:00Z"
    assert report["schema_version"] == "test-schema"

    new_params = {tuple(item["path"]) for item in report["new_parameters"]}
    retired_params = {
        tuple(item["path"])
        for item in report["registered_retirements"]
    }
    changed_params = {
        tuple(item["path"]) for item in report["changed_defaults"]
    }

    assert ("VideoSource", "WIDTH") in new_params
    assert ("VideoSource", "DEFAULT_ONLY") in new_params
    assert ("NewDefaultSection", "ENABLED") in new_params
    assert ("VideoSource", "OBSOLETE_LOCAL") in retired_params
    assert report["unknown_extensions"] == [
        {"path": ["UnknownSection", "UNKNOWN_PARAM"], "value_type": "string"}
    ]
    assert "archive-me" not in str(report)
    assert ("VideoSource", "VIDEO_SOURCE_TYPE") in changed_params
    assert report["retirement_registry_version"] == 7
    assert "total" not in report["counts"]
    assert "removed" not in report["counts"]


def test_build_defaults_sync_plan_normalizes_supported_operations():
    service = FakeConfigService()
    operations = [
        ConfigSyncOperation(
            op_type="ADD_NEW",
            path=["VideoSource", "WIDTH"],
        ),
        ConfigSyncOperation(
            op_type="ADOPT_DEFAULT",
            path=["VideoSource", "VIDEO_SOURCE_TYPE"],
        ),
        ConfigSyncOperation(
            op_type="REMOVE_RETIRED",
            path=["VideoSource", "OBSOLETE_LOCAL"],
        ),
    ]

    plan = build_defaults_sync_plan(service, operations)

    assert plan["valid"] is True
    assert plan["errors"] == []
    assert plan["summary"] == {"requested": 3, "applicable": 3, "skipped": 0}
    assert plan["operations"][0]["target_value"] == 640
    assert plan["operations"][1]["target_value"] == "usb"
    assert plan["operations"][2]["op_type"] == "REMOVE_RETIRED"
    assert plan["operations"][2]["retirement_id"] == "retire-obsolete-local"
    assert len(plan["plan_digest"]) == 64


def test_build_defaults_sync_plan_reports_invalid_and_skipped_operations():
    service = FakeConfigService()
    operations = [
        ConfigSyncOperation(
            op_type="ADD_NEW",
            path=["VideoSource", "VIDEO_SOURCE_TYPE"],
        ),
        ConfigSyncOperation(
            op_type="REMOVE_RETIRED",
            path=["VideoSource", "MISSING_LOCAL"],
        ),
        ConfigSyncOperation(
            op_type="ADOPT_DEFAULT",
            path=["VideoSource", "NO_DEFAULT"],
        ),
        ConfigSyncOperation(
            op_type="REMOVE_RETIRED",
            path=["UnknownSection", "UNKNOWN_PARAM"],
        ),
    ]

    plan = build_defaults_sync_plan(service, operations)

    assert plan["valid"] is False
    assert len(plan["errors"]) == 2
    assert plan["summary"] == {"requested": 4, "applicable": 0, "skipped": 2}
    assert plan["operations"][0]["skip"] is True
    assert plan["operations"][1]["skip"] is True
    assert any("already exists" in item["warning"] for item in plan["warnings"])
    assert any("missing in current config" in item["warning"] for item in plan["warnings"])


def test_build_defaults_sync_plan_rejects_invalid_values_and_duplicates():
    service = FakeConfigService()
    operations = [
        ConfigSyncOperation(
            op_type="ADD_NEW",
            path=["VideoSource", "WIDTH"],
            value="not-an-integer",
        ),
        ConfigSyncOperation(
            op_type="ADD_NEW",
            path=["VideoSource", "VIDEO_SOURCE_TYPE"],
            value="usb",
        ),
        ConfigSyncOperation(
            op_type="ADOPT_DEFAULT",
            path=["VideoSource", "VIDEO_SOURCE_TYPE"],
        ),
    ]

    plan = build_defaults_sync_plan(service, operations)

    assert plan["valid"] is False
    assert any("Validation failed" in item["error"] for item in plan["errors"])
    assert any("Duplicate operation" in item["error"] for item in plan["errors"])


def test_sync_report_preserves_active_scalar_defaults():
    service = FakeConfigService()
    service.defaults["ActiveScalar"] = "default-value"
    service.current["ActiveScalar"] = "operator-value"

    report = build_defaults_sync_report(service)

    assert not any(
        item["path"] == ["ActiveScalar"]
        for item in report["unknown_extensions"]
    )


def test_sync_contract_requires_v2_canonical_paths():
    request = ConfigSyncPlanRequest.model_validate(
        {
            "contract_version": 2,
            "operations": [
                {"op_type": "ADD_NEW", "path": ["VideoSource", "WIDTH"]}
            ],
        }
    )
    assert request.contract_version == 2

    with pytest.raises(ValueError):
        ConfigSyncPlanRequest.model_validate(
            {
                "contract_version": 1,
                "operations": [
                    {"op_type": "ADD_NEW", "path": ["VideoSource", "WIDTH"]}
                ],
            }
        )

    with pytest.raises(ValueError):
        ConfigSyncPlanRequest.model_validate(
            {
                "contract_version": 2,
                "operations": [
                    {
                        "op_type": "ADD_NEW",
                        "section": "VideoSource",
                        "parameter": "WIDTH",
                    }
                ],
            }
        )


def test_sync_report_redacts_sensitive_default_values():
    service = FakeConfigService()
    service.defaults["Secrets"] = {"SECRET_TOKEN": "do-not-return"}

    report = build_defaults_sync_report(service)

    item = next(
        entry
        for entry in report["new_parameters"]
        if entry["path"] == ["Secrets", "SECRET_TOKEN"]
    )
    assert item["default_value"] == "[REDACTED]"
    assert item["sensitive"] is True
    assert "do-not-return" not in str(report)
