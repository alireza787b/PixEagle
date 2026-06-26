"""Tests for legacy config defaults-sync helper extraction."""

from __future__ import annotations

import pytest

from classes.api_legacy_config_sync import (
    ConfigSyncOperation,
    build_defaults_sync_plan,
    build_defaults_sync_report,
)


pytestmark = [pytest.mark.unit]


class FakeConfigService:
    SYNC_ARCHIVE_SECTION = "_ConfigSyncArchive"

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

    def get_sync_meta(self):
        return self.sync_meta

    def get_schema_version(self):
        return "test-schema"


def test_build_defaults_sync_report_uses_schema_and_defaults_union():
    report = build_defaults_sync_report(FakeConfigService())

    assert report["baseline_available"] is True
    assert report["baseline_saved_at"] == "2026-06-01T00:00:00Z"
    assert report["schema_version"] == "test-schema"

    new_params = {(item["section"], item["parameter"]) for item in report["new_parameters"]}
    removed_params = {
        (item["section"], item["parameter"]) for item in report["removed_parameters"]
    }
    changed_params = {
        (item["section"], item["parameter"]) for item in report["changed_defaults"]
    }

    assert ("VideoSource", "WIDTH") in new_params
    assert ("VideoSource", "DEFAULT_ONLY") in new_params
    assert ("NewDefaultSection", "ENABLED") in new_params
    assert ("VideoSource", "OBSOLETE_LOCAL") in removed_params
    assert ("UnknownSection", "UNKNOWN_PARAM") in removed_params
    assert ("VideoSource", "VIDEO_SOURCE_TYPE") in changed_params


def test_build_defaults_sync_plan_normalizes_supported_operations():
    service = FakeConfigService()
    operations = [
        ConfigSyncOperation(
            op_type="ADD_NEW",
            section="VideoSource",
            parameter="WIDTH",
        ),
        ConfigSyncOperation(
            op_type="ADOPT_DEFAULT",
            section="VideoSource",
            parameter="VIDEO_SOURCE_TYPE",
        ),
        ConfigSyncOperation(
            op_type="ARCHIVE_REMOVE",
            section="VideoSource",
            parameter="OBSOLETE_LOCAL",
        ),
    ]

    plan = build_defaults_sync_plan(service, operations)

    assert plan["valid"] is True
    assert plan["errors"] == []
    assert plan["summary"] == {"requested": 3, "applicable": 3, "skipped": 0}
    assert plan["operations"][0]["target_value"] == 640
    assert plan["operations"][1]["target_value"] == "usb"
    assert plan["operations"][2]["op_type"] == "ARCHIVE_REMOVE"


def test_build_defaults_sync_plan_reports_invalid_and_skipped_operations():
    service = FakeConfigService()
    operations = [
        ConfigSyncOperation(
            op_type="ADD_NEW",
            section="VideoSource",
            parameter="VIDEO_SOURCE_TYPE",
        ),
        ConfigSyncOperation(
            op_type="ARCHIVE_REMOVE",
            section="VideoSource",
            parameter="MISSING_LOCAL",
        ),
        ConfigSyncOperation(
            op_type="ADOPT_DEFAULT",
            section="VideoSource",
            parameter="NO_DEFAULT",
        ),
        ConfigSyncOperation(
            op_type="UNKNOWN",
            section="VideoSource",
            parameter="WIDTH",
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
