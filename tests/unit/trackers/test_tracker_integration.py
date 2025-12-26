# tests/unit/trackers/test_tracker_integration.py
"""
Integration tests for tracker components.

Tests tracker-to-follower data flow, factory integration,
and tracker output compatibility.
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
    MockVideoHandler, MockDetector, MockAppController,
    create_mock_test_frame, create_mock_bbox
)
from tests.fixtures.mock_tracker import TrackerOutputFactory


@pytest.fixture
def mock_dependencies():
    """Fixture for common mock dependencies."""
    video_handler = MockVideoHandler(640, 480)
    detector = MockDetector()
    app_controller = MockAppController()
    return video_handler, detector, app_controller


@pytest.mark.integration
class TestTrackerFollowerDataFlow:
    """Tests for tracker output to follower data flow."""

    def test_tracker_output_factory_centered(self):
        """TrackerOutputFactory.centered() should create valid output."""
        output = TrackerOutputFactory.centered()

        assert output is not None
        assert output.tracking_active is True
        assert output.position_2d == (0.0, 0.0)

    def test_tracker_output_factory_offset(self):
        """TrackerOutputFactory.offset() should create offset output."""
        output = TrackerOutputFactory.offset(0.5, -0.3)

        assert output.position_2d == (0.5, -0.3)

    def test_tracker_output_factory_lost(self):
        """TrackerOutputFactory.lost() should create lost tracking output."""
        output = TrackerOutputFactory.lost()

        assert output.tracking_active is False
        assert output.confidence == 0.0

    def test_tracker_output_factory_low_confidence(self):
        """TrackerOutputFactory.low_confidence() should create low conf output."""
        output = TrackerOutputFactory.low_confidence()

        assert output.tracking_active is True
        assert output.confidence < 0.5

    def test_tracker_output_has_timestamp(self):
        """All tracker outputs should have valid timestamp."""
        output = TrackerOutputFactory.centered()

        assert output.timestamp > 0
        assert output.timestamp <= time.time()

    def test_tracker_output_data_type_valid(self):
        """Tracker output data_type should be valid."""
        from classes.tracker_output import TrackerDataType

        output = TrackerOutputFactory.centered()

        assert output.data_type in TrackerDataType


@pytest.mark.integration
class TestTrackerFactoryIntegration:
    """Tests for tracker factory integration."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_factory_creates_working_csrt(self, mock_cv2, mock_dependencies):
        """Factory-created CSRT should be functional."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MagicMock()

        from classes.trackers.tracker_factory import create_tracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = create_tracker("CSRT", video_handler, detector, app_controller)

        assert tracker is not None
        assert hasattr(tracker, 'start_tracking')
        assert hasattr(tracker, 'update')
        assert hasattr(tracker, 'get_output')

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    def test_factory_creates_working_kcf(self, mock_cv2, mock_dependencies):
        """Factory-created KCF should be functional."""
        mock_cv2.TrackerKCF_create.return_value = MagicMock()

        from classes.trackers.tracker_factory import create_tracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = create_tracker("KCF", video_handler, detector, app_controller)

        assert tracker is not None
        assert hasattr(tracker, 'start_tracking')
        assert hasattr(tracker, 'update')
        assert hasattr(tracker, 'get_output')

    def test_all_trackers_have_consistent_interface(self):
        """All trackers should have consistent interface."""
        from classes.trackers.tracker_factory import TRACKER_REGISTRY
        from classes.trackers.base_tracker import BaseTracker

        for name, tracker_class in TRACKER_REGISTRY.items():
            # Check inheritance
            assert issubclass(tracker_class, BaseTracker), f"{name} doesn't inherit BaseTracker"

            # Check required methods
            assert hasattr(tracker_class, 'start_tracking'), f"{name} missing start_tracking"
            assert hasattr(tracker_class, 'update'), f"{name} missing update"
            assert hasattr(tracker_class, 'get_output'), f"{name} missing get_output"
            assert hasattr(tracker_class, 'get_capabilities'), f"{name} missing get_capabilities"


@pytest.mark.integration
class TestTrackerOutputCompatibility:
    """Tests for tracker output compatibility with followers."""

    def test_position_2d_normalized_range(self):
        """Position 2D should be in normalized range [-1, 1]."""
        from classes.tracker_output import TrackerOutput, TrackerDataType

        # Test various positions
        positions = [
            (0.0, 0.0),  # Center
            (1.0, 1.0),  # Bottom-right
            (-1.0, -1.0),  # Top-left
            (0.5, -0.5),  # Offset
        ]

        for pos in positions:
            output = TrackerOutput(
                data_type=TrackerDataType.POSITION_2D,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id="test",
                position_2d=pos
            )

            assert -1.0 <= output.position_2d[0] <= 1.0
            assert -1.0 <= output.position_2d[1] <= 1.0

    def test_confidence_normalized_range(self):
        """Confidence should be in range [0, 1]."""
        from classes.tracker_output import TrackerOutput, TrackerDataType

        confidences = [0.0, 0.5, 0.75, 1.0]

        for conf in confidences:
            output = TrackerOutput(
                data_type=TrackerDataType.BBOX_CONFIDENCE,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id="test",
                position_2d=(0.0, 0.0),  # Required for schema validation
                bbox=(100, 100, 50, 50),  # Required for BBOX_CONFIDENCE
                confidence=conf
            )

            assert 0.0 <= output.confidence <= 1.0

    def test_velocity_aware_output_has_velocity(self):
        """VELOCITY_AWARE output should have velocity data."""
        # velocity_aware(x, y, vx, vy) - use position first, then velocity
        output = TrackerOutputFactory.velocity_aware(0.0, 0.0, 10.0, 5.0)

        assert output.velocity is not None
        assert len(output.velocity) == 2

    def test_gimbal_angles_output_has_angular(self):
        """GIMBAL_ANGLES output should have angular data."""
        output = TrackerOutputFactory.gimbal_angles(10.0, -20.0, 0.0)

        assert output.angular is not None
        assert len(output.angular) == 3


@pytest.mark.integration
class TestTrackerAppControllerIntegration:
    """Tests for tracker and AppController integration."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_tracker_receives_app_controller(self, mock_cv2, mock_dependencies):
        """Tracker should receive app_controller reference."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MagicMock()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.app_controller is app_controller

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_tracker_receives_video_handler(self, mock_cv2, mock_dependencies):
        """Tracker should receive video_handler reference."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MagicMock()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.video_handler is video_handler

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_tracker_uses_video_handler_dimensions(self, mock_cv2, mock_dependencies):
        """Tracker should use video_handler for dimensions."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MagicMock()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        # Test normalization uses video_handler dimensions
        tracker.center = (320, 240)  # Center of 640x480
        tracker.normalize_center_coordinates()

        # Should normalize to near (0, 0)
        assert tracker.normalized_center is not None
        assert abs(tracker.normalized_center[0]) < 0.01
        assert abs(tracker.normalized_center[1]) < 0.01


@pytest.mark.integration
class TestTrackerDetectorIntegration:
    """Tests for tracker and detector integration."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_tracker_receives_detector(self, mock_cv2, mock_dependencies):
        """Tracker should receive detector reference."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MagicMock()

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        assert tracker.detector is detector

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_start_tracking_initializes_detector_features(self, mock_cv2, mock_dependencies):
        """start_tracking should initialize detector features."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_csrt = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = mock_csrt

        from classes.trackers.csrt_tracker import CSRTTracker
        video_handler, detector, app_controller = mock_dependencies

        tracker = CSRTTracker(video_handler, detector, app_controller)

        frame = create_mock_test_frame()
        bbox = create_mock_bbox()

        tracker.start_tracking(frame, bbox)

        assert detector.initial_features is not None
        assert detector.adaptive_features is not None
