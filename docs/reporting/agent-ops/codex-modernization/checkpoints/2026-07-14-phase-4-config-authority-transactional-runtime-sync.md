# 2026-07-14 Phase 4 Configuration Authority And Transactional Runtime Sync

## Phase / Slice

- Phase 4 configuration, runtime-safety, setup, and operator-UX modernization
- Issue: PXE-0094 done
- Branch: `codex/modernization-pxe0040-runtime-20260604`
- Scope: exact schema authority, versioned defaults migration, transactional
  persistence/runtime publication, model-selection serialization, and
  cross-platform setup lifecycle

## Outcome

### Configuration authority

- `config_default.yaml` remains the checked-in value authority and the
  generated schema now preserves the exact nested `Safety.GlobalLimits`
  contract. Global limits are complete and strict; per-follower overrides are
  sparse and strict.
- `configs/config_retirements.yaml` is the only authority allowed to remove
  obsolete paths. Missing schema/default keys are not interpreted as obsolete,
  so plugin and extension keys survive defaults synchronization.
- Defaults synchronization now uses versioned contract v2 with exact structured
  paths and explicit `ADD_NEW`, `ADOPT_DEFAULT`, and `REMOVE_RETIRED`
  operations. It reports unknown extensions without exposing their values.
- Preview/apply uses an opaque HMAC token bound to the complete internal plan.
  The process-local secret and internal source fingerprints are not exposed;
  restarting the backend intentionally invalidates an uncommitted preview.
- The old config-sync helper was replaced by bounded config-sync and execution
  modules. Obsolete GStreamer adjustment keys, a shadowed detector threshold,
  the root boundary-margin alias, and the old archive container are retired
  only through the registry.

### Transactional persistence and runtime publication

- Config mutations serialize under the application follower-state barrier and
  the ConfigService process/file lock, snapshot every managed persistence
  artifact, persist before publishing runtime state, and restore both runtime
  and owned persistence artifacts on failure.
- Exact write receipts replace unsafe post-write ownership inference. Runtime
  config, sync metadata, audit log, and managed backup inventory writes perform
  a final digest precondition immediately before atomic replacement and return
  the digest of the bytes actually written.
- Rollback is conditional on those receipts. If a lock-ignoring external writer
  changes an artifact, PixEagle preserves the external bytes, reloads the
  observed disk/runtime state, fails closed, and reports operator recovery
  instead of overwriting the change.
- `Parameters`, `SafetyManager`, and follower configuration publish one coherent
  runtime generation through a shared reentrant barrier. Readers cannot observe
  a partially reloaded generation.
- Tracker-model replacement, SmartTracker lifecycle, smart-click target
  selection, and follower-sensitive model actions now share explicit barriers.
  Model switching rechecks the selected target after validation and fails
  closed if either required barrier is unavailable.
- Config import supports explicit merge or full replacement semantics and uses
  the same transaction, validation, audit, and rollback path as UI mutations.

### Setup and operator workflow

- Linux and Windows update paths preserve the earliest owner-controlled
  pre-update defaults file before changing the checkout. Initialization
  consumes it only after validating ownership, link/reparse-point safety, YAML
  integrity, and baseline lifecycle; failures retain it for recovery.
- Fresh setup standardizes on `.venv`. `PIXEAGLE_VENV_DIR` remains the explicit
  override and an existing legacy `venv` remains readable for upgraded
  installations. Linux and Windows launchers fail before opening service panes
  when no usable environment exists.
- The duplicate legacy OpenCV-GStreamer installer was removed. Active setup
  docs point to the maintained staged builder and runtime diagnostic path.
- The Settings defaults-sync UI consumes only contract v2, distinguishes new
  defaults, changed defaults, registered retirements, and preserved extensions,
  requires preview before apply, handles stale plans explicitly, and keeps
  sensitive values out of the response and browser state.
- Setup/update docs, clean-clone checks, schema provenance, and the production
  remote browser fixture were updated in the same slice.

## Files Changed

- Config/runtime core: `src/classes/config_service.py`,
  `src/classes/config_sync.py`, `src/classes/api_execution.py`,
  `src/classes/runtime_config_generation.py`, `src/classes/parameters.py`,
  `src/classes/safety_manager.py`, `src/classes/follower_config_manager.py`,
  and bounded API/model/controller helpers.
- Config/schema: `configs/config_default.yaml`,
  `configs/config_retirements.yaml`, `configs/config_schema.yaml`, and
  `scripts/generate_schema.py`.
- Setup: Linux/Windows installers, init/run launchers, shared sync helpers,
  `scripts/setup/config-sync-status.py`, CI, and setup lifecycle tests.
- Dashboard: defaults-sync hooks/dialog/import controls, Settings wiring,
  focused unit tests, and production remote browser coverage.
- Docs/tests: active configuration, installation, Windows, GStreamer, tracker,
  model, troubleshooting, API/MCP provenance, and regression suites.

## Validation

- Focused config/persistence/model/E2E regression selection: **210 passed**.
- Exact Phase 0 aggregate gate: **448 passed**, with one known
  Starlette/httpx deprecation warning.
- Complete maintained backend suite: **2760 passed**, **47 skipped**, **0
  failed** in 186.64 seconds. Skips cover optional dlib, native-Windows-only,
  and explicit SITL/runtime prerequisites.
- Dashboard: **30 suites / 181 tests**, lint, and production build passed.
- Generated schema: current at **40 sections / 548 parameters**.
- Generated API tool-candidate inventory: current; no new callable MCP surface.
- Python compile checks, shell syntax, ShellCheck, and `git diff --check` passed.
- The ignored live VPS config remained byte-identical during development:
  SHA-256 `88c3fc36e07b3942a41858f1bc227b708c72b7a964ba9f043052a18cb286ea9d`,
  mode `0600`, owner `alireza:alireza`, size 126661 bytes.

## Independent Review

The first adversarial review returned three P1 findings: post-write state reads
could misattribute external bytes to the transaction, malformed URL query
aliases could escape credential detection, and model switching could race
target selection. The implementation now uses exact write receipts and final
preconditions, decodes and checks malformed query keys plus scheme-less
userinfo, and serializes/rechecks model/target state. Focused regressions and
the complete suite passed after those repairs.

The final local completion audit then found three narrower gaps: SmartTracker
inference/target-loss and cancellation were outside the model barrier, a
post-replace permission/fsync failure could occur before ownership reached the
transaction (including the audit helper's exception path), and URL-fragment
credentials were not classified. Frame processing and cancellation now use the
same barrier; receipts publish immediately after `os.replace` and are recorded
in `finally`; fragment aliases use the same conservative secret classifier.
The final delegated re-review was attempted twice but exhausted the separate
subagent quota before returning a verdict. This checkpoint therefore does not
claim an independent final GO; it records the earlier independent findings,
the local line-level completion audit, regressions, and broad gates exactly.

## Evidence Boundary

- PixEagle's file lock is advisory. The write-receipt and final-precondition
  design narrows the external-writer race and prevents destructive rollback,
  but no portable filesystem primitive can provide atomic compare-and-swap
  against a process that deliberately ignores the managed lock. Direct edits
  to managed persistence files while PixEagle is running remain unsupported.
- Native Windows execution is delegated to the new Windows CI job; this VPS did
  not execute PowerShell ACL behavior or a Windows launcher.
- Optional dlib, target OpenCV-GStreamer, QGC playback/recording on the new head,
  public-demo migration, PX4/SITL/SIH/HIL, target hardware, field operation, and
  real-aircraft safety are not claimed by this checkpoint.

## Next Slice

1. Commit and push this reviewed PixEagle source checkpoint.
2. Apply the reviewed config-sync plan to the ignored VPS config, restart only
   from the pinned commit while preserving the current tester password, and
   probe dashboard/auth/HTTP MJPEG/WebSocket JPEG/log boundaries.
3. Complete exact QGC CI for the source-EOS recording-finalization repair,
   promote only a green development head to the PR branch with
   force-with-lease, and verify a fresh Windows installer. Keep PR #13594
   draft until receiver testing accepts that exact artifact.
4. Publish the public-VPS tester handoff and monitor logs during user tests.
5. Rerun the clean temporary setup/update walkthrough on the eventual release
   candidate and capture fresh Raspberry Pi/target evidence before tagging.
