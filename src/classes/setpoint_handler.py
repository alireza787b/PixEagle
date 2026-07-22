# src/classes/setpoint_handler.py
import logging
import yaml
import os
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from classes.command_safety import (
    CommandValidationError,
    validate_and_clamp_command_value,
)
from classes.command_intent import CommandIntent
from classes.safety_types import FIELD_LIMIT_MAPPING

# Set up logging
logger = logging.getLogger(__name__)

SUPPORTED_FOLLOWER_COMMAND_SCHEMA_VERSIONS = frozenset({"2.0.0"})
_SCHEMA_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _require_nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value.strip()


def _require_unique_string_list(
    value: Any,
    path: str,
    *,
    allow_empty: bool,
) -> List[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{path} must be a list of non-empty strings")
    normalized = [item.strip() for item in value]
    if not allow_empty and not normalized:
        raise ValueError(f"{path} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{path} must not contain duplicates")
    return normalized


def validate_declared_command_value(
    field_name: str,
    value: Any,
    field_definition: Dict[str, Any],
) -> float:
    """Validate a command value against its declared YAML scalar type."""
    declared_type = field_definition.get("type")
    if declared_type != "float":
        raise ValueError(
            f"command_fields.{field_name}.type {declared_type!r} is unsupported; "
            "supported types: ['float']"
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"{field_name} must be a finite Python int or float for declared "
            f"type 'float', got {type(value).__name__}"
        )
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite, got {value!r}")
    return numeric_value


def validate_follower_command_schema(schema: Any) -> Dict[str, Any]:
    """Validate the complete follower command contract before runtime use."""
    if not isinstance(schema, dict):
        raise ValueError("follower command schema must be a YAML object")
    allowed_top_level = {
        "schema_version",
        "command_fields",
        "follower_profiles",
        "removed_profile_aliases",
        "control_types",
        "ui_config",
        "validation_rules",
    }
    unknown_top_level = sorted(set(schema) - allowed_top_level)
    if unknown_top_level:
        raise ValueError(f"unknown follower command schema sections: {unknown_top_level}")

    schema_version = schema.get("schema_version")
    if schema_version not in SUPPORTED_FOLLOWER_COMMAND_SCHEMA_VERSIONS:
        raise ValueError(
            f"unsupported follower command schema_version {schema_version!r}; "
            f"supported versions: {sorted(SUPPORTED_FOLLOWER_COMMAND_SCHEMA_VERSIONS)}"
        )

    command_fields = schema.get("command_fields")
    profiles = schema.get("follower_profiles")
    control_types = schema.get("control_types")
    removed_aliases = schema.get("removed_profile_aliases")
    if not isinstance(command_fields, dict) or not command_fields:
        raise ValueError("command_fields must be a non-empty object")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("follower_profiles must be a non-empty object")
    if not isinstance(control_types, dict) or not control_types:
        raise ValueError("control_types must be a non-empty object")
    if not isinstance(removed_aliases, dict):
        raise ValueError("removed_profile_aliases must be an object")

    for field_name, field_definition in command_fields.items():
        if not isinstance(field_name, str) or not _SCHEMA_NAME_RE.fullmatch(field_name):
            raise ValueError(f"invalid command field name {field_name!r}")
        if not isinstance(field_definition, dict):
            raise ValueError(f"command_fields.{field_name} must be an object")
        unknown_field_metadata = sorted(
            set(field_definition)
            - {"type", "default", "unit", "description", "clamp", "limits"}
        )
        if unknown_field_metadata:
            raise ValueError(
                f"command_fields.{field_name} has unsupported metadata: "
                f"{unknown_field_metadata}"
            )
        _require_nonempty_string(
            field_definition.get("description"),
            f"command_fields.{field_name}.description",
        )
        _require_nonempty_string(
            field_definition.get("unit"),
            f"command_fields.{field_name}.unit",
        )
        if not isinstance(field_definition.get("clamp"), bool):
            raise ValueError(f"command_fields.{field_name}.clamp must be a boolean")
        validate_declared_command_value(
            field_name,
            field_definition.get("default"),
            field_definition,
        )
        limits = field_definition.get("limits")
        if limits is not None:
            if not isinstance(limits, dict) or set(limits) != {"min", "max"}:
                raise ValueError(
                    f"command_fields.{field_name}.limits must contain exactly min and max"
                )
            minimum = validate_declared_command_value(
                f"{field_name}.limits.min", limits["min"], field_definition
            )
            maximum = validate_declared_command_value(
                f"{field_name}.limits.max", limits["max"], field_definition
            )
            if minimum > maximum:
                raise ValueError(
                    f"command_fields.{field_name}.limits min must not exceed max"
                )

    mavsdk_methods = set()
    for control_name, metadata in control_types.items():
        if not isinstance(control_name, str) or not _SCHEMA_NAME_RE.fullmatch(control_name):
            raise ValueError(f"invalid control type name {control_name!r}")
        if not isinstance(metadata, dict):
            raise ValueError(f"control_types.{control_name} must be an object")
        unknown_control_metadata = sorted(
            set(metadata) - {"mavsdk_method", "description", "ui_display"}
        )
        if unknown_control_metadata:
            raise ValueError(
                f"control_types.{control_name} has unsupported metadata: "
                f"{unknown_control_metadata}"
            )
        method = _require_nonempty_string(
            metadata.get("mavsdk_method"),
            f"control_types.{control_name}.mavsdk_method",
        )
        _require_nonempty_string(
            metadata.get("description"),
            f"control_types.{control_name}.description",
        )
        _require_nonempty_string(
            metadata.get("ui_display"),
            f"control_types.{control_name}.ui_display",
        )
        if method in mavsdk_methods:
            raise ValueError(f"duplicate MAVSDK dispatch method {method!r}")
        mavsdk_methods.add(method)

    from classes.tracker_output import TrackerDataType

    tracker_data_types = set(TrackerDataType.__members__)
    for profile_name, profile in profiles.items():
        if not isinstance(profile_name, str) or not _SCHEMA_NAME_RE.fullmatch(profile_name):
            raise ValueError(f"invalid follower profile name {profile_name!r}")
        if not isinstance(profile, dict):
            raise ValueError(f"follower_profiles.{profile_name} must be an object")
        if "optional_fields" in profile:
            raise ValueError(
                f"follower_profiles.{profile_name}.optional_fields is unsupported; "
                "every published command field must be declared in required_fields"
            )
        unknown_profile_metadata = sorted(
            set(profile)
            - {
                "display_name",
                "description",
                "control_type",
                "required_fields",
                "ui_category",
                "required_tracker_data",
                "optional_tracker_data",
            }
        )
        if unknown_profile_metadata:
            raise ValueError(
                f"follower_profiles.{profile_name} has unsupported metadata: "
                f"{unknown_profile_metadata}"
            )
        for metadata_name in ("display_name", "description", "ui_category"):
            _require_nonempty_string(
                profile.get(metadata_name),
                f"follower_profiles.{profile_name}.{metadata_name}",
            )
        control_type = _require_nonempty_string(
            profile.get("control_type"),
            f"follower_profiles.{profile_name}.control_type",
        )
        if control_type not in control_types:
            raise ValueError(
                f"follower_profiles.{profile_name}.control_type references unknown "
                f"control type {control_type!r}"
            )
        required_fields = _require_unique_string_list(
            profile.get("required_fields"),
            f"follower_profiles.{profile_name}.required_fields",
            allow_empty=False,
        )
        unknown_fields = sorted(set(required_fields) - set(command_fields))
        if unknown_fields:
            raise ValueError(
                f"follower_profiles.{profile_name}.required_fields references unknown "
                f"command fields: {unknown_fields}"
            )
        required_tracker_data = _require_unique_string_list(
            profile.get("required_tracker_data"),
            f"follower_profiles.{profile_name}.required_tracker_data",
            allow_empty=False,
        )
        optional_tracker_data = _require_unique_string_list(
            profile.get("optional_tracker_data"),
            f"follower_profiles.{profile_name}.optional_tracker_data",
            allow_empty=True,
        )
        tracker_overlap = set(required_tracker_data) & set(optional_tracker_data)
        if tracker_overlap:
            raise ValueError(
                f"follower_profiles.{profile_name} declares tracker data as both "
                f"required and optional: {sorted(tracker_overlap)}"
            )
        unknown_tracker_data = sorted(
            (set(required_tracker_data) | set(optional_tracker_data))
            - tracker_data_types
        )
        if unknown_tracker_data:
            raise ValueError(
                f"follower_profiles.{profile_name} references unknown TrackerDataType "
                f"values: {unknown_tracker_data}"
            )

    for alias, replacement in removed_aliases.items():
        if not isinstance(alias, str) or not _SCHEMA_NAME_RE.fullmatch(alias):
            raise ValueError(f"invalid removed profile alias {alias!r}")
        if alias in profiles:
            raise ValueError(f"removed profile alias {alias!r} is still active")
        if not isinstance(replacement, str) or replacement not in profiles:
            raise ValueError(
                f"removed profile alias {alias!r} references unknown replacement "
                f"{replacement!r}"
            )

    ui_config = schema.get("ui_config")
    if not isinstance(ui_config, dict):
        raise ValueError("ui_config must be an object")
    unknown_ui_metadata = sorted(
        set(ui_config) - {"field_display_order", "field_groups", "profile_display_order"}
    )
    if unknown_ui_metadata:
        raise ValueError(f"ui_config has unsupported metadata: {unknown_ui_metadata}")
    field_order = _require_unique_string_list(
        ui_config.get("field_display_order"),
        "ui_config.field_display_order",
        allow_empty=False,
    )
    if set(field_order) != set(command_fields):
        raise ValueError("ui_config.field_display_order must list every command field exactly once")
    profile_order = _require_unique_string_list(
        ui_config.get("profile_display_order"),
        "ui_config.profile_display_order",
        allow_empty=False,
    )
    if set(profile_order) != set(profiles):
        raise ValueError("ui_config.profile_display_order must list every profile exactly once")
    field_groups = ui_config.get("field_groups")
    if not isinstance(field_groups, dict) or not field_groups:
        raise ValueError("ui_config.field_groups must be a non-empty object")
    grouped_fields = set()
    for group_name, group in field_groups.items():
        if not isinstance(group_name, str) or not _SCHEMA_NAME_RE.fullmatch(group_name):
            raise ValueError(f"invalid ui_config.field_groups name {group_name!r}")
        if not isinstance(group, dict):
            raise ValueError(f"ui_config.field_groups.{group_name} must be an object")
        unknown_group_metadata = sorted(set(group) - {"name", "fields", "color"})
        if unknown_group_metadata:
            raise ValueError(
                f"ui_config.field_groups.{group_name} has unsupported metadata: "
                f"{unknown_group_metadata}"
            )
        _require_nonempty_string(group.get("name"), f"ui_config.field_groups.{group_name}.name")
        _require_nonempty_string(group.get("color"), f"ui_config.field_groups.{group_name}.color")
        group_fields = _require_unique_string_list(
            group.get("fields"),
            f"ui_config.field_groups.{group_name}.fields",
            allow_empty=False,
        )
        unknown_group_fields = sorted(set(group_fields) - set(command_fields))
        if unknown_group_fields:
            raise ValueError(
                f"ui_config.field_groups.{group_name} references unknown fields: "
                f"{unknown_group_fields}"
            )
        grouped_fields.update(group_fields)
    if grouped_fields != set(command_fields):
        raise ValueError("ui_config.field_groups must cover every command field")

    validation_rules = schema.get("validation_rules")
    if not isinstance(validation_rules, dict):
        raise ValueError("validation_rules must be an object")
    for rule_name, rule in validation_rules.items():
        if not isinstance(rule, dict):
            raise ValueError(f"validation_rules.{rule_name} must be an object")
        unknown_rule_metadata = sorted(
            set(rule) - {"fields", "allowed_control_types", "description"}
        )
        if unknown_rule_metadata:
            raise ValueError(
                f"validation_rules.{rule_name} has unsupported metadata: "
                f"{unknown_rule_metadata}"
            )
        fields = _require_unique_string_list(
            rule.get("fields"),
            f"validation_rules.{rule_name}.fields",
            allow_empty=False,
        )
        allowed_controls = _require_unique_string_list(
            rule.get("allowed_control_types"),
            f"validation_rules.{rule_name}.allowed_control_types",
            allow_empty=False,
        )
        _require_nonempty_string(
            rule.get("description"),
            f"validation_rules.{rule_name}.description",
        )
        if set(fields) - set(command_fields):
            raise ValueError(f"validation_rules.{rule_name} references unknown command fields")
        if set(allowed_controls) - set(control_types):
            raise ValueError(f"validation_rules.{rule_name} references unknown control types")

    return schema


def command_intent_contract_errors(
    command_intent: Any,
    command_contract: Dict[str, Any],
) -> List[str]:
    """Return runtime/evidence command-intent contract violations."""
    errors: List[str] = []
    if not isinstance(command_intent, dict):
        return ["command_intent must be an object"]

    profiles = command_contract["follower_profiles"]
    removed_aliases = command_contract["removed_profile_aliases"]
    profile_name = command_intent.get("profile_name")
    profile = None
    if not isinstance(profile_name, str) or not profile_name:
        errors.append("command_intent.profile_name must be a non-empty string")
    elif profile_name in removed_aliases:
        errors.append(
            f"command_intent.profile_name {profile_name!r} is a retired profile alias"
        )
    else:
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            errors.append(
                f"command_intent.profile_name {profile_name!r} is not an active "
                "follower_commands.yaml profile"
            )

    control_type = command_intent.get("control_type")
    if not isinstance(control_type, str) or not control_type:
        errors.append("command_intent.control_type must be a non-empty string")
    elif control_type not in command_contract["control_types"]:
        errors.append(f"command_intent.control_type {control_type!r} is not declared")
    elif profile is not None and control_type != profile["control_type"]:
        errors.append(
            f"command_intent.control_type must be {profile['control_type']!r} "
            f"for profile {profile_name!r}, got {control_type!r}"
        )

    fields = command_intent.get("fields")
    if not isinstance(fields, dict) or not fields:
        errors.append("command_intent.fields must be a non-empty object")
        return errors

    if profile is not None:
        expected_fields = set(profile["required_fields"])
        actual_fields = set(fields)
        if actual_fields != expected_fields:
            errors.append(
                "command_intent.fields must exactly match follower_commands.yaml "
                f"for profile {profile_name!r}; "
                f"missing={sorted(expected_fields - actual_fields)} "
                f"unexpected={sorted(actual_fields - expected_fields)}"
            )

    definitions = command_contract["command_fields"]
    for field_name, value in fields.items():
        definition = definitions.get(field_name)
        if not isinstance(definition, dict):
            continue
        try:
            validate_declared_command_value(field_name, value, definition)
        except ValueError as exc:
            errors.append(f"command_intent.fields.{field_name}: {exc}")
    return errors

class SetpointHandler:
    """
    Schema-aware setpoint handler that loads follower profiles and field definitions
    from the unified command schema YAML file. Provides type safety, validation,
    and extensible configuration for all follower modes.
    """
    
    # Class-level schema cache to avoid repeated file loading
    _schema_cache: Optional[Dict[str, Any]] = None
    _schema_file_path = str(
        Path(__file__).resolve().parents[2] / "configs" / "follower_commands.yaml"
    )
    
    def __init__(
        self,
        profile_name: str,
        *,
        enforce_operational_limits: bool = True,
    ):
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
        self.enforce_operational_limits = bool(enforce_operational_limits)
        self.fields: Dict[str, float] = {}
        self.profile_config: Dict[str, Any] = {}
        self._fallback_defaults: Dict[str, float] = {}
        self._fallback_default_sources: Dict[str, str] = {}
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
                
            with open(cls._schema_file_path, 'r', encoding='utf-8') as f:
                schema = yaml.safe_load(f)

            cls._schema_cache = validate_follower_command_schema(schema)
                
            logger.info(f"Loaded follower command schema from {cls._schema_file_path}")
            logger.debug(f"Schema version: {cls._schema_cache.get('schema_version', 'unknown')}")
            
        except yaml.YAMLError as e:
            logger.error(f"Error parsing schema YAML: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading schema: {e}")
            raise

    @classmethod
    def load_and_validate_schema(cls, path: str | Path) -> Dict[str, Any]:
        """Load a command schema for tooling without mutating the runtime cache."""
        schema_path = Path(path)
        try:
            schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise
        except yaml.YAMLError:
            raise
        return validate_follower_command_schema(schema)

    @classmethod
    def get_removed_profile_aliases(cls) -> Dict[str, str]:
        """Return retired profile migration hints from the validated YAML contract."""
        if cls._schema_cache is None:
            cls._load_schema()
        return dict(cls._schema_cache["removed_profile_aliases"])

    @classmethod
    def get_control_type_metadata(cls, control_type: str) -> Dict[str, Any]:
        """Return the validated dispatch metadata for a control type."""
        if cls._schema_cache is None:
            cls._load_schema()
        metadata = cls._schema_cache["control_types"].get(control_type)
        if not isinstance(metadata, dict):
            raise ValueError(f"Unknown control type {control_type!r}")
        return dict(metadata)

    @classmethod
    def get_mavsdk_method(cls, control_type: str) -> str:
        """Return the YAML-declared MAVSDK dispatch method."""
        return str(cls.get_control_type_metadata(control_type)["mavsdk_method"])
    
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
        
        # Every declared field is required in each atomic command snapshot.
        required_fields = self.profile_config.get('required_fields', [])
        if not isinstance(required_fields, list):
            raise ValueError(
                f"Profile '{self.profile_name}' required_fields must be a list"
            )
        
        # Initialize fields with default values from schema
        field_definitions = schema['command_fields']
        for field_name in required_fields:
            if field_name in field_definitions:
                default_value = validate_declared_command_value(
                    field_name,
                    field_definitions[field_name].get('default'),
                    field_definitions[field_name],
                )
                self.fields[field_name] = default_value
            else:
                raise ValueError(
                    f"Profile '{self.profile_name}' references unknown command "
                    f"field '{field_name}'"
                )

        self._fallback_defaults = self.fields.copy()
        self._fallback_default_sources = {
            field_name: "command_schema"
            for field_name in self.fields
        }
        
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
        field_definition = SetpointHandler._schema_cache['command_fields'][field_name]
        numeric_value = validate_declared_command_value(
            field_name,
            value,
            field_definition,
        )
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
    ) -> CommandIntent:
        """
        Atomically validates and applies a full command field snapshot.

        Validation is performed against a staged copy first. The live setpoint
        state is changed only after every provided field is valid, finite, and
        inside the active safety/schema limits. Callers must provide every field
        in the active profile so stale values cannot be carried over implicitly.
        """
        if not isinstance(field_values, dict):
            raise ValueError(f"field_values must be a dict, got {type(field_values)}")

        # A rejected command must never leave an older intent publishable.
        self._last_command_intent = None

        expected_fields = set(self.fields.keys())
        provided_fields = set(field_values.keys())
        invalid_fields = provided_fields - expected_fields
        if invalid_fields:
            raise ValueError(
                f"Fields {sorted(invalid_fields)} are not valid for profile "
                f"'{self.profile_name}'. Valid fields: {sorted(expected_fields)}"
            )

        missing_fields = expected_fields - provided_fields
        if missing_fields:
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
        field_definition = SetpointHandler._schema_cache['command_fields'][field_name]
        numeric_value = validate_declared_command_value(
            field_name,
            value,
            field_definition,
        )
        return self._validate_field_limits(field_name, numeric_value)

    def get_last_command_intent(self) -> Optional[CommandIntent]:
        """Return the most recently accepted atomic command intent, if any."""
        return self._last_command_intent

    def clear_command_intent(self) -> None:
        """Invalidate any previously accepted intent without changing field values."""
        self._last_command_intent = None
    
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
            if not self.enforce_operational_limits:
                # The caller already validated the declared scalar type and
                # finiteness.  Local command preview records raw follower math
                # without applying the live flight envelope.
                return value
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
            str: The canonical control type for this profile.
        """
        control_type = self.profile_config.get('control_type')
        declared_types = SetpointHandler._schema_cache.get('control_types', {})
        if not isinstance(control_type, str) or control_type not in declared_types:
            raise ValueError(
                f"Profile '{self.profile_name}' has unknown control type "
                f"{control_type!r}"
            )
        return control_type

    def get_mavsdk_dispatch_method(self) -> str:
        """Return the canonical YAML-backed MAVSDK method for this profile."""
        return self.get_mavsdk_method(self.get_control_type())
    
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
        Reset all setpoints to the configured fail-closed fallback values.

        Schema defaults initialize every profile. A concrete follower may replace
        selected values, such as attitude-rate thrust, from its canonical runtime
        configuration before Offboard starts.
        """
        for field_name in self.fields:
            self.fields[field_name] = self._fallback_defaults[field_name]
        self._last_command_intent = None

        logger.info(
            "All setpoints for profile '%s' reset to configured fallback defaults",
            self.profile_name,
        )

    def configure_fallback_defaults(
        self,
        field_values: Dict[str, float],
        *,
        source: str,
    ) -> Dict[str, float]:
        """Atomically configure profile fallback values from canonical runtime config."""
        if not isinstance(field_values, dict) or not field_values:
            raise ValueError("field_values must be a non-empty dict")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be a non-empty string")

        staged_defaults = self._fallback_defaults.copy()
        staged_sources = self._fallback_default_sources.copy()
        for field_name, raw_value in field_values.items():
            staged_defaults[field_name] = self._validate_single_field(
                field_name,
                raw_value,
            )
            staged_sources[field_name] = source.strip()

        self._fallback_defaults = staged_defaults
        self._fallback_default_sources = staged_sources
        logger.info(
            "Configured fallback defaults for profile '%s': fields=%s source=%s",
            self.profile_name,
            sorted(field_values),
            source.strip(),
        )
        return self.get_fallback_defaults()

    def get_fallback_defaults(self) -> Dict[str, float]:
        """Return a copy of the setpoints used for stale/missing command intent."""
        return self._fallback_defaults.copy()

    def get_fallback_default_sources(self) -> Dict[str, str]:
        """Return the source label for every configured fallback field."""
        return self._fallback_default_sources.copy()
    
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
        self.get_control_type()

        required_fields = set(self.profile_config.get('required_fields', []))
        available_fields = set(self.fields)
        missing_required = required_fields - available_fields
        if missing_required:
            raise ValueError(
                f"Profile '{self.profile_name}' is missing required fields: "
                f"{sorted(missing_required)}"
            )
        
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
