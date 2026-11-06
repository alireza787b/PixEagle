# Gimbal Vector airframe integration — active checkpoint

Baseline: PixEagle `ee4d30b71c51eb9583d7cfb390da44d297a60bc7` (remote main verified),
branch `feat/gimbal-vector-airframes-2026-11-06`. QGC baseline `12a2200d7`, with
client changes committed locally as `c7cfdfa13`, in
the `qgroundcontrol-pixeagle-webrtc-port` worktree. Hardware is not accessed or
modified by this implementation task. No new flight path is live-qualified.

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
   unrestricted-speed firmware policy and full application integration remain.
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

1. Finish the native owner/publisher binding in the application; retain one
   heartbeat/continuity/lifecycle owner and preserve guidance identity through
   command shaping. Never send MC zero defaults to the native FW contract.
2. Complete transition command continuity and shared recovery rebind in both
   directions. Do not add another target-loss timer or auto transition trigger.
3. Implement/qualify the owner-bound unrestricted native policy; stock firmware
   continues to report it unavailable. Do not disable underspeed protection.
4. Run the full independent actual-PX4 airframe matrix and 3D evidence export,
   then package/setup/client release gates. Request hardware only after this.

## Current integration details

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
- The remaining application phase owner must update generation/baseline before
  normal publisher validation, so a legitimate phase edge is not counted as a
  publisher fault. Preserve one continuity supervisor across MC/FW/transition;
  extend its current FW-only rebind to both directions without another loss
  timer. Keep MC accumulated travel when returning to MC; never apply it to FW.
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

A clarification is pending: “nose toward target” can mean the approved native
course/vertical-path objective or direct physical-body nose alignment. These
differ under wind and angle of attack. Continue the agreed native path design
until clarified; do not silently substitute direct pitch/throttle control.
The final moving-target animations must show target ray and actual nose/flight
path separately, with airspeed, throttle, altitude and active constraints.
This refinement has not enabled unrestricted behavior or changed hardware.

Independent read-only AI reviews found that body velocity cannot command native
FW EAS, raw physical FRD differs from MAVLink's heading-only BODY_NED convention,
and disabling a local maximum alone does not implement dive path priority.
Pinned PX4 reference: `155f415168cef08dca2f5d85d2bc258b44a589ec`.
The native design must additionally account for the full upper-speed clamp call
graph, mode-entry integrators, policy expiry, and tailsitter rate/attitude frames.

Hardware checkpoint requires a cooled Pi, healthy storage, separate firmware
installation/prop-off approval, and later aircraft qualification. Existing
storage diagnostics remain evidence; this task does not clear those findings.
