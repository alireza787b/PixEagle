# Phase 5 v7 Beta Acceptance Readiness

Date: 2026-07-17

Issues: PXE-0105, PXE-0074

Source baseline: `eee45d5015789f4e96b0e023ccadd56502395927`

Release commit: `985379841a8a64b98ca4890fb51fe4b964f1acf8`

Status: complete for the bounded public VPS/browser beta gate; fresh Ubuntu,
physical Raspberry Pi, production deployment, and flight/simulation evidence
remain separate PXE-0074 and domain gates

## Scope

This slice closes the concrete defects found during the maintainer's public VPS
browser check and the final release review. `7.0.0-beta.1` was merged, tagged,
published, and exercised on the public VPS. That run exposed one bounded defect:
floating-point cosine roundoff could put Classic confidence slightly above
`1.0` and invalidate the first measurement. The detector/tracker contract now
normalizes finite epsilon overshoot and fails closed for materially invalid or
non-finite values in `7.0.0-beta.2`.

The owned historical process was stopped, exactly two registered SmartTracker
keys were retired through authenticated config sync, and the generated backup
matches the pre-retirement config byte for byte. The public process now runs the
exact clean beta.2 commit with only `MainApp` and `Dashboard`; credentials and
the post-sync runtime config were unchanged across the beta.2 restart.

## Behavior Closed

### Tracker selection

- Classic target selection no longer rejects an active or recovering tracker.
  The controller advances the tracking generation, clears retry/failure state,
  resets the tracker, and starts the replacement ROI under one lifecycle/model
  barrier.
- Smart browser selection uses one async lifecycle owner instead of acquiring
  the follower barrier twice. A click can replace the current Smart target while
  Smart mode remains active; a click miss does not falsely confirm or erase the
  previous target.
- Both canvas paths serialize requests and retain only the newest pending click.
  Continuous selection remains armed by default, including after a successful
  selection. The default point-click ROI is 4% instead of 6%.
- Classic selection is unavailable while Smart mode is active; Smart selection
  is unavailable while Following is active. Viewer sessions and unknown mode
  state remain read-only/fail-closed.

### Flight-adjacent safety

- Offboard dry-run now executes the same circuit-breaker, replay, and target
  readiness preflight as execution without starting PX4.
- The controller rechecks circuit-breaker state before connection and rechecks
  target/video/replay readiness immediately before and after Offboard entry.
- The follower circuit breaker remains a PX4 command-dispatch inhibit. It is not
  presented as a preview simulator and cannot be used to bypass target
  freshness or command safety.
- No PX4 connection, mode transition, SIH/SITL/HIL, follower command, field, or
  real-aircraft operation was run in this slice.

### Operator surface and media

- Unknown Smart mode no longer defaults to Classic. Mode, target, and redetect
  actions remain blocked until the typed runtime state is known.
- Circuit-breaker polling failure clears stale live status instead of leaving a
  misleading green command state.
- Following state is tri-state at the operator boundary. Poll startup/failure or
  ambiguous payloads display `Unknown`, never expose Start, and retain the
  defensive Stop action; an explicit active state remains visible even when its
  health status is degraded.
- Browser account controls support self-password change and responsive admin
  create/update/disable/delete flows with explicit role and last-admin guards.
- WebSocket video reconnects after clean non-auth closure, deduplicates retry,
  and treats authorization closure as terminal regardless of browser event
  ordering.
- Remote Auto streaming uses WebSocket unless a reviewed remote ICE path is
  explicitly available. Manual WebRTC still reports bounded failure guidance;
  public HTTP/IP WebRTC media acceptance remains PXE-0103.

### Configuration, setup, and governance

- `SmartTracker.SMART_TRACKER_COLOR` and
  `SmartTracker.SMART_TRACKER_HUD_STYLE` are explicit versioned retirements;
  their runtime/schema/docs metadata is removed rather than retained as hidden
  compatibility behavior.
- Active tracker docs use `Tracking.DEFAULT_TRACKING_ALGORITHM` and
  `SmartTracker.SMART_TRACKER_ENABLED`; a static guard prevents registered
  retirement names or invalid hierarchy from returning to active docs.
- Boolean schema parameters cannot receive inferred units.
- Browser password verification/hash creation shares one bounded process-local
  capacity gate. Login, account creation/reset, and self-password changes cannot
  overlap expensive password work; persisted account mutations run off the
  async event loop, and failed current-password attempts are throttled before
  mutation.
- API account routes are typed, CSRF-protected, audit-recorded, and explicitly
  blocked from MCP promotion. Generated disposition dates and inventory are
  current.
- Backend, dashboard package metadata, lock metadata, installer banner, API
  samples, and changelog all identify `7.0.0-beta.2`; beta.1 remains preserved
  and visibly marked as superseded in GitHub release history.

## Validation

- focused account/auth/store/CLI gate: `70/70` tests passed
- focused follower-state/operator gate: `87/87` tests passed
- dashboard: `52/52` suites and `336/336` tests passed
- dashboard ESLint: passed
- dashboard production build: passed
- schema: `40` sections and `538` parameters, current
- Phase 0: `473/473` tests passed
- maintained non-hardware/non-SITL suite: `3338` passed, `47` skipped for
  unavailable dlib/native Windows/cross-UID contracts, `1` deselected by marker
- Python compilation for touched runtime/setup modules: passed
- Bash syntax for `scripts/init.sh`: passed
- `git diff --check`: passed
- focused beta.2 confidence and output gate: `191/191` tests passed
- broader tracker/detector gate: `343` passed, `40` environment-specific skips
- beta.2 Phase 0 rerun: `473/473` tests passed
- beta.2 version/docs focused gate: `116/116` tests passed

The one Phase 0 rerun failure was a repository test-hygiene guard rejecting an
`append(...) or True` callback shorthand in a new auth test. It was replaced by
an explicit callback; the focused `56` tests and the complete Phase 0 rerun then
passed. It was not a runtime bypass or waived failure.

The final bounded reviewer initially returned `NO-GO` for two concrete release
blockers: unknown Following telemetry was rendered as inactive and could replace
Stop with Start, and persisted account/password work could run synchronously on
the FastAPI event loop. After the repairs above, the same reviewer inspected the
actual diff, reran the `87` frontend and `70` auth/store/CLI tests, found no
semaphore leak, audit regression, optimistic state, or parallel subsystem, and
returned `GO`. This closes that review scope; dependency warnings and target-host
evidence remain tracked gates rather than reasons for another local review loop.

Exact candidate `cb3fec14ab7579ee3c0ad51c8b14254686b46d6f` was pushed and
then passed the dashboard-inclusive clean-checkout handoff with `26/26` required
commands. The temporary checkout was clean before and after setup/profile
dry-runs, the binary download plan, schema and minimum backend/API checks, fresh
`npm ci`, all `336` dashboard tests, and the production build. Evidence is in
`docs/reporting/agent-ops/codex-modernization/evidence/2026-07-17-pxe0105-cb3fec14-beta-handoff/manifest.json`.
The stopped-runtime updater dry-run was explicitly skipped because the owned
public legacy demo was still active; its fail-closed runtime ownership policy was
not bypassed.

## Release And Live Acceptance Result

1. The reviewed candidate was merged normally to `main`; annotated tags and
   GitHub prereleases preserve both beta.1 and beta.2 history. No force push,
   tag move, or history rewrite was used.
2. Public run `pixeagle_manual_8b9b46da-877d-4112-91e2-dca3b521c100`
   reports healthy and ready with expected components `Dashboard,MainApp`.
   Typed About reports `7.0.0-beta.2`, full commit `98537984...`, branch
   `main`, and `dirty=false`.
3. Dashboard returned `200`; unauthenticated About returned `401`; an
   untrusted Origin returned `403`; authenticated login and About returned
   `200`.
4. Anonymous lab media returned a valid multipart MJPEG frame and WebSocket
   frame metadata followed by valid JPEG bytes. Browser Auto resolved to
   `Video: WebSocket / Remote`, as required for public HTTP while PXE-0103 is
   deferred.
5. Classic first selection succeeded and a second active selection returned
   `retargeted=true` with tracking active before and after. Two Smart UI clicks
   returned `override_applied` and retained an active selected target.
6. Desktop `1440px`, mobile dashboard `390px`, and mobile Settings `390px`
   had no horizontal page overflow; browser console and page errors were empty.
   Cleanup restored Classic mode with tracking and following inactive.
7. The beta.2 run log contains zero confidence-boundary errors, active-tracking
   lifecycle rejections, tracebacks, or WebSocket stream terminations. Two
   `no_detections` warnings came from a discarded click on a transient edge
   detection; a bounded detector probe and two central-target UI clicks passed,
   so no speculative product subsystem was added.
8. One final bounded independent closure review checked factual claims,
   credential leakage, hashes/identifiers, stale status, evidence links, and
   claim boundaries and returned `GO` with no concrete blockers.

Secret-free evidence and screenshots are in
`docs/reporting/agent-ops/codex-modernization/evidence/2026-07-17-pxe0105-v7-beta2-live-acceptance/manifest.json`.

## Claim Boundary

This checkpoint proves automated lifecycle, API, dashboard, configuration, and
setup behavior plus the named x86_64 public HTTP lab runtime's media,
Classic/Smart repeated selection, and responsive browser paths. It does not
imply Raspberry Pi, GStreamer source-build, QGC, public WebRTC ICE/TURN, PX4,
SIH/SITL/HIL, production TLS, field, autonomous follower-response, or aircraft
readiness.
