# Safety System

> Centralized safety management for PixEagle followers

The safety system provides velocity/altitude limits, per-follower overrides, and runtime enforcement.

---

## Documents

| Document | Description |
|----------|-------------|
| [SafetyManager](safety-manager.md) | Centralized limits manager |
| [Limits Configuration](limits-configuration.md) | Configuring safety limits |

---

## Safety Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SafetyManager (Singleton)                 │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ GlobalLimits │  │ VelocityLimits│  │ AltitudeLimits│      │
│  │              │  │              │  │              │      │
│  │ forward: 10  │  │ per-follower │  │ min: 5m      │      │
│  │ lateral: 5   │  │ overrides    │  │ max: 120m    │      │
│  │ vertical: 3  │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────┬───────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ Follower │   │ Follower │   │ Follower │
        │  Chase   │   │  Ground  │   │    FW    │
        └──────────┘   └──────────┘   └──────────┘
```

---

## Key Features

### Velocity Limiting

```python
# Automatic clamping in BaseFollower
vel_fwd, vel_right, vel_down = self.clamp_velocity(15.0, 8.0, 5.0)
# Returns (10.0, 5.0, 3.0) based on SafetyLimits
```

### Altitude Protection

```python
# Altitude check
if current_altitude < safety_limits.MIN_ALTITUDE:
    # Trigger RTL or halt descent
```

### Per-Follower Overrides

```yaml
FOLLOWER_OVERRIDES:
  MC_VELOCITY_CHASE:
    MAX_VELOCITY_FORWARD: 12.0  # Override global 10.0
```

---

## Quick Configuration

```yaml
SafetyLimits:
  MAX_VELOCITY_FORWARD: 10.0
  MAX_VELOCITY_LATERAL: 5.0
  MAX_VELOCITY_VERTICAL: 3.0
  MAX_YAW_RATE: 45.0
  MIN_ALTITUDE: 5.0
  MAX_ALTITUDE: 120.0
```
