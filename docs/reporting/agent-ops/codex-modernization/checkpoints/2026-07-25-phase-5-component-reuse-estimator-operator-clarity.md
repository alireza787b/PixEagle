# Phase 5 Checkpoint: Component Reuse, Estimator, And Operator Clarity

Date: 2026-07-25
Issues: PXE-0142; PXE-0143 deferred
Status: local gates passed; Ubuntu/Raspberry Pi/camera acceptance pending

## Problems

Guided repair could repeat expensive optional setup work even when the existing
component still met PixEagle's current contract. Config and dashboard
environment reset were separate choices. Classic estimator startup and
fixed-time assumptions could move the prediction marker away from the selected
target, while operator controls did not clearly distinguish confirmation,
Classic click assistance, and Smart model-task support.

## Changes

- Added source-owned installed-requirement verification and contract checks for
  Python/Core/AI, dlib, OpenCV/GStreamer, and dashboard dependencies.
- Reuse now requires the exact maintained version/capability contract.
  `PIXEAGLE_REBUILD_COMPONENTS` remains the single advanced explicit override.
- Made local config and dashboard environment reset one validated transaction
  with owner-only backups, rollback, and Config Sync provenance/audit updates.
- Seeded Kalman state at the selected measurement, used bounded monotonic frame
  time, reset estimator lifecycle with the tracker, and documented image axes.
- Kept measurement-free estimates visible for diagnosis/reacquisition but
  marked them stale and follower-ineligible in both Classic and Smart paths.
- Added `OperatorUI.REQUIRE_FOLLOW_START_CONFIRMATION`, default `true`, without
  weakening backend authorization, readiness, idempotency, or command safety.
- Renamed the optional Classic segmentor action to Selection Assist, exposed
  its typed runtime capability, and fail-closed the action when capability is
  unknown or Smart mode is active.
- Documented that SmartTracker currently accepts `detect` and `obb`. PXE-0143
  tracks a future normalized mask/polygon contract for `segment` models.

## Primary Files

- `scripts/lib/component_reuse.sh`
- `scripts/setup/verify-installed-requirements.py`
- `scripts/setup/reset-local-settings.py`
- `scripts/init.sh`
- `src/classes/config_service.py`
- `src/classes/estimators/kalman_estimator.py`
- `src/classes/trackers/base_tracker.py`
- `src/classes/trackers/kcf_kalman_tracker.py`
- `src/classes/tracking_state_manager.py`
- `src/classes/api_v1_snapshots.py`
- `dashboard/src/components/ActionButtons.js`
- `dashboard/src/hooks/useStatuses.js`
- `docs/trackers/03-ai-concepts/selection-assist-and-segmentation.md`

## Validation

- Setup/config/reuse suites: 352 passed, 1 expected optional skip
- Required API inventory and parameter reload: 73 passed
- Runtime/API focused suites: 169 passed
- Estimator/tracker/state suites: 221 passed
- Full backend: 3,577 passed, 48 expected skips
- Generated API candidate provenance: regenerated and 13 checks passed
- Dashboard full suite: 55 suites, 370 tests passed
- Dashboard post-review focused suite: 85 tests passed
- Dashboard production build: passed
- Schema: current, 39 sections and 517 parameters
- Bash syntax, ShellCheck, Python compile, and `git diff --check`: passed

The full backend run initially reported only stale generated API provenance.
Regenerating it with the maintained tool resolved all 13 inventory checks; no
runtime behavior test failed.

## Evidence Boundary

Local tests prove setup decisions, transactions, estimator direction/time
contracts, API state, and dashboard behavior. They do not prove target Ubuntu
upgrade/reset, Raspberry Pi performance, representative aerial reacquisition,
physical camera/gimbal, PX4, QGC, field, or aircraft behavior. Prediction
continuity remains bounded and diagnostic; no military-grade performance claim
is made.

## Next Gate

Publish this as beta.27, run the maintained update and explicit reset choices on
the Ubuntu acceptance host, then install the exact tag on Raspberry Pi and test
a representative camera. Record any target-host failure as a bounded follow-up
rather than expanding this local slice.
