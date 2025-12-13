# src/classes/followers/gimbal_vector_body_follower.py

"""
GimbalVectorBodyFollower - Direct Vector Pursuit Control
=========================================================

Modern gimbal-based follower using direct geometric transformation from
gimbal angles to body-frame velocity commands. Eliminates PID tuning complexity
through physics-based vector pursuit.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
-------------
- ✅ Direct vector pursuit (no PID loops)
- ✅ Mount-aware transformations (VERTICAL, HORIZONTAL, TILTED_45)
- ✅ Linear velocity ramping (smooth acceleration)
- ✅ Optional altitude control (3D or horizontal-only)
- ✅ Robust angle filtering and deadzone
- ✅ Target loss handling with velocity decay
- ✅ Comprehensive safety systems

Control Philosophy:
-------------------
Traditional gimbal followers use PID controllers to minimize tracking error.
This follower uses a different approach:

    Gimbal Angle → Unit Vector → Scaled Velocity → Direct Command

Benefits:
- No tuning required (works with any gimbal)
- Deterministic behavior (same angle = same velocity)
- Faster response (direct path to target)
- Easier debugging (simple vector math)

Coordinate Frames:
------------------
[Gimbal Frame] --mount_transform--> [Drone Body Frame] --command--> [PX4]

Body Frame (FRD - Forward-Right-Down):
- X-axis: Forward (vel_body_fwd, positive = forward)
- Y-axis: Right (vel_body_right, positive = right)
- Z-axis: Down (vel_body_down, positive = down, negative = up)

Usage Example:
--------------
```python
from classes.followers.gimbal_vector_body_follower import GimbalVectorBodyFollower

# Initialize with PX4 controller
follower = GimbalVectorBodyFollower(px4_controller, initial_coords=(0.5, 0.5))

# Process gimbal tracker data
success = follower.follow_target(gimbal_tracker_output)

# Get telemetry
status = follower.get_status_info()
print(f"Current velocity magnitude: {status['velocity_magnitude']:.2f} m/s")
```

Configuration:
--------------
All parameters are in configs/config_default.yaml under GIMBAL_VECTOR_BODY section.
"""

import time
import math
import logging
from typing import Tuple, Optional, Dict, Any
from dataclasses import dataclass

from classes.followers.base_follower import BaseFollower
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.parameters import Parameters

logger = logging.getLogger(__name__)


@dataclass
class Vector3D:
    """Simple 3D vector representation for velocity commands."""
    x: float = 0.0  # Forward
    y: float = 0.0  # Right
    z: float = 0.0  # Down

    def magnitude(self) -> float:
        """Calculate vector magnitude."""
        return math.sqrt(self.x**2 + self.y**2 + self.z**2)

    def normalize(self) -> 'Vector3D':
        """Return normalized unit vector."""
        mag = self.magnitude()
        if mag < 1e-6:  # Avoid division by zero
            return Vector3D(0.0, 0.0, 0.0)
        return Vector3D(self.x / mag, self.y / mag, self.z / mag)

    def scale(self, scalar: float) -> 'Vector3D':
        """Scale vector by scalar."""
        return Vector3D(self.x * scalar, self.y * scalar, self.z * scalar)


class GimbalVectorBodyFollower(BaseFollower):
    """
    Direct vector pursuit follower using gimbal angles.

    Transforms gimbal angles (body-relative) to velocity commands through
    mount-aware geometric transformations, eliminating PID tuning requirements.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initialize GimbalVectorBodyFollower.

        Args:
            px4_controller: PX4 interface for drone control
            initial_target_coords: Initial target coordinates (required by factory interface)
        """
        self.setpoint_profile = "gimbal_vector_body"
        self.follower_name = "GimbalVectorBodyFollower"
        self.initial_target_coords = initial_target_coords

        # Load configuration from Parameters
        self.config = getattr(Parameters, 'GIMBAL_VECTOR_BODY', {})
        if not self.config:
            raise ValueError("GIMBAL_VECTOR_BODY configuration not found in Parameters")

        # === Mount Configuration ===
        # IMPORTANT: Set mount_type BEFORE super().__init__() because BaseFollower.__init__()
        # calls get_display_name() which needs self.mount_type to be available
        self.mount_type = self.config.get('MOUNT_TYPE', 'VERTICAL')

        # Initialize base follower (safe to call now that mount_type is set)
        super().__init__(px4_controller, self.setpoint_profile)

        logger.info(f"Gimbal mount type: {self.mount_type}")

        # === Velocity Control ===
        self.min_velocity = self.config.get('MIN_VELOCITY', 0.5)
        self.max_velocity = self.config.get('MAX_VELOCITY', 8.0)
        self.ramp_acceleration = self.config.get('RAMP_ACCELERATION', 2.0)
        self.current_velocity_magnitude = self.config.get('INITIAL_VELOCITY', 0.0)

        # === Control Enablement ===
        self.enable_altitude_control = self.config.get('ENABLE_ALTITUDE_CONTROL', False)
        self.enable_yaw_control = self.config.get('ENABLE_YAW_CONTROL', False)
        self.yaw_rate_gain = self.config.get('YAW_RATE_GAIN', 0.5)

        # === Filtering ===
        self.angle_deadzone = self.config.get('ANGLE_DEADZONE_DEG', 2.0)
        self.angle_smoothing_alpha = self.config.get('ANGLE_SMOOTHING_ALPHA', 0.7)
        self.filtered_angles = None  # (yaw, pitch, roll) in degrees

        # === Altitude Safety (Optional Enforcement) ===
        # Use unified limit access (follower-specific overrides global SafetyLimits)
        self.altitude_safety_enabled = self.config.get('ALTITUDE_SAFETY_ENABLED', False)
        self.min_altitude_safety = Parameters.get_effective_limit('MIN_ALTITUDE', 'GIMBAL_VECTOR_BODY')
        self.max_altitude_safety = Parameters.get_effective_limit('MAX_ALTITUDE', 'GIMBAL_VECTOR_BODY')
        self.altitude_check_interval = self.config.get('ALTITUDE_CHECK_INTERVAL', 1.0)
        self.rtl_on_altitude_violation = self.config.get('RTL_ON_ALTITUDE_VIOLATION', False)
        self.altitude_warning_buffer = Parameters.get_effective_limit('ALTITUDE_WARNING_BUFFER', 'GIMBAL_VECTOR_BODY')
        self.altitude_violation_count = 0
        self.last_altitude_check_time = 0.0

        # === General Safety ===
        self.emergency_stop_enabled = self.config.get('EMERGENCY_STOP_ENABLED', True)
        self.max_safety_violations = self.config.get('MAX_SAFETY_VIOLATIONS', 5)
        self.safety_violations_count = 0

        # === Target Loss ===
        self.target_loss_timeout = self.config.get('TARGET_LOSS_TIMEOUT', 3.0)
        self.enable_velocity_decay = self.config.get('ENABLE_VELOCITY_DECAY', True)
        self.velocity_decay_rate = self.config.get('VELOCITY_DECAY_RATE', 0.5)
        self.last_valid_time = time.time()
        self.last_velocity_vector: Optional[Vector3D] = None

        # === Performance ===
        self.update_rate = self.config.get('UPDATE_RATE', 20.0)
        self.command_smoothing_enabled = self.config.get('COMMAND_SMOOTHING_ENABLED', True)
        self.smoothing_factor = self.config.get('SMOOTHING_FACTOR', 0.8)
        self.last_command_vector: Optional[Vector3D] = None

        # === Advanced: Mount Offsets ===
        self.mount_roll_offset = self.config.get('MOUNT_ROLL_OFFSET_DEG', 0.0)
        self.mount_pitch_offset = self.config.get('MOUNT_PITCH_OFFSET_DEG', 0.0)
        self.mount_yaw_offset = self.config.get('MOUNT_YAW_OFFSET_DEG', 0.0)

        # === Advanced: Inversion Flags ===
        self.invert_roll = self.config.get('INVERT_GIMBAL_ROLL', False)
        self.invert_pitch = self.config.get('INVERT_GIMBAL_PITCH', False)
        self.invert_yaw = self.config.get('INVERT_GIMBAL_YAW', False)

        # === State Tracking ===
        self.following_active = False
        self.emergency_stop_active = False
        self.last_update_time = time.time()
        self.total_follow_calls = 0
        self.successful_updates = 0

        logger.info(f"GimbalVectorBodyFollower initialized: {self.mount_type} mount, "
                   f"altitude_control={self.enable_altitude_control}, "
                   f"velocity_range=[{self.min_velocity:.1f}, {self.max_velocity:.1f}] m/s")

    # ==================== Core Control Logic ====================

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculate velocity commands from gimbal angles using direct vector transformation.

        This is the heart of the follower - transforms gimbal angles to velocity commands
        through mount-aware geometric transformations.

        Args:
            tracker_data: TrackerOutput with GIMBAL_ANGLES data

        Raises:
            ValueError: If tracker data is invalid or incompatible
        """
        try:
            current_time = time.time()
            dt = current_time - self.last_update_time
            self.last_update_time = current_time

            # Validate tracker data type
            if tracker_data.data_type != TrackerDataType.GIMBAL_ANGLES:
                raise ValueError(f"Expected GIMBAL_ANGLES, got {tracker_data.data_type}")

            # Extract gimbal angles
            if tracker_data.angular is None or len(tracker_data.angular) < 3:
                raise ValueError("GIMBAL_ANGLES tracker data missing angular field")

            yaw_deg, pitch_deg, roll_deg = tracker_data.angular[0], tracker_data.angular[1], tracker_data.angular[2]

            # Apply filtering
            yaw_deg, pitch_deg, roll_deg = self._filter_angles(yaw_deg, pitch_deg, roll_deg)

            # Apply mount offsets and inversions
            yaw_deg = self._apply_angle_corrections(yaw_deg, self.mount_yaw_offset, self.invert_yaw)
            pitch_deg = self._apply_angle_corrections(pitch_deg, self.mount_pitch_offset, self.invert_pitch)
            roll_deg = self._apply_angle_corrections(roll_deg, self.mount_roll_offset, self.invert_roll)

            # Transform gimbal angles to body-frame unit vector
            unit_vector = self._gimbal_to_body_vector(yaw_deg, pitch_deg, roll_deg)

            # Update velocity magnitude (linear ramp)
            self._update_velocity_magnitude(dt)

            # Scale unit vector by current velocity magnitude
            velocity_vector = unit_vector.scale(self.current_velocity_magnitude)

            # Log velocity calculation (DEBUG level - runs at 20Hz)
            logger.debug(f"Vector pursuit: angles=[{yaw_deg:.1f}, {pitch_deg:.1f}, {roll_deg:.1f}]°, "
                        f"vel=[{velocity_vector.x:.3f}, {velocity_vector.y:.3f}, {velocity_vector.z:.3f}] m/s, "
                        f"mag={self.current_velocity_magnitude:.3f}/{self.max_velocity:.1f} m/s")

            # Apply altitude control flag
            if not self.enable_altitude_control:
                velocity_vector.z = 0.0  # Zero vertical velocity (horizontal-only)

            # Apply minimum velocity threshold (prevent stalling)
            # If total velocity magnitude is below min_velocity, scale up to min_velocity
            if self.min_velocity > 0.0:
                actual_magnitude = velocity_vector.magnitude()
                if 0.0 < actual_magnitude < self.min_velocity:
                    scale_factor = self.min_velocity / actual_magnitude
                    velocity_vector.x *= scale_factor
                    velocity_vector.y *= scale_factor
                    velocity_vector.z *= scale_factor

            # Apply command smoothing
            if self.command_smoothing_enabled and self.last_command_vector is not None:
                velocity_vector = self._smooth_velocity(velocity_vector, self.last_command_vector)

            # Store for next iteration
            self.last_command_vector = velocity_vector
            self.last_velocity_vector = velocity_vector

            # Set command fields
            self.set_command_field("vel_body_fwd", velocity_vector.x)
            self.set_command_field("vel_body_right", velocity_vector.y)
            self.set_command_field("vel_body_down", velocity_vector.z)

            # Optional yaw control
            if self.enable_yaw_control:
                yaw_rate = self._calculate_yaw_rate(yaw_deg)
                self.set_command_field("yawspeed_deg_s", yaw_rate)
            else:
                self.set_command_field("yawspeed_deg_s", 0.0)

        except Exception as e:
            logger.error(f"Error in calculate_control_commands: {e}")
            raise RuntimeError(f"Failed to calculate gimbal vector commands: {e}")

    def follow_target(self, tracker_output: TrackerOutput) -> bool:
        """
        Main target following method with safety checks and target loss handling.

        Args:
            tracker_output: Unified tracker output from gimbal tracker

        Returns:
            bool: True if following was successful, False otherwise
        """
        self.total_follow_calls += 1
        current_time = time.time()

        try:
            # Safety checks
            safety_status = self._perform_safety_checks(current_time)
            if not safety_status['safe_to_proceed']:
                logger.warning(f"Safety check failed: {safety_status['reason']}")
                return False

            # Check if tracking is active
            if tracker_output.tracking_active:
                # Normal tracking
                self.calculate_control_commands(tracker_output)
                self.following_active = True
                self.last_valid_time = current_time
                self.successful_updates += 1
                return True
            else:
                # Target lost - handle gracefully
                return self._handle_target_loss(current_time)

        except Exception as e:
            logger.error(f"Error in follow_target: {e}")
            self.log_follower_event("follow_target_error", error=str(e))
            return False

    # ==================== Mount Transformations ====================

    def _gimbal_to_body_vector(self, yaw_deg: float, pitch_deg: float, roll_deg: float) -> Vector3D:
        """
        Transform gimbal angles to body-frame unit vector using mount-specific transformations.

        This is the core transformation that converts gimbal angles to a 3D velocity direction.

        Args:
            yaw_deg: Gimbal yaw in degrees
            pitch_deg: Gimbal pitch in degrees
            roll_deg: Gimbal roll in degrees

        Returns:
            Vector3D: Unit vector pointing toward target in body frame
        """
        # Convert to radians
        yaw = math.radians(yaw_deg)
        pitch = math.radians(pitch_deg)
        roll = math.radians(roll_deg)

        # Mount-specific transformations
        if self.mount_type == 'VERTICAL':
            # VERTICAL mount: camera points down when level
            # Neutral: pitch=90°, roll=0°, yaw=0°
            # Pitch deviation from 90° → vertical (down) motion
            # Roll → lateral (yaw) motion
            # Yaw → forward motion

            # Adjust pitch for vertical mount (neutral = 90°)
            pitch_adj = pitch - math.radians(90.0)

            # Forward: primarily from yaw rotation
            forward = math.cos(yaw) * math.cos(pitch_adj)

            # Right: from roll angle (gimbal roll controls lateral direction)
            right = -math.sin(roll)  # Negative because roll convention

            # Down: from pitch deviation (pitch > 90° = look down more = descend)
            down = math.sin(pitch_adj)

        elif self.mount_type == 'HORIZONTAL':
            # HORIZONTAL mount: camera points forward when level
            # Neutral: pitch=0°, roll=0°, yaw=0°
            # Standard FRD transformations

            # Forward: forward direction component
            forward = math.cos(pitch) * math.cos(yaw)

            # Right: lateral component from yaw
            right = math.sin(yaw) * math.cos(pitch)

            # Down: vertical component from pitch
            down = math.sin(pitch)

        elif self.mount_type == 'TILTED_45':
            # TILTED_45 mount: camera angled 45° down (FPV racing style)
            # Neutral: pitch=45° down, roll=0°, yaw=0°

            # Adjust pitch for 45° tilt
            pitch_adj = pitch - math.radians(45.0)

            # Similar to horizontal but with pitch offset
            forward = math.cos(pitch_adj) * math.cos(yaw)
            right = math.sin(yaw) * math.cos(pitch_adj)
            down = math.sin(pitch_adj)

        else:
            logger.error(f"Unknown mount type: {self.mount_type}, defaulting to VERTICAL")
            return self._gimbal_to_body_vector_vertical_fallback(yaw_deg, pitch_deg, roll_deg)

        # Create and normalize vector
        vector = Vector3D(forward, right, down)
        return vector.normalize()

    def _gimbal_to_body_vector_vertical_fallback(self, yaw_deg: float, pitch_deg: float, roll_deg: float) -> Vector3D:
        """Fallback transformation for VERTICAL mount."""
        yaw = math.radians(yaw_deg)
        pitch = math.radians(pitch_deg)
        roll = math.radians(roll_deg)

        pitch_adj = pitch - math.radians(90.0)
        forward = math.cos(yaw) * math.cos(pitch_adj)
        right = -math.sin(roll)
        down = math.sin(pitch_adj)

        vector = Vector3D(forward, right, down)
        return vector.normalize()

    # ==================== Velocity Management ====================

    def _update_velocity_magnitude(self, dt: float) -> None:
        """
        Update current velocity magnitude using linear ramping.

        Ramps from current velocity to max_velocity with acceleration limits.
        Consistent with BODY_VELOCITY_CHASE pattern.

        Args:
            dt: Time delta since last update (seconds)
        """
        # Target velocity is always max (ramp up from wherever we are)
        target_velocity = self.max_velocity

        # Calculate velocity error (how far from target)
        velocity_error = target_velocity - self.current_velocity_magnitude

        # If close enough, snap to target
        if abs(velocity_error) < 0.01:
            self.current_velocity_magnitude = target_velocity
            return

        # Apply ramping with acceleration limit
        max_velocity_change = self.ramp_acceleration * dt

        # Clip velocity change to acceleration limits
        if velocity_error > 0:  # Need to accelerate
            velocity_change = min(velocity_error, max_velocity_change)
        else:  # Need to decelerate
            velocity_change = max(velocity_error, -max_velocity_change)

        # Update velocity
        self.current_velocity_magnitude += velocity_change

        # Clamp to absolute limits [0, max_velocity]
        # Note: min_velocity is only used as a lower threshold check, not clamp
        self.current_velocity_magnitude = max(0.0, min(self.max_velocity, self.current_velocity_magnitude))

    # ==================== Filtering & Smoothing ====================

    def _filter_angles(self, yaw: float, pitch: float, roll: float) -> Tuple[float, float, float]:
        """
        Apply EMA filtering and deadzone to gimbal angles.

        Args:
            yaw, pitch, roll: Raw gimbal angles in degrees

        Returns:
            Tuple of filtered angles
        """
        # Initialize filtered angles on first call
        if self.filtered_angles is None:
            self.filtered_angles = (yaw, pitch, roll)
            return yaw, pitch, roll

        # Apply deadzone (ignore small changes)
        def apply_deadzone(current, prev, deadzone):
            if abs(current - prev) < deadzone:
                return prev
            return current

        yaw = apply_deadzone(yaw, self.filtered_angles[0], self.angle_deadzone)
        pitch = apply_deadzone(pitch, self.filtered_angles[1], self.angle_deadzone)
        roll = apply_deadzone(roll, self.filtered_angles[2], self.angle_deadzone)

        # Apply EMA filter
        alpha = self.angle_smoothing_alpha
        yaw_filt = alpha * yaw + (1 - alpha) * self.filtered_angles[0]
        pitch_filt = alpha * pitch + (1 - alpha) * self.filtered_angles[1]
        roll_filt = alpha * roll + (1 - alpha) * self.filtered_angles[2]

        # Store filtered values
        self.filtered_angles = (yaw_filt, pitch_filt, roll_filt)

        return yaw_filt, pitch_filt, roll_filt

    def _smooth_velocity(self, new_vector: Vector3D, prev_vector: Vector3D) -> Vector3D:
        """
        Apply exponential smoothing to velocity commands.

        Args:
            new_vector: New velocity command
            prev_vector: Previous velocity command

        Returns:
            Smoothed velocity vector
        """
        alpha = self.smoothing_factor
        return Vector3D(
            alpha * new_vector.x + (1 - alpha) * prev_vector.x,
            alpha * new_vector.y + (1 - alpha) * prev_vector.y,
            alpha * new_vector.z + (1 - alpha) * prev_vector.z
        )

    def _apply_angle_corrections(self, angle: float, offset: float, invert: bool) -> float:
        """
        Apply offset and inversion to a gimbal angle.

        Args:
            angle: Raw angle in degrees
            offset: Offset to add
            invert: Whether to invert the angle

        Returns:
            Corrected angle
        """
        corrected = angle + offset
        if invert:
            corrected = -corrected
        return corrected

    # ==================== Optional Yaw Control ====================

    def _calculate_yaw_rate(self, yaw_deg: float) -> float:
        """
        Calculate yaw rate to point drone toward target.

        Args:
            yaw_deg: Gimbal yaw angle in degrees

        Returns:
            Yaw rate in degrees/second
        """
        # Proportional control: yaw rate proportional to yaw error
        yaw_rate = yaw_deg * self.yaw_rate_gain

        # Clamp to SafetyLimits (deg/s)
        max_yaw_rate = Parameters.get_effective_limit('MAX_YAW_RATE', 'GIMBAL_VECTOR_BODY')
        yaw_rate = max(-max_yaw_rate, min(max_yaw_rate, yaw_rate))

        return yaw_rate

    # ==================== Target Loss Handling ====================

    def _handle_target_loss(self, current_time: float) -> bool:
        """
        Handle target loss with velocity decay.

        Args:
            current_time: Current timestamp

        Returns:
            bool: True if still coasting, False if stopped
        """
        time_since_loss = current_time - self.last_valid_time

        if time_since_loss < self.target_loss_timeout:
            # Still within timeout - coast on last velocity
            if self.enable_velocity_decay and self.last_velocity_vector is not None:
                # Decay velocity - compute dt and update last_update_time for linear decay
                dt = current_time - self.last_update_time
                self.last_update_time = current_time
                decay_amount = self.velocity_decay_rate * dt
                self.current_velocity_magnitude = max(0.0, self.current_velocity_magnitude - decay_amount)

                # Apply decayed velocity
                decayed_vector = self.last_velocity_vector.normalize().scale(self.current_velocity_magnitude)
                self.set_command_field("vel_body_fwd", decayed_vector.x)
                self.set_command_field("vel_body_right", decayed_vector.y)
                self.set_command_field("vel_body_down", decayed_vector.z)

                logger.debug(f"Target lost, coasting with decay: mag={self.current_velocity_magnitude:.2f} m/s")
                return True
            else:
                # Coast without decay
                return True
        else:
            # Timeout exceeded - stop
            self.set_command_field("vel_body_fwd", 0.0)
            self.set_command_field("vel_body_right", 0.0)
            self.set_command_field("vel_body_down", 0.0)
            self.current_velocity_magnitude = 0.0
            logger.info("Target loss timeout - stopped")
            return False

    # ==================== Safety Systems ====================

    def _perform_safety_checks(self, current_time: float) -> Dict[str, Any]:
        """
        Perform comprehensive safety checks.

        Returns:
            Dict with 'safe_to_proceed' boolean and 'reason' for any failures
        """
        # Circuit breaker override
        try:
            from classes.circuit_breaker import FollowerCircuitBreaker
            disable_safety = getattr(Parameters, 'CIRCUIT_BREAKER_DISABLE_SAFETY', False)
            if disable_safety and FollowerCircuitBreaker.is_active():
                logger.debug("Circuit breaker mode: Skipping safety checks")
                return {'safe_to_proceed': True, 'reason': 'circuit_breaker_testing_mode'}
        except ImportError:
            pass

        # Emergency stop check
        if self.emergency_stop_active:
            return {'safe_to_proceed': False, 'reason': 'emergency_stop_active', 'severity': 'critical'}

        # Altitude safety check (if available)
        altitude_status = self._check_altitude_safety()
        if not altitude_status['safe']:
            return {
                'safe_to_proceed': False,
                'reason': f"altitude_violation_{altitude_status['violation_type']}",
                'severity': 'high',
                'current_altitude': altitude_status.get('current_altitude')
            }

        # Safety violation accumulation
        if self.safety_violations_count >= self.max_safety_violations:
            return {
                'safe_to_proceed': False,
                'reason': 'excessive_safety_violations',
                'severity': 'medium',
                'violation_count': self.safety_violations_count
            }

        # All checks passed
        return {'safe_to_proceed': True, 'reason': 'all_checks_passed'}

    def _check_altitude_safety(self) -> Dict[str, Any]:
        """
        Check if drone altitude is within safe operating range (if enabled).

        Consistent with BODY_VELOCITY_CHASE pattern - altitude safety is optional.

        Returns:
            Dict with 'safe' status and additional info
        """
        # Skip check if altitude safety is disabled
        if not self.altitude_safety_enabled:
            return {'safe': True, 'reason': 'altitude_safety_disabled'}

        try:
            current_time = time.time()

            # Only check at specified intervals to avoid excessive processing
            if (current_time - self.last_altitude_check_time) < self.altitude_check_interval:
                return {'safe': True, 'reason': 'check_interval_not_reached'}

            self.last_altitude_check_time = current_time
            current_altitude = getattr(self.px4_controller, 'current_altitude', 0.0)

            # Check for violations
            if current_altitude < self.min_altitude_safety:
                self.altitude_violation_count += 1
                logger.warning(f"Altitude safety violation: {current_altitude:.1f}m < {self.min_altitude_safety:.1f}m "
                             f"(violation #{self.altitude_violation_count})")
                return {
                    'safe': False,
                    'violation_type': 'too_low',
                    'current_altitude': current_altitude,
                    'threshold': self.min_altitude_safety,
                    'violation_count': self.altitude_violation_count
                }
            elif current_altitude > self.max_altitude_safety:
                self.altitude_violation_count += 1
                logger.warning(f"Altitude safety violation: {current_altitude:.1f}m > {self.max_altitude_safety:.1f}m "
                             f"(violation #{self.altitude_violation_count})")
                return {
                    'safe': False,
                    'violation_type': 'too_high',
                    'current_altitude': current_altitude,
                    'threshold': self.max_altitude_safety,
                    'violation_count': self.altitude_violation_count
                }
            else:
                # Within safe bounds - reset violation counter
                self.altitude_violation_count = 0
                return {'safe': True, 'current_altitude': current_altitude}

        except Exception as e:
            logger.error(f"Error checking altitude safety: {e}")
            return {'safe': False, 'violation_type': 'status_unavailable', 'error': str(e)}

    def emergency_stop(self) -> None:
        """Trigger emergency stop - immediately zero all velocities."""
        logger.warning("⚠️ Emergency stop triggered")
        self.emergency_stop_active = True
        self.following_active = False

        try:
            self.set_command_field("vel_body_fwd", 0.0)
            self.set_command_field("vel_body_right", 0.0)
            self.set_command_field("vel_body_down", 0.0)
            self.set_command_field("yawspeed_deg_s", 0.0)
            self.current_velocity_magnitude = 0.0
        except Exception as e:
            logger.error(f"Failed to set emergency zero velocities: {e}")

        self.log_follower_event("emergency_stop_triggered")

    def reset_emergency_stop(self) -> None:
        """Reset emergency stop state."""
        logger.info("✅ Emergency stop reset")
        self.emergency_stop_active = False
        self.safety_violations_count = 0
        self.log_follower_event("emergency_stop_reset")

    # ==================== Status & Telemetry ====================

    def get_display_name(self) -> str:
        """Get display name for UI."""
        return f"Gimbal Vector ({self.mount_type} mount)"

    def get_status_info(self) -> Dict[str, Any]:
        """Get comprehensive status information."""
        return {
            'follower_type': 'GimbalVectorBodyFollower',
            'display_name': self.get_display_name(),
            'following_active': self.following_active,
            'emergency_stop_active': self.emergency_stop_active,
            'configuration': {
                'mount_type': self.mount_type,
                'altitude_control': self.enable_altitude_control,
                'yaw_control': self.enable_yaw_control,
                'velocity_range': [self.min_velocity, self.max_velocity]
            },
            'current_state': {
                'velocity_magnitude': self.current_velocity_magnitude,
                'last_velocity_vector': {
                    'x': self.last_velocity_vector.x if self.last_velocity_vector else 0.0,
                    'y': self.last_velocity_vector.y if self.last_velocity_vector else 0.0,
                    'z': self.last_velocity_vector.z if self.last_velocity_vector else 0.0,
                } if self.last_velocity_vector else None
            },
            'statistics': {
                'total_follow_calls': self.total_follow_calls,
                'successful_updates': self.successful_updates,
                'success_rate': (self.successful_updates / max(1, self.total_follow_calls)) * 100
            },
            'circuit_breaker_active': self.is_circuit_breaker_active()
        }

    def validate_target_coordinates(self, tracker_output: TrackerOutput) -> bool:
        """
        Validate tracker output for gimbal vector following.

        Args:
            tracker_output: Tracker output to validate

        Returns:
            bool: True if valid for gimbal vector following
        """
        try:
            if not isinstance(tracker_output, TrackerOutput):
                return False

            if tracker_output.data_type != TrackerDataType.GIMBAL_ANGLES:
                return False

            if tracker_output.tracking_active:
                if not tracker_output.angular or len(tracker_output.angular) < 3:
                    return False

            return True

        except Exception as e:
            logger.error(f"Error validating target coordinates: {e}")
            return False

    def extract_target_coordinates(self, tracker_output: TrackerOutput) -> Optional[Tuple[float, float]]:
        """
        Extract target coordinates for compatibility with base follower interface.

        For gimbal vector follower, we return normalized angular representation.

        Args:
            tracker_output: Tracker output

        Returns:
            Tuple of (yaw_normalized, pitch_normalized) or None
        """
        try:
            if not tracker_output.tracking_active or not tracker_output.angular:
                return None

            yaw = tracker_output.angular[0] if len(tracker_output.angular) > 0 else 0.0
            pitch = tracker_output.angular[1] if len(tracker_output.angular) > 1 else 0.0

            # Normalize to [-1, 1] for UI/validation
            normalized_yaw = max(-1.0, min(1.0, yaw / 180.0))
            normalized_pitch = max(-1.0, min(1.0, pitch / 90.0))

            return (normalized_yaw, normalized_pitch)

        except Exception as e:
            logger.error(f"Error extracting target coordinates: {e}")
            return None

    def __str__(self) -> str:
        """String representation for debugging."""
        return f"GimbalVectorBodyFollower(mount={self.mount_type}, active={self.following_active}, vel_mag={self.current_velocity_magnitude:.2f} m/s)"
