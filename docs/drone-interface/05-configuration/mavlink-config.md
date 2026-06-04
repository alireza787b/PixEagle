# MAVLink Configuration

This document covers MAVLink2REST configuration for telemetry access.

## Configuration Location

```yaml
# config_default.yaml
MAVLink:
  MAVLINK_ENABLED: true
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088
  MAVLINK_POLLING_INTERVAL: 0.5
  MAVLINK_REQUEST_TIMEOUT_S: 5.0
  MAVLINK_REQUEST_RETRIES: 0
  MAVLINK_STALE_TIMEOUT_S: 2.0

Follower:
  USE_MAVLINK2REST: true
```

## Options

### MAVLINK_ENABLED

Enable/disable MAVLink2REST telemetry source.

```yaml
MAVLink:
  MAVLINK_ENABLED: true
```

When disabled, telemetry may be unavailable or use fallback methods.

### MAVLINK_HOST / MAVLINK_PORT

MAVLink2REST server address.

```yaml
MAVLink:
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088
```

Common configurations:

| Setup | URL |
|-------|-----|
| Local | `http://127.0.0.1:8088` |
| Remote | `http://192.168.1.20:8088` |

Keep MAVLink2REST local-only unless a trusted network, VPN, or SSH tunnel is
part of the deployment.

### MAVLINK_POLLING_INTERVAL

Polling interval in seconds.

```yaml
MAVLink:
  MAVLINK_POLLING_INTERVAL: 0.5
```

Recommendations:

| Data Type | Recommended Rate |
|-----------|-----------------|
| Attitude | 20-50 Hz |
| Altitude | 10-20 Hz |
| Position | 5-10 Hz |
| Heartbeat | 1-2 Hz |

PixEagle also has follower refresh settings under `Follower`.

### Request Timeout, Retry, And Freshness

These settings control how PixEagle treats MAVLink2REST transport health:

```yaml
MAVLink:
  MAVLINK_REQUEST_TIMEOUT_S: 5.0
  MAVLINK_REQUEST_RETRIES: 0
  MAVLINK_STALE_TIMEOUT_S: 2.0
```

| Setting | Meaning |
|---------|---------|
| `MAVLINK_REQUEST_TIMEOUT_S` | HTTP timeout for each MAVLink2REST request. |
| `MAVLINK_REQUEST_RETRIES` | Additional retry attempts after the initial request fails. |
| `MAVLINK_STALE_TIMEOUT_S` | Age since the last successful aggregate or per-message request before telemetry is reported stale. |

The top-level `/status` response includes `mavlink_telemetry` with `fresh`,
`status`, request timeout, retry count, stale timeout, and last error fields.
This is the legacy flat compatibility summary. New API/MCP/dashboard consumers
should use `GET /api/v1/telemetry/health`, which separates latest request
success, last successful sample freshness, cached payload availability, and
consumer guidance. Both views are MAVLink2REST request/payload health; neither
is PX4-in-loop follower evidence.

## Data Points

Configure which MAVLink messages to poll:

```yaml
MAVLink:
  MAVLINK_DATA_POINTS:
    roll: /vehicles/1/components/1/messages/ATTITUDE/message/roll
    pitch: /vehicles/1/components/1/messages/ATTITUDE/message/pitch
    heading: /vehicles/1/components/1/messages/VFR_HUD/message/heading
    flight_mode: /vehicles/1/components/1/messages/HEARTBEAT/message/custom_mode
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

MAVLink:
  MAVLINK_ENABLED: true
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088
  MAVLINK_POLLING_INTERVAL: 0.5
  MAVLINK_REQUEST_TIMEOUT_S: 5.0
  MAVLINK_REQUEST_RETRIES: 0
  MAVLINK_STALE_TIMEOUT_S: 2.0

Follower:
  USE_MAVLINK2REST: true
```

## Configuration Editing

Use YAML config or the dashboard config editor. Environment-variable override
coverage is not currently the source of truth for this section.

## MAVLink2REST Source

PixEagle's launcher consumes the current MavlinkAnywhere endpoint by default:

```bash
bash scripts/components/mavlink2rest.sh \
  "udpin:127.0.0.1:14569" \
  "127.0.0.1:8088"
```

## Troubleshooting

### Connection Refused

```bash
# Check MAVLink2REST is running
curl http://127.0.0.1:8088/v1/mavlink/vehicles

# Check port
netstat -tlnp | grep 8088
```

### No Data

```bash
# Check vehicle connected
curl http://127.0.0.1:8088/v1/mavlink/vehicles

# Should return: {"vehicles":[1]}
```

### Stale Data

Check message frequency:
```bash
curl http://127.0.0.1:8088/v1/mavlink/vehicles/1/components/1/messages/ATTITUDE | jq '.status.time.frequency'
```

If frequency is 0, MAVLink source may not be sending.

## Related Documentation

- [PX4 Configuration](px4-config.md)
- [MAVLink2REST API](../03-protocols/mavlink2rest-api.md)
- [Infrastructure Setup](../04-infrastructure/mavlink-anywhere.md)
