"""Adversarial tests for executable model-artifact trust policy."""

from __future__ import annotations

import json
import multiprocessing
import os
import threading
import time
from pathlib import Path

import pytest

import classes.model_artifact_policy as artifact_policy
from classes.model_artifact_policy import (
    NCNN_MANIFEST_SCHEMA_VERSION,
    NCNN_MANIFEST_DIGEST_DOMAIN,
    canonical_ncnn_manifest_descriptor,
    ModelArtifactPolicyError,
    ModelIngestLease,
    ModelProvenanceStore,
    ModelStoreBusyError,
    ModelStoreLease,
    normalize_sha256,
    ncnn_manifest_sha256,
    resolve_model_path,
    sha256_descriptor,
    sha256_file,
    validate_ncnn_manifest,
    validate_model_filename,
    validate_models_root,
)


def _hold_store_lease_process(root, exclusive, ready, release):
    with ModelStoreLease(Path(root), exclusive=exclusive, timeout_seconds=2):
        ready.set()
        release.wait(5)


def _secure_models_root(tmp_path: Path) -> Path:
    root = tmp_path / "models"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


@pytest.mark.parametrize(
    "name",
    ["../escape.pt", "sub/model.pt", "/tmp/model.pt", "model.onnx", ".pt"],
)
def test_model_filename_policy_rejects_unsafe_names(name):
    with pytest.raises(ModelArtifactPolicyError):
        validate_model_filename(name)


def test_model_path_policy_rejects_final_symlink(tmp_path):
    root = _secure_models_root(tmp_path)
    outside = tmp_path / "outside.pt"
    outside.write_bytes(b"model")
    (root / "linked.pt").symlink_to(outside)

    with pytest.raises(ModelArtifactPolicyError, match="Symbolic-link"):
        resolve_model_path(root, "linked.pt")


def test_provenance_rejects_lexical_models_root_alias(tmp_path):
    root = _secure_models_root(tmp_path)
    model = root / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    store = ModelProvenanceStore(root)
    store.trust_pt(
        model,
        sha256=sha256_file(model),
        source="unit-test",
        expected_digest_verified=True,
        publisher_sha256=sha256_file(model),
    )
    alias = tmp_path / "models-alias"
    alias.symlink_to(root, target_is_directory=True)

    with pytest.raises(ModelArtifactPolicyError, match="lexical aliases"):
        store.verify_pt(alias / "demo.pt")


def test_models_root_is_owner_only_and_create_mode_tightens_permissions(tmp_path):
    root = tmp_path / "models"
    root.mkdir(mode=0o755)
    root.chmod(0o755)

    with pytest.raises(ModelArtifactPolicyError, match="0700"):
        validate_models_root(root)

    assert validate_models_root(root, create=True) == root.resolve()
    assert root.stat().st_mode & 0o777 == 0o700


def test_store_lease_can_be_closed_from_another_thread(tmp_path):
    root = _secure_models_root(tmp_path)
    lease = ModelStoreLease(root, exclusive=False)
    lease.__enter__()

    closer = threading.Thread(target=lease.close)
    closer.start()
    closer.join(timeout=2)
    assert not closer.is_alive()

    with ModelStoreLease(root, exclusive=True, timeout_seconds=0):
        pass


def test_store_lease_cannot_be_reentered_from_another_thread(tmp_path):
    root = _secure_models_root(tmp_path)
    lease = ModelStoreLease(root, exclusive=False)
    lease.__enter__()
    outcomes = []

    def reenter():
        try:
            lease.__enter__()
        except Exception as exc:  # Test captures the exact fail-closed type below.
            outcomes.append(exc)

    worker = threading.Thread(target=reenter)
    worker.start()
    worker.join(timeout=2)
    try:
        assert not worker.is_alive()
        assert len(outcomes) == 1
        assert isinstance(outcomes[0], ModelStoreBusyError)
    finally:
        lease.close()


def test_store_lease_excludes_a_real_second_process(tmp_path):
    root = _secure_models_root(tmp_path)
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_store_lease_process,
        args=(str(root), False, ready, release),
    )
    process.start()
    try:
        assert ready.wait(5)
        with pytest.raises(ModelStoreBusyError, match="busy"):
            ModelStoreLease(root, exclusive=True, timeout_seconds=0).__enter__()
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(2)
    assert process.exitcode == 0


def test_nested_independent_ingest_lease_fails_immediately(tmp_path):
    root = _secure_models_root(tmp_path)
    with ModelIngestLease(root):
        started = time.monotonic()
        with pytest.raises(ModelArtifactPolicyError, match="Nested model-store leases"):
            ModelIngestLease(root, timeout_seconds=5).__enter__()
        assert time.monotonic() - started < 0.5


def test_nested_shared_reads_work_but_shared_to_exclusive_upgrade_is_busy(tmp_path):
    root = _secure_models_root(tmp_path)
    with ModelStoreLease(root, exclusive=False):
        with ModelStoreLease(root, exclusive=False):
            pass
        started = time.monotonic()
        with pytest.raises(ModelStoreBusyError, match="active shared runtime lease"):
            ModelStoreLease(root, exclusive=True, timeout_seconds=5).__enter__()
        assert time.monotonic() - started < 0.5


def test_model_store_lease_descriptors_are_closed_in_fork_child(tmp_path):
    if not hasattr(os, "fork"):
        pytest.skip("fork descriptor inheritance is POSIX-specific")
    root = _secure_models_root(tmp_path)
    read_fd, write_fd = os.pipe()
    with ModelStoreLease(root, exclusive=False) as lease:
        inherited_lock_fd = lease._state.lock_fd
        child_pid = os.fork()
        if child_pid == 0:
            os.close(read_fd)
            try:
                os.fstat(inherited_lock_fd)
            except OSError:
                outcome = b"closed"
            else:
                outcome = b"open"
            os.write(write_fd, outcome)
            os.close(write_fd)
            os._exit(0)
        os.close(write_fd)
        outcome = os.read(read_fd, 16)
        os.close(read_fd)
        _, status = os.waitpid(child_pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        assert outcome == b"closed"
        os.fstat(inherited_lock_fd)


def test_loader_binding_preserves_pt_name_and_pinned_inode(tmp_path):
    root = _secure_models_root(tmp_path)
    model = root / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    replacement = root / "replacement.pt"
    replacement.write_bytes(b"replacement")
    replacement.chmod(0o600)

    with ModelStoreLease(root, exclusive=False) as lease:
        descriptor = lease.pin_model(model.name)
        binding = lease.loader_binding(descriptor, model.name)
        loader_path = binding.verified_path()
        assert loader_path.name == "demo.pt"
        assert loader_path.is_symlink()
        assert os.readlink(loader_path) == f"/proc/self/fd/{descriptor}"

        os.replace(replacement, model)
        assert loader_path.read_bytes() == b"trusted"
        with pytest.raises(ModelArtifactPolicyError, match="canonical store binding"):
            lease.assert_descriptor_binding(model.name, descriptor)

        lease.release_descriptor(descriptor)
        assert not os.path.lexists(loader_path)
        assert not loader_path.parent.exists()


def test_loader_binding_preserves_ncnn_directory_name(tmp_path):
    root = _secure_models_root(tmp_path)
    export = root / "demo_ncnn_model"
    export.mkdir(mode=0o700)

    with ModelStoreLease(root, exclusive=False) as lease:
        descriptor = lease.pin_ncnn_directory(export.name)
        binding = lease.loader_binding(
            descriptor,
            export.name,
            directory=True,
        )
        loader_path = binding.verified_path()
        assert loader_path.name == "demo_ncnn_model"
        assert loader_path.is_dir()
        assert os.readlink(loader_path) == f"/proc/self/fd/{descriptor}"

    assert not os.path.lexists(loader_path)
    assert not loader_path.parent.exists()


def test_sha256_policy_rejects_empty_and_oversized_files(tmp_path):
    empty = tmp_path / "empty.pt"
    empty.write_bytes(b"")
    empty.chmod(0o600)
    with pytest.raises(ModelArtifactPolicyError, match="empty"):
        sha256_file(empty)

    oversized = tmp_path / "oversized.pt"
    oversized.write_bytes(b"12345")
    oversized.chmod(0o600)
    with pytest.raises(ModelArtifactPolicyError, match="exceeds"):
        sha256_file(oversized, max_bytes=4)


def test_provenance_registry_is_owner_only_and_detects_mutation(tmp_path):
    root = _secure_models_root(tmp_path)
    model = root / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    digest = sha256_file(model)
    store = ModelProvenanceStore(root)

    record = store.trust_pt(
        model,
        sha256=digest,
        source="unit-test",
        expected_digest_verified=True,
        publisher_sha256=digest,
    )

    assert record["trust_method"] == "expected_sha256"
    assert store.registry_path.stat().st_mode & 0o777 == 0o600
    assert store.verify_pt(model)["sha256"] == digest

    model.write_bytes(b"modified")
    with pytest.raises(ModelArtifactPolicyError, match="digest changed"):
        store.verify_pt(model)


def test_publisher_verified_provenance_requires_explicit_publisher_digest(tmp_path):
    root = _secure_models_root(tmp_path)
    model = root / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    digest = sha256_file(model)

    with pytest.raises(ModelArtifactPolicyError, match="explicitly supplied"):
        ModelProvenanceStore(root).trust_pt(
            model,
            sha256=digest,
            source="unit-test",
            expected_digest_verified=True,
        )


def test_sha256_descriptor_rejects_short_read_even_when_stat_size_is_unchanged(
    tmp_path,
    monkeypatch,
):
    model = tmp_path / "model.pt"
    model.write_bytes(b"descriptor-content")
    model.chmod(0o600)
    descriptor = os.open(model, os.O_RDONLY)
    real_read = artifact_policy.os.read

    def adversarial_read(fd, size):
        if fd == descriptor:
            return b""
        return real_read(fd, size)

    monkeypatch.setattr(artifact_policy.os, "read", adversarial_read)
    try:
        with pytest.raises(ModelArtifactPolicyError, match="shorter"):
            sha256_descriptor(
                descriptor,
                expected_uid=os.geteuid(),
            )
    finally:
        os.close(descriptor)


def test_ncnn_manifest_records_files_directories_sizes_and_content_digests(tmp_path):
    root = _secure_models_root(tmp_path)
    export = root / "demo_ncnn_model"
    nested = export / "assets"
    empty = export / "empty"
    nested.mkdir(parents=True, mode=0o700)
    empty.mkdir(mode=0o700)
    export.chmod(0o700)
    nested.chmod(0o700)
    empty.chmod(0o700)
    files = {
        export / "model.bin": b"weights",
        export / "model.param": b"parameters",
        nested / "labels.txt": b"target\n",
    }
    for path, content in files.items():
        path.write_bytes(content)
        path.chmod(0o600)

    descriptor = os.open(export, os.O_RDONLY | os.O_DIRECTORY)
    try:
        result = canonical_ncnn_manifest_descriptor(
            descriptor,
            expected_uid=os.geteuid(),
        )
    finally:
        os.close(descriptor)

    manifest = result["manifest"]
    entries = {entry["path"]: entry for entry in manifest["entries"]}
    assert manifest["schema_version"] == NCNN_MANIFEST_SCHEMA_VERSION
    assert manifest["digest_domain"] == NCNN_MANIFEST_DIGEST_DOMAIN
    assert entries["assets"]["entry_type"] == "directory"
    assert entries["empty"]["entry_type"] == "directory"
    assert entries["empty"]["size_bytes"] == 0
    assert entries["assets/labels.txt"]["entry_type"] == "file"
    assert entries["assets/labels.txt"]["size_bytes"] == len(b"target\n")
    assert result["size_bytes"] == sum(len(content) for content in files.values())
    assert result["manifest_sha256"] == ncnn_manifest_sha256(manifest)
    assert len({entry["path"] for entry in manifest["entries"]}) == len(entries)


def test_ncnn_manifest_rejects_file_directory_structural_collision():
    collision = {
        "schema_version": NCNN_MANIFEST_SCHEMA_VERSION,
        "digest_domain": NCNN_MANIFEST_DIGEST_DOMAIN,
        "hash_algorithm": "sha256",
        "root": {
            "entry_type": "directory",
            "path": ".",
            "size_bytes": 2,
            "sha256": "0" * 64,
        },
        "entries": [
            {
                "entry_type": "file",
                "path": "node",
                "size_bytes": 1,
                "sha256": "1" * 64,
            },
            {
                "entry_type": "file",
                "path": "node/child",
                "size_bytes": 1,
                "sha256": "2" * 64,
            },
        ],
    }

    with pytest.raises(ModelArtifactPolicyError, match="structural collision"):
        validate_ncnn_manifest(collision)


def test_ncnn_manifest_digest_changes_when_only_tree_structure_changes(tmp_path):
    root = _secure_models_root(tmp_path)

    def build(name: str, *, include_empty_directory: bool) -> str:
        export = root / name
        export.mkdir(mode=0o700)
        if include_empty_directory:
            (export / "empty").mkdir(mode=0o700)
        for filename, content in (("model.bin", b"same"), ("model.param", b"same")):
            path = export / filename
            path.write_bytes(content)
            path.chmod(0o600)
        descriptor = os.open(export, os.O_RDONLY | os.O_DIRECTORY)
        try:
            return canonical_ncnn_manifest_descriptor(
                descriptor,
                expected_uid=os.geteuid(),
            )["manifest_sha256"]
        finally:
            os.close(descriptor)

    flat_digest = build("flat_ncnn_model", include_empty_directory=False)
    structured_digest = build("structured_ncnn_model", include_empty_directory=True)

    assert flat_digest != structured_digest


def test_legacy_ncnn_provenance_requires_reexport(tmp_path):
    root = _secure_models_root(tmp_path)
    model = root / "demo.pt"
    model.write_bytes(b"trusted")
    model.chmod(0o600)
    export = root / "demo_ncnn_model"
    export.mkdir(mode=0o700)
    for name, content in (("model.bin", b"weights"), ("model.param", b"params")):
        path = export / name
        path.write_bytes(content)
        path.chmod(0o600)
    store = ModelProvenanceStore(root)
    store.trust_pt(
        model,
        sha256=sha256_file(model),
        source="unit-test",
        expected_digest_verified=True,
        publisher_sha256=sha256_file(model),
    )
    store.trust_ncnn(model, export)
    payload = store.load()
    record = payload["artifacts"]["demo.pt"]["ncnn"]
    record.pop("manifest", None)
    record.pop("manifest_schema_version", None)
    record.pop("manifest_sha256", None)
    store.registry_path.write_text(json.dumps(payload), encoding="utf-8")
    store.registry_path.chmod(0o600)

    with pytest.raises(ModelArtifactPolicyError, match="re-export required"):
        store.verify_ncnn(export)


def test_corrupt_registry_fails_closed(tmp_path):
    root = _secure_models_root(tmp_path)
    model = root / "demo.pt"
    model.write_bytes(b"trusted")
    store = ModelProvenanceStore(root)
    store.registry_path.write_text("not-json", encoding="utf-8")
    store.registry_path.chmod(0o600)

    with pytest.raises(ModelArtifactPolicyError, match="unreadable"):
        store.verify_pt(model)


def test_registry_rejects_unsupported_schema(tmp_path):
    root = _secure_models_root(tmp_path)
    store = ModelProvenanceStore(root)
    store.registry_path.write_text(
        json.dumps({"schema_version": 99, "artifacts": {}}),
        encoding="utf-8",
    )
    store.registry_path.chmod(0o600)

    with pytest.raises(ModelArtifactPolicyError, match="schema version"):
        store.load()


@pytest.mark.parametrize("value", ["", "abc", "g" * 64, "0" * 63])
def test_required_sha256_rejects_invalid_values(value):
    with pytest.raises(ModelArtifactPolicyError):
        normalize_sha256(value, required=True)
