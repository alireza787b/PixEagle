# Limits Configuration

> Configuring safety limits for safe operation

`Safety.GlobalLimits` is the non-bypassable runtime envelope. All followers
read it through `SafetyManager`; sparse follower overrides may only make a
profile more restrictive.

---

## Global Limits (Single Source of Truth)

Set in `configs/config_default.yaml` under `Safety.GlobalLimits`:

```yaml
Safety:
  GlobalLimits:
    # Velocity Limits (SAFE defaults)
    MAX_VELOCITY: 1.0             # Max total velocity magnitude (m/s)
    MAX_VELOCITY_FORWARD: 0.5     # Max forward speed (m/s) - safe for testing
    MAX_VELOCITY_LATERAL: 0.5     # Max sideways speed (m/s)
    MAX_VELOCITY_VERTICAL: 0.5    # Max up/down speed (m/s)

    # Angular Rate Limits (deg/s)
    MAX_YAW_RATE: 45.0
    MAX_PITCH_RATE: 45.0
    MAX_ROLL_RATE: 45.0

    # Altitude Limits (meters)
    MIN_ALTITUDE: 3.0             # Minimum safe altitude
    MAX_ALTITUDE: 120.0           # Maximum altitude
    ALTITUDE_WARNING_BUFFER: 2.0  # Warning zone size
    ALTITUDE_SAFETY_ENABLED: true

  FollowerOverrides:              # Optional tighter profile limits
    MC_VELOCITY_POSITION:
      MAX_YAW_RATE: 10.0
```

---

## Per-Follower Overrides (Advanced Feature)

Use `Safety.FollowerOverrides` when one profile needs tighter limits or a
vehicle-appropriate target-loss action. To permit a larger operating envelope,
raise `Safety.GlobalLimits` deliberately first; a follower override cannot
bypass it.

```yaml
Safety:
  # Example: tighten limits for specific followers
  FollowerOverrides:
    MC_VELOCITY_CHASE:
      MAX_VELOCITY_FORWARD: 0.25  # Lower than the global 0.5 m/s ceiling
      MIN_ALTITUDE: 5.0           # Stricter minimum

    FW_ATTITUDE_RATE:
      MIN_ALTITUDE: 30.0          # Higher floor for fixed-wing
      MAX_ALTITUDE: 100.0         # Lower than the global 120 m ceiling
      TARGET_LOSS_ACTION: orbit   # Fixed-wing cannot hover
```

**Important**:
- All safety limits MUST be in `Safety.GlobalLimits` or `Safety.FollowerOverrides`
- Do NOT put velocity/altitude limits in follower sections directly
- All followers read limits via SafetyManager, not from config
- Maximum values and violation counts in an override must be less than or equal to global
- `MIN_ALTITUDE` and `ALTITUDE_WARNING_BUFFER` must be greater than or equal to global
- A globally enabled protection cannot be disabled by a follower override
- `TARGET_LOSS_ACTION` normally inherits the global policy; the only built-in
  substitution is fixed-wing `hover` to `orbit`

---

## Configuration Examples

Only the lab default below is a project default. Operational limits require a
vehicle/site hazard analysis, simulator evidence, and incremental flight-test
approval; PixEagle does not prescribe generic "production" speeds.

### Lab Default

```yaml
Safety:
  GlobalLimits:
    MAX_VELOCITY: 1.0
    MAX_VELOCITY_FORWARD: 0.5
    MAX_VELOCITY_LATERAL: 0.5
    MAX_VELOCITY_VERTICAL: 0.5
    MAX_YAW_RATE: 45.0
    MIN_ALTITUDE: 3.0
    MAX_ALTITUDE: 120.0
```

### Fixed-Wing Shape Example

```yaml
Safety:
  GlobalLimits:
    MAX_VELOCITY: 30.0
    MAX_VELOCITY_FORWARD: 30.0
    MAX_YAW_RATE: 25.0           # Lower for FW
    MIN_ALTITUDE: 30.0           # Higher minimum
    MAX_ALTITUDE: 200.0

  FollowerOverrides:
    FW_ATTITUDE_RATE:
      MIN_ALTITUDE: 30.0
      MAX_ALTITUDE: 180.0
      TARGET_LOSS_ACTION: orbit
```

---

## Resolution Order

When a limit is requested, SafetyManager resolves it in this order:

1. **FollowerOverrides.{follower}** - Valid, tightening per-follower value
2. **GlobalLimits** - Hard, non-bypassable envelope
3. **Fallback** - Hardcoded safety default

Persisted follower keys must use the canonical uppercase names exposed by the
schema. Runtime lookup accepts any case for compatibility. Unknown, duplicate,
or weakening profile definitions fail validation before publication.

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
