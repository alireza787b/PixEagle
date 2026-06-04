# PX4InterfaceManager

> Central orchestrator for MAVSDK command dispatch and telemetry aggregation.

**Source**: `src/classes/px4_interface_manager.py` (~756 lines)

## Overview

PX4InterfaceManager is the main interface between PixEagle and the PX4 autopilot via MAVSDK. It handles:

- MAVSDK System connection management
- Offboard mode control (start/stop)
- Command dispatch (velocity_body, attitude_rate)
- Telemetry aggregation from MAVLink2REST or MAVSDK
- Circuit breaker integration for testing

## Class Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     PX4InterfaceManager                          │
├─────────────────────────────────────────────────────────────────┤
│  State Variables:                                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ current_yaw: float          # degrees                    │    │
│  │ current_pitch: float        # degrees                    │    │
│  │ current_roll: float         # degrees                    │    │
│  │ current_altitude: float     # meters                     │    │
│  │ current_ground_speed: float # m/s                        │    │
│  │ active_mode: bool           # connection active          │    │
│  │ hover_throttle: float       # 0.0-1.0                    │    │
│  │ failsafe_active: bool       # safety triggered           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Components:                                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ drone: mavsdk.System        # MAVSDK connection          │    │
│  │ setpoint_handler: SetpointHandler                        │    │
│  │ mavlink_data_manager: MavlinkDataManager (optional)      │    │
│  │ update_task: asyncio.Task   # telemetry update loop      │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Key Methods:                                                    │
│  • connect()                                                     │
│  • start_offboard_mode() / stop_offboard_mode()                 │
│  • send_velocity_body_offboard_commands()                       │
│  • send_attitude_rate_commands()                                 │
│  • send_commands_unified()                                       │
│  • trigger_return_to_launch()                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Initialization

```python
def __init__(self, app_controller=None):
    """
    Initialize PX4InterfaceManager.

    Determines telemetry source based on USE_MAVLINK2REST parameter.
    Sets up MAVSDK connection (external server or embedded).
    """
```

### Configuration

| Parameter | Source | Description |
|-----------|--------|-------------|
| `USE_MAVLINK2REST` | Parameters | If True, use MAVLink2REST for telemetry |
| `EXTERNAL_MAVSDK_SERVER` | Parameters | If True, connect to external MAVSDK server |
| `SYSTEM_ADDRESS` | Parameters | MAVSDK connection URI (e.g., `udp://:14540`) |
| `FOLLOWER_MODE` | Parameters | Initial follower profile name |

## Connection Management

### connect()

```python
async def connect(self):
    """
    Connect to drone via MAVSDK and start telemetry updates.

    Circuit breaker aware - blocked in testing mode.
    Starts background telemetry update task.
    """
```

**Flow**:
```
connect() called
       │
       ▼
┌──────────────────┐
│ Circuit breaker  │──Active──► Set mock active state, return
│ check            │
└────────┬─────────┘
         │ Inactive
         ▼
   drone.connect(SYSTEM_ADDRESS)
         │
         ▼
   Start update_drone_data() task
         │
         ▼
   active_mode = True
```

### Validation Disconnect State

`PX4InterfaceManager` exposes a validation-only local MAVSDK command-path
disconnect hook for operator-gated SITL scenarios:

```python
await inject_mavsdk_disconnect_for_validation(
    reason="sitl_mavsdk_disconnect",
    source="sitl_validation",
)
```

The hook marks the local command path as `validation_disconnected`, clears
`active_mode`, cancels the telemetry update task, and increments
`disconnect_count`. While that state is active, `send_commands_unified()` and
`_safe_mavsdk_call()` return `False`, and `stop_offboard_mode()` raises
`RuntimeError("MAVSDK disconnected - <reason>")` so cleanup records a visible
failure instead of silently reporting success.

`get_connection_status()` exposes the fields used by `/status` and SITL
evidence: `status`, `connected`, `active_mode`,
`validation_disconnect_active`, `disconnect_reason`, `disconnect_source`,
`disconnect_age_s`, `disconnect_count`, `last_error`, `system_address`, and
`uses_mavlink2rest`.

This hook does not stop PX4, Docker, MavlinkAnywhere, MAVLink2REST, a MAVSDK
server, network interfaces, or MAVLink routes. A successful `connect()` clears
only the validation-local disconnect flag after the normal MAVSDK connect path
runs.

### stop()

```python
async def stop(self):
    """
    Stop all operations and disconnect.

    Cancels telemetry task, stops offboard mode.
    """
```

## Telemetry Updates

### update_drone_data()

Background task that continuously updates telemetry state variables.

```python
async def update_drone_data(self):
    """
    Runs at FOLLOWER_DATA_REFRESH_RATE Hz.
    Selects telemetry source based on USE_MAVLINK2REST.
    """
    while self.active_mode:
        if Parameters.USE_MAVLINK2REST:
            await self._update_telemetry_via_mavlink2rest()
        else:
            await self._update_telemetry_via_mavsdk()
        await asyncio.sleep(1.0 / refresh_rate_hz)
```

`FOLLOWER_DATA_REFRESH_RATE` is a frequency in Hertz. Runtime code validates it
and converts it to a sleep period before each telemetry polling iteration.

### MAVLink2REST Telemetry (Primary)

```python
async def _update_telemetry_via_mavlink2rest(self):
    """
    Fetches telemetry from MAVLink2REST via MavlinkDataManager.

    Updates:
    - current_roll, current_pitch, current_yaw (degrees)
    - current_altitude (meters, relative)
    - current_ground_speed (m/s)
    """
    attitude_data = await self.mavlink_data_manager.fetch_attitude_data()
    self.current_roll = attitude_data.get("roll", 0.0)
    self.current_pitch = attitude_data.get("pitch", 0.0)
    self.current_yaw = attitude_data.get("yaw", 0.0)

    altitude_data = await self.mavlink_data_manager.fetch_altitude_data()
    self.current_altitude = altitude_data.get("altitude_relative", 0.0)

    self.current_ground_speed = await self.mavlink_data_manager.fetch_ground_speed()
```

### MAVSDK Telemetry (Fallback)

```python
async def _update_telemetry_via_mavsdk(self):
    """
    Streams telemetry directly from MAVSDK (gRPC).
    Note: Circuit breaker does NOT block telemetry - only commands.
    """
    async for position in self.drone.telemetry.position():
        self.current_altitude = position.relative_altitude_m
    # ... attitude, velocity streams
```

## Command Dispatch

### Control Type Dispatch

```python
async def send_commands_unified(self):
    """
    Unified dispatcher that selects method based on control_type.

    Returns:
        bool: True if successful
    """
    control_type = self.setpoint_handler.get_control_type()

    if control_type == 'velocity_body':
        await self.send_body_velocity_commands()
    elif control_type == 'attitude_rate':
        await self.send_attitude_rate_commands()
    elif control_type == 'velocity_body_offboard':
        await self.send_velocity_body_offboard_commands()
```

### Velocity Body Offboard (Primary)

```python
async def send_velocity_body_offboard_commands(self):
    """
    Send body-frame velocity commands for multicopter control.

    Fields (from SetpointHandler):
    - vel_body_fwd: forward velocity (m/s)
    - vel_body_right: rightward velocity (m/s)
    - vel_body_down: downward velocity (m/s)
    - yawspeed_deg_s: yaw rate (deg/s)

    Uses MAVSDK VelocityBodyYawspeed.
    """
```

**MAVSDK Call**:
```python
setpoint = VelocityBodyYawspeed(vel_fwd, vel_right, vel_down, yawspeed)
await self.drone.offboard.set_velocity_body(setpoint)
```

### Attitude Rate

```python
async def send_attitude_rate_commands(self):
    """
    Send attitude rate commands for fixed-wing or aggressive control.

    Fields (deg/s - MAVSDK standard):
    - rollspeed_deg_s
    - pitchspeed_deg_s
    - yawspeed_deg_s
    - thrust (0.0-1.0)

    Uses MAVSDK AttitudeRate.
    """
```

**MAVSDK Call**:
```python
setpoint = AttitudeRate(roll_deg_s, pitch_deg_s, yaw_deg_s, thrust)
await self.drone.offboard.set_attitude_rate(setpoint)
```

## Circuit Breaker Integration

All command methods pass through the PX4 command gate before execution:

```python
def _evaluate_px4_command_gate(command_type: str, **params) -> PX4CommandGateDecision:
    if not CIRCUIT_BREAKER_AVAILABLE:
        return PX4CommandGateDecision(
            blocked=True,
            degraded=True,
            reason="circuit_breaker_unavailable",
        )

    if FollowerCircuitBreaker.is_active():
        FollowerCircuitBreaker.log_command_instead_of_execute(...)
        return PX4CommandGateDecision(
            blocked=True,
            degraded=False,
            reason="circuit_breaker_active",
        )

    FollowerCircuitBreaker.log_command_allowed(...)
    return PX4CommandGateDecision(blocked=False, degraded=False, reason="allowed")
```

`FOLLOWER_ALLOW_COMMANDS_WITHOUT_SAFETY_MODULES` is the only bypass for
unavailable or failing safety-gate infrastructure. Keep it `false` outside a
controlled bench/SITL procedure with operator approval.

## Safe MAVSDK Calls

```python
async def _safe_mavsdk_call(self, coro_func, *args, **kwargs):
    """
    Execute MAVSDK call with error handling.

    Handles async loop conflicts with retry logic.
    """
    try:
        await coro_func(*args, **kwargs)
        return True
    except Exception as e:
        if "attached to a different loop" in str(e):
            await asyncio.sleep(0.001)
            await coro_func(*args, **kwargs)  # Retry
        return False
```

## Offboard Mode Control

### start_offboard_mode()

```python
async def start_offboard_mode(self):
    """
    Start offboard mode on PX4.

    Prerequisites:
    - Drone must be armed
    - Initial setpoint must be sent before starting

    Returns:
        dict: {"steps": [...], "errors": [...]}
    """
```

### stop_offboard_mode()

```python
async def stop_offboard_mode(self):
    """
    Stop offboard mode.

    PX4 will transition to previous mode (typically Position or Hold).
    """
```

## Safety Actions

### trigger_return_to_launch()

```python
async def trigger_return_to_launch(self):
    """
    Emergency RTL action via MAVSDK.

    Circuit breaker aware - logged instead of executed when testing.
    """
    await self.drone.action.return_to_launch()
```

### trigger_failsafe()

```python
async def trigger_failsafe(self):
    """
    Initiate RTL due to safety violation (altitude, etc.).
    """
    await self.trigger_return_to_launch()
```

## Flight Mode Reference

```python
FLIGHT_MODES = {
    458752: 'Stabilized',
    196608: 'Position',
    100925440: 'Land',
    393216: 'Offboard',
    50593792: 'Hold',
    84148224: 'Return',
    131072: 'Altitude',
    65536: 'Manual',
    327680: 'Acro',
    33816576: 'Takeoff',
    67371008: 'Mission',
    151257088: 'Precision Land'
}
```

## Utility Methods

### get_orientation()

```python
def get_orientation(self):
    """Returns (yaw, pitch, roll) in degrees."""
    return self.current_yaw, self.current_pitch, self.current_roll
```

### get_flight_mode_text()

```python
def get_flight_mode_text(self, mode_code):
    """Convert mode code to human-readable text."""
    return self.FLIGHT_MODES.get(mode_code, f"Unknown ({mode_code})")
```

### validate_setpoint_compatibility()

```python
def validate_setpoint_compatibility(self) -> bool:
    """
    Validate current profile has required fields for control type.
    """
```

## Error Handling

- Connection errors logged and active_mode set appropriately
- Command errors logged with specific error types (OffboardError, ValueError)
- Async loop conflicts handled with retry mechanism
- Circuit breaker provides fail-safe when testing

## Configuration Example

```yaml
PX4:
  EXTERNAL_MAVSDK_SERVER: true
  SYSTEM_ADDRESS: "udp://127.0.0.1:14540"

Follower:
  USE_MAVLINK2REST: true  # Use REST for telemetry
  FOLLOWER_MODE: "mc_velocity_position"
```

## Related Documentation

- [SetpointHandler](setpoint-handler.md) - Command field management
- [MavlinkDataManager](mavlink-data-manager.md) - Telemetry source
- [Control Types](../03-protocols/control-types.md) - Command formats
