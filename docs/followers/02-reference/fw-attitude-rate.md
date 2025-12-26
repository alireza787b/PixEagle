# FW Attitude Rate Follower

> Fixed-wing pursuit with L1 Navigation and TECS energy management

**Profile**: `fw_attitude_rate`
**Control Type**: `attitude_rate`
**Source**: `src/classes/followers/fw_attitude_rate_follower.py`

---

## Overview

The FW Attitude Rate Follower is the **only** follower suitable for fixed-wing aircraft. PX4 ignores velocity commands in fixed-wing offboard mode, requiring direct attitude rate control.

Key features:
- **L1 Navigation** - Lateral guidance using cross-track error
- **TECS** - Total Energy Control System for coordinated pitch/throttle
- **Coordinated Turns** - Bank angle with load factor limiting
- **Stall Protection** - Automatic recovery on low airspeed
- **Orbit Behavior** - Loiters on target loss

---

## Control Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        TARGET TRACKING                            │
│  Image error → L1 cross-track → Lateral acceleration → Yaw rate  │
└───────────────────────────────┬──────────────────────────────────┘
                                │
           ┌────────────────────┼────────────────────┐
           ▼                    ▼                    ▼
    ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
    │ L1 LATERAL  │      │    TECS     │      │ COORDINATED │
    │  GUIDANCE   │      │   ENERGY    │      │    TURN     │
    │             │      │             │      │             │
    │ cross_track │      │ altitude    │      │ bank = f(ω) │
    │ → yaw_rate  │      │ speed       │      │ → roll_rate │
    │             │      │ → pitch     │      │             │
    │             │      │ → thrust    │      │             │
    └─────────────┘      └─────────────┘      └─────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
    ┌──────────────────────────────────────────────────────────────┐
    │              PX4 ATTITUDE RATE COMMANDS                       │
    │     rollspeed, pitchspeed, yawspeed (deg/s) + thrust         │
    └──────────────────────────────────────────────────────────────┘
```

---

## L1 Navigation

L1 guidance converts cross-track error to lateral acceleration command.

### Algorithm

```python
# Cross-track error from target position
cross_track = target_x * reference_distance

# L1 lateral acceleration
eta = atan2(cross_track, L1_distance)
lateral_accel = 2 * (airspeed² / L1_distance) * sin(eta)

# Convert to yaw rate
yaw_rate = lateral_accel / airspeed
```

### Parameters

- **L1_DISTANCE**: Look-ahead distance (m). Larger = smoother, smaller = tighter
- **L1_DAMPING**: Damping factor (0.5-1.0)
- **L1_ADAPTIVE**: Enable speed-based L1 adjustment

### Tuning

| Scenario | L1_DISTANCE | L1_DAMPING |
|----------|-------------|------------|
| Tight pursuit | 20-30m | 0.6 |
| Standard | 50m | 0.75 |
| Long range | 80-100m | 0.85 |

---

## TECS (Total Energy Control System)

TECS coordinates pitch and throttle for efficient energy management.

### Concept

```
Total Energy = Potential Energy + Kinetic Energy
             = m*g*h + 0.5*m*v²

Energy Rate = altitude_rate + (v/g)*speed_rate
```

### Energy Distribution

```python
# Specific energy error
spe_error = (altitude_error * g) + (speed_error * airspeed)

# Energy balance
altitude_priority = weight * altitude_error
speed_priority = (1 - weight) * speed_error

# Control distribution
pitch_command = altitude_priority
throttle_command = total_energy_error
```

### Parameters

- **TECS_TIME_CONST**: Response time constant (s)
- **TECS_SPE_WEIGHT**: Altitude vs speed priority (0.0-2.0)
- **TECS_PITCH_DAMPING**: Pitch rate damping
- **TECS_THROTTLE_DAMPING**: Throttle rate damping

---

## Coordinated Turns

Calculates required bank angle for turn rate:

```python
# Bank angle for turn rate at airspeed
bank_angle = atan(yaw_rate * airspeed / GRAVITY)

# Limit by load factor
max_bank = acos(1 / max_load_factor)
bank_angle = clip(bank_angle, -max_bank, max_bank)

# Roll rate to achieve bank
roll_rate = (bank_angle - current_bank) * gain
```

---

## Configuration

### Config Section: `FW_ATTITUDE_RATE`

```yaml
FW_ATTITUDE_RATE:
  # Flight envelope
  MIN_AIRSPEED: 12.0               # m/s (stall speed + margin)
  CRUISE_AIRSPEED: 18.0            # m/s
  MAX_AIRSPEED: 30.0               # m/s

  # Structural limits
  MAX_BANK_ANGLE: 35.0             # degrees
  MAX_LOAD_FACTOR: 2.5             # g's
  MAX_PITCH_ANGLE: 25.0            # degrees
  MIN_PITCH_ANGLE: -20.0           # degrees

  # Rate limits (deg/s)
  MAX_ROLL_RATE: 45.0
  MAX_PITCH_RATE: 20.0
  MAX_YAW_RATE: 25.0

  # L1 Navigation
  L1_DISTANCE: 50.0                # meters
  L1_DAMPING: 0.75
  ENABLE_L1_ADAPTIVE: false
  L1_MIN_DISTANCE: 20.0
  L1_MAX_DISTANCE: 100.0

  # TECS
  ENABLE_TECS: true
  TECS_TIME_CONST: 5.0             # seconds
  TECS_SPE_WEIGHT: 1.0             # altitude/speed balance
  TECS_PITCH_DAMPING: 1.0
  TECS_THROTTLE_DAMPING: 0.5

  # Thrust control
  MIN_THRUST: 0.2
  MAX_THRUST: 1.0
  CRUISE_THRUST: 0.6
  THRUST_SLEW_RATE: 0.5            # per second

  # Coordinated turns
  ENABLE_COORDINATED_TURN: true
  TURN_COORDINATION_GAIN: 1.0
  SLIP_ANGLE_LIMIT: 5.0            # degrees

  # Stall protection
  ENABLE_STALL_PROTECTION: true
  STALL_RECOVERY_PITCH: -5.0       # degrees
  STALL_RECOVERY_THROTTLE: 1.0

  # Target loss handling
  TARGET_LOSS_TIMEOUT: 3.0         # seconds
  TARGET_LOSS_ACTION: "orbit"      # "orbit", "rtl", "continue_last"
  ORBIT_RADIUS: 100.0              # meters

  # Altitude safety
  ENABLE_ALTITUDE_SAFETY: true
  RTL_ON_ALTITUDE_VIOLATION: true
```

---

## Stall Protection

Automatic recovery when airspeed drops below safe threshold:

```python
if airspeed < (min_airspeed + stall_margin):
    # Emergency recovery
    pitch_command = stall_recovery_pitch  # Nose down
    thrust_command = stall_recovery_throttle  # Full power
    roll_command = level_wings()
```

---

## Target Loss Behavior

Options for target loss:

| Action | Behavior |
|--------|----------|
| `orbit` | Enter circular orbit at last position |
| `rtl` | Return to launch |
| `continue_last` | Maintain last heading (risky) |

---

## Tracker Requirements

**Required**: `POSITION_2D`
**Optional**: `VELOCITY_AWARE` (for predictive tracking)

---

## Telemetry

```python
status = follower.get_fw_status()
# {
#     'airspeed': 18.5,
#     'l1_cross_track': 2.3,
#     'l1_eta': 0.05,
#     'tecs_energy_error': 0.12,
#     'bank_angle': 15.2,
#     'stall_protection_active': False,
#     'target_loss_action': 'orbit'
# }
```

---

## Best Practices

1. **Always enable stall protection** - Critical for fixed-wing
2. **Tune L1 in simulation first** - Affects tracking tightness
3. **Conservative bank limits** - Structural protection
4. **TECS weight = 1.0** - Balance altitude/speed
5. **Set proper airspeed range** - Based on your aircraft
6. **Use orbit on target loss** - Safer than RTL in unknown terrain

---

## References

- Park, S., Deyst, J., & How, J. P. (2004). *A New Nonlinear Guidance Logic for Trajectory Tracking*. AIAA GNC Conference.
- Lambregts, A. A. (1983). *Vertical Flight Path and Speed Control Autopilot Design Using Total Energy Principles*. AIAA Paper 83-2239.
