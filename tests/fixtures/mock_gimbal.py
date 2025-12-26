# tests/fixtures/mock_gimbal.py
"""
Mock gimbal interface and data objects for testing GimbalTracker.

Provides mock implementations of GimbalInterface, GimbalData, and related
objects for isolated unit testing without requiring actual UDP communication.
"""

import time
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass, field
from enum import Enum, auto


class MockTrackingState(Enum):
    """Mock TrackingState enum matching the real implementation."""
    DISABLED = 0
    TARGET_SELECTION = 1
    TRACKING_ACTIVE = 2
    TARGET_LOST = 3


class MockCoordinateSystem(Enum):
    """Mock CoordinateSystem enum."""
    GIMBAL_BODY = "gimbal_body"
    SPATIAL_FIXED = "spatial_fixed"
    AIRCRAFT_BODY = "aircraft_body"


@dataclass
class MockGimbalAngles:
    """Mock gimbal angles data."""
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    coordinate_system: MockCoordinateSystem = MockCoordinateSystem.GIMBAL_BODY

    def to_tuple(self) -> Tuple[float, float, float]:
        """Get angles as tuple."""
        return (self.yaw, self.pitch, self.roll)

    def is_valid(self) -> bool:
        """Check if angles are within valid ranges."""
        return (
            -180.0 <= self.yaw <= 180.0 and
            -90.0 <= self.pitch <= 90.0 and
            -180.0 <= self.roll <= 180.0
        )


@dataclass
class MockTrackingStatus:
    """Mock tracking status data."""
    state: MockTrackingState = MockTrackingState.DISABLED
    target_id: Optional[int] = None
    confidence: float = 0.0


@dataclass
class MockGimbalData:
    """Mock gimbal data packet."""
    angles: Optional[MockGimbalAngles] = None
    tracking_status: Optional[MockTrackingStatus] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class MockGimbalInterface:
    """
    Mock GimbalInterface for testing GimbalTracker.

    Simulates UDP gimbal communication with configurable responses.
    """

    def __init__(
        self,
        listen_port: int = 9004,
        gimbal_ip: str = "192.168.0.108",
        control_port: int = 9003
    ):
        """
        Initialize mock gimbal interface.

        Args:
            listen_port: UDP listen port
            gimbal_ip: Gimbal IP address
            control_port: UDP control port
        """
        self.listen_port = listen_port
        self.gimbal_ip = gimbal_ip
        self.control_port = control_port

        # State
        self.listening = False
        self._current_data: Optional[MockGimbalData] = None
        self._connection_status = "disconnected"

        # Simulation settings
        self._auto_update = False
        self._update_interval = 0.033  # ~30 Hz
        self._last_update_time = 0.0

        # Statistics
        self._packets_received = 0
        self._packets_dropped = 0
        self._connection_uptime = 0.0
        self._start_time: Optional[float] = None

    def start_listening(self) -> bool:
        """
        Start listening for UDP data.

        Returns:
            True if listening started successfully
        """
        self.listening = True
        self._connection_status = "connected"
        self._start_time = time.time()
        return True

    def stop_listening(self) -> None:
        """Stop listening for UDP data."""
        self.listening = False
        self._connection_status = "disconnected"
        if self._start_time:
            self._connection_uptime = time.time() - self._start_time
        self._start_time = None

    def get_current_data(self) -> Optional[MockGimbalData]:
        """
        Get current gimbal data.

        Returns:
            Current gimbal data or None if no data available
        """
        if not self.listening:
            return None

        # Auto-update simulation
        if self._auto_update:
            current_time = time.time()
            if current_time - self._last_update_time >= self._update_interval:
                self._last_update_time = current_time
                self._packets_received += 1

        return self._current_data

    def get_connection_status(self) -> str:
        """Get connection status string."""
        return self._connection_status

    def get_statistics(self) -> Dict[str, Any]:
        """Get interface statistics."""
        return {
            "listening": self.listening,
            "packets_received": self._packets_received,
            "packets_dropped": self._packets_dropped,
            "connection_status": self._connection_status,
            "connection_uptime": self._connection_uptime,
            "listen_port": self.listen_port,
            "gimbal_ip": self.gimbal_ip
        }

    # Test helper methods

    def set_gimbal_data(self, data: MockGimbalData) -> None:
        """Set current gimbal data for testing."""
        self._current_data = data
        self._packets_received += 1

    def set_angles(
        self,
        yaw: float,
        pitch: float,
        roll: float,
        coordinate_system: MockCoordinateSystem = MockCoordinateSystem.GIMBAL_BODY
    ) -> None:
        """Set gimbal angles for testing."""
        angles = MockGimbalAngles(yaw, pitch, roll, coordinate_system)
        if self._current_data is None:
            self._current_data = MockGimbalData(angles=angles)
        else:
            self._current_data.angles = angles
            self._current_data.timestamp = datetime.now()

    def set_tracking_state(
        self,
        state: MockTrackingState,
        target_id: Optional[int] = None,
        confidence: float = 0.95
    ) -> None:
        """Set tracking state for testing."""
        status = MockTrackingStatus(state, target_id, confidence)
        if self._current_data is None:
            self._current_data = MockGimbalData(tracking_status=status)
        else:
            self._current_data.tracking_status = status
            self._current_data.timestamp = datetime.now()

    def set_connection_status(self, status: str) -> None:
        """Set connection status for testing."""
        self._connection_status = status

    def clear_data(self) -> None:
        """Clear current data."""
        self._current_data = None

    def enable_auto_update(self, interval: float = 0.033) -> None:
        """Enable auto-update simulation."""
        self._auto_update = True
        self._update_interval = interval
        self._last_update_time = time.time()

    def disable_auto_update(self) -> None:
        """Disable auto-update simulation."""
        self._auto_update = False


class MockCoordinateTransformer:
    """Mock coordinate transformer for testing."""

    def __init__(self):
        self._cache_hits = 0
        self._cache_misses = 0

    def gimbal_angles_to_body_vector(
        self,
        yaw: float,
        pitch: float,
        roll: float,
        include_mount_offset: bool = True
    ) -> Tuple[float, float, float]:
        """
        Convert gimbal angles to body-frame vector.

        Returns unit vector pointing in gimbal direction.
        """
        import math
        # Simplified conversion (not physically accurate, just for testing)
        yaw_rad = math.radians(yaw)
        pitch_rad = math.radians(pitch)

        x = math.cos(pitch_rad) * math.sin(yaw_rad)
        y = math.cos(pitch_rad) * math.cos(yaw_rad)
        z = math.sin(pitch_rad)

        return (x, y, z)

    def vector_to_normalized_coords(
        self,
        vector: Tuple[float, float, float],
        frame_type: Any = None
    ) -> Tuple[float, float]:
        """
        Convert body-frame vector to normalized 2D coordinates.

        Returns (x, y) in [-1, 1] range.
        """
        x, y, z = vector
        # Simple projection
        if y <= 0:
            y = 0.001  # Avoid division by zero
        norm_x = x / y
        norm_y = z / y
        return (
            max(-1.0, min(1.0, norm_x)),
            max(-1.0, min(1.0, norm_y))
        )

    def get_cache_info(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses
        }


# Factory functions for creating mock objects

def create_mock_gimbal_interface(
    listen_port: int = 9004,
    gimbal_ip: str = "192.168.0.108"
) -> MockGimbalInterface:
    """Create configured mock gimbal interface."""
    return MockGimbalInterface(listen_port, gimbal_ip)


def create_mock_gimbal_data(
    yaw: float = 0.0,
    pitch: float = 0.0,
    roll: float = 0.0,
    tracking_state: MockTrackingState = MockTrackingState.TRACKING_ACTIVE,
    confidence: float = 0.95
) -> MockGimbalData:
    """
    Create mock gimbal data packet.

    Args:
        yaw: Yaw angle in degrees
        pitch: Pitch angle in degrees
        roll: Roll angle in degrees
        tracking_state: Current tracking state
        confidence: Tracking confidence

    Returns:
        MockGimbalData instance
    """
    return MockGimbalData(
        angles=MockGimbalAngles(yaw, pitch, roll),
        tracking_status=MockTrackingStatus(tracking_state, confidence=confidence),
        timestamp=datetime.now()
    )


def create_tracking_active_data(
    yaw: float = 0.0,
    pitch: float = -10.0,
    roll: float = 0.0
) -> MockGimbalData:
    """Create gimbal data with active tracking state."""
    return create_mock_gimbal_data(
        yaw, pitch, roll,
        MockTrackingState.TRACKING_ACTIVE,
        0.95
    )


def create_target_lost_data(
    yaw: float = 0.0,
    pitch: float = 0.0,
    roll: float = 0.0
) -> MockGimbalData:
    """Create gimbal data with target lost state."""
    return create_mock_gimbal_data(
        yaw, pitch, roll,
        MockTrackingState.TARGET_LOST,
        0.1
    )


def create_disabled_data() -> MockGimbalData:
    """Create gimbal data with disabled tracking state."""
    return MockGimbalData(
        angles=MockGimbalAngles(0.0, 0.0, 0.0),
        tracking_status=MockTrackingStatus(MockTrackingState.DISABLED),
        timestamp=datetime.now()
    )


class GimbalDataSequence:
    """Helper for generating sequences of gimbal data for testing."""

    def __init__(self):
        self.data_points = []

    def add_tracking_active(
        self,
        yaw: float = 0.0,
        pitch: float = -10.0,
        roll: float = 0.0
    ) -> "GimbalDataSequence":
        """Add tracking active data point."""
        self.data_points.append(create_tracking_active_data(yaw, pitch, roll))
        return self

    def add_target_lost(self) -> "GimbalDataSequence":
        """Add target lost data point."""
        self.data_points.append(create_target_lost_data())
        return self

    def add_disabled(self) -> "GimbalDataSequence":
        """Add disabled data point."""
        self.data_points.append(create_disabled_data())
        return self

    def add_sweep(
        self,
        start_yaw: float,
        end_yaw: float,
        steps: int,
        pitch: float = -10.0
    ) -> "GimbalDataSequence":
        """Add yaw sweep sequence."""
        for i in range(steps):
            yaw = start_yaw + (end_yaw - start_yaw) * i / (steps - 1)
            self.data_points.append(create_tracking_active_data(yaw, pitch, 0.0))
        return self

    def get_data(self) -> list:
        """Get all data points."""
        return self.data_points

    def __iter__(self):
        return iter(self.data_points)

    def __len__(self):
        return len(self.data_points)
