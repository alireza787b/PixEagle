"""Local follower command preview primitives.

The preview path deliberately has no PX4, MAVSDK, or network dependency.  It
uses the same follower implementations and schema-aware setpoint handler as a
live session, then records the resulting ``CommandIntent`` objects locally.
This is a diagnostic contract, not autonomous following and not a simulator.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict
import logging
import time
from typing import Any, Deque, Dict, Optional

from classes.command_intent import CommandIntent

logger = logging.getLogger(__name__)

PX4_EXECUTION_MODE = "PX4"
COMMAND_PREVIEW_EXECUTION_MODE = "COMMAND_PREVIEW"
SUPPORTED_FOLLOWER_EXECUTION_MODES = frozenset(
    {PX4_EXECUTION_MODE, COMMAND_PREVIEW_EXECUTION_MODE}
)


def normalize_follower_execution_mode(value: Any) -> str:
    """Normalize an execution-mode value, failing closed to the PX4 contract."""
    normalized = str(value or PX4_EXECUTION_MODE).strip().upper()
    if normalized not in SUPPORTED_FOLLOWER_EXECUTION_MODES:
        logger.warning(
            "Unknown Follower.FOLLOWER_EXECUTION_MODE=%r; using PX4 mode",
            value,
        )
        return PX4_EXECUTION_MODE
    return normalized


class CommandPreviewController:
    """Read-only vehicle-state adapter used by followers during command preview.

    The adapter intentionally exposes only deterministic telemetry values and
    explicit no-op safety actions.  It has no PX4 connection or command sender.
    """

    def __init__(
        self,
        *,
        altitude_m: float = 50.0,
        ground_speed_m_s: float = 1.0,
        airspeed_m_s: float = 12.0,
    ) -> None:
        self.setpoint_handler = None
        self.current_yaw = 0.0
        self.current_pitch = 0.0
        self.current_roll = 0.0
        self.current_altitude = float(altitude_m)
        self.current_ground_speed = float(ground_speed_m_s)
        self.current_airspeed = float(airspeed_m_s)
        self.attitude_timestamp = time.time()
        self.active_mode = False
        self.preview_events: Deque[Dict[str, Any]] = deque(maxlen=100)

    def get_orientation(self):
        """Return deterministic yaw/pitch/roll telemetry for follower math."""
        return self.current_yaw, self.current_pitch, self.current_roll

    def get_ground_speed(self) -> float:
        return self.current_ground_speed

    def get_connection_status(self) -> Dict[str, Any]:
        """Expose a clearly local status without implying vehicle connectivity."""
        return {
            "connected": False,
            "connection_state": "command_preview",
            "source": "command_preview",
            "commands_sent_to_px4": False,
        }

    def _record_preview_event(self, event: str, **details: Any) -> None:
        self.preview_events.append(
            {"event": event, "timestamp": time.time(), **details}
        )
        logger.info("Command preview event: %s", event)

    def send_return_to_launch_command(self) -> bool:
        """Record an RTL request without dispatching it anywhere."""
        self._record_preview_event("return_to_launch_preview")
        return False

    async def trigger_return_to_launch(self) -> Dict[str, Any]:
        """Record an async RTL request without dispatching it anywhere."""
        self._record_preview_event("return_to_launch_preview")
        return {
            "status": "preview_only",
            "executed": False,
            "commands_sent_to_px4": False,
            "reason": "command_preview_has_no_vehicle_command_path",
        }

    async def send_commands_unified(self) -> bool:
        """Defensive tripwire: preview must never be used as a command sender."""
        raise RuntimeError(
            "CommandPreviewController has no PX4/MAVSDK command path"
        )


class CommandPreviewCommander:
    """Capture validated follower intents without publishing vehicle commands."""

    STATUS_HISTORY_LIMIT = 10

    def __init__(self, setpoint_handler, *, max_history: int = 200) -> None:
        self.setpoint_handler = setpoint_handler
        self._max_history = max(1, int(max_history))
        self._intent_history: Deque[CommandIntent] = deque(
            maxlen=self._max_history
        )
        self._last_intent: Optional[CommandIntent] = None
        self._failsafe_defaults_active = False
        self.running = False
        self.accepted_intents = 0
        self.rejected_intents = 0
        self.failsafe_events = 0
        self.last_error: Optional[str] = None
        self.last_event: Optional[str] = None

    def validate_configuration(self) -> bool:
        """Validate the same schema-aware handler boundary used by live mode."""
        if self.setpoint_handler is None:
            self.last_error = "Setpoint handler is not configured"
            return False
        for method_name in (
            "get_control_type",
            "get_fields",
            "set_fields",
            "reset_setpoints",
        ):
            if not hasattr(self.setpoint_handler, method_name):
                self.last_error = f"Setpoint handler missing {method_name}()"
                return False
        return True

    async def start(self) -> bool:
        """Arm local intent capture; no background publisher is created."""
        if self.running:
            return True
        if not self.validate_configuration():
            logger.error("Command preview configuration invalid: %s", self.last_error)
            return False
        self.running = True
        self._failsafe_defaults_active = False
        self.last_error = None
        self.last_event = "started"
        logger.info("Command preview started; PX4/MAVSDK publication disabled")
        return True

    async def stop(self, *, publish_final: bool = True) -> bool:
        """Stop local capture and optionally restore schema fallback setpoints."""
        if publish_final and self.setpoint_handler is not None:
            self.activate_failsafe_defaults("operator_stop")
        self.running = False
        self.last_event = "stopped"
        logger.info("Command preview stopped")
        return True

    def submit_intent(self, intent: CommandIntent) -> bool:
        """Validate and retain one atomic follower intent."""
        if not self.running:
            self.rejected_intents += 1
            self.last_error = "Command preview is not running"
            return False
        if not isinstance(intent, CommandIntent):
            self.rejected_intents += 1
            self.last_error = f"Expected CommandIntent, got {type(intent)}"
            return False

        expected_control_type = self.setpoint_handler.get_control_type()
        expected_profile = getattr(self.setpoint_handler, "profile_name", None)
        if expected_profile and intent.profile_name != expected_profile:
            self.rejected_intents += 1
            self.last_error = (
                f"Intent profile {intent.profile_name!r} does not match active "
                f"setpoint handler {expected_profile!r}"
            )
            return False
        if intent.control_type != expected_control_type:
            self.rejected_intents += 1
            self.last_error = (
                f"Intent control type {intent.control_type!r} does not match "
                f"active setpoint handler {expected_control_type!r}"
            )
            return False

        expected_fields = set(self.setpoint_handler.get_fields().keys())
        if set(intent.fields.keys()) != expected_fields:
            self.rejected_intents += 1
            self.last_error = (
                f"Intent fields {sorted(intent.fields)} do not match active "
                f"profile fields {sorted(expected_fields)}"
            )
            return False

        try:
            applied_intent = self.setpoint_handler.set_fields(
                intent.fields,
                source=intent.source,
                reason=intent.reason,
            )
        except Exception as exc:
            self.rejected_intents += 1
            self.last_error = f"Failed to apply command intent atomically: {exc}"
            logger.error("Command preview rejected intent: %s", self.last_error)
            return False

        retained = CommandIntent(
            profile_name=applied_intent.profile_name,
            control_type=applied_intent.control_type,
            fields=applied_intent.fields.copy(),
            source=intent.source,
            reason=intent.reason,
            created_at_monotonic_s=intent.created_at_monotonic_s,
            created_at_utc=intent.created_at_utc,
        )
        self._last_intent = retained
        self._intent_history.append(retained)
        self.accepted_intents += 1
        self._failsafe_defaults_active = False
        self.last_error = None
        self.last_event = "intent_accepted"
        return True

    def activate_failsafe_defaults(self, reason: str) -> None:
        """Clear the publishable intent and restore schema fallback values."""
        self._last_intent = None
        if self.setpoint_handler is not None:
            self.setpoint_handler.reset_setpoints()
        self._failsafe_defaults_active = True
        self.failsafe_events += 1
        self.last_event = str(reason)

    def get_status(self) -> Dict[str, Any]:
        """Return bounded, explicit preview diagnostics for API/UI consumers."""
        return {
            "exists": True,
            "running": self.running,
            "task_active": self.running,
            "health_state": "running" if self.running else "stopped",
            "last_intent_fresh": self._last_intent is not None,
            "failsafe_defaults_active": self._failsafe_defaults_active,
            "successful_publishes": None,
            "failed_publishes": None,
            "consecutive_failures": 0,
            "rejected_intents": self.rejected_intents,
            "accepted_intents": self.accepted_intents,
            "preview_intent_count": len(self._intent_history),
            "failsafe_events": self.failsafe_events,
            "last_error": self.last_error,
            "last_event": self.last_event,
            "failure_policy_triggered": False,
            "failure_action": "stop_preview",
            "sends_mavsdk_commands": False,
            "commands_sent_to_px4": False,
            "command_publication_source": "command_preview",
            "execution_mode": COMMAND_PREVIEW_EXECUTION_MODE,
            "last_preview_intent": (
                asdict(self._last_intent) if self._last_intent is not None else None
            ),
            "recent_preview_intents": [
                asdict(intent)
                for intent in list(self._intent_history)[-self.STATUS_HISTORY_LIMIT :]
            ],
        }


__all__ = [
    "COMMAND_PREVIEW_EXECUTION_MODE",
    "CommandPreviewCommander",
    "CommandPreviewController",
    "PX4_EXECUTION_MODE",
    "SUPPORTED_FOLLOWER_EXECUTION_MODES",
    "normalize_follower_execution_mode",
]
