# Safety Integration

This document covers safety configurations and their integration with the drone interface.

## Overview

PixEagle implements multiple safety layers:

1. **Velocity Limits** - Clamp commands to safe ranges
2. **Circuit Breaker** - Block commands in test mode
3. **Flight Mode Monitoring** - Detect offboard exits
4. **Emergency Actions** - RTL and failsafe triggers

## Velocity Limits

### Configuration

```yaml
# config_default.yaml
Safety:
  GlobalLimits:
    MAX_VELOCITY_FORWARD: 8.0    # m/s
    MAX_VELOCITY_LATERAL: 5.0    # m/s
    MAX_VELOCITY_VERTICAL: 3.0   # m/s
    MAX_YAW_RATE: 45.0           # deg/s
```

### Implementation

SetpointHandler automatically clamps values:

```python
# SetpointHandler._clamp_value()
def set_field(self, name, value):
    clamped_value = self._clamp_value(name, value)
    self.fields[name] = clamped_value

# Example
handler.set_field('vel_body_fwd', 15.0)  # Exceeds limit
fields = handler.get_fields()
# vel_body_fwd = 8.0 (clamped)
```

### Limit Mapping

| Field | Limit Parameter |
|-------|-----------------|
| vel_body_fwd | MAX_VELOCITY_FORWARD |
| vel_body_right | MAX_VELOCITY_LATERAL |
| vel_body_down | MAX_VELOCITY_VERTICAL |
| yawspeed_deg_s | MAX_YAW_RATE |
| thrust | Fixed 0.0-1.0 |

## Circuit Breaker

### Configuration

```yaml
circuit_breaker:
  active: true           # Enable test mode
  log_commands: true     # Log blocked commands
```

### Behavior

When active:
- **Commands**: Logged but not sent to PX4
- **Telemetry**: Still received and processed
- **Safety**: RTL/failsafe still available

### Code Example

```python
from classes.circuit_breaker import FollowerCircuitBreaker

# Check if active
if FollowerCircuitBreaker.is_active():
    # Log instead of send
    FollowerCircuitBreaker.log_command_instead_of_execute(
        command_type="velocity_body",
        follower_name="MCVelocityChaseFollower",
        fields={'vel_body_fwd': 3.0}
    )
```

### Use Cases

- Indoor testing without risk
- Development without drone
- Validating tracking before flight

## Flight Mode Monitoring

### Offboard Exit Detection

MavlinkDataManager monitors flight mode changes:

```python
class MavlinkDataManager:
    OFFBOARD_MODE_CODE = 393216

    def register_offboard_exit_callback(self, callback):
        """Register callback for offboard mode exit."""
        self._offboard_exit_callback = callback

    def _handle_flight_mode_change(self, new_mode):
        if self._was_in_offboard and new_mode != self.OFFBOARD_MODE_CODE:
            self._trigger_offboard_exit_callback()
```

### Common Exit Reasons

| Exit Mode | Code | Cause |
|-----------|------|-------|
| Position | 196608 | RC override or failsafe |
| Hold | 327680 | Manual intervention |
| RTL | 84148224 | Safety trigger |
| Land | 50593792 | Low battery |

## Emergency Actions

### Return to Launch (RTL)

```python
# PX4InterfaceManager
async def trigger_return_to_launch(self):
    """Trigger RTL mode."""
    if FollowerCircuitBreaker.is_active():
        logger.info("RTL blocked by circuit breaker")
        return

    await self.drone.action.return_to_launch()
```

### Failsafe

```python
async def trigger_failsafe(self):
    """Trigger failsafe behavior."""
    await self.drone.action.terminate()
```

## Safety in Command Flow

```
Follower.follow_target()
        │
        ▼
┌───────────────────────┐
│   SetpointHandler     │
│   ├─ Clamp to limits  │
│   └─ Validate types   │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Circuit Breaker     │
│   Check               │
│   ├─ Active: Log only │
│   └─ Inactive: Pass   │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  PX4InterfaceManager  │
│   Send command        │
└───────────────────────┘
```

## Configuration Best Practices

### Development

```yaml
circuit_breaker:
  active: true

Safety:
  GlobalLimits:
    MAX_VELOCITY_FORWARD: 3.0   # Reduced
    MAX_VELOCITY_LATERAL: 2.0
    MAX_VELOCITY_VERTICAL: 1.0
```

### Testing (SITL)

```yaml
circuit_breaker:
  active: false

Safety:
  GlobalLimits:
    MAX_VELOCITY_FORWARD: 5.0
    MAX_VELOCITY_LATERAL: 3.0
    MAX_VELOCITY_VERTICAL: 2.0
```

### Production

```yaml
circuit_breaker:
  active: false

Safety:
  GlobalLimits:
    MAX_VELOCITY_FORWARD: 8.0
    MAX_VELOCITY_LATERAL: 5.0
    MAX_VELOCITY_VERTICAL: 3.0
```

## Status Reporting

SetpointHandler includes safety status:

```python
status = handler.get_fields_with_status()
# {
#   'setpoints': {...},
#   'circuit_breaker': {
#     'active': True,
#     'status': 'SAFE_MODE',
#     'commands_sent_to_px4': False
#   }
# }
```

## Related Documentation

- [PX4 Configuration](px4-config.md)
- [Circuit Breaker Testing](../06-development/testing-without-drone.md)
- [Troubleshooting](../07-troubleshooting/)
