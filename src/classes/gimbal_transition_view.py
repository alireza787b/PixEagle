"""Camera-only observation of a verified PX4 tailsitter transition."""

from dataclasses import dataclass
from classes.aircraft_state import (AircraftKind, AirframePhase,
                                    aircraft_is_tailsitter_from_mavlink, airframe_phase_from_mavlink)


def transition_home_enabled(settings):
    enabled = settings.get("HOME_AFTER_TRANSITION", True)
    if type(enabled) is not bool:
        raise ValueError("GimbalTracker.HOME_AFTER_TRANSITION must be boolean")
    return enabled and settings.get("ENABLED") is True and settings.get("CONTROL_ENABLED") is True


@dataclass(frozen=True)
class CameraPhaseSample:
    aircraft: tuple[str, str]
    counter: int
    phase: AirframePhase
    eligible: bool

    @classmethod
    def from_mavlink(cls, payload, identity, decode_arm_status):
        if identity.get("fresh") is not True:
            return None
        try:
            component = payload["vehicles"][str(identity["system_id"])]["components"][str(identity["component_id"])]
            messages = component["messages"]
            heartbeat = messages["HEARTBEAT"]["message"]
            if _enum(heartbeat.get("autopilot"), "MAV_AUTOPILOT_") not in (12, "PX4"):
                return None
            if not aircraft_is_tailsitter_from_mavlink(heartbeat):
                return None
            extended = messages["EXTENDED_SYS_STATE"]
            counter = extended["status"]["time"]["counter"]
            if type(counter) is not int or counter < 0:
                return None
            state = extended["message"]
            phase = airframe_phase_from_mavlink(AircraftKind.VTOL, state.get("vtol_state"))
            base_mode = heartbeat.get("base_mode")
            if isinstance(base_mode, dict):
                base_mode = base_mode.get("bits")
            # Non-active or unknown heartbeat status cannot authorize a move.
            eligible = (_enum(heartbeat.get("system_status"), "MAV_STATE_") in (4, "ACTIVE")
                        and _enum(state.get("landed_state"), "MAV_LANDED_STATE_") in (2, "IN_AIR")
                        and decode_arm_status(base_mode) == "Armed")
            return cls((identity["autopilot_uid"], identity["connection_generation"]), counter, phase, eligible)
        except (KeyError, TypeError, AttributeError):
            return None


def _enum(value, prefix):
    if isinstance(value, dict):
        value = value.get("type")
    if isinstance(value, str):
        return value.removeprefix(prefix)
    return value if type(value) is int else None


class CameraPhaseObserver:
    """Consume each observed transition once using distinct MAVLink receipts."""

    def __init__(self):
        self.sample = None
        self.received_at = 0.
        self.generation = 0
        self._has_baseline = False
        self._transition_seen = False
        self._candidate_at = None

    def reset(self):
        self.sample = None
        self.generation += 1
        self._has_baseline = False
        self.cancel_episode()

    def cancel_episode(self):
        self._transition_seen = False
        self._candidate_at = None

    def update(self, sample, now, settlement_s, stale_s):
        if sample is None or not sample.eligible or sample.phase is AirframePhase.UNKNOWN:
            if self.sample is not None:
                self.reset()
            return None
        previous = self.sample
        if previous and (sample.aircraft != previous.aircraft or sample.counter < previous.counter
                         or now - self.received_at > stale_s):
            self.reset()
            previous = None
        if previous and sample.counter == previous.counter:
            if sample != previous:
                self.reset()
            return None
        self.sample, self.received_at = sample, now
        if sample.phase is AirframePhase.VTOL_TRANSITION:
            if previous and previous.phase is not AirframePhase.VTOL_TRANSITION:
                self.generation += 1
                self._transition_seen = self._has_baseline
            self._candidate_at = None
            return None
        self._has_baseline = True
        if not self._transition_seen:
            return None
        if self._candidate_at is None or sample.phase is not previous.phase:
            self._candidate_at = now
            return None
        if now - self._candidate_at >= settlement_s:
            self.cancel_episode()
            return sample.phase
        return None

    def matches(self, generation, phase, now, stale_s):
        return (self.sample is not None and self.generation == generation
                and self.sample.phase is phase and 0 <= now - self.received_at <= stale_s)
