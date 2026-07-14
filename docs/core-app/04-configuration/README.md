# Configuration System

PixEagle uses a schema-driven YAML configuration system with validation, backup, and audit capabilities.

## File Structure

```
configs/
├── config_schema.yaml    # Schema definitions
├── config_default.yaml   # Default values
├── config_retirements.yaml # Exact versioned removal authority
├── config.yaml           # Active configuration
├── config_sync_meta.json # Defaults baseline and applied retirement IDs
├── config.lock           # File lock (runtime)
├── audit_log.json        # Change history
└── backups/              # Auto-backups
    ├── config_20240101_120000.yaml
    └── ...
```

## Schema-Driven Configuration

### Schema Definition

```yaml
# configs/config_schema.yaml

categories:
  tracking:
    display_name: "Tracking"
    icon: "target"

  video:
    display_name: "Video"
    icon: "video"

sections:
  tracker:
    display_name: "Tracker Settings"
    category: tracking
    icon: "crosshair"
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
        step: 0.05
```

### Parameter Properties

| Property | Type | Description |
|----------|------|-------------|
| `type` | string | `integer`, `float`, `boolean`, `string`, `array`, `object` |
| `description` | string | Human-readable description |
| `default` | any | Default value |
| `min` | number | Hard minimum (validation error if exceeded) |
| `max` | number | Hard maximum (validation error if exceeded) |
| `recommended_min` | number | Soft minimum (warning only, save still allowed) |
| `recommended_max` | number | Soft maximum (warning only, save still allowed) |
| `step` | number | UI increment step |
| `unit` | string | Unit label (e.g., `deg`, `m/s`, `px`, `fps`) |
| `options` | array | Dropdown options: `[{value, label, description?}]` |
| `reload_tier` | string | When changes take effect (see [Hot-Reload Guide](hot-reload-guide.md)) |
| `reboot_required` | boolean | Whether a system restart is needed |

### Dropdown Options

Parameters with an `options` field render as dropdowns in the dashboard. Options are auto-extracted from YAML comments or manually defined in `SCHEMA_OVERRIDES`:

```yaml
# Auto-extracted from comment:
VIDEO_SOURCE_TYPE: VIDEO_FILE   # Options: VIDEO_FILE, USB_CAMERA, RTSP, UDP

# Manual override in generate_schema.py:
FRAME_ROTATION_DEG: 0           # Options: 0, 90, 180, 270
```

Comment patterns recognized by the schema generator:
- `Options: val1, val2, val3` (comma-separated)
- `Options: val1 | val2 | val3` (pipe-separated)
- `Allowed: val1, val2, val3` (same as Options:)
- `val1 or val2 or val3` for string/integer selector parameters only
- `"val1" - desc "val2" - desc` (quoted with descriptions)

Free-form prose on numeric parameters is never inferred as an enum. Define
ambiguous selector options explicitly in `SCHEMA_OVERRIDES`.

### Recommended Ranges (Soft Validation)

Some parameters have recommended ranges alongside hard limits. Values outside the recommended range trigger warnings but save normally:

```yaml
SMART_TRACKER_CONFIDENCE_THRESHOLD:
  type: float
  min: 0.0               # Hard limit (error)
  max: 1.0               # Hard limit (error)
  recommended_min: 0.15   # Soft limit (warning)
  recommended_max: 0.7    # Soft limit (warning)
```

Recommended ranges are defined in `RECOMMENDED_RANGES` dict in `scripts/generate_schema.py`.

### Schema Overrides

For parameters where comment parsing is ambiguous, manual overrides in `SCHEMA_OVERRIDES` take highest priority:

```python
# scripts/generate_schema.py
SCHEMA_OVERRIDES = {
    'VideoSource.FRAME_ROTATION_DEG': {
        'options': [...],
        'min': 0, 'max': 270, 'unit': 'deg',
    },
}
```

### Reload Tiers (v5.3.0+)

| Tier | Description |
|------|-------------|
| `immediate` | Changes apply instantly after save |
| `follower_restart` | Requires follower restart |
| `tracker_restart` | Requires tracker restart |
| `system_restart` | Requires full system restart |

## Configuration Files

### config_default.yaml

Default values - never modified at runtime:

```yaml
# Video settings
video:
  source: 0
  target_fps: 30
  flip_horizontal: false
  flip_vertical: false

# Tracker settings
tracker:
  type: "smart"
  confidence_threshold: 0.5

# HTTP server / stream settings
Streaming:
  API_EXPOSURE_MODE: local_only
  HTTP_STREAM_HOST: 127.0.0.1
  HTTP_STREAM_PORT: 5077
  STREAM_FPS: 30
  STREAM_QUALITY: 85
```

### config.yaml

Active configuration - modified via API:

```yaml
# User customizations
video:
  source: "rtsp://camera.local/stream"
  target_fps: 25

tracker:
  confidence_threshold: 0.7
```

## Using ConfigService

### Reading Configuration

```python
from classes.config_service import ConfigService

# Get singleton instance
config = ConfigService.get_instance()

# Read full config
all_config = config.get_config()

# Read section
tracker_config = config.get_config('tracker')

# Read parameter
threshold = config.get_parameter('tracker', 'confidence_threshold')

# Get default value
default = config.get_default_parameter('tracker', 'confidence_threshold')
```

### Writing Configuration

```python
# Set parameter (validates against schema)
result = config.set_parameter('tracker', 'confidence_threshold', 0.8)

if result.valid:
    config.save_config()  # Persist to disk
else:
    print(f"Errors: {result.errors}")

# Set multiple parameters
result = config.set_section('tracker', {
    'confidence_threshold': 0.8,
    'type': 'csrt'
})
```

### Validation

```python
# Validate a value
result = config.validate_value('tracker', 'confidence_threshold', 1.5)

print(result.valid)      # False
print(result.errors)     # ['Value 1.5 is above maximum 1.0']
print(result.warnings)   # []
```

### Diff Comparison

```python
# Get changes from default
diffs = config.get_changed_from_default()

for diff in diffs:
    print(f"{diff.path}: {diff.old_value} → {diff.new_value}")
```

### Backup/Restore

```python
# List backups
backups = config.get_backup_history(limit=10)

for backup in backups:
    print(f"{backup.id}: {backup.timestamp}")

# Restore a backup
config.restore_backup('config_20240101_120000')
```

### Import/Export

```python
# Export (changes only)
exported = config.export_config(changes_only=True)

# Export specific sections
exported = config.export_config(sections=['tracker', 'follower'])

# Import
success, diffs = config.import_config(
    data=imported_config,
    merge_mode='merge'  # or 'replace'
)
```

## REST API

### Read Configuration

```bash
# Get current config
curl http://127.0.0.1:5077/api/config/current

# Get section
curl http://127.0.0.1:5077/api/config/current/tracker

# Get schema
curl http://127.0.0.1:5077/api/config/schema
```

### Update Configuration

```bash
# Update parameter
curl -X PUT http://127.0.0.1:5077/api/config/tracker/confidence_threshold \
  -H "Content-Type: application/json" \
  -d '{"value": 0.8}'
```

### Revert to Default

```bash
# Revert parameter
curl -X POST http://127.0.0.1:5077/api/config/revert/tracker/confidence_threshold

# Revert section
curl -X POST http://127.0.0.1:5077/api/config/revert/tracker

# Revert all
curl -X POST http://127.0.0.1:5077/api/config/revert
```

## Audit Logging

All configuration changes are logged:

```json
// configs/audit_log.json
[
  {
    "timestamp": "2024-01-01T12:00:00",
    "action": "update",
    "section": "tracker",
    "parameter": "confidence_threshold",
    "old_value": 0.5,
    "new_value": 0.8,
    "source": "api"
  }
]
```

### Query Audit Log

```python
log = config.get_audit_log(
    limit=100,
    section='tracker',
    action='update'
)
```

## File Safety

### Atomic Writes

Configuration changes use atomic writes:
1. Write to temporary file
2. Flush and sync to disk
3. Atomic rename to target
4. Sync the containing directory where supported

### File Locking

Config mutations use an in-process reentrant lock plus advisory `flock` on
POSIX or `msvcrt.locking` on Windows. Exact-byte digests reject stale plans and
cooperating concurrent writes. External tools must honor the lock or use the
PixEagle API; no advisory lock can constrain a process that ignores it.

POSIX state files are mode `0600` and backup directories are `0700`. Windows
state removes inherited ACLs and grants the current user SID plus LocalSystem
and local Administrators for recovery.

### Automatic Backups

Before a destructive save, a collision-safe owner-only backup is required. Old
backups are cleaned up (keeps the latest 20). Config Sync removes only paths in
`config_retirements.yaml`; unknown local extensions are preserved. See
[Config Sync](../../CONFIG_SYNC.md).

Each file replace is atomic. Multi-file config-sync apply is a process-level
transaction: exact config/metadata/audit bytes and managed backup inventory are
captured first and restored if persistence, strict `Parameters` reload,
`SafetyManager`, `FollowerConfigManager`, or audit completion fails. Both
legacy second-resolution backup IDs and current collision-safe IDs remain
restorable.

Strict reload prepares the complete replacement state before entering one
runtime publication barrier. It then installs `Parameters`, `SafetyManager`,
and `FollowerConfigManager` as one generation. Failed publication restores the
previous in-memory state and leaves the generation unchanged; application
startup also uses this strict fail-closed path. Compound runtime readers should
hold `Parameters.read_generation()` while reading several config values.

Production publication requires every canonical `Safety.GlobalLimits` field.
Null, coercive, non-finite, unknown, and contradictory safety values are
rejected. Sparse follower overrides are permitted only when their resolved
effective limits remain valid. Guarded API writes also hold the follower-state
barrier and durably append their redacted audit record before publishing the
new runtime generation.

## Related Documentation

- [ConfigService Component](../02-components/config-service.md)
- [Hot-Reload Guide](hot-reload-guide.md)
- [API Reference](../03-api/README.md)
