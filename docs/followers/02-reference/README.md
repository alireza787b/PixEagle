# Follower Reference

> Detailed documentation for all 8 follower implementations

This section provides comprehensive documentation for each follower, including control algorithms, configuration parameters, and use cases.

---

## Quick Reference

### Multicopter (MC) - Velocity Control

| Follower | Profile | Use Case | Key Feature |
|----------|---------|----------|-------------|
| [mc_velocity_chase](mc-velocity-chase.md) | `mc_velocity_chase` | Forward pursuit | Velocity ramping, PN guidance |
| [mc_velocity_ground](mc-velocity-ground.md) | `mc_velocity_ground` | Ground tracking | 3-axis control, gimbal correction |
| [mc_velocity_distance](mc-velocity-distance.md) | `mc_velocity_distance` | Visual centering | Zero forward velocity; no range hold |
| [mc_velocity_position](mc-velocity-position.md) | `mc_velocity_position` | Position hold | Yaw + altitude only |

### Multicopter (MC) - Attitude Rate Control

| Follower | Profile | Use Case | Key Feature |
|----------|---------|----------|-------------|
| [mc_attitude_rate](mc-attitude-rate.md) | `mc_attitude_rate` | High-authority visual control | Direct rate and thrust commands |

### Fixed-Wing (FW)

| Follower | Profile | Use Case | Key Feature |
|----------|---------|----------|-------------|
| [fw_attitude_rate](fw-attitude-rate.md) | `fw_attitude_rate` | Fixed-wing pursuit | L1 Navigation + TECS |

### Gimbal (GM)

| Follower | Profile | Use Case | Key Feature |
|----------|---------|----------|-------------|
| [gm_velocity_chase](gm-velocity-chase.md) | `gm_velocity_chase` | Gimbal-based | Velocity chase control |
| [gm_velocity_vector](gm-velocity-vector.md) | `gm_velocity_vector` | Vector pursuit | Direct gimbal angles |

---

## Control Types

### velocity_body_offboard

Used by most multicopter followers. Commands are sent via MAVSDK
`set_velocity_body()`; `velocity_body_offboard` is PixEagle's control-type name.

**Fields**: `vel_body_fwd`, `vel_body_right`, `vel_body_down`, `yawspeed_deg_s`

```python
# Example usage
follower.set_command_fields({
    'vel_body_fwd': 5.0,      # Forward velocity (m/s)
    'vel_body_right': 0.0,    # Right velocity (m/s)
    'vel_body_down': 0.5,     # Down velocity (m/s)
    'yawspeed_deg_s': 10.0,   # Yaw rate (deg/s)
})
```

### attitude_rate

Used by the fixed-wing and multicopter attitude-rate profiles. These are direct
angular-rate and thrust commands.

**Fields**: `rollspeed_deg_s`, `pitchspeed_deg_s`, `yawspeed_deg_s`, `thrust`

```python
# Example usage
follower.set_command_fields({
    'rollspeed_deg_s': 5.0,   # Roll rate (deg/s)
    'pitchspeed_deg_s': 2.0,  # Pitch rate (deg/s)
    'yawspeed_deg_s': 0.0,    # Yaw rate (deg/s)
    'thrust': 0.65,           # Thrust (0.0-1.0)
})
```

## Common Patterns

### PID Control

All followers use `CustomPID` controllers with anti-windup:

```python
from classes.followers.custom_pid import CustomPID

pid = CustomPID(
    Kp=1.0, Ki=0.1, Kd=0.05,
    setpoint=0.0,
    output_limits=(-10.0, 10.0)
)

# Update command
output = pid(current_error)
```

### Target Loss Handling

Multicopter followers can hover on target loss:

```python
# In config.yaml
MC_VELOCITY_CHASE:
  TARGET_LOSS_ACTION: "hover"    # or "rtl", "slow_forward"
  TARGET_LOSS_TIMEOUT: 2.0       # seconds
```

### Safety Limits

All followers respect SafetyManager limits:

```python
# Automatic clamping via base class
vel_fwd, vel_right, vel_down = self.clamp_velocity(15.0, 8.0, 5.0)
# Returns (10.0, 5.0, 3.0) based on Safety.GlobalLimits
```

---

## Selection Guide

### By Vehicle Type

| Vehicle | Recommended Follower | Reason |
|---------|---------------------|--------|
| Quadcopter | `mc_velocity_chase` | Velocity ramping, hover on loss |
| Fixed-wing | `fw_attitude_rate` | Current visual attitude-rate profile; airframe acceptance required |
| Gimbal-only | `gm_velocity_chase` | Direct gimbal control |

### By Use Case

| Scenario | Recommended Follower | Reason |
|----------|---------------------|--------|
| Chase from behind | `mc_velocity_chase` | Forward ramping, PN guidance |
| Center without forward motion | `mc_velocity_distance` | Lateral/vertical centering compatibility profile |
| Stationary tracking | `mc_velocity_position` | Position hold |
| Ground targets | `mc_velocity_ground` | 3-axis + altitude |
| Direct MC attitude authority | `mc_attitude_rate` | Direct rate and thrust control |
| Fixed-wing evaluation | `fw_attitude_rate` | L1/TECS-inspired visual control |

### By Tracker Type

| Tracker Data | Compatible Followers |
|--------------|---------------------|
| POSITION_2D | All except gimbal |
| GIMBAL_ANGLES | `gm_velocity_chase`, `gm_velocity_vector` |
| POSITION_3D | All (uses 2D projection) |

---

## Configuration Section Names

Each follower reads from a specific config section:

| Follower | Config Section |
|----------|----------------|
| mc_velocity_chase | `MC_VELOCITY_CHASE` |
| mc_velocity_ground | `MC_VELOCITY_GROUND` |
| mc_velocity_distance | `MC_VELOCITY_DISTANCE` |
| mc_velocity_position | `MC_VELOCITY_POSITION` |
| mc_attitude_rate | `MC_ATTITUDE_RATE` |
| fw_attitude_rate | `FW_ATTITUDE_RATE` |
| gm_velocity_chase | `GM_VELOCITY_CHASE` |
| gm_velocity_vector | `GM_VELOCITY_VECTOR` |

---

## Source Files

| Follower | Source File | Lines |
|----------|-------------|-------|
| mc_velocity_chase | `src/classes/followers/mc_velocity_chase_follower.py` | ~1,800 |
| mc_velocity_ground | `src/classes/followers/mc_velocity_ground_follower.py` | ~615 |
| mc_velocity_distance | `src/classes/followers/mc_velocity_distance_follower.py` | ~400 |
| mc_velocity_position | `src/classes/followers/mc_velocity_position_follower.py` | ~350 |
| mc_attitude_rate | `src/classes/followers/mc_attitude_rate_follower.py` | ~500 |
| fw_attitude_rate | `src/classes/followers/fw_attitude_rate_follower.py` | ~1,500 |
| gm_velocity_chase | `src/classes/followers/gm_velocity_chase_follower.py` | ~600 |
| gm_velocity_vector | `src/classes/followers/gm_velocity_vector_follower.py` | ~400 |
