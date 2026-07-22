# MC Velocity Position Follower

> Zero horizontal body velocity with visual yaw and optional altitude control

**Profile**: `mc_velocity_position`
**Control Type**: `velocity_body_offboard`
**Source**: `src/classes/followers/mc_velocity_position_follower.py`

---

## Overview

The MC Velocity Position Follower requests zero forward/right body velocity
while tracking the selected image target with yaw and, when explicitly enabled,
vertical velocity. PX4 is still responsible for executing the body-velocity
setpoints; this mode does not contain a separate GPS-position controller.

---

## Control Strategy

### Horizontal Position

No lateral translation - drone holds position:

```python
vel_body_fwd = 0.0
vel_body_right = 0.0
```

### Yaw Control

The PID and safety limit use radians per second internally. PixEagle converts
the bounded PID result once to degrees per second before the shared yaw
smoother and the `yawspeed_deg_s` command field.

Normalized image X increases to the right. A target to image-right therefore
requests positive MAVSDK body yaw rate, which is clockwise when viewed from
above. The configured yaw acceleration limit and smoother can make the first
reported command smaller than the final PID request; that ramp is intentional,
not command quantization.

### Altitude Control

Altitude control is disabled by default. When enabled, positive
`vel_body_down` follows the PX4 body-FRD convention (positive is down).

---

## Configuration

The schema and `configs/config_default.yaml` are authoritative. The relevant
paths are split by ownership rather than duplicated in this mode section:

```yaml
Follower:
  TARGET_POSITION_MODE: center
  General:
    ENABLE_ALTITUDE_CONTROL: false
    YAW_SMOOTHING:
      ENABLED: true
      DEADZONE_DEG_S: 0.5
      MAX_RATE_CHANGE_DEG_S2: 90.0
      SMOOTHING_ALPHA: 0.7

MC_VELOCITY_POSITION:
  ENABLE_YAW_CONTROL: true
  YAW_CONTROL_THRESHOLD: 0.02

PID:
  PID_GAINS:
    mc_yawspeed_deg_s: {p: 12.0, i: 0.5, d: 1.5}
    mc_altitude: {p: 2.0, i: 0.03, d: 0.05}

Safety:
  FollowerOverrides:
    MC_VELOCITY_POSITION:
      MAX_YAW_RATE: 10.0
```

Use Settings or the config schema to change these values. Do not create a
second follower-specific copy of shared smoothing, PID, or safety limits.

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

`get_follower_telemetry()` reports the current command intent, configured
setpoints, control summary, and performance metrics. In `COMMAND_PREVIEW`, the
same intent is visible in Following telemetry while
`commands_sent_to_px4=false`.

---

## Best Practices

1. Keep altitude control disabled until its direction and envelope are proven
   with the intended camera mounting and vehicle.
2. Tune PID, deadzone, acceleration limit, and smoothing as one recorded test;
   changing only one value can hide oscillation or sluggish response.
3. Use `COMMAND_PREVIEW` for local intent inspection, then SIH/SITL before any
   reviewed aircraft test. Preview is not vehicle-response evidence.
4. Select `mc_velocity_chase` when forward pursuit is required. This profile
   always requests zero forward and right velocity by design.
