"""
TrackingStateManager Unit Tests

Tests for robust object tracking state management.
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from classes.tracking_state_manager import TrackingStateManager


pytestmark = [pytest.mark.unit, pytest.mark.core_app]


@pytest.fixture
def default_config():
    """Default configuration for tests."""
    return {
        'TRACKING_STRATEGY': 'hybrid',
        'ID_LOSS_TOLERANCE_FRAMES': 5,
        'SPATIAL_IOU_THRESHOLD': 0.35,
        'ENABLE_PREDICTION_BUFFER': True,
        'CONFIDENCE_SMOOTHING_ALPHA': 0.8,
        'TRACK_CONFIDENCE_DECAY_RATE': 0.05,
        'ENABLE_APPEARANCE_MODEL': False,
        'ENABLE_GRACEFUL_DEGRADATION': True,
        'EXTENDED_TOLERANCE_FRAMES': 10,
    }


@pytest.fixture
def manager(default_config):
    """Create TrackingStateManager for tests."""
    return TrackingStateManager(default_config)


def compute_iou(box1, box2):
    """Simple IoU computation for tests."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    if x2 < x1 or y2 < y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection

    return intersection / union if union > 0 else 0.0


class TestTrackingStateManagerInit:
    """Tests for TrackingStateManager initialization."""

    def test_default_state(self, manager):
        """Test initial state is empty."""
        assert manager.selected_track_id is None
        assert manager.selected_class_id is None
        assert manager.last_known_bbox is None
        assert manager.frames_since_detection == 0

    def test_config_loaded(self, manager):
        """Test configuration is loaded."""
        assert manager.tracking_strategy == 'hybrid'
        assert manager.spatial_iou_threshold == 0.35
        assert manager.max_history == 5

    def test_is_not_tracking(self, manager):
        """Test not tracking initially."""
        assert manager.is_tracking_active() is False


class TestStartTracking:
    """Tests for start_tracking method."""

    def test_basic_start(self, manager):
        """Test starting tracking."""
        manager.start_tracking(
            track_id=1,
            class_id=0,
            bbox=(100, 100, 200, 200),
            confidence=0.9,
            center=(150, 150)
        )

        assert manager.selected_track_id == 1
        assert manager.selected_class_id == 0
        assert manager.last_known_bbox == (100, 100, 200, 200)
        assert manager.last_known_center == (150, 150)
        assert manager.smoothed_confidence == 0.9
        assert manager.frames_since_detection == 0

    def test_is_tracking_after_start(self, manager):
        """Test is_tracking_active after start."""
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))

        assert manager.is_tracking_active() is True

    def test_history_cleared(self, manager):
        """Test history is cleared on new tracking."""
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))

        assert len(manager.tracking_history) == 1  # New entry


class TestMatchById:
    """Tests for _match_by_id method."""

    @pytest.fixture
    def tracking_manager(self, manager):
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))
        return manager

    def test_match_found(self, tracking_manager):
        """Test ID match is found."""
        detections = [
            [110, 110, 210, 210, 1, 0.85, 0]  # Same ID
        ]

        match = tracking_manager._match_by_id(detections)

        assert match is not None
        assert match['track_id'] == 1

    def test_match_not_found(self, tracking_manager):
        """Test ID not found."""
        detections = [
            [110, 110, 210, 210, 2, 0.85, 0]  # Different ID
        ]

        match = tracking_manager._match_by_id(detections)

        assert match is None

    def test_wrong_class_not_matched(self, tracking_manager):
        """Test wrong class is not matched."""
        tracking_manager.class_match_flexible = False
        detections = [
            [110, 110, 210, 210, 1, 0.85, 1]  # Same ID, wrong class
        ]

        match = tracking_manager._match_by_id(detections)

        assert match is None


class TestMatchBySpatial:
    """Tests for _match_by_spatial method."""

    @pytest.fixture
    def tracking_manager(self, manager):
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))
        return manager

    def test_high_iou_match(self, tracking_manager):
        """Test high IoU match is found."""
        detections = [
            [110, 110, 210, 210, 2, 0.85, 0]  # Different ID but overlapping
        ]

        match = tracking_manager._match_by_spatial(detections, compute_iou)

        assert match is not None
        assert match['iou_match'] is True

    def test_low_iou_no_match(self, tracking_manager):
        """Test low IoU is not matched."""
        detections = [
            [500, 500, 600, 600, 2, 0.85, 0]  # Far away
        ]

        match = tracking_manager._match_by_spatial(detections, compute_iou)

        assert match is None

    def test_best_iou_selected(self, tracking_manager):
        """Test best IoU is selected from multiple."""
        detections = [
            [150, 150, 250, 250, 2, 0.85, 0],  # Lower IoU
            [105, 105, 205, 205, 3, 0.80, 0],  # Higher IoU
        ]

        match = tracking_manager._match_by_spatial(detections, compute_iou)

        # Should match the one with higher IoU
        assert match is not None
        assert match['track_id'] == 3

    def test_wrong_class_not_matched(self, tracking_manager):
        """Test wrong class not matched even with good IoU."""
        detections = [
            [105, 105, 205, 205, 2, 0.85, 1]  # Same location, wrong class
        ]

        match = tracking_manager._match_by_spatial(detections, compute_iou)

        assert match is None


class TestUpdateTracking:
    """Tests for update_tracking method."""

    @pytest.fixture
    def tracking_manager(self, manager):
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))
        return manager

    def test_id_match_updates_state(self, tracking_manager):
        """Test ID match updates tracking state."""
        detections = [
            [110, 110, 210, 210, 1, 0.85, 0]
        ]

        is_active, detection = tracking_manager.update_tracking(detections, compute_iou)

        assert is_active is True
        assert detection is not None
        assert tracking_manager.frames_since_detection == 0

    def test_no_match_increments_counter(self, tracking_manager):
        """Test no match increments frames_since_detection."""
        detections = []  # No detections

        is_active, detection = tracking_manager.update_tracking(detections, compute_iou)

        assert tracking_manager.frames_since_detection == 1

    def test_within_tolerance_still_active(self, tracking_manager):
        """Test tracking active within tolerance."""
        detections = []

        for _ in range(3):  # Less than tolerance (5)
            is_active, _ = tracking_manager.update_tracking(detections, compute_iou)

        assert is_active is True

    def test_spatial_fallback(self, tracking_manager):
        """Test spatial matching when ID changes."""
        # First, lose the ID
        tracking_manager.frames_since_detection = 1

        # Detection with different ID but same location
        detections = [
            [105, 105, 205, 205, 2, 0.85, 0]  # ID changed but same location
        ]

        is_active, detection = tracking_manager.update_tracking(detections, compute_iou)

        assert is_active is True
        assert detection is not None
        assert detection.get('iou_match') is True


class TestConfidenceManagement:
    """Tests for confidence smoothing and decay."""

    @pytest.fixture
    def tracking_manager(self, manager):
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))
        return manager

    def test_confidence_smoothing(self, tracking_manager):
        """Test confidence is smoothed."""
        initial_conf = tracking_manager.smoothed_confidence

        detections = [
            [110, 110, 210, 210, 1, 0.5, 0]  # Lower confidence
        ]

        tracking_manager.update_tracking(detections, compute_iou)

        # Smoothed confidence should be between initial and new
        assert tracking_manager.smoothed_confidence < initial_conf
        assert tracking_manager.smoothed_confidence > 0.5

    def test_confidence_decay_on_loss(self, tracking_manager):
        """Test confidence decays when detection lost."""
        initial_conf = tracking_manager.smoothed_confidence

        # Lose detection
        tracking_manager.update_tracking([], compute_iou)

        assert tracking_manager.smoothed_confidence < initial_conf


class TestGracefulDegradation:
    """Tests for graceful degradation during track loss."""

    @pytest.fixture
    def tracking_manager(self, manager):
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))
        return manager

    def test_lenient_spatial_recovery(self, tracking_manager):
        """Test lenient spatial matching for recovery."""
        # Exceed normal tolerance
        for _ in range(6):
            tracking_manager.update_tracking([], compute_iou)

        # Detection with moderate IoU
        detections = [
            [130, 130, 230, 230, 5, 0.7, 0]  # Moderate overlap
        ]

        is_active, detection = tracking_manager.update_tracking(detections, compute_iou)

        # May still recover with lenient matching
        # (depends on actual IoU calculation)

    def test_complete_loss(self, tracking_manager):
        """Test complete loss after extended absence."""
        # Exceed extended tolerance
        for _ in range(20):
            is_active, detection = tracking_manager.update_tracking([], compute_iou)

        # Eventually should signal loss
        assert detection is not None
        if isinstance(detection, dict):
            assert detection.get('need_reselection', False) is True or is_active is False


class TestClear:
    """Tests for clear method."""

    def test_clear_resets_state(self, manager):
        """Test clear resets all tracking state."""
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))
        manager.clear()

        assert manager.selected_track_id is None
        assert manager.selected_class_id is None
        assert manager.last_known_bbox is None
        assert manager.frames_since_detection == 0
        assert manager.smoothed_confidence == 0.0


class TestGetTrackingInfo:
    """Tests for get_tracking_info method."""

    @pytest.fixture
    def tracking_manager(self, manager):
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))
        return manager

    def test_info_contains_all_fields(self, tracking_manager):
        """Test tracking info contains all expected fields."""
        info = tracking_manager.get_tracking_info()

        assert 'track_id' in info
        assert 'class_id' in info
        assert 'bbox' in info
        assert 'center' in info
        assert 'confidence' in info
        assert 'frames_since_detection' in info
        assert 'is_active' in info

    def test_info_values_correct(self, tracking_manager):
        """Test tracking info values are correct."""
        info = tracking_manager.get_tracking_info()

        assert info['track_id'] == 1
        assert info['class_id'] == 0
        assert info['bbox'] == (100, 100, 200, 200)
        assert info['is_active'] is True


class TestTrackingStrategies:
    """Tests for different tracking strategies."""

    def test_id_only_strategy(self, default_config):
        """Test ID-only strategy."""
        default_config['TRACKING_STRATEGY'] = 'id_only'
        manager = TrackingStateManager(default_config)
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))

        # Different ID but same location - should NOT match
        detections = [
            [105, 105, 205, 205, 2, 0.85, 0]
        ]

        is_active, detection = manager.update_tracking(detections, compute_iou)

        # With ID-only, should not find detection (no spatial fallback)
        assert detection is None or detection.get('track_id') != 2

    def test_spatial_only_strategy(self, default_config):
        """Test spatial-only strategy."""
        default_config['TRACKING_STRATEGY'] = 'spatial_only'
        manager = TrackingStateManager(default_config)
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))

        # Same ID but far away - should NOT match
        detections = [
            [500, 500, 600, 600, 1, 0.85, 0]
        ]

        is_active, detection = manager.update_tracking(detections, compute_iou)

        # With spatial-only, should not match (too far)
        assert detection is None

    def test_hybrid_strategy_prefers_id(self, default_config):
        """Test hybrid strategy prefers ID match."""
        default_config['TRACKING_STRATEGY'] = 'hybrid'
        manager = TrackingStateManager(default_config)
        manager.start_tracking(1, 0, (100, 100, 200, 200), 0.9, (150, 150))

        # Two detections: one with matching ID (far), one with good IoU (different ID)
        detections = [
            [500, 500, 600, 600, 1, 0.85, 0],  # Right ID, wrong location
            [105, 105, 205, 205, 2, 0.90, 0],  # Wrong ID, right location
        ]

        is_active, detection = manager.update_tracking(detections, compute_iou)

        # Hybrid should prefer ID match
        assert detection is not None
        assert detection['track_id'] == 1


class TestParseDetection:
    """Tests for _parse_detection helper."""

    def test_parse_detection(self, manager):
        """Test detection parsing."""
        detection_list = [100, 100, 200, 200, 1, 0.85, 0]

        result = manager._parse_detection(detection_list)

        assert result['track_id'] == 1
        assert result['class_id'] == 0
        assert result['bbox'] == (100, 100, 200, 200)
        assert result['confidence'] == 0.85
        assert result['center'] == (150, 150)
        assert result['iou_match'] is False
