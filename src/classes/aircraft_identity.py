"""Observed aircraft identity; configured routes are never identity evidence."""

from __future__ import annotations

import time
from copy import deepcopy
from classes.aircraft_state import (
    AircraftKind, AirframePhase, aircraft_kind_from_mavlink, airframe_phase_from_mavlink,
)


def canonical_uid(value):
    """Keep MAVLink uint64 identifiers lossless; zero means unavailable."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    if isinstance(value, str) and (not value.isascii() or not value.isdecimal()):
        return None
    number = int(value)
    return str(number) if 0 < number <= 2**64 - 1 else None


class TelemetryAircraftIdentity:
    """Track a selected autopilot's identity and advancing heartbeat evidence.

    Repeated successful HTTP reads of cached MAVLink2REST data do not prove a
    live aircraft. Freshness begins only after its heartbeat counter advances.
    The caller serializes access using MavlinkDataManager's existing lock.
    """

    def __init__(self, system_id, component_id, stale_timeout_s):
        self.system_id = system_id
        self.component_id = component_id
        self.stale_timeout_s = stale_timeout_s
        self.generation = 0
        self.uid = None
        self._counter = None
        self._last_advance = None
        self._available = False
        self._boot_ms = None
        self._heartbeat_message = None
        self._mode_revision = 0
        self.reason = "telemetry_identity_unknown"
        self.aircraft_kind = AircraftKind.UNKNOWN
        self._phase = AirframePhase.UNKNOWN
        self._phase_counter = None
        self._phase_last_advance = None
        self._phase_identity_generation = None
        self._phase_generation = 0

    def invalidate(self, reason):
        if self._available or self.uid is not None:
            self.generation += 1
        self.uid = None
        self._counter = None
        self._last_advance = None
        self._available = False
        self._boot_ms = None
        self._heartbeat_message = None
        self.reason = reason
        self.aircraft_kind = AircraftKind.UNKNOWN
        self._reset_phase()

    def _reset_phase(self):
        if self._phase is not AirframePhase.UNKNOWN or self._phase_counter is not None:
            self._phase_generation += 1
        self._phase = AirframePhase.UNKNOWN
        self._phase_counter = None
        self._phase_last_advance = None
        self._phase_identity_generation = None

    def _invalidate_phase_sample(self):
        if self._phase is not AirframePhase.UNKNOWN or self._phase_last_advance is not None:
            self._phase_generation += 1
        self._phase = AirframePhase.UNKNOWN
        self._phase_last_advance = None

    def _observe_phase(self, messages, now):
        if self._phase_identity_generation != self.generation:
            self._reset_phase()
            self._phase_identity_generation = self.generation
        if self.aircraft_kind in (AircraftKind.MULTICOPTER, AircraftKind.FIXED_WING):
            self._phase = airframe_phase_from_mavlink(self.aircraft_kind)
            self._phase_counter = self._counter
            self._phase_last_advance = self._last_advance
            return
        packet = messages.get("EXTENDED_SYS_STATE")
        try:
            phase = airframe_phase_from_mavlink(self.aircraft_kind, packet["message"]["vtol_state"])
            counter = packet["status"]["time"]["counter"]
            if phase is AirframePhase.UNKNOWN or type(counter) is not int or counter < 0:
                raise ValueError("phase source unavailable")
        except (KeyError, TypeError, ValueError):
            self._invalidate_phase_sample()
            return
        progressed = self._phase_counter is not None and counter > self._phase_counter
        reset = self._phase_counter is not None and counter < self._phase_counter
        if reset:
            # Keep the watermark: a delayed reply cannot become a new source epoch.
            self._invalidate_phase_sample()
            return
        changed = phase is not self._phase
        if changed:
            self._phase_generation += 1
        if progressed:
            self._phase_last_advance = now
        elif changed:
            self._phase_last_advance = None
        self._phase, self._phase_counter = phase, counter

    def observe(self, payload, now=None):
        now = time.monotonic() if now is None else now
        try:
            vehicles = payload["vehicles"]
            messages = vehicles[str(self.system_id)]["components"][str(self.component_id)]["messages"]
            heartbeat = messages["HEARTBEAT"]
            kind = aircraft_kind_from_mavlink(heartbeat["message"])
            autopilot = heartbeat["message"]["autopilot"]
            if isinstance(autopilot, dict):
                autopilot = autopilot.get("type")
            if autopilot not in (3, 12, "MAV_AUTOPILOT_ARDUPILOTMEGA", "MAV_AUTOPILOT_PX4"):
                raise ValueError("selected component is not an observed PX4/ArduPilot autopilot")
            uid = canonical_uid(messages["AUTOPILOT_VERSION"]["message"].get("uid"))
            counter = heartbeat["status"]["time"]["counter"]
            boot_ms = messages.get("SYSTEM_TIME", messages.get("ATTITUDE", {})).get(
                "message", {}).get("time_boot_ms")
            if type(boot_ms) is not int or boot_ms < 0:
                boot_ms = None
            if uid is None or type(counter) is not int or counter < 0:
                raise ValueError("missing identity or heartbeat counter")
            # The same observed UID on another route is ambiguous, even if one
            # route was configured. Never silently choose among duplicates.
            for sysid, vehicle in vehicles.items():
                for compid, component in vehicle.get("components", {}).items():
                    other_uid = canonical_uid(component.get("messages", {}).get(
                        "AUTOPILOT_VERSION", {}).get("message", {}).get("uid"))
                    if other_uid == uid and (str(sysid), str(compid)) != (
                        str(self.system_id), str(self.component_id)
                    ):
                        self.invalidate("telemetry_identity_ambiguous")
                        return
        except (KeyError, TypeError, AttributeError, ValueError):
            self.invalidate("telemetry_identity_unknown")
            return

        changed = uid != self.uid or (self.aircraft_kind is not AircraftKind.UNKNOWN
                                     and kind is not AircraftKind.UNKNOWN and self.aircraft_kind is not kind)
        reset = self._counter is not None and counter < self._counter
        rebooted = self._boot_ms is not None and boot_ms is not None and boot_ms < self._boot_ms
        expired = self._last_advance is not None and now - self._last_advance > self.stale_timeout_s
        progressed = self._counter is not None and counter > self._counter
        if (self._counter is not None and counter == self._counter and self._heartbeat_message is not None
                and heartbeat["message"] != self._heartbeat_message):
            self.invalidate("telemetry_heartbeat_rewritten")
            return
        renewed_progress = (expired and progressed and kind is self.aircraft_kind
                            and not (changed or reset or rebooted))
        if changed or reset or expired or rebooted:
            self.generation += 1
            self._last_advance = now if renewed_progress else None
        elif progressed:
            self._last_advance = now
        self.uid = uid
        self._counter = counter
        self._boot_ms = boot_ms
        if (self._heartbeat_message is not None
                and heartbeat["message"].get("custom_mode") != self._heartbeat_message.get("custom_mode")):
            self._mode_revision += 1
        self._heartbeat_message = deepcopy(heartbeat["message"])
        self._available = True
        self.aircraft_kind = kind
        self.reason = "telemetry_heartbeat_unconfirmed"
        self._observe_phase(messages, now)

    @property
    def heartbeat_observed_at_monotonic_s(self):
        return self._last_advance

    @property
    def mode_revision(self):
        return self._mode_revision

    def phase_snapshot(self, *, connected, now=None):
        """Read-only phase evidence; a heartbeat cannot refresh cached VTOL state.

        Phase generation changes on observed transitions and source resets.
        It is distinct from connection identity and grants no command ownership.
        """
        now = time.monotonic() if now is None else now
        identity = self.snapshot(connected=connected, now=now)
        age = None if self._phase_last_advance is None else now - self._phase_last_advance
        fresh = bool(identity["fresh"] and self._phase is not AirframePhase.UNKNOWN
                     and age is not None and 0 <= age <= self.stale_timeout_s)
        reason = (None if fresh else identity["reason"] if not identity["fresh"] else
                  "aircraft_phase_unavailable" if self._phase is AirframePhase.UNKNOWN else
                  "aircraft_phase_unconfirmed" if age is None else "aircraft_phase_stale")
        return {
            "phase": self._phase.value if fresh else AirframePhase.UNKNOWN.value,
            "fresh": fresh, "reason": reason,
            "source": "EXTENDED_SYS_STATE" if self.aircraft_kind is AircraftKind.VTOL else "HEARTBEAT",
            "source_counter": self._phase_counter,
            "source_observed_at_monotonic_s": self._phase_last_advance,
            "source_age_s": age, "generation": self._phase_generation,
            "connection_generation": identity["connection_generation"],
            "autopilot_uid": identity["autopilot_uid"],
        }

    def snapshot(self, *, connected, now=None):
        now = time.monotonic() if now is None else now
        fresh = bool(connected and self._available and self._last_advance is not None
                     and now - self._last_advance <= self.stale_timeout_s)
        reason = None if fresh else (
            "telemetry_disconnected" if not connected else
            "telemetry_stale" if self._last_advance is not None else self.reason
        )
        return {
            "source": "mavlink2rest", "connected": bool(connected), "fresh": fresh,
            "connection_generation": str(self.generation),
            "system_id": self.system_id if self._available else None,
            "component_id": self.component_id if self._available else None,
            "autopilot_uid": self.uid, "hardware_uid": None,
            "reason": reason,
        }
