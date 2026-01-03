# Limits Configuration

> Configuring safety limits for safe operation

**v5.0.0+**: Safety limits use a single source of truth structure.

---

## Global Limits (Single Source of Truth)

Set in `configs/config.yaml` under `Safety.GlobalLimits`:

```yaml
Safety:
  GlobalLimits:
    # Velocity Limits (m/s)
    MAX_VELOCITY: 15.0            # Max total velocity
    MAX_VELOCITY_FORWARD: 10.0    # Max forward speed
    MAX_VELOCITY_LATERAL: 5.0     # Max sideways speed
    MAX_VELOCITY_VERTICAL: 3.0    # Max up/down speed

    # Angular Rate Limits (deg/s)
    MAX_YAW_RATE: 45.0
    MAX_PITCH_RATE: 30.0
    MAX_ROLL_RATE: 60.0

    # Altitude Limits (meters)
    MIN_ALTITUDE: 3.0             # Minimum safe altitude
    MAX_ALTITUDE: 120.0           # Maximum altitude
    ALTITUDE_WARNING_BUFFER: 2.0  # Warning zone size
    ALTITUDE_SAFETY_ENABLED: true
```

---

## Per-Follower Overrides

Override global limits for specific followers under `Safety.FollowerOverrides`:

```yaml
Safety:
  FollowerOverrides:
    # Stricter limits for chase mode
    MC_VELOCITY_CHASE:
      MIN_ALTITUDE: 5.0
      MAX_ALTITUDE: 50.0

    # Much higher minimum for ground view
    MC_VELOCITY_GROUND:
      MIN_ALTITUDE: 40.0

    # Higher altitude for fixed-wing
    FW_ATTITUDE_RATE:
      MIN_ALTITUDE: 30.0
      MAX_ALTITUDE: 400.0

    # Lower velocity for precision gimbal tracking
    GM_PID_PURSUIT:
      MIN_ALTITUDE: 5.0
      MAX_ALTITUDE: 100.0
```

**Important**: Do NOT put MIN_ALTITUDE/MAX_ALTITUDE in follower sections directly. They MUST be in `Safety.FollowerOverrides`.

---

## Recommended Limits by Scenario

### Indoor / Confined Space

```yaml
Safety:
  GlobalLimits:
    MAX_VELOCITY_FORWARD: 3.0
    MAX_VELOCITY_LATERAL: 2.0
    MAX_VELOCITY_VERTICAL: 1.0
    MAX_YAW_RATE: 30.0
    MIN_ALTITUDE: 1.0
    MAX_ALTITUDE: 10.0
```

### Open Field (Testing)

```yaml
Safety:
  GlobalLimits:
    MAX_VELOCITY_FORWARD: 8.0
    MAX_VELOCITY_LATERAL: 5.0
    MAX_VELOCITY_VERTICAL: 3.0
    MAX_YAW_RATE: 45.0
    MIN_ALTITUDE: 5.0
    MAX_ALTITUDE: 50.0
```

### Production (Experienced)

```yaml
Safety:
  GlobalLimits:
    MAX_VELOCITY_FORWARD: 15.0
    MAX_VELOCITY_LATERAL: 8.0
    MAX_VELOCITY_VERTICAL: 5.0
    MAX_YAW_RATE: 60.0
    MIN_ALTITUDE: 3.0
    MAX_ALTITUDE: 120.0
```

### Fixed-Wing

```yaml
Safety:
  GlobalLimits:
    MAX_VELOCITY: 40.0
    MAX_VELOCITY_FORWARD: 30.0
    MAX_YAW_RATE: 25.0           # Lower for FW
    MIN_ALTITUDE: 30.0           # Higher minimum
    MAX_ALTITUDE: 200.0

  FollowerOverrides:
    FW_ATTITUDE_RATE:
      MIN_ALTITUDE: 30.0
      MAX_ALTITUDE: 400.0
```

---

## Resolution Order

When a limit is requested, SafetyManager resolves it in this order:

1. **FollowerOverrides.{follower}** - Per-follower override
2. **GlobalLimits** - Single source of truth
3. **Fallback** - Hardcoded safety default

**Note:** Follower name lookup is case-insensitive. Both `mc_velocity_chase` and `MC_VELOCITY_CHASE` will correctly find overrides defined as `MC_VELOCITY_CHASE` in the config.

Example:
```python
# For MC_VELOCITY_CHASE:
# - MIN_ALTITUDE: 5.0 (from FollowerOverrides.MC_VELOCITY_CHASE)
# - MAX_VELOCITY: 15.0 (from GlobalLimits, no override)
```

---

## Accessing Limits in Code

```python
from classes.safety_manager import get_safety_manager

safety = get_safety_manager()

# Get altitude limits
altitude_limits = safety.get_altitude_limits('MC_VELOCITY_CHASE')
print(f"Min: {altitude_limits.min_altitude}, Max: {altitude_limits.max_altitude}")

# Get velocity limits
velocity_limits = safety.get_velocity_limits('MC_VELOCITY_CHASE')
print(f"Forward: {velocity_limits.forward} m/s")

# Get detailed resolution info (for debugging)
summary = safety.get_effective_limits_summary('MC_VELOCITY_CHASE')
for param, info in summary.items():
    print(f"{param}: {info['effective_value']} (source: {info['source']})")
```

---

## Startup Validation

On startup, PixEagle validates the config structure:

- Checks for deprecated SafetyLimits section (logs error)
- Checks for MIN_ALTITUDE/MAX_ALTITUDE in follower sections (logs warning)
- Validates Safety.GlobalLimits exists (logs error if missing)

---

## Checklist

Before flight:

- [ ] Safety.GlobalLimits configured with appropriate values
- [ ] Safety.FollowerOverrides set for any special modes
- [ ] No MIN_ALTITUDE/MAX_ALTITUDE in follower sections
- [ ] Warning buffer adequate
- [ ] Limits tested in SITL
