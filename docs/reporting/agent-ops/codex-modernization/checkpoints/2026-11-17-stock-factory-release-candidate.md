# Stock application and factory policy — 7.6.0-rc.4 candidate

## Completed software checkpoint

The stock MAVLink application owner is integrated at `704c6f386`, following the
shared-session foundation at `fe1b3802d`. This candidate completes factory policy,
configuration migration, version metadata and read-only evidence presentation.
Ordinary stock firmware uses the existing MAVLink connection; no aircraft
firmware, parameter, DDS or physical wiring change is required for that path.

One SafetyManager resolver still owns numeric limits. The new
`Safety.ALLOW_SESSION_VELOCITY_OVERRIDE: false` is permission for the existing
session override, not a second limiter or controller. Public controls advertise
bounded ranges; an explicit expert policy enables the existing override/Restore.
Missing legacy policy retains previous behavior and remains visible in Config
Sync preview rather than silently changing installed command authority. Malformed
policy cannot partially replace a published configuration.

Factory configuration: VIDEO_FILE/CSRT, MC Position, target altitude guidance off,
zero horizontal/vertical velocity intent with yaw centering, circuit breaker on, relative altitude 5–100 m, 2 m
warning buffer, total speed 1 m/s and forward/right/down caps 0.5 m/s. The normal
FW envelope remains `px4_configured_max`. A floor is estimator/home referenced,
not terrain clearance or a guarantee of pull-out distance. Private owner files
remain outside the repository and require separate installation/acceptance.

## Latest official baselines and actual SIH

The stock pin is unmodified PX4 `722ebc963555189314a8ce77b426ed074ffa6dae`.
The reproducible stock build passed; its manifest is
`reports/native-guidance/stock-sih-20261117-r1/sih-build-manifest.json`.
The retained advanced firmware patch pin is separate and is not applied to stock.
QGC `134fecd040531a0bbbc440bbad50bf25e4e51bdf` includes official upstream
`19e4246b2`; no extra upstream merge is needed at this checkpoint.

Actual PX4 evidence under `reports/sitl/stock-px4-qualification-20261117/`:

| Scenario | Result | Scope |
| --- | --- | --- |
| `latest-xvert-mc-owner-r1` | Startup 6 m/s, adjustment 6.5 m/s acknowledged; range 62.27 → 14.09 m; Hold confirmed | Tailsitter MC application; no loss injected, so no recovery claim |
| `latest-xvert-fw-expert-r1` | Range 169.69 → 57.48 m; actual altitude change 32.03 m; loss/reacquisition and Hold confirmed | Settled tailsitter FW application with explicit experimental descent |
| `xvert-application-takeover-r1` | Pilot Return retained; following ends; no cleanup mode command afterward | Earlier stock baseline, takeover regression |
| `xvert-application-transition-r1` | Following ends, no replay/automatic restart | Earlier stock baseline; native sender-loss response is Return, not Hold |

Earlier airplane and horizontal/vertical mount application results remain in the
[application checkpoint](2026-11-17-stock-mavlink-application.md). Failed runs are
retained, including the reproduced readiness/command-snapshot race. This candidate
does not relabel them as successes or rewrite historical raw evidence.

The existing visualizer now shows acknowledged request, submitted intent and
actual PX4 3D velocity separately, uses elapsed plot time, selects axes from the
actual command contract and labels application-lifecycle provenance. Renderer and
raw-input hashes are recorded. Missing original pose/phase/airspeed remains
unknown. Command vectors never generate a synthetic aircraft path. The owner-speed
scenario demonstrates accepted requests, not achievement of requested speed.

## Verification

- Backend CI unit selection: **7,747 passed**, 11 optional GI skips, 14 subtests.
- API/integration/inventory/docs: **357 passed**. Version/setup/contracts: **214 passed**.
- Final report/trace/display regressions: **101 passed**; factory/private permission: **9 passed**.
- Schema: **45 sections, 615 parameters**; fatal Python lint and shell/schema checks.
- Dashboard: **69 suites / 592 tests passed**; production build at rc.4 and lint passed.
- QGC: incremental build, changed-file lint and **269-case** client suite passed.
  Standard Unit/Integration selection: 536 passed initially; all 23 remaining video
  checks passed when the installed ICE plugin path and X11/software-GL environment
  were exposed. No tests were excluded to obtain this result.
- One private QGC Windows/Linux/Android workflow: run **43956447633** at `134fecd04`.
  Build/packaging success must be verified before replacing local binaries.

These gates overlap and must not be added together. The full backend unit run
precedes final version metadata and read-only report changes, whose focused
regressions were then renewed. Runtime policy did not change after that full run.
Exact-head cloud CI and publication are recorded in the release, not assumed here.

## Remaining checkpoint

No Pi or aircraft was changed. Request cooled hardware only after candidate CI
and matching packages pass. First verify power, storage and a clean deployment;
previous undervoltage/corrupt Git/clone-verification failures remain unresolved
hardware observations. Use the normal updater and Config Sync preview/apply,
preserve the circuit breaker during bench checks, verify physical camera signs,
client Start/Stop and recovery, then obtain operator acceptance before flight.

Stock attitude/thrust projection is not native TECS. Ground-speed proxy feedback
is not airspeed or stall-margin proof. Experimental policy removes projection
upper-speed and pitch/sink soft ceilings; bank, actuator, minimum-reference,
altitude and authority constraints remain. Transition ends following and requires
a new Start after settling. Prefer explicit Stop before a planned transition.

## Expectation audit and stock Gazebo follow-up

The exact `d2a105f4d` cloud run **43960050257** passed all jobs. Private QGC run
**43956447633** passed Windows/Linux/Android; downloaded package hashes, source
identity and formats match `134fecd04`. Old local installers were removed only
after replacement verification. Signature verification is not claimed: the
private attestation lookup returned HTTP 404.

The audit found the operator launcher still required the older native bundle for
FW/VTOL. The shared builder now supports unmodified stock Gazebo, and the selected
verified firmware policy determines whether an experimental adapter is needed.
The example and local operator recipe use stock firmware without that bundle.
New runtime scene descriptors bind templates to current verified build resources
and retain original template hashes/resource changes; historical descriptors,
strict qualification callers and raw evidence stay unchanged.

Build: `reports/native-guidance/gazebo-stock-20261117-r1/gazebo-build-manifest.json`,
unmodified PX4 `722ebc9635`, with the explicitly declared no-pitot sensor variant.
MC, conventional FW, quadplane and tailsitter templates pass their new binding
and existing resource/airframe closure checks. Original SIH build authority is
retained at `d2a105f4d`; changing a builder does not requalify an older manifest.

The fresh full-stack ground check also reproduced missing telemetry identity
without an open GCS: MAVSDK's reply on its own link did not establish the REST
route. Discovery now requests only AUTOPILOT_VERSION on the configured route,
off the flight event loop, with shared bounded demand. Receipt success grants no
identity/authority; the original poller still verifies UID and heartbeat progress.
Active following sends no discovery query. FW sensor/proxy transitions are logged
once rather than on every frame. No guidance law or numerical flight limit changed.

`reports/sitl/stock-gazebo-startup-20261117-r4/smoke-result.json` passes live rendered
video, authenticated observational connection, verified aircraft association,
disarmed state, circuit breaker on and following inactive, with no native adapter.
Its remaining Start reasons are `vehicle_not_armed` and `target_not_tracking`.
This is a ground/startup check, not a Gazebo flight or optical-mechanics pass.
Earlier runs retain the missing-identity finding and fixture-auth mistakes.

Renewed targeted gates: 420 stock build/scenario/projection checks; 158 discovery/
integration/source checks. The pre-discovery full unit renewal passed 7,753 tests
with 11 optional GI skips. The final full run and exact follow-up cloud revision
must be recorded before release promotion. Private guidance overlays remain
outside Git; their hardware adoption and the operator's stock Gazebo flight test
remain the next checkpoints.

The final local unit run passed 7,760 tests with 11 optional skips and retained
one unrelated model-swap fixture failure: its five-second race deadline included
spawned-process imports. A readiness handshake now separates process startup from
the unchanged five-second file-swap window; all 48 model-backend tests pass with
the actual inode/provenance assertions intact. The API/integration/tool/document
selection passed 565 checks. Exact-head cloud CI must renew the complete selection
before publication. No test was excluded and no runtime model trust policy changed.
