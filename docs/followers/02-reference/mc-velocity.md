# MC Velocity Follower

> Baseline multicopter follower with dual-mode lateral guidance

**Profile**: `mc_velocity`
**Control Type**: `velocity_body_offboard`
**Source**: `src/classes/followers/mc_velocity_follower.py`

---

## Overview

The MC Velocity Follower is the baseline multicopter follower providing:

- Dual-mode lateral guidance (sideslip vs coordinated turn)
- PID-controlled velocity commands
- Standard safety features
- Compatible with most tracking scenarios

This follower is simpler than `mc_velocity_chase` - it lacks velocity ramping and adaptive features but provides reliable tracking for general use cases.

---

## Control Strategy

### Horizontal Control

Uses PID controllers for lateral positioning:

**Sideslip Mode**
```python
vel_body_right = pid_right(error_x)  # Direct lateral movement
yawspeed = 0
```

**Coordinated Turn Mode**
```python
vel_body_right = 0
yawspeed = pid_yaw(error_x)  # Turn toward target
```

### Vertical Control

PID-controlled altitude tracking:

```python
vel_body_down = pid_down(error_y)
```

### Forward Velocity

Constant forward velocity (configurable):

```python
vel_body_fwd = CONSTANT_FORWARD_VELOCITY
```

---

## Configuration

### Config Section: `MC_VELOCITY`

```yaml
MC_VELOCITY:
  # Forward velocity (constant)
  CONSTANT_FORWARD_VELOCITY: 5.0     # m/s

  # Lateral guidance
  LATERAL_GUIDANCE_MODE: "coordinated_turn"
  ENABLE_AUTO_MODE_SWITCHING: false
  GUIDANCE_MODE_SWITCH_VELOCITY: 3.0

  # Vertical control
  ENABLE_ALTITUDE_CONTROL: true

  # Safety
  EMERGENCY_STOP_ENABLED: true
  MAX_TRACKING_ERROR: 1.5
```

### PID Gains

```yaml
PID_GAINS:
  vel_body_right:
    p: 3.0
    i: 0.1
    d: 0.5
  vel_body_down:
    p: 2.0
    i: 0.05
    d: 0.3
  yawspeed_deg_s:
    p: 45.0
    i: 1.0
    d: 5.0
```

---

## When to Use

- General-purpose tracking
- When velocity ramping is not needed
- As a starting point for customization
- Testing and development

## When NOT to Use

- Aggressive chase scenarios (use `mc_velocity_chase`)
- Stationary target tracking (use `mc_velocity_position`)
- Fixed-wing platforms (use `fw_attitude_rate`)

---

## Tracker Requirements

**Required**: `POSITION_2D`
**Optional**: `BBOX_CONFIDENCE`

---

## API Methods

```python
# Calculate and apply control
follower.calculate_control_commands(tracker_data)
success = follower.follow_target(tracker_data)

# Mode management
follower.force_lateral_mode('sideslip')
mode = follower.get_lateral_mode_description()

# Emergency control
follower.activate_emergency_stop()
follower.reset_state()
```

---

## Telemetry

```python
status = follower.get_status()
# {
#     'active_lateral_mode': 'coordinated_turn',
#     'current_commands': {...},
#     'tracking_active': True
# }
```
