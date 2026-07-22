# Phase 5 Checkpoint: Target Freshness And Preview Contract

- Date: 2026-07-22
- Issue: PXE-0130
- Status: yaw fix verified; bounded Smart selection snapshot under validation
- Scope: target reselection, tracker recovery, follower command freshness,
  circuit breaker, and local command preview

## Operator Finding

Rapid target changes were not reliably immediate, target-loss recovery and
command eligibility were evaluated through more than one local rule, and two
additional safety-bypass concepts competed with the final circuit breaker. This
made it possible for UI state, tracker state, and follower intent to disagree.

## Resulting Contract

1. Tracker recovery is allowed to continue through a bounded period of
   prediction, redetection, or association.
2. Prediction-only and stale output stays visible for diagnosis but cannot drive
   normal pursuit commands.
3. Each provider owns its measurement-age policy. One shared evaluator
   normalizes the explicit output contract for every follower.
4. The exact classic output returned by an update is the sample that is checked;
   the controller does not fetch a second, racing sample.
5. The circuit breaker is the one final PX4 command inhibitor.
   `COMMAND_PREVIEW` is a separate non-network sink for local follower math, not
   another way to bypass the real command boundary.
6. Rapid Smart selections are ordered before asynchronous flight-loop work, and
   only the newest request may change the active target.
7. A recent displayed Smart detection may remain selectable across a transient
   empty detector frame for a schema-owned `0.75 s` window. That snapshot is
   operator-input-only: it is tentative and cannot authorize follower commands
   until a current detector measurement confirms it.

## Files Changed

- Tracker/runtime: `src/classes/tracker_runtime_status.py`,
  `src/classes/app_controller.py`, `src/classes/smart_tracker.py`,
  `src/classes/tracking_state_manager.py`, detection adapters/backends.
- Preview/safety: `src/classes/command_preview.py`,
  `src/classes/following_readiness.py`, follower and PX4 command paths, typed and
  legacy API contracts.
- Dashboard: click selection, circuit-breaker/preview status, and raw preview
  intent rendering.
- Config/docs/tests: retired duplicate flags, regenerated schema/tool inventory,
  architecture docs, and focused controller/tracker/UI regression tests.

## Validation

- Freshness/controller: `163 passed`.
- Classic, Smart, gimbal, frame freshness, and tracker-in-loop: `177 passed`.
- Combined affected regression: `728 passed`.
- Post-cleanup Smart/freshness/base-follower/gimbal/controller gate:
  `250 passed`.
- A complete backend run collected 3516 tests and reached `3467 passed, 48
  skipped, 1 failed`; the only failure was a stale schema-version test literal.
  After replacing that literal with the generator's version authority, the
  focused generator/follower/tracker gate passed `115`. Exact-commit CI is the
  final clean full-suite gate.
- Required API/reload gate: `72 passed`.
- Schema: 38 sections / 537 parameters, no drift.
- Dashboard: 54 suites / 358 tests passed; production build passed.
- API tool-candidate inventory, Python syntax/import checks, and
  `git diff --check` passed.
- Three optional read-only reviewers returned no result before the bounded
  cutoff and were closed; no independent-review approval is claimed.
- Exact-commit CI and exact VPS replay gates for the initial contract passed;
  the final Smart selection-latency follow-up remains pending.

## Exact-Commit And VPS Follow-Up

- GitHub Actions run `29899085884` passed every job for commit `ea38783d`,
  including the complete backend, dashboard, integration, Windows setup,
  schema, and shell gates.
- The exact commit was reconciled onto the authorized lab VPS. Config Sync
  transactionally added the two Smart selection tolerances and removed the two
  registered safety bypasses; the post-report was `0 new, 0 changed, 0
  retirements, 0 extensions`.
- Live Classic start and immediate retarget both returned success, and measured
  output became follower-usable. A prediction-only target correctly blocked
  preview start; a measured target enabled preview while confirming no PX4
  publication.
- This probe exposed one independent unit-boundary defect in
  `mc_velocity_position`: its rad/s PID output entered the deg/s yaw smoother,
  so the configured deadzone suppressed valid yaw. The boundary now converts
  once before smoothing, and an enabled-smoother regression is included.
- Follow-up local gates passed: affected tracker/follower/controller `261`,
  required API/reload `72`, schema 38/537, compile, and diff checks. GitHub run
  `29901393065` then passed every job for `e0e66f2c`. The exact VPS replay
  produced accepted MC Velocity Position intents with yaw reaching
  `-4.3225 deg/s`, while both API truth and the preview commander reported
  `commands_sent_to_px4=false`; stop actions completed successfully.
- A subsequent live Smart probe reproduced the operator's intermittent first-
  click failure: API telemetry exposed one fresh OBB detection, the next frame
  was empty, and the click saw no detector rows. SmartTracker now retains only
  the latest non-empty selection snapshot for the schema-owned age bound.
  Cached selections are explicitly tentative, model changes clear the snapshot,
  and normal target freshness remains unchanged. Direct Smart-click `32`,
  combined Smart/freshness/reacquisition `283`, API/reload `72`, docs `31`,
  schema 38/538, compile, and diff gates pass. Current exact-commit CI and VPS
  first-click replay remain pending.

## Claim Boundary

These results prove local software contracts. They do not prove detector quality
on a particular aerial scene, Raspberry Pi throughput, RTSP/GStreamer timing,
external gimbal packet behavior, MAVLink routing, PX4 response, SITL/HIL,
aircraft behavior, or field safety.

## Next Gate

1. Pass exact-commit CI and repeat the VPS Smart first-click/reselection probe.
2. Complete maintainer browser testing for Classic and Smart/AI selection.
3. Keep Raspberry Pi, camera/gimbal, PX4, and field acceptance separate.
