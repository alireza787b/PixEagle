# tests/unit/test_tracker_output.py
"""
Unit tests for TrackerOutput dataclass.

Tests the unified tracker output schema including:
- TrackerDataType enum values
- TrackerOutput initialization and validation
- Serialization (to_dict, from_dict)
- Helper methods (has_position_data, get_primary_position, etc.)
- Legacy compatibility functions
"""

import pytest
import sys
import os
import time
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from classes.tracker_output import (
    TrackerOutput,
    TrackerDataType,
    create_legacy_tracker_output,
    LegacyTrackerData
)


# =============================================================================
# Test: TrackerDataType Enum
# =============================================================================

class TestTrackerDataType:
    """Test TrackerDataType enumeration."""

    def test_position_2d_value(self):
        """POSITION_2D has correct string value."""
        assert TrackerDataType.POSITION_2D.value == "POSITION_2D"

    def test_position_3d_value(self):
        """POSITION_3D has correct string value."""
        assert TrackerDataType.POSITION_3D.value == "POSITION_3D"

    def test_angular_value(self):
        """ANGULAR has correct string value."""
        assert TrackerDataType.ANGULAR.value == "ANGULAR"

    def test_gimbal_angles_value(self):
        """GIMBAL_ANGLES has correct string value."""
        assert TrackerDataType.GIMBAL_ANGLES.value == "GIMBAL_ANGLES"

    def test_bbox_confidence_value(self):
        """BBOX_CONFIDENCE has correct string value."""
        assert TrackerDataType.BBOX_CONFIDENCE.value == "BBOX_CONFIDENCE"

    def test_velocity_aware_value(self):
        """VELOCITY_AWARE has correct string value."""
        assert TrackerDataType.VELOCITY_AWARE.value == "VELOCITY_AWARE"

    def test_external_value(self):
        """EXTERNAL has correct string value."""
        assert TrackerDataType.EXTERNAL.value == "EXTERNAL"

    def test_multi_target_value(self):
        """MULTI_TARGET has correct string value."""
        assert TrackerDataType.MULTI_TARGET.value == "MULTI_TARGET"

    def test_enum_from_string(self):
        """Enum can be created from string value."""
        dt = TrackerDataType("POSITION_2D")
        assert dt == TrackerDataType.POSITION_2D

    def test_all_types_defined(self):
        """All expected types are defined."""
        expected_types = [
            'POSITION_2D', 'POSITION_3D', 'ANGULAR', 'GIMBAL_ANGLES',
            'BBOX_CONFIDENCE', 'VELOCITY_AWARE', 'EXTERNAL', 'MULTI_TARGET'
        ]
        actual_types = [t.value for t in TrackerDataType]
        assert set(expected_types) == set(actual_types)


# =============================================================================
# Test: TrackerOutput Initialization
# =============================================================================

class TestTrackerOutputInitialization:
    """Test TrackerOutput initialization."""

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_minimal_initialization(self):
        """TrackerOutput initializes with minimal required fields."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True
        )
        assert output.data_type == TrackerDataType.POSITION_2D
        assert output.tracking_active is True

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_position_2d(self):
        """TrackerOutput initializes with 2D position."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.5, -0.3)
        )
        assert output.position_2d == (0.5, -0.3)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_position_3d(self):
        """TrackerOutput initializes with 3D position."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_3D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.1, 0.2),
            position_3d=(0.1, 0.2, 10.5)
        )
        assert output.position_3d == (0.1, 0.2, 10.5)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_angular_data(self):
        """TrackerOutput initializes with angular data."""
        output = TrackerOutput(
            data_type=TrackerDataType.ANGULAR,
            timestamp=time.time(),
            tracking_active=True,
            angular=(45.0, -15.0)
        )
        assert output.angular == (45.0, -15.0)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_confidence(self):
        """TrackerOutput initializes with confidence."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            confidence=0.85
        )
        assert output.confidence == 0.85

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_bbox(self):
        """TrackerOutput initializes with bounding box."""
        output = TrackerOutput(
            data_type=TrackerDataType.BBOX_CONFIDENCE,
            timestamp=time.time(),
            tracking_active=True,
            bbox=(100, 150, 50, 75)
        )
        assert output.bbox == (100, 150, 50, 75)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_velocity(self):
        """TrackerOutput initializes with velocity."""
        output = TrackerOutput(
            data_type=TrackerDataType.VELOCITY_AWARE,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.0, 0.0),
            velocity=(1.5, -0.5)
        )
        assert output.velocity == (1.5, -0.5)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_default_tracker_id(self):
        """Default tracker_id is 'default'."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True
        )
        assert output.tracker_id == "default"

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_custom_tracker_id(self):
        """Custom tracker_id is preserved."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            tracker_id="yolo_tracker"
        )
        assert output.tracker_id == "yolo_tracker"


# =============================================================================
# Test: Validation
# =============================================================================

class TestTrackerOutputValidation:
    """Test TrackerOutput validation."""

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_invalid_timestamp_zero(self):
        """Zero timestamp raises ValueError."""
        with pytest.raises(ValueError, match="Timestamp must be positive"):
            TrackerOutput(
                data_type=TrackerDataType.POSITION_2D,
                timestamp=0,
                tracking_active=True
            )

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_invalid_timestamp_negative(self):
        """Negative timestamp raises ValueError."""
        with pytest.raises(ValueError, match="Timestamp must be positive"):
            TrackerOutput(
                data_type=TrackerDataType.POSITION_2D,
                timestamp=-1.0,
                tracking_active=True
            )

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_confidence_below_zero(self):
        """Confidence below 0 raises ValueError."""
        with pytest.raises(ValueError, match="Confidence must be between"):
            TrackerOutput(
                data_type=TrackerDataType.POSITION_2D,
                timestamp=time.time(),
                tracking_active=True,
                confidence=-0.1
            )

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_confidence_above_one(self):
        """Confidence above 1 raises ValueError."""
        with pytest.raises(ValueError, match="Confidence must be between"):
            TrackerOutput(
                data_type=TrackerDataType.POSITION_2D,
                timestamp=time.time(),
                tracking_active=True,
                confidence=1.1
            )

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_confidence_at_zero(self):
        """Confidence at 0 is valid."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            confidence=0.0
        )
        assert output.confidence == 0.0

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_confidence_at_one(self):
        """Confidence at 1 is valid."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            confidence=1.0
        )
        assert output.confidence == 1.0

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_validate_method_returns_true(self):
        """Validate method returns True for valid output."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            confidence=0.5
        )
        assert output.validate() is True


# =============================================================================
# Test: Serialization
# =============================================================================

class TestTrackerOutputSerialization:
    """Test TrackerOutput serialization methods."""

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_to_dict_basic(self):
        """to_dict converts basic output to dict."""
        ts = time.time()
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=ts,
            tracking_active=True
        )
        d = output.to_dict()

        assert d['data_type'] == "POSITION_2D"
        assert d['timestamp'] == ts
        assert d['tracking_active'] is True

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_to_dict_with_position(self):
        """to_dict includes position data."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.5, -0.5)
        )
        d = output.to_dict()

        assert d['position_2d'] == (0.5, -0.5)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_from_dict_basic(self):
        """from_dict creates output from dict."""
        ts = time.time()
        data = {
            'data_type': 'POSITION_2D',
            'timestamp': ts,
            'tracking_active': True,
            'tracker_id': 'test'
        }
        output = TrackerOutput.from_dict(data)

        assert output.data_type == TrackerDataType.POSITION_2D
        assert output.timestamp == ts
        assert output.tracking_active is True

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_roundtrip_serialization(self):
        """to_dict then from_dict preserves data."""
        original = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.1, -0.2),
            confidence=0.9,
            tracker_id="test_tracker"
        )

        d = original.to_dict()
        restored = TrackerOutput.from_dict(d)

        assert restored.data_type == original.data_type
        assert restored.timestamp == original.timestamp
        assert restored.position_2d == original.position_2d
        assert restored.confidence == original.confidence

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_from_dict_with_enum_object(self):
        """from_dict handles enum object in data_type."""
        ts = time.time()
        data = {
            'data_type': TrackerDataType.POSITION_3D,  # Already an enum
            'timestamp': ts,
            'tracking_active': True,
            'position_2d': (0.0, 0.0),
            'position_3d': (0.0, 0.0, 10.0),
            'tracker_id': 'test'
        }
        output = TrackerOutput.from_dict(data)

        assert output.data_type == TrackerDataType.POSITION_3D


# =============================================================================
# Test: Helper Methods
# =============================================================================

class TestTrackerOutputHelperMethods:
    """Test TrackerOutput helper methods."""

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_position_data_with_2d(self):
        """has_position_data returns True with 2D position."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.0, 0.0)
        )
        assert output.has_position_data() is True

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_position_data_with_3d(self):
        """has_position_data returns True with 3D position."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_3D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.0, 0.0),
            position_3d=(0.0, 0.0, 5.0)
        )
        assert output.has_position_data() is True

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_position_data_with_angular(self):
        """has_position_data returns True with angular data."""
        output = TrackerOutput(
            data_type=TrackerDataType.ANGULAR,
            timestamp=time.time(),
            tracking_active=True,
            angular=(45.0, 10.0)
        )
        assert output.has_position_data() is True

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_has_position_data_false(self):
        """has_position_data returns False without position."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=False
        )
        assert output.has_position_data() is False

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_get_primary_position_2d(self):
        """get_primary_position returns 2D position."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.5, -0.3)
        )
        pos = output.get_primary_position()
        assert pos == (0.5, -0.3)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_get_primary_position_from_3d(self):
        """get_primary_position extracts xy from 3D."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_3D,
            timestamp=time.time(),
            tracking_active=True,
            position_3d=(0.2, -0.4, 10.0)
        )
        pos = output.get_primary_position()
        assert pos == (0.2, -0.4)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_get_primary_position_none(self):
        """get_primary_position returns None without position."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=False
        )
        assert output.get_primary_position() is None

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_get_confidence_or_default_with_confidence(self):
        """get_confidence_or_default returns actual confidence."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            confidence=0.75
        )
        assert output.get_confidence_or_default() == 0.75

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_get_confidence_or_default_without_confidence(self):
        """get_confidence_or_default returns default when None."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True
        )
        assert output.get_confidence_or_default() == 1.0

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_get_confidence_or_default_custom_default(self):
        """get_confidence_or_default uses custom default."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True
        )
        assert output.get_confidence_or_default(default=0.5) == 0.5

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_is_high_confidence_true(self):
        """is_high_confidence returns True above threshold."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            confidence=0.9
        )
        assert output.is_high_confidence() is True

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_is_high_confidence_false(self):
        """is_high_confidence returns False below threshold."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            confidence=0.5
        )
        assert output.is_high_confidence() is False

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_is_high_confidence_custom_threshold(self):
        """is_high_confidence uses custom threshold."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            confidence=0.5
        )
        assert output.is_high_confidence(threshold=0.4) is True


# =============================================================================
# Test: Legacy Compatibility
# =============================================================================

class TestLegacyCompatibility:
    """Test legacy compatibility functions."""

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_create_legacy_tracker_output(self):
        """create_legacy_tracker_output creates valid output."""
        output = create_legacy_tracker_output(
            normalized_center=(0.1, -0.2),
            confidence=0.8,
            tracking_active=True
        )

        assert output.data_type == TrackerDataType.POSITION_2D
        assert output.position_2d == (0.1, -0.2)
        assert output.confidence == 0.8
        assert output.tracking_active is True
        assert output.tracker_id == "legacy"

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_create_legacy_with_bbox(self):
        """create_legacy_tracker_output handles bbox."""
        output = create_legacy_tracker_output(
            bbox=(100, 100, 50, 50),
            normalized_bbox=(0.1, 0.1, 0.05, 0.05),
            tracking_active=True
        )

        assert output.bbox == (100, 100, 50, 50)
        assert output.normalized_bbox == (0.1, 0.1, 0.05, 0.05)

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_create_legacy_metadata(self):
        """create_legacy_tracker_output sets legacy metadata."""
        output = create_legacy_tracker_output(tracking_active=False)

        assert output.metadata.get('legacy_format') is True

    def test_legacy_alias_exists(self):
        """LegacyTrackerData alias exists."""
        assert LegacyTrackerData is TrackerOutput


# =============================================================================
# Test: Multi-Target Support
# =============================================================================

class TestMultiTargetSupport:
    """Test multi-target tracking support."""

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_target_id(self):
        """TrackerOutput with target_id."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.0, 0.0),
            target_id=42
        )
        assert output.target_id == 42

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_multiple_targets(self):
        """TrackerOutput with targets list."""
        targets = [
            {'id': 1, 'position': (0.1, 0.1)},
            {'id': 2, 'position': (-0.2, 0.3)}
        ]
        output = TrackerOutput(
            data_type=TrackerDataType.MULTI_TARGET,
            timestamp=time.time(),
            tracking_active=True,
            targets=targets
        )
        assert len(output.targets) == 2
        assert output.targets[0]['id'] == 1


# =============================================================================
# Test: Raw and Metadata Fields
# =============================================================================

class TestRawAndMetadataFields:
    """Test raw_data and metadata fields."""

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_empty_raw_data_default(self):
        """raw_data defaults to empty dict."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True
        )
        assert output.raw_data == {}

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_raw_data(self):
        """raw_data stores custom data."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            raw_data={'yolo_class': 'car', 'detection_score': 0.95}
        )
        assert output.raw_data['yolo_class'] == 'car'

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_empty_metadata_default(self):
        """metadata defaults to empty dict."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True
        )
        assert output.metadata == {}

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_metadata(self):
        """metadata stores additional info."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            metadata={'source': 'camera_1', 'frame_id': 1234}
        )
        assert output.metadata['source'] == 'camera_1'

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_quality_metrics_default(self):
        """quality_metrics defaults to empty dict."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True
        )
        assert output.quality_metrics == {}

    @patch('classes.tracker_output.SCHEMA_MANAGER_AVAILABLE', False)
    def test_with_quality_metrics(self):
        """quality_metrics stores quality data."""
        output = TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            quality_metrics={'sharpness': 0.8, 'noise': 0.1}
        )
        assert output.quality_metrics['sharpness'] == 0.8
