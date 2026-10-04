# MC Attitude Rate Follower

`mc_attitude_rate` converts a measured image target into MAVSDK attitude-rate
fields (`rollspeed_deg_s`, `pitchspeed_deg_s`, `yawspeed_deg_s`, and normalized
`thrust`). It is a high-authority profile and does not command body velocity.

**Profile:** `mc_attitude_rate`

**Control type:** `attitude_rate`

**Source:** `src/classes/followers/mc_attitude_rate_follower.py`

## Axis Contract

PixEagle resolves the configured aim point before constructing the follower.
All image errors are relative to that point:

| Observation | Command direction |
|---|---|
| Target right of aim | Positive yaw rate (clockwise from above) |
| Target left of aim | Negative yaw rate |
| Target above aim | Positive pitch rate (nose up) |
| Target below aim | Negative pitch rate (nose down) |

These signs follow the MAVSDK `AttitudeRate` contract. Camera orientation and
gimbal mount transforms must be normalized before this follower receives the
target coordinates.

## Guidance Modes

- `direct_rate`: PID control of horizontal and vertical image error. This is
  the default and the first mode to validate on a new vehicle.
- `png`: derives angular-rate commands from line-of-sight rate. It falls back
  to direct-rate control until a time history exists. This is an optional
  experimental guidance law, not evidence of field suitability.

Yaw-error gating can reduce pitch authority until horizontal alignment is
within `YAW_ERROR_THRESHOLD`. Optional coordinated-turn logic derives roll rate
from yaw rate and current ground speed.

Measured roll/pitch protection runs after smoothing and again on every Offboard
publication, including heartbeats without a new image. It converts BODY rates
to coupled Euler-angle derivatives and uniformly scales the three rates to stay
within the configured envelope over the observation age and publisher horizon.
Thrust is unchanged. The horizon includes the actual publisher timeout, cadence,
telemetry poll period and command lifetime. Uniform scaling may conservatively
reduce an inward axis when another axis points outward at its boundary.

MAVSDK attitude freshness uses the attitude stream's receipt time. REST attitude
requires progress of `ATTITUDE.time_boot_ms` within the current connection;
the first cached packet cannot prove freshness, and repeated cached packets or
new altitude packets cannot refresh it. Missing, stale, invalid or out-of-envelope
attitude fails closed immediately, stops the local sender and requests handoff.
Pitch limits must remain below the Euler singularity at 90 degrees. The guard
is a software projection constraint, not a guarantee against physical inertia,
telemetry delay or unqualified airframe response.

## Thrust And Altitude

Attitude-rate control requires an explicit thrust command. `HOVER_THRUST` is
the baseline. Optional altitude hold adds a bounded correction, and optional
pitch compensation adjusts for reduced vertical thrust while tilted.

`HOVER_THRUST`, thrust limits, and altitude gains are vehicle-specific. The
checked-in values are software defaults, not flight-accepted tuning.

## Configuration

Representative profile settings are:

```yaml
MC_ATTITUDE_RATE:
  GUIDANCE_MODE: direct_rate
  MAX_PITCH_ANGLE: 35.0
  MAX_ROLL_ANGLE: 35.0
  MAX_BANK_ANGLE: 30.0

  HOVER_THRUST: 0.5
  MIN_THRUST: 0.1
  MAX_THRUST: 0.9
  ENABLE_PITCH_THRUST_COMPENSATION: true

  ENABLE_ALTITUDE_HOLD: true
  TARGET_ALTITUDE_OFFSET: 15.0

  ENABLE_YAW_ERROR_GATING: true
  YAW_ERROR_THRESHOLD: 0.3
  ENABLE_COORDINATED_TURNS: true
```

Rate, velocity, altitude, and emergency behavior are owned by the central
`Safety` and `Follower` sections. Target-evidence authority is
owned by `TargetContinuity`. PID gains are owned by `PID_GAINS`.
Use [Configuration](../../CONFIGURATION.md) and the generated schema as the
parameter authority instead of copying this excerpt as a complete config.

## Acceptance Boundary

Start with command preview and inspect signs, limits, freshness transitions,
and continuity handoff. Then validate against the exact PX4 firmware, vehicle,
camera mounting, telemetry source, and thrust model in SITL/HIL before any
controlled field acceptance. A valid visual target alone does not establish
safe thrust or attitude authority.

## References

- [MAVSDK AttitudeRate field signs](https://mavsdk.mavlink.io/main/en/cpp/api_reference/structmavsdk_1_1_offboard_1_1_attitude_rate.html)
- [Follower safety and implementation practices](../05-development/best-practices.md)
