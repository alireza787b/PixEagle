# src/classes/followers/mc_velocity_position_follower.py

"""
MC Velocity Position Follower Module
-------------------------------------

This module implements the MCVelocityPositionFollower class for drone control in aerial target tracking.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: December 2024  
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The MCVelocityPositionFollower is designed to maintain the drone's horizontal position while allowing
only yaw rotation and optional altitude adjustments to keep the target in the camera's field of view.
This mode is ideal for maintaining a stationary observation point while tracking moving targets.

Control Strategy:
----------------
- **NO horizontal translation**: body-forward and body-right commands remain zero
- **Yaw control**: Rotates the drone to keep target centered horizontally  
- **Altitude control**: Optional vertical movement to keep target in vertical view
- **Safety limits**: Enforces altitude boundaries and rate limits

Key Features:
-------------
- Schema-aware field management with automatic validation
- Robust PID control with tunable gains
- Optional altitude control with safety enforcement
- Comprehensive error handling and validation
- Enhanced telemetry and status reporting
- Production-ready logging and debugging capabilities

Usage Example:
--------------
```python
follower = MCVelocityPositionFollower(px4_controller, (0.0, 0.0))
await follower.follow_target((0.1, -0.05))  # Small target deviation
```

Technical Details:
------------------
- Uses `vel_body_down` and `yawspeed_deg_s` from the body-FRD command profile
- Implements constant acceleration PID controllers  
- Enforces schema-defined field limits and validation
- Provides comprehensive telemetry for monitoring and debugging
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
from classes.follower_config_manager import get_follower_config_manager
from classes.followers.yaw_rate_smoother import YawRateSmoother
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
import time
from math import degrees
from typing import Tuple, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class MCVelocityPositionFollower(BaseFollower):
    """
    Advanced constant position follower for drone control with schema-aware field management.
    
    This follower maintains the drone's horizontal position while enabling yaw rotation
    and optional altitude control to track targets. Designed for stationary observation
    scenarios with precise target tracking capabilities.
    
    Control Fields Used:
    - vel_body_down: Body-FRD down velocity for altitude control (optional)
    - yawspeed_deg_s: Yaw speed for horizontal target centering (always enabled)
    
    Attributes:
        yaw_control_enabled (bool): Always True - yaw control is core to this mode
        altitude_control_enabled (bool): Configurable altitude control enablement
        initial_target_coords (Tuple[float, float]): Initial target coordinates for PID setpoints
        pid_yaw_rate (CustomPID): PID controller for yaw rate commands
        pid_z (Optional[CustomPID]): PID controller for altitude control (if enabled)
        _control_statistics (Dict): Runtime statistics for monitoring performance
    """
    
    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initializes the MCVelocityPositionFollower with schema-aware configuration.

        Args:
            px4_controller: PX4InterfaceManager used by the command boundary.
            initial_target_coords (Tuple[float, float]): Initial target coordinates for 
                                                        PID controller setpoints.
                                                        
        Raises:
            ValueError: If initial_target_coords are invalid or schema validation fails.
            RuntimeError: If PID initialization fails.
            
        Note:
            Uses the complete "mc_velocity_position" body-FRD profile. Horizontal
            translation fields remain zero while down velocity and yaw speed are controlled.
        """
        # Initialize with schema-aware base class
        super().__init__(px4_controller, "mc_velocity_position")
        
        # Validate and store initial coordinates
        if not self.validate_target_coordinates(initial_target_coords):
            raise ValueError(f"Invalid initial target coordinates: {initial_target_coords}")
        
        self.initial_target_coords = initial_target_coords
        
        # Get configuration section
        config = getattr(Parameters, 'MC_VELOCITY_POSITION', {})

        # Control configuration
        self.yaw_control_enabled = config.get('ENABLE_YAW_CONTROL', True)  # Always enabled for this mode

        # Shared params from FollowerConfigManager (General → FollowerOverrides → Fallback)
        fcm = get_follower_config_manager()
        _fn = 'MC_VELOCITY_POSITION'
        self.altitude_control_enabled = fcm.get_param('ENABLE_ALTITUDE_CONTROL', _fn)
        self.target_lost_timeout = fcm.get_param('TARGET_LOSS_TIMEOUT', _fn)
        self.control_update_rate = fcm.get_param('CONTROL_UPDATE_RATE', _fn)
        self.command_smoothing_enabled = fcm.get_param('COMMAND_SMOOTHING_ENABLED', _fn)
        self.smoothing_factor = fcm.get_param('SMOOTHING_FACTOR', _fn)

        # Use base class cached limits (via SafetyManager)
        self.min_descent_height = self.altitude_limits.min_altitude
        self.max_climb_height = self.altitude_limits.max_altitude
        self.max_vertical_velocity = self.velocity_limits.vertical
        # Internal unit is rad/s; use base class cached rate limits
        self.max_yaw_rate = self.rate_limits.yaw  # Already in rad/s from SafetyManager
        self.yaw_control_threshold = config.get('YAW_CONTROL_THRESHOLD', 0.02)

        # YawRateSmoother (4-stage pipeline: deadzone → speed-scaling → rate-limiting → EMA)
        yaw_smoothing_config = fcm.get_yaw_smoothing_config(_fn)
        self.yaw_smoother = YawRateSmoother.from_config(yaw_smoothing_config)

        # Command smoothing state
        self._last_yaw_command = 0.0
        self._last_vertical_velocity_up_m_s = 0.0
        self._last_update_time = time.time()

        # Performance tracking
        self._control_statistics = {
            'pid_updates': 0,
            'commands_sent': 0,
            'last_update_time': None,
            'initialization_time': datetime.utcnow().isoformat()
        }
        
        # Initialize PID controllers
        try:
            self._initialize_pid_controllers()
            self.update_telemetry_metadata('control_mode', 'mc_velocity_position')
            self.update_telemetry_metadata('yaw_enabled', self.yaw_control_enabled)
            self.update_telemetry_metadata('altitude_enabled', self.altitude_control_enabled)
            
            logger.info(f"MCVelocityPositionFollower initialized successfully. "
                       f"Yaw: enabled, Altitude: {'enabled' if self.altitude_control_enabled else 'disabled'}")
                       
        except Exception as e:
            logger.error(f"Failed to initialize MCVelocityPositionFollower: {e}")
            raise RuntimeError(f"PID controller initialization failed: {e}")
    
    def _initialize_pid_controllers(self) -> None:
        """
        Initializes PID controllers for yaw rate and optional altitude control.

        Raises:
            RuntimeError: If PID controller creation fails.
        """
        setpoint_x, setpoint_y = self.initial_target_coords

        try:
            # Initialize yaw rate PID controller (always enabled)
            # Uses yawspeed_deg_s gains (deg/s MAVSDK standard)
            yaw_gains = self._get_pid_gains('mc_yawspeed_deg_s')
            self.pid_yaw_rate = CustomPID(
                *yaw_gains,
                setpoint=setpoint_x,
                output_limits=(-self.max_yaw_rate, self.max_yaw_rate)
            )
            logger.debug(f"Yaw rate PID initialized with gains {yaw_gains}, setpoint {setpoint_x}")
            
            # Initialize altitude PID controller if enabled
            self.pid_z = None
            if self.altitude_control_enabled:
                z_gains = self._get_pid_gains('mc_altitude')
                self.pid_z = CustomPID(
                    *z_gains,
                    setpoint=setpoint_y,
                    output_limits=(-self.max_vertical_velocity, self.max_vertical_velocity)
                )
                logger.debug(f"Altitude PID initialized with gains {z_gains}, setpoint {setpoint_y}")
            else:
                logger.debug("Altitude control disabled - no Z-axis PID controller created")
                
        except Exception as e:
            logger.error(f"PID controller initialization failed: {e}")
            raise RuntimeError(f"Could not create PID controllers: {e}")
    
    def _get_pid_gains(self, axis: str) -> Tuple[float, float, float]:
        """
        Retrieves PID gains for the specified control axis with validation.

        Args:
            axis (str): Control axis ('yawspeed_deg_s', 'z').

        Returns:
            Tuple[float, float, float]: (P, I, D) gains for the specified axis.

        Raises:
            ValueError: If axis is not supported or gains are invalid.
        """
        try:
            if axis not in Parameters.PID_GAINS:
                raise ValueError(f"Unsupported PID axis '{axis}'. Available: {list(Parameters.PID_GAINS.keys())}")
            
            gains = Parameters.PID_GAINS[axis]
            p_gain = gains['p']
            i_gain = gains['i'] 
            d_gain = gains['d']
            
            # Validate gain values
            if any(not isinstance(gain, (int, float)) or gain < 0 for gain in [p_gain, i_gain, d_gain]):
                raise ValueError(f"Invalid PID gains for axis '{axis}': P={p_gain}, I={i_gain}, D={d_gain}")
            
            logger.debug(f"Retrieved PID gains for {axis}: P={p_gain}, I={i_gain}, D={d_gain}")
            return (p_gain, i_gain, d_gain)
            
        except KeyError as e:
            logger.error(f"Missing PID configuration for axis '{axis}': {e}")
            raise ValueError(f"PID gains not configured for axis '{axis}'")
        except Exception as e:
            logger.error(f"Error retrieving PID gains for axis '{axis}': {e}")
            raise
    
    def _update_pid_gains(self) -> bool:
        """
        Updates all PID controller gains with current parameter values.

        Uses base class _update_pid_gains_from_config() method to eliminate code duplication.

        Returns:
            bool: True if update successful, False otherwise.
        """
        try:
            # Use base class method for consistent PID gain updates
            self._update_pid_gains_from_config(self.pid_yaw_rate, 'mc_yawspeed_deg_s', 'MC Velocity Position')

            if self.pid_z is not None:
                self._update_pid_gains_from_config(self.pid_z, 'mc_altitude', 'MC Velocity Position')

            logger.debug("PID gains updated successfully for MCVelocityPositionFollower")
            return True

        except Exception as e:
            logger.error(f"Failed to update PID gains: {e}")
            return False
    
    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculates and applies control commands based on target coordinates.
        
        This method implements the core control logic for constant position following:
        1. Validates input target coordinates
        2. Updates PID controller gains
        3. Calculates yaw rate command to center target horizontally
        4. Calculates altitude command if altitude control is enabled
        5. Applies commands using schema-aware field setters
        
        Args:
            tracker_data (TrackerOutput): Structured tracker data with position and metadata.
                                               
        Raises:
            ValueError: If tracker data is invalid.
            RuntimeError: If command calculation or application fails.
        """
        # Extract target coordinates
        target_coords = self.extract_target_coordinates(tracker_data)
        if not target_coords:
            raise ValueError("No valid target coordinates in tracker data")
        
        # Validate input coordinates
        if not self.validate_target_coordinates(target_coords):
            raise ValueError(f"Invalid target coordinates: {target_coords}")
        
        try:
            # Update PID gains to reflect any parameter changes
            if not self._update_pid_gains():
                logger.warning("Failed to update PID gains, using previous values")
            
            # Extract target coordinates
            target_x, target_y = target_coords
            
            # === YAW CONTROL CALCULATION ===
            # Positive normalized X means image-right. MAVSDK body yaw rate is
            # positive clockwise, so the command follows the signed image error.
            yaw_error = self.image_axis_error(target_x, self.pid_yaw_rate.setpoint)

            # Apply yaw control with PID dead zone gating
            if abs(yaw_error) > self.yaw_control_threshold:
                yaw_rate_raw = self.positive_image_axis_pid_command(
                    self.pid_yaw_rate,
                    target_x,
                )
            else:
                # Within dead zone — pass zero to smoother (it will decay smoothly)
                yaw_rate_raw = 0.0
                logger.debug(f"Yaw within dead zone: error={yaw_error:.3f}")

            # SafetyManager and the PID operate in rad/s; the shared smoother's
            # public contract and configuration are explicitly deg/s.
            yaw_rate_raw_deg_s = degrees(yaw_rate_raw)

            # Apply YawRateSmoother (deadzone + rate-limiting + speed-scaling + EMA)
            now = time.time()
            dt = now - self._last_update_time
            self._last_update_time = now
            yawspeed_deg_s = self.yaw_smoother.apply(yaw_rate_raw_deg_s, dt)
            self._last_yaw_command = yawspeed_deg_s
            logger.debug(
                "Yaw command: raw=%.3f rad/s (%.3f deg/s), smoothed=%.3f deg/s",
                yaw_rate_raw,
                yaw_rate_raw_deg_s,
                yawspeed_deg_s,
            )
            
            # === ALTITUDE CONTROL CALCULATION ===
            vertical_velocity_up_m_s = 0.0
            if self.altitude_control_enabled and self.pid_z is not None:
                # Pass measurement directly — PID computes error internally
                vertical_velocity_up_raw_m_s = self._calculate_altitude_command(target_y)

                # Apply smoothing if enabled
                if self.command_smoothing_enabled:
                    vertical_velocity_up_m_s = (
                        self.smoothing_factor * self._last_vertical_velocity_up_m_s
                        + (1 - self.smoothing_factor) * vertical_velocity_up_raw_m_s
                    )
                else:
                    vertical_velocity_up_m_s = vertical_velocity_up_raw_m_s

                self._last_vertical_velocity_up_m_s = vertical_velocity_up_m_s
                logger.debug(
                    "Altitude control: target_y=%.3f, vertical_up=%.3f m/s",
                    target_y,
                    vertical_velocity_up_m_s,
                )
            else:
                vertical_velocity_up_m_s = 0.0
                self._last_vertical_velocity_up_m_s = 0.0
                logger.debug("Altitude control disabled; vertical velocity is zero")
            
            # === APPLY COMMANDS USING SCHEMA-AWARE METHODS ===
            # Schema now uses velocity_body_offboard with yawspeed_deg_s and vel_body_down
            # Convert internal commands to schema fields
            vel_body_down = -vertical_velocity_up_m_s

            if not self.set_command_fields(
                {
                    'vel_body_fwd': 0.0,
                    'vel_body_right': 0.0,
                    'vel_body_down': vel_body_down,
                    'yawspeed_deg_s': yawspeed_deg_s,
                },
                reason='mc_velocity_position_normal_tracking',
            ):
                raise RuntimeError("Failed to apply MC velocity position command intent")
            
            # Update statistics
            self._control_statistics['pid_updates'] += 1
            self._control_statistics['last_update_time'] = datetime.utcnow().isoformat()
            
                        
        except ValueError:
            raise  # Re-raise validation errors
        except Exception as e:
            logger.error(f"Error calculating control commands: {e}")
            raise RuntimeError(f"Control command calculation failed: {e}")
    
    def _calculate_altitude_command(self, target_y: float) -> float:
        """
        Calculates altitude command with safety limits and current altitude consideration.

        Args:
            target_y (float): Current vertical target position measurement.
                              PID computes error = setpoint - target_y internally.

        Returns:
            float: Safe altitude velocity command within configured limits.
        """
        try:
            # Get current altitude for safety checks
            current_altitude = getattr(self.px4_controller, 'current_altitude', None)

            # Safety check: Ensure altitude data is available
            if current_altitude is None:
                logger.warning("Unable to get current altitude - halting altitude control for safety")
                return 0.0

            # Calculate PID output (PID computes error = setpoint - target_y internally)
            vertical_velocity_up_raw_m_s = self.pid_z(target_y)

            # Positive is up internally; body-frame conversion happens at publication.
            if current_altitude <= self.min_descent_height and vertical_velocity_up_raw_m_s < 0:
                logger.warning(f"Altitude safety limit reached: {current_altitude:.1f}m <= {self.min_descent_height:.1f}m")
                return 0.0  # Stop descent

            if current_altitude >= self.max_climb_height and vertical_velocity_up_raw_m_s > 0:
                logger.warning(f"Altitude safety: Current {current_altitude:.1f}m at maximum, preventing climb")
                return 0.0  # Stop climb

            # Apply velocity limiting
            vertical_velocity_up_m_s = max(
                -self.max_vertical_velocity,
                min(self.max_vertical_velocity, vertical_velocity_up_raw_m_s),
            )

            if abs(vertical_velocity_up_m_s - vertical_velocity_up_raw_m_s) > 0.001:
                logger.debug(
                    "Altitude command limited: %.3f -> %.3f m/s up",
                    vertical_velocity_up_raw_m_s,
                    vertical_velocity_up_m_s,
                )

            return vertical_velocity_up_m_s

        except Exception as e:
            logger.error(f"Error calculating altitude command: {e}")
            return 0.0  # Safe default
    
    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Executes target following by calculating and applying control commands.
        
        This is the main execution method called by the control loop. It orchestrates
        the complete control process while maintaining robust error handling.
        
        Args:
            tracker_data (TrackerOutput): Structured tracker data with position and metadata.
            
        Raises:
            ValueError: If target coordinates are invalid.
            RuntimeError: If control execution fails.
        """
        try:
            inactive_output = self.should_process_inactive_tracker_output(tracker_data)

            # Validate tracker compatibility (errors are logged by base class with rate limiting)
            if (
                not self.validate_tracker_compatibility(tracker_data) and
                not inactive_output
            ):
                return False

            if inactive_output:
                return self._handle_inactive_tracker_output()

            # Extract target coordinates
            target_coords = self.extract_target_coordinates(tracker_data)
            if not target_coords:
                logger.warning("No valid target coordinates found in tracker data")
                return False

            # Calculate and apply control commands using structured data
            self.calculate_control_commands(tracker_data)

            # Update execution statistics
            self._control_statistics['commands_sent'] += 1

            # Update telemetry metadata
            self.update_telemetry_metadata('last_target_coords', target_coords)
            self.update_telemetry_metadata('control_active', True)

            logger.debug(f"Following target at coordinates: {target_coords}")
            return True

        except ValueError as e:
            # Validation errors - these indicate bad configuration or state
            logger.error(f"Validation error in {self.__class__.__name__}: {e}")
            self.update_telemetry_metadata('control_active', False)
            self.update_telemetry_metadata('last_error', str(e))
            raise  # Re-raise validation errors

        except RuntimeError as e:
            # Command execution errors - these indicate system failures
            logger.error(f"Runtime error in {self.__class__.__name__}: {e}")
            self.reset_command_fields()  # Reset to safe state
            self.update_telemetry_metadata('control_active', False)
            self.update_telemetry_metadata('last_error', str(e))
            return False

        except Exception as e:
            # Unexpected errors - log and fail safe
            logger.error(f"Unexpected error in {self.__class__.__name__}.follow_target(): {e}")
            self.reset_command_fields()
            self.update_telemetry_metadata('control_active', False)
            self.update_telemetry_metadata('last_error', str(e))
            return False

    def _handle_inactive_tracker_output(self) -> bool:
        """Publish an explicit hold command for inactive vision target output."""
        self._last_yaw_command = 0.0
        self._last_vertical_velocity_up_m_s = 0.0
        self._last_update_time = time.time()
        if not self.set_command_fields(
            {
                'vel_body_fwd': 0.0,
                'vel_body_right': 0.0,
                'vel_body_down': 0.0,
                'yawspeed_deg_s': 0.0,
            },
            reason='mc_velocity_position_inactive_hold',
        ):
            return False
        self.update_telemetry_metadata('target_valid', False)
        self.update_telemetry_metadata('target_lost', True)
        self.update_telemetry_metadata('control_active', False)
        logger.warning("Inactive tracker output received - holding position follower command")
        return True

    def should_process_inactive_tracker_output(self, tracker_data: TrackerOutput) -> bool:
        """
        Allow inactive position outputs to publish an explicit hold command.

        Inactive tracker output must not run normal pursuit math even when it
        carries last-known valid coordinates.
        """
        return self._is_inactive_tracker_output(
            tracker_data,
            allowed_types={
                TrackerDataType.POSITION_2D,
                TrackerDataType.POSITION_3D,
                TrackerDataType.BBOX_CONFIDENCE,
                TrackerDataType.VELOCITY_AWARE,
                TrackerDataType.MULTI_TARGET,
            },
        )
    
    # ==================== Enhanced Status and Monitoring ====================
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Returns detailed performance metrics for monitoring and optimization.
        
        Returns:
            Dict[str, Any]: Comprehensive performance data including PID status,
                           command statistics, and control health indicators.
        """
        try:
            metrics = {
                # Control statistics
                'control_statistics': self._control_statistics.copy(),
                
                # PID controller status
                'pid_status': {
                    'yaw_rate_enabled': True,
                    'altitude_enabled': self.altitude_control_enabled,
                    'horizontal_target_setpoint': self.pid_yaw_rate.setpoint,
                    'altitude_setpoint': self.pid_z.setpoint if self.pid_z else None
                },
                
                # Current control values
                'current_commands': self.get_all_command_fields(),
                
                # Configuration status
                'configuration': {
                    'yaw_control_threshold': self.yaw_control_threshold,
                    'max_yaw_rate': self.max_yaw_rate,
                    'max_vertical_velocity': self.max_vertical_velocity,
                    'min_descent_height': self.min_descent_height,
                    'altitude_control_enabled': self.altitude_control_enabled,
                    'command_smoothing_enabled': self.command_smoothing_enabled
                },
                
                # Health indicators
                'health_status': {
                    'pid_controllers_healthy': self._check_pid_health(),
                    'field_validation_passed': self.validate_profile_consistency(),
                    'last_successful_update': self._control_statistics.get('last_update_time')
                }
            }
            
            return metrics
            
        except Exception as e:
            logger.error(f"Error generating performance metrics: {e}")
            return {'error': str(e), 'timestamp': datetime.utcnow().isoformat()}
    
    def _check_pid_health(self) -> bool:
        """
        Performs health check on PID controllers.
        
        Returns:
            bool: True if all enabled PID controllers are healthy.
        """
        try:
            # Check yaw rate PID
            if self.pid_yaw_rate is None:
                return False
            
            # Check altitude PID if enabled
            if self.altitude_control_enabled and self.pid_z is None:
                return False
            
            # Additional health checks could be added here
            # (e.g., checking for NaN values, excessive outputs, etc.)
            
            return True
            
        except Exception as e:
            logger.error(f"PID health check failed: {e}")
            return False
    
    def get_control_status_summary(self) -> str:
        """
        Generates a concise status summary for quick diagnostics.
        
        Returns:
            str: Human-readable status summary.
        """
        try:
            fields = self.get_all_command_fields()
            # Translate body-offboard fields to a readable summary
            vel_body_down = fields.get('vel_body_down', 0.0)
            yawspeed_deg_s = fields.get('yawspeed_deg_s', 0.0)
            vertical_velocity_up_m_s = -vel_body_down
            
            status = f"ConstantPosition: "
            status += f"Yaw={yawspeed_deg_s:.1f}deg/s, "
            status += f"Alt={'EN' if self.altitude_control_enabled else 'DIS'}"
            if self.altitude_control_enabled:
                status += f"({vertical_velocity_up_m_s:.3f}m/s up)"
            
            # Add activity indicator
            if abs(yawspeed_deg_s) > 0.001 or abs(vertical_velocity_up_m_s) > 0.001:
                status += " [ACTIVE]"
            else:
                status += " [IDLE]"
            
            return status
            
        except Exception as e:
            return f"Status unavailable: {e}"
    
    # ==================== Utility and Debugging Methods ====================
    
    def reset_pid_controllers(self) -> bool:
        """
        Resets all PID controllers to initial state.
        
        Returns:
            bool: True if reset successful, False otherwise.
        """
        try:
            if hasattr(self.pid_yaw_rate, 'reset'):
                self.pid_yaw_rate.reset()
            
            if self.pid_z and hasattr(self.pid_z, 'reset'):
                self.pid_z.reset()
            
            logger.info("PID controllers reset successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset PID controllers: {e}")
            return False
    
    def update_setpoints(self, new_target_coords: Tuple[float, float]) -> bool:
        """
        Updates PID controller setpoints with new target coordinates.
        
        Args:
            new_target_coords (Tuple[float, float]): New target coordinates for setpoints.
            
        Returns:
            bool: True if update successful, False otherwise.
        """
        try:
            if not self.validate_target_coordinates(new_target_coords):
                return False
            
            setpoint_x, setpoint_y = new_target_coords
            
            # Update yaw rate setpoint
            self.pid_yaw_rate.setpoint = setpoint_x
            
            # Update altitude setpoint if controller exists
            if self.pid_z:
                self.pid_z.setpoint = setpoint_y
            
            self.initial_target_coords = new_target_coords
            logger.info(f"PID setpoints updated to: {new_target_coords}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update setpoints: {e}")
            return False
    
    # ==================== Enhanced Telemetry Override ====================
    
    def get_follower_telemetry(self) -> Dict[str, Any]:
        """
        Returns enhanced telemetry data specific to constant position following.
        
        Returns:
            Dict[str, Any]: Comprehensive telemetry including base data plus
                           constant position specific metrics and status.
        """
        try:
            # Get base telemetry from parent class
            base_telemetry = super().get_follower_telemetry()
            
            # Add constant position specific data
            constant_position_data = {
                'follower_type': 'ConstantPosition',
                'control_summary': self.get_control_status_summary(),
                'performance_metrics': self.get_performance_metrics(),
                'setpoints': {
                    'horizontal_target_normalized': self.pid_yaw_rate.setpoint,
                    'altitude': self.pid_z.setpoint if self.pid_z else None
                }
            }
            
            # Merge telemetry data
            enhanced_telemetry = {**base_telemetry, **constant_position_data}
            
            return enhanced_telemetry
            
        except Exception as e:
            logger.error(f"Error generating enhanced telemetry: {e}")
            # Return base telemetry with error info on failure
            base_telemetry = super().get_follower_telemetry()
            base_telemetry['telemetry_error'] = str(e)
            return base_telemetry
