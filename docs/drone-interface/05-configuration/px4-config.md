# PX4 Configuration

This document covers the current PX4 connection keys used by PixEagle. The
source of truth is `configs/config_default.yaml` and the generated
`configs/config_schema.yaml`.

## Configuration Location

```yaml
PX4:
  EXTERNAL_MAVSDK_SERVER: true
  SYSTEM_ADDRESS: udp://127.0.0.1:14540
  MAVSDK_CONNECTION_TIMEOUT_S: 15.0
```

## System Address

`PX4.SYSTEM_ADDRESS` is passed to MAVSDK:

```python
await drone.connect(system_address=Parameters.SYSTEM_ADDRESS)
```

Common values:

| Setup | `PX4.SYSTEM_ADDRESS` |
|-------|----------------------|
| PixEagle with current MavlinkAnywhere defaults | `udp://127.0.0.1:14540` |
| Direct PX4 SITL SDK endpoint | `udp://127.0.0.1:14540` |
| Serial USB direct connection | `serial:///dev/ttyUSB0:921600` |
| MAVLink TCP server | `tcp://127.0.0.1:5760` |

Older docs used `udp://:14541` for a custom router split. That is not the
current default. If a deployment still uses that topology, record it in the
deployment notes and update the router config and `PX4.SYSTEM_ADDRESS`
together.

`PX4.MAVSDK_CONNECTION_TIMEOUT_S` bounds both link setup and vehicle discovery.
PixEagle does not report a connection until MAVSDK's connection-state stream
reports `is_connected`. Increase the timeout only for a measured slow startup or
transport; do not use it to hide a routing failure.

## External MAVSDK Server

```yaml
PX4:
  EXTERNAL_MAVSDK_SERVER: true
```

When enabled, PixEagle creates the MAVSDK Python `System` with the external
server at `localhost:50051`. The launcher can start the downloaded MAVSDK
server binary unless `bash scripts/run.sh -k` is used.

## Offboard Rate

Offboard command timing is configured under `Setpoint`:

```yaml
Setpoint:
  SETPOINT_PUBLISH_RATE_S: 0.1    # Legacy SetpointSender monitor period
  OFFBOARD_COMMAND_RATE_HZ: 20.0  # PixEagle application setpoint refresh rate
  OFFBOARD_COMMAND_TTL_S: 0.5     # CommandIntent freshness timeout
  OFFBOARD_COMMAND_FAILURE_THRESHOLD: 3  # Local publish-failure threshold
```

`OffboardCommander` owns application-level MAVSDK setter calls independently of
frame processing. MAVSDK separately retransmits its latest accepted setpoint at
an implementation-owned cadence for PX4 Offboard proof-of-life. `SetpointSender` is monitor-only and
does not publish MAVSDK commands. If consecutive commander publish failures reach
`OFFBOARD_COMMAND_FAILURE_THRESHOLD`, PixEagle marks the commander failed and
stops local follow mode through the normal Offboard disconnect path. This is
unit/mock evidence only until PXE-0018 adds PX4-in-loop validation.

## Safety Limits

Flight-control command limits are configured under:

```yaml
Safety:
  GlobalLimits:
    MAX_VELOCITY: 1.0
    MAX_VELOCITY_FORWARD: 0.5
    MAX_VELOCITY_LATERAL: 0.5
    MAX_VELOCITY_VERTICAL: 0.5
    MAX_YAW_RATE: 45.0
```

## Circuit Breaker

The current test guard is top-level:

```yaml
FOLLOWER_CIRCUIT_BREAKER: true
CIRCUIT_BREAKER_DISABLE_SAFETY: false
```

`FOLLOWER_CIRCUIT_BREAKER: true` logs follower/PX4 commands instead of sending
them. It does not suppress MAVSDK connection discovery or telemetry. Treat it as
a development/test guard, not a replacement for PX4 failsafes or a proven
flight safety system.

## Related Documentation

- [MAVLink configuration](mavlink-config.md)
- [Safety integration](safety-integration.md)
- [MavlinkAnywhere integration](../04-infrastructure/mavlink-anywhere.md)
