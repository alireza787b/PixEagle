# src/classes/followers/gm_velocity_vector_follower.py

"""
GMVelocityVectorFollower - Direct Vector Pursuit Control
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
- Direct vector pursuit (no PID loops)
- Mount-aware transformations (VERTICAL, HORIZONTAL)
- Linear velocity ramping (smooth acceleration)
- Optional altitude control (3D or horizontal-only)
- Robust angle filtering and deadzone
- Shared target-continuity authority outside this follower
- Comprehensive safety systems

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
from classes.followers.gm_velocity_vector_follower import GMVelocityVectorFollower

# Initialize with PX4 controller
follower = GMVelocityVectorFollower(px4_controller, initial_coords=(0.5, 0.5))

# Process gimbal tracker data
success = follower.follow_target(gimbal_tracker_output)

# Get telemetry
status = follower.get_status_info()
print(f"Current velocity magnitude: {status['velocity_magnitude']:.2f} m/s")
```

Configuration:
--------------
All parameters are in configs/config_default.yaml under GM_VELOCITY_VECTOR section.
"""

import time
import math
import logging
from typing import Tuple, Optional, Dict, Any
from dataclasses import dataclass

from classes.followers.base_follower import BaseFollower
from classes.gimbal_geometry import (
    InvalidGimbalGeometry,
    body_line_of_sight,
    require_canonical_geometry_settings,
    require_finite_body_angles,
    resolve_angle_geometry,
    resolve_mount_type,
)
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.parameters import Parameters
from classes.follower_config_manager import get_follower_config_manager

from classes.followers.yaw_rate_smoother import YawRateSmoother  # WP9: canonical import

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


class GMVelocityVectorFollower(BaseFollower):
    """
    Direct vector pursuit follower using gimbal angles.

    Transforms gimbal angles (body-relative) to velocity commands through
    mount-aware geometric transformations, eliminating PID tuning requirements.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initialize GMVelocityVectorFollower.

        Args:
            px4_controller: PX4 interface for drone control
            initial_target_coords: Initial target coordinates (required by factory interface)
        """
        self.setpoint_profile = "gm_velocity_vector"
        self.follower_name = "GMVelocityVectorFollower"
        self.initial_target_coords = initial_target_coords

        # Load configuration from Parameters
        self.config = getattr(Parameters, 'GM_VELOCITY_VECTOR', {})
        if not self.config:
            raise ValueError("GM_VELOCITY_VECTOR configuration not found in Parameters")
        require_canonical_geometry_settings('GM_VELOCITY_VECTOR', self.config)

        # === Mount Configuration ===
        # IMPORTANT: Set mount_type BEFORE super().__init__() because BaseFollower.__init__()
        # calls get_display_name() which needs self.mount_type to be available
        self.mount_type = resolve_mount_type(
            getattr(Parameters, 'GimbalTracker', {}),
            getattr(Parameters, 'GM_VELOCITY_CHASE', {}),
            self.config,
            allowed=('HORIZONTAL', 'VERTICAL'),
        )
        self.angle_geometry = resolve_angle_geometry(
            getattr(Parameters, 'GimbalTracker', {}), self.mount_type
        )

        # Initialize base follower (safe to call now that mount_type is set)
        super().__init__(px4_controller, self.setpoint_profile)

        logger.info(f"Gimbal mount type: {self.mount_type}")

        # === Velocity Control ===
        # v5.0.0: Use SafetyManager for velocity limits (single source of truth)
        self.min_velocity = 0.0  # Minimum can be 0 (hover)
        self.max_velocity = self.velocity_limits.forward
        self.ramp_acceleration = self.config.get('RAMP_ACCELERATION', 0.25)
        self.current_velocity_magnitude = self.config.get('INITIAL_VELOCITY', 0.0)

        # === Shared params from FollowerConfigManager (General → FollowerOverrides → Fallback) ===
        fcm = get_follower_config_manager()
        _fn = 'GM_VELOCITY_VECTOR'

        # === Control Enablement ===
        self.enable_altitude_control = fcm.get_param('ENABLE_ALTITUDE_CONTROL', _fn)
        self.yaw_rate_gain = self.config.get('YAW_RATE_GAIN', 0.5)

        # === Lateral Guidance Mode (from FollowerConfigManager) ===
        self.lateral_guidance_mode = fcm.get_param('LATERAL_GUIDANCE_MODE', _fn)
        self.active_lateral_mode = self.lateral_guidance_mode
        logger.info(f"Lateral guidance mode: {self.lateral_guidance_mode}")

        # === Auto Mode Switching (from FollowerConfigManager) ===
        self.enable_auto_mode_switching = fcm.get_param('ENABLE_AUTO_MODE_SWITCHING', _fn)
        self.guidance_mode_switch_velocity = fcm.get_param('GUIDANCE_MODE_SWITCH_VELOCITY', _fn)

        # === Mode Switch Hysteresis (from FollowerConfigManager) ===
        self.mode_switch_hysteresis = fcm.get_param('MODE_SWITCH_HYSTERESIS', _fn)
        self.min_mode_switch_interval = fcm.get_param('MIN_MODE_SWITCH_INTERVAL', _fn)
        self.last_mode_switch_time = 0.0

        # === Yaw Rate Smoother (from FollowerConfigManager) ===
        yaw_smoothing_config = fcm.get_yaw_smoothing_config(_fn)
        self.yaw_smoother = YawRateSmoother.from_config(yaw_smoothing_config)
        logger.debug(f"YawRateSmoother: enabled={self.yaw_smoother.enabled}, "
                    f"deadzone={self.yaw_smoother.deadzone_deg_s} deg/s")

        # === Filtering ===
        self.angle_deadzone = self.config.get('ANGLE_DEADZONE_DEG', 2.0)
        self.angle_smoothing_alpha = self.config.get('ANGLE_SMOOTHING_ALPHA', 0.7)
        self.filtered_body_ray = None

        # === Altitude Safety (limits from SafetyManager; per-follower flag via is_altitude_safety_enabled()) ===
        self.min_altitude_safety = self.altitude_limits.min_altitude
        self.max_altitude_safety = self.altitude_limits.max_altitude
        self.altitude_check_interval = fcm.get_param('ALTITUDE_CHECK_INTERVAL', _fn)
        self.altitude_warning_buffer = self.altitude_limits.warning_buffer
        self.altitude_violation_count = 0
        self.last_altitude_check_time = 0.0

        # === General Safety (from SafetyManager — single source of truth) ===
        self.safety_violations_count = 0

        self.last_velocity_vector: Optional[Vector3D] = None

        # === Performance (from FollowerConfigManager) ===
        self.update_rate = fcm.get_param('CONTROL_UPDATE_RATE', _fn)
        self.command_smoothing_enabled = fcm.get_param('COMMAND_SMOOTHING_ENABLED', _fn)
        self.smoothing_factor = fcm.get_param('SMOOTHING_FACTOR', _fn)
        self.last_command_vector: Optional[Vector3D] = None

        # === State Tracking ===
        self.following_active = False
        self.emergency_stop_active = False
        self.last_update_time = time.time()
        self.reset_control_session()
        self.yaw_smoother.reference_rate_hz = self.update_rate
        self.total_follow_calls = 0
        self.successful_updates = 0
        self.failed_updates = 0

        logger.info(f"GMVelocityVectorFollower initialized: {self.mount_type} mount, "
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
        self._geometry_invalid = None
        self._safety_rejection = None
        try:
            dt = self.next_control_delta()

            # Validate tracker data type
            if tracker_data.data_type != TrackerDataType.GIMBAL_ANGLES:
                raise ValueError(f"Expected GIMBAL_ANGLES, got {tracker_data.data_type}")

            # Extract gimbal angles
            yaw_deg, pitch_deg, roll_deg = require_finite_body_angles(tracker_data.angular)

            # Reject inadmissible raw rays before filtering can hide them.
            unit_vector = self._filter_body_ray(
                self._gimbal_to_body_vector(yaw_deg, pitch_deg, roll_deg), dt,
            )

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
                # Zero vertical velocity and re-normalize horizontal to maintain speed
                horiz_mag = math.sqrt(velocity_vector.x**2 + velocity_vector.y**2)
                if horiz_mag > 1e-6:
                    scale = self.current_velocity_magnitude / horiz_mag
                    velocity_vector.x *= scale
                    velocity_vector.y *= scale
                velocity_vector.z = 0.0

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
                velocity_vector = self._smooth_velocity(velocity_vector, self.last_command_vector, dt)

            if self.enable_altitude_control:
                velocity_vector.z = self.guard_gimbal_vertical_velocity(velocity_vector.z)

            # Store for next iteration
            self.last_command_vector = velocity_vector
            self.last_velocity_vector = velocity_vector

            command_fields = {
                "vel_body_fwd": velocity_vector.x,
                "vel_body_down": velocity_vector.z,
            }

            # === AUTO MODE SWITCHING (optional) ===
            if self.enable_auto_mode_switching:
                new_mode = self._get_active_lateral_mode()
                if new_mode != self.active_lateral_mode:
                    self._switch_lateral_mode(new_mode)

            # === LATERAL GUIDANCE MODE ===
            if self.active_lateral_mode == 'sideslip':
                # Sideslip Mode: Direct lateral velocity from gimbal, no yaw rotation
                # Best for: Precision hovering, close proximity, confined spaces
                command_fields["vel_body_right"] = velocity_vector.y
                command_fields["yawspeed_deg_s"] = 0.0

            elif self.active_lateral_mode == 'coordinated_turn':
                # Coordinated Turn Mode: Yaw to track target, no lateral velocity
                # Best for: Forward flight efficiency, natural behavior, wind resistance
                command_fields["vel_body_right"] = 0.0

                # Turn toward the shared aircraft-body target bearing, not
                # the provider's raw yaw channel (optical roll when vertical).
                bearing_deg = math.degrees(math.atan2(unit_vector.y, unit_vector.x))
                raw_yaw_rate = self._calculate_yaw_rate(bearing_deg)

                # Apply the shared yaw smoothing pipeline:
                # 1. Deadzone - prevents jitter at low rates
                # 2. Speed-adaptive scaling - works with slow AND fast speeds
                # 3. Rate limiting - prevents jerky movements
                # 4. EMA smoothing - noise reduction
                forward_speed = abs(velocity_vector.x)
                smoothed_yaw_rate = self.yaw_smoother.apply(raw_yaw_rate, dt, forward_speed)

                command_fields["yawspeed_deg_s"] = smoothed_yaw_rate

                logger.debug(f"Coordinated turn: raw_yaw={raw_yaw_rate:.2f} -> smoothed={smoothed_yaw_rate:.2f} deg/s")

            else:
                # Fallback: sideslip behavior (safe default)
                logger.warning(f"Unknown lateral mode '{self.active_lateral_mode}', using sideslip")
                command_fields["vel_body_right"] = velocity_vector.y
                command_fields["yawspeed_deg_s"] = 0.0

            if not self.set_command_fields(
                command_fields,
                reason='gm_velocity_vector_normal_tracking',
            ):
                raise RuntimeError("Failed to apply gimbal vector command intent")

        except Exception as e:
            if isinstance(e, InvalidGimbalGeometry):
                self._geometry_invalid = str(e)
            elif isinstance(e, ValueError):
                self._safety_rejection = str(e)
            logger.error(f"Error in calculate_control_commands: {e}")
            raise RuntimeError(f"Failed to calculate gimbal vector commands: {e}")

    def follow_target(self, tracker_output: TrackerOutput) -> bool:
        """
        Main target following method with safety checks and nominal command math.

        Args:
            tracker_output: Unified tracker output from gimbal tracker

        Returns:
            bool: True if following was successful, False otherwise
        """
        self._geometry_invalid = None
        self._safety_rejection = None
        self.total_follow_calls += 1
        current_time = time.time()

        try:
            # Safety checks
            safety_status = self._perform_safety_checks(current_time)
            if not safety_status['safe_to_proceed']:
                self._safety_rejection = str(safety_status['reason'])
                logger.warning(f"Safety check failed: {safety_status['reason']}")
                return False

            if not self.validate_tracker_compatibility(tracker_output):
                return False

            self.calculate_control_commands(tracker_output)
            self.following_active = True
            self.successful_updates += 1
            return True

        except Exception as e:
            logger.error(f"Error in follow_target: {e}")
            self.emergency_stop()
            self.log_follower_event("follow_target_error", error=str(e))
            return False

    # ==================== Mount Transformations ====================

    def _gimbal_to_body_vector(self, yaw_deg: float, pitch_deg: float, roll_deg: float) -> Vector3D:
        """Use the shared camera-to-aircraft ray for body velocity guidance."""
        forward, right, down = body_line_of_sight(
            (yaw_deg, pitch_deg, roll_deg), self.mount_type,
            getattr(self, 'angle_geometry', None),
        )
        if forward <= 0.0:
            raise InvalidGimbalGeometry("Target ray is outside the forward hemisphere")
        return Vector3D(forward, right, down).normalize()

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

    @property
    def authorized_command_acceleration(self) -> float:
        return self.ramp_acceleration

    def reset_control_session(self) -> None:
        super().reset_control_session()
        self.current_velocity_magnitude = self.config.get('INITIAL_VELOCITY', 0.0)
        self.filtered_body_ray = None
        self.last_command_vector = None
        self.last_velocity_vector = None
        self.yaw_smoother.reset()

    def _filter_body_ray(self, current: Vector3D, dt: float) -> Vector3D:
        previous = getattr(self, 'filtered_body_ray', None)
        if previous is None:
            self.filtered_body_ray = current
            return current
        dot = max(-1.0, min(1.0, current.x * previous.x + current.y * previous.y + current.z * previous.z))
        if math.degrees(math.acos(dot)) < self.angle_deadzone:
            return previous
        alpha = self.time_normalized_alpha(
            self.angle_smoothing_alpha, dt, getattr(self, 'update_rate', 20.0),
        )
        angle = math.acos(dot)
        if angle < 1e-9:
            return previous
        denominator = math.sin(angle)
        if abs(denominator) < 1e-12:
            raise InvalidGimbalGeometry("Camera rays cannot define a unique filter path")
        old_weight = math.sin((1.0 - alpha) * angle) / denominator
        new_weight = math.sin(alpha * angle) / denominator
        filtered = Vector3D(
            new_weight * current.x + old_weight * previous.x,
            new_weight * current.y + old_weight * previous.y,
            new_weight * current.z + old_weight * previous.z,
        ).normalize()
        if filtered.x <= 0.0 or filtered.magnitude() <= 0.0:
            raise InvalidGimbalGeometry("Filtered target ray is outside the forward hemisphere")
        self.filtered_body_ray = filtered
        return filtered

    def _smooth_velocity(self, new_vector: Vector3D, prev_vector: Vector3D, dt: float | None = None) -> Vector3D:
        """
        Apply exponential smoothing to velocity commands.

        Args:
            new_vector: New velocity command
            prev_vector: Previous velocity command

        Returns:
            Smoothed velocity vector
        """
        alpha = self.time_normalized_alpha(
            self.smoothing_factor, 1.0 / self.update_rate if dt is None else dt, self.update_rate,
        )
        return Vector3D(
            alpha * new_vector.x + (1 - alpha) * prev_vector.x,
            alpha * new_vector.y + (1 - alpha) * prev_vector.y,
            alpha * new_vector.z + (1 - alpha) * prev_vector.z
        )

    # ==================== Optional Yaw Control ====================

    def _calculate_yaw_rate(self, bearing_deg: float) -> float:
        """
        Calculate yaw rate to point drone toward target.

        Args:
            bearing_deg: Aircraft-body target bearing in degrees

        Returns:
            Yaw rate in degrees/second
        """
        # Proportional control: yaw rate proportional to yaw error
        yaw_rate = bearing_deg * self.yaw_rate_gain

        # Clamp to SafetyLimits (deg/s) - use base class cached limits
        max_yaw_rate = self.rate_limits.yaw * 57.2958  # Convert rad/s to deg/s
        yaw_rate = max(-max_yaw_rate, min(max_yaw_rate, yaw_rate))

        return yaw_rate

    # ==================== Lateral Guidance Mode Switching ====================

    def _get_active_lateral_mode(self) -> str:
        """
        Determine active lateral guidance mode based on configuration and flight state.

        Uses hysteresis to prevent oscillation when velocity is near the switch threshold.
        Enforces minimum time between mode switches for stability.

        Returns:
            str: 'sideslip' or 'coordinated_turn'
        """
        try:
            # If auto-switching is disabled, use configured mode
            if not self.enable_auto_mode_switching:
                return self.lateral_guidance_mode

            current_time = time.time()
            switch_velocity = self.guidance_mode_switch_velocity
            hysteresis = self.mode_switch_hysteresis

            # Enforce minimum time between mode switches
            if current_time - self.last_mode_switch_time < self.min_mode_switch_interval:
                return self.active_lateral_mode  # Stay in current mode

            # Apply hysteresis based on current mode to prevent oscillation
            if self.active_lateral_mode == 'sideslip':
                # Need to exceed threshold + hysteresis to switch to coordinated_turn
                if self.current_velocity_magnitude >= switch_velocity + hysteresis:
                    self.last_mode_switch_time = current_time
                    logger.info(f"Lateral mode switch: sideslip -> coordinated_turn "
                               f"(v={self.current_velocity_magnitude:.2f} m/s)")
                    return 'coordinated_turn'
            else:  # coordinated_turn
                # Need to drop below threshold - hysteresis to switch to sideslip
                if self.current_velocity_magnitude <= switch_velocity - hysteresis:
                    self.last_mode_switch_time = current_time
                    logger.info(f"Lateral mode switch: coordinated_turn -> sideslip "
                               f"(v={self.current_velocity_magnitude:.2f} m/s)")
                    return 'sideslip'

            # Stay in current mode (within hysteresis band)
            return self.active_lateral_mode

        except Exception as e:
            logger.error(f"Error determining lateral mode: {e}")
            return 'sideslip'  # Safe default

    def _switch_lateral_mode(self, new_mode: str) -> None:
        """
        Switch between lateral guidance modes dynamically.

        Resets yaw smoother state when switching to coordinated_turn mode
        to prevent smoothing artifacts from the previous mode.

        Args:
            new_mode: New lateral guidance mode ('sideslip' or 'coordinated_turn')
        """
        if new_mode == self.active_lateral_mode:
            return  # Already in the requested mode

        logger.info(f"Switching lateral guidance mode: {self.active_lateral_mode} -> {new_mode}")
        self.active_lateral_mode = new_mode

        # Reset yaw smoother state for clean transition to coordinated_turn
        if new_mode == 'coordinated_turn':
            self.yaw_smoother.reset()
            logger.debug("YawRateSmoother reset for coordinated_turn mode")

    # ==================== Safety Systems ====================

    def _perform_safety_checks(self, current_time: float | None = None) -> Dict[str, Any]:
        """
        Perform comprehensive safety checks.

        Returns:
            Dict with 'safe_to_proceed' boolean and 'reason' for any failures
        """
        current_time = time.time() if current_time is None else current_time
        if self._safety_checks_bypassed_for_testing():
            return {'safe_to_proceed': True, 'reason': 'command_preview'}

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
        if self.safety_violations_count >= self.safety_manager.get_safety_behavior(self._follower_config_name).max_safety_violations:
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
        if self._safety_checks_bypassed_for_testing():
            return {'safe': True, 'reason': 'command_preview'}

        # Skip check if altitude safety is disabled
        if not self.is_altitude_safety_enabled():
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
        logger.warning("Emergency stop triggered")
        self.emergency_stop_active = True
        self.following_active = False

        try:
            if not self.set_command_fields(
                {
                    "vel_body_fwd": 0.0,
                    "vel_body_right": 0.0,
                    "vel_body_down": 0.0,
                    "yawspeed_deg_s": 0.0,
                },
                reason='gm_velocity_vector_emergency_stop',
            ):
                logger.error("Failed to apply gimbal vector emergency-stop command intent")
            self.current_velocity_magnitude = 0.0
            self.last_command_vector = None
            self.last_velocity_vector = None
            smoother = getattr(self, "yaw_smoother", None)
            if smoother is not None:
                smoother.reset()
        except Exception as e:
            logger.error(f"Failed to set emergency zero velocities: {e}")

        self.log_follower_event("emergency_stop_triggered")

    def reset_emergency_stop(self) -> None:
        """Reset emergency stop state."""
        logger.info("Emergency stop reset")
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
            'follower_type': 'GMVelocityVectorFollower',
            'display_name': self.get_display_name(),
            'following_active': self.following_active,
            'emergency_stop_active': self.emergency_stop_active,
            'configuration': {
                'mount_type': self.mount_type,
                'altitude_control': self.enable_altitude_control,
                'lateral_guidance_mode': self.active_lateral_mode,
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
        return f"GMVelocityVectorFollower(mount={self.mount_type}, active={self.following_active}, vel_mag={self.current_velocity_magnitude:.2f} m/s)"
