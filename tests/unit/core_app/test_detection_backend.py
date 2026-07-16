"""Tests for the DetectionBackend ABC and backend registry/factory."""

from unittest.mock import patch

import pytest

from classes.backends.detection_backend import DetectionBackend, DevicePreference
from classes.backends import AVAILABLE_BACKENDS, create_backend
from classes.backends.ultralytics_backend import UltralyticsBackend
from classes.model_artifact_policy import (
    ModelArtifactPolicyError,
    ModelProvenanceStore,
    sha256_file,
)


class TestDevicePreference:
    def test_enum_values(self):
        assert DevicePreference.AUTO.value == "auto"
        assert DevicePreference.CPU.value == "cpu"
        assert DevicePreference.CUDA.value == "cuda"

    def test_enum_from_string(self):
        assert DevicePreference("auto") is DevicePreference.AUTO
        assert DevicePreference("cpu") is DevicePreference.CPU
        assert DevicePreference("cuda") is DevicePreference.CUDA

    def test_enum_invalid_value_raises(self):
        with pytest.raises(ValueError):
            DevicePreference("tpu")


class TestDetectionBackendABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError, match="abstract"):
            DetectionBackend()

    def test_abstract_methods_exist(self):
        expected = {
            "is_available", "backend_name", "is_loaded",
            "load_model", "unload_model", "switch_model",
            "detect", "detect_and_track",
            "get_model_labels", "get_model_task",
            "supports_tracking", "supports_obb", "get_device_info",
        }
        actual = set(DetectionBackend.__abstractmethods__)
        assert expected == actual


class TestBackendRegistry:
    def test_ultralytics_registered(self):
        assert "ultralytics" in AVAILABLE_BACKENDS
        module_path, class_name = AVAILABLE_BACKENDS["ultralytics"]
        assert module_path == "classes.backends.ultralytics_backend"
        assert class_name == "UltralyticsBackend"

    def test_create_backend_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown detection backend"):
            create_backend("nonexistent_backend")

    def test_create_backend_ultralytics_returns_instance(self):
        backend = create_backend("ultralytics", config={})
        assert backend.backend_name == "ultralytics"
        assert isinstance(backend, DetectionBackend)

    def test_create_backend_default_is_ultralytics(self):
        backend = create_backend()
        assert backend.backend_name == "ultralytics"


class TestUltralyticsLoadPolicy:
    def test_cuda_enum_normalizes_to_required_gpu(self):
        assert UltralyticsBackend._normalize_device_preference("cuda") == "gpu"

    def test_missing_model_is_rejected_before_ultralytics_can_download(self, tmp_path):
        tmp_path.chmod(0o700)
        backend = UltralyticsBackend({}, models_root=tmp_path)
        missing = tmp_path / "missing.pt"

        with pytest.raises(ModelArtifactPolicyError, match="not trusted"):
            backend._load_candidate(
                {"path": str(missing), "backend": "cpu_torch", "source": "test"}
            )

    def test_incomplete_ncnn_directory_is_rejected(self, tmp_path):
        tmp_path.chmod(0o700)
        incomplete = tmp_path / "demo_ncnn_model"
        incomplete.mkdir()
        (incomplete / "model.param").write_text("param", encoding="utf-8")
        backend = UltralyticsBackend({}, models_root=tmp_path)

        with pytest.raises(ModelArtifactPolicyError, match="not trusted"):
            backend._load_candidate(
                {"path": str(incomplete), "backend": "cpu_ncnn", "source": "test"}
            )

    def test_trusted_local_model_load_reports_runtime_provenance(self, tmp_path):
        tmp_path.chmod(0o700)
        model_path = tmp_path / "demo.pt"
        model_path.write_bytes(b"trusted-model")
        model_path.chmod(0o600)
        digest = sha256_file(model_path)
        ModelProvenanceStore(tmp_path).trust_pt(
            model_path,
            sha256=digest,
            source="unit-test",
            expected_digest_verified=True,
            publisher_sha256=digest,
        )
        backend = UltralyticsBackend(
            {"SMART_TRACKER_CPU_MODEL_PATH": str(model_path)},
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
            )

        assert runtime["model_provenance"]["verified"] is True
        assert runtime["model_provenance"]["sha256"] == digest
        backend.unload_model()
