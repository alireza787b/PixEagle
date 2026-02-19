# GM Velocity Chase Follower

> Gimbal-based velocity chase control

**Profile**: `gm_velocity_chase`
**Control Type**: `velocity_body_offboard`
**Source**: `src/classes/followers/gm_velocity_chase_follower.py`

---

## Overview

The GM Velocity Chase Follower uses gimbal angles to derive vehicle velocity commands. The gimbal tracks the target, and the drone follows the gimbal's pointing direction.

Key features:
- Mount-aware coordinate transformations
- PID-based velocity control from gimbal angles
- Unified target loss handling
- Circuit breaker integration for testing
- Zero hardcoding - fully YAML configurable

---

## Control Strategy

### Gimbal to Velocity Conversion

```python
# Gimbal angles (normalized or degrees)
gimbal_pan = tracker_data.gimbal_pan
gimbal_tilt = tracker_data.gimbal_tilt

# Convert to velocity commands
vel_fwd = pid_forward(gimbal_tilt)   # Follow gimbal pitch
vel_right = pid_lateral(gimbal_pan)   # Follow gimbal yaw
yawspeed = pid_yaw(gimbal_pan)        # Turn toward gimbal
```

### Mount Types

**VERTICAL Mount** (camera below, pointing forward)
```python
# Standard mapping
forward <- gimbal_tilt
lateral <- gimbal_pan
```

**HORIZONTAL Mount** (camera on side)
```python
# Rotated mapping
forward <- gimbal_pan
lateral <- gimbal_tilt
```

---

## Configuration

### Config Section: `GM_VELOCITY_CHASE`

```yaml
GM_VELOCITY_CHASE:
  # Mount configuration
  MOUNT_TYPE: "VERTICAL"             # or "HORIZONTAL"
  CONTROL_MODE: "VELOCITY"           # Velocity commands

  # Velocity control (via SafetyManager cached limits)
  # MAX_VELOCITY, MAX_VELOCITY_LATERAL, MAX_VELOCITY_VERTICAL
  # are automatically derived from Safety.GlobalLimits

  # Performance
  CONTROL_UPDATE_RATE: 20.0          # Hz
  COMMAND_SMOOTHING_ENABLED: true
  SMOOTHING_FACTOR: 0.8

  # Safety
  EMERGENCY_STOP_ENABLED: true
  ALTITUDE_SAFETY_ENABLED: true
  MAX_SAFETY_VIOLATIONS: 5

  # Target loss handling
  TARGET_LOSS_HANDLING:
    ENABLED: true
    CONTINUE_VELOCITY_TIMEOUT: 3.0   # seconds
    RESPONSE_ACTION: "hover"         # "hover", "rtl", "continue"
```

### PID Gains

```yaml
PID_GAINS:
  vel_body_fwd:
    p: 2.0
    i: 0.1
    d: 0.3
  vel_body_right:
    p: 3.0
    i: 0.1
    d: 0.5
  yawspeed_deg_s:
    p: 45.0
    i: 1.0
    d: 5.0
```

---

## Tracker Requirements

**Required**: `GIMBAL_ANGLES`

The tracker must provide gimbal pan/tilt angles:

```python
TrackerOutput(
    data_type=TrackerDataType.GIMBAL_ANGLES,
    gimbal_pan=0.15,    # Normalized or degrees
    gimbal_tilt=-0.05,
    confidence=0.95
)
```

---

## Target Loss Handling

Built-in target loss handler with configurable responses:

| Action | Behavior |
|--------|----------|
| `hover` | Stop and hover in place |
| `rtl` | Return to launch |
| `continue` | Continue last velocity (timeout limited) |

---

## Circuit Breaker Integration

For safe testing, circuit breaker mode logs commands without execution:

```python
if circuit_breaker.is_active():
    log_command(vel_fwd, vel_right, yawspeed)
    return  # Don't execute
```

---

## Telemetry

```python
status = follower.get_pursuit_status()
# {
#     'mount_type': 'VERTICAL',
#     'following_active': True,
#     'gimbal_angles': {'pan': 5.2, 'tilt': -2.1},
#     'velocity_command': {'fwd': 3.1, 'right': 0.5, 'yaw': 12.3},
#     'target_loss_handler_active': False,
#     'emergency_stop_active': False
# }
```

---

## When to Use

- Drone with actively-stabilized gimbal
- Tracker outputs gimbal angles (not image position)
- Want gimbal to lead, vehicle to follow

## When NOT to Use

- No gimbal on vehicle
- Tracker provides image coordinates (use `mc_velocity_chase` variants)
- Fixed camera mount

---

## Best Practices

1. **Set correct mount type** - Critical for coordinate mapping
2. **Tune gimbal PID separately** - Before vehicle following
3. **Enable smoothing** - Reduces jitter from gimbal noise
4. **Configure target loss** - Safe fallback is important
5. **Test with circuit breaker** - Verify commands before flight
