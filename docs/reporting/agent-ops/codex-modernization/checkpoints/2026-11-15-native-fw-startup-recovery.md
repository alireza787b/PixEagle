# Native FW startup recovery and speed editor — 15 November 2026

The operator approved conventional Cessna FW pursuit but reported startup video
delay, refused actions and one lost follow session. This approval does not close
startup stability or hardware qualification.

## Evidence and cause

`training-native-fw-operator-r1` retains 20,513 complete native wire records plus
an incomplete final record. Raw files are preserved, including incomplete tails.
The host subsequently restarted; missing shutdown/transport evidence is unknown.

There is one explicit `native_aircraft_context_unavailable` intent refusal and
ten socket closures. During the early interval, high-rate pose, attitude and
envelope remained fresh while vehicle-status age crossed its 1 s limit. Eight
passive reads were nonfresh; later observed status ages stayed below 0.57 s.
The pinned Commander publishes unchanged vehicle status every 500 ms. Unlike
VTOL status, its cadence had not been added to the native delivery allowance.
Every stale passive reply also destroyed discovery and aircraft association.

This confirms an aircraft-status freshness/admission problem alongside genuine
CSRT appearance losses. It does not prove that every displayed delay had the
same cause or that the real camera/network failed. Original QGC transport logs
were not retained across the interrupted run. The local audit and plot live at
`reports/sitl/follower-consolidation-20261111/native-fw-startup-review-r1`.

## Focused changes

- One phase-source helper accounts for each pinned source's publication cadence
  plus the existing delivery allowance: vehicle status 0.5+1 s, VTOL status 1+1 s.
  High-rate ownership proof, command TTL, Stop/takeover and pose freshness are
  unchanged. Genuine phase loss still blocks/ends guidance. Diagnostics report
  the effective source budgets.
- A well-formed stale passive read removes current state/Start admission, retains
  progress watermarks and retries read-only on the same connection. Fresh valid
  observations restore readiness. Identity, ownership, rescue and transport
  failures still retire the connection. No action is replayed.
- QGC and Dashboard open the speed editor with advertised-step formatting, show
  a short range and put long explanations behind Details. Acknowledged backend
  values and explicitly entered precision remain unchanged until an explicit
  request; there is no new client-side speed limit.

## Recovery boundary

GCS video loss cannot itself revoke fresh onboard target evidence. Independent
external angles/status can survive camera-video interruption. Local image
tracking without fresh camera input uses the existing bounded recovery; it
cannot pursue indefinitely from a frozen image. Aircraft telemetry/authority
loss, Stop and pilot takeover retain precedence. Connection recovery restores
read-only status/video, never Start or old camera gestures.

Native contract/sanitizer, backend, UI and actual-startup evidence are renewed
in the associated run directory. Hardware packet-loss/camera qualification,
platform packages and the earlier FW altitude-hold tolerance remain separate.
No firmware flash, real aircraft operation or public QGC release occurs here.

## Verification and artifact identities

- Canonical native build: **91 contract tests and 82 sanitizer tests passed**.
  Adapter image `274b6cfb9dd97854304900ed591918f9051b9f5b1f941737b27a3e9b8a1a0568`,
  binary SHA-256 `a01fdb07d80fd66c793808f9f9e2f3c7a9988c41ece71f12af199f1530178479`.
  No PX4 firmware source/image was changed. The current V5 evidence manifest
  binds the renewed runtime assets; archived V4/historical evidence is unchanged.
- Backend/drone/core sweep: 3,472 passed; its single stale runtime-evidence pin
  was renewed and the 138-case evidence/API/parameter gate passed. These counts
  overlap; they are not additive. Focused recovery checks passed 202 cases.
- Dashboard: all **591 tests**, lint and production build passed.
- QGC: incremental build and all **477 Unit/Integration suites** passed with
  standard Flaky/Network exclusions and the prepared GStreamer runtime. Scoped
  lint passes. Full repository lint remains blocked by existing executable,
  whitespace, formatting and vehicle-null findings outside this change; its
  automatic unrelated edits were archived and reverted.
- Launcher/menu: **85 tests passed**, including live stdout/stderr persistence.
  `qgc-live.log` is collected during future runs with actual Custom.PixEagle
  debug categories, rather than waiting for normal shutdown. A clean QGC exit
  now closes the training stack without presenting a component-failure traceback.

`training-native-fw-recovery-r2` used the renewed adapter and application.
A 91-second read-only ground check received **1,243 frames**, 86 status samples,
zero request/association errors and a successful five-second video-client
disconnect/reconnect. It sent no target/flight actions.

The operator also exercised the open application afterward. At the retained
live review there were **13,297 native observations, zero nonfresh replies,
zero native refusals**, and 175 owner-confirmed observations. Maximum observed
vehicle-status age was 0.692 s. Final following was inactive and the operator
Stop result was `confirmed_hold`; retargeting retained bounded continuity.
Later CSRT appearance loss after Stop is recorded, not relabeled as a network
failure. This is new simulator evidence, not a guarantee for every real link.

The QGC container subsequently exited cleanly (code 0); all token-owned
containers and the private network were removed. Its old launcher emitted a
generic traceback on normal close; the cleanup receipt and original log remain
unchanged, and the above normal-close classification repairs future runs.
No hardware or GitHub Actions execution is required for these local gates.
