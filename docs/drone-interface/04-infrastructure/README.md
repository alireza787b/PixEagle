# Infrastructure Overview

This section covers the infrastructure required to connect PixEagle to PX4 autopilots.

## Quick Links

| Document | Description |
|----------|-------------|
| [MavlinkAnywhere](mavlink-anywhere.md) | Recommended mavlink-router installer, configuration, dashboard, and update flow |
| [Companion Runtime Contract](../../architecture/companion-runtime-contract.md) | Sidecar ownership, auth, profile, secret, version, and evidence policy |
| [mavlink-router](mavlink-router.md) | Manual routing reference for advanced operators |
| [SITL Setup](sitl-setup.md) | PX4 Software-In-The-Loop simulation |
| [Hardware Connection](hardware-connection.md) | Physical drone connections |
| [Companion Computer](companion-computer.md) | Raspberry Pi, Jetson setup |
| [Port Configuration](port-configuration.md) | Network ports reference |

## Architecture

```text
PX4 hardware / radio / Ethernet / SITL
                  |
                  v
      MavlinkAnywhere or mavlink-router
          |                         |
          v                         v
  127.0.0.1:14540/udp       127.0.0.1:14569/udp
  MAVSDK vehicle link       MAVLink2REST vehicle link
          |                         |
          v                         v
  MAVSDK gRPC :50051/tcp    127.0.0.1:8088/tcp
  client uses 127.0.0.1     PixEagle telemetry polling
```

The physical/SITL input is deployment-specific; PixEagle does not choose it.
The upstream MAVSDK listener is wildcard-bound even though PixEagle connects
through loopback. The
[PX4 and MAVLink connectivity reference](port-configuration.md) is the
canonical port, firewall, and ownership contract.

## Component Summary

### mavlink-router

**Purpose**: Routes MAVLink streams to multiple consumers

**Why needed**:
- One service should own the physical serial or network source
- Multiple applications need MAVLink access (PixEagle, QGC, logging)
- Provides explicit fanout, routing, and optional filtering

**Alternatives**: mavproxy (heavier), direct connection (single consumer only)

### MAVLink2REST

**Purpose**: Provides HTTP REST API for MAVLink data

**Why needed**:
- Provides the maintained HTTP telemetry source used by PixEagle's default
  follower configuration
- Keeps telemetry parsing behind one local service contract

**PixEagle usage**: Primary telemetry source (attitude, altitude, ground speed)

### MAVSDK

**Purpose**: High-level SDK for MAVLink commands

**Why needed**:
- Type-safe command construction
- Automatic message formatting
- Offboard mode management
- Built-in error handling

**PixEagle usage**: Offboard commands and the optional direct MAVSDK telemetry
source when `Follower.USE_MAVLINK2REST` is false

### Companion Ownership

PixEagle's launcher owns the local MAVSDK Server and MAVLink2REST processes it
starts. It does not own MavlinkAnywhere, the physical MAVLink input, router
service lifecycle, router secrets, profile reconciliation, or fleet rollout.
Keep sidecar management APIs local-first and follow the
[Companion Runtime Contract](../../architecture/companion-runtime-contract.md)
before exposing or automating them.

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
| MavlinkAnywhere | Validated deployment pin | `install_mavlink_router.sh` + `configure_mavlink_router.sh`; record exact tag/commit |
| MAVLink2REST | Current PixEagle binary | `make init` or `download-binaries` |
| MAVSDK-Python | Checked-in requirement | Installed by `make init` |

### Network Requirements

Use the canonical
[PX4 and MAVLink connectivity reference](port-configuration.md) for the current
port inventory. In particular, UDP `14550` is mode-dependent: it may be the
router's PX4/SITL input or a QGC listener, but not two listeners on the same
address and port.

## Quick Start

### 1. SITL Development

For the optional admin-only dashboard lifecycle, keep
`Debugging.ENABLE_MANAGED_SIH: false` unless this is an isolated validation host.
Run `make managed-sih-doctor` for a read-only prerequisite report before
enabling lifecycle actions; it never pulls or starts the pinned PX4 image.
The managed-SIH dashboard action uses only the pinned plan image/model, never
pulls an image, and does not manage MavlinkAnywhere or the PixEagle runtime. See
[SITL Setup](sitl-setup.md#optional-dashboard-lifecycle).

```bash
# Validate the checked-in plan without side effects
python3 tools/run_sitl_validation_suite.py \
  --plan-name phase2_follower_validation \
  --dry-run

# Pull the reviewed tag, then start its plan-pinned digest on an approved host
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-px4-sitl"
docker pull px4io/px4-sitl:v1.17.0-alpha1-1551-g381149fb01
bash scripts/sitl/start_px4_sitl.sh \
  --artifact-dir "reports/sitl/manual/$RUN_ID"

# Optional router dashboard installation is a separate configurator mode
cd ~/mavlink-anywhere
sudo ./configure_mavlink_router.sh --install-dashboard \
  --dashboard-listen 127.0.0.1:9070

# Configure routing
sudo ./configure_mavlink_router.sh --headless \
  --input-type udp \
  --input-address 0.0.0.0 \
  --input-port 14550 \
  --endpoints "127.0.0.1:14540,127.0.0.1:14569,127.0.0.1:12550"

# Start PixEagle (its launcher also starts local MAVSDK Server and MAVLink2REST),
# then collect evidence from the running stack
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

# Start PixEagle; its launcher starts the local MAVSDK Server and MAVLink2REST
make run
```

## Configuration

### PixEagle YAML

```yaml
PX4:
  SYSTEM_ADDRESS: udpin://127.0.0.1:14540

MAVLink:
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088

Follower:
  USE_MAVLINK2REST: true
```

## Troubleshooting Quick Reference

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| No telemetry | router feed or local bridge unavailable | Check routing, then restart the PixEagle-owned runtime |
| Commands ignored | Not in offboard mode | Check flight mode |
| Connection refused | Wrong port | Check mavlink-router config |
| Intermittent data | Buffer overflow | Reduce poll rate |

See [Troubleshooting Guide](../07-troubleshooting/) for detailed solutions.
