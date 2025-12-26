# tests/unit/trackers/test_supporting_components.py
"""
Unit tests for tracker supporting components.

Tests MotionPredictor, TrackingStateManager, AppearanceModel,
and PositionEstimator classes.
"""

import pytest
import sys
import os
import numpy as np
import time
from unittest.mock import MagicMock, patch, PropertyMock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))


# =============================================================================
# MotionPredictor Tests
# =============================================================================

@pytest.mark.unit
class TestMotionPredictorInitialization:
    """Tests for MotionPredictor initialization."""

    def test_init_default_parameters(self):
        """MotionPredictor should initialize with default parameters."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()

        assert predictor.history_size == 5
        assert predictor.velocity_alpha == 0.7
        assert predictor.acceleration_alpha == 0.5

    def test_init_custom_parameters(self):
        """MotionPredictor should accept custom parameters."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor(
            history_size=10,
            velocity_alpha=0.5,
            acceleration_alpha=0.3
        )

        assert predictor.history_size == 10
        assert predictor.velocity_alpha == 0.5
        assert predictor.acceleration_alpha == 0.3

    def test_init_velocity_zero(self):
        """Initial velocity should be zero."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()

        assert predictor.velocity_x == 0.0
        assert predictor.velocity_y == 0.0
        assert predictor.velocity_w == 0.0
        assert predictor.velocity_h == 0.0

    def test_init_acceleration_zero(self):
        """Initial acceleration should be zero."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()

        assert predictor.accel_x == 0.0
        assert predictor.accel_y == 0.0


@pytest.mark.unit
class TestMotionPredictorUpdate:
    """Tests for MotionPredictor.update() method."""

    def test_update_adds_to_history(self):
        """update() should add bbox to history."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()
        bbox = (100, 100, 200, 200)
        timestamp = time.time()

        predictor.update(bbox, timestamp)

        assert len(predictor.position_history) == 1

    def test_update_computes_velocity_after_two_frames(self):
        """update() should compute velocity after two frames."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()

        # First bbox
        bbox1 = (100, 100, 200, 200)
        t1 = 1.0
        predictor.update(bbox1, t1)

        # Second bbox (moved right and down)
        bbox2 = (110, 120, 210, 220)
        t2 = 1.1  # 0.1 seconds later
        predictor.update(bbox2, t2)

        # Velocity should be non-zero now
        assert predictor.velocity_x != 0.0
        assert predictor.velocity_y != 0.0

    def test_update_limits_history_size(self):
        """update() should limit history to history_size."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor(history_size=3)

        for i in range(5):
            predictor.update((i*10, i*10, i*10+50, i*10+50), float(i))

        assert len(predictor.position_history) == 3


@pytest.mark.unit
class TestMotionPredictorPrediction:
    """Tests for MotionPredictor.predict_bbox() method."""

    def test_predict_returns_none_without_history(self):
        """predict_bbox() should return None without history."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()

        result = predictor.predict_bbox(1)

        assert result is None

    def test_predict_returns_bbox_with_history(self):
        """predict_bbox() should return bbox with history."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()
        predictor.update((100, 100, 200, 200), 1.0)

        result = predictor.predict_bbox(1)

        assert result is not None
        assert len(result) == 4

    def test_predict_linear_motion(self):
        """predict_bbox() should predict linear motion correctly."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()

        # Simulate constant velocity motion (10px/frame at 30fps = 300px/s)
        predictor.update((100, 100, 150, 150), 0.0)
        predictor.update((110, 100, 160, 150), 1/30)  # Moved 10px right

        # Predict 1 frame ahead
        result = predictor.predict_bbox(1, fps=30.0, use_acceleration=False)

        assert result is not None
        # Center should have moved further right
        center_x = (result[0] + result[2]) / 2
        assert center_x > 135  # Original center was 130

    def test_predict_kinematic_uses_acceleration(self):
        """predict_bbox() with acceleration should use kinematic equations."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()

        # Build up acceleration
        predictor.update((100, 100, 150, 150), 0.0)
        predictor.update((110, 100, 160, 150), 1/30)
        predictor.update((125, 100, 175, 150), 2/30)  # Accelerating

        # Predict with acceleration
        result_with_accel = predictor.predict_bbox(5, fps=30.0, use_acceleration=True)
        # Predict without acceleration
        result_without_accel = predictor.predict_bbox(5, fps=30.0, use_acceleration=False)

        # Results should differ
        assert result_with_accel != result_without_accel

    def test_predict_maintains_minimum_size(self):
        """predict_bbox() should maintain minimum bbox size."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()
        predictor.update((100, 100, 120, 120), 0.0)  # Small 20x20 bbox

        result = predictor.predict_bbox(1)

        width = result[2] - result[0]
        height = result[3] - result[1]

        assert width >= 10
        assert height >= 10


@pytest.mark.unit
class TestMotionPredictorUtilities:
    """Tests for MotionPredictor utility methods."""

    def test_get_velocity_magnitude(self):
        """get_velocity_magnitude() should return correct magnitude."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()
        predictor.velocity_x = 3.0
        predictor.velocity_y = 4.0

        magnitude = predictor.get_velocity_magnitude()

        assert abs(magnitude - 5.0) < 0.001

    def test_is_moving_true_when_above_threshold(self):
        """is_moving() should return True when above threshold."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()
        predictor.velocity_x = 10.0
        predictor.velocity_y = 0.0

        assert predictor.is_moving(threshold=5.0) is True

    def test_is_moving_false_when_below_threshold(self):
        """is_moving() should return False when below threshold."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()
        predictor.velocity_x = 2.0
        predictor.velocity_y = 2.0

        assert predictor.is_moving(threshold=5.0) is False

    def test_reset_clears_all_state(self):
        """reset() should clear all state."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()
        predictor.update((100, 100, 200, 200), 1.0)
        predictor.update((110, 110, 210, 210), 1.1)

        predictor.reset()

        assert len(predictor.position_history) == 0
        assert predictor.velocity_x == 0.0
        assert predictor.velocity_y == 0.0
        assert predictor.accel_x == 0.0
        assert predictor.accel_y == 0.0

    def test_get_state_returns_dict(self):
        """get_state() should return state dictionary."""
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()
        predictor.update((100, 100, 200, 200), 1.0)

        state = predictor.get_state()

        assert isinstance(state, dict)
        assert 'velocity_x' in state
        assert 'velocity_y' in state
        assert 'velocity_magnitude' in state
        assert 'is_moving' in state


# =============================================================================
# TrackingStateManager Tests
# =============================================================================

@pytest.fixture
def tracking_config():
    """Fixture for TrackingStateManager config."""
    return {
        'ID_LOSS_TOLERANCE_FRAMES': 5,
        'TRACKING_STRATEGY': 'hybrid',
        'SPATIAL_IOU_THRESHOLD': 0.35,
        'ENABLE_PREDICTION_BUFFER': True,
        'CONFIDENCE_SMOOTHING_ALPHA': 0.8,
        'TRACK_CONFIDENCE_DECAY_RATE': 0.05,
        'ENABLE_APPEARANCE_MODEL': False,
        'ENABLE_GRACEFUL_DEGRADATION': True,
        'EXTENDED_TOLERANCE_FRAMES': 10
    }


@pytest.mark.unit
class TestTrackingStateManagerInitialization:
    """Tests for TrackingStateManager initialization."""

    def test_init_with_config(self, tracking_config):
        """TrackingStateManager should initialize with config."""
        from classes.tracking_state_manager import TrackingStateManager

        manager = TrackingStateManager(tracking_config)

        assert manager.max_history == 5
        assert manager.tracking_strategy == 'hybrid'
        assert manager.spatial_iou_threshold == 0.35

    def test_init_with_motion_predictor(self, tracking_config):
        """TrackingStateManager should accept motion_predictor."""
        from classes.tracking_state_manager import TrackingStateManager
        from classes.motion_predictor import MotionPredictor

        predictor = MotionPredictor()
        manager = TrackingStateManager(tracking_config, motion_predictor=predictor)

        assert manager.motion_predictor is predictor

    def test_init_no_tracking_active(self, tracking_config):
        """Initial state should have no active tracking."""
        from classes.tracking_state_manager import TrackingStateManager

        manager = TrackingStateManager(tracking_config)

        assert manager.selected_track_id is None
        assert manager.is_tracking_active() is False


@pytest.mark.unit
class TestTrackingStateManagerStartTracking:
    """Tests for TrackingStateManager.start_tracking() method."""

    def test_start_tracking_sets_track_id(self, tracking_config):
        """start_tracking() should set selected track ID."""
        from classes.tracking_state_manager import TrackingStateManager

        manager = TrackingStateManager(tracking_config)

        manager.start_tracking(
            track_id=42,
            class_id=0,
            bbox=(100, 100, 200, 200),
            confidence=0.9,
            center=(150, 150)
        )

        assert manager.selected_track_id == 42
        assert manager.selected_class_id == 0
        assert manager.last_known_bbox == (100, 100, 200, 200)

    def test_start_tracking_activates_tracking(self, tracking_config):
        """start_tracking() should activate tracking."""
        from classes.tracking_state_manager import TrackingStateManager

        manager = TrackingStateManager(tracking_config)

        manager.start_tracking(
            track_id=1,
            class_id=0,
            bbox=(100, 100, 200, 200),
            confidence=0.9,
            center=(150, 150)
        )

        assert manager.is_tracking_active() is True

    def test_start_tracking_resets_frames_since_detection(self, tracking_config):
        """start_tracking() should reset frames_since_detection."""
        from classes.tracking_state_manager import TrackingStateManager

        manager = TrackingStateManager(tracking_config)
        manager.frames_since_detection = 10

        manager.start_tracking(
            track_id=1,
            class_id=0,
            bbox=(100, 100, 200, 200),
            confidence=0.9,
            center=(150, 150)
        )

        assert manager.frames_since_detection == 0


@pytest.mark.unit
class TestTrackingStateManagerUpdateTracking:
    """Tests for TrackingStateManager.update_tracking() method."""

    def test_update_returns_false_when_not_tracking(self, tracking_config):
        """update_tracking() should return False when not tracking."""
        from classes.tracking_state_manager import TrackingStateManager

        manager = TrackingStateManager(tracking_config)

        def mock_iou(box1, box2):
            return 0.5

        result, detection = manager.update_tracking([], mock_iou)

        assert result is False
        assert detection is None

    def test_update_finds_matching_track_id(self, tracking_config):
        """update_tracking() should find detection with matching track ID."""
        from classes.tracking_state_manager import TrackingStateManager

        manager = TrackingStateManager(tracking_config)
        manager.start_tracking(
            track_id=42,
            class_id=0,
            bbox=(100, 100, 200, 200),
            confidence=0.9,
            center=(150, 150)
        )

        # Detection format: [x1, y1, x2, y2, track_id, conf, class_id]
        detections = [
            [110, 110, 210, 210, 42, 0.85, 0]  # Matching track_id
        ]

        def mock_iou(box1, box2):
            return 0.5

        result, detection = manager.update_tracking(detections, mock_iou)

        assert result is True
        assert detection is not None
        assert detection['track_id'] == 42

    def test_update_increments_frames_on_loss(self, tracking_config):
        """update_tracking() should increment frames_since_detection on loss."""
        from classes.tracking_state_manager import TrackingStateManager

        manager = TrackingStateManager(tracking_config)
        manager.start_tracking(
            track_id=42,
            class_id=0,
            bbox=(100, 100, 200, 200),
            confidence=0.9,
            center=(150, 150)
        )

        # No matching detections
        detections = [
            [500, 500, 600, 600, 99, 0.85, 0]  # Different track_id and location
        ]

        def mock_iou(box1, box2):
            return 0.0

        manager.update_tracking(detections, mock_iou)

        assert manager.frames_since_detection == 1


@pytest.mark.unit
class TestTrackingStateManagerClear:
    """Tests for TrackingStateManager.clear() method."""

    def test_clear_resets_tracking_state(self, tracking_config):
        """clear() should reset all tracking state."""
        from classes.tracking_state_manager import TrackingStateManager

        manager = TrackingStateManager(tracking_config)
        manager.start_tracking(
            track_id=42,
            class_id=0,
            bbox=(100, 100, 200, 200),
            confidence=0.9,
            center=(150, 150)
        )

        manager.clear()

        assert manager.selected_track_id is None
        assert manager.selected_class_id is None
        assert manager.last_known_bbox is None
        assert manager.is_tracking_active() is False


@pytest.mark.unit
class TestTrackingStateManagerInfo:
    """Tests for TrackingStateManager.get_tracking_info() method."""

    def test_get_tracking_info_returns_dict(self, tracking_config):
        """get_tracking_info() should return dictionary."""
        from classes.tracking_state_manager import TrackingStateManager

        manager = TrackingStateManager(tracking_config)

        info = manager.get_tracking_info()

        assert isinstance(info, dict)
        assert 'track_id' in info
        assert 'is_active' in info


# =============================================================================
# AppearanceModel Tests
# =============================================================================

@pytest.fixture
def appearance_config():
    """Fixture for AppearanceModel config."""
    return {
        'APPEARANCE_FEATURE_TYPE': 'histogram',
        'APPEARANCE_MATCH_THRESHOLD': 0.7,
        'MAX_REIDENTIFICATION_FRAMES': 30,
        'APPEARANCE_ADAPTIVE_LEARNING': True,
        'APPEARANCE_LEARNING_RATE': 0.1,
        'MAX_LOST_OBJECTS_CACHED': 100,
        'ENABLE_APPEARANCE_PROFILING': False,
        'HIST_H_BINS': 30,
        'HIST_S_BINS': 32,
        'HOG_WIN_SIZE': [64, 64],
        'HOG_BLOCK_SIZE': [16, 16],
        'HOG_BLOCK_STRIDE': [8, 8],
        'HOG_CELL_SIZE': [8, 8],
        'HOG_NBINS': 9
    }


@pytest.mark.unit
class TestAppearanceModelInitialization:
    """Tests for AppearanceModel initialization."""

    def test_init_with_config(self, appearance_config):
        """AppearanceModel should initialize with config."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)

        assert model.feature_type == 'histogram'
        assert model.similarity_threshold == 0.7
        assert model.max_memory_frames == 30

    def test_init_creates_hog_descriptor(self, appearance_config):
        """AppearanceModel should create HOG descriptor."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)

        assert model.hog is not None

    def test_init_empty_lost_objects(self, appearance_config):
        """AppearanceModel should start with empty lost_objects."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)

        assert len(model.lost_objects) == 0


@pytest.mark.unit
class TestAppearanceModelFeatureExtraction:
    """Tests for AppearanceModel.extract_features() method."""

    def test_extract_features_returns_none_for_none_frame(self, appearance_config):
        """extract_features() should return None for None frame."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)

        result = model.extract_features(None, (0, 0, 100, 100))

        assert result is None

    def test_extract_features_returns_none_for_invalid_bbox(self, appearance_config):
        """extract_features() should return None for invalid bbox."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Invalid bbox (x2 <= x1)
        result = model.extract_features(frame, (100, 100, 50, 200))

        assert result is None

    def test_extract_features_returns_array(self, appearance_config):
        """extract_features() should return numpy array for valid input."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)

        # Create a colored test image
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[100:200, 100:200] = [255, 128, 64]  # BGR color

        result = model.extract_features(frame, (100, 100, 200, 200))

        assert result is not None
        assert isinstance(result, np.ndarray)

    def test_extract_features_normalized_unit_length(self, appearance_config):
        """extract_features() should return normalized unit-length vector."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)

        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        result = model.extract_features(frame, (100, 100, 200, 200))

        if result is not None:
            norm = np.linalg.norm(result)
            assert abs(norm - 1.0) < 0.01


@pytest.mark.unit
class TestAppearanceModelSimilarity:
    """Tests for AppearanceModel.compute_similarity() method."""

    def test_compute_similarity_same_features(self, appearance_config):
        """compute_similarity() should return 1.0 for identical features."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)
        features = np.array([0.5, 0.5, 0.5, 0.5])
        features = features / np.linalg.norm(features)

        similarity = model.compute_similarity(features, features.copy())

        assert abs(similarity - 1.0) < 0.01

    def test_compute_similarity_orthogonal_features(self, appearance_config):
        """compute_similarity() should return 0 for orthogonal features."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)
        features1 = np.array([1.0, 0.0])
        features2 = np.array([0.0, 1.0])

        similarity = model.compute_similarity(features1, features2)

        assert abs(similarity) < 0.01

    def test_compute_similarity_none_features(self, appearance_config):
        """compute_similarity() should return 0 for None features."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)

        similarity = model.compute_similarity(None, np.array([1.0, 0.0]))

        assert similarity == 0.0


@pytest.mark.unit
class TestAppearanceModelRegistration:
    """Tests for AppearanceModel register/mark methods."""

    def test_register_object_adds_to_lost_objects(self, appearance_config):
        """register_object() should add entry to lost_objects."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)
        features = np.array([1.0, 0.0, 0.0, 0.0])

        model.register_object(track_id=42, class_id=0, features=features)

        assert 42 in model.lost_objects
        assert model.lost_objects[42]['class_id'] == 0

    def test_mark_as_lost_sets_frame_lost(self, appearance_config):
        """mark_as_lost() should set frame_lost field."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)
        model.current_frame = 100

        features = np.array([1.0, 0.0])
        model.register_object(42, 0, features)

        model.mark_as_lost(42)

        assert 'frame_lost' in model.lost_objects[42]
        assert model.lost_objects[42]['frame_lost'] == 100

    def test_clear_removes_all_entries(self, appearance_config):
        """clear() should remove all entries."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)
        model.register_object(42, 0, np.array([1.0, 0.0]))
        model.register_object(43, 0, np.array([0.0, 1.0]))

        model.clear()

        assert len(model.lost_objects) == 0
        assert model.current_frame == 0


@pytest.mark.unit
class TestAppearanceModelMemoryManagement:
    """Tests for AppearanceModel memory management."""

    def test_increment_frame_updates_counter(self, appearance_config):
        """increment_frame() should update frame counter."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)

        model.increment_frame()

        assert model.current_frame == 1

    def test_cleanup_old_entries_removes_expired(self, appearance_config):
        """cleanup_old_entries() should remove expired entries."""
        from classes.appearance_model import AppearanceModel

        config = appearance_config.copy()
        config['MAX_REIDENTIFICATION_FRAMES'] = 5

        model = AppearanceModel(config)
        model.register_object(42, 0, np.array([1.0, 0.0]))
        model.mark_as_lost(42)

        # Advance frames beyond max_memory_frames
        for _ in range(10):
            model.increment_frame()

        assert 42 not in model.lost_objects

    def test_get_memory_status_returns_dict(self, appearance_config):
        """get_memory_status() should return status dictionary."""
        from classes.appearance_model import AppearanceModel

        model = AppearanceModel(appearance_config)
        model.register_object(42, 0, np.array([1.0, 0.0]))

        status = model.get_memory_status()

        assert isinstance(status, dict)
        assert status['stored_objects'] == 1
        assert 'feature_type' in status


# =============================================================================
# PositionEstimator Tests
# =============================================================================

@pytest.mark.unit
class TestPositionEstimatorInitialization:
    """Tests for PositionEstimator initialization."""

    def test_init_creates_kalman_filter(self):
        """PositionEstimator should create Kalman filter."""
        from classes.position_estimator import PositionEstimator

        estimator = PositionEstimator()

        assert estimator.filter is not None
        assert estimator.filter.dim_x == 4
        assert estimator.filter.dim_z == 2

    def test_init_default_dt(self):
        """PositionEstimator should have default dt."""
        from classes.position_estimator import PositionEstimator

        estimator = PositionEstimator()

        assert estimator.dt == 0.1


@pytest.mark.unit
class TestPositionEstimatorSetDt:
    """Tests for PositionEstimator.set_dt() method."""

    def test_set_dt_updates_value(self):
        """set_dt() should update dt value."""
        from classes.position_estimator import PositionEstimator

        estimator = PositionEstimator()

        estimator.set_dt(0.05)

        assert estimator.dt == 0.05

    def test_set_dt_raises_for_non_positive(self):
        """set_dt() should raise ValueError for non-positive dt."""
        from classes.position_estimator import PositionEstimator

        estimator = PositionEstimator()

        with pytest.raises(ValueError):
            estimator.set_dt(0)

        with pytest.raises(ValueError):
            estimator.set_dt(-0.1)


@pytest.mark.unit
class TestPositionEstimatorPredictAndUpdate:
    """Tests for PositionEstimator.predict_and_update() method."""

    def test_predict_and_update_accepts_list(self):
        """predict_and_update() should accept list measurement."""
        from classes.position_estimator import PositionEstimator

        estimator = PositionEstimator()

        # Should not raise
        estimator.predict_and_update([100.0, 200.0])

    def test_predict_and_update_accepts_array(self):
        """predict_and_update() should accept numpy array measurement."""
        from classes.position_estimator import PositionEstimator

        estimator = PositionEstimator()

        # Should not raise
        estimator.predict_and_update(np.array([100.0, 200.0]))

    def test_predict_and_update_raises_for_wrong_size(self):
        """predict_and_update() should raise ValueError for wrong size."""
        from classes.position_estimator import PositionEstimator

        estimator = PositionEstimator()

        with pytest.raises(ValueError):
            estimator.predict_and_update([100.0])

        with pytest.raises(ValueError):
            estimator.predict_and_update([100.0, 200.0, 300.0])


@pytest.mark.unit
class TestPositionEstimatorGetEstimate:
    """Tests for PositionEstimator.get_estimate() method."""

    def test_get_estimate_returns_list(self):
        """get_estimate() should return list."""
        from classes.position_estimator import PositionEstimator

        estimator = PositionEstimator()

        estimate = estimator.get_estimate()

        assert isinstance(estimate, list)
        assert len(estimate) == 4  # [x, y, dx, dy]

    def test_get_estimate_reflects_measurements(self):
        """get_estimate() should reflect measurements."""
        from classes.position_estimator import PositionEstimator

        estimator = PositionEstimator()

        # Update with consistent position
        for _ in range(10):
            estimator.predict_and_update([100.0, 200.0])

        estimate = estimator.get_estimate()

        # Position should converge near measurement
        assert abs(estimate[0] - 100.0) < 10.0
        assert abs(estimate[1] - 200.0) < 10.0


@pytest.mark.unit
class TestPositionEstimatorUpdateFQ:
    """Tests for PositionEstimator.update_F_and_Q() method."""

    def test_update_f_and_q_changes_matrices(self):
        """update_F_and_Q() should update filter matrices."""
        from classes.position_estimator import PositionEstimator

        estimator = PositionEstimator()
        original_F = estimator.filter.F.copy()

        estimator.update_F_and_Q(0.05)

        # F matrix should be different
        assert not np.array_equal(estimator.filter.F, original_F)
