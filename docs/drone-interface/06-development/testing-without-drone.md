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

FOLLOWER_CIRCUIT_BREAKER: true  # Block follower PX4 commands and log intent
```

### Configuration Options

| Option | Type | Description |
|--------|------|-------------|
| `FOLLOWER_CIRCUIT_BREAKER` | boolean | `true` keeps follower commands in log-only mode; `false` allows live PX4 commands |
| `CIRCUIT_BREAKER_DISABLE_SAFETY` | boolean | Test-only bypass used with the circuit breaker; keep `false` unless a controlled bench test explicitly needs it |
| `FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES` | boolean | Emergency bench/SITL bypass for unavailable safety-gate modules; keep `false` unless an operator-approved test explicitly needs live commands |

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
curl http://127.0.0.1:5077/api/circuit-breaker/status

# Response
{
  "active": true,
  "status": "testing",
  "safety_bypass": false,
  "safety_bypass_effective": false,
  "configuration": {
    "parameter_name": "FOLLOWER_CIRCUIT_BREAKER"
  }
}
```

### SetpointHandler Status

```python
from classes.setpoint_handler import SetpointHandler

handler = SetpointHandler('mc_velocity_chase')
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
FOLLOWER_CIRCUIT_BREAKER: true

Safety:
  GlobalLimits:
    MAX_VELOCITY_FORWARD: 3.0   # Reduced limits for safety
    MAX_VELOCITY_LATERAL: 2.0
    MAX_VELOCITY_VERTICAL: 1.0
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
bash scripts/run.sh --no-attach  # FOLLOWER_CIRCUIT_BREAKER = true

# Monitor logs
tail -f logs/pixeagle.log | grep "BLOCKED"

# Check circuit-breaker statistics
curl http://127.0.0.1:5077/api/circuit-breaker/statistics
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

### 4. PX4-In-Loop Handoff

When follower or Offboard behavior needs a real PX4 state machine, move from
mock/no-drone tests to the checked-in SITL harness instead of writing a one-off
script:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run
```

After an operator starts the headless PX4/MavlinkAnywhere/MAVLink2REST/PixEagle
stack from [SITL Setup](../04-infrastructure/sitl-setup.md), collect probe
evidence:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --probe-only \
  --artifact-root reports/sitl
```

To execute the checked-in scenario action schedule against that running stack,
add `--run-scenarios`. Control actions remain blocked unless the operator also
passes `--allow-control-actions`:

```bash
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --probe-only \
  --run-scenarios \
  --artifact-root reports/sitl
```

The probe artifacts are required before describing a PX4-in-loop run as
successful. Runs with blocked control actions, manual fault placeholders,
missing PX4 params, missing ULog/tlog manifests, or missing PX4
image/container metadata remain incomplete. Unit and mock tests remain the
normal fast gate; SITL is opt-in and uses the `sitl`, `px4`, and `e2e` pytest
markers.

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
   FOLLOWER_CIRCUIT_BREAKER: true
   ```
   - Test all scenarios
   - Check command values
   - Verify safety limits

2. **SITL Testing**
   ```yaml
   FOLLOWER_CIRCUIT_BREAKER: false
   PX4:
     SYSTEM_ADDRESS: "udp://127.0.0.1:14540"
   ```
   - Use the checked-in `phase2_follower_validation` plan
   - Verify mode transitions with saved PixEagle/PX4/MAVLink artifacts
   - Test emergency procedures only inside the documented SITL stack

3. **Hardware Testing**
   ```yaml
   FOLLOWER_CIRCUIT_BREAKER: false
   Safety:
     GlobalLimits:
       MAX_VELOCITY_FORWARD: 3.0  # Start conservative
   ```
   - Requires explicit operator approval and a documented safety plan
   - Capture exact config, versions, logs, abort procedure, and post-run evidence
   - Do not treat SITL success as field readiness
   - Start with low limits
   - Test in open area
   - Gradually increase limits

## API Endpoints for Testing

### Get Statistics

```bash
curl http://127.0.0.1:5077/api/circuit-breaker/statistics
```

### Toggle Circuit-Breaker Safety Bypass

```bash
curl -X POST http://127.0.0.1:5077/api/circuit-breaker/toggle-safety
```

This bypass only applies while the circuit breaker is active. It is separate
from `FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES`, which exists only for
operator-approved bench/SITL cases where safety-gate modules are unavailable.

### Force Circuit Breaker State

```bash
# Toggle state for controlled testing
curl -X POST http://127.0.0.1:5077/api/circuit-breaker/toggle

# Reset statistics
curl -X POST http://127.0.0.1:5077/api/circuit-breaker/reset-statistics
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
