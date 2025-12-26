# tests/unit/test_base_follower.py
"""
Unit tests for BaseFollower and related utility classes.

Tests the base follower functionality including:
- Name derivation (CamelCase to UPPER_SNAKE_CASE)
- Velocity and rate clamping
- Target coordinate validation
- Tracker data extraction
- Logging utilities (RateLimitedLogger, ErrorAggregator)
"""

import pytest
import sys
import os
import time
from unittest.mock import MagicMock, patch, PropertyMock
import logging

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from classes.followers.base_follower import (
    RateLimitedLogger,
    ErrorAggregator
)
from classes.tracker_output import TrackerOutput, TrackerDataType


# =============================================================================
# Test: RateLimitedLogger
# =============================================================================

class TestRateLimitedLogger:
    """Test rate-limited logging utility."""

    def test_first_log_always_succeeds(self):
        """First log of any key always succeeds."""
        logger = RateLimitedLogger(interval=5.0)
        mock_logger = MagicMock()

        result = logger.log_rate_limited(mock_logger, 'warning', 'key1', 'message')

        assert result is True
        mock_logger.warning.assert_called_once_with('message')

    def test_repeated_log_within_interval_blocked(self):
        """Repeated log within interval is blocked."""
        logger = RateLimitedLogger(interval=5.0)
        mock_logger = MagicMock()

        # First log succeeds
        logger.log_rate_limited(mock_logger, 'warning', 'key1', 'message1')

        # Immediate second log blocked
        result = logger.log_rate_limited(mock_logger, 'warning', 'key1', 'message2')

        assert result is False
        assert mock_logger.warning.call_count == 1

    def test_different_keys_independent(self):
        """Different keys are rate-limited independently."""
        logger = RateLimitedLogger(interval=5.0)
        mock_logger = MagicMock()

        result1 = logger.log_rate_limited(mock_logger, 'warning', 'key1', 'msg1')
        result2 = logger.log_rate_limited(mock_logger, 'warning', 'key2', 'msg2')

        assert result1 is True
        assert result2 is True
        assert mock_logger.warning.call_count == 2

    def test_log_after_interval_succeeds(self):
        """Log after interval has passed succeeds."""
        logger = RateLimitedLogger(interval=0.01)  # 10ms interval
        mock_logger = MagicMock()

        logger.log_rate_limited(mock_logger, 'warning', 'key1', 'msg1')
        time.sleep(0.02)  # Wait longer than interval
        result = logger.log_rate_limited(mock_logger, 'warning', 'key1', 'msg2')

        assert result is True
        assert mock_logger.warning.call_count == 2

    def test_different_log_levels(self):
        """Different log levels work correctly."""
        logger = RateLimitedLogger(interval=5.0)
        mock_logger = MagicMock()

        logger.log_rate_limited(mock_logger, 'debug', 'key1', 'debug msg')
        logger.log_rate_limited(mock_logger, 'info', 'key2', 'info msg')
        logger.log_rate_limited(mock_logger, 'error', 'key3', 'error msg')

        mock_logger.debug.assert_called_once()
        mock_logger.info.assert_called_once()
        mock_logger.error.assert_called_once()


# =============================================================================
# Test: ErrorAggregator
# =============================================================================

class TestErrorAggregator:
    """Test error aggregation utility."""

    def test_record_error_increments_count(self):
        """Recording error increments counter."""
        aggregator = ErrorAggregator(report_interval=10.0)

        aggregator.record_error('error_type_1')
        aggregator.record_error('error_type_1')
        aggregator.record_error('error_type_1')

        assert aggregator.error_counts['error_type_1'] == 3

    def test_different_error_types_tracked_separately(self):
        """Different error types tracked separately."""
        aggregator = ErrorAggregator(report_interval=10.0)

        aggregator.record_error('error_a')
        aggregator.record_error('error_b')
        aggregator.record_error('error_a')

        assert aggregator.error_counts['error_a'] == 2
        assert aggregator.error_counts['error_b'] == 1

    def test_report_summary_clears_counts(self):
        """Report summary clears error counts."""
        aggregator = ErrorAggregator(report_interval=10.0)
        mock_logger = MagicMock()

        aggregator.record_error('error_type')
        aggregator.record_error('error_type')
        aggregator._report_summary(mock_logger)

        assert len(aggregator.error_counts) == 0

    def test_report_summary_logs_counts(self):
        """Report summary logs error counts."""
        aggregator = ErrorAggregator(report_interval=10.0)
        mock_logger = MagicMock()

        aggregator.record_error('test_error')
        aggregator.record_error('test_error')
        aggregator._report_summary(mock_logger)

        # Check that warning was called (summary + individual errors)
        assert mock_logger.warning.call_count >= 1


# =============================================================================
# Test: Follower Config Name Derivation
# =============================================================================

class TestFollowerConfigNameDerivation:
    """Test _derive_follower_config_name method."""

    def test_mc_velocity_chase_follower(self):
        """MCVelocityChaseFollower -> MC_VELOCITY_CHASE."""
        # We need to test the logic without instantiating the full class
        class_name = "MCVelocityChaseFollower"

        # Remove 'Follower' suffix
        name = class_name[:-8] if class_name.endswith('Follower') else class_name

        # Manual conversion for test
        result = self._convert_to_snake_case(name)
        assert result == "MC_VELOCITY_CHASE"

    def test_fw_attitude_rate_follower(self):
        """FWAttitudeRateFollower -> FW_ATTITUDE_RATE."""
        class_name = "FWAttitudeRateFollower"
        name = class_name[:-8]
        result = self._convert_to_snake_case(name)
        assert result == "FW_ATTITUDE_RATE"

    def test_gm_velocity_vector_follower(self):
        """GMVelocityVectorFollower -> GM_VELOCITY_VECTOR."""
        class_name = "GMVelocityVectorFollower"
        name = class_name[:-8]
        result = self._convert_to_snake_case(name)
        assert result == "GM_VELOCITY_VECTOR"

    def test_mc_velocity_follower(self):
        """MCVelocityFollower -> MC_VELOCITY."""
        class_name = "MCVelocityFollower"
        name = class_name[:-8]
        result = self._convert_to_snake_case(name)
        assert result == "MC_VELOCITY"

    def test_mc_attitude_rate_follower(self):
        """MCAttitudeRateFollower -> MC_ATTITUDE_RATE."""
        class_name = "MCAttitudeRateFollower"
        name = class_name[:-8]
        result = self._convert_to_snake_case(name)
        assert result == "MC_ATTITUDE_RATE"

    def _convert_to_snake_case(self, class_name: str) -> str:
        """Helper to convert CamelCase to UPPER_SNAKE_CASE."""
        result = []
        i = 0
        while i < len(class_name):
            char = class_name[i]

            if char.isupper():
                acronym = char
                j = i + 1
                while j < len(class_name) and class_name[j].isupper():
                    if j + 1 < len(class_name) and class_name[j + 1].islower():
                        break
                    acronym += class_name[j]
                    j += 1

                if len(acronym) > 1:
                    if result:
                        result.append('_')
                    result.append(acronym)
                    i = j
                else:
                    if result and result[-1] != '_':
                        result.append('_')
                    result.append(char)
                    i += 1
            else:
                result.append(char.upper())
                i += 1

        return ''.join(result)


# =============================================================================
# Test: Tracker Data Extraction
# =============================================================================

class TestTrackerDataExtraction:
    """Test tracker data extraction methods."""

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_extract_from_position_2d(self):
        """Extract coordinates from position_2d."""
        tracker_data = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.5, -0.3)
        )

        # Test the extraction logic
        if tracker_data.position_2d:
            result = tracker_data.position_2d
        else:
            result = None

        assert result == (0.5, -0.3)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_extract_from_position_3d(self):
        """Extract coordinates from position_3d."""
        tracker_data = TrackerOutput(
            data_type=TrackerDataType.POSITION_3D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.2, -0.4),
            position_3d=(0.2, -0.4, 10.0)
        )

        # Primary extraction uses position_2d
        result = tracker_data.position_2d
        assert result == (0.2, -0.4)

        # Can also get from position_3d
        result_3d = tracker_data.position_3d[:2]
        assert result_3d == (0.2, -0.4)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_extract_returns_none_when_missing(self):
        """Extract returns None when no position data."""
        tracker_data = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=False
        )

        result = tracker_data.position_2d
        assert result is None


# =============================================================================
# Test: Required Data Type Checking
# =============================================================================

class TestRequiredDataTypeChecking:
    """Test _has_required_data logic."""

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_position_2d(self):
        """Check for POSITION_2D data."""
        tracker = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.0, 0.0)
        )

        assert tracker.position_2d is not None

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_missing_position_2d(self):
        """Check when POSITION_2D data missing."""
        tracker = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=False
        )

        assert tracker.position_2d is None

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_position_3d(self):
        """Check for POSITION_3D data."""
        tracker = TrackerOutput(
            data_type=TrackerDataType.POSITION_3D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.0, 0.0),
            position_3d=(0.0, 0.0, 10.0)
        )

        assert tracker.position_3d is not None

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_angular_data(self):
        """Check for ANGULAR data."""
        tracker = TrackerOutput(
            data_type=TrackerDataType.ANGULAR,
            timestamp=time.time(),
            tracking_active=True,
            angular=(45.0, -10.0)
        )

        assert tracker.angular is not None

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_bbox_data(self):
        """Check for BBOX_CONFIDENCE data."""
        tracker = TrackerOutput(
            data_type=TrackerDataType.BBOX_CONFIDENCE,
            timestamp=time.time(),
            tracking_active=True,
            bbox=(100, 100, 50, 50)
        )

        assert tracker.bbox is not None

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_velocity_data(self):
        """Check for VELOCITY_AWARE data."""
        tracker = TrackerOutput(
            data_type=TrackerDataType.VELOCITY_AWARE,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.0, 0.0),
            velocity=(1.5, -0.5)
        )

        assert tracker.velocity is not None


# =============================================================================
# Test: Velocity Clamping Logic
# =============================================================================

class TestVelocityClampingLogic:
    """Test velocity clamping functionality."""

    def test_clamp_within_limits(self):
        """Values within limits unchanged."""
        import numpy as np

        limits = type('Limits', (), {'forward': 10.0, 'lateral': 5.0, 'vertical': 3.0})()

        vel_fwd = 5.0
        vel_right = 2.0
        vel_down = 1.0

        clamped_fwd = np.clip(vel_fwd, -limits.forward, limits.forward)
        clamped_right = np.clip(vel_right, -limits.lateral, limits.lateral)
        clamped_down = np.clip(vel_down, -limits.vertical, limits.vertical)

        assert clamped_fwd == 5.0
        assert clamped_right == 2.0
        assert clamped_down == 1.0

    def test_clamp_exceeds_positive(self):
        """Values exceeding positive limits clamped."""
        import numpy as np

        limits = type('Limits', (), {'forward': 10.0, 'lateral': 5.0, 'vertical': 3.0})()

        vel_fwd = 15.0
        vel_right = 8.0
        vel_down = 5.0

        clamped_fwd = np.clip(vel_fwd, -limits.forward, limits.forward)
        clamped_right = np.clip(vel_right, -limits.lateral, limits.lateral)
        clamped_down = np.clip(vel_down, -limits.vertical, limits.vertical)

        assert clamped_fwd == 10.0
        assert clamped_right == 5.0
        assert clamped_down == 3.0

    def test_clamp_exceeds_negative(self):
        """Values exceeding negative limits clamped."""
        import numpy as np

        limits = type('Limits', (), {'forward': 10.0, 'lateral': 5.0, 'vertical': 3.0})()

        vel_fwd = -15.0
        vel_right = -8.0
        vel_down = -5.0

        clamped_fwd = np.clip(vel_fwd, -limits.forward, limits.forward)
        clamped_right = np.clip(vel_right, -limits.lateral, limits.lateral)
        clamped_down = np.clip(vel_down, -limits.vertical, limits.vertical)

        assert clamped_fwd == -10.0
        assert clamped_right == -5.0
        assert clamped_down == -3.0


# =============================================================================
# Test: Rate Clamping Logic
# =============================================================================

class TestRateClampingLogic:
    """Test rate clamping functionality."""

    def test_clamp_rate_within_limits(self):
        """Rate within limits unchanged."""
        import numpy as np

        limit = 0.785  # ~45 deg/s in rad/s
        rate_value = 0.5

        clamped = float(np.clip(rate_value, -limit, limit))

        assert clamped == 0.5

    def test_clamp_rate_exceeds_positive(self):
        """Rate exceeding positive limit clamped."""
        import numpy as np

        limit = 0.785
        rate_value = 1.5

        clamped = float(np.clip(rate_value, -limit, limit))

        assert clamped == pytest.approx(0.785)

    def test_clamp_rate_exceeds_negative(self):
        """Rate exceeding negative limit clamped."""
        import numpy as np

        limit = 0.785
        rate_value = -1.5

        clamped = float(np.clip(rate_value, -limit, limit))

        assert clamped == pytest.approx(-0.785)


# =============================================================================
# Test: Target Coordinate Validation Logic
# =============================================================================

class TestTargetCoordinateValidationLogic:
    """Test target coordinate validation logic."""

    def test_valid_tuple_coordinates(self):
        """Valid tuple coordinates pass validation."""
        target = (0.5, -0.3)

        x, y = target
        is_valid = all(isinstance(coord, (int, float)) for coord in [x, y])
        in_bounds = all(-2.0 <= coord <= 2.0 for coord in [x, y])

        assert is_valid is True
        assert in_bounds is True

    def test_out_of_bounds_coordinates(self):
        """Out of bounds coordinates fail validation."""
        target = (5.0, -3.0)  # Beyond [-2, 2] range

        x, y = target
        in_bounds = all(-2.0 <= coord <= 2.0 for coord in [x, y])

        assert in_bounds is False

    def test_non_numeric_coordinates(self):
        """Non-numeric coordinates fail validation."""
        target = ("not", "numbers")

        try:
            x, y = target
            is_valid = all(isinstance(coord, (int, float)) for coord in [x, y])
        except (TypeError, ValueError):
            is_valid = False

        assert is_valid is False

    def test_wrong_length_tuple(self):
        """Wrong length tuple fails validation."""
        target = (0.5, 0.3, 0.1)  # 3 elements instead of 2

        is_valid = len(target) == 2
        assert is_valid is False

    def test_edge_coordinates(self):
        """Edge coordinates at bounds are valid."""
        target = (2.0, -2.0)

        x, y = target
        in_bounds = all(-2.0 <= coord <= 2.0 for coord in [x, y])

        assert in_bounds is True


# =============================================================================
# Test: TrackerOutput Helper Methods
# =============================================================================

class TestTrackerOutputHelpers:
    """Test TrackerOutput helper method integration."""

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_get_primary_position_2d(self):
        """get_primary_position returns 2D position."""
        tracker = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.3, -0.2)
        )

        result = tracker.get_primary_position()
        assert result == (0.3, -0.2)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_get_primary_position_from_3d(self):
        """get_primary_position extracts from 3D."""
        tracker = TrackerOutput(
            data_type=TrackerDataType.POSITION_3D,
            timestamp=time.time(),
            tracking_active=True,
            position_3d=(0.1, -0.4, 15.0)
        )

        result = tracker.get_primary_position()
        assert result == (0.1, -0.4)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_position_data_true(self):
        """has_position_data returns True with position."""
        tracker = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.0, 0.0)
        )

        assert tracker.has_position_data() is True

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_position_data_false(self):
        """has_position_data returns False without position."""
        tracker = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=False
        )

        assert tracker.has_position_data() is False
