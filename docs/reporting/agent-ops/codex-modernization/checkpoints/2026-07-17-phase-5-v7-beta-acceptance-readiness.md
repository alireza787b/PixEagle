# Phase 5 v7 Beta Acceptance Readiness

Date: 2026-07-17

Issues: PXE-0105, PXE-0074

Source baseline: `eee45d5015789f4e96b0e023ccadd56502395927`

Status: automated gates and bounded independent review complete; exact release
commit, clean-checkout evidence, and public VPS acceptance refresh pending

## Scope

This slice closes the concrete defects found during the maintainer's public VPS
browser check and the final release review. It prepares `7.0.0-beta.1` as a
controlled prerelease for repeated browser/operator testing before fresh Ubuntu
and Raspberry Pi installation.

The currently running public process is not the candidate. Runtime log evidence
from `pixeagle_manual_95558dc9-da7a-48b1-8ba3-f3f82edd99dd` shows the historical
Classic `Tracking is already active` guard and schema-1.3.0 retirement errors.
The release process must stop that exact owned run, apply the two registered
retirements through config sync, and start the merged beta before operator
acceptance is requested.

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
  samples, and changelog all identify `7.0.0-beta.1`.

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

## Release And Live Acceptance Gate

1. Record bounded independent safety/backend, frontend/operator, and
   setup/security review verdicts; repair only concrete blockers.
2. Commit and push the release branch, then run the clean-checkout setup handoff
   including dashboard install/test/build against the exact commit.
3. Merge normally to current remote `main`, create annotated
   `v7.0.0-beta.1`, and publish a GitHub prerelease. No force push or history
   rewrite is permitted.
4. Stop only the owned old VPS run. Preserve the ignored config and private
   browser handoff hashes.
5. Apply exactly the two registered config retirements through authenticated
   config sync, retain the generated backup, restart, and require zero
   actionable operations.
6. Verify public dashboard/API/media security and exact beta provenance, then
   exercise Classic initial selection plus repeated active/loss-retry retarget
   and Smart initial selection plus repeated visible-detection retarget.
7. Only after those checks pass, ask the maintainer to retest the unchanged
   public URL and private credential.

## Claim Boundary

This checkpoint proves automated lifecycle, API, dashboard, configuration, and
setup behavior on the named x86_64 development host. Until the final live gate
is appended, it does not prove public Smart selection quality or repeated-click
behavior on the refreshed process. It never implies Raspberry Pi, GStreamer
source-build, QGC, public WebRTC ICE/TURN, PX4, SIH/SITL/HIL, production TLS,
field, autonomous follower-response, or aircraft readiness.
