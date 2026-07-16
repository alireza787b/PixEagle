# PixEagle

> Vision-based autonomous tracking system for drones and ground vehicles

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Platform](https://img.shields.io/badge/Platform-Debian--family%20Linux%20%7C%20ARM64-blue)](https://github.com/alireza787b/PixEagle)
[![PX4](https://img.shields.io/badge/Autopilot-PX4-orange)](https://px4.io/)

**PixEagle** is a modular image-processing and tracking suite for drones running PX4 autopilot. It combines MAVSDK Python, OpenCV, and YOLO object detection to deliver high-performance visual tracking and autonomous following.

**[Full Documentation](docs/README.md)** | **[Changelog](CHANGELOG.md)** | **[YouTube Demo](https://www.youtube.com/watch?v=vJn27WEXQJw)**

---

## Features

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **Tracker System** | 5 tracker types: CSRT, KCF, YOLO, SmartTracker, Gimbal | [Tracker Docs](docs/trackers/README.md) |
| **Follower System** | Active velocity, position, attitude, and gimbal pursuit modes | [Follower Docs](docs/followers/README.md) |
| **Video & Streaming** | 7 input sources, GStreamer, MJPEG/WebSocket streaming | [Video Docs](docs/video/README.md) |
| **Professional OSD** | Aviation-grade on-screen display with layered real-time pipeline and TrueType fonts | [OSD Guide](docs/OSD_GUIDE.md) |
| **Drone Interface** | PX4 integration via MAVSDK & MAVLink2REST | [Drone Docs](docs/drone-interface/README.md) |
| **Core App** | REST API, WebSocket, schema-driven configuration | [Core Docs](docs/core-app/README.md) |
| **GPU Acceleration** | Optional, platform-verified PyTorch profiles with explicit CPU fallback policy | [Installation](docs/INSTALLATION.md) |
| **Web Dashboard** | Real-time monitoring, model management, config UI | - |

---

## Documentation

| System | Description | Guide |
|--------|-------------|-------|
| **Trackers** | CSRT, KCF, YOLO, SmartTracker, Gimbal tracking | [docs/trackers/](docs/trackers/README.md) |
| **Followers** | Active velocity, position, attitude, and gimbal pursuit modes | [docs/followers/](docs/followers/README.md) |
| **Video** | 7 input sources, GStreamer, OSD, streaming | [docs/video/](docs/video/README.md) |
| **Drone Interface** | PX4, MAVLink, MAVSDK setup & troubleshooting | [docs/drone-interface/](docs/drone-interface/README.md) |
| **Core App** | REST API, WebSocket, configuration system | [docs/core-app/](docs/core-app/README.md) |
| **Development** | Schema architecture, custom components | [docs/developers/](docs/developers/) |

**Quick Links**: [Installation](docs/INSTALLATION.md) | [Model Setup](docs/MODEL_SETUP.md) | [Setup Profiles](docs/setup/setup-profiles.md) | [Binary Download Policy](docs/setup/binary-download-policy.md) | [Configuration](docs/CONFIGURATION.md) | [Troubleshooting](docs/TROUBLESHOOTING.md)

---

## Demo

[![PixEagle Demo](https://img.youtube.com/vi/vJn27WEXQJw/maxresdefault.jpg)](https://www.youtube.com/watch?v=vJn27WEXQJw)

**[Full YouTube Playlist](https://www.youtube.com/watch?v=nMThQLC7nBg&list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)**

---

## Quick Start

### Prerequisites

- Debian-family Linux on x86_64 or ARM64 (Ubuntu, Raspberry Pi OS, Jetson Linux)
- Python 3.9+
- 4GB+ RAM
- 2GB free for Core; 8GB free for Full AI setup

### One-Liner Installation

**Linux:**
```bash
curl -fsSL https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh | bash
```

### Manual Installation

**Linux:**
```bash
# Install system dependencies
sudo apt update && sudo apt install -y python3 python3-venv python3-pip make tmux lsof curl git

# Clone and initialize
git clone https://github.com/alireza787b/PixEagle.git
cd PixEagle
make init
```

The init script runs a 9-step automated setup including Python venv, Node.js,
dashboard, and manifest-pinned MAVSDK/MAVLink2REST binaries with SHA-256
verification and local provenance logging.
The final init screen is a component readiness summary: `ready`, `skipped`,
`degraded`, and `manual follow-up` entries mean exactly what they say. Resolve
degraded/manual items and re-run `make init` before treating a host as ready
for the matching workflow.

**Installation Profiles:**
- **Core** - Recommended default for demos, classic tracking, dashboard, and PX4 integration
- **Full** - Core plus guarded PyTorch/Ultralytics dependencies; a trusted local model is a separate step

Pressing Enter selects Core on every architecture. Automation may select a
profile with `PIXEAGLE_INSTALL_PROFILE=core|full`.

> **Other hosts:** macOS and native Windows are not maintained guided-bootstrap targets. Use WSL or a Debian-family Linux host. The retained native Windows scripts are contributor-only experiments gated by `PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1`.

> **AI install behavior in Full profile:** Core is installed first, then the matrix-driven PyTorch and hash-pinned Ultralytics installers preserve the existing OpenCV provider. NCNN/pnnx are opt-in with `install-ai-deps.sh --with-ncnn`. Full dependency setup may finish without a model; SmartTracker becomes ready only after the bounded checker loads a trusted local detect/OBB model on the configured effective device. See [Model Setup](docs/MODEL_SETUP.md).

> **Detailed Guide**: [Installation Documentation](docs/INSTALLATION.md)

### Run

**Linux:**
```bash
make run           # Run all services
make dev           # Development mode with hot-reload
make stop          # Stop all services
make update        # Stopped-runtime source + dependency/config reconciliation
make help          # Show all commands
```

`make update` is the only maintained update path. It requires a stopped runtime
and clean worktree (ignored operator files are preserved), publishes only an
exact fast-forward candidate, and then runs the selected Core/Full reconciler.
If a candidate or guarded rollback would turn an ignored/untracked operator
path into a tracked path, the update refuses before overwriting it. Before a
source change it privately stages the old checked-in defaults. It preserves
unresolved config baselines and never removes local config keys; use the admin
Settings preview/apply flow in [Config Sync](docs/CONFIG_SYNC.md). It never
stops or restarts PixEagle.

Maintainers should prove setup/update handoff from a temporary clean checkout
before tagging or sending instructions to testers:

```bash
python3 tools/run_setup_handoff_walkthrough.py
```

That command records dry-run/check-only evidence for public setup docs, setup
profiles, binary download planning, the stopped-runtime updater preflight,
schema, and minimum backend/API tests. It does not install services, open
firewall rules, download MAVSDK/MAVLink2REST binaries, start PX4/SITL/HIL, or claim field
readiness. The optional `--include-dashboard` lane may fetch npm package
artifacts.

For QGroundControl video on a separate ground-station device, keep the backend
local and apply the field video profile:

```bash
make qgc-video-profile GCS_HOST=<ground-station-ip>
```

For anonymous raw MJPEG/WebSocket video only on an isolated lab network, use
the explicit unsafe media-only profile:

```bash
make unsafe-demo-lan-media-profile LAN_HOST=<this-pixeagle-lan-ip>
```

This opens only `/video_feed` and `/ws/video_feed` without auth. It is not a
remote dashboard/control profile and is not for production.

For guarded direct QGC HTTPS/WSS MJPEG/WebSocket media with a draft/test QGC
build containing PR #13594:

```bash
make qgc-direct-media-profile PUBLIC_HOST=<tls-host>
```

This generates a `media:read`-only bearer credential and keeps port `5077`
loopback behind an external TLS proxy. It does not install the proxy or prove
QGC playback.

### Access Dashboard

- **Local**: http://localhost:3040
- **Fast beginner browser demo**: after `make init`, run
  `make quick-browser-demo LAN_HOST=<this-pixeagle-lan-ip>` on the PixEagle
  host. It applies the browser-session demo profile, writes the generated
  admin password to an owner-only handoff file, handles active UFW when it can
  infer a trusted local CIDR, starts the minimal dashboard/backend demo, and
  prints the URL to open from the browser device. Use
  `SESSION_ROLE=operator` or `SESSION_ROLE=viewer` when the first generated
  demo account should not expose admin diagnostics such as runtime logs. Preview
  cleanup with `DRY_RUN=1 make quick-browser-demo-cleanup LAN_HOST=<host>` and
  finish a demo with `CONFIRM=1 make quick-browser-demo-cleanup LAN_HOST=<host>`;
  cleanup stops the demo, removes generated demo credentials, and restores the
  local-only config profile by default. Add `CLOSE_FIREWALL=1` only when the
  quick demo opened UFW rules that should be removed.
- **Lab/private-overlay browser demo**: run
  `make demo-lan-browser-profile LAN_HOST=<this-pixeagle-lan-ip>` to generate a
  local browser-session user file and exact Host/CORS allowlists before
  starting or restarting with `make run`; then open
  `http://<this-pixeagle-lan-ip>:3040` from the other device and log in with
  the generated username/password. The browser uses dashboard port `3040` and
  backend/API media port `5077`. This HTTP profile is for isolated LAN or
  operator-approved private-overlay testing, not production remote access.
  `LAN_HOST`/`API_ALLOWED_HOSTS` names the PixEagle URL host, not the client IP;
  restrict selected clients with firewall, VPN, or reverse-proxy source rules.
- **Temporary public-IP demo exception**: for a VPS bench demo only, the quick
  script can be run with `ALLOW_PUBLIC_HTTP_DEMO=1 OPEN_FIREWALL=1` and
  `LAN_HOST=<public-ip>`. That path is plain HTTP, sends credentials without
  TLS, and when UFW was opened must be stopped with
  `CONFIRM=1 CLOSE_FIREWALL=1 make quick-browser-demo-cleanup LAN_HOST=<public-ip>`
  after testing.
  Do not use it as a production remote deployment.
- **Production remote operator access**: use an SSH tunnel, or generate the
  PixEagle-side reverse-proxy config with
  `make production-remote-profile PUBLIC_HOST=<tls-host> SESSION_USER_FILE=<path>`.
  That profile keeps the backend loopback and requires HTTPS/WSS proxy,
  firewall, credential handoff, adversarial auth/media tests, and evidence
  before production handoff. Follow the
  [production remote runbook](docs/setup/production-remote-reverse-proxy.md).

The backend is local-only by default and rejects contradictory local-only bind
or CORS configuration. Non-loopback backend API clients require scoped bearer
tokens from an external token file or explicit `API_AUTH_MODE=browser_session`
with an external hashed user file. Do not expose the dashboard/backend to
untrusted LANs, the public internet, or shared field networks. See the
[API exposure boundary](docs/apis/api-exposure-boundary.md).

---

## Project Structure

```
PixEagle/
├── Makefile                 # Primary entry point (make help, make run)
├── install.sh               # Bootstrap installer (Linux)
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

For guided local overrides, use [setup profiles](docs/setup/setup-profiles.md):

```bash
make setup-profile PROFILE=local_dev
make qgc-video-profile GCS_HOST=<ground-station-ip>
make qgc-direct-media-profile PUBLIC_HOST=<tls-host>
```

For manual configuration, create a local override only when needed, then edit it:
```bash
cp configs/config_default.yaml configs/config.yaml
nano configs/config.yaml
```

> **Note**: `config.yaml` is gitignored. Clean clones run from checked-in defaults in `configs/config_default.yaml`; `configs/config.yaml` is for local overrides.

> **Detailed Guide**: [Configuration Documentation](docs/CONFIGURATION.md) | [Config Sync](docs/CONFIG_SYNC.md) | [Config Service](docs/core-app/04-configuration/README.md)

## Binary Downloads

MAVSDK Server and MAVLink2REST setup downloads are pinned in
`scripts/setup/binary-manifest.env`, verified with SHA-256, and logged to
`bin/binary-provenance.jsonl` after verified install or acceptance.

Preview the exact plan without writing files:

```bash
make binary-download-plan
```

See the [Binary Download Policy](docs/setup/binary-download-policy.md) for
override and offline-install rules.

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
| 3040 | Dashboard | Loopback by default |
| 5077 | Backend API | Loopback by default |
| 5551 | Legacy telemetry WebSocket | Local/optional |
| 8088 | MAVLink2REST API | Local-only by default |
| 14540 | MAVSDK | For PX4 |

Do not open backend port `5077` directly without an explicit setup profile. For
quick lab browser access, use `make demo-lan-browser-profile
LAN_HOST=<this-pixeagle-lan-ip>` so setup generates browser-session credentials
and exact Host/CORS allowlists, then restart PixEagle with `make run` and open
`http://<this-pixeagle-lan-ip>:3040` from the browser device. The same profile
can be used on an operator-approved private overlay/VPN address for lab testing;
allow `3040` and `5077` only from the trusted demo device/CIDR.
`API_ALLOWED_HOSTS` is the PixEagle URL/proxy authority check, not the trusted
client list and not a GCS source-IP allowlist; selected client restrictions
belong in firewall, VPN, or reverse proxy source rules.
TLS is not domain-only, but production non-loopback reverse-proxy/VPN browser
operation should use `make production-remote-profile
PUBLIC_HOST=<tls-host> SESSION_USER_FILE=<path>` or an equivalent reviewed
configuration. The profile keeps PixEagle loopback behind HTTPS/WSS; production
handoff still requires proxy/firewall evidence, credential handoff evidence,
adversarial auth/media tests, and the normal safety gates.

Keep PixEagle backend `5077`, MAVLink2REST `8088`, and MAVLink local endpoints
behind localhost or SSH tunnels unless the deployment has an explicit
network-security plan. Do not rely on a reverse proxy to extend
`local_compat`; backend API clients outside the same host need scoped bearer
tokens or explicit browser-session auth.

> **Full Guide**: [Port Configuration](docs/drone-interface/04-infrastructure/port-configuration.md)

---

## Running Options

**Using Makefile (Linux):**
```bash
make run                # Full system (recommended)
make dev                # Development mode with hot-reload
make stop               # Stop all services
make update             # Stopped-runtime source + environment reconciliation
make reset-config       # Reset config files to defaults
make status             # Show this checkout's manual runtime status
make logs               # Attach to this checkout's manual runtime
make help               # Show all commands
```

**Using scripts directly:**
```bash
bash scripts/run.sh          # Full system (recommended)
bash scripts/run.sh --dev    # Development mode with hot-reload
bash scripts/run.sh --rebuild # Force rebuild
bash scripts/run.sh --no-dashboard # Skip dashboard
bash scripts/run.sh -p       # Skip Python app
bash scripts/run.sh -m       # Skip MAVLink2REST
bash scripts/run.sh -k       # Skip MAVSDK Server
bash scripts/stop.sh         # Stop all services
```

**Tmux Controls**: `Ctrl+B` + arrows (switch panes) | `Ctrl+B D` (detach) | `make attach` (manual runtime) or `pixeagle-service attach` (managed runtime)

> **Troubleshooting**: [Troubleshooting Guide](docs/TROUBLESHOOTING.md)

---

## GPU Setup (Optional)

For accelerator-aware PyTorch setup (CUDA/MPS/CPU auto-detection):

```bash
bash scripts/setup/setup-pytorch.sh --mode auto
bash scripts/setup/check-ai-runtime.sh
```

Use `--mode gpu` (strict GPU) or `--mode cpu` (force CPU) when needed.

> **More Info**: [Installation Guide](docs/INSTALLATION.md)

---

## Service Management

PixEagle supports two service management modes:

### Standalone Mode

Production auto-start (Raspberry Pi/Jetson/Linux with systemd):

Normal `make init` skips standalone service setup. Run the commands below only
on an operator-approved Linux deployment host where PixEagle should be managed
by systemd at boot. For guided prompts instead of direct service commands, use:

```bash
PIXEAGLE_ENABLE_SERVICE_SETUP=1 make init
```

```bash
# Install canonical management command
sudo bash scripts/service/install.sh

# Runtime management
pixeagle-service start
pixeagle-service stop
pixeagle-service status
pixeagle-service attach

# Boot auto-start
sudo pixeagle-service enable
sudo pixeagle-service disable

# Logs
pixeagle-service logs -f

# Optional SSH login hint (interactive SSH sessions only)
pixeagle-service login-hint enable
pixeagle-service login-hint disable

# System-wide SSH login hint (all users on the board)
sudo pixeagle-service login-hint enable --system
sudo pixeagle-service login-hint disable --system
```

System login hint now shows:
- PixEagle ASCII banner
- service and boot state
- per-interface dashboard/backend URLs
- repo metadata (branch, commit, date, origin)
- quick operations commands

If hint format still looks old after updating code, regenerate it:

```bash
sudo pixeagle-service login-hint disable --system
sudo pixeagle-service login-hint enable --system
```

The internal tmux session is named `pixeagle` on an owner-, mode-, and
checkout-specific socket. Attach through `make attach` for a manual runtime or
`pixeagle-service attach` for a managed runtime; bare `tmux attach` targets the
wrong ownership namespace.

The deployment prompts cover:
- auto-start enablement
- system-wide SSH login hint
- optional immediate start and optional reboot validation

### Platform-Managed Mode (ARK-OS, etc.)

When installed through a platform like [ARK-OS](https://github.com/ARK-Electronics/ARK-OS),
the platform manages the service lifecycle:

- Runs as a **user-level** systemd service managed by the platform
- `make init` automatically **skips** standalone service setup (no conflict)
- Use the platform's web UI or `systemctl --user {start|stop|status} pixeagle`
- Dashboard accessible at `http://<host>/pixeagle/` through the platform's nginx

> **Note**: Standalone and platform-managed modes are mutually exclusive.
> PixEagle auto-detects the active mode and prevents conflicts.

> **More Info**: [Service Management Runbook](docs/SERVICE_MANAGEMENT.md) | [Installation Guide](docs/INSTALLATION.md)

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

## Native Windows Status

Native Windows launchers are retained for contributor experiments but do not
have dependency, lifecycle, media, or release-gate parity with Linux. They fail
closed unless `PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS=1` is explicitly set. Use
WSL or Debian-family Linux for normal setup. See the
[Windows status note](docs/WINDOWS_SETUP.md).

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
