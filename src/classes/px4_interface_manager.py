import asyncio
import math
import logging
import time
from typing import NamedTuple
from mavsdk import System
from classes.parameters import Parameters
from mavsdk.offboard import OffboardError, VelocityNedYaw, VelocityBodyYawspeed, AttitudeRate
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


def _should_block_px4_command(command_type: str, **params) -> bool:
    """Compatibility wrapper for callers that only need the block flag."""
    return _evaluate_px4_command_gate(command_type, **params).blocked


def _blocked_command_result(decision: PX4CommandGateDecision) -> bool:
    """Return command result for blocked sends: active CB is simulated success, degraded safety is failure."""
    return not decision.degraded

class PX4InterfaceManager:

    DEFAULT_FOLLOWER_DATA_REFRESH_RATE_HZ = 5.0
    MIN_FOLLOWER_DATA_REFRESH_RATE_HZ = 0.1
    MAX_FOLLOWER_DATA_REFRESH_RATE_HZ = 100.0

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

    def __init__(self, app_controller=None):
        """
        Initializes the PX4InterfaceManager and sets up the connection to the PX4 drone.
        Uses MAVSDK for offboard control, and optionally uses MAVLink2Rest for telemetry data.
        """
        self.app_controller = app_controller
        self.current_yaw = 0.0  # Current yaw in radians
        self.current_pitch = 0.0  # Current pitch in radians
        self.current_roll = 0.0  # Current roll in radians
        self.current_altitude = 0.0  # Current altitude in meters
        self.current_ground_speed = 0.0  # Ground speed in m/s
        self.camera_yaw_offset = Parameters.CAMERA_YAW_OFFSET
        self.update_task = None  # Task for telemetry updates
        normalized_profile_name = SetpointHandler.normalize_profile_name(Parameters.FOLLOWER_MODE)
        self.setpoint_handler = SetpointHandler(normalized_profile_name)    
        self.active_mode = False
        self.hover_throttle = 0.0
        self.failsafe_active = False
        self._validation_mavsdk_disconnect_active = False
        self._validation_mavsdk_disconnect_reason = None
        self._validation_mavsdk_disconnect_source = None
        self._validation_mavsdk_disconnect_at_monotonic_s = None
        self._validation_mavsdk_disconnect_count = 0

        # Determine if we are using MAVLink2Rest for telemetry data
        if Parameters.USE_MAVLINK2REST and self.app_controller:
            self.mavlink_data_manager = self.app_controller.mavlink_data_manager
            logger.info("Using MAVLink2Rest for telemetry data.")
        else:
            logger.info("Using MAVSDK for telemetry and offboard control.")
        
        # Setup MAVSDK connection for both telemetry and offboard control
        if Parameters.EXTERNAL_MAVSDK_SERVER:
            self.drone = System(mavsdk_server_address='localhost', port=50051)
        else:
            self.drone = System()
            
            
    async def _safe_mavsdk_call(
        self,
        coro_func,
        *args,
        _px4_command_type="mavsdk_command",
        _px4_command_params=None,
        _px4_gate_checked=False,
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
        disconnect_error = self._validation_mavsdk_disconnect_error()
        if disconnect_error:
            logger.error("Blocking MAVSDK command during validation disconnect: %s", disconnect_error)
            return False

        if not _px4_gate_checked:
            gate_decision = _evaluate_px4_command_gate(
                _px4_command_type,
                blocked_call=f"{coro_func.__name__}({args}, {kwargs})"[:100],
                **(_px4_command_params or {}),
            )
            if gate_decision.blocked:
                return _blocked_command_result(gate_decision)

        try:
            await coro_func(*args, **kwargs)  # Create new coroutine
            return True
        except Exception as e:
            # Check if it's the specific async loop error
            if "attached to a different loop" in str(e):
                logger.debug("Async loop conflict detected, retrying...")
                # Try once more after a brief delay
                try:
                    await asyncio.sleep(0.001)  # 1ms delay
                    await coro_func(*args, **kwargs)  # Create NEW coroutine for retry
                    return True
                except Exception as retry_error:
                    logger.warning(f"MAVSDK call failed after retry: {retry_error}")
                    return False
            else:
                logger.error(f"MAVSDK call error: {e}")
                return False

    async def connect(self):
        """
        Connects to the drone using MAVSDK and starts telemetry updates.
        Even when using MAVLink2Rest for telemetry, MAVSDK is still used for offboard control.
        """
        # SAFETY FIRST: Block if circuit breaker active or unavailable
        gate_decision = _evaluate_px4_command_gate("connect", system_address=Parameters.SYSTEM_ADDRESS)
        if gate_decision.blocked:
            self.active_mode = not gate_decision.degraded  # mock active only for normal circuit-breaker testing
            logger.info("Drone connection blocked by PX4 command gate: %s", gate_decision.reason)
            return

        self.clear_validation_mavsdk_disconnect()
        await self.drone.connect(system_address=Parameters.SYSTEM_ADDRESS)
        self.active_mode = True
        logger.info("Connected to the drone.")
        self.update_task = asyncio.create_task(self.update_drone_data())

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
        self.active_mode = False

        task = self.update_task
        if task and not task.done() and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

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
        connected = bool(self.active_mode) and not validation_disconnect
        if validation_disconnect:
            status = "validation_disconnected"
            last_error = self._validation_mavsdk_disconnect_error()
        elif connected:
            status = "connected"
            last_error = None
        else:
            status = "disconnected"
            last_error = None

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
            "system_address": getattr(Parameters, "SYSTEM_ADDRESS", None),
            "uses_mavlink2rest": bool(getattr(Parameters, "USE_MAVLINK2REST", False)),
        }

    async def update_drone_data(self):
        """
        Continuously updates the drone's telemetry data using the selected source.
        Uses MAVLink2Rest for telemetry if enabled, otherwise uses MAVSDK.
        FOLLOWER_DATA_REFRESH_RATE is configured in Hz and converted to seconds
        before sleeping between telemetry polling iterations.
        """
        while self.active_mode:
            try:
                if Parameters.USE_MAVLINK2REST:
                    await self._update_telemetry_via_mavlink2rest()
                else:
                    await self._update_telemetry_via_mavsdk()
            except asyncio.CancelledError:
                logger.warning("Telemetry update task was cancelled.")
                break
            except Exception as e:
                logger.error(f"Error updating telemetry: {e}")
            await asyncio.sleep(self.get_follower_data_refresh_period_s())

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

    async def _update_telemetry_via_mavlink2rest(self):
        """
        Updates telemetry data using MAVLink2Rest.
        Retrieves telemetry data through the MAVLink data manager using modular methods.
        Default values are set to zero in case of data loss or missing data.
        """
        try:
            # Fetch attitude data (roll, pitch, yaw)
            attitude_data = await self.mavlink_data_manager.fetch_attitude_data()
            self.current_roll = attitude_data.get("roll", 0.0)
            self.current_pitch = attitude_data.get("pitch", 0.0)
            self.current_yaw = attitude_data.get("yaw", 0.0)
            
            # Fetch altitude data
            altitude_data = await self.mavlink_data_manager.fetch_altitude_data()
            self.current_altitude = altitude_data.get("altitude_relative", 0.0)  # Or use "altitude_amsl" if required
            self.current_ground_speed = await self.mavlink_data_manager.fetch_ground_speed()

        except Exception as e:
            logger.error(f"Error updating telemetry via MAVLink2Rest: {e}")

    async def _update_telemetry_via_mavsdk(self):
        # NOTE: Circuit breaker does NOT block telemetry reading - only commands
        # Telemetry is data FROM drone, not commands TO drone
        try:
            async for position in self.drone.telemetry.position():
                self.current_altitude = position.relative_altitude_m
            async for attitude in self.drone.telemetry.attitude_euler():
                self.current_yaw = attitude.yaw + self.camera_yaw_offset
                self.current_pitch = attitude.pitch
                self.current_roll = attitude.roll

            async for velocity in self.drone.telemetry.velocity_body():
                self.current_ground_speed = velocity.x_m_s  # Forward speed in m/s

        except Exception as e:
            logger.error(f"Error updating telemetry via MAVSDK: {e}")

    def get_orientation(self):
        """
        Returns the current orientation (yaw, pitch, roll) of the drone.
        """
        return self.current_yaw, self.current_pitch, self.current_roll
    
    def get_ground_speed(self):
        return self.current_ground_speed


    # Removed legacy send_body_velocity_commands; using enhanced version below
            
    async def send_attitude_rate_commands_legacy(self):
        """
        [LEGACY] Sends attitude rate commands to the drone in offboard mode.
        This method uses the old field names (roll_rate, pitch_rate, yaw_rate) in rad/s.
        Prefer the new method which uses deg/s fields directly.
        """
        setpoint = self.setpoint_handler.get_fields()

        try:
            if not isinstance(setpoint, dict):
                logger.error("Setpoint is not a dictionary. Cannot send commands.")
                return

            # Initialize variables to zero for the fields that might not be present
            roll_rate, pitch_rate, yaw_rate, thrust = 0.0, 0.0, 0.0, self.hover_throttle

            # Update values only if they are present in the current profile's setpoints
            roll_rate = float(setpoint.get('roll_rate', 0.0))
            pitch_rate = float(setpoint.get('pitch_rate', 0.0))
            yaw_rate = float(setpoint.get('yaw_rate', 0.0))
            thrust = float(setpoint.get('thrust', self.hover_throttle))

            logger.debug(f"[LEGACY] Setting ATTITUDE_RATE setpoint: Roll Rate={roll_rate}, Pitch Rate={pitch_rate}, Yaw Rate={yaw_rate}, Thrust={thrust}")

            # Circuit breaker check - log instead of executing when testing
            if CIRCUIT_BREAKER_AVAILABLE and FollowerCircuitBreaker.is_active():
                FollowerCircuitBreaker.log_command_instead_of_execute(
                    command_type="attitude_rate_legacy",
                    follower_name="PX4Interface",
                    roll_rate=roll_rate, pitch_rate=pitch_rate, yaw_rate=yaw_rate, thrust=thrust
                )
                return

            # Track allowed command when circuit breaker is inactive
            if CIRCUIT_BREAKER_AVAILABLE:
                FollowerCircuitBreaker.log_command_allowed(
                    command_type="attitude_rate_legacy",
                    follower_name="PX4Interface",
                    roll_rate=roll_rate, pitch_rate=pitch_rate, yaw_rate=yaw_rate, thrust=thrust
                )

            # Convert internal rad/s to MAVSDK degrees/s
            roll_deg_s = math.degrees(roll_rate)
            pitch_deg_s = math.degrees(pitch_rate)
            yaw_deg_s = math.degrees(yaw_rate)

            # Send the attitude rate commands to the drone
            next_setpoint = AttitudeRate(roll_deg_s, pitch_deg_s, yaw_deg_s, thrust)
            await self.drone.offboard.set_attitude_rate(next_setpoint)

        except OffboardError as e:
            logger.error(f"Failed to send offboard attitude rate command: {e}")
        except ValueError as ve:
            logger.error(f"ValueError: An error occurred while processing setpoint: {ve}")
        except Exception as ex:
            logger.error(f"An unexpected error occurred: {ex}")


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
                
            # Verify this is the correct control type
            if self.setpoint_handler.get_control_type() != 'velocity_body_offboard':
                logger.warning(f"Attempting to send velocity_body_offboard commands but control type is: {self.setpoint_handler.get_control_type()}")
                
            setpoint = self.setpoint_handler.get_fields()
            if not setpoint:
                logger.error("No setpoint data available")
                return False

            # Extract body velocity fields with safe defaults
            vel_fwd = float(setpoint.get('vel_body_fwd', 0.0))      # Forward velocity
            vel_right = float(setpoint.get('vel_body_right', 0.0))  # Right velocity  
            vel_down = float(setpoint.get('vel_body_down', 0.0))    # Down velocity
            yawspeed = float(setpoint.get('yawspeed_deg_s', 0.0))   # Yaw speed in deg/s

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

            # Circuit breaker check - log instead of executing when testing
            gate_decision = _evaluate_px4_command_gate("velocity_body_offboard", vel_body_fwd=vel_fwd, vel_body_right=vel_right, vel_body_down=vel_down, yawspeed_deg_s=yawspeed)
            if gate_decision.blocked:
                return _blocked_command_result(gate_decision)

            # Send the velocity commands to the drone using MAVSDK VelocityBodyYawspeed
            # Note: VelocityBodyYawspeed expects (forward, right, down, yawspeed_deg_s)
            next_setpoint = VelocityBodyYawspeed(vel_fwd, vel_right, vel_down, yawspeed)
            return await self._safe_mavsdk_call(
                self.drone.offboard.set_velocity_body,
                next_setpoint,
                _px4_gate_checked=True,
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


    def convert_to_ned(self, vel_x, vel_y, yaw):
        """
        Converts local frame velocities to NED frame using the current yaw.
        """
        ned_vel_x = vel_x * math.cos(yaw) - vel_y * math.sin(yaw)
        ned_vel_y = vel_x * math.sin(yaw) + vel_y * math.cos(yaw)
        return ned_vel_x, ned_vel_y

    async def start_offboard_mode(self):
        """
        Attempts to start offboard mode on the drone using MAVSDK.
        """
        result = {"steps": [], "errors": []}

        disconnect_error = self._validation_mavsdk_disconnect_error()
        if disconnect_error:
            result["errors"].append(disconnect_error)
            logger.error("Cannot start Offboard during validation disconnect: %s", disconnect_error)
            return result

        gate_decision = _evaluate_px4_command_gate("start_offboard_mode", action="start_offboard")
        if gate_decision.blocked:
            result["steps"].append("Offboard mode start intercepted by PX4 command gate")
            if gate_decision.degraded:
                result["errors"].append(f"Offboard mode start blocked: {gate_decision.reason}")
            return result  # Return success without actually starting offboard

        try:
            await self.drone.offboard.start()
            result["steps"].append("Offboard mode started.")
            logger.info("Offboard mode started.")
        except Exception as e:
            result["errors"].append(f"Failed to start offboard mode: {e}")
            logger.error(f"Failed to start offboard mode: {e}")
        return result

    async def stop_offboard_mode(self):
        """
        Stops offboard mode on the drone using MAVSDK.
        """
        disconnect_error = self._validation_mavsdk_disconnect_error()
        if disconnect_error:
            logger.error("Cannot stop Offboard through MAVSDK during validation disconnect: %s", disconnect_error)
            raise RuntimeError(disconnect_error)

        gate_decision = _evaluate_px4_command_gate("stop_offboard_mode", action="stop_offboard")
        if gate_decision.blocked:
            logger.info("Stop offboard mode intercepted by PX4 command gate: %s", gate_decision.reason)
            return

        logger.info("Stopping offboard mode...")
        await self.drone.offboard.stop()

    async def stop(self):
        """
        Stops all operations and disconnects from the drone.
        """
        if self.update_task:
            self.update_task.cancel()
            await self.update_task
        await self.stop_offboard_mode()
        self.active_mode = False
        logger.info("Disconnected from the drone.")

    async def send_initial_setpoint(self):
        """
        Sends an initial setpoint to the drone based on the current profile's control type.
        If the control type is 'velocity_body', send zero velocities.
        If the control type is 'attitude_rate', send zero rates and thrust.
        """
        try:
            control_type = self.app_controller.follower.get_control_type()

            if control_type == 'velocity_body':
                
                logger.debug("Sending initial velocity_body setpoint (all zeros).")
                await self.send_body_velocity_commands()

            elif control_type == 'attitude_rate':
                
                logger.debug("Sending initial attitude_rate setpoint (all zeros).")
                await self.send_attitude_rate_commands()

            else:
                logger.error(f"Unknown control type: {control_type}")
                return

        except Exception as e:
            logger.error(f"Error sending initial setpoint: {e}")


    def update_setpoint(self):
        """
        Updates the current setpoint for the drone.
        """
        self.last_command = self.setpoint_handler

    def get_flight_mode_text(self, mode_code):
        """
        Convert the flight mode code to a text label.
        """
        return self.FLIGHT_MODES.get(mode_code, f"Unknown ({mode_code})")
    
    async def trigger_return_to_launch(self):
        """
        Send Return to Launch as a failsafe action
        """
        gate_decision = _evaluate_px4_command_gate("return_to_launch", action="RTL")
        if gate_decision.blocked:
            logger.info("Return to Launch intercepted by PX4 command gate: %s", gate_decision.reason)
            return

        await self.drone.action.return_to_launch()
        logger.info("Initiating RTL.")

    async def set_hover_throttle(self):
        hover_throttle_raw =await self.mavlink_data_manager.fetch_throttle_percent()
        self.hover_throttle = float(hover_throttle_raw) / 100.0
        
        
    async def trigger_failsafe(self):
        logging.critical("Initiating Return to Launch due to altitude safety violation")
        await self.trigger_return_to_launch()
        
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
            if control_type == 'velocity_body':
                return await self.send_body_velocity_commands()
            elif control_type == 'attitude_rate':
                return await self.send_attitude_rate_commands()
            elif control_type == 'velocity_body_offboard':
                return await self.send_velocity_body_offboard_commands()
            else:
                logger.error(f"Unknown control type from schema: {control_type}")
                return False
            
        except Exception as e:
            logger.error(f"Error in unified command dispatch: {e}")
            return False

    async def send_body_velocity_commands(self):
        """
        Enhanced schema-aware body velocity command sender.
        Only sends velocity commands if the current profile supports them.

        DEPRECATED: This method uses legacy field names (yaw_rate in rad/s).
        Prefer using send_unified_commands() with velocity_body profiles that use
        yawspeed_deg_s directly.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized")
                return False

            # Verify this is the correct control type
            if self.setpoint_handler.get_control_type() != 'velocity_body':
                logger.warning(f"Attempting to send velocity commands but control type is: {self.setpoint_handler.get_control_type()}")

            setpoint = self.setpoint_handler.get_fields()
            if not setpoint:
                logger.error("No setpoint data available")
                return False

            # Extract velocity fields with safe defaults
            vx = float(setpoint.get('vel_x', 0.0))
            vy = float(setpoint.get('vel_y', 0.0))
            vz = float(setpoint.get('vel_z', 0.0))

            # Prefer new deg/s field, fall back to deprecated rad/s field
            if 'yawspeed_deg_s' in setpoint:
                yaw_for_mavsdk = float(setpoint.get('yawspeed_deg_s', 0.0))
            else:
                # DEPRECATED: yaw_rate is in rad/s, needs conversion
                yaw_rate = float(setpoint.get('yaw_rate', 0.0))
                yaw_for_mavsdk = math.degrees(yaw_rate)

            validated = _validate_px4_command_values(
                "velocity_body",
                vel_x=vx,
                vel_y=vy,
                vel_z=vz,
                yawspeed_deg_s=yaw_for_mavsdk,
            )
            if validated is None:
                return False

            vx = validated['vel_x']
            vy = validated['vel_y']
            vz = validated['vel_z']
            yaw_for_mavsdk = validated['yawspeed_deg_s']

            logger.debug(f"Sending VELOCITY_BODY: Vx={vx:.3f}, Vy={vy:.3f}, Vz={vz:.3f}, Yaw_deg_s={yaw_for_mavsdk:.3f}")

            # Circuit breaker check - log instead of executing when testing
            gate_decision = _evaluate_px4_command_gate("velocity_body", vel_x=vx, vel_y=vy, vel_z=vz, yawspeed_deg_s=yaw_for_mavsdk)
            if gate_decision.blocked:
                return _blocked_command_result(gate_decision)

            # Send the velocity commands to the drone
            from mavsdk.offboard import VelocityBodyYawspeed, OffboardError
            next_setpoint = VelocityBodyYawspeed(vx, vy, vz, yaw_for_mavsdk)
            return await self._safe_mavsdk_call(
                self.drone.offboard.set_velocity_body,
                next_setpoint,
                _px4_gate_checked=True,
            )

        except OffboardError as e:
            logger.error(f"MAVSDK offboard velocity command failed: {e}")
            return False
        except ValueError as e:
            logger.error(f"Invalid setpoint values for velocity command: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error in send_body_velocity_commands: {e}")
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

            # Verify this is the correct control type
            if self.setpoint_handler.get_control_type() != 'attitude_rate':
                logger.warning(f"Attempting to send attitude rate commands but control type is: {self.setpoint_handler.get_control_type()}")

            setpoint = self.setpoint_handler.get_fields()
            if not setpoint:
                logger.error("No setpoint data available")
                return False

            # Extract attitude rate fields with deg/s naming convention (MAVSDK standard)
            # Values are already in deg/s - no conversion needed
            roll_deg_s = float(setpoint.get('rollspeed_deg_s', 0.0))
            pitch_deg_s = float(setpoint.get('pitchspeed_deg_s', 0.0))
            yaw_deg_s = float(setpoint.get('yawspeed_deg_s', 0.0))
            thrust = float(setpoint.get('thrust', getattr(self, 'hover_throttle', 0.5)))

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

            # Circuit breaker check - log instead of executing when testing
            gate_decision = _evaluate_px4_command_gate("attitude_rate", rollspeed_deg_s=roll_deg_s, pitchspeed_deg_s=pitch_deg_s, yawspeed_deg_s=yaw_deg_s, thrust=thrust)
            if gate_decision.blocked:
                return _blocked_command_result(gate_decision)

            # Send the attitude rate commands to the drone (values already in deg/s)
            from mavsdk.offboard import AttitudeRate, OffboardError
            next_setpoint = AttitudeRate(roll_deg_s, pitch_deg_s, yaw_deg_s, thrust)
            return await self._safe_mavsdk_call(
                self.drone.offboard.set_attitude_rate,
                next_setpoint,
                _px4_gate_checked=True,
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

    async def send_initial_setpoint(self):
        """
        Enhanced schema-aware initial setpoint sender.
        Automatically determines the correct command type from the schema.
        """
        try:
            if not hasattr(self, 'setpoint_handler') or self.setpoint_handler is None:
                logger.error("Setpoint handler not initialized, cannot send initial setpoint")
                return False
                
            # Get control type directly from setpoint handler schema
            control_type = self.setpoint_handler.get_control_type()

            logger.info(f"Sending initial {control_type} setpoint (all zeros)")

            # Check circuit breaker before attempting any PX4 commands
            gate_decision = _evaluate_px4_command_gate("initial_setpoint", control_type=control_type)
            if gate_decision.blocked:
                logger.info(
                    "[PX4 COMMAND GATE] Initial setpoint send blocked (%s) - control_type: %s",
                    gate_decision.reason,
                    control_type,
                )
                # Still reset setpoints for consistency, but don't send to drone
                self.setpoint_handler.reset_setpoints()
                return _blocked_command_result(gate_decision)

            # Reset all fields to defaults before sending
            self.setpoint_handler.reset_setpoints()
            
            # Send appropriate command type
            if control_type == 'velocity_body':
                success = await self.send_body_velocity_commands()
            elif control_type == 'attitude_rate':
                success = await self.send_attitude_rate_commands()
            elif control_type == 'velocity_body_offboard':
                success = await self.send_velocity_body_offboard_commands()
            else:
                logger.error(f"Unknown control type from schema: {control_type}")
                return False

            if success is False:
                logger.error(f"Initial {control_type} setpoint send failed")
                return False
                
            logger.debug(f"Initial {control_type} setpoint sent successfully")
            return True

        except Exception as e:
            logger.error(f"Error sending initial setpoint: {e}")
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
            
            # Check that we have the required fields for the control type
            control_type = self.setpoint_handler.get_control_type()
            available_fields = set(self.setpoint_handler.get_fields().keys())
            
            if control_type == 'velocity_body':
                # At minimum we need vel_z for any velocity control
                if not any(field in available_fields for field in ['vel_x', 'vel_y', 'vel_z']):
                    logger.error("Velocity control type but no velocity fields available")
                    return False
                    
            elif control_type == 'attitude_rate':
                # At minimum we need thrust for attitude rate control
                if 'thrust' not in available_fields:
                    logger.error("Attitude rate control type but no thrust field available")
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

    # Method to replace update_setpoint for better schema integration
    def update_setpoint_enhanced(self):
        """
        Enhanced setpoint update that validates compatibility and logs status.
        """
        try:
            if not hasattr(self, 'setpoint_handler'):
                logger.error("Setpoint handler not available for update")
                return
                
            # Validate before updating
            if not self.validate_setpoint_compatibility():
                logger.warning("Setpoint compatibility validation failed during update")
                
            # Update the last command reference
            self.last_command = self.setpoint_handler
            
            # Optional: Log current state for debugging
            if hasattr(self, 'debug_mode') and self.debug_mode:
                summary = self.get_command_summary()
                logger.debug(f"Setpoint updated: {summary}")
                
        except Exception as e:
            logger.error(f"Error updating setpoint: {e}")
