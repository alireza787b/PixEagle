# MC Velocity Ground Follower

> Ground target tracking with 3-axis velocity control

**Profile**: `mc_velocity_ground`
**Control Type**: `velocity_body`
**Source**: `src/classes/followers/mc_velocity_ground_follower.py`

---

## Overview

The MC Velocity Ground Follower is designed for tracking ground-based targets from above. Key features:

- Full 3-axis velocity control (X, Y, Z)
- Gimbal orientation compensation
- Altitude-based dynamic adjustments
- Optional gain scheduling
- Descent control with safety limits

---

## Control Strategy

### Coordinate System

Uses body-frame velocities with axis coupling:

```python
# Image error → velocity mapping
vel_x = pid_y(error_y)   # Forward/backward (from Y error)
vel_y = pid_x(error_x)   # Left/right (from X error)
vel_z = descent_control() # Altitude control
```

### Gimbal Corrections

For non-stabilized cameras, compensates for drone orientation:

```python
corrected_x = target_x + adjustment_factor_x * roll
corrected_y = target_y - adjustment_factor_y * pitch
```

### Altitude Adjustments

Scales control response based on altitude:

```python
adj_factor = base_factor / (1 + altitude_factor * current_altitude)
```

Higher altitude = reduced adjustment factor = consistent angular response.

---

## Configuration

### Config Section: `MC_VELOCITY_GROUND`

```yaml
MC_VELOCITY_GROUND:
  # Target mode
  TARGET_POSITION_MODE: "center"     # or "initial"

  # Velocity limits
  MAX_VELOCITY_X: 10.0               # m/s forward/back
  MAX_VELOCITY_Y: 10.0               # m/s left/right
  MAX_RATE_OF_DESCENT: 2.0           # m/s down

  # Descent control
  ENABLE_DESCEND_TO_TARGET: false
  MIN_DESCENT_HEIGHT: 10.0           # meters

  # Gimbal/camera
  IS_CAMERA_GIMBALED: false

  # Altitude adjustments
  BASE_ADJUSTMENT_FACTOR_X: 0.1
  BASE_ADJUSTMENT_FACTOR_Y: 0.1
  ALTITUDE_FACTOR: 0.005

  # Gain scheduling
  ENABLE_GAIN_SCHEDULING: false
  GAIN_SCHEDULING_PARAMETER: "current_altitude"

  # Control
  CONTROL_UPDATE_RATE: 20.0          # Hz
  COORDINATE_CORRECTIONS_ENABLED: true
```

### PID Gains

```yaml
PID_GAINS:
  x:
    p: 2.0
    i: 0.1
    d: 0.3
  y:
    p: 2.0
    i: 0.1
    d: 0.3
  z:
    p: 1.0
    i: 0.05
    d: 0.2
```

### Altitude Gain Schedule (Optional)

```yaml
ALTITUDE_GAIN_SCHEDULE:
  (0, 10):      # 0-10m altitude
    x: {p: 3.0, i: 0.2, d: 0.5}
    y: {p: 3.0, i: 0.2, d: 0.5}
  (10, 30):     # 10-30m altitude
    x: {p: 2.0, i: 0.1, d: 0.3}
    y: {p: 2.0, i: 0.1, d: 0.3}
  (30, 100):    # 30-100m altitude
    x: {p: 1.5, i: 0.05, d: 0.2}
    y: {p: 1.5, i: 0.05, d: 0.2}
```

---

## Descent Control

When enabled, the follower descends toward the target:

```python
if current_altitude > min_descent_height:
    vel_z = pid_z(-current_altitude)  # Descend
else:
    vel_z = 0  # Hold altitude
```

Safety: Descent halted at `MIN_DESCENT_HEIGHT`.

---

## Use Cases

- Inspecting ground objects
- Landing zone tracking
- Ground vehicle following from above
- Survey and mapping with target lock

---

## Tracker Requirements

**Required**: `POSITION_2D`
**Optional**: `BBOX_CONFIDENCE`, `POSITION_3D`

---

## Telemetry

```python
status = follower.get_control_status()
# {
#     'control_type': 'ground_target_tracking',
#     'pid_controllers': {...},
#     'configuration': {
#         'descent_enabled': False,
#         'gimbal_corrections_enabled': True
#     },
#     'current_commands': {...}
# }

metrics = follower.get_performance_metrics()
# {
#     'command_magnitudes': {'vel_x': 2.1, 'vel_y': 1.3, 'vel_z': 0.0},
#     'total_velocity': 3.4,
#     'control_active': True
# }
```

---

## Best Practices

1. **Set IS_CAMERA_GIMBALED correctly** - Critical for proper compensation
2. **Tune altitude factor** - Test at multiple altitudes
3. **Start with gain scheduling disabled** - Enable after baseline tuning
4. **Conservative descent limits** - Safety first
5. **Use center mode** - Unless initial position is critical
