# tests/fixtures/mock_dlib.py
"""
Mock dlib tracker objects for testing dlib tracker implementations.

Provides mock implementation of dlib.correlation_tracker for isolated
unit testing without requiring actual dlib library.
"""

import numpy as np
from typing import Tuple, Optional


class MockDlibRectangle:
    """Mock dlib.rectangle for testing."""

    def __init__(self, left: int, top: int, right: int, bottom: int):
        """
        Initialize mock rectangle.

        Args:
            left: Left x coordinate
            top: Top y coordinate
            right: Right x coordinate
            bottom: Bottom y coordinate
        """
        self._left = left
        self._top = top
        self._right = right
        self._bottom = bottom

    def left(self) -> int:
        """Get left x coordinate."""
        return self._left

    def top(self) -> int:
        """Get top y coordinate."""
        return self._top

    def right(self) -> int:
        """Get right x coordinate."""
        return self._right

    def bottom(self) -> int:
        """Get bottom y coordinate."""
        return self._bottom

    def width(self) -> int:
        """Get width."""
        return self._right - self._left

    def height(self) -> int:
        """Get height."""
        return self._bottom - self._top

    def center(self) -> Tuple[float, float]:
        """Get center point."""
        return (
            (self._left + self._right) / 2,
            (self._top + self._bottom) / 2
        )


class MockDlibCorrelationTracker:
    """
    Mock dlib.correlation_tracker for testing DlibTracker.

    Simulates dlib correlation tracker behavior with configurable PSR
    (Peak-to-Sidelobe Ratio) responses.

    Attributes:
        initialized: Whether tracker has been initialized
        position: Current position as MockDlibRectangle
        psr: Current PSR value
        base_psr: Base PSR value for updates
    """

    def __init__(self, base_psr: float = 15.0):
        """
        Initialize mock dlib correlation tracker.

        Args:
            base_psr: Base PSR value for tracking updates
        """
        self.initialized = False
        self.position: Optional[MockDlibRectangle] = None
        self.psr = base_psr
        self.base_psr = base_psr
        self.update_count = 0
        self._psr_variance = 2.0  # PSR variance for realistic simulation
        self._fail_after_n_updates: Optional[int] = None
        self._movement_per_update = (0, 0)
        self._scale_change_per_update = 1.0
        self._psr_decay_rate = 0.0  # PSR decay per update

    def start_track(self, frame: np.ndarray, rect: MockDlibRectangle) -> None:
        """
        Start tracking with initial frame and rectangle.

        Args:
            frame: Initial video frame
            rect: Initial bounding rectangle
        """
        self.initialized = True
        self.position = MockDlibRectangle(
            rect.left(), rect.top(), rect.right(), rect.bottom()
        )
        self.update_count = 0
        self.psr = self.base_psr

    def update(self, frame: np.ndarray) -> float:
        """
        Update tracker with new frame.

        Args:
            frame: Current video frame

        Returns:
            PSR (Peak-to-Sidelobe Ratio) value
        """
        if not self.initialized or self.position is None:
            return 0.0

        self.update_count += 1

        # Check if configured to fail
        if self._fail_after_n_updates and self.update_count > self._fail_after_n_updates:
            self.psr = max(0.0, self.psr - 5.0)  # Rapid PSR drop
            return self.psr

        # Apply PSR decay
        self.psr = max(3.0, self.base_psr - self._psr_decay_rate * self.update_count)

        # Add realistic PSR variance
        psr_noise = np.random.normal(0, self._psr_variance)
        current_psr = max(0.0, self.psr + psr_noise)

        # Update position
        left = self.position.left() + self._movement_per_update[0]
        top = self.position.top() + self._movement_per_update[1]
        width = int(self.position.width() * self._scale_change_per_update)
        height = int(self.position.height() * self._scale_change_per_update)

        self.position = MockDlibRectangle(
            int(left), int(top), int(left + width), int(top + height)
        )

        return current_psr

    def get_position(self) -> MockDlibRectangle:
        """
        Get current tracking position.

        Returns:
            Current bounding rectangle
        """
        if self.position is None:
            return MockDlibRectangle(0, 0, 0, 0)
        return self.position

    def set_movement(self, dx: int, dy: int) -> None:
        """Configure movement per update."""
        self._movement_per_update = (dx, dy)

    def set_scale_change(self, scale: float) -> None:
        """Configure scale change per update."""
        self._scale_change_per_update = scale

    def set_fail_after(self, n_updates: int) -> None:
        """Configure tracker to fail (low PSR) after N updates."""
        self._fail_after_n_updates = n_updates

    def set_psr_variance(self, variance: float) -> None:
        """Set PSR variance for realistic simulation."""
        self._psr_variance = variance

    def set_psr_decay_rate(self, rate: float) -> None:
        """Set PSR decay rate per update."""
        self._psr_decay_rate = rate

    def set_base_psr(self, psr: float) -> None:
        """Set base PSR value."""
        self.base_psr = psr
        self.psr = psr


# Factory functions for mock dlib objects

def rectangle(left: int, top: int, right: int, bottom: int) -> MockDlibRectangle:
    """
    Create mock dlib.rectangle (matches dlib.rectangle API).

    Args:
        left: Left x coordinate
        top: Top y coordinate
        right: Right x coordinate
        bottom: Bottom y coordinate

    Returns:
        MockDlibRectangle instance
    """
    return MockDlibRectangle(left, top, right, bottom)


def correlation_tracker() -> MockDlibCorrelationTracker:
    """
    Create mock dlib.correlation_tracker (matches dlib.correlation_tracker API).

    Returns:
        MockDlibCorrelationTracker instance
    """
    return MockDlibCorrelationTracker()


# Factory functions for testing

def create_mock_dlib_tracker(
    base_psr: float = 15.0,
    movement: Tuple[int, int] = (0, 0),
    psr_variance: float = 2.0,
    fail_after: Optional[int] = None
) -> MockDlibCorrelationTracker:
    """
    Create configured mock dlib correlation tracker.

    Args:
        base_psr: Base PSR value for tracking
        movement: (dx, dy) movement per update
        psr_variance: PSR variance for realistic simulation
        fail_after: Number of updates before failure

    Returns:
        Configured MockDlibCorrelationTracker instance
    """
    tracker = MockDlibCorrelationTracker(base_psr)
    tracker.set_movement(*movement)
    tracker.set_psr_variance(psr_variance)
    if fail_after:
        tracker.set_fail_after(fail_after)
    return tracker


def create_mock_dlib_rect_from_bbox(
    bbox: Tuple[int, int, int, int]
) -> MockDlibRectangle:
    """
    Create mock dlib rectangle from (x, y, w, h) bbox.

    Args:
        bbox: Bounding box as (x, y, width, height)

    Returns:
        MockDlibRectangle instance
    """
    x, y, w, h = bbox
    return MockDlibRectangle(x, y, x + w, y + h)


class MockDlibModule:
    """
    Mock dlib module for patching dlib imports.

    Usage:
        with patch('classes.trackers.dlib_tracker.dlib', MockDlibModule()):
            tracker = DlibTracker(...)
    """

    def __init__(self, base_psr: float = 15.0):
        """
        Initialize mock dlib module.

        Args:
            base_psr: Default base PSR for trackers
        """
        self.base_psr = base_psr
        self._trackers = []  # Keep track of created trackers

    def rectangle(self, left: int, top: int, right: int, bottom: int) -> MockDlibRectangle:
        """Create mock rectangle."""
        return MockDlibRectangle(left, top, right, bottom)

    def correlation_tracker(self) -> MockDlibCorrelationTracker:
        """Create mock correlation tracker."""
        tracker = MockDlibCorrelationTracker(self.base_psr)
        self._trackers.append(tracker)
        return tracker

    @property
    def __version__(self) -> str:
        """Return mock dlib version."""
        return "19.24.0.mock"

    def get_last_tracker(self) -> Optional[MockDlibCorrelationTracker]:
        """Get last created tracker for test assertions."""
        return self._trackers[-1] if self._trackers else None

    def clear_trackers(self) -> None:
        """Clear tracked tracker instances."""
        self._trackers.clear()


# PSR value constants for testing (based on dlib research)
class PSRConstants:
    """PSR threshold constants for testing."""

    EXCELLENT = 25.0  # Excellent tracking
    GOOD = 15.0       # Good tracking
    MARGINAL = 7.0    # Marginal tracking
    POOR = 4.0        # Poor tracking - likely lost
    LOST = 2.0        # Tracking lost
