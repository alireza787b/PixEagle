# QGC slice 4b.4 — target continuity and altitude retest

## Scope and implementation

The v8 operator run demonstrated camera reacquisition after taps, but its two
unexpected Hold transitions met the former three-second retarget deadline. It
did not correlate a new target with a published command and independent PX4
response. This slice keeps the simulated-aircraft gate open until that evidence
is captured.

- `src/classes/target_continuity.py` owns an eight-second/four-meter episode
  shared by camera retarget and ordinary target loss. A repeated tap does not
  reset that episode. Retargeting blends fresh camera-selection guidance into
  bounded prior horizontal motion; stable reacquisition and a short ramp return
  full guidance. Ordinary loss decays horizontal motion with zero yaw and
  vertical velocity. Authority, telemetry, Offboard, Stop and publisher guards
  retain immediate precedence.
- `src/classes/app_controller.py` and `src/classes/gimbal_control.py` reserve
  replacement-target generations before camera execution, reject stale and
  superseded output, refresh continuity during a stalled video/camera update,
  and clear motion before Stop waits for a camera-selection barrier. Confirmed
  Hold is handled once per episode.
- Both gimbal followers now apply the shared altitude warning/hard-limit guard
  in `src/classes/followers/base_follower.py`. Their camera-profile overrides
  enable climb/descent; the ordinary local-tracker default remains unchanged.
  `tools/prepare_sitl_gimbal_profile.py` selects coordinated-turn Vector for
  this private SIH profile.
- The native following response and QGC compact status expose the continuity
  phase and altitude-limited guidance. Validation-only JSONL traces in
  `src/classes/tracker_trace.py` correlate target generation, command intent,
  completed publication result and separately observed PX4 yaw/altitude.
  Configuration, schema and follower/API guides were updated together.

## Validation

- PixEagle unit suite: **3,240 passed, 41 skipped**, 14 subtests passed.
  Integration suite: **185 passed**. Focused route/tool-candidate inventory:
  **13 passed** after regeneration; schema check and Python compile checks
  passed. Tests include bounded retarget/loss, repeated taps, frame-stall
  renewal, selection cancellation, Stop preemption, vertical guards and both
  follower direction paths.
- Dashboard: **489 tests across 64 suites**, production build and ESLint passed.
- Custom QGC debug build passed; Unit/Integration CTest passed **413/413** with
  CI timeout settings, locked Ninja on `PATH`, and `Flaky|Network` exclusions.
  The shorter local GPS timeout was reproduced in stock QGC; it was not
  classified as a PixEagle regression. The touched C++ file passed
  clang-format. Both worktrees passed `git diff --check`.
- The private v11 profile passed validation, read-only SIH startup probe and
  read-only QGC handoff check. It observed a fresh camera image and angles,
  simulated PX4 UID, QGC UDP system 1 traffic, and an active PixEagle flight
  command block. No follower command was sent in this probe. The owned Docker
  stack stopped after the check.

Evidence: `/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4-2026-10-01/camera-sih-operator-v11/logs/`;
operator instructions: `/home/alireza/qgroundcontrol-pixeagle/custom-pixeagle/OPERATOR-RETEST-4B-4.md`.
The tested QGC binary SHA-256 is
`5d36d7c91370ee0836cfee0715589ccee31a407c6d70d4f622c4d04f066efe64`.
The v8 and v10 evidence remain preserved separately.

## Open gate and next slice

The v11 operator SIH run must show a confirmed replacement target, a matching
successfully published yaw or vertical command, and an independently observed
simulated yaw or altitude trend for Chase and coordinated-turn Vector. It must
also exercise loss/reacquisition, budget expiry, altitude warning limits, Stop
and Hold. Camera image motion cannot prove simulated-aircraft response because
the real camera image is not coupled to PX4 SIH. Review the timestamped v11
trace and logs after the operator run; resolve any discrepancy before marking
4b.4 accepted. No real-aircraft, deployment or physical motor-stop claim is
made here. Network/load qualification and platform release remain later gates.

## v11 operator finding and v12 correction

The v11 operator run exposed a camera-owned retarget failure during active
following. The camera reported `TRACKING_ACTIVE` briefly after a tap, then
`TARGET_SELECTION` and `DISABLED`; six target changes reached the retarget
deadline. The native action audit recorded 43 validated camera controls but
only 19 terminal successes and one terminal failure. The selection transaction
advanced its own target revision before sending the final camera location
command, then compared the request's older revision with that new revision.
It also rechecked the age of the original displayed frame after the camera
handshake. The admitted tap could therefore be rejected after tracking had
already been disabled. The raw camera location packet was not captured, so
the absent final command is inferred from the code path and regression tests.

The v11 publisher trace contains 2,140 successful Offboard publications, with
simulated yaw spanning -93.86 to 32.59 degrees and relative altitude spanning
8.98 to 14.08 m over the whole session. Those ranges do not demonstrate that
each retarget caused the correct simulated-aircraft response. This remains an
explicit v12 operator and correlated-log gate.

The v12 fix checks the displayed frame at admission, then allows its own
reserved target revision during the bounded camera handshake while still
rejecting a changed camera/runtime, video source, aircraft association or a
later target selection. Camera selection has a six-second backend commit
deadline and an eight-second QGC action timeout. A failed late guard now
returns a terminal action result and stops following without issuing an
obsolete camera location command. Focused tests cover handshake delay,
generation/source changes and late cancellation. The private v12 profile
passed configuration validation. The live startup probe has now passed; the
human retarget/follower retest remains pending.

The final v12 software gate passed: 3,244 PixEagle unit tests (41 skipped),
185 integration tests, 172 focused API/security tests, schema validation and
generated API candidate-inventory check; the custom QGC debug build and all
413 Unit/Integration tests passed with standard exclusions. The touched QGC
C++ file passed locked `clang-format`; both worktrees passed `git diff --check`.
The v12 QGC binary SHA-256 is
`2eff53d5e474f94f33cbccc12871bd7d88721e9d5cb95020bdf43106243af68e`.
The v12 profile's source-file checksums match the tested backend files.

## v12 launcher recovery and startup evidence

The first operator v12 launch failed because an earlier v11 `--hold` launcher
had exited while its labeled Docker backend/PX4 containers still owned TCP
8096 and camera telemetry UDP 9004. The SIH launcher now serializes startup,
reclaims only labeled probe containers whose launcher process has ended,
checks the required ports before creating a new Docker network, and preserves
active or unrelated port owners. Its cleanup trap still stops only the current
run's containers.

`bash -n` and `--check` passed. An actual v12 `--probe` automatically reclaimed
the orphaned v11 containers, observed simulated PX4 UID
`5283920058631409231`, fresh camera angles and 640×480 video, QGC-directed
system 1 telemetry, and an active PixEagle flight-command block. It sent no
follower command. The probe stopped its own containers and released both ports.
A separate live `--hold` run remained running when a second `--probe` reported
port 8096 occupied; that second invocation did not stop the active stack.
Stopping the first launcher then removed its containers and freed the ports.
Evidence: `camera-sih-operator-v12/logs/stack-probe-result.json` and the
timestamped logs in the same private runtime. This is startup and cleanup
evidence, not a retarget or simulated-aircraft response result.
