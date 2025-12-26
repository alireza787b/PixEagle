# Hardware Connection Guide

This guide covers connecting PixEagle to physical PX4 flight controllers.

## Connection Methods

| Method | Speed | Distance | Use Case |
|--------|-------|----------|----------|
| USB Serial | Up to 3 Mbps | ~3m | Bench testing |
| UART Serial | Up to 921600 baud | ~1m | Companion computer |
| Ethernet | 100 Mbps+ | ~100m | Production systems |
| Telemetry Radio | 57600-115200 baud | km+ | Long range |

## USB Serial Connection

### Identify the Device

```bash
# Before connecting
ls /dev/ttyUSB* /dev/ttyACM*

# Connect flight controller via USB

# After connecting
ls /dev/ttyUSB* /dev/ttyACM*

# Typically appears as /dev/ttyACM0 or /dev/ttyUSB0
```

### Set Permissions

```bash
# Add user to dialout group
sudo usermod -a -G dialout $USER

# Apply changes (or logout/login)
newgrp dialout

# Or set device permissions directly
sudo chmod 666 /dev/ttyACM0
```

### Configure mavlink-router

```ini
# /etc/mavlink-router/main.conf

[UartEndpoint pixhawk_usb]
Device = /dev/ttyACM0
Baud = 921600

[UdpEndpoint mavsdk]
Mode = Normal
Address = 127.0.0.1
Port = 14541

[UdpEndpoint mavlink2rest]
Mode = Normal
Address = 127.0.0.1
Port = 14551
```

### Start mavlink-router

```bash
mavlink-routerd -c /etc/mavlink-router/main.conf
```

## UART Serial Connection

### Raspberry Pi GPIO Serial

```
Pixhawk TELEM1/2 ───────────► Raspberry Pi GPIO

Pin Mapping:
  Pixhawk TX  → RPi RX (GPIO 15, Pin 10)
  Pixhawk RX  → RPi TX (GPIO 14, Pin 8)
  Pixhawk GND → RPi GND (Pin 6)
```

### Enable UART on Raspberry Pi

```bash
# Edit config
sudo nano /boot/config.txt

# Add:
enable_uart=1
dtoverlay=disable-bt  # Disable Bluetooth to free UART

# Disable console on serial
sudo systemctl disable serial-getty@ttyS0.service
sudo systemctl stop serial-getty@ttyS0.service

# Reboot
sudo reboot
```

### Configure for UART

```ini
# /etc/mavlink-router/main.conf

[UartEndpoint pixhawk_uart]
Device = /dev/ttyAMA0
Baud = 921600
FlowControl = false

[UdpEndpoint mavsdk]
Mode = Normal
Address = 127.0.0.1
Port = 14541

[UdpEndpoint mavlink2rest]
Mode = Normal
Address = 127.0.0.1
Port = 14551
```

### PX4 Configuration

Set MAVLink stream rate on the connected port:

```
# In QGroundControl or via param set
MAV_0_CONFIG = TELEM 1
MAV_0_RATE = 921600
SER_TEL1_BAUD = 921600
```

## Ethernet Connection

### Requirements

- Flight controller with Ethernet (e.g., Pixhawk 6X, Cube Orange+)
- Ethernet-capable companion computer
- CAT5e/CAT6 cable

### Network Configuration

```
Flight Controller:
  IP: 192.168.1.10
  Netmask: 255.255.255.0
  MAVLink Port: 14540

Companion Computer:
  IP: 192.168.1.20
  Netmask: 255.255.255.0
```

### PX4 Parameters

```
# Set via QGroundControl
MAV_0_CONFIG = Ethernet
MAV_0_BROADCAST = 1
MAV_0_MODE = Onboard
```

### mavlink-router Configuration

```ini
# /etc/mavlink-router/main.conf

[UdpEndpoint px4_ethernet]
Mode = Normal
Address = 192.168.1.10
Port = 14540

[UdpEndpoint mavsdk]
Mode = Normal
Address = 127.0.0.1
Port = 14541

[UdpEndpoint mavlink2rest]
Mode = Normal
Address = 127.0.0.1
Port = 14551
```

### Static IP Configuration (Ubuntu)

```yaml
# /etc/netplan/01-ethernet.yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses:
        - 192.168.1.20/24
```

Apply:
```bash
sudo netplan apply
```

## Telemetry Radio Connection

### Common Radios

- SiK Radios (3DR, RFD900, etc.)
- Holybro Telemetry Radio
- mRo SiK Telemetry Radio

### Ground Station Setup

```bash
# Connect radio USB module
# Usually appears as /dev/ttyUSB0

# Configure mavlink-router
[UartEndpoint telemetry_radio]
Device = /dev/ttyUSB0
Baud = 57600  # Match radio configuration

[UdpEndpoint mavsdk]
Mode = Normal
Address = 127.0.0.1
Port = 14541
```

### Radio Configuration

Use Mission Planner or SiK Radio Configurator:
- Air baud rate: 57600 (default)
- Net ID: Match air and ground
- ECC: Enabled for reliability

## Multi-Connection Setup

### Redundant Links

```ini
# /etc/mavlink-router/main.conf

# Primary: Ethernet
[UdpEndpoint px4_ethernet]
Mode = Normal
Address = 192.168.1.10
Port = 14540

# Backup: Telemetry Radio
[UartEndpoint telemetry_radio]
Device = /dev/ttyUSB0
Baud = 57600

# Outputs
[UdpEndpoint mavsdk]
Mode = Normal
Address = 127.0.0.1
Port = 14541

[UdpEndpoint mavlink2rest]
Mode = Normal
Address = 127.0.0.1
Port = 14551
```

mavlink-router automatically merges traffic from multiple sources.

## Flight Controller Ports

### Pixhawk 4/5/6

| Port | Purpose | Typical Use |
|------|---------|-------------|
| TELEM1 | MAVLink | Companion computer |
| TELEM2 | MAVLink | Telemetry radio |
| USB | MAVLink/Console | Development |
| GPS | Serial | GPS module |

### Recommended Port Assignment

| Component | Port | Baud Rate |
|-----------|------|-----------|
| Companion Computer | TELEM1 | 921600 |
| Telemetry Radio | TELEM2 | 57600 |
| USB (testing) | USB | 921600 |

## Verification

### Check Connection

```bash
# Verify mavlink-router is receiving
mavlink-routerd -vv -c main.conf 2>&1 | head -50

# Check MAVLink2REST
curl http://localhost:8088/mavlink/vehicles

# Check message rate
curl http://localhost:8088/mavlink/vehicles/1/components/1/messages/HEARTBEAT | jq '.status.time.frequency'
```

### Test MAVSDK Connection

```python
import asyncio
from mavsdk import System

async def test():
    drone = System()
    await drone.connect(system_address="udp://:14541")

    async for state in drone.core.connection_state():
        print(f"Connected: {state.is_connected}")
        if state.is_connected:
            break

    async for battery in drone.telemetry.battery():
        print(f"Battery: {battery.remaining_percent}%")
        break

asyncio.run(test())
```

## Troubleshooting

### No Data on Serial

```bash
# Check device exists
ls -la /dev/ttyUSB* /dev/ttyACM*

# Check permissions
groups $USER  # Should include 'dialout'

# Test with minicom
minicom -D /dev/ttyACM0 -b 921600
```

### Intermittent Connection

- Check cable connections
- Verify baud rate matches PX4 configuration
- Try lower baud rate (115200)
- Check for EMI interference

### High Latency

- Use higher baud rate if possible
- Reduce MAVLink stream rate
- Use Ethernet instead of serial

## Related Documentation

- [mavlink-router Setup](mavlink-router.md) - Message routing
- [Companion Computer](companion-computer.md) - RPi/Jetson setup
- [Port Configuration](port-configuration.md) - Network ports
