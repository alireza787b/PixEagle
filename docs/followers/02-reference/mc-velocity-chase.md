# MC Velocity Chase Follower

> Dual-mode lateral guidance with forward velocity ramping

**Profile**: `mc_velocity_chase`
**Control Type**: `velocity_body_offboard`
**Source**: `src/classes/followers/mc_velocity_chase_follower.py`

---

## Overview

The MC Velocity Chase Follower is designed for pursuit scenarios where the drone chases a moving target from behind. It features:

- Forward velocity ramping with configurable acceleration
- Dual-mode lateral guidance (sideslip vs coordinated turn)
- Adaptive dive/climb control (optional)
- Pitch compensation for camera stabilization
- Comprehensive target loss handling

---

## Control Strategy

### Forward Velocity

Uses ramping rather than PID for smooth acceleration:

```
v_fwd(t) = min(v_fwd(t-1) + ramp_rate * dt, max_forward_velocity)
```

On target loss, velocity ramps down to `TARGET_LOSS_STOP_VELOCITY`.

### Lateral Guidance Modes

**Sideslip Mode**
- Direct lateral velocity (`vel_body_right != 0`)
- Yaw rate = 0
- Best for: hovering, close proximity, confined spaces

**Coordinated Turn Mode**
- Turn-to-track (`yawspeed != 0`)
- Lateral velocity = 0
- Best for: forward flight, efficiency, wind resistance

### Vertical Control

PID-controlled with optional adaptive dive/climb:

```python
down_velocity = self.pid_down(error_y)
```

Error is computed from target's vertical position in the image frame.

---

## Configuration

### Config Section: `MC_VELOCITY_CHASE`

```yaml
MC_VELOCITY_CHASE:
  # Forward Velocity
  INITIAL_FORWARD_VELOCITY: 0.0    # m/s - start stationary
  MAX_FORWARD_VELOCITY: 8.0        # m/s - maximum chase speed
  FORWARD_RAMP_RATE: 2.0           # m/s² - acceleration
  MIN_FORWARD_VELOCITY_THRESHOLD: 0.5  # m/s - minimum in motion

  # Lateral Guidance
  LATERAL_GUIDANCE_MODE: "coordinated_turn"  # or "sideslip"
  ENABLE_AUTO_MODE_SWITCHING: false
  GUIDANCE_MODE_SWITCH_VELOCITY: 3.0  # m/s - switch threshold

  # Vertical Control
  ENABLE_ALTITUDE_CONTROL: true

  # Target Loss Handling
  RAMP_DOWN_ON_TARGET_LOSS: true
  TARGET_LOSS_TIMEOUT: 2.0         # seconds
  TARGET_LOSS_STOP_VELOCITY: 0.0   # m/s - hover on loss
  TARGET_LOSS_COORDINATE_THRESHOLD: 990

  # Safety
  ALTITUDE_SAFETY_ENABLED: false
  EMERGENCY_STOP_ENABLED: true
  MAX_TRACKING_ERROR: 1.5          # normalized coords

  # Smoothing
  COMMAND_SMOOTHING_ENABLED: true
  SMOOTHING_FACTOR: 0.8            # EMA alpha

  # Adaptive Dive/Climb (Optional)
  ENABLE_ADAPTIVE_DIVE_CLIMB: false
  ADAPTIVE_SMOOTHING_ALPHA: 0.2
  ADAPTIVE_RATE_THRESHOLD: 5.0
  ADAPTIVE_MAX_CORRECTION: 1.0

  # Pitch Compensation (Optional)
  ENABLE_PITCH_COMPENSATION: false
  PITCH_COMPENSATION_MODEL: "linear_velocity"
  PITCH_COMPENSATION_GAIN: 0.05
```

### PID Gains

```yaml
PID_GAINS:
  vel_body_right:        # Sideslip mode
    p: 3.0
    i: 0.1
    d: 0.5
  vel_body_down:         # Vertical control
    p: 2.0
    i: 0.05
    d: 0.3
  yawspeed_deg_s:        # Coordinated turn mode
    p: 45.0
    i: 1.0
    d: 5.0
```

---

## Features

### Velocity Ramping

Smooth acceleration from stationary to chase speed:

```python
# Ramping logic
velocity_error = target_velocity - current_forward_velocity
max_change = ramp_rate * dt
velocity_change = clip(velocity_error, -max_change, max_change)
current_forward_velocity += velocity_change
```

### Auto Mode Switching

When enabled, switches lateral mode based on forward velocity:

- Below `GUIDANCE_MODE_SWITCH_VELOCITY`: Sideslip mode
- Above: Coordinated turn mode

```python
if self.enable_auto_mode_switching:
    if current_forward_velocity >= switch_velocity:
        return 'coordinated_turn'
    else:
        return 'sideslip'
```

### Adaptive Dive/Climb

Observes target vertical rate and adjusts velocity to match:

1. Records target Y coordinates over time
2. Calculates smoothed vertical rate (EMA filter)
3. Compares to expected rate from commanded velocities
4. Applies correction to `vel_body_down`

Safety features:
- Oscillation detection (disables on rapid sign changes)
- Divergence detection (disables if error persists)

### Pitch Compensation

Compensates for camera image shift during forward pitch:

**Models**:
- `linear_velocity`: `compensation = K * pitch * v_fwd`
- `linear_angle`: `compensation = K * pitch`
- `quadratic`: `compensation = K * pitch² * sign(pitch) * v_fwd`

Applied to vertical error before PID processing.

---

## Tracker Requirements

**Required**: `POSITION_2D`
**Optional**: `BBOX_CONFIDENCE`, `VELOCITY_AWARE`

Confidence below threshold triggers target loss handling.

---

## Telemetry

```python
status = follower.get_chase_status()
# {
#     'current_forward_velocity': 5.2,
#     'active_lateral_mode': 'coordinated_turn',
#     'target_lost': False,
#     'emergency_stop_active': False,
#     'adaptive_mode': {
#         'active': True,
#         'rate_error': 2.1,
#         'correction_down': 0.05
#     }
# }
```

---

## API Methods

### Core Methods

```python
# Calculate control commands
follower.calculate_control_commands(tracker_data)

# Execute following
success = follower.follow_target(tracker_data)
```

### Mode Control

```python
# Force lateral mode
follower.force_lateral_mode('sideslip')

# Get mode description
desc = follower.get_lateral_mode_description()
```

### Safety Control

```python
# Emergency stop
follower.activate_emergency_stop()
follower.deactivate_emergency_stop()

# Reset state
follower.reset_chase_state()
```

---

## Best Practices

1. **Start with coordinated turn** - More natural for forward flight
2. **Tune vertical PID first** - Most visible effect on tracking
3. **Enable smoothing** - Reduces command jitter
4. **Use conservative ramp rate** - 2.0 m/s² is safe default
5. **Test adaptive mode in simulation** - Can be unstable if misconfigured
6. **Keep pitch compensation disabled** unless tracking at high forward speeds

---

## Example Configuration

### Aggressive Chase (Fast Target)

```yaml
MC_VELOCITY_CHASE:
  MAX_FORWARD_VELOCITY: 12.0
  FORWARD_RAMP_RATE: 4.0
  LATERAL_GUIDANCE_MODE: "coordinated_turn"
  ENABLE_AUTO_MODE_SWITCHING: true
  GUIDANCE_MODE_SWITCH_VELOCITY: 2.0
  COMMAND_SMOOTHING_ENABLED: false
```

### Conservative Follow (Slow/Stationary Target)

```yaml
MC_VELOCITY_CHASE:
  MAX_FORWARD_VELOCITY: 3.0
  FORWARD_RAMP_RATE: 1.0
  LATERAL_GUIDANCE_MODE: "sideslip"
  COMMAND_SMOOTHING_ENABLED: true
  SMOOTHING_FACTOR: 0.9
```
