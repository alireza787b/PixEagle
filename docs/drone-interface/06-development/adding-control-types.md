# Adding Control Types

This guide covers how to add new control types to the drone interface.

## Overview

Control types define how PixEagle commands the drone. Adding a new control type involves:

1. Defining command fields in the schema
2. Creating a follower profile
3. Implementing the MAVSDK dispatch
4. Testing the new type

## Step 1: Define Command Fields

### Edit follower_commands.yaml

```yaml
# configs/follower_commands.yaml

command_fields:
  # Add new fields
  my_new_field:
    type: float
    unit: "m/s"
    description: "Description of the field"
    default: 0.0
    clamp: true
    limit_name: "MAX_MY_FIELD"  # Reference to Parameters
```

### Field Properties

| Property | Required | Description |
|----------|----------|-------------|
| type | Yes | Data type (float, int) |
| unit | Yes | Unit string for documentation |
| description | Yes | Human-readable description |
| default | Yes | Default value |
| clamp | No | Apply safety limits |
| limit_name | No | Parameter name for dynamic limit |
| limits | No | Fixed min/max limits |

### Example: Position Hold Fields

```yaml
command_fields:
  # Existing velocity fields...

  # New position fields
  pos_ned_north:
    type: float
    unit: "m"
    description: "North position in NED frame"
    default: 0.0
    clamp: false

  pos_ned_east:
    type: float
    unit: "m"
    description: "East position in NED frame"
    default: 0.0
    clamp: false

  pos_ned_down:
    type: float
    unit: "m"
    description: "Down position in NED frame (negative = up)"
    default: 0.0
    clamp: true
    limit_name: "MAX_ALTITUDE"
```

## Step 2: Create Follower Profile

### Add Profile Definition

```yaml
# configs/follower_commands.yaml

follower_profiles:
  # Existing profiles...

  mc_position_hold:
    control_type: position_ned_offboard
    display_name: "MC Position Hold"
    description: "NED position control for multicopters"
    required_fields:
      - pos_ned_north
      - pos_ned_east
      - pos_ned_down
      - yaw_deg
    optional_fields: []
```

### Profile Naming Convention

Format: `{platform}_{mode}_{variant}`

- Platform: `mc` (multicopter), `fw` (fixed-wing), `gm` (gimbal mode)
- Mode: `velocity`, `position`, `attitude`
- Variant: Optional descriptor

## Step 3: Implement MAVSDK Dispatch

### Update PX4InterfaceManager

```python
# src/classes/px4_interface_manager.py

class PX4InterfaceManager:

    async def send_offboard_command(self, control_type: str, fields: dict):
        """Send offboard command based on control type."""

        if control_type == 'velocity_body_offboard':
            await self._send_velocity_body(fields)

        elif control_type == 'attitude_rate':
            await self._send_attitude_rate(fields)

        elif control_type == 'position_ned_offboard':
            # New control type
            await self._send_position_ned(fields)

        else:
            raise ValueError(f"Unknown control type: {control_type}")

    async def _send_position_ned(self, fields: dict):
        """Send position NED command."""
        from mavsdk.offboard import PositionNedYaw

        position = PositionNedYaw(
            north_m=fields.get('pos_ned_north', 0.0),
            east_m=fields.get('pos_ned_east', 0.0),
            down_m=fields.get('pos_ned_down', 0.0),
            yaw_deg=fields.get('yaw_deg', 0.0)
        )

        await self.drone.offboard.set_position_ned(position)
```

### MAVSDK Offboard Types

| Control Type | MAVSDK Class | Import |
|--------------|--------------|--------|
| velocity_body_offboard | VelocityBodyYawspeed | `mavsdk.offboard` |
| attitude_rate | AttitudeRate | `mavsdk.offboard` |
| position_ned_offboard | PositionNedYaw | `mavsdk.offboard` |
| velocity_ned_offboard | VelocityNedYaw | `mavsdk.offboard` |

## Step 4: Create Follower Class

### Implement New Follower

```python
# src/classes/followers/mc_position_follower.py

from classes.followers.base_follower import BaseFollower
from classes.setpoint_handler import SetpointHandler


class MCPositionFollower(BaseFollower):
    """Position-based target following."""

    def __init__(self):
        super().__init__()
        self.setpoint_handler = SetpointHandler('mc_position_hold')

    def follow_target(self, target_data: dict):
        """Follow target using position commands."""
        # Calculate position setpoint
        north, east, down = self.calculate_position(target_data)
        yaw = self.calculate_yaw(target_data)

        # Set fields
        self.setpoint_handler.set_field('pos_ned_north', north)
        self.setpoint_handler.set_field('pos_ned_east', east)
        self.setpoint_handler.set_field('pos_ned_down', down)
        self.setpoint_handler.set_field('yaw_deg', yaw)

    def get_control_type(self) -> str:
        return self.setpoint_handler.get_control_type()

    def get_command_fields(self) -> dict:
        return self.setpoint_handler.get_fields()
```

### Register in Factory

```python
# src/classes/followers/follower_factory.py

from classes.followers.mc_position_follower import MCPositionFollower

FOLLOWER_REGISTRY = {
    # Existing followers...
    'mc_position_follower': MCPositionFollower,
}
```

## Step 5: Add Safety Limits

### Update Parameters

```python
# src/classes/parameters.py

# New safety limits
MAX_ALTITUDE = 50.0  # meters
MAX_HORIZONTAL_DISTANCE = 100.0  # meters
```

### Update Config Schema

```yaml
# configs/config_default.yaml

safety:
  # Existing limits...
  max_altitude: 50.0
  max_horizontal_distance: 100.0
```

## Step 6: Testing

### Unit Tests

```python
# tests/unit/drone_interface/test_position_control.py

import pytest
from unittest.mock import patch, MagicMock


class TestPositionControlType:
    """Tests for position control type."""

    def test_position_profile_loads(self):
        """Test position profile is valid."""
        from classes.setpoint_handler import SetpointHandler

        handler = SetpointHandler('mc_position_hold')

        assert handler.get_control_type() == 'position_ned_offboard'

    def test_position_fields_set(self):
        """Test position fields can be set."""
        from classes.setpoint_handler import SetpointHandler

        handler = SetpointHandler('mc_position_hold')
        handler.set_field('pos_ned_north', 10.0)
        handler.set_field('pos_ned_east', 5.0)

        fields = handler.get_fields()
        assert fields['pos_ned_north'] == 10.0
        assert fields['pos_ned_east'] == 5.0
```

### Integration Tests

```python
# tests/integration/drone_interface/test_position_flow.py

@pytest.mark.asyncio
async def test_position_command_dispatched():
    """Test position command reaches MAVSDK."""
    # Mock MAVSDK
    mock_drone = MagicMock()
    mock_drone.offboard.set_position_ned = AsyncMock()

    # Create manager with mock
    manager = PX4InterfaceManager(drone=mock_drone)

    # Send position command
    await manager.send_offboard_command(
        'position_ned_offboard',
        {'pos_ned_north': 10.0, 'pos_ned_east': 5.0, 'pos_ned_down': -2.0}
    )

    # Verify dispatch
    mock_drone.offboard.set_position_ned.assert_called_once()
```

## Validation Checklist

Before merging a new control type:

- [ ] Fields defined in `follower_commands.yaml`
- [ ] Profile created with all required fields
- [ ] MAVSDK dispatch implemented in PX4InterfaceManager
- [ ] Follower class created and registered
- [ ] Safety limits added if needed
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Tested with SITL
- [ ] Documentation updated

## Related Documentation

- [Control Types Reference](../03-protocols/control-types.md)
- [SetpointHandler Component](../02-components/setpoint-handler.md)
- [MAVSDK Offboard API](../03-protocols/mavsdk-offboard.md)
