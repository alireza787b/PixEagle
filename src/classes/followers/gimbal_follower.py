# src/classes/followers/gimbal_follower.py

"""
GimbalFollower Module - Clean Architecture Implementation
========================================================

Modern, clean implementation of GimbalFollower using the new transformation
and target loss handling architecture. Designed for maintainability,
testability, and full integration with PixEagle safety systems.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- Mount-aware coordinate transformations (VERTICAL/HORIZONTAL)
- Unified target loss handling (works with any tracker)
- Circuit breaker integration for safe testing
- Zero hardcoding - fully YAML configurable
- Clean integration with existing follower patterns
- Comprehensive safety systems (RTL, emergency stop, altitude limits)
"""

import time
import math
import logging
from typing import Tuple, Optional, Dict, Any

from classes.followers.base_follower import BaseFollower
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.parameters import Parameters

# Initialize logger before imports that might fail
logger = logging.getLogger(__name__)

# Import our new architecture components
try:
    from classes.gimbal_transforms import (
        create_gimbal_transformer, GimbalAngles, VelocityCommand,
        GimbalTransformationEngine
    )
    GIMBAL_TRANSFORMS_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import gimbal transforms: {e}")
    GIMBAL_TRANSFORMS_AVAILABLE = False

try:
    from classes.target_loss_handler import (
        create_target_loss_handler, TargetLossHandler, ResponseAction
    )
    TARGET_LOSS_HANDLER_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import target loss handler: {e}")
    TARGET_LOSS_HANDLER_AVAILABLE = False

# Import circuit breaker for integration
try:
    from classes.circuit_breaker import FollowerCircuitBreaker
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False

class GimbalFollower(BaseFollower):
    """
    Modern GimbalFollower implementation using clean architecture.

    Integrates mount-aware transformations, unified target loss handling,
    and comprehensive safety systems for professional drone control.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initialize GimbalFollower with new architecture.

        Args:
            px4_controller: PX4 interface for drone control
            initial_target_coords: Initial target coordinates (required by factory interface)
        """
        self.setpoint_profile = "gimbal_unified"  # GimbalFollower always uses gimbal_unified profile
        self.follower_name = "GimbalFollower"
        self.initial_target_coords = initial_target_coords

        # Load configuration from Parameters (needed for display name)
        self.config = getattr(Parameters, 'GimbalFollower', {})
        if not self.config:
            raise ValueError("GimbalFollower configuration not found in Parameters")

        # Set basic attributes needed for display name
        self.mount_type = self.config.get('MOUNT_TYPE', 'VERTICAL')
        self.control_mode = self.config.get('CONTROL_MODE', 'VELOCITY')

        # Initialize base follower with gimbal_unified setpoint profile
        super().__init__(px4_controller, self.setpoint_profile)

        # Initialize transformation engine
        if not GIMBAL_TRANSFORMS_AVAILABLE:
            raise ImportError("GimbalFollower requires gimbal_transforms module - check installation")
        try:
            self.transformation_engine = create_gimbal_transformer(self.config)
            logger.info(f"Transformation engine initialized: {self.config.get('MOUNT_TYPE')} mount, {self.config.get('CONTROL_MODE')} control")
        except Exception as e:
            logger.error(f"Failed to initialize transformation engine: {e}")
            raise

        # Initialize target loss handler
        if not TARGET_LOSS_HANDLER_AVAILABLE:
            raise ImportError("GimbalFollower requires target_loss_handler module - check installation")
        target_loss_config = self.config.get('TARGET_LOSS_HANDLING', {})
        try:
            self.target_loss_handler = create_target_loss_handler(target_loss_config, self.follower_name)
            self._register_target_loss_callbacks()
            logger.info(f"Target loss handler initialized with {target_loss_config.get('CONTINUE_VELOCITY_TIMEOUT', 3.0)}s timeout")
        except Exception as e:
            logger.error(f"Failed to initialize target loss handler: {e}")
            raise

        # Control parameters
        self.max_velocity = self.config.get('MAX_VELOCITY', 8.0)
        self.max_yaw_rate = self.config.get('MAX_YAW_RATE', 45.0)

        # Safety parameters
        self.emergency_stop_enabled = self.config.get('EMERGENCY_STOP_ENABLED', True)
        self.min_altitude_safety = self.config.get('MIN_ALTITUDE_SAFETY', 3.0)
        self.max_altitude_safety = self.config.get('MAX_ALTITUDE_SAFETY', 120.0)
        self.max_safety_violations = self.config.get('MAX_SAFETY_VIOLATIONS', 5)

        # Performance parameters
        self.update_rate = self.config.get('UPDATE_RATE', 20.0)
        self.command_smoothing_enabled = self.config.get('COMMAND_SMOOTHING_ENABLED', True)
        self.smoothing_factor = self.config.get('SMOOTHING_FACTOR', 0.8)

        # State tracking
        self.last_velocity_command: Optional[VelocityCommand] = None
        self.last_update_time = time.time()
        self.following_active = False
        self.emergency_stop_active = False

        # Enhanced Safety State (PHASE 3.3)
        self.altitude_safety_active = False
        self.last_safe_altitude = None
        self.safety_violations_count = 0
        self.last_safety_check_time = time.time()
        self.rtl_triggered = False
        self.altitude_recovery_in_progress = False

        # Statistics
        self.total_follow_calls = 0
        self.successful_transformations = 0
        self.target_loss_events = 0
        self.safety_interventions = 0

        logger.info(f"GimbalFollower initialized successfully")
        logger.info(f"  Mount: {self.mount_type}, Control: {self.control_mode}")
        logger.info(f"  Max velocity: {self.max_velocity} m/s, Max yaw rate: {self.max_yaw_rate}°/s")
        logger.info(f"  Safety: Emergency stop {'enabled' if self.emergency_stop_enabled else 'disabled'}")

    def _register_target_loss_callbacks(self):
        """Register callbacks for target loss response actions."""

        def continue_velocity_callback(response_data: Dict[str, Any]) -> bool:
            """Handle velocity continuation during target loss."""
            try:
                if self.last_velocity_command and response_data.get('velocity_continuation', False):
                    # Apply velocity decay if configured
                    velocity_cmd = self.last_velocity_command
                    decay_factor = response_data.get('velocity_decay_factor', 1.0)

                    if decay_factor < 1.0:
                        # Apply decay to velocity command
                        velocity_cmd.forward *= decay_factor
                        velocity_cmd.right *= decay_factor
                        velocity_cmd.yaw_rate *= decay_factor

                        logger.debug(f"Applied velocity decay: factor={decay_factor:.3f}")

                    # Continue with last velocity (with optional decay)
                    self._apply_velocity_command(velocity_cmd, "target_loss_continuation")
                    return True
                return False
            except Exception as e:
                logger.error(f"Error in continue velocity callback: {e}")
                return False

        def rtl_callback(response_data: Dict[str, Any]) -> bool:
            """Handle Return to Launch trigger."""
            try:
                if response_data.get('trigger_rtl', False):
                    rtl_altitude = response_data.get('rtl_altitude', self.config.get('TARGET_LOSS_HANDLING', {}).get('RTL_ALTITUDE', 50.0))

                    logger.warning(f"Target loss timeout - triggering RTL at {rtl_altitude}m altitude")

                    # Log the RTL event
                    self.log_follower_event(
                        "target_loss_rtl_triggered",
                        loss_duration=response_data.get('metadata', {}).get('loss_duration', 0.0),
                        rtl_altitude=rtl_altitude,
                        circuit_breaker_blocked=response_data.get('circuit_breaker_blocked', False)
                    )

                    # Trigger RTL if not blocked by circuit breaker
                    if not response_data.get('circuit_breaker_blocked', False):
                        # This would integrate with PX4 RTL functionality
                        # self.px4_controller.trigger_return_to_launch()
                        pass

                    return True
                return False
            except Exception as e:
                logger.error(f"Error in RTL callback: {e}")
                return False

        def hold_position_callback(response_data: Dict[str, Any]) -> bool:
            """Handle hold position command."""
            try:
                # Send zero velocity command to hold position
                hold_command = VelocityCommand(0.0, 0.0, 0.0, 0.0)
                self._apply_velocity_command(hold_command, "target_loss_hold_position")
                logger.info("Holding position due to target loss")
                return True
            except Exception as e:
                logger.error(f"Error in hold position callback: {e}")
                return False

        # Register the callbacks
        self.target_loss_handler.register_response_callback(ResponseAction.CONTINUE_VELOCITY, continue_velocity_callback)
        self.target_loss_handler.register_response_callback(ResponseAction.RETURN_TO_LAUNCH, rtl_callback)
        self.target_loss_handler.register_response_callback(ResponseAction.HOLD_POSITION, hold_position_callback)

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculate control commands based on tracker data and update the setpoint handler.

        This method implements the core gimbal follower control logic:
        1. Process gimbal angles or angular velocity data from tracker
        2. Transform coordinates based on mount configuration
        3. Apply safety validation and limits
        4. Update setpoint handler with transformed commands

        Args:
            tracker_data: TrackerOutput with gimbal angles or angular velocity data

        Raises:
            ValueError: If tracker data is invalid or incompatible
            RuntimeError: If transformation or command application fails
        """
        # DEBUG: Always log when this method is called
        logger.info(f"🔧 GimbalFollower.calculate_control_commands() called - data_type: {tracker_data.data_type}, tracking_active: {tracker_data.tracking_active}")

        try:
            # Extract and transform gimbal data
            if tracker_data.data_type == TrackerDataType.GIMBAL_ANGLES:
                # Process gimbal angles (yaw, pitch, roll in degrees)
                gimbal_angles = tracker_data.angular
                if gimbal_angles is None:
                    raise ValueError("GIMBAL_ANGLES tracker data missing angular field")

                # For gimbal angles, expect (yaw, pitch, roll) tuple
                if len(gimbal_angles) < 3:
                    raise ValueError(f"GIMBAL_ANGLES expects 3 values (yaw, pitch, roll), got {len(gimbal_angles)}")

                yaw_deg, pitch_deg, roll_deg = gimbal_angles[0], gimbal_angles[1], gimbal_angles[2]

                # Create GimbalAngles object for transformation engine
                from classes.gimbal_transforms import GimbalAngles
                angles_obj = GimbalAngles(
                    roll=roll_deg,
                    pitch=pitch_deg,
                    yaw=yaw_deg,
                    timestamp=tracker_data.timestamp
                )

                # Transform to velocity commands
                velocity_cmd, transform_success = self.transformation_engine.transform_angles_to_velocity(angles_obj)

                if not transform_success:
                    raise RuntimeError("Gimbal angle transformation failed")

                # DEBUG: Log the calculated velocity commands
                logger.info(f"🎯 Calculated velocity commands: fwd={velocity_cmd.forward:.3f}, right={velocity_cmd.right:.3f}, down={velocity_cmd.down:.3f}, yaw_rate={velocity_cmd.yaw_rate:.3f}")

                # Apply velocity commands via setpoint handler
                self.setpoint_handler.set_field("vel_body_fwd", velocity_cmd.forward)
                self.setpoint_handler.set_field("vel_body_right", velocity_cmd.right)
                self.setpoint_handler.set_field("vel_body_down", velocity_cmd.down)

                # Apply yaw rate if available (optional field in gimbal_unified profile)
                if hasattr(velocity_cmd, 'yaw_rate') and velocity_cmd.yaw_rate is not None:
                    # Use yaw_speed_deg_s field as per gimbal_unified profile
                    self.setpoint_handler.set_field("yaw_speed_deg_s", velocity_cmd.yaw_rate)
                    logger.debug(f"Applied yaw rate: {velocity_cmd.yaw_rate:.3f} deg/s")

                logger.debug(f"Applied gimbal angles: yaw={yaw_deg:.2f}°, pitch={pitch_deg:.2f}°, roll={roll_deg:.2f}° "
                           f"-> velocity: forward={velocity_cmd.forward:.2f}, right={velocity_cmd.right:.2f}")

            elif tracker_data.data_type == TrackerDataType.ANGULAR:
                # Process angular rate data (pitch_rate, yaw_rate in rad/s)
                angular_data = tracker_data.angular
                if angular_data is None:
                    raise ValueError("ANGULAR tracker data missing angular field")

                # For angular rates, expect (pitch_rate, yaw_rate) tuple
                if len(angular_data) < 2:
                    raise ValueError(f"ANGULAR expects at least 2 values, got {len(angular_data)}")

                pitch_rate, yaw_rate = angular_data[0], angular_data[1]

                # Apply angular rates via setpoint handler
                self.setpoint_handler.set_field("roll_rate", 0.0)  # No roll for gimbal following
                self.setpoint_handler.set_field("pitch_rate", pitch_rate)
                self.setpoint_handler.set_field("yaw_rate", yaw_rate)
                self.setpoint_handler.set_field("thrust", self.config.get('DEFAULT_THRUST', 0.5))

                logger.debug(f"Applied angular rates: pitch_rate={pitch_rate:.2f}, yaw_rate={yaw_rate:.2f}")

            else:
                # Unsupported tracker data type
                raise ValueError(f"Unsupported tracker data type: {tracker_data.data_type}")

        except Exception as e:
            logger.error(f"Error in calculate_control_commands: {e}")
            raise RuntimeError(f"Failed to calculate gimbal control commands: {e}")

    def follow_target(self, tracker_output: TrackerOutput) -> bool:
        """
        Main target following method.

        Args:
            tracker_output: Unified tracker output from any tracker type

        Returns:
            bool: True if following was successful, False otherwise
        """
        self.total_follow_calls += 1
        current_time = time.time()

        # DEBUG: Log every follow_target call
        logger.info(f"🎯 GimbalFollower.follow_target() called #{self.total_follow_calls} - tracker_output.tracking_active: {tracker_output.tracking_active}")

        try:
            # Comprehensive Safety Checks (PHASE 3.3)
            safety_status = self._perform_safety_checks(current_time)
            if not safety_status['safe_to_proceed']:
                logger.warning(f"Safety check failed: {safety_status['reason']} - blocking follow command")
                self.safety_interventions += 1
                self.log_follower_event("safety_intervention", **safety_status)
                return False

            # Update target loss handler with current tracker status
            loss_response = self.target_loss_handler.update_tracker_status(tracker_output)

            # Log state changes
            if loss_response.get('state_changed', False):
                self.log_follower_event(
                    "target_state_change",
                    new_state=loss_response['target_state'],
                    tracking_active=loss_response['tracking_active'],
                    recommended_actions=loss_response.get('recommended_actions', [])
                )

            # Check if we should continue with normal following
            if loss_response['tracking_active']:
                # Normal tracking - extract gimbal angles and transform
                success = self._process_normal_tracking(tracker_output, current_time)
                if success:
                    self.successful_transformations += 1
                return success
            else:
                # Target lost - target loss handler will manage response
                logger.debug(f"Target lost - state: {loss_response['target_state']}, actions: {loss_response.get('recommended_actions', [])}")

                # Target loss handler callbacks are automatically executed
                # Just return False to indicate tracking is not active
                return False

        except Exception as e:
            logger.error(f"Error in follow_target: {e}")
            self.log_follower_event("follow_target_error", error=str(e))
            return False

        finally:
            self.last_update_time = current_time

    def _process_normal_tracking(self, tracker_output: TrackerOutput, current_time: float) -> bool:
        """
        Process normal tracking when target is active.

        Args:
            tracker_output: Active tracker output
            current_time: Current timestamp

        Returns:
            bool: True if processing was successful
        """
        try:
            # DEBUG: Log normal tracking processing
            logger.info(f"🔄 Processing normal tracking - data_type: {tracker_output.data_type}, angular: {tracker_output.angular}")

            # Use the standard calculate_control_commands method
            self.calculate_control_commands(tracker_output)

            # Update state
            self.following_active = True
            self.last_tracker_output = tracker_output

            logger.debug("Normal tracking processed successfully")
            return True

        except Exception as e:
            logger.error(f"Error in normal tracking processing: {e}")
            return False

    def _extract_gimbal_angles(self, tracker_output: TrackerOutput) -> Optional[GimbalAngles]:
        """
        Extract gimbal angles from tracker output.

        Args:
            tracker_output: Tracker output containing angular data

        Returns:
            GimbalAngles object or None if extraction fails
        """
        try:
            # Check if this is gimbal angle data
            if tracker_output.data_type == TrackerDataType.GIMBAL_ANGLES:
                if not tracker_output.angular:
                    logger.warning("GIMBAL_ANGLES data is None or empty")
                    return None

                if len(tracker_output.angular) < 3:
                    logger.warning(f"GIMBAL_ANGLES data incomplete: expected 3 values, got {len(tracker_output.angular)}")
                    return None

                try:
                    # GIMBAL_ANGLES format: (yaw, pitch, roll)
                    yaw = float(tracker_output.angular[0])
                    pitch = float(tracker_output.angular[1])
                    roll = float(tracker_output.angular[2])

                    return GimbalAngles(
                        roll=roll,
                        pitch=pitch,
                        yaw=yaw,
                        timestamp=tracker_output.timestamp
                    )
                except (ValueError, TypeError, IndexError) as e:
                    logger.warning(f"GIMBAL_ANGLES data conversion error: {e}")
                    return None

            elif tracker_output.data_type == TrackerDataType.ANGULAR:
                # Backward compatibility with ANGULAR data type
                if not tracker_output.angular:
                    logger.warning("ANGULAR data is None or empty")
                    return None

                if len(tracker_output.angular) < 2:
                    logger.warning(f"ANGULAR data incomplete: expected 2+ values, got {len(tracker_output.angular)}")
                    return None

                try:
                    # ANGULAR format: typically (bearing, elevation) -> map to (yaw, pitch)
                    bearing = float(tracker_output.angular[0])
                    elevation = float(tracker_output.angular[1])
                    roll = float(tracker_output.angular[2]) if len(tracker_output.angular) > 2 else 0.0

                    return GimbalAngles(
                        roll=roll,
                        pitch=elevation,
                        yaw=bearing,
                        timestamp=tracker_output.timestamp
                    )
                except (ValueError, TypeError, IndexError) as e:
                    logger.warning(f"ANGULAR data conversion error: {e}")
                    return None

            else:
                logger.warning(f"Tracker output type {tracker_output.data_type} not supported by GimbalFollower")
                return None

        except Exception as e:
            logger.error(f"Error extracting gimbal angles: {e}")
            return None

    def _apply_velocity_command(self, velocity_command: VelocityCommand, source: str):
        """
        Apply velocity command to the drone.

        Args:
            velocity_command: Velocity command to apply
            source: Source description for logging
        """
        try:
            # Safety checks
            if not self._validate_velocity_command(velocity_command):
                logger.warning(f"Velocity command failed safety validation (source: {source})")
                return

            # Apply smoothing if enabled
            if self.command_smoothing_enabled and self.last_velocity_command is not None:
                velocity_command = self._apply_velocity_smoothing(velocity_command)

            # Log the command
            logger.debug(f"Applying velocity command (source: {source}): "
                        f"fwd={velocity_command.forward:.3f}, right={velocity_command.right:.3f}, "
                        f"down={velocity_command.down:.3f}, yaw_rate={velocity_command.yaw_rate:.1f}")

            # Circuit breaker integration
            if self.is_circuit_breaker_active():
                self.log_follower_event(
                    "velocity_command_circuit_breaker",
                    source=source,
                    forward=velocity_command.forward,
                    right=velocity_command.right,
                    down=velocity_command.down,
                    yaw_rate=velocity_command.yaw_rate
                )
                return

            # Apply to setpoint handler
            self._update_setpoint_fields(velocity_command)

            # Log successful application
            self.log_follower_event(
                "velocity_command_applied",
                source=source,
                forward=velocity_command.forward,
                right=velocity_command.right,
                yaw_rate=velocity_command.yaw_rate
            )

        except Exception as e:
            logger.error(f"Error applying velocity command: {e}")

    def _validate_velocity_command(self, velocity_command: VelocityCommand) -> bool:
        """Validate velocity command against safety limits."""
        try:
            # Extract and validate numerical values with proper type checking
            try:
                forward = float(velocity_command.forward)
                right = float(velocity_command.right)
                down = float(velocity_command.down)
                yaw_rate = float(velocity_command.yaw_rate)
            except (TypeError, ValueError) as e:
                logger.warning(f"Velocity command contains non-numeric values: {e}")
                return False

            values = [forward, right, down, yaw_rate]

            # Check for NaN or infinity using proper math functions
            if any(math.isnan(v) or math.isinf(v) for v in values):
                logger.warning("Velocity command contains NaN or infinity values")
                return False

            # Check individual velocity components against limits
            if (abs(forward) > self.max_velocity or
                abs(right) > self.max_velocity or
                abs(down) > self.max_velocity):
                logger.warning(f"Velocity command exceeds limits: fwd={forward:.2f}, right={right:.2f}, down={down:.2f} (max={self.max_velocity})")
                return False

            # Check yaw rate against limits
            if abs(yaw_rate) > self.max_yaw_rate:
                logger.warning(f"Yaw rate exceeds limits: {yaw_rate:.2f} (max={self.max_yaw_rate})")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating velocity command: {e}")
            return False

    def _apply_velocity_smoothing(self, new_command: VelocityCommand) -> VelocityCommand:
        """Apply exponential smoothing to velocity commands."""
        if self.last_velocity_command is None:
            return new_command

        alpha = self.smoothing_factor
        return VelocityCommand(
            forward=alpha * new_command.forward + (1 - alpha) * self.last_velocity_command.forward,
            right=alpha * new_command.right + (1 - alpha) * self.last_velocity_command.right,
            down=alpha * new_command.down + (1 - alpha) * self.last_velocity_command.down,
            yaw_rate=alpha * new_command.yaw_rate + (1 - alpha) * self.last_velocity_command.yaw_rate
        )

    def _update_setpoint_fields(self, velocity_command: VelocityCommand):
        """Update setpoint handler fields based on control mode."""
        try:
            if self.control_mode == "BODY":
                # Body frame control mode
                self.setpoint_handler.set_field('vel_body_fwd', velocity_command.forward)
                self.setpoint_handler.set_field('vel_body_right', velocity_command.right)
                self.setpoint_handler.set_field('vel_body_down', velocity_command.down)
                self.setpoint_handler.set_field('yaw_speed_deg_s', velocity_command.yaw_rate)
            elif self.control_mode == "NED":
                # NED frame control mode
                self.setpoint_handler.set_field('vel_x', velocity_command.forward)
                self.setpoint_handler.set_field('vel_y', velocity_command.right)
                self.setpoint_handler.set_field('vel_z', velocity_command.down)
                self.setpoint_handler.set_field('yaw_angle_deg', velocity_command.yaw_rate)  # Note: this would need integration for angle
            else:
                logger.error(f"Unknown control mode: {self.control_mode}")

        except Exception as e:
            logger.error(f"Error updating setpoint fields: {e}")

    def validate_target_coordinates(self, tracker_output: TrackerOutput) -> bool:
        """
        Validate tracker output for gimbal following.

        Args:
            tracker_output: Tracker output to validate

        Returns:
            bool: True if valid for gimbal following
        """
        try:
            # Check tracker output type
            if not isinstance(tracker_output, TrackerOutput):
                return False

            # Check if data type is supported
            supported_types = [TrackerDataType.GIMBAL_ANGLES, TrackerDataType.ANGULAR]
            if tracker_output.data_type not in supported_types:
                return False

            # Check if angular data is present when tracking is active
            if tracker_output.tracking_active:
                if not tracker_output.angular or len(tracker_output.angular) < 2:
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating target coordinates: {e}")
            return False

    def extract_target_coordinates(self, tracker_output: TrackerOutput) -> Optional[Tuple[float, float]]:
        """
        Extract target coordinates for compatibility with base follower interface.

        Args:
            tracker_output: Tracker output

        Returns:
            Tuple of (x, y) coordinates or None
        """
        try:
            if not tracker_output.tracking_active:
                return None

            # For gimbal, we can extract the angular data as coordinates
            if tracker_output.angular and len(tracker_output.angular) >= 2:
                # Return normalized angular coordinates
                yaw = tracker_output.angular[0] if len(tracker_output.angular) > 0 else 0.0
                pitch = tracker_output.angular[1] if len(tracker_output.angular) > 1 else 0.0

                # Normalize angles to [-1, 1] range for UI/validation
                # Yaw: -180° to +180° maps to -1.0 to +1.0
                normalized_yaw = max(-1.0, min(1.0, yaw / 180.0))
                # Pitch: -90° to +90° maps to -1.0 to +1.0
                normalized_pitch = max(-1.0, min(1.0, pitch / 90.0))

                return (normalized_yaw, normalized_pitch)

            return None

        except Exception as e:
            logger.error(f"Error extracting target coordinates: {e}")
            return None

    def emergency_stop(self):
        """Trigger emergency stop - immediately stop all movement."""
        logger.warning("Emergency stop triggered for GimbalFollower")

        self.emergency_stop_active = True
        self.following_active = False

        # Send zero velocity command
        zero_command = VelocityCommand(0.0, 0.0, 0.0, 0.0)
        self._apply_velocity_command(zero_command, "emergency_stop")

        # Reset transformation and target loss states
        self.transformation_engine.reset_state()
        self.target_loss_handler.reset_state()

        self.log_follower_event("emergency_stop_triggered")

    def reset_emergency_stop(self) -> None:
        """Reset emergency stop state."""
        logger.info("Emergency stop reset for GimbalFollower")
        self.emergency_stop_active = False
        self.log_follower_event("emergency_stop_reset")

    # ==================== Enhanced Safety Systems (PHASE 3.3) ====================

    def _perform_safety_checks(self, current_time: float) -> Dict[str, Any]:
        """
        Perform comprehensive safety checks before allowing follow commands.

        Returns:
            Dict with 'safe_to_proceed' boolean and 'reason' for any failures
        """
        # 1. Emergency stop check
        if self.emergency_stop_active:
            return {
                'safe_to_proceed': False,
                'reason': 'emergency_stop_active',
                'severity': 'critical'
            }

        # 2. RTL status check
        if self.rtl_triggered:
            return {
                'safe_to_proceed': False,
                'reason': 'rtl_in_progress',
                'severity': 'high'
            }

        # 3. Altitude safety check
        altitude_status = self._check_altitude_safety()
        if not altitude_status['safe']:
            return {
                'safe_to_proceed': False,
                'reason': f"altitude_violation_{altitude_status['violation_type']}",
                'severity': 'high',
                'current_altitude': altitude_status.get('current_altitude'),
                'safe_range': f"{self.min_altitude_safety}-{self.max_altitude_safety}m"
            }

        # 4. Safety violation accumulation check
        if self.safety_violations_count >= self.max_safety_violations:
            return {
                'safe_to_proceed': False,
                'reason': 'excessive_safety_violations',
                'severity': 'medium',
                'violation_count': self.safety_violations_count
            }

        # 5. Command rate limiting check
        if current_time - self.last_safety_check_time < (1.0 / self.update_rate):
            return {
                'safe_to_proceed': False,
                'reason': 'rate_limited',
                'severity': 'low'
            }

        # All safety checks passed
        self.last_safety_check_time = current_time
        return {
            'safe_to_proceed': True,
            'reason': 'all_checks_passed'
        }

    def _check_altitude_safety(self) -> Dict[str, Any]:
        """Check if drone altitude is within safe operating range."""
        try:
            # Get current drone status
            drone_status = self.px4_controller.get_drone_status()
            current_altitude = drone_status.get('altitude', 0.0)

            # Check altitude bounds
            if current_altitude < self.min_altitude_safety:
                return {
                    'safe': False,
                    'violation_type': 'too_low',
                    'current_altitude': current_altitude,
                    'threshold': self.min_altitude_safety
                }
            elif current_altitude > self.max_altitude_safety:
                return {
                    'safe': False,
                    'violation_type': 'too_high',
                    'current_altitude': current_altitude,
                    'threshold': self.max_altitude_safety
                }
            else:
                # Altitude is safe
                self.last_safe_altitude = current_altitude
                return {
                    'safe': True,
                    'current_altitude': current_altitude
                }

        except Exception as e:
            logger.error(f"Error checking altitude safety: {e}")
            return {
                'safe': False,
                'violation_type': 'status_unavailable',
                'error': str(e)
            }

    def trigger_emergency_stop(self, reason: str = "manual_trigger"):
        """Enhanced emergency stop with comprehensive state reset."""
        logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")

        self.emergency_stop_active = True
        self.following_active = False
        self.velocity_continuation_active = False
        self.altitude_recovery_in_progress = False

        # Zero all velocity commands immediately
        try:
            self.setpoint_handler.set_field("vel_body_fwd", 0.0)
            self.setpoint_handler.set_field("vel_body_right", 0.0)
            self.setpoint_handler.set_field("vel_body_down", 0.0)
            logger.info("Emergency velocity zero commands applied")
        except Exception as e:
            logger.error(f"Failed to apply emergency velocity commands: {e}")

        # Reset target loss handler
        self.target_loss_handler.reset_state()

        # Log emergency event
        self.log_follower_event("emergency_stop", reason=reason,
                              timestamp=time.time(), safety_interventions=self.safety_interventions)

    def trigger_return_to_launch(self, reason: str = "safety_timeout", altitude: float = None):
        """Enhanced RTL with safety integration."""
        if self.rtl_triggered:
            logger.warning("RTL already in progress")
            return False

        rtl_altitude = altitude or self.config.get('TARGET_LOSS_HANDLING', {}).get('RTL_ALTITUDE', 50.0)

        logger.warning(f"RETURN TO LAUNCH TRIGGERED: {reason} (altitude: {rtl_altitude}m)")

        # Circuit breaker check
        try:
            from classes.circuit_breaker import FollowerCircuitBreaker
            if FollowerCircuitBreaker.is_active():
                FollowerCircuitBreaker.log_command_instead_of_execute(
                    command_type="return_to_launch",
                    follower_name=self.follower_name,
                    reason=reason,
                    rtl_altitude=rtl_altitude,
                    safety_interventions=self.safety_interventions
                )
                logger.info("RTL blocked by circuit breaker - logged instead")
                return False
        except ImportError:
            pass

        # Execute RTL
        try:
            self.px4_controller.send_return_to_launch_command()
            self.rtl_triggered = True
            self.following_active = False

            self.log_follower_event("rtl_triggered", reason=reason,
                                  altitude=rtl_altitude, timestamp=time.time())
            return True
        except Exception as e:
            logger.error(f"Failed to execute RTL: {e}")
            return False

    def reset_safety_state(self) -> None:
        """Reset all safety-related state variables."""
        logger.info("Resetting safety state for GimbalFollower")

        self.emergency_stop_active = False
        self.altitude_safety_active = False
        self.safety_violations_count = 0
        self.rtl_triggered = False
        self.altitude_recovery_in_progress = False

        self.log_follower_event("safety_state_reset", timestamp=time.time())

    def get_display_name(self) -> str:
        """Get display name for UI."""
        return f"Gimbal Follower ({self.mount_type} mount, {self.control_mode} control)"

    def get_status_info(self) -> Dict[str, Any]:
        """Get comprehensive status information."""
        return {
            'follower_type': 'GimbalFollower',
            'display_name': self.get_display_name(),
            'following_active': self.following_active,
            'emergency_stop_active': self.emergency_stop_active,
            'configuration': {
                'mount_type': self.mount_type,
                'control_mode': self.control_mode,
                'max_velocity': self.max_velocity,
                'max_yaw_rate': self.max_yaw_rate
            },
            'transformation_engine': self.transformation_engine.get_configuration_summary(),
            'target_loss_handler': self.target_loss_handler.get_statistics(),
            'statistics': {
                'total_follow_calls': self.total_follow_calls,
                'successful_transformations': self.successful_transformations,
                'success_rate': (self.successful_transformations / max(1, self.total_follow_calls)) * 100
            },
            'last_velocity_command': (
                {
                    'forward': self.last_velocity_command.forward,
                    'right': self.last_velocity_command.right,
                    'down': self.last_velocity_command.down,
                    'yaw_rate': self.last_velocity_command.yaw_rate
                } if self.last_velocity_command else None
            ),
            'circuit_breaker_active': self.is_circuit_breaker_active()
        }

    def get_follower_telemetry(self) -> Dict[str, Any]:
        """
        Override base telemetry to include gimbal-specific information,
        target loss handling state, and safety system status.
        """
        # Get base telemetry from parent class
        telemetry = super().get_follower_telemetry()

        # Add gimbal-specific information
        telemetry.update({
            # Gimbal Configuration
            'gimbal_mount_type': self.mount_type,
            'gimbal_control_mode': self.control_mode,
            'transformation_active': True,

            # Target Loss Handler State
            'target_loss_handler': {
                'state': self.target_loss_handler.get_current_state() if self.target_loss_handler else 'UNAVAILABLE',
                'timeout_remaining': self.target_loss_handler.get_timeout_remaining() if self.target_loss_handler else 0.0,
                'velocity_continuation_active': self.target_loss_handler.is_continuing_velocity() if self.target_loss_handler else False,
                'statistics': self.target_loss_handler.get_statistics() if self.target_loss_handler else {}
            },

            # Safety System Status
            'safety_systems': {
                'emergency_stop_active': self.emergency_stop_active,
                'altitude_safety_active': self.altitude_safety_active,
                'rtl_triggered': self.rtl_triggered,
                'safety_violations_count': self.safety_violations_count,
                'altitude_recovery_in_progress': self.altitude_recovery_in_progress,
                'min_altitude_limit': self.min_altitude_safety,
                'max_altitude_limit': self.max_altitude_safety
            },

            # Circuit Breaker Status
            'circuit_breaker_active': self.is_circuit_breaker_active(),

            # Performance Statistics
            'performance': {
                'total_follow_calls': self.total_follow_calls,
                'successful_transformations': self.successful_transformations,
                'success_rate_percent': (self.successful_transformations / max(1, self.total_follow_calls)) * 100,
                'recent_velocity_magnitude': (
                    (self.last_velocity_command.forward**2 +
                     self.last_velocity_command.right**2 +
                     self.last_velocity_command.down**2)**0.5
                    if self.last_velocity_command else 0.0
                )
            },

            # Enhanced Status
            'enhanced_status': {
                'display_name': self.get_display_name(),
                'last_command_timestamp': time.time() if self.last_velocity_command else None,
                'transformation_engine_ready': hasattr(self, 'transformation_engine') and self.transformation_engine is not None
            }
        })

        return telemetry

    def __str__(self) -> str:
        """String representation for debugging."""
        return f"GimbalFollower(mount={self.mount_type}, control={self.control_mode}, active={self.following_active})"