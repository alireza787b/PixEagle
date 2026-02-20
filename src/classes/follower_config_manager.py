# src/classes/follower_config_manager.py
"""
Follower Config Manager — Centralized Follower Operational Config
=================================================================

Provides a singleton FollowerConfigManager that centralizes follower
operational parameters (update rates, smoothing, target loss, yaw smoothing,
lateral guidance). Mirrors the SafetyManager pattern.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi

Architecture:
- Singleton pattern for global access
- Single source of truth: Follower.General
- Optional per-follower overrides: Follower.FollowerOverrides
- Legacy fallback: reads from per-follower section with deprecation warning
- Cached lookups for O(1) access after first resolution

Resolution Order:
1. Follower-specific override (Follower.FollowerOverrides.{follower})
2. General defaults (Follower.General — single source of truth)
3. Legacy per-follower section (deprecated, emits warning)
4. Hardcoded fallback (safe default)
"""

import logging
import threading
from typing import Dict, Optional, Callable, List, Any

logger = logging.getLogger(__name__)


# Known general parameters — these are the params that belong in Follower.General.
# Used by get_effective_config_summary() for provenance reporting.
GENERAL_PARAMS = [
    'CONTROL_UPDATE_RATE',
    'COMMAND_SMOOTHING_ENABLED',
    'SMOOTHING_FACTOR',
    'TARGET_LOSS_TIMEOUT',
    'TARGET_LOSS_COORDINATE_THRESHOLD',
    'LATERAL_GUIDANCE_MODE',
    'ENABLE_AUTO_MODE_SWITCHING',
    'GUIDANCE_MODE_SWITCH_VELOCITY',
    'MODE_SWITCH_HYSTERESIS',
    'MIN_MODE_SWITCH_INTERVAL',
    'ENABLE_ALTITUDE_CONTROL',
    'ALTITUDE_CHECK_INTERVAL',
]


class FollowerConfigManager:
    """
    Centralized follower operational config with caching and runtime updates.

    This singleton class provides a unified interface for accessing follower
    operational parameters, with support for per-follower overrides.

    Usage:
        fcm = FollowerConfigManager.get_instance()
        rate = fcm.get_param('CONTROL_UPDATE_RATE', 'MC_VELOCITY_CHASE')
        yaw_cfg = fcm.get_yaw_smoothing_config('GM_VELOCITY_CHASE')
    """

    _instance: Optional['FollowerConfigManager'] = None
    _lock = threading.Lock()

    # Hardcoded fallbacks (used if config is missing entirely)
    _FALLBACKS: Dict[str, Any] = {
        'CONTROL_UPDATE_RATE': 20.0,
        'COMMAND_SMOOTHING_ENABLED': True,
        'SMOOTHING_FACTOR': 0.8,
        'TARGET_LOSS_TIMEOUT': 3.0,
        'TARGET_LOSS_COORDINATE_THRESHOLD': 1.5,
        'LATERAL_GUIDANCE_MODE': 'coordinated_turn',
        'ENABLE_AUTO_MODE_SWITCHING': False,
        'GUIDANCE_MODE_SWITCH_VELOCITY': 3.0,
        'MODE_SWITCH_HYSTERESIS': 0.5,
        'MIN_MODE_SWITCH_INTERVAL': 2.0,
        'ENABLE_ALTITUDE_CONTROL': False,
        'ALTITUDE_CHECK_INTERVAL': 0.1,
    }

    _YAW_SMOOTHING_FALLBACK: Dict[str, Any] = {
        'ENABLED': True,
        'DEADZONE_DEG_S': 0.5,
        'MAX_RATE_CHANGE_DEG_S2': 90.0,
        'SMOOTHING_ALPHA': 0.7,
        'ENABLE_SPEED_SCALING': True,
        'MIN_SPEED_THRESHOLD': 0.5,
        'MAX_SPEED_THRESHOLD': 5.0,
        'LOW_SPEED_YAW_FACTOR': 0.5,
    }

    def __init__(self):
        """Initialize FollowerConfigManager. Use get_instance() instead."""
        self._general: Dict[str, Any] = {}
        self._overrides: Dict[str, Dict[str, Any]] = {}
        self._cache: Dict[str, Any] = {}
        self._callbacks: List[Callable[[], None]] = []
        self._initialized = False

    @classmethod
    def get_instance(cls) -> 'FollowerConfigManager':
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
        Load follower configuration from parsed YAML config.

        Reads Follower.General and Follower.FollowerOverrides from the config.

        Args:
            config: Parsed configuration dictionary (full config root)
        """
        with self._lock:
            self._cache.clear()

            follower_section = config.get('Follower', {})

            if not follower_section:
                logger.warning("Missing Follower section in config. Using fallbacks.")
                self._general = {}
                self._overrides = {}
            else:
                self._general = follower_section.get('General', {})
                self._overrides = follower_section.get('FollowerOverrides', {})

                if self._general:
                    logger.info(
                        "FollowerConfigManager loaded (General: %d params, overrides: %d followers)",
                        len(self._general), len(self._overrides)
                    )
                else:
                    logger.debug("Follower.General not found; using legacy per-section config")

            self._initialized = True

    def _resolve(self, param_name: str, follower_name: Optional[str] = None) -> Any:
        """
        Resolve a parameter through the hierarchy.

        Order:
        1. Follower.FollowerOverrides.{follower}.{param}
        2. Follower.General.{param}
        3. Legacy: per-follower section (with deprecation warning)
        4. Hardcoded fallback

        Note: Follower names are normalized to uppercase for case-insensitive lookup.
        """
        # 1. Check follower-specific override
        if follower_name:
            normalized_name = follower_name.upper()
            override = self._overrides.get(normalized_name, {})
            if param_name in override:
                return override[param_name]

        # 2. Check General defaults
        if param_name in self._general:
            return self._general[param_name]

        # 3. Legacy fallback: check per-follower section in Parameters
        if follower_name:
            try:
                from classes.parameters import Parameters
                legacy_section = getattr(Parameters, follower_name.upper(), None)
                if isinstance(legacy_section, dict) and param_name in legacy_section:
                    logger.warning(
                        "DEPRECATED: '%s.%s' should move to 'Follower.General' or "
                        "'Follower.FollowerOverrides.%s'. "
                        "Legacy per-follower location will be removed in v7.0.",
                        follower_name.upper(), param_name, follower_name.upper()
                    )
                    return legacy_section[param_name]
            except ImportError:
                pass

        # 4. Hardcoded fallback
        return self._FALLBACKS.get(param_name)

    def get_param(self, param_name: str, follower_name: Optional[str] = None) -> Any:
        """
        Get an effective parameter value with caching.

        Args:
            param_name: Parameter name (e.g., 'CONTROL_UPDATE_RATE')
            follower_name: Optional follower name for per-follower resolution

        Returns:
            The effective parameter value
        """
        cache_key = f"{param_name}:{follower_name}"

        if cache_key not in self._cache:
            value = self._resolve(param_name, follower_name)
            self._cache[cache_key] = value

        return self._cache[cache_key]

    def get_yaw_smoothing_config(self, follower_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get merged YAW_SMOOTHING config for a follower.

        Merges: fallback ← General.YAW_SMOOTHING ← FollowerOverrides.{follower}.YAW_SMOOTHING.

        Args:
            follower_name: Follower name for per-follower overrides

        Returns:
            Merged YAW_SMOOTHING dict with all keys populated
        """
        cache_key = f"YAW_SMOOTHING:{follower_name}"

        if cache_key not in self._cache:
            # Start with fallback
            merged = dict(self._YAW_SMOOTHING_FALLBACK)

            # Layer General defaults
            general_yaw = self._general.get('YAW_SMOOTHING', {})
            if general_yaw:
                merged.update(general_yaw)

            # Layer per-follower override
            if follower_name:
                normalized_name = follower_name.upper()
                override = self._overrides.get(normalized_name, {})
                override_yaw = override.get('YAW_SMOOTHING', {})
                if override_yaw:
                    merged.update(override_yaw)

            self._cache[cache_key] = merged

        return self._cache[cache_key]

    def get_effective_config_summary(self, follower_name: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Get detailed parameter resolution for UI display.

        For each general parameter, returns the effective value, source, and
        override info — enabling the UI to show where each value comes from.

        Args:
            follower_name: Optional follower name for context-specific resolution

        Returns:
            Dict mapping param names to resolution info:
            {
                'CONTROL_UPDATE_RATE': {
                    'effective_value': 50.0,
                    'source': 'FollowerOverrides.MC_ATTITUDE_RATE',
                    'general_value': 20.0,
                    'override_value': 50.0,
                    'fallback_value': 20.0,
                    'is_overridden': True
                },
                ...
            }
        """
        result = {}
        normalized_name = follower_name.upper() if follower_name else None
        override = self._overrides.get(normalized_name, {}) if normalized_name else {}

        for param in GENERAL_PARAMS:
            general_value = self._general.get(param)
            override_value = override.get(param) if follower_name else None
            fallback_value = self._FALLBACKS.get(param)

            # Determine effective value and source
            if override_value is not None:
                effective_value = override_value
                source = f'FollowerOverrides.{normalized_name}'
            elif general_value is not None:
                effective_value = general_value
                source = 'General'
            else:
                effective_value = fallback_value
                source = 'Fallback'

            result[param] = {
                'effective_value': effective_value,
                'source': source,
                'general_value': general_value,
                'override_value': override_value,
                'fallback_value': fallback_value,
                'is_overridden': override_value is not None,
            }

        # Include YAW_SMOOTHING as a nested entry
        general_yaw = self._general.get('YAW_SMOOTHING')
        override_yaw = override.get('YAW_SMOOTHING') if follower_name else None
        merged_yaw = self.get_yaw_smoothing_config(follower_name)

        if override_yaw:
            yaw_source = f'FollowerOverrides.{normalized_name}'
        elif general_yaw:
            yaw_source = 'General'
        else:
            yaw_source = 'Fallback'

        result['YAW_SMOOTHING'] = {
            'effective_value': merged_yaw,
            'source': yaw_source,
            'general_value': general_yaw,
            'override_value': override_yaw,
            'fallback_value': self._YAW_SMOOTHING_FALLBACK,
            'is_overridden': override_yaw is not None,
        }

        return result

    def get_available_followers(self) -> List[str]:
        """Get list of followers with configured overrides."""
        return list(self._overrides.keys())

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback for config change notifications."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[], None]) -> None:
        """Unregister a callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of config changes."""
        for callback in self._callbacks:
            try:
                callback()
            except Exception as e:
                logger.error("Error in follower config callback: %s", e)

    def clear_cache(self) -> None:
        """Clear the config cache (call after config changes)."""
        with self._lock:
            self._cache.clear()
            self._notify_callbacks()

    def get_all_config_summary(self) -> Dict[str, Any]:
        """Get a summary of all configured params for debugging/API."""
        return {
            'general': dict(self._general),
            'follower_overrides': dict(self._overrides),
            'cache_size': len(self._cache),
            'initialized': self._initialized,
        }


# Module-level convenience functions
def get_follower_config_manager() -> FollowerConfigManager:
    """Get the FollowerConfigManager singleton instance."""
    return FollowerConfigManager.get_instance()


def get_follower_param(param_name: str, follower_name: Optional[str] = None) -> Any:
    """Convenience function to get a follower parameter value."""
    return get_follower_config_manager().get_param(param_name, follower_name)
