# PixEagle Configuration Refactoring Guide

## Overview

This document describes the Safety configuration system and PID/unit standardization in PixEagle. These changes provide a unified, safe, and maintainable configuration system for all followers.

**v5.0.0 Update**: The configuration has been simplified to use a single source of truth for safety limits.

---

## 1. Safety Configuration System (v5.0.0+)

### Purpose

The Safety system provides centralized, override-capable configuration for safety-critical parameters like altitude limits and velocity constraints.

### Configuration Structure

Located in `configs/config_default.yaml`:

```yaml
Safety:
  # === Global Limits (Single Source of Truth) ===
  GlobalLimits:
    MIN_ALTITUDE: 3.0            # Minimum safe altitude (meters AGL)
    MAX_ALTITUDE: 120.0          # Maximum safe altitude (meters AGL)
    ALTITUDE_WARNING_BUFFER: 2.0 # Warning zone buffer (meters)
    ALTITUDE_SAFETY_ENABLED: true

    MAX_VELOCITY: 15.0           # Maximum total velocity (m/s)
    MAX_VELOCITY_FORWARD: 8.0    # m/s
    MAX_VELOCITY_LATERAL: 5.0    # m/s
    MAX_VELOCITY_VERTICAL: 3.0   # m/s

    MAX_YAW_RATE: 45.0           # deg/s
    MAX_PITCH_RATE: 45.0         # deg/s
    MAX_ROLL_RATE: 45.0          # deg/s

  # === Per-Follower Overrides (optional) ===
  FollowerOverrides:
    MC_VELOCITY_CHASE:
      MIN_ALTITUDE: 5.0          # Stricter for chase mode
      MAX_ALTITUDE: 50.0

    MC_VELOCITY_GROUND:
      MIN_ALTITUDE: 40.0         # Much higher for ground view

    FW_ATTITUDE_RATE:
      MIN_ALTITUDE: 30.0         # Higher for fixed-wing
      MAX_ALTITUDE: 400.0
```

### Resolution Order

Limits are resolved in this order (first match wins):

1. **FollowerOverrides.{follower}** - Per-follower specific override
2. **GlobalLimits** - Single source of truth
3. **Fallback** - Hardcoded safety defaults

### Accessing Safety Limits

Use `Parameters.get_effective_limit()` or `SafetyManager` directly:

```python
from classes.parameters import Parameters

# Get global default
min_alt = Parameters.get_effective_limit('MIN_ALTITUDE')

# Get follower-specific override (falls back to GlobalLimits if not defined)
min_alt = Parameters.get_effective_limit('MIN_ALTITUDE', 'MC_VELOCITY_CHASE')

# Convenience methods
min_alt, max_alt = Parameters.get_altitude_limits('MC_VELOCITY_CHASE')
velocity = Parameters.get_velocity_limit('forward', 'MC_VELOCITY_CHASE')
```

Using SafetyManager directly:
```python
from classes.safety_manager import get_safety_manager

safety = get_safety_manager()
velocity_limits = safety.get_velocity_limits('MC_VELOCITY_CHASE')
altitude_limits = safety.get_altitude_limits('MC_VELOCITY_CHASE')

# Get detailed resolution info (for UI display)
summary = safety.get_effective_limits_summary('MC_VELOCITY_CHASE')
# Returns: {'MIN_ALTITUDE': {'effective_value': 5.0, 'source': 'FollowerOverrides.MC_VELOCITY_CHASE', ...}}
```

### Adding Override for a Follower

To add custom limits for a follower:

1. Add entry in `Safety.FollowerOverrides` section of config
2. Only specify parameters that differ from GlobalLimits
3. Access using `Parameters.get_effective_limit('PARAM', 'FOLLOWER_NAME')`

**Important**: Do NOT add MIN_ALTITUDE/MAX_ALTITUDE directly to follower sections (e.g., MC_VELOCITY_CHASE). These MUST be in Safety.FollowerOverrides.

---

## 2. Breaking Changes in v5.0.0

### Removed

| Removed | Replacement |
|---------|-------------|
| `SafetyLimits` section | `Safety.GlobalLimits` |
| `SafetyLimits.Overrides` | `Safety.FollowerOverrides` |
| `VehicleProfiles` | Removed (per-follower overrides only) |
| `Camera` section | `CSICamera` |
| Deprecated follower aliases (chase_follower, etc.) | Use canonical names (mc_velocity_chase, etc.) |
| Per-follower MIN_ALTITUDE/MAX_ALTITUDE | Move to Safety.FollowerOverrides |

### Migration

If your config has the old structure:

```yaml
# OLD (deprecated)
SafetyLimits:
  MIN_ALTITUDE: 3.0
  Overrides:
    CHASE_FOLLOWER:
      MIN_ALTITUDE: 5.0

MC_VELOCITY_CHASE:
  MIN_ALTITUDE: 5.0  # <- WRONG: duplicate!
```

Change to:

```yaml
# NEW (v5.0.0+)
Safety:
  GlobalLimits:
    MIN_ALTITUDE: 3.0
  FollowerOverrides:
    MC_VELOCITY_CHASE:
      MIN_ALTITUDE: 5.0

MC_VELOCITY_CHASE:
  # No altitude limits here - they're in Safety.FollowerOverrides
  PID_GAINS: ...
```

---

## 3. PID Gains and Angular Unit Standardization

### Standard: deg/s (MAVSDK Native)

All angular rate fields use **degrees per second (deg/s)** to match MAVSDK's native format.

### Standard Field Names

| Field Name | Unit | Description |
|------------|------|-------------|
| `yawspeed_deg_s` | deg/s | Yaw rate command |
| `pitchspeed_deg_s` | deg/s | Pitch rate command |
| `rollspeed_deg_s` | deg/s | Roll rate command |

### PID Gains Configuration

```yaml
PID_GAINS:
  yawspeed_deg_s:
    kp: 0.5
    ki: 0.0
    kd: 0.1

  pitchspeed_deg_s:
    kp: 0.3
    ki: 0.0
    kd: 0.05
```

---

## 4. Schema-Driven Command Fields

The follower command schema is defined in `configs/follower_commands.yaml`.

### Control Types

| Control Type | Fields | MAVSDK Method |
|--------------|--------|---------------|
| `velocity_body` | vel_x, vel_y, vel_z, yawspeed_deg_s | `set_velocity_body()` |
| `attitude_rate` | rollspeed_deg_s, pitchspeed_deg_s, yawspeed_deg_s, thrust | `set_attitude_rate()` |

---

## 5. Quick Reference

### Adding a New Follower Checklist

1. [ ] Inherit from `BaseFollower`
2. [ ] Define profile in `configs/follower_commands.yaml`
3. [ ] Register in `src/classes/follower.py` FollowerFactory
4. [ ] Use `Parameters.get_effective_limit()` for altitude/velocity limits
5. [ ] Use deg/s for all angular rate fields
6. [ ] Add follower-specific overrides in `Safety.FollowerOverrides` if needed
7. [ ] Do NOT add MIN_ALTITUDE/MAX_ALTITUDE in the follower section itself

### Key Files

| File | Purpose |
|------|---------|
| `configs/config_default.yaml` | Main configuration (Safety, PID gains) |
| `configs/follower_commands.yaml` | Command field schema and profiles |
| `src/classes/safety_manager.py` | Centralized safety limit management |
| `src/classes/parameters.py` | Configuration access methods |
| `src/classes/setpoint_handler.py` | Schema-aware setpoint management |
| `src/classes/followers/base_follower.py` | Base class for all followers |

---

## Version History

- **v5.0.0** (January 2025): Single source of truth refactor
  - Renamed `SafetyLimits` → `Safety.GlobalLimits`
  - Renamed `SafetyLimits.Overrides` → `Safety.FollowerOverrides`
  - Removed per-follower MIN_ALTITUDE/MAX_ALTITUDE from follower sections
  - Removed VehicleProfiles (deprecated since v3.6.0)
  - Deprecated follower aliases now raise ValueError
  - Added startup validation for config structure
  - Added new API endpoints for effective limits

- **v1.1** (December 2024): Legacy cleanup
  - Removed `VelocityDescent` section
  - Migrated `VELOCITY_LIMITS` to SafetyLimits section

- **v1.0** (December 2024): Initial SafetyLimits and PID standardization
  - Unified altitude limit access via `Parameters.get_effective_limit()`
  - Standardized angular rates to deg/s (MAVSDK native)
