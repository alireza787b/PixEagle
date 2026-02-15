"""Tests for UltralyticsBackend implementation."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from classes.backends.detection_backend import DetectionBackend, DevicePreference
from classes.backends.ultralytics_backend import UltralyticsBackend, ULTRALYTICS_AVAILABLE
from classes.detection_adapter import NormalizedDetection


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


# ── Tracker type selection tests ─────────────────────────────────────────────


class TestTrackerTypeSelection:
    def test_default_tracker_type(self):
        backend = UltralyticsBackend(config={})
        assert backend.tracker_type_str in (
            "bytetrack", "botsort", "botsort_reid", "custom_reid"
        )

    def test_custom_reid_from_config(self):
        backend = UltralyticsBackend(config={"TRACKER_TYPE": "custom_reid"})
        # custom_reid maps to bytetrack engine + custom ReID flag
        assert backend.tracker_type_str == "bytetrack"
        assert backend.use_custom_reid is True

    def test_bytetrack_from_config(self):
        backend = UltralyticsBackend(config={"TRACKER_TYPE": "bytetrack"})
        assert backend.tracker_type_str == "bytetrack"
        assert backend.use_custom_reid is False
