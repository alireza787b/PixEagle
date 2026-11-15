# Ubuntu visual training platform plan

**Status: MC and standard-quadplane operator checks accepted; fixed-nose
tailsitter is the next operator checkpoint.** The accepted quadplane run covered
MC Chase, FW Navigation Chase, session-speed changes and confirmed Hold after
Stop. The [checkpoint](../../reporting/agent-ops/codex-modernization/checkpoints/2026-11-14-quadplane-acceptance-tailsitter.md)
records the evidence and remaining boundaries. This is simulator qualification,
not physical-aircraft acceptance. The [follower consolidation plan](follower-consolidation-plan.md)
remains authoritative; earlier failed evidence is retained.

Use the ordinary supervised PixEagle application, custom QGroundControl (QGC)
and actual PX4/Gazebo SITL, with a visible world, camera view and moving ground
targets. This extends the [SITL setup guide](../../drone-interface/04-infrastructure/sitl-setup.md)
and [follower qualification guide](sih-follower-qualification.md); it is not a
second control stack. User visual acceptance is required alongside recorded
evidence.

## Three explicit input modes

| Mode | Normal application path | Evidence boundary |
| --- | --- | --- |
| A: rendered camera | Gazebo camera → stamped image socket (VTOL) or RTP/H.264 (MC) → `VideoHandler` → selected production tracker | Actual rendered images and tracker behaviour; simulator evidence only |
| B: mouse observations | Mouse canvas → registered simulation tracker → typed `TrackerOutput` | Synthetic 2D measurements, not computer-vision detection or real camera evidence |
| C: angle emulator | Sliders and independent tracking status → `GimbalInputProvider` → `CameraRuntime` → `GimbalTracker` | Emulated angle/lock observations, not mechanical joint response or confirmed physical target lock |

Mode C supports standalone angle stimuli and an attached rendered gimbal.
The rendered variant uses Gazebo's standard articulated joints and measured
link poses; its mechanical parameters are explicit simulator assumptions.
Mode B converts GUI
fractions into the existing centred right/down tracker convention; it must not
invent range, ground position or camera exposure timing. Mode C retains separate
angle and tracking-status receipts, source lifecycle and mount identity using
the [existing provider contract](../../trackers/05-development/external-gimbal-providers.md).
Moving a slider or target never starts aircraft following.

The rendered Mode C checkpoint uses a fixed-joint camera attachment, native
joint-position controllers, source-stamped SIP input and world-point lock.
The rendered adapter exposes point selection and camera controls through the
normal API used by both clients. Private simulator depth holds the designated
scene point; the production follower receives only angles and tracking state.
Use the [gimbal tool guide](../../gimbal_simulator.md#rendered-gimbal-training)
for assumptions and controls. The [coastal scene](../../../native/gazebo/README.md)
adds varied static ground and aerial visual targets. The camera fixture adds
its separately declared 0.04 kg payload to the stock aircraft.

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
MC Velocity Chase by default, with explicit altitude guidance, CSRT, a local RTP camera and
the circuit breaker active. The local-only training account is `admin/admin`.
Sign-in, vehicle preparation, target selection and following remain distinct
normal operator actions. The MC Chase session-speed row uses the same capability
and action as Vector; other followers show it only after implementing that contract.

PX4, the normal backend sidecars and QGC share one owned internal Docker network
namespace. A standard `socat` TCP relay exposes only the authenticated API to host loopback;
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

### Standard quadplane runtime staging

The explicit `standard-vtol-mono-camera-courtyard-v4` scenario selects the stock
4004 standard VTOL airframe with its reviewed fixed camera wrapper and populated
world. The launcher requires `--adapter-bundle` and `--adapter-file-manifest` for
this declared VTOL scenario, verifies the pinned runtime assets and DDS status
source before staging, and starts the canonical DDS agent before the one-shot
adapter bootstrap. Its private socket is mounted at the normal application path
`/run/pixeagle/guidance.sock`. The adapter joins the original simulator namespace
and the existing token-owned cleanup list; no second MAVSDK connection is added.
The native baseline retains its stricter network-none verification unchanged.

This prepares transport availability, not following eligibility. The ordinary
VTOL catalog gate, source phase/intention fence and FW image timing/calibration
requirements remain in force. Current Gazebo RTP carries an encoder-time stamp,
not the original image acquisition stamp. A rendered-image source that retains
pixels and the Gazebo acquisition stamp together, aligned with bound native
attitude samples, is required before FW image Chase qualification. Starting a
scene or a native socket does not satisfy that requirement. The default pure-MC
launcher still requires no native adapter.

The shared adapter implementation is `tools/native_adapter_runtime.py`. New
source-evidence authorities must pin this dependency along with the caller;
historical frozen runtime receipts keep their original source authority.

For the standard VTOL camera scenario, `gazebo_camera_provider.py` subscribes to
actual Gazebo `Image` messages using the Python bindings already installed in the
verified firmware image. This separate unprivileged process explicitly overrides
the firmware entrypoint with Python; it never starts another PX4. It shares the
original simulator network namespace and Gazebo partition. Pixels and the
original simulation acquisition stamp travel in one bounded private Unix stream;
the original callback's host monotonic receipt is retained separately. There is
one latest pending image and one active same-user receiver. A stalled or closed
receiver is disconnected; a replacement receives only callbacks newer than its
accept time. The valid Gazebo source incarnation persists, while the backend
creates a fresh capture epoch. Source-clock reset or calibration change remains
fatal; there is no automatic source-reset recovery. No encoder timestamp or guessed delay becomes an
acquisition stamp.

The private profile selects `GAZEBO_CAMERA`, and QGC displays the backend's normal
FramePublisher output from those same images. The source descriptor records the
clock-source file/hash, selected world/model/topic, camera resource hash,
provider/protocol hashes and original container ID. Native attitude timestamp
mapping remains independently qualified; a socket or image alone grants none.
The default MC scenario keeps its UDP path.

### Phase-specific operator checkpoint

The native contract admits MC Chase only in settled MC phase and Native
Navigation Chase only in settled FW phase. It requires the verified ownership
and altitude-hold capabilities, fresh aircraft state and an original Start
context; a configured VTOL label grants none of these. A transition ends
following and requires a new operator Start after settling. MC Chase's ordinary
MAVSDK path remains unchanged for pure multicopters.

Native Navigation Chase additionally requires the calibrated rendered-image
source and matching raw PX4 sample clock before Start is offered. The same gate
is rechecked before acquisition. Its phase declaration makes this isolated
software checkpoint possible; it does not qualify arbitrary physical cameras,
real VTOL aircraft or the private steep-dive profile.

The training overlay explicitly enables altitude guidance in the shared General
setting and selected profile override, so changing from MC to FW Chase retains
the requested training behavior. Public saved defaults stay unchanged. Session
speed controls are advertised by each supported profile: MC requested velocity
and FW airspeed reference retain their separate limits and phase generations.
Source history, passive Start context and current aircraft state share one
connection owner. Delayed older replies cannot retire newer evidence; repeated
reads cannot renew sample age or replay an action.

### Fixed nose camera on a tailsitter

Select `--scenario quadtailsitter-nose-camera-courtyard-v1` and
`--follower-mode fw_navigation_chase` with the same verified native adapter.
The scenario uses stock airframe 4018, one fixed `mono_cam`, and the populated
courtyard. It adds the camera's 0.050 kg mass and declared inertia; it does not
retune the stock aircraft. The aircraft starts disarmed on the ground. Take off
in MC, transition through QGC, wait for settled FW, select a visible feature and
Start. Then test speed adjustment and Stop. Transition always ends following;
another Start is explicit. Initial circuit breaker remains on until the operator
disables it for this isolated simulator. Altitude guidance is explicitly enabled
in this training overlay, without changing factory or private profiles.

In hover the fixed nose camera looks upward; this is the installed geometry,
not missing video. In forward flight it sees the horizon. This first case is
FW-only image tracking; it does not claim useful MC image tracking from a
sky-facing camera. The later steerable/vertical-gimbal test is separate.

One scenario `camera_mount.pose` defines the fixed six-coordinate SDF pose in
`base_link_flu`. The same pose positions the Gazebo camera and derives its
optical-to-physical-body FRD quaternion. Gazebo cameras look along +X, whereas
the image optical frame looks along +Z ([Gazebo camera reference](https://gazebosim.org/api/sdformat/14/classsdf_1_1SDF__VERSION__NAMESPACE_1_1Camera.html)).
The nose pose is `[0, 0, 0.34, 0, -pi/2, 0]`; its optical center points along
physical body -Z. Full physical aircraft attitude then maps this ray into NED.
PX4's separate FW control-frame rotation is not reapplied to camera calibration.
Tests cover both image-axis signs and nonzero mount roll/pitch/yaw.

Other fixed tilt angles use this same calibration path, with an explicitly
pinned model/scenario. The position is a physical attachment; bearing-only
guidance does not infer range or implement lever-arm range compensation. There
is currently one active camera. A future dual-camera installation must provide
each source's own calibration and use the existing source/epoch invalidation;
automatic dual-camera switching is not implemented by this test.

### Next checkpoint: vertical external gimbal on the tailsitter

Implement and verify these slices in order. Do not reopen the operator stack
until the shared Stop repair has actual simulator evidence.

1. **Shared release repair:** correlate the retained failed Stop with native
   receipt and PX4 mode evidence. Test packet loss, delayed status, EOF, Stop,
   takeover and a fresh subsequent Start. A local sender stopping is not Hold.
2. **Mount documentation:** use the [single installation guide](../../trackers/06-integration/camera-mounting.md).
   Preserve factory defaults and the private profile; no client axis branches.
3. **Protocol fixture:** use the real `topotek_sip_udp` parser/control adapter,
   canonical vertical preset and independent angle/lock receipts. Pin the
   retained FL-30/SIP reference and measured vertical-mount bench evidence.
   Retire assumptions in the older standalone simulator that disagree with the
   production packet codec; do not copy a second protocol implementation.
4. **Rendered model:** the operator accepted ideal simulated mechanics while
   the camera is offline. Use the pinned stock gimbal derivative and a fixed
   attachment to the aircraft; never move a detached camera with world-pose
   service calls. Declare payload, joint limits, pointing rate and offset.
   Use actual Gazebo aircraft/camera pose
   and shared geometry to drive camera orientation. Distinguish a stabilized
   world bearing from a finite world-target lock: attitude compensation alone
   does not track a ground point as the aircraft translates. Reuse independent
   world-target truth for the target-lock case. Unknown motor rates, travel
   limits and stabilization dynamics remain declared simulation assumptions
   until backed by vendor data or measurements; protocol parity alone cannot
   establish an exact mechanical replica.
5. **Small training GUI:** intuitive left/right and up/down aim, angle readout,
   Reset, explicit simulated lock/loss and freeze/disconnect injection. Aim
   changes must rotate the rendered camera and update independent measured
   angles. Keep raw protocol axes in details, especially the vertical mount's
   roll-derived azimuth. Reuse the camera runtime/provider lifecycle and one
   simulation owner. GUI closure cannot renew stale tracking or resume flight.
6. **Deterministic and actual SITL gates:** both mounts, MC/FW attitude changes,
   mechanical saturation, target lock/loss, retargets, transport outages,
   transition-ending-follow, Stop/takeover and subsequent Start. Retain real PX4
   pose, target truth, raw angles, normalized ray, joint pose, command intent
   and terminal receipt in the existing visualization. Explicitly distinguish
   simulated camera lock from real visual tracking. The first ideal model
   cannot qualify physical joint saturation or actual motor response.
7. **Operator test:** start fresh on the ground with the vertical-gimbal
   training overlay, QGC and the GUI. Test MC first, Stop, transition, then a
   new FW Start. Keep the accepted private MC settings separate from the
   experimental FW overlay. Request hardware only for unmeasured camera
   mechanics/timing or the later physical checkpoint.

The declared pinhole calibration uses the unchanged SDF image size and horizontal
FOV, plus the fixed optical-to-body rotation. Gazebo's
[projection conversion](https://github.com/gazebosim/gz-rendering/blob/gz-rendering8/src/Utils.cc#L160)
places the principal point at half width/height for its symmetric projection.
The provider requires actual `camera_info` to confirm dimensions, intrinsics
(within 0.001 pixel for renderer float precision) and zero distortion before
exposing its socket. The original raw protobuf and callback receipt are retained
in `camera/camera-info.json`; later calibration changes retire the source. The
inert descriptor records `actual_camera_info_confirmation=false`; only the
separate actual startup receipt can confirm it. This is not a physical-camera
calibration claim.

The v2 scenario has an explicit server-config resource overlay that removes only
the global stock GstCameraSystem encoder; all other plugins must remain
structurally identical. It is staged read-only and included in actual runtime
resource verification. The old v1 descriptor and packaged build remain unchanged.
The first disarmed bench must independently confirm continuing stamped images
and absent unused RTP output; software/source checks alone are not that proof.

For the reviewed native adapter that advertises the raw simulator-clock seam,
the launcher forwards the exact same fresh `token:world` identifier as the camera
source through `simulator_clock_id`. The shared bootstrap rejects a different
token or nonliteral identifier before writing scripts. Legacy/default baseline
startup omits the parameter. Forwarding a tag is not clock qualification: the
application must require the matching native observation capability and raw
source sample timestamps before aligned image guidance is available.

### Native training wire evidence

When the verified native adapter is selected, a private token-owned recorder
container relays the normal App's sole native connection. The App keeps
`/run/pixeagle/guidance.sock`; its mount points at the recorder's front socket,
and only the recorder mounts the original adapter endpoint behind it. The
existing `WireRecorder` forwards original bytes and records attempts, actual
replies and EOF; reconnecting cannot replay a command.

`native-wire/logs/wire.jsonl` is private (0600 within 0700 directories), with
original host-monotonic receipt times, connection IDs and archived helper hashes.
The recorder's original CID joins the launcher's existing cleanup list. Its
image, UID, namespace and exact bind mounts are checked before App startup.
These are distinct training artifacts, not canonical network-none Runtime
authority or a claim of following, phase, altitude or delivery qualification.

### Current build scenario selection

`x500-mono-camera-board-v2` (MC, airframe 4010) and
`standard-vtol-mono-camera-courtyard-v3` (quadplane, airframe 4004) explicitly
share the reviewed protocol-5-era stock build. Select either through the same
`run_gazebo_training.py --scenario` argument. The MC v2 descriptor changes only
its name and manifest/image/ELF identity; its aircraft, camera, world, target,
spawn and resource hashes are identical to MC v1. It retains ordinary UDP image
ingestion and MAVSDK MC behavior without a native adapter requirement.
Historical descriptors stay bound to their original builds; this resource
selection is not new flight or following evidence.

Desktop bootstrap compares complete original mount records sorted by destination;
Docker's returned list order is not part of mount identity. Changes to source,
destination, write permission, mount type or propagation, and missing/duplicate
records still refuse startup. The retained first VTOL bench failure remains
unchanged; this comparison correction alone is not a successful runtime claim.

### Readiness repair and next operator check

See the [2026-11-14 repair checkpoint](../../reporting/agent-ops/codex-modernization/checkpoints/2026-11-14-follow-start-readiness.md).
The connection now collects passive native samples independently of UI polling;
QGC's following eligibility updates when target state changes or expires.
Freshness and timing tolerances are unchanged. Session-speed labels use the
backend step's precision; requests retain their exact acknowledged values.

The current image training scenario still selects MC Chase or FW Navigation
Chase explicitly. Automatic selection from an installed VTOL recipe is planned,
not implemented by these repairs. A recipe must reference qualified catalog
strategies, resolve once from fresh PX4 phase at Start, and instantiate only one
follower. It must not rewrite global configuration during a transition. Both
standard VTOL and tailsitter use the same phase/ownership contract; camera
visibility, mount geometry and source qualification remain independent.

After an interrupted host shutdown, old ground-ready receipts and launch hashes
are historical. Verify original container cleanup and regenerate the launcher
pins against the repaired backend, Dashboard and QGC before a new run. Never
adopt a previous run or replay its Start. Keep simulation stopped until the
operator requests the next session.
