# MAVLink Integration

> PX4 communication via MAVSDK

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        PixEagle                                  │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────┐    │
│  │  Follower   │ → │CommandIntent│ → │OffboardCommander │    │
│  └─────────────┘    └─────────────┘    └──────────────────┘    │
│                                                  │              │
│                                           ┌─────────────┐       │
│                                           │PX4Interface │       │
│                                           └─────────────┘       │
│                                                  │              │
└──────────────────────────────────────────────────┼──────────────┘
                                               │
                                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                          MAVSDK                                  │
│                     (Python bindings)                           │
└──────────────────────────────────────────────┬───────────────────┘
                                               │
                                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        MAVLink Protocol                          │
│                     (UDP Port 14540)                            │
└──────────────────────────────────────────────┬───────────────────┘
                                               │
                                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                      PX4 Autopilot                               │
│                   (Flight Controller)                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## MAVSDK Setup

### Connection

```python
from mavsdk import System

async def connect():
    drone = System()
    await drone.connect(system_address="udpin://0.0.0.0:14540")

    async for state in drone.core.connection_state():
        if state.is_connected:
            print("Connected to PX4")
            break
```

### In PixEagle

```python
from classes.offboard_commander import OffboardCommander
from classes.px4_interface_manager import PX4InterfaceManager

px4 = PX4InterfaceManager()
await px4.connect()
commander = OffboardCommander(px4, px4.setpoint_handler)
await commander.start()
```

---

## Offboard Control

### Enable Offboard Mode

```python
async def start_offboard():
    # Must send setpoints before arming
    await drone.offboard.set_velocity_body(
        VelocityBodyYawspeed(0, 0, 0, 0)
    )

    # Start offboard mode
    await drone.offboard.start()
```

### Control Types

**Velocity Body Offboard** (Multicopter):

```python
from mavsdk.offboard import VelocityBodyYawspeed

await drone.offboard.set_velocity_body(
    VelocityBodyYawspeed(
        forward_m_s=5.0,
        right_m_s=-2.0,
        down_m_s=0.5,
        yawspeed_deg_s=10.0
    )
)
```

**Attitude Rate** (Fixed-Wing):

```python
from mavsdk.offboard import AttitudeRate

await drone.offboard.set_attitude_rate(
    AttitudeRate(
        roll_deg_s=15.0,
        pitch_deg_s=5.0,
        yaw_deg_s=10.0,
        thrust_value=0.6
    )
)
```

---

## PixEagle Command Boundary

Followers do not call MAVSDK directly. They publish one complete
`CommandIntent`; `OffboardCommander` owns the fixed-rate application setter
refresh and calls `PX4InterfaceManager.send_commands_unified()`.

```python
intent = follower.get_last_command_intent()
commander.submit_intent(intent)
```

---

## Telemetry

### Position

```python
async for position in drone.telemetry.position():
    altitude = position.relative_altitude_m
    lat = position.latitude_deg
    lon = position.longitude_deg
```

### Attitude

```python
async for attitude in drone.telemetry.attitude_euler():
    pitch = attitude.pitch_deg
    roll = attitude.roll_deg
    yaw = attitude.yaw_deg
```

### Velocity

```python
async for velocity in drone.telemetry.velocity_ned():
    north = velocity.north_m_s
    east = velocity.east_m_s
    down = velocity.down_m_s
```

---

## Safety Features

### Offboard Timeout

PX4 requires a continuous setpoint proof-of-life above its minimum rate. MAVSDK
owns the wire-level resend of its latest accepted setpoint at an internal
cadence. PixEagle's `OffboardCommander` refreshes that latest setpoint from
current application intent; `SetpointSender` is only a monitor:

```python
OFFBOARD_COMMAND_PERIOD_S = 1.0 / Parameters.OFFBOARD_COMMAND_RATE_HZ

async def offboard_commander_loop():
    while offboard_active:
        await send_current_setpoint()
        await asyncio.sleep(OFFBOARD_COMMAND_PERIOD_S)
```

### RTL Trigger

```python
async def trigger_rtl():
    """Trigger Return to Launch."""
    await drone.action.return_to_launch()
```

### Emergency Land

```python
async def emergency_land():
    """Emergency landing."""
    await drone.action.land()
```

---

## Gimbal Control

### MAVLink v2 Gimbal Protocol

```python
from mavsdk.gimbal import GimbalMode, ControlMode

# Set gimbal mode
await drone.gimbal.set_mode(GimbalMode.YAW_FOLLOW)

# Control pitch/yaw
await drone.gimbal.set_pitch_and_yaw(
    pitch_deg=-15.0,
    yaw_deg=30.0
)
```

### Rate Control

```python
await drone.gimbal.set_pitch_rate_and_yaw_rate(
    pitch_rate_deg_s=5.0,
    yaw_rate_deg_s=10.0
)
```

---

## Port Configuration

Follower behavior does not own the PX4 transport. The deployment router must
feed the PixEagle MAVSDK endpoint on `127.0.0.1:14540/udp` and, with default
REST telemetry, MAVLink2REST on `127.0.0.1:14569/udp`. Follow the canonical
[PX4 and MAVLink connectivity guide](../../drone-interface/04-infrastructure/port-configuration.md)
instead of maintaining a second routing example here.

---

## Troubleshooting

### Connection Issues

```bash
# Inspect the PixEagle-owned runtime without killing unrelated processes
make status

# Or, for the installed service
pixeagle-service status
```

### Offboard Rejection

```python
# PX4 requires:
# 1. Commands before arming
# 2. Commands at ≥2Hz
# 3. Valid command values
```

### Telemetry Lag

```python
# Use async properly
async for telemetry in drone.telemetry.position():
    # Process immediately, don't block
    process_async(telemetry)
```
