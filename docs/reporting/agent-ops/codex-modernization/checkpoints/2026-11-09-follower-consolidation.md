# Follower consolidation checkpoint

Plan: [MC/FW/VTOL consolidation](../../../../followers/05-development/follower-consolidation-plan.md).
Baseline: PixEagle `50bb2f763`; QGC implementation worktree `c7cfdfa13`.
Hardware, installed services and local saved/private configuration are untouched.

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
