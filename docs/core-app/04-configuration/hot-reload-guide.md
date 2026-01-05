# Hot-Reload Configuration Guide

PixEagle v5.3.0 introduces a tiered configuration hot-reload system that allows many settings to take effect without a full system restart.

## Overview

Configuration parameters are classified into four **reload tiers** based on when changes take effect:

| Tier | Label | Description | Action Required |
|------|-------|-------------|-----------------|
| `immediate` | Instant | Changes apply immediately after save | None |
| `follower_restart` | Follower | Requires follower component restart | Restart follower |
| `tracker_restart` | Tracker | Requires tracker component restart | Restart tracker |
| `system_restart` | Reboot | Requires full system restart | Reboot system |

## How It Works

### Immediate Tier

Parameters marked as `immediate` use hot-reload through `Parameters.reload_config()`:

1. User saves a parameter value via API or dashboard
2. ConfigService validates and persists the change
3. `Parameters.reload_config()` is called automatically
4. All class attributes are refreshed from disk
5. SafetyManager is notified to reload safety limits
6. Changes take effect immediately

**Example immediate parameters:**
- Display colors and visual settings
- OSD font sizes and positions
- Logging levels
- Non-critical thresholds

### Follower Restart Tier

Parameters marked as `follower_restart` require the follower component to restart:

1. User saves a parameter value
2. Dashboard shows "Restart follower to apply"
3. User clicks restart button or starts new follow session
4. Follower reinitializes with fresh configuration

**Example follower_restart parameters:**
- Follower mode settings
- PID gains (within safety limits)
- Control loop parameters
- Velocity limits

**API Endpoint:**
```bash
POST /api/follower/restart
```

### Tracker Restart Tier

Parameters marked as `tracker_restart` require the tracker component to restart:

1. User saves a parameter value
2. Dashboard shows "Restart tracker to apply"
3. User clicks restart button or switches tracker type
4. Tracker reinitializes with fresh configuration

**Example tracker_restart parameters:**
- Tracker algorithm settings
- Detection thresholds
- ROI parameters
- Model configurations

**API Endpoint:**
```bash
POST /api/tracker/restart
```

### System Restart Tier

Parameters marked as `system_restart` require a full application restart:

**Example system_restart parameters:**
- Video source type
- Network ports
- Hardware interfaces
- Core system parameters

## Dashboard UI

### Reload Tier Badges

Each parameter displays a badge indicating its reload tier:

- 🟢 **Instant** - Green badge with checkmark
- 🟡 **Follower** - Yellow badge with airplane icon
- 🟡 **Tracker** - Yellow badge with crosshair icon
- 🔴 **Reboot** - Red badge with warning icon

### Restart Notifications

When you save a parameter that requires restart:

1. The dashboard shows a notification with the reload message
2. A restart button appears if applicable
3. You can continue making changes before restarting
4. Multiple changes accumulate - restart once for all

## API Response

When updating parameters via API, the response includes reload tier information:

```json
{
  "success": true,
  "saved": true,
  "applied": true,
  "reload_tier": "follower_restart",
  "reload_message": "Restart follower to apply changes",
  "reboot_required": false
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `applied` | boolean | True if hot-reload was successful |
| `reload_tier` | string | The parameter's reload tier |
| `reload_message` | string | User-friendly message |
| `reboot_required` | boolean | Legacy field (true only for system_restart) |

## ConfigService Methods

### Get Reload Tier

```python
from classes.config_service import ConfigService

config = ConfigService.get_instance()

# Get reload tier for a parameter
tier = config.get_reload_tier('Follower', 'MAX_VELOCITY')
# Returns: 'follower_restart'
```

### Get Reload Message

```python
# Get user-friendly message
message = config.get_reload_message('tracker_restart')
# Returns: 'Restart tracker to apply changes'
```

### Legacy Compatibility

The `is_reboot_required()` method is still available for backward compatibility:

```python
# Returns True only for system_restart tier
needs_reboot = config.is_reboot_required('VideoSource', 'VIDEO_SOURCE_TYPE')
```

## Schema Definition

In `config_schema.yaml`, set reload tier per parameter:

```yaml
sections:
  Follower:
    parameters:
      MAX_VELOCITY:
        type: float
        default: 5.0
        reload_tier: follower_restart  # Options: immediate, follower_restart, tracker_restart, system_restart

      POSITION_DISPLAY_COLOR:
        type: array
        default: [0, 255, 0]
        reload_tier: immediate
```

## Best Practices

### For Developers

1. **Default to safe tier**: If unsure, use `system_restart`
2. **Test hot-reload**: Verify changes work without restart
3. **Consider dependencies**: Parameters that affect initialization should not be `immediate`
4. **Document side effects**: Note any caveats in parameter descriptions

### For Operators

1. **Batch changes**: Make multiple changes before restarting
2. **Check tier before editing**: Know what restart is required
3. **Use restart buttons**: Prefer UI buttons over manual restart
4. **Monitor logs**: Watch for reload success/failure messages

## Thread Safety

The hot-reload system is thread-safe:

- `Parameters.reload_config()` uses a thread lock
- Multiple concurrent reloads are serialized
- SafetyManager notifications are protected
- No race conditions on class attribute updates

## Error Handling

If hot-reload fails:

1. Config change is still saved to disk
2. `applied` field is `false` in response
3. Error is logged with full traceback
4. Original values remain in memory
5. System continues operating (no crash)

On next proper restart, the saved config will be loaded.

## Related Documentation

- [Configuration System](README.md)
- [ConfigService Component](../02-components/config-service.md)
- [API Reference](../03-api/README.md)
