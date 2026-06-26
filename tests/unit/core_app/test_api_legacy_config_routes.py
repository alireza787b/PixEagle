"""Tests for legacy config mutation route helper extraction."""

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
    def __init__(self) -> None:
        self.schema = {
            "sections": {
                "Test": {
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

    def get_schema(self):
        return self.schema

    def get_config(self):
        return self.current

    def get_default(self):
        return self.defaults

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


class FakeHandler:
    def __init__(self, service=None, rate_allowed: bool = True) -> None:
        self.service = service or FakeConfigService()
        self.config_rate_limiter = FakeRateLimiter(allowed=rate_allowed)
        self.logger = FakeLogger()

    def _get_config_service(self):
        return self.service


class FakeRequest:
    def __init__(self, payload) -> None:
        self.payload = payload

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
