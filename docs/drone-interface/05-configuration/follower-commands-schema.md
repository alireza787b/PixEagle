# Follower Commands Schema

This document covers the `follower_commands.yaml` schema that defines command field definitions and profiles.

## Schema Location

```
configs/follower_commands.yaml
```

## Schema Structure

```yaml
schema_version: "2.0"

follower_profiles:
  # Profile definitions
  mc_velocity_offboard:
    control_type: velocity_body_offboard
    # ...

command_fields:
  # Field definitions
  vel_body_fwd:
    type: float
    # ...

validation_rules:
  # Validation constraints
```

## Follower Profiles

### Profile Definition

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
    optional_fields: []
```

### Available Profiles

| Profile | Control Type | Use Case |
|---------|--------------|----------|
| mc_velocity_offboard | velocity_body_offboard | Multicopter velocity |
| mc_velocity_position | velocity_body_offboard | Position-based velocity |
| mc_velocity_chase | velocity_body_offboard | Chase/pursuit mode |
| fw_attitude_rate | attitude_rate | Fixed-wing control |

### Profile Naming Convention

Format: `{platform}_{control_mode}_{variant}`

- Platform: `mc` (multicopter), `fw` (fixed-wing), `gm` (gimbal mode)
- Control mode: `velocity`, `position`, `attitude`
- Variant: Optional descriptor

## Command Fields

### Field Definition

```yaml
command_fields:
  vel_body_fwd:
    type: float
    unit: "m/s"
    description: "Forward velocity in body frame"
    default: 0.0
    clamp: true
    limit_name: "MAX_VELOCITY_FORWARD"
```

### Field Properties

| Property | Type | Description |
|----------|------|-------------|
| type | string | Data type (float, int) |
| unit | string | Unit of measurement |
| description | string | Human-readable description |
| default | number | Default value |
| clamp | boolean | Apply safety limits |
| limit_name | string | Parameter name for limit |
| limits | object | Fixed min/max limits |

### Velocity Fields

```yaml
vel_body_fwd:
  type: float
  unit: "m/s"
  description: "Forward velocity (positive = forward)"
  default: 0.0
  clamp: true
  limit_name: "MAX_VELOCITY_FORWARD"

vel_body_right:
  type: float
  unit: "m/s"
  description: "Lateral velocity (positive = right)"
  default: 0.0
  clamp: true
  limit_name: "MAX_VELOCITY_LATERAL"

vel_body_down:
  type: float
  unit: "m/s"
  description: "Vertical velocity (positive = down)"
  default: 0.0
  clamp: true
  limit_name: "MAX_VELOCITY_VERTICAL"

yawspeed_deg_s:
  type: float
  unit: "deg/s"
  description: "Yaw rate (positive = clockwise)"
  default: 0.0
  clamp: true
  limit_name: "MAX_YAW_RATE"
```

### Attitude Rate Fields

```yaml
rollspeed_deg_s:
  type: float
  unit: "deg/s"
  description: "Roll rate (positive = roll right)"
  default: 0.0
  clamp: true

pitchspeed_deg_s:
  type: float
  unit: "deg/s"
  description: "Pitch rate (positive = pitch up)"
  default: 0.0
  clamp: true

thrust:
  type: float
  unit: "normalized"
  description: "Thrust value 0-1"
  default: 0.5
  clamp: true
  limits:
    min: 0.0
    max: 1.0
```

## Validation Rules

```yaml
validation_rules:
  attitude_rate_exclusive:
    fields:
      - rollspeed_deg_s
      - pitchspeed_deg_s
      - thrust
    allowed_control_types:
      - attitude_rate
    description: "Attitude rate fields only with attitude_rate control type"
```

## Usage in Code

### SetpointHandler

```python
from classes.setpoint_handler import SetpointHandler

# Create handler with profile
handler = SetpointHandler('mc_velocity_offboard')

# Set fields
handler.set_field('vel_body_fwd', 3.0)
handler.set_field('yawspeed_deg_s', 15.0)

# Get fields
fields = handler.get_fields()
# {'vel_body_fwd': 3.0, 'vel_body_right': 0.0, ...}

# Get control type
control_type = handler.get_control_type()
# 'velocity_body_offboard'
```

### Follower Integration

```python
class MCVelocityFollower(BaseFollower):
    def __init__(self):
        self.setpoint_handler = SetpointHandler('mc_velocity_offboard')

    def follow_target(self, target):
        # Calculate velocities
        fwd_vel = self.calculate_forward_velocity(target)
        yaw_rate = self.calculate_yaw_rate(target)

        # Set fields (clamped automatically)
        self.setpoint_handler.set_field('vel_body_fwd', fwd_vel)
        self.setpoint_handler.set_field('yawspeed_deg_s', yaw_rate)
```

## Adding New Profiles

### Step 1: Define Profile

```yaml
follower_profiles:
  my_custom_profile:
    control_type: velocity_body_offboard
    display_name: "My Custom Mode"
    description: "Custom velocity control"
    required_fields:
      - vel_body_fwd
      - yawspeed_deg_s
    optional_fields:
      - vel_body_right
```

### Step 2: Verify Fields Exist

Ensure all required fields are defined in `command_fields`.

### Step 3: Use in Code

```python
handler = SetpointHandler('my_custom_profile')
```

## Schema Validation

SetpointHandler validates on initialization:
- Profile exists in schema
- All required fields defined
- Field types match

## Related Documentation

- [SetpointHandler Component](../02-components/setpoint-handler.md)
- [Control Types](../03-protocols/control-types.md)
- [Adding Control Types](../06-development/adding-control-types.md)
