# PX4 And MAVLink Connectivity

This page is the source of truth for PixEagle's PX4/MAVLink ingress and local
port roles. The PixEagle installer prepares the MAVSDK Server and MAVLink2REST
binaries, but it does not guess or take ownership of the flight-controller
transport. Before configured PX4 operation, route the vehicle's MAVLink stream
to the two local PixEagle consumers described below.

## Required Default Topology

```text
PX4 flight controller, radio, Ethernet link, or SITL
                      |
                      v
       one MAVLink router owned by the deployment
          |                              |
          v                              v
127.0.0.1:14540/udp             127.0.0.1:14569/udp
PixEagle MAVSDK vehicle link    MAVLink2REST vehicle link
          |                              |
          v                              v
MAVSDK Server                    MAVLink2REST
gRPC listener :50051/tcp        HTTP 127.0.0.1:8088/tcp
PixEagle dials 127.0.0.1        PixEagle dials 127.0.0.1
```

Commands travel back to PX4 through the MAVSDK `14540/udp` route. With the
default `Follower.USE_MAVLINK2REST: true`, telemetry uses the separate
`14569/udp` route and the local HTTP bridge on `8088/tcp`. Both UDP outputs must
therefore carry the same vehicle MAVLink network. Do not send MAVLink packets to
`50051` or `8088`; those are application service ports, not vehicle inputs.

The pinned upstream MAVSDK Server accepts only a gRPC port argument and listens
on `0.0.0.0:50051`; PixEagle still connects to it through `127.0.0.1`. The
browser-lab workflow does not open this port. Block `50051/tcp` on every
untrusted interface because the upstream listener is not authenticated or
TLS-protected.

PixEagle starts its local MAVSDK Server and MAVLink2REST processes. It does not
start PX4, configure a Pixhawk serial port, select a network source, or manage a
MAVLink router. This avoids two services competing for one UART and keeps the
hardware transport under deployment control.

The PixEagle installer does not install a MAVLink router.

## Beginner Path: MavlinkAnywhere

[MavlinkAnywhere](mavlink-anywhere.md) is the recommended way to install and
manage `mavlink-router`. Its guided configurator detects Raspberry Pi, Jetson,
generic Linux, serial, and UDP-source cases. Configure these PixEagle outputs:

```text
127.0.0.1:14540
127.0.0.1:14569
```

The optional `127.0.0.1:12550` local-tools output is useful for diagnostics but
is not required by PixEagle.

For an interactive hardware setup:

```bash
git clone https://github.com/alireza787b/mavlink-anywhere.git
cd mavlink-anywhere
git fetch --tags origin
git checkout <reviewed-tag-or-40-character-commit>
sudo ./install_mavlink_router.sh
sudo ./configure_mavlink_router.sh
```

For an already identified UART, the equivalent headless shape is:

```bash
sudo ./configure_mavlink_router.sh --headless \
  --uart /dev/serial0 \
  --baud 921600 \
  --endpoints "127.0.0.1:14540,127.0.0.1:14569,127.0.0.1:12550"
```

`/dev/serial0` and `921600` are examples, not universal values. Use the device
and baud rate that match the board wiring and PX4 port configuration. For SITL
or another UDP source:

```bash
sudo ./configure_mavlink_router.sh --headless \
  --input-type udp \
  --input-address 0.0.0.0 \
  --input-port 14550 \
  --endpoints "127.0.0.1:14540,127.0.0.1:14569,127.0.0.1:12550"
```

MavlinkAnywhere remains a separate project and service. Pin and record the
revision accepted for each deployment; PixEagle does not silently clone,
update, or reconfigure it.

## Advanced Path: mavlink-router

Operators may configure `mavlink-router` directly instead. The physical or
simulated source is deployment-specific, but the two PixEagle outputs remain:

```ini
[UdpEndpoint pixeagle_mavsdk]
Mode = Normal
Address = 127.0.0.1
Port = 14540

[UdpEndpoint pixeagle_mavlink2rest]
Mode = Normal
Address = 127.0.0.1
Port = 14569
```

See the [manual mavlink-router guide](mavlink-router.md) for UART and UDP input
examples. Use one active router as the owner of the physical source. A direct
single-consumer connection is an advanced custom topology and does not satisfy
the default two-consumer contract.

## Port Roles

| Port | Protocol | Owner | Default exposure | Purpose |
|------|----------|-------|------------------|---------|
| 3040 | TCP/HTTP | PixEagle dashboard | loopback in checked-in defaults; all interfaces in explicit browser lab | Operator UI |
| 5077 | TCP/HTTP/WS | PixEagle backend | loopback in checked-in defaults; authenticated browser-lab exposure when selected | API and media |
| 8088 | TCP/HTTP | MAVLink2REST | `127.0.0.1` | Telemetry API consumed by PixEagle |
| 14540 | UDP | deployment MAVLink router | output to `127.0.0.1` | MAVSDK bidirectional vehicle link |
| 14569 | UDP | deployment MAVLink router | output to `127.0.0.1` | MAVLink2REST vehicle input |
| 50051 | TCP/gRPC | MAVSDK Server | upstream listener uses `0.0.0.0`; PixEagle client uses `127.0.0.1` | Internal PixEagle-to-MAVSDK API; block on untrusted interfaces |
| 12550 | UDP | deployment MAVLink router | output to `127.0.0.1` | Optional local diagnostics |
| 14550 | UDP | deployment MAVLink router | deployment-specific listener | Common PX4 UDP input or QGC field listener; these are mode-dependent roles |
| 5760 | TCP | mavlink-router | configurable | Optional dynamic MAVLink clients |
| 9070 | TCP/HTTP | MavlinkAnywhere | `127.0.0.1` by default | Optional router dashboard |

Port `5551` remains a legacy/optional telemetry WebSocket setting and is not the
primary dashboard video or MAVLink path.

## Browser Bind Versus Browser URL

The one-line installer's network choice and `make quick-browser-demo` generate
an explicit lab profile that binds dashboard and backend services to
`0.0.0.0`. Pressing Enter selects a requested host when one was supplied;
otherwise it selects the primary-route device address. A new user can then open
a real URL such as `http://192.168.0.226:3040/`.

`0.0.0.0` means "listen on every IPv4 interface". It is not an address to enter
in a browser. The selected device IP or hostname is also used to generate the
exact Host and CORS policy. Local-only mode keeps `127.0.0.1` instead.

## Verification

Run these checks on the companion computer after the router and PixEagle are
started:

```bash
sudo systemctl status mavlink-router --no-pager
sudo sed -n '1,220p' /etc/mavlink-router/main.conf
ss -lunp | grep -E ':(14540|14569|14550|12550)\b'
ss -ltnp | grep -E ':(50051|8088)\b'
curl -fsS http://127.0.0.1:8088/v1/mavlink/vehicles
```

An empty vehicle list means the HTTP bridge is alive but no vehicle has been
discovered. A listening UDP socket alone also does not prove packet flow. Accept
the link only after vehicle discovery, fresh telemetry, bidirectional command
path validation in a safe bench/SITL context, and recorded evidence.

## Network Boundary

Keep `14540`, `14569`, and `8088` on loopback. They are local integration
endpoints, not remote GCS services. The pinned MAVSDK Server cannot select a
gRPC bind host and listens on all interfaces at `50051/tcp`; deny that port on
each untrusted interface. If QGroundControl needs MAVLink, use a router field
listener, an explicit normal-mode endpoint, or its TCP server and restrict that
path with the deployment firewall/VPN policy. If `14550/udp` is already the
router's PX4/SITL input, it cannot simultaneously be a separate QGC listener on
the same address and port.

```bash
sudo ufw deny in on <external-interface> to any port 50051 proto tcp
sudo ufw allow from <trusted-gcs-ip-or-cidr> to any port 14550 proto udp
sudo ufw allow from <trusted-gcs-ip-or-cidr> to any port 5760 proto tcp
```

For dashboard access, expose only the explicit beginner lab profile or the
reviewed production reverse-proxy path. See the
[API exposure boundary](../../apis/api-exposure-boundary.md).

## Historical Layouts

Older deployments may use `14541` or `14551`. They are not current defaults.
Do not partially migrate a working custom topology: update the router outputs,
`PX4.SYSTEM_ADDRESS`, MAVLink2REST launch source, firewall policy, service
configuration, and deployment evidence together.
