import hashlib
import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from classes.model_manager import ModelManager, model_manager_kwargs_from_parameters
import classes.model_manager as model_manager_module
from classes.model_artifact_policy import (
    ModelArtifactPolicyError,
    ModelRegistryCorruptionError,
    sha256_file,
)


def _valid_detect_model():
    return {
        "valid": True,
        "num_classes": 1,
        "class_names": ["target"],
        "is_custom": True,
        "task": "detect",
        "output_geometry": "aabb",
        "smarttracker_supported": True,
        "compatibility_notes": [],
    }


def _register_test_model(manager: ModelManager, name: str = "demo.pt") -> Path:
    model_path = manager.models_folder / name
    model_path.write_bytes(b"trusted-model")
    model_path.chmod(0o600)
    digest = sha256_file(model_path)
    manager.provenance.trust_pt(
        model_path,
        sha256=digest,
        source="unit-test",
        expected_digest_verified=True,
        publisher_sha256=digest,
    )
    return model_path


def _use_inprocess_exporter(manager: ModelManager, monkeypatch) -> None:
    def run(source, _expected_path):
        return model_manager_module.YOLO(str(source)).export(format="ncnn")

    monkeypatch.setattr(manager, "_run_ncnn_export_subprocess", run)


class _FakeExportContainment:
    def __init__(self):
        self.admitted = []
        self.cleanup_calls = 0

    def admit_process(self, pid):
        self.admitted.append(pid)

    def cleanup(self):
        self.cleanup_calls += 1


def _use_fake_export_containment(manager: ModelManager, monkeypatch):
    containment = _FakeExportContainment()
    monkeypatch.setattr(manager, "_require_export_process_controls", lambda: None)
    monkeypatch.setattr(manager, "_create_export_containment", lambda: containment)
    return containment


def test_concurrent_same_name_commits_never_overwrite(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    monkeypatch.setattr(manager, "_inspect_trusted_checkpoint", lambda _: _valid_detect_model())
    staged = [manager._stage_bytes(b"first"), manager._stage_bytes(b"second")]
    barrier = threading.Barrier(2)

    def commit(path):
        barrier.wait(timeout=5)
        return manager._commit_staged_model(
            path,
            filename="demo.pt",
            expected_sha256=None,
            trust_model=True,
            source="concurrency_test",
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(commit, path) for path in staged]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result(timeout=10))
                except FileExistsError as exc:
                    outcomes.append(exc)

        assert sum(isinstance(item, dict) for item in outcomes) == 1
        assert sum(isinstance(item, FileExistsError) for item in outcomes) == 1
        assert (tmp_path / "demo.pt").read_bytes() in {b"first", b"second"}
        manager.provenance.verify_pt(tmp_path / "demo.pt")
    finally:
        for path in staged:
            path.unlink(missing_ok=True)


def test_model_manager_rejects_unknown_or_unbounded_policy_values(tmp_path):
    with pytest.raises(ValueError, match="trust_policy"):
        ModelManager(models_folder=str(tmp_path), trust_policy="unknown")
    with pytest.raises(ValueError, match="max_model_bytes"):
        ModelManager(models_folder=str(tmp_path), max_model_bytes=1024 * 1024 * 1024)
    with pytest.raises(ValueError, match="ncnn_export_timeout_seconds"):
        ModelManager(models_folder=str(tmp_path), ncnn_export_timeout_seconds=0)


def test_model_manager_policy_resolves_only_from_grouped_smarttracker_section():
    class Parameters:
        SMART_TRACKER_MODEL_MAX_BYTES = 1
        SMART_TRACKER_MODEL_TRUST_POLICY = "operator_ack_or_digest"
        SmartTracker = {
            "SMART_TRACKER_MODEL_MAX_BYTES": 1234567,
            "SMART_TRACKER_MODEL_TRUST_POLICY": "digest_required",
            "SMART_TRACKER_NCNN_EXPORT_TIMEOUT_SECONDS": 321,
        }

    assert model_manager_kwargs_from_parameters(Parameters) == {
        "max_model_bytes": 1234567,
        "trust_policy": "digest_required",
        "ncnn_export_timeout_seconds": 321,
    }


def test_model_manager_ignores_group_writable_metadata_cache(tmp_path):
    cache_path = tmp_path / ".models.json"
    cache_path.write_text(json.dumps({"demo": {"name": "tampered"}}), encoding="utf-8")
    cache_path.chmod(0o664)

    manager = ModelManager(models_folder=str(tmp_path))

    assert manager.cache == {}


@pytest.mark.asyncio
async def test_cancelled_ingest_waits_for_worker_and_removes_staging(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    worker_started = threading.Event()
    release_worker = threading.Event()

    class Upload:
        def __init__(self):
            self._sent = False

        async def read(self, _size):
            if self._sent:
                return b""
            self._sent = True
            return b"trusted-model"

    def blocking_commit(staged_path, **_kwargs):
        worker_started.set()
        assert release_worker.wait(timeout=5)
        return {
            "success": True,
            "model_id": "demo",
            "model_path": str(staged_path),
            "ncnn_exported": False,
        }

    monkeypatch.setattr(manager, "_commit_staged_model", blocking_commit)
    task = asyncio.create_task(
        manager.upload_model_file(
            Upload(),
            "demo.pt",
            trust_model=True,
        )
    )
    assert await asyncio.to_thread(worker_started.wait, 2)

    task.cancel()
    await asyncio.sleep(0.05)
    assert not task.done()
    assert list(tmp_path.glob(".model-ingest-*.pt"))

    release_worker.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert list(tmp_path.glob(".model-ingest-*.pt")) == []


@pytest.mark.asyncio
async def test_cancelled_upload_read_removes_partial_staging_file(tmp_path):
    manager = ModelManager(models_folder=str(tmp_path))

    class CancelledUpload:
        async def read(self, _size):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await manager._stage_upload_file(CancelledUpload())
    assert list(tmp_path.glob(".model-ingest-*.pt")) == []


@pytest.mark.asyncio
async def test_digest_required_upload_is_rejected_before_checkpoint_inspection(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(
        models_folder=str(tmp_path),
        trust_policy="digest_required",
    )
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: inspection_calls.append(path) or _valid_detect_model(),
    )

    result = await manager.upload_model(
        file_data=b"model",
        filename="demo.pt",
        trust_model=True,
    )

    assert result["success"] is False
    assert "publisher's SHA-256" in result["error"]
    assert inspection_calls == []
    assert not (tmp_path / "demo.pt").exists()


def test_digest_required_local_registration_never_inspects_without_digest(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(
        models_folder=str(tmp_path),
        trust_policy="digest_required",
    )
    model_path = tmp_path / "demo.pt"
    model_path.write_bytes(b"model")
    model_path.chmod(0o600)
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: inspection_calls.append(path) or _valid_detect_model(),
    )

    result = manager.trust_local_model("demo.pt", trust_model=True)

    assert result["success"] is False
    assert "publisher's SHA-256" in result["error"]
    assert inspection_calls == []


@pytest.mark.asyncio
async def test_upload_model_returns_consistent_response_shape(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))

    validation = {
        "valid": True,
        "num_classes": 3,
        "class_names": ["a", "b", "c"],
        "is_custom": True,
        "task": "detect",
        "output_geometry": "aabb",
        "smarttracker_supported": True,
        "compatibility_notes": [],
    }

    monkeypatch.setattr(manager, "validate_model", lambda _: validation)
    monkeypatch.setattr(manager, "_inspect_trusted_checkpoint", lambda _: validation)

    async def fake_export(_):
        return {
            "success": True,
            "ncnn_path": str((tmp_path / "demo_ncnn_model").as_posix()),
            "export_time": 0.12,
        }

    monkeypatch.setattr(manager, "_export_async", fake_export)

    discovered = {
        "demo": {
            "name": "DEMO",
            "path": str((tmp_path / "demo.pt").as_posix()),
            "has_ncnn": True,
            "ncnn_path": str((tmp_path / "demo_ncnn_model").as_posix()),
            "num_classes": 3,
            "class_names": ["a", "b", "c"],
        }
    }
    monkeypatch.setattr(manager, "discover_models", lambda force_rescan=False: discovered)

    result = await manager.upload_model(
        file_data=b"model-bytes",
        filename="demo.pt",
        auto_export_ncnn=True,
        expected_sha256=hashlib.sha256(b"model-bytes").hexdigest(),
        trust_model=True,
    )

    assert result["success"] is True
    assert result["model_id"] == "demo"
    assert "message" in result and result["message"]
    assert result["model_info"]["path"].endswith("demo.pt")
    assert result["ncnn_exported"] is True
    assert result["ncnn_export"]["success"] is True
    assert result["ncnn_path"].endswith("demo_ncnn_model")
    assert result["trust_method"] == "expected_sha256"


@pytest.mark.asyncio
async def test_upload_rejects_path_escape_before_writing(tmp_path):
    manager = ModelManager(models_folder=str(tmp_path / "models"))

    result = await manager.upload_model(
        file_data=b"model",
        filename="../outside.pt",
        trust_model=True,
    )

    assert result["success"] is False
    assert not (tmp_path / "outside.pt").exists()
    assert list(manager.models_folder.glob(".model-ingest-*")) == []


@pytest.mark.asyncio
async def test_upload_requires_explicit_trust_before_model_load(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    load_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: load_calls.append(path) or {"valid": True},
    )

    result = await manager.upload_model(
        file_data=b"model",
        filename="demo.pt",
    )

    assert result["success"] is False
    assert "trust acknowledgement" in result["error"]
    assert load_calls == []
    assert not (tmp_path / "demo.pt").exists()


@pytest.mark.asyncio
async def test_upload_digest_mismatch_is_atomic_and_never_loads(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    load_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: load_calls.append(path) or {"valid": True},
    )

    result = await manager.upload_model(
        file_data=b"model",
        filename="demo.pt",
        expected_sha256="0" * 64,
        trust_model=True,
    )

    assert result["success"] is False
    assert "mismatch" in result["error"]
    assert load_calls == []
    assert not (tmp_path / "demo.pt").exists()
    assert list(tmp_path.glob(".model-ingest-*")) == []


@pytest.mark.asyncio
async def test_exact_digest_bound_upload_retry_is_a_no_execution_replay(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path), trust_policy="digest_required")
    payload = b"publisher-model"
    digest = hashlib.sha256(payload).hexdigest()
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: inspection_calls.append(path) or _valid_detect_model(),
    )

    first = await manager.upload_model(
        file_data=payload,
        filename="demo.pt",
        expected_sha256=digest,
        trust_model=True,
        source="retry-test",
    )
    second = await manager.upload_model(
        file_data=payload,
        filename="demo.pt",
        expected_sha256=digest,
        trust_model=True,
        source="retry-test",
    )

    assert first["success"] is True
    assert first["idempotent_replay"] is False
    assert second["success"] is True
    assert second["idempotent_replay"] is True
    assert second["registration_action_id"] == first["registration_action_id"]
    assert len(inspection_calls) == 1
    assert (tmp_path / "demo.pt").read_bytes() == payload


@pytest.mark.asyncio
async def test_upload_does_not_export_ncnn_by_default(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    validation = {
        "valid": True,
        "num_classes": 1,
        "class_names": ["target"],
        "is_custom": True,
        "task": "detect",
        "output_geometry": "aabb",
        "smarttracker_supported": True,
        "compatibility_notes": [],
    }
    monkeypatch.setattr(manager, "_inspect_trusted_checkpoint", lambda _: validation)
    export_calls = []

    async def fake_export(path):
        export_calls.append(path)
        return {"success": True}

    monkeypatch.setattr(manager, "_export_async", fake_export)

    result = await manager.upload_model(
        file_data=b"model",
        filename="demo.pt",
        trust_model=True,
    )

    assert result["success"] is True
    assert result["ncnn_exported"] is False
    assert export_calls == []


def test_discovery_does_not_load_unregistered_checkpoint(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    (tmp_path / "unknown.pt").write_bytes(b"untrusted")
    load_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: load_calls.append(path) or {"valid": True},
    )

    assert manager.discover_models(force_rescan=True) == {}
    assert load_calls == []


def test_force_rescan_of_registered_model_never_executes_checkpoint(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path))
    _register_test_model(manager)
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: inspection_calls.append(path) or _valid_detect_model(),
    )

    discovered = manager.discover_models(force_rescan=True)

    assert discovered["demo"]["metadata"]["checkpoint_executed"] is False
    assert discovered["demo"]["metadata"]["inspection_required"] is True
    assert inspection_calls == []


def test_read_only_validation_never_executes_checkpoint(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    model = _register_test_model(manager)
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: inspection_calls.append(path) or _valid_detect_model(),
    )

    result = manager.validate_model(model)

    assert result["valid"] is False
    assert result["checkpoint_executed"] is False
    assert inspection_calls == []


def test_checkpoint_inspector_rejects_regular_and_symlink_path_aliases(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path))
    model = tmp_path / "demo.pt"
    model.write_bytes(b"trusted")
    alias = tmp_path / "alias.pt"
    alias.symlink_to(model)
    loader_calls = []
    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(
        model_manager_module,
        "YOLO",
        lambda path: loader_calls.append(path),
    )

    direct = manager._inspect_trusted_checkpoint(model)
    linked = manager._inspect_trusted_checkpoint(alias)

    assert direct["valid"] is False
    assert linked["valid"] is False
    assert direct["checkpoint_executed"] is False
    assert linked["checkpoint_executed"] is False
    assert "format-preserving loader binding" in direct["error"]
    assert "format-preserving loader binding" in linked["error"]
    assert loader_calls == []


def test_digest_required_quarantines_operator_assertion_for_all_execution_paths(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(
        models_folder=str(tmp_path),
        trust_policy="digest_required",
    )
    model = tmp_path / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    manager.provenance.trust_pt(
        model,
        sha256=sha256_file(model),
        source="legacy-lab",
        expected_digest_verified=False,
    )
    inspection_calls = []
    export_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: inspection_calls.append(path) or _valid_detect_model(),
    )
    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_run_ncnn_export_subprocess",
        lambda *args: export_calls.append(args),
    )

    assert manager.discover_models(force_rescan=True) == {}
    assert manager.quarantined_models["demo"]["trust_method"] == "operator_assertion"
    validation = manager.validate_model(
        model,
        allow_checkpoint_execution=True,
    )
    export = manager.export_to_ncnn(model)

    assert validation["valid"] is False
    assert "descriptor-bound publisher digest" in validation["error"]
    assert export["success"] is False
    assert "descriptor-bound publisher digest" in export["error"]
    assert inspection_calls == []
    assert export_calls == []


def test_digest_required_rejects_legacy_self_asserted_publisher_fields(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path), trust_policy="digest_required")
    model = tmp_path / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    digest = sha256_file(model)
    manager.provenance.trust_pt(
        model,
        sha256=digest,
        source="legacy-record",
        expected_digest_verified=False,
    )
    payload = manager.provenance.load()
    record = payload["artifacts"]["demo.pt"]
    record["trust_method"] = "expected_sha256"
    record["publisher_sha256"] = digest
    record["registration_receipt"]["trust_method"] = "expected_sha256"
    record["registration_receipt"]["publisher_sha256"] = digest
    manager.provenance.registry_path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    manager.provenance.registry_path.chmod(0o600)
    inspection_calls = []
    export_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: inspection_calls.append(path) or _valid_detect_model(),
    )
    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_run_ncnn_export_subprocess",
        lambda *args: export_calls.append(args),
    )

    assert manager.discover_models(force_rescan=True) == {}
    validation = manager.validate_model(model, allow_checkpoint_execution=True)
    export = manager.export_to_ncnn(model)

    assert validation["valid"] is False
    assert "publisher-digest evidence is incomplete" in validation["error"]
    assert export["success"] is False
    assert "publisher-digest evidence is incomplete" in export["error"]
    assert inspection_calls == []
    assert export_calls == []


def test_explicit_same_artifact_registration_replaces_incomplete_legacy_record(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path), trust_policy="digest_required")
    model = tmp_path / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    digest = sha256_file(model)
    manager.provenance.trust_pt(
        model,
        sha256=digest,
        source="legacy-record",
        expected_digest_verified=False,
    )
    payload = manager.provenance.load()
    record = payload["artifacts"]["demo.pt"]
    record["trust_method"] = "expected_sha256"
    record["publisher_sha256"] = digest
    record["registration_receipt"]["trust_method"] = "expected_sha256"
    record["registration_receipt"]["publisher_sha256"] = digest
    manager.provenance.registry_path.write_text(json.dumps(payload), encoding="utf-8")
    manager.provenance.registry_path.chmod(0o600)
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda binding: inspection_calls.append(binding) or _valid_detect_model(),
    )

    first = manager.trust_local_model(
        "demo.pt",
        expected_sha256=digest,
        trust_model=True,
        source="legacy-upgrade",
    )
    second = manager.trust_local_model(
        "demo.pt",
        expected_sha256=digest,
        trust_model=True,
        source="legacy-upgrade",
    )

    assert first["success"] is True
    assert first["idempotent_replay"] is False
    assert second["success"] is True
    assert second["idempotent_replay"] is True
    assert len(inspection_calls) == 1
    upgraded = manager.provenance.verify_pt(model)
    assert upgraded["publisher_sha256"] == digest
    assert upgraded["publisher_digest_evidence_version"] == 1
    assert upgraded["registration_receipt"][
        "publisher_digest_evidence_version"
    ] == 1
    assert second["registration_action_id"] == first["registration_action_id"]


@pytest.mark.asyncio
async def test_same_artifact_upload_replaces_incomplete_legacy_record_without_overwrite(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path), trust_policy="digest_required")
    content = b"trusted"
    model = tmp_path / "demo.pt"
    model.write_bytes(content)
    model.chmod(0o600)
    original_inode = model.stat().st_ino
    digest = sha256_file(model)
    manager.provenance.trust_pt(
        model,
        sha256=digest,
        source="legacy-record",
        expected_digest_verified=False,
    )
    payload = manager.provenance.load()
    record = payload["artifacts"]["demo.pt"]
    record.pop("registration_receipt")
    manager.provenance.registry_path.write_text(json.dumps(payload), encoding="utf-8")
    manager.provenance.registry_path.chmod(0o600)
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda binding: inspection_calls.append(binding) or _valid_detect_model(),
    )

    result = await manager.upload_model(
        file_data=content,
        filename="demo.pt",
        expected_sha256=digest,
        trust_model=True,
        source="legacy-upload-upgrade",
    )

    assert result["success"] is True
    assert result["idempotent_replay"] is False
    assert len(inspection_calls) == 1
    assert model.stat().st_ino == original_inode
    assert model.read_bytes() == content
    assert list(tmp_path.glob(".model-ingest-*")) == []
    assert manager.provenance.verify_pt(model)[
        "publisher_digest_evidence_version"
    ] == 1


def test_legacy_reregistration_refuses_contradictory_record_before_inspection(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path), trust_policy="digest_required")
    model = tmp_path / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    digest = sha256_file(model)
    manager.provenance.trust_pt(
        model,
        sha256=digest,
        source="legacy-record",
        expected_digest_verified=False,
    )
    payload = manager.provenance.load()
    payload["artifacts"]["demo.pt"]["publisher_sha256"] = "f" * 64
    manager.provenance.registry_path.write_text(json.dumps(payload), encoding="utf-8")
    manager.provenance.registry_path.chmod(0o600)
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda binding: inspection_calls.append(binding) or _valid_detect_model(),
    )

    result = manager.trust_local_model(
        "demo.pt",
        expected_sha256=digest,
        trust_model=True,
        source="legacy-upgrade",
    )

    assert result["success"] is False
    assert "contradicts" in result["error"]
    assert inspection_calls == []


def test_discovery_never_reports_corrupt_registry_as_empty_inventory(tmp_path):
    manager = ModelManager(models_folder=str(tmp_path))
    registry = tmp_path / ".model-provenance.json"
    registry.write_text("{not-json", encoding="utf-8")
    registry.chmod(0o600)

    with pytest.raises(ModelRegistryCorruptionError, match="registry is unreadable"):
        manager.discover_models(force_rescan=True)


def test_validation_refuses_artifact_changed_after_registration(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    model = tmp_path / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    manager.provenance.trust_pt(
        model,
        sha256=sha256_file(model),
        source="test",
        expected_digest_verified=True,
        publisher_sha256=sha256_file(model),
    )
    model.write_bytes(b"changed")
    load_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: load_calls.append(path) or {"valid": True},
    )

    result = manager.validate_model(model, allow_checkpoint_execution=True)

    assert result["valid"] is False
    assert "digest changed" in result["error"]
    assert load_calls == []


def test_local_registration_rejects_path_swap_after_operator_observation(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path))
    model = tmp_path / "demo.pt"
    model.write_bytes(b"operator-observed")
    model.chmod(0o600)
    replacement = tmp_path / "replacement.pt"
    replacement.write_bytes(b"replacement")
    replacement.chmod(0o600)
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: inspection_calls.append(path) or _valid_detect_model(),
    )

    with manager.observe_local_model("demo.pt") as observation:
        observed = observation.observed_sha256
        os.replace(replacement, model)
        result = manager.trust_observed_local_model(
            observation,
            trust_model=True,
            source="toctou-test",
        )

    assert result["success"] is False
    assert "canonical store binding" in result["error"]
    assert observed == hashlib.sha256(b"operator-observed").hexdigest()
    assert inspection_calls == []


def test_registration_receipt_is_durable_and_distinguishes_digest_roles(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path))
    model = tmp_path / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    digest = sha256_file(model)
    inspection_calls = []
    monkeypatch.setattr(
        manager,
        "_inspect_trusted_checkpoint",
        lambda path: inspection_calls.append(path) or _valid_detect_model(),
    )

    first = manager.trust_local_model(
        "demo.pt",
        expected_sha256=digest,
        trust_model=True,
        source="receipt-test",
    )
    second = manager.trust_local_model(
        "demo.pt",
        expected_sha256=digest,
        trust_model=True,
        source="receipt-test",
    )

    assert first["success"] is True
    assert second["success"] is True
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert inspection_calls and len(inspection_calls) == 1
    assert first["observed_sha256"] == digest
    assert first["publisher_sha256"] == digest
    assert first["registration_action_id"] == second["registration_action_id"]
    persisted = manager.provenance.verify_pt(model)
    assert persisted["registration_receipt"]["action_id"] == first[
        "registration_action_id"
    ]
    assert persisted["registration_receipt"][
        "publisher_digest_evidence_version"
    ] == 1


def test_existing_ncnn_is_verified_with_callers_exclusive_lease(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path))
    model = _register_test_model(manager)
    export = tmp_path / "demo_ncnn_model"
    export.mkdir(mode=0o700)
    for name in ("model.bin", "model.param"):
        path = export / name
        path.write_bytes(name.encode("ascii"))
        path.chmod(0o600)
    manager.provenance.trust_ncnn(model, export)
    digest = sha256_file(model)
    monkeypatch.setattr(manager, "_inspect_trusted_checkpoint", lambda _: _valid_detect_model())

    result = manager.trust_local_model(
        "demo.pt",
        expected_sha256=digest,
        trust_model=True,
        source="nested-lease-test",
    )

    assert result["success"] is True
    assert result["model_info"]["has_ncnn"] is True


def test_export_worker_cannot_change_parent_cuda_environment(tmp_path, monkeypatch):
    manager = ModelManager(
        models_folder=str(tmp_path),
        ncnn_export_timeout_seconds=2,
    )
    pt_file = tmp_path / "demo.pt"
    pt_file.write_bytes(b"pt")
    pt_file.chmod(0o600)
    manager.provenance.trust_pt(
        pt_file,
        sha256=sha256_file(pt_file),
        source="test",
        expected_digest_verified=True,
        publisher_sha256=sha256_file(pt_file),
    )
    containment = _use_fake_export_containment(manager, monkeypatch)

    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_ncnn_export_worker_command",
        lambda _source, _result: [
            sys.executable,
            "-c",
            (
                "import os,sys; "
                "os.environ['CUDA_VISIBLE_DEVICES']=''; "
                "sys.exit(7)"
            ),
        ],
    )

    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    result = manager.export_to_ncnn(pt_file)

    assert result["success"] is False
    assert "worker failed" in result["error"]
    assert model_manager_module.os.environ.get("CUDA_VISIBLE_DEVICES") == "0"
    assert containment.admitted
    assert containment.cleanup_calls == 1


def test_export_environment_is_minimal_and_drops_proxy_and_secret_state(
    tmp_path,
    monkeypatch,
):
    manager = ModelManager(models_folder=str(tmp_path))
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid")
    monkeypatch.setenv("PIXEAGLE_SECRET_TEST_VALUE", "secret")

    environment = manager._minimal_export_environment(tmp_path)

    assert "HTTPS_PROXY" not in environment
    assert "PIXEAGLE_SECRET_TEST_VALUE" not in environment
    assert environment["YOLO_OFFLINE"] == "true"
    assert environment["YOLO_AUTOINSTALL"] == "false"
    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert environment["HOME"] == str(tmp_path)


def test_export_reaps_descendant_process_group_after_leader_success(tmp_path):
    manager = ModelManager(models_folder=str(tmp_path))
    child_pid_path = tmp_path / "child.pid"
    script = (
        "import subprocess,sys; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c',"
        "'import time; time.sleep(30)'], stdin=subprocess.DEVNULL, "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "Path(sys.argv[1]).write_text(str(child.pid), encoding='ascii')"
    )
    leader = subprocess.Popen(
        [sys.executable, "-c", script, str(child_pid_path)],
        start_new_session=True,
        close_fds=True,
    )
    child_pid = None
    try:
        assert leader.wait(timeout=5) == 0
        deadline = time.monotonic() + 2
        while not child_pid_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        child_pid = int(child_pid_path.read_text(encoding="ascii"))
        assert child_pid in manager._live_process_group_members(leader.pid)

        manager._reap_export_process_group(leader, leader.pid)

        assert manager._live_process_group_members(leader.pid) == []
    finally:
        if child_pid is not None:
            try:
                os.kill(child_pid, 9)
            except ProcessLookupError:
                pass


def test_successful_export_containment_kills_setsid_descendant(tmp_path, monkeypatch):
    manager = ModelManager(
        models_folder=str(tmp_path),
        ncnn_export_timeout_seconds=2,
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir(mode=0o700)
    source = workspace / "demo.pt"
    source.write_bytes(b"trusted")
    source.chmod(0o600)
    expected_path = workspace / "demo_ncnn_model"
    worker_pid_path = workspace / "worker.pid"
    child_pid_path = workspace / "escaped.pid"
    script = (
        "import os,subprocess,sys; from pathlib import Path; "
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'], "
        "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
        "stderr=subprocess.DEVNULL,start_new_session=True); "
        "Path('worker.pid').write_text(str(os.getpid()),encoding='ascii'); "
        "Path('escaped.pid').write_text(str(child.pid),encoding='ascii')"
    )
    monkeypatch.setattr(
        manager,
        "_ncnn_export_worker_command",
        lambda _source, _result: [sys.executable, "-c", script],
    )

    def fake_worker_json(_path, *, expected_uid, max_bytes, label):  # noqa: ARG001
        if label == "control receipt":
            worker_pid = int(worker_pid_path.read_text(encoding="ascii"))
            limits = {
                "address_space_bytes": model_manager_module.NCNN_EXPORT_ADDRESS_SPACE_LIMIT_BYTES,
                "core_bytes": 0,
                "cpu_seconds": 7,
                "file_size_bytes": model_manager_module.DEFAULT_MAX_EXPORT_BYTES,
                "open_files": model_manager_module.NCNN_EXPORT_OPEN_FILES_LIMIT,
                "processes": model_manager_module.NCNN_EXPORT_MAX_UID_TASKS,
            }
            return {
                "schema_version": 1,
                "pid": worker_pid,
                "process_group_id": worker_pid,
                "session_id": worker_pid,
                "limits": {
                    name: {"soft": value, "hard": value}
                    for name, value in limits.items()
                },
            }
        return {"returned_path": str(expected_path)}

    monkeypatch.setattr(manager, "_read_worker_json", fake_worker_json)
    child_pid = None
    try:
        try:
            returned = manager._run_ncnn_export_subprocess(source, expected_path)
        except ModelArtifactPolicyError as exc:
            if "cgroup" in str(exc).lower():
                pytest.skip(f"delegated cgroup-v2 unavailable: {exc}")
            raise
        child_pid = int(child_pid_path.read_text(encoding="ascii"))
        assert returned == str(expected_path)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                raw = Path(f"/proc/{child_pid}/stat").read_text(encoding="ascii")
            except FileNotFoundError:
                break
            _, separator, suffix = raw.rpartition(") ")
            if separator and suffix.split()[0] in {"X", "Z"}:
                break
            time.sleep(0.02)
        else:
            pytest.fail("setsid descendant survived successful export cleanup")
    finally:
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_export_to_ncnn_returns_clear_error_when_pnnx_missing(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    pt_file = tmp_path / "demo.pt"
    pt_file.write_bytes(b"pt")
    pt_file.chmod(0o600)
    manager.provenance.trust_pt(
        pt_file,
        sha256=sha256_file(pt_file),
        source="test",
        expected_digest_verified=True,
        publisher_sha256=sha256_file(pt_file),
    )

    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: False)

    result = manager.export_to_ncnn(pt_file)

    assert result["success"] is False
    assert "pnnx" in result["error"].lower()


def test_ncnn_export_worker_timeout_is_bounded_and_cleans_workspace(tmp_path, monkeypatch):
    manager = ModelManager(
        models_folder=str(tmp_path),
        ncnn_export_timeout_seconds=0.1,
    )
    pt_file = _register_test_model(manager)
    containment = _use_fake_export_containment(manager, monkeypatch)
    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_ncnn_export_worker_command",
        lambda _source, _result: [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ],
    )

    result = manager.export_to_ncnn(pt_file)

    assert result["success"] is False
    assert "timeout" in result["error"]
    assert list(tmp_path.glob(".ncnn-export-*")) == []
    assert containment.cleanup_calls == 1


def test_ncnn_export_worker_workspace_quota_is_enforced(tmp_path, monkeypatch):
    manager = ModelManager(
        models_folder=str(tmp_path),
        max_model_bytes=4096,
        ncnn_export_timeout_seconds=2,
    )
    pt_file = _register_test_model(manager)
    containment = _use_fake_export_containment(manager, monkeypatch)
    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)
    monkeypatch.setattr(model_manager_module, "DEFAULT_MAX_EXPORT_BYTES", 1024)
    monkeypatch.setattr(model_manager_module, "NCNN_EXPORT_WORKSPACE_OVERHEAD_BYTES", 0)
    monkeypatch.setattr(
        manager,
        "_ncnn_export_worker_command",
        lambda _source, _result: [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('oversized.bin').write_bytes(b'x' * 100000)",
        ],
    )

    result = manager.export_to_ncnn(pt_file)

    assert result["success"] is False
    assert "byte quota" in result["error"]
    assert list(tmp_path.glob(".ncnn-export-*")) == []
    assert containment.cleanup_calls == 1


def test_export_to_ncnn_commits_only_exact_workspace_output(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    pt_file = _register_test_model(manager)
    loaded_paths = []

    class FakeYOLO:
        def __init__(self, source):
            self.source = Path(source)
            loaded_paths.append(self.source)

        def export(self, format="ncnn"):
            assert format == "ncnn"
            output = self.source.parent / "demo_ncnn_model"
            output.mkdir()
            (output / "model.bin").write_bytes(b"weights")
            (output / "model.param").write_text("parameters", encoding="utf-8")
            return str(output)

    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(model_manager_module, "YOLO", FakeYOLO)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)
    _use_inprocess_exporter(manager, monkeypatch)

    result = manager.export_to_ncnn(pt_file)
    replay = manager.export_to_ncnn(pt_file)

    export_path = tmp_path / "demo_ncnn_model"
    assert result["success"] is True
    assert result["idempotent_replay"] is False
    assert replay["success"] is True
    assert replay["idempotent_replay"] is True
    assert replay["artifact_sha256"] == result["artifact_sha256"]
    assert len(loaded_paths) == 1
    assert result["ncnn_path"] == str(export_path)
    assert loaded_paths[0].parent.name.startswith(".ncnn-export-demo-")
    assert loaded_paths[0].parent.parent == tmp_path
    assert list(tmp_path.glob(".ncnn-export-*")) == []
    assert export_path.stat().st_mode & 0o777 == 0o700
    assert (export_path / "model.bin").stat().st_mode & 0o777 == 0o600
    assert (export_path / "model.param").stat().st_mode & 0o777 == 0o600
    assert manager.provenance.verify_ncnn(export_path)["sha256"] == result[
        "artifact_sha256"
    ]


def test_ncnn_export_rejects_too_many_generated_entries(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    pt_file = _register_test_model(manager)

    class ManyFilesYOLO:
        def __init__(self, source):
            self.source = Path(source)

        def export(self, format="ncnn"):  # noqa: ARG002
            output = self.source.parent / "demo_ncnn_model"
            output.mkdir()
            for index in range(129):
                (output / f"part-{index:03d}.bin").write_bytes(b"x")
            (output / "model.param").write_bytes(b"parameters")
            return str(output)

    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(model_manager_module, "YOLO", ManyFilesYOLO)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)
    _use_inprocess_exporter(manager, monkeypatch)

    result = manager.export_to_ncnn(pt_file)

    assert result["success"] is False
    assert "entry limit" in result["error"]
    assert list(tmp_path.glob(".ncnn-export-*")) == []


def test_export_to_ncnn_never_overwrites_existing_export(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    pt_file = _register_test_model(manager)
    existing = tmp_path / "demo_ncnn_model"
    existing.mkdir(mode=0o700)
    marker = existing / "operator-data"
    marker.write_bytes(b"preserve")
    marker.chmod(0o600)

    class UnexpectedYOLO:
        def __init__(self, _source):
            raise AssertionError("Exporter must not run when the destination exists")

    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(model_manager_module, "YOLO", UnexpectedYOLO)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)

    result = manager.export_to_ncnn(pt_file)

    assert result["success"] is False
    assert result["status_code"] == 409
    assert marker.read_bytes() == b"preserve"
    assert list(tmp_path.glob(".ncnn-export-*")) == []


def test_export_to_ncnn_rejects_foreign_returned_path(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    pt_file = _register_test_model(manager)
    foreign = tmp_path / "unrelated_ncnn_model"
    foreign.mkdir(mode=0o700)
    (foreign / "model.bin").write_bytes(b"unrelated")
    (foreign / "model.param").write_bytes(b"unrelated")

    class ForeignPathYOLO:
        def __init__(self, source):
            self.source = Path(source)

        def export(self, format="ncnn"):  # noqa: ARG002
            return str(foreign)

    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(model_manager_module, "YOLO", ForeignPathYOLO)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)
    _use_inprocess_exporter(manager, monkeypatch)

    result = manager.export_to_ncnn(pt_file)

    assert result["success"] is False
    assert result["status_code"] == 422
    assert "outside the dedicated export workspace" in result["error"]
    assert not (tmp_path / "demo_ncnn_model").exists()
    assert list(tmp_path.glob(".ncnn-export-*")) == []


def test_export_returns_busy_to_concurrent_delete_without_blocking(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    pt_file = _register_test_model(manager)
    export_started = threading.Event()
    permit_export = threading.Event()
    delete_finished = threading.Event()

    class BlockingYOLO:
        def __init__(self, source):
            self.source = Path(source)

        def export(self, format="ncnn"):  # noqa: ARG002
            export_started.set()
            assert permit_export.wait(timeout=5)
            output = self.source.parent / "demo_ncnn_model"
            output.mkdir()
            (output / "model.bin").write_bytes(b"weights")
            (output / "model.param").write_bytes(b"parameters")
            return str(output)

    monkeypatch.setattr(model_manager_module, "ULTRALYTICS_AVAILABLE", True)
    monkeypatch.setattr(model_manager_module, "YOLO", BlockingYOLO)
    monkeypatch.setattr(manager, "_pnnx_available", lambda: True)
    _use_inprocess_exporter(manager, monkeypatch)

    with ThreadPoolExecutor(max_workers=2) as executor:
        export_future = executor.submit(manager.export_to_ncnn, pt_file)
        assert export_started.wait(timeout=5)

        def delete_model():
            result = manager.delete_model("demo")
            delete_finished.set()
            return result

        delete_future = executor.submit(delete_model)
        assert delete_finished.wait(timeout=1)
        delete_result = delete_future.result(timeout=1)
        assert delete_result["success"] is False
        assert delete_result["status_code"] == 409
        permit_export.set()
        export_result = export_future.result(timeout=5)

    assert export_result["success"] is True
    assert pt_file.exists()
    assert (tmp_path / "demo_ncnn_model").exists()
    assert list(tmp_path.glob(".ncnn-export-*")) == []

    cleanup_result = manager.delete_model("demo")
    assert cleanup_result["success"] is True
    assert not pt_file.exists()
    assert not (tmp_path / "demo_ncnn_model").exists()


def test_model_identifier_helpers_resolve_pt_and_ncnn_identifiers(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    discovered = {
        "demo": {
            "name": "DEMO",
            "path": str((tmp_path / "demo.pt").as_posix()),
            "class_names": ["person", "car"],
            "num_classes": 2,
        }
    }
    monkeypatch.setattr(manager, "discover_models", lambda force_rescan=False: discovered)

    assert manager.normalize_model_id("demo") == "demo"
    assert manager.normalize_model_id("demo.pt") == "demo"
    assert manager.normalize_model_id(f"{tmp_path.as_posix()}/demo.pt") == "demo"
    assert manager.normalize_model_id(f"{tmp_path.as_posix()}/demo_ncnn_model") == "demo"

    assert manager.get_model_info("demo.pt") == discovered["demo"]
    assert manager.get_model_info(f"{tmp_path.as_posix()}/demo_ncnn_model") == discovered["demo"]


def test_get_model_labels_returns_cleaned_labels(tmp_path, monkeypatch):
    manager = ModelManager(models_folder=str(tmp_path))
    discovered = {
        "demo": {
            "name": "DEMO",
            "path": str((tmp_path / "demo.pt").as_posix()),
            "class_names": ["person", "", "car", "   "],
            "num_classes": 4,
        }
    }
    monkeypatch.setattr(manager, "discover_models", lambda force_rescan=False: discovered)

    model_info, labels = manager.get_model_labels("demo.pt")
    assert model_info == discovered["demo"]
    assert labels == ["person", "car"]
