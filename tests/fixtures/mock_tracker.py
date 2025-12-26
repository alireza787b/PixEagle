# tests/fixtures/mock_tracker.py
"""
TrackerOutput factory for testing follower implementations.

Provides convenient methods to create TrackerOutput instances
for various test scenarios.
"""

import time
from typing import Optional, Tuple, Dict, Any
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from classes.tracker_output import TrackerOutput, TrackerDataType


class TrackerOutputFactory:
    """
    Factory for creating TrackerOutput test instances.

    Provides static methods for common test scenarios.
    """

    @staticmethod
    def position_2d(
        x: float = 0.0,
        y: float = 0.0,
        confidence: float = 0.95,
        tracking_active: bool = True,
        tracker_id: str = "test_tracker"
    ) -> TrackerOutput:
        """
        Create a standard 2D position tracker output.

        Args:
            x: Normalized x position [-1, 1]
            y: Normalized y position [-1, 1]
            confidence: Tracking confidence [0, 1]
            tracking_active: Whether tracking is active
            tracker_id: Tracker identifier

        Returns:
            TrackerOutput with POSITION_2D data type
        """
        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=tracking_active,
            tracker_id=tracker_id,
            position_2d=(x, y),
            confidence=confidence
        )

    @staticmethod
    def centered(confidence: float = 0.95) -> TrackerOutput:
        """Create tracker output with target at image center."""
        return TrackerOutputFactory.position_2d(0.0, 0.0, confidence)

    @staticmethod
    def offset(x: float, y: float, confidence: float = 0.9) -> TrackerOutput:
        """Create tracker output with target at specified offset."""
        return TrackerOutputFactory.position_2d(x, y, confidence)

    @staticmethod
    def top_left(confidence: float = 0.9) -> TrackerOutput:
        """Create tracker output with target in top-left quadrant."""
        return TrackerOutputFactory.position_2d(-0.5, -0.5, confidence)

    @staticmethod
    def top_right(confidence: float = 0.9) -> TrackerOutput:
        """Create tracker output with target in top-right quadrant."""
        return TrackerOutputFactory.position_2d(0.5, -0.5, confidence)

    @staticmethod
    def bottom_left(confidence: float = 0.9) -> TrackerOutput:
        """Create tracker output with target in bottom-left quadrant."""
        return TrackerOutputFactory.position_2d(-0.5, 0.5, confidence)

    @staticmethod
    def bottom_right(confidence: float = 0.9) -> TrackerOutput:
        """Create tracker output with target in bottom-right quadrant."""
        return TrackerOutputFactory.position_2d(0.5, 0.5, confidence)

    @staticmethod
    def edge_right(confidence: float = 0.85) -> TrackerOutput:
        """Create tracker output with target at right edge."""
        return TrackerOutputFactory.position_2d(0.95, 0.0, confidence)

    @staticmethod
    def edge_left(confidence: float = 0.85) -> TrackerOutput:
        """Create tracker output with target at left edge."""
        return TrackerOutputFactory.position_2d(-0.95, 0.0, confidence)

    @staticmethod
    def lost() -> TrackerOutput:
        """
        Create tracker output for target lost scenario.

        Returns:
            TrackerOutput with tracking_active=False
        """
        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=False,
            tracker_id="test_tracker",
            position_2d=None,
            confidence=0.0
        )

    @staticmethod
    def low_confidence(x: float = 0.0, y: float = 0.0, confidence: float = 0.3) -> TrackerOutput:
        """Create tracker output with low confidence."""
        return TrackerOutputFactory.position_2d(x, y, confidence)

    @staticmethod
    def position_3d(
        x: float = 0.0,
        y: float = 0.0,
        z: float = 10.0,
        confidence: float = 0.9
    ) -> TrackerOutput:
        """
        Create a 3D position tracker output.

        Args:
            x, y: Normalized 2D position
            z: Distance/depth
            confidence: Tracking confidence

        Returns:
            TrackerOutput with POSITION_3D data type
        """
        return TrackerOutput(
            data_type=TrackerDataType.POSITION_3D,
            timestamp=time.time(),
            tracking_active=True,
            tracker_id="test_tracker",
            position_2d=(x, y),  # Required for POSITION_3D
            position_3d=(x, y, z),
            confidence=confidence
        )

    @staticmethod
    def gimbal_angles(
        yaw: float = 0.0,
        pitch: float = 0.0,
        roll: float = 0.0,
        confidence: float = 0.9
    ) -> TrackerOutput:
        """
        Create a gimbal angles tracker output.

        Args:
            yaw: Gimbal yaw angle (degrees)
            pitch: Gimbal pitch angle (degrees)
            roll: Gimbal roll angle (degrees)
            confidence: Tracking confidence

        Returns:
            TrackerOutput with GIMBAL_ANGLES data type
        """
        return TrackerOutput(
            data_type=TrackerDataType.GIMBAL_ANGLES,
            timestamp=time.time(),
            tracking_active=True,
            tracker_id="test_tracker",
            position_2d=(0.0, 0.0),  # Required for schema validation
            angular=(yaw, pitch, roll),
            confidence=confidence
        )

    @staticmethod
    def velocity_aware(
        x: float = 0.0,
        y: float = 0.0,
        vx: float = 0.0,
        vy: float = 0.0,
        confidence: float = 0.9
    ) -> TrackerOutput:
        """
        Create a velocity-aware tracker output.

        Args:
            x, y: Normalized position
            vx, vy: Velocity estimates
            confidence: Tracking confidence

        Returns:
            TrackerOutput with VELOCITY_AWARE data type
        """
        return TrackerOutput(
            data_type=TrackerDataType.VELOCITY_AWARE,
            timestamp=time.time(),
            tracking_active=True,
            tracker_id="test_tracker",
            position_2d=(x, y),
            velocity=(vx, vy),
            confidence=confidence
        )

    @staticmethod
    def with_bbox(
        x: float = 0.0,
        y: float = 0.0,
        bbox: Tuple[int, int, int, int] = (100, 100, 50, 50),
        confidence: float = 0.9
    ) -> TrackerOutput:
        """
        Create tracker output with bounding box.

        Args:
            x, y: Normalized center position
            bbox: Bounding box (x, y, width, height) in pixels
            confidence: Tracking confidence

        Returns:
            TrackerOutput with bbox data
        """
        return TrackerOutput(
            data_type=TrackerDataType.BBOX_CONFIDENCE,
            timestamp=time.time(),
            tracking_active=True,
            tracker_id="test_tracker",
            position_2d=(x, y),
            bbox=bbox,
            confidence=confidence
        )

    @staticmethod
    def sequence(
        positions: list,
        start_time: Optional[float] = None,
        dt: float = 0.05
    ) -> list:
        """
        Create a sequence of tracker outputs for time-series testing.

        Args:
            positions: List of (x, y) tuples
            start_time: Starting timestamp (default: now)
            dt: Time delta between samples

        Returns:
            List of TrackerOutput instances
        """
        if start_time is None:
            start_time = time.time()

        outputs = []
        for i, (x, y) in enumerate(positions):
            output = TrackerOutput(
                data_type=TrackerDataType.POSITION_2D,
                timestamp=start_time + i * dt,
                tracking_active=True,
                tracker_id="test_tracker",
                position_2d=(x, y),
                confidence=0.9
            )
            outputs.append(output)

        return outputs

    @staticmethod
    def invalid_coordinates() -> TrackerOutput:
        """
        Create tracker output with invalid (out of range) coordinates.
        Used for testing target loss detection.
        """
        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            tracker_id="test_tracker",
            position_2d=(999.0, 999.0),  # Invalid coordinates
            confidence=0.1
        )
