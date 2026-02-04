# PixEagle

> Vision-based autonomous tracking system for drones and ground vehicles

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20Raspberry%20Pi%20%7C%20Jetson-blue)](https://github.com/alireza787b/PixEagle)
[![PX4](https://img.shields.io/badge/Autopilot-PX4-orange)](https://px4.io/)

**PixEagle** is a modular image-processing and tracking suite for drones running PX4 autopilot. It combines MAVSDK Python, OpenCV, and YOLO object detection to deliver high-performance visual tracking and autonomous following.

**[Full Documentation](docs/README.md)** | **[Changelog](CHANGELOG.md)** | **[YouTube Demo](https://www.youtube.com/watch?v=vJn27WEXQJw)**

---

## Features

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **Tracker System** | 5 tracker types: CSRT, KCF, YOLO, SmartTracker, Gimbal | [Tracker Docs](docs/trackers/README.md) |
| **Follower System** | 10 control modes: velocity, position, attitude, gimbal pursuit | [Follower Docs](docs/followers/README.md) |
| **Video & Streaming** | 7 input sources, GStreamer, MJPEG/WebSocket streaming | [Video Docs](docs/video/README.md) |
| **Professional OSD** | Aviation-grade on-screen display with TrueType fonts | [OSD Guide](docs/OSD_GUIDE.md) |
| **Drone Interface** | PX4 integration via MAVSDK & MAVLink2REST | [Drone Docs](docs/drone-interface/README.md) |
| **Core App** | REST API, WebSocket, schema-driven configuration | [Core Docs](docs/core-app/README.md) |
| **GPU Acceleration** | CUDA support for 60+ FPS, automatic CPU fallback | [Installation](docs/INSTALLATION.md) |
| **Web Dashboard** | Real-time monitoring, model management, config UI | - |

---

## Documentation

| System | Description | Guide |
|--------|-------------|-------|
| **Trackers** | CSRT, KCF, YOLO, SmartTracker, Gimbal tracking | [docs/trackers/](docs/trackers/README.md) |
| **Followers** | 10 control modes (velocity, position, attitude) | [docs/followers/](docs/followers/README.md) |
| **Video** | 7 input sources, GStreamer, OSD, streaming | [docs/video/](docs/video/README.md) |
| **Drone Interface** | PX4, MAVLink, MAVSDK setup & troubleshooting | [docs/drone-interface/](docs/drone-interface/README.md) |
| **Core App** | REST API, WebSocket, configuration system | [docs/core-app/](docs/core-app/README.md) |
| **Development** | Schema architecture, custom components | [docs/developers/](docs/developers/) |

**Quick Links**: [Installation](docs/INSTALLATION.md) | [Configuration](docs/CONFIGURATION.md) | [Troubleshooting](docs/TROUBLESHOOTING.md)

---

## Demo

[![PixEagle Demo](https://img.youtube.com/vi/vJn27WEXQJw/maxresdefault.jpg)](https://www.youtube.com/watch?v=vJn27WEXQJw)

**[Full YouTube Playlist](https://www.youtube.com/watch?v=nMThQLC7nBg&list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)**

---

## Quick Start

### Prerequisites

- Ubuntu 22.04+ / Raspbian / **Windows 10+**
- Python 3.9+
- 4GB+ RAM

### One-Liner Installation

**Linux/macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh | bash
```

**Windows PowerShell:**
```powershell
irm https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.ps1 | iex
```

### Manual Installation

**Linux:**
```bash
# Install system dependencies
sudo apt update && sudo apt install -y python3 python3-venv python3-pip tmux lsof curl git

# Clone and initialize
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle
make init
```

**Windows:**
```cmd
# Clone and initialize
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle
scripts\init.bat
```

> **Windows Guide**: [Windows Setup Documentation](docs/WINDOWS_SETUP.md)

The init script runs a 9-step automated setup including Python venv, Node.js, dashboard, and MAVSDK/MAVLink2REST binaries.

**Installation Profiles:**
- **Core** - Essential features (recommended for ARM/Raspberry Pi)
- **Full** - All features including AI/YOLO detection

The script auto-detects your platform and recommends the appropriate profile.

> **AI install behavior in Full profile:** Core dependencies are installed first, then AI packages (`ultralytics`, `lap`, `ncnn`) are installed and verified in a final phase.  
> If AI verification fails, init prompts whether to roll back to Core-safe mode and shows exact manual recovery commands.

> **Detailed Guide**: [Installation Documentation](docs/INSTALLATION.md)

### Run

**Linux/macOS:**
```bash
make run           # Run all services
make dev           # Development mode with hot-reload
make stop          # Stop all services
make help          # Show all commands
```

**Windows:**
```cmd
scripts\run.bat            # Run all services
scripts\run.bat --dev      # Development mode
scripts\stop.bat           # Stop all services
```

### Access Dashboard

- **Local**: http://localhost:3000
- **LAN**: http://<your-ip>:3000 (auto-detected)

---

## Project Structure

```
PixEagle/
├── Makefile                 # Primary entry point (make help, make run)
├── install.sh               # Bootstrap installer (Linux/macOS)
├── install.ps1              # Bootstrap installer (Windows)
├── scripts/                 # All scripts organized here
│   ├── init.sh/bat          # Main setup scripts
│   ├── run.sh/bat           # Main launcher scripts
│   ├── stop.sh/bat          # Stop services
│   ├── lib/                 # Shared utilities
│   ├── components/          # Component runners
│   └── setup/               # Setup utilities
├── bin/                     # Downloaded binaries
├── src/                     # Python source code
├── configs/                 # Configuration files
├── dashboard/               # React web dashboard
└── docs/                    # Documentation
```

---

## Configuration

Most settings can be configured via the **Web Dashboard UI** (Settings page).

For manual configuration, edit `configs/config.yaml`:
```bash
nano configs/config.yaml
```

> **Note**: `config.yaml` is gitignored. Default values are in `configs/config_default.yaml`.

> **Detailed Guide**: [Configuration Documentation](docs/CONFIGURATION.md) | [Config Service](docs/core-app/04-configuration/README.md)

---

## PX4 Integration

PixEagle requires MAVLink communication with PX4.

| Component | Purpose | Default Port |
|-----------|---------|--------------|
| MAVSDK | Offboard control & telemetry | UDP 14540 |
| MAVLink2REST | REST API for OSD/telemetry | UDP 14569 |
| QGC | Ground Control Station | UDP 14550 (optional) |

**Setup Options:**
- [mavlink-anywhere](https://github.com/alireza787b/mavlink-anywhere) - Guided setup (Recommended) | [Video Tutorial](https://www.youtube.com/watch?v=_QEWpoy6HSo)
- [Manual mavlink-router](docs/drone-interface/04-infrastructure/mavlink-router.md) - Advanced users

> **Full Guide**: [Drone Interface Documentation](docs/drone-interface/README.md) | [Port Configuration](docs/drone-interface/04-infrastructure/port-configuration.md)

---

## Network Requirements

| Port | Service | Required |
|------|---------|----------|
| 3000 | Dashboard | Yes |
| 5077 | Backend API | Yes |
| 5551 | WebSocket (video) | Yes |
| 8088 | MAVLink2REST API | For OSD |
| 14540 | MAVSDK | For PX4 |

```bash
# Ubuntu/Raspbian firewall
sudo ufw allow 3000/tcp && sudo ufw allow 5077/tcp && sudo ufw allow 5551/tcp && sudo ufw allow 8088/tcp
```

> **Full Guide**: [Port Configuration](docs/drone-interface/04-infrastructure/port-configuration.md)

---

## Running Options

**Using Makefile (Linux/macOS):**
```bash
make run                # Full system (recommended)
make dev                # Development mode with hot-reload
make stop               # Stop all services
make status             # Show service status
make logs               # Attach to tmux session
make help               # Show all commands
```

**Using scripts directly:**
```bash
bash scripts/run.sh          # Full system (recommended)
bash scripts/run.sh --dev    # Development mode with hot-reload
bash scripts/run.sh --rebuild # Force rebuild
bash scripts/run.sh -d       # Skip dashboard
bash scripts/run.sh -p       # Skip Python app
bash scripts/run.sh -m       # Skip MAVLink2REST
bash scripts/stop.sh         # Stop all services
```

**Tmux Controls**: `Ctrl+B` + arrows (switch panes) | `Ctrl+B D` (detach) | `tmux attach -t pixeagle` (reattach)

> **Troubleshooting**: [Troubleshooting Guide](docs/TROUBLESHOOTING.md)

---

## GPU Setup (Optional)

For CUDA-accelerated YOLO inference:

```bash
# Example for CUDA 12.4
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu124
```

> **More Info**: [PyTorch Installation](https://pytorch.org/get-started/locally/) | [Installation Guide](docs/INSTALLATION.md)

---

## Service Management

Auto-start on boot (Raspberry Pi/Linux):

```bash
sudo bash scripts/service/install.sh
pixeagle-service start|stop|status|restart
sudo pixeagle-service enable|disable
pixeagle-service logs -f
```

> **More Info**: [Installation Guide](docs/INSTALLATION.md)

---

## Key Bindings

| Key | Action |
|-----|--------|
| `t` | Select ROI (Classic Tracker) |
| `c` | Cancel Tracking |
| `y` | Trigger YOLO Detection |
| `f` | Start Following |
| `s` | Toggle Smart Tracker Mode |
| `q` | Quit |

---

## Windows Support

PixEagle provides **full Windows support** with enterprise-grade batch scripts matching the Linux experience:

```cmd
# Initialize (one-time setup)
scripts\init.bat

# Run PixEagle
scripts\run.bat
scripts\run.bat --dev      # Development mode

# Stop services
scripts\stop.bat
```

**Features:**
- Windows Terminal tabs support (similar to tmux)
- Automatic fallback to separate windows
- Full 9-step setup wizard
- All component runners

> **Guide**: [Windows Setup Documentation](docs/WINDOWS_SETUP.md) | [Windows SITL Setup](docs/WINDOWS_SITL_XPLANE.md)

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
