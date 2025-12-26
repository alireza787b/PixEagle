# tests/unit/trackers/test_base_tracker.py
"""
Unit tests for BaseTracker abstract base class.

Tests utility methods, coordinate normalization, confidence computation,
boundary detection, and TrackerOutput generation.
"""

import pytest
import sys
import os
import numpy as np
import time
from unittest.mock import MagicMock, patch
from collections import deque

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from tests.fixtures.mock_opencv import MockVideoHandler, MockDetector, MockAppController


class ConcreteTracker:
    """
    Concrete implementation of BaseTracker for testing abstract methods.

    Since BaseTracker is abstract, we need a minimal concrete implementation
    to test its utility methods.
    """

    def __init__(self, video_handler=None, detector=None, app_controller=None):
        # Import here to avoid circular imports
        from classes.trackers.base_tracker import BaseTracker
        from classes.parameters import Parameters

        # Mock the app_controller to avoid estimator issues
        if app_controller is None:
            app_controller = MagicMock()
            app_controller.estimator = None

        # Store BaseTracker class for method delegation
        self._base_class = BaseTracker

        # Initialize base tracker attributes manually (without calling __init__)
        self.video_handler = video_handler
        self.detector = detector
        self.app_controller = app_controller

        self.bbox = None
        self.prev_center = None
        self.center = None
        self.normalized_bbox = None
        self.normalized_center = None
        self.center_history = deque(maxlen=Parameters.CENTER_HISTORY_LENGTH)

        self.tracking_started = False
        self.estimator_enabled = False
        self.position_estimator = None
        self.estimated_position_history = deque(maxlen=Parameters.ESTIMATOR_HISTORY_LENGTH)
        self.last_update_time = 1e-6
        self.confidence = 1.0
        self.frame = None
        self.override_active = False
        self.override_bbox = None
        self.override_center = None
        self.suppress_detector = False
        self.suppress_predictor = False
        self.tracker = None

    def start_tracking(self, frame, bbox):
        """Minimal implementation of abstract method."""
        self.bbox = bbox
        x, y, w, h = bbox
        self.center = (int(x + w/2), int(y + h/2))
        self.tracking_started = True

    def update(self, frame):
        """Minimal implementation of abstract method."""
        return True, self.bbox

    def normalize_center_coordinates(self):
        """Delegate to BaseTracker."""
        self._base_class.normalize_center_coordinates(self)

    def normalize_bbox(self):
        """Delegate to BaseTracker."""
        self._base_class.normalize_bbox(self)

    def set_center(self, value):
        """Delegate to BaseTracker."""
        self._base_class.set_center(self, value)

    def _create_tracker(self):
        """Minimal implementation for reset testing."""
        self.tracker = MagicMock()

    def reset(self):
        """Delegate to BaseTracker."""
        self._base_class.reset(self)


def create_test_tracker(width=640, height=480):
    """Create a ConcreteTracker with mock dependencies."""
    video_handler = MockVideoHandler(width, height)
    detector = MockDetector()
    app_controller = MockAppController()
    return ConcreteTracker(video_handler, detector, app_controller)


@pytest.mark.unit
class TestBaseTrackerInitialization:
    """Tests for BaseTracker initialization and default attributes."""

    def test_default_bbox_is_none(self):
        """bbox should be None before tracking starts."""
        tracker = create_test_tracker()
        assert tracker.bbox is None

    def test_default_center_is_none(self):
        """center should be None before tracking starts."""
        tracker = create_test_tracker()
        assert tracker.center is None

    def test_default_tracking_started_false(self):
        """tracking_started should be False initially."""
        tracker = create_test_tracker()
        assert tracker.tracking_started is False

    def test_default_confidence_is_one(self):
        """confidence should be 1.0 initially."""
        tracker = create_test_tracker()
        assert tracker.confidence == 1.0

    def test_center_history_is_deque(self):
        """center_history should be a deque."""
        tracker = create_test_tracker()
        assert isinstance(tracker.center_history, deque)


@pytest.mark.unit
class TestNormalizeCenterCoordinates:
    """Tests for normalize_center_coordinates method."""

    def test_center_at_frame_center_normalizes_to_zero(self):
        """Target at frame center should normalize to (0, 0)."""
        tracker = create_test_tracker(640, 480)
        tracker.center = (320, 240)  # Frame center

        # Call the method from BaseTracker
        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_center_coordinates(tracker)

        assert tracker.normalized_center is not None
        assert abs(tracker.normalized_center[0]) < 0.01
        assert abs(tracker.normalized_center[1]) < 0.01

    def test_center_at_top_left_normalizes_to_negative_one(self):
        """Target at top-left corner should normalize near (-1, -1)."""
        tracker = create_test_tracker(640, 480)
        tracker.center = (0, 0)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_center_coordinates(tracker)

        assert tracker.normalized_center[0] == pytest.approx(-1.0, abs=0.01)
        assert tracker.normalized_center[1] == pytest.approx(-1.0, abs=0.01)

    def test_center_at_bottom_right_normalizes_to_positive_one(self):
        """Target at bottom-right corner should normalize near (1, 1)."""
        tracker = create_test_tracker(640, 480)
        tracker.center = (640, 480)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_center_coordinates(tracker)

        assert tracker.normalized_center[0] == pytest.approx(1.0, abs=0.01)
        assert tracker.normalized_center[1] == pytest.approx(1.0, abs=0.01)

    def test_center_at_right_edge_center(self):
        """Target at right edge center should normalize to (1, 0)."""
        tracker = create_test_tracker(640, 480)
        tracker.center = (640, 240)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_center_coordinates(tracker)

        assert tracker.normalized_center[0] == pytest.approx(1.0, abs=0.01)
        assert abs(tracker.normalized_center[1]) < 0.01

    def test_center_at_bottom_center(self):
        """Target at bottom center should normalize to (0, 1)."""
        tracker = create_test_tracker(640, 480)
        tracker.center = (320, 480)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_center_coordinates(tracker)

        assert abs(tracker.normalized_center[0]) < 0.01
        assert tracker.normalized_center[1] == pytest.approx(1.0, abs=0.01)

    def test_normalize_with_different_resolution(self):
        """Normalization should work with different frame resolutions."""
        tracker = create_test_tracker(1920, 1080)
        tracker.center = (960, 540)  # Center of 1920x1080

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_center_coordinates(tracker)

        assert abs(tracker.normalized_center[0]) < 0.01
        assert abs(tracker.normalized_center[1]) < 0.01

    def test_normalize_with_none_center_does_nothing(self):
        """Normalization with None center should not crash."""
        tracker = create_test_tracker()
        tracker.center = None

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_center_coordinates(tracker)

        # Should not set normalized_center if center is None
        assert tracker.normalized_center is None

    def test_normalize_quarter_positions(self):
        """Test normalization at quarter positions."""
        tracker = create_test_tracker(640, 480)

        # Quarter position (160, 120) should normalize to approximately (-0.5, -0.5)
        tracker.center = (160, 120)
        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_center_coordinates(tracker)

        assert tracker.normalized_center[0] == pytest.approx(-0.5, abs=0.01)
        assert tracker.normalized_center[1] == pytest.approx(-0.5, abs=0.01)


@pytest.mark.unit
class TestComputeMotionConfidence:
    """Tests for compute_motion_confidence method."""

    def test_motion_confidence_no_prev_center_returns_one(self):
        """Without previous center, confidence should be 1.0."""
        tracker = create_test_tracker()
        tracker.prev_center = None
        tracker.center = (320, 240)

        from classes.trackers.base_tracker import BaseTracker
        confidence = BaseTracker.compute_motion_confidence(tracker)

        assert confidence == 1.0

    def test_motion_confidence_no_movement_returns_one(self):
        """Without movement, confidence should be 1.0."""
        tracker = create_test_tracker()
        tracker.prev_center = (320, 240)
        tracker.center = (320, 240)

        from classes.trackers.base_tracker import BaseTracker
        confidence = BaseTracker.compute_motion_confidence(tracker)

        assert confidence == 1.0

    def test_motion_confidence_small_movement_high_confidence(self):
        """Small movement should yield high confidence."""
        tracker = create_test_tracker()
        tracker.prev_center = (320, 240)
        tracker.center = (325, 245)  # 7 pixel displacement

        from classes.trackers.base_tracker import BaseTracker
        confidence = BaseTracker.compute_motion_confidence(tracker)

        assert confidence > 0.9

    def test_motion_confidence_large_movement_lower_confidence(self):
        """Large movement should yield lower confidence."""
        tracker = create_test_tracker()
        tracker.prev_center = (320, 240)
        tracker.center = (520, 440)  # 283 pixel displacement

        from classes.trackers.base_tracker import BaseTracker
        confidence = BaseTracker.compute_motion_confidence(tracker)

        assert confidence < 0.9

    def test_motion_confidence_without_video_handler_returns_one(self):
        """Without video_handler, should return 1.0."""
        tracker = create_test_tracker()
        tracker.video_handler = None
        tracker.prev_center = (320, 240)
        tracker.center = (520, 440)

        from classes.trackers.base_tracker import BaseTracker
        confidence = BaseTracker.compute_motion_confidence(tracker)

        assert confidence == 1.0

    def test_motion_confidence_always_between_zero_and_one(self):
        """Motion confidence should always be in [0, 1] range."""
        tracker = create_test_tracker()
        tracker.prev_center = (0, 0)
        tracker.center = (640, 480)  # Maximum possible movement

        from classes.trackers.base_tracker import BaseTracker
        confidence = BaseTracker.compute_motion_confidence(tracker)

        assert 0.0 <= confidence <= 1.0


@pytest.mark.unit
class TestIsBoundaryDetection:
    """Tests for is_near_boundary method."""

    def test_center_not_near_boundary(self):
        """Target at center should not be near boundary."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (295, 215, 50, 50)  # Center of frame

        from classes.trackers.base_tracker import BaseTracker
        result = BaseTracker.is_near_boundary(tracker)

        assert result is False

    def test_left_edge_near_boundary(self):
        """Target at left edge should be near boundary."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (5, 240, 50, 50)  # Near left edge

        from classes.trackers.base_tracker import BaseTracker
        result = BaseTracker.is_near_boundary(tracker)

        assert result is True

    def test_top_edge_near_boundary(self):
        """Target at top edge should be near boundary."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (320, 5, 50, 50)  # Near top edge

        from classes.trackers.base_tracker import BaseTracker
        result = BaseTracker.is_near_boundary(tracker)

        assert result is True

    def test_right_edge_near_boundary(self):
        """Target at right edge should be near boundary."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (585, 240, 50, 50)  # Near right edge (585 + 50 = 635 > 625)

        from classes.trackers.base_tracker import BaseTracker
        result = BaseTracker.is_near_boundary(tracker)

        assert result is True

    def test_bottom_edge_near_boundary(self):
        """Target at bottom edge should be near boundary."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (320, 425, 50, 50)  # Near bottom edge (425 + 50 = 475 > 465)

        from classes.trackers.base_tracker import BaseTracker
        result = BaseTracker.is_near_boundary(tracker)

        assert result is True

    def test_custom_margin(self):
        """Custom margin should be respected."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (30, 30, 50, 50)  # 30 pixels from edge

        from classes.trackers.base_tracker import BaseTracker

        # With default margin (15), should not be near boundary
        result_default = BaseTracker.is_near_boundary(tracker)

        # With larger margin (50), should be near boundary
        result_large = BaseTracker.is_near_boundary(tracker, margin=50)

        assert result_default is False
        assert result_large is True


@pytest.mark.unit
class TestGetBoundaryStatus:
    """Tests for get_boundary_status method."""

    def test_boundary_status_center_position(self):
        """Center position should report not near boundary."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (295, 215, 50, 50)

        from classes.trackers.base_tracker import BaseTracker
        status = BaseTracker.get_boundary_status(tracker)

        assert status['near_boundary'] is False
        assert len(status['edges']) == 0
        assert status['min_distance'] > 15

    def test_boundary_status_edge_position(self):
        """Edge position should report near boundary with edge info."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (5, 240, 50, 50)  # Near left edge

        from classes.trackers.base_tracker import BaseTracker
        status = BaseTracker.get_boundary_status(tracker)

        assert status['near_boundary'] is True
        assert 'left' in status['edges']

    def test_boundary_status_corner_position(self):
        """Corner position should report multiple edges."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (5, 5, 50, 50)  # Top-left corner

        from classes.trackers.base_tracker import BaseTracker
        status = BaseTracker.get_boundary_status(tracker)

        assert status['near_boundary'] is True
        assert 'left' in status['edges']
        assert 'top' in status['edges']


@pytest.mark.unit
class TestSetCenter:
    """Tests for set_center method."""

    def test_set_center_updates_center(self):
        """set_center should update center attribute."""
        tracker = create_test_tracker()
        tracker.center = None

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.set_center(tracker, (400, 300))

        assert tracker.center == (400, 300)

    def test_set_center_normalizes_coordinates(self):
        """set_center should trigger normalization."""
        tracker = create_test_tracker(640, 480)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.set_center(tracker, (320, 240))

        assert tracker.normalized_center is not None
        assert abs(tracker.normalized_center[0]) < 0.01
        assert abs(tracker.normalized_center[1]) < 0.01

    def test_set_center_multiple_times(self):
        """set_center can be called multiple times."""
        tracker = create_test_tracker(640, 480)

        from classes.trackers.base_tracker import BaseTracker

        BaseTracker.set_center(tracker, (100, 100))
        assert tracker.center == (100, 100)

        BaseTracker.set_center(tracker, (500, 400))
        assert tracker.center == (500, 400)

    def test_set_center_with_floats(self):
        """set_center should handle float values."""
        tracker = create_test_tracker(640, 480)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.set_center(tracker, (320.5, 240.5))

        assert tracker.center == (320.5, 240.5)

    def test_set_center_with_tuple(self):
        """set_center should work with tuple input."""
        tracker = create_test_tracker()

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.set_center(tracker, (200, 150))

        assert tracker.center[0] == 200
        assert tracker.center[1] == 150


@pytest.mark.unit
class TestGetOutput:
    """Tests for get_output method."""

    def test_get_output_returns_tracker_output(self):
        """get_output should return TrackerOutput instance."""
        tracker = create_test_tracker()
        tracker.tracking_started = True
        tracker.center = (320, 240)
        tracker.bbox = (295, 215, 50, 50)
        tracker.normalized_center = (0.0, 0.0)

        from classes.trackers.base_tracker import BaseTracker
        from classes.tracker_output import TrackerOutput
        output = BaseTracker.get_output(tracker)

        assert isinstance(output, TrackerOutput)

    def test_get_output_has_correct_data_type(self):
        """get_output should set POSITION_2D data type for base tracker."""
        tracker = create_test_tracker()
        tracker.tracking_started = True
        tracker.normalized_center = (0.0, 0.0)

        from classes.trackers.base_tracker import BaseTracker
        from classes.tracker_output import TrackerDataType
        output = BaseTracker.get_output(tracker)

        assert output.data_type == TrackerDataType.POSITION_2D

    def test_get_output_has_timestamp(self):
        """get_output should include current timestamp."""
        tracker = create_test_tracker()
        tracker.tracking_started = True
        tracker.normalized_center = (0.0, 0.0)  # Required for schema validation

        before = time.time()
        from classes.trackers.base_tracker import BaseTracker
        output = BaseTracker.get_output(tracker)
        after = time.time()

        assert before <= output.timestamp <= after

    def test_get_output_tracking_active_matches_state(self):
        """tracking_active should match tracking_started."""
        tracker = create_test_tracker()
        tracker.normalized_center = (0.0, 0.0)  # Required for schema validation

        from classes.trackers.base_tracker import BaseTracker

        tracker.tracking_started = True
        output_active = BaseTracker.get_output(tracker)
        assert output_active.tracking_active is True

        tracker.tracking_started = False
        output_inactive = BaseTracker.get_output(tracker)
        assert output_inactive.tracking_active is False

    def test_get_output_includes_position_2d(self):
        """get_output should include normalized_center as position_2d."""
        tracker = create_test_tracker()
        tracker.tracking_started = True
        tracker.normalized_center = (0.5, -0.3)

        from classes.trackers.base_tracker import BaseTracker
        output = BaseTracker.get_output(tracker)

        assert output.position_2d == (0.5, -0.3)


@pytest.mark.unit
class TestGetCapabilities:
    """Tests for get_capabilities method."""

    def test_get_capabilities_returns_dict(self):
        """get_capabilities should return a dictionary."""
        tracker = create_test_tracker()

        from classes.trackers.base_tracker import BaseTracker
        capabilities = BaseTracker.get_capabilities(tracker)

        assert isinstance(capabilities, dict)

    def test_get_capabilities_includes_data_types(self):
        """get_capabilities should include data_types list."""
        tracker = create_test_tracker()

        from classes.trackers.base_tracker import BaseTracker
        capabilities = BaseTracker.get_capabilities(tracker)

        assert 'data_types' in capabilities
        assert isinstance(capabilities['data_types'], list)

    def test_get_capabilities_includes_confidence_support(self):
        """get_capabilities should indicate confidence support."""
        tracker = create_test_tracker()

        from classes.trackers.base_tracker import BaseTracker
        capabilities = BaseTracker.get_capabilities(tracker)

        assert 'supports_confidence' in capabilities
        assert capabilities['supports_confidence'] is True


@pytest.mark.unit
class TestUpdateTime:
    """Tests for update_time method."""

    def test_update_time_returns_positive_dt(self):
        """update_time should return positive time delta."""
        tracker = create_test_tracker()
        tracker.last_update_time = time.monotonic() - 0.1

        from classes.trackers.base_tracker import BaseTracker
        dt = BaseTracker.update_time(tracker)

        assert dt > 0

    def test_update_time_updates_last_update_time(self):
        """update_time should update last_update_time."""
        tracker = create_test_tracker()
        old_time = tracker.last_update_time

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.update_time(tracker)

        assert tracker.last_update_time > old_time

    def test_update_time_minimum_dt(self):
        """update_time should return positive dt even for very short intervals."""
        tracker = create_test_tracker()
        tracker.last_update_time = time.monotonic()  # Just now

        from classes.trackers.base_tracker import BaseTracker
        dt = BaseTracker.update_time(tracker)

        # Should return non-negative value (actual elapsed time)
        assert dt >= 0


@pytest.mark.unit
class TestReset:
    """Tests for reset method."""

    def test_reset_clears_bbox(self):
        """reset should clear bbox."""
        tracker = create_test_tracker()
        tracker.bbox = (100, 100, 50, 50)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.reset(tracker)

        assert tracker.bbox is None

    def test_reset_clears_center(self):
        """reset should clear center."""
        tracker = create_test_tracker()
        tracker.center = (125, 125)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.reset(tracker)

        assert tracker.center is None

    def test_reset_clears_center_history(self):
        """reset should clear center_history."""
        tracker = create_test_tracker()
        tracker.center_history.append((100, 100))
        tracker.center_history.append((110, 110))

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.reset(tracker)

        assert len(tracker.center_history) == 0

    def test_reset_clears_override_state(self):
        """reset should clear override state."""
        tracker = create_test_tracker()
        tracker.override_active = True
        tracker.override_bbox = (100, 100, 50, 50)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.reset(tracker)

        assert tracker.override_active is False
        assert tracker.override_bbox is None


@pytest.mark.unit
class TestNormalizeBbox:
    """Tests for normalize_bbox method."""

    def test_normalize_bbox_center_frame(self):
        """Bbox at center should normalize near (0, 0, w/W, h/H)."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (295, 215, 50, 50)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_bbox(tracker)

        assert tracker.normalized_bbox is not None
        # X position near center (with tolerance for different normalization methods)
        assert abs(tracker.normalized_bbox[0]) < 0.15
        # Y position near center
        assert abs(tracker.normalized_bbox[1]) < 0.15

    def test_normalize_bbox_size_components(self):
        """Bbox width/height should normalize as fraction of frame."""
        tracker = create_test_tracker(640, 480)
        tracker.bbox = (0, 0, 64, 48)  # 10% of frame

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_bbox(tracker)

        assert tracker.normalized_bbox is not None
        assert tracker.normalized_bbox[2] == pytest.approx(0.1, abs=0.01)  # width
        assert tracker.normalized_bbox[3] == pytest.approx(0.1, abs=0.01)  # height

    def test_normalize_bbox_without_video_handler(self):
        """normalize_bbox should handle missing video_handler."""
        tracker = create_test_tracker()
        tracker.video_handler = None
        tracker.bbox = (100, 100, 50, 50)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.normalize_bbox(tracker)

        # Should not crash, normalized_bbox may remain None
        # No assertion on result, just checking it doesn't crash


@pytest.mark.unit
class TestExternalOverride:
    """Tests for external override methods."""

    def test_set_external_override_enables_override(self):
        """set_external_override should enable override mode."""
        tracker = create_test_tracker(640, 480)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.set_external_override(tracker, (100, 100, 200, 200), (150, 150))

        assert tracker.override_active is True

    def test_set_external_override_sets_bbox(self):
        """set_external_override should set bbox from x1,y1,x2,y2."""
        tracker = create_test_tracker(640, 480)

        from classes.trackers.base_tracker import BaseTracker
        # Input is (x1, y1, x2, y2), should convert to (x, y, w, h)
        BaseTracker.set_external_override(tracker, (100, 100, 200, 200), (150, 150))

        assert tracker.bbox == (100, 100, 100, 100)  # w=200-100, h=200-100

    def test_clear_external_override(self):
        """clear_external_override should disable override mode."""
        tracker = create_test_tracker()
        tracker.override_active = True
        tracker.bbox = (100, 100, 50, 50)

        from classes.trackers.base_tracker import BaseTracker
        BaseTracker.clear_external_override(tracker)

        assert tracker.override_active is False
        assert tracker.bbox is None
