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

## Configuration

Representative profile settings are:

```yaml
FW_ATTITUDE_RATE:
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

Angular-rate, altitude, target-loss, and emergency limits are owned by the
central `Safety` and `Follower` sections. PID gains are owned by `PID_GAINS`.
Use [Configuration](../../CONFIGURATION.md) and the generated schema as the
parameter authority.

## Acceptance Boundary

Treat this profile as unaccepted until the exact airframe and PX4 release pass:

1. command-preview sign and saturation tests
2. deterministic software-in-loop target and telemetry traces
3. PX4 SITL/HIL Offboard transition and loss tests
4. airframe-specific stall, thrust, bank, and target-loss acceptance under an
   approved test plan

Prediction-only tracker output is not eligible for normal pursuit commands.
The configured target-loss action takes over when a fresh measured target is
unavailable.

## References

- [MAVSDK AttitudeRate field signs](https://mavsdk.mavlink.io/main/en/cpp/api_reference/structmavsdk_1_1_offboard_1_1_attitude_rate.html)
- Park, S., Deyst, J., and How, J. P. (2004), *A New Nonlinear Guidance Logic for Trajectory Tracking*
- Lambregts, A. A. (1983), *Vertical Flight Path and Speed Control Autopilot Design Using Total Energy Principles*
- [Follower safety and implementation practices](../05-development/best-practices.md)
