# src/classes/safety_manager.py
"""
Safety Manager Module - Centralized Safety Limit Management
============================================================

This module provides a singleton SafetyManager class that centralizes all
safety limit management for PixEagle followers. It implements a layered
configuration system with caching for performance.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi

Architecture:
- Singleton pattern for global access
- Layered limit resolution: Global → Vehicle Profile → Follower Override
- Cached lookups for O(1) access after first resolution
- Observable pattern for runtime updates

Resolution Order:
1. Follower-specific override (if exists)
2. Vehicle profile limit (based on follower's vehicle type)
3. Global hard limit (absolute bounds)
4. Hardcoded fallback (safety default)
"""

import logging
import threading
from typing import Dict, Optional, Callable, List, Any
from math import radians, degrees

from classes.safety_types import (
    VelocityLimits, AltitudeLimits, RateLimits, SafetyBehavior,
    SafetyStatus, SafetyAction, FollowerLimits,
    VehicleType, TargetLossAction, FOLLOWER_VEHICLE_TYPE, FIELD_LIMIT_MAPPING
)

logger = logging.getLogger(__name__)


class SafetyManager:
    """
    Centralized safety limit management with caching and runtime updates.

    This singleton class provides a unified interface for accessing safety
    limits across all followers, with support for vehicle profiles and
    per-follower overrides.

    Usage:
        safety = SafetyManager.get_instance()
        limits = safety.get_velocity_limits('MC_VELOCITY_CHASE')
        status = safety.check_altitude_safety(50.0, 'MC_VELOCITY_CHASE')
    """

    _instance: Optional['SafetyManager'] = None
    _lock = threading.Lock()

    # Hardcoded fallbacks for safety (used if config is missing)
    _FALLBACKS = {
        'MIN_ALTITUDE': 3.0,
        'MAX_ALTITUDE': 120.0,
        'ALTITUDE_WARNING_BUFFER': 2.0,
        'MAX_VELOCITY': 15.0,
        'MAX_VELOCITY_FORWARD': 8.0,
        'MAX_VELOCITY_LATERAL': 5.0,
        'MAX_VELOCITY_VERTICAL': 3.0,
        'MAX_YAW_RATE': 45.0,
        'MAX_PITCH_RATE': 45.0,
        'MAX_ROLL_RATE': 45.0,
        'EMERGENCY_STOP_ENABLED': True,
        'RTL_ON_VIOLATION': True,
        'ALTITUDE_SAFETY_ENABLED': True,
        'MAX_SAFETY_VIOLATIONS': 5,
        'TARGET_LOSS_ACTION': 'hover',
    }

    def __init__(self):
        """Initialize SafetyManager. Use get_instance() instead."""
        self._global_limits: Dict[str, Any] = {}
        self._vehicle_profiles: Dict[str, Dict[str, Any]] = {}
        self._follower_overrides: Dict[str, Dict[str, Any]] = {}
        self._follower_configs: Dict[str, Dict[str, Any]] = {}  # Behavior configs
        self._cache: Dict[str, Any] = {}
        self._callbacks: List[Callable[[], None]] = []
        self._initialized = False

    @classmethod
    def get_instance(cls) -> 'SafetyManager':
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton for testing purposes."""
        with cls._lock:
            cls._instance = None

    def load_from_config(self, config: Dict[str, Any]) -> None:
        """
        Load safety configuration from parsed YAML config.

        Args:
            config: Parsed configuration dictionary
        """
        with self._lock:
            self._cache.clear()

            # Load Safety section if it exists (new structure)
            safety_config = config.get('Safety', {})

            if safety_config:
                # New unified Safety section
                self._global_limits = safety_config.get('GlobalLimits', {})
                self._vehicle_profiles = safety_config.get('VehicleProfiles', {})
                self._follower_overrides = safety_config.get('FollowerOverrides', {})
                logger.info("Loaded new unified Safety configuration")
            else:
                # Legacy: Load from SafetyLimits and per-follower sections
                self._load_legacy_config(config)

            # Load Followers section (behavior only)
            self._follower_configs = config.get('Followers', {})

            self._initialized = True
            logger.info(f"SafetyManager initialized with {len(self._vehicle_profiles)} vehicle profiles")

    def _load_legacy_config(self, config: Dict[str, Any]) -> None:
        """Load from legacy SafetyLimits + per-follower config structure."""
        # Legacy SafetyLimits becomes global
        self._global_limits = config.get('SafetyLimits', {})

        # Create vehicle profiles from common patterns
        self._vehicle_profiles = {
            'MULTICOPTER': {
                'MIN_ALTITUDE': 3.0,
                'MAX_ALTITUDE': 120.0,
                'ALTITUDE_WARNING_BUFFER': 2.0,
                'MAX_VELOCITY_FORWARD': self._global_limits.get('MAX_VELOCITY_FORWARD', 8.0),
                'MAX_VELOCITY_LATERAL': self._global_limits.get('MAX_VELOCITY_LATERAL', 5.0),
                'MAX_VELOCITY_VERTICAL': self._global_limits.get('MAX_VELOCITY_VERTICAL', 3.0),
                'MAX_YAW_RATE': 45.0,
                'MAX_PITCH_RATE': 45.0,
                'MAX_ROLL_RATE': 45.0,
                'EMERGENCY_STOP_ENABLED': True,
                'RTL_ON_VIOLATION': True,
                'TARGET_LOSS_ACTION': 'hover',
            },
            'FIXED_WING': {
                'MIN_ALTITUDE': 30.0,
                'MAX_ALTITUDE': 400.0,
                'ALTITUDE_WARNING_BUFFER': 10.0,
                'MAX_YAW_RATE': 25.0,
                'MAX_PITCH_RATE': 20.0,
                'MAX_ROLL_RATE': 45.0,
                'EMERGENCY_STOP_ENABLED': False,
                'RTL_ON_VIOLATION': True,
                'TARGET_LOSS_ACTION': 'orbit',
            },
            'GIMBAL': {
                'MIN_ALTITUDE': 3.0,
                'MAX_ALTITUDE': 120.0,
                'ALTITUDE_WARNING_BUFFER': 2.0,
                'MAX_VELOCITY': 2.0,
                'MAX_VELOCITY_FORWARD': 2.0,
                'MAX_VELOCITY_LATERAL': 3.0,
                'MAX_VELOCITY_VERTICAL': 2.0,
                'MAX_YAW_RATE': 45.0,
                'EMERGENCY_STOP_ENABLED': True,
                'RTL_ON_VIOLATION': False,
                'TARGET_LOSS_ACTION': 'stop',
            },
        }

        # Extract follower-specific overrides from legacy sections
        for follower_name in FOLLOWER_VEHICLE_TYPE.keys():
            section = config.get(follower_name, {})
            if section:
                # Only keep limit-related overrides
                override = {}
                for key in ['MIN_ALTITUDE', 'MAX_ALTITUDE', 'ALTITUDE_WARNING_BUFFER',
                           'MAX_VELOCITY', 'MAX_VELOCITY_FORWARD', 'MAX_VELOCITY_LATERAL',
                           'MAX_VELOCITY_VERTICAL', 'MAX_YAW_RATE', 'MAX_PITCH_RATE',
                           'MAX_ROLL_RATE', 'ALTITUDE_SAFETY_ENABLED', 'EMERGENCY_STOP_ENABLED',
                           'RTL_ON_VIOLATION', 'RTL_ON_ALTITUDE_VIOLATION', 'MAX_FORWARD_VELOCITY']:
                    if key in section:
                        override[key] = section[key]
                if override:
                    self._follower_overrides[follower_name] = override

        logger.info("Loaded legacy SafetyLimits configuration (migration recommended)")

    def _get_vehicle_type(self, follower_name: str) -> VehicleType:
        """Get vehicle type for a follower."""
        # Check if explicitly configured
        follower_config = self._follower_configs.get(follower_name, {})
        if 'VEHICLE_TYPE' in follower_config:
            try:
                return VehicleType(follower_config['VEHICLE_TYPE'])
            except ValueError:
                pass

        # Fall back to mapping
        return FOLLOWER_VEHICLE_TYPE.get(follower_name, VehicleType.MULTICOPTER)

    def _resolve_limit(self, limit_name: str, follower_name: Optional[str] = None) -> Any:
        """
        Resolve a limit value through the hierarchy.

        Order: Follower Override → Vehicle Profile → Global → Fallback
        """
        # 1. Check follower-specific override
        if follower_name:
            override = self._follower_overrides.get(follower_name, {})
            if limit_name in override:
                return override[limit_name]

            # Handle alias (MAX_FORWARD_VELOCITY → MAX_VELOCITY_FORWARD)
            if limit_name == 'MAX_VELOCITY_FORWARD' and 'MAX_FORWARD_VELOCITY' in override:
                return override['MAX_FORWARD_VELOCITY']

        # 2. Check vehicle profile
        if follower_name:
            vehicle_type = self._get_vehicle_type(follower_name)
            profile = self._vehicle_profiles.get(vehicle_type.value, {})
            if limit_name in profile:
                return profile[limit_name]

        # 3. Check global limits
        if limit_name in self._global_limits:
            return self._global_limits[limit_name]

        # 4. Return fallback
        return self._FALLBACKS.get(limit_name)

    def get_limit(self, limit_name: str, follower_name: Optional[str] = None) -> float:
        """
        Get an effective limit value with caching.

        Args:
            limit_name: Name of the limit (e.g., 'MAX_VELOCITY_FORWARD')
            follower_name: Optional follower name for context

        Returns:
            The effective limit value
        """
        cache_key = f"{limit_name}:{follower_name}"

        if cache_key not in self._cache:
            value = self._resolve_limit(limit_name, follower_name)
            self._cache[cache_key] = value

        return self._cache[cache_key]

    def get_velocity_limits(self, follower_name: str) -> VelocityLimits:
        """Get velocity limits for a follower."""
        cache_key = f"velocity_limits:{follower_name}"

        if cache_key not in self._cache:
            limits = VelocityLimits(
                forward=self.get_limit('MAX_VELOCITY_FORWARD', follower_name),
                lateral=self.get_limit('MAX_VELOCITY_LATERAL', follower_name),
                vertical=self.get_limit('MAX_VELOCITY_VERTICAL', follower_name),
                max_magnitude=self.get_limit('MAX_VELOCITY', follower_name) or 15.0
            )
            self._cache[cache_key] = limits

        return self._cache[cache_key]

    def get_altitude_limits(self, follower_name: str) -> AltitudeLimits:
        """Get altitude limits for a follower."""
        cache_key = f"altitude_limits:{follower_name}"

        if cache_key not in self._cache:
            limits = AltitudeLimits(
                min_altitude=self.get_limit('MIN_ALTITUDE', follower_name),
                max_altitude=self.get_limit('MAX_ALTITUDE', follower_name),
                warning_buffer=self.get_limit('ALTITUDE_WARNING_BUFFER', follower_name),
                safety_enabled=self.is_altitude_safety_enabled(follower_name)
            )
            self._cache[cache_key] = limits

        return self._cache[cache_key]

    def get_rate_limits(self, follower_name: str) -> RateLimits:
        """Get rate limits for a follower (in rad/s)."""
        cache_key = f"rate_limits:{follower_name}"

        if cache_key not in self._cache:
            # Convert from deg/s in config to rad/s
            limits = RateLimits(
                yaw=radians(self.get_limit('MAX_YAW_RATE', follower_name)),
                pitch=radians(self.get_limit('MAX_PITCH_RATE', follower_name) or 45.0),
                roll=radians(self.get_limit('MAX_ROLL_RATE', follower_name) or 45.0)
            )
            self._cache[cache_key] = limits

        return self._cache[cache_key]

    def get_safety_behavior(self, follower_name: str) -> SafetyBehavior:
        """Get safety behavior configuration for a follower."""
        cache_key = f"safety_behavior:{follower_name}"

        if cache_key not in self._cache:
            action_str = self.get_limit('TARGET_LOSS_ACTION', follower_name) or 'hover'
            try:
                target_loss_action = TargetLossAction(action_str)
            except ValueError:
                target_loss_action = TargetLossAction.HOVER

            behavior = SafetyBehavior(
                emergency_stop_enabled=bool(self.get_limit('EMERGENCY_STOP_ENABLED', follower_name)),
                rtl_on_violation=bool(self.get_limit('RTL_ON_VIOLATION', follower_name)),
                target_loss_action=target_loss_action,
                max_safety_violations=int(self.get_limit('MAX_SAFETY_VIOLATIONS', follower_name) or 5)
            )
            self._cache[cache_key] = behavior

        return self._cache[cache_key]

    def get_follower_limits(self, follower_name: str) -> FollowerLimits:
        """Get complete set of limits for a follower."""
        cache_key = f"follower_limits:{follower_name}"

        if cache_key not in self._cache:
            limits = FollowerLimits(
                velocity=self.get_velocity_limits(follower_name),
                altitude=self.get_altitude_limits(follower_name),
                rates=self.get_rate_limits(follower_name),
                behavior=self.get_safety_behavior(follower_name),
                vehicle_type=self._get_vehicle_type(follower_name)
            )
            self._cache[cache_key] = limits

        return self._cache[cache_key]

    def is_altitude_safety_enabled(self, follower_name: str) -> bool:
        """Check if altitude safety is enabled for a follower."""
        # Check explicit override
        override = self._follower_overrides.get(follower_name, {})
        if 'ALTITUDE_SAFETY_ENABLED' in override:
            return bool(override['ALTITUDE_SAFETY_ENABLED'])

        # Check vehicle profile
        vehicle_type = self._get_vehicle_type(follower_name)
        profile = self._vehicle_profiles.get(vehicle_type.value, {})
        if 'ALTITUDE_SAFETY_ENABLED' in profile:
            return bool(profile['ALTITUDE_SAFETY_ENABLED'])

        # Default to enabled
        return self._FALLBACKS.get('ALTITUDE_SAFETY_ENABLED', True)

    def check_altitude_safety(self, current_altitude: float, follower_name: str) -> SafetyStatus:
        """
        Check if current altitude is within safety limits.

        Args:
            current_altitude: Current altitude in meters
            follower_name: Follower name for context

        Returns:
            SafetyStatus indicating if altitude is safe
        """
        if not self.is_altitude_safety_enabled(follower_name):
            return SafetyStatus(safe=True, reason='altitude_safety_disabled')

        limits = self.get_altitude_limits(follower_name)

        # Check minimum altitude
        if current_altitude < limits.min_altitude:
            return SafetyStatus.violation(
                reason=f'altitude_too_low:{current_altitude:.1f}m < {limits.min_altitude:.1f}m',
                action=SafetyAction.RTL if self.get_safety_behavior(follower_name).rtl_on_violation else SafetyAction.CLAMP,
                details={'current': current_altitude, 'limit': limits.min_altitude}
            )

        # Check maximum altitude
        if current_altitude > limits.max_altitude:
            return SafetyStatus.violation(
                reason=f'altitude_too_high:{current_altitude:.1f}m > {limits.max_altitude:.1f}m',
                action=SafetyAction.RTL if self.get_safety_behavior(follower_name).rtl_on_violation else SafetyAction.CLAMP,
                details={'current': current_altitude, 'limit': limits.max_altitude}
            )

        # Check warning zone
        if current_altitude < limits.min_altitude + limits.warning_buffer:
            return SafetyStatus(
                safe=True,
                reason='altitude_warning_low',
                action=SafetyAction.WARN,
                details={'current': current_altitude, 'warning_threshold': limits.min_altitude + limits.warning_buffer}
            )

        if current_altitude > limits.max_altitude - limits.warning_buffer:
            return SafetyStatus(
                safe=True,
                reason='altitude_warning_high',
                action=SafetyAction.WARN,
                details={'current': current_altitude, 'warning_threshold': limits.max_altitude - limits.warning_buffer}
            )

        return SafetyStatus.ok()

    def validate_command(self, field: str, value: float, follower_name: str) -> float:
        """
        Validate and clamp a command value to its limits.

        Args:
            field: Field name (e.g., 'vel_body_fwd')
            value: Value to validate
            follower_name: Follower name for context

        Returns:
            Clamped value within limits
        """
        limit_name = FIELD_LIMIT_MAPPING.get(field)
        if not limit_name:
            return value  # No limit defined for this field

        max_value = self.get_limit(limit_name, follower_name)
        if max_value is None:
            return value

        # Clamp to symmetric limits
        clamped = max(-abs(max_value), min(abs(max_value), value))

        if clamped != value:
            logger.debug(f"Clamped {field} from {value:.3f} to {clamped:.3f} (limit: ±{max_value})")

        return clamped

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback for limit change notifications."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[], None]) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of limit changes."""
        for callback in self._callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in safety callback: {e}")

    def clear_cache(self) -> None:
        """Clear the limit cache (call after config changes)."""
        with self._lock:
            self._cache.clear()
            self._notify_callbacks()

    def get_all_limits_summary(self) -> Dict[str, Any]:
        """Get a summary of all configured limits for debugging/API."""
        return {
            'global_limits': self._global_limits,
            'vehicle_profiles': self._vehicle_profiles,
            'follower_overrides': self._follower_overrides,
            'cache_size': len(self._cache),
            'initialized': self._initialized,
        }


# Module-level convenience functions
def get_safety_manager() -> SafetyManager:
    """Get the SafetyManager singleton instance."""
    return SafetyManager.get_instance()


def get_limit(limit_name: str, follower_name: Optional[str] = None) -> float:
    """Convenience function to get a limit value."""
    return get_safety_manager().get_limit(limit_name, follower_name)
