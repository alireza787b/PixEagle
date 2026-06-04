# mavlink-router Manual Setup

Use [MavlinkAnywhere](mavlink-anywhere.md) for normal PixEagle installations.
This page is for operators who must inspect or hand-maintain `mavlink-router`
configuration directly.

## Managed Files

Current MavlinkAnywhere-managed installations use:

| Path | Purpose |
|------|---------|
| `/etc/mavlink-router/main.conf` | Effective router configuration |
| `/etc/default/mavlink-router` | Service environment |
| `mavlink-router.service` | Router systemd unit |
| `mavlink-anywhere-dashboard.service` | Optional dashboard systemd unit |

Do not keep a separate PixEagle-local router config unless the deployment has a
documented reason. One active router configuration should be the source of
truth.

## Canonical PixEagle Endpoints

```ini
[General]
TcpServerPort = 5760
ReportStats = false

# Example UART input from a flight controller.
[UartEndpoint pixhawk]
Device = /dev/ttyS0
Baud = 57600

# Ad-hoc GCS access. QGC connects to <device-ip>:14550.
[UdpEndpoint gcs_listen]
Mode = Server
Address = 0.0.0.0
Port = 14550

# PixEagle MAVSDK control endpoint.
[UdpEndpoint mavsdk]
Mode = Normal
Address = 127.0.0.1
Port = 14540

# MAVLink2REST input endpoint.
[UdpEndpoint mavlink2rest]
Mode = Normal
Address = 127.0.0.1
Port = 14569

# Optional local debug endpoint.
[UdpEndpoint local_mavlink]
Mode = Normal
Address = 127.0.0.1
Port = 12550
```

For SITL or UDP input, replace the UART input with:

```ini
[UdpEndpoint udp_input]
Mode = Server
Address = 0.0.0.0
Port = 14550
```

## Command-Line Equivalent

For temporary debugging only:

```bash
mavlink-routerd \
  -e 127.0.0.1:14540 \
  -e 127.0.0.1:14569 \
  -e 127.0.0.1:12550 \
  0.0.0.0:14550
```

Prefer the managed systemd service for persistent systems:

```bash
sudo systemctl restart mavlink-router
sudo systemctl status mavlink-router
sudo journalctl -u mavlink-router -f
```

## Endpoint Semantics

- `127.0.0.1:14540` is the PixEagle MAVSDK endpoint. PixEagle defaults to
  `PX4.SYSTEM_ADDRESS: udp://127.0.0.1:14540`.
- `127.0.0.1:14569` is the MAVLink2REST input endpoint.
- `0.0.0.0:14550` in server mode is convenient for QGroundControl field access.
  It tracks the last sender and should not be treated as deterministic
  multi-client fanout.
- TCP `5760` is better for dynamic or multiple clients.

## Validation

```bash
# Router service
sudo systemctl status mavlink-router

# Effective config
sudo sed -n '1,220p' /etc/mavlink-router/main.conf

# Local MAVLink consumers
ss -ulnp | grep -E '14540|14569|12550|14550'
ss -tlnp | grep 5760
```

Then check PixEagle telemetry:

```bash
curl http://127.0.0.1:8088/v1/mavlink/vehicles
```

## Safety Notes

Before any hardware test, remove propellers, keep a manual abort path, and
verify PX4 failsafes. Router connectivity alone is not evidence that PixEagle
Offboard control is safe or flight-ready.
