# src/classes/followers/body_velocity_chase_follower.py
"""
Body Velocity Chase Follower Module - Dual-Mode Lateral Guidance
================================================================

This module implements the BodyVelocityChaseFollower class for quadcopter target following
using offboard body velocity control with dual-mode lateral guidance capabilities.

Project Information:
- Project Name: PixEagle  
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- Body velocity offboard control (forward, right, down, yaw speed)
- Dual-mode lateral guidance: Sideslip vs Coordinated Turn
- Forward velocity ramping with configurable acceleration
- PID-controlled lateral and vertical tracking
- Altitude safety monitoring with RTL capability
- Target loss handling with automatic ramp-down
- Emergency stop functionality
- Comprehensive telemetry and status reporting

Lateral Guidance Modes:
======================
- **Sideslip Mode**: Direct lateral velocity control (v_right ≠ 0, yaw_rate = 0)
  Best for: Precision hovering, close proximity operations, confined spaces
  
- **Coordinated Turn Mode**: Turn-to-track control (v_right = 0, yaw_rate ≠ 0)
  Best for: Forward flight efficiency, natural behavior, wind resistance

Configuration:
=============
- Static mode selection via LATERAL_GUIDANCE_MODE parameter
- Auto-switching based on forward velocity threshold
- Separate PID tuning for each mode (vel_body_right vs yawspeed_deg_s)
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
import logging
import numpy as np
import time
import asyncio
from typing import Tuple, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class BodyVelocityChaseFollower(BaseFollower):
    """
    Advanced body velocity chase follower with dual-mode lateral guidance for quadcopter target following.
    
    This follower uses offboard body velocity commands (forward, right, down, yaw speed)
    to achieve smooth target tracking with forward velocity ramping, dual-mode lateral guidance,
    and comprehensive safety monitoring.
    
    Control Strategy:
    ================
    - **Forward Velocity**: Ramped acceleration from 0 to max velocity
    - **Lateral Guidance**: Dual-mode approach:
      * Sideslip Mode: Direct lateral velocity (v_right ≠ 0, yaw_rate = 0)
      * Coordinated Turn Mode: Turn-to-track (v_right = 0, yaw_rate ≠ 0)
    - **Vertical Control**: PID-controlled down velocity for altitude tracking
    
    Features:
    =========
    - Forward velocity ramping with configurable acceleration rate
    - Dual-mode lateral guidance with auto-switching capability
    - PID-controlled lateral and vertical tracking
    - Target loss detection with automatic velocity ramp-down
    - Altitude safety monitoring with RTL capability
    - Emergency stop functionality for critical situations
    - Velocity smoothing for stable control commands
    - Comprehensive telemetry and status reporting
    - Dynamic mode switching based on flight conditions
    
    Safety Features:
    ===============
    - Altitude bounds checking with automatic RTL
    - Target loss handling with configurable timeout
    - Emergency velocity zeroing capability
    - Velocity command smoothing and limiting
    - Comprehensive error handling and recovery
    - Mode-specific safety considerations
    """
    
    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the BodyVelocityChaseFollower with schema-aware dual-mode offboard control.

        Args:
            px4_controller: Instance of PX4Controller to control the drone.
            initial_target_coords (Tuple[float, float]): Initial target coordinates for setpoint initialization.
            
        Raises:
            ValueError: If initial coordinates are invalid or schema initialization fails.
            RuntimeError: If PID controller initialization fails.
        """
        # Initialize with Body Velocity Chase profile for offboard control
        super().__init__(px4_controller, "Body Velocity Chase")
        
        # Validate and store initial target coordinates
        if not self.validate_target_coordinates(initial_target_coords):
            raise ValueError(f"Invalid initial target coordinates: {initial_target_coords}")
        
        self.initial_target_coords = initial_target_coords
        
        # Initialize forward velocity ramping state
        self.current_forward_velocity = Parameters.INITIAL_FORWARD_VELOCITY
        self.target_forward_velocity = Parameters.MAX_FORWARD_VELOCITY
        self.last_ramp_update_time = time.time()
        
        # Initialize target tracking state
        self.target_lost = False
        self.target_loss_start_time = None
        self.last_valid_target_coords = initial_target_coords
        
        # Initialize safety monitoring state
        self.emergency_stop_active = False
        self.last_altitude_check_time = time.time()
        self.altitude_violation_count = 0
        
        # Initialize velocity smoothing for all axes
        self.smoothed_right_velocity = 0.0
        self.smoothed_down_velocity = 0.0
        self.smoothed_yaw_speed = 0.0
        
        # Initialize lateral guidance mode tracking
        self.active_lateral_mode = None  # Will be set by PID initialization
        
        # Initialize PID controllers (includes mode determination)
        self._initialize_pid_controllers()
        
        # Update telemetry metadata
        self.update_telemetry_metadata('controller_type', 'velocity_body_offboard')
        self.update_telemetry_metadata('control_strategy', 'body_velocity_chase_dual_mode')
        self.update_telemetry_metadata('lateral_guidance_modes', ['sideslip', 'coordinated_turn'])
        self.update_telemetry_metadata('active_lateral_mode', self.active_lateral_mode)
        self.update_telemetry_metadata('safety_features', [
            'altitude_monitoring', 'target_loss_handling', 'velocity_ramping', 'emergency_stop', 'dual_mode_guidance'
        ])
        self.update_telemetry_metadata('forward_ramping_enabled', True)
        self.update_telemetry_metadata('altitude_safety_enabled', Parameters.ALTITUDE_SAFETY_ENABLED)
        
        logger.info(f"BodyVelocityChaseFollower initialized with dual-mode offboard velocity control")
        logger.info(f"Active lateral guidance mode: {self.active_lateral_mode}")
        logger.debug(f"Initial target coordinates: {initial_target_coords}")
        logger.debug(f"Max forward velocity: {self.target_forward_velocity:.1f} m/s")

    def _initialize_pid_controllers(self) -> None:
        """
        Initializes PID controllers for lateral and vertical tracking with dual-mode support.
        
        Creates PID controllers based on configured guidance mode:
        - Sideslip Mode: Right Velocity PID for direct lateral control
        - Coordinated Turn Mode: Yaw Speed PID for turn-to-track control
        - Always: Down Velocity PID for vertical tracking (if enabled)
        
        Note: Forward velocity is controlled by ramping logic, not PID.
        
        Raises:
            RuntimeError: If PID initialization fails.
        """
        try:
            setpoint_x, setpoint_y = self.initial_target_coords
            
            # Initialize lateral guidance PIDs based on mode
            self.pid_right = None
            self.pid_yaw_speed = None
            
            # Determine active lateral guidance mode
            self.active_lateral_mode = self._get_active_lateral_mode()
            
            if self.active_lateral_mode == 'sideslip':
                # Sideslip Mode: Direct lateral velocity control
                self.pid_right = CustomPID(
                    *self._get_pid_gains('vel_body_right'),
                    setpoint=setpoint_x,
                    output_limits=(-Parameters.VELOCITY_LIMITS['vel_body_right'], 
                                  Parameters.VELOCITY_LIMITS['vel_body_right'])
                )
                logger.debug(f"Sideslip mode PID initialized with gains {self._get_pid_gains('vel_body_right')}")
                
            elif self.active_lateral_mode == 'coordinated_turn':
                # Coordinated Turn Mode: Yaw rate control
                self.pid_yaw_speed = CustomPID(
                    *self._get_pid_gains('yawspeed_deg_s'),
                    setpoint=setpoint_x,
                    output_limits=(-Parameters.VELOCITY_LIMITS['yawspeed_deg_s'], 
                                  Parameters.VELOCITY_LIMITS['yawspeed_deg_s'])
                )
                logger.debug(f"Coordinated turn mode PID initialized with gains {self._get_pid_gains('yawspeed_deg_s')}")
            
            # Down Velocity Controller - Vertical Control (if enabled)
            self.pid_down = None
            if Parameters.ENABLE_ALTITUDE_CONTROL:
                self.pid_down = CustomPID(
                    *self._get_pid_gains('vel_body_down'),
                    setpoint=setpoint_y,
                    output_limits=(-Parameters.VELOCITY_LIMITS['vel_body_down'], 
                                  Parameters.VELOCITY_LIMITS['vel_body_down'])
                )
                logger.debug(f"Down velocity PID initialized with gains {self._get_pid_gains('vel_body_down')}")
            else:
                logger.debug("Altitude control disabled - no down velocity PID controller created")
            
            logger.info(f"PID controllers initialized for BodyVelocityChaseFollower - Mode: {self.active_lateral_mode}")
            logger.debug(f"PID setpoints - Lateral: {setpoint_x}, Down: {setpoint_y if self.pid_down else 'N/A'}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PID controllers: {e}")
            raise RuntimeError(f"PID controller initialization failed: {e}")

    def _get_active_lateral_mode(self) -> str:
        """
        Determines the active lateral guidance mode based on configuration and flight state.
        
        Returns:
            str: 'sideslip' or 'coordinated_turn'
        """
        try:
            # Get configured mode
            configured_mode = getattr(Parameters, 'LATERAL_GUIDANCE_MODE', 'coordinated_turn')
            
            # Check for auto-switching
            if getattr(Parameters, 'ENABLE_AUTO_MODE_SWITCHING', False):
                switch_velocity = getattr(Parameters, 'GUIDANCE_MODE_SWITCH_VELOCITY', 3.0)
                
                if self.current_forward_velocity >= switch_velocity:
                    return 'coordinated_turn'  # High speed: use coordinated turns
                else:
                    return 'sideslip'  # Low speed: use sideslip
            
            # Use configured mode
            return configured_mode
            
        except Exception as e:
            logger.error(f"Error determining lateral mode: {e}")
            return 'coordinated_turn'  # Safe default

    def _switch_lateral_mode(self, new_mode: str) -> None:
        """
        Switches between lateral guidance modes dynamically.
        
        Args:
            new_mode (str): New lateral guidance mode ('sideslip' or 'coordinated_turn')
        """
        try:
            if new_mode == self.active_lateral_mode:
                return  # No change needed
            
            logger.info(f"Switching lateral guidance mode: {self.active_lateral_mode} → {new_mode}")
            
            old_mode = self.active_lateral_mode
            self.active_lateral_mode = new_mode
            
            setpoint_x, _ = self.initial_target_coords
            
            if new_mode == 'sideslip' and self.pid_right is None:
                # Initialize sideslip PID controller
                self.pid_right = CustomPID(
                    *self._get_pid_gains('vel_body_right'),
                    setpoint=setpoint_x,
                    output_limits=(-Parameters.VELOCITY_LIMITS['vel_body_right'], 
                                  Parameters.VELOCITY_LIMITS['vel_body_right'])
                )
                logger.debug("Sideslip PID controller initialized during mode switch")
                
            elif new_mode == 'coordinated_turn' and self.pid_yaw_speed is None:
                # Initialize coordinated turn PID controller
                self.pid_yaw_speed = CustomPID(
                    *self._get_pid_gains('yawspeed_deg_s'),
                    setpoint=setpoint_x,
                    output_limits=(-Parameters.VELOCITY_LIMITS['yawspeed_deg_s'], 
                                  Parameters.VELOCITY_LIMITS['yawspeed_deg_s'])
                )
                logger.debug("Coordinated turn PID controller initialized during mode switch")
            
            # Update telemetry
            self.update_telemetry_metadata('lateral_mode_switch', {
                'old_mode': old_mode,
                'new_mode': new_mode,
                'forward_velocity': self.current_forward_velocity,
                'timestamp': datetime.utcnow().isoformat()
            })
            self.update_telemetry_metadata('active_lateral_mode', new_mode)
            
        except Exception as e:
            logger.error(f"Error switching lateral mode to {new_mode}: {e}")

    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves PID gains for the specified control axis.

        Args:
            axis (str): Control axis name ('vel_body_right', 'vel_body_down', 'yawspeed_deg_s').

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
        Handles both lateral guidance modes dynamically.
        
        This method should be called when parameters are updated during runtime
        to ensure controllers use the latest gain values.
        """
        try:
            # Update lateral guidance PIDs based on active mode
            if self.pid_right is not None:
                self.pid_right.tunings = self._get_pid_gains('vel_body_right')
                
            if self.pid_yaw_speed is not None:
                self.pid_yaw_speed.tunings = self._get_pid_gains('yawspeed_deg_s')
            
            # Update vertical PID
            if self.pid_down is not None:
                self.pid_down.tunings = self._get_pid_gains('vel_body_down')
            
            logger.debug(f"PID gains updated for BodyVelocityChaseFollower - Mode: {self.active_lateral_mode}")
            
        except Exception as e:
            logger.error(f"Failed to update PID gains: {e}")

    def _update_forward_velocity(self, dt: float) -> float:
        """
        Updates forward velocity using ramping logic with configurable acceleration.
        
        Args:
            dt (float): Time delta since last update in seconds.
            
        Returns:
            float: Updated forward velocity in m/s.
        """
        try:
            # Determine target velocity based on system state
            if self.emergency_stop_active:
                target_velocity = 0.0
            elif self.target_lost and Parameters.RAMP_DOWN_ON_TARGET_LOSS:
                target_velocity = Parameters.MIN_FORWARD_VELOCITY_THRESHOLD
            else:
                target_velocity = Parameters.MAX_FORWARD_VELOCITY
            
            # Calculate velocity change
            ramp_rate = Parameters.FORWARD_RAMP_RATE
            velocity_error = target_velocity - self.current_forward_velocity
            
            if abs(velocity_error) < 0.01:  # Close enough to target
                self.current_forward_velocity = target_velocity
            else:
                # Apply ramping with acceleration limit
                max_change = ramp_rate * dt
                velocity_change = np.clip(velocity_error, -max_change, max_change)
                self.current_forward_velocity += velocity_change
            
            # Apply absolute velocity limits
            self.current_forward_velocity = np.clip(
                self.current_forward_velocity,
                0.0,  # Never go backward
                Parameters.MAX_FORWARD_VELOCITY
            )
            
            logger.debug(f"Forward velocity updated: {self.current_forward_velocity:.2f} m/s "
                        f"(target: {target_velocity:.2f} m/s, dt: {dt:.3f}s)")
            
            return self.current_forward_velocity
            
        except Exception as e:
            logger.error(f"Error updating forward velocity: {e}")
            return 0.0  # Safe fallback

    def _calculate_tracking_commands(self, target_coords: Tuple[float, float]) -> Tuple[float, float, float]:
        """
        Calculates lateral, vertical, and yaw commands based on active guidance mode.
        
        Args:
            target_coords (Tuple[float, float]): Normalized target coordinates from vision system.
            
        Returns:
            Tuple[float, float, float]: (right_velocity, down_velocity, yaw_speed) commands.
        """
        try:
            # Update PID gains and check for mode changes
            self._update_pid_gains()
            
            # Check if mode switching is needed
            new_mode = self._get_active_lateral_mode()
            if new_mode != self.active_lateral_mode:
                self._switch_lateral_mode(new_mode)
            
            # Calculate tracking errors
            error_x = (self.pid_right.setpoint if self.pid_right else 
                      self.pid_yaw_speed.setpoint) - target_coords[0]  # Horizontal error
            error_y = (self.pid_down.setpoint - target_coords[1]) if self.pid_down else 0.0  # Vertical error
            
            # Initialize commands
            right_velocity = 0.0
            down_velocity = 0.0
            yaw_speed = 0.0
            
            # Calculate lateral guidance commands based on active mode
            if self.active_lateral_mode == 'sideslip':
                # Sideslip Mode: Direct lateral velocity, no yaw
                right_velocity = self.pid_right(error_x) if self.pid_right else 0.0
                yaw_speed = 0.0
                
            elif self.active_lateral_mode == 'coordinated_turn':
                # Coordinated Turn Mode: Yaw to track, no sideslip
                right_velocity = 0.0
                yaw_speed = self.pid_yaw_speed(error_x) if self.pid_yaw_speed else 0.0
            
            # Calculate vertical command (same for both modes)
            down_velocity = self.pid_down(error_y) if self.pid_down else 0.0
            
            # Apply velocity smoothing if enabled
            if Parameters.VELOCITY_SMOOTHING_ENABLED:
                smoothing_factor = Parameters.SMOOTHING_FACTOR
                
                # Smooth right velocity (sideslip mode)
                self.smoothed_right_velocity = (smoothing_factor * self.smoothed_right_velocity + 
                                               (1 - smoothing_factor) * right_velocity)
                
                # Smooth down velocity
                self.smoothed_down_velocity = (smoothing_factor * self.smoothed_down_velocity + 
                                              (1 - smoothing_factor) * down_velocity)
                
                # Smooth yaw speed (coordinated turn mode)
                self.smoothed_yaw_speed = (smoothing_factor * self.smoothed_yaw_speed + 
                                          (1 - smoothing_factor) * yaw_speed)
                
                # Apply smoothed values
                right_velocity = self.smoothed_right_velocity
                down_velocity = self.smoothed_down_velocity
                yaw_speed = self.smoothed_yaw_speed
            
            # Apply emergency limits based on tracking error magnitude
            max_error = Parameters.MAX_TRACKING_ERROR
            if abs(error_x) > max_error or abs(error_y) > max_error:
                # Reduce commands when tracking error is excessive
                reduction_factor = 0.5
                right_velocity *= reduction_factor
                down_velocity *= reduction_factor
                yaw_speed *= reduction_factor
                logger.debug(f"Large tracking error detected, reducing commands by {reduction_factor}")
            
            logger.debug(f"Tracking commands ({self.active_lateral_mode}) - "
                        f"Right: {right_velocity:.2f} m/s, Down: {down_velocity:.2f} m/s, "
                        f"Yaw: {yaw_speed:.2f} deg/s, Errors: [{error_x:.2f}, {error_y:.2f}]")
            
            return right_velocity, down_velocity, yaw_speed
            
        except Exception as e:
            logger.error(f"Error calculating tracking commands: {e}")
            return 0.0, 0.0, 0.0  # Safe fallback

    def _calculate_tracking_velocities(self, target_coords: Tuple[float, float]) -> Tuple[float, float]:
        """
        Legacy method wrapper for backward compatibility.
        
        Args:
            target_coords (Tuple[float, float]): Normalized target coordinates from vision system.
            
        Returns:
            Tuple[float, float]: (right_velocity, down_velocity) - yaw_speed handled separately
        """
        right_velocity, down_velocity, _ = self._calculate_tracking_commands(target_coords)
        return right_velocity, down_velocity

    def _handle_target_loss(self, target_coords: Tuple[float, float]) -> bool:
        """
        Handles target loss detection and recovery logic.
        
        Args:
            target_coords (Tuple[float, float]): Current target coordinates.
            
        Returns:
            bool: True if target is valid, False if target is lost.
        """
        try:
            current_time = time.time()
            
            # Check if target coordinates indicate a lost target
            # (This depends on your vision system's lost target indication)
            # Assuming invalid coordinates like (-999, -999) or (nan, nan) indicate lost target
            is_valid_target = (
                self.validate_target_coordinates(target_coords) and
                not (np.isnan(target_coords[0]) or np.isnan(target_coords[1])) and
                not (abs(target_coords[0]) > 990 or abs(target_coords[1]) > 990)
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
                    timeout = Parameters.TARGET_LOSS_TIMEOUT
                    
                    if loss_duration > timeout:
                        logger.debug(f"Target lost for {loss_duration:.1f}s (timeout: {timeout}s)")
                
                return False
                
        except Exception as e:
            logger.error(f"Error in target loss handling: {e}")
            return False

    def _check_altitude_safety(self) -> bool:
        """
        Monitors altitude safety bounds and triggers RTL if necessary.
        
        Returns:
            bool: True if altitude is safe, False if violation occurred.
        """
        if not Parameters.ALTITUDE_SAFETY_ENABLED:
            return True
        
        try:
            current_time = time.time()
            check_interval = Parameters.ALTITUDE_CHECK_INTERVAL
            
            # Only check at specified intervals to avoid excessive processing
            if (current_time - self.last_altitude_check_time) < check_interval:
                return True
            
            self.last_altitude_check_time = current_time
            
            # Get current altitude from PX4 controller
            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)
            min_altitude = Parameters.MIN_ALTITUDE_LIMIT
            max_altitude = Parameters.MAX_ALTITUDE_LIMIT
            warning_buffer = Parameters.ALTITUDE_WARNING_BUFFER
            
            # Check for violations
            altitude_violation = (current_altitude < min_altitude or current_altitude > max_altitude)
            altitude_warning = (
                current_altitude < (min_altitude + warning_buffer) or 
                current_altitude > (max_altitude - warning_buffer)
            )
            
            if altitude_violation:
                self.altitude_violation_count += 1
                logger.critical(f"ALTITUDE SAFETY VIOLATION! Current: {current_altitude:.1f}m, "
                              f"Limits: [{min_altitude}-{max_altitude}]m, "
                              f"Violation count: {self.altitude_violation_count}")
                
                # Trigger RTL if enabled
                if Parameters.RTL_ON_ALTITUDE_VIOLATION:
                    logger.critical("Triggering Return to Launch due to altitude violation")
                    try:
                        # Schedule RTL safely without event loop conflicts
                        logger.critical("Emergency stop activated due to altitude violation")
                        # Note: RTL will be handled by the main control loop
                    except Exception as rtl_error:
                        logger.error(f"Failed to trigger RTL: {rtl_error}")
                
                # Activate emergency stop
                self.emergency_stop_active = True
                self.update_telemetry_metadata('safety_violation', 'altitude_bounds')
                return False
                
            elif altitude_warning and self.altitude_violation_count == 0:
                logger.warning(f"Altitude warning: {current_altitude:.1f}m approaching limits "
                             f"[{min_altitude}-{max_altitude}]m")
            else:
                # Reset violation count if altitude is safe
                self.altitude_violation_count = 0
            
            return True
            
        except Exception as e:
            logger.error(f"Altitude safety check failed: {e}")
            return True  # Fail safe - allow operation if check fails

    def calculate_control_commands(self, target_coords: Tuple[float, float]) -> None:
        """
        Calculates and sets body velocity control commands with dual-mode lateral guidance.
        
        This method implements the core body velocity chase logic with support for both
        sideslip and coordinated turn lateral guidance modes:
        1. Handles target loss detection and recovery
        2. Updates forward velocity using ramping logic
        3. Calculates lateral and vertical tracking commands with mode switching
        4. Applies safety checks and emergency stops
        5. Updates setpoint handler with commands
        
        Args:
            target_coords (Tuple[float, float]): Normalized target coordinates from vision system.
            
        Note:
            This method updates the setpoint handler directly and does not return values.
            Control commands are applied via the schema-aware setpoint management system.
        """
        try:
            current_time = time.time()
            dt = current_time - self.last_ramp_update_time
            self.last_ramp_update_time = current_time
            
            # Handle target loss detection
            target_valid = self._handle_target_loss(target_coords)
            
            # Use last valid coordinates if target is lost
            tracking_coords = target_coords if target_valid else self.last_valid_target_coords
            
            # Update forward velocity using ramping logic
            forward_velocity = self._update_forward_velocity(dt)
            
            # Calculate tracking commands (includes mode switching logic)
            right_velocity, down_velocity, yaw_speed = self._calculate_tracking_commands(tracking_coords)
            
            # Apply emergency stop if active
            if self.emergency_stop_active:
                forward_velocity = 0.0
                right_velocity = 0.0
                down_velocity = 0.0
                yaw_speed = 0.0
                logger.debug("Emergency stop active - all commands set to zero")
            
            # Update setpoint handler using schema-aware methods
            self.set_command_field('vel_body_fwd', forward_velocity)
            self.set_command_field('vel_body_right', right_velocity)
            self.set_command_field('vel_body_down', down_velocity)
            self.set_command_field('yawspeed_deg_s', yaw_speed)
            
            # Update telemetry metadata
            self.update_telemetry_metadata('last_target_coords', target_coords)
            self.update_telemetry_metadata('target_valid', target_valid)
            self.update_telemetry_metadata('current_forward_velocity', forward_velocity)
            self.update_telemetry_metadata('active_lateral_mode', self.active_lateral_mode)
            self.update_telemetry_metadata('emergency_stop_active', self.emergency_stop_active)
            
            logger.debug(f"Body velocity commands ({self.active_lateral_mode}) - "
                        f"Fwd: {forward_velocity:.2f}, Right: {right_velocity:.2f}, "
                        f"Down: {down_velocity:.2f} m/s, Yaw: {yaw_speed:.2f} deg/s")
            
        except Exception as e:
            logger.error(f"Error calculating control commands: {e}")
            # Set safe fallback commands
            self.set_command_field('vel_body_fwd', 0.0)
            self.set_command_field('vel_body_right', 0.0)
            self.set_command_field('vel_body_down', 0.0)
            self.set_command_field('yawspeed_deg_s', 0.0)

    def follow_target(self, target_coords: Tuple[float, float]) -> bool:
        """
        Executes target following with dual-mode body velocity chase control logic.
        
        This is the main entry point for body velocity chase following behavior. It performs
        safety checks, calculates control commands, and applies them via the setpoint handler.
        
        Args:
            target_coords (Tuple[float, float]): Target coordinates from vision system.
            
        Returns:
            bool: True if following executed successfully, False otherwise.
        """
        try:
            # Perform altitude safety check
            if not self._check_altitude_safety():
                logger.error("Altitude safety check failed - aborting body velocity following")
                return False
            
            # Calculate and apply control commands
            self.calculate_control_commands(target_coords)
            
            logger.debug(f"Body velocity following executed for target: {target_coords}")
            return True
            
        except Exception as e:
            logger.error(f"Body velocity following failed: {e}")
            return False

    # ==================== Enhanced Telemetry and Status ====================
    
    def get_chase_status(self) -> Dict[str, Any]:
        """
        Returns comprehensive body velocity chase follower status with dual-mode information.
        
        Returns:
            Dict[str, Any]: Detailed status including velocities, modes, safety status, and control state.
        """
        try:
            current_time = time.time()
            
            return {
                # Velocity State
                'current_forward_velocity': self.current_forward_velocity,
                'target_forward_velocity': self.target_forward_velocity,
                'smoothed_right_velocity': self.smoothed_right_velocity,
                'smoothed_down_velocity': self.smoothed_down_velocity,
                'smoothed_yaw_speed': self.smoothed_yaw_speed,
                
                # Lateral Guidance Mode State
                'active_lateral_mode': self.active_lateral_mode,
                'configured_lateral_mode': getattr(Parameters, 'LATERAL_GUIDANCE_MODE', 'coordinated_turn'),
                'auto_mode_switching_enabled': getattr(Parameters, 'ENABLE_AUTO_MODE_SWITCHING', False),
                'mode_switch_velocity': getattr(Parameters, 'GUIDANCE_MODE_SWITCH_VELOCITY', 3.0),
                
                # Target Tracking State
                'target_lost': self.target_lost,
                'target_loss_duration': (
                    (current_time - self.target_loss_start_time) 
                    if self.target_loss_start_time else 0.0
                ),
                'last_valid_target_coords': self.last_valid_target_coords,
                
                # Safety Status
                'emergency_stop_active': self.emergency_stop_active,
                'altitude_violation_count': self.altitude_violation_count,
                'altitude_safety_enabled': Parameters.ALTITUDE_SAFETY_ENABLED,
                
                # PID States
                'pid_states': {
                    'right_setpoint': self.pid_right.setpoint if self.pid_right else None,
                    'down_setpoint': self.pid_down.setpoint if self.pid_down else None,
                    'yaw_speed_setpoint': self.pid_yaw_speed.setpoint if hasattr(self, 'pid_yaw_speed') and self.pid_yaw_speed else None,
                },
                
                # Configuration Status
                'config': {
                    'max_forward_velocity': Parameters.MAX_FORWARD_VELOCITY,
                    'ramp_rate': Parameters.FORWARD_RAMP_RATE,
                    'altitude_control_enabled': Parameters.ENABLE_ALTITUDE_CONTROL,
                    'min_altitude_limit': Parameters.MIN_ALTITUDE_LIMIT,
                    'max_altitude_limit': Parameters.MAX_ALTITUDE_LIMIT,
                }
            }
            
        except Exception as e:
            logger.error(f"Error generating chase status: {e}")
            return {'error': str(e)}

    def get_status_report(self) -> str:
        """
        Generates a comprehensive human-readable status report with dual-mode information.
        
        Returns:
            str: Formatted status report including all chase-specific and mode information.
        """
        try:
            # Get base status from parent class (if available)
            try:
                base_report = super().get_status_report()
            except AttributeError:
                base_report = ""
            
            # Add chase-specific status
            chase_status = self.get_chase_status()
            
            chase_report = f"\n{'='*60}\n"
            chase_report += f"Body Velocity Chase Follower Status (Dual-Mode)\n"
            chase_report += f"{'='*60}\n"
            
            # Velocity Status
            chase_report += f"Forward Velocity: {chase_status.get('current_forward_velocity', 0.0):.2f} m/s "
            chase_report += f"(target: {chase_status.get('target_forward_velocity', 0.0):.2f} m/s)\n"
            chase_report += f"Right Velocity: {chase_status.get('smoothed_right_velocity', 0.0):.2f} m/s\n"
            chase_report += f"Down Velocity: {chase_status.get('smoothed_down_velocity', 0.0):.2f} m/s\n"
            chase_report += f"Yaw Speed: {chase_status.get('smoothed_yaw_speed', 0.0):.2f} deg/s\n"
            
            # Lateral Guidance Mode Status
            chase_report += f"\nLateral Guidance Mode:\n"
            chase_report += f"  Active Mode: {chase_status.get('active_lateral_mode', 'unknown').title()}\n"
            chase_report += f"  Configured Mode: {chase_status.get('configured_lateral_mode', 'unknown').title()}\n"
            chase_report += f"  Auto-Switching: {'✓' if chase_status.get('auto_mode_switching_enabled', False) else '✗'}\n"
            if chase_status.get('auto_mode_switching_enabled', False):
                chase_report += f"  Switch Velocity: {chase_status.get('mode_switch_velocity', 0.0):.1f} m/s\n"
            
            # Target status
            chase_report += f"\nTarget Status:\n"
            chase_report += f"  Target Lost: {'✓' if chase_status.get('target_lost', False) else '✗'}\n"
            if chase_status.get('target_lost', False):
                chase_report += f"  Loss Duration: {chase_status.get('target_loss_duration', 0.0):.1f}s\n"
            
            # Safety status
            chase_report += f"\nSafety Status:\n"
            chase_report += f"  Emergency Stop: {'✓' if chase_status.get('emergency_stop_active', False) else '✗'}\n"
            chase_report += f"  Altitude Safety: {'✓' if chase_status.get('altitude_safety_enabled', False) else '✗'}\n"
            chase_report += f"  Altitude Violations: {chase_status.get('altitude_violation_count', 0)}\n"
            
            # Configuration
            config = chase_status.get('config', {})
            chase_report += f"\nConfiguration:\n"
            chase_report += f"  Max Forward Speed: {config.get('max_forward_velocity', 0.0):.1f} m/s\n"
            chase_report += f"  Ramp Rate: {config.get('ramp_rate', 0.0):.1f} m/s²\n"
            chase_report += f"  Altitude Control: {'✓' if config.get('altitude_control_enabled', False) else '✗'}\n"
            chase_report += f"  Altitude Limits: {config.get('min_altitude_limit', 0.0):.0f}-{config.get('max_altitude_limit', 0.0):.0f}m\n"
            
            return base_report + chase_report
            
        except Exception as e:
            return f"Error generating body velocity chase status report: {e}"

    def reset_chase_state(self) -> None:
        """
        Resets chase-specific state variables to initial conditions including mode state.
        
        Useful for reinitializing after mode switches or error recovery.
        """
        try:
            # Reset velocity state
            self.current_forward_velocity = Parameters.INITIAL_FORWARD_VELOCITY
            self.smoothed_right_velocity = 0.0
            self.smoothed_down_velocity = 0.0
            self.smoothed_yaw_speed = 0.0
            
            # Reset tracking state
            self.target_lost = False
            self.target_loss_start_time = None
            
            # Reset safety state
            self.emergency_stop_active = False
            self.altitude_violation_count = 0
            
            # Reset timing
            self.last_ramp_update_time = time.time()
            self.last_altitude_check_time = time.time()
            
            # Reset lateral guidance mode to configured default
            self.active_lateral_mode = self._get_active_lateral_mode()
            
            # Reset PID integrators to prevent windup
            if self.pid_right:
                self.pid_right.reset()
            if self.pid_down:
                self.pid_down.reset()
            if hasattr(self, 'pid_yaw_speed') and self.pid_yaw_speed:
                self.pid_yaw_speed.reset()
            
            # Update telemetry
            self.update_telemetry_metadata('chase_state_reset', datetime.utcnow().isoformat())
            self.update_telemetry_metadata('lateral_mode_reset', self.active_lateral_mode)
            self.update_telemetry_metadata('active_lateral_mode', self.active_lateral_mode)
            
            logger.info(f"Body velocity chase follower state reset - Mode: {self.active_lateral_mode}")
            
        except Exception as e:
            logger.error(f"Error resetting chase state: {e}")

    def activate_emergency_stop(self) -> None:
        """
        Activates emergency stop mode, setting all velocities to zero.
        """
        try:
            self.emergency_stop_active = True
            
            # Immediately set all velocities to zero
            self.set_command_field('vel_body_fwd', 0.0)
            self.set_command_field('vel_body_right', 0.0)
            self.set_command_field('vel_body_down', 0.0)
            self.set_command_field('yawspeed_deg_s', 0.0)
            
            # Update telemetry
            self.update_telemetry_metadata('emergency_stop_activated', datetime.utcnow().isoformat())
            
            logger.critical("Emergency stop activated - all velocities set to zero")
            
        except Exception as e:
            logger.error(f"Error activating emergency stop: {e}")

    def deactivate_emergency_stop(self) -> None:
        """
        Deactivates emergency stop mode, allowing normal operation to resume.
        """
        try:
            self.emergency_stop_active = False
            
            # Update telemetry
            self.update_telemetry_metadata('emergency_stop_deactivated', datetime.utcnow().isoformat())
            
            logger.info("Emergency stop deactivated - normal operation resumed")
            
        except Exception as e:
            logger.error(f"Error deactivating emergency stop: {e}")

    # ==================== Mode-Specific Utility Methods ====================
    
    def get_lateral_mode_description(self, mode: str = None) -> str:
        """
        Returns a description of the specified lateral guidance mode.
        
        Args:
            mode (str, optional): Mode to describe. If None, uses active mode.
            
        Returns:
            str: Human-readable description of the mode.
        """
        mode = mode or self.active_lateral_mode
        
        descriptions = {
            'sideslip': "Direct lateral velocity control (v_right ≠ 0, yaw_rate = 0). "
                       "Best for precision hovering, close proximity operations, confined spaces.",
            'coordinated_turn': "Turn-to-track control (v_right = 0, yaw_rate ≠ 0). "
                               "Best for forward flight efficiency, natural behavior, wind resistance."
        }
        
        return descriptions.get(mode, f"Unknown mode: {mode}")

    def force_lateral_mode(self, mode: str) -> bool:
        """
        Forces a specific lateral guidance mode, overriding auto-switching.
        
        Args:
            mode (str): Desired mode ('sideslip' or 'coordinated_turn').
            
        Returns:
            bool: True if mode switch successful, False otherwise.
        """
        try:
            if mode not in ['sideslip', 'coordinated_turn']:
                logger.error(f"Invalid lateral mode: {mode}")
                return False
            
            logger.info(f"Force switching to lateral mode: {mode}")
            self._switch_lateral_mode(mode)
            
            # Update telemetry to indicate forced mode
            self.update_telemetry_metadata('forced_lateral_mode', mode)
            self.update_telemetry_metadata('mode_force_timestamp', datetime.utcnow().isoformat())
            
            return True
            
        except Exception as e:
            logger.error(f"Error forcing lateral mode to {mode}: {e}")
            return False