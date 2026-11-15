# Limits Configuration

> Configuring safety limits for safe operation

`Safety.GlobalLimits` defines the saved envelope. All followers
read it through `SafetyManager`; sparse follower overrides may only make a
profile more restrictive.
An explicit [session speed override](../04-configuration/session-speed.md) on a
supported follower temporarily replaces velocity caps only. Restore removes
that owned override; saved limits and non-velocity protections are unchanged.

The public factory profile uses **MC Position**, target-altitude guidance off,
a shared **30 m relative-altitude floor** for MC/FW and a 120 m upper limit.
The existing 2 m warning buffer makes Start require at least **32 m**. These
are evaluation defaults, not a terrain-clearance guarantee. Native FW airspeed
remains constrained by PX4's minimum/trim/envelope; MC velocity caps are not FW
airspeed settings. The circuit breaker remains enabled.

Saved explicit values remain unchanged. Config Sync shows the new factory floor;
only an explicit adoption replaces a saved floor. Private research overlays
belong outside the repository and must explicitly supply their operating limits.

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
    MIN_ALTITUDE: 30.0            # Common MC/FW relative-altitude floor
    MAX_ALTITUDE: 120.0           # Maximum altitude
    ALTITUDE_WARNING_BUFFER: 2.0  # Warning zone size
    ALTITUDE_SAFETY_ENABLED: true

  FollowerOverrides:              # Optional tighter profile limits
    MC_VELOCITY_POSITION:
      MAX_YAW_RATE: 10.0
```

---

### Optional upper mission ceiling

From schema 1.10, `Safety.GlobalLimits.MAX_ALTITUDE: null` explicitly removes the application
mission ceiling. The checked-in default remains `120.0`; omitting the key from
a sparse overlay or import inherits that default, while a complete validated
`GlobalLimits` section must include the key. Existing numeric settings retain
their meaning. Export, import, API summaries, and configuration editors preserve
explicit `null`.

`Safety.FollowerOverrides` may supply a finite `MAX_ALTITUDE` to tighten an
unbounded global envelope. Omit the follower key to inherit; explicit follower
`null` remains invalid and cannot remove a finite global ceiling. No existing
saved configuration is automatically migrated to an unbounded setting.

The lower bound and warning buffer remain active. With `MIN_ALTITUDE: 30.0` and
`ALTITUDE_WARNING_BUFFER: 2.0`, the hard floor is 30 m and following starts at or
above 32 m; native FW descent lookahead can intervene earlier. Fast MC descent
needs its own measured braking qualification. These heights are relative
to the estimator's home reference, not terrain clearance. Removing a mission
ceiling changes no native climb/sink, acceleration, underspeed, attitude,
actuator, or speed limits. Sensorless operation still depends on native
estimation and its declared airspeedless capability; it does not establish a
measured airspeed or a physical operating envelope.

---

## Per-Follower Overrides (Advanced Feature)

Use `Safety.FollowerOverrides` when one profile needs tighter limits.
To permit a larger operating envelope, raise `Safety.GlobalLimits`
deliberately first; a follower override cannot bypass it. Target-evidence
authority is configured separately under `TargetContinuity`.

```yaml
Safety:
  # Example: tighten limits for specific followers
  FollowerOverrides:
    MC_VELOCITY_CHASE:
      MAX_VELOCITY_FORWARD: 0.25  # Lower than the global 0.5 m/s ceiling
      MIN_ALTITUDE: 35.0          # Stricter than the 30 m global floor

    FW_ATTITUDE_RATE:
      MIN_ALTITUDE: 40.0          # Stricter site-specific floor
      MAX_ALTITUDE: 100.0         # Lower than the global 120 m ceiling
```

**Important**:
- All safety limits MUST be in `Safety.GlobalLimits` or `Safety.FollowerOverrides`
- Do NOT put velocity/altitude limits in follower sections directly
- All followers read limits via SafetyManager, not from config
- Maximum values and violation counts in an override must be less than or equal to global
- `MIN_ALTITUDE` and `ALTITUDE_WARNING_BUFFER` must be greater than or equal to global
- A globally enabled protection cannot be disabled by a follower override
- Target loss/recovery behavior is not a safety-limit override; see
  [Target Continuity](target-continuity.md)

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
    MIN_ALTITUDE: 30.0
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
```

---

## Resolution Order

When a limit is requested, SafetyManager resolves it in this order:

1. **FollowerOverrides.{follower}** - Valid, tightening per-follower value
2. **GlobalLimits** - Saved envelope; explicit session velocity overrides resolve through the same manager
3. **Fallback** - Hardcoded safety default

Persisted follower keys must use the canonical uppercase names exposed by the
schema. Runtime lookup accepts any case for compatibility. Unknown, duplicate,
or weakening profile definitions fail validation before publication.

Example:
```python
# For MC_VELOCITY_CHASE:
# - MIN_ALTITUDE: 35.0 (from FollowerOverrides.MC_VELOCITY_CHASE)
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
