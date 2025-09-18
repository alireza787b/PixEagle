# src/classes/followers/gimbal_follower.py

"""
GimbalFollower Module
====================

This module implements the GimbalFollower class, which converts gimbal angle data
to velocity commands for drone control. It supports both NED and Body velocity
control modes with configurable switching.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The GimbalFollower extends BaseFollower to provide:
- Unified NED/Body velocity control from gimbal target vectors
- Real-time coordinate transformations with aircraft attitude integration
- PID-based velocity control for smooth target following
- Safety limits and altitude monitoring
- Schema-driven configuration and command field management

Key Features:
-------------
- Dual control modes: NED (absolute) and Body (relative) velocity control
- Runtime mode switching via configuration
- Vector-to-velocity conversion with configurable scaling
- Integration with MAVLink2REST for aircraft attitude
- Safety limits and emergency stop capability
- Velocity ramping for smooth acceleration/deceleration

Control Modes:
--------------
1. **NED Mode**: Uses vel_x, vel_y, vel_z, yaw_angle_deg
   - Absolute positioning relative to North-East-Down frame
   - Best for GPS-based waypoint navigation
   - Uses aircraft attitude for coordinate transformations

2. **Body Mode**: Uses vel_body_fwd, vel_body_right, vel_body_down, yaw_speed_deg_s
   - Relative movement in aircraft body frame
   - Best for close-proximity following and agile maneuvers
   - Direct conversion from gimbal target vectors

Usage:
------
```python
follower = GimbalFollower(px4_controller, "gimbal_unified")
success = follower.follow_target(tracker_output)
```

Integration:
-----------
This follower integrates with:
- GimbalTracker for angle data input
- MAVLink2REST for aircraft attitude
- PixEagle's schema-driven setpoint system
- PX4 offboard control modes
"""

import time
import math
import numpy as np
import logging
import asyncio
from typing import Tuple, Optional, Dict, Any
from datetime import datetime

from classes.followers.base_follower import BaseFollower
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.coordinate_transformer import CoordinateTransformer, FrameType
from classes.parameters import Parameters

logger = logging.getLogger(__name__)

class ControlMode:
    """Control mode constants"""
    NED = "NED"
    BODY = "BODY"

class GimbalFollower(BaseFollower):
    """
    Unified gimbal follower supporting both NED and Body velocity control modes.

    This follower receives target vectors from GimbalTracker and converts them
    to appropriate velocity commands based on the configured control mode.
    It provides smooth, responsive following behavior with safety monitoring.

    Attributes:
    -----------
    - control_mode (str): Active control mode (NED or BODY)
    - coordinate_transformer (CoordinateTransformer): Coordinate conversion utilities
    - base_velocity (float): Base velocity magnitude for target following
    - max_velocity (float): Maximum allowed velocity
    - current_velocity (float): Current velocity magnitude with ramping
    - last_update_time (float): Timestamp of last update for dt calculation
    """

    def __init__(self, px4_controller, profile_name: str = "gimbal_unified"):
        """
        Initialize GimbalFollower with configurable control mode.

        Args:
            px4_controller: PX4 controller instance for sending commands
            profile_name (str): Follower profile name from schema
        """
        super().__init__(px4_controller, profile_name)

        # Get control mode from configuration
        self.control_mode = getattr(Parameters, 'GIMBAL_CONTROL_MODE', ControlMode.BODY)

        # Configure dynamic command fields based on control mode
        self._configure_command_fields()

        # Initialize coordinate transformer
        self.coordinate_transformer = CoordinateTransformer()

        # Velocity control parameters
        self.base_velocity = getattr(Parameters, 'GIMBAL_BASE_VELOCITY', 2.0)
        self.max_velocity = getattr(Parameters, 'GIMBAL_MAX_VELOCITY', 8.0)
        self.velocity_ramp_rate = getattr(Parameters, 'GIMBAL_VELOCITY_RAMP_RATE', 1.0)

        # Current state
        self.current_velocity = 0.0
        self.target_velocity = self.base_velocity
        self.last_update_time = time.time()
        self.last_target_vector: Optional[np.ndarray] = None

        # Safety parameters
        self.min_altitude_safety = getattr(Parameters, 'GIMBAL_MIN_ALTITUDE_SAFETY', 3.0)
        self.safety_return_speed = getattr(Parameters, 'GIMBAL_SAFETY_RETURN_SPEED', 3.0)
        self.emergency_stop_active = False

        # Smoothing and filtering
        self.velocity_filter_alpha = getattr(Parameters, 'GIMBAL_VELOCITY_FILTER_ALPHA', 0.7)
        self.smoothed_velocities = np.array([0.0, 0.0, 0.0])

        # Statistics
        self.total_follow_calls = 0
        self.successful_follow_calls = 0

        # Update telemetry metadata
        self._update_follower_metadata()

        logger.info(f"GimbalFollower initialized - Mode: {self.control_mode}, "
                   f"Base velocity: {self.base_velocity:.1f} m/s")

    def _configure_command_fields(self) -> None:
        """Configure command fields based on active control mode."""
        try:
            if self.control_mode == ControlMode.NED:
                # NED mode uses global velocity commands
                self.required_fields = ["vel_x", "vel_y", "vel_z"]
                self.optional_fields = ["yaw_angle_deg"]
                self.control_type = "velocity_body"  # PixEagle's NED velocity mode

            elif self.control_mode == ControlMode.BODY:
                # Body mode uses body frame velocity commands
                self.required_fields = ["vel_body_fwd", "vel_body_right", "vel_body_down"]
                self.optional_fields = ["yaw_speed_deg_s"]
                self.control_type = "velocity_body_offboard"  # PixEagle's body velocity mode

            else:
                # Default to body mode
                logger.warning(f"Unknown control mode '{self.control_mode}', defaulting to BODY")
                self.control_mode = ControlMode.BODY
                self._configure_command_fields()
                return

            logger.debug(f"Configured for {self.control_mode} mode - "
                        f"Required: {self.required_fields}, Optional: {self.optional_fields}")

        except Exception as e:
            logger.error(f"Error configuring command fields: {e}")

    def _update_follower_metadata(self) -> None:
        """Update telemetry metadata with current configuration."""
        try:
            self.update_telemetry_metadata('control_mode', self.control_mode)
            self.update_telemetry_metadata('control_type', self.control_type)
            self.update_telemetry_metadata('base_velocity', self.base_velocity)
            self.update_telemetry_metadata('max_velocity', self.max_velocity)
            self.update_telemetry_metadata('coordinate_transformer', 'CoordinateTransformer')
            self.update_telemetry_metadata('gimbal_follower_version', '1.0')

        except Exception as e:
            logger.debug(f"Error updating metadata: {e}")

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Execute gimbal-based target following with unified NED/Body control.

        Args:
            tracker_data (TrackerOutput): Tracker output containing gimbal angle data

        Returns:
            bool: True if following executed successfully, False otherwise
        """
        self.total_follow_calls += 1

        try:
            # Validate tracker compatibility
            if not self.validate_tracker_compatibility(tracker_data):
                logger.error("Tracker data incompatible with GimbalFollower")
                return False

            # Extract target data from tracker output
            target_data = self._extract_target_data(tracker_data)
            if not target_data:
                logger.warning("No valid target data found in tracker output")
                return False

            # Check safety conditions
            if not self._check_safety_conditions():
                logger.warning("Safety check failed - applying emergency stop")
                self._apply_emergency_stop()
                return False

            # Calculate velocity commands based on control mode
            success = self._calculate_and_apply_commands(target_data, tracker_data)

            if success:
                self.successful_follow_calls += 1
                logger.debug(f"Gimbal following successful - Mode: {self.control_mode}")

            return success

        except Exception as e:
            logger.error(f"Error in gimbal following: {e}")
            self._apply_emergency_stop()
            return False

    def _extract_target_data(self, tracker_data: TrackerOutput) -> Optional[Dict[str, Any]]:
        """
        Extract target data from tracker output.

        Args:
            tracker_data (TrackerOutput): Tracker output

        Returns:
            Optional[Dict[str, Any]]: Extracted target data or None
        """
        try:
            target_data = {}

            # Primary data: gimbal angles
            if tracker_data.angular is not None:
                target_data['gimbal_angles'] = tracker_data.angular
                yaw, pitch, roll = tracker_data.angular
                target_data['gimbal_yaw'] = yaw
                target_data['gimbal_pitch'] = pitch
                target_data['gimbal_roll'] = roll

            # Secondary data: normalized position (if available)
            if tracker_data.position_2d is not None:
                target_data['normalized_position'] = tracker_data.position_2d

            # Additional data from raw_data
            if tracker_data.raw_data:
                if 'target_vector_body' in tracker_data.raw_data:
                    target_data['target_vector_body'] = np.array(tracker_data.raw_data['target_vector_body'])

                if 'aircraft_attitude' in tracker_data.raw_data:
                    target_data['aircraft_attitude'] = tracker_data.raw_data['aircraft_attitude']

            # Validate we have minimum required data
            if 'gimbal_angles' not in target_data:
                logger.warning("No gimbal angles found in tracker data")
                return None

            # Calculate target vector if not provided
            if 'target_vector_body' not in target_data:
                yaw, pitch, roll = target_data['gimbal_angles']
                target_vector = self.coordinate_transformer.gimbal_angles_to_body_vector(
                    yaw, pitch, roll, include_mount_offset=True
                )
                target_data['target_vector_body'] = target_vector

            return target_data

        except Exception as e:
            logger.error(f"Error extracting target data: {e}")
            return None

    def _calculate_and_apply_commands(self, target_data: Dict[str, Any],
                                    tracker_data: TrackerOutput) -> bool:
        """
        Calculate velocity commands and apply them based on control mode.

        Args:
            target_data (Dict[str, Any]): Extracted target data
            tracker_data (TrackerOutput): Original tracker data

        Returns:
            bool: True if commands applied successfully
        """
        try:
            # Update velocity ramping
            dt = self._update_timing()
            self._update_velocity_ramping(dt)

            # Get target vector
            target_vector = target_data['target_vector_body']

            # Apply velocity scaling
            velocity_vector = target_vector * self.current_velocity

            # Apply velocity smoothing
            velocity_vector = self._apply_velocity_smoothing(velocity_vector)

            # Convert to control commands based on mode
            if self.control_mode == ControlMode.NED:
                return self._apply_ned_commands(velocity_vector, target_data, tracker_data)
            elif self.control_mode == ControlMode.BODY:
                return self._apply_body_commands(velocity_vector, target_data, tracker_data)
            else:
                logger.error(f"Unknown control mode: {self.control_mode}")
                return False

        except Exception as e:
            logger.error(f"Error calculating velocity commands: {e}")
            return False

    def _apply_ned_commands(self, velocity_vector: np.ndarray,
                          target_data: Dict[str, Any],
                          tracker_data: TrackerOutput) -> bool:
        """
        Apply NED velocity commands.

        Args:
            velocity_vector (np.ndarray): Velocity vector in body frame
            target_data (Dict[str, Any]): Target data
            tracker_data (TrackerOutput): Tracker data

        Returns:
            bool: True if commands applied successfully
        """
        try:
            # Get aircraft attitude for coordinate transformation
            aircraft_attitude = self._get_aircraft_attitude()
            if aircraft_attitude:
                aircraft_yaw_rad = math.radians(aircraft_attitude.get('yaw', 0.0))
            else:
                aircraft_yaw_rad = 0.0
                logger.warning("No aircraft attitude available, assuming yaw=0")

            # Transform body velocity to NED frame
            ned_velocity = self.coordinate_transformer.body_to_ned_vector(
                velocity_vector, aircraft_yaw_rad
            )

            # Calculate target yaw angle (optional)
            target_yaw_deg = self._calculate_target_yaw(target_data, aircraft_attitude)

            # Apply velocity limits
            ned_velocity = self._apply_velocity_limits(ned_velocity)

            # Set commands
            self.set_command_field('vel_x', ned_velocity[0])      # North velocity
            self.set_command_field('vel_y', ned_velocity[1])      # East velocity
            self.set_command_field('vel_z', ned_velocity[2])      # Down velocity

            if target_yaw_deg is not None:
                self.set_command_field('yaw_angle_deg', target_yaw_deg)

            logger.debug(f"NED commands - N: {ned_velocity[0]:.2f}, E: {ned_velocity[1]:.2f}, "
                        f"D: {ned_velocity[2]:.2f}, Yaw: {target_yaw_deg}")

            return True

        except Exception as e:
            logger.error(f"Error applying NED commands: {e}")
            return False

    def _apply_body_commands(self, velocity_vector: np.ndarray,
                           target_data: Dict[str, Any],
                           tracker_data: TrackerOutput) -> bool:
        """
        Apply body velocity commands.

        Args:
            velocity_vector (np.ndarray): Velocity vector in body frame
            target_data (Dict[str, Any]): Target data
            tracker_data (TrackerOutput): Tracker data

        Returns:
            bool: True if commands applied successfully
        """
        try:
            # Apply velocity limits
            body_velocity = self._apply_velocity_limits(velocity_vector)

            # Calculate yaw rate (optional)
            yaw_rate_deg_s = self._calculate_yaw_rate(target_data)

            # Set body frame commands
            self.set_command_field('vel_body_fwd', body_velocity[0])    # Forward velocity
            self.set_command_field('vel_body_right', body_velocity[1])  # Right velocity
            self.set_command_field('vel_body_down', body_velocity[2])   # Down velocity

            if yaw_rate_deg_s is not None:
                self.set_command_field('yaw_speed_deg_s', yaw_rate_deg_s)

            logger.debug(f"Body commands - Fwd: {body_velocity[0]:.2f}, Right: {body_velocity[1]:.2f}, "
                        f"Down: {body_velocity[2]:.2f}, YawRate: {yaw_rate_deg_s}")

            return True

        except Exception as e:
            logger.error(f"Error applying body commands: {e}")
            return False

    def _update_timing(self) -> float:
        """
        Update timing and calculate delta time.

        Returns:
            float: Delta time since last update
        """
        current_time = time.time()
        dt = current_time - self.last_update_time
        self.last_update_time = current_time
        return dt

    def _update_velocity_ramping(self, dt: float) -> None:
        """
        Update velocity ramping for smooth acceleration.

        Args:
            dt (float): Delta time since last update
        """
        try:
            # Calculate velocity error
            velocity_error = self.target_velocity - self.current_velocity

            # Apply ramping
            if abs(velocity_error) < 0.01:
                self.current_velocity = self.target_velocity
            else:
                max_change = self.velocity_ramp_rate * dt
                velocity_change = np.clip(velocity_error, -max_change, max_change)
                self.current_velocity += velocity_change

            # Apply absolute limits
            self.current_velocity = np.clip(self.current_velocity, 0.0, self.max_velocity)

        except Exception as e:
            logger.error(f"Error updating velocity ramping: {e}")

    def _apply_velocity_smoothing(self, velocity_vector: np.ndarray) -> np.ndarray:
        """
        Apply velocity smoothing filter.

        Args:
            velocity_vector (np.ndarray): Raw velocity vector

        Returns:
            np.ndarray: Smoothed velocity vector
        """
        try:
            # Apply exponential smoothing filter
            alpha = self.velocity_filter_alpha
            self.smoothed_velocities = (alpha * self.smoothed_velocities +
                                      (1 - alpha) * velocity_vector)

            return self.smoothed_velocities.copy()

        except Exception as e:
            logger.error(f"Error applying velocity smoothing: {e}")
            return velocity_vector

    def _apply_velocity_limits(self, velocity_vector: np.ndarray) -> np.ndarray:
        """
        Apply velocity limits for safety.

        Args:
            velocity_vector (np.ndarray): Input velocity vector

        Returns:
            np.ndarray: Limited velocity vector
        """
        try:
            # Apply component-wise limits
            limited_velocity = velocity_vector.copy()

            # Limit each component
            limited_velocity[0] = np.clip(limited_velocity[0], -self.max_velocity, self.max_velocity)
            limited_velocity[1] = np.clip(limited_velocity[1], -self.max_velocity, self.max_velocity)
            limited_velocity[2] = np.clip(limited_velocity[2], -self.max_velocity/2, self.max_velocity/2)  # Conservative vertical

            # Limit total magnitude
            magnitude = np.linalg.norm(limited_velocity)
            if magnitude > self.max_velocity:
                limited_velocity = limited_velocity * (self.max_velocity / magnitude)

            return limited_velocity

        except Exception as e:
            logger.error(f"Error applying velocity limits: {e}")
            return velocity_vector

    def _calculate_target_yaw(self, target_data: Dict[str, Any],
                            aircraft_attitude: Optional[Dict]) -> Optional[float]:
        """
        Calculate target yaw angle for NED mode.

        Args:
            target_data (Dict[str, Any]): Target data
            aircraft_attitude (Optional[Dict]): Aircraft attitude data

        Returns:
            Optional[float]: Target yaw angle in degrees or None
        """
        try:
            # Simple approach: maintain current yaw + gimbal yaw offset
            if aircraft_attitude and 'gimbal_yaw' in target_data:
                aircraft_yaw = aircraft_attitude.get('yaw', 0.0)
                gimbal_yaw = target_data['gimbal_yaw']
                target_yaw = aircraft_yaw + gimbal_yaw

                # Normalize to [-180, 180]
                while target_yaw > 180:
                    target_yaw -= 360
                while target_yaw < -180:
                    target_yaw += 360

                return target_yaw

            return None

        except Exception as e:
            logger.debug(f"Error calculating target yaw: {e}")
            return None

    def _calculate_yaw_rate(self, target_data: Dict[str, Any]) -> Optional[float]:
        """
        Calculate yaw rate for body mode.

        Args:
            target_data (Dict[str, Any]): Target data

        Returns:
            Optional[float]: Yaw rate in degrees/second or None
        """
        try:
            # Use gimbal yaw as proportional yaw rate
            if 'gimbal_yaw' in target_data:
                gimbal_yaw = target_data['gimbal_yaw']

                # Simple proportional control
                yaw_rate_gain = getattr(Parameters, 'GIMBAL_YAW_RATE_GAIN', 0.5)
                yaw_rate = gimbal_yaw * yaw_rate_gain

                # Apply limits
                max_yaw_rate = getattr(Parameters, 'GIMBAL_MAX_YAW_RATE', 45.0)
                yaw_rate = np.clip(yaw_rate, -max_yaw_rate, max_yaw_rate)

                return yaw_rate

            return None

        except Exception as e:
            logger.debug(f"Error calculating yaw rate: {e}")
            return None

    def _get_aircraft_attitude(self) -> Optional[Dict[str, float]]:
        """
        Get aircraft attitude from MAVLink.

        Returns:
            Optional[Dict[str, float]]: Aircraft attitude or None
        """
        try:
            if (hasattr(self, 'px4_controller') and
                hasattr(self.px4_controller, 'app_controller') and
                hasattr(self.px4_controller.app_controller, 'mavlink_data_manager')):

                mavlink_manager = self.px4_controller.app_controller.mavlink_data_manager

                roll = mavlink_manager.get_data('roll')
                pitch = mavlink_manager.get_data('pitch')
                yaw = mavlink_manager.get_data('yaw')

                if all(x is not None and x != 'N/A' for x in [roll, pitch, yaw]):
                    return {
                        'roll': float(roll),
                        'pitch': float(pitch),
                        'yaw': float(yaw)
                    }

        except Exception as e:
            logger.debug(f"Could not get aircraft attitude: {e}")

        return None

    def _check_safety_conditions(self) -> bool:
        """
        Check safety conditions before applying commands.

        Returns:
            bool: True if safe to proceed
        """
        try:
            # Check if emergency stop is active
            if self.emergency_stop_active:
                return False

            # Check altitude safety if available
            if hasattr(self, 'px4_controller'):
                current_altitude = getattr(self.px4_controller, 'current_altitude', None)
                if current_altitude is not None and current_altitude < self.min_altitude_safety:
                    logger.warning(f"Altitude too low: {current_altitude:.1f}m < {self.min_altitude_safety:.1f}m")
                    return False

            return True

        except Exception as e:
            logger.error(f"Error checking safety conditions: {e}")
            return False

    def _apply_emergency_stop(self) -> None:
        """Apply emergency stop by zeroing all velocity commands."""
        try:
            self.emergency_stop_active = True

            # Zero all velocity commands based on control mode
            if self.control_mode == ControlMode.NED:
                self.set_command_field('vel_x', 0.0)
                self.set_command_field('vel_y', 0.0)
                self.set_command_field('vel_z', 0.0)
            elif self.control_mode == ControlMode.BODY:
                self.set_command_field('vel_body_fwd', 0.0)
                self.set_command_field('vel_body_right', 0.0)
                self.set_command_field('vel_body_down', 0.0)

            # Reset velocity state
            self.current_velocity = 0.0
            self.smoothed_velocities = np.array([0.0, 0.0, 0.0])

            logger.warning("Emergency stop applied - all velocities set to zero")

        except Exception as e:
            logger.error(f"Error applying emergency stop: {e}")

    def clear_emergency_stop(self) -> None:
        """Clear emergency stop condition."""
        self.emergency_stop_active = False
        self.target_velocity = self.base_velocity
        logger.info("Emergency stop cleared")

    def switch_control_mode(self, new_mode: str) -> bool:
        """
        Switch between NED and Body control modes.

        Args:
            new_mode (str): New control mode (NED or BODY)

        Returns:
            bool: True if switch successful
        """
        try:
            if new_mode not in [ControlMode.NED, ControlMode.BODY]:
                logger.error(f"Invalid control mode: {new_mode}")
                return False

            if new_mode == self.control_mode:
                logger.debug(f"Already in {new_mode} mode")
                return True

            logger.info(f"Switching control mode: {self.control_mode} → {new_mode}")

            # Zero current commands before switching
            self._apply_emergency_stop()

            # Update mode and reconfigure
            old_mode = self.control_mode
            self.control_mode = new_mode
            self._configure_command_fields()
            self._update_follower_metadata()

            # Clear emergency stop after reconfiguration
            time.sleep(0.1)
            self.clear_emergency_stop()

            logger.info(f"Control mode switched successfully: {old_mode} → {new_mode}")
            return True

        except Exception as e:
            logger.error(f"Error switching control mode: {e}")
            return False

    def get_follower_status(self) -> Dict[str, Any]:
        """
        Get comprehensive follower status.

        Returns:
            Dict[str, Any]: Follower status information
        """
        try:
            success_rate = (
                (self.successful_follow_calls / max(1, self.total_follow_calls)) * 100
            )

            return {
                'control_mode': self.control_mode,
                'control_type': self.control_type,
                'current_velocity': self.current_velocity,
                'target_velocity': self.target_velocity,
                'base_velocity': self.base_velocity,
                'max_velocity': self.max_velocity,
                'emergency_stop_active': self.emergency_stop_active,
                'smoothed_velocities': self.smoothed_velocities.tolist(),
                'total_follow_calls': self.total_follow_calls,
                'successful_follow_calls': self.successful_follow_calls,
                'success_rate_percent': success_rate,
                'required_fields': self.required_fields,
                'optional_fields': self.optional_fields,
                'safety_parameters': {
                    'min_altitude_safety': self.min_altitude_safety,
                    'safety_return_speed': self.safety_return_speed
                },
                'coordinate_transformer_info': self.coordinate_transformer.get_cache_info()
            }

        except Exception as e:
            logger.error(f"Error getting follower status: {e}")
            return {'error': str(e)}

    def validate_tracker_compatibility(self, tracker_data: TrackerOutput) -> bool:
        """
        Validate that tracker data is compatible with gimbal follower.

        Args:
            tracker_data (TrackerOutput): Tracker data to validate

        Returns:
            bool: True if compatible
        """
        try:
            # Check for required angular data
            if tracker_data.angular is None:
                logger.warning("No angular data in tracker output")
                return False

            # Check data type compatibility
            if tracker_data.data_type not in [TrackerDataType.ANGULAR]:
                logger.warning(f"Incompatible data type: {tracker_data.data_type}")
                return False

            # Check data freshness
            data_age = time.time() - tracker_data.timestamp
            max_age = getattr(Parameters, 'GIMBAL_MAX_DATA_AGE', 5.0)
            if data_age > max_age:
                logger.warning(f"Tracker data too old: {data_age:.1f}s > {max_age:.1f}s")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating tracker compatibility: {e}")
            return False