# MAVLink Configuration

This document covers MAVLink2REST configuration for telemetry access.

## Configuration Location

```yaml
# config_default.yaml
mavlink2rest:
  enabled: true
  base_url: "http://localhost:8088"
  poll_rate_hz: 20
  timeout_s: 1.0
```

## Options

### enabled

Enable/disable MAVLink2REST telemetry source.

```yaml
mavlink2rest:
  enabled: true   # Use MAVLink2REST for telemetry
```

When disabled, telemetry may be unavailable or use fallback methods.

### base_url

MAVLink2REST server address.

```yaml
mavlink2rest:
  base_url: "http://localhost:8088"
```

Common configurations:

| Setup | URL |
|-------|-----|
| Local | `http://localhost:8088` |
| Docker | `http://localhost:8088` |
| Remote | `http://192.168.1.20:8088` |

### poll_rate_hz

How often to poll MAVLink2REST for telemetry.

```yaml
mavlink2rest:
  poll_rate_hz: 20
```

Recommendations:

| Data Type | Recommended Rate |
|-----------|-----------------|
| Attitude | 20-50 Hz |
| Altitude | 10-20 Hz |
| Position | 5-10 Hz |
| Heartbeat | 1-2 Hz |

PixEagle uses a single rate for all data; 20 Hz is a good default.

### timeout_s

HTTP request timeout in seconds.

```yaml
mavlink2rest:
  timeout_s: 1.0
```

- **Too short (< 0.5s)**: Intermittent failures
- **Good (1.0s)**: Handles brief delays
- **Too long (> 3s)**: Slow error recovery

## Data Points

Configure which MAVLink messages to poll:

```yaml
mavlink2rest:
  data_points:
    - attitude
    - altitude
    - vfr_hud
    - heartbeat
```

### Available Data Points

| Data Point | MAVLink Message | Fields |
|------------|-----------------|--------|
| attitude | ATTITUDE | roll, pitch, yaw |
| altitude | ALTITUDE | altitude_relative |
| vfr_hud | VFR_HUD | groundspeed, throttle |
| heartbeat | HEARTBEAT | custom_mode |

## Complete Example

```yaml
# config_default.yaml - MAVLink2REST section

mavlink2rest:
  enabled: true
  base_url: "http://localhost:8088"
  poll_rate_hz: 20
  timeout_s: 1.0
  data_points:
    - attitude
    - altitude
    - vfr_hud
    - heartbeat
```

## Environment Variables

Override configuration via environment:

```bash
export MAVLINK2REST_URL="http://192.168.1.10:8088"
export MAVLINK2REST_RATE=30
```

## Docker Configuration

When running MAVLink2REST in Docker:

```yaml
# docker-compose.yml
services:
  mavlink2rest:
    image: bluerobotics/mavlink2rest
    network_mode: host
    command: --mavlink udpin:0.0.0.0:14551 --server 0.0.0.0:8088
```

## Troubleshooting

### Connection Refused

```bash
# Check MAVLink2REST is running
curl http://localhost:8088/mavlink/vehicles

# Check port
netstat -tlnp | grep 8088
```

### No Data

```bash
# Check vehicle connected
curl http://localhost:8088/mavlink/vehicles

# Should return: {"vehicles":[1]}
```

### Stale Data

Check message frequency:
```bash
curl http://localhost:8088/.../ATTITUDE | jq '.status.time.frequency'
```

If frequency is 0, MAVLink source may not be sending.

## Related Documentation

- [PX4 Configuration](px4-config.md)
- [MAVLink2REST API](../03-protocols/mavlink2rest-api.md)
- [Infrastructure Setup](../04-infrastructure/mavlink-anywhere.md)
