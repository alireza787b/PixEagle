# Ubuntu visual training platform plan

**Status: first MC camera stack implemented; operator qualification pending.**
Camera rendering and normal UDP ingestion have passed a disarmed check. The
full application, UI and airborne workflow are still being qualified; this does not establish flight
qualification. The [follower consolidation plan](follower-consolidation-plan.md)
remains authoritative for scope, admission, continuity and acceptance. The
current native engagement-altitude hold correction and pre-request source
phase/intention fence must be reviewed and qualified before full VTOL Start
through the application UI. Existing failures remain recorded.

Use the ordinary supervised PixEagle application, custom QGroundControl (QGC)
and actual PX4/Gazebo SITL, with a visible world, camera view and moving ground
targets. This extends the [SITL setup guide](../../drone-interface/04-infrastructure/sitl-setup.md)
and [follower qualification guide](sih-follower-qualification.md); it is not a
second control stack. User visual acceptance is required alongside recorded
evidence.

## Three explicit input modes

| Mode | Normal application path | Evidence boundary |
| --- | --- | --- |
| A: rendered camera | Gazebo camera → RTP/H.264 → `VideoHandler` → selected production tracker | Actual rendered images and tracker behaviour; simulator evidence only |
| B: mouse observations | Mouse canvas → registered simulation tracker → typed `TrackerOutput` | Synthetic 2D measurements, not computer-vision detection or real camera evidence |
| C: angle emulator | Sliders and independent tracking status → `GimbalInputProvider` → `CameraRuntime` → `GimbalTracker` | Emulated angle/lock observations, not mechanical joint response or confirmed physical target lock |

Begin with a generic declared training camera and direct emulated angle
observations. Mechanical gimbal joints are a later slice. Mode B converts GUI
fractions into the existing centred right/down tracker convention; it must not
invent range, ground position or camera exposure timing. Mode C retains separate
angle and tracking-status receipts, source lifecycle and mount identity using
the [existing provider contract](../../trackers/05-development/external-gimbal-providers.md).
Moving a slider or target never starts aircraft following.

The planned desktop entry opens one **PixEagle Simulator** window. Choose the
input mode and a compatible scenario, then use **Prepare aircraft** to run the
declared airborne preparation. Show readiness as observed, with a short reason
when unavailable. **Open QGC** opens the ordinary operator interface; selection,
following Start and Stop stay there or in Dashboard. **Reset session** closes the
owned run before preparing another. Mode B shows a mouse canvas; mode C shows
angle sliders and lock/loss controls. Keep resource paths, network namespaces and
runtime details behind a diagnostic view. Each run uses an isolated configuration
overlay and evidence directory, leaving saved public/private settings intact.

The existing validation injection endpoint can exercise an active follower but
cannot seed initial Start readiness. Mode B therefore needs a small input adapter
registered through the ordinary tracker lifecycle, rather than an App getter
replacement. All modes use real App construction, the shared target continuity
owner and the existing publication/teardown path. Do not use `AppController.__new__`,
eligibility substitutions, fabricated aircraft kinds or authoritative phase input.

## Scenario and resource contract

Keep scenario data beside the existing scenario library: version, backend/QGC
and simulator build identities, declared aircraft/world, input mode, follower,
mount, camera geometry, independent target trajectory, startup parameters,
airborne preparation and acceptance conditions. Reuse existing configuration
and geometry validation; do not create another configuration or policy service.

Select MC/FW/VTOL profiles from declared capabilities and current readiness.
Horizontal/vertical mount presets must agree with the physical camera
extrinsics; display rotation is separate. Real camera images do not establish
camera calibration or timing qualification by themselves. Keep world target
truth independent of the tracker, and never integrate commands into aircraft
pose. A synthetic cursor or angle ray has no independent target distance.

The pinned Gazebo resources include camera/gimbal models, camera streaming and
moving-platform support. The current native builder/verifier deliberately locks
the quad tailsitter, default world and expected scene entities. Other aircraft,
camera attachments and ground targets require reviewed, pinned manifest entries
and exact scene/resource checks, following the [Gazebo build contract](../../../native/gazebo-build.md).
Do not silently replace that authority with the older visual-plan image or allow
arbitrary models. Record added camera mass/inertia and all resource differences.

## Minimal implementation and qualification slices

1. **Desktop preflight:** verify the retained custom QGC build, Gazebo GUI/GPU,
   GStreamer decoding and authenticated browser connection without arming.
   Ubuntu 24.04, desktop sockets, browsers and QGC artifacts were found during
   planning; actual rendering and performance remain untested.
2. **Owned full stack:** reuse the canonical simulator launch/bootstrap, private
   rootfs, native socket and cleanup helpers; start normal PixEagle through its
   supervisor. Keep flight networking isolated, GUI/API access local and
   authenticated, and unrelated QGC serial/network auto-connect disabled. Grant
   only required same-user display/render access. No hardware routing or global
   service installation belongs to this launcher.
3. **One camera case:** qualify a declared MC camera/world with a visible ground
   target, then independent target motion. Verify frames, normal target selection,
   explicit Start, retarget, loss, Stop and fresh restart before expanding cases.
4. **Input adapters:** add B and C through their normal contracts, with visible
   synthetic-source labels. Frozen/closed panels must become stale or lost under
   existing rules; they cannot renew old samples or replay actions. Test source
   restart, delayed replies, retarget generations and rejected stale controls.
5. **Qualified expansion:** add declared FW/VTOL resources and both mounts after
   their prerequisites pass. Prepare airborne state through actual PX4 actions
   and observed stability, never teleportation or injected phase. Preparation,
   target selection and following Start remain distinct explicit actions. An
   unavailable profile remains visible with its real reason; no simulator-only
   permission flag bypasses admission.

Each slice needs focused contract tests and its actual integration evidence
before wider claims. Use the existing authenticated
[following](../../apis/native-following-operations.md),
[target](../../apis/native-target-operations.md) and
[camera](../../apis/native-camera-controls.md) actions, including their captured
contexts, confirmation, idempotency and Stop semantics. Reuse the
[read-only visualizer](../../drone-interface/06-development/sih-guidance-visualizer.md)
for evidence playback; do not turn it into another action client.

## Operator acceptance and reset

The initial `tools/run_gazebo_training.py --execute` launcher opens ordinary QGC
and Gazebo with a fresh private profile. Supply the verified build manifest,
scenario, QGC/Qt and installed Python/runtime paths shown by `--help`. It starts
MC Velocity Chase with explicit altitude guidance, CSRT, a local RTP camera and
the circuit breaker active. The local-only training account is `admin/admin`.
Sign-in, vehicle preparation, target selection and following remain distinct
normal operator actions. The MC Chase session-speed row uses the same capability
and action as Vector; other followers show it only after implementing that contract.

PX4, the normal backend sidecars and QGC share one owned internal Docker network
namespace. Only the authenticated API TCP port is published to host loopback;
camera and MAVLink UDP are never published. QGC has separate settings/cache and
one simulated UDP link; physical serial auto-connect is disabled. No saved user
profile is changed. Ctrl-C closes only the original token-bound containers,
retains logs and removes the empty owned network. A new run requires a new
directory; cleanup uncertainty prevents silent reuse.

Present Gazebo world view, the selected camera/input view and QGC together.
The user must visually confirm axes, mount orientation, target motion, following
response and fallback/recovery. Retain their observations with exact commands,
versions, configuration, source identities, action outcomes, native clocks,
publication/ownership traces and closed PX4/ground-truth logs. Preserve the
consolidation plan's pursuit and authority-held gates and full-flight plots;
native pilot-transition manoeuvres remain separately labelled, not hidden or
subtracted. Modes B/C cannot substitute for mode A tracker qualification, and
none qualifies hardware or a private airframe.

Reset uses the captured session and token-owned process/container identities,
closes logs and starts a fresh run/source incarnation. It must not resume an old
Start, discard failed evidence, stop unrelated processes or overwrite public or
private configuration. Any uncertain ownership/cleanup blocks another Start.
