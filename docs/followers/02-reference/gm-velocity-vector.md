# GM Velocity Vector Follower

> Direct vector pursuit from gimbal angles

**Profile**: `gm_velocity_vector`
**Control Type**: `velocity_body_offboard`
**Source**: `src/classes/followers/gm_velocity_vector_follower.py`

---

## Overview

The GM Velocity Vector Follower converts gimbal pointing angles directly into velocity vectors for pursuit. Similar to `gm_velocity_chase` but uses direct vector math instead of PID control.

Key features:
- Direct angle-to-velocity conversion
- Body-frame vector calculations
- Simplified control law
- Fast response time

---

## Control Strategy

### Vector Calculation

```python
# Gimbal angles to unit vector
unit_vec = angles_to_unit_vector(pan, tilt)

# Scale by forward velocity
vel_fwd = forward_speed
vel_right = unit_vec.y * forward_speed
vel_down = unit_vec.z * forward_speed

# Yaw toward target
yawspeed = pan * yaw_gain
```

### Coordinate Transformation

```python
# Body frame vector from gimbal angles
def angles_to_body_velocity(pan_deg, tilt_deg, speed):
    pan_rad = radians(pan_deg)
    tilt_rad = radians(tilt_deg)

    fwd = speed * cos(tilt_rad) * cos(pan_rad)
    right = speed * sin(pan_rad)
    down = speed * sin(tilt_rad)

    return fwd, right, down
```

---

## Configuration

### Config Section: `GM_VELOCITY_VECTOR`

```yaml
GM_VELOCITY_VECTOR:
  # Mount configuration
  MOUNT_TYPE: "VERTICAL"

  # Velocity control
  FORWARD_SPEED: 5.0                 # m/s - pursuit speed
  SPEED_GAIN: 1.0                    # Velocity scaling

  # Yaw control
  YAW_GAIN: 30.0                     # deg/s per unit pan
  # Rate limits are NOT configured here.
  # Set MAX_YAW_RATE, MAX_PITCH_RATE, MAX_ROLL_RATE in Safety.GlobalLimits
  # (or Safety.FollowerOverrides.GM_VELOCITY_VECTOR for per-follower overrides).

  # Vertical control
  ENABLE_VERTICAL_PURSUIT: true
  VERTICAL_GAIN: 0.5

  # Smoothing
  COMMAND_SMOOTHING_ENABLED: true
  SMOOTHING_FACTOR: 0.8

  # Safety
  EMERGENCY_STOP_ENABLED: true
```

---

## Comparison with GM Velocity Chase

| Feature | GM Velocity Chase | GM Velocity Vector |
|---------|------------------|-------------------|
| Control Law | PID feedback | Direct vector |
| Tuning | PID gains | Velocity gains |
| Response | Smoother | Faster |
| Complexity | Higher | Lower |
| Best For | Precision | Speed |

---

## Tracker Requirements

**Required**: `GIMBAL_ANGLES`

---

## When to Use

- Simple, fast gimbal following
- Direct vector control preferred
- Less tuning desired
- Rapid response needed

## When NOT to Use

- Precision following required (use `gm_velocity_chase`)
- Noisy gimbal data (PID provides filtering)
- Complex pursuit patterns

---

## Telemetry

```python
status = follower.get_status_info()
# {
#     'gimbal_vector': {'pan': 5.2, 'tilt': -2.1},
#     'velocity_vector': {'fwd': 4.8, 'right': 0.45, 'down': -0.18},
#     'yaw_rate': 15.6
# }
```
