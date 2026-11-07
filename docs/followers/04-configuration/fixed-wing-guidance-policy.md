# Shared fixed-wing guidance policy

Fixed-wing guidance commands a feasible flight path and an airspeed reference.
PX4 owns coordinated turns, energy management, attitude control and allocation.
The same policy is intended for native FW objectives produced from gimbal rays
or image tracking. Input geometry remains specific to each tracker contract.

| Setting | Factory value | Meaning |
| --- | --- | --- |
| `Follower.AIRFRAME_LAYOUT` | `AUTO` | Use fresh PX4 state; an explicit MC/FW/VTOL/tailsitter choice verifies the installation |
| `Follower.AIRFRAME_PHASE_CONFIRMATION_S` | `0.5` | Fresh settled phase before resuming pursuit |
| `Follower.VTOL_TRANSITION_TIMEOUT_S` | `30` | Maximum transition/settlement duration; never renews target recovery |
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

| Installation / observed phase | Reused implementation |
| --- | --- |
| Pure MC, or VTOL in MC flight | Existing MC vector math; pure MC uses MAVSDK, VTOL keeps its native owner |
| Pure FW, or VTOL in FW flight | The same native course, vertical-path and airspeed strategy |
| Standard VTOL or tailsitter during transition | PX4's native transition interface; pursuit paused |
| Different gimbal or mounting | Provider adapter and mounting geometry produce the same physical ray |

There is no separate tailsitter pursuit law. Public defaults provide the base
configuration; a named aircraft overlay changes only its explicit settings.
Follower-specific gains stay with that follower. Shared FW policy and PX4-owned
envelope resolution must not be copied into each aircraft or camera adapter.

The aircraft-layout choice does not establish flight phase. Actual MC/FW/
transition state comes from fresh PX4 observations. AUTO is the normal choice.
An explicit layout mismatch is an installation problem, not permission to
reinterpret telemetry.

Camera mounting remains in `GimbalTracker`. Its ray is transformed once from
physical body FRD to NED using the physical aircraft quaternion. PX4's native
FW controller supplies its own FW-frame heading and forward axis, including
the tailsitter conversion. The companion does not rotate the mounting preset
during transition or apply that conversion again.

Transition holding latches the preceding feasible course and FW request for the
transition episode. It does not chase physical yaw changes as a tailsitter
pitches through vertical, or reuse an old FW course after returning to MC.
Current native speed bounds still apply. MC provisional-angle retarget guidance
does not mutate FW/transition guidance before target confirmation.
When the guidance generation changes, the Vector input filter starts from its
first fresh measurement. A pre-transition physical-body ray cannot seed the
new phase after a tailsitter rotates. Normal filtering continues within a phase;
this reset does not change speed requests, ownership or recovery deadlines.

## Current qualification boundary

![Observed PX4 SIH target range and altitude response for both gimbal mounts](../assets/native-vector-fw-matrix-20261107.png)

The normal-envelope native Vector component matrix passed four 15-second
moving-target approaches on the pinned PX4 SIH airplane. Both mounts held
altitude with guidance off (maximum errors 0.138/0.333 m) and descended toward
the lower target with guidance on. All four confirmed Hold with no later
publication. The reusable local evidence browser is
`reports/sitl/native-vector-fw-matrix-20261107/index.html`; exact revisions,
traces and reproduction commands are retained beside it. This tests an approach,
not interception, landing or a physical installation.

The typed policy, configuration, phase-specific controls, native frame
observations and application lifecycle binding are implemented and unit tested.
Native setup/packaging, unrestricted firmware policy and full moving-target/
VTOL acceptance remain in progress. The development adapter is not installed
by ordinary setup. Native startup requires matching firmware, a verified
aircraft, fresh observations and an explicitly configured FW recovery policy;
missing legacy recovery settings require Config Sync, not a silent authority
change. A failed preparation never falls through to MC commands on FW/VTOL.
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
