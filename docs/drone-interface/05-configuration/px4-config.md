# PX4 Configuration

This document covers the PX4-related configuration options in PixEagle.

## Configuration Location

```yaml
# config_default.yaml
px4:
  connection_string: "udp://:14541"
  offboard_rate_hz: 20
  hover_throttle: 0.5
```

## Connection String

### Format

```
protocol://address:port
```

### Common Values

| Setup | Connection String |
|-------|-------------------|
| SITL (via mavlink-router) | `udp://:14541` |
| SITL (direct) | `udp://:14540` |
| Serial | `serial:///dev/ttyUSB0:921600` |

### Examples

```yaml
# SITL setup
px4:
  connection_string: "udp://:14541"

# USB serial
px4:
  connection_string: "serial:///dev/ttyACM0:921600"

# TCP (less common)
px4:
  connection_string: "tcp://127.0.0.1:5760"
```

## Offboard Rate

Controls how often setpoint commands are sent to PX4.

```yaml
px4:
  offboard_rate_hz: 20  # Commands per second
```

### Recommendations

| Use Case | Rate (Hz) |
|----------|-----------|
| Development | 10-20 |
| Production | 20-50 |
| Minimum (PX4 requirement) | 2 |

### Impact

- **Too low (< 2 Hz)**: PX4 exits offboard mode
- **Optimal (10-20 Hz)**: Smooth control
- **Too high (> 50 Hz)**: Unnecessary CPU load

## Hover Throttle

Base throttle for attitude rate control mode.

```yaml
px4:
  hover_throttle: 0.5  # 0.0 to 1.0
```

### Tuning

Vehicle-dependent. Start with 0.5 and adjust:
- Heavy vehicle: Increase (0.55-0.65)
- Light vehicle: Decrease (0.4-0.5)

## Flight Modes

PX4 flight mode codes used by PixEagle:

```yaml
px4:
  flight_modes:
    offboard: 393216
    position: 196608
    hold: 327680
    rtl: 84148224
    land: 50593792
```

These are fixed PX4 values and should not be changed.

## Safety Limits

Velocity and rate limits applied before sending commands:

```yaml
safety:
  max_velocity_forward: 8.0    # m/s
  max_velocity_lateral: 5.0    # m/s
  max_velocity_vertical: 3.0   # m/s
  max_yaw_rate: 45.0           # deg/s
```

See [Safety Integration](safety-integration.md) for details.

## Circuit Breaker

Test mode that blocks commands to PX4:

```yaml
circuit_breaker:
  active: true   # Block all PX4 commands
  log_commands: true
```

When active:
- Commands are logged but not sent
- Telemetry still received
- Safe for indoor testing

## Complete Example

```yaml
# config_default.yaml - PX4 section

px4:
  # Connection
  connection_string: "udp://:14541"

  # Command rate
  offboard_rate_hz: 20

  # Attitude rate control
  hover_throttle: 0.5

safety:
  # Velocity limits
  max_velocity_forward: 8.0
  max_velocity_lateral: 5.0
  max_velocity_vertical: 3.0
  max_yaw_rate: 45.0

circuit_breaker:
  active: false
  log_commands: true
```

## Related Documentation

- [MAVLink Configuration](mavlink-config.md)
- [Follower Commands Schema](follower-commands-schema.md)
- [Safety Integration](safety-integration.md)
