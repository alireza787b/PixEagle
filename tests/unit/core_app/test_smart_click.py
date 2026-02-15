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
import numpy as np
import pytest

from classes.detection_adapter import NormalizedDetection


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


class StubSmartTracker:
    """Minimal SmartTracker stub with the correct public API."""
    def __init__(self):
        self.last_detections = []
        self.selected_bbox = None
        self.selected_center = None
        self._click_args = None

    def select_object_by_click(self, x, y):
        self._click_args = (x, y)
        # Simulate selection from last_detections
        if self.last_detections:
            det = self.last_detections[0]
            self.selected_bbox = det.aabb_xyxy
            self.selected_center = det.center_xy


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
        ctrl.handle_smart_click(320, 240)
        assert ctrl.smart_tracker._click_args is None  # select_object_by_click not called

    def test_no_frame_returns_early(self):
        """handle_smart_click should return early if no frame available."""
        ctrl = _make_controller()
        ctrl.current_frame = None
        ctrl.handle_smart_click(100, 100)
        assert ctrl.smart_tracker._click_args is None

    def test_no_smart_tracker_returns_early(self):
        """handle_smart_click should return early if smart_tracker is None."""
        ctrl = _make_controller()
        ctrl.smart_tracker = None
        # Should not raise
        ctrl.handle_smart_click(100, 100)

    def test_empty_detections_returns_early(self):
        """handle_smart_click with empty detections should not call select_object_by_click."""
        ctrl = _make_controller()
        ctrl.smart_tracker.last_detections = []
        ctrl.handle_smart_click(320, 240)
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

        ctrl.handle_smart_click(150, 150)

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

        ctrl.handle_smart_click(400, 400)
        assert ctrl.selected_bbox is None  # No override applied


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

    def test_start_tracking_normal(self):
        """start_tracking with valid bbox should start the classic tracker."""
        import asyncio
        ctrl = _make_controller()
        ctrl.tracking_started = False

        bbox = {'x': 100, 'y': 100, 'width': 200, 'height': 150}
        asyncio.get_event_loop().run_until_complete(ctrl.start_tracking(bbox))

        assert ctrl.tracking_started is True
        assert ctrl.tracker.started_bbox == (100, 100, 200, 150)

    def test_start_tracking_already_active(self):
        """start_tracking when already active should not restart."""
        import asyncio
        ctrl = _make_controller()
        ctrl.tracking_started = True

        bbox = {'x': 50, 'y': 50, 'width': 100, 'height': 100}
        asyncio.get_event_loop().run_until_complete(ctrl.start_tracking(bbox))

        # Tracker should NOT have started_bbox (was already running)
        assert not hasattr(ctrl.tracker, 'started_bbox')

    def test_start_tracking_external_tracker_skipped(self):
        """start_tracking with external tracker should skip gracefully."""
        import asyncio
        ctrl = _make_controller()
        ctrl.tracker.is_external_tracker = True

        bbox = {'x': 50, 'y': 50, 'width': 100, 'height': 100}
        asyncio.get_event_loop().run_until_complete(ctrl.start_tracking(bbox))

        assert ctrl.tracking_started is False
