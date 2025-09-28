# src/classes/gimbal_transforms.py

"""
Gimbal Coordinate Transformation Pipeline
=========================================

This module provides mount-aware coordinate transformations for gimbal-based
drone following systems. It converts gimbal angles to drone velocity commands
based on mount configuration and provides robust validation and safety checks.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Key Features:
- Mount-aware transformations (VERTICAL/HORIZONTAL)
- Robust angle normalization and validation
- Safety-first approach with comprehensive error handling
- Zero hardcoding - fully configurable via YAML
- Seamless integration with existing follower architecture
"""

import math
import logging
import time
from typing import Dict, Tuple, Optional, Any, List
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class MountType(Enum):
    """Gimbal mount types supported by the transformation pipeline."""
    VERTICAL = "VERTICAL"      # Roll controls azimuth, pitch controls elevation
    HORIZONTAL = "HORIZONTAL"  # Direct 1:1 mapping with drone coordinates

class ControlMode(Enum):
    """Drone control coordinate systems."""
    NED = "NED"        # North-East-Down world coordinates
    BODY = "BODY"      # Body frame coordinates (forward-right-down)

class ValidationLevel(Enum):
    """Safety validation levels for gimbal transformations."""
    BASIC = "BASIC"        # Basic range and NaN checks
    STRICT = "STRICT"      # Additional consistency and rate checks
    PARANOID = "PARANOID"  # Maximum validation with temporal checks

@dataclass
class GimbalAngles:
    """
    Container for gimbal angle data with validation.

    Attributes:
        roll: Roll angle in degrees (-180 to +180)
        pitch: Pitch angle in degrees (-90 to +90)
        yaw: Yaw angle in degrees (-180 to +180)
        timestamp: Optional timestamp for data freshness validation
    """
    roll: float
    pitch: float
    yaw: float
    timestamp: Optional[float] = None

    def __post_init__(self):
        """Validate angle ranges on creation."""
        # Handle NaN and infinity values first
        if math.isnan(self.roll) or math.isinf(self.roll):
            self.roll = 0.0
        if math.isnan(self.pitch) or math.isinf(self.pitch):
            self.pitch = 90.0  # Default to center for vertical mount
        if math.isnan(self.yaw) or math.isinf(self.yaw):
            self.yaw = 0.0

        # Then normalize and clamp
        self.roll = self._normalize_angle_180(self.roll)
        self.pitch = self._clamp_pitch(self.pitch)
        self.yaw = self._normalize_angle_180(self.yaw)

    @staticmethod
    def _normalize_angle_180(angle: float) -> float:
        """Normalize angle to [-180, +180] range."""
        while angle > 180.0:
            angle -= 360.0
        while angle <= -180.0:
            angle += 360.0
        return angle

    @staticmethod
    def _clamp_pitch(pitch: float) -> float:
        """Clamp pitch to safe [-90, +90] range."""
        return max(-90.0, min(90.0, pitch))

    def is_valid(self) -> bool:
        """Check if angles are within valid ranges."""
        return (
            -180.0 <= self.roll <= 180.0 and
            -90.0 <= self.pitch <= 90.0 and
            -180.0 <= self.yaw <= 180.0 and
            not any(math.isnan(val) for val in [self.roll, self.pitch, self.yaw]) and
            not any(math.isinf(val) for val in [self.roll, self.pitch, self.yaw])
        )

@dataclass
class VelocityCommand:
    """
    Container for drone velocity commands.

    Attributes:
        forward: Forward velocity (m/s, positive = forward)
        right: Right velocity (m/s, positive = right)
        down: Down velocity (m/s, positive = down)
        yaw_rate: Yaw rate (deg/s, positive = clockwise)
    """
    forward: float = 0.0
    right: float = 0.0
    down: float = 0.0
    yaw_rate: float = 0.0

    def apply_limits(self, max_velocity: float, max_yaw_rate: float):
        """Apply velocity and yaw rate limits."""
        # Clamp individual velocities
        self.forward = max(-max_velocity, min(max_velocity, self.forward))
        self.right = max(-max_velocity, min(max_velocity, self.right))
        self.down = max(-max_velocity, min(max_velocity, self.down))
        self.yaw_rate = max(-max_yaw_rate, min(max_yaw_rate, self.yaw_rate))

    def scale_magnitude(self, max_velocity: float):
        """Scale total velocity magnitude while preserving direction."""
        horizontal_mag = math.sqrt(self.forward**2 + self.right**2)
        if horizontal_mag > max_velocity:
            scale_factor = max_velocity / horizontal_mag
            self.forward *= scale_factor
            self.right *= scale_factor

    def is_safe(self, max_velocity: float, max_yaw_rate: float) -> bool:
        """Check if velocity command is within safe limits."""
        return (
            abs(self.forward) <= max_velocity and
            abs(self.right) <= max_velocity and
            abs(self.down) <= max_velocity and
            abs(self.yaw_rate) <= max_yaw_rate and
            all(not math.isnan(v) for v in [self.forward, self.right, self.down, self.yaw_rate]) and
            all(not math.isinf(v) for v in [self.forward, self.right, self.down, self.yaw_rate])
        )

class GimbalSafetyValidator:
    """
    Comprehensive safety validation system for gimbal transformations.

    Provides multi-level validation with temporal consistency checks,
    rate limiting, and anomaly detection to ensure safe drone operation.
    """

    def __init__(self, config: Dict[str, Any]):
        """Initialize safety validator with configuration."""
        self.config = config

        # Safety limits
        self.max_velocity = config.get('MAX_VELOCITY', 8.0)
        self.max_yaw_rate = config.get('MAX_YAW_RATE', 45.0)
        self.max_angular_rate = config.get('MAX_ANGULAR_RATE', 30.0)  # deg/s for gimbal

        # Validation configuration
        validation_level_str = config.get('VALIDATION_LEVEL', 'STRICT')
        self.validation_level = ValidationLevel(validation_level_str)

        # Temporal validation parameters
        self.max_data_age = config.get('MAX_DATA_AGE', 1.0)  # seconds
        self.rate_check_window = config.get('RATE_CHECK_WINDOW', 0.1)  # seconds

        # Anomaly detection
        self.anomaly_threshold = config.get('ANOMALY_THRESHOLD', 3.0)  # sigma
        self.enable_anomaly_detection = config.get('ENABLE_ANOMALY_DETECTION', True)

        # History for rate and anomaly detection
        self._angle_history: List[Tuple[float, GimbalAngles]] = []
        self._velocity_history: List[Tuple[float, VelocityCommand]] = []
        self._max_history_size = 50

        logger.info(f"GimbalSafetyValidator initialized: {self.validation_level.value} level")

    def validate_gimbal_angles(self, angles: GimbalAngles) -> Tuple[bool, List[str]]:
        """
        Comprehensive validation of gimbal angle data.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Basic validation (always performed)
        if not angles.is_valid():
            errors.append("Gimbal angles contain invalid values (NaN, inf, or out of range)")

        # Temporal validation
        current_time = time.time()
        if angles.timestamp is not None:
            data_age = current_time - angles.timestamp
            if data_age > self.max_data_age:
                errors.append(f"Gimbal data too old: {data_age:.2f}s > {self.max_data_age}s")

        # Strict validation
        if self.validation_level in [ValidationLevel.STRICT, ValidationLevel.PARANOID]:
            errors.extend(self._validate_angular_rates(angles, current_time))

        # Paranoid validation
        if self.validation_level == ValidationLevel.PARANOID:
            errors.extend(self._validate_anomalies(angles, current_time))

        # Update history
        self._update_angle_history(current_time, angles)

        return len(errors) == 0, errors

    def validate_velocity_command(self, velocity: VelocityCommand) -> Tuple[bool, List[str]]:
        """
        Validate generated velocity command for safety.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Basic safety checks
        if not velocity.is_safe(self.max_velocity, self.max_yaw_rate):
            errors.append("Velocity command exceeds safety limits")

        # Check for reasonable velocity magnitudes (allow some tolerance)
        horizontal_mag = math.sqrt(velocity.forward**2 + velocity.right**2)
        if horizontal_mag > self.max_velocity * 1.5:  # 50% tolerance for safety validator
            errors.append(f"Horizontal velocity magnitude too high: {horizontal_mag:.2f} m/s")

        # Strict validation for velocity rates
        if self.validation_level in [ValidationLevel.STRICT, ValidationLevel.PARANOID]:
            current_time = time.time()
            errors.extend(self._validate_velocity_rates(velocity, current_time))

        # Update history
        self._update_velocity_history(time.time(), velocity)

        return len(errors) == 0, errors

    def _validate_angular_rates(self, angles: GimbalAngles, timestamp: float) -> List[str]:
        """Validate gimbal angular rates are reasonable."""
        errors = []

        if len(self._angle_history) < 2:
            return errors  # Need history for rate calculation

        # Get most recent previous angles
        prev_time, prev_angles = self._angle_history[-1]
        dt = timestamp - prev_time

        if dt <= 0 or dt > self.rate_check_window:
            return errors  # Skip if time delta is invalid

        # Calculate angular rates
        roll_rate = abs(angle_difference(prev_angles.roll, angles.roll)) / dt
        pitch_rate = abs(angle_difference(prev_angles.pitch, angles.pitch)) / dt
        yaw_rate = abs(angle_difference(prev_angles.yaw, angles.yaw)) / dt

        # Check against limits
        if roll_rate > self.max_angular_rate:
            errors.append(f"Roll rate too high: {roll_rate:.1f} deg/s")
        if pitch_rate > self.max_angular_rate:
            errors.append(f"Pitch rate too high: {pitch_rate:.1f} deg/s")
        if yaw_rate > self.max_angular_rate:
            errors.append(f"Yaw rate too high: {yaw_rate:.1f} deg/s")

        return errors

    def _validate_velocity_rates(self, velocity: VelocityCommand, timestamp: float) -> List[str]:
        """Validate velocity command rates are reasonable."""
        errors = []

        if len(self._velocity_history) < 2:
            return errors

        prev_time, prev_velocity = self._velocity_history[-1]
        dt = timestamp - prev_time

        if dt <= 0 or dt > self.rate_check_window:
            return errors

        # Calculate acceleration magnitudes
        forward_accel = abs(velocity.forward - prev_velocity.forward) / dt
        right_accel = abs(velocity.right - prev_velocity.right) / dt
        yaw_accel = abs(velocity.yaw_rate - prev_velocity.yaw_rate) / dt

        # Check against reasonable limits (configurable)
        max_accel = self.config.get('MAX_ACCELERATION', 5.0)  # m/s²
        max_yaw_accel = self.config.get('MAX_YAW_ACCELERATION', 90.0)  # deg/s²

        if forward_accel > max_accel:
            errors.append(f"Forward acceleration too high: {forward_accel:.1f} m/s²")
        if right_accel > max_accel:
            errors.append(f"Right acceleration too high: {right_accel:.1f} m/s²")
        if yaw_accel > max_yaw_accel:
            errors.append(f"Yaw acceleration too high: {yaw_accel:.1f} deg/s²")

        return errors

    def _validate_anomalies(self, angles: GimbalAngles, timestamp: float) -> List[str]:
        """Detect statistical anomalies in gimbal data."""
        errors = []

        if not self.enable_anomaly_detection or len(self._angle_history) < 10:
            return errors

        # Simple outlier detection based on recent history
        recent_rolls = [a.roll for _, a in self._angle_history[-10:]]
        recent_pitches = [a.pitch for _, a in self._angle_history[-10:]]

        # Calculate mean and standard deviation
        roll_mean = sum(recent_rolls) / len(recent_rolls)
        roll_std = math.sqrt(sum((r - roll_mean)**2 for r in recent_rolls) / len(recent_rolls))

        pitch_mean = sum(recent_pitches) / len(recent_pitches)
        pitch_std = math.sqrt(sum((p - pitch_mean)**2 for p in recent_pitches) / len(recent_pitches))

        # Check for outliers
        if roll_std > 0 and abs(angles.roll - roll_mean) > self.anomaly_threshold * roll_std:
            errors.append(f"Roll angle anomaly detected: {angles.roll:.1f}° (mean: {roll_mean:.1f}±{roll_std:.1f})")

        if pitch_std > 0 and abs(angles.pitch - pitch_mean) > self.anomaly_threshold * pitch_std:
            errors.append(f"Pitch angle anomaly detected: {angles.pitch:.1f}° (mean: {pitch_mean:.1f}±{pitch_std:.1f})")

        return errors

    def _update_angle_history(self, timestamp: float, angles: GimbalAngles):
        """Update angle history for validation purposes."""
        self._angle_history.append((timestamp, angles))
        if len(self._angle_history) > self._max_history_size:
            self._angle_history.pop(0)

    def _update_velocity_history(self, timestamp: float, velocity: VelocityCommand):
        """Update velocity history for validation purposes."""
        self._velocity_history.append((timestamp, velocity))
        if len(self._velocity_history) > self._max_history_size:
            self._velocity_history.pop(0)

    def get_validation_statistics(self) -> Dict[str, Any]:
        """Get validation statistics for monitoring and debugging."""
        return {
            'validation_level': self.validation_level.value,
            'angle_history_size': len(self._angle_history),
            'velocity_history_size': len(self._velocity_history),
            'max_velocity_limit': self.max_velocity,
            'max_yaw_rate_limit': self.max_yaw_rate,
            'max_angular_rate_limit': self.max_angular_rate,
            'anomaly_detection_enabled': self.enable_anomaly_detection
        }

    def reset_history(self):
        """Reset validation history (useful for target re-acquisition)."""
        self._angle_history.clear()
        self._velocity_history.clear()
        logger.debug("Safety validator history reset")

class GimbalTransformationEngine:
    """
    Core transformation engine for gimbal-based drone control.

    Converts gimbal angles to drone velocity commands based on mount configuration.
    Provides comprehensive validation, safety checks, and configurable parameters.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize transformation engine with configuration.

        Args:
            config: Configuration dictionary from YAML (e.g., GimbalFollower section)
        """
        self.config = config

        # Parse mount and control configuration
        self.mount_type = MountType(config.get('MOUNT_TYPE', 'VERTICAL'))
        self.control_mode = ControlMode(config.get('CONTROL_MODE', 'BODY'))

        # Velocity parameters
        self.base_velocity = config.get('BASE_VELOCITY', 2.0)
        self.max_velocity = config.get('MAX_VELOCITY', 8.0)
        self.velocity_filter_alpha = config.get('VELOCITY_FILTER_ALPHA', 0.7)

        # Yaw control parameters
        self.yaw_rate_gain = config.get('YAW_RATE_GAIN', 0.5)
        self.max_yaw_rate = config.get('MAX_YAW_RATE', 45.0)

        # Coordinate transformation parameters
        self.angle_deadzone = config.get('ANGLE_DEADZONE', 2.0)
        self.transformation_validation = config.get('TRANSFORMATION_VALIDATION', True)

        # Internal state for filtering
        self._last_velocity = VelocityCommand()
        self._initialization_complete = False

        # Safety validator
        self.safety_validator = GimbalSafetyValidator(config) if self.transformation_validation else None

        logger.info(f"GimbalTransformationEngine initialized: {self.mount_type.value} mount, {self.control_mode.value} control")
        if self.safety_validator:
            logger.info(f"Safety validation enabled: {self.safety_validator.validation_level.value} level")

    def transform_angles_to_velocity(self, gimbal_angles: GimbalAngles) -> Tuple[VelocityCommand, bool]:
        """
        Transform gimbal angles to drone velocity commands.

        Args:
            gimbal_angles: Validated gimbal angle data

        Returns:
            Tuple of (VelocityCommand, success_flag)
        """
        try:
            # Safety validation (comprehensive when enabled)
            if self.safety_validator:
                angles_valid, angle_errors = self.safety_validator.validate_gimbal_angles(gimbal_angles)
                if not angles_valid:
                    logger.warning(f"Gimbal angles failed safety validation: {'; '.join(angle_errors)}")
                    return VelocityCommand(), False
            else:
                # Basic validation when safety validator disabled
                if not gimbal_angles.is_valid():
                    logger.warning("Invalid gimbal angles provided to transformation")
                    return VelocityCommand(), False

            # Apply deadzone filtering
            filtered_angles = self._apply_deadzone_filter(gimbal_angles)

            # Mount-specific transformation
            if self.mount_type == MountType.VERTICAL:
                velocity_cmd = self._transform_vertical_mount(filtered_angles)
            elif self.mount_type == MountType.HORIZONTAL:
                velocity_cmd = self._transform_horizontal_mount(filtered_angles)
            else:
                logger.error(f"Unsupported mount type: {self.mount_type}")
                return VelocityCommand(), False

            # Apply velocity and safety limits
            velocity_cmd.apply_limits(self.max_velocity, self.max_yaw_rate)

            # Apply velocity filtering for smooth operation
            if self._initialization_complete:
                velocity_cmd = self._apply_velocity_filtering(velocity_cmd)
            else:
                self._initialization_complete = True

            # Final safety validation of velocity command
            if self.safety_validator:
                velocity_valid, velocity_errors = self.safety_validator.validate_velocity_command(velocity_cmd)
                if not velocity_valid:
                    logger.warning(f"Generated velocity command failed safety validation: {'; '.join(velocity_errors)}")
                    # Return zero velocity for safety
                    return VelocityCommand(), False

            # Update internal state
            self._last_velocity = velocity_cmd

            logger.debug(f"Transformed angles {gimbal_angles.roll:.1f}°/{gimbal_angles.pitch:.1f}°/{gimbal_angles.yaw:.1f}° "
                        f"→ vel({velocity_cmd.forward:.2f}/{velocity_cmd.right:.2f}/{velocity_cmd.down:.2f}) "
                        f"yaw_rate({velocity_cmd.yaw_rate:.1f}°/s)")

            return velocity_cmd, True

        except Exception as e:
            logger.error(f"Error in gimbal angle transformation: {e}")
            return VelocityCommand(), False

    def _apply_deadzone_filter(self, angles: GimbalAngles) -> GimbalAngles:
        """Apply deadzone filtering to reduce noise and micro-movements."""
        def apply_deadzone(angle: float, reference: float = 0.0) -> float:
            diff = angle - reference
            return reference if abs(diff) < self.angle_deadzone else angle

        # For vertical mount, pitch deadzone is relative to 90° (center position)
        if self.mount_type == MountType.VERTICAL:
            filtered_pitch = apply_deadzone(angles.pitch, 90.0)
        else:
            filtered_pitch = apply_deadzone(angles.pitch, 0.0)

        return GimbalAngles(
            roll=apply_deadzone(angles.roll, 0.0),
            pitch=filtered_pitch,
            yaw=apply_deadzone(angles.yaw, 0.0),
            timestamp=angles.timestamp
        )

    def _transform_vertical_mount(self, angles: GimbalAngles) -> VelocityCommand:
        """
        Transform angles for VERTICAL mount configuration.

        Vertical Mount Mapping:
        - Gimbal starts at pitch=90° (pointing up)
        - Roll controls azimuth (left/right movement)
        - Pitch controls elevation (forward/back movement from 90° reference)
        - Yaw controls drone rotation
        """
        # Convert pitch from vertical reference (90° = forward)
        elevation_angle = angles.pitch - 90.0

        # Calculate velocity components
        # Roll → lateral movement (right velocity)
        right_velocity = self.base_velocity * math.sin(math.radians(angles.roll))

        # Elevation → forward movement
        forward_velocity = self.base_velocity * math.sin(math.radians(elevation_angle))

        # Yaw → yaw rate
        yaw_rate = angles.yaw * self.yaw_rate_gain

        return VelocityCommand(
            forward=forward_velocity,
            right=right_velocity,
            down=0.0,  # Altitude control handled separately
            yaw_rate=yaw_rate
        )

    def _transform_horizontal_mount(self, angles: GimbalAngles) -> VelocityCommand:
        """
        Transform angles for HORIZONTAL mount configuration.

        Horizontal Mount Mapping:
        - Direct 1:1 mapping with drone coordinates
        - Roll → right velocity
        - Pitch → forward velocity
        - Yaw → yaw rate
        """
        # Direct mapping for horizontal mount
        forward_velocity = self.base_velocity * math.sin(math.radians(angles.pitch))
        right_velocity = self.base_velocity * math.sin(math.radians(angles.roll))
        yaw_rate = angles.yaw * self.yaw_rate_gain

        return VelocityCommand(
            forward=forward_velocity,
            right=right_velocity,
            down=0.0,  # Altitude control handled separately
            yaw_rate=yaw_rate
        )

    def _apply_velocity_filtering(self, new_velocity: VelocityCommand) -> VelocityCommand:
        """Apply exponential filtering for smooth velocity transitions."""
        alpha = self.velocity_filter_alpha

        return VelocityCommand(
            forward=alpha * new_velocity.forward + (1 - alpha) * self._last_velocity.forward,
            right=alpha * new_velocity.right + (1 - alpha) * self._last_velocity.right,
            down=alpha * new_velocity.down + (1 - alpha) * self._last_velocity.down,
            yaw_rate=alpha * new_velocity.yaw_rate + (1 - alpha) * self._last_velocity.yaw_rate
        )

    def reset_state(self):
        """Reset internal filtering state (useful for target re-acquisition)."""
        self._last_velocity = VelocityCommand()
        self._initialization_complete = False
        if self.safety_validator:
            self.safety_validator.reset_history()
        logger.debug("Gimbal transformation state reset")

    def get_configuration_summary(self) -> Dict[str, Any]:
        """Get current configuration summary for debugging/reporting."""
        summary = {
            'mount_type': self.mount_type.value,
            'control_mode': self.control_mode.value,
            'base_velocity': self.base_velocity,
            'max_velocity': self.max_velocity,
            'max_yaw_rate': self.max_yaw_rate,
            'angle_deadzone': self.angle_deadzone,
            'velocity_filter_alpha': self.velocity_filter_alpha,
            'yaw_rate_gain': self.yaw_rate_gain,
            'transformation_validation': self.transformation_validation
        }

        # Add safety validator statistics if available
        if self.safety_validator:
            summary['safety_validation'] = self.safety_validator.get_validation_statistics()

        return summary

    def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health status for monitoring."""
        return {
            'transformation_engine': {
                'initialized': self._initialization_complete,
                'last_velocity': {
                    'forward': self._last_velocity.forward,
                    'right': self._last_velocity.right,
                    'down': self._last_velocity.down,
                    'yaw_rate': self._last_velocity.yaw_rate
                },
                'configuration_valid': True,  # TODO: Add configuration validation
                'mount_type': self.mount_type.value,
                'control_mode': self.control_mode.value
            },
            'safety_system': (
                self.safety_validator.get_validation_statistics()
                if self.safety_validator
                else {'enabled': False, 'status': 'disabled'}
            ),
            'system_status': 'healthy'  # TODO: Add comprehensive health checks
        }

def create_gimbal_transformer(config: Dict[str, Any]) -> GimbalTransformationEngine:
    """
    Factory function to create gimbal transformation engine.

    Args:
        config: Configuration dictionary (typically from Parameters.GIMBAL_FOLLOWER)

    Returns:
        Configured GimbalTransformationEngine instance
    """
    return GimbalTransformationEngine(config)

# Utility functions for angle operations
def degrees_to_radians(degrees: float) -> float:
    """Convert degrees to radians."""
    return degrees * math.pi / 180.0

def radians_to_degrees(radians: float) -> float:
    """Convert radians to degrees."""
    return radians * 180.0 / math.pi

def normalize_angle_180(angle: float) -> float:
    """Normalize angle to [-180, +180] range."""
    return GimbalAngles._normalize_angle_180(angle)

def angle_difference(angle1: float, angle2: float) -> float:
    """Calculate shortest angular difference between two angles."""
    diff = angle2 - angle1
    return normalize_angle_180(diff)

if __name__ == "__main__":
    # Test the transformation pipeline
    print("Gimbal Transformation Pipeline Test")
    print("=" * 50)

    # Test configuration
    test_config = {
        'MOUNT_TYPE': 'VERTICAL',
        'CONTROL_MODE': 'BODY',
        'BASE_VELOCITY': 2.0,
        'MAX_VELOCITY': 8.0,
        'MAX_YAW_RATE': 45.0,
        'ANGLE_DEADZONE': 2.0,
        'VELOCITY_FILTER_ALPHA': 0.7,
        'YAW_RATE_GAIN': 0.5
    }

    # Create transformer
    transformer = create_gimbal_transformer(test_config)
    print(f"Configuration: {transformer.get_configuration_summary()}")

    # Test cases
    test_cases = [
        GimbalAngles(0.0, 90.0, 0.0),    # Center position
        GimbalAngles(15.0, 75.0, 0.0),   # Right and forward
        GimbalAngles(-10.0, 105.0, 5.0), # Left, back, slight yaw
        GimbalAngles(0.0, 85.0, 0.0),    # Forward movement
    ]

    print("\nTransformation Tests:")
    print("-" * 50)
    for i, angles in enumerate(test_cases, 1):
        velocity, success = transformer.transform_angles_to_velocity(angles)
        status = "PASS" if success else "FAIL"
        print(f"Test {i} {status}: angles({angles.roll:.1f}, {angles.pitch:.1f}, {angles.yaw:.1f}) "
              f"-> vel({velocity.forward:.2f}, {velocity.right:.2f}, {velocity.down:.2f}) "
              f"yaw({velocity.yaw_rate:.1f})")