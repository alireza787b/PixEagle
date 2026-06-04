# src/classes/setpoint_handler.py
import logging
import yaml
import os
import math
from datetime import datetime
from typing import Dict, List, Any, Optional

from classes.command_safety import (
    CommandValidationError,
    validate_and_clamp_command_value,
)
from classes.command_intent import CommandIntent
from classes.safety_types import FIELD_LIMIT_MAPPING

# Set up logging
logger = logging.getLogger(__name__)

class SetpointHandler:
    """
    Schema-aware setpoint handler that loads follower profiles and field definitions
    from the unified command schema YAML file. Provides type safety, validation,
    and extensible configuration for all follower modes.
    """
    
    # Class-level schema cache to avoid repeated file loading
    _schema_cache: Optional[Dict[str, Any]] = None
    _schema_file_path = "configs/follower_commands.yaml"
    
    def __init__(self, profile_name: str):
        """
        Initializes the SetpointHandler with the specified follower profile.
        
        Args:
            profile_name (str): The name of the follower profile (e.g., "Ground View", 
                              "Constant Distance", "Constant Position", "Chase Follower").
        
        Raises:
            ValueError: If the profile is not defined in the schema.
            FileNotFoundError: If the schema file cannot be found.
        """
        # Load schema if not already cached
        if SetpointHandler._schema_cache is None:
            SetpointHandler._load_schema()
            
        self.profile_name = self.normalize_profile_name(profile_name)
        self.fields: Dict[str, float] = {}
        self.profile_config: Dict[str, Any] = {}
        self._last_command_intent: Optional[CommandIntent] = None
        
        # Initialize the profile and fields
        self._initialize_from_schema()
        logger.info(f"SetpointHandler initialized with profile: {self.profile_name}")
    
    @classmethod
    def _load_schema(cls):
        """
        Loads the follower command schema from YAML file.
        
        Raises:
            FileNotFoundError: If the schema file cannot be found.
            yaml.YAMLError: If the schema file is malformed.
        """
        try:
            if not os.path.exists(cls._schema_file_path):
                raise FileNotFoundError(f"Schema file not found: {cls._schema_file_path}")
                
            with open(cls._schema_file_path, 'r') as f:
                cls._schema_cache = yaml.safe_load(f)
                
            logger.info(f"Loaded follower command schema from {cls._schema_file_path}")
            logger.debug(f"Schema version: {cls._schema_cache.get('schema_version', 'unknown')}")
            
        except yaml.YAMLError as e:
            logger.error(f"Error parsing schema YAML: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading schema: {e}")
            raise
    
    @classmethod
    def get_available_profiles(cls) -> List[str]:
        """
        Returns a list of all available follower profile names.
        
        Returns:
            List[str]: List of profile names.
        """
        if cls._schema_cache is None:
            cls._load_schema()
        return list(cls._schema_cache['follower_profiles'].keys())
    
    @classmethod
    def get_profile_info(cls, profile_name: str) -> Dict[str, Any]:
        """
        Returns detailed information about a specific profile.
        
        Args:
            profile_name (str): The profile name to query.
            
        Returns:
            Dict[str, Any]: Profile configuration including display name, control type, etc.
        """
        if cls._schema_cache is None:
            cls._load_schema()
        
        normalized_name = cls.normalize_profile_name(profile_name)
        profiles = cls._schema_cache['follower_profiles']
        
        # Find profile by normalized name or original key
        for key, config in profiles.items():
            if key == normalized_name or cls.normalize_profile_name(config.get('display_name', '')) == normalized_name:
                return config
        
        raise ValueError(f"Profile '{profile_name}' not found")
    
    @staticmethod
    def normalize_profile_name(profile_name: str) -> str:
        """
        Normalizes the profile name to match schema keys.
        
        Args:
            profile_name (str): The raw profile name input.
            
        Returns:
            str: The normalized profile name.
        """
        # Convert from display name format to schema key format
        return profile_name.lower().replace(" ", "_")
    
    def _initialize_from_schema(self):
        """
        Initializes the profile configuration and fields from the schema.
        
        Raises:
            ValueError: If the profile is not found in the schema.
        """
        schema = SetpointHandler._schema_cache
        profiles = schema['follower_profiles']
        
        # Find the profile configuration
        if self.profile_name not in profiles:
            available = list(profiles.keys())
            raise ValueError(f"Profile '{self.profile_name}' not found. Available profiles: {available}")
        
        self.profile_config = profiles[self.profile_name]
        
        # Get required and optional fields
        required_fields = self.profile_config.get('required_fields', [])
        optional_fields = self.profile_config.get('optional_fields', [])
        all_fields = required_fields + optional_fields
        
        # Initialize fields with default values from schema
        field_definitions = schema['command_fields']
        for field_name in all_fields:
            if field_name in field_definitions:
                default_value = field_definitions[field_name].get('default', 0.0)
                self.fields[field_name] = float(default_value)
            else:
                logger.warning(f"Field '{field_name}' not found in schema, using default 0.0")
                self.fields[field_name] = 0.0
        
        logger.debug(f"Initialized fields for profile '{self.profile_name}': {self.fields}")
    
    def set_field(self, field_name: str, value: float):
        """
        Sets the value of a specific field with validation and clamping if enabled.
        If the value is out of range and 'clamp' is true in the config, clamps to min/max.
        If 'clamp' is false, raises ValueError.
        """
        # Check if field is valid for this profile
        if field_name not in self.fields:
            valid_fields = list(self.fields.keys())
            raise ValueError(f"Field '{field_name}' is not valid for profile '{self.profile_name}'. "
                           f"Valid fields: {valid_fields}")
        # Validate value type
        try:
            numeric_value = float(value)
        except (ValueError, TypeError):
            raise ValueError(f"The value for {field_name} must be a numeric type (int or float), got {type(value)}")
        if not math.isfinite(numeric_value):
            raise ValueError(f"The value for {field_name} must be finite, got {value!r}")
        # Validate and clamp value if needed
        clamped_value = self._validate_field_limits(field_name, numeric_value)
        self.fields[field_name] = clamped_value
        logger.debug(f"Setpoint updated: {field_name} = {clamped_value}")

    def set_fields(
        self,
        field_values: Dict[str, float],
        *,
        source: str = "unknown",
        reason: Optional[str] = None,
        require_all: bool = True,
    ) -> CommandIntent:
        """
        Atomically validates and applies a full command field snapshot.

        Validation is performed against a staged copy first. The live setpoint
        state is changed only after every provided field is valid, finite, and
        inside the active safety/schema limits. When ``require_all`` is true,
        callers must provide every field in the active profile so stale values
        cannot be carried over implicitly.
        """
        if not isinstance(field_values, dict):
            raise ValueError(f"field_values must be a dict, got {type(field_values)}")

        expected_fields = set(self.fields.keys())
        provided_fields = set(field_values.keys())
        invalid_fields = provided_fields - expected_fields
        if invalid_fields:
            raise ValueError(
                f"Fields {sorted(invalid_fields)} are not valid for profile "
                f"'{self.profile_name}'. Valid fields: {sorted(expected_fields)}"
            )

        missing_fields = expected_fields - provided_fields
        if require_all and missing_fields:
            raise ValueError(
                f"Atomic command for profile '{self.profile_name}' missing fields: "
                f"{sorted(missing_fields)}"
            )

        staged_fields = self.fields.copy()
        for field_name, raw_value in field_values.items():
            staged_fields[field_name] = self._validate_single_field(field_name, raw_value)

        # Commit only after all fields validate successfully.
        self.fields = staged_fields
        intent = CommandIntent(
            profile_name=self.profile_name,
            control_type=self.get_control_type(),
            fields=self.fields.copy(),
            source=source,
            reason=reason,
        )
        self._last_command_intent = intent
        logger.debug(
            "Atomic command intent applied: profile=%s source=%s reason=%s fields=%s",
            self.profile_name,
            source,
            reason,
            intent.fields,
        )
        return intent

    def _validate_single_field(self, field_name: str, value: float) -> float:
        """Validate one field without mutating handler state."""
        if field_name not in self.fields:
            valid_fields = list(self.fields.keys())
            raise ValueError(
                f"Field '{field_name}' is not valid for profile '{self.profile_name}'. "
                f"Valid fields: {valid_fields}"
            )
        try:
            numeric_value = float(value)
        except (ValueError, TypeError):
            raise ValueError(
                f"The value for {field_name} must be a numeric type (int or float), "
                f"got {type(value)}"
            )
        if not math.isfinite(numeric_value):
            raise ValueError(f"The value for {field_name} must be finite, got {value!r}")
        return self._validate_field_limits(field_name, numeric_value)

    def get_last_command_intent(self) -> Optional[CommandIntent]:
        """Return the most recently accepted atomic command intent, if any."""
        return self._last_command_intent
    
    # Single source of truth for runtime safety-limit field mapping.
    _FIELD_TO_LIMIT_NAME = FIELD_LIMIT_MAPPING

    def _validate_field_limits(self, field_name: str, value: float) -> float:
        """
        Validates and clamps the field value according to limits from config.

        Limit source priority:
        1. Config-based limits from Parameters.SafetyLimits (for velocity/yaw fields)
        2. Schema-based limits (for special fields like thrust)

        If clamp is enabled (default), clamps to min/max and logs a warning.
        If clamp is disabled, raises ValueError if out of bounds.
        Returns the (possibly clamped) value.
        """
        schema = SetpointHandler._schema_cache
        field_definitions = schema.get('command_fields', {})

        if field_name not in field_definitions:
            return value

        field_def = field_definitions[field_name]
        clamp = field_def.get('clamp', True)  # Default to True if not specified

        # Get limits - prefer config-based limits, fallback to schema limits
        min_val = None
        max_val = None

        if field_name in self._FIELD_TO_LIMIT_NAME:
            try:
                return validate_and_clamp_command_value(
                    field_name,
                    value,
                    follower_name=self.profile_name,
                    command_type=self.profile_name,
                    clamp=clamp,
                )
            except CommandValidationError as exc:
                raise ValueError(str(exc)) from exc
        else:
            # Fallback to schema limits (for fields like thrust)
            limits = field_def.get('limits', {})
            min_val = limits.get('min', None)
            max_val = limits.get('max', None)

        # Apply clamping/validation logic
        if min_val is not None and value < min_val:
            if clamp:
                logger.warning(f"Value {value} for field '{field_name}' below min {min_val}; clamped to {min_val}.")
                value = min_val
            else:
                raise ValueError(f"Value {value} for field '{field_name}' is below minimum limit {min_val}")
        if max_val is not None and value > max_val:
            if clamp:
                logger.warning(f"Value {value} for field '{field_name}' above max {max_val}; clamped to {max_val}.")
                value = max_val
            else:
                raise ValueError(f"Value {value} for field '{field_name}' is above maximum limit {max_val}")

        return value
    
    def get_fields(self) -> Dict[str, float]:
        """
        Returns the current fields of the setpoint.

        Returns:
            Dict[str, float]: The current fields of the setpoint.
        """
        logger.debug(f"Retrieving setpoint fields: {self.fields}")
        return self.fields.copy()

    def get_fields_with_status(self) -> Dict[str, Any]:
        """
        Returns the current fields with circuit breaker status information.

        Returns:
            Dict[str, Any]: Setpoint fields plus circuit breaker metadata
        """
        # Import circuit breaker to check status
        try:
            from classes.circuit_breaker import FollowerCircuitBreaker
            circuit_breaker_active = FollowerCircuitBreaker.is_active()
            cb_stats = FollowerCircuitBreaker.get_statistics()
        except ImportError:
            circuit_breaker_active = True  # FAIL SAFE default
            cb_stats = {"error": "Circuit breaker unavailable"}

        result = {
            # Setpoint data
            "setpoints": self.fields.copy(),
            "profile": self.profile_name,

            # Circuit breaker status
            "circuit_breaker": {
                "active": circuit_breaker_active,
                "status": "SAFE_MODE" if circuit_breaker_active else "LIVE_MODE",
                "commands_allowed_by_circuit_breaker": not circuit_breaker_active,
                "commands_sent_to_px4": False,
                "commands_logged_only": circuit_breaker_active
            },

            # Metadata
            "timestamp": datetime.now().isoformat(),
            "control_type": self.get_control_type()
        }

        # Add circuit breaker statistics if active
        if circuit_breaker_active:
            result["circuit_breaker"]["statistics"] = cb_stats

        logger.debug(f"Setpoints with CB status: CB={circuit_breaker_active}, Fields={len(self.fields)}")
        return result
    
    def get_control_type(self) -> str:
        """
        Returns the control type for this profile.
        
        Returns:
            str: The control type ('velocity_body' or 'attitude_rate').
        """
        return self.profile_config.get('control_type', 'velocity_body')
    
    def get_display_name(self) -> str:
        """
        Returns the human-readable display name for this profile.
        
        Returns:
            str: The display name.
        """
        return self.profile_config.get('display_name', self.profile_name.replace('_', ' ').title())
    
    def get_description(self) -> str:
        """
        Returns the description for this profile.
        
        Returns:
            str: The profile description.
        """
        return self.profile_config.get('description', 'No description available')
    
    def report(self) -> str:
        """
        Generates a comprehensive report of the current setpoint values and profile info.
        
        Returns:
            str: A human-readable report of the setpoint values and configuration.
        """
        report = f"Setpoint Profile: {self.get_display_name()}\n"
        report += f"Control Type: {self.get_control_type()}\n"
        report += f"Description: {self.get_description()}\n"
        report += "Current Field Values:\n"
        
        for field, value in self.fields.items():
            report += f"  {field}: {value}\n"
        
        logger.info(f"Generated setpoint report: {report}")
        return report
    
    def reset_setpoints(self):
        """
        Resets all setpoints to their schema-defined default values.
        """
        schema = SetpointHandler._schema_cache
        field_definitions = schema['command_fields']
        
        for field_name in self.fields:
            if field_name in field_definitions:
                default_value = field_definitions[field_name].get('default', 0.0)
                self.fields[field_name] = float(default_value)
            else:
                self.fields[field_name] = 0.0
        self._last_command_intent = None
        
        logger.info(f"All setpoints for profile '{self.profile_name}' reset to schema defaults")
    
    def validate_profile_consistency(self) -> bool:
        """
        Validates that the current profile configuration is consistent with the schema.
        
        Returns:
            bool: True if valid, raises exception if invalid.
            
        Raises:
            ValueError: If validation fails.
        """
        schema = SetpointHandler._schema_cache
        validation_rules = schema.get('validation_rules', {})
        
        # Check attitude rate exclusive rule
        if 'attitude_rate_exclusive' in validation_rules:
            rule = validation_rules['attitude_rate_exclusive']
            exclusive_fields = rule.get('fields', [])
            allowed_types = rule.get('allowed_control_types', [])
            
            current_control_type = self.get_control_type()
            has_exclusive_fields = any(field in self.fields for field in exclusive_fields)
            
            if has_exclusive_fields and current_control_type not in allowed_types:
                raise ValueError(f"Profile validation failed: {rule.get('description', 'Unknown rule')}")
        
        return True
    
    def timestamp_setpoint(self):
        """
        Adds a timestamp to the setpoints for telemetry or logging purposes.
        Note: This adds a non-command field for telemetry tracking.
        """
        timestamp = datetime.utcnow().isoformat()
        # Store timestamp separately to avoid confusion with command fields
        if not hasattr(self, '_metadata'):
            self._metadata = {}
        self._metadata['timestamp'] = timestamp
        logger.debug(f"Setpoint timestamp added: {timestamp}")
    
    def get_telemetry_data(self) -> Dict[str, Any]:
        """
        Returns telemetry data including fields, metadata, and profile info.
        
        Returns:
            Dict[str, Any]: Complete telemetry data.
        """
        telemetry = {
            'fields': self.get_fields(),
            'profile_name': self.get_display_name(),
            'control_type': self.get_control_type(),
            'timestamp': datetime.utcnow().isoformat()
        }

        if self._last_command_intent:
            telemetry['last_command_intent'] = {
                'profile_name': self._last_command_intent.profile_name,
                'control_type': self._last_command_intent.control_type,
                'source': self._last_command_intent.source,
                'reason': self._last_command_intent.reason,
                'created_at_utc': self._last_command_intent.created_at_utc,
                'fields': self._last_command_intent.fields,
            }
        
        # Add metadata if available
        if hasattr(self, '_metadata'):
            telemetry.update(self._metadata)
            
        return telemetry
