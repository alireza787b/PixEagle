import asyncio
import math
import logging
import time
from typing import List, Literal, NamedTuple, Optional, TypedDict
from mavsdk import System
from classes.parameters import Parameters
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed, AttitudeRate
from classes.command_safety import (
    CommandValidationError,
    operator_allows_commands_without_safety_modules,
    validate_and_clamp_command_values,
)
from classes.setpoint_handler import SetpointHandler

# Import circuit breaker for testing support
try:
    from classes.circuit_breaker import FollowerCircuitBreaker
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False

# Configure logging
logger = logging.getLogger(__name__)


class PX4CommandGateDecision(NamedTuple):
    """Decision from the PX4 command safety gate."""
    blocked: bool
    degraded: bool
    reason: str


class PX4ActionOutcome(TypedDict):
    """Truthful result for one discrete MAVSDK action command."""

    command: str
    status: Literal["executed", "simulated", "blocked", "failed"]
    executed: bool
    simulated: bool
    blocked: bool
    degraded: bool
    reason: str
    steps: List[str]
    errors: List[str]


def _current_follower_limit_context() -> str:
    """Return the active follower profile name for safety-limit lookup."""
    follower_mode = getattr(Parameters, "FOLLOWER_MODE", "")
    return SetpointHandler.normalize_profile_name(str(follower_mode)).upper()


def _validate_px4_command_values(command_type: str, **values):
    """Validate and clamp command values immediately before PX4 dispatch."""
    try:
        return validate_and_clamp_command_values(
            command_type,
            values,
            follower_name=_current_follower_limit_context(),
            allow_safety_bypass=operator_allows_commands_without_safety_modules(),
        )
    except CommandValidationError as exc:
        logger.error("Blocking %s PX4 command: %s", command_type, exc)
        return None


def _evaluate_px4_command_gate(command_type: str, **params) -> PX4CommandGateDecision:
    """
    SAFETY FIRST: Determine how a PX4 COMMAND should be gated.

    BLOCKS (Commands TO drone):
    - start/stop offboard mode
    - velocity commands (set_velocity_body)
    - attitude commands (set_attitude_rate)
    - action commands (RTL, hold, land, takeoff)
    - Any command that changes drone behavior

    ALLOWS (Data FROM drone):
    - telemetry reading (position, attitude, velocity)
    - MAVLink2REST data fetching
    - status queries
    - flight mode reading

    Safety Philosophy:
    - Default to BLOCKING (fail-safe)
    - Only allow commands if circuit breaker is explicitly disabled
    - If circuit breaker system unavailable, DEFAULT TO SAFE (block all)

    Returns:
        PX4CommandGateDecision with:
        - blocked=True when no MAVSDK command should be sent
        - degraded=True when the block is caused by unavailable/failed safety
          infrastructure rather than the normal test circuit breaker
    """
    if not CIRCUIT_BREAKER_AVAILABLE:
        if operator_allows_commands_without_safety_modules():
            logger.critical(
                "Circuit breaker unavailable, but "
                "FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES is enabled; allowing %s",
                command_type,
            )
            return PX4CommandGateDecision(False, False, "operator_bypass_safety_modules")
        logger.error("Circuit breaker unavailable; blocking PX4 command %s", command_type)
        return PX4CommandGateDecision(True, True, "circuit_breaker_unavailable")

    # Check circuit breaker status - only allow if explicitly disabled
    try:
        circuit_breaker_active = FollowerCircuitBreaker.is_active()
    except Exception as exc:
        if operator_allows_commands_without_safety_modules():
            logger.critical(
                "Circuit breaker status check failed for %s (%s), but "
                "FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES is enabled; allowing command",
                command_type,
                exc,
            )
            return PX4CommandGateDecision(False, False, "operator_bypass_circuit_breaker_status")
        logger.error("Circuit breaker status check failed for %s; blocking command: %s", command_type, exc)
        return PX4CommandGateDecision(True, True, "circuit_breaker_status_failed")

    if circuit_breaker_active:
        try:
            FollowerCircuitBreaker.log_command_instead_of_execute(
                command_type=command_type,
                follower_name="PX4Interface",
                **params
            )
        except Exception as exc:
            if operator_allows_commands_without_safety_modules():
                logger.critical(
                    "Circuit breaker block logging failed for %s (%s), but "
                    "FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES is enabled; allowing command",
                    command_type,
                    exc,
                )
                return PX4CommandGateDecision(False, False, "operator_bypass_circuit_breaker_block_logging")
            logger.error("Circuit breaker block logging failed for %s; blocking command: %s", command_type, exc)
            return PX4CommandGateDecision(True, True, "circuit_breaker_block_logging_failed")
        return PX4CommandGateDecision(True, False, "circuit_breaker_active")

    # Circuit breaker explicitly disabled - allow command and track it
    try:
        FollowerCircuitBreaker.log_command_allowed(
            command_type=command_type,
            follower_name="PX4Interface",
            **params
        )
    except Exception as exc:
        if operator_allows_commands_without_safety_modules():
            logger.critical(
                "Circuit breaker audit logging failed for %s (%s), but "
                "FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES is enabled; allowing command",
                command_type,
                exc,
            )
            return PX4CommandGateDecision(False, False, "operator_bypass_circuit_breaker_audit")
        logger.error("Circuit breaker audit logging failed for %s; blocking command: %s", command_type, exc)
        return PX4CommandGateDecision(True, True, "circuit_breaker_audit_failed")
    return PX4CommandGateDecision(False, False, "allowed")


def _px4_action_outcome(
    command: str,
    *,
    status: Literal["executed", "simulated", "blocked", "failed"],
    reason: str,
    steps: Optional[List[str]] = None,
    errors: Optional[List[str]] = None,
    degraded: bool = False,
) -> PX4ActionOutcome:
    """Build one stable action result without conflating simulation with execution."""
    return {
        "command": command,
        "status": status,
        "executed": status == "executed",
        "simulated": status == "simulated",
        "blocked": status in {"simulated", "blocked"},
        "degraded": bool(degraded),
        "reason": reason,
        "steps": list(steps or []),
        "errors": list(errors or []),
    }


def _blocked_action_outcome(
    command: str,
    decision: PX4CommandGateDecision,
    *,
    step: str,
) -> PX4ActionOutcome:
    """Convert a command-gate decision into an explicit action outcome."""
    simulated = not decision.degraded and decision.reason == "circuit_breaker_active"
    return _px4_action_outcome(
        command,
        status="simulated" if simulated else "blocked",
        reason=decision.reason,
        steps=[step],
        errors=(
            []
            if simulated
            else [f"{command} blocked: {decision.reason}"]
        ),
        degraded=decision.degraded,
    )

class PX4InterfaceManager:

    DEFAULT_FOLLOWER_DATA_REFRESH_RATE_HZ = 5.0
    MIN_FOLLOWER_DATA_REFRESH_RATE_HZ = 0.1
    MAX_FOLLOWER_DATA_REFRESH_RATE_HZ = 100.0
    DEFAULT_MAVSDK_CONNECTION_TIMEOUT_S = 15.0
    MIN_MAVSDK_CONNECTION_TIMEOUT_S = 0.1
    MAX_MAVSDK_CONNECTION_TIMEOUT_S = 120.0
    DEFAULT_MAVSDK_COMMAND_TIMEOUT_S = 3.0
    MIN_MAVSDK_COMMAND_TIMEOUT_S = 0.05
    MAX_MAVSDK_COMMAND_TIMEOUT_S = 30.0
    DEFAULT_TELEMETRY_STALE_TIMEOUT_S = 2.0
    MIN_TELEMETRY_STALE_TIMEOUT_S = 0.1
    MAX_TELEMETRY_STALE_TIMEOUT_S = 5.0
    DEFAULT_TELEMETRY_MAX_SKEW_S = 0.25
    DEFAULT_MAVLINK2REST_CYCLE_TIMEOUT_S = 1.0
    DEFAULT_OWNED_TASK_STOP_TIMEOUT_S = 2.0
    # Hold the first accepted setpoint long enough to establish PX4 proof-of-life.
    OFFBOARD_PRIME_DURATION_S = 1.1
    MAVSDK_TELEMETRY_STREAM_NAMES = ("position", "attitude", "velocity_body")
    MIN_MAVSDK_STREAM_RETRY_DELAY_S = 0.25
    MAX_MAVSDK_STREAM_RETRY_DELAY_S = 5.0

    FLIGHT_MODES = {
        458752: 'Stabilized',
        196608: 'Position',
        100925440: 'Land',
        393216: 'Offboard',
        50593792: 'Hold',
        84148224: 'Return',
        131072: 'Altitude',
        65536: 'Manual',
        327680: 'Acro',
        33816576: 'Takeoff',
        67371008: 'Mission',
        151257088: 'Precission Land'
        
    }

    def __init__(self, app_controller=None, *, on_connection_lost=None):
        """
        Initializes the PX4InterfaceManager and sets up the connection to the PX4 drone.
        Uses MAVSDK for offboard control, and optionally uses MAVLink2Rest for telemetry data.
        """
        self.app_controller = app_controller
        self.current_yaw = None  # Degrees; unavailable until a complete sample
        self.current_pitch = None  # Degrees; unavailable until a complete sample
        self.current_roll = None  # Degrees; unavailable until a complete sample
        self.current_altitude = None  # Relative altitude in meters
        self.current_ground_speed = None  # Horizontal speed in m/s
        self.camera_yaw_offset = Parameters.CAMERA_YAW_OFFSET
        self.update_task = None  # Task for telemetry updates
        self.connection_monitor_task = None
        self._on_connection_lost = on_connection_lost
        self._telemetry_stream_tasks = {}
        self._telemetry_source_requested = self._get_requested_telemetry_source()
        self._telemetry_source_active = None
        self._telemetry_generation = 0
        self._telemetry_connection_generation = None
        self._telemetry_state = "idle"
        self._telemetry_sample_count = 0
        self._telemetry_last_complete_sample_monotonic_s = None
        self._telemetry_last_snapshot_skew_s = None
        self._telemetry_last_state_transition_monotonic_s = time.monotonic()
        self._telemetry_ready_event = asyncio.Event()
        self._telemetry_pending_values = {}
        self._telemetry_worker_failed = False
        self._telemetry_stream_status = {
            name: {
                "state": "idle",
                "sample_count": 0,
                "restart_count": 0,
                "last_update_monotonic_s": None,
                "last_error": None,
                "connection_generation": None,
                "telemetry_generation": None,
            }
            for name in self.MAVSDK_TELEMETRY_STREAM_NAMES
        }
        normalized_profile_name = SetpointHandler.normalize_profile_name(Parameters.FOLLOWER_MODE)
        self.setpoint_handler = SetpointHandler(normalized_profile_name)    
        self.active_mode = False
        self.failsafe_active = False
        self._validation_mavsdk_disconnect_active = False
        self._validation_mavsdk_disconnect_reason = None
        self._validation_mavsdk_disconnect_source = None
        self._validation_mavsdk_disconnect_at_monotonic_s = None
        self._validation_mavsdk_disconnect_count = 0
        self._connection_lock = asyncio.Lock()
        self._connection_state = "disconnected"
        self._connection_generation = 0
        self._connection_started_monotonic_s = None
        self._connected_at_monotonic_s = None
        self._last_connection_error = None
        self._cleanup_failed = False
        self._last_telemetry_error = None
        self._mavsdk_offboard_sender_state = "idle"
        self._mavsdk_offboard_sender_last_reason = None
        self._mavsdk_offboard_sender_last_transition_monotonic_s = None
        self._offboard_mode_start_acknowledged = False

        # Determine if we are using MAVLink2Rest for telemetry data
        if Parameters.USE_MAVLINK2REST and self.app_controller:
            self.mavlink_data_manager = self.app_controller.mavlink_data_manager
            logger.info("Using MAVLink2Rest for telemetry data.")
        else:
            logger.info("Using MAVSDK for telemetry and offboard control.")
        
        # Setup MAVSDK connection for both telemetry and offboard control.
        self._uses_external_mavsdk_server = bool(Parameters.EXTERNAL_MAVSDK_SERVER)
        self._mavsdk_server_address = str(
            getattr(Parameters, "MAVSDK_SERVER_ADDRESS", "127.0.0.1")
        ).strip() or "127.0.0.1"
        self._mavsdk_server_port = self._get_mavsdk_server_port()
        if self._uses_external_mavsdk_server:
            self.drone = System(
                mavsdk_server_address=self._mavsdk_server_address,
                port=self._mavsdk_server_port,
            )
        else:
            self.drone = System()
            
            
    async def _safe_mavsdk_call(
        self,
        coro_func,
        *args,
        _px4_command_type="mavsdk_command",
        _px4_command_params=None,
        _px4_gate_checked=False,
        _marks_offboard_sender=False,
        **kwargs,
    ):
        """
        Safely execute MAVSDK coroutine-creating function with proper error handling.

        NOTE: This is used for COMMAND calls only (offboard.set_*).
        Data retrieval calls (telemetry.*) should NOT use this wrapper.

        Args:
            coro_func: Callable that creates a coroutine when invoked
            *args, **kwargs: Arguments to pass to coro_func

        Returns:
            bool: True if successful, False otherwise

        Example:
            await self._safe_mavsdk_call(
                self.drone.offboard.set_velocity_body,
                velocity_setpoint
            )
        """
        connection_generation = self._connection_generation
        disconnect_error = self._validation_mavsdk_disconnect_error()
        if disconnect_error:
            logger.error("Blocking MAVSDK command during validation disconnect: %s", disconnect_error)
            return False

        if not self.is_command_connection_ready(
            expected_generation=connection_generation,
            require_fresh_telemetry=False,
        ):
            logger.error(
                "Blocking MAVSDK command %s because the PX4 connection is not ready "
                "(state=%s, active=%s, generation=%s)",
                _px4_command_type,
                self._connection_state,
                self.active_mode,
                connection_generation,
            )
            return False

        if not _px4_gate_checked:
            gate_decision = _evaluate_px4_command_gate(
                _px4_command_type,
                blocked_call=f"{coro_func.__name__}({args}, {kwargs})"[:100],
                **(_px4_command_params or {}),
            )
            if gate_decision.blocked:
                if self._mavsdk_offboard_sender_state == "primed":
                    await self.quiesce_offboard_sender(
                        reason=f"command_gate_blocked:{gate_decision.reason}",
                    )
                return False

        try:
            await asyncio.wait_for(
                coro_func(*args, **kwargs),
                timeout=self.get_mavsdk_command_timeout_s(),
            )
            if not self.is_command_connection_ready(
                expected_generation=connection_generation,
                require_fresh_telemetry=False,
            ):
                logger.error(
                    "MAVSDK command %s completed after its PX4 connection generation "
                    "became invalid",
                    _px4_command_type,
                )
                return False
            if _marks_offboard_sender:
                self._set_offboard_sender_state("primed", _px4_command_type)
            return True
        except asyncio.TimeoutError:
            logger.error(
                "MAVSDK command %s exceeded %.2f s deadline",
                _px4_command_type,
                self.get_mavsdk_command_timeout_s(),
            )
            return False
        except Exception as e:
            logger.error("MAVSDK command %s failed: %s", _px4_command_type, e)
            return False

    def _set_offboard_sender_state(self, state: str, reason: str) -> None:
        """Publish local MAVSDK setpoint-scheduler truth for cleanup diagnostics."""
        self._mavsdk_offboard_sender_state = str(state)
        self._mavsdk_offboard_sender_last_reason = str(reason)
        self._mavsdk_offboard_sender_last_transition_monotonic_s = time.monotonic()

    @property
    def connection_generation(self) -> int:
        """Return the identity of the current MAVSDK connection lifecycle."""
        return self._connection_generation

    def is_command_connection_ready(
        self,
        *,
        expected_generation: int | None = None,
        require_fresh_telemetry: bool = True,
    ) -> bool:
        """Return whether an ordinary command belongs to the live connection."""
        if expected_generation is not None and expected_generation != self._connection_generation:
            return False
        link_ready = (
            bool(self.active_mode)
            and self._connection_state == "connected"
            and not self._validation_mavsdk_disconnect_active
            and not self._cleanup_failed
        )
        if not link_ready or not require_fresh_telemetry:
            return link_ready
        return self.get_telemetry_readiness()["ready"]

    def _advance_connection_generation(self) -> int:
        """Invalidate command owners created for every previous connection."""
        self._connection_generation += 1
        return self._connection_generation

    def _advance_telemetry_generation(self, connection_generation: int) -> int:
        """Create a telemetry owner bound to one connection generation."""
        if connection_generation != self._connection_generation:
            raise RuntimeError(
                "Cannot start telemetry for a superseded PX4 connection generation"
            )
        self._telemetry_generation += 1
        self._telemetry_connection_generation = connection_generation
        return self._telemetry_generation

    def _is_telemetry_owner_current(
        self,
        connection_generation: int,
        telemetry_generation: int,
    ) -> bool:
        """Return whether a telemetry producer still owns the current lifecycle."""
        return (
            connection_generation == self._connection_generation
            and connection_generation == self._telemetry_connection_generation
            and telemetry_generation == self._telemetry_generation
        )

    @classmethod
    def get_telemetry_stale_timeout_s(cls) -> float:
        """Return the one follower-telemetry freshness deadline."""
        raw_value = getattr(
            Parameters,
            "MAVLINK_STALE_TIMEOUT_S",
            cls.DEFAULT_TELEMETRY_STALE_TIMEOUT_S,
        )
        try:
            timeout_s = float(raw_value)
        except (TypeError, ValueError):
            timeout_s = cls.DEFAULT_TELEMETRY_STALE_TIMEOUT_S
        if not math.isfinite(timeout_s):
            timeout_s = cls.DEFAULT_TELEMETRY_STALE_TIMEOUT_S
        return min(
            cls.MAX_TELEMETRY_STALE_TIMEOUT_S,
            max(cls.MIN_TELEMETRY_STALE_TIMEOUT_S, timeout_s),
        )

    def _set_telemetry_state(self, state: str) -> None:
        if state != self._telemetry_state:
            self._telemetry_state = state
            self._telemetry_last_state_transition_monotonic_s = time.monotonic()

    def _reset_telemetry_health(
        self,
        source: str,
        *,
        connection_generation: int | None = None,
    ) -> int:
        """Start a new source lifecycle without retaining readiness from the old one."""
        connection_generation = (
            self._connection_generation
            if connection_generation is None
            else connection_generation
        )
        telemetry_generation = self._advance_telemetry_generation(
            connection_generation
        )
        self._telemetry_source_active = source
        self._telemetry_sample_count = 0
        self._telemetry_last_complete_sample_monotonic_s = None
        self._telemetry_last_snapshot_skew_s = None
        self._telemetry_pending_values = {}
        self._telemetry_worker_failed = False
        self._last_telemetry_error = None
        self._telemetry_ready_event = asyncio.Event()
        self._set_telemetry_state("starting")
        self._telemetry_stream_status = {
            name: {
                "state": "idle",
                "sample_count": 0,
                "restart_count": 0,
                "last_update_monotonic_s": None,
                "last_error": None,
                "connection_generation": connection_generation,
                "telemetry_generation": telemetry_generation,
            }
            for name in self.MAVSDK_TELEMETRY_STREAM_NAMES
        }
        return telemetry_generation

    def _commit_telemetry_snapshot(
        self,
        values: dict,
        *,
        connection_generation: int | None = None,
        telemetry_generation: int | None = None,
        completed_at_monotonic_s: float | None = None,
        temporal_skew_s: float | None = None,
    ) -> bool:
        """Publish one complete finite follower snapshot without partial writes."""
        connection_generation = (
            self._connection_generation
            if connection_generation is None
            else connection_generation
        )
        telemetry_generation = (
            self._telemetry_generation
            if telemetry_generation is None
            else telemetry_generation
        )
        if not self._is_telemetry_owner_current(
            connection_generation,
            telemetry_generation,
        ):
            return False

        required = {
            "roll_deg",
            "pitch_deg",
            "yaw_deg",
            "relative_altitude_m",
            "ground_speed_m_s",
        }
        if set(values) != required:
            raise ValueError(
                "Telemetry snapshot fields do not match the required contract"
            )
        parsed = {}
        for field_name, raw_value in values.items():
            value = float(raw_value)
            if not math.isfinite(value):
                raise ValueError(f"Telemetry field {field_name} is not finite")
            parsed[field_name] = value

        self.current_roll = parsed["roll_deg"]
        self.current_pitch = parsed["pitch_deg"]
        self.current_yaw = parsed["yaw_deg"]
        self.current_altitude = parsed["relative_altitude_m"]
        self.current_ground_speed = parsed["ground_speed_m_s"]
        completed_at = (
            time.monotonic()
            if completed_at_monotonic_s is None
            else float(completed_at_monotonic_s)
        )
        if not math.isfinite(completed_at):
            raise ValueError("Telemetry completion timestamp is not finite")
        self._telemetry_last_complete_sample_monotonic_s = completed_at
        self._telemetry_last_snapshot_skew_s = (
            None if temporal_skew_s is None else float(temporal_skew_s)
        )
        self._telemetry_sample_count += 1
        self._telemetry_worker_failed = False
        self._last_telemetry_error = None
        self._set_telemetry_state("ready")
        self._telemetry_ready_event.set()
        return True

    def _refresh_telemetry_state(self) -> None:
        if not self.active_mode or self._telemetry_source_active is None:
            if self._telemetry_state not in {"idle", "stopped", "failed"}:
                self._set_telemetry_state("stopped")
            return
        if self._telemetry_connection_generation != self._connection_generation:
            self._set_telemetry_state("stale")
            return
        if self._telemetry_worker_failed:
            self._set_telemetry_state("failed")
            return

        last_sample = self._telemetry_last_complete_sample_monotonic_s
        if last_sample is None:
            self._set_telemetry_state("starting")
            return
        if time.monotonic() - last_sample > self.get_telemetry_stale_timeout_s():
            self._set_telemetry_state("stale")
            return
        self._set_telemetry_state("ready")

    def get_telemetry_readiness(self) -> dict:
        """Return source-independent telemetry truth used by command gates."""
        self._refresh_telemetry_state()
        now = time.monotonic()
        last_sample_age_s = (
            max(0.0, now - self._telemetry_last_complete_sample_monotonic_s)
            if self._telemetry_last_complete_sample_monotonic_s is not None
            else None
        )
        return {
            "state": self._telemetry_state,
            "ready": self._telemetry_state == "ready",
            "source": self._telemetry_source_active,
            "source_requested": self._telemetry_source_requested,
            "sample_count": self._telemetry_sample_count,
            "last_complete_sample_age_s": last_sample_age_s,
            "stale_timeout_s": self.get_telemetry_stale_timeout_s(),
            "max_temporal_skew_s": self.get_telemetry_max_skew_s(),
            "last_snapshot_skew_s": self._telemetry_last_snapshot_skew_s,
            "connection_generation": self._connection_generation,
            "telemetry_connection_generation": self._telemetry_connection_generation,
            "telemetry_generation": self._telemetry_generation,
            "owner_current": (
                self._telemetry_connection_generation == self._connection_generation
            ),
            "last_error": self._last_telemetry_error,
            "required_fields": [
                "roll_deg",
                "pitch_deg",
                "yaw_deg",
                "relative_altitude_m",
                "ground_speed_m_s",
            ],
            "state_age_s": max(
                0.0,
                now - self._telemetry_last_state_transition_monotonic_s,
            ),
        }

    async def wait_for_telemetry_ready(self, timeout_s: float | None = None) -> dict:
        """Wait for the first complete sample, bounded by the connection deadline."""
        connection_generation = self._connection_generation
        telemetry_generation = self._telemetry_generation
        readiness = self.get_telemetry_readiness()
        if readiness["ready"]:
            return readiness

        ready_event = self._telemetry_ready_event
        ready_event.clear()
        readiness = self.get_telemetry_readiness()
        if readiness["ready"]:
            return readiness

        timeout_s = (
            self.get_mavsdk_connection_timeout_s()
            if timeout_s is None
            else max(0.0, float(timeout_s))
        )
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            if self._is_telemetry_owner_current(
                connection_generation,
                telemetry_generation,
            ):
                self._last_telemetry_error = (
                    "No complete follower telemetry sample arrived within "
                    f"{timeout_s:.1f} seconds"
                )
                if self._telemetry_last_complete_sample_monotonic_s is None:
                    self._telemetry_worker_failed = True
                    self._set_telemetry_state("failed")
        return self.get_telemetry_readiness()

    @classmethod
    def get_telemetry_max_skew_s(cls) -> float:
        """Return the maximum age spread accepted within one telemetry snapshot."""
        return min(
            cls.DEFAULT_TELEMETRY_MAX_SKEW_S,
            cls.get_telemetry_stale_timeout_s(),
        )

    @classmethod
    def get_mavlink2rest_cycle_timeout_s(cls) -> float:
        """Return one bounded deadline for all follower-message HTTP requests."""
        return min(
            cls.DEFAULT_MAVLINK2REST_CYCLE_TIMEOUT_S,
            cls.get_telemetry_stale_timeout_s(),
        )

    @classmethod
    def get_mavsdk_command_timeout_s(cls) -> float:
        """Return the bounded deadline for one MAVSDK command RPC."""
        raw_value = getattr(
            Parameters,
            "MAVSDK_COMMAND_TIMEOUT_S",
            cls.DEFAULT_MAVSDK_COMMAND_TIMEOUT_S,
        )
        try:
            timeout_s = float(raw_value)
        except (TypeError, ValueError):
            return cls.DEFAULT_MAVSDK_COMMAND_TIMEOUT_S
        if not math.isfinite(timeout_s):
            return cls.DEFAULT_MAVSDK_COMMAND_TIMEOUT_S
        return min(
            cls.MAX_MAVSDK_COMMAND_TIMEOUT_S,
            max(cls.MIN_MAVSDK_COMMAND_TIMEOUT_S, timeout_s),
        )

    @staticmethod
    def _get_mavsdk_server_port() -> int:
        raw_value = getattr(Parameters, "MAVSDK_SERVER_PORT", 50051)
        try:
            port = int(raw_value)
        except (TypeError, ValueError):
            return 50051
        return min(65535, max(1, port))

    @classmethod
    def get_mavsdk_connection_timeout_s(cls) -> float:
        """Return a bounded MAVSDK vehicle-discovery timeout."""
        raw_value = getattr(
            Parameters,
            "MAVSDK_CONNECTION_TIMEOUT_S",
            cls.DEFAULT_MAVSDK_CONNECTION_TIMEOUT_S,
        )
        try:
            timeout_s = float(raw_value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid MAVSDK_CONNECTION_TIMEOUT_S=%r; using %.1f s",
                raw_value,
                cls.DEFAULT_MAVSDK_CONNECTION_TIMEOUT_S,
            )
            return cls.DEFAULT_MAVSDK_CONNECTION_TIMEOUT_S
        if not math.isfinite(timeout_s):
            return cls.DEFAULT_MAVSDK_CONNECTION_TIMEOUT_S
        return min(
            cls.MAX_MAVSDK_CONNECTION_TIMEOUT_S,
            max(cls.MIN_MAVSDK_CONNECTION_TIMEOUT_S, timeout_s),
        )

    async def _wait_for_mavsdk_connection(self) -> None:
        """Wait until MAVSDK reports vehicle discovery, not just link setup."""
        async for state in self.drone.core.connection_state():
            if bool(getattr(state, "is_connected", False)):
                return
        raise RuntimeError("MAVSDK connection-state stream ended before vehicle discovery")

    async def connect(self) -> dict:
        """
        Establish and verify the MAVSDK vehicle connection, then start telemetry.

        Connection and telemetry are observational operations and remain available
        while the command circuit breaker is active. Repeated calls are idempotent
        so stopping and restarting Follow mode can reuse the live telemetry link.
        """
        async with self._connection_lock:
            requested_source = self._get_requested_telemetry_source()
            self._telemetry_source_requested = requested_source
            connection_monitor_running = bool(
                self.connection_monitor_task
                and not self.connection_monitor_task.done()
            )
            telemetry_running = bool(
                self.update_task and not self.update_task.done()
            )
            telemetry_workers_running = telemetry_running or any(
                not task.done() for task in self._telemetry_stream_tasks.values()
            )

            if (
                self.active_mode
                and not self._validation_mavsdk_disconnect_active
                and connection_monitor_running
            ):
                if (
                    telemetry_running
                    and self._telemetry_source_active == requested_source
                    and not self._cleanup_failed
                ):
                    logger.debug("Reusing verified MAVSDK connection and telemetry task")
                    return self.get_connection_status()

                try:
                    self._prepare_telemetry_source(requested_source)
                except Exception as exc:
                    self._last_telemetry_error = (
                        f"Telemetry source preparation failed: {exc}"
                    )
                    logger.error(self._last_telemetry_error)
                    raise RuntimeError(self._last_telemetry_error) from exc

                if telemetry_workers_running:
                    telemetry_stopped = await self._cancel_telemetry_update_task()
                    if not telemetry_stopped:
                        self._cleanup_failed = True
                        self._last_telemetry_error = (
                            "Refusing telemetry replacement because the previous "
                            "telemetry owner did not stop"
                        )
                        self._telemetry_worker_failed = True
                        self._set_telemetry_state("cleanup_failed")
                        raise RuntimeError(self._last_telemetry_error)
                self._cleanup_failed = False
                self._start_telemetry_worker(requested_source)
                logger.info(
                    "Restarted telemetry worker with source %s on existing MAVSDK link",
                    requested_source,
                )
                return self.get_connection_status()

            telemetry_stopped = await self._cancel_telemetry_update_task()
            monitor_stopped = await self._cancel_connection_monitor_task()
            if not telemetry_stopped or not monitor_stopped:
                self.active_mode = False
                self._cleanup_failed = True
                self._connection_state = "cleanup_failed"
                self._last_connection_error = (
                    "Refusing PX4 connection replacement while prior owned tasks "
                    "remain alive"
                )
                self._telemetry_worker_failed = True
                self._set_telemetry_state("cleanup_failed")
                raise RuntimeError(self._last_connection_error)

            self._advance_connection_generation()
            self._cleanup_failed = False
            self.active_mode = False
            self._connection_state = "connecting"
            self._connection_started_monotonic_s = time.monotonic()
            self._last_connection_error = None
            timeout_s = self.get_mavsdk_connection_timeout_s()

            try:
                self._prepare_telemetry_source(requested_source)
            except Exception as exc:
                self._connection_state = "connection_failed"
                self._connection_started_monotonic_s = None
                self._last_telemetry_error = (
                    f"Telemetry source preparation failed: {exc}"
                )
                self._last_connection_error = self._last_telemetry_error
                self._telemetry_worker_failed = True
                self._set_telemetry_state("failed")
                logger.error(self._last_telemetry_error)
                raise RuntimeError(self._last_telemetry_error) from exc
            self._last_telemetry_error = None

            async def connect_and_discover():
                if self._uses_external_mavsdk_server:
                    await self.drone.connect()
                else:
                    await self.drone.connect(system_address=Parameters.SYSTEM_ADDRESS)
                await self._wait_for_mavsdk_connection()

            try:
                await asyncio.wait_for(connect_and_discover(), timeout=timeout_s)
            except asyncio.CancelledError:
                self.active_mode = False
                self._connection_state = "disconnected"
                self._connection_started_monotonic_s = None
                self._last_connection_error = "MAVSDK connection attempt canceled"
                self._set_telemetry_state("stopped")
                logger.warning(self._last_connection_error)
                raise
            except asyncio.TimeoutError as exc:
                self._connection_state = "connection_failed"
                self._connection_started_monotonic_s = None
                self._last_connection_error = (
                    f"MAVSDK did not discover a PX4 vehicle within {timeout_s:.1f} s"
                )
                self._telemetry_worker_failed = True
                self._set_telemetry_state("failed")
                logger.error(self._last_connection_error)
                raise TimeoutError(self._last_connection_error) from exc
            except Exception as exc:
                self._connection_state = "connection_failed"
                self._connection_started_monotonic_s = None
                self._last_connection_error = f"MAVSDK connection failed: {exc}"
                self._telemetry_worker_failed = True
                self._set_telemetry_state("failed")
                logger.error(self._last_connection_error)
                raise RuntimeError(self._last_connection_error) from exc

            self.clear_validation_mavsdk_disconnect()
            self.active_mode = True
            self._connection_state = "connected"
            self._connection_started_monotonic_s = None
            self._connected_at_monotonic_s = time.monotonic()
            self._last_connection_error = None
            self._cleanup_failed = False
            connection_generation = self._connection_generation
            self._start_telemetry_worker(requested_source)
            self.connection_monitor_task = asyncio.create_task(
                self._monitor_mavsdk_connection(connection_generation),
                name="PixEaglePX4ConnectionMonitor",
            )
            logger.info("MAVSDK vehicle connection confirmed.")
            return self.get_connection_status()

    @staticmethod
    def _get_requested_telemetry_source() -> str:
        return (
            "mavlink2rest"
            if bool(getattr(Parameters, "USE_MAVLINK2REST", False))
            else "mavsdk"
        )

    def _prepare_telemetry_source(self, source: str) -> None:
        """Resolve dependencies for the immutable telemetry-worker source."""
        if source != "mavlink2rest":
            return
        manager = getattr(self, "mavlink_data_manager", None)
        if manager is None and self.app_controller is not None:
            manager = getattr(self.app_controller, "mavlink_data_manager", None)
            self.mavlink_data_manager = manager
        if manager is None:
            raise RuntimeError(
                "MAVLink2REST telemetry requested but MavlinkDataManager is unavailable"
            )

    def _start_telemetry_worker(self, source: str) -> None:
        """Create the sole telemetry supervisor for the current connection."""
        if self.update_task is not None and not self.update_task.done():
            raise RuntimeError("A PX4 telemetry supervisor is already running")
        if any(not task.done() for task in self._telemetry_stream_tasks.values()):
            raise RuntimeError("Prior MAVSDK telemetry stream workers are still running")

        connection_generation = self._connection_generation
        telemetry_generation = self._reset_telemetry_health(
            source,
            connection_generation=connection_generation,
        )
        self.update_task = asyncio.create_task(
            self.update_drone_data(
                source,
                connection_generation=connection_generation,
                telemetry_generation=telemetry_generation,
            ),
            name="PixEaglePX4Telemetry",
        )

    async def _monitor_mavsdk_connection(
        self,
        connection_generation: int | None = None,
    ) -> None:
        """Keep local connection truth synchronized with MAVSDK after discovery."""
        connection_generation = (
            self._connection_generation
            if connection_generation is None
            else connection_generation
        )
        try:
            async for state in self.drone.core.connection_state():
                if connection_generation != self._connection_generation:
                    return
                if bool(getattr(state, "is_connected", False)):
                    continue
                if self.active_mode:
                    await self._handle_mavsdk_connection_loss(
                        "MAVSDK reported that the PX4 vehicle disconnected",
                        expected_generation=connection_generation,
                    )
                return

            if (
                self.active_mode
                and connection_generation == self._connection_generation
            ):
                await self._handle_mavsdk_connection_loss(
                    "MAVSDK connection-state stream ended unexpectedly",
                    expected_generation=connection_generation,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if (
                self.active_mode
                and connection_generation == self._connection_generation
            ):
                await self._handle_mavsdk_connection_loss(
                    f"MAVSDK connection monitor failed: {exc}",
                    expected_generation=connection_generation,
                )

    async def _handle_mavsdk_connection_loss(
        self,
        reason: str,
        *,
        expected_generation: int | None = None,
    ) -> bool:
        """Mark the link lost, stop telemetry, and notify the lifecycle owner."""
        expected_generation = (
            self._connection_generation
            if expected_generation is None
            else expected_generation
        )
        if (
            not self.active_mode
            or expected_generation != self._connection_generation
        ):
            return False

        self._advance_connection_generation()
        self.active_mode = False
        self._connection_state = "connection_lost"
        self._last_connection_error = str(reason)
        logger.error(reason)

        callback = self._on_connection_lost
        if callback is not None:
            try:
                callback_result = callback(self.get_connection_status())
                if asyncio.iscoroutine(callback_result):
                    await callback_result
            except Exception:
                logger.exception("PX4 connection-loss callback failed")

        telemetry_stopped = await self._cancel_telemetry_update_task()
        if telemetry_stopped:
            self._set_telemetry_state("stopped")
            self._telemetry_source_active = None
        else:
            self._cleanup_failed = True
            self._connection_state = "connection_lost_cleanup_failed"
            self._last_telemetry_error = (
                "PX4 connection was lost and the telemetry owner did not stop"
            )
            self._telemetry_worker_failed = True
            self._set_telemetry_state("cleanup_failed")
        return True

    def _validation_mavsdk_disconnect_error(self):
        if not self._validation_mavsdk_disconnect_active:
            return None
        reason = self._validation_mavsdk_disconnect_reason or "sitl_mavsdk_disconnect"
        return f"MAVSDK disconnected - {reason}"

    def clear_validation_mavsdk_disconnect(self):
        """Clear validation-only local MAVSDK disconnect state."""
        self._validation_mavsdk_disconnect_active = False
        self._validation_mavsdk_disconnect_reason = None
        self._validation_mavsdk_disconnect_source = None
        self._validation_mavsdk_disconnect_at_monotonic_s = None

    async def inject_mavsdk_disconnect_for_validation(
        self,
        *,
        reason="sitl_mavsdk_disconnect",
        source="sitl_validation",
    ):
        """
        Record validation-only local MAVSDK disconnect state.

        This hook does not stop PX4, Docker, MAVLink routing, MAVSDK server, or
        network interfaces. It marks PixEagle's local PX4 command path as
        disconnected so command sends and Offboard stop attempts fail locally.
        """
        self._validation_mavsdk_disconnect_active = True
        self._validation_mavsdk_disconnect_reason = str(reason)
        self._validation_mavsdk_disconnect_source = str(source)
        self._validation_mavsdk_disconnect_at_monotonic_s = time.monotonic()
        self._validation_mavsdk_disconnect_count += 1
        self._advance_connection_generation()
        self.active_mode = False
        self._connection_state = "validation_disconnected"

        monitor_stopped = await self._cancel_connection_monitor_task()
        telemetry_stopped = await self._cancel_telemetry_update_task()
        if monitor_stopped and telemetry_stopped:
            self._set_telemetry_state("stopped")
            self._telemetry_source_active = None
        else:
            self._cleanup_failed = True
            self._connection_state = "validation_disconnect_cleanup_failed"
            self._last_telemetry_error = (
                "Validation disconnect could not stop all PX4-owned tasks"
            )
            self._telemetry_worker_failed = True
            self._set_telemetry_state("cleanup_failed")

        return self.get_connection_status()

    def get_connection_status(self):
        """Return local PX4/MAVSDK connection diagnostics."""
        disconnect_age_s = None
        if self._validation_mavsdk_disconnect_at_monotonic_s is not None:
            disconnect_age_s = max(
                0.0,
                time.monotonic() - self._validation_mavsdk_disconnect_at_monotonic_s,
            )

        validation_disconnect = bool(self._validation_mavsdk_disconnect_active)
        owned_tasks = self._get_owned_task_status()
        connected = (
            bool(self.active_mode)
            and self._connection_state == "connected"
            and not validation_disconnect
            and not self._cleanup_failed
        )
        if self._cleanup_failed:
            status = (
                self._connection_state
                if "cleanup_failed" in self._connection_state
                else "cleanup_failed"
            )
            last_error = self._last_connection_error or self._last_telemetry_error
        elif validation_disconnect:
            status = "validation_disconnected"
            last_error = self._validation_mavsdk_disconnect_error()
        elif self._connection_state == "connecting":
            status = "connecting"
            last_error = None
        elif connected:
            status = "connected"
            last_error = None
        elif self._last_connection_error:
            status = self._connection_state
            last_error = self._last_connection_error
        else:
            status = "disconnected"
            last_error = None

        telemetry_streams = {}
        now = time.monotonic()
        for name, stream_status in self._telemetry_stream_status.items():
            public_stream_status = dict(stream_status)
            last_update = public_stream_status.pop("last_update_monotonic_s", None)
            public_stream_status["last_update_age_s"] = (
                max(0.0, now - last_update) if last_update is not None else None
            )
            telemetry_streams[name] = public_stream_status

        telemetry_readiness = self.get_telemetry_readiness()
        return {
            "status": status,
            "connected": connected,
            "active_mode": bool(self.active_mode),
            "validation_disconnect_active": validation_disconnect,
            "disconnect_reason": self._validation_mavsdk_disconnect_reason,
            "disconnect_source": self._validation_mavsdk_disconnect_source,
            "disconnect_age_s": disconnect_age_s,
            "disconnect_count": self._validation_mavsdk_disconnect_count,
            "last_error": last_error,
            "cleanup_failed": bool(self._cleanup_failed),
            "owned_tasks": owned_tasks,
            "connection_generation": self._connection_generation,
            "telemetry_generation": self._telemetry_generation,
            "connection_timeout_s": self.get_mavsdk_connection_timeout_s(),
            "command_timeout_s": self.get_mavsdk_command_timeout_s(),
            "connection_age_s": (
                max(0.0, now - self._connected_at_monotonic_s)
                if connected and self._connected_at_monotonic_s is not None
                else None
            ),
            "system_address": (
                None
                if self._uses_external_mavsdk_server
                else getattr(Parameters, "SYSTEM_ADDRESS", None)
            ),
            "configured_vehicle_link": getattr(Parameters, "SYSTEM_ADDRESS", None),
            "vehicle_link_owner": (
                "external_mavsdk_server"
                if self._uses_external_mavsdk_server
                else "pixeagle_embedded_mavsdk_server"
            ),
            "mavsdk_server": {
                "mode": "external" if self._uses_external_mavsdk_server else "embedded",
                "address": (
                    self._mavsdk_server_address
                    if self._uses_external_mavsdk_server
                    else "127.0.0.1"
                ),
                "port": self._mavsdk_server_port,
            },
            "uses_mavlink2rest": bool(getattr(Parameters, "USE_MAVLINK2REST", False)),
            "telemetry_source": (
                self._telemetry_source_active
                if self.update_task and not self.update_task.done()
                else None
            ),
            "telemetry_source_requested": self._telemetry_source_requested,
            "telemetry_source_active": self._telemetry_source_active,
            "telemetry_error": self._last_telemetry_error,
            "telemetry": telemetry_readiness,
            "command_ready": connected and telemetry_readiness["ready"],
            "telemetry_update_running": bool(
                self.update_task and not self.update_task.done()
            ),
            "connection_monitor_running": bool(
                self.connection_monitor_task
                and not self.connection_monitor_task.done()
            ),
            "mavsdk_streams": telemetry_streams,
            "offboard_sender": {
                "state": self._mavsdk_offboard_sender_state,
                "last_reason": self._mavsdk_offboard_sender_last_reason,
                "last_transition_age_s": (
                    max(
                        0.0,
                        now - self._mavsdk_offboard_sender_last_transition_monotonic_s,
                    )
                    if self._mavsdk_offboard_sender_last_transition_monotonic_s
                    is not None
                    else None
                ),
                "offboard_start_acknowledged": bool(
                    self._offboard_mode_start_acknowledged
                ),
            },
        }

    async def update_drone_data(
        self,
        telemetry_source=None,
        *,
        connection_generation: int | None = None,
        telemetry_generation: int | None = None,
    ):
        """
        Continuously updates the drone's telemetry data using the selected source.
        Uses MAVLink2Rest for telemetry if enabled, otherwise uses MAVSDK.
        FOLLOWER_DATA_REFRESH_RATE is configured in Hz and converted to seconds
        before sleeping between telemetry polling iterations.
        """
        connection_generation = (
            self._connection_generation
            if connection_generation is None
            else connection_generation
        )
        telemetry_generation = (
            self._telemetry_generation
            if telemetry_generation is None
            else telemetry_generation
        )
        try:
            source = telemetry_source or self._get_requested_telemetry_source()
            if source == "mavlink2rest":
                while (
                    self.active_mode
                    and self._is_telemetry_owner_current(
                        connection_generation,
                        telemetry_generation,
                    )
                ):
                    await self._update_telemetry_via_mavlink2rest(
                        connection_generation=connection_generation,
                        telemetry_generation=telemetry_generation,
                    )
                    await asyncio.sleep(self.get_follower_data_refresh_period_s())
            elif source == "mavsdk":
                await self._update_telemetry_via_mavsdk(
                    connection_generation=connection_generation,
                    telemetry_generation=telemetry_generation,
                )
            else:
                raise RuntimeError(f"Unsupported telemetry source: {source}")
        except asyncio.CancelledError:
            logger.info("Telemetry update task was cancelled.")
            if self._is_telemetry_owner_current(
                connection_generation,
                telemetry_generation,
            ):
                self._set_telemetry_state("stopped")
            raise
        except Exception as exc:
            if self._is_telemetry_owner_current(
                connection_generation,
                telemetry_generation,
            ):
                self._last_telemetry_error = f"Telemetry worker failed: {exc}"
                self._telemetry_worker_failed = True
                self._set_telemetry_state("failed")
                logger.exception("Telemetry update task failed: %s", exc)

    @classmethod
    def get_follower_data_refresh_rate_hz(cls) -> float:
        """Return the validated telemetry refresh rate in Hertz."""
        raw_rate = getattr(
            Parameters,
            'FOLLOWER_DATA_REFRESH_RATE',
            cls.DEFAULT_FOLLOWER_DATA_REFRESH_RATE_HZ,
        )
        try:
            rate_hz = float(raw_rate)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid FOLLOWER_DATA_REFRESH_RATE=%r; using default %.1f Hz",
                raw_rate,
                cls.DEFAULT_FOLLOWER_DATA_REFRESH_RATE_HZ,
            )
            rate_hz = cls.DEFAULT_FOLLOWER_DATA_REFRESH_RATE_HZ

        if not math.isfinite(rate_hz) or rate_hz <= 0.0:
            logger.warning(
                "FOLLOWER_DATA_REFRESH_RATE must be positive Hz, got %r; "
                "using default %.1f Hz",
                raw_rate,
                cls.DEFAULT_FOLLOWER_DATA_REFRESH_RATE_HZ,
            )
            rate_hz = cls.DEFAULT_FOLLOWER_DATA_REFRESH_RATE_HZ
        elif rate_hz < cls.MIN_FOLLOWER_DATA_REFRESH_RATE_HZ:
            logger.warning(
                "FOLLOWER_DATA_REFRESH_RATE %.3f Hz is below %.3f Hz; clamping",
                rate_hz,
                cls.MIN_FOLLOWER_DATA_REFRESH_RATE_HZ,
            )
            rate_hz = cls.MIN_FOLLOWER_DATA_REFRESH_RATE_HZ
        elif rate_hz > cls.MAX_FOLLOWER_DATA_REFRESH_RATE_HZ:
            logger.warning(
                "FOLLOWER_DATA_REFRESH_RATE %.3f Hz is above %.3f Hz; clamping",
                rate_hz,
                cls.MAX_FOLLOWER_DATA_REFRESH_RATE_HZ,
            )
            rate_hz = cls.MAX_FOLLOWER_DATA_REFRESH_RATE_HZ

        return rate_hz

    @classmethod
    def get_follower_data_refresh_period_s(cls) -> float:
        """Return the telemetry polling sleep period in seconds."""
        return 1.0 / cls.get_follower_data_refresh_rate_hz()

    async def _update_telemetry_via_mavlink2rest(
        self,
        *,
        connection_generation: int | None = None,
        telemetry_generation: int | None = None,
    ):
        """
        Publish one complete MAVLink2REST follower-telemetry snapshot.

        A failed field leaves the previous complete snapshot untouched. Readiness
        becomes stale after the configured freshness deadline.
        """
        connection_generation = (
            self._connection_generation
            if connection_generation is None
            else connection_generation
        )
        telemetry_generation = (
            self._telemetry_generation
            if telemetry_generation is None
            else telemetry_generation
        )

        async def timed_fetch(fetch):
            value = await fetch()
            return value, time.monotonic()

        try:
            if not self._is_telemetry_owner_current(
                connection_generation,
                telemetry_generation,
            ):
                return False
            results = await asyncio.wait_for(
                asyncio.gather(
                    timed_fetch(self.mavlink_data_manager.fetch_attitude_data),
                    timed_fetch(self.mavlink_data_manager.fetch_altitude_data),
                    timed_fetch(self.mavlink_data_manager.fetch_ground_speed),
                ),
                timeout=self.get_mavlink2rest_cycle_timeout_s(),
            )
            (attitude_data, attitude_at), (altitude_data, altitude_at), (
                ground_speed,
                ground_speed_at,
            ) = results

            completion_times = (attitude_at, altitude_at, ground_speed_at)
            temporal_skew_s = max(completion_times) - min(completion_times)
            if temporal_skew_s > self.get_telemetry_max_skew_s():
                raise RuntimeError(
                    "message completion skew "
                    f"{temporal_skew_s:.3f}s exceeds "
                    f"{self.get_telemetry_max_skew_s():.3f}s"
                )

            if not isinstance(attitude_data, dict):
                raise RuntimeError("attitude payload unavailable")
            if not isinstance(altitude_data, dict):
                raise RuntimeError("altitude payload unavailable")
            if ground_speed is None:
                raise RuntimeError("ground-speed payload unavailable")

            committed = self._commit_telemetry_snapshot(
                {
                    "roll_deg": attitude_data["roll"],
                    "pitch_deg": attitude_data["pitch"],
                    "yaw_deg": attitude_data["yaw"],
                    "relative_altitude_m": altitude_data["altitude_relative"],
                    "ground_speed_m_s": ground_speed,
                },
                connection_generation=connection_generation,
                telemetry_generation=telemetry_generation,
                completed_at_monotonic_s=max(completion_times),
                temporal_skew_s=temporal_skew_s,
            )
            return committed
        except asyncio.TimeoutError:
            exc = RuntimeError(
                "cycle exceeded "
                f"{self.get_mavlink2rest_cycle_timeout_s():.3f}s deadline"
            )
            if self._is_telemetry_owner_current(
                connection_generation,
                telemetry_generation,
            ):
                self._last_telemetry_error = (
                    f"MAVLink2REST follower telemetry unavailable: {exc}"
                )
                self._refresh_telemetry_state()
                logger.warning(self._last_telemetry_error)
            return False
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            if self._is_telemetry_owner_current(
                connection_generation,
                telemetry_generation,
            ):
                self._last_telemetry_error = (
                    f"MAVLink2REST follower telemetry unavailable: {exc}"
                )
                self._refresh_telemetry_state()
                logger.warning(self._last_telemetry_error)
            return False

    async def _update_telemetry_via_mavsdk(
        self,
        *,
        connection_generation: int,
        telemetry_generation: int,
    ):
        """Own and supervise the independent MAVSDK telemetry streams."""
        if not self._is_telemetry_owner_current(
            connection_generation,
            telemetry_generation,
        ):
            return
        workers = {
            "position": (
                self.drone.telemetry.position,
                self._consume_mavsdk_position,
            ),
            "attitude": (
                self.drone.telemetry.attitude_euler,
                self._consume_mavsdk_attitude,
            ),
            "velocity_body": (
                self.drone.telemetry.velocity_body,
                self._consume_mavsdk_velocity_body,
            ),
        }
        statuses = {
            name: self._telemetry_stream_status[name] for name in workers
        }
        tasks = {
            name: asyncio.create_task(
                self._run_mavsdk_telemetry_stream(
                    name,
                    stream_factory,
                    consume_sample,
                    status=statuses[name],
                    connection_generation=connection_generation,
                    telemetry_generation=telemetry_generation,
                ),
                name=f"px4-telemetry-{name}",
            )
            for name, (stream_factory, consume_sample) in workers.items()
        }
        if not self._is_telemetry_owner_current(
            connection_generation,
            telemetry_generation,
        ):
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
            return
        self._telemetry_stream_tasks = tasks
        try:
            await asyncio.gather(*tasks.values())
        finally:
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            done, pending = await asyncio.wait(
                set(tasks.values()),
                timeout=self.DEFAULT_OWNED_TASK_STOP_TIMEOUT_S,
            )
            for task in done:
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    logger.debug("MAVSDK telemetry worker stopped with error: %s", exc)
            for name, task in tasks.items():
                if task in pending:
                    statuses[name]["state"] = "cancel_timeout"
                    logger.error(
                        "MAVSDK telemetry stream %s did not stop within %.2f seconds",
                        name,
                        self.DEFAULT_OWNED_TASK_STOP_TIMEOUT_S,
                    )
            if self._telemetry_stream_tasks is tasks:
                self._telemetry_stream_tasks = {
                    name: task for name, task in tasks.items() if task in pending
                }

    async def _run_mavsdk_telemetry_stream(
        self,
        name,
        stream_factory,
        consume_sample,
        *,
        status: dict,
        connection_generation: int,
        telemetry_generation: int,
    ):
        """Consume one MAVSDK stream and retry it without starving peer streams."""
        retry_delay_s = min(
            self.MAX_MAVSDK_STREAM_RETRY_DELAY_S,
            max(
                self.MIN_MAVSDK_STREAM_RETRY_DELAY_S,
                self.get_follower_data_refresh_period_s(),
            ),
        )

        while (
            self.active_mode
            and self._is_telemetry_owner_current(
                connection_generation,
                telemetry_generation,
            )
        ):
            status["state"] = "running"
            try:
                async for sample in stream_factory():
                    if (
                        not self.active_mode
                        or not self._is_telemetry_owner_current(
                            connection_generation,
                            telemetry_generation,
                        )
                    ):
                        status["state"] = "stopped"
                        return
                    values = consume_sample(sample)
                    completed_at = time.monotonic()
                    if not self._is_telemetry_owner_current(
                        connection_generation,
                        telemetry_generation,
                    ):
                        status["state"] = "superseded"
                        return
                    self._telemetry_pending_values.update(values)
                    status["sample_count"] += 1
                    status["last_update_monotonic_s"] = completed_at
                    status["last_error"] = None
                    self._try_commit_mavsdk_telemetry_snapshot(
                        connection_generation=connection_generation,
                        telemetry_generation=telemetry_generation,
                    )

                if (
                    not self.active_mode
                    or not self._is_telemetry_owner_current(
                        connection_generation,
                        telemetry_generation,
                    )
                ):
                    status["state"] = "stopped"
                    return
                raise RuntimeError("stream ended while PX4 interface remained active")
            except asyncio.CancelledError:
                status["state"] = "cancelled"
                raise
            except Exception as exc:
                status["state"] = "retrying"
                status["restart_count"] += 1
                status["last_error"] = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "MAVSDK telemetry stream %s failed; retrying in %.2fs: %s",
                    name,
                    retry_delay_s,
                    exc,
                )
                await asyncio.sleep(retry_delay_s)

        status["state"] = "stopped"

    def _consume_mavsdk_position(self, position):
        value = float(position.relative_altitude_m)
        if not math.isfinite(value):
            raise ValueError("MAVSDK relative altitude is not finite")
        return {"relative_altitude_m": value}

    def _consume_mavsdk_attitude(self, attitude):
        values = {
            "yaw_deg": float(attitude.yaw_deg) + float(self.camera_yaw_offset),
            "pitch_deg": float(attitude.pitch_deg),
            "roll_deg": float(attitude.roll_deg),
        }
        if not all(math.isfinite(value) for value in values.values()):
            raise ValueError("MAVSDK attitude contains a non-finite value")
        return values

    def _consume_mavsdk_velocity_body(self, velocity):
        ground_speed = math.hypot(
            float(velocity.x_m_s),
            float(velocity.y_m_s),
        )
        if not math.isfinite(ground_speed):
            raise ValueError("MAVSDK ground speed is not finite")
        return {"ground_speed_m_s": ground_speed}

    def _try_commit_mavsdk_telemetry_snapshot(
        self,
        *,
        connection_generation: int | None = None,
        telemetry_generation: int | None = None,
    ) -> bool:
        """Commit staged stream values only when every source is fresh."""
        connection_generation = (
            self._connection_generation
            if connection_generation is None
            else connection_generation
        )
        telemetry_generation = (
            self._telemetry_generation
            if telemetry_generation is None
            else telemetry_generation
        )
        if not self._is_telemetry_owner_current(
            connection_generation,
            telemetry_generation,
        ):
            return False

        now = time.monotonic()
        stale_timeout_s = self.get_telemetry_stale_timeout_s()
        completion_times = []
        for stream_status in self._telemetry_stream_status.values():
            if (
                stream_status["connection_generation"] != connection_generation
                or stream_status["telemetry_generation"] != telemetry_generation
            ):
                return False
            last_update = stream_status["last_update_monotonic_s"]
            if last_update is None or now - last_update > stale_timeout_s:
                return False
            completion_times.append(last_update)
        temporal_skew_s = max(completion_times) - min(completion_times)
        if temporal_skew_s > self.get_telemetry_max_skew_s():
            self._last_telemetry_error = (
                "MAVSDK telemetry stream skew "
                f"{temporal_skew_s:.3f}s exceeds "
                f"{self.get_telemetry_max_skew_s():.3f}s"
            )
            return False
        try:
            committed = self._commit_telemetry_snapshot(
                dict(self._telemetry_pending_values),
                connection_generation=connection_generation,
                telemetry_generation=telemetry_generation,
                completed_at_monotonic_s=max(completion_times),
                temporal_skew_s=temporal_skew_s,
            )
        except ValueError:
            return False
        return committed

    async def _cancel_owned_task(
        self,
        task,
        *,
        label: str,
        timeout_s: float | None = None,
    ) -> bool:
        """Cancel one task with a deadline while preserving parent cancellation."""
        if task is None or task.done() or task is asyncio.current_task():
            return True
        timeout_s = (
            self.DEFAULT_OWNED_TASK_STOP_TIMEOUT_S
            if timeout_s is None
            else max(0.0, float(timeout_s))
        )
        task.cancel()
        try:
            done, _ = await asyncio.wait(
                {task},
                timeout=timeout_s,
            )
        except asyncio.CancelledError:
            raise
        if task not in done:
            logger.error(
                "%s did not stop within %.2f seconds",
                label,
                timeout_s,
            )
            return False
        try:
            task.result()
        except asyncio.CancelledError:
            return True
        except Exception as exc:
            logger.warning("%s stopped with error: %s", label, exc)
        return True

    async def _cancel_mavsdk_stream_tasks(self) -> bool:
        """Cancel all retained MAVSDK stream workers without losing pending refs."""
        tasks = dict(self._telemetry_stream_tasks)
        alive = {name: task for name, task in tasks.items() if not task.done()}
        for task in alive.values():
            if task is not asyncio.current_task():
                task.cancel()

        if alive:
            done, pending = await asyncio.wait(
                set(alive.values()),
                timeout=self.DEFAULT_OWNED_TASK_STOP_TIMEOUT_S,
            )
        else:
            done, pending = set(), set()

        for task in done:
            try:
                task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("MAVSDK telemetry stream stopped with error: %s", exc)

        retained = {
            name: task
            for name, task in self._telemetry_stream_tasks.items()
            if not task.done()
        }
        self._telemetry_stream_tasks = retained
        if pending or retained:
            logger.error(
                "MAVSDK telemetry stream cleanup left %d task(s) alive",
                len(retained),
            )
            return False
        return True

    def _get_owned_task_status(self) -> dict:
        """Return explicit ownership truth without discarding task references."""
        telemetry_supervisor_alive = bool(
            self.update_task is not None and not self.update_task.done()
        )
        connection_monitor_alive = bool(
            self.connection_monitor_task is not None
            and not self.connection_monitor_task.done()
        )
        stream_workers = {
            name: not task.done()
            for name, task in self._telemetry_stream_tasks.items()
        }
        alive_count = (
            int(telemetry_supervisor_alive)
            + int(connection_monitor_alive)
            + sum(int(alive) for alive in stream_workers.values())
        )
        return {
            "telemetry_supervisor_alive": telemetry_supervisor_alive,
            "connection_monitor_alive": connection_monitor_alive,
            "mavsdk_stream_workers": stream_workers,
            "alive_count": alive_count,
            "all_stopped": alive_count == 0,
        }

    async def _cancel_telemetry_update_task(self):
        """Cancel and join the owned telemetry supervisor task."""
        supervisor_stopped = await self._cancel_owned_task(
            self.update_task,
            label="PX4 telemetry supervisor",
            timeout_s=self.DEFAULT_OWNED_TASK_STOP_TIMEOUT_S * 2.0,
        )
        streams_stopped = await self._cancel_mavsdk_stream_tasks()
        return supervisor_stopped and streams_stopped

    async def _cancel_connection_monitor_task(self):
        """Cancel and join the owned MAVSDK connection monitor."""
        return await self._cancel_owned_task(
            self.connection_monitor_task,
            label="PX4 connection monitor",
        )

    def get_orientation(self):
        """
        Returns the current orientation (yaw, pitch, roll) of the drone.
        """
        return self.current_yaw, self.current_pitch, self.current_roll

    def get_ground_speed(self):
        return self.current_ground_speed


    async def send_velocity_body_offboard_commands(self):
        """
        Sends body velocity offboard commands for quadcopter control.
        Uses the new body velocity field names (vel_body_fwd, vel_body_right, vel_body_down, yawspeed_deg_s).
        This operation uses MAVSDK VelocityBodyYawspeed.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized")
                return False
                
            control_type = self.setpoint_handler.get_control_type()
            if control_type != 'velocity_body_offboard':
                logger.error(
                    "Refusing velocity_body_offboard command for control type %s",
                    control_type,
                )
                return False
                
            setpoint = self.setpoint_handler.get_fields()
            if not setpoint:
                logger.error("No setpoint data available")
                return False

            expected_fields = {
                'vel_body_fwd',
                'vel_body_right',
                'vel_body_down',
                'yawspeed_deg_s',
            }
            actual_fields = set(setpoint)
            if actual_fields != expected_fields:
                logger.error(
                    "Refusing incomplete or mixed velocity_body_offboard snapshot: "
                    "expected=%s actual=%s",
                    sorted(expected_fields),
                    sorted(actual_fields),
                )
                return False

            vel_fwd = float(setpoint['vel_body_fwd'])
            vel_right = float(setpoint['vel_body_right'])
            vel_down = float(setpoint['vel_body_down'])
            yawspeed = float(setpoint['yawspeed_deg_s'])

            validated = _validate_px4_command_values(
                "velocity_body_offboard",
                vel_body_fwd=vel_fwd,
                vel_body_right=vel_right,
                vel_body_down=vel_down,
                yawspeed_deg_s=yawspeed,
            )
            if validated is None:
                return False

            vel_fwd = validated['vel_body_fwd']
            vel_right = validated['vel_body_right']
            vel_down = validated['vel_body_down']
            yawspeed = validated['yawspeed_deg_s']

            # Convert yaw speed from degrees/s to radians/s if needed
            # yawspeed_rad = math.radians(yawspeed)

            logger.debug(f"Sending VELOCITY_BODY_OFFBOARD: Fwd={vel_fwd:.3f}, Right={vel_right:.3f}, Down={vel_down:.3f}, YawSpeed={yawspeed:.1f}°/s")

            # Send the velocity commands to the drone using MAVSDK VelocityBodyYawspeed
            # Note: VelocityBodyYawspeed expects (forward, right, down, yawspeed_deg_s)
            next_setpoint = VelocityBodyYawspeed(vel_fwd, vel_right, vel_down, yawspeed)
            return await self._safe_mavsdk_call(
                self.drone.offboard.set_velocity_body,
                next_setpoint,
                _px4_command_type="velocity_body_offboard",
                _px4_command_params={
                    "vel_body_fwd": vel_fwd,
                    "vel_body_right": vel_right,
                    "vel_body_down": vel_down,
                    "yawspeed_deg_s": yawspeed,
                },
                _marks_offboard_sender=True,
            )

        except OffboardError as e:
            logger.error(f"MAVSDK offboard velocity_body_offboard command failed: {e}")
            return False
        except ValueError as e:
            logger.error(f"Invalid setpoint values for velocity_body_offboard command: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in send_velocity_body_offboard_commands: {e}")
            return False


    async def quiesce_offboard_sender(
        self,
        *,
        reason: str,
        force: bool = False,
    ) -> dict:
        """Stop MAVSDK's local setpoint scheduler without assuming PX4 receipt."""
        state_before = self._mavsdk_offboard_sender_state
        if state_before != "primed" and not force:
            return {
                "attempted": False,
                "local_sender_quiesced": state_before in {"idle", "quiesced"},
                "vehicle_hold_acknowledged": False,
                "state_before": state_before,
                "state_after": state_before,
                "reason": reason,
                "error": None,
            }

        timeout_s = self.get_mavsdk_command_timeout_s()
        try:
            await asyncio.wait_for(
                self.drone.offboard.stop(),
                timeout=timeout_s,
            )
        except OffboardError as exc:
            # MAVSDK C++ stops its local scheduler before requesting Hold. An
            # OffboardError is a completed RPC response, so local quiescence did
            # occur even though PX4 did not acknowledge the mode change.
            self._set_offboard_sender_state("quiesced", reason)
            self._offboard_mode_start_acknowledged = False
            return {
                "attempted": True,
                "local_sender_quiesced": True,
                "vehicle_hold_acknowledged": False,
                "state_before": state_before,
                "state_after": "quiesced",
                "reason": reason,
                "error": str(exc),
            }
        except asyncio.TimeoutError:
            error = f"MAVSDK Offboard sender quiesce exceeded {timeout_s:.2f} s"
            self._set_offboard_sender_state("unknown", reason)
            logger.error(error)
            return {
                "attempted": True,
                "local_sender_quiesced": False,
                "vehicle_hold_acknowledged": False,
                "state_before": state_before,
                "state_after": "unknown",
                "reason": reason,
                "error": error,
            }
        except Exception as exc:
            self._set_offboard_sender_state("unknown", reason)
            logger.error("MAVSDK Offboard sender quiesce failed: %s", exc)
            return {
                "attempted": True,
                "local_sender_quiesced": False,
                "vehicle_hold_acknowledged": False,
                "state_before": state_before,
                "state_after": "unknown",
                "reason": reason,
                "error": str(exc),
            }

        self._set_offboard_sender_state("quiesced", reason)
        self._offboard_mode_start_acknowledged = False
        return {
            "attempted": True,
            "local_sender_quiesced": True,
            "vehicle_hold_acknowledged": True,
            "state_before": state_before,
            "state_after": "quiesced",
            "reason": reason,
            "error": None,
        }

    async def start_offboard_mode(self) -> PX4ActionOutcome:
        """
        Prime a fail-closed default setpoint stream and enter PX4 Offboard mode.

        MAVSDK independently retransmits the latest accepted setpoint. Waiting
        after the first setter call establishes more than one second of PX4
        Offboard proof-of-life before mode entry without depending on frame rate.
        """
        disconnect_error = self._validation_mavsdk_disconnect_error()
        if disconnect_error:
            logger.error("Cannot start Offboard during validation disconnect: %s", disconnect_error)
            return _px4_action_outcome(
                "start_offboard_mode",
                status="blocked",
                reason="validation_mavsdk_disconnected",
                errors=[disconnect_error],
                degraded=True,
            )

        gate_decision = _evaluate_px4_command_gate("start_offboard_mode", action="start_offboard")
        if gate_decision.blocked:
            return _blocked_action_outcome(
                "start_offboard_mode",
                gate_decision,
                step="Offboard mode start intercepted by PX4 command gate",
            )

        if not self.active_mode:
            error = "Cannot start Offboard before MAVSDK vehicle connection is confirmed"
            logger.error(error)
            return _px4_action_outcome(
                "start_offboard_mode",
                status="blocked",
                reason="mavsdk_not_connected",
                errors=[error],
                degraded=True,
            )

        telemetry = self.get_telemetry_readiness()
        if not telemetry["ready"]:
            state = telemetry["state"]
            error = (
                "Cannot start Offboard without fresh, complete follower telemetry "
                f"(state={state}, source={telemetry['source']})"
            )
            logger.error(error)
            return _px4_action_outcome(
                "start_offboard_mode",
                status="blocked",
                reason=f"telemetry_{state}",
                errors=[error],
                degraded=True,
            )

        try:
            control_type = self.setpoint_handler.get_control_type()
            self.setpoint_handler.reset_setpoints()
            initial_setpoint_success = await self.send_commands_unified()
            if initial_setpoint_success is not True:
                raise RuntimeError(
                    f"MAVSDK rejected the initial {control_type} setpoint"
                )

            await asyncio.sleep(self.OFFBOARD_PRIME_DURATION_S)
            if not self.active_mode:
                raise RuntimeError(
                    "MAVSDK vehicle connection was lost while priming Offboard"
                )
            telemetry = self.get_telemetry_readiness()
            if not telemetry["ready"]:
                raise RuntimeError(
                    "Follower telemetry became unavailable while priming Offboard "
                    f"(state={telemetry['state']})"
                )
            disconnect_error = self._validation_mavsdk_disconnect_error()
            if disconnect_error:
                raise RuntimeError(disconnect_error)

            post_prime_gate = _evaluate_px4_command_gate(
                "start_offboard_mode",
                action="start_offboard_after_priming",
            )
            if post_prime_gate.blocked:
                quiesce = await self.quiesce_offboard_sender(
                    reason=f"start_gate_changed:{post_prime_gate.reason}",
                )
                outcome = _blocked_action_outcome(
                    "start_offboard_mode",
                    post_prime_gate,
                    step="Offboard start blocked after setpoint priming",
                )
                outcome["steps"].append(
                    "MAVSDK local setpoint sender quiesce "
                    f"state: {quiesce['state_after']}"
                )
                if quiesce.get("error"):
                    outcome["errors"].append(quiesce["error"])
                return outcome

            await asyncio.wait_for(
                self.drone.offboard.start(),
                timeout=self.get_mavsdk_command_timeout_s(),
            )
            self._offboard_mode_start_acknowledged = True
            if not self.active_mode:
                quiesce = await self.quiesce_offboard_sender(
                    reason="link_lost_after_offboard_start_ack",
                )
                outcome = _px4_action_outcome(
                    "start_offboard_mode",
                    status="executed",
                    reason="mavsdk_action_acknowledged_then_link_lost",
                    steps=[
                        f"Initial {control_type} setpoint accepted by MAVSDK.",
                        (
                            "MAVSDK setpoint stream primed for "
                            f"{self.OFFBOARD_PRIME_DURATION_S:.1f} seconds."
                        ),
                        "MAVSDK Offboard start was acknowledged before the vehicle link was lost.",
                    ],
                    errors=[
                        "PX4 connection was lost immediately after Offboard start; "
                        "local following was not activated"
                    ],
                    degraded=True,
                )
                outcome["steps"].append(
                    "MAVSDK local setpoint sender quiesce "
                    f"state: {quiesce['state_after']}"
                )
                if quiesce.get("error"):
                    outcome["errors"].append(quiesce["error"])
                return outcome
            logger.info("Offboard mode started.")
            return _px4_action_outcome(
                "start_offboard_mode",
                status="executed",
                reason="mavsdk_action_acknowledged",
                steps=[
                    f"Initial {control_type} setpoint accepted by MAVSDK.",
                    (
                        "MAVSDK setpoint stream primed for "
                        f"{self.OFFBOARD_PRIME_DURATION_S:.1f} seconds."
                    ),
                    "MAVSDK Offboard start command acknowledged.",
                ],
            )
        except asyncio.CancelledError:
            await self.quiesce_offboard_sender(
                reason="offboard_start_canceled",
            )
            raise
        except Exception as e:
            logger.error(f"Failed to start offboard mode: {e}")
            quiesce = await self.quiesce_offboard_sender(
                reason="offboard_start_failed",
            )
            outcome = _px4_action_outcome(
                "start_offboard_mode",
                status="failed",
                reason="mavsdk_action_failed",
                errors=[f"Failed to start offboard mode: {e}"],
            )
            outcome["steps"].append(
                "MAVSDK local setpoint sender quiesce "
                f"state: {quiesce['state_after']}"
            )
            if quiesce.get("error"):
                outcome["errors"].append(quiesce["error"])
            return outcome

    async def stop_offboard_mode(self) -> PX4ActionOutcome:
        """
        Stops offboard mode on the drone using MAVSDK.
        """
        disconnect_error = self._validation_mavsdk_disconnect_error()
        if disconnect_error:
            logger.error("Cannot stop Offboard through MAVSDK during validation disconnect: %s", disconnect_error)
            quiesce = await self.quiesce_offboard_sender(
                reason="validation_disconnect_cleanup",
            )
            return _px4_action_outcome(
                "stop_offboard_mode",
                status="blocked",
                reason="validation_mavsdk_disconnected",
                steps=[f"Local sender state: {quiesce['state_after']}"],
                errors=[disconnect_error] + ([quiesce["error"]] if quiesce.get("error") else []),
                degraded=True,
            )

        gate_decision = _evaluate_px4_command_gate("stop_offboard_mode", action="stop_offboard")
        if gate_decision.blocked:
            logger.info("Stop offboard mode intercepted by PX4 command gate: %s", gate_decision.reason)
            if self._mavsdk_offboard_sender_state != "primed":
                return _blocked_action_outcome(
                    "stop_offboard_mode",
                    gate_decision,
                    step="Offboard mode stop intercepted by PX4 command gate",
                )
            quiesce = await self.quiesce_offboard_sender(
                reason=f"safety_teardown:{gate_decision.reason}",
            )
            if quiesce["vehicle_hold_acknowledged"]:
                return _px4_action_outcome(
                    "stop_offboard_mode",
                    status="executed",
                    reason="safety_teardown_overrode_command_gate",
                    steps=[
                        "MAVSDK sender quiesced and Hold acknowledged during safety teardown."
                    ],
                )
            return _px4_action_outcome(
                "stop_offboard_mode",
                status="failed",
                reason="sender_quiesce_unconfirmed",
                steps=[f"Local sender state: {quiesce['state_after']}"],
                errors=[quiesce.get("error") or "MAVSDK sender quiesce was not confirmed"],
                degraded=True,
            )

        if not self.active_mode:
            error = "Cannot stop Offboard because the MAVSDK vehicle is not connected"
            logger.error(error)
            quiesce = await self.quiesce_offboard_sender(
                reason="disconnected_cleanup",
            )
            return _px4_action_outcome(
                "stop_offboard_mode",
                status="blocked",
                reason="mavsdk_not_connected",
                steps=[f"Local sender state: {quiesce['state_after']}"],
                errors=[error] + ([quiesce["error"]] if quiesce.get("error") else []),
                degraded=True,
            )

        logger.info("Stopping offboard mode...")
        quiesce = await self.quiesce_offboard_sender(
            reason="operator_stop",
            force=True,
        )
        if quiesce["vehicle_hold_acknowledged"]:
            return _px4_action_outcome(
                "stop_offboard_mode",
                status="executed",
                reason="mavsdk_action_acknowledged",
                steps=["MAVSDK sender quiesced and Hold command acknowledged."],
            )
        return _px4_action_outcome(
            "stop_offboard_mode",
            status="failed",
            reason="mavsdk_action_failed",
            steps=[f"Local sender state: {quiesce['state_after']}"],
            errors=[quiesce.get("error") or "PX4 Hold acknowledgement was not received"],
            degraded=True,
        )

    async def stop(self, *, attempt_offboard_stop: bool = False):
        """
        Stop owned connection-monitor and telemetry tasks.

        AppController normally exits Offboard before calling this method. A caller
        that still owns an active Offboard session must opt in explicitly; commands
        are never inferred during generic task cleanup.
        """
        outcome = {
            "connection_monitor_stopped": True,
            "telemetry_stopped": True,
            "offboard_stop": None,
            "cleanup_failed": False,
            "status": "disconnecting",
            "owned_tasks": None,
        }
        async with self._connection_lock:
            was_active = bool(self.active_mode)
            if attempt_offboard_stop and was_active:
                outcome["offboard_stop"] = await self.stop_offboard_mode()

            self._advance_connection_generation()
            self.active_mode = False
            self._connection_state = "disconnecting"
            try:
                outcome["connection_monitor_stopped"] = (
                    await self._cancel_connection_monitor_task()
                )
            finally:
                cleanup_task = asyncio.create_task(
                    self._cancel_telemetry_update_task(),
                    name="PixEaglePX4TelemetryStop",
                )
                try:
                    outcome["telemetry_stopped"] = await asyncio.shield(cleanup_task)
                except asyncio.CancelledError:
                    outcome["telemetry_stopped"] = await cleanup_task
                    raise
                finally:
                    owned_tasks = self._get_owned_task_status()
                    cleanup_failed = (
                        not outcome["connection_monitor_stopped"]
                        or not outcome["telemetry_stopped"]
                        or not owned_tasks["all_stopped"]
                    )
                    outcome["cleanup_failed"] = cleanup_failed
                    outcome["owned_tasks"] = owned_tasks
                    self._cleanup_failed = cleanup_failed
                    if cleanup_failed:
                        self._connection_state = "cleanup_failed"
                        self._last_connection_error = (
                            "PX4 shutdown deadline expired while owned tasks remained alive"
                        )
                        self._telemetry_worker_failed = True
                        self._last_telemetry_error = self._last_connection_error
                        self._set_telemetry_state("cleanup_failed")
                        outcome["status"] = "cleanup_failed"
                    else:
                        self._connection_state = "disconnected"
                        self._last_connection_error = None
                        self._set_telemetry_state("stopped")
                        self._telemetry_source_active = None
                        outcome["status"] = "disconnected"
        if outcome["cleanup_failed"]:
            logger.error("PX4 shutdown incomplete; owned tasks remain alive")
        else:
            logger.info("Disconnected from the drone.")
        return outcome

    def get_flight_mode_text(self, mode_code):
        """
        Convert the flight mode code to a text label.
        """
        return self.FLIGHT_MODES.get(mode_code, f"Unknown ({mode_code})")
    
    async def trigger_return_to_launch(self) -> PX4ActionOutcome:
        """
        Send Return to Launch as a failsafe action
        """
        gate_decision = _evaluate_px4_command_gate("return_to_launch", action="RTL")
        if gate_decision.blocked:
            logger.info("Return to Launch intercepted by PX4 command gate: %s", gate_decision.reason)
            return _blocked_action_outcome(
                "return_to_launch",
                gate_decision,
                step="Return to Launch intercepted by PX4 command gate",
            )

        if not self.active_mode:
            error = "Cannot request Return to Launch without a confirmed MAVSDK vehicle link"
            logger.error(error)
            return _px4_action_outcome(
                "return_to_launch",
                status="blocked",
                reason="mavsdk_not_connected",
                errors=[error],
                degraded=True,
            )

        try:
            await asyncio.wait_for(
                self.drone.action.return_to_launch(),
                timeout=self.get_mavsdk_command_timeout_s(),
            )
        except asyncio.TimeoutError:
            error = (
                "Return to Launch acknowledgement exceeded "
                f"{self.get_mavsdk_command_timeout_s():.2f} s"
            )
            logger.error(error)
            return _px4_action_outcome(
                "return_to_launch",
                status="failed",
                reason="mavsdk_action_timeout",
                errors=[error],
                degraded=True,
            )
        except Exception as exc:
            error = f"Return to Launch request failed: {exc}"
            logger.error(error)
            return _px4_action_outcome(
                "return_to_launch",
                status="failed",
                reason="mavsdk_action_failed",
                errors=[error],
                degraded=True,
            )

        logger.info("Return to Launch command acknowledged.")
        return _px4_action_outcome(
            "return_to_launch",
            status="executed",
            reason="mavsdk_action_acknowledged",
            steps=["Return to Launch command acknowledged."],
        )

    async def trigger_failsafe(self) -> PX4ActionOutcome:
        logging.critical("Initiating Return to Launch due to altitude safety violation")
        return await self.trigger_return_to_launch()
        
    async def send_commands_unified(self):
        """
        Unified command dispatcher that automatically selects the appropriate 
        MAVSDK method based on the current follower's control type from schema.
        """
        try:
            disconnect_error = self._validation_mavsdk_disconnect_error()
            if disconnect_error:
                logger.error("MAVSDK command dispatch blocked: %s", disconnect_error)
                return False

            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized")
                return False
                
            # Get control type from schema
            control_type = self.setpoint_handler.get_control_type()
            
            # Dispatch to appropriate method
            if control_type == 'attitude_rate':
                return await self.send_attitude_rate_commands()
            elif control_type == 'velocity_body_offboard':
                return await self.send_velocity_body_offboard_commands()
            else:
                logger.error(f"Unknown control type from schema: {control_type}")
                return False
            
        except Exception as e:
            logger.error(f"Error in unified command dispatch: {e}")
            return False

    async def send_attitude_rate_commands(self):
        """
        Enhanced schema-aware attitude rate command sender.
        Only sends attitude rate commands if the current profile supports them.

        Uses deg/s field names directly (MAVSDK standard):
        - rollspeed_deg_s, pitchspeed_deg_s, yawspeed_deg_s
        Values are already in deg/s - no conversion needed.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized")
                return False

            control_type = self.setpoint_handler.get_control_type()
            if control_type != 'attitude_rate':
                logger.error(
                    "Refusing attitude_rate command for control type %s",
                    control_type,
                )
                return False

            setpoint = self.setpoint_handler.get_fields()
            if not setpoint:
                logger.error("No setpoint data available")
                return False

            expected_fields = {
                'rollspeed_deg_s',
                'pitchspeed_deg_s',
                'yawspeed_deg_s',
                'thrust',
            }
            actual_fields = set(setpoint)
            if actual_fields != expected_fields:
                logger.error(
                    "Refusing incomplete or mixed attitude_rate snapshot: "
                    "expected=%s actual=%s",
                    sorted(expected_fields),
                    sorted(actual_fields),
                )
                return False

            # Values are already in deg/s; no unit conversion is required here.
            roll_deg_s = float(setpoint['rollspeed_deg_s'])
            pitch_deg_s = float(setpoint['pitchspeed_deg_s'])
            yaw_deg_s = float(setpoint['yawspeed_deg_s'])
            thrust = float(setpoint['thrust'])

            validated = _validate_px4_command_values(
                "attitude_rate",
                rollspeed_deg_s=roll_deg_s,
                pitchspeed_deg_s=pitch_deg_s,
                yawspeed_deg_s=yaw_deg_s,
                thrust=thrust,
            )
            if validated is None:
                return False

            roll_deg_s = validated['rollspeed_deg_s']
            pitch_deg_s = validated['pitchspeed_deg_s']
            yaw_deg_s = validated['yawspeed_deg_s']
            thrust = validated['thrust']

            logger.debug(f"Sending ATTITUDE_RATE (deg/s): Roll={roll_deg_s:.3f}, Pitch={pitch_deg_s:.3f}, Yaw={yaw_deg_s:.3f}, Thrust={thrust:.3f}")

            # Send the attitude rate commands to the drone (values already in deg/s)
            from mavsdk.offboard import AttitudeRate, OffboardError
            next_setpoint = AttitudeRate(roll_deg_s, pitch_deg_s, yaw_deg_s, thrust)
            return await self._safe_mavsdk_call(
                self.drone.offboard.set_attitude_rate,
                next_setpoint,
                _px4_command_type="attitude_rate",
                _px4_command_params={
                    "rollspeed_deg_s": roll_deg_s,
                    "pitchspeed_deg_s": pitch_deg_s,
                    "yawspeed_deg_s": yaw_deg_s,
                    "thrust": thrust,
                },
                _marks_offboard_sender=True,
            )

        except OffboardError as e:
            logger.error(f"MAVSDK offboard attitude rate command failed: {e}")
            return False
        except ValueError as e:
            logger.error(f"Invalid setpoint values for attitude rate command: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in send_attitude_rate_commands: {e}")
            return False

    def validate_setpoint_compatibility(self) -> bool:
        """
        Validates that the current setpoint configuration is compatible 
        with the expected control type.
        
        Returns:
            bool: True if compatible, False otherwise.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized")
                return False
                
            # Validate profile consistency
            if hasattr(self.setpoint_handler, 'validate_profile_consistency'):
                if not self.setpoint_handler.validate_profile_consistency():
                    logger.error("Setpoint profile consistency validation failed")
                    return False
            
            control_type = self.setpoint_handler.get_control_type()
            available_fields = set(self.setpoint_handler.get_fields().keys())
            required_fields = set(
                self.setpoint_handler.profile_config.get('required_fields', [])
            )
            missing_fields = required_fields - available_fields
            if missing_fields:
                logger.error(
                    "Control type %s is missing required command fields: %s",
                    control_type,
                    sorted(missing_fields),
                )
                return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Error validating setpoint compatibility: {e}")
            return False

    def get_command_summary(self) -> dict:
        """
        Returns a summary of the current command configuration for debugging.
        
        Returns:
            dict: Summary of command state and configuration.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                return {'error': 'Setpoint handler not initialized'}
                
            summary = {
                'control_type': self.setpoint_handler.get_control_type(),
                'profile_name': self.setpoint_handler.get_display_name(),
                'available_fields': list(self.setpoint_handler.get_fields().keys()),
                'current_values': self.setpoint_handler.get_fields(),
                'validation_status': self.validate_setpoint_compatibility(),
                'schema_version': getattr(self.setpoint_handler, '_schema_cache', {}).get('schema_version', 'unknown')
            }
            
            return summary
            
        except Exception as e:
            return {'error': f'Failed to generate command summary: {e}'}
