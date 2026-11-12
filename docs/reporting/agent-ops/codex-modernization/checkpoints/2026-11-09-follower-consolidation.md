# Follower consolidation checkpoint

Plan: [MC/FW/VTOL consolidation](../../../../followers/05-development/follower-consolidation-plan.md).
Baseline: PixEagle `50bb2f763`; QGC implementation worktree `c7cfdfa13`.
Hardware, installed services and local saved/private configuration are untouched.

Current position (November 12): **S0–S6 component/software checkpoints complete;
S7 implementation in progress.** The S6 closeout below records 32 selected
actual-PX4 component passes and retained failed history. Native causal ownership,
transition-preserving release, clients, packaging and hardware remain open.
The repaired `e4b366d5e` baseline and separate, unmerged `fd57059a6` native
Transition candidate each pass the renewed 6,391/196/155 software gate.
Protocol-3 airplane renewal passes three component cases. The declared MC
process-loss component now retains both flight logs, while VTOL altitude,
remaining ownership cases and full application qualification stay open.
VTOL admission stays closed. See the
[current S7 findings](#s7-current-diagnostics-and-native-response).

Continuation on 2026-11-11: the current MC component selector has 28 passing
cases. Broader software renewal exposed and repaired duplicate manager caching;
the renewed full gate passes and the S4 component/software checkpoint is closed.
S5 image provenance, shared
world-ray math and native timing foundations are committed; public image-FW
admission, VTOL release and hardware qualification remain pending. Detailed
earlier entries below retain their original verification scope.

## S0 — inventory complete

- Reviewed all eight real input/command contracts, defaults and evidence scopes.
- Reconciled the qualification matrix with retained actual PX4 manifests rather
  than promoting synthetic gallery fixtures or historical component passes.
- Corrected overview PN, geographic-position, gimbal-actuation and tracker-input
  claims; distinguished shared continuity from follower-local loss commands.
- Marked retained/automatic transition behavior historical. The chosen policy
  is end following on transition and require a new Start; transition-preserving
  release remains an S7 implementation gate.
- Recorded direct-rate altitude inconsistencies for S4/S5: MC rate altitude hold
  has its own enabled +15 m target offset; FW rate guidance uses image Y. Shared
  target-altitude-off is not a universal altitude-hold guarantee.
- Local `configs/config.yaml` is a Position/demo configuration, not the intended
  private vertical tailsitter overlay. Preserve it and locate/compare the actual
  accepted private artifact before migration; never silently apply 6 m/s/5 m.

Private baseline subsequently located read-only in the October 27 Desktop
handoff: `private-vertical-gimbal-profile/configs/config.yaml` is byte-identical
to `pi-deployment-2026-10-27/config-after.yaml`, SHA-256
`3df34625378fef3759431a69a163cf0ddacddf724920363b97eee0c831ecafc8`.
Its separate sparse `overlay.yaml` SHA-256 is
`3800c635ebc0c72abe05f9e9dc05879097f763b2f399664034d2c257c592804a`.
The accepted MC settings are vertical Topotek mount, zero startup/initial speed,
6 m/s saved velocity caps, 1.5 m/s² ramp, coordinated turn, Vector altitude
guidance on through its override, relative altitude 5–120 m, yaw limit 90°/s
and circuit breaker on. These are retained installation values, not new FW
tuning or a physical tailsitter geometry qualification. No archive was modified.

Validation: 74 route-inventory/config-publication tests and 36 documentation/
tracker-contract tests passed; schema is current
(44 sections, 616 parameters). One existing Starlette deprecation warning.
No new simulation, plot or aircraft-response claim was generated. Existing
read-only reports remain under the run roots listed in the
[qualification inventory](../../../../followers/05-development/follower-sih-validation-matrix.md).

## S1 — backend catalog complete

- Added `follower_catalog.py` with typed immutable descriptors and pure input/
  aircraft eligibility. All eight IDs, nominal command fields and algorithms
  remain; family/visibility and native phase-to-command mappings are explicit.
- Command schema `2.2.0` replaces the native phase list with
  `native_phase_contracts`. Every in-repo reader/fixture was migrated; no runtime
  alias remains. Developer-owned schema assets need the documented new metadata;
  persisted operator settings are not rewritten.
- Tracker schemas own observation representation and guaranteed fields.
  SmartTracker explicitly promises selected-target `position_2d`; runtime still
  checks its actual presence, shape and finite values. Optional fields alone
  cannot qualify static selection. Synthesized gimbal coordinates and unrelated
  external/angular data cannot authorize image followers. This intentionally
  tightens previously accidental compatibility; it is not behavior-neutral.
- Removed the duplicate class compatibility matrix and unused descriptive mount
  maps/default. Canonical geometry and real provider transforms are unchanged.
- Typed status exposes selection eligibility separately from live gating while
  retaining the older `compatible` projection. Selecting a profile does not
  authorize Start. Catalog generation excludes changing aircraft readiness.
- Start/Stop readiness uses the action permission sets. Typed Start checks fresh
  reported aircraft kind; it does not yet establish independent settled VTOL
  phase. VTOL typed admission remains blocked until S7's transition-preserving
  release passes. Legacy owner entry paths still need S3 consolidation.
- Updated extension/schema guides and generated non-callable API candidate
  provenance, including the catalog and its declaration assets. No MCP surface
  was promoted. Dashboard/QGC catalog adoption remains S9.

Validation: 829 focused follower/backend/command/harness tests passed; the
315-test CI preflight plus catalog/native/parser gate passed; 54 visualizer tests
passed. These commands overlap and are not additive unique-test counts. Fatal
lint passes, schema remains 44 sections/616 parameters, and existing Starlette
deprecation is unchanged.

Read-only archive compatibility check: the current renderer consumed the actual
`native-vector-fw-matrix-20261107/vertical-hold` capture and produced
`reports/sitl/follower-consolidation-20261109/archived-fw-reader/` (HTML, PNG,
CSV/JSON). It retained 590 observed pose samples with no analyzer flags and
range 163.8 to 26.4 m. This renews report-reader compatibility, not SIH behavior
after S1; original capture/evidence remains unchanged.

## S2 — exact configuration migration complete

- ConfigService owns the nested schema resolver used by validation, retirement
  classification and redaction. Exact writes preserve customized siblings and
  sparse override absence, including typed extension children.
- Config Sync v2 accepts up to 16 mapping components and reports leaf changes.
  Arrays/empty objects remain atomic. Explicit null differs from omitted values;
  schema-only additions need an explicit value. Duplicate/prefix-overlapping
  operations, scalar ancestors and unknown schema paths are rejected.
- Apply advances only selected baseline leaves and audits their exact paths.
  Inherited sensitivity protects nested leaves. Existing CAS, backups, durable
  audit, publication barrier and conditional rollback remain authoritative.
- Retired exactly three confirmed inert GM Chase keys through the registry;
  no gains or operational defaults changed. Schema is 44 sections/613 parameters.
- Required `Follower.General` remains strict before preview; missing required
  values are not silently merged. This limitation and recovery boundary are
  documented in Config Sync; no new required General field was introduced.

Validation: the combined config/service/routes/CLI/schema/publication gate passed
389 tests; one Windows-only ACL test skipped on Linux. One existing Starlette
deprecation warning. Fatal CI lint, schema drift and whitespace checks passed.
No saved/private configuration was applied, and no hardware or SIH run occurred.

## S3 — explicit strategy/lifecycle boundaries complete

- Command schema 2.3.0 requires explicit `config_section`; all eight existing
  bindings are preserved. Class renaming/subclassing no longer selects limits.
- Explicit `reset_target_state(reason)` hooks replace reset-method discovery.
  Retarget invalidates intent before resetting established controller memory,
  while preserving acknowledged session controls. Stateless paths remain no-op.
- AppController delegates post-continuity shaping and accepted-submission
  history through hooks. Session caps precede shaping/guarding; rejected
  submission does not advance history. Native FW never enters an MC guard.
- Native intents carry explicit profile identity rather than a hidden Vector ID.
- The common flight owner applies catalog admission to typed and legacy Starts,
  after fresh telemetry/pending configuration and again after awaited native
  discovery. Unknown/mismatched aircraft and VTOL are rejected before acquisition.
  VTOL remains blocked until S7; preview is separate and unchanged.

Validation: 1,120 focused follower/owner/native/continuity/transport tests and
65 preview/factory/retarget tests passed. Existing controller algorithms, units,
gains, safety envelopes and transition behavior were not retuned. No simulation
or hardware run is claimed by this structural slice. The independent review also
updates a continuity-sync fixture to accept S2's nested leaf paths.
Independent root review: 392 catalog/lifecycle/owner/API/provenance/documentation
tests passed, including local Markdown links; fatal CI lint and whitespace passed.

## S4 — MC behavior repair and component SIH in progress

Real factory/default tests reproduced and repaired these configuration defects:

- Visual Centering ignored altitude-off and could replay vertical EMA history.
- Chase's optional adaptive path could add vertical guidance while disabled.
- Stationary tracking ignored yaw-disable and retained old smoother output.
- Ground used swapped forward/lateral PID keys and ignored correction-disable
  for attitude correction. Descent now also respects shared altitude permission.
- MC rate's saved altitude offset applied while shared altitude guidance was off.
  It now captures engagement altitude in that case; the fresh offset is zero.
  Saved values remain intact. This is not native FW-style flight-path guidance.
- Position/Centering use bounded monotonic intervals. Nonprogressing smoother
  time retains the previous output instead of bypassing acceleration limiting.

Factory Ground gains are numerically equal, so correcting key ownership does
not retune them. Unequal custom gains must be reviewed against the corrected
axis names. PID rate-key labels/internal-unit history remains a characterization
item; no blind gain-unit rescaling occurred. Ground's heuristic attitude
correction still needs actual fixed-camera/tilted-flight evidence.

Validation: 603 follower/envelope/schema tests and 85 config/API/provenance/
documentation tests passed (overlapping gates). Schema retains the existing
0–100 m offset range, including saved 15 m values. No saved/private configuration
was applied. A PixEagle-owned moving-world-target SIH harness is being verified;
S4 and all-mode response qualification remain open until its actual runs pass.

Retarget follow-up: actual factory tests reproduced residual command history in
Position, Centering and Ground after replacement by a centered target. Explicit
target-reset hooks now clear their PID/filter memory without ending session
controls. The 538-test follower gate passes. This renews reset behavior, not
physical retarget acceptance.

Browser review of the retained November 7 FW replay passed in Chromium: no page
errors, populated command/measurement values and different 3D/side canvas views.
Screenshot retained at the archived-reader run's `browser-review.png`; its
underlying PX4 capture is historical, not a new S4 flight.

The canonical MC world-target harness passes 49 focused tests (projection,
staging, readiness, timing, fault rejection, response and owned ULog cleanup).
Root review passed 102 runner/visualizer tests before four final timing cases
were added. The worker uses production component dispatch/publication; HTTP/App
startup is not qualified. Five nominal scenarios and one explicit Chase loss
case are provided; unsupported faults fail instead of implying coverage. Actual
runs are next. The shared host extraction retains its QGC source/hash and an
explicit S10 consolidation task; no QGC code or hardware changed.

First actual attempt at `8c5d0f9d3`,
`reports/sitl/follower-consolidation-20261109/mc-position-off-r1/`, stopped before
following because the new worker omitted requesting aircraft identity on the
independent REST telemetry link. MAVSDK identity alone was correctly insufficient.
The failed result, source/config, logs and actual ULog are retained. Restore the
existing route-specific identity handshake, not an identity-check bypass, then
use a new run directory. This attempt is not accepted follower-response evidence.

### Actual MC evidence and simulator baseline investigation

Runs remain under `reports/sitl/follower-consolidation-20261109/` with exact
source/configuration, publication, observed pose, ULog and interactive reports.
The identity-request omission, immutable UID check after Stop, cleared-commander
reference and delayed read-only Hold confirmation were repaired in the worker.
Failed attempts remain unchanged. Successful commands alone never grant a pass.

The historical image (`381149fb012762f5e38c4a7fdc1b905b28038970`) failed
Stationary tracking with 7.53 m horizontal drift and Centering with 2.03 m altitude
variation. A no-follower comparison also observed drift in native Hold and direct
zero velocity. ULog inspection found disagreement between SIH physics and the
estimated attitude/velocity; the precise upstream cause is not established.

A separately packaged **diagnostic candidate**, PX4
`155f415168cef08dca2f5d85d2bc258b44a589ec` plus the reviewed native extension,
uses immutable local image
`sha256:f486e59d879b68dbf3ceba067aa513be9be90c09e5fb93d3fd19592f23f1d07f`.
Matching binary, ROMFS, source patch and invocation are retained per run.
No follower gains, test limits, real firmware or compatibility default changed
for these comparisons. The candidate's no-follower physics displacement was
0.079 m in native Hold and 0.203 m in direct zero velocity, versus 1.474/1.321 m
on the historical image. These are two observed runs, not proof of a particular
upstream fix. Canonical clean-source compilation/attestation is a separate gate.

| Candidate component case | Altitude off | Altitude on |
| --- | --- | --- |
| Stationary tracking | passed; 0.208 m horizontal drift | passed; observed climb 3.27 m, horizontal drift 0.127 m |
| MC Chase | passed; range 18.26 → 16.34 m | passed; range 18.51 → 16.47 m, observed descent 2.76 m |
| Visual Centering | passed; altitude variation 0.138 m | passed; observed climb 3.74 m, zero forward intent |
| Downlooking Ground | passed; altitude variation 0.097 m | passed; observed descent 5.60 m |
| MC direct rates | failed; altitude variation 5.99 m and wrong net image response | pending repair |

Case directories use `mc-{position,chase,centering,ground,rates}-{off,alt}-native155-r1`.
The velocity cases retained bounded successful publication, declared axis checks,
Stop with confirmed Hold, no later publication and restored circuit breaker.
Altitude-on values are signed response work toward independent target height,
not altitude-hold errors or interception claims. Ground's tilted/edge correction,
loss/retarget/takeover, full application and repeatability remain pending.

Altitude cases require an explicit stimulus and at least 0.1 m observed vertical
response; camera tilt/target motion alone receive no credit. Failed-run replay
shows **Scenario failed**; only an explicit qualification result produces a pass
badge. The harness/report/projection gate passes 126 tests.

Direct-rate diagnosis reproduced a degree/radian mismatch with real factory PIDs:
pitch/yaw normalized-image gains were amplified 57.3-fold. Unit conversion is now
centralized at gain loading, including hot tuning; angular roll gains remain
unchanged. Factory/unit checks pass. Its 1 Hz cached altitude stream also fed
camera-rate I/D and saturated thrust. Source-progress-aware height/vertical-speed
feedback and actual response requalification are in progress; this profile is
not accepted. Saved/private configuration and hardware remain unchanged.

Retarget admission follow-up: the application previously inserted velocity
fields into a live rate/thrust command and reset the follower before continuity
could reject its unsupported contract. One pure intent validator now runs
before mutation and is reused by the continuity supervisor. Unsupported live
rates return `retarget_requires_stop`, preserving target, generation, authority
and command. Native FW carryover retains its identity and own level/altitude
fields. Preview is unchanged. Focused and broader controller/native/camera/API
gates passed 549 tests. No rate-coasting policy was invented or qualified.

### Canonical build and wider S4 matrix (still open)

The clean source build now passed. Its verified manifest is
`reports/native-guidance/sih-canonical-build-20261109-r1/sih-build-manifest.json`
(SHA256 `d11fad144d5451c86b259cef3e5b281acb9b95fdd48a329c5cb25eff8e7cbe9a`),
runtime image `sha256:aad1b03f8c0ae0e157002123f622fb12fb82ebc970e1287f48f54b4cfda8fdf8`,
binary `08d6255866feaf4b65a5c9914598804464d534a9cadbb0193c34c2d4b90593d1`.
The pinned compiler runs offline and packages matching ROMFS/aliases. No firmware
was flashed and the historical compatibility default was not silently replaced.
The diagnostic baseline comparison has a reproducible PNG/CSV/HTML and source
hashes at `reports/sitl/follower-consolidation-20261109/baseline-comparison/`.

All four velocity profiles passed nominal altitude-off/on scenarios on this
manifest. The repaired direct-rate default also passed: REST run
`mc-rates-off-canonical-r2`, and both rate/Stationary MAVSDK comparisons
`mc-{rates,position}-off-sdk-canonical-r1`. Source-timed paired height feedback,
measured vertical damping and heartbeat datum/freshness checks replace cached
camera-rate differentiation. Fresh thrust gains are 0.03/0.003/0.08, with saved
values preserved; the SDK datum comparison accounts for transport precision.
The direct-rate altitude variation was about 0.25 m on both telemetry paths.
The height/default/preview/schema gate passed 363 tests; a broader overlapping
controller/follower gate passed 1,282 before the subsequent fault repairs.

The first 19-case loss/retarget/takeover/stale matrix is retained under
`matrix-*` and `matrix-inputs/`. **It did not fully pass**:

- Takeover control checks passed, but five reports lacked pose samples while
  waiting for cleanup. The observer now continues during handoff; fresh repeats
  must pass trace validation rather than relaxing freshness limits.
- Ground's four-second loss case failed image response. Its uncalibrated
  degree-based pose correction shows wrong-sign/excessive feedback; removal and
  exact configuration retirement are in progress, followed by unchanged tests.
- Visual Centering acquired forward motion when continuity rotated retained
  lateral velocity. Its strategy now projects forward to zero after continuity,
  without redistribution or budget reset; 966 tests passed. Actual repeat pending.
- Rate telemetry-loss handling correctly refused before MAVSDK and confirmed
  Hold. Publication evidence now distinguishes that guard refusal from a failed
  concrete send; fresh repeat pending. Refusals require explicit source-stage
  evidence, failed readiness and a declared fault boundary.

Publication traces now retain actual submitted fallback fields without inventing
fresh guidance. Canonical captures are counted/preserved; failed trace validation
produces a visibly failed report even when raw component checks passed. The
recorder/harness gate passed 389 tests before the last handoff observer change;
that observer change passed 30 focused tests. Independent pose/relative-height
observation no longer depends on the control cache during fault injection.
The first matrix's raw failures are never edited or promoted to accepted runs.

At that earlier matrix checkpoint S4 remained open. No Pi, camera, private
profile, QGC build, publication or release changed. The then-dormant calibrated
image-bearing contract did not advertise live FW support; later foundations are
recorded below.

### S4 repair repeats on frozen source `20f2ffe6e`

All seven final repair repeats passed against the same canonical build above:

| Case | Run | Result |
| --- | --- | --- |
| Stationary takeover | `matrix-mc_velocity_position-takeover-r3` | Hold observed, publisher stopped, no stale replay samples |
| Chase takeover | `matrix-mc_velocity_chase-takeover-r3` | Same authority and evidence gates passed |
| Ground takeover | `matrix-mc_velocity_ground-takeover-r3` | Same gates; corrected raw image mapping |
| Visual Centering takeover | `matrix-mc_velocity_distance-takeover-r3` | Same gates; zero-forward constraint retained |
| MC rates takeover | `matrix-mc_attitude_rate-takeover-r3` | Same gates at the advanced rate/thrust layer |
| MC rates stale telemetry | `matrix-mc_attitude_rate-stale-r3` | Following ended before a stale send attempt; no failed concrete writes |
| Ground altitude on | `mc-ground-alt-cleanup-r1` | Positive image response; 5.588 m target-directed vertical work, zero stale replay samples |

The Ground cleanup also passed unchanged nominal/loss scenarios
`mc-ground-{off,loss}-cleanup-r1`, plus retarget/stale `matrix-mc_velocity_ground-{retarget,stale}-r2`.
Its five obsolete correction keys have exact ConfigSync retirements; saved sibling
values, gains and shared limits remain intact. Visual Centering retarget passed
`matrix-mc_velocity_distance-retarget-r2` without a forbidden forward component.
Earlier failed raw data and animations remain unchanged.

The rate stale-r2 trace contains a real pre-MAVSDK height-guard refusal. Its general
connection readiness was still true, so the recorder now exposes raw readiness
and final guard refusal separately. Strict regression tests replay that case;
the fresh r3 run stopped earlier and contained zero refusals. Expected refusals
must be inside the declared injected outage; actual failed writes still fail.

Takeover replay now retains observed pose through cleanup. Only fresh observed
Hold plus a stopped publisher/task proves that no command is expected. Commands
then remain absent, rather than invented zeros. Missing active commands or pose,
and any successful publication after release, still fail. No tolerance was widened.

Software checks so far: 158 control/Ground tests, 171 harness/report tests,
79 required API/configuration tests, independent 138-test Ground/migration audit,
fatal lint and current schema (608 parameters). Full unit/integration renewal is
in progress. This remains actual component SIH with simulated image observations;
it is not optical-tracker, whole-application or aircraft qualification.

### Current evidence and next foundations

The local selector at `reports/sitl/follower-consolidation-20261109/current-evidence/index.html`
scans canonical raw captures rather than a second qualification list. Its retained
validation checks 54 attempts, 28 current passing cases, 114 local links, all eight
selector entries and a clean Chrome console. Earlier failures remain accessible;
rates explicitly require Stop before retargeting and do not claim target-vertical
guidance. The guide documents regeneration and raw/replay hash checks.

`43e6e0a64` binds Classic/Smart measurements to immutable capture, geometry and
target generations. Repeated, cached, predicted, failed and superseded output
cannot renew measured identity or timestamps. Uncalibrated image measurements
remain valid for existing image followers; they do not become calibrated bearings.
Root verification passed 143 image/bearing/output tests; the expert review also
passed broader tracker/controller gates. No live FW mode was enabled.

`418a8e7e3` adds one explicit unit-NED-ray entry to the existing native FW objective
calculation. Physical-body callers rotate once and delegate; aligned callers
must not rotate again. It preserves course/EAS/altitude/rearward behavior. The
71 new parity/invalid-input tests and broader 890-test review pass. Timing and
authority admission remain separate gates.

The first full unit run exposed ten test-fixture/expectation failures: missing
factory initialization, an empty mocked catalog descriptor, an omitted explicit
Stop reason, and a missing FW continuity override expectation. They are corrected
in `bfbb14db3`; all 67 affected-module tests pass without weakening production
guards. The integration suite passed 196 tests. Renewed unit/integration logs from
the frozen `418a8e7e3` source are retained under
`reports/sitl/follower-consolidation-20261109/software-gates-r2/` so an interrupted
terminal does not discard them. Native attitude timing work remains in progress.

### November 11 continuation

The second full run passed 4,854 tests but retained seven tracker-loop failures.
The fixtures exposed a real duplicate-manager-reference defect: Parameters kept
its own manager cache after the authoritative singleton registry had replaced
the instance. Config publication could initialize the abandoned manager while
followers read an uninitialized replacement. `ca2e20398` removes both redundant
caches. Three regressions fail before the repair; 111 manager/publication,
tracker-loop and session-speed tests pass afterward. This is not a relaxed gate
or a production fallback for incomplete configuration.

Native timing foundation `878f17de7` is committed. Its exact source hashes match
`reports/native-guidance/attitude-timing-20261109-r1/summary.json`: actual adapter
compilation, 38 native tests, 38 sanitizer tests, 149 Python tests and the legacy
client wire-compatibility smoke pass. The nested wire remains unchanged; timing
is optional top-level metadata. Camera exposure alignment remains unqualified.

### S4 checkpoint closed; S5 continues

On frozen source `2513965f3`, the renewed CI-style local gates pass:

| Gate | Result |
| --- | --- |
| Full unit suite, standard software exclusions | 4,975 passed; 11 optional GStreamer-introspection skips |
| Full integration suite, same exclusions | 196 passed |
| Phase 0 API/configuration/documentation checks | 155 passed after regenerating the command-schema source hash |
| Fatal Python lint | 0 errors |
| Generated configuration schema | Current: 44 sections, 608 parameters |

Logs and source manifest are retained at
`reports/sitl/follower-consolidation-20261111/software-gates-r1/`. The initial
Phase 0 inventory-hash failure is preserved beside the passing final run.
Existing deprecation warnings and optional streaming skips are visible in the
logs; they are not additional platform/media qualification.

`ed239e5f7` replaces the provider-named session module with
`VectorGuidanceSession`; all runtime/test imports were migrated without a legacy
alias. It accepts explicit controls and supported phases. The FW-only control
constructor has no MC value or ceiling, initializes from native EAS/trim, and
cannot accept MC/transition edits. A FW-only session ends on an unsupported phase
and cannot resume; the existing overall VTOL admission gate remains closed.
Shared session regression: 903 passed, plus 66 final narrow declaration cases.

`2513965f3` declares command schema 2.4.0 with explicit MAVSDK/native transports.
The dormant native FW contract references the canonical command's exact two
vertical variants, with no scalar defaults, fake EAS or MAVSDK method. Native
handlers start empty, accept only complete typed session-bound intent, and
refuse scalar/fallback/MAVSDK dispatch. Existing eight profiles are preserved;
no new live profile is advertised. Root's final command/evidence gate passes
237 tests. The generated API inventory is synchronized with the new schema.

S4 closure means the declared MC component/software gate, not optical tracking,
whole-application startup, installation, hardware or release acceptance. Next is
S5's source-bound calibration, qualified timing association, native FW profile
and independent moving-target airplane SIH. S6–S13 and QGC/client qualification
remain open. No hardware, private profile, firmware, services or QGC were changed.

### S5 — source-bound image calibration and explicit admission

The November 11 continuation commits four bounded changes:

| Revision | Change | Verification |
| --- | --- | --- |
| `226084bb9` | Optional immutable fixed-camera calibration, exact decoder grid/source binding and pixel-centre affine | 96 calibration/configuration tests; missing/null stays uncalibrated |
| `a95a47fdf` | Actual capture-path identity and pre-inference calibration in Classic/Smart inputs; retired-source/mode rejection | 334 video/producer tests and 201 configuration/API/docs tests |
| `b75fc55b7` | Command schema 2.5.0: explicit live-qualified phases, independent of command capability | 1,524 broad and 294 narrow tests; 74 Phase 0 checks |
| `d5458ee85` | Native FW geometry takes four input-independent thresholds, without gimbal manoeuvre/timing policy | 1,110 follower/catalog/handler tests |

These test commands overlap; counts are not additive unique coverage. Logs are
under `reports/sitl/follower-consolidation-20261111/software-gates-r1/`.
The renewed full software gate passes on detached `d5458ee85`: 5,149 unit tests
(11 optional GStreamer skips), 196 integration tests, current schema and zero
fatal lint errors. Phase 0 passes 155 tests at documentation-only revision
`3b4e1c73c`. Its initial clean-clone failure exposed three generated-report
links being advertised as source links; the guide now identifies them as local
artifacts with regeneration instructions. Original failures and exact per-gate
revisions remain in `software-gates-r2/{manifest,result}.json` and logs.

Calibration is a closed optional `VideoSource.FIXED_CAMERA_CALIBRATION` object
with public default `null`. The saved source digest identifies the actual
capture specification/backend, not the physical camera at an address. Runtime
stream/epoch, decoder dimensions, orientation, analysis resize and calibration
content all participate in binding. Missing/mismatched values preserve ordinary
2D measurements but cannot produce a calibrated bearing. Manual gimbal control
does not supply fixed extrinsics. Existing saved/private configuration is not
rewritten. Generated schema: 44 sections, 609 parameters.

Independent review reproduced five capture regressions: same-handle source
epochs or resolution mutation could stamp old pixels fresh; async UDP could
mutate the sole reader's negotiated mode. The read lock now includes commit,
epoch/handle checks reject retired results, and async property mutation refuses
before changing anything. UDP mode changes use normal configuration/reopen.
The failing reproductions are retained beside the passing 334-test run.

The qualification list preserves current permissions for the existing eight
profiles. It does not promote image FW, direct FW rates or VTOL, and it is not
proof of installation/field acceptance. Shared FW math still uses the existing
native EAS/envelope/altitude owner; gains, speeds and mount values are unchanged.

`016154ff2` adds immutable image/attitude association. Physical receipt-time
qualification requires explicit source-bound measured delay intervals and clock
uncertainty; missing bounds refuse it. Exact SIH pairing is separately labelled
and disabled unless the isolated fixture opts in. Duplicate reads retain their
original result/time; rewritten samples, changed bindings/resets and silent
timing-policy changes reject. Root's 384-test alignment/calibration/native-input
gate passes; the broader expert gate passes 1,196 overlapping tests.

`8a5104e2e` adds an explicit native target-geometry reset, preserving last feasible
course, engagement altitude, speed controls and authority identity. It does not
renew continuity budgets or revive a stopped session; 143 planner/session tests
pass. This hook is available for the new image strategy; existing gimbal retarget
adoption remains part of S6's provider audit.

`919674af9` makes additional guidance-input validation a read-only follower hook,
shared by startup readiness and continuity evidence. Native discovery precedes
the specialized check; source/target identity is rechecked before engagement,
after engagement and before activation. A discovery-only failure aborts locally
instead of requesting Hold that was never acquired. Actual/uncertain acquisition
retains owner-aware cleanup. The 27 new cases and final 261-test owner gate pass;
the broader core/follower gate passes 2,904 tests. No fresh timestamp is created
by these reads, and video-only epoch changes do not invalidate non-video camera
evidence. Inactive catalog input-readiness projection remains future integration.

The adapter rebuild at
`reports/native-guidance/image-fw-runtime-20261111-r1/` also passes 38 native
contracts in the pinned network-isolated environment. Its source hashes, binary
checksum and dependency/extension identity are retained for the upcoming SIH
run. No service was installed or aircraft firmware changed.

`c19b5c879` adds the calibrated image strategy through the shared native FW
session. `d9c151161` registers experimental `fw_navigation_chase` with explicit
configuration and no live-qualified phase. Its four geometry thresholds are
separate from native EAS/envelope/altitude authority. Focused registration gates
pass; generated schema is current at 45 sections and 613 parameters. Ordinary
camera timing remains unqualified; synthetic SIH pairing is explicitly labelled.

`6c7f181e5` derives command-preview availability from the canonical transport.
Native-only profiles refuse before construction or connection, including a
pending-configuration race, rather than recommending an unsupported preview.
Existing MAVSDK preview behavior remains; 523 relevant tests pass.

The current adapter and attested source-built airplane also pass renewed native
gimbal component checks on clean PixEagle `65cbf4967`:

| Mount / altitude guidance | Observed target range | Maximum altitude-hold error | Stop |
| --- | --- | --- | --- |
| Horizontal / off | 163.78 -> 25.25 m | 0.245 m | Hold confirmed; no later publication |
| Vertical / off | 163.78 -> 27.49 m | 0.204 m | Hold confirmed; no later publication |

Raw results, source/config/firmware identities and interactive replays are under
`reports/sitl/follower-consolidation-20261111/gm-fw-*-hold-r1/`. These are observed
PX4 approaches with simulated gimbal input, not camera/installation acceptance.

`dd5af2902` retains the original SIH image, paired attitude and measured target
truth during partial telemetry progress. `9b23bf6e2` fixes the reproduced
command-TTL mismatch: a new authoritative aircraft sample recalculates guidance
against the still-current world bearing; frozen polling cannot renew a command.
Expired images enter the existing recovery, without extending its deadline.
The original failing reproduction and the passing 389-test regression remain
in `software-gates-r1/`.

### S5 — actual calibrated-image component response

Clean source `3cb7a8355` passes four `fw_navigation_chase` cases on the attested
SIH airplane and current native adapter. Independent moving world targets are
projected into explicitly synthetic pixels; production calibration, alignment,
guidance, continuity, native ownership and publication remain in the loop.

| Case directory | Observed range | Response | Successful publications |
| --- | --- | --- | --- |
| `fw-navigation-image-hold-r2` | 161.22 -> 28.03 m | Maximum altitude-hold error 0.220 m | 290 |
| `fw-navigation-image-altitude-r1` | 162.51 -> 34.41 m | 7.86 m descent toward the lower target | 290 |
| `fw-navigation-image-reacquisition-r2` | 431.82 -> 296.33 m | 1 s loss; 0.5 s confirmation and 0.5 s restoration | 290 |
| `fw-navigation-image-expiry-r2` | 430.17 -> 331.15 m | Genuine loss handed off after 8.014 s | 216 |

Every case has zero failed publications, confirmed native Hold and no later
publication. Per-case config/schema checksums, parameters, commands, observations
and interactive HTML/CSV/JSON/PNG are retained under
`reports/sitl/follower-consolidation-20261111/`. The canonical read-only validator
(`1954a51dd`) requires matching native response, captured scenario and configuration
bytes before assigning a passed replay. All four have no timeline flags; Chrome
verified target/PX4 points, populated command fields, views and orbit without
page errors. Actual pose receipt times and source timestamps are preserved.

The subsequent source-change case `fw-navigation-image-airspeed-r2` passes on
clean `0dd2fcccd`: 483 successful publications, 0.255 m maximum altitude-hold
error, sensorless continuation after genuine sensor loss, and qualified sensor
return after restoration. Stop confirms Hold with no later publication. Its
explicit simulator-only overlay `ASPD_FS_T_START=2` is recorded separately and
restored to the original `-1` afterward. The first `airspeed-r1` remains failed
for its requested sensor-return assertion: native PX4's default `-1` latches a
failed sensor out in flight even when raw packets return. All its publication,
path and Stop checks passed; it never claimed selected-sensor recovery. Native
policy, not a timeout extension or invented groundspeed measurement, explains
the difference. See the shared FW policy and `airspeed-case-inputs-r{1,2}/`.

The failed `hold-r1` identified a harness-only engagement packet mismatch; the
shared acquisition/publication observer fixes it without relaxing association.
An initial loss fixture put the target outside the camera FOV after stable
loiter and correctly refused before acquisition. Its replacement defines a
visible fixed world trajectory before Start; no guidance gain, limit or
within-run target anchor was changed. Both failures remain retained.

S6's bounded lifecycle prerequisite is also repaired: `aea29d844` clears GM
target-specific PID/filter/classifier memory and invokes the canonical native
target reset while preserving acknowledged controls, submitted-command slew
history and continuity ownership (1,281-test regression). `d6ad4656a` replaces
broken handwritten proportional-on-measurement with the PID library's feature
and handles its initial manual-mode `None` result (1,304-test regression).
Gains, anti-windup equations, defaults and private configuration are unchanged.

The first renewed full unit gate on `1954a51dd` passed 5,484 tests with one stale
catalog expectation: the original-eight configuration identity test rejected
the additional ninth profile. It now checks that those eight mappings remain
unchanged without prohibiting additions; 61 affected tests pass. The renewed full
gate on frozen `132396744` passes 5,514 unit tests (11 optional GStreamer skips),
196 integration tests and 155 Phase 0 checks. Schema is current (45/613), API
inventory matches, and fatal lint has zero errors. Exact source and logs are in
`software-gates-r4/`; earlier failures remain in `software-gates-r3/`.

S5's native image **component/software** checkpoint is closed. Physical timing,
optical tracking, whole-application qualified input, platform and installation
acceptance remain separate; live qualification stays empty. Next is S6's
provider identity/receipt hygiene, then its reviewed capability, timing and frame
cutover. The first sub-slice preserves accepted MC angular calculations and does
not pretend that GAC/TRC proves target-centre alignment or physical exposure.
Backend receipt is not exposure time. No Pi, private-profile, QGC, service or
firmware deployment occurred.

### S6a — external observation identity

`70c69f75e` removes an implicit all-capabilities fallback from incompletely
constructed Vector followers. Missing classifier state now refuses instead of
inventing vertical/reverse permission. Real construction and both mounts retain
their existing calculations; the focused gate passes 139 tests and the follower
regression passes 1,127 tests.

`f0928a40f` binds received gimbal angles and independent tracking status to
the camera transport incarnation and local selection generation. Receipt time,
boresight semantics and unconfirmed physical target identity remain explicit.
Gimbal output no longer synthesizes pixels or advertises image normalization.
Manual gesture cancellation must leave the observation source intact; real
provider start/stop/replacement invalidates it independently of video epochs.

The first affected gate passes 3,097 tests. Independent review then identified a
startup lock held across manual-worker readiness, which could delay camera Stop,
and an unsupported in-place replacement that could orphan a running provider.
The final captured gate passes 476 tests after both repairs, including real
blocked-worker readiness, immediate cancellation, idle control availability,
original-provider cleanup and a normalized provider independent of SIP inheritance.
Commands and input hashes are retained in
`software-gates-r1/s6a-source-hygiene-final-focused.{log,json}`. Earlier broad
results are labelled transcript summaries, not frozen final-source evidence.

`a4ebef4cf` adds the pure source-comparison contract (47 focused tests). It checks
independent publisher/runtime ownership as well as the sample's geometry/source,
without rebinding on retarget, frame progress or media delivery changes. A source
identity read remains available during real lifecycle invalidation; it is separate
from the availability of usable angle data. The next consumer sub-slice must
retain the original source before awaited startup, apply the existing continuity
policy to missing data, and reject definitively changed or superseded work at
the actual publication boundary. These foundations do not yet claim that gate.

Tracker reference/development docs now remove the old synthetic-pixel and
duplicate Euler-transform examples. Physical target, mechanical capability and
timing/frame qualification remain open. S6 is not closed, and no new live phase
is admitted. The completed S5 isolated simulator was stopped to release resources;
its container, evidence and software-only shutdown record remain retained.

Full S6a renewal on frozen `b0228d991` passes integration (196), Phase 0 (155),
schema/inventory and fatal lint. Its unit sweep passes 5,631 with two obsolete
factory mocks for the removed `CoordinateTransformer`. `5a4fbb4bf` replaces those
mocks with actual inactive-provider construction; the frozen unit renewal passes
5,633 tests (11 optional GStreamer skips). Both exact revisions and logs remain
in `software-gates-s6a-r{1,2}/`; the later gate excludes ongoing consumer work.

### S6 — command frame and queued publication prerequisites

`f6793260c` corrects GM PID's physical-FRD versus MAVLink-heading mismatch. With
+30-degree roll and a target directly ahead/below in NED, both mounts previously
commanded +0.353 deg/s yaw despite zero target bearing. The canonical conversion
now precedes angular PID error extraction and gives zero yaw. The 251-test gate
includes 84 real-constructor cases covering both mounts, lateral/altitude modes,
combined attitudes, wrap, level-flight characterization and stale refusal. Gains,
ramps, limits and forward-speed laws remain unchanged. Component CSV/PNG and
failed/passing logs are retained under `software-gates-r1/s6c-pid-frame-*`.
These are calculation proofs; actual SIH response renewal remains pending.

`359218ffd` adds a reusable synchronous dispatch guard to the native client and
MAVSDK boundary (206 focused checks). Accepted command fields survive queued
waits; mode/setter dispatch is recorded conservatively, and pre-acquire refusal
uses the existing read-only sender cleanup without an unrelated Hold. This is
the transport foundation only: the original-source session consumer and its
integrated software gate are still in progress. Explicit Stop stays separate
from stale pursuit/retarget work. See plan section 4 for the shared semantics.

### S6b — retained source and final-dispatch consumer

`fdb303b3d` freezes the observation owner before awaited startup and retains it
through same-source retargets. Missing observations use the existing continuity
budget; a definitely changed owner terminates the original session. The final
write guard checks captured session, target, source, aircraft and control
revision after queued waits. Superseded work is skipped without a failed-link
count; explicit Stop remains independently reachable. Accepted fields and their
source context are traced rather than rereading a mutable handler after an ACK.

Startup distinguishes possible mode acquisition from local sender priming.
Refusal before acquisition cannot request Hold. Unconfirmed sender cleanup keeps
the original binding and blocks another Start. Independent review also found and
fixed delayed continuity tasks capturing a newer session: their synchronous
schedulers now retain the original session/supervisor before task execution.
The focused source/owner/dispatch gate passes 549 tests. These are software
checks, not renewed aircraft-response evidence.

The frozen broad run in `software-gates-s6bc-r1/` passes 5,794 unit tests with
two obsolete tracker-provenance fixtures failing; integration passes 194 with
two fake senders rejecting the new immutable command arguments. The original
failures remain retained. `7b409aefd` updates those fake senders and the frozen
`software-gates-s6bc-r2/` renewal passes all 196 integration and 155 Phase 0
checks, schema/inventory and fatal lint. `56c2b33c0` gives the synthetic tracker
fixtures actual source/frame bindings and pixel positions; 62 focused and 584
tracker tests pass. Preview publications remain explicitly non-physical. A
combined full unit renewal is still required after the reviewed SIH-tooling
change; neither the earlier failing run nor the focused tests establish it.

S6 remains open for separating observation limits from aircraft manoeuvre
support, bounded attitude association and renewed actual horizontal/vertical
gimbal SIH. Physical timing and native-FW installation gates stay closed. Public
defaults, the saved private profile, QGC, hardware and services are unchanged.

### November 12 continuation — frozen foundation renewal

`fb21da6d4` routes eight nominal gimbal MC scenarios through the canonical
source-owned SIH worker: PID/Vector, horizontal/vertical, altitude off/on. The
335-test tooling gate and eight read-only launch dry-runs pass. Actual captures
remain pending. Synthetic image pixels now round-trip through the production
normalizer; unsupported gimbal fault/retarget scenarios refuse before launch
rather than failing after simulated acquisition. This is deliberately narrower
than complete gimbal fault qualification.

`3ac33e443` fixes the audited last pre-SDK MAVSDK Stop scheduling gap. The original
SDK/connection/aircraft/session/start context survives queued cleanup and retries;
takeover or replacement withholds Hold, without clearing a replacement sender's
state. Its frozen integrated gate passes 1,026 tests, with 168 focused manager
checks and four preserved scheduling reproductions invoking zero SDK Stop calls.
The limitation after an SDK RPC has already been invoked remains explicit.
Native transition-preserving release and S7 actual SIH are still unimplemented.

`f23753005` shares image/gimbal bearing association without synthetic gimbal
pixels or exposure claims. Independent review reproduced and repaired provider
identity drift, cached physical-bound expiry and same-sample quaternion rewrites.
The 322-test focused and 1,976-test follower/drone gates pass. Reported estimator
resets remain visible and invalidate older associations. These counts overlap;
they are not additive unique tests.

The coherent frozen source at `f23753005` passes **5,940 unit tests**, **196
integration tests**, **155 Phase 0 checks**, schema/inventory and fatal lint;
11 optional GStreamer introspection tests skip. Exact commands, exclusions,
checkout and logs are in `software-gates-s6-foundations-r1/`. This excludes the
subsequent capability migration/native-gimbal consumer cutover, which still needs
its own combined gate and actual horizontal/vertical MC/FW response renewal.

Read-only S7 native review also found a distinct activation-epoch problem: late
cleanup can replace the original lease's activation timestamp with the current
same-mode activation. The audit and pinned source excerpts are retained in
`software-gates-r1/s7-native-transition-release-audit/`. It is not repaired or
qualified by the MAVSDK foundation. No hardware, private saved configuration,
installed service, QGC, main branch or release artifact has changed.

### S6 input cutover — combined software gate

`adb9b68f6` separates implemented MC manoeuvres from optional observed-ray
windows, removes provider permission grants, and migrates the retired mixed
capability object through Config Sync. Known factory placeholders preserve the
accepted boresight behavior. Ambiguous/custom legacy values keep API/startup
available but require explicit canonical choices before Vector Start. Unrelated
merge imports and ancestor updates preserve pending retirements; canonical
digests reject boolean/integer overwrite ambiguity. Explicit reviewed removal,
CAS, backup and rollback remain the existing configuration service's operations.
Dashboard accepts the backend's existing nested 1–16-component paths.

Native gimbal preparation retains its unbound session for input qualification
before acquisition. No command can be calculated before binding. Both native
input families share association/progression checks; ordinary input expiry uses
the existing FW recovery budget, while Stop and geometry/authority guards retain
precedence. Review reproduced and repaired missing-current-state acceptance,
preparation ordering and accidental MC emergency Stop on ordinary FW expiry.

`2f7082a4c` shares retained actual native-pose validation between image and
gimbal SIH fixtures. The frozen combined gate passes **6,072 unit**, **196
integration**, **155 Phase 0**, and **141 special harness/smoke tests**, plus
schema/inventory/fatal lint. Dashboard passes **523 tests** (65 suites), lint
and production build. Eleven optional GStreamer introspection tests skip. Exact
commands/source are in `software-gates-s6-combined-r1/`; overlapping development
gates and independent review logs remain separately scoped.

The first actual GM MC run reached stable flight but stopped before Offboard:
the harness rejected its own recorded resolved continuity policy as an authored
override. The failed `s6-mc-gm_velocity_vector-horizontal-off-r1` is retained.
`115192e15` fixes only this report-analysis boundary; authored policy overrides
remain forbidden. Its frozen 336-test harness gate passes; production/config/
Dashboard/native bytes are identical to the combined gate. The retry confirms
actual range closure, zero failed publications and Hold after Stop. The remaining
nominal matrix, gimbal fault captures and native-FW response renewal are still
required; S6 is not closed by the software gate or one passing run.

### S6 observed renewal — November 12

All eight nominal GM MC cases at `115192e15` pass: Chase/Vector, both mounts,
altitude off/on. The actual PX4 traces retain **3,784 successful publications,
zero failures**, maximum publication gap 0.062 s, range closure and confirmed
Hold without later commands. Altitude-off hold error is at most 0.232 m; the
on cases show independently observed target-directed vertical response.
`software-gates-r1/s6-mc-nominal-results-r1.json` retains the case results.
Eight interactive reports also pass a real browser check: observed pose/target,
finite command fields, side/top views and orbit, with no JavaScript errors.

The four renewed native GM FW cases pass on the same frozen source: both mounts,
altitude off/on. Actual range closes from roughly 160–163 m to 28–34 m.
Altitude-off hold error is below 0.284 m; altitude-on response descends about
7.6 m. Native course/EAS/height commands remain distinct from MC body velocity.
Their reports pass the same browser/pose checks. Cases are retained at
`s6-gm-fw-{horizontal,vertical}-{off,on}-r1/`, with exact configuration, source,
adapter and PX4 provenance. The final descending case finishes below the
runner's 15 m stable-start floor; fault tests therefore require a fresh isolated
airborne preparation, not a relaxed gate. No physical aircraft is involved.

Tools-only `bf98f4dd0` adds received-fault witnesses before operator cleanup,
same-source simulated target-generation retargets and actual SDK mode-call
observation through cleanup. Its frozen affected gate passes **458 tests**;
production/configuration/native/Dashboard bytes remain identical to the full
combined gate. The first one-second MC loss case passes with received loss,
reacquisition and restored guidance. The remaining matrix is paused for two
independent review findings in the test verdicts: observe the original recovery
deadline across repeated retargets, and reject an immediate-handoff result when
the GM runtime policy promises bounded recovery. These are evidence gaps, not
new production-controller failures. Preserve the passing short-loss capture and
all older failed attempts; rerun affected cases after the checks are repaired.

The S4 raw-evidence audit supports the latest fifteen image-follower loss,
stale-telemetry and takeover cases. The historical Chase takeover `r2` capture
does not support its stronger fault-handoff claim: its final reason is
`operator_stop`. Keep it as superseded history; the later `r3` supplies the
fault-specific evidence. The audit is retained in
`software-gates-s6-combined-r1/s4-fault-evidence-audit.{json,md}`. No raw verdict,
trace or historical animation was rewritten. S10 must keep this disposition in
the selector rather than promoting an old green result.

S6 still requires renewed fault results. S7 native activation-bound release and
end-on-transition remain open. Physical timing, target/boresight alignment,
installation, HTTP/App startup, clients and release qualification remain separate;
the public/private saved defaults and hardware are unchanged.

### S6 component/software checkpoint complete

The source/receipt, geometry, dispatch, capability migration and native bearing
work now has renewed actual PX4 component evidence on the reviewed baseline:

| Evidence | Selected passes | Publication evidence |
| --- | --- | --- |
| GM MC nominal: Chase/Vector, both mounts, altitude off/on | 8 | 3,784 successful MAVSDK publications, zero failures |
| GM MC faults: both followers/mounts, short loss, expiry, repeated retarget, pilot takeover | 16 | 6,063 successful MAVSDK publications, zero failures; maximum gap 0.065 s |
| Native GM FW: both mounts, altitude off/on, short loss and expiry | 8 | 2,170 successful companion submissions; 3,356 observed native publications; zero failed submissions |

The nominal captures use `115192e15`. The first MC short-loss capture uses
`bf98f4dd0`; the other selected fault captures use `7327c2153`. These later
commits change test tooling and documentation only: production, configuration,
Dashboard and native implementation bytes remain identical to the combined
`2f7082a4c` gate (6,072 unit / 196 integration / 155 Phase 0 / 141 special tests;
523 Dashboard tests, lint/build and static/schema checks). The final committed
fault-tool gate passes **487 tests** in a clean frozen checkout. Its manifest is
`software-gates-r1/s6-fault-witness-committed-frozen-r1.json`.

The strengthened tests reject a deadline-only reset or compatibility immediate
handoff in a configured bounded GM case. Actual repeated selections preserve
the original pending deadline. After confirmed restoration a later selection
legitimately creates a new episode. Actual pilot Hold produces release with no
additional backend `action.hold`/`offboard.stop`, including final cleanup. The
independent reader retains exact source/receipt, trace-line and checksum witnesses.

One original Vector-V long-loss run failed only its vertical-response gate:
0.021272 m against 0.1 m. Correctly signed climb commands and measured response
precede the outage, but hover drift and the short excitation interval leave
insufficient net motion. The original H case passed at 0.113555 m. Both stay
retained. Two **distinct** initial-climb fixtures start the target 3 m above
at t0/t4, matching the original t8 height; all later points, loss schedule,
gains, limits and the 0.1 m gate remain unchanged. They pass with 0.420776 /
0.400268 m vertical work. This qualifies the revised fixture, not repeatability
of the original weak-excitation case. The fault archive contains eighteen
attempts and sixteen explicitly selected passes, with failed history visible.

Evidence under `reports/sitl/follower-consolidation-20261111/`:

- `software-gates-r1/s6-mc-fault-proof-r2.{json,md}` and its proof manifest;
- `software-gates-r1/s6-mc-fault-browser-r2.json`: all eighteen fault/history
  reports load, play, scrub, change views and orbit without JavaScript errors;
- `software-gates-r1/s6-gm-fw-fault-evidence-r1.json`: actual short-loss
  restoration, 8.041 / 8.016 s expiry, native flight policy with no MC travel
  budget, Hold and unchanged post-release publication count;
- nominal MC/FW and fault FW browser manifests: another sixteen checked reports;
- `s6-fw-gimbal-runtime-r{1,2}/stopped-and-log-hashes.json`: owned simulators
  stopped, ULogs flushed and hashed. No physical service was started or changed.

All **34 completed report pages** were browser-checked; the selected matrix is
32 passing component cases. Raw evidence and failed verdicts remain unchanged.
Physical gimbal mechanics, target-centre alignment/exposure timing, whole-app
startup and live FW/VTOL admission remain separate. The S6 source fixture does
not turn unknown mechanical limits into physical qualification. Public/private
saved gains, speed ceilings, altitude settings and geometry remain unchanged.

### S7 next — causal native ownership and transition-preserving release

Independent pinned-source reviews found that current mode ID/epoch and command
acceptance cannot establish which request caused acquisition. A pilot may select
the same external mode while Start is pending; a prior activation may also be
replaced before a status poll. Same-ID explicit selection need not advance PX4's
mode timestamp. The supported executor interface does not resolve those cases.
An adapter-only receipt derived from a later status would overclaim ownership.

The reviewed next implementation adds an optional atomic `OwnedModeRequest` /
`OwnedModeStatus` extension **replacing** the adapter's raw mode-command route.
It reuses Commander intention/CAS handling and the existing native owner/lease.
Standard VehicleCommand/VehicleStatus definitions and ordinary MAVSDK remain
unchanged. Correlation identifies the original request/incarnation/intention
revision and actual resulting activation; release cannot adopt a newer epoch.
The existing custom-message build/compatibility workflow owns the extension.
Native-clock expiry and host RPC timeout remain distinct; paused/scaled SIH
cannot establish host-wall deadline equivalence. Entropy availability is an
explicit platform gate. No weak boot identity or raw fallback is authorized.

The source audits and alternatives are in
`software-gates-r1/s7-native-transition-release-audit/`. Implementation has begun
in a fresh standalone pinned source checkout; no new firmware build, simulator
or hardware claim follows yet. End-on-transition/new-Start, transition-preserving
release and actual tailsitter/standard-VTOL qualification remain open. S7–S13
continue under the same plan, with no QGC PR or hardware changes in this slice.

### S7 causal ownership foundation — software gate

The atomic request/receipt implementation now replaces the raw mode-command
route. Private RPC protocol 2 pins the original acquisition token, runtime,
firmware incarnation, intention revision, registration and resulting activation
epoch. Submitted intents and cleanup require that context; lost acknowledgements
are reconciled read-only. Accepted pilot changes, including same-ID selections,
retire the original ownership. Pending cancellation cannot become a later Start.

Independent review reproduced two additional races: activation crossing the
native deadline, and a firmware restart whose lower publication clock hid its
new incarnation. Both have regressions. Late activation stays unresolved until
actual release; reset-clock packets retire the old owner without becoming fresh
status. The obsolete compare-mode helper, custom status flag and runtime branch
are removed by patch 02. Standard VehicleCommand/VehicleStatus are unchanged.
The build manifest verifies required removals as well as retained file hashes.

| Gate | Result and scope |
| --- | --- |
| Frozen Python migration | 6,268 unit, 196 integration, 74 Phase 0; 11 optional GStreamer skips, 14 unit subtests |
| Native contracts | 19 production firmware-helper and 45 C++ adapter contract tests |
| Real PX4 intention/entropy | Seven functional tests, including ineligible Hold and actual POSIX entropy |
| Adapter compile | Generated final custom messages, adapter and main compile; executable not started |
| Build/verifier delta | 25 tests, fatal lint/compile/diff clean; no added full-Ruff rule-count findings |
| Patch round-trip | Both patches apply to the pinned baseline; 20 final hashes match and two removed files are absent |

The Python gate uses the unchanged r14 sources in
`software-gates-s7-python-r1/full-backend-results-r1.json`. Later build-verifier
changes are covered separately in `software-gates-s7-r1/`; final native compile,
functional and source manifests remain there. Earlier failed link/configure
attempts are retained. PX4's pinned functional runner logs pre-test workqueue
startup diagnostics; the real health fixtures initialize their own workqueue,
and these tests do not qualify worker timing or NuttX entropy.

This is a software foundation, not a new SIH or aircraft acceptance. Full SIH
firmware build, continuous neutral publication during release, transition
disposition, end-on-transition/new-Start wiring and actual tailsitter/standard
VTOL fault evidence remain open. VTOL admission stays closed. No hardware,
public/private saved settings, controller gains or QGC files were changed.

### S7 source build and first observed response

Committed foundation `3233d0faa` passes the normal pinned SIH builder: 1,172
compile/link steps, `DONT_RUN=1`, network disabled. The verified bundle is
`reports/native-guidance/sih-s7-ownership-build-20261112-r1/`; its build result
retains board configuration, generated header, CMake cache, compiler/runtime
pins and binary/ROMFS hashes. This is an explicitly selected test bundle, not a
new default image or hardware firmware.

A fresh isolated `sihsim_airplane` then reached seven stable native-Hold samples
near 30 m before any native acquisition. Three production-component moving-target
runs pass on the new firmware and generated-message adapter:

| Input/profile | Mount | Actual target range, start → end | Maximum altitude-hold error |
| --- | --- | --- | --- |
| Gimbal Vector | Vertical | 162.60 → 36.06 m | 0.524 m |
| Gimbal Vector | Horizontal | 162.95 → 32.07 m | 0.063 m |
| Calibrated image FW navigation | Horizontal | 163.30 → 33.47 m | 0.129 m |

These altitude-guidance-off cases record **870 successful component submissions,
1,347 adapter-observed publications, zero failures**, and maximum recorded write
gap **55.636 ms**. Each retains the original acquisition context through observed
native Hold and has no later publication. Independent checks and raw/derived file
hashes are in `software-gates-s7-r1/native-nominal-independent-proof-r1.json` under
the consolidation run root. All three validated HTML/CSV/PNG reports load in a
real browser with actual pose, independent target, finite native command values,
working scrub/views/orbit and zero page errors.

This renews component acquisition/normal release, not takeover/disconnect,
transition preservation, altitude-enabled response or full-application startup.
Those scopes retain their separate gates; the new causal-ownership fault harness
and terminal neutral draining are next. No hardware or installed service changed.

### S7 baseline ownership fault checks

Four isolated airplane cases now pass on the committed `3233d0faa` foundation:
normal Stop, confirmed-owner socket EOF, pilot reselection of the same external
mode, and delayed original cleanup after a newer acquisition. These use the
production binding/publisher with absent target evidence and phase-confirmation
baselines. They qualify causal ownership and cleanup, not tracking, mounting,
VTOL, lost engagement acknowledgements or aircraft operation.

The independent file-only audit is
`software-gates-s7-ownership-tool-r1/independent-raw-audit-r1.{json,md}` under the
consolidation run root. It verifies exact original ACK/source context, successful
submissions, actual pose, same-epoch intention retirement, read-only reconciliation,
and publication stopping after correlated release. Delayed cleanup cannot write
the original token into the newer acquisition or close its socket. Pilot
reselection produces an already-released result rather than a backend Hold claim;
independent simulator cleanup is recorded after that verdict.

Two earlier harness failures remain unchanged: the EOF parser treated an actual
socket lifecycle marker as an RPC, and the first post-cleanup read combined a
new ownership receipt with the preceding VehicleStatus. Regressions retain exact
raw subsets. Coherence waiting uses only the original status's remaining freshness
allowance; polling does not renew it. The selected EOF run proves its timing check
in the archived tool, but lacks the absolute monotonic origin needed to recompute
that inequality independently. Subsequent captures archive that origin explicitly.

**ULog retention gap:** the default PX4 logger rotated at 1 GiB and automatically
deleted its earlier file under the host free-space cleanup policy. The runtime
was stopped during the next file's creation; no ULog survives for this batch.
`s7-native-ownership-runtime-r1/px4.log` and `stopped-and-log-hashes.json` retain
the deletion and empty ULog inventory. Per-case PX4 pose/status, wire traces,
configuration, parameters and verdicts remain. Do not claim ULog corroboration
or full qualification from this batch. Later runs must flush/archive logs before
rotation and stop simulators while long software reviews are pending.

Registration replacement, continuous neutral release publication, adapter-process
restart and end-on-transition remain open. Their reviewed implementation and
fresh bounded SIH runs follow; no hardware, gains, saved configuration or QGC
files changed in these ownership checks.

### S7 registered-owner and neutral-release software delta

The reviewed SDK overlay exposes only its own successfully matched registration
request ID and an opt-out from automatic weak unregister. The adapter pins that
ID before acquisition and retires permanently after confirmed registration loss
or aircraft/incarnation conflict. Other SDK clients retain normal defaults.
Deferred native garbage collection can wait for disarm; rapid adapter-process
restarts can still exhaust the eight slots. No prompt cleanup claim is made.

Stop, socket EOF, command expiry and fresh phase exit now terminally revoke
pursuit. While the original activation still needs conditional release, the
existing callback can publish current-data-only neutral setpoints. It cannot
reuse the previous target objective, restore an old speed request or renew a
deadline. Exact original registration, token, activation, aircraft and fresh
status remain required, including a matched Releasing receipt. Startup retains
only its original bounded confirmation window and publishes nothing before
causal acquisition is confirmed. The obsolete phase-hold helper is deleted.

The combined source gate is frozen in
`software-gates-s7-integration-r1/integration-review-manifest-r1.json`: fresh
matching SDK build, four genuine SDK registration/lifecycle tests, 63 native
contracts plus 63 ASan/UBSan checks, adapter/main compilation and 35 packaging/
baseline tests pass. Root verifies all eighteen source hashes and two removals;
the seventeen affected builder tests also pass after integration. The runtime
bundle includes the matching SDK and generated-message libraries, with loading
paths and hashes checked separately. The failed initial output-permission build
is retained.

Actual registration reuse, neutral draining and transition preservation remain
unqualified by this software gate. Native release still uses conditional
AUTO_LOITER; its effect on a pilot-requested transition must be observed before
claiming preservation. Backend end-on-transition migration and process-restart
reconciliation remain open; VTOL admission stays closed. No controller tuning,
saved profile, standard DDS message or hardware changes accompany this delta.

### S7 Python 3.10 compatibility

A real Python 3.10.20 check reproduced startup failure in the native client:
`asyncio.timeout` is unavailable on the supported interpreter. The client now
uses existing `wait_for` APIs with one absolute drain/reply deadline and one
overall read-only reconciliation budget. Final dispatch guards and socket write
remain inline; timeout/cancellation retires only the captured current socket
without waiting through another close deadline. Explicit normal close remains
bounded. No dependency or supported Python-floor change is introduced.

`software-gates-s7-python310-r1/review-manifest-r1.json` freezes 118 native-client
tests on actual Python 3.10 and 118 on 3.12, plus 243 affected 3.12 checks. Compile,
fatal lint and diff checks pass; the existing fourteen full-Ruff diagnostics are
unchanged. Original runtime and test-fixture failures remain archived. This
renewal covers transport/cleanup compatibility, not new aircraft behavior.

### S7 renewed release and registration response

On `05d38b175` with the matching reviewed SDK/adapter, normal Stop and confirmed
backend EOF pass on a fresh stable SIH airplane: 61 acknowledged baseline intents
each, original-context native Hold and stable post-release publication counts.
The retained ULog corroborates actual modes, pose and native setpoints; maximum
active setpoint gap is 36 ms. The newly retained host clock origin independently
proves EOF occurred with 0.254638 s remaining on the last intent. Evidence is
`software-gates-s7-integration-r1/actual-release-proof-r1.json`; the checked visual
summary is `actual-release-summary-r2.png`. Fast Hold did not exercise sustained
neutral draining, so that remains a separate test. The earlier summary rendering's
unsigned-time error is retained as superseded derived output, not selected proof.

The first actual registry-reuse case also passes: PX4 garbage-collects stopped
adapter A while disarmed; B reuses mode 23 and health slot 0 with a distinct SDK
request ID. Resumed A exits with `native_registration_lost`. Fourteen retained
fresh B snapshots and a flushed reliable monitor show B's registration/preflight
preserved and zero observed weak unregister messages; B then reaches seven
stable airborne samples near 30 m. `s7-registration-runtime-r1/overall-result.json`
records the stopped runtime and retained ULog. This is bounded registry/baseline
evidence, not a following, target, transition or zero-stale-health-reply claim.

Both new runtimes are stopped. Their flushed ULogs are retained and hashed
(55,293,264 and 8,184,499 bytes); neither logs ownership-status messages, so raw
CLI/wire/registration replies remain the causal ownership witnesses. Backend
end-on-transition migration and private-protocol retirement are still under
review. Hardware, installed services, saved profiles and QGC are unchanged.

### S7 end-on-transition backend migration

Start now pins one supported settled phase and initializes its controls and
continuity policy once under the original acquisition identity. A fresh transition
or unexpected phase ends the session; settled telemetry cannot resume it. The
backend's transition pursuit/rebind paths and transition timeout are removed.
Schema 1.9 retires only `Follower.VTOL_TRANSITION_TIMEOUT_S` through Config Sync
preview/apply; saved files are not silently rewritten. Startup phase confirmation,
target-loss budgets, gains and ordinary public/private defaults remain intact.

Native completion uses its already-validated original receipt. Already-released
ownership is not a new Hold claim; the original supervisor records completion
once. Review also reproduced a link-loss gap: aborting the socket could discard
the binding before release proof. That path now aborts, then uses existing
read-only reconciliation. Failed or mismatched proof retains the original binding
and Start barrier; a replacement owner is untouched. No additional mode request
or new recovery service is introduced.

The frozen phase gate passes 708 targeted and 87 Phase 0 checks with schema/static
verification. Its broad run retained four fixture-migration failures alongside
4,265 passes; the final targeted renewal covers those corrections, rather than
claiming a full broad pass. The small link-loss delta passes 487 checks, including
nine real-client/Unix-protocol-server cases; preserved original code reproduces
eight failures. Root's migrated ownership/native-vector callers pass 193 checks,
and the final ownership/link-loss combination passes 67. Manifests are in
`software-gates-s7-end-transition-r1/` and its `connection-loss-r2/` subdirectory.

The private phase-advance API is retired next in a coordinated protocol cutover.
Actual transition preservation, process-restart limits and the MAVSDK queued-Stop
boundary remain S7 gates. These software changes do not reopen VTOL/hardware
admission or change the installed Pi/QGC.

### S7 private protocol retirement and coherent candidate

Private RPC 3 removes the old phase-advance operation, transition pursuit payload
and lease-rearming branch. Settled native MC support is named
`multicopter_supported`; observed transition state and internal neutral draining
remain. PX4 ROS API 2 and firmware ownership contract 1 are unchanged. Protocol-2
peers are refused before acquisition, and historical protocol-2 captures/fixtures
remain byte-identical. Backend and adapter must be updated together at deployment.

The integrated software gate passes 727 affected checks, 74 Phase 0 checks and
118 client tests on actual Python 3.10. The matching adapter/main compiles with
66 native, 66 ASan/UBSan and 35 packaging checks. Its unchanged SDK/message inputs
are hash-attested rather than rebuilt. Root's 218-check integration renewal passes
after repairing a test-only dependency on a previously loaded dynamic Parameters
attribute; the failed ordering-sensitive test run remains retained. Full combined
unit/integration renewal follows on the committed candidate. Source and bundle
manifests are in `software-gates-s7-protocol3-integration-r1/` and
`software-gates-s7-protocol3-build-r1/`.

A separate read-only review closes the **pre-SDK** MAVSDK queued-Stop software
gate without a production change: the existing inner captured-owner guard runs
inside the queued coroutine immediately before SDK entry. All 22 authority
tests pass on Python 3.12; installed 3.10/3.11 scheduling sources were inspected,
not presented as integration runs. `software-gates-s7-mavsdk-queued-stop-r2/`
records exact sources and scope. Stock SDK/gRPC requests already submitted remain
potentially nonretractable; this is not PX4-level atomic release qualification.

S7 still needs actual VTOL transition, failure and restart evidence on this
candidate. Restart remains fail-closed: a new runtime cannot confirm an old
receipt, disarm alone does not clear the App barrier, and no automatic Start is
permitted. Hardware, publication and release gates remain separate.

### S7 combined renewal and transition evidence tools

The frozen `cc5ebce07` renewal passes 6,308 unit checks with 11 optional
GStreamer skips, but fails one report-loader test. Integration passes 196;
Phase 0 passes 154 and fails its fixture-hygiene check. These retained failures
are in `software-gates-s7-final-r1/`; they are not a full green gate.

The report now derives settled VTOL contracts from the canonical follower
catalog, including FW-only composition, without requiring retired transition
pursuit. The two terse fake callbacks are explicit functions; the hygiene rule
is unchanged. A shared transparent wire recorder archives exact helper bytes
and one host clock origin. The native SIH runner adds one explicitly declared
pilot transition and read-only post-release settling. It requires real backend
termination, the original receipt and constant post-release publication counts;
an independent ULog gap audit remains mandatory. It cannot resume following.

The frozen tool/viewer gate passes 383 checks; root's combined renewal passes
321. `software-gates-s7-vtol-tool-r1/` retains exact sources and manifest. Root
removes one extra final newline from the new recorder file. Global target-clock
slicing and the production lifecycle-observation fix remain under review before
the next full renewal and actual VTOL execution. No runtime or hardware action
is claimed by these tool tests.

### S7 immediate native lifecycle interruption

A real-client reproducer exposed a lifecycle ordering gap: a validated reply
reporting owner loss or unavailable aircraft state was rejected before reaching
the session observer. Public dispatch already refused commands, but internal
controls could remain active until the generic publisher failure path ran.

The existing observer now receives the actual reply before dispatch admission.
Absent, expired or rejected state is typed `None`, never a cached pose. The
binding fences its original acquisition before target work, ends controls and
uses the existing terminal-dispatch callback on that first attempt. Replacement
ownership is not aborted. The canonical phase owner records a fresh progressing
transition even when its reply also confirms release; binding, stale state,
rescue, layout and sequence guards retain precedence. No second callback,
supervisor, command route or fabricated ownership is added.

The frozen candidate passes 369 scoped checks, 74 Phase 0 checks, schema and
critical static checks. Root's combined native/tool/doc renewal passes 325.
The full Ruff comparison retains 13 existing findings, with none added.
`software-gates-s7-observation-order-r1/fix-r1/review-manifest-final.json` records
the exact seven files and tests. Missing-wire/invalid-reply exceptions without
a validated observation retain the existing generic failure policy; this change
does not invent a phase on communication failure. Full combined renewal and
actual protocol-3 transition evidence remain next. The FW guide now presents
only the current session behavior and labels earlier phase-retaining figures
historical.

The independent source/hash review found no concrete blocker in that frozen
lifecycle candidate or the earlier viewer correction; it did not run flight
tests or certify the subsequent target-clock change.

### S7 shared target clock for explicit Starts

The native component runner can now read one immutable target-clock artifact
binding the original scenario bytes, target ID, NED frame, host boot and
monotonic origin. Two separately invoked Starts sample that same world trajectory
at their actual observation receipts. Each report exports a self-contained slice
without moving the target relative to the aircraft or resetting its clock.
Changed artifacts/boot or missing trajectory coverage refuse acquisition.

A wire transition witness can precede its in-flight lifecycle callback. The
runner now waits, without submitting another intent, for that existing attempt's
terminal completion within its publication timeout plus one period. Missing or
wrong completion still fails. The three-file delta passes 291 focused checks;
root's combined tool/native renewal passes 307. Exact artifacts are in
`software-gates-s7-vtol-tool-r2/`. No cycle auto-start or runtime action is added;
the original 2 m altitude and independent 100 ms native-gap gates remain.

### S7 protocol-3 observed renewal and tailsitter baseline

The frozen clean `66d54217a` backend gate passes **6,339 unit** tests (11
optional-GStreamer skips), **196 integration** and **155 Phase 0** tests, plus
schema and route inventory. Exact commands, source hashes and logs are in
`reports/sitl/follower-consolidation-20261111/software-gates-s7-final-r2/`.
This renews the backend software, not all later report/tool edits or aircraft
admission. The unchanged native inputs match the compiled protocol-3 bundle:
66 native, 66 ASan/UBSan and 35 packaging checks remain separately attested.

Three fresh airplane component cases pass on that revision and matching bundle:

| Input / mount, altitude guidance off | Successful submitted intents | Independent target range | Maximum altitude deviation |
| --- | ---: | ---: | ---: |
| Gimbal / vertical | 291 | 162.96 → 37.27 m | 0.386 m |
| Gimbal / horizontal | 290 | 162.95 → 36.25 m | 0.277 m |
| Calibrated image / horizontal | 290 | 162.95 → 33.14 m | 0.291 m |

All 871 actual wire intents are finite and acknowledged. The independent ULog
audit matches 869 unique pose points exactly, observes no logger dropouts and
finds active native FW setpoint gaps no larger than 36 ms, including release
edges. Each original session reaches confirmed Hold with no later submission.
The audit and three checked interactive replays are linked from
`reports/sitl/follower-consolidation-20261111/s7-protocol3-fw-runtime-r1/index.html`.
These remain simulated-input component checks, not optical or full-App acceptance.

The first real `sihsim_xvert` MC-to-FW run correctly ends following on transition,
reconciles its original release receipt and makes no further acquisition or intent.
PX4 settles in FW Hold. **The run nevertheless fails** its unchanged 2 m
altitude gate, at 6.806 m. Its MC ULog was decimated at 200 ms, so the separate
100 ms active-publication gate remains **unverified**, not failed or passed.
An earlier parser refusal occurred before arming and is retained separately.

Native-only comparisons then remove external ownership and following entirely:

| Disposable simulator comparison | Completion | Maximum relative-altitude deviation | Result |
| --- | --- | ---: | --- |
| Default transition threshold 7 m/s, first observer | incomplete | retained physical trace only | observer failure; not accepted |
| Default transition threshold 7 m/s, corrected observer | complete | 6.962 m | altitude gate failed |
| Explicit trim-speed transition threshold 15 m/s | complete | 8.414 m | altitude gate failed |

The higher threshold is **not adopted**. Its selected sensor CAS crosses 15 m/s
4 ms before actual FW entry, with no TECS underspeed flag in the FW capture;
the altitude breach begins during the longer 8.764 s transition. Native level
altitude objectives remain present. These comparisons demonstrate that failure
also occurs without PixEagle pursuit; hover entry differs from the moving
follower case, so they do not isolate a single cause or exonerate every release
effect. Native transition, loiter and plant/controller behavior still need review.
Do not transplant simulator gains or relax acceptance to conceal that failure.

Raw captures, parameter diffs, exact binaries and independent audits remain under
`s7-protocol3-xvert-runtime-r2/`, `s7-xvert-onboard-baseline-runtime-r{1,2}/`,
`s7-xvert-trim15-baseline-runtime-r1/` and their `software-gates-s7-*audit*`
directories. The approved additive logger preserves profile 131, records actual
control topics at source rate and reports zero dropouts in completed native-only
runs. Those runs have no external publisher and cannot qualify its timing.
All these owned simulators are stopped; public/private saved profiles and
hardware are unchanged.

Review also found a report-only defect: after release in FW, the tailsitter glyph
could use the physical MC body axis because no current FW command remained.
The renderer now selects the supplied PX4 native axis from actual settled phase,
independently of command intent. Nine regression cases and the full affected
viewer suite cover missing axes, retained intents and legacy pure-FW traces.
The failed replay's earlier derived view remains alongside its corrected version;
raw traces, aircraft movement and failed verdict are unchanged. The source/patch
manifest is `software-gates-s7-viewer-phase-axis-r1/review-manifest-r1.json`.

S7 remains open: actual adapter-process recovery, sustained neutral release,
full-rate active MC publication, both transition directions/mounts, standard VTOL,
abort/rescue/takeover and fresh explicit Starts still require evidence. VTOL live
admission stays closed. No QGC build, Pi deployment, push, tag or release follows
from this partial renewal.

### S7 adapter-process recovery harness

The ownership runner now has an explicit settled-VTOL-MC component contract and
one hash-bound `adapter_process_restart` case. It reuses the production binding,
commander, original-context reconciliation and normal-Stop path. It publishes
phase-safe baselines only; no tracker, target, automatic Start or production
restart service is introduced. Original A remains unresolved after its verified
process death. Read-only replacement registration cannot satisfy A's receipt;
old intent/handoff probes must refuse locally. A separate clean backend requires
an explicit new Start and its own original-token Hold receipt.

The report-owned launcher keeps PX4/Agent alive when A dies. It verifies exact
PID/start time, UID, binary, socket inode and Linux time namespace. Actual
source-derived Acquired state and a matching positive wire ACK must precede the
kill syscall; the unchanged intent expiry must extend past syscall return.
Already queued bytes remain nonretractable. Landing requires three distinct
progressing landed and pose publications within the existing 120 s deadline,
using the pinned detector's 1 s cadence plus 50 ms backup schedule. No force
disarm or `COM_MODE_ARM_CHK` write is permitted. Its actual value determines
whether armed replacement registration succeeds or is refused; one branch does
not qualify the other. Failed preparation stops only its independently verified
container even when logger stop fails, preserving the original error.

The first frozen tool candidate was not executed: independent review found
landing-cadence, preparation-cleanup and live-lease witness gaps. The corrected
`software-gates-s7-process-restart-r2/review-manifest-r2.json` passes 151 focused
checks, schema, Ruff, Python 3.10 syntax, shell and offline-plan checks. Python
syntax is not a 3.10 runtime claim for the diagnostic runner. Independent review
binds the final hashes and all three fixes. Actual crash/recovery, native ULog
timing and full application admission remain unqualified until the isolated run;
the coherent post-merge backend gate is next. No firmware, guidance, configuration,
hardware or live VTOL admission change accompanies these tools.

### S7 standard-VTOL release diagnostic and recovery preparation

The clean `d47835ee6` backend renewal passes 6,348 unit, 196 integration and
155 Phase 0 tests, plus API inventory, schema and critical lint. Eleven optional
GStreamer unit checks are skipped. Exact commands, source hashes and logs are in
`software-gates-s7-final-r3/results-r3.json`; this is not client or flight acceptance.

The actual `sihsim_standard_vtol` MC-to-FW capture reaches its original Hold
receipt and settled FW phase with 162 successful finite MC intents, no later
submission, 252 native publications and active publication gaps at most 36 ms.
Its maximum relative-altitude deviation is 1.987 m against the unchanged 2 m
gate. Independent ULog review matches the observed poses and finds no logger
dropouts. The short MC pursuit interval does not demonstrate interception;
post-release native Hold motion must not be attributed to follower commands.

**The capture remains provisional.** Archive admission correctly refuses because
`release_pending` remains true despite the genuine original Hold receipt. The
adapter used that flag both as a permanent old-pursuit fence and as unresolved
release status. The repair separates those meanings in the existing ownership
context and retains only exact original terminal proof. Native Hold alone or a
replacement owner cannot complete release. Contradictory active-owner evidence
is rejected; confirmed Hold requires a real activation after the original source
epoch. Valid pre-acquisition cancellation/expiry still supports zero activation.
Later stale state, disarm or a new owner cannot rewrite historical proof or
resume old pursuit. No new controller, timer, wire service or configuration is
introduced.

The rebuilt candidate passes 75 native, 75 ASan/UBSan and 35 packaging tests;
both malformed-proof regressions first fail against the earlier candidate.
Root's 326 backend/native-client/ownership/documentation checks pass. Exact
source, adapter and unchanged SDK/firmware pins are retained in
`software-gates-s7-release-receipt-r2/review-manifest-final-r2.json`.
Actual middleware scheduling and fresh archive acceptance still require a new
capture after independent source review and coherent full software renewal.

Raw `result.json.passed: true` is retained with its original component scope;
overall acceptance remains false. Evidence and the archive refusal are in
`s7-protocol3-standard-vtol-runtime-r3/`; the independent audit is
`software-gates-s7-standard-vtol-provisional-audit-r1/audit.json`.

Two restart preparations failed before arming or following: sidecars were queried
before startup, then unavailable aircraft data was parsed before its readiness
check. Exact-CID cleanup stopped both simulators and retained their raw logs.
Review subsequently caught a synthetic fixture accepting null where the healthy
native producer emits an empty diagnostic string. Report helpers are being
corrected against retained real replies, using the canonical client and recorder;
none of these preparation failures qualifies an actual adapter crash/restart.
No missing historical reply is reconstructed. The separate tailsitter altitude
failure, public/private settings and closed VTOL admission remain unchanged.

### S7 terminal-receipt renewal — actual standard VTOL

Local commit `c2e053dac` separates permanent pursuit termination from pending
release and retains exact original terminal proof. Its clean frozen renewal
passes 6,348 unit, 196 integration and 155 Phase 0 checks, schema, API inventory
and critical lint. Eleven optional GStreamer tests are skipped. The matching
adapter passes 75 native and 75 sanitizer checks; 35 packaging checks pass.
Sources, commands and hashes are in `software-gates-s7-final-r4/` and
`software-gates-s7-release-receipt-r2/`. No gains, firmware or saved profiles change.

Two explicit sessions then run on the same actual standard-VTOL simulator,
adapter and original independent world-target clock:

| Vertical mount, altitude guidance off | Original intent ACKs | Active native gap, including edges | Independent maximum altitude error | Component outcome |
| --- | ---: | ---: | ---: | --- |
| MC → FW | 161 | 52 ms | 1.890 m | control/response checks pass |
| Fresh FW Start → MC | 162 | 36 ms | 4.493 m | altitude failed, original 2 m gate retained |

Both sessions end on the first observed transition, confirm their own original
Hold receipt and publish no later pursuit. The second uses a different session,
connection and token; the first receipt cannot complete its release. One neutral
transition setpoint coincides with the second Hold epoch; its within-tick order
is not inferred. The second altitude excursion follows release, after its FW
pursuit altitude stays between 29.795 and 30.278 m. This observation does not
identify the cause or waive transition acceptance.

Fresh native Hold now reports `release_pending=false`, no active drain and an
empty drain-failure string. Strict archive admission, logger flush and exact-CID
stop succeed. Independent ULog review matches all 282/366 captured pose points,
verifies both timing bounds and finds no dropouts. The first capture also has a
0.618 s recording gap around release: its stricter complete-replay validator refuses
acceptance. Its 3D view therefore remains **Replay only**, with the independently
passed control checks reported separately; the gap stays visibly unknown. The
reverse view retains **Scenario failed**. Raw data and earlier derived views are
unchanged; this is not whole-VTOL or hardware acceptance.

Evidence: `s7-protocol3-standard-vtol-runtime-r4/`, its two
`visualization-reviewed-r2/` directories, and
`software-gates-s7-standard-vtol-actual-audit-r2/` (audit, comparison plot and CSV).
The former R3 capture remains provisional with its original archive refusal.

### S7 process-failure clock witness — open

The corrected report preparation now reaches stable airborne MC with actual
canonical replies. The R7 case verifies original A ownership and executes its
guarded SIGKILL, then refuses `ownership_restart_signal_clock_unqualified`.
The test incorrectly equates namespace-inode equality with clock-domain equality.
Container and host namespace IDs differ, but the original container offset and
boot identity were not captured; no retrospective time/lease proof is claimed.
Replacement registration, landing and the fresh backend session were not run.
The dead owner's release remains unresolved. Exact-CID cleanup flushes logging
and stops this simulator without inventing a receipt or sending a mode command.

The failed capture and 76,075,548-byte ULog remain in
`s7-process-restart-runtime-r7/`; the hash ledger is
`software-gates-s7-final-r4/process-restart-failed-runtime-retention-r1.json`.
The next fixture revision must prove the host/helper/original process monotonic
domain before the signal and retain it at the signal. Unknown or unequal domains
must refuse, with original timestamps and expiry unchanged. This is diagnostic
test infrastructure, not another flight-control deadline or recovery mechanism.

The prospective tooling now uses one shared read-only Linux clock reader and
validator. It retains kernel boot identity, namespace identities and raw
`timens_offsets`; equal monotonic offsets may qualify different namespaces.
Active and child namespace must match because the kernel exposes the child
namespace's offsets. Unknown or unequal domains refuse before SIGKILL; the
runner revalidates the signal evidence independently afterward. No timestamp
conversion, refreshed expiry or duplicated process-identity parser is added.
The existing PID/UID/start-time/binary owner still controls signaling; permitting
PID 1 as read-only clock evidence grants no signal permission.

The baseline first reproduces rejection occurring too late, after the mocked
signal. The repair passes 147 source and 143 report-helper checks; root's combined
ownership/vector/documentation renewal passes 373 checks. These overlap and are
not unique test totals. Candidate and preserved red/negative evidence are in
`software-gates-s7-process-restart-r8/review-manifest-final-r2.json`.
A fresh actual process-failure run remains required after coherent integration;
R7's missing clock data and failed verdict remain unchanged.

S7 stays open for both airframes' altitude failures and the remaining ownership,
transition, rescue/takeover and application checks. Hardware and VTOL admission
remain unchanged.

### S7 terminal recording repair — prospective captures

One shared recorder now projects the same final and five post-stop confirmation
packets before phase-settling capture resumes. It replaces the previous later
projection block, retaining original pose sample IDs/receipts, release and
publication cursors, independent target clock and grading window. Missing,
stale or duplicate pose does not become new movement evidence. Only a successful
publisher join and the original validated receipt permit inactive/no-command
markers; the existing Stop result is checked before normal release projection.
A cancellation-retaining real Commander task regression covers the false-join
case. No extra query, observer, publisher, timer or flight-control path is added.

A compact checked-in fixture preserves the six actual packets and relative
source provenance, so tests do not require local ignored reports. The old gap is
reproduced from those packets and disappears when future captures record them
through the shared path. Invalid proof, changed counters and missing/stale pose
remain refused or unknown. Older R3/R4 traces are not backfilled, their verdicts
are unchanged and complete-replay validation is not relaxed.

The reviewed candidate passes 283 focused and 74 Phase 0 checks, critical lint,
schema and Python 3.10 syntax. Root's combined clock/ownership/recording/viewer
renewal passes 430 checks, plus the four test-hygiene checks. These are overlapping
software scopes; an actual fresh capture remains required after the next full
coherent gate. Exact source, fixture, independent review and logs are in
`software-gates-s7-poststop-projection-r1/`.

### S7 combined renewal — recording and process loss

The clean frozen `952ff8950` renewal passes 6,348 unit, 196 integration and
155 Phase 0 checks, plus API inventory, schema and critical lint. Eleven optional
GStreamer checks are skipped. The 24 compiled native inputs and three pins still
match the reviewed adapter; no controller rebuild or tuning change is implied.
Exact commands, source correspondence and final results are retained in
`software-gates-s7-final-r5/`.

The fresh standard-VTOL MC→FW capture records all six actual terminal/post-stop
packets through the shared projection. The canonical reader now produces 742
timeline samples with 289 actual pose samples, no stale intervals and no flags.
This fixes future recording coverage without backfilling R4. Original Hold proof,
cleared release-pending and strict logger/archive shutdown are retained. The raw
flight verdict nevertheless fails: altitude deviation is 2.124 m against the
unchanged 2 m gate. R4's 1.890 m forward result is therefore not robust transition
qualification. Independent ULog review matches all 289 poses and 251 native MC
setpoints, verifies a 36 ms maximum active gap, and measures 2.123657 m altitude
error. New raw evidence is in `s7-protocol3-standard-vtol-runtime-r5/`; the audit
and browser-checked failed 3D replay are bound by
`software-gates-s7-standard-vtol-actual-audit-r3/review-manifest-r1.json`.

The R9 adapter-crash experiment reaches stable MC flight and proves equal raw
monotonic clock domains before and at the original process's SIGKILL. A matching
positive intent ACK retains 0.283 s of its original lease at the signal; expiry
and timestamps are not refreshed. Native PX4 then enters failsafe RTL. Replacement
B registers without acquisition, but the fixture wrongly demands healthy-flight
readiness for that passive registration and refuses. Land/disarm and a fresh
backend Start are not run. The old owner remains unresolved; exact-CID cleanup
flushes and stops the simulator without inventing Hold. R9 stays failed in
`s7-process-restart-runtime-r9/`. The next report-only correction must distinguish
passive registration from flight readiness, preserving all actual Start guards.

The R10 report-only correction passes 191 helper checks and independent review.
Its actual functional case passes: under observed `COM_MODE_ARM_CHK=1`, B
registers with no binding, acquisition or publication, then remains the same
adapter through normal landing and automatic disarm. A separate clean backend
creates a new token/activation and confirms its own Stop/Hold without reviving
A. Policy 0 and an explicit disarm command are not exercised. However, native
low-disk log rotation deletes the first closed flight ULog when the next takeoff
begins. Only the fresh-backend-C ULog remains; A/B/landing have raw wire, CLI,
process and clock evidence but no retained ULog corroboration. The raw functional
pass is not promoted to complete-evidence acceptance. R10 is retained in
`s7-process-restart-runtime-r10/`. The next capture must seal the closed first
log outside the logger-managed directory before rearming; native cleanup,
parameters and flight guards must remain unchanged.

The one native-only slower-transition contrast also remains failed. Source and
ULog evidence identify the early low-speed timeout at 6.59 s, not expiry of the
unchanged 15 s full timeout: selected CAS is 4.813 m/s, below the 6 m/s blend
threshold. No FW state or TECS dataset appears. The reported 0.288 m altitude
error covers only usable samples before rescue; the complete captured interval
includes native RTL toward its configured 60 m reference. It is not a full-flight
altitude bound and does not demonstrate a transport outage. Audit, source
references and plots are in
`software-gates-s7-xvert-duration10-actual-audit-r1/`. No setting is adopted.

All these simulators are stopped. The native Transition→Auto trajectory handover
is under causal review before any firmware change. S7, VTOL admission, S8's
unrestricted-speed capability and hardware qualification remain open. Public and
private defaults, QGC, installed services and remote repositories are unchanged.

### S7 ownership fixture — explicit airframe contract

Source review finds that replacement acquisition omitted the selected airframe
at both readiness and session construction, silently reverting to pure FW.
A control-flow regression reproduces rejection of a valid settled VTOL MC
replacement through the production validator. One selected contract now flows
through both boundaries and the retained manifest. A single declarative map
also admits explicitly observed settled VTOL FW; wrong kind, transition or
settled phase still refuses. Crash/restart remains explicitly MC-only.
The three baseline tests use the production binding; replacement tests retain
the original stale-owner rejection and separate acquisition identities.

Independent source review and 19 focused contract checks plus four hygiene
checks pass. Root's combined ownership/vector/clock/native-client/viewer/docs
renewal passes 576 checks; touched tool/test Ruff checks pass. The prior
236-check native-client/tool gate overlaps this scope.
Candidate, red/green evidence and review are in
`software-gates-s7-ownership-airframe-repair-r2/`. Full coherent renewal and actual
cases remain required; this is diagnostic-tool support, not a follower,
firmware, default or production-admission change.

### S7 resumed renewal — complete process-loss evidence

Clean frozen `582d3a89d` passes all six coherent gates: 6,348 unit, 196
integration and 155 Phase 0 checks, API inventory, schema and critical lint.
Eleven optional GStreamer checks remain skipped. The native adapter's 24
compiled inputs, three pins and 6,559 runtime entries still match the reviewed
bundle. Results and correspondence are in `software-gates-s7-final-r6/`.

The R11 process-loss capture passes its declared zero-command MC ownership
checks with both flight ULogs retained. Its reviewed, 224-check report helper
seals the original closed log outside PX4's managed directory before the next
arm; native cleanup, flight parameters and the original landing deadline are
unchanged. R11 deliberately uses the clean `952ff8950`/R5 source bound by its
review, not the later ownership-matrix repair. Raw R10 evidence and its missing
first log remain unchanged.

Independent native-log review confirms 87 acknowledged original intents, a
positive 0.276 s original command lease at SIGKILL, passive B registration with
no acquisition/publication, normal landing and automatic disarm, then 61
acknowledged intents from a distinct fresh backend session. That session's own
Hold receipt ends publication at 93, with five fresh inactive plateaus and a
36 ms maximum active gap. The original owner remains unresolved and cannot
adopt the new token. Both ULogs are readable with no dropouts or corruption;
the disarmed logging interval is shown as a gap, never interpolated.

After the intentional crash, native publication is silent for 1.344 s until
observed failsafe RTL removes the original owner. This is **not** a 100 ms
publication pass across the crash, a verified failsafe deadline, or evidence for
the separate camera Stop/lease timing gates. Only observed registration policy 1
and automatic disarm were exercised. Full application, tracking, transition,
policy-0 and hardware qualification remain separate. The stopped raw run is
`s7-process-restart-runtime-r11/`; hashes, independent audit and the actual-pose
plot are in `software-gates-s7-process-restart-r11/`.

The real native Transition→Auto replay separately reproduces all 199 retained
vertical reference updates. It isolates measured-acceleration initialization
when the prior requested acceleration is absent. A report-owned candidate
supplies the derivative of Transition's existing two-second velocity filter;
eight native component tests pass, while the unchanged baseline fails five
new-behavior checks. Other characterized outputs remain unchanged. This is
reference/component evidence, not an aircraft-response fix: a separately pinned
firmware build and actual comparisons under the original altitude/publication
gates remain required. The replay and candidate are in
`software-gates-s7-transition-handover-replay-r1/` and
`software-gates-s7-transition-acceleration-candidate-r1/`.

S7 and VTOL admission stay open. No candidate firmware, gain, saved profile,
QGC change or service has been deployed or published.

### S7 current diagnostics and native response

Canonical source `e312400a0` passes all six gates: **6,391 unit, 196 integration,
155 Phase 0**, inventory, schema and critical lint. Eleven optional GStreamer
checks are skipped. R10's unit stage completed successfully before its runner
exited 143 during integration. R11 retains that unit receipt and reruns only
unfinished stages after proving identical source bytes; the interrupted log and
failed aggregate remain intact. The earlier paired-flight sources
`e4b366d5e`/R8 and `fd57059a6`/R9 retain their separate green gates. The adapter's
24 compiled inputs and SDK are unchanged and hash-correlated with their retained
native build. No firmware is deployed or VTOL admission opened.

| Actual isolated ownership check | Observed result | Scope |
| --- | --- | --- |
| MC owner EOF | Own release; 36 ms active gap; 0.761 m altitude error | Declared component supported on its earlier frozen source |
| MC late cleanup/new acquisition | Old token cannot cancel replacement; both gaps 36 ms | Component supported; original outer archive failure retained |
| MC same-mode reselection R4 | 63 ACKs, zero refusals; 95 native publications; 36 ms gap; 0.785 m altitude error | Renewed component supported; old receipt remains immutable |
| Settled VTOL FW normal Stop R2 | 61/61 ACKs; 93 native publication pairs; 36 ms gap; 1.786469 m altitude error; own Hold and five inactive plateaus | Target-free ownership component supported under declared standard-SIH trim |
| Settled VTOL FW EOF R3 | 61/61 ACKs; 93 native pairs; 36 ms gap; 1.670288 m full-log altitude error; original expiry and own Hold | Target-free ownership component supported on frozen e4b/R8 |
| Settled VTOL FW replacement R3 | 130/131 ACKs; one terminal refusal; 95 original + 104 replacement pairs; 36 ms gaps; 1.685760 m altitude error | Timestamp-resolved checks supported; final old pair shares retirement timestamp, so sub-tick ordering remains unknown |
| Observe-to-intent phase exit | Both renewed forward cases retain the typed refused RPC and reconcile the original owner | Actual MC→FW race repair exercised; reverse-race fixture coverage remains separate |

The same-mode diagnostic repair `5fa1f35d9` does not rewrite the failed R3 run.
It verifies an independently newer pilot Hold without changing the old terminal
receipt or its deadline. The production repair `526775f60` retains socket
retirement and spends only the refused request's remaining deadline on fresh,
original-acquisition read-only evidence through the existing lifecycle. It does
not retry, reacquire, replay a command or infer phase from an error string.
Structured diagnostics distinguish an attempted/refused RPC from admission to
PX4. The 608 focused checks and independent 54-case review pass; both R6
forward runs report zero failed publications after their correlated refusal.
All four later R7 cases use ordinary observed-phase handling; they do not
re-exercise that refused-RPC path.

The renewed R7 pair uses the explicitly declared standard-SIH pitch-offset
profile (`FW_PSP_OFF=-2°`). It retains each original target clock across two
separately started sessions, own release receipts, five post-stop plateaus, no
later control RPC/publication, intact ULogs and stopped original containers.
Full-rate native altitude and both edges of the active-publication interval are
independently checked:

| Variant / direction | Altitude error | Maximum active gap | Recorded result |
| --- | --- | --- | --- |
| Baseline MC→FW | 1.920837 m | 36 ms | Component passed |
| Baseline FW→MC | 0.458923 m | 48 ms | Component passed |
| Candidate MC→FW | 1.724426 m | 36 ms | Component passed |
| Candidate FW→MC | 0.602600 m | 36 ms | Component passed |

The baseline reverse again seeds Auto from measured acceleration when the prior
requested value is absent: −1.966405 m/s². The candidate supplies Transition's
existing two-second filter derivative, and Auto inherits −0.009780 m/s² despite
measured −1.126868 m/s². First-four-second reference excursions are 0.270454 m
and 0.084297 m. Native effective parameter dictionaries are identical across
the pair, and closed-log outputs prove both consumed the declared −2° offset.
Entry pose/velocity still differ. The candidate's physical reverse altitude
error is **larger** in this pair, so reference consistency is demonstrated,
not overall aircraft improvement or firmware adoption. This is one vertical-
mount, target-altitude-off diagnostic pair, not repeatability or hardware proof.
All 269 original files remain unchanged. The earlier R6 candidate forward
failure at 2.001404 m remains failed in its separate retained audit; the original
R4 reverse's stronger stress and 4.493286 m error were not reproduced.

A separate native-only standard-VTOL hover→FW run also **fails**: full-rate
upward error **2.154724 m**, peaking 1.760 s after FW entry. All 5,920 poses through
log end are valid, ground truth confirms a 2.163208 m climb, and the native Hold
objective remains unchanged. There is no follower, external owner or external
publication; the external 100 ms gate is **unexercised**. Its hover entry differs
from preceding pursuit and cannot isolate the release's causal contribution.
The full source/parameter/closure audit verifies all 81 raw files unchanged.
One native-only standard-SIH −2° pitch-offset contrast then passes at 1.745911 m
full-rate error, with 1.744629 m ground-truth change from its independently
stamped entry. The only effective native parameter difference is pitch offset;
actual transition/TECS outputs independently prove its consumption. This
supports the targeted trim hypothesis, not calibrated trim or an installation
recommendation. The original failure remains. The tailsitter's distinct
zero-lift geometry must not inherit this offset; its native duration/open-loop
control remains failed at 7.257324 m descent. A separate threshold-10 contrast
proves native admission at 10.321 m/s and removes initial TECS underspeed, but
still fails at 7.303467 m descent. Ground truth independently confirms 7.262268 m.
The later nadir remains associated with roughly 52° bank. Neither threshold,
timing nor trim is adopted for the tailsitter. Review existing lateral,
attitude/rate and actuator evidence before another tuning trial.

Portable native functional builds now execute ten tests from fresh pinned
sources. The baseline compiles and links, then fails exactly six semantic
checks while four compatibility checks pass. The candidate passes all ten,
including high-speed handover through real PositionControl and saturation/
recovery. Both retain 15,086 unchanged source inputs, identical Ninja/compile
graphs and exactly 28 known generated files. Earlier configuration/link failures
remain separate failed attempts; they are not negative-control test evidence.
These are native component results, not flight-envelope or normal-CI acceptance.
The reviewed source change and functional regressions are now integrated in the
canonical PX4 patch series. Firmware deployment and VTOL admission remain closed.

The existing native builder now provides `--target px4-functional`, using the
same firmware authority/compiler pin, isolated copies and verified source-only
dependencies. It retains the expected failing comparison's real exit/XML and
requires the complete candidate to pass. Partial builds, missing/skipped cases,
changed inputs and unknown generated files refuse acceptance. Root renews
52 build/source tests, 74 API/reload checks, schema and critical lint. The new
command's actual compiler execution also passes the exact six-failure comparison
and ten-pass candidate. Both executables, characterization CSVs, Ninja graphs
and compile commands are byte-identical to their reviewed R5 counterparts.
The new inventory hashes all 16,434 recursive files: its 1,348 extra entries are
exactly the pinned submodule contents, with every old entry unchanged. Both
copies retain only 28 known generated outputs and the operator checkout remains
unchanged. See `native/README.md` for reproduction.

The separate FW Stop audit covers the complete airborne preparation/ownership/
closed-log interval, confirms actual −2° native consumption, all 61 positive
ACKs, matched 93 lateral/longitudinal publications, correlated original-owner
Hold and no later command/publication. This uses the frozen e4b/R8 source and
old firmware, not the new canonical controller build. It contains no target and
does not qualify pursuit, transition response, calibrated trim or hardware.

Existing tailsitter traces identify an initial heading-boundary defect: with
Hold yaw absent, ModeManager uses near-vertical FW-axis azimuth rather than
the native MC heading aligned with front-transition rotation. Reviewed patches
0006/0007 now encode this boundary and ten real-ModeManager functional cases.
Finite explicit yaw still wins. Invalid or unqualified fallback leaves the
incoming Navigator geometry intact; existing waypoint latch/reset is unchanged.
One declarative regression record reuses the existing builder, source authority,
dependencies and script. The default Transition regression remains unchanged.
Root renews 63 focused build/source tests, API/configuration checks, schema and
critical lint. Actual native execution compiles/links all ten cases: the control
has exactly five expected failures/five compatibility passes, and the candidate
passes ten. Independent audit verifies 31 inputs, seven derived artifacts,
unchanged operator source and only the intended production-source difference.
The matched control SIH firmware build is complete; candidate compilation and
actual heading/altitude response remain separate gates. Later 50° bank is native
orbit-capture feedback; neither the complete altitude loss nor its remedy is
established by the initial-heading finding.

Continue the native build verification and separate tailsitter performance investigation, then FW ownership,
abort/rescue/takeover, fault, mount and full-application matrix. Do not tune a
follower to conceal a native-only failure or relax the 2 m/100 ms gates.
The original report-owned replay remains historical evidence; the ten-test
fixture now lives in canonical patch 0004. VTOL admission stays closed.

The read-only entry point is
`reports/sitl/follower-consolidation-20261111/s7-review-r6/index.html`.
All four new 3D replays pass browser checks at 320, 400, 800 and 1440 pixels:
actual pose/target and command values, playback/scrub/reset, draggable 3D, correct
original verdicts, no overflow, page errors or external requests.
The review links the current native results and actual plots. Raw reports are
not modified.

Exact evidence under that run root:

- `software-gates-s7-final-r8/` and `software-gates-s7-final-r9/`;
- `software-gates-s7-final-r10/` and `software-gates-s7-final-r11/`;
- `software-gates-s7-canonical-native-r1/`;
- `software-gates-s7-ownership-matrix-r4/actual-r4-same-mode-audit-r1/`;
- `software-gates-s7-ownership-fw-normal-stop-actual-audit-r1/`;
- `software-gates-s7-ownership-fw-batch-actual-audit-r1/`;
- `software-gates-s7-heading-functional-actual-audit-r1/`;
- `software-gates-s7-transition-reverse-paired-actual-audit-r3/`;
- `software-gates-s7-standard-vtol-native-only-hover-actual-audit-r1/`;
- `software-gates-s7-standard-vtol-pitch-trim-actual-audit-r1/`;
- `software-gates-s7-xvert-threshold10-actual-audit-r1/`;
- `software-gates-s7-xvert-lateral-causal-review-r1/`;
- `../../native-guidance/transition-portable-native-20261112-r5/`;
- `software-gates-s7-replay-browser-r2/`.

Earlier failures, source-barrier and ANSI archive repairs retain their original
scope in the preceding history. No saved public/private defaults, hardware,
QGC, installed services or remote publication changed in this renewal.
