# Best Practices

> Code standards and guidelines for follower development

---

## Code Organization

### File Structure

```python
"""
Module docstring with:
- Purpose
- Key features
- Author info
"""

# Standard library imports
import logging
import time
from typing import Tuple, Dict, Any

# Third-party imports
import numpy as np

# PixEagle imports
from classes.followers.base_follower import BaseFollower
from classes.parameters import Parameters

# Module setup
logger = logging.getLogger(__name__)


class MyFollower(BaseFollower):
    """Class docstring."""

    # Class constants
    SOME_CONSTANT = 1.0

    def __init__(self, ...):
        """Constructor."""

    # Private methods (underscore prefix)
    def _initialize_components(self):
        pass

    # Abstract method implementations
    def calculate_control_commands(self, ...):
        pass

    def follow_target(self, ...):
        pass

    # Public utility methods
    def get_status(self):
        pass
```

---

## Naming Conventions

### Variables

```python
# Good: descriptive, snake_case
forward_velocity = 5.0
target_coords = (0.1, -0.2)
pid_controller = CustomPID(...)

# Bad: ambiguous, inconsistent
v = 5.0
tc = (0.1, -0.2)
pidCtrl = CustomPID(...)
```

### Methods

```python
# Good: verb prefix, descriptive
def calculate_control_commands(self, ...):
def get_velocity_limits(self):
def _initialize_pid_controllers(self):

# Bad: ambiguous
def commands(self, ...):
def limits(self):
def init(self):
```

### Constants

```python
# Good: UPPER_SNAKE_CASE
MAX_VELOCITY = 10.0
DEFAULT_UPDATE_RATE = 20.0

# Bad: mixed case
maxVelocity = 10.0
default_update_rate = 20.0
```

---

## Error Handling

### Use Specific Exceptions

```python
# Good
def __init__(self, px4_controller, coords):
    if not self.validate_target_coordinates(coords):
        raise ValueError(f"Invalid coordinates: {coords}")

    try:
        self._initialize_pid()
    except KeyError as e:
        raise RuntimeError(f"PID configuration missing: {e}")
```

### Fail Safely

```python
def calculate_control_commands(self, tracker_data):
    try:
        # Control logic
        pass
    except Exception as e:
        logger.error(f"Control calculation failed: {e}")
        # Safe fallback
        self.reset_command_fields()
```

### Use Rate-Limited Logging

```python
# Good: prevents log spam at 20Hz
self._rate_limiter.log_rate_limited(
    logger, 'warning', 'velocity_clamp',
    f"Velocity clamped: {vel}"
)

# Bad: logs every iteration
logger.warning(f"Velocity clamped: {vel}")
```

---

## Safety First

### Always Use SafetyManager Limits

```python
# Good: respects SafetyManager
vel_fwd = min(vel_fwd, self.velocity_limits.forward)
vel_clamped = self.clamp_velocity(vel_fwd, vel_right, vel_down)

# Bad: hardcoded limits
vel_fwd = min(vel_fwd, 10.0)
```

### Check Altitude Safety

```python
def follow_target(self, tracker_data):
    # Check safety before proceeding (returns SafetyStatus NamedTuple)
    status = self.check_safety()
    if not status.safe:
        logger.error(f"Safety violation: {status.reason}")
        return False

    # ... rest of logic
```

### Implement Emergency Stop

```python
def activate_emergency_stop(self):
    self.emergency_stop_active = True
    self.set_command_field('vel_body_fwd', 0.0)
    self.set_command_field('vel_body_right', 0.0)
    self.set_command_field('vel_body_down', 0.0)
    logger.critical("Emergency stop activated")
```

---

## Configuration

### Load from Parameters

```python
# Good: configurable
config = getattr(Parameters, 'MY_FOLLOWER', {})
self.max_velocity = config.get('MAX_VELOCITY', 5.0)

# Bad: hardcoded
self.max_velocity = 5.0
```

### Provide Sensible Defaults

```python
# Good: safe default if missing
self.timeout = config.get('TIMEOUT', 2.0)  # Default 2 seconds

# Bad: no default
self.timeout = config['TIMEOUT']  # KeyError if missing
```

---

## Testing

### Write Tests First (TDD)

```python
def test_centered_target_zero_velocity():
    """Target at center should produce zero lateral velocity."""
    # Arrange
    follower = MyFollower(mock_px4, (0, 0))
    tracker_data = TrackerOutput(position_2d=(0.0, 0.0))

    # Act
    follower.calculate_control_commands(tracker_data)

    # Assert
    fields = follower.get_all_command_fields()
    assert abs(fields['vel_body_right']) < 0.01
```

### Test Edge Cases

- Target at frame edges
- Zero velocity
- Maximum velocity
- Target loss
- Invalid input

---

## Documentation

### Docstrings

```python
def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
    """
    Calculate velocity commands from tracker data.

    Uses PID control to center target in frame. Applies velocity
    clamping from SafetyManager limits.

    Args:
        tracker_data: Structured tracker output with position

    Note:
        Sets vel_body_fwd, vel_body_right, vel_body_down fields
        via SetpointHandler.
    """
```

### Inline Comments

```python
# Calculate error from image center
error_x = 0.0 - target_x  # Positive error = target is right

# PID output is lateral velocity
vel_right = self.pid_lateral(error_x)

# Clamp to safety limits
vel_right = max(-self.velocity_limits.lateral,
                min(vel_right, self.velocity_limits.lateral))
```

---

## Performance

### Cache Expensive Calculations

```python
# Good: compute once
self._degrees = math.degrees  # Cache function reference

# In loop
yaw_deg = self._degrees(yaw_rad)
```

### Avoid Repeated Attribute Access

```python
# Good: local variable
limits = self.velocity_limits
clamped_fwd = min(vel_fwd, limits.forward)
clamped_right = min(vel_right, limits.lateral)

# Bad: repeated access
clamped_fwd = min(vel_fwd, self.velocity_limits.forward)
clamped_right = min(vel_right, self.velocity_limits.lateral)
```

---

## Checklist

Before submitting a new follower:

- [ ] Inherits from BaseFollower
- [ ] Implements calculate_control_commands()
- [ ] Implements follow_target()
- [ ] Has schema profile in follower_commands.yaml
- [ ] Registered in FollowerFactory
- [ ] Has configuration section in config_default.yaml
- [ ] Uses SafetyManager limits
- [ ] Has unit tests
- [ ] Tested in SITL
- [ ] Has docstrings
- [ ] Follows naming conventions
