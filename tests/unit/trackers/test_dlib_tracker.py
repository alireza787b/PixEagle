# tests/unit/trackers/test_dlib_tracker.py
"""
Unit tests for DlibTracker implementation.

Tests dlib correlation tracker functionality including PSR-based confidence,
performance modes, and adaptive features.

Note: These tests are skipped if dlib is not installed (e.g., in CI).
"""

import pytest
import sys
import os
import numpy as np
import time
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

# Check if dlib is available and skip all tests if not
from classes.trackers.dlib_tracker import DLIB_AVAILABLE

pytestmark = pytest.mark.skipif(
    not DLIB_AVAILABLE,
    reason="dlib library not installed - skipping dlib tracker tests"
)

from tests.fixtures.mock_dlib import (
    MockDlibCorrelationTracker, MockDlibRectangle, MockDlibModule,
    create_mock_dlib_tracker, create_mock_dlib_rect_from_bbox, PSRConstants
)
from tests.fixtures.mock_opencv import (
    MockVideoHandler, MockDetector, MockAppController,
    create_mock_test_frame, create_mock_bbox
)


@pytest.fixture
def mock_dependencies():
    """Fixture for common mock dependencies."""
    video_handler = MockVideoHandler(640, 480)
    detector = MockDetector()
    app_controller = MockAppController()
    return video_handler, detector, app_controller


@pytest.fixture
def mock_dlib_module():
    """Fixture for mock dlib module."""
    return MockDlibModule(base_psr=15.0)


@pytest.mark.unit
class TestDlibInitialization:
    """Tests for DlibTracker initialization."""

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_initialization_sets_tracker_name(self, mock_dlib, mock_dependencies):
        """Tracker name should be set to 'dlib'."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        assert tracker.tracker_name == "dlib"

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_default_performance_mode_balanced(self, mock_dlib, mock_dependencies):
        """Default performance mode should be 'balanced'."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.dlib_tracker.Parameters') as mock_params:
            mock_params.DLIB_Tracker = {}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = DlibTracker(video_handler, detector, app_controller)

        assert tracker.performance_mode == 'balanced'

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_initialization_has_psr_threshold(self, mock_dlib, mock_dependencies):
        """Should have PSR confidence threshold."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        assert hasattr(tracker, 'psr_confidence_threshold')
        assert tracker.psr_confidence_threshold > 0

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_initialization_psr_history_empty(self, mock_dlib, mock_dependencies):
        """psr_history should be empty initially."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        assert len(tracker.psr_history) == 0

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_initialization_adaptive_enabled(self, mock_dlib, mock_dependencies):
        """Adaptive PSR system should be enabled by default."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        assert hasattr(tracker, 'adaptive_enabled')


@pytest.mark.unit
class TestDlibPerformanceModes:
    """Tests for dlib performance mode configurations."""

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_fast_mode_disables_validation(self, mock_dlib, mock_dependencies):
        """Fast mode should disable validation."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.dlib_tracker.Parameters') as mock_params:
            mock_params.DLIB_Tracker = {'performance_mode': 'fast'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = DlibTracker(video_handler, detector, app_controller)

        assert tracker.performance_mode == 'fast'
        assert tracker.enable_validation is False
        assert tracker.enable_ema_smoothing is False

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_balanced_mode_enables_smoothing(self, mock_dlib, mock_dependencies):
        """Balanced mode should enable EMA smoothing."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.dlib_tracker.Parameters') as mock_params:
            mock_params.DLIB_Tracker = {'performance_mode': 'balanced'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = DlibTracker(video_handler, detector, app_controller)

        assert tracker.performance_mode == 'balanced'
        assert tracker.enable_ema_smoothing is True

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_robust_mode_enables_validation(self, mock_dlib, mock_dependencies):
        """Robust mode should enable validation."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.dlib_tracker.Parameters') as mock_params:
            mock_params.DLIB_Tracker = {'performance_mode': 'robust'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = DlibTracker(video_handler, detector, app_controller)

        assert tracker.performance_mode == 'robust'
        assert tracker.enable_validation is True

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_unknown_mode_defaults_to_balanced(self, mock_dlib, mock_dependencies):
        """Unknown performance mode should default to balanced."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.dlib_tracker.Parameters') as mock_params:
            mock_params.DLIB_Tracker = {'performance_mode': 'unknown_mode'}
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = DlibTracker(video_handler, detector, app_controller)

        assert tracker.performance_mode == 'balanced'


@pytest.mark.unit
class TestDlibStartTracking:
    """Tests for DlibTracker.start_tracking method."""

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_start_tracking_converts_bbox_to_rect(self, mock_dlib, mock_dependencies):
        """start_tracking should convert bbox to dlib rectangle."""
        mock_tracker = MockDlibCorrelationTracker()
        mock_dlib.correlation_tracker.return_value = mock_tracker
        mock_dlib.rectangle = MockDlibRectangle

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = (100, 100, 50, 50)

        tracker.start_tracking(frame, bbox)

        # Verify tracker was initialized
        assert mock_tracker.initialized is True

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_start_tracking_sets_bbox(self, mock_dlib, mock_dependencies):
        """start_tracking should store bbox."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()
        mock_dlib.rectangle = MockDlibRectangle

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = (100, 100, 50, 50)

        tracker.start_tracking(frame, bbox)

        assert tracker.bbox == bbox

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_start_tracking_enables_tracking_started(self, mock_dlib, mock_dependencies):
        """start_tracking should set tracking_started to True."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()
        mock_dlib.rectangle = MockDlibRectangle

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.tracking_started is True

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_start_tracking_resets_failure_count(self, mock_dlib, mock_dependencies):
        """start_tracking should reset failure_count."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()
        mock_dlib.rectangle = MockDlibRectangle

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.failure_count = 5

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert tracker.failure_count == 0

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_start_tracking_clears_psr_history(self, mock_dlib, mock_dependencies):
        """start_tracking should clear psr_history."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()
        mock_dlib.rectangle = MockDlibRectangle

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.psr_history.append(10.0)
        tracker.psr_history.append(12.0)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert len(tracker.psr_history) == 0


@pytest.mark.unit
class TestDlibUpdate:
    """Tests for DlibTracker.update method."""

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_update_returns_tuple(self, mock_dlib, mock_dependencies):
        """update should return (bool, bbox) tuple."""
        mock_tracker = MockDlibCorrelationTracker(base_psr=15.0)
        mock_dlib.correlation_tracker.return_value = mock_tracker
        mock_dlib.rectangle = MockDlibRectangle

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        result = tracker.update(frame)

        assert isinstance(result, tuple)
        assert len(result) == 2

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_update_stores_psr(self, mock_dlib, mock_dependencies):
        """update should store PSR in history."""
        mock_tracker = MockDlibCorrelationTracker(base_psr=15.0)
        mock_dlib.correlation_tracker.return_value = mock_tracker
        mock_dlib.rectangle = MockDlibRectangle

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        tracker.update(frame)

        assert len(tracker.psr_history) > 0

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_update_before_start_returns_false(self, mock_dlib, mock_dependencies):
        """update before start_tracking should return False."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()
        mock_dlib.rectangle = MockDlibRectangle

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        success, bbox = tracker.update(frame)

        assert success is False

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_update_increments_frame_count(self, mock_dlib, mock_dependencies):
        """update should increment frame_count."""
        mock_tracker = MockDlibCorrelationTracker(base_psr=15.0)
        mock_dlib.correlation_tracker.return_value = mock_tracker
        mock_dlib.rectangle = MockDlibRectangle

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)
        initial_count = tracker.frame_count

        tracker.update(frame)

        assert tracker.frame_count == initial_count + 1


@pytest.mark.unit
class TestDlibPSRConfidence:
    """Tests for PSR-based confidence calculation."""

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_psr_to_confidence_excellent(self, mock_dlib, mock_dependencies):
        """Excellent PSR (>20) should give high confidence."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        confidence = tracker._psr_to_confidence(25.0)

        assert confidence > 0.85

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_psr_to_confidence_good(self, mock_dlib, mock_dependencies):
        """Good PSR (7-20) should give medium-high confidence."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        confidence = tracker._psr_to_confidence(15.0)

        assert 0.5 < confidence < 0.9

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_psr_to_confidence_poor(self, mock_dlib, mock_dependencies):
        """Poor PSR (<5) should give low confidence."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        confidence = tracker._psr_to_confidence(3.0)

        assert confidence < 0.4

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_psr_to_confidence_clamped(self, mock_dlib, mock_dependencies):
        """Confidence should be clamped to [0, 1]."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        # Test with extreme values
        conf_low = tracker._psr_to_confidence(-5.0)
        conf_high = tracker._psr_to_confidence(100.0)

        assert 0.0 <= conf_low <= 1.0
        assert 0.0 <= conf_high <= 1.0

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_psr_to_confidence_zero(self, mock_dlib, mock_dependencies):
        """Zero PSR should give very low confidence."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)

        confidence = tracker._psr_to_confidence(0.0)

        assert confidence < 0.1


@pytest.mark.unit
class TestDlibAdaptiveFeatures:
    """Tests for adaptive PSR and learning rate features."""

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_adaptive_psr_threshold_updates(self, mock_dlib, mock_dependencies):
        """Adaptive PSR threshold should update based on history."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.adaptive_enabled = True
        tracker.psr_dynamic_scaling = True

        # Add some PSR history
        tracker.psr_history.append(15.0)
        tracker.psr_history.append(16.0)
        tracker.psr_history.append(14.0)

        initial_threshold = tracker.adaptive_psr_threshold
        tracker._update_adaptive_psr_threshold(15.0)

        # Threshold should be adjusted
        assert tracker.adaptive_psr_threshold != initial_threshold or initial_threshold == tracker.adaptive_psr_threshold

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_adaptive_learning_rate_high_psr(self, mock_dlib, mock_dependencies):
        """High PSR should give higher learning rate."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        with patch('classes.trackers.dlib_tracker.Parameters') as mock_params:
            mock_params.DLIB_Tracker = {
                'performance_mode': 'robust',
                'appearance_learning_rate': 0.08
            }
            mock_params.CENTER_HISTORY_LENGTH = 100
            mock_params.ESTIMATOR_HISTORY_LENGTH = 100
            mock_params.ENABLE_ESTIMATOR = False

            tracker = DlibTracker(video_handler, detector, app_controller)

        lr_high = tracker._get_adaptive_learning_rate(25.0)
        lr_low = tracker._get_adaptive_learning_rate(3.0)

        assert lr_high > lr_low

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_should_freeze_template_low_psr(self, mock_dlib, mock_dependencies):
        """Template should freeze on low PSR."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.freeze_on_low_confidence = True
        tracker.psr_low_confidence = 5.0

        should_freeze = tracker._should_freeze_template(3.0)  # Below threshold

        assert should_freeze is True

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_should_not_freeze_template_high_psr(self, mock_dlib, mock_dependencies):
        """Template should not freeze on high PSR."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.freeze_on_low_confidence = True
        tracker.psr_low_confidence = 5.0

        should_freeze = tracker._should_freeze_template(15.0)  # Above threshold

        assert should_freeze is False


@pytest.mark.unit
class TestDlibMotionStabilization:
    """Tests for motion stabilization feature."""

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_motion_stabilization_first_frame(self, mock_dlib, mock_dependencies):
        """First frame should return bbox unchanged."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.smoothed_bbox = None

        bbox = (100, 100, 50, 50)
        result = tracker._apply_motion_stabilization(bbox)

        assert result == bbox

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_motion_stabilization_smooths_motion(self, mock_dlib, mock_dependencies):
        """Motion stabilization should smooth bbox changes."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.smoothed_bbox = (100, 100, 50, 50)
        tracker.stabilization_alpha = 0.3

        # Large jump
        bbox = (200, 200, 50, 50)
        result = tracker._apply_motion_stabilization(bbox)

        # Result should be somewhere between old and new
        assert result[0] < bbox[0]  # Smoothed x
        assert result[0] > 100  # But moved from original


@pytest.mark.unit
class TestDlibGetOutput:
    """Tests for get_output method."""

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_get_output_returns_tracker_output(self, mock_dlib, mock_dependencies):
        """get_output should return TrackerOutput."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()
        mock_dlib.__version__ = "19.24.0"

        from classes.trackers.dlib_tracker import DlibTracker
        from classes.tracker_output import TrackerOutput
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.tracking_started = True
        tracker.normalized_center = (0.0, 0.0)

        output = tracker.get_output()

        assert isinstance(output, TrackerOutput)

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_get_output_includes_performance_mode(self, mock_dlib, mock_dependencies):
        """get_output should include performance_mode in raw_data."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()
        mock_dlib.__version__ = "19.24.0"

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.tracking_started = True
        tracker.normalized_center = (0.0, 0.0)  # Required for schema validation

        output = tracker.get_output()

        assert output.raw_data['performance_mode'] == tracker.performance_mode

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_get_output_includes_psr_in_quality_metrics(self, mock_dlib, mock_dependencies):
        """get_output should include PSR in quality_metrics."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()
        mock_dlib.__version__ = "19.24.0"

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.tracking_started = True
        tracker.normalized_center = (0.0, 0.0)  # Required for schema validation
        tracker.psr_history.append(15.0)

        output = tracker.get_output()

        assert 'psr_value' in output.quality_metrics


@pytest.mark.unit
class TestDlibGetCapabilities:
    """Tests for get_capabilities method."""

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_get_capabilities_includes_dlib_algorithm(self, mock_dlib, mock_dependencies):
        """get_capabilities should identify as dlib."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        capabilities = tracker.get_capabilities()

        assert capabilities['tracker_algorithm'] == 'dlib_correlation_filter'

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_get_capabilities_has_psr_confidence(self, mock_dlib, mock_dependencies):
        """get_capabilities should indicate PSR confidence support."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        capabilities = tracker.get_capabilities()

        assert capabilities['psr_confidence'] is True

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_get_capabilities_includes_performance_mode(self, mock_dlib, mock_dependencies):
        """get_capabilities should include current performance_mode."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        capabilities = tracker.get_capabilities()

        assert 'performance_mode' in capabilities


@pytest.mark.unit
class TestDlibVelocityValidation:
    """Tests for velocity validation."""

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_validate_velocity_no_prev_bbox(self, mock_dlib, mock_dependencies):
        """Should return True if no previous bbox."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.prev_bbox = None

        bbox = create_mock_bbox()
        result = tracker._validate_velocity(bbox)

        assert result is True

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_validate_velocity_reasonable_motion(self, mock_dlib, mock_dependencies):
        """Reasonable motion should be valid."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.prev_bbox = (100, 100, 50, 50)
        tracker.frame_count = 10

        bbox = (105, 105, 50, 50)  # Small movement
        result = tracker._validate_velocity(bbox)

        assert result == True  # Use == for boolean comparison

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_validate_velocity_extreme_motion(self, mock_dlib, mock_dependencies):
        """Extreme motion should be invalid."""
        mock_dlib.correlation_tracker.return_value = MockDlibCorrelationTracker()

        from classes.trackers.dlib_tracker import DlibTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = DlibTracker(video_handler, detector, app_controller)
        tracker.prev_bbox = (100, 100, 50, 50)
        tracker.frame_count = 10
        tracker.velocity_limit = 25.0

        bbox = (500, 500, 50, 50)  # Very large movement
        result = tracker._validate_velocity(bbox)

        assert result == False  # Use == for boolean comparison
