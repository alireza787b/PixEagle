# ConfigService

Schema-driven configuration management with persistence, validation, and audit logging.

## Overview

`ConfigService` (`src/classes/config_service.py`) provides:

- YAML configuration persistence with comment preservation
- Schema-based validation
- Diff comparison between configs
- Backup and restore functionality
- Versioned defaults baselines and exact retirement registry validation
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
│  │  ├── config_retirements.yaml (Exact removals)        │   │
│  │  ├── config.yaml          (Active config)            │   │
│  │  ├── config_sync_meta.json (Defaults baseline)       │   │
│  │  ├── config.lock          (POSIX/Windows advisory lock)│  │
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
with service.mutation_guard():
    source_digest = service.get_source_state_digests()["runtime_config"]
    if not service.save_config(
        backup=True,
        lock_acquired=True,
        expected_config_digest=source_digest,
    ):
        raise RuntimeError("Config persistence failed")
```

`save_config()` requires the backup when requested, writes an owner-only
same-directory temporary file, flushes and syncs it, atomically replaces the
target, and syncs the directory where supported.

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
backup_path = service.create_backup()
if backup_path is None:
    raise RuntimeError("Required backup was not created")
```

Backup names combine a microsecond timestamp and a unique temporary-file
suffix. The backup directory is mode `0700`; backup files are mode `0600`.
Creation is durable before a destructive config replacement proceeds, and the
latest `MAX_BACKUPS` files are retained.

History and restore accept both current collision-safe IDs such as
`config_20260713_120000_123456_ab12cd` and legacy IDs such as
`config_20240101_120000`. Only regular, non-symlink files matching those exact
formats are exposed.

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

# Defaults/retirement migration (legacy compatibility surface)
GET  /api/config/defaults-sync
POST /api/config/defaults-sync/plan
POST /api/config/defaults-sync/apply
```

Defaults-sync reads are side-effect free. Apply requires the opaque
process-local preview token returned in the `plan_digest` field, explicit
confirmation, and an exact path in
`configs/config_retirements.yaml` for removal. See
[Config Sync](../../CONFIG_SYNC.md).

The compatibility API uses strict contract v2 canonical `path` arrays. Config
writes use compare-and-swap disk digests, owner-restricted state, strict
dependent-manager reload, redacted audit entries, and process-level rollback.
Internal source fingerprints never enter the public plan response, and a
backend restart invalidates outstanding preview tokens. Rollback restores only
artifacts written by the failed transaction whose current fingerprints still
match the exact service-issued write receipt. CAS is rechecked immediately
before replacement. Receipt ownership is recorded immediately after atomic
replacement, before final permission and directory-durability checks, so those
post-replace failures cannot escape rollback ownership. Detected
non-cooperating edits are preserved and produce
an operator-recovery error. Because the final check/replace pair is not a
portable atomic compare-and-swap against writers that ignore the advisory lock,
managed config files must not be edited directly while the service is running.
All blocking config transactions are dispatched as one unit to a worker thread;
their lock entry and exit never cross threads and do not block the ASGI loop.
The AppController follower-state barrier surrounds each mutation, and the
durable audit write precedes runtime publication. A missing state barrier or a
failed audit therefore refuses or rolls back the change instead of leaving an
active unaudited generation.

`merge` import overlays the current config. `replace` import overlays the
supplied document on checked-in defaults, drops prior local extensions, then
strictly validates the complete candidate; sparse input cannot delete required
runtime sections.

## Reload Tier System (v5.3.0+)

Parameters support hot-reload tiers for granular restart control:

### Get Reload Tier

```python
def get_reload_tier(self, section: str, param: str) -> str:
    """
    Get reload tier for a parameter.

    Returns:
        One of: 'immediate', 'follower_restart', 'tracker_restart', 'system_restart'
    """
    param_schema = self.get_parameter_schema(section, param)
    if param_schema:
        return param_schema.get('reload_tier', 'system_restart')
    return 'system_restart'  # Safe default
```

### Get Reload Message

```python
def get_reload_message(self, reload_tier: str) -> str:
    """
    Get user-friendly message for reload tier.

    Returns:
        Human-readable message describing when changes take effect
    """
    messages = {
        'immediate': 'Changes applied immediately',
        'follower_restart': 'Restart follower to apply changes',
        'tracker_restart': 'Restart tracker to apply changes',
        'system_restart': 'System restart required to apply changes'
    }
    return messages.get(reload_tier, 'Unknown reload tier')
```

### Legacy Compatibility

```python
def is_reboot_required(self, section: str, param: str) -> bool:
    """
    DEPRECATED: Use get_reload_tier() for more granular control.

    Returns True only for system_restart tier.
    """
    tier = self.get_reload_tier(section, param)
    return tier == 'system_restart'
```

See [Hot-Reload Guide](../04-configuration/hot-reload-guide.md) for complete documentation.

## Thread Safety

- Config transactions use an in-process reentrant lock plus an advisory file
  lock (`flock` on POSIX, `msvcrt.locking` on Windows).
- Exact-byte compare-and-swap digests reject stale previews and external
  cooperating-writer races.
- Conditional rollback restores only transaction-owned fingerprints. It
  preserves detected external edits that bypass the advisory lock and reports
  the resulting recovery requirement. Operators must stop PixEagle or use its
  mutation API/tooling rather than bypassing the lock.
- Blocking lock, YAML, backup, sync, reload, and rollback work is dispatched as
  one worker-thread operation from async routes; lock ownership never crosses
  threads.
- Strict runtime reload prepares all dependent state, then publishes
  `Parameters`, `SafetyManager`, and `FollowerConfigManager` behind one shared
  generation barrier. Readers cannot observe an in-progress mixed generation.
- Public schema/config/default getters and recursive redaction/search helpers
  use the same in-process lock and return defensive snapshots. Standalone
  in-memory section/import mutations are atomic to those readers.

## Related Components

- [FastAPIHandler](fastapi-handler.md) - Exposes config API
- [SchemaManager](schema-manager.md) - Tracker schemas
- [Hot-Reload Guide](../04-configuration/hot-reload-guide.md) - Reload tier system
