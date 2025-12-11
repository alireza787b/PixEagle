# src/classes/followers/ground_target_follower.py
"""
Ground Target Follower Module
============================

This module implements the GroundTargetFollower class for tracking ground-based targets
using velocity body control with advanced PID features.

Project Information:
    - Project Name: PixEagle
    - Repository: https://github.com/alireza787b/PixEagle
    - Author: Alireza Ghaderi
    - LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
    The GroundTargetFollower provides comprehensive 3-axis velocity control for tracking
    ground targets. It implements advanced PID control with optional gain scheduling,
    gimbal corrections, and altitude-based adjustments.

Key Features:
    - Full 3-axis velocity control (vel_x, vel_y, vel_z)
    - Advanced PID control with gain scheduling support
    - Gimbal orientation compensation
    - Altitude-based dynamic adjustments
    - Descent control with safety limits
    - Schema-aware command field management

Control Strategy:
    - X/Y axes: Target centering with gimbal and altitude corrections
    - Z axis: Descent control with configurable limits
    - Coordinate system: Body frame velocities
    - Safety: Altitude limits and descent protection
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
from typing import Tuple, Dict, Optional, Any
from datetime import datetime

# Configure module logger
logger = logging.getLogger(__name__)

class GroundTargetFollower(BaseFollower):
    """
    Advanced ground target follower with 3-axis velocity control.
    
    This follower implements sophisticated ground target tracking using body frame
    velocity commands. It features advanced PID control with optional gain scheduling,
    gimbal compensation, and altitude-based adjustments for optimal tracking performance.
    
    Control Architecture:
        - Uses three independent PID controllers for X, Y, and Z axes
        - Implements cross-coupling between axes for coordinate system differences
        - Applies gimbal corrections for non-stabilized cameras
        - Dynamically adjusts control parameters based on altitude
        
    Safety Features:
        - Descent altitude limits
        - PID output clamping
        - Input validation and error handling
        - Graceful degradation on sensor failures
    """
    
    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initialize the GroundTargetFollower with advanced PID control configuration.
        
        Args:
            px4_controller: PX4 controller instance for drone communication
            initial_target_coords (Tuple[float, float]): Initial target coordinates (x, y)
                - Normalized coordinates typically in range [-1, 1]
                - (0, 0) represents image center
                
        Raises:
            ValueError: If initial coordinates are invalid
            RuntimeError: If PID controller initialization fails
            
        Note:
            The follower automatically configures itself based on TARGET_POSITION_MODE:
            - 'initial': Uses provided initial_target_coords as setpoints
            - 'center': Uses (0, 0) as setpoints for center tracking
        """
        # Initialize with Ground View profile for full velocity control
        super().__init__(px4_controller, "Ground View")
        
        # Get configuration section (like other followers do)
        config = getattr(Parameters, 'GROUND_VIEW', {})

        # Store configuration parameters
        self.target_position_mode = config.get('TARGET_POSITION_MODE', 'center')
        self.initial_target_coords = (
            initial_target_coords if self.target_position_mode == 'initial'
            else (0.0, 0.0)
        )

        # Load ground view specific parameters from config
        self.max_velocity_x = config.get('MAX_VELOCITY_X', 10.0)
        self.max_velocity_y = config.get('MAX_VELOCITY_Y', 10.0)
        self.max_rate_of_descent = config.get('MAX_RATE_OF_DESCENT', 2.0)
        self.enable_descend_to_target = config.get('ENABLE_DESCEND_TO_TARGET', False)
        # Use unified limit access (follower-specific overrides global SafetyLimits)
        self.min_descent_height = Parameters.get_effective_limit('MIN_ALTITUDE', 'GROUND_VIEW')
        self.is_camera_gimbaled = config.get('IS_CAMERA_GIMBALED', False)
        self.base_adjustment_factor_x = config.get('BASE_ADJUSTMENT_FACTOR_X', 0.1)
        self.base_adjustment_factor_y = config.get('BASE_ADJUSTMENT_FACTOR_Y', 0.1)
        self.altitude_factor = config.get('ALTITUDE_FACTOR', 0.005)
        self.enable_gain_scheduling = config.get('ENABLE_GAIN_SCHEDULING', False)
        self.gain_scheduling_parameter = config.get('GAIN_SCHEDULING_PARAMETER', 'current_altitude')
        self.control_update_rate = config.get('CONTROL_UPDATE_RATE', 20.0)
        self.coordinate_corrections_enabled = config.get('COORDINATE_CORRECTIONS_ENABLED', True)
        self.error_logging_enabled = config.get('ERROR_LOGGING_ENABLED', True)
        
        # Initialize control system components
        self._initialize_pid_controllers()
        
        # Update telemetry metadata
        self.update_telemetry_metadata('control_strategy', 'ground_target_tracking')
        self.update_telemetry_metadata('coordinate_system', 'body_frame_velocity')
        self.update_telemetry_metadata('target_position_mode', self.target_position_mode)
        
        logger.info(f"GroundTargetFollower initialized successfully - "
                   f"Mode: {self.target_position_mode}, "
                   f"Target: {self.initial_target_coords}")
    
    def _initialize_pid_controllers(self) -> None:
        """
        Initialize PID controllers for all three axes with proper configuration.
        
        This method sets up three independent PID controllers:
        - X-axis: Lateral movement control
        - Y-axis: Longitudinal movement control  
        - Z-axis: Altitude/descent control
        
        Each controller is configured with:
        - Axis-specific gains (with optional gain scheduling)
        - Appropriate output limits from parameters
        - Initial setpoints based on target position mode
        
        Raises:
            RuntimeError: If PID initialization fails
            ValueError: If parameters are invalid
        """
        try:
            setpoint_x, setpoint_y = self.initial_target_coords
            
            # Initialize X-axis PID controller (lateral movement)
            self.pid_x = CustomPID(
                *self._get_pid_gains('x'),
                setpoint=setpoint_x,
                output_limits=(-self.max_velocity_x, self.max_velocity_x)
            )

            # Initialize Y-axis PID controller (longitudinal movement)
            self.pid_y = CustomPID(
                *self._get_pid_gains('y'),
                setpoint=setpoint_y,
                output_limits=(-self.max_velocity_y, self.max_velocity_y)
            )

            # Initialize Z-axis PID controller (altitude control)
            self.pid_z = CustomPID(
                *self._get_pid_gains('z'),
                setpoint=self.min_descent_height,
                output_limits=(-self.max_rate_of_descent, self.max_rate_of_descent)
            )
            
            # Log successful initialization
            logger.info("PID controllers initialized successfully for GroundTargetFollower")
            logger.debug(f"PID setpoints - X: {setpoint_x}, Y: {setpoint_y}, "
                        f"Z: {self.min_descent_height}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PID controllers: {e}")
            raise RuntimeError(f"PID controller initialization failed: {e}")
    
    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieve PID gains for specified axis with optional gain scheduling.
        
        This method implements adaptive gain scheduling based on current flight conditions.
        When gain scheduling is enabled, it selects appropriate gains based on the
        configured scheduling parameter (typically altitude).
        
        Args:
            axis (str): Control axis identifier ('x', 'y', or 'z')
            
        Returns:
            Tuple[float, float, float]: PID gains as (P, I, D) tuple
            
        Raises:
            KeyError: If axis is not found in PID_GAINS configuration
            ValueError: If gain scheduling parameter is invalid
            
        Note:
            Gain scheduling provides adaptive control by adjusting PID parameters
            based on flight conditions, improving performance across different
            operational scenarios.
        """
        try:
            # Check if gain scheduling is enabled
            if self.enable_gain_scheduling:
                current_value = getattr(
                    self.px4_controller,
                    self.gain_scheduling_parameter,
                    None
                )

                if current_value is None:
                    logger.warning(
                        f"Gain scheduling parameter '{self.gain_scheduling_parameter}' "
                        f"not available in PX4Controller. Using default gains."
                    )
                else:
                    # Search for appropriate gain schedule
                    for (lower_bound, upper_bound), gains in Parameters.ALTITUDE_GAIN_SCHEDULE.items():
                        if lower_bound <= current_value < upper_bound:
                            logger.debug(f"Using scheduled gains for {axis} axis "
                                       f"(parameter: {current_value})")
                            return gains[axis]['p'], gains[axis]['i'], gains[axis]['d']
            
            # Use default gains
            default_gains = (
                Parameters.PID_GAINS[axis]['p'],
                Parameters.PID_GAINS[axis]['i'], 
                Parameters.PID_GAINS[axis]['d']
            )
            logger.debug(f"Using default gains for {axis} axis: {default_gains}")
            return default_gains
            
        except KeyError as e:
            logger.error(f"PID gains not found for axis '{axis}': {e}")
            raise
        except Exception as e:
            logger.error(f"Error retrieving PID gains for axis '{axis}': {e}")
            raise ValueError(f"Invalid gain configuration for axis '{axis}': {e}")
    
    def _update_pid_gains(self) -> None:
        """
        Update PID controller gains based on current flight conditions.
        
        This method refreshes the tuning parameters for all PID controllers,
        enabling adaptive control based on current conditions. Should be called
        regularly during operation to maintain optimal performance.
        
        Note:
            Gain updates are performed smoothly to avoid control discontinuities.
            The method includes error handling to ensure system stability.
        """
        try:
            self.pid_x.tunings = self._get_pid_gains('x')
            self.pid_y.tunings = self._get_pid_gains('y')
            self.pid_z.tunings = self._get_pid_gains('z')
            
            logger.debug("PID gains updated successfully for GroundTargetFollower")
            
        except Exception as e:
            logger.error(f"Failed to update PID gains: {e}")
            # Continue operation with existing gains rather than failing
    
    def _apply_gimbal_corrections(self, target_coords: Tuple[float, float]) -> Tuple[float, float]:
        """
        Apply gimbal-based corrections for non-stabilized camera systems.
        
        When the camera is not gimbal-stabilized, drone orientation affects the
        apparent target position. This method compensates for pitch and roll
        movements to maintain accurate tracking.
        
        Args:
            target_coords (Tuple[float, float]): Raw target coordinates from vision
            
        Returns:
            Tuple[float, float]: Corrected target coordinates accounting for drone orientation
            
        Note:
            - Correction is only applied when IS_CAMERA_GIMBALED is False
            - Uses current drone orientation (pitch, roll) for compensation
            - Correction factors are configurable via Parameters
        """
        # Skip correction for gimbaled cameras
        if self.is_camera_gimbaled:
            logger.debug("Camera is gimbaled - skipping gimbal corrections")
            return target_coords
        
        try:
            # Get current drone orientation
            orientation = self.px4_controller.get_orientation()  # (yaw, pitch, roll)
            if orientation is None or len(orientation) < 3:
                logger.warning("Unable to get drone orientation - skipping gimbal corrections")
                return target_coords
            
            yaw, pitch, roll = orientation
            
            # Apply orientation-based corrections
            corrected_x = (target_coords[0] +
                          self.base_adjustment_factor_x * roll)
            corrected_y = (target_coords[1] -
                          self.base_adjustment_factor_y * pitch)
            
            logger.debug(f"Applied gimbal corrections - "
                        f"Roll: {roll:.3f}, Pitch: {pitch:.3f}, "
                        f"Correction: ({corrected_x - target_coords[0]:.3f}, "
                        f"{corrected_y - target_coords[1]:.3f})")
            
            return corrected_x, corrected_y
            
        except Exception as e:
            logger.error(f"Error applying gimbal corrections: {e}")
            return target_coords  # Return uncorrected coordinates as fallback
    
    def _apply_altitude_adjustments(self, target_x: float, target_y: float) -> Tuple[float, float]:
        """
        Apply altitude-based dynamic adjustments to target coordinates.
        
        At different altitudes, the same pixel displacement corresponds to different
        real-world distances. This method applies scaling factors based on current
        altitude to maintain consistent control response.
        
        Args:
            target_x (float): X-coordinate after gimbal corrections
            target_y (float): Y-coordinate after gimbal corrections
            
        Returns:
            Tuple[float, float]: Altitude-adjusted target coordinates
            
        Note:
            - Adjustment factors decrease with altitude for consistent angular response
            - Uses configurable base factors and altitude scaling parameters
            - Provides altitude-invariant tracking behavior
        """
        try:
            current_altitude = self.px4_controller.current_altitude
            if current_altitude is None or current_altitude < 0:
                logger.warning(f"Invalid altitude reading: {current_altitude} - "
                             f"skipping altitude adjustments")
                return target_x, target_y
            
            # Calculate altitude-dependent adjustment factors
            adj_factor_x = (self.base_adjustment_factor_x /
                           (1 + self.altitude_factor * current_altitude))
            adj_factor_y = (self.base_adjustment_factor_y /
                           (1 + self.altitude_factor * current_altitude))
            
            # Apply adjustments
            adjusted_x = target_x + adj_factor_x
            adjusted_y = target_y + adj_factor_y
            
            logger.debug(f"Applied altitude adjustments - "
                        f"Altitude: {current_altitude:.1f}m, "
                        f"Factors: ({adj_factor_x:.3f}, {adj_factor_y:.3f})")
            
            return adjusted_x, adjusted_y
            
        except Exception as e:
            logger.error(f"Error applying altitude adjustments: {e}")
            return target_x, target_y  # Return unadjusted coordinates as fallback
    
    def _control_descent(self) -> float:
        """
        Calculate altitude control command with safety limits.
        
        This method implements safe descent control with configurable limits.
        It prevents the drone from descending below a minimum safe altitude
        while allowing controlled descent when appropriate.
        
        Returns:
            float: Z-axis velocity command (negative for descent, positive for climb)
            
        Note:
            - Returns 0 if descent is disabled or altitude limits are reached
            - Uses current altitude from PX4 controller for limit checking
            - Integrates with PID controller for smooth altitude control
        """
        # Check if descent is enabled
        if not self.enable_descend_to_target:
            logger.debug("Descent to target is disabled")
            return 0.0
        
        try:
            current_altitude = self.px4_controller.current_altitude
            if current_altitude is None:
                logger.warning("Unable to get current altitude - halting descent")
                return 0.0
            
            logger.debug(f"Altitude control - Current: {current_altitude:.1f}m, "
                        f"Minimum: {self.min_descent_height:.1f}m")

            # Check altitude limits
            if current_altitude > self.min_descent_height:
                # Calculate descent command using PID controller
                descent_command = self.pid_z(-current_altitude)
                logger.debug(f"Descent command: {descent_command:.3f} m/s")
                return descent_command
            else:
                logger.debug("At or below minimum descent height - descent halted")
                return 0.0
                
        except Exception as e:
            logger.error(f"Error in descent control: {e}")
            return 0.0  # Safe fallback
    
    # ==================== Required Abstract Method Implementations ====================
    
    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculate and apply comprehensive control commands for ground target tracking.
        
        This is the main control method that orchestrates the complete control pipeline:
        1. Input validation and tracker data extraction
        2. PID gain updates for adaptive control
        3. Gimbal corrections for camera orientation
        4. Altitude adjustments for scale invariance
        5. Error calculation and PID control
        6. Command field updates via schema-aware interface
        
        Args:
            tracker_data (TrackerOutput): Structured tracker data with position and metadata
                
        Raises:
            ValueError: If tracker data or target coordinates are invalid
            RuntimeError: If control calculation fails
            
        Note:
            The method implements axis coupling where:
            - error_y controls vel_x (forward/backward motion)
            - error_x controls vel_y (left/right motion)
            This accounts for the body frame coordinate system differences.
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
            
            # Update PID gains for adaptive control
            self._update_pid_gains()
            
            # Apply coordinate corrections and adjustments
            corrected_x, corrected_y = self._apply_gimbal_corrections(target_coords)
            adjusted_x, adjusted_y = self._apply_altitude_adjustments(corrected_x, corrected_y)
            
            # Calculate control errors
            error_x = self.pid_x.setpoint - adjusted_x
            error_y = self.pid_y.setpoint - (-1) * adjusted_y  # Invert Y for coordinate system
            
            # Calculate velocity commands using PID controllers
            # Note: Cross-coupling between axes for body frame coordinate system
            vel_x = self.pid_y(error_y)  # Forward/backward motion
            vel_y = self.pid_x(error_x)  # Left/right motion
            vel_z = self._control_descent()  # Altitude control
            
            # Update command fields using schema-aware interface
            success_x = self.set_command_field('vel_x', vel_x)
            success_y = self.set_command_field('vel_y', vel_y)
            success_z = self.set_command_field('vel_z', vel_z)
            
            # Validate command updates
            if not all([success_x, success_y, success_z]):
                logger.warning("Some command fields failed to update")
            
            # Log control status
            logger.debug(f"Control commands calculated - "
                        f"Target: {target_coords}, "
                        f"Adjusted: ({adjusted_x:.3f}, {adjusted_y:.3f}), "
                        f"Errors: ({error_x:.3f}, {error_y:.3f}), "
                        f"Commands: vel_x={vel_x:.3f}, vel_y={vel_y:.3f}, vel_z={vel_z:.3f}")
            
            # Update telemetry metadata
            self.update_telemetry_metadata('last_control_update', datetime.utcnow().isoformat())
            self.update_telemetry_metadata('control_errors', {'x': error_x, 'y': error_y})
            
        except Exception as e:
            logger.error(f"Failed to calculate control commands: {e}")
            # Reset commands to safe values on error
            self.reset_command_fields()
            raise RuntimeError(f"Control calculation failed: {e}")
    
    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Execute target following behavior using schema-driven tracker data.
        
        This method implements the high-level following logic by calculating
        and applying control commands. It serves as the main entry point for
        the tracking system with enhanced schema support.
        
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
            # Validate tracker data
            if not tracker_data or not hasattr(tracker_data, 'data_type'):
                logger.error("Invalid tracker data provided")
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
            
            logger.info(f"Successfully following target at: {target_coords}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to follow target: {e}")
            return False
    
    # ==================== Enhanced Status and Debug Methods ====================
    
    def get_control_status(self) -> Dict[str, Any]:
        """
        Get comprehensive control system status information.
        
        Returns:
            Dict[str, Any]: Detailed status including:
                - PID controller states
                - Current command values
                - Error states
                - Configuration parameters
        """
        try:
            return {
                'control_type': 'ground_target_tracking',
                'pid_controllers': {
                    'x_axis': {
                        'setpoint': self.pid_x.setpoint,
                        'tunings': self.pid_x.tunings,
                        'output_limits': self.pid_x.output_limits
                    },
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
                    'target_position_mode': self.target_position_mode,
                    'initial_target_coords': self.initial_target_coords,
                    'gain_scheduling_enabled': self.enable_gain_scheduling,
                    'gimbal_corrections_enabled': not self.is_camera_gimbaled,
                    'descent_enabled': self.enable_descend_to_target,
                    'velocity_limits': {
                        'max_velocity_x': self.max_velocity_x,
                        'max_velocity_y': self.max_velocity_y,
                        'max_rate_of_descent': self.max_rate_of_descent
                    },
                    'coordinate_corrections_enabled': self.coordinate_corrections_enabled,
                    'control_update_rate': self.control_update_rate
                },
                'current_commands': self.get_all_command_fields(),
                'validation_status': self.validate_profile_consistency()
            }
        except Exception as e:
            logger.error(f"Error getting control status: {e}")
            return {'error': str(e)}
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Calculate and return performance metrics for monitoring and tuning.
        
        Returns:
            Dict[str, Any]: Performance metrics including error statistics and timing
        """
        try:
            current_commands = self.get_all_command_fields()
            
            return {
                'command_magnitudes': {
                    'vel_x': abs(current_commands.get('vel_x', 0)),
                    'vel_y': abs(current_commands.get('vel_y', 0)),
                    'vel_z': abs(current_commands.get('vel_z', 0))
                },
                'total_velocity': sum(abs(v) for v in current_commands.values()),
                'active_axes': sum(1 for v in current_commands.values() if abs(v) > 0.001),
                'control_active': any(abs(v) > 0.001 for v in current_commands.values())
            }
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {e}")
            return {'error': str(e)}