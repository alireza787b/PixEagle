# Follower System Documentation

> Comprehensive guide to PixEagle's autonomous target following system

The follower system translates tracker evidence into aircraft command intent.
Profiles have distinct multicopter, fixed-wing and external/gimbal input
contracts. See the [qualification inventory](05-development/follower-sih-validation-matrix.md)
for actual response evidence and live availability; implementation is not flight qualification.

---

## Quick Navigation

| Section | Description |
|---------|-------------|
| [Architecture](01-architecture/README.md) | System design, inheritance, factory pattern |
| [Follower Reference](02-reference/README.md) | Registered follower purposes, contracts and qualification |
| [GNC Concepts](03-gnc-concepts/README.md) | Proportional Navigation, L1, TECS, PID |
| [Configuration](04-configuration/README.md) | Parameters, schema, tuning |
| [Development Guide](05-development/README.md) | Creating new followers |
| [Safety System](06-safety/README.md) | Safety limits and target continuity |
| [Integration](07-integration/README.md) | Tracker and MAVLink integration |

---

## Available Followers

### Multicopter (MC)

| Follower | Control Type | Use Case |
|----------|--------------|----------|
| [mc_velocity_chase](02-reference/mc-velocity-chase.md) | velocity_body_offboard | Image-error pursuit with a forward ramp |
| [mc_velocity_ground](02-reference/mc-velocity-ground.md) | velocity_body_offboard | Ground target tracking |
| [mc_velocity_distance](02-reference/mc-velocity-distance.md) | velocity_body_offboard | Visual centering with zero forward velocity |
| [mc_velocity_position](02-reference/mc-velocity-position.md) | velocity_body_offboard | Zero horizontal velocity with yaw/altitude |
| [mc_attitude_rate](02-reference/mc-attitude-rate.md) | attitude_rate | Aggressive rate-based control |

### Fixed-Wing (FW)

| Follower | Control Type | Use Case |
|----------|--------------|----------|
| [fw_navigation_chase](02-reference/fw-navigation-chase.md) | fixed_wing_external | Calibrated image pursuit through native PX4 navigation; experimental, live gate closed |
| [fw_attitude_rate](02-reference/fw-attitude-rate.md) | attitude_rate | Research visual guidance; current live gate remains |

### Gimbal (GM)

| Follower | Control Type | Use Case |
|----------|--------------|----------|
| [gm_velocity_chase](02-reference/gm-velocity-chase.md) | velocity_body_offboard | Velocity chase from gimbal angles |
| [gm_velocity_vector](02-reference/gm-velocity-vector.md) | velocity_body_offboard | Direct vector pursuit |

---

## Control Types

The existing profile schema uses two MAVSDK control types:

```
velocity_body_offboard - MAVSDK offboard velocity (vel_body_fwd, vel_body_right, vel_body_down)
attitude_rate          - Angular rate commands (rollspeed, pitchspeed, yawspeed, thrust)
```

### When to Use Each

- **velocity_body_offboard**: Most multicopter applications. Stable, GPS-aided control.
- **attitude_rate**: Advanced direct rates/thrust; it does not itself qualify GPS-denied or fixed-wing operation.

The experimental native image and Vector paths separately command FW course,
EAS and altitude/height rate. See the [FW policy](04-configuration/fixed-wing-guidance-policy.md).

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
│  - Explicit registered implementations and removed aliases      │
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
│ image inputs │   │ native/rates │   │ external rays│
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## Quick Start

### 1. Select a Follower Mode

In `configs/config.yaml`:

```yaml
Follower:
  FOLLOWER_MODE: "mc_velocity_chase"  # Optional image pursuit; factory default is mc_velocity_position
```

### 2. Configure Safety Limits

```yaml
Safety:
  GlobalLimits:
    MAX_VELOCITY: 1.0            # m/s
    MAX_VELOCITY_FORWARD: 0.5    # m/s
    MAX_VELOCITY_LATERAL: 0.5    # m/s
    MAX_VELOCITY_VERTICAL: 0.5   # m/s
    MAX_YAW_RATE: 45.0           # deg/s
```

Saved `Safety.FollowerOverrides` may only tighten the global envelope.
Supported session-speed controls deliberately replace saved velocity caps for
that session; they do not override altitude, rate, authority or circuit-breaker
protections. See [session speed](04-configuration/session-speed.md) before
interpreting saved versus effective limits.

### 3. Run PixEagle

```bash
bash scripts/run.sh
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
# Publish one complete, validated command snapshot
follower.set_command_fields({
    "vel_body_fwd": 5.0,
    "vel_body_right": 0.0,
    "vel_body_down": 0.0,
    "yawspeed_deg_s": 0.0,
})

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

- [Tracker & Follower Schema Guide](../developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md)
- [SmartTracker Guide](../trackers/02-reference/smart-tracker.md)
- [Configuration Guide](../CONFIGURATION.md)
- [Target Continuity](06-safety/target-continuity.md)
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
| `src/classes/target_continuity.py` | Shared target-evidence command authority |
