"""Tests for the DetectionBackend ABC and backend registry/factory."""

import pytest

from classes.backends.detection_backend import DetectionBackend, DevicePreference
from classes.backends import AVAILABLE_BACKENDS, create_backend


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
