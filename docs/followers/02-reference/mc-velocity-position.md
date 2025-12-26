# MC Velocity Position Follower

> Position hold with yaw and altitude tracking only

**Profile**: `mc_velocity_position`
**Control Type**: `velocity_body_offboard`
**Source**: `src/classes/followers/mc_velocity_position_follower.py`

---

## Overview

The MC Velocity Position Follower maintains the drone's position while tracking the target with yaw and altitude adjustments. The drone does not translate horizontally - only rotates and changes altitude to keep the target centered.

---

## Control Strategy

### Horizontal Position

No lateral translation - drone holds position:

```python
vel_body_fwd = 0.0
vel_body_right = 0.0
```

### Yaw Control

Rotates to face target:

```python
yawspeed = pid_yaw(error_x)  # Turn toward target
```

### Altitude Control

Adjusts altitude to center target vertically:

```python
vel_body_down = pid_down(error_y)
```

---

## Configuration

### Config Section: `MC_VELOCITY_POSITION`

```yaml
MC_VELOCITY_POSITION:
  # Yaw control
  MAX_YAW_RATE: 30.0                 # deg/s
  YAW_DEADBAND: 0.02                 # normalized

  # Altitude control
  ENABLE_ALTITUDE_CONTROL: true
  MAX_VERTICAL_VELOCITY: 2.0         # m/s

  # Position hold assist
  ENABLE_GPS_POSITION_HOLD: true
```

### PID Gains

```yaml
PID_GAINS:
  yawspeed_deg_s:
    p: 30.0
    i: 0.5
    d: 3.0
  vel_body_down:
    p: 2.0
    i: 0.05
    d: 0.3
```

---

## Use Cases

- Stationary surveillance
- Tripod-style tracking
- Camera operator simulation
- Minimal movement tracking

---

## Tracker Requirements

**Required**: `POSITION_2D`

---

## Telemetry

```python
status = follower.get_position_status()
# {
#     'yaw_tracking_error': 0.05,
#     'altitude_tracking_error': 0.1,
#     'position_hold_active': True
# }
```

---

## Best Practices

1. **Tune yaw PID for smooth rotation** - Avoid jerky movements
2. **Use deadband** - Prevents micro-adjustments
3. **Enable GPS position hold** - Maintains location in wind
