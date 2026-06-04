# Infrastructure Overview

This section covers the infrastructure required to connect PixEagle to PX4 autopilots.

## Quick Links

| Document | Description |
|----------|-------------|
| [MavlinkAnywhere](mavlink-anywhere.md) | Recommended mavlink-router installer, configuration, dashboard, and update flow |
| [mavlink-router](mavlink-router.md) | Manual routing reference for advanced operators |
| [SITL Setup](sitl-setup.md) | PX4 Software-In-The-Loop simulation |
| [Hardware Connection](hardware-connection.md) | Physical drone connections |
| [Companion Computer](companion-computer.md) | Raspberry Pi, Jetson setup |
| [Port Configuration](port-configuration.md) | Network ports reference |

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Physical/Simulated Drone                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                         PX4 Autopilot                            │   │
│  │                                                                   │   │
│  │   SITL Mode:          │    Hardware Mode:                        │   │
│  │   - lockstep/standalone    - Pixhawk 4/6                        │   │
│  │   - UDP :14540              - Serial /dev/ttyUSB0               │   │
│  │                              - Ethernet 192.168.x.x              │   │
│  └──────────────────────────────┬────────────────────────────────────┘   │
└─────────────────────────────────┼────────────────────────────────────────┘
                                  │ MAVLink
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          mavlink-router                                  │
│                                                                          │
│   Managed by MavlinkAnywhere / mavlink-router                            │
│   Routes MAVLink to local services and optional GCS clients              │
│                                                                          │
│   ┌─────────────┬─────────────┬─────────────┬─────────────┐            │
│   │  Endpoint 1 │  Endpoint 2 │  Endpoint 3 │  Endpoint 4 │            │
│   │  :14540     │  :14569     │  :12550     │  :14550     │            │
│   │  (MAVSDK)   │  (m2r in)   │  (local)    │  (QGC)      │            │
│   └──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┘            │
└──────────┼─────────────┼─────────────┼─────────────┼─────────────────────┘
           │             │             │             │
           ▼             ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐
    │  MAVSDK  │  │   QGC    │  │  Spare   │  │ MAVLink2REST│
    │ Commands │  │ Monitor  │  │          │  │  Telemetry  │
    └────┬─────┘  └──────────┘  └──────────┘  └──────┬──────┘
         │                                           │
         └───────────────────┬───────────────────────┘
                             │
                             ▼
                  ┌────────────────────┐
                  │  PX4InterfaceManager │
                  │                      │
                  │  Commands ← MAVSDK   │
                  │  Telemetry ← REST    │
                  └────────────────────┘
```

## Component Summary

### mavlink-router

**Purpose**: Routes MAVLink streams to multiple consumers

**Why needed**:
- Only one application can listen on a serial/UDP port
- Multiple applications need MAVLink access (PixEagle, QGC, logging)
- Provides message filtering and buffering

**Alternatives**: mavproxy (heavier), direct connection (single consumer only)

### MAVLink2REST

**Purpose**: Provides HTTP REST API for MAVLink data

**Why needed**:
- Simple HTTP polling vs complex MAVLink parsing
- Language-agnostic access to telemetry
- No async complexity for telemetry reads
- More reliable than MAVSDK streams for high-frequency data

**PixEagle usage**: Primary telemetry source (attitude, altitude, ground speed)

### MAVSDK

**Purpose**: High-level SDK for MAVLink commands

**Why needed**:
- Type-safe command construction
- Automatic message formatting
- Offboard mode management
- Built-in error handling

**PixEagle usage**: Commands only (velocity, attitude rate)

## Connection Modes

### SITL (Development)

```
PX4 SITL ──UDP──► mavlink-router ──► MAVSDK, MAVLink2REST
```

Simplest setup for development and testing. No hardware required.

### USB Serial (Testing)

```
Pixhawk ──USB──► /dev/ttyUSB0 ──► mavlink-router ──► ...
```

Direct connection for bench testing.

### Ethernet (Production)

```
Companion ──Ethernet──► Flight Controller ──► mavlink-router ──► ...
```

Reliable, high-bandwidth connection for production deployments.

### Radio Telemetry (Long Range)

```
Drone ──Radio──► Ground Station ──UDP──► mavlink-router ──► ...
```

For long-range operations with telemetry radios.

## Prerequisites

### Software Requirements

| Component | Version | Installation |
|-----------|---------|--------------|
| PX4 | v1.14+ | [PX4 Docs](https://docs.px4.io/) |
| MavlinkAnywhere | Current | `install_mavlink_router.sh` + `configure_mavlink_router.sh` |
| MAVLink2REST | Current PixEagle binary | `make init` or `download-binaries` |
| MAVSDK-Python | 1.4.0+ | `pip install mavsdk` |

### Network Requirements

| Port | Protocol | Purpose |
|------|----------|---------|
| 14540 | UDP | MAVSDK connection |
| 14569 | UDP | MAVLink2REST input |
| 14550 | UDP | Ground station (QGC) |
| 8088 | HTTP | MAVLink2REST API |

## Quick Start

### 1. SITL Development

```bash
# Validate the checked-in plan without side effects
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run

# Start a pinned official PX4 SITL container on an operator-approved host
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-px4-sitl"
docker pull px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01
bash scripts/sitl/start_px4_sitl.sh \
  --image px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01 \
  --model sihsim_quadx \
  --artifact-dir "reports/sitl/manual/$RUN_ID"

# Configure routing
cd ~/mavlink-anywhere
sudo ./configure_mavlink_router.sh --headless \
  --input-type udp \
  --input-address 0.0.0.0 \
  --input-port 14550 \
  --endpoints "127.0.0.1:14540,127.0.0.1:14569,127.0.0.1:12550" \
  --install-dashboard \
  --dashboard-listen 127.0.0.1:9070

# Start MAVLink2REST
bash scripts/components/mavlink2rest.sh "udpin:127.0.0.1:14569" "127.0.0.1:8088"

# Start PixEagle, then collect evidence from the running stack
bash scripts/run.sh --no-dashboard --no-attach
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --probe-only \
  --artifact-root reports/sitl
```

See [SITL Setup](sitl-setup.md) for the artifact contract and acceptance rules.

### 2. Hardware Connection

Hardware connection and flight-control testing require explicit operator
approval, a documented safety plan, current config snapshots, abort procedures,
and post-run evidence artifacts. Do not use these commands as proof of flight
readiness from SITL alone.

```bash
# Configure routing on serial
cd ~/mavlink-anywhere
sudo ./configure_mavlink_router.sh --headless \
  --uart /dev/ttyUSB0 \
  --baud 921600 \
  --endpoints "127.0.0.1:14540,127.0.0.1:14569,127.0.0.1:12550"

# Start MAVLink2REST
bash scripts/components/mavlink2rest.sh

# Start PixEagle
make run
```

## Configuration

### PixEagle YAML

```yaml
PX4:
  SYSTEM_ADDRESS: udp://127.0.0.1:14540

MAVLink:
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088

Follower:
  USE_MAVLINK2REST: true
```

## Troubleshooting Quick Reference

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| No telemetry | MAVLink2REST not running | Start MAVLink2REST |
| Commands ignored | Not in offboard mode | Check flight mode |
| Connection refused | Wrong port | Check mavlink-router config |
| Intermittent data | Buffer overflow | Reduce poll rate |

See [Troubleshooting Guide](../07-troubleshooting/) for detailed solutions.
