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
- Cached lookups for O(1) access after first resolution

Resolution Order:
1. Follower-specific override (Follower.FollowerOverrides.{follower})
2. General defaults (Follower.General — single source of truth)

Missing, undeclared, or malformed operational values fail configuration
publication. Runtime code never substitutes hidden literals.
"""

import copy
import logging
import threading
from typing import Dict, Optional, Callable, List, Any

from classes.runtime_config_generation import manager_runtime_config_reader

logger = logging.getLogger(__name__)


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
    _lock = threading.RLock()

    def __init__(self):
        """Initialize FollowerConfigManager. Use get_instance() instead."""
        self._general: Dict[str, Any] = {}
        self._overrides: Dict[str, Dict[str, Any]] = {}
        self._general_parameters: tuple[str, ...] = ()
        self._follower_catalog: tuple[str, ...] = ()
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
        prepared_state = self._prepare_runtime_state(config)
        self._publish_runtime_state(prepared_state)

    def _prepare_runtime_state(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and build replacement state before publication."""
        if not isinstance(config, dict):
            raise TypeError("Follower runtime configuration root must be an object")
        follower_section = config.get('Follower')
        if not isinstance(follower_section, dict):
            raise ValueError("Follower configuration section is required")
        raw_general = follower_section.get('General')
        raw_overrides = follower_section.get('FollowerOverrides')
        if not isinstance(raw_general, dict):
            raise ValueError("Follower.General must be a complete object")
        if not isinstance(raw_overrides, dict):
            raise ValueError("Follower.FollowerOverrides must be an object")

        from classes.config_service import ConfigService

        config_service = ConfigService.get_instance()
        general_schema = config_service.get_parameter_schema('Follower', 'General')
        overrides_schema = config_service.get_parameter_schema(
            'Follower',
            'FollowerOverrides',
        )
        if not isinstance(general_schema, dict) or not isinstance(
            overrides_schema,
            dict,
        ):
            raise RuntimeError(
                "Follower operational schema contract is unavailable"
            )

        general_result = config_service.validate_value(
            'Follower',
            'General',
            raw_general,
        )
        overrides_result = config_service.validate_value(
            'Follower',
            'FollowerOverrides',
            raw_overrides,
        )
        validation_errors = general_result.errors + overrides_result.errors
        if validation_errors:
            raise ValueError(
                "Follower operational configuration failed validation: "
                + "; ".join(validation_errors)
            )

        general_properties = general_schema.get('properties')
        follower_properties = overrides_schema.get('properties')
        if not isinstance(general_properties, dict) or not general_properties:
            raise RuntimeError("Follower.General schema has no property contract")
        if not isinstance(follower_properties, dict) or not follower_properties:
            raise RuntimeError(
                "Follower.FollowerOverrides schema has no profile catalog"
            )

        general = copy.deepcopy(raw_general)
        overrides = copy.deepcopy(raw_overrides)
        general_parameters = tuple(
            name for name in general_properties if name != 'YAW_SMOOTHING'
        )
        follower_catalog = tuple(follower_properties)
        logger.info(
            "FollowerConfigManager loaded validated contract "
            "(General: %d params, overrides: %d/%d profiles)",
            len(general),
            len(overrides),
            len(follower_catalog),
        )

        return {
            'general': general,
            'overrides': overrides,
            'general_parameters': general_parameters,
            'follower_catalog': follower_catalog,
            'cache': {},
            'initialized': True,
        }

    def _publish_runtime_state(self, state: Dict[str, Any]) -> None:
        """Install prepared state using only bounded in-memory assignments."""
        with self._lock:
            self._general = state['general']
            self._overrides = state['overrides']
            self._general_parameters = state['general_parameters']
            self._follower_catalog = state['follower_catalog']
            self._cache = state['cache']
            self._initialized = state['initialized']

    def _capture_runtime_state(self) -> Dict[str, Any]:
        """Capture references needed for a bounded publication rollback."""
        with self._lock:
            return {
                'general': self._general,
                'overrides': self._overrides,
                'general_parameters': self._general_parameters,
                'follower_catalog': self._follower_catalog,
                'cache': self._cache,
                'initialized': self._initialized,
            }

    def _restore_runtime_state(self, state: Dict[str, Any]) -> None:
        """Restore a captured state without reparsing or reloading config."""
        with self._lock:
            self._general = state['general']
            self._overrides = state['overrides']
            self._general_parameters = state['general_parameters']
            self._follower_catalog = state['follower_catalog']
            self._cache = state['cache']
            self._initialized = state['initialized']

    def _resolve(self, param_name: str, follower_name: Optional[str] = None) -> Any:
        """
        Resolve a parameter through the hierarchy.

        Order:
        1. Follower.FollowerOverrides.{follower}.{param}
        2. Follower.General.{param}

        Note: Follower names are normalized to uppercase for case-insensitive lookup.
        """
        if not self._initialized:
            raise RuntimeError("FollowerConfigManager is not initialized")

        # 1. Check follower-specific override
        if follower_name:
            normalized_name = follower_name.upper()
            if normalized_name not in self._follower_catalog:
                raise KeyError(
                    f"Unknown follower profile {follower_name!r}"
                )
            override = self._overrides.get(normalized_name, {})
            if param_name in override:
                return override[param_name]

        # 2. Check General defaults
        if param_name in self._general:
            return self._general[param_name]
        raise KeyError(
            f"Follower operational parameter {param_name!r} is not declared"
        )

    @manager_runtime_config_reader
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

    @manager_runtime_config_reader
    def get_yaw_smoothing_config(self, follower_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get merged YAW_SMOOTHING config for a follower.

        Merges General.YAW_SMOOTHING with an optional profile override.

        Args:
            follower_name: Follower name for per-follower overrides

        Returns:
            Complete merged YAW_SMOOTHING dict
        """
        cache_key = f"YAW_SMOOTHING:{follower_name}"

        if cache_key not in self._cache:
            if not self._initialized:
                raise RuntimeError("FollowerConfigManager is not initialized")
            general_yaw = self._general.get('YAW_SMOOTHING')
            if not isinstance(general_yaw, dict):
                raise RuntimeError(
                    "Validated Follower.General.YAW_SMOOTHING is unavailable"
                )
            merged = copy.deepcopy(general_yaw)

            # Layer per-follower override
            if follower_name:
                normalized_name = follower_name.upper()
                if normalized_name not in self._follower_catalog:
                    raise KeyError(
                        f"Unknown follower profile {follower_name!r}"
                    )
                override = self._overrides.get(normalized_name, {})
                override_yaw = override.get('YAW_SMOOTHING', {})
                if override_yaw:
                    merged.update(override_yaw)

            self._cache[cache_key] = merged

        return self._cache[cache_key]

    @manager_runtime_config_reader
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
                    'fallback_value': None,
                    'is_overridden': True
                },
                ...
            }
        """
        result = {}
        normalized_name = follower_name.upper() if follower_name else None
        override = self._overrides.get(normalized_name, {}) if normalized_name else {}

        if not self._initialized:
            raise RuntimeError("FollowerConfigManager is not initialized")
        if normalized_name and normalized_name not in self._follower_catalog:
            raise KeyError(f"Unknown follower profile {follower_name!r}")

        for param in self._general_parameters:
            general_value = self._general.get(param)
            override_value = override.get(param) if follower_name else None

            # Determine effective value and source
            if override_value is not None:
                effective_value = override_value
                source = f'FollowerOverrides.{normalized_name}'
            elif general_value is not None:
                effective_value = general_value
                source = 'General'
            else:
                raise RuntimeError(
                    f"Validated Follower.General.{param} is unavailable"
                )

            result[param] = {
                'effective_value': effective_value,
                'source': source,
                'general_value': general_value,
                'override_value': override_value,
                'fallback_value': None,
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
            raise RuntimeError(
                "Validated Follower.General.YAW_SMOOTHING is unavailable"
            )

        result['YAW_SMOOTHING'] = {
            'effective_value': merged_yaw,
            'source': yaw_source,
            'general_value': general_yaw,
            'override_value': override_yaw,
            'fallback_value': None,
            'is_overridden': override_yaw is not None,
        }

        return result

    @manager_runtime_config_reader
    def get_available_followers(self) -> List[str]:
        """Get the canonical follower profile catalog from the schema."""
        if not self._initialized:
            raise RuntimeError("FollowerConfigManager is not initialized")
        return list(self._follower_catalog)

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback for config change notifications."""
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[], None]) -> None:
        """Unregister a callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of config changes."""
        with self._lock:
            callbacks = tuple(self._callbacks)
        for callback in callbacks:
            try:
                callback()
            except Exception as e:
                logger.error("Error in follower config callback: %s", e)

    def clear_cache(self) -> None:
        """Clear the config cache (call after config changes)."""
        with self._lock:
            self._cache = {}
        self._notify_callbacks()

    @manager_runtime_config_reader
    def get_all_config_summary(self) -> Dict[str, Any]:
        """Get a summary of all configured params for debugging/API."""
        return {
            'general': copy.deepcopy(self._general),
            'follower_overrides': copy.deepcopy(self._overrides),
            'available_followers': list(self._follower_catalog),
            'cache_size': len(self._cache),
            'initialized': self._initialized,
        }

    @manager_runtime_config_reader
    def is_initialized(self) -> bool:
        """Return whether a complete follower configuration has been loaded."""
        return self._initialized


# Module-level convenience functions
def get_follower_config_manager() -> FollowerConfigManager:
    """Get the FollowerConfigManager singleton instance."""
    return FollowerConfigManager.get_instance()


def get_follower_param(param_name: str, follower_name: Optional[str] = None) -> Any:
    """Convenience function to get a follower parameter value."""
    return get_follower_config_manager().get_param(param_name, follower_name)
