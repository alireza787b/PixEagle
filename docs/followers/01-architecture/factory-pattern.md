# FollowerFactory Pattern

> Registry-based follower instantiation

`FollowerFactory` manages follower registration and creation using a registry pattern with lazy initialization.

**Source**: `src/classes/follower.py` (lines 9-223)

---

## Class Definition

```python
class FollowerFactory:
    """
    Schema-aware follower factory that dynamically manages follower modes
    based on the unified command schema.
    """

    # Class-level registry
    _follower_registry: Dict[str, Type] = {}
    _registry_initialized = False
```

---

## Naming Convention

Follower names follow the pattern: `{vehicle}_{control}_{behavior}`

| Prefix | Vehicle Type |
|--------|--------------|
| `mc_` | Multicopter |
| `fw_` | Fixed-Wing |
| `gm_` | Gimbal |

| Control Type | Description |
|--------------|-------------|
| `velocity` | Body velocity commands |
| `attitude_rate` | Angular rate commands |

| Behavior | Description |
|----------|-------------|
| `chase` | Pursuit mode |
| `ground` | Ground target tracking |
| `distance` | Distance maintenance |
| `position` | Position hold |
| `vector` | Direct vector pursuit |

---

## Registry Initialization

```python
@classmethod
def _initialize_registry(cls):
    """
    Lazy initialization to avoid circular imports.
    """
    if cls._registry_initialized:
        return

    # Primary registry (8 implementations)
    cls._follower_registry = {
        # Multicopter - Velocity Control
        'mc_velocity_chase': MCVelocityChaseFollower,
        'mc_velocity_ground': MCVelocityGroundFollower,
        'mc_velocity_distance': MCVelocityDistanceFollower,
        'mc_velocity_position': MCVelocityPositionFollower,

        # Multicopter - Attitude Rate
        'mc_attitude_rate': MCAttitudeRateFollower,

        # Fixed-Wing
        'fw_attitude_rate': FWAttitudeRateFollower,

        # Gimbal
        'gm_velocity_chase': GMVelocityChaseFollower,
        'gm_velocity_vector': GMVelocityVectorFollower,
    }

    cls._registry_initialized = True
```

---

## Deprecated Aliases

For backward compatibility, old names map to new implementations:

```python
_deprecated_aliases = {
    'ground_view': 'mc_velocity_ground',
    'constant_distance': 'mc_velocity_distance',
    'constant_position': 'mc_velocity_position',
    'attitude_rate': 'mc_attitude_rate',
    'chase_follower': 'mc_attitude_rate',
    'body_velocity_chase': 'mc_velocity_chase',
    'gimbal_unified': 'gm_velocity_chase',
    'gm_velocity_unified': 'gm_velocity_chase',
    'gimbal_vector_body': 'gm_velocity_vector',
    'fixed_wing': 'fw_attitude_rate',
    'multicopter': 'mc_velocity_chase',
    'multicopter_attitude_rate': 'mc_attitude_rate',
}
```

Using deprecated names raises a `ValueError` with a migration hint:

```
ValueError: Follower mode 'ground_view' has been removed.
Use 'mc_velocity_ground' instead.
```

---

## Key Methods

### create_follower

```python
@classmethod
def create_follower(cls, profile_name: str, px4_controller, initial_target_coords):
    """
    Create follower instance for the specified profile.

    Args:
        profile_name: Follower profile name
        px4_controller: PX4 controller instance
        initial_target_coords: Initial target (x, y)

    Returns:
        BaseFollower: Follower instance

    Raises:
        ValueError: If profile invalid or no implementation
    """
```

### register_follower

```python
@classmethod
def register_follower(cls, profile_name: str, follower_class: Type) -> bool:
    """
    Register a new follower implementation.

    Validates:
    - Profile exists in schema
    - Class has required methods

    Returns:
        bool: True if successful
    """
```

### get_available_modes

```python
@classmethod
def get_available_modes(cls) -> List[str]:
    """
    Returns primary mode names only (excludes deprecated aliases).

    Returns:
        ['mc_velocity_chase', 'mc_velocity_ground', 'fw_attitude_rate', ...]
    """
```

### get_follower_info

```python
@classmethod
def get_follower_info(cls, profile_name: str) -> Dict[str, Any]:
    """
    Returns detailed profile information.

    Includes:
    - Schema info (display_name, description, control_type)
    - Implementation info (class name, availability)
    """
```

---

## Follower Manager

The `Follower` class wraps `FollowerFactory` for runtime management:

```python
class Follower:
    """
    Unified interface for drone control using schema-aware
    follower implementations.
    """

    def __init__(self, px4_controller, initial_target_coords):
        self.mode = Parameters.FOLLOWER_MODE
        self.follower = FollowerFactory.create_follower(
            self.mode, px4_controller, initial_target_coords
        )
```

### Mode Switching

```python
def switch_mode(self, new_mode: str, preserve_target_coords: bool = True) -> bool:
    """
    Switch to different follower mode at runtime.

    Args:
        new_mode: New mode name
        preserve_target_coords: Keep current target

    Returns:
        bool: True if successful
    """
```

### Telemetry

```python
def get_follower_telemetry(self) -> Dict[str, Any]:
    """
    Aggregate telemetry from current follower.

    Adds manager-level info:
    - manager_mode
    - manager_status
    - available_modes
    - implementation_class
    """
```

---

## Usage Example

### Standard Usage

```python
from classes.follower import Follower

# Create with configured mode
follower_manager = Follower(px4_controller, (0.0, 0.0))

# Follow target
result = follower_manager.follow_target(tracker_output)

# Get telemetry
telemetry = follower_manager.get_follower_telemetry()
```

### Direct Factory Usage

```python
from classes.follower import FollowerFactory

# Get available modes
modes = FollowerFactory.get_available_modes()
# ['mc_velocity_chase', 'mc_velocity_ground', ...]

# Create specific follower
chase_follower = FollowerFactory.create_follower(
    'mc_velocity_chase',
    px4_controller,
    (0.0, 0.0)
)

# Get mode info
info = FollowerFactory.get_follower_info('mc_velocity_chase')
# {
#     'display_name': 'MC Velocity Chase',
#     'control_type': 'velocity_body_offboard',
#     'implementation_available': True,
#     'implementation_class': 'MCVelocityChaseFollower'
# }
```

### Custom Follower Registration

```python
from classes.followers.base_follower import BaseFollower
from classes.follower import FollowerFactory

class CustomFollower(BaseFollower):
    def calculate_control_commands(self, tracker_data):
        # Custom logic
        pass

    def follow_target(self, tracker_data):
        # Custom behavior
        return True

# Register (requires matching schema profile)
FollowerFactory.register_follower('custom_mode', CustomFollower)
```

---

## Validation Flow

```
create_follower(profile_name)
       │
       ▼
_initialize_registry()         # Lazy load if needed
       │
       ▼
normalize_profile_name()       # Case normalization
       │
       ▼
Check deprecated aliases       # Raise ValueError with migration hint if old name
       │
       ▼
Validate profile in schema     # SetpointHandler.get_available_profiles()
       │
       ▼
Check implementation exists    # In _follower_registry
       │
       ▼
Instantiate follower class     # follower_class(px4_controller, coords)
```

---

## Error Handling

```python
# Invalid profile
FollowerFactory.create_follower('nonexistent', px4, (0, 0))
# ValueError: Invalid follower profile 'nonexistent'.
#             Available profiles: ['mc_velocity_chase', ...]

# No implementation
FollowerFactory.create_follower('schema_only_profile', px4, (0, 0))
# ValueError: No implementation found for profile 'schema_only_profile'.
#             Available implementations: [...]
```
