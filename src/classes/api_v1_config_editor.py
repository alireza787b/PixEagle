"""Reviewed configuration batches for the Dashboard Settings editor."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
from pathlib import Path

from fastapi.responses import JSONResponse
from ruamel.yaml import YAML
from starlette.concurrency import run_in_threadpool

from classes.api_legacy_config_routes import (
    _assert_audit_source_unchanged,
    _config_mutation_transaction,
    _config_write_rate_limit_response,
    _create_config_backup,
    _log_config_audit,
    _persist_config,
    _publish_runtime_config,
)
from classes.api_v1_actions import ensure_api_action_store, new_api_action_record
from classes.api_security_types import APIPrincipalKind
from classes.api_v1_native_config import _error
from classes.api_v1_native_targets import NativeTargetError
from classes.api_v1_paths import API_V1_ACTION_CONFIG_SAVE_PATH, API_V1_CONFIG_EDITOR_PATH

_TOKEN_KEY = secrets.token_bytes(32)
_MISSING = object()
_ACTION = "config_save"


class ConfigSettingError(NativeTargetError):
    def __init__(self, path, message):
        super().__init__("config_invalid_value", message, 422)
        self.setting_path = path


def _principal(http_request, *, write=False):
    principal = getattr(http_request.state, "api_principal", None)
    scopes = {"config:read", "config:write"} if write else {"config:read"}
    if principal is None or principal.kind is APIPrincipalKind.ANONYMOUS:
        raise NativeTargetError("config_login_required", "Sign in to review settings.", 401)
    if not scopes.issubset(principal.scopes):
        raise NativeTargetError("config_permission_required", "Configuration permission is required.", 403)
    return principal


def _digest(*parts):
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(_TOKEN_KEY, payload.encode(), hashlib.sha256).hexdigest()


def _read_config(service):
    source, _ = service._get_persisted_source_file_locked()
    with source.open(encoding="utf-8") as stream:
        raw = YAML().load(stream)
    if not isinstance(raw, dict):
        raise NativeTargetError("config_invalid", "The saved configuration is not a mapping.", 422)
    return raw


def _current_locked(service):
    digests = service.get_source_state_digests()
    if service._get_source_generation_status_locked()["state"] != "current":
        raise NativeTargetError("config_definitions_changed", "Restart PixEagle to load the updated configuration schema.")
    raw = _read_config(service)
    if digests != service.get_source_state_digests():
        raise NativeTargetError("config_revision_stale", "Settings changed while reading. Refresh and review again.")
    return raw, _digest(digests)


def _snapshot(owner, principal):
    service = owner._get_config_service()
    with service._mutation_lock:
        raw, revision = _current_locked(service)
        return dict(revision=revision, config=service.redact_value(service._normalize_effective_config_locked(raw)),
                    writable="config:write" in principal.scopes,
                    pending_changes=service.get_pending_runtime_config_status()["pending_changes"])


async def get_config_editor(owner, http_request):
    try:
        principal = _principal(http_request)
        payload = await run_in_threadpool(_snapshot, owner, principal)
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return _error(owner, exc, API_V1_CONFIG_EDITOR_PATH)


def _changes(service, before, after, path=()):
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            yield from _changes(service, before.get(key, _MISSING), after.get(key, _MISSING), (*path, key))
        return
    if before is _MISSING and isinstance(after, dict) and after:
        yield from _changes(service, {}, after, path)
        return
    if after is _MISSING and isinstance(before, dict) and before:
        yield from _changes(service, before, {}, path)
        return
    if before == after and isinstance(before, bool) == isinstance(after, bool):
        return
    yield dict(
        path=list(path),
        old_value=None if before is _MISSING else service.redact_value(before, path),
        new_value=None if after is _MISSING else service.redact_value(after, path),
        kind="added" if before is _MISSING else "removed" if after is _MISSING else "changed",
        reload_tier=service.get_reload_tier(path[0], path[1] if len(path) > 1 else "_value"),
    )


def _validate_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise NativeTargetError("config_invalid_number", "Enter a finite number.", 422)
    if value == "[REDACTED]":
        raise NativeTargetError("config_redacted_value", "Supply a value in place of the masked setting.", 422)
    if isinstance(value, dict):
        for item in value.values():
            _validate_value(item)
    elif isinstance(value, list):
        for item in value:
            _validate_value(item)


def _import_mapping(service, raw, request):
    excluded = {tuple(path) for path in request.excluded_paths}
    if any(not path or len(path) > 16 for path in excluded):
        raise NativeTargetError("config_path_invalid", "A setting has an invalid path.", 422)

    count = 0

    def keep(value, path=()):
        nonlocal count
        count += 1
        if count > 20000 or len(path) > 16:
            raise NativeTargetError("config_import_too_large", "This configuration is too large to review.", 422)
        if value == "[REDACTED]" or path in excluded:
            return _MISSING
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if not key or len(key) > 160 or key.strip() != key:
                    raise NativeTargetError("config_path_invalid", "A YAML key has an invalid name.", 422)
                child = keep(item, (*path, key))
                if child is not _MISSING:
                    result[key] = child
            return result if result or not value else _MISSING
        if isinstance(value, list):
            # Arrays are atomic. A redacted item means the destination array stays intact.
            result = [keep(item, (*path, str(index))) for index, item in enumerate(value)]
            return _MISSING if result != value else value
        _validate_value(value)
        return value

    filtered = keep(request.import_values)
    if filtered is _MISSING:
        return raw
    for retirement in service._get_retirement_registry_locked()["retirements"]:
        path = retirement["path"]
        existing = service._get_mapping_path(raw, path, _MISSING)
        supplied = service._get_mapping_path(filtered, path, _MISSING)
        if supplied is not _MISSING and supplied != existing:
            raise NativeTargetError("config_retired_setting", f"Review {'.'.join(path)} in Sync with defaults.", 422)
    return service._deep_merge_mapping(raw, filtered)


def _candidate(service, raw, request):
    if request.backup_id:
        backup = next((p for p in service._get_managed_backup_files() if p.stem == request.backup_id), None)
        if backup is None:
            raise NativeTargetError("config_backup_missing", "That settings backup is no longer available.", 404)
        with backup.open(encoding="utf-8") as stream:
            candidate = YAML().load(stream)
        if not isinstance(candidate, dict):
            raise NativeTargetError("config_invalid_backup", "This backup cannot be restored.", 422)
        return candidate

    if request.import_values is not None:
        return _import_mapping(service, raw, request)

    # The source is a newly read object, so modifying a copy keeps the preview
    # baseline intact for the exact per-setting comparison.
    candidate = service._deep_merge_mapping(raw, {})
    paths = {tuple(edit.path) for edit in request.edits}
    if len(paths) != len(request.edits) or any(
        path[:length] in paths for path in paths for length in range(1, len(path))
    ):
        raise NativeTargetError("config_overlapping_edits", "Review duplicate settings before saving.", 422)

    for edit in request.edits:
        path = edit.path
        if any(not part or part.strip() != part or len(part) > 160 for part in path):
            raise NativeTargetError("config_path_invalid", "A setting has an invalid path.", 422)
        schema = service.get_path_schema(path)
        if not schema or schema.get("read_only"):
            raise NativeTargetError("config_path_undeclared", f"{'.'.join(path)} is read-only.", 422)
        if edit.unset:
            service._remove_mapping_path(candidate, path)
        else:
            _validate_value(edit.value)
            if not service.validate_path(path, edit.value).valid:
                raise ConfigSettingError(path, f"Check the value for {'.'.join(path)}.")
            service._set_mapping_path(candidate, path, edit.value)
    return candidate


def _review(service, request, scope):
    raw, revision = _current_locked(service)
    if not hmac.compare_digest(request.revision, revision):
        raise NativeTargetError("config_revision_stale", "Settings changed on PixEagle. Refresh and review again.")
    candidate = _candidate(service, raw, request)
    try:
        if request.import_values is not None:
            for change in _changes(service, raw, candidate):
                path = change["path"]
                definition = service.get_path_schema(path)
                if definition.get("read_only"):
                    raise NativeTargetError("config_path_read_only", f"{'.'.join(path)} is read-only.", 422)
                value = service._get_mapping_path(candidate, path, _MISSING)
                if definition and value is not _MISSING and not service.validate_path(path, value).valid:
                    raise ConfigSettingError(path, f"Check the value for {'.'.join(path)}.")
        normalized = service._normalize_effective_config_locked(candidate)
        validation = service.validate_config_mapping(normalized, require_safety=True)
    except ValueError:
        raise NativeTargetError("config_invalid", "Check the proposed values and the relationships between limits.", 422) from None
    if not validation.valid:
        # Validation errors can contain actual option values.
        raise NativeTargetError("config_invalid", "Some proposed values do not match the configuration schema.", 422)
    changes = list(_changes(service, service._normalize_effective_config_locked(raw), normalized))
    token = _digest(scope, revision, candidate, request.backup_id)
    return candidate, normalized, changes, token


def _record(request, result):
    return new_api_action_record(
        action_type=_ACTION, request=request, status_value="validated" if request.dry_run else "success",
        accepted=True, executed=not request.dry_run, following_active_before=False,
        following_active_after=False, result=result,
    )


def _preview(owner, request, scope):
    service = owner._get_config_service()
    with service._mutation_lock:
        _, _, changes, token = _review(service, request, scope)
    return _record(request, dict(revision=request.revision, changes=changes, preview_token=token))


def _save(owner, request, scope):
    blocked = _config_write_rate_limit_response(owner)
    if blocked is not None:
        return blocked
    with _config_mutation_transaction(owner) as (service, transaction):
        candidate, normalized, changes, token = _review(service, request, scope)
        if not hmac.compare_digest(request.preview_token, token):
            raise NativeTargetError("config_preview_stale", "Review the latest changes before saving.")
        backup = None
        if changes:
            backup = _create_config_backup(service, transaction)
            if service.runtime_config_exists() and backup is None:
                raise RuntimeError("Could not create the configuration backup")
            service.stage_reviewed_config(candidate, normalized)
            _persist_config(service, transaction, backup=False)
            _assert_audit_source_unchanged(service, transaction)
            audit_action = "restore" if request.backup_id else "import" if request.import_values is not None else "update"
            _log_config_audit(service, transaction, action=audit_action,
                              section="*", old_value=None, new_value=None, source=_ACTION)
            _publish_runtime_config(service)
        _, revision = _current_locked(service)
    return _record(request, dict(revision=revision, changes=changes, backup_id=Path(backup).stem if backup else None))


async def config_save_action(owner, request, http_request):
    try:
        principal = _principal(http_request, write=True)
        scope = _digest(principal.kind.value, principal.subject) + ":"
        if request.dry_run:
            return await run_in_threadpool(_preview, owner, request, scope)

        app = owner.app_controller
        store = ensure_api_action_store(owner)
        digest = _digest(request.model_dump(mode="json"))

        async def execute():
            lock = getattr(app, "_follower_state_lock", None)
            if lock is None:
                raise NativeTargetError("state_barrier_unavailable", "Configuration state is unavailable.", 503)
            async with lock:
                replay = store.lookup_idempotent_action(_ACTION, request.idempotency_key, scope=scope)
                if replay:
                    if store.request_digests.get(replay["action_id"]) != digest:
                        raise NativeTargetError("idempotency_conflict", "This request key belongs to another save.")
                    return replay
                record = await run_in_threadpool(_save, owner, request, scope)
                if not isinstance(record, JSONResponse):
                    store.store_action_record(record, scope=scope, digest=digest)
                return record

        return await app._run_on_flight_event_loop(execute)
    except ConfigSettingError as exc:
        return owner._api_v1_error_response(
            status_code=exc.status_code, code=exc.code, path=API_V1_ACTION_CONFIG_SAVE_PATH,
            detail={"message": str(exc), "setting_path": exc.setting_path},
        )
    except Exception as exc:
        return _error(owner, exc, API_V1_ACTION_CONFIG_SAVE_PATH)
