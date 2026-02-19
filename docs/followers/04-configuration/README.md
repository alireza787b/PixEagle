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

---

## Quick Start

### 1. Select Follower Mode

```yaml
# In configs/config.yaml
FOLLOWER_MODE: "mc_velocity_chase"
```

### 2. Set Safety Limits

```yaml
Safety:
  GlobalLimits:
  MAX_VELOCITY_FORWARD: 10.0
  MAX_VELOCITY_LATERAL: 5.0
  MAX_VELOCITY_VERTICAL: 3.0
  MAX_YAW_RATE: 45.0
```

### 3. Configure Follower-Specific Parameters

```yaml
MC_VELOCITY_CHASE:
  MAX_FORWARD_VELOCITY: 8.0
  FORWARD_RAMP_RATE: 2.0
  LATERAL_GUIDANCE_MODE: "coordinated_turn"
```

### 4. Set PID Gains

```yaml
PID_GAINS:
  vel_body_fwd:
    p: 2.0
    i: 0.1
    d: 0.3
```

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

## Hot-Reload vs Restart

| Change Type | Effect |
|-------------|--------|
| Safety limits | Hot-reload (immediate) |
| PID gains | Hot-reload |
| Follower mode | Restart required |
| Control type | Restart required |

---

## Validation

Parameters are validated at multiple levels:

1. **Schema validation** - Type checking, ranges
2. **SafetyManager** - Limit enforcement
3. **SetpointHandler** - Field clamping
4. **Runtime checks** - Safety monitoring

Invalid configurations are logged with warnings and fall back to defaults.
