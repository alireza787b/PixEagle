# Follower Configuration

> Complete guide to configuring PixEagle followers

Configuration for followers is managed through YAML files with schema validation and UI support.

---

## Configuration Files

| File | Purpose |
|------|---------|
| `configs/config.yaml` | Main configuration (gitignored) |
| `configs/config_default.yaml` | Default values and reference |
| `configs/config_schema.yaml` | Schema for validation |
| `configs/follower_commands.yaml` | Follower profile definitions |

---

## Documents

| Document | Description |
|----------|-------------|
| [Parameter Reference](parameter-reference.md) | All follower parameters |
| [Schema System](schema-system.md) | Profile and field definitions |
| [Tuning Guide](tuning-guide.md) | Practical tuning advice |
| [Gimbal Guidance](gimbal-guidance.md) | Vertical, rearward, and yaw-first Vector policy |
| [Stock PX4 MC/VTOL workflow](../07-integration/stock-px4-gimbal-vtol.md) | Mount, phase, supported transports and qualification status |

---

## Quick Start

### 1. Select Follower Mode

```yaml
# In configs/config.yaml
Follower:
  FOLLOWER_MODE: "mc_velocity_position"
```

### 2. Set Safety Limits

```yaml
Safety:
  GlobalLimits:
    MAX_VELOCITY: 1.0
    MAX_VELOCITY_FORWARD: 0.5
    MAX_VELOCITY_LATERAL: 0.5
    MAX_VELOCITY_VERTICAL: 0.5
    MAX_YAW_RATE: 45.0
```

`GlobalLimits` is the hard envelope. Follower-specific entries may tighten
these values but cannot expand them or disable globally enabled protections.
The explicit [session speed override](session-speed.md) is an operator-owned
exception for velocity only on supported followers; restore removes it without
changing configuration. Altitude and rate protections remain in force.

### 3. Configure Follower-Specific Parameters

```yaml
MC_VELOCITY_CHASE:
  FORWARD_RAMP_RATE: 0.5

Follower:
  FollowerOverrides:
    MC_VELOCITY_CHASE:
      LATERAL_GUIDANCE_MODE: coordinated_turn
```

### 4. Tune profile gains only when needed

Use the selected profile's schema-backed Dashboard fields and the
[Tuning Guide](tuning-guide.md). There is no universal root-level `PID_GAINS`
block to copy across followers. Preserve the factory baseline until its
recorded/simulated behavior is understood.

---

## Configuration Hierarchy

```
configs/config_default.yaml     ← Defaults (tracked in git)
        │
        ▼
configs/config.yaml             ← User overrides (gitignored)
        │
        ▼
SafetyManager                   ← Runtime limits
        │
        ▼
SetpointHandler                 ← Schema validation
        │
        ▼
Follower                        ← Final configuration
```

---

## Web Dashboard

Most settings are configurable via the Dashboard UI:

1. Access http://localhost:3040
2. Navigate to Settings
3. Select Follower section
4. Modify parameters
5. Apply (may require restart)

---

## Saved versus running settings

The configuration service reports each field's reload tier and pending state.
A successful save does not necessarily mean the new value is running. Apply
changes while following is inactive, then perform the reported follower or
backend restart. Do not infer the reload tier from the category alone.

---

## Validation

Parameters are validated at multiple levels:

1. **Schema validation** - Type checking, ranges
2. **SafetyManager** - Limit enforcement
3. **SetpointHandler** - Field clamping
4. **Runtime checks** - Safety monitoring

Invalid required configuration is rejected; required safety values do not
silently fall back. Optional compatibility behavior applies only where the
individual contract documents it. Edit the existing complete safety object
rather than replacing it with the partial examples above.
