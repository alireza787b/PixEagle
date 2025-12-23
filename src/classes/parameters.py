# src/classes/parameters.py

import yaml
import os
from typing import Optional

class Parameters:
    """
    Central configuration class for the PixEagle project.
    Automatically loads all configuration parameters from the config.yaml file.
    Configurations are set as class variables, maintaining compatibility with existing code.

    Safety Limits Resolution:
        The get_effective_limit() method resolves limits in this priority order:
        1. Follower-specific override (if follower_name provided and limit exists in follower section)
        2. Global SafetyLimits section value
        3. Hardcoded fallback default (for safety)
    """

    # Grouped sections that should NOT be flattened
    _GROUPED_SECTIONS = [
        'SafetyLimits',  # Global safety limits
        # Follower sections (new naming convention: {vehicle}_{control}_{behavior})
        'MC_VELOCITY_POSITION', 'MC_VELOCITY_DISTANCE', 'MC_VELOCITY_GROUND',
        'MC_VELOCITY_CHASE', 'MC_VELOCITY', 'MC_ATTITUDE_RATE',
        'GM_VELOCITY_VECTOR', 'GM_VELOCITY_UNIFIED',
        'FW_ATTITUDE_RATE',
        # Tracker sections
        'GimbalTracker', 'GimbalTrackerSettings',
        'CSRT_Tracker', 'KCF_Tracker', 'DLIB_Tracker', 'SmartTracker'
    ]

    # Hardcoded fallback defaults for safety (used if config is missing)
    _SAFETY_FALLBACKS = {
        'MIN_ALTITUDE': 3.0,
        'MAX_ALTITUDE': 120.0,
        'MAX_VELOCITY_FORWARD': 15.0,
        'MAX_VELOCITY_LATERAL': 10.0,
        'MAX_VELOCITY_VERTICAL': 5.0,
        'MAX_YAW_RATE': 45.0,
        'ALTITUDE_WARNING_BUFFER': 2.0,
        'MAX_SAFETY_VIOLATIONS': 5,
        'EMERGENCY_STOP_ENABLED': True,
        'RTL_ON_VIOLATION': True,
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
        """
        # Fix: Specify UTF-8 encoding to handle special characters
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

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

        Resolution order:
        1. Follower-specific override (if follower_name provided and limit exists)
        2. Global SafetyLimits value
        3. Hardcoded fallback (for safety)

        Args:
            limit_name: Name of the limit (e.g., 'MIN_ALTITUDE', 'MAX_VELOCITY_FORWARD')
            follower_name: Optional follower section name (e.g., 'MC_VELOCITY_CHASE')

        Returns:
            float: The effective limit value

        Example:
            >>> Parameters.get_effective_limit('MIN_ALTITUDE', 'MC_VELOCITY_CHASE')
            5.0  # Returns follower override if exists, else global

            >>> Parameters.get_effective_limit('MIN_ALTITUDE')
            3.0  # Returns global SafetyLimits value
        """
        # Step 1: Check follower-specific override
        if follower_name:
            follower_config = getattr(cls, follower_name, {})
            if isinstance(follower_config, dict) and limit_name in follower_config:
                return float(follower_config[limit_name])

        # Step 2: Check global SafetyLimits
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

# Load the configurations upon module import
Parameters.load_config()