# Schema System

> Profile and field definitions for followers

The schema system defines follower profiles, command fields, and control types in `configs/follower_commands.yaml`.

---

## Schema Structure

```yaml
# Field definitions
command_fields:
  vel_body_fwd:
    type: float
    default: 0.0
    unit: "m/s"
    description: "Body frame forward velocity"

# Profile definitions
follower_profiles:
  mc_velocity_chase:
    display_name: "MC Velocity Chase"
    control_type: "velocity_body_offboard"
    required_fields: [...]

# Control type definitions
control_types:
  velocity_body_offboard:
    mavsdk_method: "set_velocity_body_offboard"
    description: "Offboard body velocity commands"
```

---

## Command Fields

### Velocity Fields

```yaml
command_fields:
  vel_body_fwd:
    type: float
    default: 0.0
    unit: "m/s"
    description: "Body frame forward velocity"
    clamp: true

  vel_body_right:
    type: float
    default: 0.0
    unit: "m/s"
    description: "Body frame right velocity"
    clamp: true

  vel_body_down:
    type: float
    default: 0.0
    unit: "m/s"
    description: "Body frame down velocity (positive = descend)"
    clamp: true
```

### Rate Fields

```yaml
command_fields:
  yawspeed_deg_s:
    type: float
    default: 0.0
    unit: "deg/s"
    description: "Yaw rate"
    clamp: true

  rollspeed_deg_s:
    type: float
    default: 0.0
    unit: "deg/s"
    description: "Roll rate"
    clamp: true

  pitchspeed_deg_s:
    type: float
    default: 0.0
    unit: "deg/s"
    description: "Pitch rate"
    clamp: true
```

### Thrust Field

```yaml
command_fields:
  thrust:
    type: float
    default: 0.5
    unit: ""
    description: "Normalized thrust (0.0-1.0)"
    min: 0.0
    max: 1.0
    clamp: true
```

---

## Follower Profiles

### Profile Structure

```yaml
follower_profiles:
  profile_name:
    display_name: "Human-Readable Name"
    description: "Profile purpose and behavior"
    control_type: "velocity_body_offboard"
    required_fields: ["field1", "field2"]
    optional_fields: ["field3"]
    ui_category: "velocity"
    required_tracker_data: ["POSITION_2D"]
    optional_tracker_data: ["BBOX_CONFIDENCE"]
```

### Example: MC Velocity Chase

```yaml
mc_velocity_chase:
  display_name: "MC Velocity Chase"
  description: "Quadcopter chase with velocity ramping and dual-mode lateral guidance"
  control_type: "velocity_body_offboard"
  required_fields:
    - vel_body_fwd
    - vel_body_right
    - vel_body_down
  optional_fields:
    - yawspeed_deg_s
  ui_category: "velocity"
  required_tracker_data:
    - POSITION_2D
  optional_tracker_data:
    - BBOX_CONFIDENCE
    - VELOCITY_AWARE
```

### Example: FW Attitude Rate

```yaml
fw_attitude_rate:
  display_name: "FW Attitude Rate"
  description: "Fixed-wing with L1 navigation and TECS"
  control_type: "attitude_rate"
  required_fields:
    - rollspeed_deg_s
    - pitchspeed_deg_s
    - yawspeed_deg_s
    - thrust
  optional_fields: []
  ui_category: "attitude"
  required_tracker_data:
    - POSITION_2D
```

---

## Control Types

```yaml
control_types:
  velocity_body:
    mavsdk_method: "set_velocity_body"
    description: "Legacy body velocity commands"
    ui_display: "Body Velocity"

  velocity_body_offboard:
    mavsdk_method: "set_velocity_body_offboard"
    description: "Offboard body velocity commands"
    ui_display: "Body Velocity Offboard"

  attitude_rate:
    mavsdk_method: "set_attitude_rate"
    description: "Angular rate commands with thrust"
    ui_display: "Attitude Rate"
```

---

## Tracker Data Types

```yaml
tracker_data_types:
  POSITION_2D:
    description: "Normalized 2D position (-1 to +1)"

  POSITION_3D:
    description: "3D position with depth"

  GIMBAL_ANGLES:
    description: "Gimbal pan/tilt angles"

  BBOX_CONFIDENCE:
    description: "Bounding box with confidence score"

  VELOCITY_AWARE:
    description: "Target velocity estimation"
```

---

## SetpointHandler Usage

### Loading a Profile

```python
from classes.setpoint_handler import SetpointHandler

handler = SetpointHandler("mc_velocity_chase")

# Get profile info
print(handler.get_display_name())    # "MC Velocity Chase"
print(handler.get_control_type())    # "velocity_body_offboard"
```

### Setting Fields

```python
# Set with validation
handler.set_field("vel_body_fwd", 5.0)
handler.set_field("vel_body_right", -2.0)

# Get all fields
fields = handler.get_fields()
# {'vel_body_fwd': 5.0, 'vel_body_right': -2.0, 'vel_body_down': 0.0}
```

### Validation

```python
# Check profile consistency
valid = handler.validate_profile_consistency()

# Get telemetry
telemetry = handler.get_telemetry_data()
```

---

## Adding New Profiles

1. Add command fields (if new):

```yaml
command_fields:
  new_field:
    type: float
    default: 0.0
    unit: "m/s"
    description: "New field description"
```

2. Add profile:

```yaml
follower_profiles:
  new_profile:
    display_name: "New Profile"
    control_type: "velocity_body_offboard"
    required_fields: ["new_field", ...]
```

3. Register in FollowerFactory:

```python
FollowerFactory.register_follower('new_profile', NewFollowerClass)
```
