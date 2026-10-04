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

The follower applies the shared camera mounting geometry to raw measurements,
validates the resulting body-frame line of sight, filters that unit vector,
ramps the commanded speed using bounded monotonic time,
and then applies the shared safety envelope. Body axes use PX4 FRD convention:
forward, right, down.

Two lateral modes are supported through the shared follower configuration:

- `sideslip`: publish body-right velocity and zero yaw rate;
- `coordinated_turn`: zero body-right velocity and turn toward the target using
  the shared yaw smoothing pipeline.

Fresh defaults select `coordinated_turn` and enable altitude guidance for this
gimbal follower, subject to SafetyManager limits. Explicit saved sideslip choices
are preserved. Vertical velocity remains zero while `ENABLE_ALTITUDE_CONTROL`
is false or its direction is altitude-limited.

## Configuration

Use the current grouped config contracts. Maximum velocity, altitude, and rate
limits do not belong in `GM_VELOCITY_VECTOR`; they come from the canonical
`Safety` section.

Unknown `GimbalTracker.MOUNT_TYPE` values reject initialization. The shared
geometry contract supports the qualified Horizontal and base-pitched-up 90°
Vertical presets; expert provider mapping belongs in the same camera settings
group. Image rotation and non-gimbal camera orientation remain separate. See the
[mounting audit](../../reporting/agent-ops/codex-modernization/checkpoints/2026-09-19-gimbal-mounting-audit.md).

```yaml
Follower:
  FOLLOWER_MODE: gm_velocity_vector
  General:
    ENABLE_ALTITUDE_CONTROL: false
  FollowerOverrides:
    GM_VELOCITY_VECTOR:
      ENABLE_ALTITUDE_CONTROL: true
      LATERAL_GUIDANCE_MODE: coordinated_turn # fresh default; sideslip remains selectable
      ALTITUDE_CHECK_INTERVAL: 1.0

GimbalTracker:
  MOUNT_TYPE: HORIZONTAL          # HORIZONTAL | VERTICAL

GM_VELOCITY_VECTOR:
  RAMP_ACCELERATION: 0.25
  INITIAL_VELOCITY: 0.0
  YAW_RATE_GAIN: 0.5
  ANGLE_DEADZONE_DEG: 2.0
  ANGLE_SMOOTHING_ALPHA: 0.7
  ENABLE_VELOCITY_DECAY: true
  VELOCITY_DECAY_RATE: 0.5
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

## Timing And Filtering

`ANGLE_SMOOTHING_ALPHA` and `Follower.General.SMOOTHING_FACTOR` retain their
new-sample weight at `CONTROL_UPDATE_RATE`. Higher weights respond faster; the
filters normalize elapsed time so 20/30/60 Hz processing does not alter their
nominal response. Angular deadzone applies to separation of body rays rather
than individual camera Euler channels. Raw rearward or malformed measurements
are refused before old filter history can hide them.

Each follow session resets ramp/filter history. The first interval and stalled
intervals are bounded by one configured update period; connection setup time
cannot become accumulated acceleration. Slower processing conservatively
reduces ramp progress rather than catching up in one command.

After normal/retarget continuity blending, the authorized velocity-vector change
uses `RAMP_ACCELERATION`; yaw change uses the existing yaw acceleration limit.
The baseline advances only for accepted submissions. Current safety limits are
reapplied after shaping, while Stop and ordinary-loss restrictions bypass slew.

## Freshness And Target Continuity

The follower accepts commands only from a fresh, active, usable gimbal tracker
output. A stale angle sample may remain visible for diagnostics, but the tracker
marks it inactive and unusable for following. It then bypasses follower math
and reaches the shared target-continuity authority boundary. Prediction-only or
last-known angles never authorize an old pursuit vector.

## Bring-Up Order

1. Keep `FOLLOWER_CIRCUIT_BREAKER: true`.
2. Confirm the provider is connected and reports fresh tracking-status packets.
3. Verify yaw, pitch, and roll signs while the vehicle cannot move.
4. Verify `MOUNT_TYPE`, offsets, and inversion flags against the physical mount.
5. Confirm stale or lost tracking produces an unusable output and continuity
   handoff.
6. Validate telemetry, Offboard transitions, and command bounds in SIH/SITL or
   HIL before any separately approved field test.

Unit and tracker-in-loop tests cover vector normalization, stale-input
fail-closed behavior, command schema, and provider freshness. They do not prove
the client camera address, vendor firmware behavior, network delivery, PX4
response, or aircraft safety.

See [Gimbal Tracker](../../trackers/02-reference/gimbal-tracker.md) for the
provider contract and [Follower Command Schema](../../drone-interface/05-configuration/follower-commands-schema.md)
for the published intent fields.
