# MAVLink2REST Setup Guide

MAVLink2REST provides a REST API for accessing MAVLink data, enabling PixEagle to retrieve telemetry via simple HTTP requests.

## Overview

MAVLink2REST (also known as mavlink-anywhere) converts MAVLink streams to HTTP endpoints, making telemetry accessible without complex MAVLink parsing.

## Installation

### Docker (Recommended)

```bash
# Pull official image
docker pull bluerobotics/mavlink2rest

# Run with default settings
docker run -d \
    --name mavlink2rest \
    -p 8088:8088 \
    --network host \
    bluerobotics/mavlink2rest

# Or with specific MAVLink source
docker run -d \
    --name mavlink2rest \
    -p 8088:8088 \
    bluerobotics/mavlink2rest \
    --mavlink udpin:0.0.0.0:14551
```

### Cargo (From Source)

```bash
# Install Rust if needed
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install from crates.io
cargo install mavlink2rest

# Or build from source
git clone https://github.com/patrickelectric/mavlink2rest.git
cd mavlink2rest
cargo build --release
./target/release/mavlink2rest
```

### Verify Installation

```bash
# Check service is running
curl http://localhost:8088/mavlink/vehicles

# Should return list of connected vehicles
```

## Configuration

### Command Line Options

```bash
mavlink2rest \
    --mavlink udpin:0.0.0.0:14551 \  # MAVLink source
    --server 0.0.0.0:8088 \          # HTTP server address
    --verbose                         # Enable debug logging
```

### Common MAVLink Sources

```bash
# UDP from mavlink-router
--mavlink udpin:0.0.0.0:14551

# Serial connection
--mavlink serial:/dev/ttyUSB0:921600

# TCP server
--mavlink tcpout:127.0.0.1:5760

# TCP client
--mavlink tcpin:127.0.0.1:5760
```

### Docker Compose

```yaml
# docker-compose.yml
version: '3'
services:
  mavlink2rest:
    image: bluerobotics/mavlink2rest
    container_name: mavlink2rest
    network_mode: host
    command: --mavlink udpin:0.0.0.0:14551 --server 0.0.0.0:8088
    restart: unless-stopped
```

## API Endpoints

### List Vehicles

```bash
curl http://localhost:8088/mavlink/vehicles
```

Response:
```json
{
  "vehicles": [1]
}
```

### List Components

```bash
curl http://localhost:8088/mavlink/vehicles/1/components
```

Response:
```json
{
  "components": [1, 190]
}
```

### Get Message

```bash
# Get ATTITUDE message
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages/ATTITUDE
```

Response:
```json
{
  "status": {
    "time": {
      "first_update": "2024-01-15T10:30:00Z",
      "last_update": "2024-01-15T10:30:01Z",
      "frequency": 50.0
    }
  },
  "message": {
    "type": "ATTITUDE",
    "time_boot_ms": 123456,
    "roll": 0.05,
    "pitch": -0.02,
    "yaw": 1.57,
    "rollspeed": 0.01,
    "pitchspeed": 0.0,
    "yawspeed": 0.02
  }
}
```

### Messages Used by PixEagle

| Endpoint | Purpose |
|----------|---------|
| `/mavlink/vehicles/1/components/1/messages/ATTITUDE` | Roll, pitch, yaw |
| `/mavlink/vehicles/1/components/1/messages/ALTITUDE` | Altitude data |
| `/mavlink/vehicles/1/components/1/messages/VFR_HUD` | Ground speed, throttle |
| `/mavlink/vehicles/1/components/1/messages/HEARTBEAT` | Flight mode |

## PixEagle Integration

### Configuration

```yaml
# config_default.yaml
mavlink2rest:
  enabled: true
  base_url: "http://localhost:8088"
  poll_rate_hz: 20
  timeout_s: 1.0
```

### MavlinkDataManager Usage

```python
class MavlinkDataManager:
    def __init__(self):
        self.base_url = "http://localhost:8088"
        self.endpoint_base = "/mavlink/vehicles/1/components/1/messages"

    def fetch_attitude_data(self):
        url = f"{self.base_url}{self.endpoint_base}/ATTITUDE"
        response = requests.get(url, timeout=1.0)
        data = response.json()

        return {
            'roll': math.degrees(data['message']['roll']),
            'pitch': math.degrees(data['message']['pitch']),
            'yaw': math.degrees(data['message']['yaw'])
        }
```

## Systemd Service

### Create Service File

```ini
# /etc/systemd/system/mavlink2rest.service

[Unit]
Description=MAVLink2REST API Server
After=network.target mavlink-router.service
Requires=mavlink-router.service

[Service]
Type=simple
ExecStart=/usr/local/bin/mavlink2rest --mavlink udpin:0.0.0.0:14551 --server 0.0.0.0:8088
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
```

### Docker Service

```ini
# /etc/systemd/system/mavlink2rest-docker.service

[Unit]
Description=MAVLink2REST Docker Container
After=docker.service mavlink-router.service
Requires=docker.service

[Service]
Type=simple
ExecStartPre=-/usr/bin/docker stop mavlink2rest
ExecStartPre=-/usr/bin/docker rm mavlink2rest
ExecStart=/usr/bin/docker run --rm --name mavlink2rest --network host bluerobotics/mavlink2rest --mavlink udpin:0.0.0.0:14551
ExecStop=/usr/bin/docker stop mavlink2rest
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### Enable Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable mavlink2rest
sudo systemctl start mavlink2rest
```

## Troubleshooting

### No Data Available

```bash
# Check MAVLink2REST is receiving data
curl http://localhost:8088/mavlink/vehicles

# If empty, check mavlink-router is routing to correct port
netstat -ulnp | grep 14551
```

### Connection Refused

```bash
# Check service is running
systemctl status mavlink2rest

# Check port binding
ss -tlnp | grep 8088

# Check firewall
sudo ufw status
```

### Stale Data

Check message frequency:
```bash
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages/ATTITUDE | jq '.status.time.frequency'
```

If frequency is 0 or very low, MAVLink source may not be providing data.

### Docker Networking Issues

```bash
# Use host networking for simplest setup
docker run --network host ...

# Or expose specific ports
docker run -p 8088:8088 -p 14551:14551/udp ...
```

## Performance

### Polling Rates

| Use Case | Recommended Poll Rate |
|----------|----------------------|
| Attitude | 20-50 Hz |
| Altitude | 10-20 Hz |
| Ground Speed | 4-10 Hz |
| Flight Mode | 1-2 Hz |

### PixEagle Default

PixEagle polls at 20 Hz by default, which provides good responsiveness while avoiding excessive load.

### Caching Behavior

MAVLink2REST caches the latest message of each type. Polling faster than the source rate returns the same cached data.

## Security

### Localhost Only (Default)

By default, bind to localhost only:
```bash
--server 127.0.0.1:8088
```

### Network Access

To allow network access (use with caution):
```bash
--server 0.0.0.0:8088
```

Consider firewall rules:
```bash
sudo ufw allow from 192.168.1.0/24 to any port 8088
```

## Related Documentation

- [mavlink-router Setup](mavlink-router.md) - MAVLink routing
- [MavlinkDataManager](../02-components/mavlink-data-manager.md) - PixEagle integration
- [MAVLink2REST API](../03-protocols/mavlink2rest-api.md) - API reference
