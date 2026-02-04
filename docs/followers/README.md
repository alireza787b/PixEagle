# Follower System Documentation

> Comprehensive guide to PixEagle's autonomous target following system

The follower system is the control core of PixEagle, translating tracker output into vehicle commands for autonomous target following. It supports multicopters, fixed-wing aircraft, and gimbal-only tracking.

---

## Quick Navigation

| Section | Description |
|---------|-------------|
| [Architecture](01-architecture/README.md) | System design, inheritance, factory pattern |
| [Follower Reference](02-reference/README.md) | All 10 follower implementations |
| [GNC Concepts](03-gnc-concepts/README.md) | Proportional Navigation, L1, TECS, PID |
| [Configuration](04-configuration/README.md) | Parameters, schema, tuning |
| [Development Guide](05-development/README.md) | Creating new followers |
| [Safety System](06-safety/README.md) | SafetyManager, limits |
| [Integration](07-integration/README.md) | Tracker and MAVLink integration |

---

## Available Followers

### Multicopter (MC)

| Follower | Control Type | Use Case |
|----------|--------------|----------|
| [mc_velocity](02-reference/mc-velocity.md) | velocity_body_offboard | Dual-mode lateral guidance with hover |
| [mc_velocity_chase](02-reference/mc-velocity-chase.md) | velocity_body_offboard | Proportional Navigation pursuit |
| [mc_velocity_ground](02-reference/mc-velocity-ground.md) | velocity_body | Ground target tracking |
| [mc_velocity_distance](02-reference/mc-velocity-distance.md) | velocity_body_offboard | Constant distance maintenance |
| [mc_velocity_position](02-reference/mc-velocity-position.md) | velocity_body_offboard | Position hold with yaw/altitude |
| [mc_attitude_rate](02-reference/mc-attitude-rate.md) | attitude_rate | Aggressive rate-based control |

### Fixed-Wing (FW)

| Follower | Control Type | Use Case |
|----------|--------------|----------|
| [fw_attitude_rate](02-reference/fw-attitude-rate.md) | attitude_rate | L1 Navigation + TECS energy management |

### Gimbal (GM)

| Follower | Control Type | Use Case |
|----------|--------------|----------|
| [gm_pid_pursuit](02-reference/gm-pid-pursuit.md) | velocity_body_offboard | PID-based pursuit from gimbal angles |
| [gm_velocity_vector](02-reference/gm-velocity-vector.md) | velocity_body_offboard | Direct vector pursuit |

---

## Control Types

The follower system uses three control types:

```
velocity_body          - Legacy body-frame velocity (vel_x, vel_y, vel_z)
velocity_body_offboard - MAVSDK offboard velocity (vel_body_fwd, vel_body_right, vel_body_down)
attitude_rate          - Angular rate commands (rollspeed, pitchspeed, yawspeed, thrust)
```

### When to Use Each

- **velocity_body_offboard**: Most multicopter applications. Stable, GPS-aided control.
- **attitude_rate**: Fixed-wing (required), aggressive multicopter tracking, GPS-denied operation.
- **velocity_body**: Legacy compatibility only.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Follower Manager                          │
│  - Mode switching                                                │
│  - Telemetry aggregation                                        │
│  - Status reporting                                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FollowerFactory                             │
│  - Registry pattern (10 implementations + 15 aliases)           │
│  - Lazy initialization                                          │
│  - Profile validation                                           │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       BaseFollower (ABC)                         │
│  - SetpointHandler (schema-aware configuration)                 │
│  - SafetyManager integration (velocity/altitude limits)         │
│  - RateLimitedLogger (prevent log spam at 20Hz)                │
│  - Abstract: calculate_control_commands(), follow_target()      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ MC Followers  │   │ FW Followers  │   │ GM Followers  │
│ (6 variants)  │   │ (1 variant)   │   │ (2 variants)  │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## Quick Start

### 1. Select a Follower Mode

In `configs/config.yaml`:

```yaml
FOLLOWER_MODE: "mc_velocity_chase"  # Proportional Navigation pursuit
```

### 2. Configure Safety Limits

```yaml
SafetyLimits:
  MAX_VELOCITY_FORWARD: 10.0   # m/s
  MAX_VELOCITY_LATERAL: 5.0    # m/s
  MAX_VELOCITY_VERTICAL: 3.0   # m/s
  MAX_YAW_RATE: 45.0           # deg/s
```

### 3. Run PixEagle

```bash
bash run_pixeagle.sh
```

The follower automatically initializes based on your configuration.

---

## Key Concepts

### TrackerOutput

All followers receive tracker data via the `TrackerOutput` dataclass:

```python
TrackerOutput(
    data_type=TrackerDataType.POSITION_2D,
    timestamp=1703000000.0,
    tracking_active=True,
    position_2d=(0.15, -0.08),  # Normalized [-1, 1]
    confidence=0.95
)
```

### Setpoint Handler

Schema-aware configuration management:

```python
# Set velocity command
follower.set_command_field("vel_body_fwd", 5.0)

# Get all fields
fields = follower.get_all_command_fields()
# {'vel_body_fwd': 5.0, 'vel_body_right': 0.0, ...}
```

### Safety Integration

Automatic velocity clamping and altitude protection:

```python
# Velocity automatically clamped to configured limits
clamped = follower.clamp_velocity(15.0, 8.0, 5.0)
# (10.0, 5.0, 3.0)  # Clamped to MAX values
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `configs/config.yaml` | Main configuration (FOLLOWER_MODE, safety limits) |
| `configs/config_schema.yaml` | Schema definitions for config validation |
| `configs/follower_commands.yaml` | Follower profile definitions |

---

## Related Documentation

- [Tracker & Follower Schema Guide](../Tracker_and_Follower_Schema_Developer_Guide.md)
- [SmartTracker Guide](../trackers/02-reference/smart-tracker.md)
- [Configuration Guide](../CONFIGURATION.md)
- [Main README](../../README.md)

---

## Source Files

| File | Description |
|------|-------------|
| `src/classes/follower.py` | FollowerFactory and Follower manager |
| `src/classes/followers/base_follower.py` | Abstract base class |
| `src/classes/followers/*.py` | Individual follower implementations |
| `src/classes/safety_manager.py` | Centralized safety limits |
| `src/classes/setpoint_handler.py` | Schema-aware setpoint management |
