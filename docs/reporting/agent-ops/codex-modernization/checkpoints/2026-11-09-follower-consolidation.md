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

## Next — S2

Generalize exact nested ConfigService/Config Sync paths, preserve sparse override
absence and transactional preview/apply/rollback, then retire the three confirmed
inert GM Chase settings. Use the existing service and migration store.
