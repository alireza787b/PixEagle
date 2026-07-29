# PixEagle: Computer Vision Tracking for PX4 Drones

**Open-source visual tracking, AI object detection, and target-following
software for PX4 drones and UAV companion computers.**

[![Tests](https://github.com/alireza787b/PixEagle/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/alireza787b/PixEagle/actions/workflows/tests.yml)
[![Release](https://img.shields.io/github/v/release/alireza787b/PixEagle?sort=semver)](https://github.com/alireza787b/PixEagle/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Linux](https://img.shields.io/badge/Linux-x86__64%20%7C%20ARM64-3DA639.svg)](docs/INSTALLATION.md)
[![Windows](https://img.shields.io/badge/Windows%2011-Core%20preview-6B7280.svg)](docs/WINDOWS_SETUP.md)

PixEagle connects camera input to target state, follower command intent,
operator telemetry, and guarded PX4 integration. Its modular Python and React
stack combines OpenCV, YOLO, MAVSDK, MAVLink, FastAPI, and browser video
streaming for education, research, companion-computer prototyping, and custom
UAV vision projects.

**[Watch](#watch-pixeagle)** | **[Quick start](#quick-start)** |
**[Explore capabilities](#what-pixeagle-provides)** |
**[Read the docs](docs/README.md)** | **[Collaborate](#collaborate)**

## Watch PixEagle

[![PixEagle computer vision drone tracking demo](https://img.youtube.com/vi/vJn27WEXQJw/maxresdefault.jpg)](https://www.youtube.com/watch?v=vJn27WEXQJw)

[Watch the PixEagle playlist](https://www.youtube.com/playlist?list=PLVZvZdBQdm_4oain9--ClKioiZrq64-Ky)
or see the
[PX4 and MAVLink routing tutorial](https://www.youtube.com/watch?v=_QEWpoy6HSo).
A new PixEagle v7 walkthrough is planned; the repository documentation remains
the source of truth for current setup and safety behavior.

## Quick Start

### Linux

**Maintained guided-bootstrap architectures:** Debian-family Linux on x86_64
or ARM64. The one-line path follows the current `main` branch and is intended
for evaluation, education, and development.

```bash
curl -fsSL https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.sh | bash
```

For the shortest first run:

1. Press Enter for the recommended Core profile and displayed optional defaults.
2. At dashboard access, enter `l` for this computer only, or press Enter for
   the displayed network address.
3. Press Enter at the login prompts to use `admin/admin`.
4. Open the URL printed by setup, sign in, and select a target. Fresh installs
   use the bundled video; updates preserve the configured source.

Re-running the installer updates and repairs in place. It preserves an existing
dashboard account and service/boot policy instead of repeating those setup
prompts or silently changing them.

The included-video lab calculates follower command intents but cannot publish
PX4 commands. Network access is for temporary trusted lab networks; choose
`l` on an untrusted host. `admin/admin` is a beginner lab default, not a
deployment credential. Use the
[Production Remote Runbook](docs/setup/production-remote-reverse-proxy.md)
before public or operational exposure.

Need Full AI, CUDA/Jetson, Raspberry Pi, GStreamer, services, repair, or secure
remote access? Continue with the
[Installation Guide](docs/INSTALLATION.md) and
[Setup Profiles](docs/setup/setup-profiles.md).

### Windows 11

**Experimental Core local preview:** bundled video, classic tracking,
authenticated loopback dashboard, and no PX4 commands. AI, cameras, services,
remote access, and PX4/SITL are outside this preview.
It is not a maintained deployment platform.

Install Git for Windows, CPython 3.11 or 3.12 x64, and Node.js 24 first. See the
[Windows Preview Guide](docs/WINDOWS_SETUP.md#prerequisites) for exact
requirements, then open PowerShell:

```powershell
$env:PIXEAGLE_ENABLE_EXPERIMENTAL_WINDOWS = "1"
irm https://raw.githubusercontent.com/alireza787b/PixEagle/main/install.ps1 | iex
cd "$HOME\PixEagle"
.\scripts\run.bat
```

Press Enter during first setup to keep `admin/admin`, then open
`http://127.0.0.1:3040`. Stop the preview with:

```powershell
.\scripts\stop.bat
```

Status, restart, media verification, repair behavior, and current limitations
are documented in the [Windows Preview Guide](docs/WINDOWS_SETUP.md).

## What PixEagle Provides

| Area | Current software surface |
|------|--------------------------|
| **Video input** | Files, USB/CSI cameras, RTSP, HTTP, UDP, and custom GStreamer pipelines |
| **Tracking** | OpenCV CSRT/KCF, optional dlib, AI-assisted SmartTracker, and external gimbal tracking |
| **AI detection** | Registered local YOLO detect/OBB models with runtime and accelerator checks |
| **Guidance** | Multicopter, fixed-wing, and gimbal follower profiles that produce typed command intents |
| **PX4 integration** | Telemetry and guarded Offboard publication paths through MAVSDK, MAVLink, and MAVLink2REST |
| **Operator console** | Live video, OSD, tracking/following state, settings, users, models, diagnostics, and logs |
| **Streaming** | Browser HTTP JPEG, WebSocket JPEG, and WebRTC, plus optional H.264/RTP/UDP GStreamer output |
| **Engineering** | Schema-driven configuration, typed REST APIs, component factories, and automated contract tests |

Hardware, network, model, and flight behavior still require validation on the
exact target system. A listed integration surface is not a claim that every
device or operating condition has been qualified.

## How It Works

```text
camera or stream
  -> frame preprocessing
  -> detector / tracker
  -> normalized target state
  -> follower command intent
  -> readiness and safety gates
  -> local command preview OR reviewed PX4 / gimbal publisher
```

Only the configured live path can reach a control publisher. Recorded-video
replay and the beginner lab remain separate command-preview workflows.

## Documentation

| Goal | Start here |
|------|------------|
| Install, update, or troubleshoot | [Installation](docs/INSTALLATION.md), [Setup Profiles](docs/setup/setup-profiles.md), [Troubleshooting](docs/TROUBLESHOOTING.md) |
| Configure cameras, streaming, and AI | [Video System](docs/video/README.md), [Tracker System](docs/trackers/README.md), [Model Catalog](docs/MODEL_CATALOG.md), [AI Accelerators](docs/AI_ACCELERATOR_SUPPORT.md) |
| Connect PX4 or develop followers | [Drone Interface](docs/drone-interface/README.md), [Follower System](docs/followers/README.md), [Safety](docs/followers/06-safety/README.md), [Command Preview](docs/drone-interface/06-development/follower-command-preview.md) |
| Deploy or secure a system | [Service Management](docs/SERVICE_MANAGEMENT.md), [Production Remote Runbook](docs/setup/production-remote-reverse-proxy.md), [Binary Download Policy](docs/setup/binary-download-policy.md) |
| Extend PixEagle | [Full Documentation](docs/README.md), [Core App and API](docs/core-app/README.md), [Configuration](docs/CONFIGURATION.md), [Architecture](docs/architecture/pixeagle-modernization-blueprint.md), [Agent Guide](AGENTS.md) |

See [Known Issues](docs/KNOWN_ISSUES.md) and the
[Changelog](CHANGELOG.md) before a new integration or deployment.

## Project Status And Safety

The release badge and [release notes](https://github.com/alireza787b/PixEagle/releases)
show the current local/demo software release. CI validates backend, dashboard,
schema, setup, and selected media contracts. These checks do not prove tracker
quality on a new camera, Raspberry Pi or Jetson performance, PX4 vehicle
response, SITL/HIL behavior, field safety, or regulatory compliance.

Reproducible tests, Raspberry Pi acceptance, and production handoffs should use
a reviewed exact commit as described in
[Exact-Commit Installation](docs/INSTALLATION.md#productionraspberry-pi-exact-commit-bootstrap).

PixEagle is not certified avionics. Real-vehicle use requires qualified
operators, independent safety review, verified failsafes and abort paths,
controlled test progression, and compliance with local law. Use is at your own
risk under the warranty and liability terms in the
[Apache License 2.0](LICENSE).

Reports from real cameras, Raspberry Pi or Jetson systems, PX4/Pixhawk,
simulation, and controlled hardware tests are valuable when they include exact
versions, configuration, commands, and sanitized logs.

## Collaborate

PixEagle welcomes focused engineering contributions and collaboration in
computer vision, aerial object detection, tracking, embedded acceleration,
PX4/MAVLink integration, operator interfaces, and reproducible validation.

- **Bug reports and feature proposals:**
  [GitHub Issues](https://github.com/alireza787b/PixEagle/issues)
- **Questions and technical discussion:**
  [GitHub Discussions](https://github.com/alireza787b/PixEagle/discussions)
- **Research, commercial integration, and custom development:**
  [p30planets@gmail.com](mailto:p30planets@gmail.com)
- **Maintainer:** [Alireza on LinkedIn](https://www.linkedin.com/in/alireza787b/)

PixEagle source code is available under the [Apache License 2.0](LICENSE).
Models, datasets, downloaded binaries, and other third-party artifacts may have
separate license terms.
