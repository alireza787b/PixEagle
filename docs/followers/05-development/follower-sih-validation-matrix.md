# Follower qualification inventory

Reviewed 2026-11-09 at PixEagle `50bb2f763`. Historical results retain their
capture revisions; they are not release acceptance for subsequent changes.
The [consolidation plan](follower-consolidation-plan.md) defines the next gates.

## Existing profiles

| Profile | Actual input and behavior | Evidence / remaining gate |
| --- | --- | --- |
| `mc_velocity_position` | Real image position; zero forward/right, visual yaw and optional vertical guidance | Synthetic replay; fresh behavior-specific SIH required |
| `mc_velocity_chase` | Image position; forward ramp, yaw or sideslip, optional vertical guidance | One bounded actual quadx command/publication/response run; full release scenario suite required |
| `mc_velocity_ground` | Downlooking/oblique image position; image X to right, Y to forward, optional descent | Synthetic replay; fresh SIH required; no landing qualification |
| `mc_velocity_distance` | Image position; visual centering with zero forward command | Synthetic replay; fresh SIH required; no measured distance keeping |
| `mc_attitude_rate` | Image position and aircraft state; rates/thrust | Synthetic replay/software guards; actual envelope/response qualification required |
| `fw_attitude_rate` | Image position and aircraft state; L1/TECS-inspired rates/thrust | Synthetic replay; live gate remains; native Vector evidence does not qualify this implementation |
| `gm_velocity_chase` | Camera-provider angles and canonical installation geometry; MC PID pursuit | Synthetic replay; fresh MC SIH required |
| `gm_velocity_vector` | Provider angles to physical ray; MC velocity or native FW navigation | Actual bounded FW component/recovery/application evidence below; MC and new VTOL behavior require fresh qualification |

Public defaults select Position, circuit breaker on and shared target-altitude
guidance off. That shared flag is not a universal altitude-hold contract:
Ground has `ENABLE_DESCEND_TO_TARGET`; MC direct rates has its own altitude hold
enabled with a 15 m offset; FW direct rates derives altitude error from image Y.
Those differences require audit in S4/S5, not an unsupported common guarantee.

## PX4-observed evidence

Run paths below are local evidence roots under `reports/sitl/`. They contain
manifests/results and read-only visualizations where generated. Synthetic
gallery traces do not become PX4 evidence by linking to these runs.

| Run / capture revision | Bounded result | Scope exclusions |
| --- | --- | --- |
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
