# Abstraction Layers

> Interface patterns and component boundaries in the drone interface.

## Overview

The drone interface uses a layered architecture that separates concerns:

1. **Application Layer** - Business logic (followers, trackers)
2. **Command Abstraction Layer** - Autopilot-agnostic field management
3. **Interface Layer** - Protocol-specific communication
4. **Transport Layer** - Physical/network communication

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                                │
│                                                                          │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│   │    Follower     │  │    Tracker      │  │  AppController  │        │
│   │                 │  │                 │  │                 │        │
│   │ • Control logic │  │ • Target data   │  │ • Orchestration │        │
│   │ • PID/guidance  │  │ • Position/vel  │  │ • Mode control  │        │
│   └────────┬────────┘  └─────────────────┘  └────────┬────────┘        │
│            │                                          │                  │
│            │ TrackerOutput                           │ Control flow     │
│            ▼                                          ▼                  │
├─────────────────────────────────────────────────────────────────────────┤
│                    COMMAND ABSTRACTION LAYER                             │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                      SetpointHandler                             │   │
│   │                                                                  │   │
│   │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │   │
│   │  │ Schema Loading   │  │ Field Validation │  │ Value Clamp  │  │   │
│   │  │                  │  │                  │  │              │  │   │
│   │  │ • YAML profiles  │  │ • Type checking  │  │ • Min/max    │  │   │
│   │  │ • Field defs     │  │ • Required flds  │  │ • Safety     │  │   │
│   │  └──────────────────┘  └──────────────────┘  └──────────────┘  │   │
│   │                                                                  │   │
│   │  Control Type: velocity_body_offboard | attitude_rate | ...     │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    │ Validated setpoints                │
│                                    ▼                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                         INTERFACE LAYER                                  │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    PX4InterfaceManager                           │   │
│   │                                                                  │   │
│   │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │   │
│   │  │ Command Dispatch │  │ Telemetry Update │  │ Mode Control │  │   │
│   │  │                  │  │                  │  │              │  │   │
│   │  │ • vel_body_off   │  │ • MAVLink2REST   │  │ • Offboard   │  │   │
│   │  │ • attitude_rate  │  │ • State vars     │  │ • Arm/Disarm │  │   │
│   │  └──────────────────┘  └──────────────────┘  └──────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                         │                    │                           │
│         ┌───────────────┘                    └───────────────┐          │
│         ▼                                                    ▼          │
│   ┌──────────────────┐                        ┌──────────────────┐      │
│   │ MavlinkDataMgr   │                        │  MAVSDK System   │      │
│   │ (Telemetry In)   │                        │ (Commands Out)   │      │
│   └────────┬─────────┘                        └────────┬─────────┘      │
│            │                                           │                 │
├────────────┼───────────────────────────────────────────┼─────────────────┤
│            │           TRANSPORT LAYER                 │                 │
│            ▼                                           ▼                 │
│   ┌──────────────────┐                        ┌──────────────────┐      │
│   │  MAVLink2REST    │                        │  MAVSDK Server   │      │
│   │  HTTP/REST       │                        │  gRPC            │      │
│   │  Port 8088       │                        │  Port 50051      │      │
│   └────────┬─────────┘                        └────────┬─────────┘      │
│            │                                           │                 │
│            └──────────────────┬────────────────────────┘                │
│                               ▼                                          │
│                      ┌──────────────────┐                               │
│                      │  mavlink-router  │                               │
│                      │  (Port routing)  │                               │
│                      └────────┬─────────┘                               │
│                               │                                          │
│                               ▼                                          │
│                      ┌──────────────────┐                               │
│                      │   PX4 Autopilot  │                               │
│                      └──────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────┘
```

## SetpointHandler: The Abstraction Core

SetpointHandler is the key abstraction that decouples followers from autopilot specifics:

### Schema-Driven Design

```yaml
# configs/follower_commands.yaml
follower_profiles:
  mc_velocity_offboard:
    control_type: "velocity_body_offboard"
    display_name: "MC Velocity Offboard"
    required_fields:
      - vel_body_fwd
      - vel_body_right
      - vel_body_down
      - yawspeed_deg_s

  fw_attitude_rate:
    control_type: "attitude_rate"
    display_name: "FW Attitude Rate"
    required_fields:
      - rollspeed_deg_s
      - pitchspeed_deg_s
      - yawspeed_deg_s
      - thrust
```

### Benefits

1. **Autopilot Independence**: Followers don't know about MAVSDK or PX4
2. **Type Safety**: Schema validates field types and ranges
3. **Extensibility**: New control types added via YAML, not code
4. **Consistency**: All followers use the same interface

### Usage Pattern

```python
# Follower (Application Layer)
class MCVelocityChaseFollower(BaseFollower):
    def follow_target(self, tracker_output: TrackerOutput) -> FollowResult:
        # Calculate control commands
        fwd_velocity = self._calculate_forward_velocity(error)
        yaw_rate = self._calculate_yaw_rate(angular_error)

        # Set via abstraction - no MAVSDK knowledge needed
        self.setpoint_handler.set_field('vel_body_fwd', fwd_velocity)
        self.setpoint_handler.set_field('yawspeed_deg_s', yaw_rate)

        return FollowResult(success=True)
```

## PX4InterfaceManager: Protocol Translation

Translates abstract setpoints to protocol-specific commands:

### Control Type Dispatch

```python
# Interface Layer - translates to MAVSDK
async def _dispatch_by_control_type(self):
    control_type = self.setpoint_handler.get_control_type()

    if control_type == 'velocity_body_offboard':
        await self.send_velocity_body_offboard_commands()
    elif control_type == 'attitude_rate':
        await self.send_attitude_rate_commands()
```

### MAVSDK Translation

```python
async def send_velocity_body_offboard_commands(self):
    fields = self.setpoint_handler.get_fields()

    # Translate to MAVSDK types
    setpoint = VelocityBodyYawspeed(
        forward_m_s=fields['vel_body_fwd'],
        right_m_s=fields['vel_body_right'],
        down_m_s=fields['vel_body_down'],
        yawspeed_deg_s=fields['yawspeed_deg_s']
    )

    await self.drone.offboard.set_velocity_body(setpoint)
```

## MavlinkDataManager: Telemetry Abstraction

Provides normalized telemetry data from MAVLink2REST:

### Data Normalization

```python
class MavlinkDataManager:
    """Abstracts MAVLink2REST HTTP polling."""

    async def fetch_attitude_data(self) -> dict:
        """Returns normalized attitude data."""
        # Fetch from REST API
        response = self._get_mavlink_data('ATTITUDE')

        # Normalize to standard format
        return {
            'roll': response['message']['roll'],      # radians
            'pitch': response['message']['pitch'],    # radians
            'yaw': response['message']['yaw']         # radians
        }
```

### Consumer Interface

```python
# PX4InterfaceManager consumes normalized data
async def _update_telemetry_via_mavlink2rest(self):
    attitude = await self.mavlink_data_manager.fetch_attitude_data()

    # Update state variables
    self.current_roll = math.degrees(attitude['roll'])
    self.current_pitch = math.degrees(attitude['pitch'])
    self.current_yaw = math.degrees(attitude['yaw'])
```

## Interface Boundaries

### Clear Contracts

| Boundary | Input | Output | Contract |
|----------|-------|--------|----------|
| Follower → SetpointHandler | Field name + value | Success bool | `set_field(name, value)` |
| SetpointHandler → PX4Interface | Control type + fields | None | `get_fields()`, `get_control_type()` |
| MavlinkDataMgr → PX4Interface | Normalized telemetry | None | `fetch_*_data()` methods |
| PX4Interface → MAVSDK | MAVSDK types | Async result | `set_velocity_body()`, etc. |

### Dependency Direction

```
Application Layer
       │
       │ depends on
       ▼
Command Abstraction Layer (SetpointHandler)
       │
       │ depends on
       ▼
Interface Layer (PX4InterfaceManager)
       │
       │ depends on
       ▼
Transport Layer (MAVSDK, MAVLink2REST)
```

**Key Principle**: Upper layers never depend on lower layer implementations. Followers don't import MAVSDK. SetpointHandler doesn't know about HTTP.

## Testing at Boundaries

Each boundary can be tested in isolation:

```python
# Test Follower with mock SetpointHandler
def test_follower_sets_velocity():
    mock_handler = MockSetpointHandler()
    follower = MCVelocityChaseFollower(setpoint_handler=mock_handler)

    follower.follow_target(tracker_output)

    # Verify abstract interface calls
    assert mock_handler.get_field('vel_body_fwd') == expected_velocity

# Test PX4Interface with mock MAVSDK
async def test_command_dispatch():
    mock_system = MockMAVSDKSystem()
    px4 = PX4InterfaceManager(drone=mock_system)

    px4.setpoint_handler.set_field('vel_body_fwd', 2.0)
    await px4.send_velocity_body_offboard_commands()

    # Verify MAVSDK calls
    cmd = mock_system.offboard.get_last_command()
    assert cmd.params['forward'] == 2.0
```

## Configuration Injection

Configuration flows down through layers:

```
config_default.yaml
       │
       ├─► PX4 section ──────────► PX4InterfaceManager
       │                             • SYSTEM_ADDRESS
       │                             • EXTERNAL_MAVSDK_SERVER
       │
       ├─► MAVLink section ──────► MavlinkDataManager
       │                             • MAVLINK_HOST/PORT
       │                             • POLLING_INTERVAL
       │
       └─► Follower section ─────► SetpointHandler
                                    • FOLLOWER_MODE (profile)
                                    • Control type selection
```

## Related Documentation

- [Data Flow](data-flow.md) - Detailed telemetry and command flows
- [Future Autopilot Support](future-autopilot-support.md) - Extensibility notes
- [SetpointHandler Reference](../02-components/setpoint-handler.md) - Component details
