# src/classes/gimbal_types.py

"""Normalized gimbal data types shared by providers and trackers."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

from classes.aircraft_state import finite_number
from classes.capture_timing import SourceSampleStamp


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
    UNSUPPORTED = 4


@dataclass(frozen=True)
class CameraObservationSource:
    """CameraRuntime ownership, independently of the video source epoch."""

    camera_id: str
    source_generation: int

    def __post_init__(self):
        if not isinstance(self.camera_id, str) or not self.camera_id or self.camera_id.strip() != self.camera_id:
            raise ValueError('camera_observation_source_invalid')
        if type(self.source_generation) is not int or self.source_generation < 0:
            raise ValueError('camera_observation_source_generation_invalid')


@dataclass(frozen=True)
class GimbalAngleObservation:
    """Received boresight angles and independent status, without exposure time.

    target_generation is the local App selection generation, never a physical
    target ID. Missing standalone ownership/target authority remains None.
    """

    source: CameraObservationSource | None
    target_generation: int | None
    provider_id: str
    geometry_revision: str
    angles_deg: tuple[float, float, float]
    coordinate_system: str
    angle_receipt_sequence: int
    angle_received_at_monotonic_s: float
    tracking_state: str | None
    tracking_received_at_monotonic_s: float | None
    source_sample: SourceSampleStamp | None = None
    time_basis: str = field(default='backend_receipt', init=False)
    bearing_semantics: str = field(default='camera_boresight', init=False)
    physical_target_identity_confirmed: bool = field(default=False, init=False)

    def __post_init__(self):
        if self.source_sample is not None and not isinstance(self.source_sample, SourceSampleStamp):
            raise ValueError('gimbal_observation_source_sample_invalid')
        if self.source is not None and not isinstance(self.source, CameraObservationSource):
            raise ValueError('gimbal_observation_source_invalid')
        if self.target_generation is not None and (type(self.target_generation) is not int or self.target_generation < 0):
            raise ValueError('gimbal_observation_target_generation_invalid')
        for value in (self.provider_id, self.geometry_revision):
            if not isinstance(value, str) or not value or value.strip() != value:
                raise ValueError('gimbal_observation_identity_invalid')
        if not isinstance(self.angles_deg, tuple) or len(self.angles_deg) != 3:
            raise ValueError('gimbal_observation_angles_invalid')
        if any(not -180. <= finite_number(value, 'gimbal_angle') <= 180. for value in self.angles_deg):
            raise ValueError('gimbal_observation_angles_invalid')
        if self.coordinate_system != CoordinateSystem.GIMBAL_BODY.value:
            raise ValueError('gimbal_observation_frame_unsupported')
        if type(self.angle_receipt_sequence) is not int or self.angle_receipt_sequence <= 0:
            raise ValueError('gimbal_observation_receipt_sequence_invalid')
        for value in (self.angle_received_at_monotonic_s, self.tracking_received_at_monotonic_s):
            if value is not None and finite_number(value, 'gimbal_receipt') < 0:
                raise ValueError('gimbal_observation_receipt_invalid')
        if self.angle_received_at_monotonic_s is None:
            raise ValueError('gimbal_observation_receipt_missing')
        if ((self.tracking_state is None) != (self.tracking_received_at_monotonic_s is None)
                or self.tracking_state is not None and (not isinstance(self.tracking_state, str)
                                                       or self.tracking_state not in TrackingState.__members__)):
            raise ValueError('gimbal_observation_tracking_status_invalid')

    @classmethod
    def from_dict(cls, payload):
        try:
            if not isinstance(payload, dict) or set(payload) | {'source_sample'} != set(cls.__dataclass_fields__):
                raise ValueError('gimbal_observation_contract_invalid')
            values = dict(payload)
            sample = values.get('source_sample')
            if sample is not None:
                if not isinstance(sample, dict) or set(sample) != set(SourceSampleStamp.__dataclass_fields__):
                    raise ValueError('gimbal_observation_source_sample_invalid')
                values['source_sample'] = SourceSampleStamp(**sample)
            for name, expected in (('time_basis', 'backend_receipt'), ('bearing_semantics', 'camera_boresight'),
                                   ('physical_target_identity_confirmed', False)):
                actual = values.pop(name)
                if type(actual) is not type(expected) or actual != expected:
                    raise ValueError('gimbal_observation_semantics_invalid')
            if values['source'] is not None:
                if not isinstance(values['source'], dict) or set(values['source']) != set(CameraObservationSource.__dataclass_fields__):
                    raise ValueError('gimbal_observation_source_invalid')
                values['source'] = CameraObservationSource(**values['source'])
            if not isinstance(values['angles_deg'], (list, tuple)):
                raise ValueError('gimbal_observation_angles_invalid')
            values['angles_deg'] = tuple(values['angles_deg'])
            return cls(**values)
        except (KeyError, TypeError) as error:
            raise ValueError('gimbal_observation_contract_invalid') from error


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
    angle_sample_monotonic: Optional[float] = None
    angle_sample_sequence: Optional[int] = None
    tracking_sample_monotonic: Optional[float] = None
    source_sample: SourceSampleStamp | None = None

    def is_tracking_active(self) -> bool:
        """Return True only when the provider reports active tracking."""
        return bool(
            self.tracking_status and
            self.tracking_status.is_tracking_active()
        )
