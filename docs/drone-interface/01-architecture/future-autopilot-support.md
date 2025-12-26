# Future Autopilot Support

> Brief note on architecture extensibility for ArduPilot and other autopilots.

## Current State

PixEagle currently supports **PX4** autopilot:
- **Commands**: MAVSDK offboard control (gRPC)
- **Telemetry**: MAVLink2REST (HTTP/REST) - primary and recommended
- **Protocol**: MAVLink 2.0

## Architecture Extensibility

The current design provides clear abstraction points that could support additional autopilots:

### Abstraction Points

| Component | Current | Abstraction Available |
|-----------|---------|----------------------|
| SetpointHandler | Autopilot-agnostic | ✅ YAML-defined control types |
| Control Types | PX4-specific dispatch | ✅ Could map to different protocols |
| MavlinkDataManager | MAVLink2REST endpoints | ⚠️ Endpoint paths are PX4-specific |
| PX4InterfaceManager | MAVSDK-specific | ⚠️ Would need interface abstraction |

### SetpointHandler Already Abstracted

The command field system is autopilot-agnostic:

```yaml
# Works for any autopilot that supports velocity control
follower_profiles:
  mc_velocity_offboard:
    control_type: "velocity_body_offboard"
    required_fields:
      - vel_body_fwd
      - vel_body_right
      - vel_body_down
      - yawspeed_deg_s
```

### Potential Interface Pattern

```python
# Future abstraction (not yet implemented)
class DroneInterface(ABC):
    """Abstract base for autopilot interfaces."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def send_velocity_command(
        self, fwd: float, right: float, down: float, yaw_rate: float
    ) -> None: ...

    @abstractmethod
    async def get_attitude(self) -> AttitudeData: ...

class PX4Interface(DroneInterface):
    """PX4 implementation using MAVSDK."""
    ...

class ArduPilotInterface(DroneInterface):
    """ArduPilot implementation (future)."""
    ...
```

## ArduPilot Considerations

Key differences that would need addressing:

| Aspect | PX4 | ArduPilot |
|--------|-----|-----------|
| Offboard Protocol | MAVSDK gRPC | MAVLink direct or DroneKit |
| Flight Modes | Offboard mode | Guided mode |
| Velocity Commands | SET_POSITION_TARGET_LOCAL_NED | SET_POSITION_TARGET_LOCAL_NED (similar) |
| Mode Codes | Different numeric values | Different numeric values |

## Implementation Scope

Full ArduPilot support would require:

1. **Interface Abstraction**: Extract `DroneInterface` base class
2. **Protocol Adapter**: MAVLink direct or DroneKit-Python
3. **Mode Mapping**: ArduPilot flight mode handling
4. **Telemetry Parsing**: Different MAVLink message formats
5. **Testing Infrastructure**: ArduPilot SITL integration

This is a significant effort and is **not currently planned**. The architecture notes here are for future reference.

## Current Recommendation

For now, focus on PX4 with the current architecture. The abstractions in place (SetpointHandler, control types) provide a foundation if ArduPilot support becomes needed.

## Related Documentation

- [Abstraction Layers](abstraction-layers.md) - Current interface patterns
- [PX4InterfaceManager](../02-components/px4-interface-manager.md) - Current implementation
