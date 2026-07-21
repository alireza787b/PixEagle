# PixEagle

**Open-source computer vision, object tracking, and target-following software for PX4 drones and UAV companion computers.**

[![Tests](https://github.com/alireza787b/PixEagle/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/alireza787b/PixEagle/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/alireza787b/PixEagle?include_prereleases&sort=semver)](https://github.com/alireza787b/PixEagle/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![PX4](https://img.shields.io/badge/PX4-MAVSDK-005CAF.svg)](https://px4.io/)
[![Platform](https://img.shields.io/badge/Linux-x86__64%20%7C%20ARM64-3DA639.svg)](docs/INSTALLATION.md)

PixEagle turns camera input into tracked targets, follower command intents,
operator telemetry, and optional PX4 Offboard control. It combines OpenCV,
YOLO object detection, MAVSDK, MAVLink, FastAPI, and a responsive React
dashboard in a modular pipeline that developers can extend with new video
sources, trackers, detectors, followers, gimbals, and integrations.

**[Quick start](#quick-start)** | **[Documentation](docs/README.md)** | **[Videos](#watch-pixeagle)** | **[Changelog](CHANGELOG.md)** | **[Get help](https://github.com/alireza787b/PixEagle/issues)**

## Watch PixEagle

[![PixEagle video demo](https://img.youtube.com/vi/vJn27WEXQJw/maxresdefault.jpg)](https://www.youtube.com/watch?v=vJn27WEXQJw)

[PixEagle videos and demos](https://www.youtube.com/playlist?list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky) | [PX4 and MAVLink routing tutorial](https://www.youtube.com/watch?v=_QEWpoy6HSo)

A PixEagle v7 walkthrough is coming soon. The current README and versioned
documentation remain authoritative for installation and safety decisions.

## Quick Start

On a Debian-family Linux host with at least 4 GB RAM and 2 GB free disk space,
install the current PixEagle product with:

```bash
curl -fsSL https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh | bash
```

In an interactive terminal, choose **Core** for the complete runtime without
local AI packages or **Full AI** to add PyTorch and Ultralytics. If the command
is piped through an interactive SSH shell, the bootstrap explicitly forwards
that terminal to every guided setup prompt. Automation without a controlling
terminal safely selects Core and prints the environment override for Full AI.
Pressing Enter at every guided choice selects Core, installs only the
current-user `pixeagle` directory shortcut and standalone service controls,
while leaving dlib, the long OpenCV/GStreamer source build, boot auto-start,
and SSH login hints disabled. The final dashboard selector lists the usable
device addresses and their interfaces: press Enter for the primary route,
enter `l` for local-only access, or enter `c` for a custom address. The
network path keeps the beginner `admin/admin` login when Enter is pressed and
starts the bundled-video dashboard. A public IP receives one concise HTTP-lab
warning and a link to the HTTPS deployment guide. The installer finishes with
the exact browser URL and a component readiness summary. Full AI validates the selected CPU, CUDA, or target-board profile from
the checked-in compatibility policy. If no reviewed AI profile can use the
selected interpreter, guided setup offers Core without installing unsupported
AI packages.

Rerunning the same command on a clean existing checkout performs an
**update + repair**, not a reset. It verifies actual component state, reuses a
lockfile-matched dashboard dependency tree, and preserves local config,
credentials, models, recordings, logs, and evidence. If SSH or power is lost,
reconnect and run `cd ~/PixEagle && make setup-status` before retrying. A
verified active operation may continue cleanup after the terminal disappears;
wait for it to finish. Do not delete lock files or start several installers
concurrently. See [Interrupted Setup](docs/TROUBLESHOOTING.md#ssh-disconnected-during-setup).

For configured camera and PX4 operation, review the matching setup guide and
then run:

```bash
cd ~/PixEagle && make run
```

For a first local verification with the bundled video and no drone, run:

```bash
cd ~/PixEagle && make demo
```

Open `http://127.0.0.1:3040` and select a target in the video.

If you accepted the optional `pixeagle` helper, it changes to the installed
project directory only. Run `pixeagle help` to see the explicit commands; use
`make demo` or `make run` for a manual runtime, and
`pixeagle-service start` only after the standalone service has been installed.
`pixeagle-service enable` controls boot auto-start and does not start a process
immediately.

This local verification runs classic tracking and the **Follower Test**. It calculates
and displays command intents, but it has no PX4/MAVSDK command publisher and
keeps the circuit breaker active. It is a software check, not a simulator or
flight-readiness result.

For a browser on another trusted device, a Raspberry Pi or Jetson companion
computer, AI/YOLO setup, or a live PX4 connection, use the matching guide in
[Start Here](#start-here) instead of modifying ports or config files ad hoc.

## What PixEagle Does

| Area | Included capabilities |
|------|-----------------------|
| **Vision input** | Video files, USB and CSI cameras, RTSP, HTTP, UDP, and custom GStreamer pipelines |
| **Tracking** | OpenCV CSRT and KCF, optional dlib, AI-assisted SmartTracker, and external gimbal tracking |
| **Detection** | Local YOLO detect/OBB models with explicit artifact registration and runtime checks |
| **Following** | Multicopter, fixed-wing, and gimbal follower profiles behind shared readiness and safety boundaries |
| **Drone interface** | PX4 telemetry and optional Offboard control through MAVSDK, MAVLink, and MAVLink2REST |
| **Operator tools** | Live video, OSD, tracker/follower status, configuration, accounts, diagnostics, and unified logs in the web dashboard |
| **Streaming** | Browser MJPEG/WebSocket delivery plus optional GStreamer H.264/RTP/UDP output for field receivers |
| **Developer surface** | Versioned typed REST APIs, schema-driven configuration, plugin-oriented factories, tests, and API inventory artifacts |

The maintained data path is deliberately explicit:

```text
camera or stream
  -> frame preprocessing
  -> detector / tracker
  -> normalized target state
  -> follower command intent
  -> readiness and safety gates
  -> local test recorder OR reviewed PX4 / gimbal publisher
```

Only the explicit live path can reach PX4. Recorded-video replay remains
separate from autonomous Following.

## Start Here

| I want to... | Start with... |
|--------------|---------------|
| try tracking and follower calculations without a drone | [Quick Start](#quick-start) and [Local Follower Test](docs/drone-interface/06-development/follower-command-preview.md) |
| install manually or understand Core versus Full | [Installation Guide](docs/INSTALLATION.md) |
| open the dashboard from another trusted device | [Setup Profiles](docs/setup/setup-profiles.md) |
| compare aerial, maritime, aircraft, and small-object detectors | [Detection Model Catalog](docs/MODEL_CATALOG.md) |
| add a YOLO model or validate SmartTracker | [Model Setup](docs/MODEL_SETUP.md) |
| connect telemetry and PX4 Offboard control | [PX4 and MAVLink Connectivity](docs/drone-interface/04-infrastructure/port-configuration.md), [Drone Interface](docs/drone-interface/README.md), and [Safety System](docs/followers/06-safety/README.md) |
| use QGroundControl or another video receiver | [Video and Streaming](docs/video/README.md) |
| deploy on Raspberry Pi, Jetson, or another companion computer | [Exact-Commit Installation](docs/INSTALLATION.md#productionraspberry-pi-exact-commit-bootstrap) and [Service Management](docs/SERVICE_MANAGEMENT.md) |
| build a tracker, detector, follower, or integration | [Tracker Development](docs/trackers/05-development/README.md), [Follower Development](docs/followers/05-development/README.md), and [Core App](docs/core-app/README.md) |
| work with the typed API or future agent integrations | [API Guide](docs/core-app/03-api/README.md) and [Agent Context Boundary](docs/agent-context/README.md) |
| diagnose a problem | [Troubleshooting](docs/TROUBLESHOOTING.md) and the dashboard Logs page |

## Installation Profiles

- **Core** is the default. It provides the dashboard, classic OpenCV tracking,
  configuration, and the maintained PX4/MAVLink integration surface without
  installing AI packages.
- **Full** adds the guarded PyTorch and Ultralytics dependency path. A trusted,
  registered model is still a separate step. Python support belongs to each
  checked-in hardware profile; the current Linux CPU profile supports CPython
  3.10-3.14 except 3.14.1. Setup validates the exact profile before changing AI
  packages and can fall back from an incompatible accelerator profile to the
  reviewed CPU profile in automatic mode.
- **Optional capabilities** such as dlib, a GStreamer-enabled OpenCV build,
  QGroundControl profiles, firewall changes, and systemd service/auto-start are
  always explicit. Guided setup asks a separate yes/no question for dlib,
  GStreamer, the reversible current-user `pixeagle` directory shortcut,
  standalone service controls, boot auto-start, and SSH login hints. Enter
  accepts the displayed default; it never selects dlib, GStreamer, auto-start,
  or login hints. Setup reports the follow-up command for every skipped
  capability.

The installer ends with a **component readiness summary** so skipped, degraded,
or manual follow-up work is visible before launch. macOS and native Windows are not maintained guided-bootstrap targets;
use WSL or a supported Debian-family Linux host for the normal path.

The checked-in runtime default remains local-only and creates no dashboard
account. The one-line installer's final prompt and `make quick-browser-demo`
are the explicit beginner exceptions: they ask for dashboard credentials,
pressing Enter keeps `admin/admin`, and they expose only dashboard `3040` plus
the authenticated API/media port `5077`. Commercial and production deployments
must use the documented generated-credential and HTTPS proxy workflow.

The one-line installer tracks mutable `main` and is intended for evaluation and
development. Raspberry Pi acceptance, production deployments, and reproducible
testing must use a reviewed 40-character commit as described in the
[Installation Guide](docs/INSTALLATION.md).

## Everyday Commands

Run these from the repository directory:

| Command | Purpose |
|---------|---------|
| `make demo` | Start the included-video local follower test; no PX4 commands |
| `make run` | Start the configured runtime; review live-source and PX4 settings first |
| `make stop` | Stop the manual runtime owned by this checkout |
| `make repair` | Verify and repair the current source without a Git update or data reset |
| `make update` | Reconcile a stopped, clean checkout using the maintained update path |
| `make clean` | Remove generated dashboard/build caches; preserve dependencies and operator data |
| `make help` | List setup, validation, streaming, and service commands |

Configuration is schema-driven. Most settings are available in the dashboard;
the checked-in source of truth is `configs/config_default.yaml`, while an
optional local `configs/config.yaml` override is ignored by Git. See
[Configuration](docs/CONFIGURATION.md) and [Config Sync](docs/CONFIG_SYNC.md)
before changing deployment settings.

## Dashboard And Remote Access

The dashboard and backend bind to loopback by default. Do not open backend port
`5077` directly or copy a public-demo configuration into production.

`API_ALLOWED_HOSTS` names the PixEagle URL authority, not the client IP; it is not a GCS source-IP allowlist.
Put selected client restrictions in the firewall, VPN, or reverse-proxy source
policy.

- For a short trusted-LAN browser test, use the guarded
  [`quick-browser-demo`](docs/setup/setup-profiles.md#demo_lan_browser) workflow.
- **Lab/private-overlay browser demo:** a private address does not by itself
  make the setup production-ready. TLS is not domain-only; IP and private-name
  deployments still need a reviewed trust, authentication, and proxy design.
- For remote operations, use an SSH tunnel, private overlay, or the
  [production reverse-proxy runbook](docs/setup/production-remote-reverse-proxy.md).
- For raw QGC/media receivers, choose the documented field-video or guarded
  direct-media profile in [Setup Profiles](docs/setup/setup-profiles.md).

Authentication, TLS, firewall scope, video transport, and PX4 command safety
are separate controls. Enabling one does not imply the others are ready.

## Documentation

| System | Guide |
|--------|-------|
| Installation and setup | [Installation](docs/INSTALLATION.md) |
| Full documentation map | [Documentation Index](docs/README.md) |
| Trackers and computer vision | [Tracker System](docs/trackers/README.md) |
| Detection model selection | [Model Catalog](docs/MODEL_CATALOG.md) |
| Followers and guidance | [Follower System](docs/followers/README.md) |
| Cameras, video, OSD, and streaming | [Video System](docs/video/README.md) |
| PX4, MAVSDK, MAVLink, and simulation | [Drone Interface](docs/drone-interface/README.md) |
| API, dashboard backend, and configuration | [Core App](docs/core-app/README.md) |
| Verified MAVSDK/MAVLink2REST assets | [Binary Download Policy](docs/setup/binary-download-policy.md) |
| Known limitations | [Known Issues](docs/KNOWN_ISSUES.md) |

Optional ecosystem tools remain separate projects:

- [MAVLink Anywhere](https://github.com/alireza787b/mavlink-anywhere) for
  companion-computer MAVLink routing over serial, UDP, Wi-Fi, LTE, or VPN.
  PixEagle does not install it automatically; use the
  [PX4 connectivity guide](docs/drone-interface/04-infrastructure/port-configuration.md)
  after setup when connecting a vehicle.
- [Smart Wi-Fi Manager](https://github.com/alireza787b/smart-wifi-manager) for
  managed Linux field-network profiles

Neither is required for the local demo.

## For Developers

PixEagle is organized around explicit component contracts and factories rather
than a single hard-coded tracker/follower loop. The main extension guides cover
tracker outputs and capabilities, follower command intents, schema-backed
configuration, lifecycle ownership, API contracts, and test expectations.

```text
src/          Python runtime and component contracts
dashboard/    React operator interface
configs/      checked-in defaults and generated schema
scripts/      setup, runtime, validation, and service tooling
tests/        unit, integration, API, setup, and simulation contracts
docs/         architecture, operator, safety, and extension guides
```

Before opening a pull request, run the focused tests for your change and the
repository gates documented in [AGENTS.md](AGENTS.md). Bug reports and focused
feature proposals are welcome in [GitHub Issues](https://github.com/alireza787b/PixEagle/issues).

Maintainers can verify the public setup/update contract from a temporary clean
checkout without starting PX4 or installing services:

```bash
.venv/bin/python tools/run_setup_handoff_walkthrough.py
```

## Project Status And Safety

PixEagle v7 is in prerelease validation. The local demo and automated tests do
not prove PX4 vehicle response, tracker quality on a new camera, Raspberry Pi
performance, GStreamer receiver compatibility, SIH/SITL/HIL behavior, field
safety, or regulatory compliance. Those require separate evidence on the
selected hardware, model, network, autopilot configuration, and operating
environment.

PixEagle is not certified avionics. Real-vehicle use requires qualified
operators, independent safety review, verified failsafes and abort paths,
controlled test progression, and compliance with local law.

## Contact, Contributions, And License

- **Commercial, research, and custom deployment inquiries:**
  [p30planets@gmail.com](mailto:p30planets@gmail.com)
- **Project contact:** [Alireza on LinkedIn](https://www.linkedin.com/in/alireza787b/)
- **Issues and feature requests:** [GitHub Issues](https://github.com/alireza787b/PixEagle/issues)

PixEagle is licensed under the [Apache License 2.0](LICENSE). Commercial use is
allowed under that license; retain the required notices and attribution.
