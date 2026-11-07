"""Connection-owned aircraft observations and explicit physical/navigation frames.

These contracts contain observations, not flight commands. Source progress is
required: polling or a new video frame cannot refresh an aircraft measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math
import threading
import time
from typing import Callable


class AirframePhase(str, Enum):
    MULTICOPTER = "multicopter"
    FIXED_WING = "fixed_wing"
    VTOL_TRANSITION = "vtol_transition"
    UNKNOWN = "unknown"


class AircraftKind(str, Enum):
    MULTICOPTER = "multicopter"
    FIXED_WING = "fixed_wing"
    VTOL = "vtol"
    UNKNOWN = "unknown"


class AircraftLayout(str, Enum):
    AUTO = "AUTO"
    MULTICOPTER = "MULTICOPTER"
    FIXED_WING = "FIXED_WING"
    VTOL = "VTOL"
    VTOL_TAILSITTER = "VTOL_TAILSITTER"

    def accepts_kind(self, kind: AircraftKind) -> bool:
        if self is AircraftLayout.AUTO:
            return True
        expected = {AircraftLayout.MULTICOPTER: AircraftKind.MULTICOPTER,
                    AircraftLayout.FIXED_WING: AircraftKind.FIXED_WING,
                    AircraftLayout.VTOL: AircraftKind.VTOL,
                    AircraftLayout.VTOL_TAILSITTER: AircraftKind.VTOL}[self]
        return kind is expected

    def matches(self, state: "AircraftState") -> bool:
        """Verify an installation choice; configuration never declares phase."""
        if self is AircraftLayout.AUTO:
            return True
        if self is AircraftLayout.VTOL_TAILSITTER:
            return state.is_vtol and state.is_tailsitter
        if self is AircraftLayout.VTOL:
            return state.is_vtol and not state.is_tailsitter
        expected = AirframePhase.MULTICOPTER if self is AircraftLayout.MULTICOPTER else AirframePhase.FIXED_WING
        return not state.is_vtol and state.phase is expected


# Standard MAV_TYPE wire identifiers, not follower configuration or flight
# phases. VTOL's current phase must still come from fresh native state.
_MAVLINK_AIRCRAFT_TYPES = (
    (1, "FIXED_WING", AircraftKind.FIXED_WING),
    (2, "QUADROTOR", AircraftKind.MULTICOPTER),
    (3, "COAXIAL", AircraftKind.MULTICOPTER),
    (4, "HELICOPTER", AircraftKind.MULTICOPTER),
    (13, "HEXAROTOR", AircraftKind.MULTICOPTER),
    (14, "OCTOROTOR", AircraftKind.MULTICOPTER),
    (15, "TRICOPTER", AircraftKind.MULTICOPTER),
    (19, "VTOL_TAILSITTER_DUOROTOR", AircraftKind.VTOL),
    (20, "VTOL_TAILSITTER_QUADROTOR", AircraftKind.VTOL),
    (21, "VTOL_TILTROTOR", AircraftKind.VTOL),
    (22, "VTOL_FIXEDROTOR", AircraftKind.VTOL),
    (23, "VTOL_TAILSITTER", AircraftKind.VTOL),
    (24, "VTOL_TILTWING", AircraftKind.VTOL),
    (29, "DODECAROTOR", AircraftKind.MULTICOPTER),
    (35, "DECAROTOR", AircraftKind.MULTICOPTER),
    (43, "GENERIC_MULTIROTOR", AircraftKind.MULTICOPTER),
    (47, "VTOL_GYRODYNE", AircraftKind.VTOL),
)


def aircraft_kind_from_mavlink(value) -> AircraftKind:
    """Classify an observed HEARTBEAT type; unknown types stay unsupported."""
    if isinstance(value, dict):
        value = value.get("type")
    if type(value) is int:
        return next((kind for number, _, kind in _MAVLINK_AIRCRAFT_TYPES if number == value), AircraftKind.UNKNOWN)
    if isinstance(value, str):
        name = value.removeprefix("MAV_TYPE_")
        aliases = {"VTOL_DUOROTOR": "VTOL_TAILSITTER_DUOROTOR", "VTOL_QUADROTOR": "VTOL_TAILSITTER_QUADROTOR"}
        name = aliases.get(name, name)
        return next((kind for _, label, kind in _MAVLINK_AIRCRAFT_TYPES if label == name), AircraftKind.UNKNOWN)
    return AircraftKind.UNKNOWN


def finite_number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}_invalid")
    return float(value)


@dataclass(frozen=True)
class Vector3:
    x: float
    y: float
    z: float

    def __post_init__(self):
        for name in ("x", "y", "z"):
            finite_number(getattr(self, name), f"vector_{name}")

    @property
    def magnitude(self) -> float:
        return math.hypot(self.x, self.y, self.z)

    @property
    def horizontal_magnitude(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> Vector3:
        scale = max(abs(self.x), abs(self.y), abs(self.z))
        if scale <= 1e-12:
            raise ValueError("zero_direction")
        x, y, z = self.x / scale, self.y / scale, self.z / scale
        length = math.hypot(x, y, z)
        return Vector3(x / length, y / length, z / length)


@dataclass(frozen=True)
class Quaternion:
    """Hamilton w,x,y,z rotation from physical aircraft FRD to local NED."""

    w: float
    x: float
    y: float
    z: float

    def __post_init__(self):
        for name in ("w", "x", "y", "z"):
            finite_number(getattr(self, name), f"quaternion_{name}")
        norm = math.hypot(self.w, self.x, self.y, self.z)
        if not math.isclose(norm, 1.0, abs_tol=1e-3):
            raise ValueError("quaternion_not_unit")

    def rotate(self, vector: Vector3) -> Vector3:
        norm = math.hypot(self.w, self.x, self.y, self.z)
        w, x, y, z = (item / norm for item in (self.w, self.x, self.y, self.z))
        tx = 2 * (y * vector.z - z * vector.y)
        ty = 2 * (z * vector.x - x * vector.z)
        tz = 2 * (x * vector.y - y * vector.x)
        return Vector3(vector.x + w * tx + y * tz - z * ty,
                       vector.y + w * ty + z * tx - x * tz,
                       vector.z + w * tz + x * ty - y * tx)

    @property
    def heading_rad(self) -> float:
        forward = self.rotate(Vector3(1.0, 0.0, 0.0))
        if forward.horizontal_magnitude <= 1e-9:
            raise ValueError("physical_body_heading_undefined")
        return math.atan2(forward.y, forward.x)


def ned_to_heading_frame(vector: Vector3, heading_rad: float) -> Vector3:
    """MAV_FRAME_BODY_NED rotates velocity by yaw only; down stays NED down."""
    heading = finite_number(heading_rad, "heading")
    c, s = math.cos(heading), math.sin(heading)
    return Vector3(c * vector.x + s * vector.y, -s * vector.x + c * vector.y, vector.z)


def heading_frame_to_ned(vector: Vector3, heading_rad: float) -> Vector3:
    """Inverse of MAVLink's yaw-only velocity boundary, preserving NED down."""
    heading = finite_number(heading_rad, "heading")
    c, s = math.cos(heading), math.sin(heading)
    return Vector3(c * vector.x - s * vector.y, s * vector.x + c * vector.y, vector.z)


@dataclass(frozen=True)
class AircraftBinding:
    aircraft_uid: str
    connection_generation: str
    telemetry_generation: int

    def __post_init__(self):
        if (not isinstance(self.aircraft_uid, str) or not self.aircraft_uid
                or not isinstance(self.connection_generation, str) or not self.connection_generation):
            raise ValueError("aircraft_binding_missing")
        if type(self.telemetry_generation) is not int or self.telemetry_generation < 0:
            raise ValueError("telemetry_generation_invalid")


@dataclass(frozen=True)
class GuidanceSessionIdentity:
    follow_session_id: str
    binding: AircraftBinding
    guidance_generation: int

    def __post_init__(self):
        if not isinstance(self.follow_session_id, str) or not self.follow_session_id:
            raise ValueError("follow_session_missing")
        if not isinstance(self.binding, AircraftBinding):
            raise ValueError("aircraft_binding_invalid")
        if type(self.guidance_generation) is not int or self.guidance_generation < 0:
            raise ValueError("guidance_generation_invalid")


@dataclass(frozen=True)
class AirspeedObservation:
    """Qualified PX4 CAS/EAS observation; groundspeed is never an airspeed source."""

    source: str
    equivalent_m_s: float | None
    true_m_s: float | None
    observed_at_monotonic_s: float
    valid: bool

    def __post_init__(self):
        if self.source not in {"sensor", "ground_minus_wind", "unavailable"}:
            raise ValueError("airspeed_source_invalid")
        finite_number(self.observed_at_monotonic_s, "airspeed_timestamp")
        for name in ("equivalent_m_s", "true_m_s"):
            value = getattr(self, name)
            if value is not None and finite_number(value, name) < 0:
                raise ValueError("airspeed_negative")
        if type(self.valid) is not bool:
            raise ValueError("airspeed_validity_invalid")
        if self.valid and (self.source == "unavailable" or self.equivalent_m_s is None):
            raise ValueError("airspeed_observation_missing")

    def fresh(self, now: float, timeout_s: float) -> bool:
        return self.valid and 0 <= now - self.observed_at_monotonic_s <= timeout_s


@dataclass(frozen=True)
class FixedWingEnvelope:
    """Aircraft-owned effective values, including native load-dependent minimum."""

    minimum_eas_m_s: float
    trim_eas_m_s: float
    maximum_eas_m_s: float
    climb_rate_m_s: float
    sink_rate_m_s: float
    bank_limit_rad: float
    source: str
    revision: str
    vertical_acceleration_limit_m_s2: float | None = None
    altitude_response_time_s: float | None = None

    def __post_init__(self):
        for name in ("minimum_eas_m_s", "trim_eas_m_s", "maximum_eas_m_s",
                     "climb_rate_m_s", "sink_rate_m_s", "bank_limit_rad"):
            if finite_number(getattr(self, name), name) <= 0:
                raise ValueError(f"{name}_not_positive")
        # Bank-dependent minimum can exceed trim. It must not exceed maximum.
        if not (self.minimum_eas_m_s <= self.maximum_eas_m_s
                and self.trim_eas_m_s <= self.maximum_eas_m_s and self.bank_limit_rad < math.pi / 2):
            raise ValueError("fixed_wing_envelope_inconsistent")
        if not self.source or not self.revision:
            raise ValueError("fixed_wing_envelope_provenance_missing")
        for name in ("vertical_acceleration_limit_m_s2", "altitude_response_time_s"):
            if getattr(self, name) is not None and finite_number(getattr(self, name), name) <= 0:
                raise ValueError("fixed_wing_vertical_response_invalid")


@dataclass(frozen=True)
class AircraftState:
    binding: AircraftBinding
    sequence: int
    source: str
    observed_at_monotonic_s: float
    phase: AirframePhase
    is_vtol: bool
    is_tailsitter: bool
    rescue_active: bool
    attitude_body_to_ned: Quaternion
    velocity_ned_m_s: Vector3
    relative_altitude_m: float
    altitude_amsl_m: float
    navigation_heading_rad: float
    airspeed: AirspeedObservation
    fixed_wing_envelope: FixedWingEnvelope | None = None
    altitude_reference_generation: int = 0

    def __post_init__(self):
        if type(self.sequence) is not int or self.sequence < 0 or not isinstance(self.source, str) or not self.source:
            raise ValueError("aircraft_source_progress_missing")
        for name, kind in (("binding", AircraftBinding), ("attitude_body_to_ned", Quaternion),
                           ("velocity_ned_m_s", Vector3), ("airspeed", AirspeedObservation)):
            if not isinstance(getattr(self, name), kind):
                raise ValueError(f"aircraft_{name}_invalid")
        if self.fixed_wing_envelope is not None and not isinstance(self.fixed_wing_envelope, FixedWingEnvelope):
            raise ValueError("fixed_wing_envelope_invalid")
        if type(self.altitude_reference_generation) is not int or self.altitude_reference_generation < 0:
            raise ValueError("altitude_reference_generation_invalid")
        if not isinstance(self.phase, AirframePhase):
            raise ValueError("aircraft_phase_invalid")
        for name in ("is_vtol", "is_tailsitter", "rescue_active"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name}_invalid")
        if self.is_tailsitter and not self.is_vtol:
            raise ValueError("tailsitter_requires_vtol")
        if self.phase is AirframePhase.VTOL_TRANSITION and not self.is_vtol:
            raise ValueError("transition_requires_vtol")
        for name in ("observed_at_monotonic_s", "relative_altitude_m", "altitude_amsl_m", "navigation_heading_rad"):
            finite_number(getattr(self, name), name)

    def fresh(self, now: float, timeout_s: float) -> bool:
        return 0 <= now - self.observed_at_monotonic_s <= timeout_s

    @classmethod
    def from_payload(cls, payload: dict) -> AircraftState:
        """Decode the native observation contract without refreshing its clock."""
        def fields(value, kind):
            if not isinstance(value, dict) or set(value) != set(kind.__dataclass_fields__):
                raise ValueError("aircraft_observation_contract_invalid")
            return value

        values = dict(fields(payload, cls))
        values["binding"] = AircraftBinding(**fields(values["binding"], AircraftBinding))
        values["attitude_body_to_ned"] = Quaternion(**fields(values["attitude_body_to_ned"], Quaternion))
        values["velocity_ned_m_s"] = Vector3(**fields(values["velocity_ned_m_s"], Vector3))
        values["airspeed"] = AirspeedObservation(**fields(values["airspeed"], AirspeedObservation))
        if values["fixed_wing_envelope"] is not None:
            values["fixed_wing_envelope"] = FixedWingEnvelope(**fields(values["fixed_wing_envelope"], FixedWingEnvelope))
        values["phase"] = AirframePhase(values["phase"])
        return cls(**values)


class AircraftStateOwner:
    """Atomic immutable snapshots bound to the active connection and source epoch."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.RLock()
        self._binding: AircraftBinding | None = None
        self._snapshot: AircraftState | None = None

    def bind(self, binding: AircraftBinding | None) -> None:
        with self._lock:
            if binding != self._binding:
                self._binding = binding
                self._snapshot = None

    def commit(self, state: AircraftState) -> bool:
        with self._lock:
            if state.binding != self._binding:
                return False
            if state.observed_at_monotonic_s > self._clock():
                return False
            previous = self._snapshot
            if previous is not None and (state.sequence <= previous.sequence
                    or state.observed_at_monotonic_s <= previous.observed_at_monotonic_s
                    or state.source != previous.source or state.is_vtol != previous.is_vtol
                    or state.is_tailsitter != previous.is_tailsitter):
                return False
            self._snapshot = state
            return True

    def snapshot(self, *, timeout_s: float) -> AircraftState | None:
        if finite_number(timeout_s, "aircraft_timeout") <= 0:
            raise ValueError("aircraft_timeout_not_positive")
        with self._lock:
            state = self._snapshot
            return state if state is not None and state.fresh(self._clock(), timeout_s) else None

    def selected_airspeed(self, *, timeout_s: float) -> AirspeedObservation | None:
        state = self.snapshot(timeout_s=timeout_s)
        if state is None:
            return None
        return state.airspeed if state.airspeed.fresh(self._clock(), timeout_s) else replace(
            state.airspeed, valid=False,
        )
