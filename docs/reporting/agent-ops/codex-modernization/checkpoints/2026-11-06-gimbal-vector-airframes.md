# Gimbal Vector airframe integration — active checkpoint

Baseline: PixEagle `ee4d30b71c51eb9583d7cfb390da44d297a60bc7` (remote main verified),
branch `feat/gimbal-vector-airframes-2026-11-06`. QGC baseline `12a2200d7`, with
client changes committed locally as `c7cfdfa13`, in
the `qgroundcontrol-pixeagle-webrtc-port` worktree. Hardware is not accessed or
modified by this implementation task. No new flight path is live-qualified.

The PixEagle foundation is committed locally as `7bcce3c5f`, with phase binding
in `56cbbcafa`. Subsequent work remains on this feature branch. Nothing has been merged/released
or deployed to the Pi by this task.

## Accepted decisions

- One Gimbal Vector profile; strategy follows actual MC/FW/transition state.
- One canonical physical-body ray, full-quaternion NED conversion, and explicit
  heading-frame conversion at the MAVLink velocity boundary.
- Pure MC retains MAVSDK; FW/VTOL use a pinned native PX4 external-mode adapter.
  VTOL uses that owner throughout a session, including MC and transitions.
- PX4 owns energy/turn/transition control. Do not clone TECS on the companion.
- Keep session/target through authorized transition and resume only after fresh
  settled phase/authority/target confirmation. Rescue/takeover ends the session.
- FW reference starts at qualified current airspeed or PX4 trim, never MC zero.
  Source selection degrades automatically without treating ground speed as EAS.
- FW recovery is eight seconds on the existing continuity supervisor, without
  MC velocity decay or its four-metre budget. Terminal action is native loiter.
- Public speed policy respects PX4. Optional experimental no-upper-bound policy
  requires verified matching firmware, native path priority, retained underspeed
  protection, explicit finite commands and owner-bound expiry/reset.
- Existing MC tuning/private geometry and public beginner defaults are preserved.

## Implementation and acceptance ledger

1. Aircraft contracts: immutable connection-bound snapshots, qualified airspeed
   freshness, full physical FRD quaternion and explicit MAVLink heading-frame
   conversion implemented and unit tested. Native UID must match the verified
   connection. Pose is independently observed, never integrated from commands.
2. FW guidance, phase lifecycle and phase-specific speed contracts implemented
   and unit tested. The shared continuity supervisor has FW eight-second
   course/airspeed recovery and preserves the original episode deadline. Live
   recovery remains gated until the complete application publisher integration.
3. Native Linux x86-64 adapter, private bounded IPC, DDS Agent and reviewable PX4
   extension build. Native normal and sanitizer tests pass. Registration and
   read-only live SIH snapshots pass; initial airborne native FW course/altitude
   controller publication and confirmed loiter pass. ARM64/setup installation,
   unrestricted-speed firmware policy and actual-PX4 application qualification remain.
4. API, Dashboard and QGC negotiate speed-control contract version 2. FW EAS is
   never labeled as MC 3D speed; stale phase-generation edits are rejected.
   Older clients do not receive unsupported FW controls. Phase policy defaults
   use Config Sync; no saved installation is silently changed.
5. Renewed backend foundation gate: 1,057 passed, one existing Starlette
   deprecation warning. Dashboard: 65 suites,
   520 tests plus production build. QGC build/lint/client test passed; 470/476
   Unit/Integration tests passed initially, all six passed on targeted rerun
   after supplying missing host GStreamer/Ninja tools and running the timeout
   test separately. Native: 19 contracts with ASan/UBSan; three firmware
   compare-and-change regression cases passed. Schema gate passed.
6. All-airframe moving-target qualification (`sihsim_quadx`, `sihsim_airplane`,
   `sihsim_xvert`, standard VTOL), native policy tests, reusable 3D evidence,
   Windows-first bench build and reviewed publication remain open. No release
   or qualified-hardware claim before these gates.

## Current evidence

Development logs are under
`/home/alireza/.cache/pixeagle-native-guidance/`; the isolated build container
is `pixeagle-native-build` on a Docker bridge. PX4/DDS test traffic uses container
loopback; no hardware endpoint is used.

- `backend-gate-renewed.log`, `schema-gate.log`, `dashboard-full-test.log`,
  `dashboard-build.log`, `qgc-build.log`, `qgc-lint.log`, `qgc-full-test.log`,
  `qgc-host-retest.log`, `qgc-client-test.log`.
- `mode-build.log`, `native-sanitizer.log`, `expected-mode-guard-test.log`,
  `px4-status-build.log`, `ros-status-build.log`, `xrce-build.log`.
- Adapter runtime evidence is in the container/cache `native-runtime/`:
  `observations-2.jsonl` (55 complete fresh observations, no publications),
  `airborne-observations-2.jsonl` (91 complete observations), and
  `native-controller-probe.jsonl` (80 accepted objectives, 145 native
  publications, actual heading response and confirmed final loiter).
- `native-takeover-probe-v2.jsonl`: actual RTL preserved after a deliberately
  delayed guarded Hold, no later native publications and stale cleanup rejected.

The native-controller probe is a command-boundary test, not a production
follower acceptance run. It does not close moving-target, transition, rescue,
phase-specific control ownership or hardware qualification.

## Next implementation order

1. Qualify the application native owner against actual independent moving
   targets. Keep one publisher/continuity/lifecycle owner; never send MC zero
   defaults to FW. Pure-MC heading-frame conversion is now implemented and
   deterministic-tested; include it and both mounts at nonzero tilt in SIH.
2. Verify transition command continuity and shared recovery rebind in both
   directions on actual PX4. Do not add another loss timer or transition trigger.
3. Implement/qualify the owner-bound unrestricted native policy; stock firmware
   continues to report it unavailable. Do not disable underspeed protection.
4. Run the full independent actual-PX4 airframe matrix and 3D evidence export,
   then package/setup/client release gates. Request hardware only after this.

## Current integration details

- `GimbalVectorSession` now binds the existing registered Vector follower to
  the shared phase lifecycle, separate MC/FW requests and native FW guidance.
  It adopts the existing MC control declaration, rather than maintaining a
  second active MC speed value. MC calculations are reused; the native path
  applies physical FRD → full-quaternion NED → heading-frame conversion once.
  Both mounts are tested through the registered follower with pitch/roll/yaw.
- Shared continuity now supports paused pursuit and bidirectional phase rebind.
  Genuine loss during transition starts the same episode; confirmation,
  repeated retargets and phase changes cannot renew its deadline. MC travel is
  retained across phase changes, frozen during transition/FW, and resumes only
  under MC policy. Pause cannot authorize MC translation or FW descent.
- The native publisher has an observation hook for application phase binding.
  It advances native generations before submitting a new contract, accepts the
  next generation while its acknowledgement is pending, preserves newer
  tracker intents and records the effective contract in publication evidence.
  Failed binding revokes the socket. The application now installs this hook
  when the matching native runtime is present; ordinary setup does not install
  that development runtime yet.
- Camera angle receipt time now advances classifier dwell. Processing the same
  angle repeatedly cannot complete vertical/rearward confirmation. Provider
  geometry is checked before filtering, in physical FRD, for both strategies.
  FW final command guards reuse the native speed/vertical/altitude envelope
  after continuity blending and never apply MC component-speed limits to EAS.
- Integration gate: 1,326 backend cases passed after the final publisher race
  additions; the focused publisher gate passed 28/28. The final combined
  evidence is `backend-phase-final-gate.log`. Fatal Python checks passed for changed
  modules. The repository's existing unused-import warnings in large legacy
  API modules are separate from these changes.

- `NativeCommandTransport` now uses the existing `OffboardCommander` schedule.
  Native start requires a complete fresh initial objective; native stale/Stop
  handling cannot emit MC zero defaults. Repeated publication retains the
  original intent expiry. Immediate socket revocation bypasses a blocked status
  exchange; the C++ server detects EOF even during a pending reply.
- `PX4InterfaceManager.prepare_native_guidance` is read-only, verifies the
  connection binding and commits to its one aircraft-state owner. Connection or
  telemetry generation changes revoke the native socket. Observed MAVLink
  aircraft kind is available for transport choice, not for guessing VTOL phase.
- The native phase resolver pauses pursuit on positive transition evidence or
  disagreement between independently delivered vehicle/VTOL status. Settled
  pursuit requires agreement. During settlement the adapter supplies the safe
  contract for the native helper's actual phase. It does not request transitions.
- The application binding updates generation/baseline before normal publisher
  validation, so a legitimate phase edge is not counted as a publisher fault.
  One continuity supervisor persists across MC/FW/transition, with the tested
  bidirectional rebind and no additional loss timer.
  Keep MC accumulated travel when returning to MC; never apply it to FW.
- Dynamic native load limits do not revise an editor on every telemetry tick.
  Each action still checks current bounds; parameter provenance, phase and
  request revisions invalidate stale edits. Acknowledged requests survive
  temporary native floor changes and phase re-entry.
- The independent target fixture now covers rearward and vertical targets for
  both mounts. `GimbalGuidanceClassifier.provider_ray` allows navigation-frame
  guidance while applying provider limits in physical body FRD. Complete the
  MC application frame conversion and fresh angle-sequence/dwell cases before
  flight acceptance; do not rotate the tailsitter mount twice.

## Operator refinement — 2026-11-06

The unrestricted FW option must prioritize target-directed descent rather than
pitching away solely to enforce an upper-speed ceiling. Consider an optional
`MIN_DIVE_THROTTLE`, default unset/native behavior, applied only to an authorized
unrestricted descent through PX4's existing longitudinal configuration. It must
expire/restore with the same owner-bound policy and stay within actuator limits.
No second throttle controller or saved global PX4-parameter rewrite is intended.

The operator clarified that “nose toward target” means the **flight path**,
not direct physical-body nose alignment. Retain native course/vertical-path
objectives; do not substitute direct pitch/throttle control. Once the requested
path is established, exceeding the normal upper speed bound alone must not
redirect it under the experimental policy. Underspeed, altitude, attitude and
actuator constraints remain active.
The final moving-target animations must show target ray and actual nose/flight
path separately, with airspeed, throttle, altitude and active constraints.
This refinement has not enabled unrestricted behavior or changed hardware.

## Shared policy and frame checkpoint

- `FixedWingGuidance` is the canonical policy for native FW guidance, with
  `UPPER_SPEED_POLICY` and optional normalized `MIN_DIVE_THROTTLE`. The frozen
  typed policy does not implement another controller. Factory behavior remains
  normal PX4 limits/native throttle; missing saved settings remain compatible.
- Configuring an unavailable experiment resolves to normal native behavior and
  reports `unrestricted_speed_not_supported`. It must not advertise successful
  unrestricted activation or create an unbounded session control on unsupported
  firmware. MC behavior remains independent of the FW experiment.
- `Follower.AIRFRAME_LAYOUT` defaults to `AUTO`. Optional installation choices
  are MC, FW, standard/tilt VTOL and tailsitter. They verify observed layout and
  never establish the current phase or modify the camera mounting preset.
- The native frame audit found that local-position heading is not the native FW
  frame for tailsitters. The reviewable firmware observation patch now exports
  the FW controller's already-transformed heading/forward axis and actual
  attitude sample age. The adapter uses that fresh matching frame in FW, while
  preserving physical attitude and MC yaw for their original contracts. No
  second tailsitter rotation is implemented on the companion.
- Updated PX4 SIH firmware and ROS messages compile. Native normal and
  ASan/UBSan gates each pass 28 cases. The combined backend/configuration gate
  passed 1,545 cases, including graceful normal-envelope fallback instead of
  claiming unsupported experimental capability.
- Native phase changes invalidate the old pursuit contract immediately. While
  the same original command lease is unexpired, the adapter publishes the
  appropriate MC hold, transition setpoints or level FW objective pending the
  backend's new generation. This cannot renew a deadline or survive takeover,
  rescue or expiry. Native load-dependent minimum speed may exceed trim and
  remains authoritative during that hold.
- `fw_attitude_rate` still has its older direct-rate/thrust contract. It does not
  inherit the native policy simply because it shares FW terminology. Porting
  its guidance input to the same native owner is required before that mode can
  advertise consistent path priority/minimum dive throttle. Do not copy a local
  upper-limit bypass or retain another long-term TECS implementation.

No hardware or installed profile was changed. Public guide:
[shared FW policy](../../../../followers/04-configuration/fixed-wing-guidance-policy.md).

## Application lifecycle checkpoint

- Profile metadata declares native phase capability; there are no follower-name
  checks in transport selection. Fresh observed aircraft kind selects pure-MC
  MAVSDK versus one native owner for FW/VTOL. Explicit layout mismatch fails
  before command acquisition. Tailsitter subtype is verified from native state.
- Startup prepares observations, freezes configuration, engages explicitly and
  seeds a complete phase-safe intent before starting the existing publisher.
  VTOL uses the same owner from MC engagement through both transitions. Legacy
  missing FW recovery requires Config Sync before engagement; it is not silently
  replaced with new authority. Preparation failure never sends MAVSDK Hold.
- Stop joins the publisher before native handoff, revokes phase controls before
  awaiting teardown and preserves unresolved cleanup. Delayed MAVLink Offboard
  exit cannot revoke a newer registered native mode. Terminal phase reasons are
  retained across publisher cleanup. Speed editing uses actual native ownership
  and pauses during phase confirmation rather than requiring MAVLink Offboard.
- The typed continuity API now accepts `bounded_flight` and retains effective
  policy/origin, phase pause and command fields. Pending configuration is
  rechecked before connection, preventing an unqualified direct-rate FW mode
  from bypassing the start gate after the initial profile check.
- Schema: 44 sections / 616 parameters. Native/sanitizer contracts remain 28
  each; the combined backend/API/configuration gate passes 1,590 cases in
  `native-app-final-20261107.log`. New lifecycle and binding regressions are in
  `test_native_follow_application.py` and `test_native_follow_binding.py`.
- Native telemetry reads the current adapter-accepted publication, not the MC
  schema's default fields. Expired, retired and cross-phase commands remain
  unknown without falling back to legacy telemetry. Guidance generation stays
  attached. The session-relative native publication counter is separate from
  local acknowledgements; missing/reset counts cannot claim publication.

This is software composition evidence, not all-airframe or aircraft acceptance.
The native unrestricted policy, optional dive-throttle implementation, legacy
FW input adoption, actual transition/moving-target matrix, visualizer extension,
packaging and deployment remain open. No new hardware test is requested yet.

## MC frame checkpoint — 2026-11-07

Pure MC now uses the same physical FRD → NED → MAVLink heading-frame helper as
native VTOL MC. The existing telemetry owner supplies measured attitude and its
actual receipt age; unknown/stale attitude cannot become level flight by
default. The legacy MAVSDK camera-yaw view is removed when deriving physical
attitude; MAVLink2REST already supplies physical angles. Preview attitude stays
explicitly synthetic. Speed/acceleration/yaw gains and safety limits are unchanged.

Independent axis fixtures and both mounts at combined pitch/roll/yaw pass,
including ±180° heading and altitude disabled without horizontal redistribution.
The combined gate passes 1,608 tests in `mc-command-frame-combined-20261107.log`.
The pinned native image rebuild separately passes 28 normal and 28 ASan/UBSan
tests in `reproducible-application-20261107.log`. These are software gates;
new actual moving-target/VTOL evidence remains required.

## Readable boundary evidence

`reports/sitl/native-vector-boundary-20261106/` retains the raw transcripts,
ULogs, exact probe drivers, SHA-256 inventory, synchronized CSV and a static
`summary.png`. It shows an approximately 20° course step and 19.46° observed
heading change, 14.64–15.58 m/s sensor EAS and 24.33–24.42 m relative altitude.
The 80 accepted objectives and 145 native publications ended in observed
loiter. This short run has no target-truth trajectory and is labeled controller
boundary evidence; do not add it to the fully qualified follower gallery.
It predates the foundation commit, so that later commit is not claimed as an
exact capture-time source revision. New qualification runs must capture exact
commits and configuration before starting.

Independent read-only AI reviews found that body velocity cannot command native
FW EAS, raw physical FRD differs from MAVLink's heading-only BODY_NED convention,
and disabling a local maximum alone does not implement dive path priority.
Pinned PX4 reference: `155f415168cef08dca2f5d85d2bc258b44a589ec`.
The native design must additionally account for the full upper-speed clamp call
graph, mode-entry integrators, policy expiry, and tailsitter rate/attitude frames.

Hardware checkpoint requires a cooled Pi, healthy storage, separate firmware
installation/prop-off approval, and later aircraft qualification. Existing
storage diagnostics remain evidence; this task does not clear those findings.

## Native report checkpoint — 2026-11-07

The existing evidence reader and offline viewer now support version-2 native
FW/VTOL contracts, deriving profile compatibility from the canonical command
registry. FW course, EAS request, observed EAS and native effective reference stay
separate from MC velocity magnitude. Actual per-sample contracts select the
display during VTOL phase changes. Missing native FW frame evidence stays
unknown, successful publication wins over a proposed command, and independent
target truth wins over tracker-side target coordinates.

The report uses per-unit timeline strips, recorded playback timing, bounded
viewport fitting for long FW paths, and phase-aware PNG/CSV exports. Its one
embedded JavaScript file remains part of the self-contained HTML output.
Fifty focused tests pass; a headless Chrome check loaded the native fixture
without script errors and displayed the separate EAS values correctly. The
fixture is explicitly synthetic and is not new aircraft-response evidence.

The isolated airplane instance is disarmed; read-only observations confirm the
pinned firmware, UID, native frame and 10/15/20 m/s minimum/trim/maximum envelope.
Moving-target native follower evidence and the remaining firmware policy,
transition, legacy-FW adoption and deployment gates are still open.

## Actual moving-target FW component matrix — 2026-11-07

Capture revision `3b3e172cf` exercised the registered Vector follower, native
phase binding, shared continuity supervisor and existing command publisher
against an independent moving world target on the pinned SIH airplane. The
temporary simulator overlay explicitly disabled its circuit breaker; public
and installed configurations were unchanged. Each run began from seven fresh,
settled airborne Hold samples. Targets were frozen in world coordinates before
engagement, not repositioned relative to the pursuing aircraft.

| Mount / altitude guidance | Observed target range | Maximum hold error | Relative altitude, start → Hold | Command submissions / failures |
| --- | --- | --- | --- | --- |
| Vertical / off | 163.8 → 26.4 m | 0.138 m | 34.5 → 34.6 m | 295 / 0 |
| Horizontal / off | 163.8 → 23.0 m | 0.333 m | 34.6 → 34.9 m | 295 / 0 |
| Vertical / on | 164.0 → 33.5 m | not applicable | 35.0 → 26.7 m | 295 / 0 |
| Horizontal / on | 164.0 → 28.5 m | not applicable | 27.0 → 18.5 m | 295 / 0 |

All four 15-second approaches confirmed Hold and unchanged native publication
counters afterward. There were 1,180 successful submissions, zero publication
failures and 1,800 observed native publications. Requested/native-effective EAS
and measured EAS remain separate. These are component response checks, not
interception/landing, full application startup, VTOL or aircraft acceptance.

The canonical report is
`reports/sitl/native-vector-fw-matrix-20261107/index.html`; a Desktop shortcut
points to the same directory. It includes selectable 3D replays, synchronized
traces, PNG/CSV/JSON, exact configuration/source revision, build-source and
binary hashes, native envelopes, parameters, runtime logs and the compressed
full-session ULog. The browser check exercised playback, scrubbing and view
reset without script errors.

An initial engagement during an insufficiently settled point showed about 5 m
altitude deviation. Its evidence is retained in the task cache. The gate now
requires settled Hold near the selected test altitude and checks independent
response, rather than declaring success from publication alone. Later, after
all sessions ended in Hold, the idle adapter exited with an FMU-request timeout.
Supervisor/reconnection qualification remains open; this is not an active-flight
recovery pass. The owned simulator was subsequently shut down to close its log.

The subsequent transition regression reproduced a retained MC filter ray
overriding the first FW direction after a 90° physical rotation. Both mount
fixtures failed before the repair and pass afterward. Only measurement filter
state follows guidance generation; same-phase filtering, phase speed requests,
command ownership and continuity budgets remain intact. The focused follower
and application/binding gate passes 479 tests. Actual VTOL transition validation
is still required.

The renewed combined follower/lifecycle/continuity/aircraft/configuration/API
and viewer gate passes 1,682 tests in `native-guidance-final-20261107.log`.
The generated schema remains current at 44 sections / 616 parameters. The
existing Starlette 422 deprecation warning is unrelated to these changes.
All 98 archived artifact checksums and all four browser replays pass. Native
C++ sources are unchanged from the earlier 28 normal / 28 sanitizer build;
no Dashboard or QGC source changed in this checkpoint.

## Tailsitter observation repair — 2026-11-07

The disarmed `sihsim_xvert` probe reproduced an observation-extension defect:
the FW-frame bank/load factor is singular while the wing is upright in MC.
It reported a 28,963 m/s minimum and the backend correctly refused the
inconsistent envelope. The extension now reports PX4's unloaded minimum in
MC/transition and retains load-dependent minimums in settled FW. No controller
gains, saved PX4 parameters, underspeed logic or backend validators were changed.

The same probe exposed a second source-contract error. Unchanged PX4 VTOL
status is published at 1 Hz, but the adapter used a one-second expiry including
that interval. Two of 91 normal samples became incomplete. The source-specific
budget now includes its known sample interval plus the existing delivery
allowance. Vehicle-owner, pose and command-lease deadlines are unchanged.
Private diagnostics expose both status ages/budgets. A ten-second repeat
observed 182/182 complete fresh samples, minimum 10 m/s, with no acquired owner.
Maximum VTOL sample age was 1.016 s; maximum vehicle-status age was 0.517 s.

The updated pinned SIH firmware compiled successfully. The reproducible native
image passes 31 normal and 31 ASan/UBSan tests, including ordinary heartbeat
cadence, missing/stale/future samples and unchanged vehicle-owner expiry.
Firmware patch/source checksums were renewed. Live transition/flight response
has not yet been qualified by this ground observation repair.

The return-to-MC regression additionally found that submitted FW course/EAS
history could reach the MC velocity limiter. One shared command-history reset
now separates phase contracts without clearing controls or continuity budgets.
MC filter/ramp/yaw state uses its existing reset path; MC-only safety-envelope
binding is restored from the stored MC control. FW edits cannot supply an MC
velocity envelope. Both mount tests include forward and return transitions,
fresh-ray guidance, a paused zero-velocity baseline and resumed bounded motion.
The focused follower/application/binding/harness gate passes 494 tests.

## Aggregate observation progress — 2026-11-07

The first live tailsitter transition attempt reached normal MC pursuit, then
requested safe Hold at the phase edge with `native_aircraft_state_rejected`.
The native snapshot had used the position timestamp as progress: a status/phase
packet can arrive before the next position packet. The state owner and phase
owner incorrectly treated that valid aggregate change as reordered data.

Native aggregate sequence now advances only on accepted source arrivals,
including phase status. Polling does not advance it. The oldest measurement's
receipt timestamp stays unchanged; status updates cannot refresh old pose or
airspeed. Backend owners accept equal oldest-component time only with new
sequence progress, still reject backward/duplicate data, and still expire stale
measurements. The original PX4 position timestamp remains separate in pose
evidence. No target/flight authority is reacquired by this repair.

The focused aircraft/binding/transport/phase gate passes 109 tests. The pinned
native image passes 33 normal and 33 ASan/UBSan tests. The failed attempt and
confirmed cleanup remain retained in the task cache; both transition directions
still require an actual successful repeat before acceptance.

The aggregate-progress repeat completed MC → transition → FW → transition → MC
under one native owner. All 785 submissions succeeded, 1,200 native publications
were observed, and Stop confirmed Hold with no later publication. All 834
observations (including pre-engagement samples) remained fresh. The retained MC
request was 6 m/s on both sides of the cycle. This proves the repaired phase
boundary for this run, not full transition acceptance: the scenario failed its
range and 2 m altitude checks (163.8 → 245.7 m; 2.831 m maximum altitude change).
The target outran much of the unchanged 0.25 m/s² MC ramp, and the altitude dip
occurred just after FW entry at a minimum-clipped 10 m/s reference. Both require
separate response investigation. Raw data and the replay remain in the task
cache `sih-20261107/xvert-aggregate/vector-cycle-attempt2/`.

The renewed combined software gate passes 1,685 tests. The component harness
now accepts the existing version-2 world-target YAML without moving its target
relative to the drone. It records actual phase lifecycle/generation, effective
continuity policy and per-phase response spans. Unsupported fault/speed scenario
edits are refused explicitly. Overall failed checks remain failed; scenario
selection is not a substitute for qualifying the flight response.
