# Drone Interface Documentation

> Comprehensive documentation for PixEagle's drone interface layer, covering MAVLink2REST telemetry, MAVSDK offboard control, and autopilot integration.

## Quick Navigation

| Section | Description |
|---------|-------------|
| [Architecture](01-architecture/README.md) | System design, data flows, and abstraction layers |
| [Components](02-components/) | Detailed component reference (PX4InterfaceManager, MavlinkDataManager, etc.) |
| [Protocols](03-protocols/) | MAVLink, MAVSDK Offboard API, and control types |
| [Infrastructure](04-infrastructure/) | Setup guides for mavlink-router, SITL, hardware connections |
| [Configuration](05-configuration/) | YAML configuration parameters and tuning |
| [Development](06-development/) | Adding control types, custom telemetry, testing |
| [Troubleshooting](07-troubleshooting/) | Common issues and solutions |

## System Overview

PixEagle's drone interface provides a flexible abstraction layer for communicating with PX4-based autopilots. The system supports two telemetry sources and a dedicated application-level Offboard setpoint refresh owner.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          PixEagle Application                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐     ┌──────────────────┐     ┌───────────────────┐   │
│  │  Follower   │────>│  CommandIntent   │────>│ OffboardCommander │   │
│  │  (Control)  │     │  (Atomic Fields) │     │  (Refresh Owner)  │   │
│  └─────────────┘     └──────────────────┘     └─────────┬─────────┘   │
│                                                          ▼             │
│                                                ┌───────────────────┐   │
│                                                │ PX4InterfaceManager│   │
│                                                │ (Command Dispatch) │   │
│                                                └─────────┬─────────┘   │
│                                                          │             │
│                              ┌───────────────────────────┼─────────┐   │
│                              │                           │         │   │
│                              ▼                           ▼         │   │
│                 ┌────────────────────┐     ┌─────────────────────┐ │   │
│                 │ MavlinkDataManager │     │   MAVSDK Offboard   │ │   │
│                 │   (REST Polling)   │     │   (gRPC Commands)   │ │   │
│                 └─────────┬──────────┘     └──────────┬──────────┘ │   │
│                           │                           │            │   │
└───────────────────────────┼───────────────────────────┼────────────┘   │
                            │                           │                │
                            ▼                           ▼                │
                  ┌──────────────────┐       ┌──────────────────┐       │
                  │  MAVLink2REST    │       │  MAVSDK Server   │       │
                  │   (Port 8088)    │       │   (Port 50051)   │       │
                  └────────┬─────────┘       └────────┬─────────┘       │
                           │                          │                  │
                           └──────────┬───────────────┘                  │
                                      │                                  │
                                      ▼                                  │
                            ┌──────────────────┐                         │
                            │  mavlink-router  │                         │
                            │  (Stream Router) │                         │
                            └────────┬─────────┘                         │
                                     │                                   │
                    ┌────────────────┼────────────────┐                  │
                    ▼                ▼                ▼                  │
              ┌──────────┐    ┌──────────┐    ┌──────────────┐          │
              │   SITL   │    │  Serial  │    │   Ethernet   │          │
              │(UDP:14540)│   │(/dev/tty)│    │(192.168.x.x) │          │
              └──────────┘    └──────────┘    └──────────────┘          │
                                     │                                   │
                                     ▼                                   │
                            ┌──────────────────┐                         │
                            │   PX4 Autopilot  │                         │
                            └──────────────────┘                         │
```

## Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **PX4InterfaceManager** | `src/classes/px4_interface_manager.py` | MAVSDK orchestration, command dispatch, telemetry updates |
| **OffboardCommander** | `src/classes/offboard_commander.py` | Fixed-rate application refresh of MAVSDK setters from atomic command intents |
| **MavlinkDataManager** | `src/classes/mavlink_data_manager.py` | MAVLink2REST HTTP polling, data parsing, flight mode detection |
| **SetpointHandler** | `src/classes/setpoint_handler.py` | Schema-driven command validation and field management |
| **SetpointSender** | `src/classes/setpoint_sender.py` | Legacy threaded setpoint monitoring; does not publish MAVSDK commands |
| **TelemetryHandler** | `src/classes/telemetry_handler.py` | Data formatting and UDP broadcast |

## Data Flows

### Telemetry (Drone → Application)

Two sources are available, configurable via `USE_MAVLINK2REST`:

1. **MAVLink2REST** (default): HTTP REST API polling at configurable intervals
2. **MAVSDK Streams**: Direct async telemetry streams via gRPC

```
PX4 → MAVLink → mavlink-router → MAVLink2REST (port 8088)
                              └─→ MAVSDK (port 14540)
       ↓
MavlinkDataManager.fetch_*() OR MAVSDK telemetry streams
       ↓
PX4InterfaceManager state variables
       ↓
TelemetryHandler → UDP broadcast to clients
```

### Commands (Application → Drone)

```
Follower.follow_target(tracker_data)
       ↓
SetpointHandler.set_fields(...) -> CommandIntent
       ↓
AppController submits CommandIntent to OffboardCommander
       ↓
OffboardCommander fixed-rate application refresh
       ↓
PX4InterfaceManager.send_commands_unified()
       ↓
MAVSDK Offboard API (VelocityBodyYawspeed / AttitudeRate)
       ↓
MAVLink → PX4 Autopilot
```

## Control Types

PixEagle supports three control types for offboard drone control:

| Control Type | MAVSDK Class | Fields | Use Case |
|-------------|--------------|--------|----------|
| `velocity_body_offboard` | `VelocityBodyYawspeed` | vel_body_fwd, vel_body_right, vel_body_down, yawspeed_deg_s | Multicopter velocity control (preferred) |
| `attitude_rate` | `AttitudeRate` | rollspeed_deg_s, pitchspeed_deg_s, yawspeed_deg_s, thrust | Fixed-wing, aggressive MC control |

## Quick Start

### Basic Configuration

```yaml
# configs/config_default.yaml

PX4:
  EXTERNAL_MAVSDK_SERVER: true       # Use external gRPC server
  SYSTEM_ADDRESS: udp://127.0.0.1:14540
  MAVSDK_CONNECTION_TIMEOUT_S: 15.0

MAVLink:
  MAVLINK_ENABLED: true
  MAVLINK_HOST: 127.0.0.1
  MAVLINK_PORT: 8088
  MAVLINK_POLLING_INTERVAL: 0.5      # seconds

Follower:
  USE_MAVLINK2REST: true             # Use REST for telemetry
  FOLLOWER_MODE: mc_velocity_position

Setpoint:
  SETPOINT_PUBLISH_RATE_S: 0.1       # monitor loop period in seconds
```

### Usage Example

```python
from classes.offboard_commander import OffboardCommander
from classes.px4_interface_manager import PX4InterfaceManager

# Initialize
px4 = PX4InterfaceManager(app_controller=None)

# Connect to drone
await px4.connect()

# Start offboard mode
await px4.start_offboard_mode()

# Normal runtime: followers create CommandIntent snapshots and
# OffboardCommander publishes them at OFFBOARD_COMMAND_RATE_HZ.
commander = OffboardCommander(px4, px4.setpoint_handler)
await commander.start()

# Stop and disconnect
await commander.stop()
await px4.stop()
```

## Configuration Files

| File | Purpose |
|------|---------|
| `configs/config_default.yaml` | Main configuration (PX4, MAVLink sections) |
| `configs/follower_commands.yaml` | Command field schema definitions |
| `configs/config_schema.yaml` | Configuration validation schema |

## Source Files

| File | Lines | Description |
|------|-------|-------------|
| `src/classes/px4_interface_manager.py` | ~756 | MAVSDK command dispatch, telemetry |
| `src/classes/mavlink_data_manager.py` | ~435 | REST polling, data parsing |
| `src/classes/setpoint_handler.py` | ~300 | Schema-driven field management |
| `src/classes/setpoint_sender.py` | ~150 | Threaded setpoint monitoring |
| `src/classes/telemetry_handler.py` | ~200 | Data formatting, UDP broadcast |

## Key Features

### Safety Integration

- **Circuit Breaker**: Test mode blocks all drone commands while allowing telemetry
- **Velocity Clamping**: Commands clamped to safety limits before sending
- **Altitude Monitoring**: RTL triggered on altitude violations
- **Offboard Exit Detection**: Auto-disable follow mode on mode changes

### Thread Safety

- MavlinkDataManager uses threading locks for data access
- Async loop conflict resolution for MAVSDK calls
- Thread-safe setpoint monitoring

### Error Handling

- Connection loss detection with auto-retry
- Throttled error logging to prevent spam
- Graceful degradation on telemetry failures

## Future Extensibility

The architecture provides abstraction points for future autopilot support (e.g., ArduPilot):

- **SetpointHandler** is autopilot-agnostic
- **Control types** are defined in YAML schema
- **PX4InterfaceManager** methods could be abstracted to an interface

## Related Documentation

- [Follower System](../followers/README.md) - Target tracking algorithms
- [Tracker System](../trackers/README.md) - Object detection and tracking
- [Video System](../video/README.md) - Video input and streaming
- [Main README](../README.md) - Project overview
