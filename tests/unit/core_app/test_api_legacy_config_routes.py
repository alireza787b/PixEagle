"""Tests for legacy config route helper extraction."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from classes import api_legacy_config_routes as routes
from classes.api_legacy_config_routes import (
    ConfigImportRequest,
    ConfigParameterUpdate,
    ConfigSectionUpdate,
)
from classes.api_legacy_config_sync import (
    ConfigSyncOperation,
    ConfigSyncPlanRequest,
)


pytestmark = [pytest.mark.unit]


class FakeLogger:
    def __init__(self) -> None:
        self.infos = []
        self.warnings = []
        self.errors = []

    def info(self, *args):
        self.infos.append(args)

    def warning(self, *args):
        self.warnings.append(args)

    def error(self, *args):
        self.errors.append(args)


class FakeRateLimiter:
    def __init__(self, allowed: bool = True, retry_after: int = 7) -> None:
        self.allowed = allowed
        self.retry_after = retry_after
        self.calls = []

    def is_allowed(self, bucket: str):
        self.calls.append(bucket)
        return self.allowed, self.retry_after


class FakeValidationResult:
    def __init__(self, valid: bool = True, errors=None, warnings=None) -> None:
        self.valid = valid
        self.errors = list(errors or [])
        self.warnings = list(warnings or [])
        self.status = "valid" if valid else "error"

    def to_dict(self):
        return {
            "valid": self.valid,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class FakeDiff:
    def __init__(self, path: str = "Test.A") -> None:
        self.path = path

    def to_dict(self):
        return {
            "path": self.path,
            "section": "Test",
            "parameter": "A",
            "old_value": 1,
            "new_value": 2,
            "change_type": "changed",
        }


class FakeConfigService:
    SYNC_ARCHIVE_SECTION = "_archived_parameters"

    def __init__(self) -> None:
        self.schema = {
            "sections": {
                "Test": {
                    "display_name": "Test",
                    "category": "test",
                    "icon": "settings",
                    "parameters": {
                        "A": {"default": 1, "type": "integer", "reload_tier": "immediate"},
                        "B": {"default": 2, "type": "integer", "reload_tier": "system_restart"},
                        "C": {"default": 3, "type": "integer", "reload_tier": "follower_restart"},
                    }
                }
            }
        }
        self.current = {"Test": {"A": 10, "B": 20, "REMOVE": "old"}}
        self.defaults = {"Test": {"A": 1, "B": 2, "C": 3}}
        self.sync_meta = {
            "defaults_snapshot": {"Test": {"A": 1, "B": 2, "C": 3}},
            "defaults_snapshot_saved_at": "2026-06-01T00:00:00Z",
        }
        self.invalid_parameters = set()
        self.save_result = True
        self.revert_result = True
        self.restore_result = True
        self.import_success = True
        self.save_calls = []
        self.set_calls = []
        self.archive_calls = []
        self.backup_calls = 0
        self.reload_calls = 0
        self.snapshot_refreshes = 0
        self.revert_calls = []
        self.restore_calls = []
        self.import_calls = []
        self.diff_calls = []
        self.backup_history_calls = []
        self.export_calls = []
        self.search_calls = []
        self.audit_calls = []

    def get_schema(self, section=None):
        if section is not None:
            return self.schema["sections"].get(section, {})
        return self.schema

    def get_config(self, section=None):
        if section is not None:
            return self.current.get(section, {})
        return self.current

    def get_default(self, section=None):
        if section is not None:
            return self.defaults.get(section, {})
        return self.defaults

    def get_sections(self):
        sections = []
        for name, schema in self.schema["sections"].items():
            sections.append(
                {
                    "name": name,
                    "display_name": schema.get("display_name"),
                    "category": schema.get("category"),
                    "icon": schema.get("icon"),
                    "parameter_count": len(schema.get("parameters", {})),
                }
            )
        return sections

    def get_categories(self):
        return {"test": {"display_name": "Test"}}

    def get_changed_from_default(self):
        return [FakeDiff("Test.A")]

    def get_diff(self, config1, config2):
        self.diff_calls.append((config1, config2))
        return [FakeDiff("Diff.A")]

    def get_sync_meta(self):
        return self.sync_meta

    def get_schema_version(self):
        return "test-schema"

    def set_parameter(self, section, parameter, value, validate=True):
        self.set_calls.append((section, parameter, value, validate))
        if parameter in self.invalid_parameters:
            return FakeValidationResult(False, errors=[f"invalid {section}.{parameter}"])
        self.current.setdefault(section, {})[parameter] = value
        return FakeValidationResult(True)

    def set_section(self, section, parameters):
        errors = []
        for parameter, value in parameters.items():
            result = self.set_parameter(section, parameter, value)
            errors.extend(result.errors)
        return FakeValidationResult(not errors, errors=errors)

    def validate_value(self, section, parameter, value):
        if parameter in self.invalid_parameters:
            return FakeValidationResult(False, errors=["invalid"])
        return FakeValidationResult(True)

    def save_config(self, backup=True):
        self.save_calls.append(backup)
        return self.save_result

    def get_reload_tier(self, section, parameter):
        return (
            self.schema["sections"]
            .get(section, {})
            .get("parameters", {})
            .get(parameter, {})
            .get("reload_tier", "system_restart")
        )

    def get_reload_message(self, tier):
        return f"message:{tier}"

    def is_reboot_required(self, section, parameter):
        return self.get_reload_tier(section, parameter) == "system_restart"

    def _create_backup(self):
        self.backup_calls += 1
        return "/tmp/config_20260626_123456.yaml"

    def archive_and_remove_parameter(self, section, parameter):
        self.archive_calls.append((section, parameter))
        section_data = self.current.get(section, {})
        if parameter not in section_data:
            return False
        del section_data[parameter]
        return True

    def refresh_defaults_snapshot(self):
        self.snapshot_refreshes += 1
        return True

    def reload(self):
        self.reload_calls += 1

    def revert_to_default(self, section=None, param=None):
        self.revert_calls.append((section, param))
        return self.revert_result

    def get_default_parameter(self, section, parameter):
        return self.defaults.get(section, {}).get(parameter)

    def restore_backup(self, backup_id):
        self.restore_calls.append(backup_id)
        return self.restore_result

    def import_config(self, data, merge_mode):
        self.import_calls.append((data, merge_mode))
        return self.import_success, [FakeDiff()]

    def get_backup_history(self, limit=20):
        self.backup_history_calls.append(limit)
        return [
            SimpleNamespace(
                to_dict=lambda: {
                    "id": "config_20260626_123456",
                    "created_at": "2026-06-26T12:34:56Z",
                }
            )
        ]

    def export_config(self, sections=None, changes_only=False):
        self.export_calls.append((sections, changes_only))
        if sections:
            return {section: self.current.get(section, {}) for section in sections}
        return self.current

    def search_parameters(
        self,
        *,
        query,
        section,
        param_type,
        modified_only,
        limit,
        offset,
    ):
        self.search_calls.append(
            {
                "query": query,
                "section": section,
                "param_type": param_type,
                "modified_only": modified_only,
                "limit": limit,
                "offset": offset,
            }
        )
        return {
            "parameters": [{"section": "Test", "parameter": "A"}],
            "total": 1,
            "limit": limit,
            "offset": offset,
        }

    def get_audit_log(self, *, limit, offset, section, action):
        self.audit_calls.append(
            {
                "limit": limit,
                "offset": offset,
                "section": section,
                "action": action,
            }
        )
        return {
            "entries": [{"section": section or "Test", "action": action or "update"}],
            "total": 1,
            "limit": limit,
            "offset": offset,
        }


class FakeHandler:
    def __init__(self, service=None, rate_allowed: bool = True) -> None:
        self.service = service or FakeConfigService()
        self.config_rate_limiter = FakeRateLimiter(allowed=rate_allowed)
        self.logger = FakeLogger()

    def _get_config_service(self):
        return self.service


class FakeRequest:
    def __init__(self, payload=None, query_params=None) -> None:
        self.payload = payload or {}
        self.query_params = query_params or {}

    async def json(self):
        return self.payload


def response_body(response):
    return json.loads(response.body.decode("utf-8"))


def patch_reload(monkeypatch, *, result=True, exc=None):
    calls = []

    def reload_config():
        calls.append(True)
        if exc is not None:
            raise exc
        return result

    monkeypatch.setattr(routes.Parameters, "reload_config", staticmethod(reload_config))
    return calls


@pytest.mark.asyncio
async def test_config_schema_sections_and_categories_read_shapes():
    handler = FakeHandler()

    schema = response_body(await routes.get_config_schema(handler))
    section_schema = response_body(
        await routes.get_config_section_schema(handler, "Test")
    )
    sections = response_body(await routes.get_config_sections(handler))
    categories = response_body(await routes.get_config_categories(handler))

    assert schema["success"] is True
    assert schema["schema"]["sections"]["Test"]["parameters"]["A"]["default"] == 1
    assert section_schema["success"] is True
    assert section_schema["section"] == "Test"
    assert section_schema["schema"]["parameters"]["B"]["reload_tier"] == "system_restart"
    assert sections["success"] is True
    assert sections["count"] == 1
    assert sections["sections"][0]["name"] == "Test"
    assert categories["success"] is True
    assert categories["categories"]["test"]["display_name"] == "Test"

    with pytest.raises(HTTPException) as exc_info:
        await routes.get_config_section_schema(handler, "Missing")
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Section 'Missing' not found"


@pytest.mark.asyncio
async def test_current_default_and_diff_read_shapes():
    handler = FakeHandler()

    current = response_body(await routes.get_current_config(handler))
    current_section = response_body(
        await routes.get_current_config_section(handler, "Test")
    )
    missing_current_section = response_body(
        await routes.get_current_config_section(handler, "Missing")
    )
    default = response_body(await routes.get_default_config(handler))
    default_section = response_body(
        await routes.get_default_config_section(handler, "Test")
    )
    missing_default_section = response_body(
        await routes.get_default_config_section(handler, "Missing")
    )
    diff = response_body(await routes.get_config_diff(handler))

    assert current["config"]["Test"]["A"] == 10
    assert current_section["section"] == "Test"
    assert current_section["config"]["B"] == 20
    assert missing_current_section["success"] is True
    assert missing_current_section["config"] == {}
    assert default["config"]["Test"]["C"] == 3
    assert default_section["section"] == "Test"
    assert default_section["config"]["A"] == 1
    assert missing_default_section["success"] is True
    assert missing_default_section["config"] == {}
    assert diff["success"] is True
    assert diff["count"] == 1
    assert diff["differences"][0]["path"] == "Test.A"


@pytest.mark.asyncio
async def test_compare_defaults_sync_and_plan_routes_preserve_request_modes():
    service = FakeConfigService()
    handler = FakeHandler(service=service)

    compare_current = response_body(
        await routes.compare_configs(
            handler,
            FakeRequest({"compare_config": {"Test": {"A": 99}}}),
        )
    )
    compare_pair = response_body(
        await routes.compare_configs(
            handler,
            FakeRequest({"config1": {"A": 1}, "config2": {"A": 2}}),
        )
    )
    sync_with_baseline = response_body(await routes.get_defaults_sync(handler))

    service.sync_meta = {"defaults_snapshot": {}, "defaults_snapshot_saved_at": None}
    sync_without_baseline = response_body(await routes.get_defaults_sync(handler))

    valid_plan = response_body(
        await routes.plan_defaults_sync(
            handler,
            ConfigSyncPlanRequest(
                operations=[
                    ConfigSyncOperation(
                        op_type="ADD_NEW",
                        section="Test",
                        parameter="C",
                    )
                ]
            ),
        )
    )
    invalid_plan = response_body(
        await routes.plan_defaults_sync(
            handler,
            ConfigSyncPlanRequest(
                operations=[
                    ConfigSyncOperation(
                        op_type="UNKNOWN",
                        section="Test",
                        parameter="A",
                    )
                ]
            ),
        )
    )

    assert compare_current["success"] is True
    assert compare_pair["success"] is True
    assert service.diff_calls == [
        (service.current, {"Test": {"A": 99}}),
        ({"A": 1}, {"A": 2}),
    ]
    assert sync_with_baseline["baseline_available"] is True
    assert sync_with_baseline["baseline_initialized"] is False
    assert sync_without_baseline["baseline_available"] is False
    assert sync_without_baseline["baseline_initialized"] is True
    assert service.snapshot_refreshes == 1
    assert valid_plan["success"] is True
    assert valid_plan["plan"]["valid"] is True
    assert invalid_plan["success"] is True
    assert invalid_plan["plan"]["valid"] is False


@pytest.mark.asyncio
async def test_backup_export_search_and_audit_query_params_are_preserved():
    service = FakeConfigService()
    handler = FakeHandler(service=service)

    history = response_body(
        await routes.get_config_backup_history(
            handler,
            FakeRequest(query_params={"limit": "5"}),
        )
    )
    exported = response_body(
        await routes.export_config(
            handler,
            FakeRequest(
                query_params={"sections": "Test,Missing", "changes_only": "true"}
            ),
        )
    )
    search = response_body(
        await routes.search_config_parameters(
            handler,
            FakeRequest(
                query_params={
                    "q": "gain",
                    "section": "Test",
                    "type": "integer",
                    "modified_only": "true",
                    "limit": "7",
                    "offset": "3",
                }
            ),
        )
    )
    audit = response_body(
        await routes.get_config_audit_log(
            handler,
            FakeRequest(
                query_params={
                    "limit": "9",
                    "offset": "4",
                    "section": "Test",
                    "action": "update",
                }
            ),
        )
    )

    assert history["success"] is True
    assert history["count"] == 1
    assert service.backup_history_calls == [5]
    assert exported["changes_only"] is True
    assert exported["config"] == {"Test": service.current["Test"], "Missing": {}}
    assert service.export_calls == [(["Test", "Missing"], True)]
    assert search["success"] is True
    assert search["query"] == "gain"
    assert search["filters"] == {
        "section": "Test",
        "type": "integer",
        "modified_only": True,
    }
    assert service.search_calls == [
        {
            "query": "gain",
            "section": "Test",
            "param_type": "integer",
            "modified_only": True,
            "limit": 7,
            "offset": 3,
        }
    ]
    assert audit["success"] is True
    assert audit["entries"] == [{"section": "Test", "action": "update"}]
    assert service.audit_calls == [
        {
            "limit": 9,
            "offset": 4,
            "section": "Test",
            "action": "update",
        }
    ]


@pytest.mark.asyncio
async def test_query_int_parse_errors_preserve_legacy_500_behavior():
    handler = FakeHandler()

    with pytest.raises(HTTPException) as history_exc:
        await routes.get_config_backup_history(
            handler,
            FakeRequest(query_params={"limit": "bad"}),
        )
    with pytest.raises(HTTPException) as search_exc:
        await routes.search_config_parameters(
            handler,
            FakeRequest(query_params={"limit": "bad"}),
        )
    with pytest.raises(HTTPException) as audit_exc:
        await routes.get_config_audit_log(
            handler,
            FakeRequest(query_params={"offset": "bad"}),
        )

    assert history_exc.value.status_code == 500
    assert search_exc.value.status_code == 500
    assert audit_exc.value.status_code == 500


@pytest.mark.asyncio
async def test_config_write_rate_limit_response_shape():
    handler = FakeHandler(rate_allowed=False)

    calls = [
        routes.update_config_parameter(
            handler,
            "Test",
            "A",
            ConfigParameterUpdate(value=1),
        ),
        routes.update_config_section(
            handler,
            "Test",
            ConfigSectionUpdate(parameters={"A": 1}),
        ),
        routes.apply_defaults_sync(handler, ConfigSyncPlanRequest(operations=[])),
        routes.import_config(handler, ConfigImportRequest(data={"Test": {"A": 1}})),
    ]

    for call in calls:
        response = await call
        body = response_body(response)
        assert response.status_code == 429
        assert response.headers["retry-after"] == "7"
        assert body["success"] is False
        assert body["error"] == "Too many requests"
        assert body["retry_after"] == 7

    assert handler.config_rate_limiter.calls == ["config_write"] * 4


@pytest.mark.asyncio
async def test_update_parameter_invalid_validation_does_not_save_or_reload(monkeypatch):
    reload_calls = patch_reload(monkeypatch)
    service = FakeConfigService()
    service.invalid_parameters.add("A")
    handler = FakeHandler(service=service)

    response = await routes.update_config_parameter(
        handler,
        "Test",
        "A",
        ConfigParameterUpdate(value="bad"),
    )
    body = response_body(response)

    assert response.status_code == 400
    assert body["success"] is False
    assert body["validation"]["valid"] is False
    assert service.save_calls == []
    assert reload_calls == []


@pytest.mark.asyncio
async def test_update_parameter_reports_immediate_and_restart_applied_state(monkeypatch):
    reload_calls = patch_reload(monkeypatch, result=True)
    service = FakeConfigService()
    handler = FakeHandler(service=service)

    immediate = await routes.update_config_parameter(
        handler,
        "Test",
        "A",
        ConfigParameterUpdate(value=11),
    )
    restart = await routes.update_config_parameter(
        handler,
        "Test",
        "B",
        ConfigParameterUpdate(value=22),
    )

    immediate_body = response_body(immediate)
    restart_body = response_body(restart)
    assert immediate_body["saved"] is True
    assert immediate_body["applied"] is True
    assert immediate_body["reload_tier"] == "immediate"
    assert restart_body["saved"] is True
    assert restart_body["applied"] is False
    assert restart_body["reload_tier"] == "system_restart"
    assert restart_body["reboot_required"] is True
    assert len(reload_calls) == 2


@pytest.mark.asyncio
async def test_update_section_uses_highest_reload_tier_and_reboot_required(monkeypatch):
    patch_reload(monkeypatch, result=True)
    handler = FakeHandler()

    response = await routes.update_config_section(
        handler,
        "Test",
        ConfigSectionUpdate(parameters={"A": 1, "C": 3, "B": 2}),
    )
    body = response_body(response)

    assert body["success"] is True
    assert body["applied"] is False
    assert body["reload_tiers"] == {
        "A": "immediate",
        "C": "follower_restart",
        "B": "system_restart",
    }
    assert body["reload_tier"] == "system_restart"
    assert body["reboot_required"] is True


@pytest.mark.asyncio
async def test_validate_config_value_allows_null_and_rejects_missing_fields():
    handler = FakeHandler()

    response = await routes.validate_config_value(
        handler,
        FakeRequest({"section": "Test", "parameter": "A", "value": None}),
    )
    body = response_body(response)
    assert body["success"] is True
    assert body["value"] is None

    with pytest.raises(HTTPException) as exc_info:
        await routes.validate_config_value(
            handler,
            FakeRequest({"section": "Test", "value": 1}),
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "section and parameter are required"


@pytest.mark.asyncio
async def test_apply_defaults_sync_success_covers_all_operation_types(monkeypatch):
    reload_calls = patch_reload(monkeypatch, result=True)
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    request = ConfigSyncPlanRequest(
        operations=[
            ConfigSyncOperation(op_type="ADD_NEW", section="Test", parameter="C"),
            ConfigSyncOperation(op_type="ADOPT_DEFAULT", section="Test", parameter="A"),
            ConfigSyncOperation(
                op_type="ARCHIVE_REMOVE",
                section="Test",
                parameter="REMOVE",
            ),
        ]
    )

    response = await routes.apply_defaults_sync(handler, request)
    body = response_body(response)

    assert body["success"] is True
    assert body["applied_count"] == 3
    assert body["skipped_count"] == 0
    assert body["backup_id"] == "config_20260626_123456"
    assert service.backup_calls == 1
    assert service.save_calls == [False]
    assert service.snapshot_refreshes == 1
    assert service.archive_calls == [("Test", "REMOVE")]
    assert reload_calls == [True]


@pytest.mark.asyncio
async def test_apply_defaults_sync_invalid_plan_returns_400_without_mutation(monkeypatch):
    reload_calls = patch_reload(monkeypatch)
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    request = ConfigSyncPlanRequest(
        operations=[
            ConfigSyncOperation(op_type="UNKNOWN", section="Test", parameter="A"),
        ]
    )

    response = await routes.apply_defaults_sync(handler, request)
    body = response_body(response)

    assert response.status_code == 400
    assert body["success"] is False
    assert body["plan"]["valid"] is False
    assert service.backup_calls == 0
    assert service.save_calls == []
    assert reload_calls == []


@pytest.mark.asyncio
async def test_apply_defaults_sync_save_failure_rolls_back_and_raises_500(monkeypatch):
    patch_reload(monkeypatch)
    service = FakeConfigService()
    service.save_result = False
    handler = FakeHandler(service=service)
    request = ConfigSyncPlanRequest(
        operations=[
            ConfigSyncOperation(op_type="ADOPT_DEFAULT", section="Test", parameter="A"),
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.apply_defaults_sync(handler, request)

    assert exc_info.value.status_code == 500
    assert "Failed to save config after applying sync plan" in exc_info.value.detail
    assert service.reload_calls == 1
    assert service.snapshot_refreshes == 0


@pytest.mark.asyncio
async def test_revert_restore_and_import_preserve_legacy_reload_contract(monkeypatch):
    reload_calls = patch_reload(monkeypatch, exc=RuntimeError("reload failed"))
    service = FakeConfigService()
    handler = FakeHandler(service=service, rate_allowed=False)

    reverted = await routes.revert_config_to_default(handler)
    restored = await routes.restore_config_backup(handler, "config_20260626_123456")
    imported = await routes.import_config(
        handler,
        ConfigImportRequest(data={"Test": {"A": 33}}, merge_mode="replace"),
    )

    reverted_body = response_body(reverted)
    restored_body = response_body(restored)
    imported_body = response_body(imported)

    assert reverted_body["success"] is True
    assert service.revert_calls == [(None, None)]
    assert service.save_calls == [True]

    assert restored_body["success"] is True
    assert restored_body["backup_id"] == "config_20260626_123456"
    assert reload_calls == [True]
    assert handler.logger.errors

    assert imported.status_code == 429
    assert imported_body["success"] is False
    assert service.import_calls == []


@pytest.mark.asyncio
async def test_import_config_success_saves_without_hot_reload(monkeypatch):
    reload_calls = patch_reload(monkeypatch)
    service = FakeConfigService()
    handler = FakeHandler(service=service)

    response = await routes.import_config(
        handler,
        ConfigImportRequest(data={"Test": {"A": 44}}, merge_mode="replace"),
    )
    body = response_body(response)

    assert body["success"] is True
    assert body["merge_mode"] == "replace"
    assert body["changes_count"] == 1
    assert service.import_calls == [({"Test": {"A": 44}}, "replace")]
    assert service.save_calls == [True]
    assert reload_calls == []
