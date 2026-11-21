"""Preview/save integration through the real atomic ConfigService."""

import asyncio
import logging
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from classes import api_v1_config_editor as editor
from classes.api_security_types import APIPrincipal
from classes.api_v1_contracts import APIConfigSaveRequest, APIConfigSaveResponse
from classes.api_v1_native_targets import NativeTargetError
from classes.config_service import ConfigService


@pytest.fixture
def settings_owner(tmp_path, monkeypatch):
    root = tmp_path / "configs"
    root.mkdir()
    for name in ("config_default.yaml", "config_schema.yaml", "config_retirements.yaml"):
        shutil.copyfile(Path("configs") / name, root / name)
    path = root / "config.yaml"
    path.write_text("# Operator note\n" + (root / "config_default.yaml").read_text())
    service = ConfigService(project_root=tmp_path)

    async def on_owner_loop(operation):
        return await operation()

    owner = SimpleNamespace(
        _get_config_service=lambda: service,
        logger=logging.getLogger(__name__),
        app_controller=SimpleNamespace(
            following_active=False, _follower_state_lock=asyncio.Lock(),
            _run_on_flight_event_loop=on_owner_loop,
        ),
        config_rate_limiter=SimpleNamespace(is_allowed=lambda _: (True, None)),
    )
    # Persistence and rollback are real. The test has no active component managers.
    monkeypatch.setattr(editor, "_publish_runtime_config", lambda _: None)
    monkeypatch.setattr(service, "get_applied_runtime_config", lambda: service.get_sync_config())
    monkeypatch.setattr(service, "publish_runtime_config_snapshot", lambda *_a, **_kw: None)
    return owner, service, path


def request(revision, **kwargs):
    return APIConfigSaveRequest(revision=revision, **kwargs)


def saved(service, path):
    return service._get_mapping_path(service.get_sync_config(), path)


def test_review_and_save_one_batch_and_review_backup_restore(settings_owner):
    owner, service, path = settings_owner
    original = path.read_bytes()
    principal = APIPrincipal.local_compat()
    revision = editor._snapshot(owner, principal)["revision"]
    edits = [
        {"path": ["Streaming", "STREAM_FPS"], "value": 12},
        {"path": ["VideoSource", "CAPTURE_FPS"], "value": 24},
    ]
    review = editor._preview(owner, request(revision, edits=edits, dry_run=True), "scope")
    assert [row["path"] for row in review["result"]["changes"]] == [edit["path"] for edit in edits]
    assert path.read_bytes() == original
    assert not service.get_backup_history()

    save = request(revision, edits=edits, confirm=True, idempotency_key="batch",
                   preview_token=review["result"]["preview_token"])
    result = APIConfigSaveResponse.model_validate(editor._save(owner, save, "scope")).result
    assert len(service.get_backup_history()) == 1
    assert (path.parent / "backups" / f"{result.backup_id}.yaml").read_bytes() == original
    assert "# Operator note" in path.read_text()
    assert saved(service, edits[0]["path"]) == 12
    assert saved(service, edits[1]["path"]) == 24
    restore = editor._preview(owner, request(result.revision, backup_id=result.backup_id, dry_run=True), "scope")
    assert [row["new_value"] for row in restore["result"]["changes"]] == [20, 30]


def test_bad_and_stale_review_cannot_write(settings_owner):
    owner, service, path = settings_owner
    revision = editor._snapshot(owner, APIPrincipal.local_compat())["revision"]
    edits = [{"path": ["Streaming", "STREAM_FPS"], "value": 12}]
    invalid = [{"path": ["Streaming", "STREAM_FPS"], "value": "invalid"}]
    with pytest.raises(NativeTargetError, match="STREAM_FPS"):
        editor._preview(owner, request(revision, edits=invalid, dry_run=True), "scope")

    review = editor._preview(owner, request(revision, edits=edits, dry_run=True), "scope")
    path.write_bytes(path.read_bytes() + b"\n# Settings edited elsewhere\n")
    original = path.read_bytes()
    with pytest.raises(NativeTargetError, match="Refresh and review"):
        editor._save(owner, request(revision, edits=edits, confirm=True, idempotency_key="stale",
                                   preview_token=review["result"]["preview_token"]), "scope")
    assert path.read_bytes() == original
    assert not service.get_backup_history()


def test_persistence_and_backup_roll_back_after_runtime_failure(settings_owner, monkeypatch):
    owner, service, path = settings_owner
    original = path.read_bytes()
    revision = editor._snapshot(owner, APIPrincipal.local_compat())["revision"]
    edits = [{"path": ["Streaming", "STREAM_FPS"], "value": 12}]
    review = editor._preview(owner, request(revision, edits=edits, dry_run=True), "scope")

    def fail(_):
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr(editor, "_publish_runtime_config", fail)
    with pytest.raises(RuntimeError, match="runtime unavailable"):
        editor._save(owner, request(revision, edits=edits, confirm=True, idempotency_key="rollback",
                                   preview_token=review["result"]["preview_token"]), "scope")
    assert path.read_bytes() == original
    assert not service.get_backup_history()
    assert not (path.parent / "audit_log.json").exists()


@pytest.mark.asyncio
async def test_same_confirmed_request_replays_existing_result(settings_owner):
    owner, service, _ = settings_owner
    principal = APIPrincipal.local_compat()
    http = SimpleNamespace(state=SimpleNamespace(api_principal=principal))
    revision = editor._snapshot(owner, principal)["revision"]
    edits = [{"path": ["Streaming", "STREAM_FPS"], "value": 12}]
    reviewed = await editor.config_save_action(owner, request(revision, edits=edits, dry_run=True), http)
    save = request(revision, edits=edits, confirm=True, idempotency_key="same",
                   preview_token=reviewed["result"]["preview_token"])
    first = await editor.config_save_action(owner, save, http)
    replay = await editor.config_save_action(owner, save, http)
    assert first["action_id"] == replay["action_id"]
    assert replay["idempotent_replay"] is True
    assert len(service.get_backup_history()) == 1
