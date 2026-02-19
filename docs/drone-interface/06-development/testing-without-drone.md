# Testing Without a Drone

This guide covers how to test PixEagle's drone interface without a physical drone or SITL.

## Overview

PixEagle provides a **Circuit Breaker** system that blocks commands to PX4 while still allowing:

- Telemetry reception and processing
- Tracker operation
- Follower calculations
- Dashboard operation
- Command logging

## Circuit Breaker Configuration

### Enable Circuit Breaker

```yaml
# config_default.yaml

circuit_breaker:
  active: true           # Block all PX4 commands
  log_commands: true     # Log what would be sent
```

### Configuration Options

| Option | Type | Description |
|--------|------|-------------|
| active | boolean | Enable/disable command blocking |
| log_commands | boolean | Log blocked commands for debugging |

## How It Works

### Command Flow with Circuit Breaker

```
Follower.follow_target()
        │
        ▼
┌───────────────────────┐
│   SetpointHandler     │
│   (Clamping applies)  │
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│   Circuit Breaker     │
│   ├─ Active: LOG      │◄── Commands logged, not sent
│   └─ Inactive: PASS   │
└───────────┬───────────┘
            │
            ▼ (if inactive)
┌───────────────────────┐
│  PX4InterfaceManager  │
│   Send to MAVSDK      │
└───────────────────────┘
```

### What Gets Blocked

| Blocked | Allowed |
|---------|---------|
| Velocity commands | Telemetry polling |
| Attitude commands | REST API responses |
| Position commands | Dashboard updates |
| Arm/Disarm | Tracker processing |
| Offboard start | Follower calculations |

## Using the Circuit Breaker

### In Code

```python
from classes.circuit_breaker import FollowerCircuitBreaker

# Check if active
if FollowerCircuitBreaker.is_active():
    print("Safe mode - commands blocked")

# Log command instead of executing
if FollowerCircuitBreaker.is_active():
    FollowerCircuitBreaker.log_command_instead_of_execute(
        command_type="velocity_body",
        follower_name="MCVelocityChaseFollower",
        fields={
            'vel_body_fwd': 3.0,
            'vel_body_right': 0.0,
            'vel_body_down': 0.0,
            'yawspeed_deg_s': 15.0
        }
    )
```

### Check Status via API

```bash
# Check circuit breaker status
curl http://localhost:8000/api/status/circuit_breaker

# Response
{
  "active": true,
  "commands_blocked": 42,
  "last_blocked": "2024-01-01T12:00:00Z"
}
```

### SetpointHandler Status

```python
from classes.setpoint_handler import SetpointHandler

handler = SetpointHandler('mc_velocity_offboard')
status = handler.get_fields_with_status()

# Output includes circuit breaker info
# {
#   'setpoints': {...},
#   'circuit_breaker': {
#     'active': True,
#     'status': 'SAFE_MODE',
#     'commands_sent_to_px4': False
#   }
# }
```

## Testing Scenarios

### 1. Indoor Development

Test tracker and follower logic without risk:

```yaml
circuit_breaker:
  active: true
  log_commands: true

safety:
  max_velocity_forward: 3.0   # Reduced limits for safety
  max_velocity_lateral: 2.0
  max_velocity_vertical: 1.0
```

**Test Steps:**
1. Start PixEagle with circuit breaker active
2. Run tracker on camera feed
3. Observe follower calculations in logs
4. Verify command values are reasonable

### 2. Validate Before Flight

Verify system behavior before enabling commands:

```bash
# Start with circuit breaker
python main.py  # circuit_breaker.active = true

# Monitor logs
tail -f logs/pixeagle.log | grep "BLOCKED"

# Check command values
curl http://localhost:8000/api/follower/commands
```

**Validation Checklist:**
- [ ] Commands have expected values
- [ ] Safety limits are applied
- [ ] No unexpected spikes
- [ ] Yaw rate is stable
- [ ] Vertical velocity reasonable

### 3. Mock Telemetry Testing

Test with mock telemetry when no MAVLink source:

```python
# In test code
from tests.fixtures.mock_mavlink2rest import MockMAVLink2RESTClient

client = MockMAVLink2RESTClient()
client.set_attitude(roll=0.1, pitch=0.05, yaw=1.57)
client.set_altitude(relative=10.0, amsl=50.0)
```

## Log Output

### Command Log Format

When `log_commands: true`:

```
[INFO] CIRCUIT_BREAKER: Blocked velocity_body command from MCVelocityChaseFollower
[INFO]   vel_body_fwd: 3.00 m/s
[INFO]   vel_body_right: 0.00 m/s
[INFO]   vel_body_down: -0.50 m/s
[INFO]   yawspeed_deg_s: 12.00 deg/s
```

### Analyzing Logs

```bash
# Count blocked commands
grep "CIRCUIT_BREAKER: Blocked" logs/pixeagle.log | wc -l

# Find max forward velocity attempted
grep "vel_body_fwd" logs/pixeagle.log | awk '{print $2}' | sort -n | tail -1

# Check for limit clamping
grep "clamped" logs/pixeagle.log
```

## Dashboard Integration

The dashboard shows circuit breaker status:

```
┌─────────────────────────────────────┐
│  Status: SAFE MODE                  │
│  Circuit Breaker: ACTIVE            │
│  Commands Blocked: 156              │
│                                     │
│  Last Command:                      │
│    Type: velocity_body              │
│    Fwd: 2.50 m/s                    │
│    Yaw: 10.0 deg/s                  │
└─────────────────────────────────────┘
```

## Transitioning to Flight

### Safe Transition Process

1. **Verify with Circuit Breaker**
   ```yaml
   circuit_breaker:
     active: true
   ```
   - Test all scenarios
   - Check command values
   - Verify safety limits

2. **SITL Testing**
   ```yaml
   circuit_breaker:
     active: false
   px4:
     connection_string: "udp://:14541"
   ```
   - Test with PX4 SITL
   - Verify mode transitions
   - Test emergency procedures

3. **Hardware Testing**
   ```yaml
   circuit_breaker:
     active: false
   safety:
     max_velocity_forward: 3.0  # Start conservative
   ```
   - Start with low limits
   - Test in open area
   - Gradually increase limits

## API Endpoints for Testing

### Get Blocked Commands History

```bash
curl http://localhost:8000/api/circuit_breaker/history
```

### Get Current Setpoints

```bash
curl http://localhost:8000/api/follower/current_setpoints
```

### Force Circuit Breaker State

```bash
# Enable (for testing)
curl -X POST http://localhost:8000/api/circuit_breaker/enable

# Disable (requires confirmation)
curl -X POST http://localhost:8000/api/circuit_breaker/disable \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

## Best Practices

1. **Always Start with Circuit Breaker Active**
   - Enables safe iteration
   - Prevents accidental commands

2. **Review Logs Before Flight**
   - Check command patterns
   - Verify no anomalies

3. **Use Conservative Limits Initially**
   - Start with 50% of production limits
   - Increase gradually after testing

4. **Test Emergency Procedures**
   - RTL trigger works
   - Mode transitions handled
   - Failsafe behavior correct

## Related Documentation

- [Safety Integration](../05-configuration/safety-integration.md)
- [SITL Setup](../04-infrastructure/sitl-setup.md)
- [Troubleshooting](../07-troubleshooting/)
