# Control Types Reference

This document defines the control types (command formats) supported by PixEagle for drone control.

## Overview

Control types define how PixEagle commands the drone. Each type maps to specific MAVSDK methods and MAVLink messages.

## Supported Control Types

| Control Type | Description | MAVSDK Method | Use Case |
|--------------|-------------|---------------|----------|
| `velocity_body_offboard` | Body-frame velocity | `set_velocity_body` | Multicopters, primary |
| `attitude_rate` | Angular rates + thrust | `set_attitude_rate` | Fixed-wing, advanced |
| `velocity_body` | Legacy velocity (deprecated) | `set_velocity_body` | Backward compatibility |

## velocity_body_offboard

The primary control type for multicopter tracking in PixEagle.

### Field Definitions

| Field | Type | Unit | Range | Description |
|-------|------|------|-------|-------------|
| `vel_body_fwd` | float | m/s | -8 to +8 | Forward velocity |
| `vel_body_right` | float | m/s | -5 to +5 | Lateral velocity |
| `vel_body_down` | float | m/s | -3 to +3 | Vertical velocity |
| `yawspeed_deg_s` | float | deg/s | -45 to +45 | Yaw rotation rate |

### Coordinate System

```
        Forward (+X)
            ▲
            │
            │
   Left ◄───┼───► Right (+Y)
            │
            │
            ▼
        Backward

    Down (+Z) is into the page
```

### Sign Conventions

- `vel_body_fwd`: Positive = move forward, Negative = move backward
- `vel_body_right`: Positive = move right, Negative = move left
- `vel_body_down`: Positive = descend, Negative = climb
- `yawspeed_deg_s`: Positive = rotate clockwise (viewed from above)

### Schema Definition

From `configs/follower_commands.yaml`:

```yaml
follower_profiles:
  mc_velocity_offboard:
    control_type: velocity_body_offboard
    display_name: "MC Velocity Offboard"
    description: "Body-frame velocity control for multicopters"
    required_fields:
      - vel_body_fwd
      - vel_body_right
      - vel_body_down
      - yawspeed_deg_s
```

### Example Usage

```python
# SetpointHandler usage
setpoint_handler = SetpointHandler('mc_velocity_offboard')

# Set forward velocity for pursuit
setpoint_handler.set_field('vel_body_fwd', 3.0)

# Add yaw to track target laterally
setpoint_handler.set_field('yawspeed_deg_s', 15.0)

# Get all fields for sending
fields = setpoint_handler.get_fields()
# Returns: {'vel_body_fwd': 3.0, 'vel_body_right': 0.0,
#           'vel_body_down': 0.0, 'yawspeed_deg_s': 15.0}
```

### MAVSDK Mapping

```python
from mavsdk.offboard import VelocityBodyYawspeed

velocity_cmd = VelocityBodyYawspeed(
    forward_m_s=fields['vel_body_fwd'],
    right_m_s=fields['vel_body_right'],
    down_m_s=fields['vel_body_down'],
    yawspeed_deg_s=fields['yawspeed_deg_s']
)
```

## attitude_rate

Control type for angular rate control, typically used for fixed-wing aircraft.

### Field Definitions

| Field | Type | Unit | Range | Description |
|-------|------|------|-------|-------------|
| `rollspeed_deg_s` | float | deg/s | -60 to +60 | Roll rotation rate |
| `pitchspeed_deg_s` | float | deg/s | -60 to +60 | Pitch rotation rate |
| `yawspeed_deg_s` | float | deg/s | -45 to +45 | Yaw rotation rate |
| `thrust` | float | 0-1 | 0.0 to 1.0 | Normalized thrust |

### Sign Conventions

- `rollspeed_deg_s`: Positive = roll right (right wing down)
- `pitchspeed_deg_s`: Positive = pitch up (nose up)
- `yawspeed_deg_s`: Positive = yaw right (clockwise from above)
- `thrust`: 0.0 = no thrust, 1.0 = full thrust

### Schema Definition

```yaml
follower_profiles:
  fw_attitude_rate:
    control_type: attitude_rate
    display_name: "FW Attitude Rate"
    description: "Angular rate control for fixed-wing"
    required_fields:
      - rollspeed_deg_s
      - pitchspeed_deg_s
      - yawspeed_deg_s
      - thrust
```

### Thrust Considerations

Unlike velocity control, attitude rate requires explicit thrust management:

```python
# Hover thrust varies by vehicle
HOVER_THRUST = 0.5  # Typical starting point

# Climbing requires more thrust
if climbing:
    thrust = HOVER_THRUST + 0.1

# Descending requires less
if descending:
    thrust = HOVER_THRUST - 0.1
```

### MAVSDK Mapping

```python
from mavsdk.offboard import AttitudeRate

attitude_cmd = AttitudeRate(
    roll_deg_s=fields['rollspeed_deg_s'],
    pitch_deg_s=fields['pitchspeed_deg_s'],
    yaw_deg_s=fields['yawspeed_deg_s'],
    thrust_value=fields['thrust']
)
```

## Velocity Limits

### Safety Clamping

Values are automatically clamped to safe limits:

```python
# From Parameters
MAX_VELOCITY_FORWARD = 8.0   # m/s
MAX_VELOCITY_LATERAL = 5.0   # m/s
MAX_VELOCITY_VERTICAL = 3.0  # m/s
MAX_YAW_RATE = 45.0          # deg/s

# SetpointHandler applies clamping
def set_field(self, name, value):
    clamped_value = self._clamp_value(name, value)
    self.fields[name] = clamped_value
```

### Per-Field Limit Mapping

```python
FIELD_LIMIT_MAP = {
    'vel_body_fwd': 'MAX_VELOCITY_FORWARD',
    'vel_body_right': 'MAX_VELOCITY_LATERAL',
    'vel_body_down': 'MAX_VELOCITY_VERTICAL',
    'yawspeed_deg_s': 'MAX_YAW_RATE',
    'rollspeed_deg_s': 'MAX_ATTITUDE_RATE',
    'pitchspeed_deg_s': 'MAX_ATTITUDE_RATE',
    'thrust': None  # Fixed 0-1 range
}
```

## Control Type Selection

### By Aircraft Type

| Aircraft Type | Recommended Control Type |
|---------------|--------------------------|
| Multicopter | `velocity_body_offboard` |
| Fixed-wing | `attitude_rate` |
| Hybrid/VTOL | Varies by mode |

### By Follower Type

| Follower | Control Type | Reason |
|----------|--------------|--------|
| MCVelocityFollower | velocity_body_offboard | Direct velocity mapping |
| MCVelocityChaseFollower | velocity_body_offboard | Pursuit geometry |
| FWAttitudeRateFollower | attitude_rate | Fixed-wing control |
| GMVelocityVectorFollower | velocity_body_offboard | Gimbal + velocity |

## Unit Conversions

### Degrees vs Radians

PixEagle uses degrees internally, MAVSDK uses degrees for offboard:

```python
# No conversion needed for yawspeed
yawspeed_deg_s = 45.0  # Degrees per second

# MAVLink internally converts to radians
# VelocityBodyYawspeed expects degrees
```

### Meters per Second

All velocities are in m/s:

```python
# Converting from km/h
velocity_mps = velocity_kmh / 3.6

# Converting from knots
velocity_mps = velocity_knots * 0.514444
```

## Zero Command (Hover)

### Velocity Control

```python
# Zero velocity = hover in place
hover_cmd = {
    'vel_body_fwd': 0.0,
    'vel_body_right': 0.0,
    'vel_body_down': 0.0,
    'yawspeed_deg_s': 0.0
}
```

### Attitude Rate Control

```python
# Zero rates with hover thrust
hover_cmd = {
    'rollspeed_deg_s': 0.0,
    'pitchspeed_deg_s': 0.0,
    'yawspeed_deg_s': 0.0,
    'thrust': 0.5  # Vehicle-dependent
}
```

## Deprecated Control Types

### velocity_body (Legacy)

Identical to `velocity_body_offboard` but marked for removal:

```yaml
# Deprecated - use velocity_body_offboard instead
velocity_body:
  control_type: velocity_body  # Legacy
  display_name: "MC Velocity (Deprecated)"
```

Migration:
```python
# Old
handler = SetpointHandler('velocity_body')

# New
handler = SetpointHandler('mc_velocity_offboard')
```

## Related Documentation

- [SetpointHandler](../02-components/setpoint-handler.md) - Schema implementation
- [MAVSDK Offboard](mavsdk-offboard.md) - Command interface
- [follower_commands.yaml](../../../configs/follower_commands.yaml) - Full schema
