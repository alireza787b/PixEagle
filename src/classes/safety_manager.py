# src/classes/safety_manager.py
"""
Safety Manager Module - Centralized Safety Limit Management
============================================================

This module provides a singleton SafetyManager class that centralizes all
safety limit management for PixEagle followers. It implements a simple
configuration system with caching for performance.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi

Architecture (v5.0.0+):
- Singleton pattern for global access
- Single source of truth: Safety.GlobalLimits
- Optional per-follower overrides: Safety.FollowerOverrides
- Cached lookups for O(1) access after first resolution

Resolution Order:
1. Follower-specific override (Safety.FollowerOverrides.{follower})
2. Global limit (Safety.GlobalLimits - single source of truth)
3. Hardcoded fallback (safety default)

Breaking Changes in v5.0.0:
- Per-follower MIN_ALTITUDE/MAX_ALTITUDE moved to Safety.FollowerOverrides
- VehicleProfiles removed (was deprecated in v3.6.0)
- SafetyLimits section renamed to Safety.GlobalLimits
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
    limits across all followers, with support for per-follower overrides.

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

        Architecture (v5.0.0+):
        - Single Source of Truth: Safety.GlobalLimits
        - Per-Follower Overrides: Safety.FollowerOverrides
        - No legacy SafetyLimits or VehicleProfiles support

        Args:
            config: Parsed configuration dictionary
        """
        with self._lock:
            self._cache.clear()

            # Load Safety section (REQUIRED in v5.0.0+)
            safety_config = config.get('Safety', {})

            if not safety_config:
                logger.error("Missing Safety section in config! Using hardcoded fallbacks.")
                self._global_limits = {}
                self._follower_overrides = {}
            else:
                # Load GlobalLimits (single source of truth)
                self._global_limits = safety_config.get('GlobalLimits', {})
                self._follower_overrides = safety_config.get('FollowerOverrides', {})
                logger.info(f"Loaded Safety configuration (GlobalLimits: {len(self._global_limits)} params)")

            # Load Followers section (behavior only)
            self._follower_configs = config.get('Followers', {})

            self._initialized = True
            logger.info(f"SafetyManager initialized (overrides: {len(self._follower_overrides)} followers)")

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
        Resolve a limit value through the simplified hierarchy.

        Order: Follower Override → GlobalLimits → Fallback

        Note: Follower names are normalized to uppercase for case-insensitive lookup.
        """
        # 1. Check follower-specific override (normalize to uppercase for consistent lookup)
        if follower_name:
            normalized_name = follower_name.upper()
            override = self._follower_overrides.get(normalized_name, {})
            if limit_name in override:
                return override[limit_name]

            # Handle alias (MAX_FORWARD_VELOCITY → MAX_VELOCITY_FORWARD)
            if limit_name == 'MAX_VELOCITY_FORWARD' and 'MAX_FORWARD_VELOCITY' in override:
                return override['MAX_FORWARD_VELOCITY']

        # 2. Check global limits (single source of truth)
        if limit_name in self._global_limits:
            return self._global_limits[limit_name]

        # 3. Return hardcoded fallback
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
                max_magnitude=self.get_limit('MAX_VELOCITY', follower_name)
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
                pitch=radians(self.get_limit('MAX_PITCH_RATE', follower_name)),
                roll=radians(self.get_limit('MAX_ROLL_RATE', follower_name))
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
        """
        Check if altitude safety is enabled for a follower.

        Resolution order (first match wins):
        1. Follower-specific override
        2. Global limits
        3. Fallback (enabled by default for safety)

        Note: Follower names are normalized to uppercase for case-insensitive lookup.
        """
        # 1. Check follower-specific override (normalize to uppercase)
        normalized_name = follower_name.upper() if follower_name else None
        override = self._follower_overrides.get(normalized_name, {}) if normalized_name else {}
        if 'ALTITUDE_SAFETY_ENABLED' in override:
            return bool(override['ALTITUDE_SAFETY_ENABLED'])

        # 2. Check global limits
        if 'ALTITUDE_SAFETY_ENABLED' in self._global_limits:
            return bool(self._global_limits['ALTITUDE_SAFETY_ENABLED'])

        # 3. Default to enabled (safe default)
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
            'follower_overrides': self._follower_overrides,
            'cache_size': len(self._cache),
            'initialized': self._initialized,
        }

    def get_effective_limits_summary(self, follower_name: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Get detailed limit resolution for UI display.

        For each safety limit, returns the effective value, source, and override info.
        This enables the UI to show where each value comes from.

        Args:
            follower_name: Optional follower name for context-specific resolution

        Returns:
            Dict mapping limit names to resolution info:
            {
                'MIN_ALTITUDE': {
                    'effective_value': 5.0,
                    'source': 'FollowerOverrides.MC_VELOCITY_CHASE',  # or 'GlobalLimits' or 'Fallback'
                    'global_value': 3.0,
                    'override_value': 5.0,  # None if not overridden
                    'fallback_value': 3.0,
                    'is_overridden': True
                },
                ...
            }

        Note: Follower names are normalized to uppercase for case-insensitive lookup.
        """
        # Define all safety limit parameters
        LIMIT_PARAMS = [
            'MIN_ALTITUDE', 'MAX_ALTITUDE', 'ALTITUDE_WARNING_BUFFER', 'ALTITUDE_SAFETY_ENABLED',
            'MAX_VELOCITY', 'MAX_VELOCITY_FORWARD', 'MAX_VELOCITY_LATERAL', 'MAX_VELOCITY_VERTICAL',
            'MAX_YAW_RATE', 'MAX_PITCH_RATE', 'MAX_ROLL_RATE',
            'EMERGENCY_STOP_ENABLED', 'RTL_ON_VIOLATION', 'TARGET_LOSS_ACTION', 'MAX_SAFETY_VIOLATIONS'
        ]

        result = {}
        # Normalize follower name to uppercase for consistent lookup
        normalized_name = follower_name.upper() if follower_name else None
        override = self._follower_overrides.get(normalized_name, {}) if normalized_name else {}

        for param in LIMIT_PARAMS:
            global_value = self._global_limits.get(param)
            override_value = override.get(param) if follower_name else None
            fallback_value = self._FALLBACKS.get(param)

            # Determine effective value and source
            if override_value is not None:
                effective_value = override_value
                source = f'FollowerOverrides.{normalized_name}'
            elif global_value is not None:
                effective_value = global_value
                source = 'GlobalLimits'
            else:
                effective_value = fallback_value
                source = 'Fallback'

            result[param] = {
                'effective_value': effective_value,
                'source': source,
                'global_value': global_value,
                'override_value': override_value,
                'fallback_value': fallback_value,
                'is_overridden': override_value is not None
            }

        return result

    def get_available_followers(self) -> List[str]:
        """Get list of followers with configured overrides."""
        return list(self._follower_overrides.keys())


# Module-level convenience functions
def get_safety_manager() -> SafetyManager:
    """Get the SafetyManager singleton instance."""
    return SafetyManager.get_instance()


def get_limit(limit_name: str, follower_name: Optional[str] = None) -> float:
    """Convenience function to get a limit value."""
    return get_safety_manager().get_limit(limit_name, follower_name)
