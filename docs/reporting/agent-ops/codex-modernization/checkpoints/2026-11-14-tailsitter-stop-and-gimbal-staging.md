# Tailsitter Stop repair and vertical-gimbal staging

## Operator evidence and closure

The operator accepted fixed-nose FW image pursuit but reported failed Stop and
subsequent Start refusal. The run is
`reports/sitl/follower-consolidation-20261111/training-tailsitter-nose-operator-r1`.
All six original token-owned containers, GUI, host relay/frontend and internal
network were closed after saving status and timestamped logs. Physical devices
were untouched. `stop-review-20261114` retains the pre-shutdown snapshots.

Native wire records one acquisition and 353 intent requests. Stop ended the
pursuit socket; subsequent observations retained the original acquisition,
fresh owner confirmation, external navigation state 23, neutral drain and
`release_pending=true`. Repeated Stop attempts did not resolve the receipt.
The backend retained `last_handoff.result=failed`. This is a genuine release
failure, not proof of a QGC transport or camera failure. Local publisher shutdown
must never be described as confirmed Hold.

The original capture does not log each DDS release request/Commander rejection,
so the exact reason the first native release was ineffective is **unconfirmed**.
Do not invent packet-loss or timeout causation from the failed receipt alone.
The code audit independently establishes a liveness defect: release dispatch was
one-shot, and read-only reconciliation could not repair a lost first dispatch.

## Shared repair

The adapter retransmits the identical original request only on progressing
native ownership status, inside the same frozen native deadline and under fresh
exact original Acquired/Releasing ownership. Terminal proof, takeover, rescue,
registration/incarnation change and expiry prevent retries. There is no new
acquisition, deadline renewal, global timeout increase or resumed pursuit.
The same path covers native MC/FW, transition exit, explicit Stop and EOF.
Ordinary MC MAVSDK control remains unchanged.

Native `observe` now records release dispatch count, request source-clock and
expiry, current source-clock and receipt state without exposing ownership tokens.
Backend cleanup failures are also logged rather than only appearing in an
action result. The component runner now exercises App's Stop ordering: immediate
failsafe invalidation/EOF, publisher join, original-acquisition reconciliation.
The current runtime asset and v5 evidence-contract pins are renewed together;
archived evidence is not rewritten.

## Verification boundary

The new native build passes 91 normal and 82 ASan/UBSan contract tests, including
frozen deadline, stale/replacement/takeover rejection and no resumed pursuit.
Build and extracted runtime:
`reports/native-guidance/native-release-repair-20261114-r1`.

The first actual tailsitter cycle confirms native Hold after MC phase exit and
FW Stop. Its full result remains failed: FW altitude-hold error reached 2.200 m
against the unchanged 2.000 m gate. End altitude recovered near the anchor; this
does not erase the exceeded envelope. The initial evidence-source pin mismatch
also prevents that capture from claiming fully attributed publication success.
Both failures remain in `stop-release-cycle-20261114-r1`; do not tune thresholds
merely to recolor the result.

The renewed EOF/application-order cycle (`stop-release-eof-cycle-20261114-r2`)
also confirms both original native Hold receipts, no publication failure and no
publication after Stop. FW's full response remains failed at 2.193 m excursion;
MC received-topic counts do not match its native counter exactly, so per-source
publication attribution stays unknown rather than being inferred. The gates and
final receipt are stored beside it. The deliberately dropped-release cycle
(`stop-release-drop-cycle-20261114-r3/release-proof.json`) confirms Hold after
dropping the first release delivery for each of the MC and FW acquisitions.
Forwarded retries keep the original source clock and expiry. Its full result
still reports the separate altitude-response and publication-attribution gates;
it is not relabelled passed. The fixture is loopback-namespace/token restricted
and introduces no normal runtime relay. Actual operator Stop/restart acceptance
remains required before closing this issue.
No firmware/controller gain, speed/altitude limit, public default or private
gimbal parameter was changed in this repair.

Backend/native integration gates passed 888 tests; the renewed evidence/runner
suites passed 627, and the fault/baseline suites passed 338 (these selections
overlap). Generated schema and critical Python lint passed. No QGC source or
binary changed in this repair.

## Next slices

The [camera mounting guide](../../../../trackers/06-integration/camera-mounting.md)
is the single setting/frame reference for users and agents. The
[training plan](../../../../followers/05-development/ubuntu-training-platform.md#inputs-frames-and-replacement-cameras)
orders shared Stop qualification, protocol parity, a pinned mechanical renderer,
the small aim/lock GUI, deterministic/actual SITL checks and operator acceptance.

Reuse Topotek SIP parsing, independent GAC/TRC freshness, canonical vertical
geometry and the retained FL-30/bench references. The old standalone simulator
is not proof of physical dynamics. Joint travel/rates, stabilization and combined
axis behavior need documented source or measured evidence before claiming an
exact hardware replica. The private October 27 configuration is an archived
comparison, not automatic authority for a newer tailsitter FW overlay.

Hardware reconnection is unnecessary for the initial software slices. Request
it only when an unmeasured physical convention blocks qualification or at the
later operator hardware checkpoint.

## Protocol/GUI slice completed

The existing `tools/gimbal_simulator.py` is now an input stimulus with one UDP
worker, production enums/checksum and independent GAC/TRC cadence. Captured
hardware packets decode through the real provider parser. Incorrect headers,
fabricated OFT angle broadcasts, duplicate enums, automatic package installation
and unmeasured smoothing/pattern motion were removed. The compact GUI uses the
existing installation configuration and shared inverse angle convention; both
mounts were exercised with real Tk layout/worker cleanup. It provides explicit
simulated lock/loss, Center and independent sample-freeze controls.

207 protocol/geometry/provider/documentation tests pass, including actual local
UDP delivery and unchanged forward geometry. See `gimbal-protocol-parity-final-r2.log`
and `gimbal-tk-smoke.log` in the common report directory. Tk was staged locally
from Ubuntu packages for this host check; no system package/service or runtime
configuration was modified. The [short tool guide](../../../../gimbal_simulator.md)
replaces the old misleading full-hardware-emulation instructions.

This slice does not rotate Gazebo or establish a native FW gimbal timing
association. All GUI and flight-test processes remain closed. No private camera
setting was changed.

## Source-time input slice

The operator chose the most practical simulation while the camera is offline.
Use verified SIP/mount conventions and explicitly ideal stabilized pointing;
unmeasured motor response, joint travel and image roll remain unqualified.

The Topotek provider now has an optional private simulator transport. It reuses
the parser, independent GAC/TRC caches and CameraRuntime lifecycle. Original
source stamps and producer receipts survive tracking; queued/paused data cannot
gain fresh timestamps. EOF, malformed/reordered packets and clock/incarnation
changes retire the source. Null `GAZEBO_INPUT` keeps factory UDP behavior.

The renamed shared `gazebo_guidance_alignment.py` binds both image and gimbal
contracts to retained raw PX4 samples. The same readiness/Start gate checks
native FW gimbal timing, mount revision, source owner and selection generation.
Hardware receipt-only input cannot claim simulator source-time qualification.
No synthetic pixels, latest-pose shortcut or fabricated receive-delay bounds
were added.

Initial gates: 160 provider/observation tests and 126 alignment/application tests
pass. Full domain/configuration gates and rendered-camera qualification follow.
Logs: `gimbal-stamped-input-r1.log`, `gimbal-shared-alignment-r2.log` in the common
report directory. These are deterministic/local transport checks, not flight
or rendered-model evidence. The prior FW altitude gate remains open.

## Rendered ideal model and GUI

Added one ideal world-stabilized pointing model, a separate static camera
instrumentation role and a local GUI. Source angles derive from actual Gazebo
camera/aircraft pose feedback; camera pose intents never stand in for measured
motion. World-point lock uses the explicitly entered fixture range. There is
no detector, inferred depth, guessed joint mechanics or aircraft command API.
Bad GUI input preserves current observations/target and reports rejection.

Actual component evidence:
`reports/sitl/follower-consolidation-20261111/gimbal-render-probe-20261114-r1/`.
`pose-and-image-receipt.json` and the before/after PNGs show moved camera pose
and changed rendered pixels. `gui-source-receipt.json` confirms real Tk aim,
finite lock, loss and release through the production SIP parser/CameraRuntime.
`gui-observed-source.jsonl` retains original stamps and receipts. Both owned
containers exited zero and were removed; the aircraft remained on the ground
with no aircraft commands sent.

A camera pose request may be applied despite a missing reply; only observed
pose feedback supplies angles. The Python probe's initial shutdown abort was
resolved by disposing transport explicitly before interpreter shutdown; final
probe and provider exits were zero. Earlier failed probes remain retained.

459 focused renderer/launcher/configuration/Phase 0 checks pass, plus 188
coastal scene/asset/role checks (counts overlap). Logs are
`gimbal-render-software-final-r1.log` and `gimbal-coastal-world-gates-r1.log`.
Native aircraft-following, full QGC operator Stop/restart and the unchanged FW
altitude gate remain separate acceptance items.

The operator additionally requested a richer PixEagle world. A reproducible
coastal scene adds branded signs/road art, cars, balloons, airship and vessels.
It uses pinned locally generated art and static visual props; moving objects,
hydrodynamics and collision qualification are not implied. See
`native/gazebo/README.md`. A fresh ground-start QGC/gimbal stack follows the
remaining software checks and actual scene-render inspection.

The first coastal full-stack launch retired cleanly before QGC opened: startup
uses round-trip YAML numeric subclasses, while the new simulator skew validator
incorrectly required a plain built-in float. It now accepts finite numeric
subclasses while continuing to reject booleans/nonfinite values. The same
round-trip fixture is checked through Config Sync and startup validation;
53 relevant source/profile regressions pass. The failed run remains at
`training-tailsitter-gimbal-coast-operator-r1`; a fresh run is required.

## Operator-feedback repair: frame-bound rendered selection

The staged coastal r2 operator run exposed an obstructed camera offset and an
input-only provider, not a complete camera-control acceptance fixture. Its
`operator-review-20261114/triage.json` and `altitude-review.png` retain actual
PX4 altitude and command intent separately. Both MC and FW intents were
observed; missing client speed controls remain an API/UI verification item.
The private hardware/public factory profiles have not been retuned.

The rendered fixture now declares a mesh-clearance offset and an explicitly
pinned RGB-D derivative with unchanged stock optics. Depth is hidden simulator
truth for clicking a finite scene surface; guidance still receives only the
production gimbal angle and tracking-status observations. This is not a new
3D hardware tracker or a hardware timing qualification.

One rendered-camera owner composes the existing bounded RGB stream, original
camera-pose/depth history, normalized camera commands and SIP input. QGC and
Dashboard continue using shared authenticated selection/control actions, camera
leases, lifecycle guards and retarget continuity. Provider resolution is
read-only and asynchronous before lifecycle mutation; original target/frame
and permission guards are rechecked after the await. Prepared selections are
bounded and cannot survive Stop, source replacement, another owner's mutation
or original-frame expiry. Unsupported controls are not advertised. Simulated
tracking becomes active only after fresh observed boresight alignment.

The first motion probe demonstrated that the normal 50 Hz scene broadcast does
not align every image stamp. It remains retained as a failed probe. A stock
read-only PosePublisher attached only to the instrumented camera supplies
simulation-step poses. The subsequent actual renderer probe passed with maximum
known-surface reconstruction error 0.000575 m. Source and exact commands are in
`rgbd-motion-selection-probe-20261114-r2`; no aircraft was present, container
exited 0 and was removed. This proves the selected scene-point association,
not aircraft guidance or mechanical FL-30 fidelity.

The launcher can now explicitly choose the existing bounded continuity policy
with `--continuity-mode bounded_decay`; factory defaults are unchanged.
Integrated MC/FW Start, retarget, speed UI, altitude response, Stop/restart and
operator acceptance are still required before calling this checkpoint ready.

Software slice gate: 683 focused camera/provider/selection/lifecycle/profile/
launcher/API/Phase 0 tests passed; generated schema matches defaults and the
critical Python lint gate passes. Results are in
`rendered-selection-software-r1.log` and `rendered-selection-schema-r1.log`.

Integrated controls validation r1 reached the normal backend and advertised
fresh camera status, point selection, pan/tilt/Home/Stop and manual gestures.
It then stopped on a >250 ms observed-pose gap. The ideal actuator incorrectly
classified that gap as unrecoverable source-clock corruption. The repaired
model rebases on fresh feedback with zero integration across the missing
interval, cancels latched manual motion and counts gaps. Regressions still
reject backwards/replaced timestamps. No-op camera pose requests are skipped
and unchanged GUI snapshots are limited to 10 Hz to avoid unnecessary service
and filesystem contention. The old failed run is retained unchanged.

The next integrated run remained available with fresh controls and clear
rendered video. During the operator's incidental check, Center and tilt exposed
two simulator semantics errors: Home kept camera pan, and manual tilt used
up-positive elevation against the shared clients' down-positive tilt contract.
The fixes use observed physical body-forward for Home and convert tilt once;
mount round-trip regressions cover both presets. Real camera motor dynamics
remain unqualified. Region selection now validates the whole normalized region
and uses its scene-center surface, without claiming vendor optical recognition.

A retained fresh-frame selection also encountered a false "fresh camera frame"
refusal: the async consumer's most recent poll was between acquisitions, while
the actual capture/retained displayed frame was recent. Camera admission now
shares one capture-age check for fresh or explicitly waiting connected sources.
It does not label cached imagery as fresh tracker measurements or weaken frame,
source, permission or target-generation checks. A genuinely failed/disconnected/
expired source still rejects.

## Superseded rendered attachment — next repair (2026-11-15)

The operator rejected hover lock jitter and a camera left behind during fast
MC/FW motion in the later staged runs. The separate static camera moved by
world `set_pose` calls is **not an accepted flight fixture**. All desktop stacks
are closed. Do not relaunch that mechanism or call the camera repairs ready.
The current camera API/mount/selection improvements remain useful, but do not
qualify attachment or pursuit response.

Official PX4 `x500_gimbal` attaches the stock articulated gimbal with a fixed
joint; Gazebo's JointPositionController explicitly supports ideal velocity-command
positioning without PID. We will reuse those standard mechanisms, with separately
pinned training resources, an explicit lightweight payload and source-observed
link/camera transforms. No custom world-position follower/plugin or second
camera guidance/aircraft publisher is needed. References:

- https://github.com/PX4/PX4-gazebo-models/blob/main/models/x500_gimbal/model.sdf
- https://docs.px4.io/main/en/sim_gazebo_gz/vehicles
- https://gazebosim.org/api/sim/8/classgz_1_1sim_1_1systems_1_1JointPositionController.html

`tools/gazebo_joint_gimbal.py`, `gazebo_gimbal_resources.py` and
`gazebo_geometry.py` establish the declared ZXY mechanism and shared ENU/FLU
boundary. 200 focused kinematics/resource/provider tests pass. An actual
**gravity-free carrier fixture**, not PX4 flight, passed 1998 observed pose rows
at measured approximately 0/5/20/40 m/s. Camera/body distance stayed below
1.228 m, and settled pointing error below 0.045°. Exact source, input commands,
observations and bounds are retained in `attached-gimbal-bench-r1`; container
exited 0 and was removed. This proves that component approach, not the final
stock tailsitter payload, limits, selection or operator workflow.

Next: pin a composite aircraft + physically attached gimbal scenario, feed
actual link/sensor observations through the existing SIP provider, replace the
world-pose actuator with joint targets, and remove the obsolete detached-camera
runtime branch. Then repeat MC/FW camera/pursuit/Stop gates before operator use.
The real camera remains 2D video plus gimbal angles/status. Hidden renderer depth
can remain simulator-only scene truth; no depth or 3D tracker requirement is
added to hardware. Camera mechanical properties remain explicit assumptions.

### Attached fixture integration (2026-11-15)

Schema 5 now pins the stock-aircraft/fixed-joint gimbal composite and actual
root/link/joint observations. The schema-4 detached camera resources, generator
and world-pose actuator are removed. Normal camera APIs retain exact-frame
point/region selection and motion leases. Read-only scene lookup holds neither
the follower lifecycle lock nor the tracker model lock; original admission is
revalidated before selection commit. `--no-operator-ui` permits the same full
runtime to be qualified before opening QGC/Gazebo/slider windows.

The first actual integrated hover exposed physics-rate telemetry flooding:
69,340 SIP packets and one source-side client failure; no following began in
that failed attempt. Delivery is now bounded to 50 Hz with immediate state
changes, a small nonblocking socket buffer and explicit dropped-sample counts.
Physics/link observation and exact image-pose history remain full-rate. The
regression fills a real SOCK_SEQPACKET buffer, verifies drops without closing
it, then verifies a fresh packet after the consumer recovers.

`training-attached-gimbal-integration-r2` subsequently verified actual stable
PX4 hover, region lock, normal Start, requests of 1 and 6 m/s, confirmed Stop,
and a fresh Start. Camera/body distance stayed below 1.228 m with no observed
pose gaps. Its FW stage remained **failed**: the orientation IK required a
world-level image and exceeded the stock roll bound during transition. The
training actuator now solves the optical ray with feasible ZXY joints, without
claiming unmeasured image-roll stabilization. Genuine unreachable directions
still reject; no mechanical limit is increased. Independent rotation-library
checks cover reachable directions, declared mount extrinsics, nearest branches
and unreachable rays. The new full MC/FW run is
`training-attached-gimbal-integration-r3`; its result is not yet accepted.

The pre-integration software gate passed 915 tests, schema check and critical
Python lint. After the telemetry and ray-only actuator changes, the focused
joint/provider gate passed 199 tests. The full relevant gate must be renewed
before publication. QGC and firmware/adapter binaries are unchanged. Public and
private hardware configurations remain untouched. No hardware test, deployment,
Windows rebuild or release is implied by these component/integration results.

### Reviewed final training gate

The original r3 smoke script falsely reported PASS after automatic FW recovery
Hold. `review-verdict.json` records its rejection without changing that original
capture. The gate now checks continuing active status and requires an actual
`operator_stop` / `confirmed_hold` receipt at every Stop. Measured source lead
was 4–76 ms (median 40 ms); the old 50 ms pairing bound repeatedly refused at
52–68 ms. One explicit launcher setting now supplies the shared image/angle
source-pairing tolerance, default 100 ms, with original stamps and actual skew
retained. Hardware age/authority/recovery limits are not relaxed.

The stock restricted gimbal also lost the view during bank. The final fixture
uses a physical 90° vertical installation and an explicitly ideal ±180° pitch
range. This is **not measured FL-30 travel**, and changes no hardware profile.
Image rotation is separate: the existing VideoSource orientation setting is
exposed by the profile/launcher; the vertical desktop uses 270°. Read-only field
introspection now reads canonical schema variants instead of calculating a
baseline command after session end, eliminating the observed teardown metadata
errors without weakening command guards.

`training-attached-gimbal-integration-r6/review/index.html` and `summary.json`
retain the accepted smoke result: 415/415 confirmed FW guidance samples, 46
active-status observations, three operator Stops confirmed Hold, no observed
pose gaps, actual PX4 speed up to 20.13 m/s and attached camera/body separation
at most 1.372 m. The review deliberately keeps PX4 local pose and independent
Gazebo optical/attachment metrics in their own frames. Commands are not
integrated into a fabricated aircraft path. This is simulator workflow evidence,
not field or hardware-envelope qualification.

Renewed software evidence: 920 relevant tests before the final profile settings;
326 final resource/profile/kinematics tests; 52 variable-rate/gap/backpressure
tests; 95 native guidance/teardown metadata regressions. The full unit sweep
had 7,470 passes, 11 optional GStreamer skips and two obsolete RTSP-specific
message assertions; those assertions were updated for the existing generic
camera-source message and all 82 video tests then passed. Display-rotation
profile tests cover all four orientations and invalid inputs. Schema and critical
lint are renewed before commit. No QGC/firmware/adapter binary changed.

Next: one fresh ground operator session using the reviewed fixture. Operator
acceptance, hardware mechanics/timing and the independently open FW altitude-hold
qualification remain separate. Do not publish a field-safety claim from this run.
