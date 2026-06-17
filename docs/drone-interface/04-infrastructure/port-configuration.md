# Port Configuration Reference

This page is the source of truth for PixEagle's current local networking
defaults. Historical examples that use the old MAVSDK and MAVLink2REST UDP
split are legacy/custom setups and should not be taught as the default path.

## Port Summary

| Port | Protocol | Owner | Default Exposure | Purpose |
|------|----------|-------|------------------|---------|
| 3040 | TCP/HTTP | PixEagle dashboard | `127.0.0.1` by launcher default | React operator dashboard |
| 5077 | TCP/HTTP/WS | PixEagle backend | `127.0.0.1` current default; local-compat plus scoped bearer auth | FastAPI API, MJPEG stream, current backend WebSocket routes |
| 5551 | TCP/WS | PixEagle telemetry config | local/optional | Legacy telemetry WebSocket setting; not the primary dashboard video path |
| 8088 | TCP/HTTP | MAVLink2REST | `127.0.0.1` by default | HTTP telemetry API consumed by PixEagle |
| 14540 | UDP | MavlinkAnywhere/mavlink-router | `127.0.0.1` output | MAVSDK endpoint for PixEagle Offboard control |
| 14569 | UDP | MavlinkAnywhere/mavlink-router | `127.0.0.1` output | MAVLink2REST input endpoint |
| 12550 | UDP | MavlinkAnywhere/mavlink-router | `127.0.0.1` output | Local debug/monitoring MAVLink endpoint |
| 14550 | UDP | MavlinkAnywhere/mavlink-router | field listener | QGroundControl `gcs_listen` server-mode endpoint |
| 5760 | TCP | MavlinkAnywhere/mavlink-router | configurable | MAVLink TCP server for dynamic clients |
| 9070 | TCP/HTTP | MavlinkAnywhere dashboard | `127.0.0.1` by default | Router management dashboard |

## PixEagle Application Ports

### 3040 - Dashboard

`dashboard/env_default.yaml` sets the dashboard development/serve port:

```yaml
PORT: 3040
HOST: 127.0.0.1
REACT_APP_API_PORT: 5077
```

### 5077 - Backend API And Streaming

`configs/config_default.yaml` sets:

```yaml
Streaming:
  API_EXPOSURE_MODE: local_only
  HTTP_STREAM_HOST: 127.0.0.1
  HTTP_STREAM_PORT: 5077
  API_ALLOWED_HOSTS: []
  API_CORS_ALLOWED_ORIGINS:
    - http://127.0.0.1:3040
    - http://localhost:3040
```

The current backend hosts REST routes, `/video_feed`, and backend WebSocket
routes on this port. The API modernization program is tracking the migration
from mixed legacy routes to typed `/api/v1/...` contracts. The checked-in
policy is local-only with loopback local compatibility. Non-loopback backend
API clients require an exact `API_ALLOWED_HOSTS` entry plus scoped bearer
tokens or explicit browser-session auth from an external hashed user file. See the
[API exposure boundary](../../apis/api-exposure-boundary.md).

### 5551 - Legacy Telemetry WebSocket Setting

`Telemetry.WEBSOCK_PORT` remains in the config defaults. It should be treated
as a legacy/optional telemetry setting until the streaming and telemetry
surface is normalized in the streaming/UI phase.

### 8088 - MAVLink2REST HTTP API

MAVLink2REST serves telemetry over HTTP:

```text
http://127.0.0.1:8088/v1/mavlink
```

PixEagle's launcher binds this service to `127.0.0.1:8088` by default. Expose
it on `0.0.0.0:8088` only with
`PIXEAGLE_MAVLINK2REST_EXPOSURE_MODE=trusted_lan_legacy` on an isolated trusted
network; this is unauthenticated and not production-approved.

## MAVLink Routing Ports

### 14540 - MAVSDK

Current PixEagle default:

```yaml
PX4:
  SYSTEM_ADDRESS: udp://127.0.0.1:14540
```

MavlinkAnywhere should provide an explicit normal-mode local endpoint at
`127.0.0.1:14540`.

### 14569 - MAVLink2REST Input

PixEagle's `mavlink2rest.sh` consumes:

```text
udpin:127.0.0.1:14569
```

MavlinkAnywhere should provide an explicit normal-mode local endpoint at
`127.0.0.1:14569`.

### 14550 - QGroundControl

MavlinkAnywhere creates `gcs_listen` as a server-mode endpoint on
`0.0.0.0:14550`. Configure QGroundControl to connect to `<device-ip>:14550`.

This endpoint is for ad-hoc field access. For deterministic multi-client
remote access, use explicit normal-mode endpoints or TCP `5760`.

### 5760 - MAVLink TCP Server

`mavlink-router` listens on TCP `5760` by default in the current
MavlinkAnywhere profile. Use it for dynamic clients or tools that prefer TCP.

## Typical Local Topology

```text
PX4/SITL/UART
    -> mavlink-router / MavlinkAnywhere
        -> 127.0.0.1:14540  PixEagle MAVSDK
        -> 127.0.0.1:14569  MAVLink2REST input
        -> 127.0.0.1:12550  local tools
        -> 0.0.0.0:14550    QGC server-mode listener
        -> 0.0.0.0:5760/tcp MAVLink TCP server

MAVLink2REST 127.0.0.1:8088 -> PixEagle telemetry polling
PixEagle backend 127.0.0.1:5077 -> dashboard/API/video (checked-in local-only bind)
PixEagle dashboard 127.0.0.1:3040 -> operator UI (checked-in local-only bind)
```

## Firewall Guidance

Expose only what the deployment needs:

```bash
# Optional separately secured trusted/VPN operator network
sudo ufw allow from <trusted-cidr> to any port 3040 proto tcp

# Optional GCS field access
sudo ufw allow 14550/udp

# Optional dynamic MAVLink TCP clients
sudo ufw allow 5760/tcp
```

Keep PixEagle backend `5077`, MAVLink2REST `8088`, local service endpoints
`14540`, `14569`, `12550`, and the MavlinkAnywhere dashboard `9070` local-only.
Remote operator access should terminate at a separately secured VPN/reverse
proxy or SSH tunnel rather than directly exposing backend port `5077`.
Non-loopback PixEagle browser operation remains deferred until TLS,
operator deployment hardening, typed replacements and retirement for remaining
legacy tracking/control mutations, adversarial auth/media tests, and evidence
gates are complete.

## Legacy Port Note

Older PixEagle docs used a custom split where MAVSDK listened on `14541` and
MAVLink2REST consumed `14551`. That layout is not the current default. If an
operator intentionally keeps that custom topology, record it in the deployment
notes and update `PX4.SYSTEM_ADDRESS`, `scripts/components/mavlink2rest.sh`
arguments, and the router config together.
