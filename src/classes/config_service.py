"""
Configuration Service - Schema-Driven Config Management
=========================================================

Provides centralized configuration management with:
- YAML persistence with backup and comment preservation
- Schema-based validation
- Diff comparison using deepdiff
- Import/export functionality

Project: PixEagle
Author: Alireza Ghaderi
"""

import os
import json
import shutil
import logging
import threading
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

# File locking (Unix-only, but graceful fallback on Windows)
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

# Use ruamel.yaml for round-trip YAML (comment preservation)
from ruamel.yaml import YAML
from deepdiff import DeepDiff

logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Validation result status."""
    VALID = "valid"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ValidationResult:
    """Result of parameter validation."""
    valid: bool
    status: ValidationStatus
    errors: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict:
        return {
            'valid': self.valid,
            'status': self.status.value,
            'errors': self.errors,
            'warnings': self.warnings
        }


@dataclass
class DiffEntry:
    """A single difference between two configs."""
    path: str
    section: str
    parameter: str
    old_value: Any
    new_value: Any
    change_type: str  # 'added', 'removed', 'changed'

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ConfigBackup:
    """Metadata for a config backup."""
    id: str
    filename: str
    timestamp: float
    size: int

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AuditEntry:
    """Audit log entry for config changes."""
    timestamp: str
    action: str  # 'update', 'import', 'restore', 'revert'
    section: str
    parameter: Optional[str]
    old_value: Any
    new_value: Any
    source: str  # 'api', 'import', 'restore'

    def to_dict(self) -> Dict:
        return asdict(self)


class ConfigService:
    """
    Singleton service for schema-driven configuration management.

    Provides:
    - Schema loading and parameter metadata
    - Config CRUD operations with validation
    - Backup and restore
    - Diff comparison between configs
    - Import/export functionality
    """

    _instance = None
    _lock = threading.Lock()

    # Paths relative to project root
    SCHEMA_PATH = "configs/config_schema.yaml"
    CONFIG_PATH = "configs/config.yaml"
    DEFAULT_PATH = "configs/config_default.yaml"
    BACKUP_DIR = "configs/backups"
    AUDIT_LOG_PATH = "configs/audit_log.json"
    MAX_BACKUPS = 20
    MAX_AUDIT_ENTRIES = 1000

    def __init__(self):
        """Initialize ConfigService. Use get_instance() instead."""
        self._schema: Dict = {}
        self._config: Dict = {}
        self._config_raw = None  # Raw ruamel.yaml object for round-trip
        self._default: Dict = {}
        self._audit_log: List[Dict] = []
        self._project_root = Path(__file__).parent.parent.parent
        self._load_all()
        self._load_audit_log()

    @classmethod
    def get_instance(cls) -> 'ConfigService':
        """Get singleton instance of ConfigService."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_path(self, relative_path: str) -> Path:
        """Get absolute path from relative path."""
        return self._project_root / relative_path

    def _load_all(self):
        """Load schema, current config, and defaults."""
        yaml = YAML()
        yaml.preserve_quotes = True

        try:
            # Load schema
            schema_path = self._get_path(self.SCHEMA_PATH)
            if schema_path.exists():
                with open(schema_path, 'r', encoding='utf-8') as f:
                    self._schema = dict(yaml.load(f) or {})
                logger.info(f"Loaded schema from {schema_path}")
            else:
                logger.warning(f"Schema file not found: {schema_path}")

            # Load current config (with comment preservation for editing)
            config_path = self._get_path(self.CONFIG_PATH)
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    loaded = yaml.load(f)
                    self._config = dict(loaded) if loaded else {}
                    self._config_raw = loaded  # Keep raw for round-trip
                logger.info(f"Loaded config from {config_path}")
            else:
                logger.warning(f"Config file not found: {config_path}")

            # Load defaults
            default_path = self._get_path(self.DEFAULT_PATH)
            if default_path.exists():
                with open(default_path, 'r', encoding='utf-8') as f:
                    loaded = yaml.load(f)
                    self._default = dict(loaded) if loaded else {}
                logger.info(f"Loaded defaults from {default_path}")

        except Exception as e:
            logger.error(f"Error loading config files: {e}")

    def reload(self):
        """Reload all config files from disk."""
        self._load_all()

    # =========================================================================
    # Audit Log Methods
    # =========================================================================

    def _load_audit_log(self):
        """Load audit log from disk."""
        try:
            audit_path = self._get_path(self.AUDIT_LOG_PATH)
            if audit_path.exists():
                with open(audit_path, 'r', encoding='utf-8') as f:
                    self._audit_log = json.load(f)
                logger.info(f"Loaded {len(self._audit_log)} audit entries")
            else:
                self._audit_log = []
        except Exception as e:
            logger.error(f"Error loading audit log: {e}")
            self._audit_log = []

    def _save_audit_log(self):
        """Save audit log to disk."""
        try:
            audit_path = self._get_path(self.AUDIT_LOG_PATH)
            # Trim to max entries
            if len(self._audit_log) > self.MAX_AUDIT_ENTRIES:
                self._audit_log = self._audit_log[-self.MAX_AUDIT_ENTRIES:]
            with open(audit_path, 'w', encoding='utf-8') as f:
                json.dump(self._audit_log, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving audit log: {e}")

    def log_audit_entry(
        self,
        action: str,
        section: str,
        parameter: Optional[str] = None,
        old_value: Any = None,
        new_value: Any = None,
        source: str = 'api'
    ):
        """Log a config change to the audit log."""
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            action=action,
            section=section,
            parameter=parameter,
            old_value=old_value,
            new_value=new_value,
            source=source
        )
        self._audit_log.append(entry.to_dict())
        self._save_audit_log()
        logger.debug(f"Audit: {action} {section}.{parameter}")

    def get_audit_log(
        self,
        limit: int = 100,
        offset: int = 0,
        section: Optional[str] = None,
        action: Optional[str] = None
    ) -> Dict:
        """
        Get audit log entries with optional filtering.

        Args:
            limit: Max entries to return
            offset: Skip first N entries
            section: Filter by section name
            action: Filter by action type

        Returns:
            Dict with 'entries', 'total', 'limit', 'offset'
        """
        entries = self._audit_log.copy()

        # Apply filters
        if section:
            entries = [e for e in entries if e.get('section') == section]
        if action:
            entries = [e for e in entries if e.get('action') == action]

        # Sort by timestamp descending (most recent first)
        entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        total = len(entries)
        entries = entries[offset:offset + limit]

        return {
            'entries': entries,
            'total': total,
            'limit': limit,
            'offset': offset
        }

    def clear_audit_log(self):
        """Clear all audit log entries."""
        self._audit_log = []
        self._save_audit_log()
        logger.info("Audit log cleared")

    # =========================================================================
    # Schema Methods
    # =========================================================================

    def get_schema(self, section: Optional[str] = None) -> Dict:
        """
        Get schema definition.

        Args:
            section: Optional section name to get only that section's schema

        Returns:
            Full schema or section schema
        """
        if section:
            return self._schema.get('sections', {}).get(section, {})
        return self._schema

    def get_categories(self) -> Dict:
        """Get category definitions from schema."""
        return self._schema.get('categories', {})

    def get_sections(self) -> List[Dict]:
        """Get list of all sections with metadata."""
        sections = []
        for name, data in self._schema.get('sections', {}).items():
            sections.append({
                'name': name,
                'display_name': data.get('display_name', name),
                'category': data.get('category', 'other'),
                'icon': data.get('icon', 'settings'),
                'parameter_count': len(data.get('parameters', {}))
            })
        return sections

    def get_parameter_schema(self, section: str, param: str) -> Optional[Dict]:
        """Get schema for a specific parameter."""
        section_schema = self.get_schema(section)
        return section_schema.get('parameters', {}).get(param)

    # =========================================================================
    # Config Read Methods
    # =========================================================================

    def get_config(self, section: Optional[str] = None) -> Dict:
        """
        Get current configuration.

        Args:
            section: Optional section name

        Returns:
            Full config or section config
        """
        if section:
            return self._config.get(section, {})
        return self._config

    def get_default(self, section: Optional[str] = None) -> Dict:
        """Get default configuration."""
        if section:
            return self._default.get(section, {})
        return self._default

    def get_parameter(self, section: str, param: str) -> Any:
        """Get a specific parameter value."""
        section_data = self._config.get(section, {})
        if isinstance(section_data, dict):
            return section_data.get(param)
        return None

    def get_default_parameter(self, section: str, param: str) -> Any:
        """Get default value for a parameter."""
        section_data = self._default.get(section, {})
        if isinstance(section_data, dict):
            return section_data.get(param)
        return None

    # =========================================================================
    # Validation
    # =========================================================================

    def validate_value(self, section: str, param: str, value: Any) -> ValidationResult:
        """
        Validate a value against its schema.

        Args:
            section: Section name
            param: Parameter name
            value: Value to validate

        Returns:
            ValidationResult with status, errors, and warnings
        """
        errors = []
        warnings = []

        # Get parameter schema
        param_schema = self.get_parameter_schema(section, param)
        if not param_schema:
            # No schema - allow any value but warn
            warnings.append(f"No schema found for {section}.{param}")
            return ValidationResult(True, ValidationStatus.WARNING, errors, warnings)

        expected_type = param_schema.get('type', 'any')

        # Type validation
        if expected_type == 'integer':
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"Expected integer, got {type(value).__name__}")
            else:
                # Range validation
                if 'min' in param_schema and value < param_schema['min']:
                    errors.append(f"Value {value} is below minimum {param_schema['min']}")
                if 'max' in param_schema and value > param_schema['max']:
                    errors.append(f"Value {value} is above maximum {param_schema['max']}")

        elif expected_type == 'float':
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"Expected float, got {type(value).__name__}")
            else:
                if 'min' in param_schema and value < param_schema['min']:
                    errors.append(f"Value {value} is below minimum {param_schema['min']}")
                if 'max' in param_schema and value > param_schema['max']:
                    errors.append(f"Value {value} is above maximum {param_schema['max']}")

        elif expected_type == 'boolean':
            if not isinstance(value, bool):
                errors.append(f"Expected boolean, got {type(value).__name__}")

        elif expected_type == 'string':
            if not isinstance(value, str):
                errors.append(f"Expected string, got {type(value).__name__}")
            elif 'enum' in param_schema and value not in param_schema['enum']:
                errors.append(
                    f"Value '{value}' not in allowed set {param_schema['enum']}"
                )

        elif expected_type == 'array':
            if not isinstance(value, list):
                errors.append(f"Expected array, got {type(value).__name__}")

        elif expected_type == 'object':
            if not isinstance(value, dict):
                errors.append(f"Expected object, got {type(value).__name__}")

        # Check if value is different from default
        default_value = self.get_default_parameter(section, param)
        if value != default_value:
            warnings.append("Value differs from default")

        # Check reboot requirement
        if param_schema.get('reboot_required', False):
            warnings.append("Restart required for this change to take effect")

        valid = len(errors) == 0
        status = ValidationStatus.ERROR if errors else (
            ValidationStatus.WARNING if warnings else ValidationStatus.VALID
        )

        return ValidationResult(valid, status, errors, warnings)

    # =========================================================================
    # Config Write Methods
    # =========================================================================

    def set_parameter(
        self,
        section: str,
        param: str,
        value: Any,
        validate: bool = True
    ) -> ValidationResult:
        """
        Set a parameter value (in memory only, call save_config to persist).

        Args:
            section: Section name
            param: Parameter name
            value: New value
            validate: Whether to validate before setting

        Returns:
            ValidationResult
        """
        if validate:
            result = self.validate_value(section, param, value)
            if not result.valid:
                return result
        else:
            result = ValidationResult(True, ValidationStatus.VALID, [], [])

        # Ensure section exists
        if section not in self._config:
            self._config[section] = {}

        # Set value
        if isinstance(self._config[section], dict):
            # Capture old value for audit
            old_value = self._config[section].get(param)
            self._config[section][param] = value
            logger.info(f"Set {section}.{param} = {value}")

            # Log to audit trail
            self.log_audit_entry(
                action='update',
                section=section,
                parameter=param,
                old_value=old_value,
                new_value=value,
                source='api'
            )
        else:
            result.errors.append(f"Section {section} is not a dictionary")
            result.valid = False
            result.status = ValidationStatus.ERROR

        return result

    def set_section(self, section: str, values: Dict, validate: bool = True) -> ValidationResult:
        """Set multiple parameters in a section."""
        all_errors = []
        all_warnings = []

        for param, value in values.items():
            result = self.set_parameter(section, param, value, validate)
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)

        valid = len(all_errors) == 0
        status = ValidationStatus.ERROR if all_errors else (
            ValidationStatus.WARNING if all_warnings else ValidationStatus.VALID
        )

        return ValidationResult(valid, status, all_errors, all_warnings)

    def revert_to_default(
        self,
        section: Optional[str] = None,
        param: Optional[str] = None
    ) -> bool:
        """
        Revert config to default values.

        Args:
            section: Optional section to revert (None = all)
            param: Optional parameter to revert (requires section)

        Returns:
            True if successful
        """
        try:
            if section and param:
                # Revert single parameter
                default_value = self.get_default_parameter(section, param)
                if default_value is not None:
                    self.set_parameter(section, param, default_value, validate=False)
            elif section:
                # Revert entire section
                default_section = self.get_default(section)
                if default_section:
                    self._config[section] = default_section.copy()
            else:
                # Revert everything
                self._config = self._default.copy()

            logger.info(f"Reverted to default: section={section}, param={param}")
            return True

        except Exception as e:
            logger.error(f"Error reverting to default: {e}")
            return False

    # =========================================================================
    # Persistence
    # =========================================================================

    def save_config(self, backup: bool = True) -> bool:
        """
        Save current config to YAML file with atomic writes and file locking.

        Uses a safe write pattern:
        1. Acquire file lock (if available)
        2. Write to temporary file
        3. Flush and sync to disk
        4. Atomic rename to target file
        5. Release lock

        Args:
            backup: Whether to create backup before saving

        Returns:
            True if successful
        """
        config_path = self._get_path(self.CONFIG_PATH)
        temp_path = None
        lock_file = None

        try:
            # Create backup if requested
            if backup and config_path.exists():
                self._create_backup()

            # Acquire file lock for writing (if available)
            lock_path = config_path.with_suffix('.lock')
            if HAS_FCNTL:
                lock_file = open(lock_path, 'w')
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    # Wait for lock with timeout
                    import time
                    for _ in range(10):  # 10 second timeout
                        time.sleep(1)
                        try:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            continue
                    else:
                        raise TimeoutError("Could not acquire config file lock")

            yaml = YAML()
            yaml.preserve_quotes = True
            yaml.width = 120
            yaml.default_flow_style = False

            # If we have raw config with comments, update it
            if self._config_raw is not None:
                # Update raw config with current values
                for section, params in self._config.items():
                    if section in self._config_raw:
                        if isinstance(params, dict) and isinstance(self._config_raw[section], dict):
                            for key, value in params.items():
                                self._config_raw[section][key] = value
                        else:
                            self._config_raw[section] = params
                    else:
                        self._config_raw[section] = params
                data_to_write = self._config_raw
            else:
                data_to_write = self._config

            # Atomic write: write to temp file, then rename
            # Create temp file in same directory for atomic rename
            fd, temp_path = tempfile.mkstemp(
                suffix='.yaml.tmp',
                dir=config_path.parent,
                prefix='config_'
            )

            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    yaml.dump(data_to_write, f)
                    f.flush()
                    os.fsync(f.fileno())  # Ensure data is written to disk

                # Atomic rename (POSIX guarantees this is atomic)
                os.replace(temp_path, config_path)
                temp_path = None  # Rename succeeded, don't clean up

                logger.info(f"Saved config to {config_path} (atomic)")
                return True

            except Exception as e:
                # Clean up temp file on error
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise

        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False

        finally:
            # Release file lock
            if lock_file:
                try:
                    if HAS_FCNTL:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                except Exception:
                    pass

    def _create_backup(self) -> Optional[str]:
        """Create a timestamped backup of current config."""
        try:
            backup_dir = self._get_path(self.BACKUP_DIR)
            backup_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"config_{timestamp}.yaml"
            backup_path = backup_dir / backup_filename

            config_path = self._get_path(self.CONFIG_PATH)
            shutil.copy2(config_path, backup_path)

            logger.info(f"Created backup: {backup_path}")

            # Cleanup old backups
            self._cleanup_old_backups()

            return str(backup_path)

        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return None

    def _cleanup_old_backups(self):
        """Remove old backups exceeding MAX_BACKUPS."""
        try:
            backup_dir = self._get_path(self.BACKUP_DIR)
            if not backup_dir.exists():
                return

            backups = sorted(
                backup_dir.glob("config_*.yaml"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )

            for old_backup in backups[self.MAX_BACKUPS:]:
                old_backup.unlink()
                logger.debug(f"Removed old backup: {old_backup}")

        except Exception as e:
            logger.error(f"Error cleaning up backups: {e}")

    def get_backup_history(self, limit: int = 20) -> List[ConfigBackup]:
        """Get list of available backups."""
        backups = []
        backup_dir = self._get_path(self.BACKUP_DIR)

        if not backup_dir.exists():
            return backups

        for backup_file in sorted(
            backup_dir.glob("config_*.yaml"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:limit]:
            backups.append(ConfigBackup(
                id=backup_file.stem,
                filename=backup_file.name,
                timestamp=backup_file.stat().st_mtime,
                size=backup_file.stat().st_size
            ))

        return backups

    def restore_backup(self, backup_id: str) -> bool:
        """
        Restore config from a backup.

        Args:
            backup_id: Backup ID (filename without extension)

        Returns:
            True if successful
        """
        try:
            backup_dir = self._get_path(self.BACKUP_DIR)
            backup_path = backup_dir / f"{backup_id}.yaml"

            if not backup_path.exists():
                logger.error(f"Backup not found: {backup_path}")
                return False

            # Create backup of current config before restore
            self._create_backup()

            # Load backup using ruamel.yaml
            yaml_loader = YAML()
            yaml_loader.preserve_quotes = True
            with open(backup_path, 'r', encoding='utf-8') as f:
                loaded = yaml_loader.load(f)
                self._config = dict(loaded) if loaded else {}
                self._config_raw = loaded

            # Save as current config
            self.save_config(backup=False)

            logger.info(f"Restored config from backup: {backup_id}")
            return True

        except Exception as e:
            logger.error(f"Error restoring backup: {e}")
            return False

    # =========================================================================
    # Diff & Comparison
    # =========================================================================

    def get_diff(self, config1: Dict, config2: Dict) -> List[DiffEntry]:
        """
        Get differences between two configs.

        Args:
            config1: First config
            config2: Second config

        Returns:
            List of differences
        """
        diffs = []

        all_sections = set(config1.keys()) | set(config2.keys())

        for section in all_sections:
            section1 = config1.get(section, {})
            section2 = config2.get(section, {})

            if not isinstance(section1, dict):
                section1 = {'_value': section1} if section1 is not None else {}
            if not isinstance(section2, dict):
                section2 = {'_value': section2} if section2 is not None else {}

            all_params = set(section1.keys()) | set(section2.keys())

            for param in all_params:
                val1 = section1.get(param)
                val2 = section2.get(param)

                if val1 is None and val2 is not None:
                    diffs.append(DiffEntry(
                        path=f"{section}.{param}",
                        section=section,
                        parameter=param,
                        old_value=None,
                        new_value=val2,
                        change_type='added'
                    ))
                elif val1 is not None and val2 is None:
                    diffs.append(DiffEntry(
                        path=f"{section}.{param}",
                        section=section,
                        parameter=param,
                        old_value=val1,
                        new_value=None,
                        change_type='removed'
                    ))
                elif val1 != val2:
                    diffs.append(DiffEntry(
                        path=f"{section}.{param}",
                        section=section,
                        parameter=param,
                        old_value=val1,
                        new_value=val2,
                        change_type='changed'
                    ))

        return diffs

    def get_changed_from_default(self) -> List[DiffEntry]:
        """Get parameters that differ from defaults."""
        return self.get_diff(self._default, self._config)

    def diff_with_default(self, section: Optional[str] = None) -> List[DiffEntry]:
        """Get diff between current config and defaults."""
        if section:
            return self.get_diff(
                {section: self._default.get(section, {})},
                {section: self._config.get(section, {})}
            )
        return self.get_diff(self._default, self._config)

    # =========================================================================
    # Import/Export
    # =========================================================================

    def export_config(
        self,
        sections: Optional[List[str]] = None,
        changes_only: bool = False
    ) -> Dict:
        """
        Export configuration.

        Args:
            sections: Optional list of sections to export (None = all)
            changes_only: Only export values that differ from defaults

        Returns:
            Config dict for export
        """
        if changes_only:
            # Build config with only changed values
            export_config = {}
            diffs = self.get_changed_from_default()

            for diff in diffs:
                if sections and diff.section not in sections:
                    continue
                if diff.section not in export_config:
                    export_config[diff.section] = {}
                export_config[diff.section][diff.parameter] = diff.new_value

            return export_config

        if sections:
            return {s: self._config.get(s, {}) for s in sections}

        return self._config.copy()

    def import_config(
        self,
        data: Dict,
        merge_mode: str = 'merge'
    ) -> Tuple[bool, List[DiffEntry]]:
        """
        Import configuration data.

        Args:
            data: Config data to import
            merge_mode: 'merge' (update existing) or 'replace' (full replacement)

        Returns:
            Tuple of (success, list of changes made)
        """
        try:
            # Calculate diff before import
            diffs = self.get_diff(self._config, data)

            if merge_mode == 'replace':
                self._config = data.copy()
            else:  # merge
                for section, section_data in data.items():
                    if section not in self._config:
                        self._config[section] = {}

                    if isinstance(section_data, dict):
                        for param, value in section_data.items():
                            self._config[section][param] = value
                    else:
                        self._config[section] = section_data

            logger.info(f"Imported config with mode={merge_mode}, changes={len(diffs)}")
            return True, diffs

        except Exception as e:
            logger.error(f"Error importing config: {e}")
            return False, []

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_reload_tier(self, section: str, param: str) -> str:
        """
        Get the reload tier for a parameter.

        Tiers:
        - 'immediate': Takes effect immediately after Parameters.reload_config()
        - 'follower_restart': Requires follower restart to take effect
        - 'tracker_restart': Requires tracker restart to take effect
        - 'system_restart': Requires full system restart

        Returns:
            Reload tier string, defaults to 'system_restart' for safety
        """
        param_schema = self.get_parameter_schema(section, param)
        if param_schema:
            return param_schema.get('reload_tier', 'system_restart')
        return 'system_restart'

    def is_reboot_required(self, section: str, param: str) -> bool:
        """
        Check if a parameter requires system restart.

        DEPRECATED: Use get_reload_tier() for more granular control.
        This method is kept for backward compatibility.
        """
        tier = self.get_reload_tier(section, param)
        return tier == 'system_restart'

    def get_reload_message(self, reload_tier: str) -> str:
        """Get user-friendly message for reload tier."""
        messages = {
            'immediate': 'Changes applied immediately',
            'follower_restart': 'Restart follower to apply changes',
            'tracker_restart': 'Restart tracker to apply changes',
            'system_restart': 'System restart required to apply changes'
        }
        return messages.get(reload_tier, 'Unknown reload tier')

    def search_parameters(
        self,
        query: str,
        section: Optional[str] = None,
        param_type: Optional[str] = None,
        modified_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> Dict:
        """
        Search for parameters matching a query with filtering and pagination.

        Args:
            query: Search string
            section: Filter by section name
            param_type: Filter by parameter type (integer, float, boolean, etc.)
            modified_only: Only return parameters that differ from default
            limit: Max results to return
            offset: Skip first N results

        Returns:
            Dict with 'results', 'total', 'limit', 'offset'
        """
        all_results = []
        query_lower = query.lower() if query else ''

        for section_name, section_data in self._schema.get('sections', {}).items():
            # Section filter
            if section and section_name != section:
                continue

            for param_name, param_data in section_data.get('parameters', {}).items():
                # Type filter
                if param_type and param_data.get('type') != param_type:
                    continue

                current_value = self.get_parameter(section_name, param_name)
                default_value = self.get_default_parameter(section_name, param_name)

                # Modified-only filter
                if modified_only and current_value == default_value:
                    continue

                # Search in param name and description
                if query_lower and not (
                    query_lower in param_name.lower() or
                    query_lower in param_data.get('description', '').lower()
                ):
                    continue

                all_results.append({
                    'section': section_name,
                    'parameter': param_name,
                    'description': param_data.get('description', ''),
                    'type': param_data.get('type', 'any'),
                    'current_value': current_value,
                    'default_value': default_value,
                    'is_modified': current_value != default_value
                })

        total = len(all_results)
        paginated = all_results[offset:offset + limit]

        return {
            'results': paginated,
            'total': total,
            'limit': limit,
            'offset': offset
        }
