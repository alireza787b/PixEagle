"""Tests for SmartTracker runtime — model loading, fallback, and switch logic.

Mocks at the DetectionBackend level (not at YOLO directly) to match the
refactored architecture where SmartTracker delegates inference to a backend.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from classes.parameters import Parameters
from classes.smart_tracker import SmartTracker
from classes.backends.detection_backend import DetectionBackend, DevicePreference
from classes.detection_adapter import NormalizedDetection


class FakeBackend(DetectionBackend):
    """Minimal DetectionBackend stub for SmartTracker tests."""

    def __init__(self, config: dict):
        self._config = config
        self._loaded = False
        self._runtime = {}
        self._labels = {0: "person"}
        self._task = "detect"
        # Tracker selection attributes (SmartTracker reads these)
        self.tracker_type_str = "bytetrack"
        self.use_custom_reid = False
        self.tracker_args = {}
        # Track load calls for assertions
        self.load_calls = []
        self.switch_calls = []

    @property
    def is_available(self) -> bool:
        return True

    @property
    def backend_name(self) -> str:
        return "fake"

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_model(self, model_path, device=DevicePreference.AUTO,
                   fallback_enabled=True, context="startup"):
        self.load_calls.append({
            "model_path": model_path, "device": device,
            "fallback_enabled": fallback_enabled, "context": context,
        })
        self._loaded = True
        backend_type = "cpu_ncnn" if "ncnn" in str(model_path) else "cpu_torch"
        effective_device = "cpu"
        fallback_occurred = False
        fallback_reason = None

        # Simulate GPU failure + fallback
        if device == DevicePreference.CUDA and getattr(self, '_fail_gpu', False):
            if fallback_enabled:
                fallback_occurred = True
                fallback_reason = "forced GPU failure"
                backend_type = "cpu_ncnn"
            else:
                raise RuntimeError("GPU not available")

        self._runtime = {
            "requested_device": device.value if isinstance(device, DevicePreference) else str(device),
            "effective_device": effective_device,
            "backend": backend_type,
            "model_path": str(model_path),
            "model_name": Path(model_path).name,
            "fallback_enabled": fallback_enabled,
            "fallback_occurred": fallback_occurred,
            "fallback_reason": fallback_reason,
            "context": context,
            "attempts": [],
        }
        return dict(self._runtime)

    def unload_model(self):
        self._loaded = False
        self._runtime = {}

    def switch_model(self, new_model_path, device=DevicePreference.AUTO,
                     fallback_enabled=True):
        self.switch_calls.append({
            "new_model_path": new_model_path, "device": device,
        })
        return self.load_model(new_model_path, device, fallback_enabled, context="switch")

    def detect(self, frame, conf=0.3, iou=0.3, max_det=20):
        return "detect", []

    def detect_and_track(self, frame, conf=0.3, iou=0.3, max_det=20,
                         tracker_type="bytetrack", tracker_args=None):
        return "detect", []

    def get_model_labels(self):
        return dict(self._labels)

    def get_model_task(self):
        return self._task

    def supports_tracking(self):
        return True

    def supports_obb(self):
        return False

    def get_device_info(self):
        return dict(self._runtime)


class DummyAppController:
    def __init__(self):
        self.tracker = None
        self.tracking_started = False


def _configure(monkeypatch, model_path="models/test.pt", use_gpu=False,
               fallback_to_cpu=True, fail_gpu=False):
    """Configure Parameters and patch create_backend to return FakeBackend."""

    fake_backend_instance = None

    def fake_create_backend(backend_name='ultralytics', config=None):
        nonlocal fake_backend_instance
        fb = FakeBackend(config or {})
        fb._fail_gpu = fail_gpu
        fake_backend_instance = fb
        return fb

    monkeypatch.setattr(
        "classes.smart_tracker.create_backend",
        fake_create_backend,
    )
    monkeypatch.setattr(
        Parameters,
        "SmartTracker",
        {
            "SMART_TRACKER_USE_GPU": use_gpu,
            "SMART_TRACKER_FALLBACK_TO_CPU": fallback_to_cpu,
            "SMART_TRACKER_GPU_MODEL_PATH": str(model_path),
            "SMART_TRACKER_CPU_MODEL_PATH": str(model_path),
            "TRACKER_TYPE": "bytetrack",
            "ENABLE_PREDICTION_BUFFER": False,
            "ENABLE_APPEARANCE_MODEL": False,
            "SMART_TRACKER_SHOW_FPS": False,
            "DETECTION_BACKEND": "ultralytics",
        },
        raising=False,
    )
    return fake_backend_instance  # Will be set after SmartTracker.__init__


def test_init_cpu_mode(monkeypatch, tmp_path):
    ncnn_model = tmp_path / "demo_ncnn_model"
    ncnn_model.mkdir()
    _configure(monkeypatch, model_path=str(ncnn_model.as_posix()), use_gpu=False)

    tracker = SmartTracker(DummyAppController())
    runtime = tracker.get_runtime_info()

    assert runtime["backend"] == "cpu_ncnn"
    assert runtime["effective_device"] == "cpu"
    assert runtime["fallback_occurred"] is False


def test_gpu_failure_falls_back_to_cpu(monkeypatch, tmp_path):
    model_path = tmp_path / "gpu_ncnn_model"
    model_path.mkdir()
    _configure(monkeypatch, model_path=str(model_path.as_posix()),
               use_gpu=True, fail_gpu=True)

    tracker = SmartTracker(DummyAppController())
    runtime = tracker.get_runtime_info()

    assert runtime["effective_device"] == "cpu"
    assert runtime["fallback_occurred"] is True
    assert runtime["fallback_reason"] is not None


def test_switch_model_delegates_to_backend(monkeypatch, tmp_path):
    base_model = tmp_path / "base.pt"
    base_model.write_bytes(b"base")
    _configure(monkeypatch, model_path=str(base_model.as_posix()), use_gpu=False)

    tracker = SmartTracker(DummyAppController())
    backend = tracker.backend

    next_model = tmp_path / "next_ncnn_model"
    next_model.mkdir()
    result = tracker.switch_model(str(next_model.as_posix()), device="cpu")

    assert result["success"] is True
    assert len(backend.switch_calls) == 1
    assert backend.switch_calls[0]["new_model_path"] == str(next_model.as_posix())


def test_switch_model_restores_tracking_on_compatible_classes(monkeypatch, tmp_path):
    model = tmp_path / "base.pt"
    model.write_bytes(b"base")
    _configure(monkeypatch, model_path=str(model.as_posix()), use_gpu=False)

    tracker = SmartTracker(DummyAppController())
    # Simulate active tracking
    tracker.selected_object_id = 5
    tracker.selected_class_id = 0  # class 0 exists in FakeBackend labels
    tracker.selected_bbox = (10, 10, 50, 50)
    tracker.selected_center = (30, 30)

    next_model = tmp_path / "next.pt"
    next_model.write_bytes(b"next")
    result = tracker.switch_model(str(next_model.as_posix()), device="cpu")

    assert result["success"] is True
    assert result["model_info"]["tracking_restored"] is True


def test_track_and_draw_handles_loss_report_without_track_id(monkeypatch, tmp_path):
    model = tmp_path / "base.pt"
    model.write_bytes(b"base")
    _configure(monkeypatch, model_path=str(model.as_posix()), use_gpu=False)

    tracker = SmartTracker(DummyAppController())

    frame = np.zeros((96, 96, 3), dtype=np.uint8)
    detections = [
        NormalizedDetection(
            track_id=7,
            class_id=0,
            confidence=0.9,
            aabb_xyxy=(10, 10, 36, 36),
            center_xy=(23, 23),
            geometry_type="aabb",
        )
    ]

    # Mock the backend's detect_and_track to return our detections
    tracker.backend.detect_and_track = MagicMock(
        return_value=("detect", detections)
    )

    tracker.tracking_manager.selected_track_id = 7
    tracker.tracking_manager.update_tracking = MagicMock(
        return_value=(False, {"need_reselection": True, "loss_reason": "occluded"})
    )
    tracker.tracking_manager.clear = MagicMock()

    tracker.selected_object_id = 7
    tracker.selected_class_id = 0
    tracker.selected_bbox = (10, 10, 36, 36)
    tracker.selected_center = (23, 23)

    output = tracker.track_and_draw(frame)

    assert output.shape == frame.shape
    assert tracker.app_controller.tracking_started is False
    assert tracker.selected_object_id is None
    assert tracker.selected_bbox is None
    tracker.tracking_manager.clear.assert_called_once()
