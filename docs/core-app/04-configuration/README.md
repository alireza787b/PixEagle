# Configuration System

PixEagle uses a schema-driven YAML configuration system with validation, backup, and audit capabilities.

## File Structure

```
configs/
├── config_schema.yaml    # Schema definitions
├── config_default.yaml   # Default values
├── config.yaml           # Active configuration
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
| `min` | number | Minimum value (numeric types) |
| `max` | number | Maximum value (numeric types) |
| `step` | number | UI increment step |
| `reboot_required` | boolean | Requires restart to apply |

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

# HTTP server
http:
  host: "0.0.0.0"
  port: 8000
  stream_fps: 30
  stream_quality: 85
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
curl http://localhost:8000/api/config/current

# Get section
curl http://localhost:8000/api/config/current/tracker

# Get schema
curl http://localhost:8000/api/config/schema
```

### Update Configuration

```bash
# Update parameter
curl -X PUT http://localhost:8000/api/config/tracker/confidence_threshold \
  -H "Content-Type: application/json" \
  -d '{"value": 0.8}'
```

### Revert to Default

```bash
# Revert parameter
curl -X POST http://localhost:8000/api/config/revert/tracker/confidence_threshold

# Revert section
curl -X POST http://localhost:8000/api/config/revert/tracker

# Revert all
curl -X POST http://localhost:8000/api/config/revert
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

### File Locking

On Unix systems, `fcntl` file locking prevents concurrent writes.

### Automatic Backups

Before each save, a timestamped backup is created. Old backups are cleaned up (keeps last 20).

## Related Documentation

- [ConfigService Component](../02-components/config-service.md)
- [API Reference](../03-api/README.md)
