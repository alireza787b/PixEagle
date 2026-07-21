# PX4 Hardware Connection

This guide covers the deployment boundary between a PX4 flight controller and
PixEagle on a Linux companion computer. It does not authorize a flight test.
Remove propellers for bench work, retain an independent operator abort path, and
validate the exact PX4 firmware, wiring, port settings, and failsafes before any
command-capable test.

## Connection Contract

PixEagle does not open the flight-controller UART or network source directly in
the maintained default topology. One deployment-owned MAVLink router reads that
source and sends the same MAVLink network to:

```text
127.0.0.1:14540/udp  PixEagle MAVSDK vehicle link
127.0.0.1:14569/udp  PixEagle MAVLink2REST vehicle link
```

Use the [PX4 and MAVLink connectivity guide](port-configuration.md) as the
canonical port reference. MavlinkAnywhere is the recommended guided
`mavlink-router` manager for Raspberry Pi, Jetson, and generic Linux.

## 1. Identify The Physical Source

Common inputs are:

| Input | Typical Linux identity | Notes |
|-------|------------------------|-------|
| USB | `/dev/ttyACM0` or `/dev/ttyUSB0` | Best for removable bench setup |
| Board UART | `/dev/serial0`, `/dev/ttyAMA*`, or `/dev/ttyTHS*` | Device name and pin mux are board-specific |
| UDP/Ethernet | deployment IP and UDP listen port | PX4 must be configured to send MAVLink to the companion |
| Telemetry radio | `/dev/ttyUSB*` | Baud must match the radio and PX4 link |

Discover serial devices without changing their permissions:

```bash
ls -l /dev/serial/by-id/ 2>/dev/null || true
ls -l /dev/ttyACM* /dev/ttyUSB* /dev/serial0 2>/dev/null || true
dmesg --color=always | tail -n 80
```

Prefer a stable `/dev/serial/by-id/...` path for USB devices when available.
For non-root services, add the PixEagle/router service account to the platform's
serial-access group (normally `dialout`), then log out and back in:

```bash
sudo usermod -aG dialout <service-user>
```

Do not use world-writable device permissions as a persistent fix.

## 2. Configure The Board And PX4

For a GPIO UART, verify voltage levels, TX/RX crossover, common ground, pin mux,
and whether hardware flow control is required from the board and autopilot
manuals. Do not infer a Pixhawk connector pinout from this repository.

On Raspberry Pi, `/dev/serial0` is the preferred stable alias when the selected
UART is configured. Serial console and Bluetooth ownership vary by Raspberry Pi
model and OS image. Let the current MavlinkAnywhere configurator inspect and
offer the applicable change instead of copying old `/boot/config.txt` commands:

```bash
cd ~/mavlink-anywhere
sudo ./configure_mavlink_router.sh
```

If it requests a reboot, reboot once and rerun the configurator.

On PX4, configure one MAVLink instance for the connected TELEM/USB/Ethernet
interface and match its baud or UDP destination to the companion. Parameter
names and enumerated values change across PX4 releases and boards; use the
current QGroundControl parameter metadata and PX4 documentation for the exact
firmware rather than copying fixed values from this guide.

## 3. Configure MAVLink Routing

The interactive MavlinkAnywhere flow is preferred. For an already verified
UART and baud, the headless command shape is:

```bash
cd ~/mavlink-anywhere
sudo ./configure_mavlink_router.sh --headless \
  --uart /dev/serial0 \
  --baud 921600 \
  --endpoints "127.0.0.1:14540,127.0.0.1:14569,127.0.0.1:12550"
```

Replace `/dev/serial0` and `921600` with the accepted deployment values. For a
PX4 UDP source, use the actual companion listen port:

```bash
cd ~/mavlink-anywhere
sudo ./configure_mavlink_router.sh --headless \
  --input-type udp \
  --input-address 0.0.0.0 \
  --input-port 14550 \
  --endpoints "127.0.0.1:14540,127.0.0.1:14569,127.0.0.1:12550"
```

`14550` is a common example, not a universal PX4 Ethernet setting. The PX4
sender destination and router input must agree.

Advanced operators may maintain
[`mavlink-router` directly](mavlink-router.md). Keep one active router config as
the source of truth; do not start a second router against the same UART.

## 4. Start And Verify

```bash
sudo systemctl status mavlink-router --no-pager
sudo sed -n '1,220p' /etc/mavlink-router/main.conf

cd ~/PixEagle
make run
```

In another terminal:

```bash
ss -lunp | grep -E ':(14540|14569)\b'
ss -ltnp | grep -E ':(50051|8088)\b'
curl -fsS http://127.0.0.1:8088/v1/mavlink/vehicles
```

An empty vehicle list means the bridge is running but has not discovered a
vehicle. Do not treat open ports or a router `active` state as proof of packet
flow. Require fresh telemetry and MAVSDK vehicle discovery before evaluating a
command path.

## Redundant Links

Do not add Ethernet and radio inputs to the same router and assume they provide
safe redundancy. Duplicate MAVLink traffic and route learning can change system
behavior; MAVLink itself does not deconflict redundant channels. Design,
configure, and test primary/fallback or router de-duplication behavior as a
separate deployment feature with captured evidence.

## Related Documentation

- [PX4 and MAVLink connectivity](port-configuration.md)
- [MavlinkAnywhere integration](mavlink-anywhere.md)
- [Manual mavlink-router setup](mavlink-router.md)
- [Connection troubleshooting](../07-troubleshooting/connection-issues.md)
- [Follower safety](../../followers/06-safety/README.md)
