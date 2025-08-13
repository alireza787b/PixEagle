# src/classes/followers/constant_position_follower.py

"""
Constant Position Follower Module
---------------------------------

This module implements the ConstantPositionFollower class for drone control in aerial target tracking.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: December 2024  
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The ConstantPositionFollower is designed to maintain the drone's horizontal position while allowing
only yaw rotation and optional altitude adjustments to keep the target in the camera's field of view.
This mode is ideal for maintaining a stationary observation point while tracking moving targets.

Control Strategy:
----------------
- **NO lateral movement**: vel_x and vel_y are not used (kept at 0)
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
follower = ConstantPositionFollower(px4_controller, (0.0, 0.0))
await follower.follow_target((0.1, -0.05))  # Small target deviation
```

Technical Details:
------------------
- Uses only 'vel_z' and 'yaw_rate' command fields from the schema
- Implements constant acceleration PID controllers  
- Enforces schema-defined field limits and validation
- Provides comprehensive telemetry for monitoring and debugging
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
import logging
from typing import Tuple, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class ConstantPositionFollower(BaseFollower):
    """
    Advanced constant position follower for drone control with schema-aware field management.
    
    This follower maintains the drone's horizontal position while enabling yaw rotation
    and optional altitude control to track targets. Designed for stationary observation
    scenarios with precise target tracking capabilities.
    
    Control Fields Used:
    - vel_z: Vertical velocity for altitude control (optional)
    - yaw_rate: Yaw rotation rate for horizontal target centering (always enabled)
    
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
        Initializes the ConstantPositionFollower with schema-aware configuration.

        Args:
            px4_controller: Instance of PX4Controller for drone control interface.
            initial_target_coords (Tuple[float, float]): Initial target coordinates for 
                                                        PID controller setpoints.
                                                        
        Raises:
            ValueError: If initial_target_coords are invalid or schema validation fails.
            RuntimeError: If PID initialization fails.
            
        Note:
            Uses "Constant Position" profile which provides vel_z and yaw_rate fields only.
        """
        # Initialize with schema-aware base class
        super().__init__(px4_controller, "Constant Position")
        
        # Validate and store initial coordinates
        if not self.validate_target_coordinates(initial_target_coords):
            raise ValueError(f"Invalid initial target coordinates: {initial_target_coords}")
        
        self.initial_target_coords = initial_target_coords
        
        # Control configuration
        self.yaw_control_enabled = True  # Always enabled for this mode
        self.altitude_control_enabled = Parameters.ENABLE_ALTITUDE_CONTROL
        
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
            self.update_telemetry_metadata('control_mode', 'constant_position')
            self.update_telemetry_metadata('yaw_enabled', self.yaw_control_enabled)
            self.update_telemetry_metadata('altitude_enabled', self.altitude_control_enabled)
            
            logger.info(f"ConstantPositionFollower initialized successfully. "
                       f"Yaw: enabled, Altitude: {'enabled' if self.altitude_control_enabled else 'disabled'}")
                       
        except Exception as e:
            logger.error(f"Failed to initialize ConstantPositionFollower: {e}")
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
            yaw_gains = self._get_pid_gains('yaw_rate')
            self.pid_yaw_rate = CustomPID(
                *yaw_gains,
                setpoint=setpoint_x,
                output_limits=(-Parameters.MAX_YAW_RATE, Parameters.MAX_YAW_RATE)
            )
            logger.debug(f"Yaw rate PID initialized with gains {yaw_gains}, setpoint {setpoint_x}")
            
            # Initialize altitude PID controller if enabled
            self.pid_z = None
            if self.altitude_control_enabled:
                z_gains = self._get_pid_gains('z')
                self.pid_z = CustomPID(
                    *z_gains,
                    setpoint=setpoint_y,
                    output_limits=(-Parameters.VELOCITY_LIMITS['z'], Parameters.VELOCITY_LIMITS['z'])
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
            axis (str): Control axis ('yaw_rate', 'z').

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
        
        Returns:
            bool: True if update successful, False otherwise.
        """
        try:
            # Update yaw rate PID gains
            yaw_gains = self._get_pid_gains('yaw_rate')
            self.pid_yaw_rate.tunings = yaw_gains
            
            # Update altitude PID gains if controller exists
            if self.pid_z is not None:
                z_gains = self._get_pid_gains('z')
                self.pid_z.tunings = z_gains
            
            logger.debug("PID gains updated successfully for ConstantPositionFollower")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update PID gains: {e}")
            return False
    
    def calculate_control_commands(self, target_coords: Tuple[float, float]) -> None:
        """
        Calculates and applies control commands based on target coordinates.
        
        This method implements the core control logic for constant position following:
        1. Validates input target coordinates
        2. Updates PID controller gains
        3. Calculates yaw rate command to center target horizontally
        4. Calculates altitude command if altitude control is enabled
        5. Applies commands using schema-aware field setters
        
        Args:
            target_coords (Tuple[float, float]): Normalized target coordinates from image processing
                                               where (0,0) represents image center.
                                               
        Raises:
            ValueError: If target coordinates are invalid.
            RuntimeError: If command calculation or application fails.
        """
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
            # Calculate horizontal error (target_x relative to image center)
            yaw_error = self.pid_yaw_rate.setpoint - target_x
            
            # Apply yaw control with dead zone to prevent unnecessary oscillation
            if abs(yaw_error) > Parameters.YAW_CONTROL_THRESHOLD:
                yaw_rate_command = self.pid_yaw_rate(yaw_error)
                logger.debug(f"Yaw control active: error={yaw_error:.3f}, command={yaw_rate_command:.3f}")
            else:
                yaw_rate_command = 0.0
                logger.debug(f"Yaw within dead zone: error={yaw_error:.3f}, no command sent")
            
            # === ALTITUDE CONTROL CALCULATION ===
            vel_z_command = 0.0
            if self.altitude_control_enabled and self.pid_z is not None:
                altitude_error = self.pid_z.setpoint - target_y
                vel_z_command = self._calculate_altitude_command(altitude_error)
                logger.debug(f"Altitude control: error={altitude_error:.3f}, command={vel_z_command:.3f}")
            else:
                logger.debug("Altitude control disabled, vel_z = 0")
            
            # === APPLY COMMANDS USING SCHEMA-AWARE METHODS ===
            # Set altitude command
            if not self.set_command_field('vel_z', vel_z_command):
                raise RuntimeError("Failed to set vel_z command")
            
            # Set yaw rate command  
            if not self.set_command_field('yaw_rate', yaw_rate_command):
                raise RuntimeError("Failed to set yaw_rate command")
            
            # Update statistics
            self._control_statistics['pid_updates'] += 1
            self._control_statistics['last_update_time'] = datetime.utcnow().isoformat()
            
            # Log command summary
            logger.debug(f"Commands calculated - Vel_z: {vel_z_command:.3f} m/s, "
                        f"Yaw_rate: {yaw_rate_command:.3f} rad/s")
                        
        except ValueError:
            raise  # Re-raise validation errors
        except Exception as e:
            logger.error(f"Error calculating control commands: {e}")
            raise RuntimeError(f"Control command calculation failed: {e}")
    
    def _calculate_altitude_command(self, altitude_error: float) -> float:
        """
        Calculates altitude command with safety limits and current altitude consideration.
        
        Args:
            altitude_error (float): Vertical position error from PID setpoint.
            
        Returns:
            float: Safe altitude velocity command within configured limits.
        """
        try:
            # Get current altitude for safety checks
            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)
            
            # Check minimum altitude safety limit
            if (current_altitude <= Parameters.MIN_DESCENT_HEIGHT and altitude_error < 0):
                logger.warning(f"Altitude safety limit reached: {current_altitude:.1f}m <= {Parameters.MIN_DESCENT_HEIGHT:.1f}m")
                return 0.0  # Stop descent
            
            # Calculate PID output
            vel_z_raw = self.pid_z(altitude_error)
            
            # Apply additional safety limiting
            max_rate = Parameters.VELOCITY_LIMITS.get('z', 2.0)
            vel_z_limited = max(-max_rate, min(max_rate, vel_z_raw))
            
            if abs(vel_z_limited - vel_z_raw) > 0.001:
                logger.debug(f"Altitude command limited: {vel_z_raw:.3f} -> {vel_z_limited:.3f}")
            
            return vel_z_limited
            
        except Exception as e:
            logger.error(f"Error calculating altitude command: {e}")
            return 0.0  # Safe default
    
    async def follow_target(self, target_coords: Tuple[float, float]):
        """
        Executes target following by calculating and applying control commands.
        
        This is the main execution method called by the control loop. It orchestrates
        the complete control process while maintaining robust error handling.
        
        Args:
            target_coords (Tuple[float, float]): Current target coordinates from tracking.
            
        Raises:
            ValueError: If target coordinates are invalid.
            RuntimeError: If control execution fails.
        """
        try:
            # Calculate and apply control commands
            self.calculate_control_commands(target_coords)
            
            # Update execution statistics
            self._control_statistics['commands_sent'] += 1
            
            # Update telemetry metadata
            self.update_telemetry_metadata('last_target_coords', target_coords)
            self.update_telemetry_metadata('control_active', True)
            
            logger.debug(f"Following target at coordinates: {target_coords}")
            
        except Exception as e:
            logger.error(f"Failed to follow target at {target_coords}: {e}")
            # Update error status in telemetry
            self.update_telemetry_metadata('control_active', False)
            self.update_telemetry_metadata('last_error', str(e))
            raise
    
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
                    'yaw_setpoint': self.pid_yaw_rate.setpoint,
                    'altitude_setpoint': self.pid_z.setpoint if self.pid_z else None
                },
                
                # Current control values
                'current_commands': self.get_all_command_fields(),
                
                # Configuration status
                'configuration': {
                    'yaw_control_threshold': Parameters.YAW_CONTROL_THRESHOLD,
                    'max_yaw_rate': Parameters.MAX_YAW_RATE,
                    'velocity_limits': Parameters.VELOCITY_LIMITS.get('z', 'undefined'),
                    'min_descent_height': Parameters.MIN_DESCENT_HEIGHT
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
            vel_z = fields.get('vel_z', 0.0)
            yaw_rate = fields.get('yaw_rate', 0.0)
            
            status = f"ConstantPosition: "
            status += f"Yaw={yaw_rate:.3f}rad/s, "
            status += f"Alt={'EN' if self.altitude_control_enabled else 'DIS'}"
            if self.altitude_control_enabled:
                status += f"({vel_z:.3f}m/s)"
            
            # Add activity indicator
            if abs(yaw_rate) > 0.001 or abs(vel_z) > 0.001:
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
                    'yaw_rate': self.pid_yaw_rate.setpoint,
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