# Phase 5 Checkpoint: Beta.4 Tracker Acceptance Readiness

**Date:** 2026-07-18  
**Slice:** PXE-0106  
**Status:** Code and schema gates passed; release and operator acceptance pending

## Why This Slice Exists

The beta.3 operator feedback still showed a point-click classic ROI that was
too small for reliable manual acquisition. The tracker review also found two
runtime correctness gaps: a manual retarget could leave the previous
template-matching identity in place, and template recovery selected the best
finite candidate without enforcing its configured threshold. A bounded review
of the exposed CSRT configuration found settings whose names did not map to
the runtime, plus unreachable feature-matching prototypes and four orphaned
configuration keys.

This slice intentionally fixes those concrete issues without replacing the
short-term tracker architecture or making an unsupported accuracy or
"military-grade" claim.

## Changes

- Point-click ROI default is now `0.08` in `dashboard/env_default.yaml` and the
  JavaScript fallback. A repository test keeps those authorities aligned; an
  operator drag remains the exact user-drawn ROI.
- Added `BaseDetector.initialize_target(frame, bbox)` as the explicit target
  identity contract with frame/ROI validation.
- `TemplateMatchingDetector` now replaces its image template, initial and
  adaptive appearance features, geometry, and score state on every explicit
  target selection. Invalid geometry is rejected before prior identity state
  is changed.
- Multi-scale template recovery now resets its observable score, rejects
  non-finite scores and thresholds, and applies method-aware threshold logic
  for normalized/raw correlation and square-difference methods.
- CSRT, KCF, and dlib start paths use the shared detector-target contract.
  CSRT schema names now map explicitly to runtime validation fields and
  OpenCV `filter_lr`; its appearance-update threshold is effective and its
  missing/unknown-mode fallback is the checked-in `robust` mode.
- Removed unreachable root-level detector prototypes and registered the four
  unused FeatureMatching/ORB/RANSAC settings for exact config retirement in
  schema `1.4.0`. Existing local configuration is not silently overwritten;
  the normal config-sync workflow owns migration and backups.
- Corrected detector/CSRT/configuration docs and generated schema descriptions,
  including constrained detector and template-method options.

## Validation

- Focused Python gate: **456 passed, 39 expected optional dlib skips**.
- Dashboard click/retarget test: **9 passed**.
- Generated schema: **40 sections, 534 active parameters**, check mode clean.
- Phase 0 API route/reload gate: **72 passed**. The maintained backend suite
  then passed **3,352 tests with 48 expected skips** after updating the
  intentional schema-version assertion from `1.3.0` to `1.4.0`.
- Isolated dashboard CI passed `npm ci`, **53 suites / 339 tests**, lint,
  production build, and `npm audit --omit=dev` with zero runtime
  vulnerabilities. The full audit's existing CRA dev-toolchain findings stay
  tracked as PXE-0021.
- Python compile checks for touched tracker/detector packages: passed.
- Bash syntax and ShellCheck passed for the touched setup/lifecycle scripts
  with only the repository-standard dynamic-source `SC1091` exclusion.
- `git diff --check`: passed.
- No delegated independent reviewer agent was available in this resumed
  context because the prior review-agent quota was exhausted. A bounded local
  review covered CV identity/recovery, fail-closed tracker behavior, config
  migration, UI default authority, and legacy cleanup. No independent GO is
  claimed; the broad release gates below are the next evidence boundary.

## Explicit Non-Claims / Deferred Debt

- No claim is made about long-duration tracking accuracy, occlusion/scale
  benchmark performance, real-aircraft following, PX4/SIH/SITL/HIL, or field
  operation. A later recorded-video benchmark must measure acquisition,
  retarget, loss, redetection, false reacquisition, and latency before any
  performance claim is published.
- Public-IP WebRTC remains PXE-0103 until an authenticated, bounded ICE/TURN
  design and remote receiver evidence exist. Non-local demo Auto remains
  WebSocket.
- The existing guarded SIH page is not the integrated PX4/MAVLink2REST/
  follower-training stack; that remains PXE-0102.

## Next Gate

Run the broad Phase 0/backend/dashboard gates, bump and publish `v7.0.0-beta.4`,
refresh the public VPS from the exact tag while preserving the operator config
and credential, and provide the operator a short retest checklist. Do not
start fresh Ubuntu installation until the beta.4 public retest passes.
