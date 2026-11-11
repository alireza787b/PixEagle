# Follower qualification inventory

Reviewed 2026-11-12. The [raw-backed evidence selector](../02-reference/follower-visual-guide.md)
retains the MC image cases; the [consolidation checkpoint](../../reporting/agent-ops/codex-modernization/checkpoints/2026-11-09-follower-consolidation.md)
records renewed S5/S6 image/gimbal/native-FW evidence pending S10's unified selector.
This page records behavior and broader gates.
Historical results retain their capture revisions; they are not release acceptance for subsequent changes.
The [consolidation plan](follower-consolidation-plan.md) defines the next gates.

## Existing profiles

| Profile | Actual input and behavior | Evidence / remaining gate |
| --- | --- | --- |
| `mc_velocity_position` | Image position; zero forward/right, visual yaw and optional vertical guidance | Observed MC component cases in the selector; optical/application/release gates remain |
| `mc_velocity_chase` | Image position; forward ramp, yaw or sideslip, optional vertical guidance | Observed MC component cases in the selector; no interception or field-tuning guarantee |
| `mc_velocity_ground` | Downlooking image axes: X to right, image-up to forward; optional descent | Observed MC component cases in the selector after correction cleanup; no landing qualification |
| `mc_velocity_distance` | Image position; visual centering with zero forward command | Observed MC component cases in the selector; no measured distance keeping |
| `mc_attitude_rate` | Image position and aircraft state; rates/thrust | Observed advanced rate/height-hold component cases; live retarget requires Stop; no target-vertical qualification |
| `fw_attitude_rate` | Image position and aircraft state; L1/TECS-inspired rates/thrust | Synthetic replay; live gate remains; native Vector evidence does not qualify this implementation |
| `fw_navigation_chase` | Calibrated image bearing; native course/EAS/altitude guidance | Renewed S5 airplane component cases; physical calibration/timing and live admission remain gated |
| `gm_velocity_chase` | Camera-provider angles and canonical installation geometry; MC PID pursuit | Renewed S6 nominal/fault MC cases, both mounts; simulated boresight, no physical acquisition qualification |
| `gm_velocity_vector` | Provider angles to physical ray; MC velocity or native FW navigation | Renewed S6 nominal/fault MC and native-FW cases, both mounts; new VTOL and native ownership release remain S7 gates |

Public defaults select Position, circuit breaker on and shared target-altitude
guidance off. That shared flag is not a universal altitude-hold contract:
Ground has `ENABLE_DESCEND_TO_TARGET`; MC direct rates holds engagement height,
with its saved offset applied only when optional altitude guidance is enabled
(factory offset zero). FW direct rates derives altitude error from image Y.
These remain distinct declared behaviors, not an unsupported common guarantee.

## PX4-observed evidence

Run paths below are local evidence roots under `reports/sitl/`. They contain
manifests/results and read-only visualizations where generated. Synthetic
gallery traces do not become PX4 evidence by linking to these runs.

| Run / capture revision | Bounded result | Scope exclusions |
| --- | --- | --- |
| `follower-consolidation-20261109/current-evidence` / per-run manifests | Current canonical MC captures, raw verdicts, replays and retained failed history; generated inventory rather than a hand-maintained case list | Simulated fixed-camera measurements; no optical tracking, whole-app startup, installation, hardware or release qualification |
| `follower-consolidation-20261111/s6-mc-*` / `115192e15`, `bf98f4dd0`, `7327c2153` | Eight nominal and sixteen selected fault cases; both followers/mounts, altitude off/on, short loss, budget expiry, repeated retarget and pilot takeover; exact selection and history in `software-gates-r1/s6-mc-fault-proof-r2.json` | Simulated boresight component evidence; original Vector-V weak-excitation long-loss run stays failed, explicitly distinct initial-climb fixtures pass both mounts |
| `follower-consolidation-20261111/s6-gm-fw-*` / `115192e15` | Eight native GM airplane cases: both mounts, altitude off/on, short-loss restoration and eight-second expiry; confirmed Hold with no later publication | No physical timing/target alignment, application startup, causal acquisition/takeover or transition qualification; airspeed-fault renewal skipped with recorded simulator-policy reason |
| `mc_velocity_chase-20261025` / `fcdebc0d7` | Actual quadx, 199 successful publications, confirmed Hold and post-Stop CB probe | `release_qualified=false`; no physical camera or tracker acquisition acceptance |
| `native-vector-fw-matrix-20261107` / `3b3e172cf` | Four actual airplane cases: both mounts, altitude guidance off/on; 1,180 successful submissions and 1,800 observed publications | Component approach tests, not interception, installation or hardware |
| `native-vector-recovery-20261107` / `e51e1c59e` | Six airplane recovery cases pass; eight-second expiry and publication continuity retained | Process-stall assertions are separate; intentionally terminal component result remains failed |
| `native-vector-application-20261107` / `91d2084e6`, `12e14a93f` | Two real application/HTTP airplane sessions, vertical mount, RTSP/SIP fixtures; 297 publications each, confirmed Hold and 55 post-Stop observations | No real camera, setup or VTOL application; native FW orientation and measured EAS absent from this trace |
| `native-vector-vtol-matrix-20261107` / `0f4769952` repaired cases | Two tailsitter component passes; maximum altitude error 1.244/1.407 m; three failed comparisons retained | Historical continuing-session transitions; **not** the new end-on-transition/new-Start policy; simulator-only settings |
| `native-vector-standard-vtol-20261107/vector-cycle-vertical` | **Failed:** altitude error 2.165 m exceeds unchanged 2 m gate | Remains open; separate successful takeover assertions do not convert this run into a pass |
| `native-vector-standard-vtol-20261107/pilot-takeover-proof.json` | 55 subsequent RTL observations, unchanged publication count, no reacquired owner | Authority boundary only; intentionally terminal component result remains failed |
| `native-vector-connection-boundary-20261107` | Disarmed identity/transport checks, zero publications | Not following or aircraft-response qualification |

The failed `gm_velocity_vector-20261025-failed` vertical-MC run remains evidence
of insufficient altitude response. October 24 imported traces with no observed
PX4 pose remain incomplete. Keep both failure history and newer scoped results.
The S6 low-excitation vertical long-loss failure also remains failed: its budget
handoff passed, but measured vertical work was 0.0213 m against the 0.1 m gate.
The two distinct revised loss fixtures start the target 3 m above the aircraft;
both pass that same gate without changing gains, limits or loss timing. This
does not establish repeatability of the original weak-excitation fixture.

## Qualification rules

- Distinguish contract tests, synthetic replay, actual PX4 SIH, physical camera,
  installation/prop-off checks and field acceptance.
- Start actual SIH from a measured stable airborne state and retain independent
  target truth, actual pose/attitude and actual publications in the same run.
- Position and centering profiles are not required to intercept targets; pursuit
  needs independently measured closure/path response appropriate to its purpose.
- New transition behavior is **end following and require a new Start**. Today's
  adapter Stop-to-Hold does not prove transition-preserving release. This remains
  an S7 gate; historical automatic-resume passes cannot satisfy it.
- Unrestricted FW firmware policy, native setup/ARM64 packaging, real image-to-FW
  geometry and remaining profile/application/fault runs remain open.
- Rerun affected qualification after changes. Never integrate commands to invent
  pose, hide stale intervals or relax a failed gate merely to obtain a pass.

See the [SIH runner guide](sih-follower-qualification.md),
[native airframe checkpoint](../../reporting/agent-ops/codex-modernization/checkpoints/2026-11-06-gimbal-vector-airframes.md)
and [current consolidation checkpoint](../../reporting/agent-ops/codex-modernization/checkpoints/2026-11-09-follower-consolidation.md).
