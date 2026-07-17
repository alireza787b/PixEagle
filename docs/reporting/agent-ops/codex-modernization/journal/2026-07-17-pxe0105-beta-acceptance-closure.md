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
- Committed and pushed exact candidate
  `cb3fec14ab7579ee3c0ad51c8b14254686b46d6f`, then passed the
  dashboard-inclusive clean-checkout handoff (`26/26` commands) with clean
  initial/final checkout state, setup/profile and binary dry-runs, schema,
  minimum backend/API tests, fresh dashboard install, all `336` dashboard tests,
  and production build. The updater dry-run remained explicitly skipped while
  the owned public legacy runtime was active.
- Merged the reviewed branch normally to `main` at `da736ff8`, created annotated
  `v7.0.0-beta.1`, and published the first prerelease without rewriting history.
- Stopped only the owned legacy public run, preserved credential/config hashes,
  applied exactly `SmartTracker.SMART_TRACKER_COLOR` and
  `SmartTracker.SMART_TRACKER_HUD_STYLE` through authenticated config sync, and
  retained backup `config_20260717_141511_160518_u1fyog8t.yaml`. The backup hash
  matches the pre-sync config and the final status is zero actionable changes.
- Public beta.1 API, media, responsive browser, Classic retarget, and Smart
  repeated-click checks passed. Unified logs nevertheless exposed a real
  Classic first-measurement defect: cosine roundoff could produce confidence
  slightly above `1.0` and violate the tracker output contract.
- Normalized confidence at detector, smoothing, output, and legacy boundaries;
  finite epsilon overshoot clamps to `1.0`, while non-finite or materially
  invalid values fail closed. Focused confidence/output (`191`), broader
  tracker/detector (`343` passed, `40` skipped), Phase 0 (`473`), and
  version/docs (`116`) gates passed.
- Published corrective prerelease `v7.0.0-beta.2` at exact commit
  `985379841a8a64b98ca4890fb51fe4b964f1acf8`; beta.1 remains immutable and is
  labeled superseded in its GitHub release.
- Refreshed the public VPS to beta.2 run
  `pixeagle_manual_8b9b46da-877d-4112-91e2-dca3b521c100` with only
  `MainApp` and `Dashboard`. Runtime config, hashed user store, and private
  handoff hashes were identical before and after restart.
- Exact live identity, public/unauthenticated/wrong-Origin guards, MJPEG,
  WebSocket JPEG, Classic active retarget, two Smart override clicks, desktop
  and mobile overflow, browser console/page errors, cleanup state, and runtime
  logs passed. A discarded transient edge-target attempt produced two expected
  `no_detections` warnings; a bounded 100-sample detector probe and the central
  target UI pass justified no product patch.
- PXE-0105 is complete. The unchanged public URL and private credential are
  ready for maintainer acceptance; fresh Ubuntu and physical Raspberry Pi Core
  then Full/model evidence continue under PXE-0074.
- A final bounded independent evidence/claim/secret consistency review returned
  `GO` with no concrete blockers; no additional review loop was opened.
- Raspberry Pi, PX4/SIH/SITL/HIL, QGC, public WebRTC ICE/TURN, production TLS,
  field, autonomous follower response, and aircraft evidence remain separate
  gates and are not implied by this beta slice.
