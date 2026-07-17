# 2026-07-17 PXE-0105 Beta Acceptance Closure Journal

- Resumed from the exact `eee45d5015789f4e96b0e023ccadd56502395927`
  branch baseline and reconciled the worktree, active public runtime, ignored
  config, credential hashes, schema retirements, and previous acceptance notes.
- Confirmed the public VPS was still running the older process
  `pixeagle_manual_95558dc9-da7a-48b1-8ba3-f3f82edd99dd`, not the beta
  candidate. Its logs reproduced the reported `Tracking is already active`
  rejection and pre-1.3.0 config-retirement errors.
- Removed the Classic active-target rejection. A new ROI now resets and replaces
  the target under the existing follower/model lifecycle barriers, including
  loss/retry state, and reports whether the operation was a retarget.
- Moved Smart HTTP selection to one async lifecycle owner, allowed a selected
  target to be replaced while Smart mode remains active, preserved the current
  target on a click miss, and kept target mutation blocked while Following is
  active.
- Added latest-click-wins queues for Classic and Smart canvas selection so rapid
  operator input cannot create overlapping mutations or leave an older queued
  click as the final target. Continuous selection is enabled by default and the
  default click ROI was reduced from 6% to 4% of the displayed video bounds.
- Hardened unknown tracker-mode and circuit-breaker UI states to fail closed,
  kept viewer sessions read-only, made SIH controls responsive, and fixed
  WebSocket reconnect/auth-close event ordering.
- Closed the final follower-state review blocker: startup, polling failure, and
  ambiguous status now remain unknown instead of becoming inactive. Start is
  shown only for explicit inactive state, while unknown/degraded-active state
  retains a defensive Stop path and truthful operator labels.
- Added responsive self-password and admin account management backed by one
  canonical atomic user store, session revocation, durable audit records,
  last-admin guards, bounded password verification/hash creation, and host-side
  recovery. Persisted create/update/delete/self-password operations now run in
  the threadpool rather than blocking FastAPI; current-password failures share
  the bounded attempt throttle and fail before mutation.
- Rechecked Offboard dry-run and startup: dry-run evaluates real preconditions,
  and circuit-breaker, replay, tracker, video, and target freshness are checked
  again inside the flight lifecycle immediately before and after Offboard mode
  entry.
- Removed two obsolete SmartTracker config keys through the versioned retirement
  registry, corrected active tracker docs to the canonical config hierarchy,
  prevented units on boolean schema fields, and regenerated the API/MCP
  governance inventory.
- Set the prerelease version consistently to `7.0.0-beta.1` across backend,
  dashboard, lock metadata, installer banner, API examples, and changelog.
- Passed the focused account/auth/store/CLI gate (`70` tests), focused
  follower/operator gate (`87` tests), complete dashboard gate (`52` suites,
  `336` tests, ESLint, and production build), Phase 0 (`473` tests), schema
  (`40` sections, `538` parameters), and the maintained non-hardware suite
  (`3338` passed, `47`
  environment-specific skips, `1` intentional deselection).
- The final bounded reviewer first returned `NO-GO` only for the two follower
  state and event-loop blockers above. The same reviewer inspected the repaired
  diff, reran both focused gates, and returned `GO` with no semaphore leak,
  audit regression, unsafe optimism, or unnecessary parallel subsystem. No
  further local review loop is planned absent a concrete gate or live failure.
- Public VPS refresh, exact config retirement, credential-preservation check,
  live Classic/Smart repeated-click acceptance, and clean-checkout release
  evidence remain the final steps before maintainer retest.
- Raspberry Pi, PX4/SIH/SITL/HIL, QGC, public WebRTC ICE/TURN, production TLS,
  field, autonomous follower response, and aircraft evidence remain separate
  gates and are not implied by this beta slice.
