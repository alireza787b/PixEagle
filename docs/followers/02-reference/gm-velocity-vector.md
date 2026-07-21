# GM Velocity Vector Follower

`gm_velocity_vector` converts fresh external gimbal angles directly into a
body-frame velocity intent. It is intended for a status-aware gimbal provider,
such as the current `topotek_sip_udp` provider, and does not consume image
bounding boxes.

| Contract | Value |
| --- | --- |
| Profile | `gm_velocity_vector` |
| Tracker input | `TrackerDataType.GIMBAL_ANGLES` |
| Command schema | `velocity_body_offboard` |
| Implementation | `src/classes/followers/gm_velocity_vector_follower.py` |

## Control Path

The follower applies mount calibration and sign corrections, filters the input
angles, converts them to a body-frame unit vector, ramps the commanded speed,
and then applies the shared safety envelope. Body axes use PX4 FRD convention:
forward, right, down.

Two lateral modes are supported through the shared follower configuration:

- `sideslip`: publish body-right velocity and zero yaw rate;
- `coordinated_turn`: zero body-right velocity and turn toward the target using
  the shared yaw smoothing pipeline.

The checked-in profile override selects `sideslip`. Vertical velocity remains
zero while `ENABLE_ALTITUDE_CONTROL` is false.

## Configuration

Use the current grouped config contracts. Maximum velocity, altitude, and rate
limits do not belong in `GM_VELOCITY_VECTOR`; they come from the canonical
`Safety` section.

```yaml
Follower:
  FOLLOWER_MODE: gm_velocity_vector
  General:
    ENABLE_ALTITUDE_CONTROL: false
  FollowerOverrides:
    GM_VELOCITY_VECTOR:
      LATERAL_GUIDANCE_MODE: sideslip
      ALTITUDE_CHECK_INTERVAL: 1.0

GM_VELOCITY_VECTOR:
  MOUNT_TYPE: HORIZONTAL          # HORIZONTAL | VERTICAL | TILTED_45
  RAMP_ACCELERATION: 0.25
  INITIAL_VELOCITY: 0.0
  YAW_RATE_GAIN: 0.5
  ANGLE_DEADZONE_DEG: 2.0
  ANGLE_SMOOTHING_ALPHA: 0.7
  ENABLE_VELOCITY_DECAY: true
  VELOCITY_DECAY_RATE: 0.5
  MOUNT_ROLL_OFFSET_DEG: 0.0
  MOUNT_PITCH_OFFSET_DEG: 0.0
  MOUNT_YAW_OFFSET_DEG: 0.0
  INVERT_GIMBAL_ROLL: false
  INVERT_GIMBAL_PITCH: false
  INVERT_GIMBAL_YAW: false

Safety:
  GlobalLimits:
    MAX_VELOCITY: 1.0
    MAX_VELOCITY_FORWARD: 0.5
    MAX_VELOCITY_LATERAL: 0.5
    MAX_VELOCITY_VERTICAL: 0.5
```

`Safety.FollowerOverrides.GM_VELOCITY_VECTOR` may tighten the global envelope;
it cannot raise it. Change the global limits only after validating the vehicle,
site, coordinate signs, and mount geometry.

## Freshness And Target Loss

The follower accepts commands only from a fresh, active, usable gimbal tracker
output. A stale angle sample may remain visible for diagnostics, but the tracker
marks it inactive and unusable for following. The follower then emits a bounded
zero/hold intent instead of continuing an old pursuit vector. Velocity decay is
used only inside the configured target-loss handling boundary.

## Bring-Up Order

1. Keep `FOLLOWER_CIRCUIT_BREAKER: true`.
2. Confirm the provider is connected and reports fresh tracking-status packets.
3. Verify yaw, pitch, and roll signs while the vehicle cannot move.
4. Verify `MOUNT_TYPE`, offsets, and inversion flags against the physical mount.
5. Confirm stale or lost tracking produces an unusable output and zero/hold
   intent.
6. Validate telemetry, Offboard transitions, and command bounds in SIH/SITL or
   HIL before any separately approved field test.

Unit and tracker-in-loop tests cover vector normalization, stale-input
fail-closed behavior, command schema, and provider freshness. They do not prove
the client camera address, vendor firmware behavior, network delivery, PX4
response, or aircraft safety.

See [Gimbal Tracker](../../trackers/02-reference/gimbal-tracker.md) for the
provider contract and [Follower Command Schema](../../drone-interface/05-configuration/follower-commands-schema.md)
for the published intent fields.
