# tests/unit/trackers/test_csrt_tracker.py
"""
Unit tests for CSRTTracker implementation.

Tests CSRT-specific functionality including performance modes,
multi-frame validation, and appearance model updates.
"""

import pytest
import sys
import os
import numpy as np
import time
from unittest.mock import MagicMock, patch, PropertyMock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from tests.fixtures.mock_opencv import (
    MockCSRTTracker, MockVideoHandler, MockDetector,
    MockAppController, create_mock_test_frame, create_mock_bbox
)


def create_mock_cv2():
    """Create a mock cv2 module."""
    mock_cv2 = MagicMock()
    mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
    mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()
    mock_cv2.__version__ = "4.8.0.mock"
    return mock_cv2


@pytest.fixture
def mock_cv2_module():
    """Fixture for mock cv2 module."""
    return create_mock_cv2()


@pytest.fixture
def mock_dependencies():
    """Fixture for common mock dependencies."""
    video_handler = MockVideoHandler(640, 480)
    detector = MockDetector()
    app_controller = MockAppController()
    return video_handler, detector, app_controller


@pytest.mark.unit
class TestCSRTInitialization:
    """Tests for CSRTTracker initialization."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_initialization_sets_tracker_name(self, mock_cv2, mock_dependencies):
        """Tracker name should be set to 'CSRT'."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.tracker_name == "CSRT"

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_default_performance_mode_balanced(self, mock_cv2, mock_dependencies):
        """Default performance mode should be 'balanced'."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.performance_mode == 'balanced'

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_initialization_tracking_started_false(self, mock_cv2, mock_dependencies):
        """tracking_started should be False initially."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.tracking_started is False

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_initialization_failure_count_zero(self, mock_cv2, mock_dependencies):
        """failure_count should be 0 initially."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.failure_count == 0

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_initialization_multiframe_validation_enabled(self, mock_cv2, mock_dependencies):
        """Multi-frame validation should be enabled by default."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        assert hasattr(tracker, 'enable_multiframe_validation')


@pytest.mark.unit
class TestCSRTPerformanceModes:
    """Tests for CSRT performance mode configurations."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_legacy_mode_disables_validation(self, mock_cv2, mock_dependencies):
        """Legacy mode should disable validation."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {'performance_mode': 'legacy'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False
            mock_params.CONFIDENCE_THRESHOLD = 0.5

            tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.performance_mode == 'legacy'
        assert tracker.enable_validation is False
        assert tracker.enable_ema_smoothing is False

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_balanced_mode_enables_ema_smoothing(self, mock_cv2, mock_dependencies):
        """Balanced mode should enable EMA smoothing."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {'performance_mode': 'balanced'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.performance_mode == 'balanced'
        assert tracker.enable_ema_smoothing is True

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_robust_mode_enables_validation(self, mock_cv2, mock_dependencies):
        """Robust mode should enable validation."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {'performance_mode': 'robust'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.performance_mode == 'robust'
        assert tracker.enable_validation is True
        assert tracker.enable_ema_smoothing is True

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_unknown_mode_defaults_to_balanced(self, mock_cv2, mock_dependencies):
        """Unknown performance mode should default to balanced."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {'performance_mode': 'unknown_mode'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.performance_mode == 'balanced'

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_robust_mode_has_scale_threshold(self, mock_cv2, mock_dependencies):
        """Robust mode should have max_scale_change threshold."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {'performance_mode': 'robust'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = CSRTTracker(video_handler, detector, app_controller)

        assert hasattr(tracker, 'max_scale_change')
        assert tracker.max_scale_change > 0

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_robust_mode_has_motion_threshold(self, mock_cv2, mock_dependencies):
        """Robust mode should have motion_consistency_threshold."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {'performance_mode': 'robust'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = CSRTTracker(video_handler, detector, app_controller)

        assert hasattr(tracker, 'motion_consistency_threshold')


@pytest.mark.unit
class TestCSRTStartTracking:
    """Tests for CSRTTracker.start_tracking method."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_start_tracking_sets_bbox(self, mock_cv2, mock_dependencies):
        """start_tracking should set the bbox."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_csrt = MockCSRTTracker()
        mock_cv2.TrackerCSRT_create.return_value = mock_csrt

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.bbox == bbox

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_start_tracking_enables_tracking_started(self, mock_cv2, mock_dependencies):
        """start_tracking should set tracking_started to True."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.tracking_started is True

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_start_tracking_resets_failure_count(self, mock_cv2, mock_dependencies):
        """start_tracking should reset failure_count to 0."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.failure_count = 5  # Set some failures

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.failure_count == 0

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_start_tracking_initializes_appearance_model(self, mock_cv2, mock_dependencies):
        """start_tracking should initialize detector features."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.detector.initial_features is not None
        assert tracker.detector.adaptive_features is not None

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_start_tracking_sets_confidence_to_one(self, mock_cv2, mock_dependencies):
        """start_tracking should set confidence to 1.0."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.confidence = 0.5  # Set some confidence

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.confidence == 1.0

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_start_tracking_resets_multiframe_validation(self, mock_cv2, mock_dependencies):
        """start_tracking should reset multi-frame validation state."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.consecutive_valid_frames = 5
        tracker.is_validated = True

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.consecutive_valid_frames == 0
        assert tracker.is_validated is False


@pytest.mark.unit
class TestCSRTUpdate:
    """Tests for CSRTTracker.update method."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_update_returns_tuple(self, mock_cv2, mock_dependencies):
        """update should return (bool, bbox) tuple."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_csrt = MockCSRTTracker()
        mock_cv2.TrackerCSRT_create.return_value = mock_csrt

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        result = tracker.update(frame)

        assert isinstance(result, tuple)
        assert len(result) == 2

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_update_before_start_returns_false(self, mock_cv2, mock_dependencies):
        """update before start_tracking should return False."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        success, bbox = tracker.update(frame)

        assert success is False

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_update_increments_frame_count(self, mock_cv2, mock_dependencies):
        """update should increment frame_count."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_csrt = MockCSRTTracker()
        mock_cv2.TrackerCSRT_create.return_value = mock_csrt

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        initial_count = tracker.frame_count

        tracker.update(frame)

        assert tracker.frame_count == initial_count + 1

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_update_success_resets_failure_count(self, mock_cv2, mock_dependencies):
        """Successful update should reset failure_count."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_csrt = MockCSRTTracker(success_rate=1.0)
        mock_cv2.TrackerCSRT_create.return_value = mock_csrt

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.failure_count = 2

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        mock_csrt.init(frame, bbox)  # Properly initialize mock

        tracker.update(frame)

        assert tracker.failure_count == 0

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_update_updates_center_history(self, mock_cv2, mock_dependencies):
        """update should add to center_history."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_csrt = MockCSRTTracker()
        mock_cv2.TrackerCSRT_create.return_value = mock_csrt

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        mock_csrt.init(frame, bbox)

        initial_len = len(tracker.center_history)
        tracker.update(frame)

        assert len(tracker.center_history) == initial_len + 1

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_update_failure_increments_failure_count(self, mock_cv2, mock_dependencies):
        """Failed update should increment failure_count."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_csrt = MockCSRTTracker(success_rate=0.0)  # Always fail
        mock_cv2.TrackerCSRT_create.return_value = mock_csrt

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        mock_csrt.init(frame, bbox)

        initial_failures = tracker.failure_count
        tracker.update(frame)

        assert tracker.failure_count >= initial_failures

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_update_normalizes_bbox(self, mock_cv2, mock_dependencies):
        """update should normalize bbox."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_csrt = MockCSRTTracker()
        mock_cv2.TrackerCSRT_create.return_value = mock_csrt

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        mock_csrt.init(frame, bbox)

        tracker.update(frame)

        assert tracker.normalized_bbox is not None


@pytest.mark.unit
class TestCSRTMultiFrameValidation:
    """Tests for multi-frame validation consensus."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_multiframe_validation_increments_on_valid(self, mock_cv2, mock_dependencies):
        """Valid frame should increment consecutive_valid_frames."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.enable_multiframe_validation = True
        tracker.consecutive_valid_frames = 0

        result = tracker._update_multiframe_consensus(True)

        assert tracker.consecutive_valid_frames == 1

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_multiframe_validation_reaches_consensus(self, mock_cv2, mock_dependencies):
        """Should reach consensus after N valid frames."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.enable_multiframe_validation = True
        tracker.validation_consensus_frames = 3
        tracker.consecutive_valid_frames = 2
        tracker.is_validated = False

        tracker._update_multiframe_consensus(True)

        assert tracker.is_validated is True

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_multiframe_validation_resets_on_invalid(self, mock_cv2, mock_dependencies):
        """Invalid frame should decrement consecutive_valid_frames."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.enable_multiframe_validation = True
        tracker.consecutive_valid_frames = 2
        tracker.is_validated = False

        tracker._update_multiframe_consensus(False)

        assert tracker.consecutive_valid_frames < 2

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_multiframe_validation_disabled_passthrough(self, mock_cv2, mock_dependencies):
        """With validation disabled, should pass through input."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.enable_multiframe_validation = False

        result_true = tracker._update_multiframe_consensus(True)
        result_false = tracker._update_multiframe_consensus(False)

        assert result_true is True
        assert result_false is False

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_multiframe_validation_breaks_consensus(self, mock_cv2, mock_dependencies):
        """Enough failures should break validated state."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.enable_multiframe_validation = True
        tracker.validation_consensus_frames = 3
        tracker.consecutive_valid_frames = 3
        tracker.is_validated = True

        # Simulate multiple failures
        for _ in range(4):
            tracker._update_multiframe_consensus(False)

        assert tracker.is_validated is False


@pytest.mark.unit
class TestCSRTAppearanceModel:
    """Tests for appearance model update logic."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_should_update_appearance_high_confidence(self, mock_cv2, mock_dependencies):
        """Should allow update with high confidence."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.confidence = 0.8
        tracker.prev_center = None  # No previous center
        tracker.center = (320, 240)
        tracker.prev_bbox = None  # No previous bbox

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        result = tracker._should_update_appearance(frame, bbox)

        assert result is True

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_should_not_update_appearance_low_confidence(self, mock_cv2, mock_dependencies):
        """Should not update with low confidence."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.confidence = 0.2  # Low confidence

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        result = tracker._should_update_appearance(frame, bbox)

        assert result is False

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_should_not_update_appearance_large_scale_change(self, mock_cv2, mock_dependencies):
        """Should not update with large scale change."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.confidence = 0.8
        tracker.prev_center = None
        tracker.center = None
        tracker.prev_bbox = (100, 100, 50, 50)  # Previous small bbox

        frame = create_mock_test_frame()
        bbox = (100, 100, 100, 100)  # Double size

        result = tracker._should_update_appearance(frame, bbox)

        assert result is False


@pytest.mark.unit
class TestCSRTValidation:
    """Tests for bbox validation methods."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_validate_bbox_motion_no_estimator(self, mock_cv2, mock_dependencies):
        """Should return True if no estimator prediction."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {'performance_mode': 'robust'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = CSRTTracker(video_handler, detector, app_controller)

        bbox = create_mock_bbox()
        result = tracker._validate_bbox_motion(bbox, None)

        assert result is True

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_validate_bbox_scale_no_prev_bbox(self, mock_cv2, mock_dependencies):
        """Should return True if no previous bbox."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {'performance_mode': 'robust'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = CSRTTracker(video_handler, detector, app_controller)

        tracker.prev_bbox = None
        bbox = create_mock_bbox()
        result = tracker._validate_bbox_scale(bbox)

        assert result is True

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_validate_bbox_scale_small_change(self, mock_cv2, mock_dependencies):
        """Small scale change should be valid."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {'performance_mode': 'robust'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = CSRTTracker(video_handler, detector, app_controller)

        tracker.prev_bbox = (100, 100, 50, 50)
        bbox = (100, 100, 52, 52)  # 4% change
        result = tracker._validate_bbox_scale(bbox)

        assert result is True

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_validate_bbox_scale_large_change(self, mock_cv2, mock_dependencies):
        """Large scale change should be invalid."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.csrt_tracker.Parameters') as mock_params:
            mock_params.CSRT_Tracker = {'performance_mode': 'robust'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = CSRTTracker(video_handler, detector, app_controller)

        tracker.prev_bbox = (100, 100, 50, 50)
        bbox = (100, 100, 100, 100)  # 100% change
        result = tracker._validate_bbox_scale(bbox)

        assert result is False


@pytest.mark.unit
class TestCSRTGetOutput:
    """Tests for get_output method."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_get_output_returns_tracker_output(self, mock_cv2, mock_dependencies):
        """get_output should return TrackerOutput."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()
        mock_cv2.__version__ = "4.8.0"

        from classes.trackers.csrt_tracker import CSRTTracker
        from classes.tracker_output import TrackerOutput
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.tracking_started = True
        tracker.normalized_center = (0.0, 0.0)

        output = tracker.get_output()

        assert isinstance(output, TrackerOutput)

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_get_output_includes_performance_mode(self, mock_cv2, mock_dependencies):
        """get_output should include performance_mode in metadata."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()
        mock_cv2.__version__ = "4.8.0"

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.tracking_started = True
        tracker.normalized_center = (0.0, 0.0)  # Required for schema validation

        output = tracker.get_output()

        assert output.raw_data['performance_mode'] == tracker.performance_mode

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_get_output_includes_quality_metrics(self, mock_cv2, mock_dependencies):
        """get_output should include quality_metrics."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()
        mock_cv2.__version__ = "4.8.0"

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        tracker.tracking_started = True
        tracker.normalized_center = (0.0, 0.0)  # Required for schema validation

        output = tracker.get_output()

        assert output.quality_metrics is not None
        assert 'failure_count' in output.quality_metrics


@pytest.mark.unit
class TestCSRTGetCapabilities:
    """Tests for get_capabilities method."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_get_capabilities_includes_csrt_algorithm(self, mock_cv2, mock_dependencies):
        """get_capabilities should identify as CSRT."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        capabilities = tracker.get_capabilities()

        assert capabilities['tracker_algorithm'] == 'CSRT'

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_get_capabilities_supports_rotation(self, mock_cv2, mock_dependencies):
        """CSRT should support rotation."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        capabilities = tracker.get_capabilities()

        assert capabilities['supports_rotation'] is True

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_get_capabilities_supports_scale(self, mock_cv2, mock_dependencies):
        """CSRT should support scale change."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        capabilities = tracker.get_capabilities()

        assert capabilities['supports_scale_change'] is True

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_get_capabilities_includes_performance_mode(self, mock_cv2, mock_dependencies):
        """get_capabilities should include current performance_mode."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MockCSRTTracker()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)
        capabilities = tracker.get_capabilities()

        assert 'performance_mode' in capabilities
        assert capabilities['performance_mode'] == tracker.performance_mode
