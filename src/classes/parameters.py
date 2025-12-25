# src/classes/parameters.py
"""
Parameters Module - Central Configuration Management
=====================================================

This module provides the Parameters class for loading and accessing
configuration values from YAML files. It integrates with SafetyManager
for unified safety limit management.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi

Safety Limit Resolution (via SafetyManager):
    1. Follower-specific override
    2. Vehicle profile (MULTICOPTER, FIXED_WING, GIMBAL)
    3. Global limits
    4. Hardcoded fallback
"""

import yaml
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependency
_safety_manager = None

def _get_safety_manager():
    """Lazy load SafetyManager to avoid circular import."""
    global _safety_manager
    if _safety_manager is None:
        from classes.safety_manager import SafetyManager
        _safety_manager = SafetyManager.get_instance()
    return _safety_manager


class Parameters:
    """
    Central configuration class for the PixEagle project.
    Automatically loads all configuration parameters from the config.yaml file.
    Configurations are set as class variables, maintaining compatibility with existing code.

    Safety Limits Resolution (v3.5.0+):
        Uses SafetyManager for centralized limit resolution:
        1. FollowerOverrides (if follower_name provided)
        2. VehicleProfiles (based on follower's vehicle type)
        3. GlobalLimits
        4. Hardcoded fallback (for safety)
    """

    # Raw config storage for SafetyManager initialization
    _raw_config: Dict[str, Any] = {}

    # Grouped sections that should NOT be flattened
    _GROUPED_SECTIONS = [
        'Safety',        # New unified safety config (v3.5.0+)
        'SafetyLimits',  # Legacy safety limits (deprecated)
        'Followers',     # New unified follower configs (v3.5.0+)
        # Follower sections (legacy - maintained for compatibility)
        'MC_VELOCITY_POSITION', 'MC_VELOCITY_DISTANCE', 'MC_VELOCITY_GROUND',
        'MC_VELOCITY_CHASE', 'MC_VELOCITY', 'MC_ATTITUDE_RATE',
        'GM_VELOCITY_VECTOR', 'GM_PID_PURSUIT',
        'FW_ATTITUDE_RATE',
        # Tracker sections
        'GimbalTracker', 'GimbalTrackerSettings',
        'CSRT_Tracker', 'KCF_Tracker', 'DLIB_Tracker', 'SmartTracker'
    ]

    # Hardcoded fallback defaults for safety (used if config is missing)
    # NOTE: These MUST match SafetyManager._FALLBACKS for consistency
    _SAFETY_FALLBACKS = {
        'MIN_ALTITUDE': 3.0,
        'MAX_ALTITUDE': 120.0,
        'MAX_VELOCITY': 15.0,           # Overall magnitude limit (matches SafetyManager)
        'MAX_VELOCITY_FORWARD': 8.0,    # Conservative (matches SafetyManager)
        'MAX_VELOCITY_LATERAL': 5.0,    # Conservative (matches SafetyManager)
        'MAX_VELOCITY_VERTICAL': 3.0,   # Conservative (matches SafetyManager)
        'MAX_YAW_RATE': 45.0,
        'MAX_PITCH_RATE': 45.0,         # Added for completeness
        'MAX_ROLL_RATE': 45.0,          # Added for completeness
        'ALTITUDE_WARNING_BUFFER': 2.0,
        'ALTITUDE_SAFETY_ENABLED': True,  # Added for safety
        'MAX_SAFETY_VIOLATIONS': 5,
        'EMERGENCY_STOP_ENABLED': True,
        'RTL_ON_VIOLATION': True,
        'TARGET_LOSS_ACTION': 'hover',  # Default action on target loss (matches SafetyManager)
    }

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

        # Initialize SafetyManager with the loaded config
        try:
            safety_manager = _get_safety_manager()
            safety_manager.load_from_config(config)
            logger.info("SafetyManager initialized with configuration")
        except Exception as e:
            logger.warning(f"Could not initialize SafetyManager: {e}")

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

        Resolution order (via SafetyManager):
        1. Follower-specific override (Safety.FollowerOverrides)
        2. Vehicle profile (Safety.VehicleProfiles based on follower type)
        3. Global limits (Safety.GlobalLimits)
        4. Legacy SafetyLimits (for backward compatibility)
        5. Hardcoded fallback (for safety)

        Args:
            limit_name: Name of the limit (e.g., 'MIN_ALTITUDE', 'MAX_VELOCITY_FORWARD')
            follower_name: Optional follower section name (e.g., 'MC_VELOCITY_CHASE')

        Returns:
            float: The effective limit value

        Example:
            >>> Parameters.get_effective_limit('MIN_ALTITUDE', 'MC_VELOCITY_CHASE')
            5.0  # Returns follower override if exists, else vehicle profile

            >>> Parameters.get_effective_limit('MIN_ALTITUDE')
            3.0  # Returns global limit
        """
        try:
            # Use SafetyManager for centralized resolution
            safety_manager = _get_safety_manager()
            value = safety_manager.get_limit(limit_name, follower_name)
            if value is not None:
                return float(value)
        except Exception as e:
            logger.debug(f"SafetyManager fallback for {limit_name}: {e}")

        # Fallback to legacy resolution if SafetyManager fails
        # Step 1: Check follower-specific override (legacy)
        if follower_name:
            follower_config = getattr(cls, follower_name, {})
            if isinstance(follower_config, dict) and limit_name in follower_config:
                return float(follower_config[limit_name])

        # Step 2: Check global SafetyLimits (legacy)
        safety_limits = getattr(cls, 'SafetyLimits', {})
        if isinstance(safety_limits, dict) and limit_name in safety_limits:
            return float(safety_limits[limit_name])

        # Step 3: Return hardcoded fallback
        return float(cls._SAFETY_FALLBACKS.get(limit_name, 0.0))

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
        Reload configuration from disk.

        This method reloads the configuration file and updates all class attributes.
        It also notifies SafetyManager to reload its configuration.

        Args:
            config_file: Path to the config file (default: configs/config.yaml)

        Returns:
            bool: True if reload was successful, False otherwise

        Note:
            This is intended for use by the restart mechanism to reload
            configuration changes without a full application restart.
        """
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
                logger.warning(f"Could not reload SafetyManager: {e}")

            logger.info("✅ Configuration reloaded successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to reload configuration: {e}")
            return False

# Load the configurations upon module import
Parameters.load_config()