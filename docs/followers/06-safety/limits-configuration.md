# Limits Configuration

> Configuring safety limits for safe operation

---

## Global Limits

Set in `configs/config.yaml`:

```yaml
SafetyLimits:
  # Velocity Limits (m/s)
  MAX_VELOCITY_FORWARD: 10.0    # Max forward speed
  MAX_VELOCITY_LATERAL: 5.0     # Max sideways speed
  MAX_VELOCITY_VERTICAL: 3.0    # Max up/down speed
  MIN_VELOCITY_FORWARD: 0.0     # Minimum forward
  DEFAULT_VELOCITY_FORWARD: 5.0 # Default cruise

  # Angular Rate Limits (deg/s)
  MAX_YAW_RATE: 45.0
  MAX_PITCH_RATE: 30.0
  MAX_ROLL_RATE: 60.0

  # Altitude Limits (meters)
  MIN_ALTITUDE: 5.0             # Minimum safe altitude
  MAX_ALTITUDE: 120.0           # Maximum altitude
  ALTITUDE_WARNING_BUFFER: 5.0  # Warning zone size
  USE_HOME_RELATIVE_ALTITUDE: true
```

---

## Per-Follower Overrides

Override global limits for specific followers:

```yaml
FOLLOWER_OVERRIDES:
  # Higher limits for chase mode
  MC_VELOCITY_CHASE:
    MAX_VELOCITY_FORWARD: 12.0
    MAX_VELOCITY_VERTICAL: 4.0

  # Much higher for fixed-wing
  FW_ATTITUDE_RATE:
    MAX_VELOCITY_FORWARD: 30.0

  # Lower for precision gimbal tracking
  GM_PID_PURSUIT:
    MAX_VELOCITY_FORWARD: 6.0
    MAX_VELOCITY_LATERAL: 3.0
```

---

## Recommended Limits by Scenario

### Indoor / Confined Space

```yaml
SafetyLimits:
  MAX_VELOCITY_FORWARD: 3.0
  MAX_VELOCITY_LATERAL: 2.0
  MAX_VELOCITY_VERTICAL: 1.0
  MAX_YAW_RATE: 30.0
  MIN_ALTITUDE: 1.0
  MAX_ALTITUDE: 10.0
```

### Open Field (Testing)

```yaml
SafetyLimits:
  MAX_VELOCITY_FORWARD: 8.0
  MAX_VELOCITY_LATERAL: 5.0
  MAX_VELOCITY_VERTICAL: 3.0
  MAX_YAW_RATE: 45.0
  MIN_ALTITUDE: 5.0
  MAX_ALTITUDE: 50.0
```

### Production (Experienced)

```yaml
SafetyLimits:
  MAX_VELOCITY_FORWARD: 15.0
  MAX_VELOCITY_LATERAL: 8.0
  MAX_VELOCITY_VERTICAL: 5.0
  MAX_YAW_RATE: 60.0
  MIN_ALTITUDE: 3.0
  MAX_ALTITUDE: 120.0
```

### Fixed-Wing

```yaml
SafetyLimits:
  MAX_VELOCITY_FORWARD: 30.0   # Higher for FW
  MAX_VELOCITY_LATERAL: 10.0
  MAX_VELOCITY_VERTICAL: 5.0
  MAX_YAW_RATE: 25.0           # Lower for FW
  MIN_ALTITUDE: 30.0           # Higher minimum
  MAX_ALTITUDE: 200.0

FOLLOWER_OVERRIDES:
  FW_ATTITUDE_RATE:
    MAX_VELOCITY_FORWARD: 40.0
```

---

## Altitude Considerations

### Home-Relative vs Absolute

```yaml
SafetyLimits:
  USE_HOME_RELATIVE_ALTITUDE: true   # Relative to takeoff
  # or
  USE_HOME_RELATIVE_ALTITUDE: false  # MSL altitude
```

### Warning Buffer

Distance from limits before warning:

```yaml
ALTITUDE_WARNING_BUFFER: 5.0  # Warn 5m before limits
```

### RTL on Violation

Trigger RTL when limits exceeded:

```yaml
# In follower-specific config
MC_VELOCITY_CHASE:
  RTL_ON_ALTITUDE_VIOLATION: true
```

---

## Dynamic Limit Updates

SafetyManager supports hot-reload:

```python
# In application code
safety_manager.reload_config()

# Followers automatically use new limits
# (properties read fresh from SafetyManager)
```

---

## Limit Validation

Limits are validated on load:

```python
# Automatic validation
if max_velocity < 0:
    raise ValueError("Velocity must be positive")

if min_altitude >= max_altitude:
    raise ValueError("Invalid altitude range")
```

---

## Emergency Overrides

For emergency situations:

```python
# Manually set temporary limits
safety_manager.set_emergency_limits(
    VelocityLimits(forward=0, lateral=0, vertical=0)
)

# Restore normal limits
safety_manager.clear_emergency_limits()
```

---

## Checklist

Before flight:

- [ ] Velocity limits appropriate for environment
- [ ] Altitude limits set correctly
- [ ] Per-follower overrides reviewed
- [ ] Warning buffer adequate
- [ ] RTL behavior configured
- [ ] Limits tested in SITL
