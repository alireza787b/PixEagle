# PX4InterfaceManager

> Central orchestrator for MAVSDK command dispatch and telemetry aggregation.

**Source**: `src/classes/px4_interface_manager.py`

## Overview

PX4InterfaceManager is the main interface between PixEagle and the PX4 autopilot via MAVSDK. It handles:

- MAVSDK System connection management
- Offboard mode control (start/stop)
- Command dispatch (`velocity_body_offboard`, `attitude_rate`)
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
│  │ failsafe_active: bool       # safety triggered           │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Components:                                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ drone: mavsdk.System        # MAVSDK connection          │    │
│  │ setpoint_handler: SetpointHandler                        │    │
│  │ mavlink_data_manager: MavlinkDataManager (optional)      │    │
│  │ update_task: asyncio.Task   # telemetry supervisor       │    │
│  │ connection_monitor_task: asyncio.Task                    │    │
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
| `MAVSDK_SERVER_ADDRESS` / `MAVSDK_SERVER_PORT` | Parameters | Python client's external gRPC destination |
| `SYSTEM_ADDRESS` | Parameters | MAVSDK vehicle-link URI (for example, `udpin://127.0.0.1:14540`) |
| `MAVSDK_CONNECTION_TIMEOUT_S` | Parameters | Deadline for MAVSDK vehicle discovery after link setup |
| `MAVLINK_STALE_TIMEOUT_S` | Parameters | Source-independent maximum age of a complete follower telemetry snapshot |
| `FOLLOWER_MODE` | Parameters | Initial follower profile name |

## Connection Management

### connect()

```python
async def connect(self):
    """
    Open the MAVSDK link, await confirmed vehicle discovery, and start telemetry.
    Reuse an already verified connection and telemetry task.
    """
```

**Flow**:
```
connect() called
       │
       ▼
┌──────────────────────┐
│ Verified connection? │──Yes──► Reuse telemetry task, return status
└──────────┬───────────┘
           │ No
         ▼
   external: drone.connect()
   embedded: drone.connect(SYSTEM_ADDRESS)
         │
         ▼
   await core.connection_state().is_connected
         │ timeout/error
         ├──────────────► fail; active_mode remains false
         │ confirmed
         ▼
   active_mode = True
         │
         ▼
   Start telemetry supervisor and connection monitor
         │
         ▼
   state = starting until every required field has a sample
```

The monitor keeps consuming MAVSDK connection state after discovery. A reported
loss revokes local connection truth, cancels telemetry, and asks `AppController`
to stop local following without a final command over the known-dead link. Each
monitor captures its connection generation, so a delayed event from an old
monitor cannot invalidate a newer connection.

`stop()` is task cleanup, not an inferred aircraft command. Normal lifecycle
ownership exits Offboard through `AppController` first, then calls `stop()` to
join the monitor and telemetry tasks. A caller must explicitly opt in if it
still owns an active Offboard session and needs a stop attempt.

The follower circuit breaker gates commands to PX4. It does not block MAVSDK
link setup, vehicle discovery, telemetry subscriptions, or status reads.
`connect()` returns only after discovery is confirmed, and raises after
`PX4.MAVSDK_CONNECTION_TIMEOUT_S` instead of publishing a false connected state.

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
`disconnect_age_s`, `disconnect_count`, `last_error`, `connection_timeout_s`,
`connection_age_s`, `system_address`, `uses_mavlink2rest`, and telemetry worker
diagnostics. Its `telemetry` object separately reports `state`, `ready`,
`source`, `sample_count`, complete-sample age, freshness deadline, required
fields, connection/telemetry generations, temporal skew, and the last error.
Top-level status also exposes `cleanup_failed` and `owned_tasks`; `connected`
is never true while retained task ownership is unresolved. `connected` means
MAVSDK discovered the vehicle;
`command_ready` additionally requires complete, fresh follower telemetry. A
persistent MAVSDK connection-state monitor changes status to
`connection_lost`, stops telemetry, and asks `AppController` to stop local
following without a final link command when a post-discovery disconnect occurs.

This hook does not stop PX4, Docker, MavlinkAnywhere, MAVLink2REST, a MAVSDK
server, network interfaces, or MAVLink routes. A successful `connect()` clears
only the validation-local disconnect flag after the normal MAVSDK connect path
runs.

### stop()

```python
async def stop(self):
    """
    Revoke command ownership and stop owned monitor/telemetry tasks.

    Offboard stop is attempted only when explicitly requested by the caller.
    """
```

Task joins have bounded deadlines. Parent cancellation is propagated rather
than mistaken for successful child cancellation. A task that ignores
cancellation remains referenced, blocks replacement ownership, and makes
`stop()` return `status = cleanup_failed` until a later cleanup confirms that
all owned tasks stopped.

## Telemetry Updates

### update_drone_data()

Background task that assembles complete follower telemetry snapshots.

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

### MAVLink2REST Telemetry

```python
async def _update_telemetry_via_mavlink2rest(self):
    """
    Fetches telemetry from MAVLink2REST via MavlinkDataManager.

    Fetch every required field and publish only a complete finite snapshot.
    Preserve the last complete snapshot on a request or payload failure.
    """
```

Missing or invalid fields never become zero or a safety-limit value. A measured
zero is valid data; an unavailable value is `None`. Follow startup waits for the
first complete snapshot. Later failures retain the last snapshot for
diagnostics, but `MAVLINK_STALE_TIMEOUT_S` transitions readiness to `stale` and
ordinary Offboard publication fails closed. Attitude, altitude, and ground speed
requests run concurrently under one cycle deadline. Their completion timestamps
must fit within the telemetry temporal-skew bound before a snapshot can commit.

### MAVSDK Telemetry

```python
async def _update_telemetry_via_mavsdk(self):
    """
    Streams telemetry directly from MAVSDK (gRPC).
    Note: Circuit breaker does NOT block telemetry - only commands.
    """
    # Position, attitude_euler, and velocity_body run concurrently.
    # Their latest finite values are staged and committed together only while
    # all required streams are fresh.
```

MAVSDK and MAVLink2REST are alternative telemetry sources, not primary and
fallback layers. The configured source is immutable for one worker lifecycle;
changing it restarts the worker and resets readiness so samples from two source
lifecycles cannot be mixed. MAVSDK stream samples must all carry the current
telemetry generation and fit within the same temporal-skew bound. Every
telemetry generation is bound to one connection generation, preventing late
workers from committing after reconnect.

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

    if control_type == 'attitude_rate':
        await self.send_attitude_rate_commands()
    elif control_type == 'velocity_body_offboard':
        await self.send_velocity_body_offboard_commands()
    elif control_type == 'velocity_body_offboard':
        await self.send_velocity_body_offboard_commands()
```

`OffboardCommander` checks `is_command_connection_ready()` before every
publication. The check binds commands to the current connection generation and
requires fresh telemetry. Teardown commands use the known link state instead,
so a telemetry outage cannot prevent a bounded Hold/Offboard-stop attempt.

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

Unavailable or failing safety-gate infrastructure always blocks the command.
There is no live-PX4 bypass for a missing or unhealthy safety gate. Use the
explicit `COMMAND_PREVIEW` execution mode when the goal is to inspect follower
math without publishing to a vehicle.

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
    Reset to profile defaults, publish the initial setpoint, establish the
    MAVSDK retransmission stream for 1.1 seconds, then request Offboard mode.
    Return an explicit executed/simulated/blocked/failed action outcome.
    """
```

The operation is simulated without MAVSDK calls when the circuit breaker is
active, fails closed when no vehicle connection is confirmed, and never calls
`offboard.start()` after a failed initial setpoint.

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

- Link setup and vehicle discovery share a bounded timeout; failures keep
  `active_mode` false and remain visible in connection status
- Command errors logged with specific error types (OffboardError, ValueError)
- Async loop conflicts handled with retry mechanism
- Circuit breaker provides fail-safe when testing

## Configuration Example

```yaml
PX4:
  EXTERNAL_MAVSDK_SERVER: true
  MAVSDK_SERVER_ADDRESS: 127.0.0.1
  MAVSDK_SERVER_PORT: 50051
  SYSTEM_ADDRESS: "udpin://127.0.0.1:14540"
  MAVSDK_CONNECTION_TIMEOUT_S: 15.0

Follower:
  USE_MAVLINK2REST: true  # Use REST for telemetry
  FOLLOWER_MODE: "mc_velocity_position"
```

## Related Documentation

- [SetpointHandler](setpoint-handler.md) - Command field management
- [MavlinkDataManager](mavlink-data-manager.md) - Telemetry source
- [Control Types](../03-protocols/control-types.md) - Command formats
