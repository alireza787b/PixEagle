# SetpointHandler

> Schema-driven command field management with validation and clamping.

**Source**: `src/classes/setpoint_handler.py` (~425 lines)

## Overview

SetpointHandler is the abstraction layer between followers and the autopilot interface. It provides:

- Schema-driven field definitions loaded from YAML
- Type validation and range clamping
- Profile-based field management
- Control type routing
- Autopilot-agnostic interface

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      SetpointHandler                             │
├─────────────────────────────────────────────────────────────────┤
│  Class Variables:                                                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ _schema_cache: Dict           # Cached YAML schema       │    │
│  │ _schema_file_path: str        # configs/follower_commands│    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Instance Variables:                                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ profile_name: str             # e.g., "mc_velocity_pos" │    │
│  │ fields: Dict[str, float]      # Current field values     │    │
│  │ profile_config: Dict          # Profile from schema      │    │
│  └─────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│  Key Methods:                                                    │
│  • set_fields({...}) → atomic command intent                   │
│  • set_field(name, value) → legacy single-field helper          │
│  • get_fields() → Dict[str, float]                              │
│  • get_control_type() → str                                     │
│  • reset_setpoints()                                             │
│  • validate_profile_consistency() → bool                        │
└─────────────────────────────────────────────────────────────────┘
```

## Schema Structure

The schema is loaded from `configs/follower_commands.yaml`:

```yaml
schema_version: "2.0.0"

follower_profiles:
  mc_velocity_chase:
    control_type: "velocity_body_offboard"
    display_name: "MC Velocity Chase"
    description: "Quadcopter chase using body velocity with forward ramp-up"
    required_fields:
      - vel_body_fwd
      - vel_body_right
      - vel_body_down
      - yawspeed_deg_s

  fw_attitude_rate:
    control_type: "attitude_rate"
    display_name: "FW Attitude Rate"
    description: "Angular rate control for fixed-wing"
    required_fields:
      - rollspeed_deg_s
      - pitchspeed_deg_s
      - yawspeed_deg_s
      - thrust

command_fields:
  vel_body_fwd:
    type: float
    unit: "m/s"
    description: "Forward velocity in body frame"
    default: 0.0
    clamp: true

  yawspeed_deg_s:
    type: float
    unit: "deg/s"
    description: "Yaw rotation rate"
    default: 0.0
    clamp: true

  thrust:
    type: float
    unit: "normalized"
    description: "Thrust 0.0-1.0"
    default: 0.5
    limits:
      min: 0.0
      max: 1.0
    clamp: true
```

## Initialization

```python
def __init__(self, profile_name: str):
    """
    Initialize with specified follower profile.

    Args:
        profile_name: Profile key (e.g., "mc_velocity_position")

    Raises:
        ValueError: If profile not in schema
        FileNotFoundError: If schema file missing
    """
    # Load schema if not cached
    if SetpointHandler._schema_cache is None:
        SetpointHandler._load_schema()

    self.profile_name = self.normalize_profile_name(profile_name)
    self._initialize_from_schema()
```

### normalize_profile_name()

```python
@staticmethod
def normalize_profile_name(profile_name: str) -> str:
    """
    Convert display name to schema key format.

    "MC Velocity Position" → "mc_velocity_position"
    """
    return profile_name.lower().replace(" ", "_")
```

## Field Management

### set_fields()

```python
def set_fields(self, field_values: Dict[str, float], *, source: str, reason: str | None = None) -> CommandIntent:
    """
    Atomically validate and apply one complete command field snapshot.

    The live setpoint state is changed only after every field is valid,
    finite, and within the active safety/schema limits. By default, every field
    in the active profile must be present so stale command values cannot carry
    over implicitly.
    """
```

Concrete followers should publish through `BaseFollower.set_command_fields()`,
which calls this method and records the accepted or rejected command intent in
telemetry.

### set_field()

```python
def set_field(self, field_name: str, value: float):
    """
    Set field value with validation and clamping.

    Args:
        field_name: Must be valid for current profile
        value: Numeric value to set

    Raises:
        ValueError: If field invalid or value out of range (when clamp=false)
    """
    # Validate field is in profile
    if field_name not in self.fields:
        raise ValueError(f"Field '{field_name}' not valid for profile")

    # Declared type validation rejects bool, strings, NaN, and infinity.
    numeric_value = validate_declared_command_value(
        field_name,
        value,
        self._schema_cache['command_fields'][field_name],
    )

    # Limit validation/clamping
    clamped_value = self._validate_field_limits(field_name, numeric_value)

    self.fields[field_name] = clamped_value
```

`set_field()` remains available for initialization and low-level tests. New
follower command output must use `set_fields()` through
`BaseFollower.set_command_fields()`.

### Limit Validation

```python
def _validate_field_limits(self, field_name: str, value: float) -> float:
    """
    Validate and clamp field value.

    Limit sources (priority order):
    1. Safety.GlobalLimits / Safety.FollowerOverrides through SafetyManager
    2. Schema-based limits for non-safety fields such as thrust

    Returns:
        Clamped value (or raises ValueError if clamp=false)
    """
```

The field-to-limit mapping is defined once in
`classes.safety_types.FIELD_LIMIT_MAPPING` and consumed by SetpointHandler and
the final command validator.

**Clamping Logic**:
```python
# Get limit from the shared command safety validator
max_limit = Parameters.get_effective_limit(limit_name, follower_name)
min_val = -max_limit
max_val = max_limit

# Apply clamping
if value < min_val:
    if clamp:
        logger.warning(f"Value {value} clamped to {min_val}")
        value = min_val
    else:
        raise ValueError(f"Value below minimum")
```

### get_fields()

```python
def get_fields(self) -> Dict[str, float]:
    """
    Get current field values.

    Returns:
        Copy of fields dict (safe for modification)
    """
    return self.fields.copy()
```

### reset_setpoints()

```python
def reset_setpoints(self):
    """
    Reset all fields to validated fail-closed fallback defaults and clear the
    last command intent.

    A concrete follower may configure selected fallback values from canonical
    runtime configuration before Offboard starts.
    """
    for field_name in self.fields:
        self.fields[field_name] = self._fallback_defaults[field_name]
    self._last_command_intent = None
```

## Profile Information

### get_control_type()

```python
def get_control_type(self) -> str:
    """
    Get control type for current profile.

    Returns:
        "velocity_body_offboard" | "attitude_rate"
    """
    control_type = self.profile_config.get('control_type')
    if control_type not in self._schema_cache['control_types']:
        raise ValueError("Unknown control type")
    return control_type
```

`get_mavsdk_dispatch_method()` resolves `control_types.<name>.mavsdk_method`
from the same validated YAML contract. Runtime code and test fixtures must not
maintain a second dispatch-method catalog.

### get_display_name()

```python
def get_display_name(self) -> str:
    """
    Get human-readable profile name.

    Returns:
        e.g., "MC Velocity Position"
    """
    return self.profile_config.get('display_name',
        self.profile_name.replace('_', ' ').title())
```

### get_available_profiles() (Class Method)

```python
@classmethod
def get_available_profiles(cls) -> List[str]:
    """
    Get all available profile names from schema.

    Returns:
        List of profile keys
    """
    return list(cls._schema_cache['follower_profiles'].keys())
```

## Circuit Breaker Integration

### get_fields_with_status()

```python
def get_fields_with_status(self) -> Dict[str, Any]:
    """
    Get fields with circuit breaker status metadata.

    Returns:
        {
            "setpoints": {...},
            "profile": "...",
            "circuit_breaker": {
                "active": bool,
                "status": "SAFE_MODE" | "LIVE_MODE",
                "commands_sent_to_px4": bool
            },
            "timestamp": "...",
            "control_type": "..."
        }
    """
```

## Validation

### validate_profile_consistency()

```python
def validate_profile_consistency(self) -> bool:
    """
    Validate profile against schema rules.

    Checks:
    - Attitude rate fields only with attitude_rate control type
    - Required fields present

    Returns:
        True if valid

    Raises:
        ValueError: If validation fails
    """
```

## Telemetry Export

### get_telemetry_data()

```python
def get_telemetry_data(self) -> Dict[str, Any]:
    """
    Get complete telemetry data for logging/broadcast.

    Returns:
        {
            'fields': {...},
            'profile_name': "...",
            'control_type': "...",
            'timestamp': "...",
            'last_command_intent': {
                'source': 'MCVelocityChaseFollower',
                'reason': 'normal_tracking',
                'fields': {...}
            }
        }
    """
```

## Usage Example

```python
# Initialize handler with profile
handler = SetpointHandler("mc_velocity_position")

# Set one complete command snapshot (follower calculates these)
intent = handler.set_fields({
    'vel_body_fwd': 2.5,      # m/s forward
    'vel_body_right': 0.0,    # no lateral
    'vel_body_down': -0.5,    # slight climb
    'yawspeed_deg_s': 15.0,   # deg/s yaw rate
}, source='docs_example')

# Get for dispatch
fields = handler.get_fields()
control_type = handler.get_control_type()

# OffboardCommander consumes the accepted intent and refreshes the MAVSDK setter.
offboard_commander.submit_intent(intent)
```

## Control Types Summary

| Control Type | MAVSDK Class | Use Case |
|-------------|--------------|----------|
| `velocity_body_offboard` | VelocityBodyYawspeed | Multicopter (primary) |
| `attitude_rate` | AttitudeRate | Fixed-wing, aggressive MC |

## Field Units

| Category | Fields | Unit | Notes |
|----------|--------|------|-------|
| Velocity | vel_body_fwd, vel_body_right, vel_body_down | m/s | Body frame |
| Angular Rate | yawspeed_deg_s, rollspeed_deg_s, pitchspeed_deg_s | deg/s | MAVSDK standard |
| Thrust | thrust | 0.0-1.0 | Normalized |

## Related Documentation

- [PX4InterfaceManager](px4-interface-manager.md) - Command dispatch
- [follower_commands.yaml](../05-configuration/follower-commands-schema.md) - Schema file
- [Control Types](../03-protocols/control-types.md) - Protocol details
