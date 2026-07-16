"""Tests for smart click and classic start_tracking interaction.

Verifies that:
- AppController.handle_smart_click uses the correct SmartTracker attribute
  (last_detections, not the removed last_results)
- Click with empty detections is handled gracefully
- Click with valid detections selects object and activates override
- Classic start_tracking works correctly
- FastAPI handler's smart_click/start_tracking propagate errors properly
"""

from unittest.mock import MagicMock, patch, AsyncMock
import gc
import threading
import asyncio
import numpy as np
import pytest

from classes.detection_adapter import NormalizedDetection


class CleanupBackend:
    is_available = True
    tracker_type_str = "bytetrack"
    use_custom_reid = False
    tracker_args = None
    backend_name = "cleanup-test"

    def __init__(self):
        self.unload_calls = 0

    def load_model(self, **_kwargs):
        return {
            "model_path": "models/demo.pt",
            "backend": "cpu_torch",
            "requested_device": "cpu",
            "effective_device": "cpu",
            "fallback_occurred": False,
        }

    def unload_model(self):
        self.unload_calls += 1

    def get_model_labels(self):
        return {0: "target"}

    def get_model_task(self):
        return "detect"


# ---------------------------------------------------------------------------
# Minimal stubs — avoid importing heavy modules (cv2.selectROI, MAVLink, etc.)
# ---------------------------------------------------------------------------

class StubTracker:
    """Minimal classic tracker stub."""
    is_external_tracker = False

    def set_external_override(self, bbox, center):
        self.last_override_bbox = bbox
        self.last_override_center = center

    def start_tracking(self, frame, bbox):
        self.started_bbox = bbox

    def stop_tracking(self):
        self.stopped = True

    def clear_external_override(self):
        self.override_cleared = True

    def reset(self):
        self.reset_called = True


class StubSmartTracker:
    """Minimal SmartTracker stub with the correct public API."""
    def __init__(self):
        self.last_detections = []
        self.selected_bbox = None
        self.selected_center = None
        self._click_args = None
        self.on_track = None
        self.on_clear = None

    def select_object_by_click(self, x, y):
        self._click_args = (x, y)
        # Simulate selection from last_detections
        if self.last_detections:
            det = self.last_detections[0]
            self.selected_bbox = det.aabb_xyxy
            self.selected_center = det.center_xy

    def track_and_draw(self, frame):
        if self.on_track:
            self.on_track()
        return frame

    def clear_selection(self):
        if self.on_clear:
            self.on_clear()
        self.selected_bbox = None
        self.selected_center = None


class RecordingLock:
    """Minimal context-manager lock that exposes ownership to test callbacks."""

    def __init__(self):
        self.active = False
        self.entries = 0

    def __enter__(self):
        assert self.active is False
        self.active = True
        self.entries += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.active = False


def _make_controller():
    """Build a minimal AppController-like object for testing handle_smart_click."""
    # We don't instantiate the real AppController (too many deps).
    # Instead, import only the method and bind it to a stub.
    from types import MethodType

    # Read the real method source — import it directly
    from classes.app_controller import AppController

    ctrl = object.__new__(AppController)  # skip __init__
    ctrl.current_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    ctrl.smart_tracker = StubSmartTracker()
    ctrl.tracker = StubTracker()
    ctrl.selected_bbox = None
    ctrl.smart_mode_active = True
    ctrl.tracking_started = False
    ctrl.following_active = False
    ctrl._follower_state_lock = asyncio.Lock()
    ctrl._tracker_model_state_lock = threading.RLock()
    return ctrl


# ---------------------------------------------------------------------------
# Tests: handle_smart_click
# ---------------------------------------------------------------------------

class TestHandleSmartClick:
    """Tests for AppController.handle_smart_click."""

    def test_uses_last_detections_not_last_results(self):
        """Regression: v4.0.0 removed last_results; handle_smart_click must use last_detections."""
        ctrl = _make_controller()
        # Verify the attribute exists and is accessed correctly
        assert hasattr(ctrl.smart_tracker, 'last_detections')
        assert not hasattr(ctrl.smart_tracker, 'last_results')

        # With empty detections, should return early without error
        result = ctrl.handle_smart_click(320, 240)
        assert result["success"] is False
        assert result["reason"] == "no_detections"
        assert ctrl.smart_tracker._click_args is None  # select_object_by_click not called

    def test_no_frame_returns_early(self):
        """handle_smart_click should return early if no frame available."""
        ctrl = _make_controller()
        ctrl.current_frame = None
        result = ctrl.handle_smart_click(100, 100)
        assert result["success"] is False
        assert result["reason"] == "smart_tracker_unavailable"
        assert ctrl.smart_tracker._click_args is None

    def test_missing_tracker_model_barrier_fails_closed(self):
        ctrl = _make_controller()
        del ctrl._tracker_model_state_lock

        result = ctrl.handle_smart_click(100, 100)

        assert result["success"] is False
        assert result["reason"] == "tracker_model_state_barrier_unavailable"
        assert ctrl.smart_tracker._click_args is None

    def test_no_smart_tracker_returns_early(self):
        """handle_smart_click should return early if smart_tracker is None."""
        ctrl = _make_controller()
        ctrl.smart_tracker = None
        # Should not raise
        result = ctrl.handle_smart_click(100, 100)
        assert result["success"] is False
        assert result["reason"] == "smart_tracker_unavailable"

    def test_empty_detections_returns_early(self):
        """handle_smart_click with empty detections should not call select_object_by_click."""
        ctrl = _make_controller()
        ctrl.smart_tracker.last_detections = []
        result = ctrl.handle_smart_click(320, 240)
        assert result["success"] is False
        assert result["reason"] == "no_detections"
        assert ctrl.smart_tracker._click_args is None

    def test_valid_detection_selects_and_overrides(self):
        """handle_smart_click with detections should select object and set override."""
        ctrl = _make_controller()
        det = NormalizedDetection(
            track_id=1,
            class_id=0,
            confidence=0.95,
            aabb_xyxy=(100, 100, 200, 200),
            center_xy=(150, 150),
        )
        ctrl.smart_tracker.last_detections = [det]

        result = ctrl.handle_smart_click(150, 150)

        assert result["success"] is True
        assert result["reason"] == "override_applied"
        assert result["selected_bbox"] == [100, 100, 200, 200]
        assert result["selected_center"] == [150, 150]
        assert ctrl.smart_tracker._click_args == (150, 150)
        assert ctrl.selected_bbox == (100, 100, 200, 200)
        assert ctrl.tracker.last_override_bbox == (100, 100, 200, 200)
        assert ctrl.tracker.last_override_center == (150, 150)

    def test_click_miss_no_override(self):
        """handle_smart_click where select_object_by_click finds nothing."""
        ctrl = _make_controller()
        # Add detection but don't match (StubSmartTracker always selects first)
        # Override to simulate a miss
        ctrl.smart_tracker.last_detections = [
            NormalizedDetection(
                track_id=1, class_id=0, confidence=0.9,
                aabb_xyxy=(10, 10, 50, 50), center_xy=(30, 30),
            )
        ]
        # Override select_object_by_click to simulate miss
        ctrl.smart_tracker.select_object_by_click = lambda x, y: None

        result = ctrl.handle_smart_click(400, 400)
        assert result["success"] is False
        assert result["reason"] == "no_detection_selected"
        assert ctrl.selected_bbox is None  # No override applied


class TestSmartTrackerModelBarrier:
    """Keep inference and cancellation serialized with detector replacement."""

    def test_frame_processing_holds_model_state_barrier(self):
        ctrl = _make_controller()
        lock = RecordingLock()
        ctrl._tracker_model_state_lock = lock
        ctrl.smart_tracker.on_track = lambda: (
            None if lock.active else pytest.fail("Smart frame ran outside barrier")
        )

        frame = np.zeros((32, 32, 3), dtype=np.uint8)
        assert ctrl._track_and_draw_smart_frame(frame) is frame
        assert lock.entries == 1
        assert lock.active is False

    def test_frame_processing_fails_closed_without_model_state_barrier(self):
        ctrl = _make_controller()
        del ctrl._tracker_model_state_lock

        with pytest.raises(RuntimeError, match="state barrier is unavailable"):
            ctrl._track_and_draw_smart_frame(ctrl.current_frame)

    def test_cancel_holds_model_state_barrier(self):
        ctrl = _make_controller()
        lock = RecordingLock()
        ctrl._tracker_model_state_lock = lock
        ctrl.segmentation_active = True
        ctrl.setpoint_sender = None
        ctrl.smart_tracker.on_clear = lambda: (
            None if lock.active else pytest.fail("Target clear ran outside barrier")
        )

        ctrl.cancel_activities()

        assert lock.entries == 1
        assert lock.active is False
        assert ctrl.tracking_started is False
        assert ctrl.segmentation_active is False
        assert ctrl.tracker.override_cleared is True


# ---------------------------------------------------------------------------
# Tests: SmartTracker.last_detections attribute contract
# ---------------------------------------------------------------------------

class TestSmartTrackerDetectionsContract:
    """Verify SmartTracker always exposes last_detections as a list."""

    def test_last_detections_initialized_as_list(self, monkeypatch, tmp_path):
        """SmartTracker.last_detections should be initialized as empty list."""
        from tests.unit.core_app.test_smart_tracker_runtime import (
            FakeBackend, DummyAppController, _configure,
        )
        model = tmp_path / "test.pt"
        model.write_bytes(b"test")
        _configure(monkeypatch, model_path=str(model.as_posix()), use_gpu=False)

        from classes.smart_tracker import SmartTracker
        tracker = SmartTracker(DummyAppController())

        assert isinstance(tracker.last_detections, list)
        assert len(tracker.last_detections) == 0

    def test_last_detections_populated_after_inference(self, monkeypatch, tmp_path):
        """After track_and_draw, last_detections should contain NormalizedDetection objects."""
        from tests.unit.core_app.test_smart_tracker_runtime import (
            FakeBackend, DummyAppController, _configure,
        )
        model = tmp_path / "test.pt"
        model.write_bytes(b"test")
        _configure(monkeypatch, model_path=str(model.as_posix()), use_gpu=False)

        from classes.smart_tracker import SmartTracker
        tracker = SmartTracker(DummyAppController())

        det = NormalizedDetection(
            track_id=3, class_id=0, confidence=0.8,
            aabb_xyxy=(10, 10, 50, 50), center_xy=(30, 30),
        )
        tracker.backend.detect_and_track = MagicMock(return_value=("detect", [det]))

        frame = np.zeros((96, 96, 3), dtype=np.uint8)
        tracker.track_and_draw(frame)

        assert len(tracker.last_detections) == 1
        assert tracker.last_detections[0].track_id == 3


# ---------------------------------------------------------------------------
# Tests: Classic start_tracking via AppController
# ---------------------------------------------------------------------------

class TestClassicStartTracking:
    """Tests for AppController.start_tracking (classic mode)."""

    @pytest.mark.asyncio
    async def test_start_tracking_normal(self):
        """start_tracking with valid bbox should start the classic tracker."""
        ctrl = _make_controller()
        ctrl.tracking_started = False

        bbox = {'x': 100, 'y': 100, 'width': 200, 'height': 150}
        await ctrl.start_tracking(bbox)

        assert ctrl.tracking_started is True
        assert ctrl.tracker.started_bbox == (100, 100, 200, 150)

    @pytest.mark.asyncio
    async def test_start_tracking_already_active(self):
        """start_tracking when already active should not restart."""
        ctrl = _make_controller()
        ctrl.tracking_started = True

        bbox = {'x': 50, 'y': 50, 'width': 100, 'height': 100}
        await ctrl.start_tracking(bbox)

        # Tracker should NOT have started_bbox (was already running)
        assert not hasattr(ctrl.tracker, 'started_bbox')

    @pytest.mark.asyncio
    async def test_start_tracking_external_tracker_skipped(self):
        """start_tracking with external tracker should skip gracefully."""
        ctrl = _make_controller()
        ctrl.tracker.is_external_tracker = True

        bbox = {'x': 50, 'y': 50, 'width': 100, 'height': 100}
        await ctrl.start_tracking(bbox)

        assert ctrl.tracking_started is False


def _smart_tracker_cleanup_config():
    return {
        "DETECTION_BACKEND": "cleanup-test",
        "SMART_TRACKER_USE_GPU": False,
        "SMART_TRACKER_FALLBACK_TO_CPU": False,
        "SMART_TRACKER_CPU_MODEL_PATH": "models/demo.pt",
        "SMART_TRACKER_MODEL_TASK_POLICY": "auto",
        "SMART_TRACKER_GEOMETRY_OUTPUT_MODE": "hybrid",
        "TRACKER_TYPE": "bytetrack",
        "ENABLE_PREDICTION_BUFFER": False,
    }


def test_smart_tracker_construction_failure_unloads_backend():
    from classes.parameters import Parameters
    from classes.smart_tracker import SmartTracker

    backend = CleanupBackend()
    with patch.object(
        Parameters,
        "SmartTracker",
        _smart_tracker_cleanup_config(),
    ), patch(
        "classes.smart_tracker.create_backend",
        return_value=backend,
    ), patch.object(
        SmartTracker,
        "_apply_model_task_policy",
        side_effect=RuntimeError("post-load construction failure"),
    ), pytest.raises(RuntimeError, match="post-load construction failure"):
        SmartTracker(app_controller=MagicMock())

    gc.collect()
    assert backend.unload_calls == 1


def test_smart_tracker_close_is_idempotent_and_unloads_backend():
    from classes.parameters import Parameters
    from classes.smart_tracker import SmartTracker

    backend = CleanupBackend()
    with patch.object(
        Parameters,
        "SmartTracker",
        _smart_tracker_cleanup_config(),
    ), patch(
        "classes.smart_tracker.create_backend",
        return_value=backend,
    ), patch.object(
        SmartTracker,
        "_apply_model_task_policy",
        return_value=None,
    ):
        tracker = SmartTracker(app_controller=MagicMock())

    tracker.close()
    tracker.close()

    assert backend.unload_calls == 1
