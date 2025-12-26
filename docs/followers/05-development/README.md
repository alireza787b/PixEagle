# Follower Development Guide

> Creating and testing custom followers

This section covers developing new followers for PixEagle.

---

## Documents

| Document | Description |
|----------|-------------|
| [Creating Followers](creating-followers.md) | Step-by-step guide |
| [Testing Followers](testing-followers.md) | Testing methodology |
| [Best Practices](best-practices.md) | Code standards |

---

## Quick Start

### 1. Create Follower Class

```python
# src/classes/followers/my_custom_follower.py

from classes.followers.base_follower import BaseFollower
from classes.tracker_output import TrackerOutput

class MyCustomFollower(BaseFollower):
    def __init__(self, px4_controller, initial_target_coords):
        super().__init__(px4_controller, "my_custom_profile")
        # Custom initialization

    def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
        # Compute and set commands
        pass

    def follow_target(self, tracker_data: TrackerOutput) -> bool:
        # Execute following
        self.calculate_control_commands(tracker_data)
        return True
```

### 2. Add Schema Profile

```yaml
# configs/follower_commands.yaml

follower_profiles:
  my_custom_profile:
    display_name: "My Custom Follower"
    control_type: "velocity_body_offboard"
    required_fields: ["vel_body_fwd", "vel_body_right"]
```

### 3. Register with Factory

```python
# src/classes/follower.py

from classes.followers.my_custom_follower import MyCustomFollower

# In FollowerFactory._initialize_registry()
cls._follower_registry['my_custom_profile'] = MyCustomFollower
```

### 4. Add Configuration

```yaml
# configs/config_default.yaml

MY_CUSTOM:
  PARAM_ONE: 1.0
  PARAM_TWO: true
```

---

## Required Methods

Every follower must implement:

```python
def calculate_control_commands(self, tracker_data: TrackerOutput) -> None:
    """Compute setpoints from tracker data."""

def follow_target(self, tracker_data: TrackerOutput) -> bool:
    """Execute following behavior. Returns success status."""
```

---

## Development Workflow

```
1. Design           → Define control strategy
2. Schema           → Add profile to YAML
3. Implement        → Create follower class
4. Register         → Add to factory
5. Configure        → Add parameters
6. Test SITL        → Validate in simulation
7. Test Real        → Field testing
8. Document         → Update docs
```
