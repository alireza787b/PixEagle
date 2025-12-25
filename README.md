# PixEagle

> Vision-based autonomous tracking system for drones and ground vehicles

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Raspberry%20Pi%20%7C%20Jetson-blue)](https://github.com/alireza787b/PixEagle)
[![PX4](https://img.shields.io/badge/Autopilot-PX4-orange)](https://px4.io/)

**PixEagle** is a modular image-processing and tracking suite for drones running PX4 autopilot. It combines MAVSDK Python, OpenCV, and YOLO object detection to deliver high-performance visual tracking and autonomous following.

**[Full Documentation](docs/README.md)** | **[Changelog](CHANGELOG.md)** | **[YouTube Demo](https://www.youtube.com/watch?v=vJn27WEXQJw)**

---

## Features

- **SmartTracker** - AI-powered tracking with YOLO + ByteTrack/BoT-SORT ([Guide](docs/SMART_TRACKER_GUIDE.md))
- **Professional OSD** - Aviation-grade on-screen display with TrueType fonts ([Guide](docs/OSD_GUIDE.md))
- **GPU Acceleration** - CUDA support for 60+ FPS, automatic CPU fallback
- **Web Dashboard** - Real-time monitoring, model management, config UI
- **Schema Architecture** - Extensible YAML-based configuration ([Developer Guide](docs/Tracker_and_Follower_Schema_Developer_Guide.md))
- **Multiple Follower Modes** - Position hold, chase, gimbal pursuit, fixed-wing support

---

## Demo

[![PixEagle Demo](https://img.youtube.com/vi/vJn27WEXQJw/maxresdefault.jpg)](https://www.youtube.com/watch?v=vJn27WEXQJw)

**[Full YouTube Playlist](https://www.youtube.com/watch?v=nMThQLC7nBg&list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)**

---

## Quick Start

### Prerequisites

- Ubuntu 22.04+ / Raspbian (Linux recommended) or Windows for SITL only
- Python 3.9+
- 4GB+ RAM

```bash
# Install system dependencies
sudo apt update && sudo apt install -y python3 python3-venv python3-pip tmux lsof curl git
```

### Installation

```bash
# Clone and initialize
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle
bash init_pixeagle.sh
```

The init script runs a 9-step automated setup including Python venv, Node.js, dashboard, and MAVSDK/MAVLink2REST binaries.

### Run

```bash
bash run_pixeagle.sh
```

### Access Dashboard

Open in your browser:
- **Local**: http://localhost:3000
- **LAN**: http://<your-ip>:3000 (auto-detected, accessible from any device on network)

---

## Configuration

Most settings can be configured via the **Web Dashboard UI** (Settings page).

For manual configuration, edit `configs/config.yaml`:
```bash
nano configs/config.yaml
```

> **Note**: `config.yaml` is gitignored and created by the init script. Default values are in `configs/config_default.yaml`.

---

## GPU Setup (Optional)

For CUDA-accelerated YOLO inference:

```bash
# Example for CUDA 12.4
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
```

Visit [PyTorch Installation](https://pytorch.org/get-started/locally/) for your specific setup.

---

## PX4 Integration

### Port Requirements

Your PX4 connection (serial/ethernet) must route MAVLink data to these ports:

| Port | Service | Purpose |
|------|---------|---------|
| 14540 | MAVSDK | PX4 telemetry & commands |
| 14569 | MAVLink2REST | REST API for OSD/telemetry |
| 14550 | QGC | Ground Control Station (optional) |

### MAVLink Routing

**Option A: mavlink-anywhere (Recommended)**

Step-by-step guided setup for serial/ethernet routing:

```bash
git clone https://github.com/alireza787b/mavlink-anywhere.git
cd mavlink-anywhere
bash install_mavlink_router.sh
bash configure_mavlink_router.sh  # Configure your serial port and endpoints
```

- **Repository**: [github.com/alireza787b/mavlink-anywhere](https://github.com/alireza787b/mavlink-anywhere)
- **Video Tutorial**: [YouTube - MAVLink Anywhere Setup](https://www.youtube.com/watch?v=_QEWpoy6HSo)

**Option B: Manual mavlink-routerd (Advanced)**

```bash
# Requires mavlink-routerd installed separately
mavlink-routerd -e 127.0.0.1:14540 -e 127.0.0.1:14569 -e 127.0.0.1:14550 /dev/ttyUSB0:921600
```

### MAVSDK & MAVLink2REST

Both are automatically installed during `init_pixeagle.sh` (Steps 8-9). Manual download:

```bash
bash src/tools/download_mavsdk_server.sh
bash src/tools/download_mavlink2rest.sh
```

---

## Network Requirements

Ensure these ports are accessible (firewall allowed) for full functionality:

| Port | Service | Required |
|------|---------|----------|
| 3000 | Dashboard | Yes |
| 5077 | Backend API | Yes |
| 5551 | WebSocket (video) | Yes |
| 8088 | MAVLink2REST API | For OSD/telemetry |
| 14540 | MAVSDK | For PX4 |
| 14569 | MAVLink2REST input | For PX4 |
| 14550 | QGC | Optional |
| 22 | SSH | For remote access |

**Ubuntu/Raspbian firewall**:
```bash
sudo ufw allow 3000/tcp && sudo ufw allow 5077/tcp && sudo ufw allow 5551/tcp && sudo ufw allow 8088/tcp
```

---

## Running Options

```bash
# Full system (recommended)
bash run_pixeagle.sh

# Development mode with hot-reload
bash run_pixeagle.sh --dev

# Force rebuild
bash run_pixeagle.sh --rebuild

# Individual components
bash run_pixeagle.sh -d  # Skip dashboard
bash run_pixeagle.sh -p  # Skip Python app
bash run_pixeagle.sh -m  # Skip MAVLink2REST
```

### Tmux Controls

- Switch panes: `Ctrl+B`, then arrow keys
- Detach: `Ctrl+B`, then `D`
- Reattach: `tmux attach -t PixEagle`

---

## Service Management

Auto-start on boot (Raspberry Pi/Linux):

```bash
sudo bash install_service.sh

# Commands
pixeagle-service start|stop|status|restart
sudo pixeagle-service enable|disable
pixeagle-service logs -f
```

---

## Key Bindings

| Key | Action |
|-----|--------|
| `t` | Select ROI (Classic Tracker) |
| `c` | Cancel Tracking |
| `y` | Trigger YOLO Detection |
| `f` | Start Following |
| `d` | Redetect Lost Object |
| `s` | Toggle Smart Tracker Mode |
| `q` | Quit |

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Documentation Index](docs/README.md) | All documentation |
| [SmartTracker Guide](docs/SMART_TRACKER_GUIDE.md) | AI tracking setup |
| [OSD Guide](docs/OSD_GUIDE.md) | On-screen display |
| [Windows SITL](docs/WINDOWS_SITL_XPLANE.md) | X-Plane simulation |
| [Schema Guide](docs/Tracker_and_Follower_Schema_Developer_Guide.md) | Developer architecture |

---

## Windows (SITL Only)

PixEagle supports Windows for X-Plane SITL testing. See [Windows SITL Guide](docs/WINDOWS_SITL_XPLANE.md).

```bash
# Run components manually
python src/main.py
cd dashboard && npm install && npm start
```

---

## Resources

- [GitHub Repository](https://github.com/alireza787b/PixEagle)
- [YouTube Playlist](https://www.youtube.com/watch?v=nMThQLC7nBg&list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)
- [PX4Xplane Plugin](https://github.com/alireza787b/px4xplane)

---

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

Report issues at [GitHub Issues](https://github.com/alireza787b/PixEagle/issues).

---

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

**Commercial use**: Allowed with attribution. You must include the copyright notice and license in any distribution.

---

## Disclaimer

PixEagle is experimental software. Use at your own risk. The developers are not responsible for any misuse or damages.

---

**Star this repo** if you find it useful!
