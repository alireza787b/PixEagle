# src/classes/followers/mc_velocity_ground_follower.py
"""
Ground Target Follower Module
============================

This module implements the MCVelocityGroundFollower class for tracking ground-based targets
using velocity body control with advanced PID features.

Project Information:
    - Project Name: PixEagle
    - Repository: https://github.com/alireza787b/PixEagle
    - Author: Alireza Ghaderi
    - LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
    The MCVelocityGroundFollower provides comprehensive 3-axis velocity control for tracking
    ground targets. Image coordinates enter the lateral and forward PID controllers
    directly; optional descent uses the shared altitude permission and limits.

Key Features:
    - Full body-FRD velocity control (forward, right, down)
    - Axis-specific PID control from shared configured gains
    - Descent control with safety limits
    - Schema-aware command field management

Control Strategy:
    - X/Y axes: Target centering around the configured image aim
    - Z axis: Descent control with configurable limits
    - Coordinate system: Body frame velocities
    - Safety: Altitude limits and descent protection
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
from classes.follower_config_manager import get_follower_config_manager
from classes.tracker_output import TrackerOutput
import logging
from typing import Tuple, Dict, Any
from datetime import datetime

# Configure module logger
logger = logging.getLogger(__name__)

class MCVelocityGroundFollower(BaseFollower):
    """
    Advanced ground target follower with 3-axis velocity control.
    
    This follower implements sophisticated ground target tracking using body frame
    velocity commands around the resolved image aim point.
    
    Control Architecture:
        - Uses three independent PID controllers for X, Y, and Z axes
        - Implements cross-coupling between axes for coordinate system differences
        
    Safety Features:
        - Descent altitude limits
        - PID output clamping
        - Input validation and error handling
        - Graceful degradation on sensor failures
    """
    
    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initialize the MCVelocityGroundFollower with advanced PID control configuration.
        
        Args:
            px4_controller: PX4 controller instance for drone communication
            initial_target_coords (Tuple[float, float]): Initial target coordinates (x, y)
                - Normalized coordinates typically in range [-1, 1]
                - (0, 0) represents image center
                
        Raises:
            ValueError: If initial coordinates are invalid
            RuntimeError: If PID controller initialization fails
            
        Note:
            AppController resolves the configured target-position policy before
            constructing the follower. The supplied coordinates are the desired
            normalized image aim point.
        """
        # Initialize with mc_velocity_ground profile for full velocity control
        super().__init__(px4_controller, "mc_velocity_ground")
        
        # Get configuration section
        config = getattr(Parameters, 'MC_VELOCITY_GROUND', {})

        # Store configuration parameters
        self.target_position_mode = getattr(
            Parameters,
            'TARGET_POSITION_MODE',
            'center',
        )
        self.initial_target_coords = tuple(initial_target_coords)

        # Load ground view specific parameters from config
        # v5.0.0: Use SafetyManager for velocity limits (single source of truth)
        self.max_velocity_x = self.velocity_limits.lateral
        self.max_velocity_y = self.velocity_limits.forward
        self.max_rate_of_descent = config.get('MAX_RATE_OF_DESCENT', 1.0)  # Operational parameter
        self.enable_descend_to_target = config.get('ENABLE_DESCEND_TO_TARGET', False)
        # Use base class cached limits (via SafetyManager)
        self.min_descent_height = self.altitude_limits.min_altitude
        # GainScheduling removed in v6.0 — all gains from PID.PID_GAINS
        fcm = get_follower_config_manager()
        self.control_update_rate = fcm.get_param('CONTROL_UPDATE_RATE', 'MC_VELOCITY_GROUND')
        self.altitude_control_enabled = fcm.get_param('ENABLE_ALTITUDE_CONTROL', 'MC_VELOCITY_GROUND')
        
        # Initialize control system components
        self._initialize_pid_controllers()
        
        # Update telemetry metadata
        self.update_telemetry_metadata('control_strategy', 'ground_target_tracking')
        self.update_telemetry_metadata('coordinate_system', 'body_frame_velocity')
        self.update_telemetry_metadata('target_position_mode', self.target_position_mode)
        
        logger.info(f"MCVelocityGroundFollower initialized successfully - "
                   f"Mode: {self.target_position_mode}, "
                   f"Target: {self.initial_target_coords}")
    
    def reset_target_state(self, reason: str) -> bool:
        for controller in (self.pid_x, self.pid_y, self.pid_z):
            controller.reset()
        return True

    def _initialize_pid_controllers(self) -> None:
        """
        Initialize PID controllers for all three axes with proper configuration.
        
        This method sets up three independent PID controllers:
        - X-axis: Lateral movement control
        - Y-axis: Longitudinal movement control  
        - Z-axis: Altitude/descent control
        
        Each controller is configured with:
        - Axis-specific gains from PID.PID_GAINS
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
                *self._get_pid_gains('mc_vel_lateral'),
                setpoint=setpoint_x,
                output_limits=(-self.max_velocity_x, self.max_velocity_x)
            )

            # Initialize Y-axis PID controller (longitudinal movement)
            self.pid_y = CustomPID(
                *self._get_pid_gains('mc_vel_forward'),
                setpoint=setpoint_y,
                output_limits=(-self.max_velocity_y, self.max_velocity_y)
            )

            # Initialize Z-axis PID controller (descent-to-target control).
            # setpoint=0: input is (current_altitude - min_descent_height), negated so
            # PID error = 0 - (-height_above_floor) = +height → positive = descent.
            # output_limits clamped to (0, max) so PID never commands climb.
            self.pid_z = CustomPID(
                *self._get_pid_gains('mc_altitude'),
                setpoint=0.0,
                output_limits=(0.0, self.max_rate_of_descent)
            )
            
            # Log successful initialization
            logger.info("PID controllers initialized successfully for MCVelocityGroundFollower")
            logger.debug(f"PID setpoints - X: {setpoint_x}, Y: {setpoint_y}, "
                        f"Z: {self.min_descent_height}")
            
        except Exception as e:
            logger.error(f"Failed to initialize PID controllers: {e}")
            raise RuntimeError(f"PID controller initialization failed: {e}")
    
    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieve PID gains for specified axis from global PID_GAINS.

        Args:
            axis (str): Control axis identifier ('mc_vel_forward', 'mc_vel_lateral', 'mc_altitude')

        Returns:
            Tuple[float, float, float]: PID gains as (P, I, D) tuple

        Raises:
            KeyError: If axis is not found in PID_GAINS configuration
        """
        try:
            gains = Parameters.PID_GAINS[axis]
            return gains['p'], gains['i'], gains['d']
        except KeyError as e:
            logger.error(f"PID gains not found for axis '{axis}': {e}")
            raise
    
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
            self.pid_x.tunings = self._get_pid_gains('mc_vel_lateral')
            self.pid_y.tunings = self._get_pid_gains('mc_vel_forward')
            self.pid_z.tunings = self._get_pid_gains('mc_altitude')
            
            logger.debug("PID gains updated successfully for MCVelocityGroundFollower")
            
        except Exception as e:
            logger.error(f"Failed to update PID gains: {e}")
            # Continue operation with existing gains rather than failing
    
    def _control_descent(self) -> float:
        """
        Calculate a positive-body-down descent request above the relative altitude floor.

        At or below the configured floor this helper requests zero descent.
        That does not model braking, inertia, terrain clearance or guarantee
        that the aircraft cannot travel below the floor.
        
        Returns:
            float: Positive-body-down descent velocity in m/s, or zero when disabled,
                at the floor or missing the altitude observation.
            
        Note:
            - Returns 0 if descent is disabled or altitude limits are reached
            - Uses current altitude from PX4 controller for limit checking
            - The descent PID output remains bounded by the configured descent rate
        """
        # Check if descent is enabled
        if not self.altitude_control_enabled or not self.enable_descend_to_target:
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
                # Pass negative height-above-floor so PID error (0 - input) is positive → descent
                height_above_floor = current_altitude - self.min_descent_height
                descent_command = self.pid_z(-height_above_floor)
                logger.debug(f"Descent command: {descent_command:.3f} m/s (height above floor: {height_above_floor:.1f}m)")
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
        3. Image aim error calculation and PID control
        4. Command field updates via schema-aware interface
        
        Args:
            tracker_data (TrackerOutput): Structured tracker data with position and metadata
                
        Raises:
            ValueError: If tracker data or target coordinates are invalid
            RuntimeError: If control calculation fails
            
        Note:
            The method implements axis coupling where:
            - error_y controls body-forward velocity
            - error_x controls body-right velocity
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
            
            error_x = self.image_axis_error(target_coords[0], self.pid_x.setpoint)
            error_y = self.image_axis_error(target_coords[1], self.pid_y.setpoint)
            
            # Calculate velocity commands using PID controllers
            # Note: Cross-coupling between axes for body frame coordinate system
            vel_body_fwd = self.pid_y(target_coords[1])
            vel_body_right = self.positive_image_axis_pid_command(
                self.pid_x,
                target_coords[0],
            )
            vel_body_down = self._control_descent()
            
            if not self.set_command_fields(
                {
                    'vel_body_fwd': vel_body_fwd,
                    'vel_body_right': vel_body_right,
                    'vel_body_down': vel_body_down,
                    'yawspeed_deg_s': 0.0,
                },
                reason='mc_velocity_ground_normal_tracking',
            ):
                raise RuntimeError("Failed to apply MC velocity ground command intent")
            
            # Log control status
            logger.debug(f"Control commands calculated - "
                        f"Target: {target_coords}, "
                        f"Errors: ({error_x:.3f}, {error_y:.3f}), "
                        f"Commands: fwd={vel_body_fwd:.3f}, "
                        f"right={vel_body_right:.3f}, down={vel_body_down:.3f}")
            
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
                    'descent_enabled': self.enable_descend_to_target,
                    'velocity_limits': {
                        'max_velocity_x': self.max_velocity_x,
                        'max_velocity_y': self.max_velocity_y,
                        'max_rate_of_descent': self.max_rate_of_descent
                    },
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
                    'vel_body_fwd': abs(current_commands.get('vel_body_fwd', 0)),
                    'vel_body_right': abs(current_commands.get('vel_body_right', 0)),
                    'vel_body_down': abs(current_commands.get('vel_body_down', 0)),
                    'yawspeed_deg_s': abs(current_commands.get('yawspeed_deg_s', 0))
                },
                'total_velocity': sum(abs(v) for v in current_commands.values()),
                'active_axes': sum(1 for v in current_commands.values() if abs(v) > 0.001),
                'control_active': any(abs(v) > 0.001 for v in current_commands.values())
            }
        except Exception as e:
            logger.error(f"Error calculating performance metrics: {e}")
            return {'error': str(e)}
