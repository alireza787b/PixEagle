"""Tests for legacy config route helper extraction."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from classes import api_legacy_config_routes as routes
from classes.api_legacy_config_routes import (
    ConfigImportRequest,
    ConfigParameterUpdate,
    ConfigSectionUpdate,
)
from classes.config_sync import (
    ConfigSyncApplyRequest,
    ConfigSyncOperation,
    ConfigSyncPlanRequest,
    build_defaults_sync_plan,
)


pytestmark = [pytest.mark.unit]


class FakeLogger:
    def __init__(self) -> None:
        self.infos = []
        self.warnings = []
        self.errors = []
        self.criticals = []

    def info(self, *args):
        self.infos.append(args)

    def warning(self, *args):
        self.warnings.append(args)

    def error(self, *args):
        self.errors.append(args)

    def critical(self, *args):
        self.criticals.append(args)


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
    def __init__(
        self,
        path: str = "Test.A",
        *,
        section: str = "Test",
        parameter: str = "A",
        old_value=1,
        new_value=2,
    ) -> None:
        self.path = path
        self.section = section
        self.parameter = parameter
        self.old_value = old_value
        self.new_value = new_value

    def to_dict(self):
        return {
            "path": self.path,
            "section": self.section,
            "parameter": self.parameter,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "change_type": "changed",
        }


class FakeConfigService:
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
        self.disk_current = copy.deepcopy(self.current)
        self.runtime_current = copy.deepcopy(self.current)
        self.runtime_publications = []
        self.runtime_generation = 1
        self.defaults = {"Test": {"A": 1, "B": 2, "C": 3}}
        self.sync_meta = {
            "defaults_snapshot": {"Test": {"A": 1, "B": 2, "C": 3}},
            "defaults_snapshot_saved_at": "2026-06-01T00:00:00Z",
        }
        self.invalid_parameters = set()
        self.save_result = True
        self.backup_result = "/tmp/config_20260626_123456.yaml"
        self.revert_result = True
        self.restore_result = True
        self.import_success = True
        self.save_calls = []
        self.set_calls = []
        self.remove_calls = []
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
        self.logged_audits = []
        self.source_digests = {
            "runtime_config": "1" * 64,
            "defaults": "2" * 64,
            "schema": "3" * 64,
            "retirements": "4" * 64,
            "sync_meta": "5" * 64,
            "audit_log": "6" * 64,
        }
        self.backups = {}

    @staticmethod
    def _digest(value):
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    def get_schema(self, section=None):
        if section is not None:
            return self.schema["sections"].get(section, {})
        return self.schema

    def get_config(self, section=None):
        if section is not None:
            return self.current.get(section, {})
        return self.current

    def get_applied_runtime_config(self):
        return copy.deepcopy(self.runtime_current)

    def publish_runtime_config_snapshot(self, config, *, source):
        self.runtime_current = copy.deepcopy(config)
        self.runtime_generation += 1
        self.runtime_publications.append(
            {"source": source, "restored": True, "config": copy.deepcopy(config)}
        )

    def apply_runtime_config_tiers(self, tiers, *, source):
        requested = set(tiers)
        applied_paths = []
        pending_paths = []
        candidate = copy.deepcopy(self.runtime_current)
        for section in sorted(set(self.runtime_current) | set(self.current)):
            runtime_section = self.runtime_current.get(section, {})
            persisted_section = self.current.get(section, {})
            if not isinstance(runtime_section, dict) or not isinstance(persisted_section, dict):
                continue
            for parameter in sorted(set(runtime_section) | set(persisted_section)):
                runtime_present = parameter in runtime_section
                persisted_present = parameter in persisted_section
                if (
                    runtime_present == persisted_present
                    and runtime_section.get(parameter) == persisted_section.get(parameter)
                ):
                    continue
                path = f"{section}.{parameter}"
                tier = self.get_reload_tier(section, parameter)
                if tier not in requested:
                    pending_paths.append(path)
                    continue
                if persisted_present:
                    candidate.setdefault(section, {})[parameter] = copy.deepcopy(
                        persisted_section[parameter]
                    )
                else:
                    candidate.get(section, {}).pop(parameter, None)
                applied_paths.append(path)

        generation_before = self.runtime_generation
        if applied_paths:
            self.runtime_current = candidate
            self.runtime_generation += 1
        result = {
            "requested_tiers": sorted(requested),
            "applied": bool(applied_paths),
            "applied_paths": applied_paths,
            "applied_count": len(applied_paths),
            "pending_paths": pending_paths,
            "pending_count": len(pending_paths),
            "generation_before": generation_before,
            "generation_after": self.runtime_generation,
        }
        self.runtime_publications.append(
            {"source": source, "restored": False, "result": copy.deepcopy(result)}
        )
        return result

    def get_default(self, section=None):
        if section is not None:
            return self.defaults.get(section, {})
        return self.defaults

    def get_effective_defaults(self):
        return self.defaults

    def get_parameter(self, section, parameter):
        section_data = self.current.get(section, {})
        return section_data.get(parameter) if isinstance(section_data, dict) else None

    def get_path_value(self, path, default=None):
        if len(path) == 1:
            return self.current.get(path[0], default)
        return self.current.get(path[0], {}).get(path[1], default)

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

    def get_retirement_registry(self):
        return {
            "registry_version": 1,
            "registry_digest": "b" * 64,
            "retirements": [
                {
                    "id": "retire-test-remove",
                    "path": ["Test", "REMOVE"],
                    "action": "remove",
                    "retired_in_schema_version": "test-schema",
                    "reason": "Test retirement",
                    "replacement": None,
                }
            ],
        }

    def set_parameter(
        self,
        section,
        parameter,
        value,
        validate=True,
        *,
        audit=False,
        source="api",
    ):
        self.set_calls.append((section, parameter, value, validate))
        if parameter in self.invalid_parameters:
            return FakeValidationResult(False, errors=[f"invalid {section}.{parameter}"])
        self.current.setdefault(section, {})[parameter] = value
        return FakeValidationResult(True)

    def set_section(self, section, parameters, *, audit=False, source="api"):
        errors = []
        for parameter, value in parameters.items():
            result = self.set_parameter(section, parameter, value, audit=audit)
            errors.extend(result.errors)
        return FakeValidationResult(not errors, errors=errors)

    def validate_value(self, section, parameter, value):
        if parameter in self.invalid_parameters:
            return FakeValidationResult(False, errors=["invalid"])
        return FakeValidationResult(True)

    def validate_path(self, path, value):
        if len(path) == 1:
            return FakeValidationResult(True)
        return self.validate_value(path[0], path[1], value)

    def set_path(self, path, value, **kwargs):
        if len(path) == 1:
            self.current[path[0]] = value
            return FakeValidationResult(True)
        return self.set_parameter(path[0], path[1], value, **kwargs)

    def save_config(
        self,
        backup=True,
        *,
        lock_acquired=False,
        expected_config_digest=None,
        write_receipt=None,
    ):
        self.save_calls.append(backup)
        if (
            expected_config_digest is not None
            and expected_config_digest != self.source_digests["runtime_config"]
        ):
            return False
        if self.save_result:
            self.disk_current = copy.deepcopy(self.current)
            self.source_digests["runtime_config"] = self._digest(self.disk_current)
            if write_receipt is not None:
                write_receipt["runtime_config"] = self.source_digests[
                    "runtime_config"
                ]
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

    def runtime_config_exists(self):
        return True

    def create_backup(self, *, lock_acquired=False, write_receipt=None):
        self.backup_calls += 1
        if self.backup_result is not None:
            self.backups[self.backup_result.rsplit("/", 1)[-1]] = self._digest(
                self.disk_current
            )
            if write_receipt is not None:
                write_receipt["backups"] = copy.deepcopy(self.backups)
        return self.backup_result

    def remove_registered_retirement(self, path, parameter=None):
        if isinstance(path, str):
            normalized = [path, parameter]
        else:
            normalized = list(path)
        section, parameter = normalized
        self.remove_calls.append((section, parameter))
        section_data = self.current.get(section, {})
        if parameter not in section_data:
            return False
        del section_data[parameter]
        return True

    def refresh_defaults_snapshot(self):
        self.snapshot_refreshes += 1
        return True

    def save_sync_meta(
        self,
        meta,
        *,
        lock_acquired=False,
        expected_digest=None,
        write_receipt=None,
    ):
        if expected_digest is not None and expected_digest != self.source_digests["sync_meta"]:
            return False
        self.sync_meta = meta
        self.source_digests["sync_meta"] = self._digest(meta)
        if write_receipt is not None:
            write_receipt["sync_meta"] = self.source_digests["sync_meta"]
        return True

    def reload(self):
        self.reload_calls += 1
        self.current = copy.deepcopy(self.disk_current)

    def reload_audit_log(self, *, strict=False, lock_acquired=False):
        return None

    @contextmanager
    def mutation_guard(self):
        yield

    def get_source_state_digests(self):
        return dict(self.source_digests)

    def get_persistence_state_digests(self):
        return {
            "runtime_config": self.source_digests["runtime_config"],
            "sync_meta": self.source_digests["sync_meta"],
            "audit_log": self.source_digests["audit_log"],
            "backups": copy.deepcopy(self.backups),
        }

    def capture_persistence_snapshot(self):
        return {
            "current": copy.deepcopy(self.current),
            "disk_current": copy.deepcopy(self.disk_current),
            "sync_meta": copy.deepcopy(self.sync_meta),
            "logged_audits": copy.deepcopy(self.logged_audits),
            "source_digests": copy.deepcopy(self.source_digests),
            "backups": copy.deepcopy(self.backups),
        }

    def restore_persistence_snapshot(
        self,
        snapshot,
        *,
        lock_acquired=False,
        expected_current_state=None,
    ):
        expected = (
            expected_current_state
            if expected_current_state is not None
            else {
                "runtime_config": self.source_digests["runtime_config"],
                "sync_meta": self.source_digests["sync_meta"],
                "audit_log": self.source_digests["audit_log"],
                "backups": copy.deepcopy(self.backups),
            }
        )
        conflicts = []
        current_state = self.get_persistence_state_digests()
        for name in ("runtime_config", "sync_meta", "audit_log", "backups"):
            if name not in expected:
                continue
            if current_state[name] != expected[name]:
                conflicts.append(name)
                continue
            if name == "runtime_config":
                self.disk_current = copy.deepcopy(snapshot["disk_current"])
            elif name == "sync_meta":
                self.sync_meta = copy.deepcopy(snapshot["sync_meta"])
            elif name == "audit_log":
                self.logged_audits = copy.deepcopy(snapshot["logged_audits"])
            else:
                self.backups = copy.deepcopy(snapshot["backups"])
            if name != "backups":
                self.source_digests[name] = snapshot["source_digests"][name]
        self.current = copy.deepcopy(self.disk_current)
        if conflicts:
            raise RuntimeError("external rollback conflict: " + ", ".join(conflicts))

    def revert_to_default(self, section=None, param=None):
        self.revert_calls.append((section, param))
        return self.revert_result

    def get_default_parameter(self, section, parameter):
        return self.defaults.get(section, {}).get(parameter)

    def restore_backup(
        self,
        backup_id,
        *,
        lock_acquired=False,
        expected_config_digest=None,
        write_receipt=None,
    ):
        self.restore_calls.append(backup_id)
        if self.restore_result:
            self.disk_current = copy.deepcopy(self.current)
            self.source_digests["runtime_config"] = self._digest(self.disk_current)
            if write_receipt is not None:
                write_receipt["runtime_config"] = self.source_digests[
                    "runtime_config"
                ]
        return self.restore_result

    def import_config(self, data, merge_mode):
        self.import_calls.append((data, merge_mode))
        return self.import_success, [FakeDiff()]

    def is_sensitive_path(self, path):
        return bool(path and path[-1] == "SECRET")

    def redact_value(self, value, path=()):
        if path and self.is_sensitive_path(path):
            return "[REDACTED]"
        if isinstance(value, str) and (
            "://user:password@" in value or "access_token=" in value
        ):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {
                key: self.redact_value(item, [*path, key])
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self.redact_value(item, path) for item in value]
        return copy.deepcopy(value)

    def redact_diff_entry(self, diff):
        result = diff.to_dict()
        path = [diff.section, diff.parameter]
        result["old_value"] = self.redact_value(result["old_value"], path)
        result["new_value"] = self.redact_value(result["new_value"], path)
        return result

    def log_audit_entry(self, **entry):
        expected_digest = entry.pop("expected_digest", None)
        write_receipt = entry.pop("write_receipt", None)
        entry.pop("lock_acquired", None)
        if (
            expected_digest is not None
            and expected_digest != self.source_digests["audit_log"]
        ):
            raise RuntimeError("audit CAS conflict")
        self.logged_audits.append(entry)
        self.source_digests["audit_log"] = self._digest(self.logged_audits)
        if write_receipt is not None:
            write_receipt["audit_log"] = self.source_digests["audit_log"]

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
        self.app_controller = SimpleNamespace(
            following_active=False,
            _follower_state_lock=asyncio.Lock(),
        )

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


def patch_runtime_publication(monkeypatch, *, result=True, exc=None):
    calls = []
    original = FakeConfigService.apply_runtime_config_tiers

    def apply_runtime_config_tiers(service, *args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        if exc is not None:
            raise exc
        if result is False:
            return {
                "applied": False,
                "applied_paths": [],
                "pending_paths": [],
            }
        return original(service, *args, **kwargs)

    monkeypatch.setattr(
        FakeConfigService,
        "apply_runtime_config_tiers",
        apply_runtime_config_tiers,
    )
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
async def test_config_mutation_wait_does_not_block_event_loop(monkeypatch):
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    entered = threading.Event()
    release = threading.Event()
    worker_thread_ids = []

    @contextmanager
    def blocked_mutation_guard():
        worker_thread_ids.append(threading.get_ident())
        entered.set()
        if not release.wait(timeout=2):
            raise TimeoutError("test mutation guard was not released")
        yield

    service.mutation_guard = blocked_mutation_guard
    patch_runtime_publication(monkeypatch)
    watchdog = threading.Timer(1.0, release.set)
    watchdog.start()
    event_loop_thread_id = threading.get_ident()
    started = time.perf_counter()
    task = asyncio.create_task(
        routes.update_config_parameter(
            handler,
            "Test",
            "A",
            ConfigParameterUpdate(value=11),
        )
    )

    try:
        await asyncio.sleep(0)
        event_loop_delay = time.perf_counter() - started
        assert event_loop_delay < 0.2
        assert await asyncio.to_thread(entered.wait, 1.0)
        assert worker_thread_ids != [event_loop_thread_id]
        release.set()
        response = await task
    finally:
        release.set()
        watchdog.cancel()

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_public_read_surfaces_do_not_serialize_config_credentials(monkeypatch):
    service = FakeConfigService()
    secret = "do-not-return"
    credential_url = "rtsp://user:password@camera.local/live"
    service.current["Test"].update({"SECRET": secret, "CAMERA_URL": credential_url})
    service.defaults["Test"].update({"SECRET": secret, "CAMERA_URL": credential_url})
    secret_diff = FakeDiff(
        "Test.SECRET",
        parameter="SECRET",
        old_value=secret,
        new_value=credential_url,
    )
    service.get_changed_from_default = lambda: [secret_diff]
    service.get_diff = lambda *_args: [secret_diff]
    service.import_config = lambda *_args: (True, [secret_diff])
    handler = FakeHandler(service=service)
    patch_runtime_publication(monkeypatch)

    payloads = [
        response_body(await routes.get_current_config(handler)),
        response_body(await routes.get_default_config(handler)),
        response_body(await routes.get_config_diff(handler)),
        response_body(
            await routes.compare_configs(
                handler,
                FakeRequest({"compare_config": {"Test": {"A": 1}}}),
            )
        ),
        response_body(await routes.export_config(handler, FakeRequest())),
        response_body(
            await routes.import_config(
                handler,
                ConfigImportRequest(data={"Test": {"A": 1}}),
            )
        ),
        response_body(
            await routes.validate_config_value(
                handler,
                FakeRequest(
                    {
                        "section": "Test",
                        "parameter": "SECRET",
                        "value": secret,
                    }
                ),
            )
        ),
    ]

    serialized = json.dumps(payloads)
    assert secret not in serialized
    assert credential_url not in serialized
    assert serialized.count("[REDACTED]") >= 6


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
                contract_version=2,
                operations=[
                    ConfigSyncOperation(
                        op_type="ADD_NEW",
                        path=["Test", "C"],
                    )
                ]
            ),
        )
    )
    invalid_plan = response_body(
        await routes.plan_defaults_sync(
            handler,
            ConfigSyncPlanRequest(
                contract_version=2,
                operations=[
                    ConfigSyncOperation(
                        op_type="REMOVE_RETIRED",
                        path=["Test", "UNMANAGED_EXTENSION"],
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
    assert sync_without_baseline["baseline_available"] is False
    assert service.snapshot_refreshes == 0
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
        routes.apply_defaults_sync(
            handler,
            ConfigSyncPlanRequest(contract_version=2, operations=[]),
        ),
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
    publication_calls = patch_runtime_publication(monkeypatch)
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
    assert publication_calls == []


@pytest.mark.asyncio
async def test_update_parameter_reports_immediate_and_restart_applied_state(monkeypatch):
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
    assert [
        publication["result"]["applied_paths"]
        for publication in service.runtime_publications
    ] == [["Test.A"], []]
    assert service.runtime_current["Test"]["A"] == 11
    assert service.runtime_current["Test"]["B"] == 20


@pytest.mark.asyncio
async def test_update_section_uses_highest_reload_tier_and_reboot_required(monkeypatch):
    patch_runtime_publication(monkeypatch, result=True)
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
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    operations = [
        ConfigSyncOperation(op_type="ADD_NEW", path=["Test", "C"]),
        ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=["Test", "A"]),
        ConfigSyncOperation(
            op_type="REMOVE_RETIRED",
            path=["Test", "REMOVE"],
        ),
    ]
    plan = build_defaults_sync_plan(service, operations)
    request = ConfigSyncApplyRequest(
        contract_version=2,
        operations=operations,
        plan_digest=routes._config_sync_plan_token(plan),
        confirm=True,
    )

    response = await routes.apply_defaults_sync(handler, request)
    body = response_body(response)

    assert body["success"] is True
    assert body["applied_count"] == 3
    assert body["skipped_count"] == 0
    assert body["backup_id"] == "config_20260626_123456"
    assert service.backup_calls == 1
    assert service.save_calls == [False]
    assert service.remove_calls == [("Test", "REMOVE")]
    assert body["runtime_reloaded"] is True
    assert "retire-test-remove" in service.sync_meta["applied_retirements"]
    assert service.runtime_publications[-1]["source"] == "config_api_immediate_apply"
    assert service.runtime_publications[-1]["result"]["applied_paths"] == ["Test.A"]


@pytest.mark.asyncio
async def test_apply_defaults_sync_advances_only_applied_baseline_paths(monkeypatch):
    patch_runtime_publication(monkeypatch, result=True)
    service = FakeConfigService()
    service.sync_meta["defaults_snapshot"] = {
        "Test": {"A": 0, "B": 0, "C": 3}
    }
    handler = FakeHandler(service=service)
    operations = [
        ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=["Test", "A"])
    ]
    plan = build_defaults_sync_plan(service, operations)

    response = await routes.apply_defaults_sync(
        handler,
        ConfigSyncApplyRequest(
            contract_version=2,
            operations=operations,
            plan_digest=routes._config_sync_plan_token(plan),
            confirm=True,
        ),
    )

    assert response.status_code == 200
    assert service.sync_meta["defaults_snapshot"] == {
        "Test": {"A": 1, "B": 0, "C": 3}
    }
    assert service.sync_meta["defaults_snapshot_mode"] == "incremental"


@pytest.mark.asyncio
async def test_apply_defaults_sync_invalid_plan_returns_400_without_mutation(monkeypatch):
    publication_calls = patch_runtime_publication(monkeypatch)
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    operations = [
        ConfigSyncOperation(
            op_type="REMOVE_RETIRED",
            path=["Test", "UNMANAGED_EXTENSION"],
        )
    ]
    plan = build_defaults_sync_plan(service, operations)
    request = ConfigSyncApplyRequest(
        contract_version=2,
        operations=operations,
        plan_digest=routes._config_sync_plan_token(plan),
        confirm=True,
    )

    response = await routes.apply_defaults_sync(handler, request)
    body = response_body(response)

    assert response.status_code == 400
    assert body["success"] is False
    assert body["plan"]["valid"] is False
    assert service.backup_calls == 0
    assert service.save_calls == []
    assert publication_calls == []


@pytest.mark.asyncio
async def test_apply_defaults_sync_save_failure_rolls_back_and_raises_500(monkeypatch):
    patch_runtime_publication(monkeypatch)
    service = FakeConfigService()
    service.save_result = False
    handler = FakeHandler(service=service)
    operations = [
        ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=["Test", "A"])
    ]
    plan = build_defaults_sync_plan(service, operations)
    request = ConfigSyncApplyRequest(
        contract_version=2,
        operations=operations,
        plan_digest=routes._config_sync_plan_token(plan),
        confirm=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.apply_defaults_sync(handler, request)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Config migration failed and was rolled back"
    assert service.reload_calls == 2
    assert service.snapshot_refreshes == 0


@pytest.mark.asyncio
async def test_apply_defaults_sync_backup_failure_prevents_mutation(monkeypatch):
    service = FakeConfigService()
    service.backup_result = None
    handler = FakeHandler(service=service)
    operations = [
        ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=["Test", "A"])
    ]
    plan = build_defaults_sync_plan(service, operations)

    with pytest.raises(HTTPException) as exc_info:
        await routes.apply_defaults_sync(
            handler,
            ConfigSyncApplyRequest(
                contract_version=2,
                operations=operations,
                plan_digest=routes._config_sync_plan_token(plan),
                confirm=True,
            ),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Config migration failed and was rolled back"
    assert service.set_calls == []
    assert service.save_calls == []
    assert service.runtime_publications == [
        {
            "source": "config_transaction_rollback",
            "restored": True,
            "config": service.runtime_current,
        }
    ]


@pytest.mark.asyncio
async def test_apply_defaults_sync_requires_confirmation_and_current_preview(monkeypatch):
    publication_calls = patch_runtime_publication(monkeypatch)
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    operations = [
        ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=["Test", "A"])
    ]
    plan = build_defaults_sync_plan(service, operations)

    unconfirmed = await routes.apply_defaults_sync(
        handler,
        ConfigSyncApplyRequest(
            contract_version=2,
            operations=operations,
            plan_digest=routes._config_sync_plan_token(plan),
            confirm=False,
        ),
    )
    stale = await routes.apply_defaults_sync(
        handler,
        ConfigSyncApplyRequest(
            contract_version=2,
            operations=operations,
            plan_digest="0" * 64,
            confirm=True,
        ),
    )

    assert unconfirmed.status_code == 400
    assert stale.status_code == 409
    assert service.backup_calls == 0
    assert service.save_calls == []
    assert publication_calls == []


@pytest.mark.asyncio
async def test_revert_restore_and_import_publish_only_immediate_runtime_tier(monkeypatch):
    service = FakeConfigService()
    handler = FakeHandler(service=service)

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
    assert service.save_calls == [True, True]

    assert restored_body["success"] is True
    assert restored_body["backup_id"] == "config_20260626_123456"
    assert service.restore_calls == ["config_20260626_123456"]

    assert imported.status_code == 200
    assert imported_body["success"] is True
    assert service.import_calls == [({"Test": {"A": 33}}, "replace")]
    assert len(service.runtime_publications) == 3
    assert all(
        publication["source"] == "config_api_immediate_apply"
        for publication in service.runtime_publications
    )


@pytest.mark.asyncio
async def test_failed_backup_restore_rolls_back_in_memory_and_persistence(monkeypatch):
    service = FakeConfigService()
    service.restore_result = False
    original_current = copy.deepcopy(service.current)

    def failed_restore(*args, **kwargs):
        service.current = {"Test": {"A": 999}}
        restore_succeeded = False
        return restore_succeeded

    service.restore_backup = failed_restore
    handler = FakeHandler(service=service)

    with pytest.raises(HTTPException) as exc_info:
        await routes.restore_config_backup(handler, "config_20260626_123456")

    assert exc_info.value.status_code == 500
    assert service.current == original_current
    assert service.runtime_publications[-1]["source"] == "config_transaction_rollback"
    assert service.runtime_current == original_current


@pytest.mark.asyncio
async def test_import_config_success_saves_and_applies_immediate_tier(monkeypatch):
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
    assert service.runtime_publications[-1]["source"] == "config_api_immediate_apply"


@pytest.mark.asyncio
async def test_config_mutation_is_blocked_while_following_is_active():
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    handler.app_controller = SimpleNamespace(
        following_active=True,
        _follower_state_lock=asyncio.Lock(),
    )

    response = await routes.update_config_parameter(
        handler,
        "Test",
        "A",
        ConfigParameterUpdate(value=11),
    )
    body = response_body(response)

    assert response.status_code == 409
    assert body["error_code"] == "CONFIG_MUTATION_FOLLOWING_ACTIVE"
    assert service.current["Test"]["A"] == 10
    assert service.save_calls == []
    assert handler.config_rate_limiter.calls == []


@pytest.mark.asyncio
async def test_config_mutation_fails_closed_without_follower_state_barrier():
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    handler.app_controller = SimpleNamespace(following_active=False)

    response = await routes.update_config_parameter(
        handler,
        "Test",
        "A",
        ConfigParameterUpdate(value=11),
    )
    body = response_body(response)

    assert response.status_code == 503
    assert body["error_code"] == "CONFIG_MUTATION_STATE_BARRIER_UNAVAILABLE"
    assert service.current["Test"]["A"] == 10
    assert service.save_calls == []


@pytest.mark.asyncio
async def test_config_mutation_serializes_follow_activation(monkeypatch):
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    patch_runtime_publication(monkeypatch, result=True)
    save_entered = threading.Event()
    release_save = threading.Event()
    activation_acquired = asyncio.Event()
    original_save = service.save_config

    def blocking_save(*args, **kwargs):
        save_entered.set()
        assert release_save.wait(2.0)
        return original_save(*args, **kwargs)

    service.save_config = blocking_save

    async def activate_following():
        async with handler.app_controller._follower_state_lock:
            handler.app_controller.following_active = True
            activation_acquired.set()

    mutation = asyncio.create_task(
        routes.update_config_parameter(
            handler,
            "Test",
            "A",
            ConfigParameterUpdate(value=11),
        )
    )
    try:
        assert await asyncio.to_thread(save_entered.wait, 1.0)
        activation = asyncio.create_task(activate_following())
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(activation_acquired.wait(), timeout=0.05)
        release_save.set()
        response = await mutation
        await activation
    finally:
        release_save.set()

    assert response.status_code == 200
    assert service.current["Test"]["A"] == 11
    assert handler.app_controller.following_active is True


@pytest.mark.asyncio
async def test_config_audit_is_durable_before_runtime_publication(monkeypatch):
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    events = []
    original_save = service.save_config
    original_audit = service.log_audit_entry

    def save_config(*args, **kwargs):
        events.append("config")
        return original_save(*args, **kwargs)

    def log_audit_entry(*args, **kwargs):
        events.append("audit")
        return original_audit(*args, **kwargs)

    original_apply = service.apply_runtime_config_tiers

    def apply_runtime_config_tiers(*args, **kwargs):
        events.append("runtime")
        return original_apply(*args, **kwargs)

    service.save_config = save_config
    service.log_audit_entry = log_audit_entry
    service.apply_runtime_config_tiers = apply_runtime_config_tiers

    response = await routes.update_config_parameter(
        handler,
        "Test",
        "A",
        ConfigParameterUpdate(value=11),
    )

    assert response.status_code == 200
    assert events == ["config", "audit", "runtime"]


@pytest.mark.asyncio
async def test_audit_failure_never_publishes_candidate_runtime(monkeypatch):
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("audit persistence failed")

    service.log_audit_entry = fail_audit

    with pytest.raises(HTTPException) as exc_info:
        await routes.update_config_parameter(
            handler,
            "Test",
            "A",
            ConfigParameterUpdate(value=11),
        )

    assert exc_info.value.status_code == 500
    assert service.runtime_publications[-1]["source"] == "config_transaction_rollback"
    assert service.runtime_current["Test"]["A"] == 10
    assert service.current["Test"]["A"] == 10


@pytest.mark.asyncio
async def test_selective_publication_failure_restores_persisted_and_runtime_state(monkeypatch):
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    def fail_publication(*_args, **_kwargs):
        raise RuntimeError("injected selective publication failure")

    service.apply_runtime_config_tiers = fail_publication

    with pytest.raises(HTTPException) as exc_info:
        await routes.update_config_parameter(
            handler,
            "Test",
            "A",
            ConfigParameterUpdate(value=99),
        )

    assert exc_info.value.status_code == 500
    assert service.current["Test"]["A"] == 10
    assert service.logged_audits == []
    assert service.runtime_publications[-1]["source"] == "config_transaction_rollback"
    assert service.runtime_current["Test"]["A"] == 10


@pytest.mark.asyncio
async def test_config_cas_failure_preserves_and_reloads_external_edit(monkeypatch):
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    patch_runtime_publication(monkeypatch, result=True)
    original_save = service.save_config

    def externally_edited_save(*args, **kwargs):
        service.disk_current["Test"]["A"] = 77
        service.source_digests["runtime_config"] = service._digest(
            service.disk_current
        )
        return original_save(*args, **kwargs)

    service.save_config = externally_edited_save

    with pytest.raises(HTTPException) as exc_info:
        await routes.update_config_parameter(
            handler,
            "Test",
            "A",
            ConfigParameterUpdate(value=11),
        )

    assert exc_info.value.status_code == 500
    assert service.disk_current["Test"]["A"] == 77
    assert service.current["Test"]["A"] == 77
    assert service.logged_audits == []


@pytest.mark.asyncio
async def test_rollback_preserves_external_edit_after_owned_config_write(monkeypatch):
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    patch_runtime_publication(monkeypatch, result=True)

    def externally_edit_then_fail_audit(**_entry):
        service.disk_current["Test"]["A"] = 88
        service.source_digests["runtime_config"] = service._digest(
            service.disk_current
        )
        raise RuntimeError("external edit raced audit")

    service.log_audit_entry = externally_edit_then_fail_audit

    with pytest.raises(HTTPException) as exc_info:
        await routes.update_config_parameter(
            handler,
            "Test",
            "A",
            ConfigParameterUpdate(value=11),
        )

    assert exc_info.value.status_code == 500
    assert "operator recovery" in str(exc_info.value.detail)
    assert service.disk_current["Test"]["A"] == 88
    assert service.current["Test"]["A"] == 88


@pytest.mark.asyncio
async def test_write_receipt_does_not_claim_external_edit_after_save(monkeypatch):
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    patch_runtime_publication(monkeypatch, result=True)
    original_save = service.save_config

    def save_then_external_edit(*args, **kwargs):
        result = original_save(*args, **kwargs)
        service.disk_current["Test"]["A"] = 91
        service.source_digests["runtime_config"] = service._digest(
            service.disk_current
        )
        return result

    def fail_audit(**_entry):
        raise RuntimeError("audit persistence failed")

    service.save_config = save_then_external_edit
    service.log_audit_entry = fail_audit

    with pytest.raises(HTTPException) as exc_info:
        await routes.update_config_parameter(
            handler,
            "Test",
            "A",
            ConfigParameterUpdate(value=11),
        )

    assert exc_info.value.status_code == 500
    assert "operator recovery" in str(exc_info.value.detail)
    assert service.disk_current["Test"]["A"] == 91
    assert service.current["Test"]["A"] == 91


@pytest.mark.asyncio
async def test_post_write_audit_failure_records_receipt_before_rollback(monkeypatch):
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    patch_runtime_publication(monkeypatch, result=True)
    original_disk = copy.deepcopy(service.disk_current)
    original_audits = copy.deepcopy(service.logged_audits)

    def write_audit_then_fail(**entry):
        expected_digest = entry.pop("expected_digest", None)
        write_receipt = entry.pop("write_receipt", None)
        entry.pop("lock_acquired", None)
        assert expected_digest == service.source_digests["audit_log"]
        service.logged_audits.append(entry)
        service.source_digests["audit_log"] = service._digest(
            service.logged_audits
        )
        write_receipt["audit_log"] = service.source_digests["audit_log"]
        raise RuntimeError("injected failure after audit persistence")

    service.log_audit_entry = write_audit_then_fail

    with pytest.raises(HTTPException) as exc_info:
        await routes.update_config_parameter(
            handler,
            "Test",
            "A",
            ConfigParameterUpdate(value=11),
        )

    assert exc_info.value.status_code == 500
    assert service.disk_current == original_disk
    assert service.current == original_disk
    assert service.logged_audits == original_audits


@pytest.mark.asyncio
async def test_plan_and_noop_apply_redact_sensitive_operation_values(monkeypatch):
    patch_runtime_publication(monkeypatch, result=True)
    service = FakeConfigService()
    service.schema["sections"]["Test"]["parameters"]["SECRET"] = {
        "default": "canonical-secret",
        "type": "string",
        "reload_tier": "system_restart",
    }
    service.defaults["Test"]["SECRET"] = "canonical-secret"
    service.current["Test"]["SECRET"] = "operator-secret"
    service.disk_current = copy.deepcopy(service.current)
    handler = FakeHandler(service=service)
    operations = [
        ConfigSyncOperation(
            op_type="ADD_NEW",
            path=["Test", "SECRET"],
            value="request-secret",
        )
    ]
    internal_plan = build_defaults_sync_plan(service, operations)

    preview = response_body(
        await routes.plan_defaults_sync(
            handler,
            ConfigSyncPlanRequest(contract_version=2, operations=operations),
        )
    )
    applied = response_body(
        await routes.apply_defaults_sync(
            handler,
            ConfigSyncApplyRequest(
                contract_version=2,
                operations=operations,
                plan_digest=routes._config_sync_plan_token(internal_plan),
                confirm=True,
            ),
        )
    )

    assert preview["plan"]["operations"][0]["target_value"] == "[REDACTED]"
    assert applied["skipped_operations"][0]["target_value"] == "[REDACTED]"
    assert "request-secret" not in str(preview)
    assert "request-secret" not in str(applied)


@pytest.mark.asyncio
async def test_public_plan_uses_opaque_token_and_hides_internal_fingerprints():
    service = FakeConfigService()
    handler = FakeHandler(service=service)
    operations = [ConfigSyncOperation(op_type="ADOPT_DEFAULT", path=["Test", "A"])]
    internal_plan = build_defaults_sync_plan(service, operations)

    preview = response_body(
        await routes.plan_defaults_sync(
            handler,
            ConfigSyncPlanRequest(contract_version=2, operations=operations),
        )
    )
    public_plan = preview["plan"]

    assert public_plan["plan_digest"] == routes._config_sync_plan_token(internal_plan)
    assert public_plan["plan_digest"] != internal_plan["plan_digest"]
    for internal_field in (
        "config_digest",
        "defaults_digest",
        "schema_digest",
        "source_state_digests",
    ):
        assert internal_field not in public_plan

    response = await routes.apply_defaults_sync(
        handler,
        ConfigSyncApplyRequest(
            contract_version=2,
            operations=operations,
            plan_digest=internal_plan["plan_digest"],
            confirm=True,
        ),
    )
    assert response.status_code == 409
