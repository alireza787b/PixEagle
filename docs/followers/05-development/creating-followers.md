# Creating New Followers

> Step-by-step guide to implementing custom followers

---

## Step 1: Design Your Control Strategy

Before coding, answer:

1. **What vehicle type?** MC, FW, or Gimbal
2. **What control type?** velocity_body, velocity_body_offboard, attitude_rate
3. **What tracker data needed?** POSITION_2D, GIMBAL_ANGLES, etc.
4. **What algorithm?** PID, PN, L1, custom

---

## Step 2: Create the Schema Profile

Add to `configs/follower_commands.yaml`:

```yaml
follower_profiles:
  my_follower:
    display_name: "My Custom Follower"
    description: "Brief description of behavior"
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
```

---

## Step 3: Implement the Follower Class

Create `src/classes/followers/my_follower.py`:

```python
"""
My Custom Follower Module
=========================

Description of what this follower does.
"""

from classes.followers.base_follower import BaseFollower
from classes.followers.custom_pid import CustomPID
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging
from typing import Tuple, Dict, Any

logger = logging.getLogger(__name__)


class MyFollower(BaseFollower):
    """
    Custom follower implementation.

    Describe the control strategy and use cases.
    """

    def __init__(self, px4_controller, initial_target_coords: Tuple[float, float]):
        """
        Initialize the follower.

        Args:
            px4_controller: PX4 controller instance
            initial_target_coords: Initial target position
        """
        # Initialize base class with profile name
        super().__init__(px4_controller, "my_follower")

        # Validate initial coordinates
        if not self.validate_target_coordinates(initial_target_coords):
            raise ValueError(f"Invalid coordinates: {initial_target_coords}")

        self.initial_target_coords = initial_target_coords

        # Load configuration
        config = getattr(Parameters, 'MY_FOLLOWER', {})
        self.param_one = config.get('PARAM_ONE', 1.0)
        self.param_two = config.get('PARAM_TWO', True)

        # Initialize PID controllers
        self._initialize_pid()

        # Update telemetry metadata
        self.update_telemetry_metadata('follower_type', 'my_follower')

        logger.info("MyFollower initialized successfully")

    def _initialize_pid(self) -> None:
        """Initialize PID controllers."""
        try:
            gains = Parameters.PID_GAINS['vel_body_fwd']
            self.pid_fwd = CustomPID(
                gains['p'], gains['i'], gains['d'],
                setpoint=0.0,
                output_limits=(-self.velocity_limits.forward,
                              self.velocity_limits.forward)
            )
        except Exception as e:
            logger.error(f"PID initialization failed: {e}")
            raise RuntimeError(f"PID init failed: {e}")

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        """
        Calculate control commands from tracker data.

        Args:
            tracker_data: Structured tracker output
        """
        try:
            # Extract target coordinates
            coords = self.extract_target_coordinates(tracker_data)
            if not coords:
                logger.warning("No valid coordinates")
                return

            target_x, target_y = coords

            # Compute control commands
            error_x = 0.0 - target_x  # Target center
            error_y = 0.0 - target_y

            vel_fwd = self.pid_fwd(error_y)
            vel_right = 0.0  # Custom logic here

            # Clamp velocities
            vel_fwd, vel_right, vel_down = self.clamp_velocity(
                vel_fwd, vel_right, 0.0
            )

            # Set command fields
            self.set_command_field('vel_body_fwd', vel_fwd)
            self.set_command_field('vel_body_right', vel_right)
            self.set_command_field('vel_body_down', 0.0)

            logger.debug(f"Commands: fwd={vel_fwd:.2f}, right={vel_right:.2f}")

        except Exception as e:
            logger.error(f"Control calculation failed: {e}")
            self.reset_command_fields()

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        """
        Execute target following.

        Args:
            tracker_data: Tracker output

        Returns:
            bool: True if successful
        """
        try:
            # Validate tracker compatibility
            if not self.validate_tracker_compatibility(tracker_data):
                return False

            # Calculate and apply commands
            self.calculate_control_commands(tracker_data)

            return True

        except Exception as e:
            logger.error(f"Follow failed: {e}")
            self.reset_command_fields()
            return False

    def get_status(self) -> Dict[str, Any]:
        """Return follower status for telemetry."""
        return {
            'type': 'my_follower',
            'param_one': self.param_one,
            'commands': self.get_all_command_fields()
        }
```

---

## Step 4: Register with Factory

Edit `src/classes/follower.py`:

```python
# Add import
from classes.followers.my_follower import MyFollower

# In FollowerFactory._initialize_registry()
@classmethod
def _initialize_registry(cls):
    if cls._registry_initialized:
        return

    cls._follower_registry = {
        # ... existing entries ...
        'my_follower': MyFollower,  # Add this
    }

    cls._registry_initialized = True
```

---

## Step 5: Add Configuration

Add to `configs/config_default.yaml`:

```yaml
# My Custom Follower Configuration
MY_FOLLOWER:
  PARAM_ONE: 1.0
  PARAM_TWO: true
  MAX_VELOCITY: 5.0
```

---

## Step 6: Add PID Gains (if needed)

```yaml
PID_GAINS:
  # ... existing gains ...
  my_follower_axis:
    p: 2.0
    i: 0.1
    d: 0.3
```

---

## Step 7: Test

### Unit Test

```python
# tests/test_my_follower.py

import pytest
from classes.followers.my_follower import MyFollower
from classes.tracker_output import TrackerOutput, TrackerDataType

class MockPX4Controller:
    pass

def test_initialization():
    px4 = MockPX4Controller()
    follower = MyFollower(px4, (0.0, 0.0))
    assert follower is not None

def test_follow_target():
    px4 = MockPX4Controller()
    follower = MyFollower(px4, (0.0, 0.0))

    tracker_data = TrackerOutput(
        data_type=TrackerDataType.POSITION_2D,
        position_2d=(0.1, -0.1)
    )

    result = follower.follow_target(tracker_data)
    assert result == True
```

### SITL Test

```bash
# Start SITL
make px4_sitl gazebo

# Run PixEagle with your follower
FOLLOWER_MODE=my_follower bash run_pixeagle.sh
```

---

## Common Patterns

### Using Base Class Utilities

```python
# Extract coordinates
coords = self.extract_target_coordinates(tracker_data)

# Validate coordinates
if not self.validate_target_coordinates(coords):
    return

# Clamp velocities
clamped = self.clamp_velocity(vel_fwd, vel_right, vel_down)

# Set command fields
self.set_command_field('vel_body_fwd', vel_fwd)

# Rate-limited logging
self._rate_limiter.log_rate_limited(
    logger, 'info', 'status', f"Status: {status}"
)
```

### Accessing Safety Limits

```python
# Velocity limits (from SafetyManager)
max_fwd = self.velocity_limits.forward
max_lat = self.velocity_limits.lateral
max_vert = self.velocity_limits.vertical

# Altitude limits
min_alt = self.altitude_limits.min_altitude
max_alt = self.altitude_limits.max_altitude

# Rate limits
max_yaw = self.rate_limits.yaw  # rad/s
```

### Custom Telemetry

```python
def get_telemetry(self) -> Dict[str, Any]:
    return {
        **self.get_follower_telemetry(),  # Base telemetry
        'custom_field': self.custom_value,
        'status': self.get_status()
    }
```
