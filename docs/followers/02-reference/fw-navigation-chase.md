# FW Navigation Chase

`fw_navigation_chase` turns a calibrated, time-associated image measurement into
native PX4 **course, equivalent-airspeed reference and vertical-path intent**.
PX4 handles coordinated turns, energy management and attitude control.

**Status:** experimental implementation with `live_qualified_phases: [fixed_wing]`.
The [standard VTOL application checkpoint](../../reporting/agent-ops/codex-modernization/checkpoints/2026-11-13-vtol-training-app.md)
records normal Start, speed adjustment and Stop with an actual Gazebo-rendered
camera and qualified simulated source-clock association. This is bounded
source/runtime evidence, not physical-camera timing, sensorless hardware or
general aircraft qualification. The [qualification inventory](../05-development/follower-sih-validation-matrix.md)
records the other verification layers. Local `COMMAND_PREVIEW` is unavailable
for this native-only contract.

```text
measured image pixel + exact calibration + qualified sample-time attitude
                  -> NED bearing -> native FW objective -> PX4
```

This is a bearing without measured range. It does not use the old direct-rate
profile's L1/TECS-inspired controller, invent an MC velocity command, or treat
image-centering error as a world direction. PID initial-aim settings do not
rotate the measured ray. The same native guidance, envelope, session controls,
publisher and continuity owner also support external Vector input.

## Behavior

| Input / setting | Result |
| --- | --- |
| Target ahead or to either side | Feasible course toward the world bearing; native coordinated turn |
| Target behind | Latched turn direction avoids ambiguous ±180° changes |
| Near-vertical ray | Retain the last usable course; no stationary yaw or pure vertical FW flight |
| Altitude guidance off | Hold engagement AMSL altitude |
| Altitude guidance on | Target-derived height rate, bounded by native climb/sink and altitude authority |
| Requested speed | Positive EAS reference initialized from qualified airspeed or PX4 trim; achieved speed is separate |
| Missing/unqualified observation | Existing bounded FW recovery, then owner-aware Hold handoff |

Groundspeed supplies navigation data, never measured EAS. Missing airspeed does
not establish stall margin. Relative-altitude protection is estimator/home
referenced, not terrain clearance. The recorded standard-VTOL workflow selects
MC Chase and FW Navigation Chase separately while following is inactive.
Transition ends following; settled-phase readiness permits a fresh Start.
Configured MC/FW recipe resolution is proposed, not implemented; there is no
automatic strategy switch or resume.

## Configuration

| Authority | Owns |
| --- | --- |
| `VideoSource.FIXED_CAMERA_CALIBRATION` | Exact decoder-grid intrinsics, source identity and fixed optical-to-physical-FRD transform |
| Qualified observation association | Exact image/attitude binding, timing uncertainty and reset identity |
| `FW_NAVIGATION_CHASE` | Only the four direction thresholds below |
| `Follower.General` / sparse `Follower.FollowerOverrides.FW_NAVIGATION_CHASE` | Altitude permission and shared operational settings |
| `FixedWingGuidance` | Shared native FW policy |
| `Safety.GlobalLimits` / tighter profile override | Existing altitude authority; native PX4 retains its performance envelope |

| Strategy threshold | Factory value |
| --- | --- |
| `VERTICAL_ENTER_HORIZONTAL_NORM` | `0.20` |
| `VERTICAL_EXIT_HORIZONTAL_NORM` | `0.30` |
| `REARWARD_ENTRY_BEARING_DEG` | `100.0°` |
| `FORWARD_REENTRY_BEARING_DEG` | `80.0°` |

Enter must be below exit; forward re-entry must be below rearward entry. The
canonical configuration service validates the ordered pairs. These values do
not tune speed, acceleration, bank, pitch or thrust. No gimbal settings are read.
Changing them uses the existing follower-restart tier.

Older saved configurations stay unchanged. Config Sync offers the four missing
settings for explicit preview/apply; absent or incomplete geometry cannot be
replaced by hidden constructor defaults. Public VIDEO_FILE/CSRT/Stationary,
altitude-guidance-off, altitude safeguards and circuit breaker remain unchanged.

Physical capture currently lacks a qualified exposure/attitude association.
Calibration alone cannot remove that readiness restriction. The default
constructor creates no native owner or commands. Controlled SIH injects an
explicit sample association; the recorded Gazebo application path uses its
qualified simulated source-clock association. See [creating a follower](../05-development/creating-followers.md)
and the [shared FW policy](../04-configuration/fixed-wing-guidance-policy.md).

Repeated reads of one image retain its original capture and paired attitude.
Fresh authoritative aircraft-state progress can recalculate native constraints
against that still-qualified world bearing; identical state and speed requests
reuse the original command deadline. Image expiry enters the existing FW
continuity policy, while frozen aircraft input cannot renew publication.
