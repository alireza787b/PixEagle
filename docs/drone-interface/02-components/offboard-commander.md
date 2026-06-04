# OffboardCommander

> Async PX4 Offboard setpoint heartbeat owner.

**Source**: `src/classes/offboard_commander.py`

## Overview

`OffboardCommander` publishes MAVSDK Offboard setpoints at a fixed async cadence
that is independent of camera FPS, tracker latency, UI requests, and streaming
health. Followers do not send MAVSDK commands directly; they produce atomic
`CommandIntent` snapshots through `BaseFollower.set_command_fields(...)`.
`AppController` submits the accepted intent to `OffboardCommander`, and the
commander repeatedly calls `PX4InterfaceManager.send_commands_unified()`.

This closes the previous frame-loop-coupled publication path at the code level.
It is still unit/mock/integration evidence only until PX4-in-loop validation
lands under PXE-0018.

## Runtime Flow

```text
TrackerOutput
  -> Follower.follow_target()
  -> BaseFollower.set_command_fields(...)
  -> CommandIntent
  -> AppController._submit_current_command_intent_to_commander()
  -> OffboardCommander heartbeat loop
  -> PX4InterfaceManager.send_commands_unified()
  -> MAVSDK Offboard setpoint
```

## Freshness

`OFFBOARD_COMMAND_TTL_S` defines how long the latest follower command intent can
be reused. If no intent exists or the latest intent is stale, the commander
resets the active `SetpointHandler` to profile defaults before publishing.

For velocity-body profiles, the default setpoint is zero body velocity and zero
yaw rate. For attitude-rate profiles, the defaults come from
`configs/follower_commands.yaml`, including neutral angular rates and the
configured default thrust field.

## Configuration

```yaml
Setpoint:
  SETPOINT_PUBLISH_RATE_S: 0.1    # Legacy SetpointSender monitor period only
  OFFBOARD_COMMAND_RATE_HZ: 20.0  # MAVSDK Offboard heartbeat rate
  OFFBOARD_COMMAND_TTL_S: 0.5     # Intent freshness timeout
  OFFBOARD_COMMAND_FAILURE_THRESHOLD: 3  # Local failure policy threshold
```

`OFFBOARD_COMMAND_RATE_HZ`, `OFFBOARD_COMMAND_TTL_S`, and
`OFFBOARD_COMMAND_FAILURE_THRESHOLD` require a follower restart because they are
consumed when the commander is created.

## Failure Policy

Each failed `PX4InterfaceManager.send_commands_unified()` result, exception, or
commander dependency-validation failure increments `consecutive_failures`. A
successful publish resets that counter. When `consecutive_failures` reaches
`OFFBOARD_COMMAND_FAILURE_THRESHOLD`, the commander marks
`failure_policy_triggered`, changes health to `failed`, stops its local
heartbeat loop, and asks `AppController` to stop follow mode through the normal
Offboard disconnect path.

This is a local fail-closed policy: PixEagle stops claiming active command
publication and calls the local Offboard stop path. It does not prove PX4
accepted a final command or executed an aircraft failsafe; PX4-in-loop evidence
remains PXE-0018.

For operator-gated SITL validation,
`inject_publish_failures_for_validation()` can record bounded synthetic
failures inside the commander without publishing through MAVSDK. The
`/api/v1/sitl/injections/commander-publish-failure` route uses that hook to
cross the configured threshold and then lets AppController run the same
fail-closed cleanup path, including the normal Offboard stop request. This
proves PixEagle's local commander policy only; transport outage and PX4
failsafe behavior require separate PX4-in-loop evidence.

The `/api/v1/sitl/injections/mavsdk-disconnect` route uses the same commander
failure threshold after `PX4InterfaceManager` marks PixEagle's local MAVSDK
command path validation-disconnected. This makes the cleanup path record the
expected failed Offboard stop error while keeping PX4, Docker,
MavlinkAnywhere, MAVLink2REST, network interfaces, and MAVLink routes running.
It proves local PixEagle fail-closed behavior, not an external transport-loss
or PX4 failsafe event.

## Stop Behavior

On normal disconnect, `AppController._disconnect_px4_internal()` stops
`OffboardCommander` before calling `PX4InterfaceManager.stop_offboard_mode()`.
The commander performs a best-effort final default-setpoint publish while
Offboard is still active, then the PX4 Offboard mode is stopped.

## Status

`OffboardCommander.get_status()` reports:

- running/task state
- configured heartbeat rate and TTL
- latest intent age/freshness
- stale-intent reset count
- publish success/failure counts
- consecutive publish failures and threshold
- `health_state` (`running`, `degraded`, `failed`, `stopped`)
- local failure-policy reason and trigger count
- last publish result and error
- `sends_mavsdk_commands: true`
- `command_publication_source: offboard_commander`

The follower health API uses this status to avoid treating `following_active`
as healthy unless the commander exists and is running.

## Evidence Boundary

This component has unit/mock coverage for independent publication, stale intent
defaulting, rejected intents, publish failure telemetry, AppController routing,
local failure-policy stop behavior, and disconnect ordering. It does not by
itself prove PX4 SITL, HIL, or field behavior.
