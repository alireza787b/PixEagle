# SafetyManager

> Centralized safety limits for all followers

**Source**: `src/classes/safety_manager.py`

---

## Overview

SafetyManager is a singleton that provides:

- Global velocity/rate/altitude limits
- Per-follower limit overrides
- Dynamic limit access for BaseFollower
- Configuration hot-reload support

---

## Singleton Access

```python
from classes.safety_manager import get_safety_manager

# Get the singleton instance
safety_manager = get_safety_manager()

# Access limits
velocity_limits = safety_manager.get_velocity_limits('MC_VELOCITY_CHASE')
altitude_limits = safety_manager.get_altitude_limits()
```

---

## Data Classes

### VelocityLimits

```python
class VelocityLimits(NamedTuple):
    forward: float        # Max forward velocity (m/s)
    lateral: float        # Max lateral velocity (m/s)
    vertical: float       # Max vertical velocity (m/s)
    max_magnitude: float  # Overall magnitude limit (m/s)
```

### AltitudeLimits

```python
class AltitudeLimits(NamedTuple):
    """Altitude limits in meters."""
    min_altitude: float        # MIN_ALTITUDE
    max_altitude: float        # MAX_ALTITUDE
    warning_buffer: float      # ALTITUDE_WARNING_BUFFER
    safety_enabled: bool = True
```

### RateLimits

```python
class RateLimits(NamedTuple):
    """Rate limits in rad/s (converted from deg/s in config)."""
    yaw: float    # MAX_YAW_RATE in rad/s
    pitch: float  # MAX_PITCH_RATE in rad/s
    roll: float   # MAX_ROLL_RATE in rad/s
```

### FollowerLimits

```python
class FollowerLimits(NamedTuple):
    velocity: VelocityLimits
    altitude: AltitudeLimits
    rates: RateLimits
    behavior: SafetyBehavior
    vehicle_type: VehicleType
```

---

## Configuration Loading

SafetyManager loads from `config.yaml`:

```yaml
Safety:
  GlobalLimits:
    # Velocity
    MAX_VELOCITY_FORWARD: 10.0
    MAX_VELOCITY_LATERAL: 5.0
    MAX_VELOCITY_VERTICAL: 3.0

    # Rate (converted to rad/s internally)
    MAX_YAW_RATE: 45.0      # deg/s in config
    MAX_PITCH_RATE: 30.0
    MAX_ROLL_RATE: 60.0

    # Altitude
    MIN_ALTITUDE: 5.0
    MAX_ALTITUDE: 120.0
    ALTITUDE_WARNING_BUFFER: 5.0
    USE_HOME_RELATIVE_ALTITUDE: true
```

---

## Per-Follower Overrides

Followers can have custom limits:

```yaml
Safety:
  FollowerOverrides:
    MC_VELOCITY_CHASE:
      MAX_VELOCITY_FORWARD: 12.0   # Higher than global
      MAX_VELOCITY_VERTICAL: 4.0

    FW_ATTITUDE_RATE:
      MAX_VELOCITY_FORWARD: 30.0   # Much higher for fixed-wing

    GM_VELOCITY_CHASE:
      MAX_VELOCITY_FORWARD: 8.0    # Lower for gimbal mode
```

---

## API Methods

### get_velocity_limits

```python
def get_velocity_limits(self, follower_name: str = None) -> VelocityLimits:
    """
    Get velocity limits, optionally with per-follower overrides.

    Args:
        follower_name: Config section name (e.g., 'MC_VELOCITY_CHASE')

    Returns:
        VelocityLimits with overrides applied
    """
```

### get_altitude_limits

```python
def get_altitude_limits(self, follower_name: str = None) -> AltitudeLimits:
    """
    Get altitude limits, optionally with per-follower overrides applied.

    Args:
        follower_name: Config section name (e.g., 'MC_VELOCITY_CHASE').
                       If None, returns global limits.
    """
```

### get_rate_limits

```python
def get_rate_limits(self) -> RateLimits:
    """Get rate limits in rad/s."""
```

### reload_config

```python
def reload_config(self) -> bool:
    """
    Reload limits from config file.

    Called on config changes for hot-reload.
    Returns True if successful.
    """
```

---

## Integration with BaseFollower

BaseFollower accesses limits via properties:

```python
class BaseFollower(ABC):
    @property
    def velocity_limits(self):
        """Get velocity limits from SafetyManager (v5.0.0+: single source of truth)."""
        return self.safety_manager.get_velocity_limits(self._follower_config_name)

    @property
    def altitude_limits(self):
        """Dynamic altitude limits from SafetyManager."""
        if self.safety_manager:
            return self.safety_manager.get_altitude_limits()
        return self._legacy_altitude_limits

    @property
    def rate_limits(self):
        """Dynamic rate limits from SafetyManager."""
        if self.safety_manager:
            return self.safety_manager.get_rate_limits()
        return self._legacy_rate_limits
```

---

## Velocity Clamping

BaseFollower provides automatic clamping:

```python
def clamp_velocity(self, vel_fwd, vel_right, vel_down):
    """Clamp velocities to SafetyManager limits."""
    limits = self.velocity_limits

    clamped_fwd = np.clip(vel_fwd, -limits.forward, limits.forward)
    clamped_right = np.clip(vel_right, -limits.lateral, limits.lateral)
    clamped_down = np.clip(vel_down, -limits.vertical, limits.vertical)

    return clamped_fwd, clamped_right, clamped_down
```

---

## Safety Check

```python
def check_safety(self) -> SafetyStatus:
    """
    Centralized safety check — validates altitude and velocity limits.

    Returns:
        SafetyStatus: NamedTuple with .safe (bool), .reason (str),
                      .action (SafetyAction), .details (Optional[Dict])

    Use SafetyStatus.ok() classmethod to create a passing result.
    """
```

---

## Field-to-Limit Mapping

SetpointHandler uses `_FIELD_TO_LIMIT_NAME` to resolve which limit applies to each field:

```python
'yawspeed_deg_s': 'MAX_YAW_RATE',
'pitchspeed_deg_s': 'MAX_PITCH_RATE',
'rollspeed_deg_s': 'MAX_ROLL_RATE',
```

---

## Warning Zones

Altitude warning before hitting limits:

```python
def check_altitude_warning(self) -> bool:
    """Check if in warning zone (near limits)."""
    current = self.px4_controller.current_altitude
    limits = self.altitude_limits
    buffer = limits.warning_buffer

    near_min = current < (limits.min_altitude + buffer)
    near_max = current > (limits.max_altitude - buffer)

    if near_min or near_max:
        logger.warning(f"Altitude {current}m near limits")
        return True

    return False
```

---

## Thread Safety

SafetyManager is thread-safe:

```python
class SafetyManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
```

---

## v5.0.0 Requirement

SafetyManager is required in v5.0.0+. If `get_safety_manager()` cannot be
imported, `BaseFollower.__init__` raises `RuntimeError`:

    RuntimeError: SafetyManager is required in v5.0.0+. Check your imports.

There is no fallback mode. Ensure `src/classes/safety_manager.py` is present.
