"""Tests for legacy model/yolo route helper extraction."""

from __future__ import annotations

import asyncio
import copy
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from classes import api_legacy_model_routes as model_routes
from classes.model_artifact_policy import ModelIngestLease, ModelStoreLease, sha256_file
from classes.model_manager import ModelManager


pytestmark = [pytest.mark.unit]


class FakeLogger:
    def debug(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass

    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def critical(self, *_args, **_kwargs):
        pass

    def exception(self, *_args, **_kwargs):
        pass


class FakeModelManager:
    def __init__(self, models):
        self.models = models
        self.folder = "."
        self.last_force_rescan = None
        self.validation_calls = []
        self.validation_hook = None

    def normalize_model_id(self, model_identifier):
        if model_identifier is None:
            return None
        return Path(str(model_identifier)).name

    def discover_models(self, force_rescan=False):
        self.last_force_rescan = force_rescan
        return self.models

    def get_model_labels(self, model_identifier, force_rescan=False):
        self.last_force_rescan = force_rescan
        model_info = self.models.get(model_identifier)
        if model_info is None:
            return None, []
        return model_info, list(model_info.get("class_names", []))

    def validate_model(self, model_path, *, allow_checkpoint_execution=False):
        assert allow_checkpoint_execution is True
        self.validation_calls.append(Path(model_path))
        if self.validation_hook is not None:
            self.validation_hook()
        return {"valid": True, "smarttracker_supported": True}


class FakeRequest:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return dict(self.body)


class FakeFormRequest:
    def __init__(self, form):
        self._form = form

    async def form(self, **_limits):
        return dict(self._form)


class FakeUploadFile:
    def __init__(self, filename="demo.pt", chunks=None):
        self.filename = filename
        self._chunks = list(chunks or [b"model"])
        self.closed = False

    async def read(self, _size=-1):
        return self._chunks.pop(0) if self._chunks else b""

    async def close(self):
        self.closed = True


class FakeRuntimeTracker:
    def __init__(self, model_path):
        self.runtime = {
            "model_path": str(model_path),
            "requested_device": "gpu",
            "effective_device": "cuda",
        }
        self.switch_calls = []
        self.fail_rollback = False
        self.selected_object_id = None
        self.tracking_manager = SimpleNamespace(selected_track_id=None)

    def get_runtime_info(self):
        return dict(self.runtime)

    def switch_model(self, model_path, device="auto"):
        self.switch_calls.append((str(model_path), device))
        if self.fail_rollback and len(self.switch_calls) > 1:
            return {"success": False, "message": "rollback rejected"}

        effective_device = "cuda" if device == "gpu" else "cpu"
        self.runtime = {
            "model_path": str(model_path),
            "requested_device": device,
            "effective_device": effective_device,
        }
        return {
            "success": True,
            "message": "model switched",
            "model_info": {"runtime": dict(self.runtime)},
        }


class FakeConfigService:
    def __init__(self, initial_config, failure_stage=None):
        self.disk_config = copy.deepcopy(initial_config)
        self.memory_config = copy.deepcopy(initial_config)
        self.audit_log = []
        self.failure_stage = failure_stage
        self.applied_runtime_config = copy.deepcopy(initial_config)

    @contextmanager
    def mutation_guard(self):
        yield

    def reload(self):
        self.memory_config = copy.deepcopy(self.disk_config)

    def reload_audit_log(self, strict=False, lock_acquired=False):
        return None

    def get_applied_runtime_config(self):
        return copy.deepcopy(self.applied_runtime_config)

    def publish_runtime_config_snapshot(self, config, *, source):  # noqa: ARG002
        self.applied_runtime_config = copy.deepcopy(config)

    def apply_runtime_config_tiers(self, tiers, *, source):  # noqa: ARG002
        if self.failure_stage == "reload":
            raise RuntimeError("runtime publication failed")
        self.applied_runtime_config = copy.deepcopy(self.memory_config)
        return {"applied_paths": [], "pending_paths": []}

    def capture_persistence_snapshot(self):
        return {
            "disk_config": copy.deepcopy(self.disk_config),
            "audit_log": copy.deepcopy(self.audit_log),
        }

    def restore_persistence_snapshot(
        self,
        snapshot,
        lock_acquired=False,
        expected_current_state=None,
    ):
        expected = expected_current_state if expected_current_state is not None else {
            "runtime_config": self.get_source_state_digests()["runtime_config"],
            "audit_log": self.get_source_state_digests()["audit_log"],
        }
        current = self.get_persistence_state_digests()
        if "runtime_config" in expected:
            if current["runtime_config"] != expected["runtime_config"]:
                raise RuntimeError("external runtime config edit")
            self.disk_config = copy.deepcopy(snapshot["disk_config"])
        if "audit_log" in expected:
            if current["audit_log"] != expected["audit_log"]:
                raise RuntimeError("external audit edit")
            self.audit_log = copy.deepcopy(snapshot["audit_log"])
        self.memory_config = copy.deepcopy(self.disk_config)

    def get_source_state_digests(self):
        return {
            "runtime_config": json.dumps(self.disk_config, sort_keys=True),
            "audit_log": json.dumps(self.audit_log, sort_keys=True),
        }

    def get_persistence_state_digests(self):
        source = self.get_source_state_digests()
        return {
            "runtime_config": source["runtime_config"],
            "sync_meta": "missing",
            "audit_log": source["audit_log"],
            "backups": {},
        }

    def get_parameter(self, section, parameter):
        return self.memory_config[section][parameter]

    def set_parameter(self, section, parameter, value, audit=False):
        self.memory_config[section][parameter] = value
        return SimpleNamespace(valid=True, errors=[], warnings=[])

    def save_config(self, **kwargs):
        if self.failure_stage == "save":
            return False
        self.disk_config = copy.deepcopy(self.memory_config)
        write_receipt = kwargs.get("write_receipt")
        if write_receipt is not None:
            write_receipt["runtime_config"] = self.get_source_state_digests()[
                "runtime_config"
            ]
        return True

    def log_audit_entry(self, **entry):
        if self.failure_stage == "audit":
            raise RuntimeError("audit persistence failed")
        expected_digest = entry.pop("expected_digest", None)
        write_receipt = entry.pop("write_receipt", None)
        entry.pop("lock_acquired", None)
        if (
            expected_digest is not None
            and expected_digest != self.get_source_state_digests()["audit_log"]
        ):
            raise RuntimeError("audit CAS conflict")
        self.audit_log.append(copy.deepcopy(entry))
        if write_receipt is not None:
            write_receipt["audit_log"] = self.get_source_state_digests()[
                "audit_log"
            ]


def _json_body(response):
    return json.loads(response.body.decode("utf-8"))


def test_build_active_model_summary_limits_label_preview():
    summary = model_routes.build_active_model_summary(
        model_id="demo.pt",
        model_info={
            "name": "Demo",
            "path": "models/demo.pt",
            "class_names": ["boat", "person", "car"],
            "is_custom": True,
            "has_ncnn": True,
        },
        runtime={
            "model_task": "detect",
            "geometry_mode": "obb",
            "backend": "ultralytics",
            "effective_device": "cpu",
        },
        source="runtime",
        label_preview_limit=2,
    )

    assert summary["model_id"] == "demo.pt"
    assert summary["task"] == "detect"
    assert summary["geometry_mode"] == "obb"
    assert summary["label_preview"] == ["boat", "person"]
    assert summary["has_more_labels"] is True
    assert summary["is_custom"] is True


@pytest.mark.asyncio
async def test_get_models_uses_runtime_model_and_force_rescan(tmp_path):
    model_path = tmp_path / "demo.pt"
    model_path.write_text("placeholder", encoding="utf-8")
    ncnn_dir = tmp_path / "demo_ncnn_model"
    ncnn_dir.mkdir()

    manager = FakeModelManager(
        {
            "demo.pt": {
                "name": "Demo",
                "path": str(model_path),
                "class_names": ["boat"],
                "task": "detect",
            }
        }
    )
    smart_tracker = SimpleNamespace(
        get_runtime_info=lambda: {
            "model_path": str(ncnn_dir),
            "model_task": "detect",
            "geometry_mode": "aabb",
            "backend": "test-backend",
            "effective_device": "cpu",
        }
    )
    handler = SimpleNamespace(
        app_controller=SimpleNamespace(smart_tracker=smart_tracker),
        model_manager=manager,
        logger=FakeLogger(),
    )
    request = SimpleNamespace(query_params={"force_rescan": "true"})

    response = await model_routes.get_models(handler, request)
    body = _json_body(response)

    assert manager.last_force_rescan is True
    assert body["current_model"] == "demo.pt"
    assert body["active_model_id"] == "demo.pt"
    assert body["active_model_source"] == "runtime"
    assert body["active_model_summary"]["backend"] == "test-backend"


@pytest.mark.asyncio
async def test_get_model_labels_searches_and_bounds_page():
    manager = FakeModelManager(
        {
            "demo.pt": {
                "name": "Demo",
                "class_names": ["boat", "person", "bottle"],
            }
        }
    )
    handler = SimpleNamespace(model_manager=manager, logger=FakeLogger())
    request = SimpleNamespace(
        query_params={
            "search": "bo",
            "offset": "0",
            "limit": "1",
            "force_rescan": "true",
        }
    )

    response = await model_routes.get_model_labels(handler, "demo.pt", request)
    body = _json_body(response)

    assert manager.last_force_rescan is True
    assert body["filtered_count"] == 2
    assert body["returned_count"] == 1
    assert body["has_more"] is True
    assert body["labels"] == [{"class_id": 0, "label": "boat"}]


def test_resolve_standby_cpu_model_path_prefers_sibling_ncnn_export(tmp_path):
    model_path = tmp_path / "demo.pt"
    model_path.write_text("placeholder", encoding="utf-8")
    ncnn_dir = tmp_path / "demo_ncnn_model"
    ncnn_dir.mkdir()
    (ncnn_dir / "demo.bin").write_text("bin", encoding="utf-8")
    (ncnn_dir / "demo.param").write_text("param", encoding="utf-8")

    assert model_routes.resolve_standby_cpu_model_path(model_path) == str(
        ncnn_dir.as_posix()
    )


@pytest.mark.asyncio
async def test_upload_route_streams_file_and_defaults_ncnn_off(tmp_path, monkeypatch):
    calls = []

    class Manager:
        models_folder = tmp_path
        max_model_bytes = 1024 * 1024

        async def upload_model_file(self, **kwargs):
            calls.append(kwargs)
            return {
                "success": True,
                "message": "registered",
                "artifact_sha256": "a" * 64,
                "trust_method": "operator_assertion",
                "model_info": {"path": "models/demo.pt"},
                "ncnn_exported": False,
                "ncnn_export": None,
            }

    upload = FakeUploadFile()
    request = FakeFormRequest({"file": upload, "trust_model": "true"})
    handler = SimpleNamespace(model_manager=Manager(), logger=FakeLogger())

    async def parse_form(_request, **_limits):
        return request._form

    monkeypatch.setattr(model_routes, "parse_bounded_multipart_form", parse_form)

    response = await model_routes.upload_model(handler, request)
    body = _json_body(response)

    assert response.status_code == 200
    assert body["artifact_sha256"] == "a" * 64
    assert calls == [
        {
            "upload_file": upload,
            "filename": "demo.pt",
            "auto_export_ncnn": False,
            "expected_sha256": None,
            "trust_model": True,
            "source": "dashboard_or_api_upload",
        }
    ]
    assert upload.closed is False


@pytest.mark.asyncio
async def test_upload_route_rejects_low_disk_before_parsing(tmp_path, monkeypatch):
    class Manager:
        models_folder = tmp_path
        max_model_bytes = 1024 * 1024

    parser_calls = []

    async def unexpected_parser(*_args, **_kwargs):
        parser_calls.append(True)
        raise AssertionError("multipart parser must not run without disk headroom")

    monkeypatch.setattr(model_routes, "parse_bounded_multipart_form", unexpected_parser)
    monkeypatch.setattr(
        model_routes,
        "_require_model_ingest_capacity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            model_routes.ModelIngestCapacityError("low disk")
        ),
    )
    handler = SimpleNamespace(model_manager=Manager(), logger=FakeLogger())

    response = await model_routes.upload_model(handler, FakeRequest({}))
    body = _json_body(response)

    assert response.status_code == 507
    assert body["error_code"] == "MODEL_UPLOAD_STORAGE_UNAVAILABLE"
    assert parser_calls == []
    assert handler.model_ingest_semaphore.locked() is False


@pytest.mark.asyncio
async def test_upload_route_rejects_concurrent_ingest_without_reading_body(tmp_path):
    class Manager:
        models_folder = tmp_path
        max_model_bytes = 1024 * 1024

    semaphore = asyncio.Semaphore(1)
    await semaphore.acquire()
    handler = SimpleNamespace(
        model_manager=Manager(),
        model_ingest_semaphore=semaphore,
        logger=FakeLogger(),
    )
    try:
        response = await model_routes.upload_model(handler, FakeRequest({}))
    finally:
        semaphore.release()

    body = _json_body(response)
    assert response.status_code == 429
    assert body["error_code"] == "MODEL_UPLOAD_BUSY"


@pytest.mark.asyncio
async def test_upload_route_rejects_cross_owner_admission_contention(tmp_path):
    class Manager:
        models_folder = tmp_path
        max_model_bytes = 1024 * 1024

    tmp_path.chmod(0o700)
    handler = SimpleNamespace(
        model_manager=Manager(),
        model_ingest_semaphore=asyncio.Semaphore(1),
        logger=FakeLogger(),
    )
    ready = threading.Event()
    release = threading.Event()

    def hold_ingest_lease():
        with ModelIngestLease(tmp_path):
            ready.set()
            assert release.wait(timeout=5)

    owner = threading.Thread(target=hold_ingest_lease)
    owner.start()
    try:
        assert await asyncio.to_thread(ready.wait, 2)
        response = await model_routes.upload_model(handler, FakeRequest({}))
    finally:
        release.set()
        owner.join(timeout=2)
    assert not owner.is_alive()

    body = _json_body(response)
    assert response.status_code == 429
    assert body["error_code"] == "MODEL_UPLOAD_BUSY"


@pytest.mark.asyncio
async def test_delete_route_does_not_block_event_loop_while_model_is_loaded(tmp_path):
    manager = ModelManager(models_folder=str(tmp_path))
    model_path = tmp_path / "demo.pt"
    model_path.write_bytes(b"trusted-model")
    model_path.chmod(0o600)
    manager.provenance.trust_pt(
        model_path,
        sha256=sha256_file(model_path),
        source="unit-test",
        expected_digest_verified=True,
        publisher_sha256=sha256_file(model_path),
    )
    handler = SimpleNamespace(model_manager=manager, logger=FakeLogger())
    heartbeat_ran = False

    async def heartbeat():
        nonlocal heartbeat_ran
        await asyncio.sleep(0.01)
        heartbeat_ran = True

    with ModelStoreLease(tmp_path, exclusive=False):
        response, _ = await asyncio.gather(
            model_routes.delete_model(handler, "demo"),
            heartbeat(),
        )

    assert heartbeat_ran is True
    assert response.status_code == 409
    assert _json_body(response)["error_code"] == "MODEL_STORE_BUSY"


@pytest.mark.asyncio
async def test_model_file_download_releases_store_lock_but_streams_pinned_inode(tmp_path):
    manager = ModelManager(models_folder=str(tmp_path))
    model_path = tmp_path / "demo.pt"
    model_path.write_bytes(b"trusted-model-payload")
    model_path.chmod(0o600)
    digest = sha256_file(model_path)
    manager.provenance.trust_pt(
        model_path,
        sha256=digest,
        source="unit-test",
        expected_digest_verified=True,
        publisher_sha256=digest,
    )
    handler = SimpleNamespace(model_manager=manager, logger=FakeLogger())

    response = await model_routes.download_model_file(handler, "demo")
    delete_finished = threading.Event()
    delete_result = {}

    def delete_model():
        delete_result.update(manager.delete_model("demo"))
        delete_finished.set()

    delete_thread = threading.Thread(target=delete_model, daemon=True)
    delete_thread.start()
    assert delete_finished.wait(timeout=1)
    assert delete_result["success"] is True
    assert not model_path.exists()

    payload = b"".join([chunk async for chunk in response.body_iterator])
    delete_thread.join(timeout=2)

    assert payload == b"trusted-model-payload"
    assert response.headers["x-artifact-sha256"] == digest
    assert response.headers["content-length"] == str(len(payload))


@pytest.mark.asyncio
async def test_model_file_download_reports_corrupt_registry_as_unavailable(tmp_path):
    manager = ModelManager(models_folder=str(tmp_path))
    registry = tmp_path / ".model-provenance.json"
    registry.write_text("{not-json", encoding="utf-8")
    registry.chmod(0o600)
    handler = SimpleNamespace(model_manager=manager, logger=FakeLogger())

    with pytest.raises(HTTPException) as exc_info:
        await model_routes.download_model_file(handler, "demo")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error_code"] == "MODEL_PROVENANCE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_model_file_download_reports_digest_tamper_as_unavailable(tmp_path):
    manager = ModelManager(models_folder=str(tmp_path))
    model_path = tmp_path / "demo.pt"
    model_path.write_bytes(b"trusted")
    model_path.chmod(0o600)
    manager.provenance.trust_pt(
        model_path,
        sha256=sha256_file(model_path),
        source="unit-test",
        expected_digest_verified=True,
        publisher_sha256=sha256_file(model_path),
    )
    model_path.write_bytes(b"tampered")
    handler = SimpleNamespace(model_manager=manager, logger=FakeLogger())

    with pytest.raises(HTTPException) as exc_info:
        await model_routes.download_model_file(handler, "demo")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error_code"] == "MODEL_ARTIFACT_TRUST_FAILURE"


@pytest.mark.asyncio
async def test_model_inventory_reports_corrupt_registry_as_unavailable(tmp_path):
    manager = ModelManager(models_folder=str(tmp_path))
    registry = tmp_path / ".model-provenance.json"
    registry.write_text("{not-json", encoding="utf-8")
    registry.chmod(0o600)
    handler = SimpleNamespace(model_manager=manager, logger=FakeLogger())

    with pytest.raises(HTTPException) as exc_info:
        await model_routes.get_models(handler)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error_code"] == "MODEL_PROVENANCE_UNAVAILABLE"


def _model_switch_fixture(tmp_path, failure_stage=None):
    old_model = tmp_path / "old.pt"
    new_model = tmp_path / "new.pt"
    old_model.write_bytes(b"old")
    new_model.write_bytes(b"new")

    initial_config = {
        "SmartTracker": {
            "SMART_TRACKER_GPU_MODEL_PATH": str(old_model),
            "SMART_TRACKER_CPU_MODEL_PATH": str(old_model),
        }
    }
    service = FakeConfigService(initial_config, failure_stage=failure_stage)
    tracker = FakeRuntimeTracker(old_model)
    manager = FakeModelManager({})
    controller = SimpleNamespace(
        following_active=False,
        smart_tracker=tracker,
        _follower_state_lock=asyncio.Lock(),
        _tracker_model_state_lock=threading.RLock(),
    )
    handler = SimpleNamespace(
        app_controller=controller,
        model_manager=manager,
        logger=FakeLogger(),
        _get_config_service=lambda: service,
    )
    request = FakeRequest({"model_path": str(new_model), "device": "gpu"})
    return handler, request, service, tracker, old_model, new_model, initial_config


@pytest.mark.asyncio
async def test_switch_model_is_blocked_while_following(tmp_path):
    (
        handler,
        request,
        _service,
        tracker,
        _old_model,
        _new_model,
        _initial_config,
    ) = _model_switch_fixture(tmp_path)
    handler.app_controller.following_active = True

    response = await model_routes.switch_model(handler, request)
    body = _json_body(response)

    assert response.status_code == 409
    assert body["error_code"] == "MODEL_SWITCH_FOLLOWING_ACTIVE"
    assert body["requires_disconnect"] is True
    assert handler.model_manager.validation_calls == []
    assert tracker.switch_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("selection_owner", ["smart_tracker", "tracking_manager"])
async def test_switch_model_is_blocked_while_target_is_selected(
    tmp_path,
    selection_owner,
):
    (
        handler,
        request,
        service,
        tracker,
        _old_model,
        _new_model,
        initial_config,
    ) = _model_switch_fixture(tmp_path)
    if selection_owner == "smart_tracker":
        tracker.selected_object_id = 42
    else:
        tracker.tracking_manager.selected_track_id = 42

    response = await model_routes.switch_model(handler, request)
    body = _json_body(response)

    assert response.status_code == 409
    assert body["error_code"] == "MODEL_SWITCH_TRACKING_ACTIVE"
    assert body["requires_target_clear"] is True
    assert service.disk_config == initial_config
    assert handler.model_manager.validation_calls == []
    assert tracker.switch_calls == []


@pytest.mark.asyncio
async def test_switch_model_fails_closed_without_follower_state_barrier(tmp_path):
    (
        handler,
        request,
        service,
        tracker,
        _old_model,
        _new_model,
        _initial_config,
    ) = _model_switch_fixture(tmp_path)
    del handler.app_controller._follower_state_lock

    response = await model_routes.switch_model(handler, request)
    body = _json_body(response)

    assert response.status_code == 503
    assert body["error_code"] == "MODEL_SWITCH_STATE_BARRIER_UNAVAILABLE"
    assert service.disk_config == service.memory_config
    assert handler.model_manager.validation_calls == []
    assert tracker.switch_calls == []


@pytest.mark.asyncio
async def test_switch_model_fails_closed_without_target_state_barrier(tmp_path):
    (
        handler,
        request,
        service,
        tracker,
        _old_model,
        _new_model,
        _initial_config,
    ) = _model_switch_fixture(tmp_path)
    del handler.app_controller._tracker_model_state_lock

    response = await model_routes.switch_model(handler, request)
    body = _json_body(response)

    assert response.status_code == 503
    assert body["error_code"] == "MODEL_SWITCH_TARGET_BARRIER_UNAVAILABLE"
    assert service.disk_config == service.memory_config
    assert handler.model_manager.validation_calls == []
    assert tracker.switch_calls == []


@pytest.mark.asyncio
async def test_switch_model_rechecks_target_selection_after_validation(tmp_path):
    (
        handler,
        request,
        service,
        tracker,
        _old_model,
        _new_model,
        initial_config,
    ) = _model_switch_fixture(tmp_path)
    handler.model_manager.validation_hook = lambda: setattr(
        tracker,
        "selected_object_id",
        42,
    )

    response = await model_routes.switch_model(handler, request)
    body = _json_body(response)

    assert response.status_code == 409
    assert body["error_code"] == "MODEL_SWITCH_TRACKING_ACTIVE"
    assert service.disk_config == initial_config
    assert tracker.switch_calls == []


@pytest.mark.asyncio
async def test_switch_model_publishes_only_after_runtime_and_config_succeed(
    monkeypatch,
    tmp_path,
):
    (
        handler,
        request,
        service,
        tracker,
        _old_model,
        new_model,
        _initial_config,
    ) = _model_switch_fixture(tmp_path)
    monkeypatch.setattr(
        model_routes.Parameters,
        "reload_config",
        staticmethod(lambda strict_dependents=False: True),
    )

    response = await model_routes.switch_model(handler, request)
    body = _json_body(response)

    assert response.status_code == 200
    assert body["status"] == "success"
    assert body["action"] == "model_switched"
    assert body["config_persist_warning"] is None
    assert tracker.get_runtime_info()["model_path"] == str(new_model)
    assert service.disk_config["SmartTracker"][
        "SMART_TRACKER_GPU_MODEL_PATH"
    ] == str(new_model)
    assert len(service.audit_log) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["save", "reload", "audit"])
async def test_switch_model_restores_runtime_and_config_on_persistence_failure(
    monkeypatch,
    tmp_path,
    failure_stage,
):
    (
        handler,
        request,
        service,
        tracker,
        old_model,
        new_model,
        initial_config,
    ) = _model_switch_fixture(tmp_path, failure_stage=failure_stage)

    reload_calls = 0

    def reload_config(strict_dependents=False):
        nonlocal reload_calls
        reload_calls += 1
        reload_succeeded = not (
            failure_stage == "reload" and reload_calls == 1
        )
        return reload_succeeded

    monkeypatch.setattr(
        model_routes.Parameters,
        "reload_config",
        staticmethod(reload_config),
    )

    with pytest.raises(HTTPException) as exc_info:
        await model_routes.switch_model(handler, request)

    assert exc_info.value.status_code == 500
    assert "rolled back" in str(exc_info.value.detail)
    assert service.disk_config == initial_config
    assert service.memory_config == initial_config
    assert service.audit_log == []
    assert tracker.get_runtime_info()["model_path"] == str(old_model)
    assert tracker.get_runtime_info()["effective_device"] == "cuda"
    assert tracker.switch_calls == [
        (str(new_model), "gpu"),
        (str(old_model), "gpu"),
    ]


@pytest.mark.asyncio
async def test_switch_model_reports_operator_recovery_if_runtime_rollback_fails(
    monkeypatch,
    tmp_path,
):
    (
        handler,
        request,
        service,
        tracker,
        _old_model,
        new_model,
        initial_config,
    ) = _model_switch_fixture(tmp_path, failure_stage="save")
    tracker.fail_rollback = True
    monkeypatch.setattr(
        model_routes.Parameters,
        "reload_config",
        staticmethod(lambda strict_dependents=False: True),
    )

    with pytest.raises(HTTPException) as exc_info:
        await model_routes.switch_model(handler, request)

    assert exc_info.value.status_code == 500
    assert "operator recovery is required" in str(exc_info.value.detail)
    assert service.disk_config == initial_config
    assert tracker.get_runtime_info()["model_path"] == str(new_model)
