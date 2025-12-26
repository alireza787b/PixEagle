# tests/fixtures/mock_opencv.py
"""
Mock OpenCV tracker objects for testing tracker implementations.

Provides mock implementations of cv2.TrackerCSRT and cv2.TrackerKCF
for isolated unit testing without requiring actual OpenCV functionality.
"""

import numpy as np
from typing import Tuple, Optional
from unittest.mock import MagicMock


class MockCSRTParams:
    """Mock cv2.TrackerCSRT_Params for testing CSRT configuration."""

    def __init__(self):
        self.use_color_names = True
        self.use_hog = True
        self.number_of_scales = 33
        self.scale_step = 1.02
        self.use_segmentation = True


class MockCSRTTracker:
    """
    Mock cv2.TrackerCSRT for testing CSRTTracker.

    Simulates OpenCV CSRT tracker behavior with configurable responses.

    Attributes:
        initialized: Whether tracker has been initialized
        bbox: Current bounding box
        update_success: Whether next update should succeed
        update_count: Number of update calls
        consecutive_failures: Counter for simulating failures
    """

    def __init__(self, success_rate: float = 1.0):
        """
        Initialize mock CSRT tracker.

        Args:
            success_rate: Probability of successful update (0.0-1.0)
        """
        self.initialized = False
        self.bbox: Optional[Tuple[int, int, int, int]] = None
        self.success_rate = success_rate
        self.update_success = True
        self.update_count = 0
        self.consecutive_failures = 0
        self._fail_after_n_updates: Optional[int] = None
        self._movement_per_update = (0, 0)  # (dx, dy) per update
        self._scale_change_per_update = 1.0  # Scale multiplier per update

    def init(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> bool:
        """
        Initialize tracker with frame and bounding box.

        Args:
            frame: Initial video frame
            bbox: Initial bounding box (x, y, w, h)

        Returns:
            True if initialization successful
        """
        self.initialized = True
        self.bbox = tuple(int(v) for v in bbox)
        self.update_count = 0
        self.consecutive_failures = 0
        return True

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Update tracker with new frame.

        Args:
            frame: Current video frame

        Returns:
            Tuple of (success, bbox)
        """
        if not self.initialized or self.bbox is None:
            return False, (0, 0, 0, 0)

        self.update_count += 1

        # Check if configured to fail after N updates
        if self._fail_after_n_updates and self.update_count > self._fail_after_n_updates:
            self.consecutive_failures += 1
            return False, self.bbox

        # Random failure based on success rate
        if np.random.random() > self.success_rate:
            self.consecutive_failures += 1
            return False, self.bbox

        # Apply movement simulation
        x, y, w, h = self.bbox
        x += self._movement_per_update[0]
        y += self._movement_per_update[1]

        # Apply scale change
        new_w = int(w * self._scale_change_per_update)
        new_h = int(h * self._scale_change_per_update)

        self.bbox = (int(x), int(y), new_w, new_h)
        self.consecutive_failures = 0

        return True, self.bbox

    def set_movement(self, dx: int, dy: int) -> None:
        """Configure movement per update for motion simulation."""
        self._movement_per_update = (dx, dy)

    def set_scale_change(self, scale: float) -> None:
        """Configure scale change per update."""
        self._scale_change_per_update = scale

    def set_fail_after(self, n_updates: int) -> None:
        """Configure tracker to fail after N updates."""
        self._fail_after_n_updates = n_updates

    def set_success_rate(self, rate: float) -> None:
        """Set success rate (0.0-1.0)."""
        self.success_rate = max(0.0, min(1.0, rate))


class MockKCFTracker:
    """
    Mock cv2.TrackerKCF for testing KCFKalmanTracker.

    Simulates OpenCV KCF tracker behavior with configurable responses.
    """

    def __init__(self, success_rate: float = 1.0):
        """
        Initialize mock KCF tracker.

        Args:
            success_rate: Probability of successful update (0.0-1.0)
        """
        self.initialized = False
        self.bbox: Optional[Tuple[int, int, int, int]] = None
        self.success_rate = success_rate
        self.update_count = 0
        self._fail_after_n_updates: Optional[int] = None
        self._movement_per_update = (0, 0)
        self._scale_change_per_update = 1.0
        self._noise_std = 0.0  # Pixel noise standard deviation

    def init(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> bool:
        """Initialize tracker with frame and bounding box."""
        self.initialized = True
        self.bbox = tuple(int(v) for v in bbox)
        self.update_count = 0
        return True

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[float, float, float, float]]:
        """
        Update tracker with new frame.

        Returns:
            Tuple of (success, bbox) where bbox may have float values
        """
        if not self.initialized or self.bbox is None:
            return False, (0.0, 0.0, 0.0, 0.0)

        self.update_count += 1

        # Check if configured to fail
        if self._fail_after_n_updates and self.update_count > self._fail_after_n_updates:
            return False, tuple(float(v) for v in self.bbox)

        # Random failure based on success rate
        if np.random.random() > self.success_rate:
            return False, tuple(float(v) for v in self.bbox)

        # Apply movement + noise
        x, y, w, h = self.bbox
        x += self._movement_per_update[0] + np.random.normal(0, self._noise_std)
        y += self._movement_per_update[1] + np.random.normal(0, self._noise_std)

        # Apply scale change
        new_w = w * self._scale_change_per_update
        new_h = h * self._scale_change_per_update

        self.bbox = (int(x), int(y), int(new_w), int(new_h))

        return True, (float(x), float(y), float(new_w), float(new_h))

    def set_movement(self, dx: int, dy: int) -> None:
        """Configure movement per update."""
        self._movement_per_update = (dx, dy)

    def set_scale_change(self, scale: float) -> None:
        """Configure scale change per update."""
        self._scale_change_per_update = scale

    def set_fail_after(self, n_updates: int) -> None:
        """Configure tracker to fail after N updates."""
        self._fail_after_n_updates = n_updates

    def set_noise(self, std: float) -> None:
        """Set position noise standard deviation."""
        self._noise_std = std


class MockVideoHandler:
    """Mock video handler for testing trackers."""

    def __init__(self, width: int = 640, height: int = 480):
        """
        Initialize mock video handler.

        Args:
            width: Frame width in pixels
            height: Frame height in pixels
        """
        self.width = width
        self.height = height

    def get_frame(self) -> np.ndarray:
        """Get a mock frame."""
        return np.zeros((self.height, self.width, 3), dtype=np.uint8)

    def get_resolution(self) -> Tuple[int, int]:
        """Get frame resolution."""
        return (self.width, self.height)


class MockDetector:
    """Mock detector for appearance model testing."""

    def __init__(self, feature_dim: int = 128):
        """
        Initialize mock detector.

        Args:
            feature_dim: Dimension of feature vectors
        """
        self.feature_dim = feature_dim
        self.initial_features = None
        self.adaptive_features = None

    def extract_features(self, frame: np.ndarray, bbox: Tuple) -> np.ndarray:
        """Extract mock features from frame region."""
        # Return consistent features based on bbox position
        np.random.seed(hash(bbox) % 2**32)
        features = np.random.randn(self.feature_dim).astype(np.float32)
        np.random.seed()  # Reset seed
        return features

    def compute_appearance_confidence(self, current: np.ndarray, reference: np.ndarray) -> float:
        """Compute appearance similarity."""
        if current is None or reference is None:
            return 0.5
        similarity = np.dot(current, reference) / (np.linalg.norm(current) * np.linalg.norm(reference) + 1e-6)
        return float(max(0.0, min(1.0, (similarity + 1) / 2)))


class MockAppController:
    """Mock application controller for testing."""

    def __init__(self):
        self.estimator = None
        self.smart_tracker = None
        self.following_active = False

    def set_estimator(self, estimator) -> None:
        """Set position estimator."""
        self.estimator = estimator


class MockPositionEstimator:
    """Mock position estimator for testing."""

    def __init__(self):
        self.dt = 0.033  # ~30 FPS
        self.state = np.array([0.0, 0.0, 0.0, 0.0])  # [x, y, vx, vy]
        self._reset_called = False

    def reset(self) -> None:
        """Reset estimator state."""
        self.state = np.array([0.0, 0.0, 0.0, 0.0])
        self._reset_called = True

    def set_dt(self, dt: float) -> None:
        """Set time delta."""
        self.dt = dt

    def predict_only(self) -> None:
        """Predict next state without measurement."""
        self.state[0] += self.state[2] * self.dt
        self.state[1] += self.state[3] * self.dt

    def predict_and_update(self, measurement: np.ndarray) -> None:
        """Predict and update with measurement."""
        # Simple update: blend prediction with measurement
        self.predict_only()
        if len(measurement) >= 2:
            alpha = 0.7
            self.state[0] = alpha * measurement[0] + (1 - alpha) * self.state[0]
            self.state[1] = alpha * measurement[1] + (1 - alpha) * self.state[1]

    def get_estimate(self) -> np.ndarray:
        """Get current state estimate."""
        return self.state.copy()


# Factory functions for creating mocks with specific configurations

def create_mock_csrt_tracker(
    success_rate: float = 1.0,
    movement: Tuple[int, int] = (0, 0),
    fail_after: Optional[int] = None
) -> MockCSRTTracker:
    """
    Create configured mock CSRT tracker.

    Args:
        success_rate: Update success probability
        movement: (dx, dy) movement per update
        fail_after: Number of updates before failure

    Returns:
        Configured MockCSRTTracker instance
    """
    tracker = MockCSRTTracker(success_rate)
    tracker.set_movement(*movement)
    if fail_after:
        tracker.set_fail_after(fail_after)
    return tracker


def create_mock_kcf_tracker(
    success_rate: float = 1.0,
    movement: Tuple[int, int] = (0, 0),
    noise: float = 0.0
) -> MockKCFTracker:
    """
    Create configured mock KCF tracker.

    Args:
        success_rate: Update success probability
        movement: (dx, dy) movement per update
        noise: Position noise standard deviation

    Returns:
        Configured MockKCFTracker instance
    """
    tracker = MockKCFTracker(success_rate)
    tracker.set_movement(*movement)
    tracker.set_noise(noise)
    return tracker


def create_mock_test_frame(
    width: int = 640,
    height: int = 480,
    channels: int = 3
) -> np.ndarray:
    """
    Create a mock test frame.

    Args:
        width: Frame width
        height: Frame height
        channels: Number of color channels

    Returns:
        np.ndarray: Mock frame
    """
    return np.random.randint(0, 255, (height, width, channels), dtype=np.uint8)


def create_mock_bbox(
    center: Tuple[int, int] = (320, 240),
    size: Tuple[int, int] = (50, 50)
) -> Tuple[int, int, int, int]:
    """
    Create a mock bounding box.

    Args:
        center: (cx, cy) center coordinates
        size: (width, height) dimensions

    Returns:
        Tuple of (x, y, w, h)
    """
    cx, cy = center
    w, h = size
    x = cx - w // 2
    y = cy - h // 2
    return (x, y, w, h)
