# src/classes/followers/chase_follower.py
"""
Chase Follower Module
=====================

This module implements the ChaseFollower class for aggressive target following using
attitude rate control. It provides dynamic chase capabilities with coordinated turn
control, thrust management, and safety monitoring.

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
from typing import Tuple, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class ChaseFollower(BaseFollower):
    """
    Advanced chase follower implementing aggressive target following using attitude rate control.
    
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
    - Altitude safety monitoring with failsafe capability
    - Schema-aware field validation and management
    
    Safety Features:
    ===============
    - Altitude bounds checking with automatic failsafe
    - Yaw error gating to ensure proper heading before aggressive maneuvers
    - PID output limiting to prevent excessive control surface deflection
    - Ground speed normalization for consistent thrust response
    """
    
    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the ChaseFollower with schema-aware attitude rate control.

        Args:
            px4_controller: Instance of PX4Controller to control the drone.
            initial_target_coords (Tuple[float, float]): Initial target coordinates for setpoint initialization.
            
        Raises:
            ValueError: If initial coordinates are invalid or schema initialization fails.
        """
        # Initialize with Chase Follower profile for attitude rate control
        super().__init__(px4_controller, "Chase Follower")
        
        # Validate and store initial target coordinates
        if not self.validate_target_coordinates(initial_target_coords):
            raise ValueError(f"Invalid initial target coordinates: {initial_target_coords}")
        
        self.initial_target_coords = initial_target_coords
        
        # Initialize chase-specific state
        self.dive_started = False
        self.last_bank_angle = 0.0
        self.last_thrust_command = 0.5
        
        # Initialize PID controllers
        self._initialize_pid_controllers()
        
        # Update telemetry metadata
        self.update_telemetry_metadata('controller_type', 'attitude_rate')
        self.update_telemetry_metadata('chase_mode', 'aggressive')
        self.update_telemetry_metadata('safety_features', ['altitude_failsafe', 'yaw_error_gating'])
        
        logger.info(f"ChaseFollower initialized with attitude rate control")
        logger.debug(f"Initial target coordinates: {initial_target_coords}")

    def _initialize_pid_controllers(self) -> None:
        """
        Initializes all PID controllers for attitude rate control with proper configuration.
        
        Creates four PID controllers:
        - Pitch Rate: Vertical target tracking
        - Yaw Rate: Horizontal target tracking  
        - Roll Rate: Coordinated turn control
        - Thrust: Speed management
        
        Raises:
            ValueError: If PID gain configuration is invalid.
        """
        try:
            setpoint_x, setpoint_y = self.initial_target_coords
            
            # Pitch Rate Controller - Vertical Control
            self.pid_pitch_rate = CustomPID(
                *self._get_pid_gains('pitch_rate'),
                setpoint=setpoint_y,
                output_limits=(-Parameters.MAX_PITCH_RATE, Parameters.MAX_PITCH_RATE)
            )
            
            # Yaw Rate Controller - Horizontal Control
            self.pid_yaw_rate = CustomPID(
                *self._get_pid_gains('yaw_rate'),
                setpoint=setpoint_x,
                output_limits=(-Parameters.MAX_YAW_RATE, Parameters.MAX_YAW_RATE)
            )
            
            # Roll Rate Controller - Coordinated Turn Control (setpoint updated dynamically)
            self.pid_roll_rate = CustomPID(
                *self._get_pid_gains('roll_rate'),
                setpoint=0.0,  # Updated based on bank angle calculations
                output_limits=(-Parameters.MAX_ROLL_RATE, Parameters.MAX_ROLL_RATE)
            )
            
            # Thrust Controller - Speed Management
            target_speed_normalized = self._normalize_speed(Parameters.TARGET_SPEED)
            self.pid_thrust = CustomPID(
                *self._get_pid_gains('thrust'),
                setpoint=target_speed_normalized,
                output_limits=(Parameters.MIN_THRUST, Parameters.MAX_THRUST)
            )
            
            logger.info("All PID controllers initialized successfully for ChaseFollower")
            logger.debug(f"PID setpoints - Pitch: {setpoint_y}, Yaw: {setpoint_x}, "
                        f"Roll: 0.0, Thrust: {target_speed_normalized:.3f}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PID controllers: {e}")
            raise ValueError(f"PID controller initialization failed: {e}")

    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves PID gains for the specified control axis.

        Args:
            axis (str): Control axis name ('pitch_rate', 'yaw_rate', 'roll_rate', 'thrust').

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
            self.pid_pitch_rate.tunings = self._get_pid_gains('pitch_rate')
            self.pid_yaw_rate.tunings = self._get_pid_gains('yaw_rate')
            self.pid_roll_rate.tunings = self._get_pid_gains('roll_rate')
            self.pid_thrust.tunings = self._get_pid_gains('thrust')
            
            logger.debug("PID gains updated for all ChaseFollower controllers")
            
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
        
        # Update setpoint handler using schema-aware methods
        self.set_command_field('roll_rate', roll_rate)
        self.set_command_field('yaw_rate', yaw_rate)
        
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
        target_bank_angle = np.clip(target_bank_angle, -Parameters.MAX_BANK_ANGLE, Parameters.MAX_BANK_ANGLE)
        
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
        if not Parameters.YAW_ERROR_CHECK_ENABLED:
            # If gating disabled, apply commands directly
            self.set_command_field('pitch_rate', pitch_command)
            self.set_command_field('thrust', thrust_command)
            self.dive_started = True
            logger.debug("Yaw error gating disabled - applying all commands directly")
            return
        
        # Check if already in dive mode or yaw error is acceptable
        if self.dive_started or abs(yaw_error) < Parameters.YAW_ERROR_THRESHOLD:
            # Apply full control commands
            self.set_command_field('pitch_rate', pitch_command)
            self.set_command_field('thrust', thrust_command)
            
            if not self.dive_started:
                self.dive_started = True
                logger.info(f"Dive mode activated - yaw error {abs(yaw_error):.1f}° below threshold")
                
            logger.debug(f"Full chase commands applied - Pitch: {pitch_command:.2f}°/s, "
                        f"Thrust: {thrust_command:.3f}")
        else:
            # Hold hover throttle until yaw alignment improves
            hover_throttle = getattr(self.px4_controller, 'hover_throttle', 0.5)
            self.set_command_field('pitch_rate', 0.0)  # No pitch until aligned
            self.set_command_field('thrust', hover_throttle)
            
            logger.debug(f"Yaw error {abs(yaw_error):.1f}° exceeds threshold {Parameters.YAW_ERROR_THRESHOLD}° - "
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
        thrust_command = np.clip(thrust_command, Parameters.MIN_THRUST, Parameters.MAX_THRUST)
        
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
        min_speed = min_speed if min_speed is not None else Parameters.MIN_GROUND_SPEED
        max_speed = max_speed if max_speed is not None else Parameters.MAX_GROUND_SPEED
        
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
        
        Returns:
            bool: True if altitude is safe, False if failsafe triggered.
        """
        if not Parameters.ALTITUDE_FAILSAFE_ENABLED:
            return True
        
        try:
            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)
            min_altitude = getattr(Parameters, 'MIN_DESCENT_HEIGHT', 5.0)
            max_altitude = getattr(Parameters, 'MAX_CLIMB_HEIGHT', 100.0)
            
            # Check altitude bounds
            if current_altitude < min_altitude or current_altitude > max_altitude:
                logger.critical(f"ALTITUDE SAFETY VIOLATION! Current: {current_altitude:.1f}m, "
                              f"Limits: [{min_altitude}-{max_altitude}]m")
                
                # Trigger emergency disconnection
                if hasattr(self.px4_controller, 'app_controller'):
                    self.px4_controller.app_controller.disconnect_px4()
                    
                self.update_telemetry_metadata('safety_violation', 'altitude_bounds')
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Altitude safety check failed: {e}")
            return True  # Fail safe - allow operation if check fails

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Executes target following with chase control logic using enhanced tracker schema.
        
        This is the main entry point for chase following behavior. It performs
        compatibility validation, safety checks, and calculates control commands.
        
        Args:
            tracker_data (TrackerOutput): Structured tracker data with position and metadata.
            
        Returns:
            bool: True if following executed successfully, False otherwise.
        """
        try:
            # Validate tracker compatibility
            if not self.validate_tracker_compatibility(tracker_data):
                logger.error("Tracker data incompatible with ChaseFollower")
                return False
            
            # Extract target coordinates
            target_coords = self.extract_target_coordinates(tracker_data)
            if not target_coords:
                logger.warning("No valid target coordinates found in tracker data")
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
                
                # PID States
                'pid_states': {
                    'pitch_rate_setpoint': self.pid_pitch_rate.setpoint,
                    'yaw_rate_setpoint': self.pid_yaw_rate.setpoint,
                    'roll_rate_setpoint': self.pid_roll_rate.setpoint,
                    'thrust_setpoint': self.pid_thrust.setpoint,
                },
                
                # Safety Status
                'altitude_safety_enabled': Parameters.ALTITUDE_FAILSAFE_ENABLED,
                'yaw_error_gating_enabled': Parameters.YAW_ERROR_CHECK_ENABLED,
                'safety_thresholds': {
                    'yaw_error_threshold': Parameters.YAW_ERROR_THRESHOLD,
                    'max_bank_angle': Parameters.MAX_BANK_ANGLE,
                    'min_thrust': Parameters.MIN_THRUST,
                    'max_thrust': Parameters.MAX_THRUST,
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
            
            # Safety status
            chase_report += f"\nSafety Features:\n"
            chase_report += f"  Altitude Failsafe: {'✓' if chase_status.get('altitude_safety_enabled', False) else '✗'}\n"
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
            self.dive_started = False
            self.last_bank_angle = 0.0
            self.last_thrust_command = 0.5
            
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
        min_speed = min_speed or Parameters.MIN_GROUND_SPEED
        max_speed = max_speed or Parameters.MAX_GROUND_SPEED
        return self._normalize_speed(speed, min_speed, max_speed)
    
    def check_altitude_safety(self) -> None:
        """Backward compatibility wrapper for altitude safety."""
        logger.warning("check_altitude_safety() is deprecated, use _check_altitude_safety()")
        self._check_altitude_safety()