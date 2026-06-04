"""Async Offboard command publisher for PX4 setpoint heartbeat ownership."""

import asyncio
import logging
import math
import time
from typing import Callable, Optional

from classes.command_intent import CommandIntent
from classes.parameters import Parameters
from classes.setpoint_handler import SetpointHandler

logger = logging.getLogger(__name__)


class OffboardCommander:
    """
    Own fixed-rate Offboard setpoint publication independently of the frame loop.

    Followers produce atomic ``CommandIntent`` snapshots. The commander accepts
    those intents and repeatedly publishes the current setpoint through
    ``PX4InterfaceManager.send_commands_unified()`` until a new intent arrives,
    the intent expires, or the commander is stopped.
    """

    DEFAULT_COMMAND_RATE_HZ = 20.0
    MIN_COMMAND_RATE_HZ = 2.0
    MAX_COMMAND_RATE_HZ = 100.0

    DEFAULT_COMMAND_TTL_S = 0.5
    MIN_COMMAND_TTL_S = 0.1
    MAX_COMMAND_TTL_S = 10.0

    DEFAULT_FAILURE_THRESHOLD = 3
    MIN_FAILURE_THRESHOLD = 1
    MAX_FAILURE_THRESHOLD = 100

    def __init__(
        self,
        px4_interface,
        setpoint_handler: SetpointHandler,
        *,
        command_rate_hz: Optional[float] = None,
        command_ttl_s: Optional[float] = None,
        command_failure_threshold: Optional[int] = None,
        on_failure_threshold: Optional[Callable[[dict], object]] = None,
    ):
        self.px4_interface = px4_interface
        self.setpoint_handler = setpoint_handler
        self.command_rate_hz = self._validate_command_rate_hz(command_rate_hz)
        self.command_period_s = 1.0 / self.command_rate_hz
        self.command_ttl_s = self._validate_command_ttl_s(command_ttl_s)
        self.command_failure_threshold = self._validate_failure_threshold(
            command_failure_threshold
        )
        self._on_failure_threshold = on_failure_threshold

        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._publish_lock = asyncio.Lock()
        self._last_intent: Optional[CommandIntent] = None
        self._failsafe_defaults_active = False
        self._stop_requested_at_monotonic_s: Optional[float] = None

        self.publish_count = 0
        self.successful_publishes = 0
        self.failed_publishes = 0
        self.consecutive_failures = 0
        self.stale_intent_resets = 0
        self.rejected_intents = 0
        self.last_publish_success: Optional[bool] = None
        self.last_publish_reason: Optional[str] = None
        self.last_publish_monotonic_s: Optional[float] = None
        self.last_error: Optional[str] = None
        self.failure_policy_triggered = False
        self.failure_policy_reason: Optional[str] = None
        self.failure_policy_triggered_at_monotonic_s: Optional[float] = None
        self.failure_policy_trigger_count = 0

    @classmethod
    def _validate_command_rate_hz(cls, value: Optional[float]) -> float:
        raw_value = (
            getattr(Parameters, "OFFBOARD_COMMAND_RATE_HZ", cls.DEFAULT_COMMAND_RATE_HZ)
            if value is None
            else value
        )
        try:
            rate_hz = float(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid OFFBOARD_COMMAND_RATE_HZ=%r; using default %.1f Hz",
                raw_value,
                cls.DEFAULT_COMMAND_RATE_HZ,
            )
            return cls.DEFAULT_COMMAND_RATE_HZ

        if not math.isfinite(rate_hz) or rate_hz <= 0.0:
            logger.warning(
                "OFFBOARD_COMMAND_RATE_HZ must be positive finite Hz, got %r; "
                "using default %.1f Hz",
                raw_value,
                cls.DEFAULT_COMMAND_RATE_HZ,
            )
            return cls.DEFAULT_COMMAND_RATE_HZ
        if rate_hz < cls.MIN_COMMAND_RATE_HZ:
            logger.warning(
                "OFFBOARD_COMMAND_RATE_HZ %.3f Hz is below %.3f Hz; clamping",
                rate_hz,
                cls.MIN_COMMAND_RATE_HZ,
            )
            return cls.MIN_COMMAND_RATE_HZ
        if rate_hz > cls.MAX_COMMAND_RATE_HZ:
            logger.warning(
                "OFFBOARD_COMMAND_RATE_HZ %.3f Hz is above %.3f Hz; clamping",
                rate_hz,
                cls.MAX_COMMAND_RATE_HZ,
            )
            return cls.MAX_COMMAND_RATE_HZ
        return rate_hz

    @classmethod
    def _validate_command_ttl_s(cls, value: Optional[float]) -> float:
        raw_value = (
            getattr(Parameters, "OFFBOARD_COMMAND_TTL_S", cls.DEFAULT_COMMAND_TTL_S)
            if value is None
            else value
        )
        try:
            ttl_s = float(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid OFFBOARD_COMMAND_TTL_S=%r; using default %.1f s",
                raw_value,
                cls.DEFAULT_COMMAND_TTL_S,
            )
            return cls.DEFAULT_COMMAND_TTL_S

        if not math.isfinite(ttl_s) or ttl_s <= 0.0:
            logger.warning(
                "OFFBOARD_COMMAND_TTL_S must be positive finite seconds, got %r; "
                "using default %.1f s",
                raw_value,
                cls.DEFAULT_COMMAND_TTL_S,
            )
            return cls.DEFAULT_COMMAND_TTL_S
        if ttl_s < cls.MIN_COMMAND_TTL_S:
            logger.warning(
                "OFFBOARD_COMMAND_TTL_S %.3f s is below %.3f s; clamping",
                ttl_s,
                cls.MIN_COMMAND_TTL_S,
            )
            return cls.MIN_COMMAND_TTL_S
        if ttl_s > cls.MAX_COMMAND_TTL_S:
            logger.warning(
                "OFFBOARD_COMMAND_TTL_S %.3f s is above %.3f s; clamping",
                ttl_s,
                cls.MAX_COMMAND_TTL_S,
            )
            return cls.MAX_COMMAND_TTL_S
        return ttl_s

    @classmethod
    def _validate_failure_threshold(cls, value: Optional[int]) -> int:
        raw_value = (
            getattr(
                Parameters,
                "OFFBOARD_COMMAND_FAILURE_THRESHOLD",
                cls.DEFAULT_FAILURE_THRESHOLD,
            )
            if value is None
            else value
        )
        try:
            threshold = int(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid OFFBOARD_COMMAND_FAILURE_THRESHOLD=%r; using default %d",
                raw_value,
                cls.DEFAULT_FAILURE_THRESHOLD,
            )
            return cls.DEFAULT_FAILURE_THRESHOLD

        if threshold < cls.MIN_FAILURE_THRESHOLD:
            logger.warning(
                "OFFBOARD_COMMAND_FAILURE_THRESHOLD %r is below %d; clamping",
                raw_value,
                cls.MIN_FAILURE_THRESHOLD,
            )
            return cls.MIN_FAILURE_THRESHOLD
        if threshold > cls.MAX_FAILURE_THRESHOLD:
            logger.warning(
                "OFFBOARD_COMMAND_FAILURE_THRESHOLD %r is above %d; clamping",
                raw_value,
                cls.MAX_FAILURE_THRESHOLD,
            )
            return cls.MAX_FAILURE_THRESHOLD
        return threshold

    def validate_configuration(self) -> bool:
        """Return whether the commander has the dependencies needed to publish."""
        if self.px4_interface is None:
            self.last_error = "PX4 interface is not configured"
            logger.error(self.last_error)
            return False
        if not hasattr(self.px4_interface, "send_commands_unified"):
            self.last_error = "PX4 interface missing send_commands_unified()"
            logger.error(self.last_error)
            return False
        if self.setpoint_handler is None:
            self.last_error = "Setpoint handler is not configured"
            logger.error(self.last_error)
            return False
        for method_name in ("get_control_type", "get_fields", "set_fields", "reset_setpoints"):
            if not hasattr(self.setpoint_handler, method_name):
                self.last_error = f"Setpoint handler missing {method_name}()"
                logger.error(self.last_error)
                return False
        return True

    async def start(self) -> bool:
        """Start the async command publication loop."""
        if self.running:
            return True
        if not self.validate_configuration():
            return False

        self.running = True
        self._stop_requested_at_monotonic_s = None
        self.consecutive_failures = 0
        self.failure_policy_triggered = False
        self.failure_policy_reason = None
        self.failure_policy_triggered_at_monotonic_s = None
        self._task = asyncio.create_task(
            self._run(),
            name="PixEagleOffboardCommander",
        )
        logger.info(
            "OffboardCommander started: rate=%.1f Hz ttl=%.3f s failure_threshold=%d",
            self.command_rate_hz,
            self.command_ttl_s,
            self.command_failure_threshold,
        )
        return True

    async def stop(self, *, publish_final: bool = True) -> None:
        """
        Stop the commander loop and optionally publish one final default setpoint.

        The final publish happens before stopping the loop so PX4 receives a
        best-effort zero/hold command while Offboard is still active.
        """
        self._stop_requested_at_monotonic_s = time.monotonic()
        self.running = False
        task = self._task
        if task and task is not asyncio.current_task():
            try:
                await asyncio.wait_for(task, timeout=max(1.0, self.command_period_s * 3.0))
            except asyncio.TimeoutError:
                logger.warning("OffboardCommander task did not stop before timeout; cancelling")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._task = None

        if publish_final:
            await self._publish_once(
                reason="operator_stop",
                enforce_failure_policy=False,
                force_default_reason="operator_stop",
            )
        logger.info("OffboardCommander stopped")

    def submit_intent(self, intent: CommandIntent) -> bool:
        """Accept the latest follower command intent for heartbeat publication."""
        if not isinstance(intent, CommandIntent):
            self.rejected_intents += 1
            self.last_error = f"Expected CommandIntent, got {type(intent)}"
            logger.error(self.last_error)
            return False

        expected_control_type = self.setpoint_handler.get_control_type()
        if intent.control_type != expected_control_type:
            self.rejected_intents += 1
            self.last_error = (
                f"Intent control type {intent.control_type!r} does not match "
                f"active setpoint handler {expected_control_type!r}"
            )
            logger.error(self.last_error)
            return False

        expected_fields = set(self.setpoint_handler.get_fields().keys())
        intent_fields = set(intent.fields.keys())
        if intent_fields != expected_fields:
            self.rejected_intents += 1
            self.last_error = (
                f"Intent fields {sorted(intent_fields)} do not match active "
                f"profile fields {sorted(expected_fields)}"
            )
            logger.error(self.last_error)
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
            logger.error(self.last_error)
            return False

        self._last_intent = CommandIntent(
            profile_name=applied_intent.profile_name,
            control_type=applied_intent.control_type,
            fields=applied_intent.fields.copy(),
            source=intent.source,
            reason=intent.reason,
            created_at_monotonic_s=intent.created_at_monotonic_s,
            created_at_utc=intent.created_at_utc,
        )
        self._failsafe_defaults_active = False
        self.last_error = None
        logger.debug(
            "OffboardCommander accepted intent: source=%s reason=%s control_type=%s",
            intent.source,
            intent.reason,
            intent.control_type,
        )
        return True

    async def publish_once(
        self,
        *,
        reason: str = "manual",
        enforce_failure_policy: bool = True,
    ) -> bool:
        """Publish one setpoint immediately using the active PX4 interface."""
        return await self._publish_once(
            reason=reason,
            enforce_failure_policy=enforce_failure_policy,
        )

    async def inject_publish_failures_for_validation(
        self,
        *,
        failure_count: int,
        reason: str = "sitl_commander_publish_failure",
        invoke_failure_callback: bool = False,
    ) -> dict:
        """
        Record validation-only publish failures without publishing via MAVSDK.

        This is used by operator-gated SITL validation routes to exercise the
        local failure policy deterministically. It does not send a setpoint to
        PX4, replace the PX4 interface, stop services, or mutate MAVLink
        routing. AppController cleanup may still call the normal Offboard stop
        path after the policy trips.
        """
        try:
            count = int(failure_count)
        except (TypeError, ValueError) as exc:
            raise ValueError("failure_count must be an integer") from exc

        if count < 1 or count > self.MAX_FAILURE_THRESHOLD:
            raise ValueError(
                f"failure_count must be between 1 and {self.MAX_FAILURE_THRESHOLD}"
            )

        triggered_now = False
        async with self._publish_lock:
            for _ in range(count):
                self.last_error = reason
                self._record_publish_result(False, reason)
            triggered_now = self._mark_failure_policy_triggered(reason)

        if triggered_now and invoke_failure_callback:
            await self._invoke_failure_threshold_callback()
        status = self.get_status()
        return {
            "applied_failure_count": count,
            "failure_reason": reason,
            "failure_policy_triggered": status.get("failure_policy_triggered"),
            "offboard_commander": status,
        }

    async def _run(self) -> None:
        try:
            while self.running:
                started = time.monotonic()
                await self._publish_once(reason="heartbeat")
                elapsed = time.monotonic() - started
                await asyncio.sleep(max(0.0, self.command_period_s - elapsed))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("Fatal OffboardCommander loop error: %s", exc)
            self.running = False

    async def _publish_once(
        self,
        *,
        reason: str,
        enforce_failure_policy: bool = True,
        force_default_reason: Optional[str] = None,
    ) -> bool:
        async with self._publish_lock:
            if reason == "heartbeat" and not self.running:
                return False

            if not self.validate_configuration():
                self._record_publish_result(False, reason)
                if enforce_failure_policy:
                    await self._maybe_trigger_failure_policy(reason)
                return False

            if force_default_reason is not None:
                self._apply_default_setpoints(force_default_reason)
            elif not self._has_fresh_intent():
                self._apply_default_setpoints("intent_stale_or_missing")

            try:
                success = await self.px4_interface.send_commands_unified()
            except Exception as exc:
                self.last_error = str(exc)
                logger.error("OffboardCommander publish error: %s", exc)
                success = False

            success = bool(success)
            self._record_publish_result(success, reason)
        if not success and enforce_failure_policy:
            await self._maybe_trigger_failure_policy(reason)
        return success

    def _has_fresh_intent(self) -> bool:
        if self._last_intent is None:
            return False
        return (time.monotonic() - self._last_intent.created_at_monotonic_s) <= self.command_ttl_s

    def _apply_default_setpoints(self, reason: str) -> None:
        if not self._failsafe_defaults_active:
            self.stale_intent_resets += 1
            logger.warning(
                "OffboardCommander applying default setpoints because %s",
                reason,
            )
        self.setpoint_handler.reset_setpoints()
        self._failsafe_defaults_active = True

    def _record_publish_result(self, success: bool, reason: str) -> None:
        self.publish_count += 1
        self.last_publish_success = success
        self.last_publish_reason = reason
        self.last_publish_monotonic_s = time.monotonic()
        if success:
            self.successful_publishes += 1
            self.consecutive_failures = 0
            self.last_error = None
        else:
            self.failed_publishes += 1
            self.consecutive_failures += 1

    async def _maybe_trigger_failure_policy(
        self,
        reason: str,
        *,
        invoke_callback: bool = True,
    ) -> None:
        triggered_now = self._mark_failure_policy_triggered(reason)
        if not triggered_now or not invoke_callback:
            return

        await self._invoke_failure_threshold_callback()

    def _mark_failure_policy_triggered(self, reason: str) -> bool:
        if self.failure_policy_triggered:
            return False
        if self.consecutive_failures < self.command_failure_threshold:
            return False

        self.failure_policy_triggered = True
        self.failure_policy_trigger_count += 1
        self.failure_policy_reason = (
            f"{self.consecutive_failures} consecutive publish failures; "
            f"threshold={self.command_failure_threshold}; last_reason={reason}"
        )
        self.failure_policy_triggered_at_monotonic_s = time.monotonic()
        self.running = False
        logger.error(
            "OffboardCommander local failure policy triggered: %s",
            self.failure_policy_reason,
        )
        return True

    async def _invoke_failure_threshold_callback(self) -> None:
        if self._on_failure_threshold is None:
            return

        try:
            callback_result = self._on_failure_threshold(self.get_status())
            if asyncio.iscoroutine(callback_result):
                await callback_result
        except Exception as exc:
            self.last_error = f"Failure-policy callback failed: {exc}"
            logger.error("OffboardCommander failure-policy callback failed: %s", exc)

    def get_status(self) -> dict:
        """Return commander diagnostics for APIs, logs, and tests."""
        intent_age_s = None
        if self._last_intent is not None:
            intent_age_s = max(0.0, time.monotonic() - self._last_intent.created_at_monotonic_s)

        return {
            "exists": True,
            "running": self.running,
            "task_active": bool(self._task and not self._task.done()),
            "health_state": self._get_health_state(),
            "command_rate_hz": self.command_rate_hz,
            "command_period_s": self.command_period_s,
            "command_ttl_s": self.command_ttl_s,
            "command_failure_threshold": self.command_failure_threshold,
            "last_intent_age_s": intent_age_s,
            "last_intent_fresh": self._has_fresh_intent(),
            "failsafe_defaults_active": self._failsafe_defaults_active,
            "publish_count": self.publish_count,
            "successful_publishes": self.successful_publishes,
            "failed_publishes": self.failed_publishes,
            "consecutive_failures": self.consecutive_failures,
            "stale_intent_resets": self.stale_intent_resets,
            "rejected_intents": self.rejected_intents,
            "last_publish_success": self.last_publish_success,
            "last_publish_reason": self.last_publish_reason,
            "last_publish_monotonic_s": self.last_publish_monotonic_s,
            "last_error": self.last_error,
            "failure_policy_triggered": self.failure_policy_triggered,
            "failure_policy_reason": self.failure_policy_reason,
            "failure_policy_triggered_at_monotonic_s": self.failure_policy_triggered_at_monotonic_s,
            "failure_policy_trigger_count": self.failure_policy_trigger_count,
            "failure_action": "stop_following",
            "sends_mavsdk_commands": True,
            "command_publication_source": "offboard_commander",
        }

    def _get_health_state(self) -> str:
        if self.failure_policy_triggered:
            return "failed"
        if self.running and self.consecutive_failures > 0:
            return "degraded"
        if self.running:
            return "running"
        return "stopped"
