# Phase 5 Checkpoint: Gimbal Live-Switch Lifecycle

Date: 2026-07-23
Issue: PXE-0139
Status: local implementation complete; physical provider acceptance pending

## Problem

The startup path began background monitoring for external trackers, but the live
tracker-switch path only constructed the new object. A live switch to Gimbal
therefore left `monitoring_active` false. Its update returned no output on every
video frame, which both hid angle telemetry and flooded the always-reporting
loop with warnings.

The Settings page also exposed `Tracking.DEFAULT_TRACKING_ALGORITHM` as free
text without explaining that it is the saved startup/restart default rather
than the live tracker selector.

## Changes

- Centralized external tracker provider activation in AppController and reused
  it for application startup, live switch, and switch rollback.
- Publish switch success only after the external tracker confirms monitoring is
  active.
- Stop a failed tracker before restoring the previous implementation.
- Return structured inactive Gimbal output when monitoring has not started,
  avoiding null-output warning loops while preserving fail-closed following.
- Generate the saved tracker-default dropdown from the selectable factory
  entries in `configs/tracker_schemas.yaml`.
- Documented the saved default, process-only live selection, provider startup,
  and real-hardware troubleshooting boundaries.

## Validation

- Gimbal tracker: 33 passed.
- AppController safety/lifecycle and generated schema: 220 passed.
- Tracker API, telemetry, route inventory, and parameter reload: 112 passed.
- Gimbal provider and tracker factory: 29 passed, 2 optional-backend skips.
- Selected docs, tracker/follower contract, and config-service checks:
  47 passed.
- Dashboard Settings editor: 20 passed.
- Generated schema: current, 38 sections and 513 parameters.
- Python compile, focused Flake8 fatal checks, diff check, and dashboard
  production build: passed.

One bounded independent review found a failed-rollback cleanup/reporting gap and
a missing catalog-to-factory drift guard. The rollback now cleans partial
external state and reports `rollback_restored`, `rollback_error`, and the
actual active tracker; schema tests require catalog keys to match the runtime
factory registry. Both findings are closed.

## Evidence Boundary

Software tests can prove lifecycle ordering, rollback, structured state, and
schema consistency. They cannot prove UDP routing, camera firmware behavior,
angle conventions, physical gimbal cadence, compatible followers, PX4, or
field operation.

## Next Gate

Update the Ubuntu host to the exact pushed commit, select Gimbal Tracker while
the RTSP stream is running, and confirm that valid Topotek packets produce
yaw/pitch/roll telemetry without warning floods. Test a gimbal follower only
after angle direction, mount configuration, freshness, and tracking status are
observed and recorded.
