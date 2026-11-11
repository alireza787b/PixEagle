# Follower consolidation checkpoint

Plan: [MC/FW/VTOL consolidation](../../../../followers/05-development/follower-consolidation-plan.md).
Baseline: PixEagle `50bb2f763`; QGC implementation worktree `c7cfdfa13`.
Hardware, installed services and local saved/private configuration are untouched.

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
