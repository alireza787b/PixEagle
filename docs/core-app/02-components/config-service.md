# ConfigService

Schema-driven configuration management with persistence, validation, and audit logging.

## Overview

`ConfigService` (`src/classes/config_service.py`) provides:

- YAML configuration persistence with comment preservation
- Schema-based validation
- Diff comparison between configs
- Backup and restore functionality
- Import/export capabilities
- Audit logging for changes

## Class Definition

```python
class ConfigService:
    """
    Singleton service for schema-driven configuration management.

    Features:
    - Schema loading and parameter metadata
    - Config CRUD operations with validation
    - Backup and restore
    - Diff comparison between configs
    - Import/export functionality
    """
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      ConfigService                           │
│                        (Singleton)                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  File Structure                                       │   │
│  │  configs/                                             │   │
│  │  ├── config_schema.yaml   (Schema definitions)       │   │
│  │  ├── config_default.yaml  (Default values)           │   │
│  │  ├── config.yaml          (Active config)            │   │
│  │  ├── config.lock          (File lock)                │   │
│  │  ├── audit_log.json       (Change history)           │   │
│  │  └── backups/             (Auto-backups)             │   │
│  │      ├── config_20240101_120000.yaml                 │   │
│  │      └── ...                                          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Singleton Pattern

```python
class ConfigService:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'ConfigService':
        """Get singleton instance of ConfigService."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
```

## Schema System

### Schema Structure

```yaml
# configs/config_schema.yaml
categories:
  tracking:
    display_name: "Tracking"
    icon: "target"

sections:
  tracker:
    display_name: "Tracker Settings"
    category: tracking
    parameters:
      type:
        type: string
        description: "Tracker type to use"
        default: "smart"
        reboot_required: true

      confidence_threshold:
        type: float
        description: "Minimum confidence for detection"
        default: 0.5
        min: 0.0
        max: 1.0
```

### Validation

```python
def validate_value(self, section: str, param: str, value: Any) -> ValidationResult:
    """
    Validate a value against its schema.

    Returns:
        ValidationResult with status, errors, and warnings
    """
    param_schema = self.get_parameter_schema(section, param)

    errors = []
    warnings = []

    # Type validation
    expected_type = param_schema.get('type')
    if expected_type == 'integer':
        if not isinstance(value, int):
            errors.append(f"Expected integer, got {type(value).__name__}")
        elif 'min' in param_schema and value < param_schema['min']:
            errors.append(f"Value below minimum {param_schema['min']}")

    # Check reboot requirement
    if param_schema.get('reboot_required', False):
        warnings.append("Restart required for this change")

    return ValidationResult(
        valid=len(errors) == 0,
        status=ValidationStatus.ERROR if errors else ValidationStatus.VALID,
        errors=errors,
        warnings=warnings
    )
```

## CRUD Operations

### Read Configuration

```python
# Get full config
config = service.get_config()

# Get section
tracker_config = service.get_config('tracker')

# Get specific parameter
threshold = service.get_parameter('tracker', 'confidence_threshold')
```

### Update Configuration

```python
# Set single parameter
result = service.set_parameter('tracker', 'confidence_threshold', 0.7)

if result.valid:
    service.save_config()  # Persist to disk
else:
    print(f"Validation errors: {result.errors}")

# Set multiple parameters
result = service.set_section('tracker', {
    'confidence_threshold': 0.7,
    'type': 'csrt'
})
```

### Revert to Default

```python
# Revert single parameter
service.revert_to_default('tracker', 'confidence_threshold')

# Revert entire section
service.revert_to_default('tracker')

# Revert everything
service.revert_to_default()
```

## Persistence

### Atomic Writes

```python
def save_config(self, backup: bool = True) -> bool:
    """
    Save config with atomic writes and file locking.

    Process:
    1. Acquire file lock
    2. Write to temporary file
    3. Flush and sync to disk
    4. Atomic rename to target
    5. Release lock
    """
    # Acquire lock
    if HAS_FCNTL:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

    # Write to temp file
    with tempfile.NamedTemporaryFile(...) as f:
        yaml.dump(config, f)
        f.flush()
        os.fsync(f.fileno())

    # Atomic rename
    os.replace(temp_path, config_path)
```

### Comment Preservation

Uses `ruamel.yaml` for round-trip YAML handling:

```python
from ruamel.yaml import YAML

yaml = YAML()
yaml.preserve_quotes = True

# Load preserving comments
with open(config_path) as f:
    config = yaml.load(f)

# Modify
config['tracker']['threshold'] = 0.7

# Save with comments intact
with open(config_path, 'w') as f:
    yaml.dump(config, f)
```

## Backup System

### Create Backup

```python
def _create_backup(self) -> Optional[str]:
    """Create timestamped backup."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"config_{timestamp}.yaml"
    backup_path = backup_dir / backup_filename

    shutil.copy2(config_path, backup_path)

    # Cleanup old backups (keep MAX_BACKUPS)
    self._cleanup_old_backups()

    return str(backup_path)
```

### Restore Backup

```python
def restore_backup(self, backup_id: str) -> bool:
    """Restore config from backup."""
    backup_path = backup_dir / f"{backup_id}.yaml"

    # Create backup of current config first
    self._create_backup()

    # Load backup
    with open(backup_path) as f:
        self._config = yaml.load(f)

    # Save as current
    self.save_config(backup=False)
```

### List Backups

```python
def get_backup_history(self, limit: int = 20) -> List[ConfigBackup]:
    """Get list of available backups."""
    backups = []
    for backup_file in sorted(backup_dir.glob("config_*.yaml")):
        backups.append(ConfigBackup(
            id=backup_file.stem,
            filename=backup_file.name,
            timestamp=backup_file.stat().st_mtime,
            size=backup_file.stat().st_size
        ))
    return backups[:limit]
```

## Diff Comparison

```python
def get_diff(self, config1: Dict, config2: Dict) -> List[DiffEntry]:
    """Get differences between two configs."""
    diffs = []

    for section in all_sections:
        for param in all_params:
            val1 = config1.get(section, {}).get(param)
            val2 = config2.get(section, {}).get(param)

            if val1 != val2:
                diffs.append(DiffEntry(
                    path=f"{section}.{param}",
                    section=section,
                    parameter=param,
                    old_value=val1,
                    new_value=val2,
                    change_type='changed' if val1 and val2 else
                                'added' if val2 else 'removed'
                ))

    return diffs

# Get changes from default
diffs = service.get_changed_from_default()
```

## Audit Logging

```python
def log_audit_entry(
    self,
    action: str,
    section: str,
    parameter: Optional[str] = None,
    old_value: Any = None,
    new_value: Any = None,
    source: str = 'api'
):
    """Log config change to audit trail."""
    entry = AuditEntry(
        timestamp=datetime.now().isoformat(),
        action=action,  # 'update', 'import', 'restore', 'revert'
        section=section,
        parameter=parameter,
        old_value=old_value,
        new_value=new_value,
        source=source  # 'api', 'import', 'restore'
    )

    self._audit_log.append(entry.to_dict())
    self._save_audit_log()
```

### Query Audit Log

```python
def get_audit_log(
    self,
    limit: int = 100,
    offset: int = 0,
    section: Optional[str] = None,
    action: Optional[str] = None
) -> Dict:
    """Get audit log with filtering."""
    entries = self._audit_log.copy()

    if section:
        entries = [e for e in entries if e['section'] == section]
    if action:
        entries = [e for e in entries if e['action'] == action]

    return {
        'entries': entries[offset:offset + limit],
        'total': len(entries),
        'limit': limit,
        'offset': offset
    }
```

## Import/Export

```python
# Export config
exported = service.export_config(
    sections=['tracker', 'follower'],  # Optional filter
    changes_only=True  # Only export non-default values
)

# Import config
success, diffs = service.import_config(
    data=imported_config,
    merge_mode='merge'  # or 'replace'
)
```

## API Integration

FastAPIHandler exposes config endpoints:

```python
# Read
GET /api/config/current
GET /api/config/current/{section}
GET /api/config/schema

# Write
PUT /api/config/{section}/{parameter}
PUT /api/config/{section}

# Backup/Restore
GET /api/config/history
POST /api/config/restore/{backup_id}

# Diff
GET /api/config/diff
```

## Thread Safety

- Singleton uses `threading.Lock`
- File operations use `fcntl` locking (Unix)
- Graceful fallback on Windows

## Related Components

- [FastAPIHandler](fastapi-handler.md) - Exposes config API
- [SchemaManager](schema-manager.md) - Tracker schemas
