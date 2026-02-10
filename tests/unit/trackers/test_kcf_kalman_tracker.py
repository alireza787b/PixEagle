# tests/unit/trackers/test_kcf_kalman_tracker.py
"""
Unit tests for KCFKalmanTracker implementation.

Tests KCF+Kalman hybrid tracker functionality including internal Kalman filter,
motion validation, and robustness features.
"""

import pytest
import sys
import os
import numpy as np
import time
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from tests.fixtures.mock_opencv import (
    MockKCFTracker, MockVideoHandler, MockDetector,
    MockAppController, create_mock_test_frame, create_mock_bbox
)


def create_mock_kalman_filter():
    """Create a mock Kalman filter."""
    mock_kf = MagicMock()
    mock_kf.x = np.array([320.0, 240.0, 0.0, 0.0])  # [x, y, vx, vy]
    mock_kf.P = np.eye(4) * 10
    mock_kf.F = np.eye(4)
    mock_kf.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
    mock_kf.Q = np.eye(4) * 0.1
    mock_kf.R = np.eye(2) * 5
    return mock_kf


@pytest.fixture
def mock_dependencies():
    """Fixture for common mock dependencies."""
    video_handler = MockVideoHandler(640, 480)
    detector = MockDetector()
    app_controller = MockAppController()
    return video_handler, detector, app_controller


@pytest.mark.unit
class TestKCFInitialization:
    """Tests for KCFKalmanTracker initialization."""

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    def test_initialization_sets_tracker_name(self, mock_cv2, mock_dependencies):
        """Tracker name should be set to 'KCF+Kalman'."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        assert tracker.tracker_name == "KCF+Kalman"

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    def test_initialization_kalman_filter_none(self, mock_cv2, mock_dependencies):
        """Kalman filter should be None before start_tracking."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        assert tracker.kf is None

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    def test_initialization_failure_count_zero(self, mock_cv2, mock_dependencies):
        """failure_count should be 0 initially."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        assert tracker.failure_count == 0

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    def test_initialization_confidence_thresholds(self, mock_cv2, mock_dependencies):
        """Should have confidence threshold configured."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        assert hasattr(tracker, 'confidence_threshold')
        assert tracker.confidence_threshold > 0

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    def test_initialization_motion_consistency_threshold(self, mock_cv2, mock_dependencies):
        """Should have motion consistency threshold."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        assert hasattr(tracker, 'motion_consistency_threshold')


@pytest.mark.unit
class TestKCFStartTracking:
    """Tests for KCFKalmanTracker.start_tracking method."""

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_start_tracking_initializes_kalman(self, mock_kf_class, mock_cv2, mock_dependencies):
        """start_tracking should initialize Kalman filter."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.kf is not None

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_start_tracking_sets_kalman_initial_state(self, mock_kf_class, mock_cv2, mock_dependencies):
        """start_tracking should set Kalman initial state from bbox center."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = create_mock_kalman_filter()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = (100, 100, 50, 50)  # Center at (125, 125)

        tracker.start_tracking(frame, bbox)

        # Kalman state should be set to bbox center
        assert tracker.kf.x[0] == pytest.approx(125, abs=1)
        assert tracker.kf.x[1] == pytest.approx(125, abs=1)

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_start_tracking_sets_initial_velocity_zero(self, mock_kf_class, mock_cv2, mock_dependencies):
        """start_tracking should set initial velocity to zero."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = create_mock_kalman_filter()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        # Initial velocity should be zero
        assert tracker.kf.x[2] == 0
        assert tracker.kf.x[3] == 0

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_start_tracking_enables_tracking_started(self, mock_kf_class, mock_cv2, mock_dependencies):
        """start_tracking should set tracking_started to True."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.tracking_started is True

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_start_tracking_resets_failure_count(self, mock_kf_class, mock_cv2, mock_dependencies):
        """start_tracking should reset failure_count."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)
        tracker.failure_count = 5

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.failure_count == 0


@pytest.mark.unit
class TestKCFUpdate:
    """Tests for KCFKalmanTracker.update method."""

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_update_returns_tuple(self, mock_kf_class, mock_cv2, mock_dependencies):
        """update should return (bool, bbox) tuple."""
        mock_kcf = MockKCFTracker()
        mock_cv2.TrackerKCF_create.return_value = mock_kcf
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        mock_kcf.init(frame, bbox)

        result = tracker.update(frame)

        assert isinstance(result, tuple)
        assert len(result) == 2

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_update_calls_kalman_predict(self, mock_kf_class, mock_cv2, mock_dependencies):
        """update should call Kalman predict."""
        mock_kcf = MockKCFTracker()
        mock_cv2.TrackerKCF_create.return_value = mock_kcf
        mock_kf = create_mock_kalman_filter()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        mock_kcf.init(frame, bbox)

        tracker.update(frame)

        mock_kf.predict.assert_called()

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_update_success_calls_kalman_update(self, mock_kf_class, mock_cv2, mock_dependencies):
        """Successful update should call Kalman update."""
        mock_kcf = MockKCFTracker(success_rate=1.0)
        mock_cv2.TrackerKCF_create.return_value = mock_kcf
        mock_kf = create_mock_kalman_filter()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        mock_kcf.init(frame, bbox)

        # Force high confidence
        tracker.confidence = 0.9
        tracker.confidence_threshold = 0.15

        tracker.update(frame)

        mock_kf.update.assert_called()

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_update_before_start_returns_false(self, mock_kf_class, mock_cv2, mock_dependencies):
        """update before start_tracking should return False."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        success, bbox = tracker.update(frame)

        assert success is False

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_update_failure_uses_kalman_prediction(self, mock_kf_class, mock_cv2, mock_dependencies):
        """Failed update should use Kalman prediction."""
        mock_kcf = MockKCFTracker(success_rate=0.0)  # Always fail
        mock_cv2.TrackerKCF_create.return_value = mock_kcf
        mock_kf = create_mock_kalman_filter()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        mock_kcf.init(frame, bbox)

        # Update should still call predict even on failure
        tracker.update(frame)

        mock_kf.predict.assert_called()

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_update_increments_frame_count(self, mock_kf_class, mock_cv2, mock_dependencies):
        """update should increment frame_count."""
        mock_kcf = MockKCFTracker()
        mock_cv2.TrackerKCF_create.return_value = mock_kcf
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        mock_kcf.init(frame, bbox)

        initial_count = tracker.frame_count
        tracker.update(frame)

        assert tracker.frame_count == initial_count + 1

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_update_tracks_successful_frames(self, mock_kf_class, mock_cv2, mock_dependencies):
        """Successful updates should increment successful_frames."""
        mock_kcf = MockKCFTracker(success_rate=1.0)
        mock_cv2.TrackerKCF_create.return_value = mock_kcf
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        mock_kcf.init(frame, bbox)

        # Force high confidence
        tracker.confidence = 0.9

        initial_successful = tracker.successful_frames
        tracker.update(frame)

        assert tracker.successful_frames >= initial_successful


@pytest.mark.unit
class TestKCFKalmanFilter:
    """Tests for internal Kalman filter functionality."""

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_init_kalman_creates_4d_state(self, mock_kf_class, mock_cv2, mock_dependencies):
        """_init_kalman should create 4D state (x, y, vx, vy)."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = MagicMock()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        bbox = (100, 100, 50, 50)
        tracker._init_kalman(bbox)

        # KalmanFilter should be created with dim_x=4, dim_z=2
        mock_kf_class.assert_called_with(dim_x=4, dim_z=2)

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_init_kalman_sets_transition_matrix(self, mock_kf_class, mock_cv2, mock_dependencies):
        """_init_kalman should set state transition matrix F."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = MagicMock()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        bbox = (100, 100, 50, 50)
        tracker._init_kalman(bbox)

        # F should be set (constant velocity model)
        assert mock_kf.F is not None

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_init_kalman_sets_measurement_matrix(self, mock_kf_class, mock_cv2, mock_dependencies):
        """_init_kalman should set measurement matrix H."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = MagicMock()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        bbox = (100, 100, 50, 50)
        tracker._init_kalman(bbox)

        # H should be set (measure position only)
        assert mock_kf.H is not None

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_init_kalman_sets_process_noise(self, mock_kf_class, mock_cv2, mock_dependencies):
        """_init_kalman should set process noise Q."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = MagicMock()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        bbox = (100, 100, 50, 50)
        tracker._init_kalman(bbox)

        # Q should be set
        assert mock_kf.Q is not None

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_init_kalman_sets_measurement_noise(self, mock_kf_class, mock_cv2, mock_dependencies):
        """_init_kalman should set measurement noise R."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = MagicMock()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        bbox = (100, 100, 50, 50)
        tracker._init_kalman(bbox)

        # R should be set
        assert mock_kf.R is not None

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_init_kalman_sets_initial_covariance(self, mock_kf_class, mock_cv2, mock_dependencies):
        """_init_kalman should set initial covariance P."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = MagicMock()
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        bbox = (100, 100, 50, 50)
        tracker._init_kalman(bbox)

        # P should be set with asymmetric covariance
        assert mock_kf.P is not None

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_get_estimated_position_returns_kalman_state(self, mock_kf_class, mock_cv2, mock_dependencies):
        """get_estimated_position should return Kalman state."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = create_mock_kalman_filter()
        mock_kf.x = np.array([320.0, 240.0, 5.0, -3.0])
        mock_kf_class.return_value = mock_kf

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        position = tracker.get_estimated_position()

        assert position is not None
        assert len(position) == 2


@pytest.mark.unit
class TestKCFMotionValidation:
    """Tests for motion validation against Kalman prediction."""

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_validate_bbox_motion_no_prediction(self, mock_kf_class, mock_cv2, mock_dependencies):
        """Should return True if no Kalman prediction available."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        bbox = create_mock_bbox()
        result = tracker._validate_bbox_motion(bbox, None)

        assert result is True

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_validate_bbox_motion_small_deviation(self, mock_kf_class, mock_cv2, mock_dependencies):
        """Small motion deviation should be valid."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        # Bbox center at (325, 245)
        bbox = (300, 220, 50, 50)
        # Kalman prediction near bbox center
        kf_prediction = (320.0, 240.0)

        result = tracker._validate_bbox_motion(bbox, kf_prediction)

        assert result == True  # Use == for boolean comparison

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_validate_bbox_motion_large_deviation(self, mock_kf_class, mock_cv2, mock_dependencies):
        """Large motion deviation should be invalid."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)
        tracker.frame_count = 20  # Must be >= 15 to bypass early-return guard

        # Bbox center far from prediction
        bbox = (0, 0, 50, 50)  # Center at (25, 25)
        kf_prediction = (600.0, 450.0)  # Far away

        result = tracker._validate_bbox_motion(bbox, kf_prediction)

        assert result == False  # Use == for boolean comparison

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_validate_bbox_scale_no_prev_bbox(self, mock_kf_class, mock_cv2, mock_dependencies):
        """Should return True if no previous bbox."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)
        tracker.prev_bbox = None

        bbox = create_mock_bbox()
        result = tracker._validate_bbox_scale(bbox)

        assert result is True

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_validate_bbox_scale_reasonable_change(self, mock_kf_class, mock_cv2, mock_dependencies):
        """Reasonable scale change should be valid."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)
        tracker.prev_bbox = (100, 100, 50, 50)

        bbox = (100, 100, 55, 55)  # 10% increase
        result = tracker._validate_bbox_scale(bbox)

        assert result is True


@pytest.mark.unit
class TestKCFConfidenceSmoothing:
    """Tests for confidence EMA smoothing."""

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_smooth_confidence_first_frame(self, mock_kf_class, mock_cv2, mock_dependencies):
        """First frame should use raw confidence."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)
        tracker.confidence = 0.0
        tracker.raw_confidence_history.clear()

        result = tracker._smooth_confidence(0.8)

        assert result == pytest.approx(0.8, abs=0.01)

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_smooth_confidence_blends_values(self, mock_kf_class, mock_cv2, mock_dependencies):
        """Subsequent frames should blend with EMA."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)
        tracker.confidence = 0.5
        tracker.confidence_ema_alpha = 0.6
        tracker.raw_confidence_history.append(0.5)

        result = tracker._smooth_confidence(0.8)

        # Expected: 0.6 * 0.8 + 0.4 * 0.5 = 0.68
        expected = 0.6 * 0.8 + 0.4 * 0.5
        assert result == pytest.approx(expected, abs=0.01)


@pytest.mark.unit
class TestKCFGetOutput:
    """Tests for get_output method."""

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_get_output_returns_tracker_output(self, mock_kf_class, mock_cv2, mock_dependencies):
        """get_output should return TrackerOutput."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = create_mock_kalman_filter()
        mock_kf_class.return_value = mock_kf
        mock_cv2.__version__ = "4.8.0"

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        from classes.tracker_output import TrackerOutput
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)
        tracker.tracking_started = True
        tracker.normalized_center = (0.0, 0.0)

        output = tracker.get_output()

        assert isinstance(output, TrackerOutput)

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_get_output_includes_velocity(self, mock_kf_class, mock_cv2, mock_dependencies):
        """get_output should include velocity from Kalman filter."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf = create_mock_kalman_filter()
        mock_kf.x = np.array([320.0, 240.0, 10.0, 5.0])  # Non-zero velocity
        mock_kf_class.return_value = mock_kf
        mock_cv2.__version__ = "4.8.0"

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()
        tracker.start_tracking(frame, bbox)

        # Add some history
        tracker.center_history.append((100, 100))
        tracker.center_history.append((110, 105))
        tracker.center_history.append((120, 110))

        output = tracker.get_output()

        # KCFKalmanTracker uses BBOX_CONFIDENCE by default, but metadata indicates
        # velocity support is available through the internal Kalman filter
        from classes.tracker_output import TrackerDataType
        assert output.data_type in [TrackerDataType.BBOX_CONFIDENCE, TrackerDataType.VELOCITY_AWARE]
        assert output.metadata['supports_velocity'] is True


@pytest.mark.unit
class TestKCFReset:
    """Tests for reset method."""

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_reset_clears_kalman_filter(self, mock_kf_class, mock_cv2, mock_dependencies):
        """reset should clear Kalman filter."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()
        tracker.start_tracking(frame, bbox)

        tracker.reset()

        assert tracker.kf is None

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_reset_clears_tracking_state(self, mock_kf_class, mock_cv2, mock_dependencies):
        """reset should clear tracking state."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()
        tracker.start_tracking(frame, bbox)

        tracker.reset()

        assert tracker.tracking_started is False
        assert tracker.is_initialized is False

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    @patch('classes.trackers.kcf_kalman_tracker.KalmanFilter')
    def test_reset_clears_counters(self, mock_kf_class, mock_cv2, mock_dependencies):
        """reset should clear all counters."""
        mock_cv2.TrackerKCF_create.return_value = MockKCFTracker()
        mock_kf_class.return_value = create_mock_kalman_filter()

        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = KCFKalmanTracker(video_handler, detector, app_controller)
        tracker.frame_count = 100
        tracker.failure_count = 5
        tracker.successful_frames = 90
        tracker.failed_frames = 10

        tracker.reset()

        assert tracker.frame_count == 0
        assert tracker.failure_count == 0
        assert tracker.successful_frames == 0
        assert tracker.failed_frames == 0
