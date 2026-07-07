# Installation Guide

> Detailed installation instructions for PixEagle

## Quick Installation

### One-Liner (Recommended)

**Linux:**
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
- **macOS** - not a maintained guided-bootstrap target; use Linux/Windows/WSL
  for the documented `install.sh` / `scripts/init.sh` path until a reviewed
  macOS bootstrap exists.
- **Windows** - Windows 10 version 1809+ (x86_64)

## Prerequisites

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip make tmux lsof curl git
```

## Init Script Steps

The `scripts/init.sh` (or `make init`) performs a 9-step setup:

1. **System Requirements** - Validates Python version, disk space
2. **System Packages** - Installs missing dependencies
3. **Python Virtual Environment** - Creates isolated venv
4. **Python Dependencies** - Installs role-based Core/AI requirements
5. **Node.js via nvm** - Installs Node.js for dashboard
6. **Dashboard Dependencies** - Runs npm install
7. **Configuration Defaults** - Uses checked-in runtime defaults and creates
   dashboard `.env` when missing
8. **MAVSDK Server** - Downloads manifest-pinned platform binary with SHA-256 verification
9. **MAVLink2REST** - Downloads manifest-pinned REST API bridge with SHA-256 verification

At the end, init prints a component readiness summary. `ready` means the step
was completed or verified in this run, `skipped` means an optional/operator
choice was intentionally not performed, `degraded` means PixEagle continued but
that component needs attention, and `manual follow-up` means the guide gives the
next command to run before using that capability. Do not treat `make run` as
ready for a workflow until the relevant summary entries are ready.

### OpenCV + GStreamer Safety During Init

If your venv already has a **custom OpenCV build with GStreamer**, `make init` detects it and asks:

`Overwrite custom OpenCV? [y/N]`

- Choosing **N** (default) preserves your custom build and skips pip OpenCV packages.
- Choosing **Y** installs pip OpenCV and replaces the custom GStreamer-enabled build.

### Full Profile AI Install Strategy

When you select **Full** profile, init uses a two-phase Python dependency flow:

1. Install **core** packages first from `requirements-core.txt` (stable base)
2. Offer automated PyTorch setup (`scripts/setup/setup-pytorch.sh --mode auto`)
3. Install and verify **AI** packages from `requirements-ai.txt` (`ultralytics`, `lap`, `ncnn`) and then best-effort `pnnx` for NCNN export

If AI verification fails, init keeps your core install usable and prompts whether to roll back AI packages to Core-safe mode.

Note: NCNN auto-export from uploaded `.pt` models requires `pnnx` in the same venv.

Manual AI recovery commands:

```bash
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh
bash scripts/setup/check-ai-runtime.sh
```

### Virtual Environment Selection

Fresh `make init` creates `venv/`. Development/demo checkouts may already use
`.venv/`. PixEagle setup helpers use one resolver so optional commands do not
silently inspect the wrong Python environment:

1. `PIXEAGLE_VENV_DIR` when explicitly set, for example
   `export PIXEAGLE_VENV_DIR="$PWD/.venv"`
2. `.venv/` when it contains `bin/python`
3. `venv/` when it contains `bin/python`
4. `venv/` as the expected missing path in error messages

`scripts/setup/check-ai-runtime.sh` prints the exact Python path it inspected
and reports PyTorch/YOLO/dlib modules, OpenCV version, OpenCV contrib tracker
APIs, and OpenCV GStreamer support.

## Manual Installation

If you prefer manual setup:

```bash
# Create virtual environment
python3 -m venv venv
export PIXEAGLE_VENV_DIR="$PWD/venv"
source "$PIXEAGLE_VENV_DIR/bin/activate"

# Install core Python dependencies first, matching scripts/init.sh.
# Full AI packages are installed later with the deterministic AI setup scripts.
pip install -r requirements-core.txt

# Optional AI/YOLO support
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/install-ai-deps.sh

# Optional developer/test tooling
pip install -r requirements-dev.txt

# Install Node.js and dashboard
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source ~/.nvm/nvm.sh
nvm install 22
cd dashboard && npm install
cd ..

# Optional: create dashboard env if init was skipped
"$PIXEAGLE_VENV_DIR/bin/python" - <<'PY'
import yaml
from pathlib import Path

source = Path("dashboard/env_default.yaml")
target = Path("dashboard/.env")
config = yaml.safe_load(source.read_text(encoding="utf-8"))
target.write_text(
    "".join(f"{key}={value}\n" for key, value in config.items()),
    encoding="utf-8",
)
PY
```

PixEagle can read checked-in defaults from `configs/config_default.yaml` when
`configs/config.yaml` is absent. Create `configs/config.yaml` only when the host
needs local overrides or an explicit setup profile. See
[Setup Profiles](setup/setup-profiles.md).

For field QGroundControl video on another device, keep the backend local and
apply the QGC video profile:

```bash
make qgc-video-profile GCS_HOST=<ground-station-ip>
```

For guarded direct QGC HTTPS/WSS media with a draft/test compatible QGC build:

```bash
make qgc-direct-media-profile PUBLIC_HOST=<tls-host>
```

This keeps PixEagle loopback, generates a hashed `media:read`-only bearer token
record, and writes an owner-only one-time QGC handoff. It still requires a
separately configured TLS reverse proxy and target receiver validation.

## Setup Choice Matrix

| Choice | Default Path | When To Select | Follow-up |
|--------|--------------|----------------|-----------|
| Core profile | Recommended on ARM/Raspberry Pi | Demo, OpenCV tracking, dashboard, MAVSDK/MAVLink runtime without AI/YOLO | Add AI later with `setup-pytorch.sh` and `install-ai-deps.sh` |
| Full profile | Recommended on x86_64 | AI/YOLO SmartTracker or model tooling | Review PyTorch/AI summary and run `check-ai-runtime.sh` if degraded |
| Custom OpenCV + GStreamer | Optional, never forced | RTSP/GStreamer input or QGC H.264 output needing GStreamer-enabled OpenCV | Build with `scripts/setup/build-opencv.sh`; init asks before overwriting it |
| dlib tracker | Optional manual step | Fast correlation-filter tracker experiments | `bash scripts/setup/install-dlib.sh` |
| Browser quick demo | Explicit admin demo command | Fast phone/tablet/PC demo on isolated LAN or private overlay; temporary public HTTP lab demos require explicit override and are not production remote access | `make quick-browser-demo LAN_HOST=<host>`; use `SESSION_ROLE=operator`/`viewer` to downgrade; cleanup with `CONFIRM=1 make quick-browser-demo-cleanup LAN_HOST=<host>`, which restores local-only config by default; add `CLOSE_FIREWALL=1` only when demo UFW rules were opened |
| Services | Opt-in only | Standalone deployment requiring boot auto-start | `PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init` |
| MAVSDK/MAVLink2REST binaries | Guided by init | PX4/SITL/HIL/field integration | Review final summary and binary provenance before claiming readiness |

Browser-session users are managed offline through:

```bash
python3 scripts/setup/manage-browser-users.py --file <API_SESSION_USER_FILE> list
```

Use it for admin password resets, role changes, disabling old users, or adding
viewer/operator/admin users. It writes owner-only JSON and never stores
plaintext passwords in the runtime user file.

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

`check-ai-runtime.sh` is also the fastest way to answer "what is installed on
this host?" It does not install packages; it reports the active venv, OpenCV
capabilities, dlib status, PyTorch acceleration status, YOLO/Ultralytics
status, NCNN exporter status, and model-file readiness.

### GStreamer Support

```bash
bash scripts/setup/build-opencv.sh
```

For manual build instructions, see [OpenCV GStreamer Guide](OPENCV_GSTREAMER.md).

## Network Requirements

### Required Ports

Keep application ports local by default. PixEagle's checked-in backend policy
binds `127.0.0.1:5077` and fails startup when `local_only` configuration
requests non-loopback exposure. The current backend supports loopback local
compatibility, scoped machine bearer tokens, and explicit browser-session auth
from an external hashed user file. See the
[API exposure boundary](apis/api-exposure-boundary.md) before configuring any
remote operator path.

If upgrading from an older local `configs/config.yaml`, a missing exposure mode
with `HTTP_STREAM_HOST: 0.0.0.0` is coerced to loopback at runtime. For a quick
browser demo on another device, use `make demo-lan-browser-profile
LAN_HOST=<this-pixeagle-lan-ip-or-overlay-ip>` so setup generates credentials
and exact Host/CORS allowlists. Explicitly set `API_EXPOSURE_MODE:
trusted_lan_legacy` by hand only for reviewed temporary isolated-LAN or private
overlay/VPN compatibility.

| Port | Service | Required |
|------|---------|----------|
| 3040 | Dashboard | Loopback by default |
| 5077 | Backend API | Loopback by default |
| 5551 | Legacy telemetry WebSocket | Local/optional |
| 8088 | MAVLink2REST API | Local-only by default |
| 14540 | MAVSDK | Local endpoint for PX4 integration |
| 14569 | MAVLink2REST input | Local endpoint for PX4 integration |
| 14550 | QGC | Optional |
| 22 | SSH | For remote access |

### Separately Secured Remote Operator Path

```bash
# Example only after the guarded HTTPS reverse proxy is configured
sudo ufw allow from <trusted-cidr> to any port 443 proto tcp

# Optional field GCS access only from the trusted GCS device/CIDR
sudo ufw allow from <trusted-gcs-ip-or-cidr> to any port 14550 proto udp
```

For the `demo_lan_browser` profile only, add equivalently scoped TCP rules for
dashboard port `3040` and backend/API media port `5077`, limited to the trusted
demo device or CIDR. Do not add a broad backend rule.

Do not open backend port `5077` directly. `trusted_lan_legacy` only permits a
non-loopback bind/CORS boundary; backend requests still require scoped API
authorization or explicit browser-session auth. The `demo_lan_browser` profile
is the supported beginner exception: it intentionally makes `3040` and `5077`
reachable on the isolated LAN/private overlay so the browser dashboard can load
static assets and call the backend API/media endpoints. HTTP over a private LAN
or private overlay/VPN is acceptable only for that explicit lab/demo posture.
TLS is not domain-only. Production remote-browser setup should use
`make production-remote-profile PUBLIC_HOST=<tls-host>
SESSION_USER_FILE=<path>` or an equivalent reviewed config so PixEagle stays
loopback behind HTTPS/WSS; production handoff still requires proxy/firewall
evidence, credential handoff evidence, adversarial auth/media tests, and safety
evidence gates.
Do not open raw dashboard port `3040` for this profile. Follow the
[production remote reverse-proxy runbook](setup/production-remote-reverse-proxy.md)
and expose only its reviewed TLS listener.

Do not expose PixEagle backend `5077`, MAVLink2REST `8088`, local MAVLink
endpoints `14540`/`14569`, or MavlinkAnywhere dashboard `9070` beyond
localhost or an SSH tunnel unless an explicit network-security plan exists.
A reverse proxy does not make `local_compat` remote-safe; non-loopback backend
API clients need scoped bearer tokens or explicit browser-session auth.

## OpenCV Diagnostic

```bash
python src/test_Ver.py
```

This is a quick OpenCV version/build diagnostic, not a release or vehicle
readiness test.

### Maintainer Clean-Handoff Walkthrough

Before tagging a release or handing setup instructions to testers, run the
clean-checkout walkthrough from a clean worktree:

```bash
python3 tools/run_setup_handoff_walkthrough.py
```

The harness clones PixEagle to a temporary checkout, verifies required public
setup docs/files, runs documented setup profile dry-runs, previews the binary
download plan without downloading, checks the fast-forward-only update path, and
runs the schema plus minimum backend/API tests. It writes an evidence manifest
under `docs/reporting/agent-ops/codex-modernization/evidence/`.

Optional heavier dashboard evidence can be added with:

```bash
python3 tools/run_setup_handoff_walkthrough.py --include-dashboard
```

The dashboard option runs `npm ci` in the temporary checkout and may fetch npm
package artifacts from the configured npm registry. This remains setup/update
evidence only: it does not install services, open firewall rules, download
MAVSDK/MAVLink2REST binaries, start PX4/SITL/HIL, prove QGC playback, or claim
field or real-aircraft readiness.

## Running PixEagle

**Linux (using Makefile):**
```bash
make run           # Run all services
make dev           # Development mode with hot-reload
make stop          # Stop all services
make sync          # Fetch and fast-forward latest updates on a clean worktree
make reset-config  # Reset config files to defaults
make setup-profile # Apply an explicit setup profile
make qgc-video-profile GCS_HOST=<ip>  # Configure QGC field video
make qgc-direct-media-profile PUBLIC_HOST=<tls-host>  # Guarded QGC HTTPS/WSS media
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
bash scripts/setup/download-binaries.sh --all --dry-run
bash scripts/setup/download-binaries.sh --all
bash scripts/setup/download-binaries.sh --mavsdk
bash scripts/setup/download-binaries.sh --mavlink2rest
```

**Windows:**
```cmd
scripts\setup\download-binaries.bat --all --dry-run
scripts\setup\download-binaries.bat --all
```

Binaries are downloaded to the `bin/` directory only after SHA-256 verification
against `scripts/setup/binary-manifest.env`. Successful verified downloads
append provenance to `bin/binary-provenance.jsonl`; keep that file with SITL,
HIL, field, and tester handoff evidence. See the
[Binary Download Policy](setup/binary-download-policy.md) for pinned release
URLs, override variables, manual/offline placement, and unverified-lab limits.

## Service Management

### Standalone Installations

For standalone Linux deployments, normal `make init` skips service setup. Opt
into deployment prompts with:

```bash
PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init
```

Those prompts default to **No** for:
- installing `pixeagle-service` CLI
- enabling boot auto-start
- enabling system-wide SSH login hints
- optional immediate service start and optional reboot validation

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
```

### Platform-Managed Installations (ARK-OS, etc.)

When installed through a platform like ARK-OS, service management is handled by the
platform. `make init` automatically skips standalone service setup in this case.

Use the platform's web UI or:

```bash
systemctl --user start pixeagle
systemctl --user stop pixeagle
systemctl --user status pixeagle
journalctl --user -u pixeagle -f
```

> **Note**: Standalone and platform-managed modes are mutually exclusive.
> PixEagle auto-detects and prevents conflicts between the two.

See [Service Management Runbook](SERVICE_MANAGEMENT.md) for full operational guidance.

## Next Steps

- [Configuration Guide](CONFIGURATION.md)
- [SmartTracker Reference](trackers/02-reference/smart-tracker.md)
- [Windows Setup](WINDOWS_SETUP.md)
- [Main README](../README.md)
