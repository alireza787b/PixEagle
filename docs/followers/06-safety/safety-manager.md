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
@dataclass
class AltitudeLimits:
    min_altitude: float       # Minimum safe altitude (m)
    max_altitude: float       # Maximum altitude (m)
    warning_buffer: float     # Warning zone buffer (m)
    home_relative: bool       # Use home-relative altitude
```

### RateLimits

```python
@dataclass
class RateLimits:
    yaw: float    # Max yaw rate (rad/s)
    pitch: float  # Max pitch rate (rad/s)
    roll: float   # Max roll rate (rad/s)
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
def get_altitude_limits(self) -> AltitudeLimits:
    """Get altitude limits (no per-follower overrides)."""
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

BaseFollower caches limits via properties:

```python
class BaseFollower(ABC):
    @property
    def velocity_limits(self):
        """Dynamic velocity limits from SafetyManager."""
        if self.safety_manager:
            return self.safety_manager.get_velocity_limits(
                self._follower_config_name
            )
        return self._legacy_velocity_limits

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

## Altitude Safety Check

```python
def check_altitude_safety(self) -> bool:
    """
    Check if current altitude is within limits.

    Returns:
        True if safe, False if violation
    """
    current = self.px4_controller.current_altitude
    limits = self.altitude_limits

    if current < limits.min_altitude:
        logger.critical(f"Below minimum altitude: {current}m")
        return False

    if current > limits.max_altitude:
        logger.critical(f"Above maximum altitude: {current}m")
        return False

    return True
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

## Fallback Behavior

If SafetyManager unavailable, followers use legacy limits:

```python
# In BaseFollower.__init__
try:
    from classes.safety_manager import get_safety_manager
    self.safety_manager = get_safety_manager()
except ImportError:
    logger.warning("SafetyManager not available, using legacy limits")
    self.safety_manager = None
    self._legacy_velocity_limits = VelocityLimits(...)
```
