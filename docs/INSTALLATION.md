# Installation Guide

> Detailed installation instructions for PixEagle

## Quick Installation

```bash
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle
bash init_pixeagle.sh
```

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 20.04 | Ubuntu 22.04+ |
| Python | 3.9 | 3.11+ |
| RAM | 4GB | 8GB+ |
| Disk | 2GB | 5GB+ |

### Supported Platforms

- **x86_64** - Intel/AMD desktops, laptops, servers
- **ARM64** - Raspberry Pi 4/5, Jetson Nano/Xavier/Orin
- **ARMv7** - Raspberry Pi 3
- **Raspbian** - Raspberry Pi OS
- **macOS** - Intel and Apple Silicon

## Prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip tmux lsof curl git
```

## Init Script Steps

The `init_pixeagle.sh` script performs a 9-step setup:

1. **System Requirements** - Validates Python version, disk space
2. **System Packages** - Installs missing dependencies
3. **Python Virtual Environment** - Creates isolated venv
4. **Python Dependencies** - Installs from requirements.txt
5. **Node.js via nvm** - Installs Node.js for dashboard
6. **Dashboard Dependencies** - Runs npm install
7. **Configuration Files** - Generates config.yaml and .env
8. **MAVSDK Server** - Downloads platform-specific binary
9. **MAVLink2REST** - Downloads REST API bridge

## Manual Installation

If you prefer manual setup:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Node.js and dashboard
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.nvm/nvm.sh
nvm install 22
cd dashboard && npm install

# Create config files
cp configs/config_default.yaml configs/config.yaml
cp dashboard/env_default.yaml dashboard/.env
```

## Optional Components

### dlib Tracker

```bash
bash scripts/install_dlib.sh
```

### GPU Support (PyTorch)

Visit [PyTorch Installation](https://pytorch.org/get-started/locally/) and install for your CUDA version.

### GStreamer Support

```bash
bash auto_opencv_build.sh
```

For manual build instructions, see [OpenCV GStreamer Guide](OPENCV_GSTREAMER.md).

## Network Requirements

### Required Ports

Ensure these ports are accessible for full functionality:

| Port | Service | Required |
|------|---------|----------|
| 3000 | Dashboard | Yes |
| 5077 | Backend API | Yes |
| 5551 | WebSocket (video) | Yes |
| 8088 | MAVLink2REST API | For OSD/telemetry |
| 14540 | MAVSDK | For PX4 integration |
| 14569 | MAVLink2REST input | For PX4 integration |
| 14550 | QGC | Optional |
| 22 | SSH | For remote access |

### Firewall Configuration (Ubuntu/Raspbian)

```bash
# Allow PixEagle ports
sudo ufw allow 3000/tcp  # Dashboard
sudo ufw allow 5077/tcp  # Backend API
sudo ufw allow 5551/tcp  # WebSocket (video)
sudo ufw allow 8088/tcp  # MAVLink2REST

# For PX4 integration
sudo ufw allow 14540/udp
sudo ufw allow 14569/udp
sudo ufw allow 14550/udp  # QGC (optional)
```

## Verification

```bash
python src/test_Ver.py
```

## Next Steps

- [Configuration Guide](CONFIGURATION.md)
- [SmartTracker Setup](SMART_TRACKER_GUIDE.md)
- [Main README](../README.md)
