# Infrastructure Overview

This section covers the infrastructure required to connect PixEagle to PX4 autopilots.

## Quick Links

| Document | Description |
|----------|-------------|
| [mavlink-router](mavlink-router.md) | MAVLink stream routing and multiplexing |
| [MAVLink2REST Setup](mavlink-anywhere.md) | REST API for telemetry access |
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
│   Accepts: UDP :14550, Serial, Ethernet                                 │
│   Routes to multiple endpoints simultaneously                           │
│                                                                          │
│   ┌─────────────┬─────────────┬─────────────┬─────────────┐            │
│   │  Endpoint 1 │  Endpoint 2 │  Endpoint 3 │  Endpoint 4 │            │
│   │  :14540     │  :14550     │  :14551     │  :8088      │            │
│   │  (MAVSDK)   │  (QGC)      │  (Spare)    │  (m2r)      │            │
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
| mavlink-router | Latest | `apt install mavlink-router` |
| MAVLink2REST | Latest | Docker or cargo |
| MAVSDK-Python | 1.4.0+ | `pip install mavsdk` |

### Network Requirements

| Port | Protocol | Purpose |
|------|----------|---------|
| 14540 | UDP | MAVSDK connection |
| 14550 | UDP | Ground station (QGC) |
| 8088 | HTTP | MAVLink2REST API |

## Quick Start

### 1. SITL Development

```bash
# Terminal 1: Start PX4 SITL
cd PX4-Autopilot
make px4_sitl_default gazebo

# Terminal 2: Start mavlink-router
mavlink-routerd -e 127.0.0.1:14540 -e 127.0.0.1:14550 0.0.0.0:14540

# Terminal 3: Start MAVLink2REST
docker run -p 8088:8088 mavlink2rest

# Terminal 4: Start PixEagle
python main.py
```

### 2. Hardware Connection

```bash
# Start mavlink-router on serial
mavlink-routerd -e 127.0.0.1:14540 -e 127.0.0.1:14550 /dev/ttyUSB0:921600

# Start MAVLink2REST
docker run -p 8088:8088 mavlink2rest

# Start PixEagle
python main.py
```

## Configuration

### PixEagle YAML

```yaml
px4:
  connection_string: "udp://:14540"
  offboard_rate_hz: 20

mavlink2rest:
  enabled: true
  base_url: "http://localhost:8088"
  poll_rate_hz: 20
```

## Troubleshooting Quick Reference

| Symptom | Likely Cause | Solution |
|---------|--------------|----------|
| No telemetry | MAVLink2REST not running | Start MAVLink2REST |
| Commands ignored | Not in offboard mode | Check flight mode |
| Connection refused | Wrong port | Check mavlink-router config |
| Intermittent data | Buffer overflow | Reduce poll rate |

See [Troubleshooting Guide](../07-troubleshooting/) for detailed solutions.
