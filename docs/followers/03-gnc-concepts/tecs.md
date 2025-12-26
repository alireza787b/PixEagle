# TECS - Total Energy Control System

> Coordinated altitude and speed control for fixed-wing aircraft

TECS manages the aircraft's total energy by coordinating pitch and throttle commands. It treats altitude and speed as coupled variables sharing a common energy pool.

---

## Energy Concept

### Total Specific Energy

```
E_specific = h + V²/(2g)

Where:
h = Altitude
V = Airspeed
g = Gravity (9.81 m/s²)
```

### Energy Rate

```
Ė_specific = ḣ + (V/g) × V̇

           = altitude_rate + (V/g) × speed_rate
```

---

## Energy Distribution

### Key Insight

- **Throttle** controls total energy (altitude + speed)
- **Pitch** distributes energy between altitude and speed

```
┌──────────────────────────────────────────────┐
│               TOTAL ENERGY                    │
│                                              │
│    Throttle ↑ → More energy (climb/accel)   │
│    Throttle ↓ → Less energy (descend/decel) │
└──────────────────────┬───────────────────────┘
                       │
          Pitch redistributes
                       │
        ┌──────────────┴──────────────┐
        │              │              │
        ▼              ▼              ▼
   Nose Up        Level         Nose Down
   ↑ Altitude    Balanced      ↓ Altitude
   ↓ Speed       Both OK       ↑ Speed
```

---

## TECS Algorithm

### Error Computation

```python
# Energy errors
altitude_error = target_altitude - current_altitude
speed_error = target_speed - current_speed

# Specific energy errors
spe_altitude = altitude_error * g
spe_speed = speed_error * current_speed

# Total and balance errors
total_energy_error = spe_altitude + spe_speed
energy_balance_error = weight * spe_altitude - (1 - weight) * spe_speed
```

### Control Output

```python
# Throttle controls total energy
throttle_command = pid_throttle(total_energy_error)

# Pitch controls energy distribution
pitch_command = pid_pitch(energy_balance_error)
```

---

## Implementation

### PixEagle TECS

```python
def _compute_tecs_commands(self) -> Tuple[float, float]:
    """
    Compute pitch rate and thrust using TECS.

    Returns:
        (pitch_rate, thrust) commands
    """
    # Get current state
    altitude = self.current_altitude
    airspeed = self.current_airspeed

    # Target values (from tracking)
    target_altitude = self.desired_altitude
    target_speed = self.cruise_airspeed

    # Altitude error → energy error
    alt_error = target_altitude - altitude
    spe_altitude = alt_error * self.GRAVITY

    # Speed error → energy error
    spd_error = target_speed - airspeed
    spe_speed = spd_error * airspeed

    # Total energy error (throttle axis)
    total_energy_error = spe_altitude + spe_speed

    # Energy balance (pitch axis)
    weight = self.tecs_spe_weight  # Altitude priority (default 1.0)
    balance_error = weight * spe_altitude - (1 - weight) * spe_speed

    # Time-scaled errors
    tau = self.tecs_time_const
    total_energy_rate = total_energy_error / tau
    balance_rate = balance_error / tau

    # Throttle command
    thrust = self.cruise_thrust + self.pid_throttle(total_energy_rate)
    thrust *= self.tecs_throttle_damping
    thrust = clip(thrust, self.min_thrust, self.max_thrust)

    # Pitch rate command
    pitch_rate = self.pid_pitch(balance_rate)
    pitch_rate *= self.tecs_pitch_damping

    return pitch_rate, thrust
```

---

## Parameters

### Time Constant

Controls response speed:

```yaml
TECS_TIME_CONST: 5.0  # seconds

# Smaller = faster response (more aggressive)
# Larger = slower response (smoother)
```

### SPE Weight

Altitude vs speed priority:

```yaml
TECS_SPE_WEIGHT: 1.0

# 0.0 = Prioritize speed (ignore altitude errors)
# 1.0 = Equal priority
# 2.0 = Prioritize altitude (ignore speed errors)
```

### Damping

```yaml
TECS_PITCH_DAMPING: 1.0      # Pitch rate scaling
TECS_THROTTLE_DAMPING: 0.5   # Throttle scaling
```

---

## Configuration

### FW Attitude Rate Follower

```yaml
FW_ATTITUDE_RATE:
  # TECS
  ENABLE_TECS: true
  TECS_TIME_CONST: 5.0
  TECS_SPE_WEIGHT: 1.0
  TECS_PITCH_DAMPING: 1.0
  TECS_THROTTLE_DAMPING: 0.5

  # Thrust limits
  MIN_THRUST: 0.2
  MAX_THRUST: 1.0
  CRUISE_THRUST: 0.6
  THRUST_SLEW_RATE: 0.5  # Max change per second
```

---

## Thrust Slew Rate Limiting

Prevents sudden throttle changes:

```python
# Limit throttle rate of change
thrust_change = new_thrust - current_thrust
max_change = self.thrust_slew_rate * dt

if abs(thrust_change) > max_change:
    thrust_change = sign(thrust_change) * max_change

current_thrust += thrust_change
```

---

## Mode Priorities

### Climb Priority (TECS_SPE_WEIGHT > 1)

Altitude is more important than speed:
- Slower response to speed errors
- Faster climb/descent response
- May fly slower than target during climb

### Speed Priority (TECS_SPE_WEIGHT < 1)

Airspeed is more important:
- Maintains speed during maneuvers
- May deviate from target altitude
- Safer for stall prevention

### Balanced (TECS_SPE_WEIGHT = 1)

Equal priority:
- General purpose
- Recommended default

---

## Stall Prevention Integration

TECS integrates with stall protection:

```python
if airspeed < stall_speed + margin:
    # Override TECS - prioritize speed
    pitch_rate = stall_recovery_pitch
    thrust = max_thrust
```

---

## Limitations

1. **Requires accurate airspeed** - Pitot failure degrades performance
2. **Thrust authority** - Limited by engine power
3. **Wind effects** - Altitude changes require more energy in headwind
4. **Descent limits** - Drag limits descent rate without power

---

## References

- Lambregts, A. A. (1983). *Vertical Flight Path and Speed Control Autopilot Design Using Total Energy Principles*. AIAA Paper 83-2239.
- PX4 TECS Implementation: [github.com/PX4/PX4-Autopilot](https://github.com/PX4/PX4-Autopilot)
