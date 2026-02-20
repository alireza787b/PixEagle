# src/classes/followers/mc_velocity_distance_follower.py
"""
MC Velocity Distance Follower Module
====================================

This module implements the MCVelocityDistanceFollower class for maintaining a
constant distance from targets while allowing lateral and vertical adjustments.

Project Information:
    - Project Name: PixEagle
    - Repository: https://github.com/alireza787b/PixEagle
    - Author: Alireza Ghaderi
    - LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
    The MCVelocityDistanceFollower provides selective 4-axis control for maintaining
    a constant distance from targets. It implements controlled Y/Z movement with
    optional yaw control while keeping the X-axis (forward/backward) fixed.

Key Features:
    - Selective axis control (vel_x=0, vel_y, vel_z, optional yaw_rate)
    - Advanced altitude control with bidirectional movement
    - Optional yaw control for target centering
    - Altitude safety limits with climb/descent protection
    - Schema-aware command field management

Control Strategy:
    - X axis: Fixed at zero (maintains constant forward distance)
    - Y axis: Lateral movement control for side positioning
    - Z axis: Bidirectional altitude control with safety limits
    - Yaw axis: Optional rotation for target centering
    - Safety: Altitude limits and movement constraints
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
from classes.follower_config_manager import get_follower_config_manager
from classes.followers.yaw_rate_smoother import YawRateSmoother
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
import math
import time
from typing import Tuple, Dict, Optional, Any
from datetime import datetime

# Configure module logger
logger = logging.getLogger(__name__)

class MCVelocityDistanceFollower(BaseFollower):
    """
    Advanced constant distance follower with selective axis control.
    
    This follower maintains a constant forward distance from targets while allowing
    precise lateral and vertical positioning. It features optional yaw control for
    target centering and sophisticated altitude management with safety limits.
    
    Control Architecture:
        - Uses two or three PID controllers (Y, Z, optional Yaw)
        - X-axis velocity fixed at zero for constant distance
        - Bidirectional altitude control with configurable limits
        - Optional yaw control for target centering
        
    Safety Features:
        - Altitude ceiling and floor limits
        - PID output clamping
        - Input validation and error handling
        - Graceful degradation on sensor failures
    """
    
    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initialize the MCVelocityDistanceFollower with selective axis control.
        
        Args:
            px4_controller: PX4 controller instance for drone communication
            initial_target_coords (Tuple[float, float]): Initial target coordinates (x, y)
                - Normalized coordinates typically in range [-1, 1]
                - (0, 0) represents image center
                
        Raises:
            ValueError: If initial coordinates are invalid
            RuntimeError: If PID controller initialization fails
            
        Note:
            Yaw control is enabled/disabled based on Parameters.ENABLE_YAW_CONTROL.
            The follower automatically configures PID controllers based on enabled features.
        """
        # Initialize with mc_velocity_distance profile for enhanced velocity control
        super().__init__(px4_controller, "mc_velocity_distance")
        
        # Get configuration section
        config = getattr(Parameters, 'MC_VELOCITY_DISTANCE', {})

        # Store configuration parameters
        self.yaw_enabled = config.get('ENABLE_YAW_CONTROL', False)
        self.initial_target_coords = initial_target_coords

        # Shared params from FollowerConfigManager (General → FollowerOverrides → Fallback)
        fcm = get_follower_config_manager()
        _fn = 'MC_VELOCITY_DISTANCE'
        self.altitude_control_enabled = fcm.get_param('ENABLE_ALTITUDE_CONTROL', _fn)
        self.target_lost_timeout = fcm.get_param('TARGET_LOSS_TIMEOUT', _fn)
        self.control_update_rate = fcm.get_param('CONTROL_UPDATE_RATE', _fn)
        self.command_smoothing_enabled = fcm.get_param('COMMAND_SMOOTHING_ENABLED', _fn)
        self.smoothing_factor = fcm.get_param('SMOOTHING_FACTOR', _fn)

        # Use base class cached limits (via SafetyManager)
        self.min_descent_height = self.altitude_limits.min_altitude
        self.max_climb_height = self.altitude_limits.max_altitude
        self.max_vertical_velocity = self.velocity_limits.vertical
        self.max_lateral_velocity = self.velocity_limits.lateral
        # Internal rad/s; use base class cached rate limits
        self.max_yaw_rate = self.rate_limits.yaw  # Already in rad/s from SafetyManager
        self.yaw_control_threshold = config.get('YAW_CONTROL_THRESHOLD', 0.3)
        # NOTE: distance_hold is not yet implemented — X-axis is always fixed at zero
        # These params are loaded for future use / status reporting only
        self.distance_hold_enabled = config.get('DISTANCE_HOLD_ENABLED', True)
        self.distance_hold_tolerance = config.get('DISTANCE_HOLD_TOLERANCE', 0.1)

        # YawRateSmoother (4-stage pipeline: deadzone → speed-scaling → rate-limiting → EMA)
        yaw_smoothing_config = fcm.get_yaw_smoothing_config(_fn)
        self.yaw_smoother = YawRateSmoother.from_config(yaw_smoothing_config)

        # Smoothing state for velocity EMA (initialized to 0; updated each control cycle)
        self._last_vel_right = 0.0
        self._last_vel_down = 0.0
        self._last_update_time = time.time()

        # Initialize control system components
        self._initialize_pid_controllers()
        
        # Update telemetry metadata
        self.update_telemetry_metadata('control_strategy', 'constant_distance_tracking')
        self.update_telemetry_metadata('coordinate_system', 'body_frame_velocity')
        self.update_telemetry_metadata('yaw_control_enabled', self.yaw_enabled)
        self.update_telemetry_metadata('x_axis_behavior', 'fixed_zero')
        
        logger.info(f"MCVelocityDistanceFollower initialized successfully - "
                   f"Yaw control: {'enabled' if self.yaw_enabled else 'disabled'}, "
                   f"Target: {self.initial_target_coords}")
    
    def _initialize_pid_controllers(self) -> None:
        """
        Initialize PID controllers for active axes with proper configuration.
        
        This method sets up controllers based on enabled features:
        - Y-axis: Always enabled for lateral movement control
        - Z-axis: Always enabled for altitude control
        - Yaw-axis: Conditionally enabled based on parameters
        
        Each controller is configured with:
        - Axis-specific gains from parameters
        - Appropriate output limits from parameters
        - Initial setpoints based on target coordinates
        
        Raises:
            RuntimeError: If PID initialization fails
            ValueError: If parameters are invalid
        """
        try:
            setpoint_x, setpoint_y = self.initial_target_coords
            
            # Initialize Y-axis PID controller (lateral movement)
            self.pid_y = CustomPID(
                *self._get_pid_gains('mc_vel_lateral'),
                setpoint=setpoint_x,  # X coordinate controls Y movement
                output_limits=(-self.max_lateral_velocity, self.max_lateral_velocity)
            )

            # Initialize Z-axis PID controller (altitude control)
            self.pid_z = CustomPID(
                *self._get_pid_gains('mc_altitude'),
                setpoint=setpoint_y,  # Y coordinate controls Z movement
                output_limits=(-self.max_vertical_velocity, self.max_vertical_velocity)
            )
            
            # Initialize yaw PID controller if enabled (internal rad/s)
            # Uses yawspeed_deg_s gains (deg/s MAVSDK standard)
            if self.yaw_enabled:
                self.pid_yaw_rate = CustomPID(
                    *self._get_pid_gains('mc_yawspeed_deg_s'),
                    setpoint=setpoint_x,  # X coordinate controls yaw
                    output_limits=(-self.max_yaw_rate, self.max_yaw_rate)
                )
                logger.debug("Yaw rate PID controller initialized")
            else:
                self.pid_yaw_rate = None
                logger.debug("Yaw control disabled - no yaw PID controller")
            
            # Log successful initialization
            logger.info("PID controllers initialized successfully for MCVelocityDistanceFollower")
            logger.debug(f"PID setpoints - Y: {setpoint_x}, Z: {setpoint_y}, "
                        f"Yaw enabled: {self.yaw_enabled}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PID controllers: {e}")
            raise RuntimeError(f"PID controller initialization failed: {e}")
    
    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieve PID gains for specified axis from parameters.

        This method retrieves the standard PID gains without gain scheduling
        as MCVelocityDistanceFollower uses simpler control logic.

        Args:
            axis (str): Control axis identifier ('y', 'z', or 'yawspeed_deg_s')
            
        Returns:
            Tuple[float, float, float]: PID gains as (P, I, D) tuple
            
        Raises:
            KeyError: If axis is not found in PID_GAINS configuration
            ValueError: If gain values are invalid
        """
        try:
            gains = (
                Parameters.PID_GAINS[axis]['p'],
                Parameters.PID_GAINS[axis]['i'],
                Parameters.PID_GAINS[axis]['d']
            )
            logger.debug(f"Retrieved gains for {axis} axis: {gains}")
            return gains
            
        except KeyError as e:
            logger.error(f"PID gains not found for axis '{axis}': {e}")
            raise
        except Exception as e:
            logger.error(f"Error retrieving PID gains for axis '{axis}': {e}")
            raise ValueError(f"Invalid gain configuration for axis '{axis}': {e}")
    
    def _update_pid_gains(self) -> None:
        """
        Update PID controller gains based on current configuration.

        Uses base class _update_pid_gains_from_config() method to eliminate code duplication.
        Updates are performed smoothly to avoid control discontinuities.
        """
        try:
            # Use base class method for consistent PID gain updates
            self._update_pid_gains_from_config(self.pid_y, 'mc_vel_lateral', 'MC Velocity Distance')
            self._update_pid_gains_from_config(self.pid_z, 'mc_altitude', 'MC Velocity Distance')

            if self.yaw_enabled and self.pid_yaw_rate is not None:
                self._update_pid_gains_from_config(self.pid_yaw_rate, 'mc_yawspeed_deg_s', 'MC Velocity Distance')

            logger.debug("PID gains updated successfully for MCVelocityDistanceFollower")

        except Exception as e:
            logger.error(f"Failed to update PID gains: {e}")
            # Continue operation with existing gains rather than failing
    
    def _control_altitude_bidirectional(self, error_y: float) -> float:
        """
        Calculate bidirectional altitude control with safety limits.
        
        This method implements safe altitude control allowing both climb and descent
        operations while respecting configurable safety limits.
        
        Args:
            error_y (float): Vertical position error from target
            
        Returns:
            float: Z-axis velocity command (negative=up, positive=down)
            
        Note:
            - Positive command = descent (down)
            - Negative command = climb (up)
            - Returns 0 if altitude limits are reached
            - Uses current altitude from PX4 controller for limit checking
        """
        try:
            current_altitude = self.px4_controller.current_altitude
            if current_altitude is None:
                logger.warning("Unable to get current altitude - halting altitude control")
                return 0.0
            
            logger.debug(f"Altitude control - Current: {current_altitude:.1f}m, "
                        f"Min: {self.min_descent_height:.1f}m, "
                        f"Max: {self.max_climb_height:.1f}m")
            
            # Calculate PID-controlled vertical command
            command = self.pid_z(error_y)
            
            # Apply altitude safety limits
            if command > 0:  # Descending (positive command)
                if current_altitude >= self.min_descent_height:
                    logger.debug(f"Descent command: {command:.3f} m/s")
                    return command
                else:
                    logger.debug("At minimum descent height - descent halted")
                    return 0.0
            else:  # Climbing (negative command)
                if current_altitude < self.max_climb_height:
                    logger.debug(f"Climb command: {command:.3f} m/s")
                    return command
                else:
                    logger.debug("At maximum climb height - climb halted")
                    return 0.0
                    
        except Exception as e:
            logger.error(f"Error in altitude control: {e}")
            return 0.0  # Safe fallback
    
    def _calculate_yaw_control(self, error_x: float) -> float:
        """
        Calculate yaw control command with threshold-based activation.
        
        Args:
            error_x (float): Horizontal position error from target
            
        Returns:
            float: Yaw rate command (rad/s)
        """
        if not self.yaw_enabled or self.pid_yaw_rate is None:
            return 0.0
        
        try:
            # Only apply yaw control if error exceeds threshold
            if abs(error_x) > self.yaw_control_threshold:
                yaw_command = self.pid_yaw_rate(error_x)
                logger.debug(f"Yaw control active - Error: {error_x:.3f}, Command: {yaw_command:.3f}")
                return yaw_command
            else:
                logger.debug(f"Yaw error {error_x:.3f} below threshold {self.yaw_control_threshold}")
                return 0.0
                
        except Exception as e:
            logger.error(f"Error in yaw control calculation: {e}")
            return 0.0
    
    # ==================== Required Abstract Method Implementations ====================
    
    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculate and apply control commands for constant distance tracking.
        
        This is the main control method that orchestrates the control pipeline:
        1. Input validation and preprocessing
        2. PID gain updates
        3. Error calculation for active axes
        4. PID control calculations
        5. Command field updates via schema-aware interface
        
        Args:
            tracker_data (TrackerOutput): Structured tracker data with position and metadata
                
        Raises:
            ValueError: If tracker data or target coordinates are invalid
            RuntimeError: If control calculation fails
            
        Note:
            X-axis velocity is always set to zero to maintain constant distance.
            The method maps target coordinates to appropriate control axes.
        """
        try:
            # Extract target coordinates from tracker data
            target_coords = self.extract_target_coordinates(tracker_data)
            if not target_coords:
                logger.error("Could not extract target coordinates from tracker data")
                return
            
            # Validate extracted coordinates
            if not self.validate_target_coordinates(target_coords):
                logger.error(f"Invalid target coordinates: {target_coords}")
                raise ValueError(f"Invalid target coordinates: {target_coords}")
            
            # Update PID gains
            self._update_pid_gains()
            
            # Calculate control errors
            error_x = self.pid_y.setpoint - target_coords[0]  # Horizontal error
            error_y = self.pid_z.setpoint - target_coords[1]  # Vertical error
            
            # Calculate velocity commands
            vel_x = 0.0  # Fixed at zero for constant distance
            vel_y = self.pid_y(error_x)  # Lateral movement
            vel_z = self._control_altitude_bidirectional(error_y)  # Altitude control
            yaw_rate = self._calculate_yaw_control(error_x)  # Optional yaw control (rad/s internal)
            
            # Update command fields using schema-aware interface (body offboard with deg/s yaw)
            vel_body_fwd = 0.0
            vel_body_right = vel_y
            # Altitude sign convention: _control_altitude_bidirectional() returns positive=down, negative=up
            # This matches NED/body frame convention directly - no negation needed
            vel_body_down = vel_z
            yawspeed_deg_s = math.degrees(yaw_rate)

            # Apply velocity EMA smoothing if enabled
            if self.command_smoothing_enabled:
                alpha = self.smoothing_factor
                vel_body_right = alpha * self._last_vel_right + (1.0 - alpha) * vel_body_right
                vel_body_down = alpha * self._last_vel_down + (1.0 - alpha) * vel_body_down
                self._last_vel_right = vel_body_right
                self._last_vel_down = vel_body_down

            # Apply YawRateSmoother (deadzone + rate-limiting + speed-scaling + EMA)
            now = time.time()
            dt = now - self._last_update_time
            self._last_update_time = now
            yawspeed_deg_s = self.yaw_smoother.apply(yawspeed_deg_s, dt)

            success_x = self.set_command_field('vel_body_fwd', vel_body_fwd)
            success_y = self.set_command_field('vel_body_right', vel_body_right)
            success_z = self.set_command_field('vel_body_down', vel_body_down)
            success_yaw = self.set_command_field('yawspeed_deg_s', yawspeed_deg_s)
            
            # Validate command updates
            if not all([success_x, success_y, success_z, success_yaw]):
                logger.warning("Some command fields failed to update")
            
            # Log control status
            logger.debug(f"Control commands calculated - "
                        f"Target: {target_coords}, "
                        f"Errors: ({error_x:.3f}, {error_y:.3f}), "
                        f"Commands: fwd={vel_body_fwd:.3f}, right={vel_body_right:.3f}, "
                        f"down={vel_body_down:.3f}, yaw_deg_s={yawspeed_deg_s:.1f}")
            
            # Update telemetry metadata
            self.update_telemetry_metadata('last_control_update', datetime.utcnow().isoformat())
            self.update_telemetry_metadata('control_errors', {'x': error_x, 'y': error_y})
            self.update_telemetry_metadata('yaw_active', abs(yaw_rate) > 0.001)
            
        except Exception as e:
            logger.error(f"Failed to calculate control commands: {e}")
            # Reset commands to safe values on error
            self.reset_command_fields()
            raise RuntimeError(f"Control calculation failed: {e}")
    
    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Execute target following behavior using schema-driven tracker data.
        
        This method implements the high-level following logic by calculating
        and applying control commands for constant distance tracking.
        
        Args:
            tracker_data (TrackerOutput): Structured tracker data with position and metadata
            
        Returns:
            bool: True if following executed successfully, False otherwise
            
        Raises:
            ValueError: If tracker data is invalid
            RuntimeError: If following operation fails
            
        Note:
            This method is async to support future enhancements like:
            - Asynchronous sensor data collection
            - Non-blocking command transmission
            - Concurrent safety monitoring
        """
        try:
            # Validate tracker compatibility (errors are logged by base class with rate limiting)
            if not self.validate_tracker_compatibility(tracker_data):
                return False

            # Extract target coordinates from tracker data
            target_coords = self.extract_target_coordinates(tracker_data)
            if not target_coords:
                logger.warning("Could not extract target coordinates from tracker data")
                return False

            logger.debug(f"Following target at coordinates: {target_coords}")

            # Calculate and apply control commands using structured data
            self.calculate_control_commands(tracker_data)

            # Update telemetry metadata
            self.update_telemetry_metadata('last_follow_update', datetime.utcnow().isoformat())
            self.update_telemetry_metadata('current_target', target_coords)

            logger.debug(f"Successfully following target at: {target_coords}")
            return True

        except ValueError as e:
            # Validation errors - these indicate bad configuration or state
            logger.error(f"Validation error in {self.__class__.__name__}: {e}")
            raise  # Re-raise validation errors

        except RuntimeError as e:
            # Command execution errors - these indicate system failures
            logger.error(f"Runtime error in {self.__class__.__name__}: {e}")
            self.reset_command_fields()  # Reset to safe state
            return False

        except Exception as e:
            # Unexpected errors - log and fail safe
            logger.error(f"Unexpected error in {self.__class__.__name__}.follow_target(): {e}")
            self.reset_command_fields()
            return False
    
    # ==================== Enhanced Status and Debug Methods ====================
    
    def get_control_status(self) -> Dict[str, Any]:
        """
        Get comprehensive control system status information.
        
        Returns:
            Dict[str, Any]: Detailed status including:
                - PID controller states
                - Current command values
                - Feature enable states
                - Configuration parameters
        """
        try:
            status = {
                'control_type': 'constant_distance_tracking',
                'pid_controllers': {
                    'y_axis': {
                        'setpoint': self.pid_y.setpoint,
                        'tunings': self.pid_y.tunings,
                        'output_limits': self.pid_y.output_limits
                    },
                    'z_axis': {
                        'setpoint': self.pid_z.setpoint,
                        'tunings': self.pid_z.tunings,
                        'output_limits': self.pid_z.output_limits
                    }
                },
                'configuration': {
                    'yaw_control_enabled': self.yaw_enabled,
                    'altitude_control_enabled': self.altitude_control_enabled,
                    'initial_target_coords': self.initial_target_coords,
                    'x_axis_behavior': 'fixed_zero',
                    'yaw_control_threshold': self.yaw_control_threshold,
                    'altitude_limits': {
                        'min_descent_height': self.min_descent_height,
                        'max_climb_height': self.max_climb_height
                    },
                    'velocity_limits': {
                        'max_lateral_velocity': self.max_lateral_velocity,
                        'max_vertical_velocity': self.max_vertical_velocity,
                        'max_yaw_rate': self.max_yaw_rate
                    },
                    'distance_maintenance': {
                        'distance_hold_enabled': self.distance_hold_enabled,
                        'distance_hold_tolerance': self.distance_hold_tolerance
                    }
                },
                'current_commands': self.get_all_command_fields(),
                'validation_status': self.validate_profile_consistency()
            }
            
            # Add yaw controller status if enabled
            if self.yaw_enabled and self.pid_yaw_rate is not None:
                status['pid_controllers']['yaw_rate'] = {
                    'setpoint': self.pid_yaw_rate.setpoint,
                    'tunings': self.pid_yaw_rate.tunings,
                    'output_limits': self.pid_yaw_rate.output_limits
                }
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting control status: {e}")
            return {'error': str(e)}
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Calculate and return performance metrics for monitoring and tuning.
        
        Returns:
            Dict[str, Any]: Performance metrics including command statistics
        """
        try:
            current_commands = self.get_all_command_fields()
            
            return {
                'command_magnitudes': {
                    'vel_body_fwd': abs(current_commands.get('vel_body_fwd', 0)),
                    'vel_body_right': abs(current_commands.get('vel_body_right', 0)),
                    'vel_body_down': abs(current_commands.get('vel_body_down', 0)),
                    'yawspeed_deg_s': abs(current_commands.get('yawspeed_deg_s', 0))
                },
                'total_velocity': sum(abs(v) for k, v in current_commands.items()
                                    if k.startswith('vel_')),
                'active_axes': sum(1 for k, v in current_commands.items()
                                 if abs(v) > 0.001),
                'control_active': any(abs(v) > 0.001 for v in current_commands.values()),
                'yaw_control_active': abs(current_commands.get('yawspeed_deg_s', 0)) > 0.001,
                'altitude_control_active': abs(current_commands.get('vel_body_down', 0)) > 0.001
            }
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {e}")
            return {'error': str(e)}
    
    def get_axis_configuration(self) -> Dict[str, Any]:
        """
        Get current axis configuration and control mapping.
        
        Returns:
            Dict[str, Any]: Axis configuration details
        """
        return {
            'axis_mapping': {
                'vel_x': 'fixed_zero',
                'vel_y': 'lateral_movement',
                'vel_z': 'altitude_control',
                'yaw_rate': 'optional_centering' if self.yaw_enabled else 'disabled'
            },
            'control_strategy': {
                'distance_maintenance': 'X-axis fixed at zero',
                'lateral_positioning': 'Y-axis PID control',
                'altitude_positioning': 'Z-axis bidirectional PID',
                'orientation_control': 'Yaw rate PID (optional)'
            },
            'safety_features': {
                'altitude_limits': True,
                'yaw_threshold': self.yaw_enabled,
                'pid_output_limits': True,
                'error_handling': True
            }
        }