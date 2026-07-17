# src/classes/gimbal_types.py

"""Normalized gimbal data types shared by providers and trackers."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple


class CoordinateSystem(Enum):
    """Normalized gimbal coordinate system modes."""

    GIMBAL_BODY = "gimbal_body"
    SPATIAL_FIXED = "spatial_fixed"


class TrackingState(Enum):
    """Normalized external gimbal tracking states."""

    DISABLED = 0
    TARGET_SELECTION = 1
    TRACKING_ACTIVE = 2
    TARGET_LOST = 3


@dataclass
class GimbalAngles:
    """Normalized gimbal yaw/pitch/roll angles in degrees."""

    yaw: float
    pitch: float
    roll: float
    coordinate_system: CoordinateSystem
    timestamp: datetime

    def is_valid(self) -> bool:
        """Check if angles are within conservative normalized ranges."""
        return (
            -180.0 <= self.yaw <= 180.0 and
            -180.0 <= self.pitch <= 180.0 and
            -180.0 <= self.roll <= 180.0
        )

    def to_tuple(self) -> Tuple[float, float, float]:
        """Return angles as `(yaw, pitch, roll)`."""
        return (self.yaw, self.pitch, self.roll)


@dataclass
class TrackingStatus:
    """Normalized tracking status from an external gimbal provider."""

    state: TrackingState
    target_x: Optional[int] = None
    target_y: Optional[int] = None
    target_width: Optional[int] = None
    target_height: Optional[int] = None
    timestamp: Optional[datetime] = None

    def is_tracking_active(self) -> bool:
        """Return True only when target tracking is active."""
        return self.state == TrackingState.TRACKING_ACTIVE


@dataclass
class GimbalData:
    """Normalized gimbal data package returned by providers."""

    angles: Optional[GimbalAngles] = None
    tracking_status: Optional[TrackingStatus] = None
    coordinate_system: Optional[CoordinateSystem] = None
    timestamp: Optional[datetime] = None
    raw_packet: str = ""

    def is_tracking_active(self) -> bool:
        """Return True only when the provider reports active tracking."""
        return bool(
            self.tracking_status and
            self.tracking_status.is_tracking_active()
        )
