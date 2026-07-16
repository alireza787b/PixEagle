# SetpointHandler

> Schema-aware configuration and command field management

`SetpointHandler` loads follower profiles from the YAML schema and provides type-safe field access with automatic validation and clamping.

**Source**: `src/classes/setpoint_handler.py`

---

## Class Definition

```python
class SetpointHandler:
    """
    Schema-aware setpoint handler that loads follower profiles and field
    definitions from the unified command schema YAML file.
    """

    # Class-level schema cache
    _schema_cache: Optional[Dict[str, Any]] = None
    _schema_file_path = "configs/follower_commands.yaml"
```

---

## Constructor

```python
def __init__(self, profile_name: str):
    """
    Args:
        profile_name: Profile key (e.g., "mc_velocity_chase")

    Raises:
        ValueError: If profile not found
        FileNotFoundError: If schema file missing
    """
```

### Initialization Flow

1. Load schema (cached at class level)
2. Normalize profile name
3. Initialize fields and fallback values with schema defaults
4. Let concrete followers replace profile-dependent fallback values from their
   canonical runtime config before Offboard startup

---

## Schema Loading

### _load_schema (class method)

```python
@classmethod
def _load_schema(cls):
    """
    Load follower_commands.yaml into class-level cache.
    Called once on first SetpointHandler creation.
    """
```

### get_available_profiles (class method)

```python
@classmethod
def get_available_profiles(cls) -> List[str]:
    """Returns all profile names from schema."""
    # ['mc_velocity_chase', 'mc_velocity_ground', 'fw_attitude_rate', ...]
```

### get_profile_info (class method)

```python
@classmethod
def get_profile_info(cls, profile_name: str) -> Dict[str, Any]:
    """Returns complete profile configuration."""
    # {
    #     'display_name': 'MC Velocity Chase',
    #     'control_type': 'velocity_body_offboard',
    #     'required_fields': [...],
    #     ...
    # }
```

---

## Field Management

### configure_fallback_defaults

Concrete followers use `configure_fallback_defaults(...)` for values that
cannot have a universal safe schema default. Updates are validated and atomic.
The shipped attitude-rate followers source thrust from
`MC_ATTITUDE_RATE.HOVER_THRUST` or `FW_ATTITUDE_RATE.CRUISE_THRUST`; stale or
missing command intents reset to those values with neutral angular rates.

### set_fields

```python
def set_fields(self, field_values: Dict[str, float], *, source: str, reason: str | None = None) -> CommandIntent:
    """
    Atomically validate and apply one complete command snapshot.

    Every field in the active profile is required by default. The live setpoint
    state is not changed unless all fields pass validation and clamping.
    """
```

Concrete followers should call `BaseFollower.set_command_fields()`, which wraps
this method and records command-intent metadata.

### set_field

```python
def set_field(self, field_name: str, value: float):
    """
    Set field value with validation and clamping.

    Args:
        field_name: Must be in profile's required/optional fields
        value: Numeric value to set

    Raises:
        ValueError: If field not valid for profile
        ValueError: If value invalid and clamp=false
    """
```

`set_field()` is a compatibility helper for low-level cases. New follower
command output should not build commands one field at a time.

### get_fields

```python
def get_fields(self) -> Dict[str, float]:
    """Returns copy of all current field values."""
```

### reset_setpoints

```python
def reset_setpoints(self):
    """Reset all fields to schema-defined defaults."""
```

---

## Limit Validation

### Field-to-Limit Mapping

```python
_FIELD_TO_LIMIT_NAME = {
    'vel_body_fwd': 'MAX_VELOCITY_FORWARD',
    'vel_body_right': 'MAX_VELOCITY_LATERAL',
    'vel_body_down': 'MAX_VELOCITY_VERTICAL',
    'yawspeed_deg_s': 'MAX_YAW_RATE',
    'pitchspeed_deg_s': 'MAX_PITCH_RATE',
    'rollspeed_deg_s': 'MAX_ROLL_RATE',
}
```

### _validate_field_limits

```python
def _validate_field_limits(self, field_name: str, value: float) -> float:
    """
    Validate and clamp field value.

    Priority:
    1. Runtime limits from SafetyManager.get_velocity_limits()
    2. Schema-based limits (e.g., thrust 0.0-1.0)

    If clamp=true (default): Clamp and warn
    If clamp=false: Raise ValueError
    """
```

Example:

```python
# MAX_VELOCITY_FORWARD = 10.0 in config
handler.set_fields({
    'vel_body_fwd': 15.0,
    'vel_body_right': 0.0,
    'vel_body_down': 0.0,
    'yawspeed_deg_s': 0.0,
}, source='docs_example')
# WARNING: Value 15.0 for field 'vel_body_fwd' above max 10.0; clamped to 10.0.
```

---

## Profile Information

### get_control_type

```python
def get_control_type(self) -> str:
    """Returns: 'velocity_body_offboard' or 'attitude_rate'."""
```

### get_display_name

```python
def get_display_name(self) -> str:
    """Returns human-readable name (e.g., 'MC Velocity Chase')"""
```

### get_description

```python
def get_description(self) -> str:
    """Returns profile description from schema."""
```

---

## Telemetry

### get_telemetry_data

```python
def get_telemetry_data(self) -> Dict[str, Any]:
    """
    Returns comprehensive telemetry data.

    {
        'fields': {'vel_body_fwd': 5.0, ...},
        'profile_name': 'MC Velocity Chase',
        'control_type': 'velocity_body_offboard',
        'timestamp': '2024-01-15T12:00:00.000000',
        'last_command_intent': {'source': '...', 'reason': '...', 'fields': {...}}
    }
    """
```

### get_fields_with_status

```python
def get_fields_with_status(self) -> Dict[str, Any]:
    """
    Returns fields with circuit breaker status.

    {
        'setpoints': {...},
        'profile': 'mc_velocity_chase',
        'circuit_breaker': {
            'active': True/False,
            'status': 'SAFE_MODE'/'LIVE_MODE',
            'commands_sent_to_px4': True/False
        },
        'timestamp': '...',
        'control_type': '...'
    }
    """
```

---

## Validation

### validate_profile_consistency

```python
def validate_profile_consistency(self) -> bool:
    """
    Validate profile against schema rules.

    Checks:
    - Attitude rate fields only with attitude_rate control type
    - Velocity fields with velocity control types

    Returns: True if valid
    Raises: ValueError if invalid
    """
```

---

## Utility Methods

### normalize_profile_name (static)

```python
@staticmethod
def normalize_profile_name(profile_name: str) -> str:
    """
    Convert display name to schema key.

    'MC Velocity Chase' -> 'mc_velocity_chase'
    """
```

### report

```python
def report(self) -> str:
    """Generate human-readable status report."""
```

---

## Schema Structure

The schema file (`configs/follower_commands.yaml`) defines:

### Command Fields

```yaml
command_fields:
  vel_body_fwd:
    type: float
    default: 0.0
    unit: "m/s"
    description: "Body frame forward velocity"
    clamp: true
```

### Follower Profiles

```yaml
follower_profiles:
  mc_velocity_chase:
    display_name: "MC Velocity Chase"
    description: "Quadcopter chase using body velocity"
    control_type: "velocity_body_offboard"
    required_fields: ["vel_body_fwd", "vel_body_right", "vel_body_down", "yawspeed_deg_s"]
    ui_category: "velocity"
    required_tracker_data: ["POSITION_2D"]
    optional_tracker_data: ["BBOX_CONFIDENCE", "VELOCITY_AWARE"]
```

### Control Types

```yaml
control_types:
  velocity_body_offboard:
    mavsdk_method: "set_velocity_body"
    description: "Offboard body velocity commands"
    ui_display: "Body Velocity Offboard"
```

---

## Usage Example

```python
# Create handler for specific profile
handler = SetpointHandler("mc_velocity_chase")

# Get profile info
print(handler.get_display_name())  # "MC Velocity Chase"
print(handler.get_control_type())  # "velocity_body_offboard"

# Set one complete command value snapshot (validated and clamped)
handler.set_fields({
    "vel_body_fwd": 5.0,
    "vel_body_right": -2.0,
    "vel_body_down": 0.5,
    "yawspeed_deg_s": 0.0,
}, source="example", reason="normal_tracking")

# Get all values
fields = handler.get_fields()
# {'vel_body_fwd': 5.0, 'vel_body_right': -2.0, 'vel_body_down': 0.5}

# Reset to defaults
handler.reset_setpoints()

# Telemetry
telemetry = handler.get_telemetry_data()
```

---

## Integration with BaseFollower

BaseFollower initializes SetpointHandler in its constructor:

```python
class BaseFollower(ABC):
    def __init__(self, px4_controller, profile_name: str):
        self.setpoint_handler = SetpointHandler(profile_name)
        self.px4_controller.setpoint_handler = self.setpoint_handler

    def set_command_fields(self, field_values: Dict[str, float], *, reason: str | None = None) -> bool:
        """Wrapper that publishes one atomic, validated command intent."""
        try:
            self.setpoint_handler.set_fields(
                field_values,
                source=self.__class__.__name__,
                reason=reason,
            )
            return True
        except ValueError as e:
            logger.warning(f"Command intent rejected: {e}")
            return False
```
