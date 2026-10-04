# QGC 4b.3 closeout and 4b.4 entry

## Scope and source

The QGC integration worktree is `feature/pixeagle-native-integration` at
`2e6190bafc4f4796e29ae24cbd1d27f73b96d07d` plus uncommitted integration
changes. The PixEagle worktree is `feature/qgc-native-integration` at
`989d9662173b364de03b307f4208e9d0ca96451f` plus uncommitted integration
changes. Neither worktree has been published. The operator accepted the
camera-v5 tracking and manual-control workflow; the new circuit-breaker and
advanced-engine interfaces await a separate operator review.

## Changes under review

- The native safety API exposes authoritative circuit-breaker state and a
  confirmed, identity-bound mutation. QGC uses it in PixEagle Options; the
  dashboard still uses the same backend setting. Follower Test is labelled as
  a test rather than aircraft following.
- Tracking-engine selection applies and saves through the guarded native
  transition. Dashboard and QGC expose the advanced engine setting; valid
  runtime choices are remembered in the session. A failed save is reported
  separately and can be retried without selecting a target.
- `src/classes/gimbal_geometry.py` validates raw camera-body angle samples.
  The chase and vector followers issue hold/zero intent on invalid geometry;
  neither treats a transform failure as neutral steering during forward pursuit.
  Both consume one camera-to-aircraft ray. The saved installation choice is
  `GimbalTracker.MOUNT_TYPE`; optional expert axis, sign and zero corrections
  live in `GimbalTracker.GEOMETRY_OVERRIDE`. An unambiguous old mount is
  promoted through the retirement registry; conflicting mounts and non-neutral
  old corrections fail rather than being discarded. Mount and expert changes
  require a PixEagle restart because followers cache geometry. These are
  software direction checks, not qualified aircraft control.
  The old `TILTED_45` choice is rejected instead of treated as a qualified
  installation; an arbitrary-mount workflow remains later scope.

## Validation evidence

- Backend safety, engine, route and schema gate: 150 tests passed; schema
  validation passed. Focused geometry/follower gate: 54 passed; broader
  follower/safety/engine gate: 136 passed. A subsequent malformed-angle
  regression gate passed 30 tests. Logs: `/tmp/pixeagle-4b3-backend-gates.log`,
  `/tmp/pixeagle-4b3-schema.log`, `/tmp/pixeagle-4b4-geometry-boundary-all.log`,
  `/tmp/pixeagle-4b4-followers-broad.log`.
- The later shared-mount/config/follower run passed 342 tests; the complete
  Dashboard suite passed 489 tests across 64 suites and its production build
  succeeded. Schema regeneration/check and `git diff --check` passed after
  retiring the duplicate follower geometry keys. This is software evidence;
  no aircraft command delivery was exercised by those runs.
- A follow-up config/route/parameter/geometry gate passed 226 tests after the
  retirement migration test was added. Python compile checks passed. Ruff was
  unavailable in this worktree, so it was not counted as a passing lint gate.
- Config-sync and integration configuration-flow checks passed 58 tests with
  one platform-dependent skip. The production vector-command direction matrix
  for both mount presets passed 21 focused tests; it exercises left/right and
  up/down commands with finite, bounded speed. Horizontal signs remain
  software-only until physical characterization. Dashboard ESLint passed.
- Deterministic chase command tests exposed an ignored shared altitude-control
  setting. The chase follower now emits zero body-down velocity when the
  setting is off, matching the vector follower and the documented safe default.
  Focused image-axis/geometry tests passed 65 after this fix; the broadened
  follower, config, schema and smoke gate passed 368.
- Dashboard focused tests: 3 suites and 7 tests passed; build and lint passed.
  Logs: `/tmp/pixeagle-4b3-dashboard-build.log` and
  `/tmp/pixeagle-4b3-dashboard-lint.log`.
- QGC focused PixEagle client/target/camera tests: 3/3 passed. The combined
  Unit/Integration run passed 410/413; the three host-dependent failures
  passed isolated reruns (Bluetooth warning, GPS UI timeout and CMake fixture
  Ninja path). Logs: `/tmp/pixeagle-qgc-4b3-focused.log`,
  `/tmp/pixeagle-qgc-4b3-full.log` and `/tmp/pixeagle-qgc-4b3-host-rerun.log`.
- The isolated camera-v6 bench uses a source snapshot identified by
  `camera-v6/source-provenance.json`, a distinct profile, CB enabled, Follower
  Test, MAVLink disabled and no aircraft connection. Its logs are in
  `camera-v6/logs/` and `desktop-v6/qgc.log` under
  `/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b3-2026-10-01/`.

## Open gates

The vertical camera-only first-pose characterization found that joystick left
panned the image left as reported roll increased, pitch-up reduced reported
pitch from about 90°, and roll-left reduced reported yaw. The operator judged
all six directions correct, confirmed neutral lens alignment with aircraft
forward, and reported no left/up reversal at a second modest pose. The paired
opposite-direction numeric signs were not individually documented. Manual-axis
dispatch and Stop records are in `camera-v6/logs/backend.log`. The shared
camera-body-to-aircraft ray and independent known-direction tests use these
observed signs. The web Settings editor exposes only the canonical camera
installation setting; QGC keeps no mount-setting copy. Old profiles with
conflicting or custom follower geometry need operator correction before load.
This is enough to begin follower command tests,
but not to claim PX4-response qualification or silently migrate conflicting
legacy values.
After that come both follower laws, PX4 SIH, network
and load, platform release candidates, and the separately approved onboard
ground test. Real aircraft command testing and deployment have not occurred.

The existing `phase2_follower_validation` SIH plan asserts the
`mc_velocity_position` profile. It cannot be used as proof for either gimbal
follower without a separate camera-angle stimulus and PX4-observed command
scenario. The desktop SIH launcher also uses a recorded image source, not a
closed-loop camera-angle model. 4b.4c therefore remains open.
The official SIH profile's side-effect-free `--mode dry-run --json` completed
and reported `would_start_processes=false`; this validates only the existing
plan definition, not gimbal follower behavior or PX4 delivery.
An independent world-target/PX4-pose angle fixture now emits typed
`GIMBAL_ANGLES` injection JSON for horizontal or vertical installations.
Pose-direction and native injection tests passed 33; the broader geometry and
follower direction gate passed 91. Its quaternion contract is PX4 body-FRD to
NED, not MAVSDK's reverse convention. This is a prerequisite for closed-loop
SIH, not a PX4-observed result.
The fixture now accepts a read-only MAVLink2REST pose snapshot for one explicit
PX4 system and rejects stale, wrong-component or desynchronized position and
attitude. It also compares quaternion yaw with `ATTITUDE.yaw` to catch a frame
convention mismatch. The final focused fixture/injection gate passed 37 tests.
An isolated PX4 SIH and MAVLink2REST probe subsequently supplied all three
pose messages to the fixture. System 1/component 1 passed the freshness,
boot-time and yaw checks, and the fixture produced both mount presets for a
fixed NED world target. The raw selected messages, conversion result, image
ID and container logs are under
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4-2026-10-01/pose-probe-v1/`.
The simulator image was the pinned
`px4io/px4-sitl@sha256:fd6d93dc2705482aeb64ea26fdf16185d8a511010fdc53e26305f10d91855865`;
MAVLink2REST ran in the PX4 container's isolated network namespace, with only
its read-only HTTP probe mapped to host loopback port 18088. The probe did not
start following or send aircraft commands. World-target-to-production-command
tests now pass for both mount presets and both gimbal followers; the focused
fixture, follower and injection gate passed 102 tests. These are still not
PX4-observed gimbal follower setpoints or simulated vehicle response.
A separate current-source camera/SIH preparation tool now creates a fresh
private profile without launching services. The first version omitted a
required segmentation catalog and exited at import; its failed startup log
remains under `camera-sih-preflight-v1/logs/`. The tool now copies all
nonsecret repository configs. The current vertical profile is
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b4-2026-10-01/camera-sih-preflight-v4/`.
It passed strict dependent-config loading and starts with the flight-command
circuit breaker active, camera controls available for target acquisition,
an authenticated API bound within a dedicated Docker network and its own login.
A brief camera-only backend smoke of v3
confirmed authenticated context, the expected instance identity, active
circuit breaker, camera-control capabilities and live RTSP capture; its log is
`camera-sih-preflight-v3/logs/backend-preflight.log`. MAVLink was expectedly
disconnected because PX4 and MAVLink2REST were not started. Six dedicated
preparation-safety tests passed. This is a configuration and camera-startup
checkpoint only; it has not started PX4 following.
After tightening URL/credential validation, the combined profile, fixture,
follower and injection gate passed 108 tests; the checked-in configuration
schema still validates. The newly prepared runtime passed strict dependent
configuration loading.
The first combined Docker probe failed because OpenCV's host shared libraries
were not mounted; the error is preserved at
`camera-sih-preflight-v4/logs/pixeagle-missing-opencv-lib.log`.
After matching the earlier library mount, PX4/backend startup and simulated
UID association passed. The probe was tightened to require live camera-angle
telemetry and video, which required forwarding the camera's UDP status port
from the camera-facing host interface into the dedicated Docker network.
The final `bash tools/run_gimbal_sih_probe.sh --probe .../camera-sih-preflight-v4`
passed with system UID `5283920058631409231`, fresh camera angles, a
640×480 published frame and the circuit breaker active. Evidence:
`camera-sih-preflight-v4/logs/stack-probe-result.json`, `pixeagle.log`,
`router.log`, `mavlink2rest.log`, and `mavsdk.log`. The script stopped its
containers. It did not start following or test setpoint delivery.
The startup probe now also verifies a MAVLink system-1 packet reaches QGC's
UDP 14560 input. A second fresh profile at
`camera-sih-operator-v5/` passed `--hold`, and the QGC handoff's read-only
`--check` verified the running instance, simulated UID and active command
block without writing QGC settings. Ctrl-C stopped the owned containers.
The operator sequence is recorded in the QGC worktree at
`custom-pixeagle/OPERATOR-SIH-GIMBAL-4B-4.md`. No camera target, follower
setpoint, PX4 response or pilot takeover has been claimed from this startup
probe.
The old camera-v6 private profile contains the former default
`GM_VELOCITY_CHASE.INVERT_VERTICAL_CONTROL=true`. Refreshing that snapshot
against the new schema would correctly reject it as ambiguous. Preserve the
old evidence and create a fresh, explicitly vertical profile with neutral
retired fields for the next handoff; do not silently rewrite camera-v6.
Local-only profiles that carry the historical checked-in `true` default are
accepted because that retired field was unused; saved gimbal profiles still
fail until the correction is reviewed.
During harness inspection, `run-sih-desktop.sh --check --video test9` started a
short-lived owned SIH stack and refreshed the older test9 source snapshot. The
run was stopped, no owned containers remain, and the prior test9 source,
definitions and manifest were restored from its generated backup (manifest
hash verified). The refreshed generation remains archived under
`sih-test9-v1/source-refresh-cancelled-20261001T134823Z`; the launcher
archived transient logs under `slice-4-operator-desktop/history/20261001T134823Z-340606`.
The launcher now exits immediately after read-only prerequisites in `--check`
mode. A repeat preflight passed, left the test9 manifest hash unchanged and
started no containers. Its output explicitly excludes backend, video and PX4
runtime claims.
