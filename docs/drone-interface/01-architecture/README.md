# Drone Interface Architecture

> High-level design of PixEagle's drone communication layer.

## Overview

The drone interface architecture provides a layered approach to autopilot communication, separating concerns between telemetry acquisition, command validation, and command dispatch.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            APPLICATION LAYER                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ AppController│  │   Follower   │  │   Tracker    │  │  FastAPI     │    │
│  │              │  │              │  │              │  │  Handler     │    │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘  └──────────────┘    │
│         │                 │                                                  │
├─────────┴─────────────────┴──────────────────────────────────────────────────┤
│                          COMMAND ABSTRACTION LAYER                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        SetpointHandler                               │    │
│  │  • Schema-driven field definitions (follower_commands.yaml)         │    │
│  │  • Type validation and range clamping                               │    │
│  │  • Profile-based field management                                    │    │
│  │  • Control type routing                                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
├────────────────────────────────────┼─────────────────────────────────────────┤
│                          INTERFACE LAYER                                     │
│         ┌──────────────────────────┴──────────────────────────┐             │
│         │                  PX4InterfaceManager                 │             │
│         │  • MAVSDK System management                          │             │
│         │  • Offboard mode control                             │             │
│         │  • Command dispatch (velocity_body, attitude_rate)   │             │
│         │  • Telemetry aggregation                             │             │
│         │  • Circuit breaker integration                       │             │
│         └────────────────────────┬─────────────────────────────┘             │
│                                  │                                           │
│    ┌─────────────────────────────┼─────────────────────────────────────┐    │
│    │                             │                                      │    │
│    ▼                             ▼                                      │    │
│ ┌──────────────────────┐  ┌──────────────────────┐                     │    │
│ │  MavlinkDataManager  │  │    MAVSDK System     │                     │    │
│ │  (Telemetry Input)   │  │  (Command Output)    │                     │    │
│ └──────────┬───────────┘  └──────────┬───────────┘                     │    │
│            │                         │                                  │    │
├────────────┼─────────────────────────┼──────────────────────────────────┤    │
│            │      TRANSPORT LAYER    │                                  │    │
│            ▼                         ▼                                  │    │
│   ┌────────────────┐       ┌────────────────┐                          │    │
│   │  MAVLink2REST  │       │ MAVSDK Server  │                          │    │
│   │  HTTP/REST     │       │    gRPC        │                          │    │
│   │  Port 8088     │       │  Port 50051    │                          │    │
│   └────────┬───────┘       └────────┬───────┘                          │    │
│            │                        │                                   │    │
│            └──────────┬─────────────┘                                   │    │
│                       ▼                                                 │    │
│              ┌────────────────┐                                         │    │
│              │ mavlink-router │                                         │    │
│              └────────┬───────┘                                         │    │
│                       │                                                 │    │
└───────────────────────┼─────────────────────────────────────────────────┘    │
                        ▼                                                       │
               ┌────────────────┐                                              │
               │  PX4 Autopilot │                                              │
               └────────────────┘                                              │
```

## Layer Responsibilities

### Application Layer

Components that consume drone data and generate control commands:

- **AppController**: Orchestrates the main control loop
- **Follower**: Generates control commands from tracker data
- **Tracker**: Provides target position data
- **FastAPI Handler**: REST API for external control

### Command Abstraction Layer

Provides autopilot-agnostic command field management:

- **SetpointHandler**: Schema-driven field definitions
  - Loads profiles from `follower_commands.yaml`
  - Validates field types and ranges
  - Clamps values to safety limits
  - Routes to appropriate control type

### Interface Layer

Manages drone communication:

- **PX4InterfaceManager**: Central orchestrator
  - MAVSDK connection management
  - Offboard mode state machine
  - Command dispatch based on control type
  - Telemetry aggregation from sources

- **MavlinkDataManager**: Telemetry input
  - HTTP polling of MAVLink2REST
  - Data parsing and normalization
  - Flight mode monitoring
  - Connection state tracking

### Transport Layer

Communication protocols:

- **MAVLink2REST**: HTTP REST API for telemetry
- **MAVSDK Server**: gRPC for commands
- **mavlink-router**: MAVLink stream routing

## Design Principles

### 1. Separation of Concerns

Each component has a single responsibility:
- SetpointHandler: Validation
- PX4InterfaceManager: Command dispatch
- MavlinkDataManager: Telemetry collection

### 2. Synchronous Calculation, Asynchronous Execution

```python
# Synchronous: Follower calculates commands
follow_result = follower.follow_target(tracker_output)

# Asynchronous: PX4InterfaceManager sends to drone
await px4_interface.send_velocity_body_offboard_commands()
```

### 3. Schema-Driven Configuration

Control types and fields are defined in YAML, not hardcoded:

```yaml
# follower_commands.yaml
follower_profiles:
  mc_velocity_offboard:
    control_type: "velocity_body_offboard"
    required_fields: [vel_body_fwd, vel_body_right, vel_body_down, yawspeed_deg_s]
```

### 4. Safety-First Design

- Circuit breaker blocks commands in test mode
- All velocities clamped to configured limits
- RTL triggered on safety violations
- Offboard exit detection for mode changes

## Thread Model

```
┌─────────────────────────────────────────────────────────────────┐
│                      Main Async Loop                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ AppController.follow_target()                             │  │
│  │  - Runs at ~20 Hz                                         │  │
│  │  - Calls follower synchronously                           │  │
│  │  - Sends commands asynchronously                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        ▼                                      ▼
┌─────────────────────┐              ┌─────────────────────┐
│ Telemetry Update    │              │ SetpointSender      │
│ Background Task     │              │ Thread              │
│                     │              │                     │
│ - Runs continuously │              │ - Independent thread│
│ - Updates state     │              │ - Validates config  │
│   variables         │              │ - Rate-limited logs │
└─────────────────────┘              └─────────────────────┘
        │
        ▼
┌─────────────────────┐
│ MavlinkDataManager  │
│ Polling Thread      │
│                     │
│ - Separate thread   │
│ - Lock-protected    │
│ - Configurable rate │
└─────────────────────┘
```

## Error Handling Strategy

### Connection Errors

```
Connection attempt
       │
       ▼
  ┌─────────┐
  │ Success?│──Yes──> Update state to "connected"
  └────┬────┘
       │ No
       ▼
  Log error (throttled)
       │
       ▼
  Increment error count
       │
       ▼
  Retry on next poll
```

### Command Errors

```
Command dispatch
       │
       ▼
  ┌──────────────────┐
  │ Circuit breaker  │──Active──> Log instead of execute
  │ check            │
  └────────┬─────────┘
           │ Inactive
           ▼
  ┌──────────────────┐
  │ MAVSDK call      │──Error──> Retry once with delay
  │                  │
  └────────┬─────────┘
           │ Success
           ▼
     Log command sent
```

## Configuration Points

| Parameter | Location | Purpose |
|-----------|----------|---------|
| `SYSTEM_ADDRESS` | PX4 section | MAVSDK connection URI |
| `EXTERNAL_MAVSDK_SERVER` | PX4 section | Use external gRPC server |
| `MAVLINK_HOST/PORT` | MAVLink section | MAVLink2REST endpoint |
| `MAVLINK_POLLING_INTERVAL` | MAVLink section | Telemetry poll rate |
| `USE_MAVLINK2REST` | Follower section | Telemetry source selection |
| `SETPOINT_PUBLISH_RATE_S` | Follower section | Command send rate |

## Related Documentation

- [Data Flow](data-flow.md) - Detailed telemetry and command flows
- [Abstraction Layers](abstraction-layers.md) - Interface patterns
- [Future Autopilot Support](future-autopilot-support.md) - ArduPilot extensibility notes
