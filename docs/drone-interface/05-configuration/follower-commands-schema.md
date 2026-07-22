# Follower Commands Schema

This document covers the `follower_commands.yaml` schema that defines command field definitions and profiles.

## Schema Location

```
configs/follower_commands.yaml
```

## Schema Structure

```yaml
schema_version: "2.0.0"

follower_profiles:
  # Profile definitions
  mc_velocity_chase:
    control_type: velocity_body_offboard
    # ...

command_fields:
  # Field definitions
  vel_body_fwd:
    type: float
    # ...

validation_rules:
  # Attitude-only field constraints; yawspeed_deg_s is shared by both controls
```

## Follower Profiles

### Profile Definition

```yaml
follower_profiles:
  mc_velocity_chase:
    control_type: velocity_body_offboard
    display_name: "MC Velocity Chase"
    description: "Body-frame velocity control for multicopters"
    required_fields:
      - vel_body_fwd
      - vel_body_right
      - vel_body_down
      - yawspeed_deg_s
    ui_category: velocity
    required_tracker_data: [POSITION_2D]
    optional_tracker_data: [BBOX_CONFIDENCE, VELOCITY_AWARE]
```

`required_fields` is the exact atomic command snapshot. Optional or partial
command fields are not supported because omitted values could otherwise retain
motion from an older command.

### Available Profiles

| Profile | Control Type | Use Case |
|---------|--------------|----------|
| mc_velocity_chase | velocity_body_offboard | Multicopter chase/pursuit mode |
| mc_velocity_position | velocity_body_offboard | Position-based velocity |
| mc_velocity_distance | velocity_body_offboard | Visual centering; forward velocity fixed at zero |
| mc_velocity_ground | velocity_body_offboard | Ground target tracking |
| mc_attitude_rate | attitude_rate | Aggressive rate-based control |
| fw_attitude_rate | attitude_rate | Fixed-wing control |
| gm_velocity_chase | velocity_body_offboard | Gimbal-based chase |
| gm_velocity_vector | velocity_body_offboard | Direct vector pursuit |

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
```

### Field Properties

| Property | Type | Description |
|----------|------|-------------|
| type | string | Runtime scalar type; currently only `float` is supported |
| unit | string | Unit of measurement |
| description | string | Human-readable description |
| default | number | Default value |
| clamp | boolean | Apply safety limits |
| limits | object | Fixed min/max limits |

Values for `type: float` must be finite Python `int` or `float` values. Boolean
values and numeric strings are rejected. Mapped flight-control limits come from
`Safety.GlobalLimits` / `Safety.FollowerOverrides` through the canonical mapping
in `classes.safety_types.FIELD_LIMIT_MAPPING`; `limit_name` is not a supported
field-schema property.

### Velocity Fields

```yaml
vel_body_fwd:
  type: float
  unit: "m/s"
  description: "Forward velocity (positive = forward)"
  default: 0.0
  clamp: true

vel_body_right:
  type: float
  unit: "m/s"
  description: "Lateral velocity (positive = right)"
  default: 0.0
  clamp: true

vel_body_down:
  type: float
  unit: "m/s"
  description: "Vertical velocity (positive = down)"
  default: 0.0
  clamp: true

yawspeed_deg_s:
  type: float
  unit: "deg/s"
  description: "Yaw rate (positive = clockwise)"
  default: 0.0
  clamp: true
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

`yawspeed_deg_s` is intentionally shared by `velocity_body_offboard` and
`attitude_rate`. The only additional exclusivity rule covers the
attitude-specific roll, pitch, and thrust fields:

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

The body-velocity field set does not need a separate validation rule. Each
profile's `control_type` and `required_fields` are the canonical routing and
exact field contract.

## MAVSDK Method Metadata

The PixEagle control type remains `velocity_body_offboard`, while the MAVSDK
Python method is `set_velocity_body`:

```yaml
control_types:
  velocity_body_offboard:
    mavsdk_method: set_velocity_body
```

There is no MAVSDK Python method named `set_velocity_body_offboard`.

## Usage in Code

### SetpointHandler

```python
from classes.setpoint_handler import SetpointHandler

# Create handler with profile
handler = SetpointHandler('mc_velocity_chase')

# Set one complete command snapshot
handler.set_fields({
    'vel_body_fwd': 3.0,
    'vel_body_right': 0.0,
    'vel_body_down': 0.0,
    'yawspeed_deg_s': 15.0,
}, source='docs_example')

# Get fields
fields = handler.get_fields()
# {'vel_body_fwd': 3.0, 'vel_body_right': 0.0, ...}

# Get control type
control_type = handler.get_control_type()
# 'velocity_body_offboard'
```

### Follower Integration

```python
class MCVelocityChaseFollower(BaseFollower):
    def __init__(self, px4_controller, initial_target_coords):
        # SetpointHandler is initialized by BaseFollower.__init__
        super().__init__(px4_controller, 'mc_velocity_chase')

    def follow_target(self, target):
        # Calculate velocities
        fwd_vel = self.calculate_forward_velocity(target)
        yaw_rate = self.calculate_yaw_rate(target)

        # Publish one complete command snapshot (clamped automatically)
        return self.set_command_fields({
            'vel_body_fwd': fwd_vel,
            'vel_body_right': 0.0,
            'vel_body_down': 0.0,
            'yawspeed_deg_s': yaw_rate,
        }, reason='mc_velocity_chase')
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
      - vel_body_right
      - vel_body_down
      - yawspeed_deg_s
    ui_category: velocity
    required_tracker_data: [POSITION_2D]
    optional_tracker_data: []
```

### Step 2: Verify Fields Exist

Ensure all required fields are defined in `command_fields`.

### Step 3: Use in Code

```python
handler = SetpointHandler('my_custom_profile')
```

## Schema Validation

SetpointHandler validates the complete file before caching any profile:

- supported schema version and required metadata
- finite, strictly typed defaults and valid fixed limits
- exact profile fields and declared control types
- required and optional tracker names against `TrackerDataType`
- migration aliases against active replacement profiles
- complete UI field/profile order and validation-rule references

Any malformed declaration fails schema loading; unknown tracker requirements
are never logged and omitted.

## Related Documentation

- [SetpointHandler Component](../02-components/setpoint-handler.md)
- [Control Types](../03-protocols/control-types.md)
- [Adding Control Types](../06-development/adding-control-types.md)
