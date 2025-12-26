# PX4 SITL Setup Guide

Software-In-The-Loop (SITL) simulation enables PixEagle development and testing without physical hardware.

## Overview

PX4 SITL runs the full PX4 flight stack on your development machine, simulating drone physics in Gazebo or jMAVSim.

## Prerequisites

### System Requirements

- Ubuntu 20.04/22.04 LTS (recommended)
- 8GB+ RAM (16GB for Gazebo)
- Modern CPU with virtualization support
- GPU recommended for Gazebo (not required for jMAVSim)

### Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install common dependencies
sudo apt install -y \
    git \
    cmake \
    python3-pip \
    python3-jinja2 \
    python3-toml \
    python3-numpy \
    python3-empy \
    python3-packaging \
    ninja-build \
    libgstreamer1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good
```

## PX4 Installation

### Clone PX4 Repository

```bash
cd ~
git clone https://github.com/PX4/PX4-Autopilot.git --recursive
cd PX4-Autopilot
```

### Run Setup Script

```bash
# Install all dependencies
bash ./Tools/setup/ubuntu.sh

# Log out and back in (or reboot) after setup
```

### Verify Installation

```bash
# Build SITL (first build takes 10-30 minutes)
make px4_sitl_default
```

## Running SITL

### jMAVSim (Lightweight)

```bash
cd ~/PX4-Autopilot

# Start with jMAVSim
make px4_sitl_default jmavsim

# Headless mode (no GUI)
HEADLESS=1 make px4_sitl_default jmavsim
```

### Gazebo Classic

```bash
cd ~/PX4-Autopilot

# Standard quadcopter
make px4_sitl_default gazebo-classic

# Specific vehicle
make px4_sitl_default gazebo-classic_iris
make px4_sitl_default gazebo-classic_typhoon_h480
make px4_sitl_default gazebo-classic_plane

# Headless mode
HEADLESS=1 make px4_sitl_default gazebo-classic
```

### Gazebo Sim (New Generation)

```bash
cd ~/PX4-Autopilot

# Install Gazebo Sim dependencies
make px4_sitl gz_x500

# With specific world
PX4_GZ_WORLD=default make px4_sitl gz_x500
```

## MAVLink Configuration

### Default Ports

When SITL starts, it creates MAVLink endpoints:

| Port | Protocol | Purpose |
|------|----------|---------|
| 14540 | UDP | SDK connection (MAVSDK) |
| 14550 | UDP | Ground station (QGC) |
| 18570 | UDP | Secondary |

### Verify MAVLink Output

```bash
# In another terminal, check SITL is sending
nc -ulp 14550

# Or use tcpdump
sudo tcpdump -i lo udp port 14540
```

## Integration with mavlink-router

### Recommended Setup

```bash
# Terminal 1: Start SITL
cd ~/PX4-Autopilot
make px4_sitl_default jmavsim

# Terminal 2: Start mavlink-router
mavlink-routerd \
    -e 127.0.0.1:14541 \  # MAVSDK (PixEagle)
    -e 127.0.0.1:14550 \  # QGC
    -e 127.0.0.1:14551 \  # MAVLink2REST
    0.0.0.0:14540          # Listen for SITL

# Terminal 3: Start MAVLink2REST
docker run --rm --network host bluerobotics/mavlink2rest --mavlink udpin:0.0.0.0:14551

# Terminal 4: Start PixEagle
cd ~/PixEagle
source venv/bin/activate
python main.py
```

### PixEagle Configuration for SITL

```yaml
# config_default.yaml
px4:
  connection_string: "udp://:14541"
  offboard_rate_hz: 20

mavlink2rest:
  enabled: true
  base_url: "http://localhost:8088"
  poll_rate_hz: 20

circuit_breaker:
  active: false  # Allow real commands in SITL
```

## Startup Scripts

### All-in-One Script

```bash
#!/bin/bash
# start_sitl_stack.sh

# Configuration
PX4_DIR="${HOME}/PX4-Autopilot"
PIXEAGLE_DIR="${HOME}/PixEagle"

# Start SITL in background
echo "Starting PX4 SITL..."
cd "$PX4_DIR"
HEADLESS=1 make px4_sitl_default jmavsim &
SITL_PID=$!
sleep 10  # Wait for SITL to initialize

# Start mavlink-router
echo "Starting mavlink-router..."
mavlink-routerd \
    -e 127.0.0.1:14541 \
    -e 127.0.0.1:14550 \
    -e 127.0.0.1:14551 \
    0.0.0.0:14540 &
ROUTER_PID=$!
sleep 2

# Start MAVLink2REST
echo "Starting MAVLink2REST..."
docker run -d --rm --name mavlink2rest --network host \
    bluerobotics/mavlink2rest --mavlink udpin:0.0.0.0:14551
sleep 2

# Start QGroundControl (optional)
# qgroundcontrol &

echo "SITL stack ready!"
echo "  SITL PID: $SITL_PID"
echo "  Router PID: $ROUTER_PID"
echo ""
echo "Start PixEagle with:"
echo "  cd $PIXEAGLE_DIR && source venv/bin/activate && python main.py"

# Wait for SITL
wait $SITL_PID
```

### Cleanup Script

```bash
#!/bin/bash
# stop_sitl_stack.sh

# Stop MAVLink2REST
docker stop mavlink2rest 2>/dev/null

# Stop mavlink-router
pkill -f mavlink-routerd

# Stop SITL (careful - this kills all PX4 processes)
pkill -f px4

echo "SITL stack stopped"
```

## PX4 Shell Commands

### In the SITL Terminal

```bash
# Takeoff
commander takeoff

# Land
commander land

# Set flight mode
commander mode offboard
commander mode posctl
commander mode rtl

# Arm/Disarm
commander arm
commander disarm

# Check status
commander status
```

### From PixEagle (via MAVSDK)

```python
# These are available in PX4InterfaceManager
await self.drone.action.arm()
await self.drone.action.takeoff()
await self.drone.action.land()
await self.drone.action.return_to_launch()
```

## Multiple SITL Instances

### Running Multiple Drones

```bash
# Instance 1
PX4_SIM_HOST_ADDR=127.0.0.1 \
PX4_SIM_MODEL=iris \
PX4_INSTANCE=0 \
make px4_sitl_default jmavsim

# Instance 2 (different terminal)
PX4_SIM_HOST_ADDR=127.0.0.1 \
PX4_SIM_MODEL=iris \
PX4_INSTANCE=1 \
make px4_sitl_default jmavsim
```

Port offset: Instance N uses ports 14540+N*10, 14550+N*10, etc.

## Troubleshooting

### SITL Won't Start

```bash
# Clean build
cd ~/PX4-Autopilot
make clean
make distclean
make px4_sitl_default jmavsim
```

### No MAVLink Output

```bash
# Check if listening
netstat -ulnp | grep 14540

# Check process
ps aux | grep px4
```

### Gazebo Crashes

```bash
# Use jMAVSim instead (more stable)
HEADLESS=1 make px4_sitl_default jmavsim

# Or reduce Gazebo complexity
export SVGA_VGPU10=0  # Disable advanced graphics
make px4_sitl_default gazebo-classic
```

### Slow Performance

```bash
# Use lockstep disabled for better performance
PX4_SIM_SPEED_FACTOR=1 make px4_sitl_default jmavsim

# Or run headless
HEADLESS=1 make px4_sitl_default jmavsim
```

## Testing PixEagle with SITL

### Basic Connection Test

```python
# test_connection.py
import asyncio
from mavsdk import System

async def main():
    drone = System()
    await drone.connect(system_address="udp://:14541")

    async for state in drone.core.connection_state():
        print(f"Connected: {state.is_connected}")
        if state.is_connected:
            break

asyncio.run(main())
```

### Offboard Test

```python
# test_offboard.py
import asyncio
from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed

async def main():
    drone = System()
    await drone.connect(system_address="udp://:14541")

    # Wait for connection
    async for state in drone.core.connection_state():
        if state.is_connected:
            break

    # Arm and takeoff
    await drone.action.arm()
    await drone.action.takeoff()
    await asyncio.sleep(5)

    # Start offboard mode
    await drone.offboard.set_velocity_body(
        VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
    )
    await drone.offboard.start()

    # Move forward for 3 seconds
    await drone.offboard.set_velocity_body(
        VelocityBodyYawspeed(2.0, 0.0, 0.0, 0.0)
    )
    await asyncio.sleep(3)

    # Stop and land
    await drone.offboard.stop()
    await drone.action.land()

asyncio.run(main())
```

## Related Documentation

- [mavlink-router Setup](mavlink-router.md) - Message routing
- [MAVLink2REST Setup](mavlink-anywhere.md) - REST API
- [Hardware Connection](hardware-connection.md) - Physical setup
