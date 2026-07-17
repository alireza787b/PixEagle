# MAVLink2REST API Reference

This page documents the MAVLink2REST HTTP surface PixEagle currently consumes.
MavlinkAnywhere provides the routed MAVLink input at `127.0.0.1:14569`;
MAVLink2REST converts that stream into HTTP telemetry on `127.0.0.1:8088`.

## Base URL

```text
http://127.0.0.1:8088
```

PixEagle launches MAVLink2REST local-only by default:

```bash
bash scripts/components/mavlink2rest.sh \
  "udpin:127.0.0.1:14569" \
  "127.0.0.1:8088"
```

The maintained launchers reject non-loopback HTTP binds unless
`PIXEAGLE_MAVLINK2REST_EXPOSURE_MODE=trusted_lan_legacy` is set explicitly.
That mode is unauthenticated and not production-approved; prefer keeping
`8088` local and tunneling when needed.

## Configuration

```yaml
MAVLink:
  MAVLINK_ENABLED: true
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088
  MAVLINK_POLLING_INTERVAL: 0.5

Follower:
  USE_MAVLINK2REST: true
```

## Endpoints Used By PixEagle

PixEagle code uses `/v1/mavlink/...` paths.

| Endpoint | Purpose |
|----------|---------|
| `GET /v1/mavlink` | Bulk MAVLink state used by background polling |
| `GET /v1/mavlink/vehicles` | Vehicle discovery and connectivity check |
| `GET /v1/mavlink/vehicles/1/components/1/messages/ATTITUDE` | Roll, pitch, yaw |
| `GET /v1/mavlink/vehicles/1/components/1/messages/ALTITUDE` | Relative and AMSL altitude |
| `GET /v1/mavlink/vehicles/1/components/1/messages/LOCAL_POSITION_NED` | Local velocity vector |
| `GET /v1/mavlink/vehicles/1/components/1/messages/VFR_HUD` | Ground speed, throttle, heading |
| `GET /v1/mavlink/vehicles/1/components/1/messages/HEARTBEAT` | Flight mode and arm status |

## Verification

```bash
curl http://127.0.0.1:8088/v1/mavlink/vehicles
curl http://127.0.0.1:8088/v1/mavlink/vehicles/1/components/1/messages/HEARTBEAT
curl http://127.0.0.1:8088/v1/mavlink/vehicles/1/components/1/messages/ATTITUDE | jq '.status.time.frequency'
```

If vehicles are empty or message frequency is zero, check:

- PX4/SITL or hardware input is producing MAVLink
- `mavlink-router.service` is running
- `/etc/mavlink-router/main.conf` includes `127.0.0.1:14569`
- `scripts/components/mavlink2rest.sh` is running and consuming
  `udpin:127.0.0.1:14569`

## PixEagle Code Paths

- `src/classes/mavlink_data_manager.py` builds requests from
  `MAVLink.MAVLINK_HOST` and `MAVLink.MAVLINK_PORT`.
- Background polling reads `http://<host>:<port>/v1/mavlink`.
- Follower-specific async helpers read individual
  `/v1/mavlink/vehicles/.../messages/...` endpoints.

## Related Documentation

- [MAVLink configuration](../05-configuration/mavlink-config.md)
- [MavlinkAnywhere integration](../04-infrastructure/mavlink-anywhere.md)
- [Port configuration](../04-infrastructure/port-configuration.md)
