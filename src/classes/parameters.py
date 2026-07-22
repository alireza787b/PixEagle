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

import copy
import yaml
import os
import logging
import threading
from typing import Optional, Dict, Any, Set, Tuple, List

from classes.runtime_config_generation import runtime_config_barrier

logger = logging.getLogger(__name__)

# Thread lock for config reload operations
_config_reload_lock = threading.RLock()

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


class _ParametersMeta(type):
    """Serialize direct class-attribute access with config publication."""

    def __getattribute__(cls, name: str) -> Any:
        with runtime_config_barrier.read():
            return super().__getattribute__(name)

    def __setattr__(cls, name: str, value: Any) -> None:
        with runtime_config_barrier.read():
            super().__setattr__(name, value)

    def __delattr__(cls, name: str) -> None:
        with runtime_config_barrier.read():
            super().__delattr__(name)


class Parameters(metaclass=_ParametersMeta):
    """
    Central configuration class for the PixEagle project.
    Automatically loads all configuration parameters from the config.yaml file.
    Configurations are set as class variables, maintaining compatibility with existing code.

    Safety Limits Resolution (v5.0.0+):
        Uses SafetyManager for centralized limit resolution:
        1. Valid tightening Safety.FollowerOverrides (if follower_name provided)
        2. Hard Safety.GlobalLimits envelope (single source of truth)
        3. Hardcoded fallback (for safety)
    """

    # Raw config storage for SafetyManager initialization
    _raw_config: Dict[str, Any] = {}
    _loaded_config_file: Optional[str] = None

    # Names installed from the most recent successful config load. Keeping
    # explicit ownership prevents reloads from deleting regular class state.
    _dynamic_config_attributes = set()

    @classmethod
    def read_generation(cls):
        """Return a context manager for compound reads from one generation."""
        return runtime_config_barrier.read()

    @classmethod
    def get_runtime_config_generation(cls) -> int:
        """Return the latest completely published config generation."""
        return runtime_config_barrier.generation()

    # Runtime config is intentionally gitignored. Clean clones should still be
    # importable by falling back to the checked-in default config for reads.
    _DEFAULT_CONFIG_FILE = os.path.normpath('configs/config.yaml')
    _FALLBACK_CONFIG_FILE = os.path.normpath('configs/config_default.yaml')
    # Grouped sections that should NOT be flattened
    _GROUPED_SECTIONS = [
        'Safety',        # Unified safety config (v5.0.0+)
        'TrackerSafety', # Boundary behavior is consumed as one tracker policy
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

    # Hybrid sections: stored as grouped dict AND flat params flattened to class attrs.
    # Use for sections that have both simple values (accessed as Parameters.ATTR)
    # and nested sub-sections (accessed as Parameters.Section['SubSection']).
    _HYBRID_SECTIONS = [
        'Follower',      # Unified follower config (v6.1.0+)
                         # Flat: FOLLOWER_MODE, USE_MAVLINK2REST, visualization params, etc.
                         # Nested: General, FollowerOverrides (for FollowerConfigManager)
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
    def _resolve_config_file(cls, config_file: str) -> str:
        """Resolve config path, falling back to config_default.yaml for clean clones."""
        normalized = os.path.normpath(config_file)
        if os.path.exists(normalized):
            return normalized

        if normalized == cls._DEFAULT_CONFIG_FILE and os.path.exists(cls._FALLBACK_CONFIG_FILE):
            logger.warning(
                "Runtime config %s not found; loading checked-in defaults from %s. "
                "Run the bootstrap/config workflow before editing runtime config.",
                cls._DEFAULT_CONFIG_FILE,
                cls._FALLBACK_CONFIG_FILE,
            )
            return cls._FALLBACK_CONFIG_FILE

        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    @classmethod
    def _load_retired_config_paths(cls) -> Set[Tuple[str, ...]]:
        """Load exact runtime-ignored paths from the canonical retirement registry."""
        from classes.config_service import ConfigService

        registry = ConfigService.get_instance().get_retirement_registry()
        return {
            tuple(entry['path'])
            for entry in registry['retirements']
        }

    @classmethod
    def _without_retired_paths(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """Remove only registry-authorized retired paths from runtime state."""
        filtered = copy.deepcopy(config)
        for path in cls._load_retired_config_paths():
            cursor: Any = filtered
            parents = []
            for component in path[:-1]:
                if not isinstance(cursor, dict) or component not in cursor:
                    break
                parents.append((cursor, component))
                cursor = cursor[component]
            else:
                if isinstance(cursor, dict):
                    cursor.pop(path[-1], None)
                    for parent, component in reversed(parents):
                        child = parent.get(component)
                        if isinstance(child, dict) and not child:
                            parent.pop(component, None)
                        else:
                            break
        return filtered

    @classmethod
    def _build_dynamic_attribute_map(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """Build config attributes and reject ambiguous flattened ownership."""
        attributes: Dict[str, Any] = {}
        origins: Dict[str, Tuple[str, ...]] = {}

        def register(name: str, value: Any, path: Tuple[str, ...]) -> None:
            previous_path = origins.get(name)
            if previous_path is not None:
                raise ValueError(
                    "Configuration paths "
                    f"{'.'.join(previous_path)} and {'.'.join(path)} both map to "
                    f"Parameters.{name}"
                )
            attributes[name] = value
            origins[name] = path

        for section, params in config.items():
            if not isinstance(section, str):
                raise ValueError(
                    f"Configuration section names must be strings, got {section!r}"
                )

            if section in cls._GROUPED_SECTIONS:
                register(section, params, (section,))
            elif section in cls._HYBRID_SECTIONS:
                register(section, params, (section,))
                if isinstance(params, dict):
                    for key, value in params.items():
                        if not isinstance(key, str):
                            raise ValueError(
                                f"Configuration keys in {section!r} must be strings, "
                                f"got {key!r}"
                            )
                        if not isinstance(value, dict):
                            register(key.upper(), value, (section, key))
            elif isinstance(params, dict):
                for key, value in params.items():
                    if not isinstance(key, str):
                        raise ValueError(
                            f"Configuration keys in {section!r} must be strings, "
                            f"got {key!r}"
                        )
                    register(key.upper(), value, (section, key))
            else:
                register(section, params, (section,))

        return attributes

    @classmethod
    def _validate_dynamic_attribute_map(cls, attributes: Dict[str, Any]) -> None:
        """Reject config names owned by the class rather than a previous load."""
        class_attribute_names = set(dir(cls))
        collisions = sorted(
            name
            for name in attributes
            if name not in cls._dynamic_config_attributes
            and name in class_attribute_names
        )
        if collisions:
            names = ", ".join(collisions)
            raise ValueError(
                "Configuration attributes collide with reserved/non-dynamic "
                f"Parameters attributes: {names}"
            )

    @classmethod
    def _install_dynamic_attribute_map(
        cls,
        attributes: Dict[str, Any],
        config: Dict[str, Any],
        resolved_config_file: str,
    ) -> None:
        """Replace config-owned attributes, rolling back on commit failure."""
        previous_names = set(cls._dynamic_config_attributes)
        previous_values = {
            name: cls.__dict__[name]
            for name in previous_names
            if name in cls.__dict__
        }
        previous_raw_config = cls._raw_config
        previous_loaded_config_file = cls._loaded_config_file
        touched_names = previous_names | set(attributes)

        try:
            for name in previous_names - set(attributes):
                if name in cls.__dict__:
                    delattr(cls, name)

            for name, value in attributes.items():
                setattr(cls, name, value)

            cls._dynamic_config_attributes = set(attributes)
            cls._raw_config = config
            cls._loaded_config_file = resolved_config_file
        except Exception:
            for name in touched_names:
                if name in cls.__dict__:
                    delattr(cls, name)
            for name, value in previous_values.items():
                setattr(cls, name, value)

            cls._dynamic_config_attributes = previous_names
            cls._raw_config = previous_raw_config
            cls._loaded_config_file = previous_loaded_config_file
            raise

    @classmethod
    def _capture_dynamic_state(cls) -> Dict[str, Any]:
        """Capture class-owned config state before a strict runtime reload."""
        names = set(cls._dynamic_config_attributes)
        return {
            'names': names,
            'values': {
                name: cls.__dict__[name]
                for name in names
                if name in cls.__dict__
            },
            'raw_config': cls._raw_config,
            'loaded_config_file': cls._loaded_config_file,
        }

    @classmethod
    def _restore_dynamic_state(cls, state: Dict[str, Any]) -> None:
        """Restore config-owned class attributes from a captured state."""
        touched_names = set(cls._dynamic_config_attributes) | set(state['names'])
        for name in touched_names:
            if name in cls.__dict__:
                delattr(cls, name)
        for name, value in state['values'].items():
            setattr(cls, name, value)
        cls._dynamic_config_attributes = set(state['names'])
        cls._raw_config = state['raw_config']
        cls._loaded_config_file = state['loaded_config_file']

    @classmethod
    def _prepare_dependent_managers(
        cls,
        config: Dict[str, Any],
        *,
        strict: bool,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """Prepare manager replacement state before publication."""
        prepared: Dict[str, Any] = {
            'safety_manager': None,
            'safety_state': None,
            'follower_manager': None,
            'follower_state': None,
        }
        failures = []
        try:
            safety_manager = _get_safety_manager()
            prepared['safety_manager'] = safety_manager
            prepared['safety_state'] = safety_manager._prepare_runtime_state(config)
        except Exception as exc:
            failures.append(f"SafetyManager preparation failed: {exc}")

        try:
            follower_manager = _get_follower_config_manager()
            prepared['follower_manager'] = follower_manager
            prepared['follower_state'] = follower_manager._prepare_runtime_state(config)
        except Exception as exc:
            failures.append(f"FollowerConfigManager preparation failed: {exc}")

        if strict and failures:
            raise RuntimeError("; ".join(failures))
        return prepared, failures

    @classmethod
    def _restore_publication_state(
        cls,
        parameter_state: Dict[str, Any],
        prepared: Dict[str, Any],
        safety_state: Any,
        follower_state: Any,
    ) -> None:
        """Restore all config consumers by bounded in-memory assignment."""
        rollback_failures = []
        try:
            cls._restore_dynamic_state(parameter_state)
        except Exception as exc:
            rollback_failures.append(f"Parameters rollback failed: {exc}")

        safety_manager = prepared['safety_manager']
        if safety_manager is not None and safety_state is not None:
            try:
                safety_manager._restore_runtime_state(safety_state)
            except Exception as exc:
                rollback_failures.append(f"SafetyManager rollback failed: {exc}")

        follower_manager = prepared['follower_manager']
        if follower_manager is not None and follower_state is not None:
            try:
                follower_manager._restore_runtime_state(follower_state)
            except Exception as exc:
                rollback_failures.append(
                    f"FollowerConfigManager rollback failed: {exc}"
                )

        if rollback_failures:
            raise RuntimeError("; ".join(rollback_failures))

    @classmethod
    def _validate_dependent_config(
        cls,
        config: Dict[str, Any],
        *,
        strict: bool,
    ) -> Dict[str, Any]:
        """Validate and normalize before publishing any dependent state."""
        failures = []
        normalized_config = config
        if strict:
            try:
                from classes.config_service import ConfigService

                config_service = ConfigService.get_instance()
                normalized_config, legacy_warnings = (
                    config_service.normalize_declared_legacy_values(config)
                )
                for warning in legacy_warnings:
                    logger.warning("Runtime config compatibility: %s", warning)
                validation = config_service.validate_config_mapping(
                    normalized_config,
                    require_safety=True,
                )
                if not validation.valid:
                    failures.extend(
                        f"config schema validation failed: {error}"
                        for error in validation.errors
                    )
                if validation.warnings:
                    logger.debug(
                        "Config schema validation completed with %d warnings",
                        len(validation.warnings),
                    )
            except Exception as exc:
                failures.append(f"config schema validator unavailable: {exc}")

        try:
            from classes.config_validator import normalize_safety_config

            normalized_config = normalize_safety_config(
                normalized_config,
                require_safety=strict,
            )
        except Exception as exc:
            failures.append(f"safety-critical config validation failed: {exc}")
            logger.warning("Could not validate safety config: %s", exc)

        if strict and failures:
            raise RuntimeError("; ".join(failures))
        return normalized_config

    @classmethod
    def load_config(
        cls,
        config_file='configs/config.yaml',
        *,
        strict_dependents: bool = False,
    ):
        """
        Class method to load configurations from the config.yaml file and set class variables.
        Also initializes SafetyManager with the loaded configuration.
        """
        resolved_config_file = cls._resolve_config_file(config_file)

        # Fix: Specify UTF-8 encoding to handle special characters
        with open(resolved_config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        if not isinstance(config, dict):
            raise ValueError(f"Configuration root must be a mapping: {resolved_config_file}")

        cls._publish_config_mapping(
            config,
            resolved_config_file=resolved_config_file,
            strict_dependents=strict_dependents,
        )

    @classmethod
    def get_runtime_config_snapshot(cls) -> Dict[str, Any]:
        """Return one defensive copy of the configuration applied in this process."""
        with runtime_config_barrier.read():
            return copy.deepcopy(cls._raw_config)

    @classmethod
    def publish_config_mapping(
        cls,
        config: Dict[str, Any],
        *,
        source: str = "runtime_config_selection",
        strict_dependents: bool = True,
    ) -> None:
        """Atomically publish a validated in-memory config without rereading disk.

        ConfigService uses this entry point to apply only the reload tiers that a
        runtime action owns. Loading the complete persisted file here would also
        publish unrelated tracker/system-restart changes and create a mixed
        runtime generation.
        """
        if not isinstance(config, dict):
            raise ValueError("Runtime configuration root must be a mapping")
        resolved_source = cls._loaded_config_file or source
        cls._publish_config_mapping(
            copy.deepcopy(config),
            resolved_config_file=resolved_source,
            strict_dependents=strict_dependents,
        )

    @classmethod
    def _publish_config_mapping(
        cls,
        config: Dict[str, Any],
        *,
        resolved_config_file: str,
        strict_dependents: bool,
    ) -> None:
        """Validate, prepare, and atomically publish one complete mapping."""

        runtime_config = cls._without_retired_paths(config)
        validated_config = cls._validate_dependent_config(
            runtime_config,
            strict=strict_dependents,
        )
        if isinstance(validated_config, dict):
            runtime_config = validated_config
        attributes = cls._build_dynamic_attribute_map(runtime_config)
        cls._validate_dynamic_attribute_map(attributes)
        prepared, preparation_failures = cls._prepare_dependent_managers(
            runtime_config,
            strict=strict_dependents,
        )

        publication_failures = list(preparation_failures)
        follower_published = False
        with runtime_config_barrier.publish() as publication:
            previous_parameter_state = cls._capture_dynamic_state()
            safety_manager = prepared['safety_manager']
            follower_manager = prepared['follower_manager']
            previous_safety_state = (
                safety_manager._capture_runtime_state()
                if strict_dependents and safety_manager is not None
                else None
            )
            previous_follower_state = (
                follower_manager._capture_runtime_state()
                if strict_dependents and follower_manager is not None
                else None
            )

            try:
                cls._install_dynamic_attribute_map(
                    attributes,
                    runtime_config,
                    resolved_config_file,
                )

                if prepared['safety_state'] is not None:
                    try:
                        safety_manager._publish_runtime_state(prepared['safety_state'])
                    except Exception as exc:
                        publication_failures.append(
                            f"SafetyManager publication failed: {exc}"
                        )
                        if strict_dependents:
                            raise

                if prepared['follower_state'] is not None:
                    try:
                        follower_manager._publish_runtime_state(
                            prepared['follower_state']
                        )
                        follower_published = True
                    except Exception as exc:
                        publication_failures.append(
                            f"FollowerConfigManager publication failed: {exc}"
                        )
                        if strict_dependents:
                            raise
            except Exception as publication_exc:
                if strict_dependents:
                    try:
                        cls._restore_publication_state(
                            previous_parameter_state,
                            prepared,
                            previous_safety_state,
                            previous_follower_state,
                        )
                    except Exception as rollback_exc:
                        raise RuntimeError(
                            "Strict config publication failed and bounded rollback "
                            f"also failed: {rollback_exc}"
                        ) from publication_exc
                raise

            if strict_dependents or not publication_failures:
                publication.commit()

        if follower_published:
            prepared['follower_manager']._notify_callbacks()

        if publication_failures:
            for failure in publication_failures:
                logger.warning(failure)
        else:
            logger.info("Runtime configuration generation published successfully")

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
    def reload_config(
        cls,
        config_file: str = 'configs/config.yaml',
        *,
        strict_dependents: bool = True,
    ) -> bool:
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

                cls.load_config(
                    config_file,
                    strict_dependents=strict_dependents,
                )

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


# Production startup is strict: invalid safety config or an unavailable runtime
# consumer must stop initialization rather than publish a degraded generation.
Parameters.load_config(strict_dependents=True)

# Validate configuration structure on startup
Parameters.validate_config_structure()
