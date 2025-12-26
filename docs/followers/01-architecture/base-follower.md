# BaseFollower Abstract Class

> Core foundation for all follower implementations

`BaseFollower` is the abstract base class that all follower implementations inherit from. It provides centralized safety management, schema-aware setpoint handling, and common utilities.

**Source**: `src/classes/followers/base_follower.py` (1,142 lines)

---

## Class Definition

```python
class BaseFollower(ABC):
    """
    Enhanced abstract base class for different follower modes.

    Provides:
    - Schema-aware setpoint management
    - Type-safe field access
    - Centralized safety limits
    - Rate-limited logging
    """
```

---

## Constructor

```python
def __init__(self, px4_controller, profile_name: str):
    """
    Args:
        px4_controller: PX4Controller instance for vehicle commands
        profile_name: Schema profile name (e.g., "mc_velocity_chase")
    """
```

### Initialization Sequence

1. **SetpointHandler** - Load profile from schema
2. **Telemetry metadata** - Initialize tracking info
3. **Rate-limited logging** - Prevent log spam (5s interval)
4. **Error aggregator** - Summary reports (10s interval)
5. **SafetyManager** - Load limits from config

---

## Abstract Methods

### calculate_control_commands

```python
@abstractmethod
def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
    """
    Calculate control commands from tracker data.

    Must update SetpointHandler with computed values.
    Called at tracker update rate (~20Hz).
    """
    pass
```

### follow_target

```python
@abstractmethod
def follow_target(self, tracker_data: TrackerOutput) -> bool:
    """
    Execute following behavior.

    Returns:
        bool: True if successful, False otherwise
    """
    pass
```

---

## Schema-Aware Methods

### get_control_type

```python
def get_control_type(self) -> str:
    """Returns control type: 'velocity_body', 'velocity_body_offboard', or 'attitude_rate'"""
```

### get_available_fields

```python
def get_available_fields(self) -> List[str]:
    """Returns list of command fields for this profile."""
    # Example: ['vel_body_fwd', 'vel_body_right', 'vel_body_down', 'yawspeed_deg_s']
```

### set_command_field

```python
def set_command_field(self, field_name: str, value: float) -> bool:
    """
    Set a command field with validation.

    Args:
        field_name: Field from schema (e.g., 'vel_body_fwd')
        value: Value to set

    Returns:
        bool: True if successful
    """
```

### get_all_command_fields

```python
def get_all_command_fields(self) -> Dict[str, float]:
    """Returns all current command field values."""
```

---

## Safety Management

### Safety Integration (v3.5.0+)

BaseFollower integrates with the centralized SafetyManager:

```python
# Initialized during construction
if SAFETY_MANAGER_AVAILABLE:
    self.safety_manager = get_safety_manager()
    self._follower_config_name = self._derive_follower_config_name()
```

### Dynamic Safety Properties

Safety limits are dynamic properties that read fresh from SafetyManager:

```python
@property
def velocity_limits(self):
    """Get velocity limits - dynamic from SafetyManager or fallback."""
    if self.safety_manager:
        return self.safety_manager.get_velocity_limits(self._follower_config_name)
    return self._legacy_velocity_limits

@property
def altitude_limits(self):
    """Get altitude limits - dynamic from SafetyManager."""
    # Same pattern

@property
def rate_limits(self):
    """Get rate limits - dynamic from SafetyManager."""
    # Same pattern
```

### clamp_velocity

```python
def clamp_velocity(self, vel_fwd: float, vel_right: float, vel_down: float) -> tuple:
    """
    Clamp velocity components to configured limits.

    Returns:
        tuple: (clamped_fwd, clamped_right, clamped_down)
    """
```

Example:

```python
# Configured limits: forward=10, lateral=5, vertical=3
clamped = self.clamp_velocity(15.0, 8.0, 5.0)
# Returns: (10.0, 5.0, 3.0)
```

### clamp_rate

```python
def clamp_rate(self, rate_value: float, rate_type: str = 'yaw') -> float:
    """
    Clamp angular rate to limits.

    Args:
        rate_value: Rate in rad/s
        rate_type: 'yaw', 'pitch', or 'roll'
    """
```

### check_safety

```python
def check_safety(self) -> SafetyStatus:
    """
    Centralized safety check.

    Validates:
    - Altitude bounds
    - Velocity magnitude
    - Violation counting

    Rate-limited to 20Hz.
    """
```

---

## Rate-Limited Logging

### RateLimitedLogger

Prevents log spam in high-frequency control loops:

```python
class RateLimitedLogger:
    def __init__(self, interval: float = 5.0):
        """Log same message at most once per interval."""

    def log_rate_limited(self, logger_instance, level, key, message) -> bool:
        """Returns True if message was logged."""
```

Usage in BaseFollower:

```python
self._rate_limiter = RateLimitedLogger(interval=5.0)

# In control loop
self._rate_limiter.log_rate_limited(
    logger, 'warning',
    'velocity_clamp',
    f"Velocity clamped: {original} -> {clamped}"
)
```

### ErrorAggregator

Reports error summaries periodically:

```python
class ErrorAggregator:
    def __init__(self, report_interval: float = 10.0):
        """Report error summary every interval."""

    def record_error(self, error_key: str, logger_instance=None):
        """Record error occurrence, log summary when interval elapsed."""
```

---

## Tracker Compatibility

### get_required_tracker_data_types

```python
def get_required_tracker_data_types(self) -> List[TrackerDataType]:
    """
    Returns required tracker data types from schema.

    Reads 'required_tracker_data' from profile config.
    """
```

### validate_tracker_compatibility

```python
def validate_tracker_compatibility(self, tracker_data: TrackerOutput) -> bool:
    """
    Check if tracker data is compatible with this follower.

    Uses schema manager for advanced compatibility checking.
    """
```

### extract_target_coordinates

```python
def extract_target_coordinates(self, tracker_data: TrackerOutput) -> Optional[Tuple[float, float]]:
    """
    Extract 2D coordinates from tracker data.

    Priority:
    1. position_2d
    2. position_3d (take x, y)
    3. None if no compatible data
    """
```

---

## PID Utility

### _update_pid_gains_from_config

```python
def _update_pid_gains_from_config(self, pid_controller, axis: str, profile_name: str):
    """
    Update PID controller gains from Parameters.PID_GAINS.

    Eliminates code duplication across followers.

    Args:
        pid_controller: CustomPID instance
        axis: 'yawspeed_deg_s', 'vel_body_down', etc.
        profile_name: For logging
    """
```

---

## Telemetry

### get_follower_telemetry

```python
def get_follower_telemetry(self) -> Dict[str, Any]:
    """
    Returns comprehensive telemetry data.

    Includes:
    - All command fields
    - Profile information
    - Metadata (init time, control type)
    - Validation status
    """
```

---

## Circuit Breaker Integration

### log_follower_event

```python
def log_follower_event(self, event_type: str, **event_data):
    """
    Log events for debugging and testing.

    When circuit breaker active, commands logged but not executed.
    """
```

### is_circuit_breaker_active

```python
def is_circuit_breaker_active(self) -> bool:
    """Check if in testing mode (commands logged, not executed)."""
```

---

## Legacy Compatibility

### follow_target_legacy

```python
def follow_target_legacy(self, target_coords: Tuple[float, float]) -> bool:
    """
    For old code using tuple coordinates.

    Creates minimal TrackerOutput and calls follow_target().
    """
```

### latest_velocities property

```python
@property
def latest_velocities(self) -> Dict[str, Any]:
    """Legacy property for old code accessing velocity data."""
```

---

## Config Name Derivation

### _derive_follower_config_name

```python
def _derive_follower_config_name(self) -> str:
    """
    Convert class name to config section name.

    MCVelocityChaseFollower -> MC_VELOCITY_CHASE
    FWAttitudeRateFollower -> FW_ATTITUDE_RATE
    """
```

---

## Usage Example

```python
class MCVelocityChaseFollower(BaseFollower):
    def __init__(self, px4_controller, initial_target_coords):
        super().__init__(px4_controller, "mc_velocity_chase")
        # Custom initialization

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        # Extract target position
        coords = self.extract_target_coordinates(tracker_data)
        if coords is None:
            return

        # Compute velocity command
        vel_fwd = self._compute_forward_velocity(coords)

        # Set with schema validation
        self.set_command_field("vel_body_fwd", vel_fwd)

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        if not self.validate_tracker_compatibility(tracker_data):
            return False

        self.calculate_control_commands(tracker_data)
        return True
```
