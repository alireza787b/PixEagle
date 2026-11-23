"""Standard-MAVLink observations under the existing telemetry/identity owner.

No polling, parameter writer or command authority lives here. Packet receipts
are local freshness evidence, never invented estimator sample times or resets.
"""

from copy import deepcopy
from dataclasses import dataclass
import math

from classes.aircraft_state import (
    AircraftBinding, AircraftKind, AircraftState, AirframePhase, AirspeedObservation,
    Quaternion, Vector3, aircraft_is_tailsitter_from_mavlink, finite_number, fixed_wing_control_attitude,
)


def mode_observed_after_request(flight, *, source_epoch, expected_mode, requested_at):
    """A mode value cached before dispatch cannot confirm the new acquisition."""
    observed = flight.get("flight_mode_observed_at_monotonic_s")
    return (flight.get("fresh") is True
            and (flight.get("autopilot_uid"), flight.get("connection_generation")) == source_epoch
            and type(flight.get("flight_mode")) is int and flight["flight_mode"] == expected_mode
            and type(observed) in (int, float) and math.isfinite(observed)
            and observed >= finite_number(requested_at, "mode_request_clock"))


@dataclass(frozen=True)
class MavlinkSample:
    counter: int
    marker: int | None
    received_at: float
    message: dict


@dataclass(frozen=True)
class MavlinkGuidanceObservation:
    """One serialized read of pose, selected route and observed flight mode."""

    state: AircraftState
    source_epoch: tuple[str, str]
    system_id: int
    component_id: int
    armed: bool | None
    flight_mode: int | None
    mode_observed_at_monotonic_s: float | None
    local_position_ned: Vector3 | None
    phase_generation: int = 0
    mode_generation: int = 0


class MavlinkMessageProgress:
    """Keep high watermarks when cached, rewritten or reordered reads arrive."""

    def __init__(self, *, time_field=None):
        self.time_field = time_field
        self.counter = self.marker = self.sample = None
        self._message = None

    def observe(self, packet, now):
        finite_number(now, "mavlink_receipt")
        try:
            message = packet["message"]
            counter = packet["status"]["time"]["counter"]
            marker = None if self.time_field is None else message[self.time_field]
            if (not isinstance(message, dict) or type(counter) is not int or counter < 0
                    or (self.time_field is not None and (type(marker) is not int or marker < 0))):
                raise ValueError("mavlink_source_progress_invalid")
        except (KeyError, TypeError, ValueError):
            self.sample = None
            return False
        if self.counter is None:
            self.counter, self.marker, self._message = counter, marker, deepcopy(message)
            return False
        if counter < self.counter or (marker is not None and marker < self.marker):
            self.sample = None
            return False
        if counter == self.counter or (marker is not None and marker == self.marker):
            if message != self._message:
                self.sample = None
            self.counter = counter
            return False
        self.counter, self.marker, self._message = counter, marker, deepcopy(message)
        self.sample = MavlinkSample(counter, marker, now, deepcopy(message))
        return True


class AirspeedProgress:
    """Selected VFR_HUD CAS keeps its original advancing packet receipt."""

    def __init__(self):
        self.progress = MavlinkMessageProgress()
        self._observation = AirspeedObservation("unavailable", None, None, 0., False)

    def observe(self, packet, now):
        self.progress.observe(packet, now)
        sample = self.progress.sample
        value = None if sample is None else sample.message.get("airspeed")
        valid = (isinstance(value, (int, float)) and not isinstance(value, bool)
                 and math.isfinite(value) and value >= 0)
        if valid:
            self._observation = AirspeedObservation("sensor", value, None, sample.received_at, True)
        elif self._observation.valid:
            self._observation = AirspeedObservation("unavailable", None, None, now, False)
        return self._observation


class MavlinkAircraftStateSource:
    REQUIRED = ("ATTITUDE_QUATERNION", "LOCAL_POSITION_NED", "GLOBAL_POSITION_INT")

    def __init__(self):
        self.epoch = None
        self._reset()

    def _reset(self):
        self._messages = {name: MavlinkMessageProgress(time_field="time_boot_ms") for name in self.REQUIRED}
        self._airspeed = AirspeedProgress()
        self._speed = AirspeedObservation("unavailable", None, None, 0., False)
        self._sequence = 0
        self._phase_generation = None
        self._kind = AircraftKind.UNKNOWN
        self._tailsitter = False
        self._home_mm = None
        self._altitude_generation = 0

    def invalidate(self):
        self.epoch = None
        self._reset()

    def observe(self, messages, *, identity, phase, kind, now):
        """Called only by the existing serialized aggregate-poll consumer."""
        epoch = (identity.get("autopilot_uid"), identity.get("connection_generation"))
        if (not isinstance(messages, dict) or not all(isinstance(item, str) and item for item in epoch)
                or not isinstance(kind, AircraftKind) or kind is AircraftKind.UNKNOWN):
            self.invalidate()
            return
        heartbeat = messages.get("HEARTBEAT", {}).get("message", {})
        autopilot = heartbeat.get("autopilot") if isinstance(heartbeat, dict) else None
        if isinstance(autopilot, dict):
            autopilot = autopilot.get("type")
        if not (type(autopilot) is int and autopilot == 12 or autopilot == "MAV_AUTOPILOT_PX4"):
            self.invalidate()
            return
        if epoch != self.epoch:
            self._reset()
            self.epoch = epoch
        progressed = False
        for name, progress in self._messages.items():
            progressed = progress.observe(messages.get(name), now) or progressed
        speed = self._airspeed.observe(messages.get("VFR_HUD"), now)
        progressed = progressed or speed != self._speed
        self._speed = speed
        self._kind = kind
        self._tailsitter = aircraft_is_tailsitter_from_mavlink(messages.get("HEARTBEAT", {}).get("message"))
        if progressed or phase.get("generation") != self._phase_generation:
            self._sequence += 1
        self._phase_generation = phase.get("generation")
        global_sample = self._messages["GLOBAL_POSITION_INT"].sample
        if global_sample is not None:
            absolute = global_sample.message.get("alt")
            relative = global_sample.message.get("relative_alt")
            if type(absolute) is int and type(relative) is int:
                home = absolute - relative
                if self._home_mm is None or abs(home - self._home_mm) > 2:
                    self._home_mm = home
                    self._altitude_generation += 1

    def snapshot(self, binding: AircraftBinding, *, source_epoch, identity, phase, now,
                 timeout_s, envelope=None):
        """Bind only fresh observations from the explicitly captured source epoch."""
        if (not isinstance(binding, AircraftBinding) or self.epoch != source_epoch
                or self.epoch is None or binding.aircraft_uid != self.epoch[0]
                or identity.get("fresh") is not True or phase.get("fresh") is not True
                or (identity.get("autopilot_uid"), identity.get("connection_generation")) != self.epoch
                or phase.get("generation") != self._phase_generation):
            return None
        if finite_number(timeout_s, "aircraft_timeout") <= 0:
            raise ValueError("aircraft_timeout_not_positive")
        finite_number(now, "aircraft_clock")
        age = phase.get("source_age_s")
        if isinstance(age, bool) or not isinstance(age, (int, float)) or not math.isfinite(age) or not 0 <= age <= timeout_s:
            return None
        phase_at = phase.get("source_observed_at_monotonic_s")
        if (isinstance(phase_at, bool) or not isinstance(phase_at, (int, float))
                or not math.isfinite(phase_at) or not 0 <= now - phase_at <= timeout_s):
            return None
        samples = [self._messages[name].sample for name in self.REQUIRED]
        if any(sample is None or not 0 <= now - sample.received_at <= timeout_s for sample in samples):
            return None
        try:
            attitude, local, global_position = (sample.message for sample in samples)
            q = Quaternion(*(attitude[name] for name in ("q1", "q2", "q3", "q4")))
            velocity = Vector3(*(local[name] for name in ("vx", "vy", "vz")))
            relative_mm, absolute_mm = global_position["relative_alt"], global_position["alt"]
            if type(relative_mm) is not int or type(absolute_mm) is not int:
                return None
            selected_phase = AirframePhase(phase["phase"])
            heading_q = (fixed_wing_control_attitude(q, is_tailsitter=self._tailsitter)
                         if selected_phase is AirframePhase.FIXED_WING else q)
            return AircraftState(
                binding, self._sequence, "mavlink2rest_source_progress", min(phase_at, *(s.received_at for s in samples)),
                selected_phase, self._kind is AircraftKind.VTOL, self._tailsitter, False, q, velocity,
                relative_mm / 1000., absolute_mm / 1000., heading_q.heading_rad, self._speed, envelope,
                altitude_reference_generation=self._altitude_generation,
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            return None

    def local_position(self):
        """Read only alongside a validated snapshot under the poller's lock."""
        sample = self._messages["LOCAL_POSITION_NED"].sample
        try:
            return Vector3(*(sample.message[name] for name in ("x", "y", "z")))
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
