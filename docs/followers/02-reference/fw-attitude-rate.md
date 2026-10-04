# FW Attitude Rate Follower

`fw_attitude_rate` is PixEagle's current fixed-wing visual guidance profile. It
maps image error and vehicle telemetry into MAVSDK attitude-rate and thrust
fields using L1- and TECS-inspired calculations.

**Profile:** `fw_attitude_rate`

**Control type:** `attitude_rate`

**Source:** `src/classes/followers/fw_attitude_rate_follower.py`

This implementation is not PX4's internal L1 or TECS controller, and its
presence is not evidence of airframe or field readiness.

## Control Contract

The centrally resolved aim point is the equilibrium for both image axes:

| Observation | Guidance response |
|---|---|
| Target right of aim | Positive lateral error and positive clockwise yaw rate |
| Target left of aim | Negative lateral error and negative yaw rate |
| Target above aim | Positive climb error |
| Target below aim | Negative climb error |

The lateral path converts normalized image-X error to a scaled lateral error,
then computes yaw rate and a coordinated bank target. The longitudinal path
combines image-Y-derived climb error with airspeed error to produce pitch rate
and thrust. Attitude rates are published in degrees per second.

## Required Vehicle State

Normal control depends on fresh, correctly signed telemetry for:

- airspeed
- relative altitude
- roll attitude

Stall and altitude handling cannot be validated from video alone. Missing or
incorrect telemetry, camera mounting, airspeed calibration, or airframe tuning
invalidates the control assumptions.

By default the follower does not substitute ground speed for airspeed. Configured
cruise speed is always a target, never an observation. The current PX4 interface
does not yet acquire a qualified airspeed
observation; live fixed-wing following remains blocked by the existing
`profile_not_live_qualified` policy. Its readiness additionally reports
`following_airspeed_unavailable`. A fresh stationary or underspeed reading is
not sufficient to start: the configured `MIN_AIRSPEED + STALL_MARGIN_BUFFER`
margin still applies.

The admission boundary accepts only an explicit telemetry-owner observation
with finite nonnegative `airspeed_m_s`, `available` and `fresh` true,
`observed_at_monotonic_s`, source, owner-instance identity, connection generation
and telemetry generation. Its age and identity must match canonical telemetry
readiness. This is a contract for later qualified acquisition, not a claim that
the current PX4 interface supplies it. New camera frames, HTTP polling completion,
ground speed and cruise configuration cannot supply these semantics.

Without an enabled and fresh fallback, missing/stale airspeed and confirmed underspeed refuse guidance through the
existing immediate safety handoff. The legacy nose-down/full-throttle recovery
method is not automatically dispatched by this path. Target loss cannot delay
the airspeed guard or convert it into bounded coasting.

Command Preview retains its explicitly synthetic airspeed input for mathematical
checks. Its observation says `source: command_preview`,
`execution_mode: COMMAND_PREVIEW` and `commands_sent_to_px4: false`; that adapter
cannot satisfy live aircraft startup. Synthetic math does not qualify a real
airspeed source or stall envelope.

Sensorless installations can explicitly enable **Use ground speed when airspeed
is unavailable** in the web Dashboard's Advanced configuration, under
**Fixed-Wing Attitude Rate** (`FW_ATTITUDE_RATE.ALLOW_GROUND_SPEED_FALLBACK`).
It defaults to `false`, uses the existing config save/reload path and requires
the normal follower restart. There is no QGC setting or separate speed store.

When enabled, fresh valid airspeed still takes precedence, including a stationary
or underspeed observation; the fallback cannot bypass its minimum-speed refusal.
Only unavailable airspeed permits fresh canonical ground velocity to act as the
control-speed proxy. The existing guidance law, minimum-speed checks, speed/gain
limits and altitude guards are unchanged. Wind and body-axis projection can make
this proxy differ from airspeed: the option does not measure airflow or physical
stall margin. It never invents wind compensation or substitutes a cruise constant.

The proxy's source is reported as `mavsdk.velocity_body` or
`mavlink2rest.LOCAL_POSITION_NED`, with `fallback_active: true` in
`guidance_speed`. `current_airspeed` is null during fallback. Startup readiness
and the status report name the ground-speed proxy explicitly. Unavailable/stale
ground data and ground speed below the configured minimum fail closed through
the immediate handoff, including during target loss.

SDK observations retain their actual velocity-stream receipt. REST requires
advancing `LOCAL_POSITION_NED.time_boot_ms`; repeated polling cannot refresh
cached velocity. Ground value, original receipt and owner generations are
committed together with the canonical complete snapshot. Failed gathers and
previous-owner results cannot pair fresh timestamps with old values. Missing
source timestamps remain unavailable for this fallback.

Enabling the checkbox does **not** remove the existing fixed-wing
`profile_not_live_qualified` restriction or qualify a real airframe. Command Preview
remains synthetic math only. Publisher-to-PX4 fixed-wing SIH response, sensorless
control-envelope validation and real-airframe qualification remain open.

A future validated ground-minus-wind estimator can provide a separate airspeed
observation without relabelling this raw ground-speed option. The MAVLink VFR_HUD field and SDK
fixedwing-metrics label alone do not certify physical sensor provenance on every
firmware version. See the [MAVLink contract](https://mavlink.io/en/messages/common.html#VFR_HUD)
and [PX4 v1.17 source](https://github.com/PX4/PX4-Autopilot/blob/v1.17.0/src/modules/mavlink/streams/VFR_HUD.hpp).

## Configuration

Representative profile settings are:

```yaml
FW_ATTITUDE_RATE:
  ALLOW_GROUND_SPEED_FALLBACK: false
  MIN_AIRSPEED: 12.0
  CRUISE_AIRSPEED: 18.0
  MAX_AIRSPEED: 30.0

  L1_DISTANCE: 50.0
  L1_DAMPING: 0.75
  L1_LATERAL_SCALE: 50.0

  ENABLE_TECS: true
  TECS_TIME_CONST: 5.0
  TECS_SPE_WEIGHT: 1.0
  TECS_ALTITUDE_SCALE: 20.0

  MIN_THRUST: 0.2
  CRUISE_THRUST: 0.6
  MAX_THRUST: 1.0
  THRUST_SLEW_RATE: 0.5

  ENABLE_COORDINATED_TURN: true
  ENABLE_STALL_PROTECTION: true
```

Angular-rate, altitude, and emergency limits are owned by the central
`Safety` and `Follower` sections. Target-evidence authority is
owned by `TargetContinuity`. PID gains are owned by `PID_GAINS`.
Use [Configuration](../../CONFIGURATION.md) and the generated schema as the
parameter authority.

## Acceptance Boundary

Treat this profile as unaccepted until the exact airframe and PX4 release pass:

1. command-preview sign and saturation tests
2. deterministic software-in-loop target and telemetry traces
3. PX4 SITL/HIL Offboard transition and loss tests
4. airframe-specific stall, thrust, bank, and authority-handoff acceptance under an
   approved test plan

Prediction-only tracker output is not eligible for normal pursuit commands.
Fixed-wing attitude-rate continuity requests immediate handoff; live coasting is
not qualified.

## References

- [MAVSDK AttitudeRate field signs](https://mavsdk.mavlink.io/main/en/cpp/api_reference/structmavsdk_1_1_offboard_1_1_attitude_rate.html)
- Park, S., Deyst, J., and How, J. P. (2004), *A New Nonlinear Guidance Logic for Trajectory Tracking*
- Lambregts, A. A. (1983), *Vertical Flight Path and Speed Control Autopilot Design Using Total Energy Principles*
- [Follower safety and implementation practices](../05-development/best-practices.md)
