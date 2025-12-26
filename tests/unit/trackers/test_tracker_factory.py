# tests/unit/trackers/test_tracker_factory.py
"""
Unit tests for TrackerFactory module.

Tests the factory pattern implementation for creating tracker instances.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))


@pytest.mark.unit
class TestTrackerFactoryRegistry:
    """Tests for TRACKER_REGISTRY contents and structure."""

    def test_registry_contains_csrt(self):
        """CSRT should be registered in TRACKER_REGISTRY."""
        from classes.trackers.tracker_factory import TRACKER_REGISTRY
        assert "CSRT" in TRACKER_REGISTRY

    def test_registry_contains_kcf(self):
        """KCF should be registered in TRACKER_REGISTRY."""
        from classes.trackers.tracker_factory import TRACKER_REGISTRY
        assert "KCF" in TRACKER_REGISTRY

    def test_registry_contains_dlib(self):
        """dlib should be registered in TRACKER_REGISTRY."""
        from classes.trackers.tracker_factory import TRACKER_REGISTRY
        assert "dlib" in TRACKER_REGISTRY

    def test_registry_contains_gimbal(self):
        """Gimbal should be registered in TRACKER_REGISTRY."""
        from classes.trackers.tracker_factory import TRACKER_REGISTRY
        assert "Gimbal" in TRACKER_REGISTRY

    def test_registry_has_expected_count(self):
        """TRACKER_REGISTRY should have at least 4 tracker types."""
        from classes.trackers.tracker_factory import TRACKER_REGISTRY
        assert len(TRACKER_REGISTRY) >= 4

    def test_registry_values_are_classes(self):
        """All registry values should be class types."""
        from classes.trackers.tracker_factory import TRACKER_REGISTRY
        for name, tracker_class in TRACKER_REGISTRY.items():
            assert isinstance(tracker_class, type), f"{name} is not a class type"


@pytest.mark.unit
class TestCreateTrackerFunction:
    """Tests for create_tracker factory function."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_create_csrt_tracker(self, mock_cv2):
        """create_tracker('CSRT') should return CSRTTracker instance."""
        # Setup mock
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MagicMock()

        from classes.trackers.tracker_factory import create_tracker
        from classes.trackers.csrt_tracker import CSRTTracker

        # Create mock dependencies
        mock_video_handler = MagicMock()
        mock_video_handler.width = 640
        mock_video_handler.height = 480
        mock_app_controller = MagicMock()
        mock_app_controller.estimator = None

        tracker = create_tracker("CSRT", mock_video_handler, None, mock_app_controller)
        assert isinstance(tracker, CSRTTracker)

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    def test_create_kcf_tracker(self, mock_cv2):
        """create_tracker('KCF') should return KCFKalmanTracker instance."""
        mock_cv2.TrackerKCF_create.return_value = MagicMock()

        from classes.trackers.tracker_factory import create_tracker
        from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker

        mock_video_handler = MagicMock()
        mock_video_handler.width = 640
        mock_video_handler.height = 480
        mock_app_controller = MagicMock()
        mock_app_controller.estimator = None

        tracker = create_tracker("KCF", mock_video_handler, None, mock_app_controller)
        assert isinstance(tracker, KCFKalmanTracker)

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_create_dlib_tracker(self, mock_dlib):
        """create_tracker('dlib') should return DlibTracker instance."""
        mock_dlib.correlation_tracker.return_value = MagicMock()

        from classes.trackers.tracker_factory import create_tracker
        from classes.trackers.dlib_tracker import DlibTracker

        mock_video_handler = MagicMock()
        mock_video_handler.width = 640
        mock_video_handler.height = 480
        mock_app_controller = MagicMock()
        mock_app_controller.estimator = None

        tracker = create_tracker("dlib", mock_video_handler, None, mock_app_controller)
        assert isinstance(tracker, DlibTracker)

    @patch('classes.trackers.gimbal_tracker.GimbalInterface')
    @patch('classes.trackers.gimbal_tracker.CoordinateTransformer')
    def test_create_gimbal_tracker(self, mock_transformer, mock_interface):
        """create_tracker('Gimbal') should return GimbalTracker instance."""
        mock_interface.return_value = MagicMock()
        mock_transformer.return_value = MagicMock()

        from classes.trackers.tracker_factory import create_tracker
        from classes.trackers.gimbal_tracker import GimbalTracker

        mock_video_handler = MagicMock()
        mock_app_controller = MagicMock()
        mock_app_controller.estimator = None

        tracker = create_tracker("Gimbal", mock_video_handler, None, mock_app_controller)
        assert isinstance(tracker, GimbalTracker)

    def test_create_tracker_with_none_arguments(self):
        """create_tracker should accept None for video_handler and detector."""
        from classes.trackers.tracker_factory import create_tracker

        # This should not raise even with None video_handler/detector
        with patch('classes.trackers.csrt_tracker.cv2') as mock_cv2:
            mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
            mock_cv2.TrackerCSRT_create.return_value = MagicMock()

            # app_controller must have estimator attribute
            mock_app_controller = MagicMock()
            mock_app_controller.estimator = None

            tracker = create_tracker("CSRT", None, None, mock_app_controller)
            assert tracker is not None

    def test_create_tracker_returns_new_instance(self):
        """Each call to create_tracker should return a new instance."""
        from classes.trackers.tracker_factory import create_tracker

        with patch('classes.trackers.csrt_tracker.cv2') as mock_cv2:
            mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
            mock_cv2.TrackerCSRT_create.return_value = MagicMock()

            # app_controller must have estimator attribute
            mock_app_controller = MagicMock()
            mock_app_controller.estimator = None

            tracker1 = create_tracker("CSRT", None, None, mock_app_controller)
            tracker2 = create_tracker("CSRT", None, None, mock_app_controller)

            assert tracker1 is not tracker2


@pytest.mark.unit
class TestFactoryErrors:
    """Tests for factory error handling."""

    def test_unsupported_algorithm_raises_value_error(self):
        """create_tracker should raise ValueError for unsupported algorithm."""
        from classes.trackers.tracker_factory import create_tracker

        with pytest.raises(ValueError) as exc_info:
            create_tracker("UnsupportedTracker", None, None, None)

        assert "Unsupported tracking algorithm" in str(exc_info.value)
        assert "UnsupportedTracker" in str(exc_info.value)

    def test_error_message_lists_supported_algorithms(self):
        """ValueError message should list supported algorithms."""
        from classes.trackers.tracker_factory import create_tracker

        with pytest.raises(ValueError) as exc_info:
            create_tracker("InvalidTracker", None, None, None)

        error_msg = str(exc_info.value)
        # Check that supported algorithms are mentioned
        assert "CSRT" in error_msg or "Supported" in error_msg

    def test_empty_string_algorithm_raises_error(self):
        """create_tracker should raise ValueError for empty string."""
        from classes.trackers.tracker_factory import create_tracker

        with pytest.raises(ValueError):
            create_tracker("", None, None, None)

    def test_case_sensitive_algorithm_names(self):
        """Algorithm names should be case-sensitive."""
        from classes.trackers.tracker_factory import create_tracker

        # "csrt" lowercase should fail (the registry has "CSRT")
        with pytest.raises(ValueError):
            create_tracker("csrt", None, None, None)


@pytest.fixture
def mock_app_controller():
    """Create mock app_controller with required attributes."""
    controller = MagicMock()
    controller.estimator = None
    return controller


@pytest.mark.unit
class TestTrackerBaseClass:
    """Tests verifying all factory-created trackers inherit from BaseTracker."""

    @patch('classes.trackers.csrt_tracker.cv2')
    def test_csrt_inherits_base_tracker(self, mock_cv2, mock_app_controller):
        """CSRTTracker should inherit from BaseTracker."""
        mock_cv2.TrackerCSRT_Params.return_value = MagicMock()
        mock_cv2.TrackerCSRT_create.return_value = MagicMock()

        from classes.trackers.tracker_factory import create_tracker
        from classes.trackers.base_tracker import BaseTracker

        tracker = create_tracker("CSRT", None, None, mock_app_controller)
        assert isinstance(tracker, BaseTracker)

    @patch('classes.trackers.kcf_kalman_tracker.cv2')
    def test_kcf_inherits_base_tracker(self, mock_cv2, mock_app_controller):
        """KCFKalmanTracker should inherit from BaseTracker."""
        mock_cv2.TrackerKCF_create.return_value = MagicMock()

        from classes.trackers.tracker_factory import create_tracker
        from classes.trackers.base_tracker import BaseTracker

        tracker = create_tracker("KCF", None, None, mock_app_controller)
        assert isinstance(tracker, BaseTracker)

    @patch('classes.trackers.dlib_tracker.dlib')
    @patch('classes.trackers.dlib_tracker.DLIB_AVAILABLE', True)
    def test_dlib_inherits_base_tracker(self, mock_dlib, mock_app_controller):
        """DlibTracker should inherit from BaseTracker."""
        mock_dlib.correlation_tracker.return_value = MagicMock()

        from classes.trackers.tracker_factory import create_tracker
        from classes.trackers.base_tracker import BaseTracker

        tracker = create_tracker("dlib", None, None, mock_app_controller)
        assert isinstance(tracker, BaseTracker)

    @patch('classes.trackers.gimbal_tracker.GimbalInterface')
    @patch('classes.trackers.gimbal_tracker.CoordinateTransformer')
    def test_gimbal_inherits_base_tracker(self, mock_transformer, mock_interface, mock_app_controller):
        """GimbalTracker should inherit from BaseTracker."""
        mock_interface.return_value = MagicMock()
        mock_transformer.return_value = MagicMock()

        from classes.trackers.tracker_factory import create_tracker
        from classes.trackers.base_tracker import BaseTracker

        tracker = create_tracker("Gimbal", None, None, mock_app_controller)
        assert isinstance(tracker, BaseTracker)
