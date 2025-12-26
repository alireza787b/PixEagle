# mavlink-router Setup Guide

mavlink-router routes MAVLink messages between multiple endpoints, enabling simultaneous access by PixEagle, QGroundControl, and other tools.

## Installation

### Ubuntu/Debian

```bash
# From package manager (if available)
sudo apt install mavlink-router

# Or build from source
git clone https://github.com/mavlink-router/mavlink-router.git
cd mavlink-router
git submodule update --init --recursive
meson setup build .
ninja -C build
sudo ninja -C build install
```

### Verify Installation

```bash
mavlink-routerd --version
```

## Configuration

### Configuration File Location

```bash
# System-wide
/etc/mavlink-router/main.conf

# User-specific
~/.config/mavlink-router/main.conf

# Project-specific (PixEagle)
/home/alireza/PixEagle/configs/mavlink-router.conf
```

### Basic Configuration

```ini
# /etc/mavlink-router/main.conf

[General]
TcpServerPort = 5760
ReportStats = false
MavlinkDialect = common

# SITL Input
[UdpEndpoint sitl]
Mode = Normal
Address = 127.0.0.1
Port = 14540

# MAVSDK Output (PixEagle commands)
[UdpEndpoint mavsdk]
Mode = Normal
Address = 127.0.0.1
Port = 14541

# QGroundControl
[UdpEndpoint qgc]
Mode = Normal
Address = 127.0.0.1
Port = 14550

# MAVLink2REST
[UdpEndpoint mavlink2rest]
Mode = Normal
Address = 127.0.0.1
Port = 14551
```

### Serial Input Configuration

```ini
# For USB-connected flight controller
[UartEndpoint pixhawk]
Device = /dev/ttyUSB0
Baud = 921600

# For GPIO serial (Raspberry Pi)
[UartEndpoint pixhawk_gpio]
Device = /dev/ttyAMA0
Baud = 921600
FlowControl = false
```

### Ethernet Configuration

```ini
# Flight controller with Ethernet
[UdpEndpoint fmu_ethernet]
Mode = Normal
Address = 192.168.1.10
Port = 14540
```

## Command Line Usage

### Basic Startup

```bash
# Start with config file
mavlink-routerd -c /etc/mavlink-router/main.conf

# Start with command-line endpoints
mavlink-routerd \
    -e 127.0.0.1:14540 \   # MAVSDK
    -e 127.0.0.1:14550 \   # QGC
    -e 127.0.0.1:14551 \   # MAVLink2REST
    0.0.0.0:14540          # Listen for SITL
```

### Serial to UDP

```bash
# Route serial to multiple UDP endpoints
mavlink-routerd \
    -e 127.0.0.1:14540 \
    -e 127.0.0.1:14550 \
    /dev/ttyUSB0:921600
```

### Debug Mode

```bash
# Enable verbose logging
mavlink-routerd -v -c /etc/mavlink-router/main.conf

# Very verbose
mavlink-routerd -vv -c /etc/mavlink-router/main.conf
```

## PixEagle Integration

### Recommended Configuration

```ini
# /home/alireza/PixEagle/configs/mavlink-router.conf

[General]
TcpServerPort = 5760
ReportStats = false

# Input: PX4 SITL or Hardware
[UdpEndpoint px4_input]
Mode = Server
Address = 0.0.0.0
Port = 14540

# Output: MAVSDK (PixEagle commands)
[UdpEndpoint mavsdk_output]
Mode = Normal
Address = 127.0.0.1
Port = 14541

# Output: MAVLink2REST (PixEagle telemetry)
[UdpEndpoint mavlink2rest_output]
Mode = Normal
Address = 127.0.0.1
Port = 14551

# Output: QGroundControl (monitoring)
[UdpEndpoint qgc_output]
Mode = Normal
Address = 127.0.0.1
Port = 14550
```

### Startup Script

```bash
#!/bin/bash
# start_mavlink_router.sh

CONFIG_FILE="${HOME}/PixEagle/configs/mavlink-router.conf"

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Config file not found: $CONFIG_FILE"
    exit 1
fi

mavlink-routerd -c "$CONFIG_FILE"
```

## Systemd Service

### Create Service File

```ini
# /etc/systemd/system/mavlink-router.service

[Unit]
Description=MAVLink Router
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/mavlink-routerd -c /etc/mavlink-router/main.conf
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
```

### Enable Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable mavlink-router
sudo systemctl start mavlink-router

# Check status
sudo systemctl status mavlink-router
```

## Message Filtering

### Filter by Message ID

```ini
# Only forward specific messages to an endpoint
[UdpEndpoint filtered]
Mode = Normal
Address = 127.0.0.1
Port = 14552
Filter = 0,30,33,74,141  # HEARTBEAT, ATTITUDE, POSITION, VFR_HUD, ALTITUDE
```

### Rate Limiting

```ini
# Limit message rate to endpoint
[UdpEndpoint rate_limited]
Mode = Normal
Address = 127.0.0.1
Port = 14553
# Note: Rate limiting requires mavlink-router 2.0+
```

## Troubleshooting

### Check if Running

```bash
# Check process
ps aux | grep mavlink-routerd

# Check listening ports
netstat -ulnp | grep mavlink
# or
ss -ulnp | grep mavlink
```

### Common Issues

#### "Address already in use"

```bash
# Find process using port
sudo lsof -i :14540

# Kill if necessary
sudo kill -9 <PID>
```

#### No Data Received

```bash
# Check SITL is sending
tcpdump -i lo udp port 14540

# Verify mavlink-router is receiving
mavlink-routerd -vv -c main.conf
```

#### Permission Denied on Serial

```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Log out and back in, or:
newgrp dialout
```

### Debug Commands

```bash
# Monitor all MAVLink traffic
mavlink-routerd -vv ... 2>&1 | grep -i "message"

# Check specific endpoint
mavlink-routerd -vv ... 2>&1 | grep "14540"
```

## Performance Tuning

### Buffer Sizes

For high-frequency data:

```ini
[General]
# Increase internal buffer
MaxBuffer = 65536
```

### Multiple Sources

When routing from multiple sources:

```ini
# Mark as ground station to differentiate
[UdpEndpoint source1]
Mode = Normal
Address = 192.168.1.10
Port = 14540
# System ID filtering prevents conflicts
```

## Related Documentation

- [MAVLink2REST Setup](mavlink-anywhere.md) - REST API configuration
- [SITL Setup](sitl-setup.md) - Simulation environment
- [Port Configuration](port-configuration.md) - Network reference
