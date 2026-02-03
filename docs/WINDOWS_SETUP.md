# Windows Setup Guide for PixEagle

This guide provides comprehensive instructions for setting up and running PixEagle on Windows systems.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Detailed Installation](#detailed-installation)
- [Windows Terminal (Recommended)](#windows-terminal-recommended)
- [Running PixEagle](#running-pixeagle)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Scripts Reference](#scripts-reference)

---

## Prerequisites

### Required Software

| Software | Minimum Version | Download Link |
|----------|-----------------|---------------|
| **Windows** | Windows 10 version 1809+ | - |
| **Python** | 3.9+ | [python.org/downloads](https://www.python.org/downloads/) |
| **Node.js** | 14+ (LTS recommended) | [nodejs.org/download](https://nodejs.org/en/download) |

### Optional Software

| Software | Purpose | Download Link |
|----------|---------|---------------|
| **Windows Terminal** | Tabbed interface (like tmux) | [Microsoft Store](https://aka.ms/terminal) |
| **Git** | Version control | [git-scm.com](https://git-scm.com/download/win) |
| **VS Code** | Code editing | [code.visualstudio.com](https://code.visualstudio.com/) |

### Verify Prerequisites

Open Command Prompt or PowerShell and run:

```cmd
python --version
node --version
npm --version
```

Expected output:
```
Python 3.9.x (or higher)
v18.x.x (or higher)
9.x.x (or higher)
```

---

## Quick Start

### One-Liner Installation (PowerShell)

```powershell
irm https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.ps1 | iex
```

### Manual Installation

1. **Open Command Prompt** (or Windows Terminal)

2. **Clone and navigate to PixEagle:**
   ```cmd
   git clone https://github.com/alireza787b/PixEagle.git
   cd PixEagle
   ```

3. **Run the initialization script:**
   ```cmd
   scripts\init.bat
   ```

4. **Start PixEagle:**
   ```cmd
   scripts\run.bat
   ```

5. **Open the dashboard** in your browser:
   - Local: http://localhost:3000
   - Network: http://YOUR_IP:3000

---

## Detailed Installation

### Step 1: Clone or Download PixEagle

Using Git:
```cmd
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle
```

Or download and extract the ZIP from GitHub.

### Step 2: Run the Setup Script

The `scripts\init.bat` script performs a complete 9-step setup:

```cmd
scripts\init.bat
```

**What it does:**
1. Checks system requirements (Python, disk space)
2. Verifies system prerequisites
3. Creates Python virtual environment
4. Installs Python dependencies (~100+ packages)
5. Checks Node.js installation
6. Installs dashboard npm dependencies
7. Generates configuration files
8. Downloads MAVSDK Server (optional)
9. Downloads MAVLink2REST (optional)

### Step 3: Configure PixEagle

Edit the configuration file for your setup:

```cmd
notepad configs\config.yaml
```

Key settings to configure:
- Camera source (SITL, USB camera, RTSP stream)
- Connection settings (UDP ports, serial ports)
- Tracking parameters

### Step 4: Download Binary Dependencies

If you skipped during init, run these manually:

**All binaries:**
```cmd
scripts\setup\download-binaries.bat --all
```

**MAVSDK Server only:**
```cmd
scripts\setup\download-binaries.bat --mavsdk
```

**MAVLink2REST only:**
```cmd
scripts\setup\download-binaries.bat --mavlink2rest
```

Binaries are downloaded to the `bin\` directory.

---

## Windows Terminal (Recommended)

Windows Terminal provides a tabbed interface similar to Linux's `tmux`, making it easy to manage multiple PixEagle services.

### Installation

Install from the [Microsoft Store](https://aka.ms/terminal) or via winget:

```cmd
winget install Microsoft.WindowsTerminal
```

### Benefits

- **Tabbed interface**: All 4 services in one window
- **Easy navigation**: Ctrl+Tab to switch tabs
- **Split panes**: Alt+Shift+D to split
- **Modern appearance**: Professional look and feel

### How PixEagle Uses Windows Terminal

When you run `scripts\run.bat`:
- If Windows Terminal is installed, services open in **tabs**
- If not installed, services open in **separate cmd windows**

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Tab` | Switch between tabs |
| `Ctrl+Shift+T` | New tab |
| `Ctrl+Shift+W` | Close current tab |
| `Alt+Shift+D` | Split pane |
| `Alt+Arrow` | Navigate panes |

---

## Running PixEagle

### Basic Usage

```cmd
scripts\run.bat
```

This starts all 4 components:
- Main Python Application (computer vision)
- Dashboard (React web interface)
- MAVLink2REST (REST API bridge)
- MAVSDK Server (MAVLink communication)

### Development Mode

For hot-reload and enhanced debugging:

```cmd
scripts\run.bat --dev
```

### Stopping Services

```cmd
scripts\stop.bat
```

### Command-Line Options

| Option | Description |
|--------|-------------|
| `--dev`, `-d` | Development mode with hot-reload |
| `--rebuild`, `-r` | Force dashboard rebuild |
| `-m` | Skip MAVLink2REST |
| `-p` | Skip Python application |
| `-k` | Skip MAVSDK Server |
| `--help`, `-h` | Show help message |

### Examples

```cmd
# Normal startup
scripts\run.bat

# Development mode
scripts\run.bat --dev

# Force rebuild and development mode
scripts\run.bat --dev --rebuild

# Skip MAVLink2REST (for testing)
scripts\run.bat -m

# Stop all services
scripts\stop.bat
```

### Running Individual Components

**Dashboard only:**
```cmd
scripts\components\dashboard.bat
scripts\components\dashboard.bat --dev    # Development mode
```

**Python backend only:**
```cmd
scripts\components\main.bat
```

**MAVLink2REST only:**
```cmd
scripts\components\mavlink2rest.bat
```

---

## Configuration

### Main Configuration

Location: `configs\config.yaml`

Key sections:
- **Camera**: Video source configuration
- **Tracker**: Tracking algorithm settings
- **MAVLink**: Connection parameters
- **Streaming**: Port configuration

### Dashboard Configuration

Location: `dashboard\.env`

Generated automatically from `dashboard\env_default.yaml`.

### Regenerating Configs

To reset to defaults:
```cmd
copy configs\config_default.yaml configs\config.yaml
```

---

## Troubleshooting

### Common Issues

#### Python not found

**Error:** `'python' is not recognized as an internal or external command`

**Solution:**
1. Install Python from [python.org](https://www.python.org/downloads/)
2. During installation, check "Add Python to PATH"
3. Restart Command Prompt

#### Node.js not found

**Error:** `'node' is not recognized...`

**Solution:**
1. Install Node.js from [nodejs.org](https://nodejs.org/en/download)
2. Restart Command Prompt

#### Port already in use

**Error:** `Port 3000 is already in use`

**Solution:**
```cmd
# Find process using the port
netstat -ano | findstr :3000

# Kill the process (replace PID with actual number)
taskkill /PID 12345 /F
```

Or run the stop script:
```cmd
scripts\stop.bat
```

#### Colors not displaying

**Issue:** ANSI color codes showing as text

**Solution:**
- Use Windows Terminal (recommended)
- Or ensure Windows 10 version 1809 or later
- Colors are enabled automatically by the scripts

#### npm install fails

**Error:** npm ci or npm install failures

**Solution:**
```cmd
cd dashboard
rmdir /s /q node_modules
del package-lock.json
npm install
```

#### Virtual environment issues

**Error:** venv activation fails

**Solution:**
```cmd
# Remove corrupted venv
rmdir /s /q venv

# Re-run init
scripts\init.bat
```

### Port Reference

| Service | Default Port |
|---------|--------------|
| Dashboard | 3000 |
| Backend API | 5077 |
| MAVLink2REST | 8088 |
| WebSocket | 5551 |

### Checking Service Status

```cmd
# Check if ports are in use
netstat -ano | findstr "3000 5077 8088 5551"
```

### Logs and Debugging

- Each service window shows real-time logs
- Python errors appear in the Main App window
- Dashboard errors appear in the Dashboard window

---

## Scripts Reference

### Main Scripts

| Script | Purpose |
|--------|---------|
| `scripts\init.bat` | Complete 9-step setup wizard |
| `scripts\run.bat` | Launch all services |
| `scripts\run.bat --dev` | Launch in development mode |
| `scripts\stop.bat` | Stop all services |

### Component Scripts

| Script | Purpose |
|--------|---------|
| `scripts\components\main.bat` | Python backend only |
| `scripts\components\dashboard.bat` | Dashboard server only |
| `scripts\components\mavlink2rest.bat` | MAVLink2REST bridge only |

### Setup Scripts

| Script | Purpose |
|--------|---------|
| `scripts\setup\download-binaries.bat` | Download MAVSDK/MAVLink2REST binaries |
| `scripts\lib\common.bat` | Shared functions (colors, logging) |

---

## Comparison: Windows vs Linux

| Feature | Linux | Windows |
|---------|-------|---------|
| Primary entry | `make run` | `scripts\run.bat` |
| Init command | `make init` | `scripts\init.bat` |
| Stop command | `make stop` | `scripts\stop.bat` |
| Terminal multiplexer | tmux | Windows Terminal (tabs) |
| Virtual env activation | `source venv/bin/activate` | `call venv\Scripts\activate.bat` |
| Port checking | `lsof -i :PORT` | `netstat -ano \| findstr :PORT` |
| Kill process | `kill PID` | `taskkill /PID PID /F` |
| Path separator | `/` | `\` |

---

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/alireza787b/PixEagle/issues)
- **Documentation**: Check the `docs/` folder
- **Help command**: `scripts\run.bat --help`

---

## Next Steps

After successful setup:

1. **Configure for your setup** - Edit `configs\config.yaml`
2. **Connect to SITL** - For simulation testing
3. **Connect to real vehicle** - For actual flights
4. **Explore the dashboard** - http://localhost:3000
