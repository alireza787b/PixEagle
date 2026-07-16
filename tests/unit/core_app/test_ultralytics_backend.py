"""Tests for UltralyticsBackend implementation."""

import os
import importlib.metadata
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from classes.backends.detection_backend import DetectionBackend, DevicePreference
from classes.backends.ultralytics_backend import UltralyticsBackend, ULTRALYTICS_AVAILABLE
from classes.detection_adapter import NormalizedDetection
from classes.model_artifact_policy import (
    ModelArtifactPolicyError,
    ModelProvenanceStore,
    ModelStoreBusyError,
    ModelStoreLease,
    sha256_file,
)


def _replace_model_after_signal(replacement, target, start, complete):
    start.wait(5)
    os.replace(replacement, target)
    complete.set()


def _trust_pt(model_path: Path) -> ModelProvenanceStore:
    model_path.chmod(0o600)
    store = ModelProvenanceStore(model_path.parent)
    digest = sha256_file(model_path)
    store.trust_pt(
        model_path,
        sha256=digest,
        source="unit-test",
        expected_digest_verified=True,
        publisher_sha256=digest,
    )
    return store


def _close_candidate_lease(candidate: dict) -> None:
    lease = candidate.pop("_model_store_lease", None)
    if lease is not None:
        lease.close()


# ── Property / metadata tests (no model load needed) ────────────────────────


class TestBackendProperties:
    def test_backend_name(self):
        backend = UltralyticsBackend(config={})
        assert backend.backend_name == "ultralytics"

    def test_is_detection_backend_subclass(self):
        assert issubclass(UltralyticsBackend, DetectionBackend)

    def test_is_available_reflects_import(self):
        backend = UltralyticsBackend(config={})
        assert backend.is_available is ULTRALYTICS_AVAILABLE

    def test_not_loaded_before_load(self):
        backend = UltralyticsBackend(config={})
        assert backend.is_loaded is False

    def test_supports_tracking(self):
        backend = UltralyticsBackend(config={})
        assert backend.supports_tracking() is True

    def test_supports_obb(self):
        backend = UltralyticsBackend(config={})
        assert backend.supports_obb() is True


# ── Model path resolution tests ─────────────────────────────────────────────


class TestModelPathHelpers:
    def setup_method(self):
        self.backend = UltralyticsBackend(config={})

    def test_is_valid_ncnn_dir(self, tmp_path):
        # Not valid: empty dir
        assert self.backend._is_valid_ncnn_dir(str(tmp_path)) is False

        # Valid: dir with .bin + .param
        (tmp_path / "model.bin").touch()
        (tmp_path / "model.param").touch()
        assert self.backend._is_valid_ncnn_dir(str(tmp_path)) is True

    def test_looks_like_ncnn_path(self):
        assert self.backend._looks_like_ncnn_path("yolo11n_ncnn_model") is True
        assert self.backend._looks_like_ncnn_path("models/yolo_ncnn_model") is True
        assert self.backend._looks_like_ncnn_path("yolo11n.pt") is False
        assert self.backend._looks_like_ncnn_path("model.onnx") is False

    def test_derive_ncnn_path(self):
        assert self.backend._derive_ncnn_path("models/yolo11n.pt") == "models/yolo11n_ncnn_model"
        assert self.backend._derive_ncnn_path("yolo.pt") == "yolo_ncnn_model"

    def test_derive_pt_from_ncnn_path(self):
        result = self.backend._derive_pt_from_ncnn_path("models/yolo11n_ncnn_model")
        assert result == "models/yolo11n.pt"

    def test_normalize_model_path(self):
        # Converts to forward-slash posix path
        assert self.backend._normalize_model_path("models\\yolo.pt") == "models/yolo.pt"
        assert self.backend._normalize_model_path("models/yolo.pt") == "models/yolo.pt"


# ── CPU / GPU candidate selection tests ──────────────────────────────────────


class TestCandidateSelection:
    def test_pick_cpu_prefers_ncnn(self, tmp_path):
        """When a valid NCNN dir exists, CPU candidate should prefer it."""
        pt_file = tmp_path / "model.pt"
        pt_file.write_bytes(b"fake-pt")
        ncnn_dir = tmp_path / "model_ncnn_model"
        ncnn_dir.mkdir()
        (ncnn_dir / "model.bin").touch()
        (ncnn_dir / "model.param").touch()

        backend = UltralyticsBackend(config={
            "SMART_TRACKER_CPU_MODEL_PATH": str(ncnn_dir),
        })

        candidate = backend._pick_cpu_model_candidate(str(pt_file))
        # Returns a single dict with path/backend/source keys
        assert "_ncnn_model" in candidate["path"]
        assert candidate["backend"] == "cpu_ncnn"

    def test_pick_cpu_falls_back_to_pt(self, tmp_path):
        """When no NCNN dir exists, CPU candidate falls back to .pt file."""
        pt_file = tmp_path / "model.pt"
        pt_file.write_bytes(b"fake-pt")

        backend = UltralyticsBackend(config={
            "SMART_TRACKER_CPU_MODEL_PATH": str(tmp_path / "nonexistent_ncnn_model"),
        })

        candidate = backend._pick_cpu_model_candidate(str(pt_file))
        # Should still find the .pt as a fallback
        assert "model" in candidate["path"]

    def test_pick_gpu_prefers_pt(self, tmp_path):
        """GPU candidate should prefer .pt files."""
        pt_file = tmp_path / "model.pt"
        pt_file.write_bytes(b"fake-pt")

        backend = UltralyticsBackend(config={
            "SMART_TRACKER_GPU_MODEL_PATH": str(pt_file),
        })

        candidate = backend._pick_gpu_model_candidate(str(pt_file))
        assert candidate["path"].endswith(".pt")
        assert candidate["backend"] == "cuda"


class TestRuntimeModelProvenance:
    def test_digest_required_rejects_operator_assertion_at_runtime(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_bytes(b"trusted-model")
        model_path.chmod(0o600)
        store = ModelProvenanceStore(tmp_path)
        store.trust_pt(
            model_path,
            sha256=sha256_file(model_path),
            source="unit-test",
            expected_digest_verified=False,
        )
        backend = UltralyticsBackend(
            config={"SMART_TRACKER_MODEL_TRUST_POLICY": "digest_required"},
            models_root=tmp_path,
        )
        candidate = {
            "path": str(model_path),
            "backend": "cpu_pt",
            "source": "test",
        }

        with patch("classes.backends.ultralytics_backend.YOLO", return_value=object()):
            with pytest.raises(ModelArtifactPolicyError, match="publisher-digest"):
                backend._load_candidate(candidate)

    def test_untrusted_pt_is_rejected_before_yolo_load(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_bytes(b"untrusted-model")
        backend = UltralyticsBackend(
            config={"ALLOW_UNTRUSTED_MODELS": True},
            models_root=tmp_path,
        )
        candidate = {
            "path": str(model_path),
            "backend": "cpu_torch",
            "source": "test",
        }

        with patch(
            "classes.backends.ultralytics_backend.YOLO"
        ) as yolo_loader, pytest.raises(
            ModelArtifactPolicyError,
            match="not trusted",
        ):
            backend._load_candidate(candidate)

        yolo_loader.assert_not_called()

    def test_trusted_pt_is_verified_before_yolo_load(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_bytes(b"trusted-model")
        _trust_pt(model_path)
        expected_digest = sha256_file(model_path)
        backend = UltralyticsBackend(config={}, models_root=tmp_path)
        candidate = {
            "path": str(model_path),
            "backend": "cpu_torch",
            "source": "test",
        }
        loaded_model = object()

        with patch(
            "classes.backends.ultralytics_backend.YOLO",
            return_value=loaded_model,
        ) as yolo_loader:
            result = backend._load_candidate(candidate)

        assert result is loaded_model
        loaded_path = Path(yolo_loader.call_args.args[0])
        assert loaded_path.name == "model.pt"
        assert loaded_path.is_symlink()
        assert os.readlink(loaded_path).startswith("/proc/self/fd/")
        assert candidate["model_provenance"]["verified"] is True
        assert candidate["model_provenance"]["artifact_type"] == "pt"
        assert candidate["model_provenance"]["sha256"] == expected_digest
        assert candidate["model_provenance"]["trust_method"] == "expected_sha256"
        _close_candidate_lease(candidate)
        assert not os.path.lexists(loaded_path)
        assert not loaded_path.parent.exists()

    def test_mutated_pt_is_rejected_before_yolo_load(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_bytes(b"trusted-model")
        _trust_pt(model_path)
        model_path.write_bytes(b"mutated-model")
        backend = UltralyticsBackend(config={}, models_root=tmp_path)

        with patch(
            "classes.backends.ultralytics_backend.YOLO"
        ) as yolo_loader, pytest.raises(
            ModelArtifactPolicyError,
            match="digest changed",
        ):
            backend._load_candidate(
                {
                    "path": str(model_path),
                    "backend": "cpu_torch",
                    "source": "test",
                }
            )

        yolo_loader.assert_not_called()

    def test_ncnn_requires_verified_export_provenance(self, tmp_path):
        pt_path = tmp_path / "model.pt"
        pt_path.write_bytes(b"trusted-model")
        ncnn_path = tmp_path / "model_ncnn_model"
        ncnn_path.mkdir(mode=0o700)
        ncnn_path.chmod(0o700)
        (ncnn_path / "model.bin").write_bytes(b"weights")
        (ncnn_path / "model.param").write_text("params", encoding="utf-8")
        (ncnn_path / "model.bin").chmod(0o600)
        (ncnn_path / "model.param").chmod(0o600)
        store = _trust_pt(pt_path)
        ncnn_record = store.trust_ncnn(pt_path, ncnn_path)
        registration_receipt = store.verify_pt(pt_path)["registration_receipt"]
        backend = UltralyticsBackend(config={}, models_root=tmp_path)
        candidate = {
            "path": str(ncnn_path),
            "backend": "cpu_ncnn",
            "source": "test",
        }

        with patch(
            "classes.backends.ultralytics_backend.YOLO",
            return_value=object(),
        ) as yolo_loader:
            backend._load_candidate(candidate)

        loaded_path = Path(yolo_loader.call_args.args[0])
        assert loaded_path.name == "model_ncnn_model"
        assert loaded_path.is_symlink()
        assert os.readlink(loaded_path).startswith("/proc/self/fd/")

        assert candidate["model_provenance"] == {
            "verified": True,
            "artifact_type": "ncnn",
            "sha256": ncnn_record["sha256"],
            "models_root": str(tmp_path.resolve()),
            "registry_path": str(store.registry_path),
            "recorded_at": ncnn_record["recorded_at"],
            "source_pt_sha256": ncnn_record["source_pt_sha256"],
            "file_count": ncnn_record["file_count"],
            "size_bytes": ncnn_record["size_bytes"],
            "trust_method": "expected_sha256",
            "manifest_schema_version": ncnn_record["manifest_schema_version"],
            "observed_sha256": sha256_file(pt_path),
            "publisher_sha256": sha256_file(pt_path),
            "registration_receipt": registration_receipt,
        }
        _close_candidate_lease(candidate)
        assert not os.path.lexists(loaded_path)
        assert not loaded_path.parent.exists()

    def test_load_model_exposes_verified_provenance(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_bytes(b"trusted-model")
        _trust_pt(model_path)
        expected_digest = sha256_file(model_path)
        backend = UltralyticsBackend(
            config={
                "SMART_TRACKER_CPU_MODEL_PATH": str(model_path),
            },
            models_root=tmp_path,
        )

        with patch(
            "classes.backends.ultralytics_backend.YOLO",
            return_value=object(),
        ):
            runtime = backend.load_model(
                str(model_path),
                device=DevicePreference.CPU,
                fallback_enabled=False,
                context="unit_test",
            )

        assert runtime["artifact_sha256"] == expected_digest
        assert runtime["trust_method"] == "expected_sha256"
        assert runtime["model_provenance"]["verified"] is True
        assert runtime["model_provenance"]["artifact_type"] == "pt"
        assert runtime["attempts"][0]["model_provenance"] == runtime[
            "model_provenance"
        ]
        backend.unload_model()

    def test_adjacent_attacker_registry_outside_canonical_root_is_rejected(
        self,
        tmp_path,
    ):
        models_root = tmp_path / "models"
        models_root.mkdir()
        models_root.chmod(0o700)
        outside_root = tmp_path / "outside"
        outside_root.mkdir()
        outside_root.chmod(0o700)
        outside_model = outside_root / "model.pt"
        outside_model.write_bytes(b"attacker-controlled")
        _trust_pt(outside_model)
        backend = UltralyticsBackend(config={}, models_root=models_root)

        with patch(
            "classes.backends.ultralytics_backend.YOLO"
        ) as yolo_loader, pytest.raises(
            ModelArtifactPolicyError,
            match="configured models root",
        ):
            backend._load_candidate(
                {
                    "path": str(outside_model),
                    "backend": "cpu_torch",
                    "source": "test",
                }
            )

        yolo_loader.assert_not_called()

    def test_runtime_rejects_lexical_symlink_alias_of_models_root(self, tmp_path):
        models_root = tmp_path / "models"
        models_root.mkdir(mode=0o700)
        models_root.chmod(0o700)
        model_path = models_root / "model.pt"
        model_path.write_bytes(b"trusted-model")
        _trust_pt(model_path)
        alias = tmp_path / "models-alias"
        alias.symlink_to(models_root, target_is_directory=True)
        backend = UltralyticsBackend(config={}, models_root=models_root)

        with patch(
            "classes.backends.ultralytics_backend.YOLO"
        ) as yolo_loader, pytest.raises(
            ModelArtifactPolicyError,
            match="canonical direct-child path",
        ):
            backend._load_candidate(
                {
                    "path": str(alias / "model.pt"),
                    "backend": "cpu_torch",
                    "source": "test",
                }
            )

        yolo_loader.assert_not_called()

    def test_runtime_loader_uses_pinned_inode_and_rejects_multiprocess_swap(
        self,
        tmp_path,
    ):
        model_path = tmp_path / "model.pt"
        model_path.write_bytes(b"trusted-model")
        _trust_pt(model_path)
        replacement = tmp_path / "replacement.pt"
        replacement.write_bytes(b"attacker-model")
        replacement.chmod(0o600)
        backend = UltralyticsBackend(config={}, models_root=tmp_path)
        context = multiprocessing.get_context("spawn")
        start = context.Event()
        complete = context.Event()
        process = context.Process(
            target=_replace_model_after_signal,
            args=(str(replacement), str(model_path), start, complete),
        )
        process.start()
        loaded_bytes = []
        loaded_paths = []
        loader_targets = []

        def pinned_loader(path):
            loaded_paths.append(path)
            loader_targets.append(os.readlink(path))
            start.set()
            assert complete.wait(5)
            loaded_bytes.append(Path(path).read_bytes())
            return object()

        try:
            with patch(
                "classes.backends.ultralytics_backend.YOLO",
                side_effect=pinned_loader,
            ), pytest.raises(
                ModelArtifactPolicyError,
                match="canonical store binding",
            ):
                backend._load_candidate(
                    {
                        "path": str(model_path),
                        "backend": "cpu_torch",
                        "source": "test",
                    }
                )
        finally:
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(2)

        assert process.exitcode == 0
        assert loaded_bytes == [b"trusted-model"]
        assert Path(loaded_paths[0]).name == "model.pt"
        assert loader_targets[0].startswith("/proc/self/fd/")
        assert not os.path.lexists(loaded_paths[0])
        assert model_path.read_bytes() == b"attacker-model"

    def test_real_ultralytics_8495_detects_bound_pt_and_ncnn_formats(self, tmp_path):
        pytest.importorskip("ultralytics")
        assert importlib.metadata.version("ultralytics") == "8.4.95"
        from ultralytics.nn.autobackend import AutoBackend

        pt_path = tmp_path / "model.pt"
        pt_path.write_bytes(b"format-only")
        pt_path.chmod(0o600)
        ncnn_path = tmp_path / "model_ncnn_model"
        ncnn_path.mkdir(mode=0o700)

        with ModelStoreLease(tmp_path, exclusive=False) as lease:
            pt_descriptor = lease.pin_model(pt_path.name)
            ncnn_descriptor = lease.pin_ncnn_directory(ncnn_path.name)
            pt_loader = lease.loader_binding(pt_descriptor, pt_path.name)
            ncnn_loader = lease.loader_binding(
                ncnn_descriptor,
                ncnn_path.name,
                directory=True,
            )

            assert AutoBackend._model_type(str(pt_loader.verified_path())) == "pt"
            assert AutoBackend._model_type(str(ncnn_loader.verified_path())) == "ncnn"

    def test_loaded_model_lease_releases_on_explicit_unload(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_bytes(b"trusted-model")
        _trust_pt(model_path)
        backend = UltralyticsBackend(
            config={"SMART_TRACKER_CPU_MODEL_PATH": str(model_path)},
            models_root=tmp_path,
        )

        with patch("classes.backends.ultralytics_backend.YOLO", return_value=object()):
            backend.load_model(
                str(model_path),
                device=DevicePreference.CPU,
                fallback_enabled=False,
            )

        def acquire_exclusive():
            with ModelStoreLease(tmp_path, exclusive=True, timeout_seconds=0):
                pass

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(acquire_exclusive)
            with pytest.raises(ModelStoreBusyError):
                future.result(timeout=2)
        backend.unload_model()
        with ModelStoreLease(tmp_path, exclusive=True, timeout_seconds=0):
            pass

    def test_failed_candidate_load_releases_lease(self, tmp_path):
        model_path = tmp_path / "model.pt"
        model_path.write_bytes(b"trusted-model")
        _trust_pt(model_path)
        backend = UltralyticsBackend(config={}, models_root=tmp_path)

        with patch(
            "classes.backends.ultralytics_backend.YOLO",
            side_effect=RuntimeError("construction failed"),
        ), pytest.raises(RuntimeError, match="construction failed"):
            backend._load_candidate(
                {
                    "path": str(model_path),
                    "backend": "cpu_torch",
                    "source": "test",
                }
            )

        with ModelStoreLease(tmp_path, exclusive=True, timeout_seconds=0):
            pass


# ── Result normalization tests ───────────────────────────────────────────────


class TestResultNormalization:
    """Test the static/classmethods for parsing Ultralytics results."""

    def test_to_list_with_numpy(self):
        result = UltralyticsBackend._to_list(np.array([1.0, 2.0, 3.0]))
        assert result == [1.0, 2.0, 3.0]

    def test_to_list_with_plain_list(self):
        result = UltralyticsBackend._to_list([1, 2, 3])
        assert result == [1, 2, 3]

    def test_to_list_with_none(self):
        assert UltralyticsBackend._to_list(None) == []

    def test_detect_result_mode_boxes(self):
        result = MagicMock()
        result.obb = None
        result.boxes = MagicMock()
        result.boxes.data = np.array([[10, 20, 30, 40, 0.9, 0]])  # non-empty

        mode = UltralyticsBackend._detect_result_mode(result)
        assert mode == "detect"

    def test_detect_result_mode_obb(self):
        result = MagicMock()
        result.obb = MagicMock()
        result.obb.data = np.array([[10, 20, 30, 40, 0.5]])  # non-empty
        result.boxes = None

        mode = UltralyticsBackend._detect_result_mode(result)
        assert mode == "obb"

    def test_detect_result_mode_none(self):
        result = MagicMock()
        result.obb = None
        result.boxes = None

        mode = UltralyticsBackend._detect_result_mode(result)
        assert mode == "none"

    def test_parse_boxes_returns_normalized_detections(self):
        """_parse_boxes should convert Ultralytics boxes to NormalizedDetection."""

        class FakeBoxes:
            xyxy = np.array([[10.0, 20.0, 50.0, 60.0]])
            conf = np.array([0.95])
            cls = np.array([2.0])
            id = np.array([7.0])

        class FakeResult:
            boxes = FakeBoxes()

        detections = UltralyticsBackend._parse_boxes(FakeResult())
        assert len(detections) == 1
        d = detections[0]
        assert isinstance(d, NormalizedDetection)
        assert d.aabb_xyxy == (10, 20, 50, 60)
        assert d.confidence == pytest.approx(0.95)
        assert d.class_id == 2
        assert d.track_id == 7

    def test_parse_boxes_no_ids(self):
        """When boxes.id is None, track_id should be a negative sentinel."""

        class FakeBoxes:
            xyxy = np.array([[10.0, 20.0, 50.0, 60.0]])
            conf = np.array([0.8])
            cls = np.array([0.0])
            id = None

        class FakeResult:
            boxes = FakeBoxes()

        detections = UltralyticsBackend._parse_boxes(FakeResult())
        assert len(detections) == 1
        assert detections[0].track_id == -1  # -(0+1)


# ── Device info tests ────────────────────────────────────────────────────────


class TestDeviceInfo:
    def test_get_device_info_no_model_is_empty(self):
        backend = UltralyticsBackend(config={})
        info = backend.get_device_info()
        # Before model load, runtime_info is empty dict
        assert isinstance(info, dict)
        assert len(info) == 0

    def test_get_model_labels_no_model(self):
        backend = UltralyticsBackend(config={})
        assert backend.get_model_labels() == {}

    def test_get_model_task_no_model(self):
        backend = UltralyticsBackend(config={})
        assert backend.get_model_task() == "detect"


class TestModelSwitchAtomicity:
    def test_cache_cleanup_failure_restores_prior_model_and_runtime(self):
        backend = UltralyticsBackend(config={})
        prior_model = object()
        replacement_model = object()
        prior_runtime = {
            "model_path": "models/prior.pt",
            "effective_device": "cuda",
        }
        replacement_runtime = {
            "model_path": "models/replacement.pt",
            "effective_device": "cpu",
        }
        backend._model = prior_model
        backend._runtime_info = dict(prior_runtime)

        def install_replacement(*args, **kwargs):
            backend._model = replacement_model
            backend._runtime_info = dict(replacement_runtime)
            return dict(replacement_runtime)

        with patch.object(
            backend,
            "load_model",
            side_effect=install_replacement,
        ), patch.object(
            backend,
            "_clear_torch_cuda_cache",
            side_effect=RuntimeError("cache cleanup failed"),
        ), pytest.raises(RuntimeError, match="cache cleanup failed"):
            backend.switch_model("models/replacement.pt")

        assert backend._model is prior_model
        assert backend._runtime_info == prior_runtime


# ── Tracker type selection tests ─────────────────────────────────────────────


class TestTrackerTypeSelection:
    def test_default_tracker_type(self):
        backend = UltralyticsBackend(config={})
        assert backend.tracker_type_str == "botsort"
        assert backend.use_custom_reid is False

    def test_botsort_from_config(self):
        backend = UltralyticsBackend(config={"TRACKER_TYPE": "botsort"})
        assert backend.tracker_type_str == "botsort"
        assert backend.use_custom_reid is False

    def test_custom_reid_from_config(self):
        backend = UltralyticsBackend(config={"TRACKER_TYPE": "custom_reid"})
        # custom_reid maps to bytetrack engine + custom ReID flag
        assert backend.tracker_type_str == "bytetrack"
        assert backend.use_custom_reid is True

    def test_bytetrack_from_config(self):
        backend = UltralyticsBackend(config={"TRACKER_TYPE": "bytetrack"})
        assert backend.tracker_type_str == "bytetrack"
        assert backend.use_custom_reid is False

    def test_unsupported_tracker_type_falls_back_to_truthful_default(self, caplog):
        with caplog.at_level("WARNING"):
            backend = UltralyticsBackend(config={"TRACKER_TYPE": "botsort_reid"})

        assert backend.tracker_type_str == "botsort"
        assert backend.use_custom_reid is False
        assert "Unsupported tracker type 'botsort_reid'" in caplog.text
        assert "without ReID" in caplog.text
