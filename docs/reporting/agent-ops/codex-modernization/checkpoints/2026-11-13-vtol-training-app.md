# Standard VTOL camera application checkpoint

## Scope

Local Ubuntu Gazebo/PX4 standard quadplane, actual rendered camera, ordinary
supervised PixEagle and custom QGC. No physical aircraft, flashing, publication
or private-profile changes. Transition ends following and requires a new Start.

## Actual bench results

Evidence: `reports/sitl/follower-consolidation-20261111/training-vtol-bench-r3/`.
The run started from disarmed ground, then passed the existing seven-sample
progressing PX4 stable-Hold gate at 30 m relative altitude.

| Check | Observed result |
| --- | --- |
| QGC sign-in | admin/admin prefilled; association verified automatically |
| Rendered video and target | Actual Gazebo pixels through normal tracker/FramePublisher/QGC path; selection succeeded |
| MC Chase | QGC Start acquired native mode; QGC speed increased 1.0 → 1.5 m/s, revision 1 → 2 |
| MC Stop | QGC Stop ended publication; native receipt and PX4 status confirmed Hold |
| Transition | Explicit simulated-pilot FW transition ended following; no automatic restart |
| FW Navigation Chase | Calibrated source-clock gate passed; normal Start succeeded from a fresh rendered scene selection |
| FW speed | PX4-derived effective minimum ≈10.02 m/s and maximum 20 m/s; request ≈15.09 →15.59 m/s acknowledged |
| FW Stop | Confirmed native FW Hold; session speed controls retired |
| Teardown | Pilot MC transition, landing, observed disarm, token-owned cleanup and network removal |

The speed values are requests, not guaranteed vehicle speeds. FW used simulated
sensor airspeed; this is not sensorless-hardware qualification. An immediate
post-Start speed request was correctly refused while phase confirmation was
pending; a fresh available control then accepted the request without ending the
session. Do not replay that earlier rejected request.

Actual PX4 pose, raw native traffic, API responses and normal command/publication
traces are retained. No aircraft path was integrated from commands. These checks
establish this bounded application workflow, not arbitrary airframe performance,
vision accuracy, target interception or field safety. CSRT can drift during a
large camera-view change; following readiness does not establish semantic lock
on a particular world object.

## Repairs and delivery

The original native context survives startup awaits. Full observation rejection
cannot reuse an equal cached pose, older replies cannot retire newer evidence,
and tied publication timestamps permit only genuinely advancing estimator samples.
The first camera/attitude wait remains inside its original deadline. YAML numeric
wrappers now pass the same finite-positive camera configuration validation.

The first two combined launch failures are retained: Docker mount-list order and
the numeric YAML wrapper. Immediate restart now distinguishes a closed listener's
TIME_WAIT from an active server. Both airframes use the same canonical launcher.

The source snapshot originally lacked reachable release tags, producing firmware
version 0.0.0. Authentic upstream ancestry now identifies unchanged source HEAD
as `v1.18.0-beta1-1442-g155f415168`. A new version-pinned manifest and descriptors
preserve the previous evidence; no version string was invented or warning
suppressed. Courtyard-v4 adds collision-free ground features and orbit landmarks
without altering aircraft physics, camera extrinsics or controller parameters.

Software evidence includes 700 combined application checks, 253 alignment checks,
88 YAML/capture/config checks, 45 launcher checks and 226 delivery checks (sets
overlap). Separate QGC, native adapter/controller and build receipts are retained
beside their source checkpoints. Do not add these overlapping counts together.

Fresh ground handoff remains an operator acceptance checkpoint. Public defaults
and the private physical gimbal/tailsitter configuration remain unchanged.
