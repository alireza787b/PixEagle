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
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle

# Recommended: run guided init
make init
```

If you choose **Full** profile and SmartTracker AI deps fail verification, recover manually:

```bash
source venv/bin/activate
pip install --prefer-binary ultralytics lap
pip install --prefer-binary ncnn
pip install --prefer-binary pnnx
python -c "from ultralytics import YOLO; import lap; import pnnx; print('AI OK')"
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

Normal `make init` skips service setup. On a deployment host where PixEagle
should run as a managed service, opt in explicitly:

```bash
cd ~/PixEagle
sudo bash scripts/service/install.sh
sudo pixeagle-service enable
sudo pixeagle-service start
pixeagle-service logs -f
```

The guided init path is also available for deployment setup:

```bash
PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init
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
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle

# Create environment
python3 -m venv venv
source venv/bin/activate

# Install accelerator-aware dependencies
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh
bash scripts/setup/check-ai-runtime.sh
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
VideoSource:
  VIDEO_SOURCE_TYPE: USB_CAMERA
  CAMERA_INDEX: 0
  CAPTURE_WIDTH: 1280
  CAPTURE_HEIGHT: 720
  CAPTURE_FPS: 30

  # Or for CSI camera on Jetson
  # VIDEO_SOURCE_TYPE: CUSTOM_GSTREAMER
  # CUSTOM_PIPELINE: "nvarguscamerasrc ! video/x-raw(memory:NVMM), width=1280, height=720 ! nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! video/x-raw, format=BGR ! appsink"
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

Create a WiFi AP for field networking only after deciding the operator access
model. For browser dashboard access, prefer an SSH tunnel to the local-only
backend, or use an explicit credentialed `browser_session` profile with exact
Host/CORS allowlists when that deployment has passed the hardening gates.

```bash
# Install hostapd
sudo apt install -y hostapd dnsmasq

# Configure (detailed setup beyond this guide)
```

## Complete Startup Stack

### Systemd Services Order

```
1. mavlink-router service or MavlinkAnywhere-managed router
2. MAVLink2REST wrapper bound to 127.0.0.1:8088
3. pixeagle.service
```

Avoid ad hoc master startup scripts that also start MAVLink routing or
MAVLink2REST. MavlinkAnywhere owns routing service lifecycle, PixEagle owns its
own managed service, and each service should be started, updated, and evidenced
through its own runbook.

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
