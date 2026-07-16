# MAVSDK Offboard Control

This document covers MAVSDK's Offboard API used by PixEagle for sending commands to PX4.

## Overview

MAVSDK is a C++/Python SDK for MAVLink-based drones. PixEagle uses MAVSDK exclusively for sending commands (not telemetry) because:
- Type-safe command construction
- Automatic MAVLink message formatting
- Built-in error handling
- Offboard mode management

## Connection

### Default Configuration

```python
# PX4InterfaceManager
system_address = "udp://127.0.0.1:14540"
connection_timeout_s = 15.0
```

### Connection Sequence

```python
async def connect(self):
    """Connect to PX4 via MAVSDK."""
    self.drone = System()

    async def connect_and_discover():
        await self.drone.connect(system_address=Parameters.SYSTEM_ADDRESS)
        async for state in self.drone.core.connection_state():
            if state.is_connected:
                return

    await asyncio.wait_for(
        connect_and_discover(),
        timeout=Parameters.MAVSDK_CONNECTION_TIMEOUT_S,
    )
```

Link setup alone is not success: PixEagle remains disconnected until MAVSDK's
connection-state stream reports vehicle discovery. Connection and telemetry stay
available when the follower circuit breaker is active because they do not change
aircraft behavior. After discovery, a separate connection-state subscription
keeps status truthful; a disconnect stops telemetry and local following without
attempting another command over the failed link.

## Offboard Mode

### What is Offboard Mode?

Offboard mode allows external systems (like PixEagle) to control the drone via MAVLink commands. The drone follows velocity, position, or attitude commands instead of RC inputs.

### Entering Offboard Mode

```python
async def start_offboard_mode(self):
    """Start offboard mode with safety priming."""
    self.setpoint_handler.reset_setpoints()
    await self.drone.offboard.set_velocity_body(
        VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
    )
    await asyncio.sleep(1.1)
    await self.drone.offboard.start()
    logger.info("Offboard mode started")
```

PX4 requires setpoint proof-of-life for more than one second before mode entry.
MAVSDK automatically retransmits the latest accepted setpoint at its internal
cadence, so PixEagle waits 1.1 seconds before requesting Offboard without
depending on an implementation-specific resend rate. A failed initial setter
prevents the mode request.

### Exiting Offboard Mode

```python
async def stop_offboard_mode(self):
    """Stop offboard mode - drone holds position."""
    await self.drone.offboard.stop()
    logger.info("Offboard mode stopped")
```

### Safety: Continuous Command Requirement

PX4 requires continuous offboard commands (typically 2+ Hz). If commands stop,
PX4 exits offboard mode for safety.

Current PixEagle application-level setter calls are owned by
`OffboardCommander`, an async refresh loop started by `AppController` after
Offboard mode is entered. MAVSDK owns the separate internal retransmission of
its latest setpoint. `AppController.follow_target()` updates follower math and
submits atomic `CommandIntent` snapshots; it does not send MAVSDK commands directly.
`SetpointSender` remains a legacy monitor and does not send MAVSDK commands.

## Command Types

### VelocityBodyYawspeed

Body-frame velocity control - the primary mode for PixEagle followers.

```python
from mavsdk.offboard import VelocityBodyYawspeed

# Create velocity command
velocity_cmd = VelocityBodyYawspeed(
    forward_m_s=2.0,     # Forward velocity (positive = forward)
    right_m_s=0.5,       # Right velocity (positive = right)
    down_m_s=-0.2,       # Down velocity (positive = descend)
    yawspeed_deg_s=15.0  # Yaw rate (positive = clockwise)
)

# Send to drone
await self.drone.offboard.set_velocity_body(velocity_cmd)
```

### AttitudeRate

Angular rate control for fixed-wing or advanced maneuvers.

```python
from mavsdk.offboard import AttitudeRate

# Create attitude rate command
attitude_cmd = AttitudeRate(
    roll_deg_s=10.0,     # Roll rate (positive = roll right)
    pitch_deg_s=5.0,     # Pitch rate (positive = pitch up)
    yaw_deg_s=15.0,      # Yaw rate (positive = yaw right)
    thrust_value=0.6     # Thrust (0.0 to 1.0)
)

# Send to drone
await self.drone.offboard.set_attitude_rate(attitude_cmd)
```

### VelocityNedYaw (Less Common)

NED-frame velocity control - requires yaw knowledge for conversion.

```python
from mavsdk.offboard import VelocityNedYaw

velocity_ned = VelocityNedYaw(
    north_m_s=2.0,
    east_m_s=1.0,
    down_m_s=0.0,
    yaw_deg=45.0
)

await self.drone.offboard.set_velocity_ned(velocity_ned)
```

## PX4InterfaceManager Command Dispatch

### Unified Send Method

```python
async def send_commands_unified(self, control_type: str, fields: dict):
    """Dispatch commands based on control type."""
    if control_type == 'velocity_body_offboard':
        await self._send_velocity_body_commands(fields)
    elif control_type == 'attitude_rate':
        await self._send_attitude_rate_commands(fields)
    else:
        logger.warning(f"Unknown control type: {control_type}")
```

### Velocity Body Commands

```python
async def _send_velocity_body_commands(self, fields: dict):
    """Send body-frame velocity command."""
    velocity_cmd = VelocityBodyYawspeed(
        forward_m_s=fields.get('vel_body_fwd', 0.0),
        right_m_s=fields.get('vel_body_right', 0.0),
        down_m_s=fields.get('vel_body_down', 0.0),
        yawspeed_deg_s=fields.get('yawspeed_deg_s', 0.0)
    )

    await self.drone.offboard.set_velocity_body(velocity_cmd)
```

### Attitude Rate Commands

```python
async def _send_attitude_rate_commands(self, fields: dict):
    """Send attitude rate command."""
    if 'thrust' not in fields:
        return False  # Required; never infer thrust at the PX4 boundary.
    attitude_cmd = AttitudeRate(
        roll_deg_s=fields.get('rollspeed_deg_s', 0.0),
        pitch_deg_s=fields.get('pitchspeed_deg_s', 0.0),
        yaw_deg_s=fields.get('yawspeed_deg_s', 0.0),
        thrust_value=fields['thrust']
    )

    await self.drone.offboard.set_attitude_rate(attitude_cmd)
```

## Error Handling

### Command Failures

```python
async def _safe_mavsdk_call(self, coro):
    """Execute MAVSDK call with error handling."""
    try:
        return await coro
    except OffboardError as e:
        if "event loop" in str(e).lower():
            # Async loop conflict - retry once
            logger.warning("Event loop conflict, retrying...")
            return await coro
        logger.error(f"Offboard error: {e}")
        raise
```

### Connection Loss

If MAVSDK loses connection:

1. PixEagle records local setter failures and stops local following after the
   configured consecutive-failure threshold.
2. PX4 independently exits Offboard after its configured loss timeout when the
   MAVLink proof-of-life stops.
3. The resulting aircraft action is governed by PX4 failsafe parameters and must
   be validated for the deployed vehicle configuration.

## Circuit Breaker Integration

PixEagle's circuit breaker intercepts commands in test mode:

```python
async def send_velocity_body_commands(self, fields):
    """Send velocity command with circuit breaker check."""
    if FollowerCircuitBreaker.is_active():
        FollowerCircuitBreaker.log_command_instead_of_execute(
            command_type="velocity_body_offboard",
            follower_name="PX4Interface",
            fields=fields
        )
        return  # Don't send to drone

    # Actually send command
    await self._send_velocity_body_commands(fields)
```

## Typical Command Flow

```
┌──────────────┐
│   Follower   │
│ follow_target│
└──────┬───────┘
       │ Calculates velocities
       ▼
┌──────────────────────┐
│  SetpointHandler     │
│  set_fields(...)     │◄─── Validates full command snapshot
└──────┬───────────────┘
       │ Emits CommandIntent
       ▼
┌──────────────────────┐
│  OffboardCommander   │
│ fixed-rate refresh   │◄─── application setter owner
└──────┬───────────────┘
       │ send_commands_unified()
       ▼
┌──────────────────────┐
│  PX4InterfaceManager │
│  send_*_commands()   │
└──────┬───────────────┘
       │ Creates VelocityBodyYawspeed
       ▼
┌──────────────────┐
│    MAVSDK        │
│ set_velocity_body│◄─── Formats MAVLink
└──────┬───────────┘
       │ MAVLink message
       ▼
┌──────────────────┐
│       PX4        │
│   Autopilot      │
└──────────────────┘
```

## Best Practices

### Command Rates

- Minimum: 2 Hz (PX4 timeout threshold)
- `OFFBOARD_COMMAND_RATE_HZ` defaults to 20 Hz and controls PixEagle's
  application-level MAVSDK setter refresh cadence.
- Tracker/follower updates submit fresh `CommandIntent` snapshots; they are not
  direct MAVSDK sends.
- MAVSDK independently retransmits its latest accepted setpoint at an
  implementation-owned cadence; PixEagle does not use that private rate as a
  configurable or safety assumption.
- SITL/HIL/field evidence is still required before claiming vehicle-level timing
  success for a specific PX4 setup.

### Smooth Transitions

```python
# Avoid sudden velocity changes
current_vel = 0.0
target_vel = 5.0
ramp_rate = 2.0  # m/s per second

while current_vel < target_vel:
    current_vel = min(current_vel + ramp_rate * dt, target_vel)
    await send_velocity(current_vel)
```

### Attitude-Rate Fallback Thrust

Thrust is vehicle- and profile-dependent. It is never sampled from current
throttle telemetry or invented by the MAVSDK dispatch boundary. The active
follower configures the shared `SetpointHandler` fallback from the canonical
runtime parameter before Offboard priming:

```yaml
MC_ATTITUDE_RATE:
  HOVER_THRUST: 0.5

FW_ATTITUDE_RATE:
  CRUISE_THRUST: 0.6
```

These are configuration examples, not vehicle-safe universal values. They must
be reviewed and validated for the target airframe before live commands are
enabled. Missing `thrust` fails closed.

## Related Documentation

- [Control Types](control-types.md) - Command field definitions
- [PX4InterfaceManager](../02-components/px4-interface-manager.md) - Implementation
- [MAVLink Overview](mavlink-overview.md) - Protocol basics
