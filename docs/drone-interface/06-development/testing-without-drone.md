# Testing Without a Drone

This guide defines the safe boundaries for testing PixEagle without a physical
drone or PX4 simulator.

## Overview

PixEagle provides a **Circuit Breaker** that inhibits PX4 command dispatch. It
still allows:

- Telemetry reception and processing
- Tracker operation
- Dashboard operation

The circuit breaker is not a telemetry simulator or PX4 substitute. The
explicit `beginner_lab` profile selects the separate
[Local Follower Test](follower-command-preview.md), which records replay-driven
intents and sends nothing to PX4/MAVSDK. The checked-in execution default
remains `PX4`; it rejects Start Following while the circuit breaker is active.

For the maintained no-PX4 tracker-to-follower acceptance contract, run:

```bash
make follower-contract-test
```

This deterministic harness feeds synthetic visual and gimbal tracker outputs
through concrete followers and a capturing command sink. It checks command
intent fields, signs, finite values, stale-target holds, and normalized trace
artifacts. It does not connect to PX4, publish MAVLink, or prove vehicle
response. Neither this harness nor the Local Follower Test authorizes autonomous
following.

## Circuit Breaker Configuration

### Enable Circuit Breaker

```yaml
# config_default.yaml

FOLLOWER_CIRCUIT_BREAKER: true  # Block follower PX4 commands and log intent
```

### Configuration Options

| Option | Type | Description |
|--------|------|-------------|
| `FOLLOWER_CIRCUIT_BREAKER` | boolean | `true` inhibits PX4 command dispatch and blocks Following startup; `false` permits the reviewed live/SIH command path |
| `CIRCUIT_BREAKER_DISABLE_SAFETY` | boolean | Test-only bypass used with the circuit breaker; keep `false` unless a controlled bench test explicitly needs it |
| `FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES` | boolean | Emergency bench/SITL bypass for unavailable safety-gate modules; keep `false` unless an operator-approved test explicitly needs live commands |

## How It Works

### Command Boundary

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
│   ├─ Active: BLOCK    │◄── Following start is rejected
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
| Offboard start | Tracker processing |

Low-level command interception remains as defense in depth, but it must not be
used as evidence that a follower session ran. No follower calculations or PX4
response are claimed without a dedicated preview/test sink or SIH/SITL evidence.

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
  "available": true,
  "active": true,
  "status": "testing",
  "semantics": "px4_command_dispatch_inhibit",
  "state_reason": null,
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

### 1. Tracker and Dashboard Development

Test video, tracker, API, and dashboard behavior without a command target:

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
3. Confirm Start Following is unavailable while command dispatch is inhibited
4. Run `make follower-contract-test` for command-value assertions

### 2. Validate the Command Inhibit

Verify the fail-closed boundary before preparing a simulator or flight test:

```bash
# Start with circuit breaker
bash scripts/run.sh --no-attach  # FOLLOWER_CIRCUIT_BREAKER = true

# Confirm the dashboard reports command dispatch as blocked

# Check circuit-breaker statistics
curl http://127.0.0.1:5077/api/circuit-breaker/statistics
```

**Validation Checklist:**
- [ ] Start Following is unavailable
- [ ] No MAVSDK/PX4 command startup is attempted
- [ ] Tracker and dashboard remain observable
- [ ] Invalid or missing circuit-breaker config fails closed

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

## Logs and Dashboard

The dashboard reports command dispatch as `Blocked` or `Live`. While blocked,
the Start Following action is unavailable. The statistics panel exposes any
lower-level interception that occurred as defense in depth; zero intercepted
commands is normal because startup is rejected before MAVSDK connection.

Use the unified Logs page or exported support bundle for diagnostics. Do not
parse free-form command logs as follower-validation evidence. Follower command
values belong in typed unit/integration traces or accepted SIH/SITL artifacts.

## Transitioning to Flight

### Safe Transition Process

1. **Verify fail-closed behavior**
   ```yaml
   FOLLOWER_CIRCUIT_BREAKER: true
   ```
   - Confirm Following is blocked before MAVSDK connection
   - Test tracker/dashboard behavior
   - Run follower unit and integration tests

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

### Change Circuit-Breaker State

Use the dashboard's explicit state control or the typed, confirmed,
idempotent actions:

- `POST /api/v1/actions/circuit-breaker-set`
- `POST /api/v1/actions/circuit-breaker-safety-bypass-set`

Both require authenticated action scope and a valid action request. The safety
bypass is an advanced diagnostic setting; it does not create a follower
preview and it remains separate from
`FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES`.

## Best Practices

1. **Always Start with Circuit Breaker Active**
   - Enables safe iteration
   - Prevents accidental commands

2. **Require Typed Evidence Before Flight**
   - Validate command traces in unit/integration tests and SIH/SITL
   - Preserve exact versions, config, logs, and abort-path evidence

3. **Use Conservative Limits Initially**
   - Start with 50% of production limits
   - Increase gradually after testing

4. **Test Emergency Procedures**
   - RTL trigger works
   - Mode transitions handled
   - Failsafe behavior correct

## Related Documentation

- [Local Follower Test](follower-command-preview.md)
- [Safety Integration](../05-configuration/safety-integration.md)
- [SITL Setup](../04-infrastructure/sitl-setup.md)
- [Troubleshooting](../07-troubleshooting/)
