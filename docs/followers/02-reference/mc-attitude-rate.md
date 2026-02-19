# MC Attitude Rate Follower

> Direct angular rate control for aggressive multicopter tracking

**Profile**: `mc_attitude_rate`
**Control Type**: `attitude_rate`
**Source**: `src/classes/followers/mc_attitude_rate_follower.py`

---

## Overview

The MC Attitude Rate Follower uses direct angular rate commands for aggressive, low-latency tracking. Unlike velocity-based followers, this directly commands pitch, roll, and yaw rates.

Use cases:
- Aggressive pursuit scenarios
- High-speed tracking
- GPS-denied environments (rate control only)
- Situations requiring direct attitude authority

---

## Control Strategy

### Rate Commands

Directly commands angular rates and thrust:

```python
rollspeed = pid_roll(error_x)    # Bank toward target
pitchspeed = pid_pitch(error_y)  # Pitch to pursue
yawspeed = pid_yaw(error_x)      # Turn toward target
thrust = compute_thrust()         # Maintain flight
```

### Thrust Control

Maintains altitude via thrust:

```python
thrust = base_thrust + pid_altitude(altitude_error)
```

Thrust is normalized (0.0-1.0).

---

## Configuration

### Config Section: `MC_ATTITUDE_RATE`

```yaml
MC_ATTITUDE_RATE:
  # Rate limits (deg/s)
  MAX_ROLL_RATE: 90.0
  MAX_PITCH_RATE: 60.0
  MAX_YAW_RATE: 120.0

  # Thrust control
  BASE_THRUST: 0.5
  MIN_THRUST: 0.3
  MAX_THRUST: 0.9
  THRUST_AUTHORITY: 0.2           # ± from base

  # Altitude control
  ENABLE_ALTITUDE_CONTROL: true
  ALTITUDE_DEADBAND: 0.5          # meters

  # Safety
  EMERGENCY_STOP_ENABLED: true
  MAX_TRACKING_ERROR: 2.0
```

### PID Gains

```yaml
PID_GAINS:
  rollspeed_deg_s:
    p: 60.0
    i: 2.0
    d: 10.0
  pitchspeed_deg_s:
    p: 40.0
    i: 1.5
    d: 8.0
  yawspeed_deg_s:
    p: 80.0
    i: 3.0
    d: 15.0
  thrust:
    p: 0.2
    i: 0.05
    d: 0.02
```

---

## When to Use

- High-speed chase requiring aggressive maneuvers
- Direct attitude authority needed
- GPS signal unreliable
- Very responsive tracking required

## When NOT to Use

- General-purpose tracking (use `mc_velocity_chase` variants)
- Precision following (velocity control is smoother)
- Inexperienced operators (aggressive response)

---

## Safety Considerations

1. **High authority** - Can produce aggressive maneuvers
2. **Thrust control** - Incorrect settings cause altitude loss
3. **Rate limits** - Tune conservatively first
4. **Emergency stop** - Keep enabled

---

## Tracker Requirements

**Required**: `POSITION_2D`

---

## Telemetry

```python
status = follower.get_rate_status()
# {
#     'current_rates': {
#         'roll': 15.2,
#         'pitch': 8.1,
#         'yaw': 22.5
#     },
#     'thrust': 0.55,
#     'tracking_error': 0.12
# }
```
