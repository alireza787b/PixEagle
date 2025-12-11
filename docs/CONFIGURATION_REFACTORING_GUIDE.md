# PixEagle Configuration Refactoring Guide

## Overview

This document describes the SafetyLimits system and PID/unit standardization refactoring implemented in PixEagle. These changes provide a unified, safe, and maintainable configuration system for all followers.

---

## 1. SafetyLimits System

### Purpose

The SafetyLimits system provides a centralized, override-capable configuration for safety-critical parameters like altitude limits and velocity constraints.

### Configuration Structure

Located in `configs/config_default.yaml`:

```yaml
SafetyLimits:
  # === Global Defaults ===
  MIN_ALTITUDE: 5.0          # Minimum safe altitude (meters AGL)
  MAX_ALTITUDE: 120.0        # Maximum safe altitude (meters AGL)
  MAX_VELOCITY_FORWARD: 8.0  # m/s
  MAX_VELOCITY_LATERAL: 5.0  # m/s
  MAX_VELOCITY_VERTICAL: 3.0 # m/s
  MAX_YAW_RATE: 45.0         # deg/s

  # === Follower-Specific Overrides ===
  Overrides:
    CHASE_FOLLOWER:
      MIN_ALTITUDE: 10.0
      MAX_ALTITUDE: 100.0

    GimbalFollower:
      MIN_ALTITUDE: 3.0
      MAX_ALTITUDE: 150.0
```

### How to Access SafetyLimits

Use `Parameters.get_effective_limit()` for unified access:

```python
from classes.parameters import Parameters

# Get global default
min_alt = Parameters.get_effective_limit('MIN_ALTITUDE')

# Get follower-specific override (falls back to global if not defined)
min_alt = Parameters.get_effective_limit('MIN_ALTITUDE', 'CHASE_FOLLOWER')
```

### Adding New Followers

When creating a new follower:

1. Define default limits in the global `SafetyLimits` section
2. Add follower-specific overrides in `SafetyLimits.Overrides` if needed
3. Access limits using `Parameters.get_effective_limit('LIMIT_NAME', 'FOLLOWER_KEY')`

Example:
```python
class MyNewFollower(BaseFollower):
    def __init__(self, px4_controller, profile_name):
        super().__init__(px4_controller, profile_name)

        # Use unified SafetyLimits access
        self.min_altitude = Parameters.get_effective_limit('MIN_ALTITUDE', 'MY_NEW_FOLLOWER')
        self.max_altitude = Parameters.get_effective_limit('MAX_ALTITUDE', 'MY_NEW_FOLLOWER')
```

---

## 2. PID Gains and Angular Unit Standardization

### Standard: deg/s (MAVSDK Native)

All angular rate fields use **degrees per second (deg/s)** to match MAVSDK's native format. This eliminates conversion errors and simplifies the codebase.

### Standard Field Names

| Field Name | Unit | Description |
|------------|------|-------------|
| `yawspeed_deg_s` | deg/s | Yaw rate command |
| `pitchspeed_deg_s` | deg/s | Pitch rate command |
| `rollspeed_deg_s` | deg/s | Roll rate command |

### PID Gains Configuration

Located in `configs/config_default.yaml`:

```yaml
PID_GAINS:
  # Yaw rate control (deg/s output)
  yawspeed_deg_s:
    kp: 0.5
    ki: 0.0
    kd: 0.1

  # Pitch rate control (deg/s output)
  pitchspeed_deg_s:
    kp: 0.3
    ki: 0.0
    kd: 0.05

  # Roll rate control (deg/s output)
  rollspeed_deg_s:
    kp: 0.3
    ki: 0.0
    kd: 0.05
```

### Accessing PID Gains

```python
from classes.parameters import Parameters

# Get PID gains for yaw rate
yaw_gains = Parameters.get_pid_gains('yawspeed_deg_s')
kp = yaw_gains.get('kp', 0.5)
ki = yaw_gains.get('ki', 0.0)
kd = yaw_gains.get('kd', 0.1)
```

---

## 3. Field Name Migration Table

### Deprecated Field Names

| Old Name (DEPRECATED) | New Name | Unit | Notes |
|----------------------|----------|------|-------|
| `yaw_rate` | `yawspeed_deg_s` | deg/s | Was rad/s, required conversion |
| `pitch_rate` | `pitchspeed_deg_s` | deg/s | Was rad/s, required conversion |
| `roll_rate` | `rollspeed_deg_s` | deg/s | Was rad/s, required conversion |
| `yaw_speed_deg_s` | `yawspeed_deg_s` | deg/s | Typo variant |

### Deprecated Parameter Names

| Old Name (DEPRECATED) | New Name | Location |
|----------------------|----------|----------|
| `MIN_DESCENT_HEIGHT` | `MIN_ALTITUDE` | SafetyLimits section |
| `MAX_CLIMB_HEIGHT` | `MAX_ALTITUDE` | SafetyLimits section |
| `MIN_ALTITUDE_SAFETY` | `MIN_ALTITUDE` | SafetyLimits section |
| `MAX_ALTITUDE_SAFETY` | `MAX_ALTITUDE` | SafetyLimits section |
| `GIMBAL_MIN_ALTITUDE_SAFETY` | `MIN_ALTITUDE` (with GimbalFollower override) | SafetyLimits.Overrides |
| `VELOCITY_LIMITS['vel_body_fwd']` | `MAX_VELOCITY_FORWARD` | SafetyLimits section |
| `VELOCITY_LIMITS['vel_body_right']` | `MAX_VELOCITY_LATERAL` | SafetyLimits section |
| `VELOCITY_LIMITS['vel_body_down']` | `MAX_VELOCITY_VERTICAL` | SafetyLimits section |
| `VelocityDescent` section | **REMOVED** | Params moved to SafetyLimits, GROUND_VIEW, Tracking |

---

## 4. Schema-Driven Command Fields

The follower command schema is defined in `configs/follower_commands.yaml`.

### Control Types

| Control Type | Fields | MAVSDK Method |
|--------------|--------|---------------|
| `velocity_body` | vel_x, vel_y, vel_z, yawspeed_deg_s | `set_velocity_body()` |
| `attitude_rate` | rollspeed_deg_s, pitchspeed_deg_s, yawspeed_deg_s, thrust | `set_attitude_rate()` |

### Field Definitions

Fields are defined with type, units, limits, and defaults:

```yaml
command_fields:
  yawspeed_deg_s:
    type: float
    unit: deg/s
    description: "Yaw angular rate (MAVSDK standard)"
    default: 0.0
    limits:
      min: -90.0
      max: 90.0
    clamp: true
```

---

## 5. SetpointHandler Usage

The `SetpointHandler` class provides schema-aware setpoint management:

```python
from classes.setpoint_handler import SetpointHandler

# Initialize with profile name
handler = SetpointHandler("chase_follower")

# Set fields (automatically validated and clamped)
handler.set_field('yawspeed_deg_s', 30.0)
handler.set_field('pitchspeed_deg_s', 10.0)
handler.set_field('thrust', 0.5)

# Get all fields
fields = handler.get_fields()
```

### Validation and Clamping

- Values are automatically validated against limits
- If `clamp: true` (default), out-of-range values are clamped with a warning
- If `clamp: false`, out-of-range values raise `ValueError`

---

## 6. Circuit Breaker Safety

The circuit breaker system blocks actual PX4 commands during testing:

```python
from classes.circuit_breaker import FollowerCircuitBreaker

# Check if circuit breaker is active
if FollowerCircuitBreaker.is_active():
    # Commands will be logged but not sent to PX4
    pass
```

Configuration:
```yaml
CIRCUIT_BREAKER:
  ENABLED: true              # Enable circuit breaker
  AUTO_DISABLE_ON_ARM: true  # Auto-disable when drone arms
```

---

## 7. Future Improvements

### Variable Naming Standardization

Internal variable names vary across followers:
- `min_descent_height` / `max_climb_height` (chase_follower, constant_distance_follower)
- `min_altitude_limit` / `max_altitude_limit` (body_velocity_chase_follower)
- `min_altitude_safety` / `max_altitude_safety` (gimbal_follower)

Future refactoring should standardize to `min_altitude` / `max_altitude` for consistency.

---

## 8. Quick Reference

### Adding a New Follower Checklist

1. [ ] Inherit from `BaseFollower`
2. [ ] Define profile in `configs/follower_commands.yaml`
3. [ ] Use `Parameters.get_effective_limit()` for altitude/velocity limits
4. [ ] Use `Parameters.get_pid_gains()` for PID configuration
5. [ ] Set command fields using `self.set_command_field()`
6. [ ] Use deg/s for all angular rate fields
7. [ ] Add follower-specific overrides in SafetyLimits if needed

### Key Files

| File | Purpose |
|------|---------|
| `configs/config_default.yaml` | Main configuration (SafetyLimits, PID gains) |
| `configs/follower_commands.yaml` | Command field schema and profiles |
| `src/classes/parameters.py` | Configuration access methods |
| `src/classes/setpoint_handler.py` | Schema-aware setpoint management |
| `src/classes/followers/base_follower.py` | Base class for all followers |
| `src/classes/px4_interface_manager.py` | PX4/MAVSDK command interface |

---

## Version History

- **v1.1** (December 2024): Complete legacy removal - clean config
  - Removed `VelocityDescent` LEGACY section entirely
  - Migrated `VELOCITY_LIMITS` dict to `SafetyLimits` section
  - Updated `body_velocity_chase_follower.py` to use `Parameters.get_effective_limit()`
  - Moved `DESIRE_AIM` to `Tracking` section
  - No more "LEGACY" or "deprecated" labels in config file
  - Config file is now clean and unified

- **v1.0** (December 2024): Initial SafetyLimits and PID standardization refactoring
  - Unified altitude limit access via `Parameters.get_effective_limit()`
  - Standardized angular rates to deg/s (MAVSDK native)
  - Consolidated PID gain names: `yawspeed_deg_s`, `pitchspeed_deg_s`, `rollspeed_deg_s`
  - Fixed critical rad→deg conversion bug in px4_interface_manager
  - Added deprecation notices for old parameter names
