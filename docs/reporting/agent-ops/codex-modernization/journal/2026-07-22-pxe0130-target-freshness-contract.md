# PXE-0130 Target Freshness Contract

- Date: 2026-07-22
- Phase: 5
- Status: selection race live-proven; class continuity locally verified

## Trigger

Operator tests showed that reacquisition clicks could be delayed or rejected,
preview intent could remain zero or be obscured by telemetry, and the meaning of
the circuit breaker, calculation bypasses, target loss, prediction, and stale
output had become difficult to reason about. The controller also had separate
freshness checks for classic updates and follower dispatch.

## Decision

PixEagle now separates two concerns:

1. Trackers may retain a lost target internally for bounded prediction,
   visualization, association, and reacquisition.
2. Followers may use normal pursuit math only from an explicitly measured,
   active, non-stale output marked usable by its source.

`evaluate_tracker_command_freshness()` is the one controller-side normalizer for
classic, Smart/AI, and external tracker outputs. Sources retain their own timing
and loss policies because frame age, detector cadence, and external gimbal
packet age are different clocks. No second universal timeout was added.

The final circuit breaker remains the last command boundary. Local follower
testing uses `COMMAND_PREVIEW`, whose controller has no MAVSDK/PX4 publisher.
Preview may skip the operational flight envelope so it can expose raw follower
intent, but it still requires current measured tracker input and finite,
schema-valid command fields.

Operator click timing is a separate observation-selection concern. SmartTracker
keeps one time-bounded non-empty detection snapshot so a box already delivered
to the browser is not erased by one empty inference frame before its click
arrives. A cached selection is tentative and remains ineligible for follower
use until a current measured frame confirms it. This follows the timestamped,
bounded observation-cache pattern used by ROS message filters without making
the cache a control-authoritative source:
<https://docs.ros.org/en/ros2_packages/rolling/api/message_filters/doc/Tutorials/Cache-Python.html>.

## Implementation

- Normalized bool-like provider metadata and made prediction-only output stale
  even if a provider accidentally claims it is usable.
- Reused the output from the same classic update call instead of re-reading a
  potentially newer tracker sample.
- Canonicalized inactive external output before passing it to followers that
  explicitly implement a target-loss response.
- Preserved bounded classic/Smart recovery and overlays while blocking normal
  pursuit on prediction-only or stale data.
- Ordered rapid Smart selections and bounded click fallback to stable tracks so
  the newest operator request wins without global tracker shutdown.
- Removed the active duplicate safety-bypass flags/routes and exposed raw local
  preview intent separately from stale vehicle telemetry.

## Evidence Review

The contract matches two established patterns. NVIDIA DeepStream retains targets
in shadow tracking for bounded recovery but does not report unreliable shadow
data as normal downstream output. ByteTrack recovers occluded targets through
association rather than terminating on one weak detection. PX4 independently
applies an Offboard proof-of-life timeout and configured failsafe action; visual
recovery state is not a substitute for a current command source.

- <https://docs.nvidia.com/metropolis/deepstream/dev-guide/text/DS_plugin_gst-nvtracker.html>
- <https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136820001.pdf>
- <https://docs.px4.io/main/en/flight_modes/offboard>

## Local Validation

- Shared freshness/controller suite: `163 passed`.
- Classic, Smart, gimbal, frame-freshness, and tracker-in-loop suite:
  `177 passed`.
- Combined affected regression before final cleanup: `728 passed`.
- Post-cleanup Smart/freshness/base-follower/gimbal/controller suite:
  `250 passed`.
- The complete backend run collected 3516 tests and reached `3467 passed, 48
  skipped, 1 failed`; the sole failure was a stale test literal expecting
  schema `1.4.0` after the intentional `1.5.0` migration. The test now imports
  the generator's schema-version authority. Post-fix generator/follower/tracker
  regression passed `115`; the exact-commit CI run remains the final clean
  full-suite evidence.
- Required API route/reload gate: `72 passed`.
- Config/schema gate: 38 sections / 537 parameters, no drift.
- Dashboard: 54 suites / 358 tests passed; production build passed.
- API tool-candidate inventory, Python compile, and `git diff --check` passed.

Three optional read-only review tasks did not return a result within the
bounded review window and were closed. No reviewer approval is claimed or used
as evidence for this checkpoint.

## Exact-Commit And VPS Follow-Up

- GitHub Actions run `29899085884` passed all jobs for `ea38783d`.
- The authorized VPS was updated to that exact clean commit. The guarded Config
  Sync workflow adopted the two Smart tolerance defaults and removed the two
  registered safety bypass keys, leaving zero actionable config operations.
- Live Classic start/reselection and measured/prediction-only freshness gates
  behaved as designed. Command Preview started only on measured output and
  retained `commands_sent_to_px4=false`.
- The live preview exposed an existing MC Velocity Position unit mismatch:
  rad/s PID output was compared with deg/s smoothing thresholds. The follower
  now converts the bounded PID result once before smoothing and writes the
  resulting deg/s value directly to its typed command field. A real enabled-
  smoother regression prevents recurrence.
- Follow-up local validation passed: affected tracker/follower/controller `261`,
  required API/reload `72`, schema 38/537, Python compile, and diff checks.
  GitHub run `29901393065` passed all jobs for `e0e66f2c`. The exact VPS then
  accepted nonzero yaw preview intents up to `-4.3225 deg/s`, retained
  `commands_sent_to_px4=false`, and stopped preview/tracking cleanly.
- The live Smart follow-up found a producer/selection race: a fresh OBB target
  was visible through telemetry but an immediately following empty inference
  frame cleared `last_detections` before the click. The first click failed and
  the second succeeded. A schema-owned `0.75 s` latest-non-empty selection
  snapshot now absorbs that UI/stream latency. Cached selection is tentative,
  expiry is fail-closed, and model changes clear it. Direct `32`, combined
  Smart/freshness/reacquisition `283`, API/reload `72`, docs `31`, schema
  38/538, compile, and diff gates pass. Exact-commit CI and VPS replay of this
  final follow-up remain pending.
- Exact `8cb96f7e` VPS evidence reproduced a fresh-to-empty detector transition
  in `0.031 s`; first selection and immediate reselection both succeeded from
  the bounded snapshot at `0.272 s` and `0.280 s`. Both were correctly marked
  as requiring current-measurement confirmation. The same replay exposed an
  independent OBB continuity defect: unstable detector ID `-1` plus class-label
  flicker prevented a strongly overlapping observation from entering class
  history. The common tracking-state manager now permits a cross-class match
  only for an unstable selected ID, within the normal short-loss window, and at
  the primary spatial-IoU threshold against the unexpanded reference. A
  compatible-class candidate has priority. Long-loss, lenient-IoU, distance,
  and appearance recovery remain class-gated. Provisional class-flicker matches
  do not enter trusted class history or appearance memory, and a follow-on
  regression proves they cannot authorize a weaker or long-loss match. The
  tracker gate passes `406` with `40` optional dlib skips; follower/control
  freshness passes `208`; API/reload passes `72`; docs pass `31`; schema 38/538,
  compile, and diff checks pass. Exact-commit CI and VPS measured-confirmation
  replay are pending.
- GitHub run `29902656465` passed all jobs for cached-selection commit
  `8cb96f7e`. A bounded independent re-review of the follow-up continuity diff
  returned `GO` after `89` focused tests plus compile/diff checks and found no
  release blocker; current exact-commit CI remains pending.
- A bounded aerial review found that Smart's Kalman transition and several
  recovery horizons remain frame-count based. Command eligibility is still
  measurement-aware and fail-closed, but cadence-independent tracking quality
  is not proven. PXE-0131 records the monotonic-time migration and 5/15/30 FPS,
  dropped-frame, small-target, ego-motion, turn, scale, occlusion, crossing, and
  distractor benchmark gate instead of expanding this fix with speculative
  thresholds.

## Open Evidence

- Exact-commit CI and VPS proof that a cached Smart click survives one transient
  empty detector frame and transitions to current measured output through the
  bounded unstable-ID/class-flicker association rule.
- Maintainer browser proof for Classic and Smart/AI measured/lost/reacquired
  selection behavior.
- Time-aware Smart recovery and representative aerial-video acceptance tracked
  by PXE-0131.
- Raspberry Pi, real RTSP camera, Topotek gimbal, routed PX4, SITL/HIL, and field
  acceptance. None is implied by the local results.
