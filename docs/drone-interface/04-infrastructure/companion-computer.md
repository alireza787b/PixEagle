# Companion Computer Setup

This guide covers setting up PixEagle on companion computers (Raspberry Pi, NVIDIA Jetson, Intel NUC).

## Overview

A companion computer runs PixEagle onboard the drone, enabling autonomous tracking without ground station dependency.

## Supported Platforms

| Platform | RAM | Compute | Best For |
|----------|-----|---------|----------|
| Raspberry Pi 4 | 4-8 GB | CPU | Basic tracking |
| Raspberry Pi 5 | 4-8 GB | CPU | Standard tracking |
| Jetson Nano | 4 GB | GPU | YOLO inference |
| Jetson Orin Nano | 8 GB | GPU | Real-time YOLO |
| Intel NUC | 8-32 GB | CPU/iGPU | High-performance |

## Raspberry Pi Setup

### Base Installation

```bash
# Flash Raspberry Pi OS (64-bit) to SD card
# Use Raspberry Pi Imager

# Enable SSH during imaging or:
sudo systemctl enable ssh
sudo systemctl start ssh

# Update system
sudo apt update && sudo apt full-upgrade -y
```

### Install Dependencies

```bash
# Python and build tools
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-opencv \
    libopencv-dev \
    git \
    cmake

# Video capture
sudo apt install -y \
    v4l-utils \
    libv4l-dev \
    libgstreamer1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good

# MAVSDK dependencies
sudo apt install -y libatomic1
```

### Install PixEagle

```bash
# Clone repository
cd ~
git clone https://github.com/yourusername/PixEagle.git
cd PixEagle

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### UART Configuration

See [Hardware Connection](hardware-connection.md#uart-serial-connection) for detailed UART setup.

```bash
# Enable UART
sudo nano /boot/config.txt
# Add: enable_uart=1

# Disable Bluetooth (frees primary UART)
# Add: dtoverlay=disable-bt

sudo reboot
```

### Autostart Configuration

```ini
# /etc/systemd/system/pixeagle.service

[Unit]
Description=PixEagle Tracking System
After=network.target mavlink-router.service mavlink2rest.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/PixEagle
ExecStart=/home/pi/PixEagle/venv/bin/python main.py
Restart=always
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
```

Enable service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable pixeagle
```

## NVIDIA Jetson Setup

### JetPack Installation

Flash JetPack using NVIDIA SDK Manager on a host computer.

### Post-Flash Setup

```bash
# Update system
sudo apt update && sudo apt full-upgrade -y

# Install Python dependencies
sudo apt install -y \
    python3-pip \
    python3-venv \
    python3-numpy \
    libopencv-python

# Install PyTorch for Jetson
# Version depends on JetPack version
# See: https://forums.developer.nvidia.com/t/pytorch-for-jetson/
```

### CUDA-Enabled PixEagle

```bash
# Clone repository
git clone https://github.com/yourusername/PixEagle.git
cd PixEagle

# Create environment
python3 -m venv venv
source venv/bin/activate

# Install with CUDA support
pip install -r requirements-jetson.txt
```

### Power Mode

Set maximum performance:
```bash
# Check current mode
nvpmodel -q

# Set maximum performance (Jetson Nano)
sudo nvpmodel -m 0

# Enable all cores
sudo jetson_clocks
```

### Thermal Management

```bash
# Monitor temperature
tegrastats

# Install fan control (if applicable)
sudo apt install python3-pip
pip3 install jetson-stats
sudo jtop
```

## Intel NUC Setup

### Ubuntu Installation

Flash Ubuntu 22.04 LTS to NUC.

### Intel Optimizations

```bash
# Install Intel OpenVINO for inference acceleration
# See: https://docs.openvino.ai/

# Install Intel MKL for NumPy acceleration
pip install intel-numpy
```

## Camera Configuration

### USB Camera (All Platforms)

```bash
# List cameras
v4l2-ctl --list-devices

# Check capabilities
v4l2-ctl -d /dev/video0 --all

# Set resolution
v4l2-ctl -d /dev/video0 --set-fmt-video=width=1280,height=720
```

### CSI Camera (RPi/Jetson)

```bash
# Raspberry Pi
# Enable camera in raspi-config
sudo raspi-config
# Interface Options → Camera → Enable

# Jetson
# CSI cameras work out of the box
nvgstcapture-1.0  # Test capture
```

### PixEagle Camera Config

```yaml
# config_default.yaml
video:
  source: 0  # /dev/video0
  width: 1280
  height: 720
  fps: 30

  # Or for CSI camera on Jetson
  # source: "nvarguscamerasrc ! video/x-raw(memory:NVMM), width=1280, height=720 ! nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! video/x-raw, format=BGR ! appsink"
```

## Network Configuration

### Static IP

```yaml
# /etc/netplan/01-static.yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: no
      addresses:
        - 192.168.1.20/24
      gateway4: 192.168.1.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
```

Apply:
```bash
sudo netplan apply
```

### WiFi Access Point (Optional)

Create a WiFi AP for dashboard access:

```bash
# Install hostapd
sudo apt install -y hostapd dnsmasq

# Configure (detailed setup beyond this guide)
```

## Complete Startup Stack

### Systemd Services Order

```
1. mavlink-router.service
2. mavlink2rest.service
3. pixeagle.service
```

### Master Startup Script

```bash
#!/bin/bash
# /home/pi/start_pixeagle_stack.sh

# Wait for network
sleep 10

# Start mavlink-router
mavlink-routerd -c /etc/mavlink-router/main.conf &
sleep 2

# Start MAVLink2REST
docker run -d --rm --name mavlink2rest --network host \
    bluerobotics/mavlink2rest --mavlink udpin:0.0.0.0:14551

sleep 2

# Start PixEagle
cd /home/pi/PixEagle
source venv/bin/activate
python main.py
```

## Performance Optimization

### Raspberry Pi

```bash
# Increase GPU memory
sudo nano /boot/config.txt
# Add: gpu_mem=256

# Overclock (optional, with cooling)
# Add:
# over_voltage=6
# arm_freq=2000

# Disable unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
```

### Jetson

```bash
# Maximum performance
sudo nvpmodel -m 0
sudo jetson_clocks

# Disable GUI (saves resources)
sudo systemctl set-default multi-user.target
```

## Monitoring

### System Resources

```bash
# CPU/Memory usage
htop

# Disk usage
df -h

# GPU (Jetson)
tegrastats

# Temperature (RPi)
vcgencmd measure_temp
```

### PixEagle Logs

```bash
# View service logs
journalctl -u pixeagle -f

# View application logs
tail -f ~/PixEagle/logs/pixeagle.log
```

## Troubleshooting

### Camera Not Found

```bash
# Check if detected
v4l2-ctl --list-devices

# Check permissions
ls -la /dev/video*
sudo chmod 666 /dev/video0
```

### High CPU Usage

- Reduce video resolution
- Lower tracker FPS
- Use hardware video decode
- Disable unnecessary features

### Memory Issues

```bash
# Check memory usage
free -h

# Add swap (RPi)
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Set CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

## Related Documentation

- [Hardware Connection](hardware-connection.md) - Physical connections
- [SITL Setup](sitl-setup.md) - Development testing
- [Port Configuration](port-configuration.md) - Network ports
