# src/classes/parameters.py
"""
Parameters Module - Central Configuration Management
=====================================================

This module provides the Parameters class for loading and accessing
configuration values from YAML files. It integrates with SafetyManager
for unified safety limit management and FollowerConfigManager for
centralized follower operational config.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi

Safety Limit Resolution (v5.0.0+ via SafetyManager):
    1. Safety.FollowerOverrides (per-follower limits)
    2. Safety.GlobalLimits (single source of truth)
    3. Hardcoded fallback (for safety)

Follower Config Resolution (v6.1.0+ via FollowerConfigManager):
    1. Follower.FollowerOverrides (per-follower operational params)
    2. Follower.General (single source of truth for shared params)
    3. Legacy per-follower section (deprecated, emits warning)
    4. Hardcoded fallback
"""

import yaml
import os
import logging
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Thread lock for config reload operations
_config_reload_lock = threading.Lock()

# Lazy imports to avoid circular dependencies
_safety_manager = None
_follower_config_manager = None

def _get_safety_manager():
    """Lazy load SafetyManager to avoid circular import."""
    global _safety_manager
    if _safety_manager is None:
        from classes.safety_manager import SafetyManager
        _safety_manager = SafetyManager.get_instance()
    return _safety_manager

def _get_follower_config_manager():
    """Lazy load FollowerConfigManager to avoid circular import."""
    global _follower_config_manager
    if _follower_config_manager is None:
        from classes.follower_config_manager import FollowerConfigManager
        _follower_config_manager = FollowerConfigManager.get_instance()
    return _follower_config_manager


class Parameters:
    """
    Central configuration class for the PixEagle project.
    Automatically loads all configuration parameters from the config.yaml file.
    Configurations are set as class variables, maintaining compatibility with existing code.

    Safety Limits Resolution (v5.0.0+):
        Uses SafetyManager for centralized limit resolution:
        1. Safety.FollowerOverrides (if follower_name provided)
        2. Safety.GlobalLimits (single source of truth)
        3. Hardcoded fallback (for safety)
    """

    # Raw config storage for SafetyManager initialization
    _raw_config: Dict[str, Any] = {}

    # Grouped sections that should NOT be flattened
    _GROUPED_SECTIONS = [
        'Safety',        # Unified safety config (v5.0.0+)
        'Follower',      # Unified follower config (v6.1.0+)
        # Per-follower sections (unique params only)
        'MC_VELOCITY_POSITION', 'MC_VELOCITY_DISTANCE', 'MC_VELOCITY_GROUND',
        'MC_VELOCITY_CHASE', 'MC_ATTITUDE_RATE',
        'GM_VELOCITY_VECTOR', 'GM_VELOCITY_CHASE',
        'FW_ATTITUDE_RATE',
        # Tracker sections
        'GimbalTracker',
        'ClassicTracker_Common',
        'CSRT_Tracker', 'KCF_Tracker', 'DLIB_Tracker', 'SmartTracker'
    ]

    # Axis name to limit name mapping for get_velocity_limit()
    _AXIS_TO_LIMIT = {
        'forward': 'MAX_VELOCITY_FORWARD',
        'x': 'MAX_VELOCITY_FORWARD',
        'vel_body_fwd': 'MAX_VELOCITY_FORWARD',
        'fwd': 'MAX_VELOCITY_FORWARD',
        'lateral': 'MAX_VELOCITY_LATERAL',
        'y': 'MAX_VELOCITY_LATERAL',
        'right': 'MAX_VELOCITY_LATERAL',
        'vel_body_right': 'MAX_VELOCITY_LATERAL',
        'vertical': 'MAX_VELOCITY_VERTICAL',
        'z': 'MAX_VELOCITY_VERTICAL',
        'down': 'MAX_VELOCITY_VERTICAL',
        'vel_body_down': 'MAX_VELOCITY_VERTICAL',
    }

    @classmethod
    def load_config(cls, config_file='configs/config.yaml'):
        """
        Class method to load configurations from the config.yaml file and set class variables.
        Also initializes SafetyManager with the loaded configuration.
        """
        # Fix: Specify UTF-8 encoding to handle special characters
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Store raw config for SafetyManager
        cls._raw_config = config

        # Iterate over all top-level keys (sections)
        for section, params in config.items():
            if params:  # Check if params is not None
                # Check if this section should be kept as a group
                if section in cls._GROUPED_SECTIONS:
                    # Keep as grouped section for followers, trackers, and safety limits
                    setattr(cls, section, params)
                elif isinstance(params, dict):
                    # Flatten other sections (legacy behavior)
                    for key, value in params.items():
                        # Construct the attribute name in uppercase to match existing usage
                        attr_name = key.upper()
                        # Set the attribute as a class variable
                        setattr(cls, attr_name, value)
                else:
                    # Simple values (not dict) - set directly
                    setattr(cls, section, params)

        # Validate safety-critical sections (non-blocking — logs warning on failure)
        try:
            from classes.config_validator import validate_safety_config
            if not validate_safety_config(config):
                logger.warning(
                    "Config validation found issues in safety-critical sections. "
                    "Review logged errors before flight."
                )
        except Exception as e:
            logger.debug("Config validator unavailable: %s", e)

        # Initialize SafetyManager with the loaded config
        try:
            safety_manager = _get_safety_manager()
            safety_manager.load_from_config(config)
            logger.info("SafetyManager initialized with configuration")
        except Exception as e:
            logger.warning(f"Could not initialize SafetyManager: {e}")

        # Initialize FollowerConfigManager with the loaded config
        try:
            fcm = _get_follower_config_manager()
            fcm.load_from_config(config)
            logger.info("FollowerConfigManager initialized with configuration")
        except Exception as e:
            logger.warning(f"Could not initialize FollowerConfigManager: {e}")

    @classmethod
    def get_section(cls, section_name: str) -> dict:
        """
        Get all parameters in a section as a dictionary.

        Args:
            section_name: Name of the section (e.g., 'SafetyLimits', 'MC_VELOCITY_CHASE')

        Returns:
            dict: The section parameters, or empty dict if not found
        """
        return getattr(cls, section_name, {})

    @classmethod
    def get_effective_limit(cls, limit_name: str, follower_name: Optional[str] = None) -> float:
        """
        Get the effective safety limit for a given parameter.

        Resolution order (v5.0.0+ via SafetyManager):
        1. Safety.FollowerOverrides (if follower_name provided)
        2. Safety.GlobalLimits (single source of truth)
        3. Hardcoded fallback (for safety)

        Args:
            limit_name: Name of the limit (e.g., 'MIN_ALTITUDE', 'MAX_VELOCITY_FORWARD')
            follower_name: Optional follower section name (e.g., 'MC_VELOCITY_CHASE')

        Returns:
            float: The effective limit value

        Example:
            >>> Parameters.get_effective_limit('MIN_ALTITUDE', 'MC_VELOCITY_CHASE')
            5.0  # Returns follower override from Safety.FollowerOverrides

            >>> Parameters.get_effective_limit('MIN_ALTITUDE')
            3.0  # Returns global limit from Safety.GlobalLimits
        """
        try:
            # Use SafetyManager for centralized resolution (single source of truth)
            safety_manager = _get_safety_manager()
            value = safety_manager.get_limit(limit_name, follower_name)
            if value is not None:
                return float(value)
        except Exception as e:
            logger.error(f"SafetyManager error for {limit_name}: {e}")

        # SafetyManager handles fallbacks internally, this should rarely execute
        logger.warning(f"SafetyManager returned None for {limit_name}, using 0.0")
        return 0.0

    @classmethod
    def get_velocity_limit(cls, axis: str, follower_name: Optional[str] = None) -> float:
        """
        Convenience method for velocity limits with axis mapping.

        Args:
            axis: Axis name - one of:
                  'forward', 'x', 'vel_body_fwd', 'fwd'
                  'lateral', 'y', 'right', 'vel_body_right'
                  'vertical', 'z', 'down', 'vel_body_down'
            follower_name: Optional follower section name

        Returns:
            float: The velocity limit for the specified axis

        Example:
            >>> Parameters.get_velocity_limit('forward', 'MC_VELOCITY_CHASE')
            15.0

            >>> Parameters.get_velocity_limit('vel_body_right')
            10.0
        """
        limit_name = cls._AXIS_TO_LIMIT.get(axis.lower(), 'MAX_VELOCITY_FORWARD')
        return cls.get_effective_limit(limit_name, follower_name)

    @classmethod
    def get_altitude_limits(cls, follower_name: Optional[str] = None) -> tuple:
        """
        Convenience method to get both altitude limits at once.

        Args:
            follower_name: Optional follower section name

        Returns:
            tuple: (min_altitude, max_altitude) in meters

        Example:
            >>> Parameters.get_altitude_limits('MC_VELOCITY_CHASE')
            (5.0, 50.0)
        """
        min_alt = cls.get_effective_limit('MIN_ALTITUDE', follower_name)
        max_alt = cls.get_effective_limit('MAX_ALTITUDE', follower_name)
        return (min_alt, max_alt)

    @classmethod
    def reload_config(cls, config_file: str = 'configs/config.yaml') -> bool:
        """
        Reload configuration from disk (thread-safe).

        This method reloads the configuration file and updates all class attributes.
        It also notifies SafetyManager to reload its configuration.

        Args:
            config_file: Path to the config file (default: configs/config.yaml)

        Returns:
            bool: True if reload was successful, False otherwise

        Note:
            This is intended for use by the restart mechanism to reload
            configuration changes without a full application restart.
            Thread-safe via _config_reload_lock.
        """
        with _config_reload_lock:
            try:
                logger.info(f"🔄 Reloading configuration from {config_file}")

                # Reload the config
                cls.load_config(config_file)

                # Notify SafetyManager to reload
                try:
                    safety_manager = _get_safety_manager()
                    if hasattr(safety_manager, 'load_from_config') and cls._raw_config:
                        safety_manager.load_from_config(cls._raw_config)
                        logger.info("✅ SafetyManager reloaded with new configuration")
                except Exception as e:
                    # Critical failure - SafetyManager must stay in sync
                    logger.error(f"❌ Failed to reload SafetyManager: {e}")
                    # Continue - config was loaded, safety manager will use stale data
                    # but this is better than crashing

                # Notify FollowerConfigManager to reload
                try:
                    fcm = _get_follower_config_manager()
                    if hasattr(fcm, 'load_from_config') and cls._raw_config:
                        fcm.load_from_config(cls._raw_config)
                        fcm.clear_cache()
                        logger.info("✅ FollowerConfigManager reloaded with new configuration")
                except Exception as e:
                    logger.error(f"❌ Failed to reload FollowerConfigManager: {e}")

                logger.info("✅ Configuration reloaded successfully")
                return True

            except Exception as e:
                logger.error(f"❌ Failed to reload configuration: {e}")
                return False

    @classmethod
    def validate_config_structure(cls) -> bool:
        """
        Validate configuration structure for v5.0.0+ compliance.

        Checks for deprecated patterns and logs warnings/errors with migration hints.

        Returns:
            bool: True if config is valid, False if deprecated patterns found
        """
        issues_found = False

        # Deprecated SAFETY limit fields that should no longer exist in follower sections
        # Note: MAX_VELOCITY in follower sections is often an operational parameter (pursuit speed),
        # not a safety limit, so we only check for altitude-related safety limits
        DEPRECATED_FOLLOWER_FIELDS = ['MIN_ALTITUDE', 'MAX_ALTITUDE']

        FOLLOWER_SECTIONS = [
            'MC_VELOCITY_CHASE', 'MC_VELOCITY_POSITION', 'MC_VELOCITY_DISTANCE',
            'MC_VELOCITY_GROUND', 'MC_ATTITUDE_RATE',
            'GM_VELOCITY_CHASE', 'GM_VELOCITY_VECTOR', 'FW_ATTITUDE_RATE'
        ]

        # Check for deprecated top-level sections
        deprecated_sections = ['SafetyLimits', 'VehicleProfiles', 'Camera']
        for section in deprecated_sections:
            if hasattr(cls, section) and getattr(cls, section):
                logger.error(
                    f"❌ DEPRECATED: '{section}' section found in config. "
                    f"This section was removed in v5.0.0. Please migrate your configuration."
                )
                issues_found = True

        # Check for deprecated limit fields in follower sections
        for section_name in FOLLOWER_SECTIONS:
            section_data = getattr(cls, section_name, None)
            if section_data and isinstance(section_data, dict):
                for field in DEPRECATED_FOLLOWER_FIELDS:
                    if field in section_data:
                        logger.warning(
                            f"⚠️  DEPRECATED: '{section_name}.{field}' should be in "
                            f"'Safety.FollowerOverrides.{section_name}.{field}' instead. "
                            f"Per-follower limits in section configs are deprecated in v5.0.0."
                        )
                        issues_found = True

        # Verify Safety section has correct structure
        safety = getattr(cls, 'Safety', None)
        if safety:
            if 'GlobalLimits' not in safety:
                logger.error(
                    "❌ MISSING: 'Safety.GlobalLimits' section not found. "
                    "This is required in v5.0.0+ for safety limit management."
                )
                issues_found = True
        else:
            logger.error(
                "❌ MISSING: 'Safety' section not found in configuration. "
                "This section is required for v5.0.0+ safety management."
            )
            issues_found = True

        if not issues_found:
            logger.info("✅ Configuration structure validated (v5.0.0+ compliant)")

        return not issues_found


# Load the configurations upon module import
Parameters.load_config()

# Validate configuration structure on startup
Parameters.validate_config_structure()