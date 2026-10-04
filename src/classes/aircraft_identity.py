"""Observed aircraft identity; configured routes are never identity evidence."""

from __future__ import annotations

import time


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
        self.reason = "telemetry_identity_unknown"

    def invalidate(self, reason):
        if self._available or self.uid is not None:
            self.generation += 1
        self.uid = None
        self._counter = None
        self._last_advance = None
        self._available = False
        self._boot_ms = None
        self.reason = reason

    def observe(self, payload, now=None):
        now = time.monotonic() if now is None else now
        try:
            vehicles = payload["vehicles"]
            messages = vehicles[str(self.system_id)]["components"][str(self.component_id)]["messages"]
            heartbeat = messages["HEARTBEAT"]
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

        changed = uid != self.uid
        reset = self._counter is not None and counter < self._counter
        rebooted = self._boot_ms is not None and boot_ms is not None and boot_ms < self._boot_ms
        expired = self._last_advance is not None and now - self._last_advance > self.stale_timeout_s
        if changed or reset or expired or rebooted:
            self.generation += 1
            self._last_advance = None
        elif self._counter is not None and counter > self._counter:
            self._last_advance = now
        self.uid = uid
        self._counter = counter
        self._boot_ms = boot_ms
        self._available = True
        self.reason = "telemetry_heartbeat_unconfirmed"

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
