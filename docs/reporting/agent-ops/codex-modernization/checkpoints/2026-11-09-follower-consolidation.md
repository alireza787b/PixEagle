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

## Next — S3

Remove class/profile-name coupling at the strategy boundary, preserve command
shaping/reset behavior, and converge live admission in the flight owner.
