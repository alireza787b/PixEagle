# Installation Guide

> Detailed installation instructions for PixEagle

## Quick Installation

### One-Liner (Recommended)

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
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle
make init
```

**Windows:**
```cmd
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle
scripts\init.bat
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
- **Windows** - Windows 10 version 1809+ (x86_64)

## Prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip tmux lsof curl git
```

## Init Script Steps

The `scripts/init.sh` (or `make init`) performs a 9-step setup:

1. **System Requirements** - Validates Python version, disk space
2. **System Packages** - Installs missing dependencies
3. **Python Virtual Environment** - Creates isolated venv
4. **Python Dependencies** - Installs from requirements.txt
5. **Node.js via nvm** - Installs Node.js for dashboard
6. **Dashboard Dependencies** - Runs npm install
7. **Configuration Files** - Generates config.yaml and .env
8. **MAVSDK Server** - Downloads platform-specific binary
9. **MAVLink2REST** - Downloads REST API bridge

### OpenCV + GStreamer Safety During Init

If your venv already has a **custom OpenCV build with GStreamer**, `make init` detects it and asks:

`Overwrite custom OpenCV? [y/N]`

- Choosing **N** (default) preserves your custom build and skips pip OpenCV packages.
- Choosing **Y** installs pip OpenCV and replaces the custom GStreamer-enabled build.

### Full Profile AI Install Strategy

When you select **Full** profile, init uses a two-phase Python dependency flow:

1. Install **core** packages first (stable base)
2. Offer automated PyTorch setup (`scripts/setup/setup-pytorch.sh --mode auto`)
3. Install and verify **AI** packages (`ultralytics`, `lap`, `ncnn`, and optional `pnnx` for NCNN export)

If AI verification fails, init keeps your core install usable and prompts whether to roll back AI packages to Core-safe mode.

Note: NCNN auto-export from uploaded `.pt` models requires `pnnx` in the same venv.

Manual AI recovery commands:

```bash
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh
bash scripts/setup/check-ai-runtime.sh
```

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
bash scripts/setup/install-dlib.sh
```

### GPU Support (PyTorch)

Use the deterministic installer:
```bash
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/check-ai-runtime.sh
```

Useful options:
- `--mode auto` - Resolve best profile automatically (recommended)
- `--mode gpu` - Require accelerated backend (fail if unavailable)
- `--mode cpu` - Force CPU-only profile
- `--dry-run` - Preview selected profile without installing

### GStreamer Support

```bash
bash scripts/setup/build-opencv.sh
```

For manual build instructions, see [OpenCV GStreamer Guide](OPENCV_GSTREAMER.md).

## Network Requirements

### Required Ports

Ensure these ports are accessible for full functionality:

| Port | Service | Required |
|------|---------|----------|
| 3040 | Dashboard | Yes |
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
sudo ufw allow 3040/tcp  # Dashboard
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

## Running PixEagle

**Linux/macOS (using Makefile):**
```bash
make run           # Run all services
make dev           # Development mode with hot-reload
make stop          # Stop all services
make sync          # Pull latest updates from upstream
make reset-config  # Reset config files to defaults
make status        # Show service status
make help          # Show all commands
```

**Linux (using scripts directly):**
```bash
bash scripts/run.sh          # Run all services
bash scripts/run.sh --dev    # Development mode
bash scripts/stop.sh         # Stop all services
```

## Windows Installation

For Windows users, PixEagle provides enterprise-grade batch scripts matching the Linux experience.

### Quick Start (Windows)

```cmd
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle
scripts\init.bat
```

### Windows Requirements

| Software | Minimum Version | Download |
|----------|-----------------|----------|
| Windows | 10 version 1809+ | - |
| Python | 3.9+ | [python.org](https://www.python.org/downloads/) |
| Node.js | 14+ LTS | [nodejs.org](https://nodejs.org/en/download) |

### Windows Scripts

| Script | Purpose |
|--------|---------|
| `scripts\init.bat` | 9-step setup wizard |
| `scripts\run.bat` | Launch all services |
| `scripts\run.bat --dev` | Development mode |
| `scripts\stop.bat` | Stop all services |
| `scripts\components\dashboard.bat` | Dashboard only |
| `scripts\components\main.bat` | Python backend only |

### Windows Terminal (Recommended)

Install [Windows Terminal](https://aka.ms/terminal) for a tabbed interface similar to Linux's tmux.

> **Full Guide**: [Windows Setup Documentation](WINDOWS_SETUP.md)

## Downloading Binaries

If you need to download MAVSDK and MAVLink2REST binaries separately:

**Linux:**
```bash
bash scripts/setup/download-binaries.sh --all
bash scripts/setup/download-binaries.sh --mavsdk
bash scripts/setup/download-binaries.sh --mavlink2rest
```

**Windows:**
```cmd
scripts\setup\download-binaries.bat --all
```

Binaries are downloaded to the `bin/` directory.

## Service Management

Production startup on Linux/systemd (Raspberry Pi/Jetson):

`make init` now includes guided prompts for:
- installing `pixeagle-service`
- enabling boot auto-start
- enabling system-wide SSH login hints
- optional immediate service start and optional reboot validation

After enabling SSH login hints in `make init`, open a new SSH session to validate
the startup guide output.

```bash
# Install command wrapper
sudo bash scripts/service/install.sh

# Manage runtime
pixeagle-service start
pixeagle-service stop
pixeagle-service status
pixeagle-service attach

# Manage boot auto-start
sudo pixeagle-service enable
sudo pixeagle-service disable

# Inspect logs
pixeagle-service logs -f

# Optional SSH login summary
pixeagle-service login-hint enable

# System-wide SSH login summary (all users)
sudo pixeagle-service login-hint enable --system

# Reboot validation (recommended after enabling auto-start)
sudo reboot
# after reconnect:
pixeagle-service status
```

What the SSH login hint includes:
- PixEagle ASCII banner
- service status + boot enablement
- dashboard/backend URLs for each detected IPv4 interface
- repo metadata (branch, commit, commit date, origin)

If your login still shows the old short 3-line hint after updating:

```bash
sudo pixeagle-service login-hint disable --system
sudo pixeagle-service login-hint enable --system
```

tmux session name: `pixeagle`

See [Service Management Runbook](SERVICE_MANAGEMENT.md) for full operational guidance.

## Next Steps

- [Configuration Guide](CONFIGURATION.md)
- [SmartTracker Reference](trackers/02-reference/smart-tracker.md)
- [Windows Setup](WINDOWS_SETUP.md)
- [Main README](../README.md)
