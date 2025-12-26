# Data Flow Architecture

> Detailed telemetry and command flow documentation.

## Telemetry Flow (Drone → Application)

### Source Selection

PixEagle supports two telemetry sources, selected via `USE_MAVLINK2REST`:

| Source | Protocol | Rate | Use Case |
|--------|----------|------|----------|
| MAVLink2REST | HTTP REST | Configurable (default 2 Hz) | Decoupled, network-transparent |
| MAVSDK | gRPC streams | Event-driven | Low latency, direct connection |

### MAVLink2REST Flow

```
PX4 Autopilot
       │
       │ MAVLink 2.0 (serial/UDP)
       ▼
┌──────────────────┐
│  mavlink-router  │
│  (Port routing)  │
└────────┬─────────┘
         │
         │ UDP :14570 (MAVLink2REST input)
         ▼
┌──────────────────┐
│   MAVLink2REST   │
│  (REST server)   │
│    Port 8088     │
└────────┬─────────┘
         │
         │ HTTP GET /v1/mavlink/...
         ▼
┌──────────────────────────────────────────────────┐
│              MavlinkDataManager                   │
│  ┌──────────────────────────────────────────┐   │
│  │ _poll_data() [Thread]                    │   │
│  │  - Polls at MAVLINK_POLLING_INTERVAL     │   │
│  │  - Fetches /v1/mavlink (all data)        │   │
│  │  - Parses JSON paths from config         │   │
│  │  - Updates self.data dict (lock-protected)│   │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │ Async fetch methods:                     │   │
│  │  - fetch_attitude_data()   → roll,pitch,yaw│  │
│  │  - fetch_altitude_data()   → relative,amsl │  │
│  │  - fetch_ground_speed()    → m/s          │  │
│  │  - fetch_throttle_percent()→ 0-100        │  │
│  └──────────────────────────────────────────┘   │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│             PX4InterfaceManager                   │
│  ┌──────────────────────────────────────────┐   │
│  │ _update_telemetry_via_mavlink2rest()     │   │
│  │  - Called in update_drone_data() loop    │   │
│  │  - Updates instance variables:           │   │
│  │    • current_yaw                         │   │
│  │    • current_pitch                       │   │
│  │    • current_roll                        │   │
│  │    • current_altitude                    │   │
│  │    • current_ground_speed                │   │
│  └──────────────────────────────────────────┘   │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│              TelemetryHandler                     │
│  - Formats tracker + drone telemetry             │
│  - UDP broadcast to configured port              │
│  - Rate-limited by TELEMETRY_SEND_RATE           │
└──────────────────────────────────────────────────┘
```

### MAVSDK Stream Flow

```
PX4 Autopilot
       │
       │ MAVLink 2.0
       ▼
┌──────────────────┐
│  mavlink-router  │
└────────┬─────────┘
         │
         │ UDP :14540
         ▼
┌──────────────────┐
│   MAVSDK Server  │
│  (gRPC :50051)   │
└────────┬─────────┘
         │
         │ gRPC streams
         ▼
┌──────────────────────────────────────────────────┐
│             PX4InterfaceManager                   │
│  ┌──────────────────────────────────────────┐   │
│  │ _update_telemetry_via_mavsdk()           │   │
│  │  - Async for loops on telemetry streams  │   │
│  │  - drone.telemetry.position()            │   │
│  │  - drone.telemetry.attitude_euler()      │   │
│  │  - drone.telemetry.velocity_body()       │   │
│  └──────────────────────────────────────────┘   │
└──────────────────────────────────────────────────┘
```

### REST Endpoints Used

| Endpoint | Data | Usage |
|----------|------|-------|
| `/v1/mavlink` | Full data dump | Polling thread |
| `/v1/mavlink/vehicles/1/components/1/messages/ATTITUDE` | roll, pitch, yaw | Attitude data |
| `/v1/mavlink/vehicles/1/components/1/messages/ALTITUDE` | relative, AMSL | Altitude data |
| `/v1/mavlink/vehicles/1/components/1/messages/LOCAL_POSITION_NED` | vx, vy, vz | Velocity/speed |
| `/v1/mavlink/vehicles/1/components/1/messages/VFR_HUD` | throttle | Throttle percent |
| `/v1/mavlink/vehicles/1/components/191/messages/HEARTBEAT` | base_mode, custom_mode | Armed state, flight mode |

## Command Flow (Application → Drone)

### Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      Follower.follow_target()                     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 1. Get TrackerOutput (position_2d, angular, etc.)          │  │
│  │ 2. Calculate control commands (PID, guidance)              │  │
│  │ 3. Call setpoint_handler.set_field() for each output       │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                        SetpointHandler                            │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ set_field(field_name, value)                               │  │
│  │  1. Validate field exists in current profile               │  │
│  │  2. Convert to float                                       │  │
│  │  3. Clamp to configured limits                             │  │
│  │  4. Store in internal dict                                 │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ get_control_type() → "velocity_body_offboard" | ...        │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                    PX4InterfaceManager                            │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Control Type Dispatch:                                      │  │
│  │                                                             │  │
│  │ if control_type == 'velocity_body_offboard':               │  │
│  │   → send_velocity_body_offboard_commands()                 │  │
│  │                                                             │  │
│  │ elif control_type == 'attitude_rate':                      │  │
│  │   → send_attitude_rate_commands()                          │  │
│  │                                                             │  │
│  │ elif control_type == 'velocity_body':                      │  │
│  │   → send_body_velocity_commands() [deprecated]             │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Circuit Breaker Check                         │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ if FollowerCircuitBreaker.is_active():                     │  │
│  │   → Log command instead of executing                       │  │
│  │   → Return success (for testing)                           │  │
│  │ else:                                                       │  │
│  │   → Proceed to MAVSDK call                                 │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                      MAVSDK Offboard API                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Velocity Body:                                              │  │
│  │   VelocityBodyYawspeed(fwd, right, down, yawspeed_deg_s)   │  │
│  │   await drone.offboard.set_velocity_body(setpoint)         │  │
│  │                                                             │  │
│  │ Attitude Rate:                                              │  │
│  │   AttitudeRate(roll_deg_s, pitch_deg_s, yaw_deg_s, thrust) │  │
│  │   await drone.offboard.set_attitude_rate(setpoint)         │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 │ gRPC
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                      MAVSDK Server                                │
│                       Port 50051                                  │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
                                 │ MAVLink
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                      PX4 Autopilot                                │
│  - Offboard mode required                                        │
│  - Processes SET_POSITION_TARGET_LOCAL_NED                       │
│  - Executes velocity/attitude control loops                      │
└──────────────────────────────────────────────────────────────────┘
```

### Command Field Mapping

| SetpointHandler Field | Unit | MAVSDK Parameter | Control Type |
|----------------------|------|------------------|--------------|
| `vel_body_fwd` | m/s | forward_m_s | velocity_body_offboard |
| `vel_body_right` | m/s | right_m_s | velocity_body_offboard |
| `vel_body_down` | m/s | down_m_s | velocity_body_offboard |
| `yawspeed_deg_s` | deg/s | yawspeed_deg_s | velocity_body_offboard |
| `rollspeed_deg_s` | deg/s | roll_rate_deg_s | attitude_rate |
| `pitchspeed_deg_s` | deg/s | pitch_rate_deg_s | attitude_rate |
| `thrust` | 0.0-1.0 | thrust_value | attitude_rate |

### Safety Limit Application

```
SetpointHandler.set_field('vel_body_fwd', value)
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│            Limit Clamping (from config)             │
│                                                     │
│  MAX_VELOCITY_FORWARD: 8.0   # m/s                 │
│  MAX_VELOCITY_LATERAL: 5.0   # m/s                 │
│  MAX_VELOCITY_VERTICAL: 3.0  # m/s                 │
│  MAX_YAW_RATE: 45.0          # deg/s               │
│                                                     │
│  clamped_value = clip(value, -limit, +limit)       │
└─────────────────────────────────────────────────────┘
```

## Flight Mode Detection

MavlinkDataManager monitors flight mode transitions:

```
┌──────────────────────────────────────────────────────┐
│            _handle_flight_mode_change()              │
│                                                      │
│  old_mode == 393216 (Offboard)                      │
│       AND                                            │
│  new_mode != 393216                                  │
│       │                                              │
│       ▼                                              │
│  Offboard mode exited!                               │
│       │                                              │
│       ▼                                              │
│  Call _offboard_exit_callback()                     │
│       │                                              │
│       ▼                                              │
│  AppController._handle_offboard_mode_exit()         │
│       │                                              │
│       ▼                                              │
│  Disable follow mode automatically                  │
└──────────────────────────────────────────────────────┘
```

## Timing Considerations

| Operation | Rate | Notes |
|-----------|------|-------|
| Telemetry polling | 0.5-2 Hz | Configurable via MAVLINK_POLLING_INTERVAL |
| Command sending | 20 Hz | SETPOINT_PUBLISH_RATE_S = 0.05 |
| Follow target loop | ~20 Hz | Matched to command rate |
| PX4 offboard timeout | 0.5s | Commands must be sent within this window |

## Error Recovery Patterns

### Connection Loss

```
MavlinkDataManager._poll_data()
           │
           ▼
  ┌────────────────────┐
  │ requests.get()     │
  └─────────┬──────────┘
            │
    ┌───────┴───────┐
    │   Exception   │
    └───────┬───────┘
            │
            ▼
   _handle_connection_error()
            │
            ├─ connection_state = "error"
            ├─ Increment error count
            ├─ Log (throttled)
            └─ Retry on next poll cycle
```

### Async Loop Conflict

```
_safe_mavsdk_call(coro_func)
           │
           ▼
  ┌────────────────────┐
  │ await coro_func()  │
  └─────────┬──────────┘
            │
    ┌───────┴───────────────────────┐
    │ "attached to different loop" │
    └───────┬───────────────────────┘
            │
            ▼
    await asyncio.sleep(0.001)
            │
            ▼
  ┌────────────────────────┐
  │ await coro_func() NEW  │  ← Create NEW coroutine
  └────────────────────────┘
```
