# Shared fixed-wing guidance policy

Fixed-wing guidance commands a feasible flight path and an airspeed reference.
PX4 owns coordinated turns, energy management, attitude control and allocation.
The same policy is intended for native FW objectives produced from gimbal rays
or image tracking. Input geometry remains specific to each tracker contract.

| Setting | Factory value | Meaning |
| --- | --- | --- |
| `Follower.AIRFRAME_LAYOUT` | `AUTO` | Use fresh PX4 state; an explicit MC/FW/VTOL/tailsitter choice verifies the installation |
| `FixedWingGuidance.UPPER_SPEED_POLICY` | `px4_configured_max` | Respect the current native PX4 airspeed envelope |
| `FixedWingGuidance.MIN_DIVE_THROTTLE` | `null` | Keep native throttle behavior |

The Dashboard exposes these through the canonical configuration service. Apply
changes while following is inactive; they use the existing follower-restart
tier. Existing saved configurations retain their values until Config Sync
preview/apply accepts changes. Missing policy settings retain normal native
behavior. Public video/CSRT, constant-position, altitude-guidance-off,
altitude-safety and circuit-breaker defaults are preserved.

## Flight-path priority

`no_upper_speed_bound` requests experimental flight-path priority. During an
authorized target-directed descent, crossing the normal upper speed bound
alone must not redirect pitch away from the requested path. It does not request
direct nose alignment, disable underspeed protection, or remove altitude,
attitude and actuator constraints. It cannot guarantee deceleration in a dive.

`MIN_DIVE_THROTTLE` is an optional normalized floor during that descent: `0.10`
means 10%; `null` keeps native behavior. Native actuator bounds remain
authoritative. A throttle floor can keep motors running; it does not guarantee
control authority. It does not apply to MC flight, ordinary FW guidance or
PX4-owned transitions.

The runtime policy must share the command owner's lease and restore on Stop,
takeover, expiry, rescue or disarm. It must not rewrite saved PX4 parameters.
The policy remains unavailable unless the matching native firmware capability
has been verified; a configuration value alone cannot grant it. If the
experiment is configured but unavailable, the effective policy stays at normal
PX4 limits with native throttle and reports `unrestricted_speed_not_supported`.
This supported fallback must remain visible in diagnostics; it is not successful
activation of flight-path priority.

## Aircraft and camera frames

The aircraft-layout choice does not establish flight phase. Actual MC/FW/
transition state comes from fresh PX4 observations. AUTO is the normal choice.
An explicit layout mismatch is an installation problem, not permission to
reinterpret telemetry.

Camera mounting remains in `GimbalTracker`. Its ray is transformed once from
physical body FRD to NED using the physical aircraft quaternion. PX4's native
FW controller supplies its own FW-frame heading and forward axis, including
the tailsitter conversion. The companion does not rotate the mounting preset
during transition or apply that conversion again.

## Current qualification boundary

The typed policy, configuration, phase-specific controls and native frame
observations are implemented. Automatic application wiring, the unrestricted
firmware policy and full moving-target/VTOL acceptance remain in progress.
The older `fw_attitude_rate` implementation still uses its direct-rate/thrust
contract and does **not** gain unrestricted behavior from these settings. It
must adopt the shared qualified native boundary before advertising the policy;
copying an upper-limit bypass into its local controller is not an equivalent
implementation.

Qualification reports must show independent target truth, actual PX4 position,
flight phase, flight path, requested/effective/observed speed, throttle and
constraints. Nose direction is diagnostic alongside the flight path, not the
command objective. See the [active checkpoint](../../reporting/agent-ops/codex-modernization/checkpoints/2026-11-06-gimbal-vector-airframes.md)
for current evidence and remaining gates.
