# MC Velocity Distance Follower

> Constant distance maintenance from target

**Profile**: `mc_velocity_distance`
**Control Type**: `velocity_body_offboard`
**Source**: `src/classes/followers/mc_velocity_distance_follower.py`

---

## Overview

The MC Velocity Distance Follower maintains a constant standoff distance from the target while tracking it. Ideal for:

- Orbit-like following patterns
- Safe distance surveillance
- Following without closing in

---

## Control Strategy

### Distance Control

Maintains target at a specified apparent size or distance:

```python
# Distance error based on bounding box size or 3D position
distance_error = desired_distance - current_distance

# Forward velocity to maintain distance
vel_fwd = pid_distance(distance_error)
```

### Lateral Control

Standard center-tracking:

```python
vel_right = pid_lateral(error_x)
# or
yawspeed = pid_yaw(error_x)
```

### Vertical Control

Optional altitude matching or fixed offset:

```python
vel_down = pid_vertical(error_y)
```

---

## Configuration

### Config Section: `MC_VELOCITY_DISTANCE`

```yaml
MC_VELOCITY_DISTANCE:
  # Distance control
  DESIRED_DISTANCE: 10.0             # meters
  DISTANCE_TOLERANCE: 1.0            # meters
  USE_BBOX_FOR_DISTANCE: true        # Use bbox size as distance proxy

  # Velocity limits
  MAX_APPROACH_VELOCITY: 3.0         # m/s toward target
  MAX_RETREAT_VELOCITY: 3.0          # m/s away from target
  MAX_LATERAL_VELOCITY: 5.0          # m/s

  # Lateral guidance
  LATERAL_GUIDANCE_MODE: "coordinated_turn"

  # Vertical control
  ENABLE_ALTITUDE_CONTROL: true
  ALTITUDE_OFFSET: 0.0               # meters above/below target
```

### PID Gains

```yaml
PID_GAINS:
  distance:
    p: 1.0
    i: 0.05
    d: 0.2
  vel_body_right:
    p: 3.0
    i: 0.1
    d: 0.5
  vel_body_down:
    p: 2.0
    i: 0.05
    d: 0.3
```

---

## Distance Estimation

### From Bounding Box

Uses apparent size as distance proxy:

```python
# Larger bbox = closer target
apparent_size = bbox_width * bbox_height
estimated_distance = calibration_factor / sqrt(apparent_size)
```

### From 3D Position

If tracker provides 3D coordinates:

```python
distance = sqrt(x² + y² + z²)
```

---

## Tracker Requirements

**Required**: `POSITION_2D`
**Optional**: `BBOX_SIZE`, `POSITION_3D`

3D position provides more accurate distance control.

---

## Use Cases

- Surveillance at safe distance
- Orbit following
- Buffer zone maintenance
- Gradual approach/retreat maneuvers

---

## Telemetry

```python
status = follower.get_distance_status()
# {
#     'current_distance': 12.5,
#     'desired_distance': 10.0,
#     'distance_error': 2.5,
#     'approach_velocity': 1.2
# }
```

---

## Best Practices

1. **Calibrate distance estimation** - Especially for bbox-based
2. **Set reasonable tolerance** - Avoid oscillation
3. **Conservative approach velocity** - Prevent overshoot
4. **Use 3D position when available** - More accurate
