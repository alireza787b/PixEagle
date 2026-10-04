# GM Velocity Chase Follower

**Profile:** `gm_velocity_chase`

**Control type:** `velocity_body_offboard`

**Tracker input:** `GIMBAL_ANGLES`
**Source:** `src/classes/followers/gm_velocity_chase_follower.py`

`gm_velocity_chase` converts provider-normalized gimbal angles into a complete
body-FRD velocity intent:

- `vel_body_fwd` in m/s;
- `vel_body_right` in m/s;
- `vel_body_down` in m/s;
- `yawspeed_deg_s` in degrees/s, positive clockwise.

It does not emit local-NED commands and does not infer target range.

## Angle Contract

The tracker supplies raw `(yaw_deg, pitch_deg, roll_deg)` measurements. Both
gimbal followers consume the same camera-to-aircraft line-of-sight mapping from
`GimbalTracker.MOUNT_TYPE` and its optional `GEOMETRY_OVERRIDE`.

For the observed Topotek base-pitched-up-90° vertical installation, pitch 90°
looks forward, decreasing pitch looks up, and positive raw roll pans left. Raw
yaw rotates the image and is not the bearing input. Horizontal geometry uses
raw yaw for azimuth and raw pitch for depression; physical horizontal-mount
acceptance remains separate from synthetic geometry tests.

The follower validates the raw body ray before calculating pursuit. A malformed
or rearward ray invalidates guidance rather than producing neutral steering
while forward motion continues. Installation corrections belong in the camera
configuration, not duplicated follower inversion settings. See the
[mounting audit](../../reporting/agent-ops/codex-modernization/checkpoints/2026-09-19-gimbal-mounting-audit.md).

## Guidance Modes

`Follower.General.LATERAL_GUIDANCE_MODE` selects one horizontal command owner:

- `coordinated_turn`: transformed lateral error drives clockwise/counterclockwise yaw; body-right is zero.
- `sideslip`: transformed lateral error drives body-right velocity; yaw is zero.

Mode changes clear both PID histories and yaw-smoother state before the next
intent. Vertical control is enabled separately through the resolved follower
configuration.

Forward speed is documented in [Gimbal Chase Forward
Speed](../03-gnc-concepts/gimbal-forward-speed.md). Only `CONSTANT` and
`PITCH_BASED` exist.

## Minimal Configuration

```yaml
GimbalTracker:
  MOUNT_TYPE: HORIZONTAL             # HORIZONTAL or VERTICAL; one installation setting

GM_VELOCITY_CHASE:
  FORWARD_VELOCITY_MODE: "CONSTANT"
  BASE_FORWARD_SPEED: 2.0            # m/s
  FORWARD_ACCELERATION: 2.0          # m/s^2

Follower:
  General:
    LATERAL_GUIDANCE_MODE: coordinated_turn
    ENABLE_ALTITUDE_CONTROL: false    # ordinary followers retain this default
    CONTROL_UPDATE_RATE: 20.0
  FollowerOverrides:
    GM_VELOCITY_CHASE:
      ENABLE_ALTITUDE_CONTROL: true   # fresh gimbal default; Safety limits still govern
```

Velocity/rate/altitude limits are owned by `Safety.GlobalLimits` and optional
tightening overrides, not by this profile.

## Timing And Command Shaping

Each follow session resets the ramp, PID, yaw filter and submitted-command
history. Monotonic intervals are bounded by one configured update period, so
connection delays, wall-clock changes and scheduler stalls cannot accumulate a
large speed step.

`COMMAND_SMOOTHING_ENABLED` applies the configured `SMOOTHING_FACTOR` to normal
velocity guidance, normalized to elapsed time at `CONTROL_UPDATE_RATE`. The
existing yaw pipeline remains the sole yaw filter. Higher new-sample weights
respond faster. Altitude guards run after smoothing.

After continuity blending, the authorized velocity-vector change uses
`FORWARD_ACCELERATION`; yaw change uses the existing yaw acceleration limit.
Only submitted commands advance the shaping baseline. Safety clamps, immediate
Stop and ordinary-loss zero-yaw/vertical restrictions retain precedence.

## Validation Sequence

1. Confirm the gimbal provider reports finite, fresh angle data.
2. In command preview, move one gimbal axis at a time and verify command sign.
3. Confirm ordinary loss uses the configured bounded horizontal decay, while
   ambiguous identity or invalid geometry requests immediate handoff.
4. Validate speed ramps and mode switching with PX4 in the loop.
5. Enable real command publication only after operator abort and envelope tests.

Circuit breaker and command preview are separate: command preview has no PX4
publisher, while the circuit breaker is the final dispatch inhibit on the
normal command path.
