# MAVLink Protocol Overview

This document covers MAVLink basics as used in PixEagle for PX4 communication.

## What is MAVLink?

MAVLink (Micro Air Vehicle Link) is a lightweight messaging protocol for communicating with drones and between onboard drone components. PixEagle uses MAVLink 2.0.

## Key Concepts

### Message Structure

MAVLink messages consist of:
- **System ID**: Identifies the sending system (1 = autopilot, 255 = ground station)
- **Component ID**: Identifies the component within a system
- **Message ID**: Specifies the message type
- **Payload**: Message-specific data

### Common Messages Used by PixEagle

| Message | ID | Purpose | Source |
|---------|-----|---------|--------|
| `HEARTBEAT` | 0 | Connection health, flight mode | Autopilot |
| `ATTITUDE` | 30 | Roll, pitch, yaw | Autopilot |
| `GLOBAL_POSITION_INT` | 33 | GPS position | Autopilot |
| `VFR_HUD` | 74 | Ground speed, throttle | Autopilot |
| `ALTITUDE` | 141 | Altitude data | Autopilot |
| `OFFBOARD_CONTROL_MODE` | - | Command mode selection | GCS |

## Flight Mode Encoding

PX4 encodes flight modes in the `custom_mode` field of HEARTBEAT:

```python
FLIGHT_MODES = {
    196608: "Position",      # Standard position hold
    393216: "Offboard",      # External control (PixEagle)
    327680: "Hold",          # Loiter in place
    84148224: "RTL",         # Return to launch
    50593792: "Land",        # Automatic landing
    65536: "Manual",         # Direct RC control
}
```

### Mode Detection in PixEagle

```python
# From MavlinkDataManager
def _handle_flight_mode_change(self, new_mode_code):
    """Handle flight mode changes from MAVLink."""
    if self._was_in_offboard and new_mode_code != self.OFFBOARD_MODE_CODE:
        # Drone exited offboard mode - trigger callback
        self._trigger_offboard_exit_callback()
```

## Connection Architecture

```
┌─────────────┐    MAVLink     ┌─────────────────┐
│    PX4      │◄──────────────►│  mavlink-router │
│  Autopilot  │                └────────┬────────┘
└─────────────┘                         │
                                        │ Routes to:
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
                    ▼                   ▼                   ▼
            ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
            │ MAVLink2REST │    │    MAVSDK    │    │   QGC/GCS    │
            │  :8088       │    │   :14540     │    │   :14550     │
            └──────────────┘    └──────────────┘    └──────────────┘
                    │                   │
                    ▼                   ▼
            ┌─────────────────────────────────────┐
            │          PX4InterfaceManager         │
            │  Telemetry ◄──┘           └──► Commands
            └─────────────────────────────────────┘
```

## Telemetry Messages

### ATTITUDE (ID: 30)

Provides orientation in radians:

```json
{
  "message": {
    "roll": 0.05,        // Roll angle (rad)
    "pitch": -0.02,      // Pitch angle (rad)
    "yaw": 1.57,         // Yaw angle (rad)
    "rollspeed": 0.01,   // Roll rate (rad/s)
    "pitchspeed": 0.0,   // Pitch rate (rad/s)
    "yawspeed": 0.02     // Yaw rate (rad/s)
  }
}
```

PixEagle converts to degrees:
```python
roll_deg = math.degrees(attitude_data['roll'])
pitch_deg = math.degrees(attitude_data['pitch'])
yaw_deg = math.degrees(attitude_data['yaw'])
```

### VFR_HUD (ID: 74)

Provides speed and throttle:

```json
{
  "message": {
    "groundspeed": 5.2,  // Ground speed (m/s)
    "airspeed": 5.5,     // Air speed (m/s)
    "throttle": 45,      // Throttle percentage (0-100)
    "alt": 50.0,         // Altitude (m)
    "climb": 0.5,        // Climb rate (m/s)
    "heading": 90        // Heading (degrees)
  }
}
```

### ALTITUDE (ID: 141)

Provides multiple altitude references:

```json
{
  "message": {
    "altitude_relative": 25.5,  // Relative to home (m)
    "altitude_terrain": 30.0,   // Above terrain (m)
    "altitude_amsl": 125.5      // Above mean sea level (m)
  }
}
```

## Command Messages

### SET_POSITION_TARGET_LOCAL_NED (ID: 84)

Used for velocity body commands via MAVSDK:

| Field | Description | Unit |
|-------|-------------|------|
| `vx` | Velocity in body X (forward) | m/s |
| `vy` | Velocity in body Y (right) | m/s |
| `vz` | Velocity in body Z (down) | m/s |
| `yaw_rate` | Yaw rate | rad/s |

### SET_ATTITUDE_TARGET (ID: 82)

Used for attitude rate commands:

| Field | Description | Unit |
|-------|-------------|------|
| `body_roll_rate` | Roll rate | rad/s |
| `body_pitch_rate` | Pitch rate | rad/s |
| `body_yaw_rate` | Yaw rate | rad/s |
| `thrust` | Normalized thrust | 0-1 |

## Frame Conventions

### NED (North-East-Down)

Global reference frame:
- **X**: Points North
- **Y**: Points East
- **Z**: Points Down (positive = descending)

### Body Frame

Vehicle-relative frame:
- **X**: Points Forward (nose)
- **Y**: Points Right (starboard)
- **Z**: Points Down

### Conversion

```python
def body_to_ned(forward_vel, right_vel, yaw_rad):
    """Convert body velocities to NED frame."""
    north = forward_vel * cos(yaw_rad) - right_vel * sin(yaw_rad)
    east = forward_vel * sin(yaw_rad) + right_vel * cos(yaw_rad)
    return north, east
```

## Connection Health

### Heartbeat Monitoring

PixEagle monitors heartbeat rate:
- Expected: 1 Hz from autopilot
- Timeout: >5 seconds = connection lost

### Connection States

```python
class ConnectionState:
    DISCONNECTED = 0   # No heartbeat received
    CONNECTING = 1     # Initial connection
    CONNECTED = 2      # Healthy heartbeat stream
    DEGRADED = 3       # Intermittent heartbeat
```

## Message Rates

Typical PX4 SITL rates:
- `HEARTBEAT`: 1 Hz
- `ATTITUDE`: 50 Hz
- `GLOBAL_POSITION_INT`: 10 Hz
- `VFR_HUD`: 4 Hz
- `ALTITUDE`: 10 Hz

## Related Documentation

- [MAVLink2REST API](mavlink2rest-api.md) - HTTP access to MAVLink
- [MAVSDK Offboard](mavsdk-offboard.md) - Command interface
- [Control Types](control-types.md) - Command formats
