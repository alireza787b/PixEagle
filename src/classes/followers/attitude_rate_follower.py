# src/classes/followers/attitude_rate_follower.py
"""
Attitude Rate Follower Module
=============================

This module implements the AttitudeRateFollower class (formerly ChaseFollower) for
aggressive target following using attitude rate control. It provides dynamic chase
capabilities with coordinated turn control, thrust management, and safety monitoring.

Note: This follower was renamed from ChaseFollower to AttitudeRateFollower to better
describe its control method. The old class name is kept as an alias for backward compatibility.

Project Information:
- Project Name: PixEagle  
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- Attitude rate control (roll, pitch, yaw rates + thrust)
- Coordinated turn dynamics with bank angle calculations
- Adaptive thrust control based on ground speed
- Yaw error threshold checking with dive control
- Altitude safety monitoring and failsafe
- Schema-aware setpoint management
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
import numpy as np
import time
from typing import Tuple, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class AttitudeRateFollower(BaseFollower):
    """
    Advanced attitude rate follower implementing aggressive target following.

    Formerly known as ChaseFollower. Renamed to better describe its control method:
    attitude rate control (roll, pitch, yaw rates + thrust).

    This follower uses roll, pitch, yaw rates, and thrust commands to achieve dynamic chase
    behavior with coordinated turn control. It's designed for scenarios requiring rapid
    response and aggressive following capabilities.

    Control Strategy:
    ================
    - **Yaw Rate Control**: Horizontal target tracking
    - **Pitch Rate Control**: Vertical target tracking (with yaw error gating)
    - **Roll Rate Control**: Coordinated turns based on bank angle calculations
    - **Thrust Control**: Adaptive speed management

    Features:
    =========
    - Coordinated turn dynamics with proper bank angle calculations
    - Yaw error threshold checking to prevent premature diving
    - Adaptive thrust control based on current ground speed
    - Altitude safety monitoring with RTL capability
    - Target loss detection and handling
    - Emergency stop capability
    - Velocity smoothing for smooth rate commands
    - Schema-aware field validation and management

    Safety Features:
    ===============
    - Altitude bounds checking with RTL trigger
    - Target loss detection with safe hover behavior
    - Emergency stop mode for immediate rate zeroing
    - Yaw error gating to ensure proper heading before aggressive maneuvers
    - PID output limiting to prevent excessive control surface deflection
    - Ground speed normalization for consistent thrust response
    """
    
    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the AttitudeRateFollower with schema-aware attitude rate control.

        Args:
            px4_controller: Instance of PX4Controller to control the drone.
            initial_target_coords (Tuple[float, float]): Initial target coordinates for setpoint initialization.

        Raises:
            ValueError: If initial coordinates are invalid or schema initialization fails.
        """
        # Initialize with Attitude Rate Follower profile for attitude rate control
        # Uses chase_follower profile name for backward compatibility with schema
        super().__init__(px4_controller, "chase_follower")
        
        # Validate and store initial target coordinates
        if not self.validate_target_coordinates(initial_target_coords):
            raise ValueError(f"Invalid initial target coordinates: {initial_target_coords}")
        
        self.initial_target_coords = initial_target_coords

        # Get configuration section (like other followers do)
        config = getattr(Parameters, 'CHASE_FOLLOWER', {})

        # Load chase-specific parameters from config
        # Use ENABLE_ prefix for consistency with other followers
        self.yaw_error_check_enabled = config.get('ENABLE_YAW_ERROR_CHECK', config.get('YAW_ERROR_CHECK_ENABLED', True))
        self.altitude_safety_enabled = config.get('ENABLE_ALTITUDE_SAFETY', config.get('ALTITUDE_FAILSAFE_ENABLED', True))
        self.max_pitch_rate = config.get('MAX_PITCH_RATE', 10.0)
        self.max_yaw_rate = config.get('MAX_YAW_RATE', 10.0)
        self.max_roll_rate = config.get('MAX_ROLL_RATE', 20.0)
        self.max_bank_angle = config.get('MAX_BANK_ANGLE', 20.0)
        self.target_speed = config.get('TARGET_SPEED', 60.0)
        self.min_ground_speed = config.get('MIN_GROUND_SPEED', 0.0)
        self.max_ground_speed = config.get('MAX_GROUND_SPEED', 100.0)
        self.min_thrust = config.get('MIN_THRUST', 0.3)
        self.max_thrust = config.get('MAX_THRUST', 1.0)
        self.yaw_error_threshold = config.get('YAW_ERROR_THRESHOLD', 20.0)
        # Use unified limit access (follower-specific overrides global SafetyLimits)
        self.min_altitude_limit = Parameters.get_effective_limit('MIN_ALTITUDE', 'CHASE_FOLLOWER')
        self.max_altitude_limit = Parameters.get_effective_limit('MAX_ALTITUDE', 'CHASE_FOLLOWER')
        self.altitude_check_interval = config.get('ALTITUDE_CHECK_INTERVAL', 0.1)  # 100ms for safety
        self.rtl_on_altitude_violation = config.get('RTL_ON_ALTITUDE_VIOLATION', True)
        self.control_update_rate = config.get('CONTROL_UPDATE_RATE', 20.0)
        self.coordinate_turn_enabled = config.get('ENABLE_COORDINATED_TURN', config.get('COORDINATE_TURN_ENABLED', True))
        self.aggressive_mode = config.get('ENABLE_AGGRESSIVE_MODE', config.get('AGGRESSIVE_MODE', True))

        # Target loss handling parameters (consistent with body_velocity_chase)
        self.target_loss_timeout = config.get('TARGET_LOSS_TIMEOUT', 2.0)
        self.ramp_down_on_target_loss = config.get('RAMP_DOWN_ON_TARGET_LOSS', True)
        self.target_loss_coord_threshold = config.get('TARGET_LOSS_COORDINATE_THRESHOLD', 990)

        # Emergency stop parameters
        self.emergency_stop_enabled = config.get('ENABLE_EMERGENCY_STOP', True)

        # Velocity smoothing parameters
        self.velocity_smoothing_enabled = config.get('ENABLE_VELOCITY_SMOOTHING', True)
        self.smoothing_factor = config.get('SMOOTHING_FACTOR', 0.8)

        # Initialize chase-specific state
        self.dive_started = False
        self.last_bank_angle = 0.0
        self.last_thrust_command = 0.5

        # Target loss state
        self.target_lost = False
        self.target_loss_start_time = None
        self.last_valid_target_coords = None

        # Emergency stop state
        self.emergency_stop_active = False

        # Altitude monitoring state
        self.last_altitude_check_time = 0.0
        self.altitude_violation_count = 0

        # Smoothed commands for velocity smoothing
        self.smoothed_pitch_rate = 0.0
        self.smoothed_yaw_rate = 0.0
        self.smoothed_roll_rate = 0.0
        
        # Initialize PID controllers
        self._initialize_pid_controllers()
        
        # Update telemetry metadata
        self.update_telemetry_metadata('controller_type', 'attitude_rate')
        self.update_telemetry_metadata('chase_mode', 'aggressive')
        self.update_telemetry_metadata('safety_features', ['altitude_safety', 'yaw_error_gating', 'target_loss_handling', 'emergency_stop'])

        logger.info(f"AttitudeRateFollower initialized with attitude rate control")
        logger.info(f"Safety features - Altitude: {self.altitude_safety_enabled}, RTL: {self.rtl_on_altitude_violation}, "
                   f"EmergencyStop: {self.emergency_stop_enabled}")
        logger.debug(f"Initial target coordinates: {initial_target_coords}")
        logger.debug(f"Rate limits - Pitch: {self.max_pitch_rate}°/s, Yaw: {self.max_yaw_rate}°/s, "
                    f"Roll: {self.max_roll_rate}°/s, Bank: {self.max_bank_angle}°")

    def _initialize_pid_controllers(self) -> None:
        """
        Initializes all PID controllers for attitude rate control with proper configuration.

        Creates four PID controllers:
        - Pitch Rate: Vertical target tracking
        - Yaw Rate: Horizontal target tracking
        - Roll Rate: Coordinated turn control
        - Thrust: Speed management

        All angular rate PID gains use deg/s naming convention (MAVSDK standard).

        Raises:
            ValueError: If PID gain configuration is invalid.
        """
        try:
            setpoint_x, setpoint_y = self.initial_target_coords

            # Pitch Rate Controller - Vertical Control (deg/s)
            self.pid_pitch_rate = CustomPID(
                *self._get_pid_gains('pitchspeed_deg_s'),
                setpoint=setpoint_y,
                output_limits=(-self.max_pitch_rate, self.max_pitch_rate)
            )

            # Yaw Rate Controller - Horizontal Control (deg/s)
            self.pid_yaw_rate = CustomPID(
                *self._get_pid_gains('yawspeed_deg_s'),
                setpoint=setpoint_x,
                output_limits=(-self.max_yaw_rate, self.max_yaw_rate)
            )

            # Roll Rate Controller - Coordinated Turn Control (deg/s, setpoint updated dynamically)
            self.pid_roll_rate = CustomPID(
                *self._get_pid_gains('rollspeed_deg_s'),
                setpoint=0.0,  # Updated based on bank angle calculations
                output_limits=(-self.max_roll_rate, self.max_roll_rate)
            )
            
            # Thrust Controller - Speed Management
            target_speed_normalized = self._normalize_speed(self.target_speed)
            self.pid_thrust = CustomPID(
                *self._get_pid_gains('thrust'),
                setpoint=target_speed_normalized,
                output_limits=(self.min_thrust, self.max_thrust)
            )
            
            logger.info("All PID controllers initialized successfully for AttitudeRateFollower")
            logger.debug(f"PID setpoints - Pitch: {setpoint_y}, Yaw: {setpoint_x}, "
                        f"Roll: 0.0, Thrust: {target_speed_normalized:.3f}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PID controllers: {e}")
            raise ValueError(f"PID controller initialization failed: {e}")

    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves PID gains for the specified control axis.

        Args:
            axis (str): Control axis name ('pitchspeed_deg_s', 'yawspeed_deg_s', 'rollspeed_deg_s', 'thrust').

        Returns:
            Tuple[float, float, float]: (P, I, D) gains for the specified axis.

        Raises:
            KeyError: If the specified axis is not configured.
        """
        try:
            gains = Parameters.PID_GAINS[axis]
            return gains['p'], gains['i'], gains['d']
        except KeyError as e:
            logger.error(f"PID gains not found for axis '{axis}': {e}")
            raise KeyError(f"Invalid PID axis '{axis}'. Check Parameters.PID_GAINS configuration.")

    def _update_pid_gains(self) -> None:
        """
        Updates all PID controller gains from current parameter configuration.

        This method should be called when parameters are updated during runtime
        to ensure controllers use the latest gain values.
        """
        try:
            # All angular rate gains use deg/s naming convention
            self.pid_pitch_rate.tunings = self._get_pid_gains('pitchspeed_deg_s')
            self.pid_yaw_rate.tunings = self._get_pid_gains('yawspeed_deg_s')
            self.pid_roll_rate.tunings = self._get_pid_gains('rollspeed_deg_s')
            self.pid_thrust.tunings = self._get_pid_gains('thrust')

            logger.debug("PID gains updated for all AttitudeRateFollower controllers")

        except Exception as e:
            logger.error(f"Failed to update PID gains: {e}")

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculates and sets attitude rate control commands using enhanced tracker data.
        
        This method implements the core chase logic:
        1. Extracts target coordinates from structured data
        2. Updates PID gains
        3. Calculates pitch and yaw rate errors
        4. Computes control outputs
        5. Calculates coordinated turn dynamics
        6. Updates setpoint handler with commands
        
        Args:
            tracker_data (TrackerOutput): Structured tracker data with position and metadata.
            
        Note:
            This method updates the setpoint handler directly and does not return values.
            Control commands are applied via the schema-aware setpoint management system.
        """
        # Extract target coordinates
        target_coords = self.extract_target_coordinates(tracker_data)
        if not target_coords:
            logger.warning("No valid target coordinates in tracker data, skipping control update")
            return
        
        # Validate input coordinates  
        if not self.validate_target_coordinates(target_coords):
            logger.warning(f"Invalid target coordinates: {target_coords}, skipping control update")
            return
        
        # Update PID gains (in case parameters changed)
        self._update_pid_gains()
        
        # Calculate tracking errors
        error_y = (self.pid_pitch_rate.setpoint - target_coords[1]) * (-1)  # Vertical error
        error_x = (self.pid_yaw_rate.setpoint - target_coords[0]) * (+1)   # Horizontal error
        
        # Generate control rates using PID controllers
        pitch_rate = self.pid_pitch_rate(error_y)
        yaw_rate = self.pid_yaw_rate(error_x)
        
        # Get current flight state for advanced control calculations
        current_speed = getattr(self.px4_controller, 'current_ground_speed', 0.0)
        current_roll = getattr(self.px4_controller, 'current_roll', 0.0)
        
        # Calculate adaptive thrust command
        thrust_command = self._calculate_thrust_command(current_speed)
        
        # Apply yaw error gating for pitch and thrust commands
        self._apply_yaw_error_gating(error_x, pitch_rate, thrust_command)
        
        # Calculate coordinated turn dynamics
        roll_rate = self._calculate_coordinated_roll_rate(yaw_rate, current_speed, current_roll)
        
        # Update setpoint handler using schema-aware methods (deg/s field names)
        self.set_command_field('rollspeed_deg_s', roll_rate)
        self.set_command_field('yawspeed_deg_s', yaw_rate)
        
        # Store last commands for telemetry
        self.last_bank_angle = self._calculate_target_bank_angle(yaw_rate, current_speed)
        self.last_thrust_command = thrust_command
        
        # Log control commands for debugging
        logger.debug(f"Chase control commands - Roll: {roll_rate:.2f}°/s, "
                    f"Yaw: {yaw_rate:.2f}°/s, Target bank: {self.last_bank_angle:.1f}°")

    def _calculate_coordinated_roll_rate(self, yaw_rate: float, ground_speed: float, current_roll: float) -> float:
        """
        Calculates roll rate for coordinated turns based on yaw rate and ground speed.
        
        Implements standard coordinated turn equations for aircraft dynamics:
        Bank Angle = arctan((yaw_rate * ground_speed) / g)
        
        Args:
            yaw_rate (float): Commanded yaw rate in degrees/second.
            ground_speed (float): Current ground speed in m/s.
            current_roll (float): Current roll angle in degrees.
            
        Returns:
            float: Commanded roll rate in degrees/second.
        """
        # Convert yaw rate to radians
        yaw_rate_rad = np.deg2rad(yaw_rate)
        
        # Calculate required bank angle for coordinated turn
        target_bank_angle = self._calculate_target_bank_angle(yaw_rate, ground_speed)
        
        # Calculate roll angle error
        bank_angle_error = -1.0 * (target_bank_angle - current_roll)
        
        # Generate roll rate command using PID controller
        roll_rate = self.pid_roll_rate(bank_angle_error)
        
        logger.debug(f"Coordinated turn calculation - Target bank: {target_bank_angle:.1f}°, "
                    f"Current roll: {current_roll:.1f}°, Roll rate: {roll_rate:.2f}°/s")
        
        return roll_rate

    def _calculate_target_bank_angle(self, yaw_rate: float, ground_speed: float) -> float:
        """
        Calculates target bank angle for coordinated turn dynamics.
        
        Args:
            yaw_rate (float): Yaw rate in degrees/second.
            ground_speed (float): Ground speed in m/s.
            
        Returns:
            float: Target bank angle in degrees.
        """
        # Avoid division by zero and limit minimum speed
        safe_speed = max(ground_speed, 1.0)  # Minimum 1 m/s for calculation stability
        
        # Convert to radians for calculation
        yaw_rate_rad = np.deg2rad(yaw_rate)
        
        # Standard coordinated turn equation: bank = arctan((v * ω) / g)
        g = 9.81  # Gravitational acceleration
        target_bank_angle_rad = np.arctan((yaw_rate_rad * safe_speed) / g)
        
        # Convert back to degrees and apply limits
        target_bank_angle = np.rad2deg(target_bank_angle_rad)
        target_bank_angle = np.clip(target_bank_angle, -self.max_bank_angle, self.max_bank_angle)
        
        return target_bank_angle

    def _apply_yaw_error_gating(self, yaw_error: float, pitch_command: float, thrust_command: float) -> None:
        """
        Applies yaw error gating logic to prevent premature diving maneuvers.
        
        This safety feature ensures the aircraft is properly aligned with the target
        before initiating aggressive pitch and thrust commands.
        
        Args:
            yaw_error (float): Current yaw tracking error.
            pitch_command (float): Calculated pitch rate command.
            thrust_command (float): Calculated thrust command.
        """
        if not self.yaw_error_check_enabled:
            # If gating disabled, apply commands directly (deg/s field names)
            self.set_command_field('pitchspeed_deg_s', pitch_command)
            self.set_command_field('thrust', thrust_command)
            self.dive_started = True
            logger.debug("Yaw error gating disabled - applying all commands directly")
            return

        # Check if already in dive mode or yaw error is acceptable
        if self.dive_started or abs(yaw_error) < self.yaw_error_threshold:
            # Apply full control commands (deg/s field names)
            self.set_command_field('pitchspeed_deg_s', pitch_command)
            self.set_command_field('thrust', thrust_command)
            
            if not self.dive_started:
                self.dive_started = True
                logger.info(f"Dive mode activated - yaw error {abs(yaw_error):.1f}° below threshold")
                
            logger.debug(f"Full chase commands applied - Pitch: {pitch_command:.2f}°/s, "
                        f"Thrust: {thrust_command:.3f}")
        else:
            # Hold hover throttle until yaw alignment improves
            hover_throttle = getattr(self.px4_controller, 'hover_throttle', 0.5)
            self.set_command_field('pitchspeed_deg_s', 0.0)  # No pitch until aligned
            self.set_command_field('thrust', hover_throttle)
            
            logger.debug(f"Yaw error {abs(yaw_error):.1f}° exceeds threshold {self.yaw_error_threshold}° - "
                        f"holding hover, pitch disabled")

    def _calculate_thrust_command(self, ground_speed: float) -> float:
        """
        Calculates adaptive thrust command based on current ground speed.
        
        Uses normalized speed error as input to thrust PID controller for
        consistent speed management across different flight conditions.
        
        Args:
            ground_speed (float): Current ground speed in m/s.
            
        Returns:
            float: Thrust command (0.0 to 1.0).
        """
        # Normalize current speed for PID input
        normalized_speed = self._normalize_speed(ground_speed)
        
        # Calculate thrust adjustment using PID controller
        thrust_adjustment = self.pid_thrust(normalized_speed)
        
        # Apply thrust with optional hover throttle offset (currently disabled)
        hover_throttle_offset = 0.0  # Was: self.px4_controller.hover_throttle * 0
        thrust_command = thrust_adjustment + hover_throttle_offset
        
        # Ensure thrust is within valid bounds
        thrust_command = np.clip(thrust_command, self.min_thrust, self.max_thrust)
        
        logger.debug(f"Thrust calculation - Speed: {ground_speed:.1f} m/s, "
                    f"Normalized: {normalized_speed:.3f}, Command: {thrust_command:.3f}")
        
        return thrust_command

    def _normalize_speed(self, speed: float, 
                        min_speed: Optional[float] = None, 
                        max_speed: Optional[float] = None) -> float:
        """
        Normalizes speed value to 0-1 range for consistent PID processing.
        
        Args:
            speed (float): Raw speed value to normalize.
            min_speed (Optional[float]): Minimum speed bound (defaults to Parameters.MIN_GROUND_SPEED).
            max_speed (Optional[float]): Maximum speed bound (defaults to Parameters.MAX_GROUND_SPEED).
            
        Returns:
            float: Normalized speed value clamped to [0.0, 1.0] range.
        """
        # Use parameter defaults if not specified
        min_speed = min_speed if min_speed is not None else self.min_ground_speed
        max_speed = max_speed if max_speed is not None else self.max_ground_speed
        
        # Avoid division by zero
        if max_speed <= min_speed:
            logger.warning(f"Invalid speed bounds: min={min_speed}, max={max_speed}")
            return 0.5  # Safe default
        
        # Normalize and clamp to [0, 1]
        normalized = (speed - min_speed) / (max_speed - min_speed)
        return max(0.0, min(1.0, normalized))

    def _check_altitude_safety(self) -> bool:
        """
        Monitors altitude safety bounds and triggers failsafe if necessary.

        Uses time-based interval checking (like body_velocity_chase) for consistent
        monitoring without overwhelming the system.

        Returns:
            bool: True if altitude is safe, False if failsafe triggered.
        """
        if not self.altitude_safety_enabled:
            return True

        try:
            current_time = time.time()

            # Only check at configured interval
            if current_time - self.last_altitude_check_time < self.altitude_check_interval:
                return True
            self.last_altitude_check_time = current_time

            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)
            min_altitude = self.min_altitude_limit
            max_altitude = self.max_altitude_limit

            # Check altitude bounds
            if current_altitude < min_altitude or current_altitude > max_altitude:
                self.altitude_violation_count += 1
                logger.critical(f"ALTITUDE SAFETY VIOLATION! Current: {current_altitude:.1f}m, "
                              f"Limits: [{min_altitude}-{max_altitude}]m, "
                              f"Violation count: {self.altitude_violation_count}")

                # Trigger RTL if enabled (consistent with body_velocity_chase)
                if self.rtl_on_altitude_violation:
                    logger.critical("Triggering Return to Launch due to altitude violation")
                    try:
                        # Actually trigger RTL via PX4 controller
                        if self.px4_controller and hasattr(self.px4_controller, 'trigger_return_to_launch'):
                            import asyncio
                            try:
                                loop = asyncio.get_running_loop()
                                asyncio.create_task(self.px4_controller.trigger_return_to_launch())
                            except RuntimeError:
                                # No running loop - create new one
                                asyncio.run(self.px4_controller.trigger_return_to_launch())
                            logger.critical("RTL command issued successfully")
                        else:
                            logger.error("PX4 controller not available for RTL - emergency stop only")
                    except Exception as rtl_error:
                        logger.error(f"Failed to trigger RTL: {rtl_error}")

                # Activate emergency stop
                self.emergency_stop_active = True
                self.update_telemetry_metadata('safety_violation', 'altitude_bounds')
                return False

            return True

        except Exception as e:
            logger.error(f"Altitude safety check failed: {e}")
            return True  # Fail safe - allow operation if check fails

    def _handle_target_loss(self, target_coords: Tuple[float, float]) -> bool:
        """
        Handles target loss detection and recovery logic.

        Consistent with body_velocity_chase implementation for unified behavior.

        Args:
            target_coords (Tuple[float, float]): Current target coordinates.

        Returns:
            bool: True if target is valid, False if target is lost.
        """
        try:
            current_time = time.time()

            # Check if target coordinates indicate a lost target
            threshold = self.target_loss_coord_threshold
            is_valid_target = (
                self.validate_target_coordinates(target_coords) and
                not (np.isnan(target_coords[0]) or np.isnan(target_coords[1])) and
                not (abs(target_coords[0]) > threshold or abs(target_coords[1]) > threshold)
            )

            if is_valid_target:
                # Target is valid - reset loss tracking
                if self.target_lost:
                    logger.info("Target recovered after loss")
                self.target_lost = False
                self.target_loss_start_time = None
                self.last_valid_target_coords = target_coords
                return True
            else:
                # Target appears to be lost
                if not self.target_lost:
                    # Just lost the target
                    self.target_lost = True
                    self.target_loss_start_time = current_time
                    logger.warning(f"Target lost at coordinates: {target_coords}")
                else:
                    # Target has been lost for some time
                    loss_duration = current_time - self.target_loss_start_time
                    timeout = self.target_loss_timeout

                    if loss_duration > timeout:
                        logger.debug(f"Target lost for {loss_duration:.1f}s (timeout: {timeout}s)")

                return False

        except Exception as e:
            logger.error(f"Error in target loss handling: {e}")
            return False

    def activate_emergency_stop(self) -> None:
        """
        Activates emergency stop mode, zeroing all control commands.

        When activated, all attitude rate commands are set to zero until
        explicitly deactivated. Provides consistent behavior with other followers.
        """
        if not self.emergency_stop_enabled:
            logger.warning("Emergency stop requested but not enabled in config")
            return

        self.emergency_stop_active = True

        # Zero all commands
        self.set_command_field('pitchspeed_deg_s', 0.0)
        self.set_command_field('yawspeed_deg_s', 0.0)
        self.set_command_field('rollspeed_deg_s', 0.0)
        # Hold current thrust (hover)
        hover_throttle = getattr(self.px4_controller, 'hover_throttle', 0.5)
        self.set_command_field('thrust', hover_throttle)

        self.update_telemetry_metadata('emergency_stop_active', True)
        logger.critical("EMERGENCY STOP ACTIVATED - All attitude rates zeroed")

    def deactivate_emergency_stop(self) -> None:
        """
        Deactivates emergency stop mode, allowing normal control to resume.

        Resets the emergency stop flag and clears violation counts.
        """
        if self.emergency_stop_active:
            self.emergency_stop_active = False
            self.altitude_violation_count = 0

            self.update_telemetry_metadata('emergency_stop_active', False)
            logger.info("Emergency stop deactivated - Normal control resumed")

    def _apply_velocity_smoothing(self, pitch_rate: float, yaw_rate: float, roll_rate: float) -> Tuple[float, float, float]:
        """
        Applies exponential moving average smoothing to rate commands.

        Args:
            pitch_rate (float): Raw pitch rate command (deg/s).
            yaw_rate (float): Raw yaw rate command (deg/s).
            roll_rate (float): Raw roll rate command (deg/s).

        Returns:
            Tuple[float, float, float]: Smoothed (pitch, yaw, roll) rates.
        """
        if not self.velocity_smoothing_enabled:
            return pitch_rate, yaw_rate, roll_rate

        alpha = self.smoothing_factor

        self.smoothed_pitch_rate = alpha * self.smoothed_pitch_rate + (1 - alpha) * pitch_rate
        self.smoothed_yaw_rate = alpha * self.smoothed_yaw_rate + (1 - alpha) * yaw_rate
        self.smoothed_roll_rate = alpha * self.smoothed_roll_rate + (1 - alpha) * roll_rate

        return self.smoothed_pitch_rate, self.smoothed_yaw_rate, self.smoothed_roll_rate

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Executes target following with chase control logic using enhanced tracker schema.

        This is the main entry point for chase following behavior. It performs
        compatibility validation, safety checks, target loss handling, and calculates
        control commands.

        Args:
            tracker_data (TrackerOutput): Structured tracker data with position and metadata.

        Returns:
            bool: True if following executed successfully, False otherwise.
        """
        try:
            # Check emergency stop first
            if self.emergency_stop_active:
                logger.debug("Emergency stop active - skipping control update")
                return False

            # Validate tracker compatibility
            if not self.validate_tracker_compatibility(tracker_data):
                logger.error("Tracker data incompatible with AttitudeRateFollower")
                return False

            # Extract target coordinates
            target_coords = self.extract_target_coordinates(tracker_data)
            if not target_coords:
                logger.warning("No valid target coordinates found in tracker data")
                return False

            # Handle target loss detection
            if not self._handle_target_loss(target_coords):
                # Target is lost - apply safe behavior
                if self.ramp_down_on_target_loss:
                    # Zero rates and hold hover throttle
                    self.set_command_field('pitchspeed_deg_s', 0.0)
                    self.set_command_field('yawspeed_deg_s', 0.0)
                    self.set_command_field('rollspeed_deg_s', 0.0)
                    hover_throttle = getattr(self.px4_controller, 'hover_throttle', 0.5)
                    self.set_command_field('thrust', hover_throttle)
                    logger.debug("Target lost - holding hover position")
                return False

            # Validate target coordinates
            if not self.validate_target_coordinates(target_coords):
                logger.warning(f"Invalid target coordinates for chase following: {target_coords}")
                return False

            # Perform altitude safety check
            if not self._check_altitude_safety():
                logger.error("Altitude safety check failed - aborting chase following")
                return False

            # Calculate and apply control commands using structured data
            self.calculate_control_commands(tracker_data)

            # Update telemetry metadata
            self.update_telemetry_metadata('last_target_coords', target_coords)
            self.update_telemetry_metadata('dive_mode_active', self.dive_started)
            self.update_telemetry_metadata('last_bank_angle', self.last_bank_angle)
            self.update_telemetry_metadata('target_lost', self.target_lost)
            self.update_telemetry_metadata('emergency_stop_active', self.emergency_stop_active)

            logger.debug(f"Chase following executed for target: {target_coords}")
            return True
            
        except Exception as e:
            logger.error(f"Chase following failed: {e}")
            return False

    # ==================== Enhanced Telemetry and Status ====================
    
    def get_chase_status(self) -> Dict[str, Any]:
        """
        Returns comprehensive chase follower status information.
        
        Returns:
            Dict[str, Any]: Detailed status including PID states, safety status, and control state.
        """
        try:
            current_speed = getattr(self.px4_controller, 'current_ground_speed', 0.0)
            current_roll = getattr(self.px4_controller, 'current_roll', 0.0)
            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)
            
            return {
                # Control State
                'dive_started': self.dive_started,
                'last_bank_angle': self.last_bank_angle,
                'last_thrust_command': self.last_thrust_command,
                'normalized_speed': self._normalize_speed(current_speed),

                # Flight State
                'current_ground_speed': current_speed,
                'current_roll_angle': current_roll,
                'current_altitude': current_altitude,

                # Target Loss State
                'target_lost': self.target_lost,
                'target_loss_duration': (time.time() - self.target_loss_start_time) if self.target_loss_start_time else 0.0,

                # Emergency Stop State
                'emergency_stop_active': self.emergency_stop_active,
                'altitude_violation_count': self.altitude_violation_count,

                # PID States
                'pid_states': {
                    'pitch_rate_setpoint': self.pid_pitch_rate.setpoint,
                    'yaw_rate_setpoint': self.pid_yaw_rate.setpoint,
                    'roll_rate_setpoint': self.pid_roll_rate.setpoint,
                    'thrust_setpoint': self.pid_thrust.setpoint,
                },

                # Safety Status
                'altitude_safety_enabled': self.altitude_safety_enabled,
                'yaw_error_gating_enabled': self.yaw_error_check_enabled,
                'rtl_on_altitude_violation': self.rtl_on_altitude_violation,
                'safety_thresholds': {
                    'yaw_error_threshold': self.yaw_error_threshold,
                    'max_bank_angle': self.max_bank_angle,
                    'min_thrust': self.min_thrust,
                    'max_thrust': self.max_thrust,
                    'min_altitude': self.min_altitude_limit,
                    'max_altitude': self.max_altitude_limit,
                },
                'configuration': {
                    'target_speed': self.target_speed,
                    'coordinate_turn_enabled': self.coordinate_turn_enabled,
                    'aggressive_mode': self.aggressive_mode,
                    'control_update_rate': self.control_update_rate,
                    'velocity_smoothing_enabled': self.velocity_smoothing_enabled,
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating chase status: {e}")
            return {'error': str(e)}

    def get_status_report(self) -> str:
        """
        Generates a comprehensive human-readable status report for chase follower.
        
        Returns:
            str: Formatted status report including all chase-specific information.
        """
        try:
            # Get base status from parent class
            base_report = super().get_status_report()
            
            # Add chase-specific status
            chase_status = self.get_chase_status()
            
            chase_report = f"\n{'='*60}\n"
            chase_report += f"Chase Follower Specific Status\n"
            chase_report += f"{'='*60}\n"
            chase_report += f"Dive Mode Active: {'✓' if chase_status.get('dive_started', False) else '✗'}\n"
            chase_report += f"Current Bank Angle: {chase_status.get('last_bank_angle', 0.0):.1f}°\n"
            chase_report += f"Thrust Command: {chase_status.get('last_thrust_command', 0.0):.3f}\n"
            chase_report += f"Ground Speed: {chase_status.get('current_ground_speed', 0.0):.1f} m/s\n"
            chase_report += f"Normalized Speed: {chase_status.get('normalized_speed', 0.0):.3f}\n"
            
            # Target loss status
            chase_report += f"\nTarget Status:\n"
            chase_report += f"  Target Lost: {'✓' if chase_status.get('target_lost', False) else '✗'}\n"
            chase_report += f"  Loss Duration: {chase_status.get('target_loss_duration', 0.0):.1f}s\n"

            # Emergency stop status
            chase_report += f"\nEmergency Status:\n"
            chase_report += f"  Emergency Stop: {'ACTIVE' if chase_status.get('emergency_stop_active', False) else 'Inactive'}\n"
            chase_report += f"  Altitude Violations: {chase_status.get('altitude_violation_count', 0)}\n"

            # Safety status
            chase_report += f"\nSafety Features:\n"
            chase_report += f"  Altitude Safety: {'✓' if chase_status.get('altitude_safety_enabled', False) else '✗'}\n"
            chase_report += f"  RTL on Violation: {'✓' if chase_status.get('rtl_on_altitude_violation', False) else '✗'}\n"
            chase_report += f"  Yaw Error Gating: {'✓' if chase_status.get('yaw_error_gating_enabled', False) else '✗'}\n"
            
            # PID setpoints
            pid_states = chase_status.get('pid_states', {})
            chase_report += f"\nPID Setpoints:\n"
            chase_report += f"  Pitch Rate: {pid_states.get('pitch_rate_setpoint', 0.0):.3f}\n"
            chase_report += f"  Yaw Rate: {pid_states.get('yaw_rate_setpoint', 0.0):.3f}\n"
            chase_report += f"  Roll Rate: {pid_states.get('roll_rate_setpoint', 0.0):.3f}\n"
            chase_report += f"  Thrust: {pid_states.get('thrust_setpoint', 0.0):.3f}\n"
            
            return base_report + chase_report
            
        except Exception as e:
            return f"Error generating chase status report: {e}"

    def reset_chase_state(self) -> None:
        """
        Resets chase-specific state variables to initial conditions.

        Useful for reinitializing after mode switches or error recovery.
        """
        try:
            # Reset control state
            self.dive_started = False
            self.last_bank_angle = 0.0
            self.last_thrust_command = 0.5

            # Reset target loss state
            self.target_lost = False
            self.target_loss_start_time = None
            self.last_valid_target_coords = None

            # Reset emergency stop state
            self.emergency_stop_active = False
            self.altitude_violation_count = 0
            self.last_altitude_check_time = 0.0

            # Reset smoothed commands
            self.smoothed_pitch_rate = 0.0
            self.smoothed_yaw_rate = 0.0
            self.smoothed_roll_rate = 0.0

            # Reset PID integrators to prevent windup
            self.pid_pitch_rate.reset()
            self.pid_yaw_rate.reset()
            self.pid_roll_rate.reset()
            self.pid_thrust.reset()

            # Update telemetry
            self.update_telemetry_metadata('chase_state_reset', datetime.utcnow().isoformat())

            logger.info("Chase follower state reset to initial conditions")

        except Exception as e:
            logger.error(f"Error resetting chase state: {e}")

    # ==================== Backward Compatibility ====================
    
    def initialize_pids(self) -> None:
        """Backward compatibility wrapper for PID initialization."""
        logger.warning("initialize_pids() is deprecated, PID controllers are initialized automatically")
        self._initialize_pid_controllers()
    
    def get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """Backward compatibility wrapper for PID gain access."""
        logger.warning("get_pid_gains() is deprecated, use _get_pid_gains() for internal access")
        return self._get_pid_gains(axis)
    
    def update_pid_gains(self) -> None:
        """Backward compatibility wrapper for PID gain updates."""
        logger.warning("update_pid_gains() is deprecated, gains are updated automatically")
        self._update_pid_gains()
    
    def check_yaw_and_control(self, yaw_error: float, pitch_command: float, thrust_command: float) -> None:
        """Backward compatibility wrapper for yaw error gating."""
        logger.warning("check_yaw_and_control() is deprecated, use _apply_yaw_error_gating()")
        self._apply_yaw_error_gating(yaw_error, pitch_command, thrust_command)
    
    def control_thrust(self, ground_speed: float) -> float:
        """Backward compatibility wrapper for thrust calculation."""
        logger.warning("control_thrust() is deprecated, use _calculate_thrust_command()")
        return self._calculate_thrust_command(ground_speed)
    
    def normalize_speed(self, speed: float, min_speed=None, max_speed=None) -> float:
        """Backward compatibility wrapper for speed normalization."""
        logger.warning("normalize_speed() is deprecated, use _normalize_speed()")
        min_speed = min_speed or self.min_ground_speed
        max_speed = max_speed or self.max_ground_speed
        return self._normalize_speed(speed, min_speed, max_speed)
    
    def check_altitude_safety(self) -> None:
        """Backward compatibility wrapper for altitude safety."""
        logger.warning("check_altitude_safety() is deprecated, use _check_altitude_safety()")
        self._check_altitude_safety()


# Backward compatibility alias - ChaseFollower maps to AttitudeRateFollower
# This allows existing code using ChaseFollower to continue working
ChaseFollower = AttitudeRateFollower