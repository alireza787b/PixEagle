# Phase 5 VPS Feedback Closure

Date: 2026-07-16

Issue: PXE-0100

Final code commit: `e4121ce44f8894835b80b054c12b40ce9b19da3b`

Status: ready for maintainer VPS browser test; Raspberry Pi execution pending

## Scope

This slice closed the bounded operator feedback found immediately before the
Raspberry Pi handoff and then exercised the real authenticated restart path. It
did not reopen the API architecture, add a remote updater, claim public-IP
WebRTC, or represent the PX4-only SIH lifecycle as a complete simulator.

## Findings And Decisions

- The disabled remote restart was deployment drift. The old public run had
  startup policy `local_only`; the maintained beginner browser profile selects
  `lab_admin_browser` for authenticated administrators.
- Browser sessions are intentionally process-local. After a restart, a stale
  cookie correctly failed closed, but authorization middleware sat outside the
  CORS boundary. The browser therefore received an opaque network failure and
  could remain on a reconnect screen instead of returning to sign-in.
- The first exact restart test passed, but the restore restart found two
  competing 10-second exit paths: the API restart path requested supervisor
  code `42`, while the main-loop shutdown watchdog could exit with generic code
  `1`. The second path won the race and stopped the backend. Restart intent now
  propagates through the API task, watchdog, and graceful `main()` return.
- The production-remote browser harness had drifted from current dashboard
  headings and config contracts. Its repair was kept narrow and retained the
  existing local self-signed HTTPS/security claim boundary.
- Manual WebRTC signaling can succeed on a public HTTP/IP bench while media ICE
  remains unreachable through the current NAT/firewall path. Opening a broad
  UDP range or weakening authentication was rejected.
- Browser account CRUD, a complete SIH training stack, and production browser
  TURN remain separately tracked as PXE-0101, PXE-0102, and PXE-0103.

## Changes

- Inactive classic-tracker video clicks give short, non-mutating target-arm
  guidance; public HTTP WebRTC, restart, SIH, and About wording match actual
  ownership and evidence boundaries.
- HTTP enforcement is now ordered as Host/Origin validation, CORS, then
  authorization. Hostile authorities remain outside CORS, while an explicitly
  allowed dashboard Origin can read a fail-closed stale-session denial and
  start reauthentication.
- The supervised restart exit request is recorded synchronously and preserved
  by both shutdown watchdog and normal process return paths.
- The production-remote harness now uses current headings, current config/About
  routes, minimal valid inert fixtures, and a narrowly checked same-origin
  browser image-blob exception.
- Setup, security, and troubleshooting docs explain process-local sessions,
  post-restart sign-in, middleware ordering, and the supervised restart path.

## Validation

- Initial operator-feedback candidate: `72` mandatory tests, `177`
  setup/profile/API/docs tests, `49/49` dashboard suites and `297/297` tests,
  dashboard lint/build, schema, compile, and diff checks passed.
- Restart/CORS candidate: `342` adjacent auth/setup/docs tests and `91` Phase 0
  plus production-harness tests passed; the dashboard again passed `49` suites,
  `297` tests, lint, and production build.
- Exit-race correction: `160` full lifecycle/Offboard-safety tests and `179`
  Phase 0/exposure/harness tests passed; the five new focused restart tests
  passed after the final synchronous-intent refinement.
- Schema remained current at `40` sections and `540` parameters; Python compile,
  Node syntax, and `git diff --check` passed.
- Local production-remote browser evidence was accepted with all `16` security
  checks, `180` requests, `130` responses, `8` WebSockets, no page errors, and
  passed adversarial Host/Origin/authority/auth probes. It proves only a local
  self-signed HTTPS reverse-proxy/browser boundary.
- Two bounded independent reviews returned `GO`; the final review found no
  blocking or high-risk defect.

## Exact Public Lab Acceptance

The final pushed candidate was started with the maintained Core-only command:

```bash
bash scripts/run.sh --no-attach -m -k
```

- run ID: `pixeagle_manual_78362d7d-8d7a-43e1-be2c-04e290181ba8`
- dashboard: `http://204.168.181.45:3040`
- backend: `http://204.168.181.45:5077`
- components: backend/main app and dashboard
- intentionally skipped: MAVSDK Server and MAVLink2REST
- final source: `resources/test4.mp4`
- final backend PID: `2566632`

The real browser acceptance performed `test4 -> test3 -> test4`, used the
dashboard confirmation for both restarts, and observed backend PIDs
`2565651 -> 2566525 -> 2566632`. Both slow graceful shutdowns exited with the
supervised code `42`; the launcher started a replacement process each time.
After each restart the stale session produced CORS-readable `401` responses for
the exact dashboard Origin, the UI returned to `Operator sign in`, re-login
succeeded, the expected source loaded, and pending restart state cleared.

There were no page errors. Two aborted and 152 connection-refused browser
requests occurred only while the backend process was intentionally absent and
were followed by successful reauthentication. The final config has zero
pending restart changes, tracking/following remain inactive, and managed SIH
remains disabled.

The existing credential files were not rotated or rewritten. Their SHA-256
digests remained:

- user store: `bde8b1a955c856b21cc7b8be02679fcef24db2fb92eae78befa52f1e11faeb75`
- owner handoff: `e58c5dda6736d51285ffe9318d3a965109236036cf29c6c8b534b53decd6fda9`

Both files remain owner-only mode `0600`; no plaintext credential is stored in
repository evidence.

Evidence:

- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-16-pxe0100-vps-feedback-closure/manifest.json`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-16-pxe0100-vps-feedback-closure/restart-acceptance.json`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-16-pxe0100-vps-feedback-closure/validation-desktop.png`
- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-16-pxe0100-vps-feedback-closure/dashboard-mobile-rendered.png`
- `logs/runtime/pixeagle_manual_78362d7d-8d7a-43e1-be2c-04e290181ba8/`

## Post-Acceptance Log Soak

At `2026-07-17T01:33:13Z`, the same run had remained healthy for `19,865`
seconds. The dashboard still returned HTTP `200`; the supervisor and listener
processes remained alive. All three component JSONL files parsed successfully.

After the final accepted restart boundary at `2026-07-16T20:02:13Z`, the
backend recorded `17,289` INFO entries and zero WARNING, ERROR, or CRITICAL
entries in the first bounded scan. At the final snapshot, all historical
non-INFO entries were still limited to the three expected lab-exposure startup
boundaries, two forced exits from the accepted restart tests, and three copies
each of Core-only MAVLink disconnect, video-dimension mismatch, and OSD
auto-degrade warnings. There was no traceback.

The runtime session occupied `12,256,512` bytes, below the existing default
100 MiB runtime-log retention budget. The exact demo password was absent from
the runtime log tree. Both credential files retained their prior SHA-256
digests and mode `0600`; the soak audit did not restart the process or mutate
configuration, credentials, firewall, or services.

Soak evidence:

- `docs/reporting/agent-ops/codex-modernization/evidence/2026-07-17-pxe0100-vps-log-soak/manifest.json`

## Claim Boundary

This checkpoint proves only the listed x86_64 VPS process, browser, auth,
config, restart, and media behavior. It does not prove Raspberry Pi execution,
model inference, custom OpenCV/GStreamer, MAVSDK Server, MAVLink2REST, QGC
playback, PX4, SIH runtime, SITL, HIL, field, production TLS, follower response,
vehicle response, or real-aircraft behavior.

## Next Gate

1. Maintainer tests the current VPS dashboard using the unchanged credential.
2. If accepted, execute the owner-only Core-first Raspberry Pi 5 handoff and
   stop at the first failed command without undocumented workarounds.
3. Add Full AI/model and optional OpenCV-GStreamer checks only after Core
   acceptance.
4. Keep QGC, production TLS, PX4-in-loop, tag, and release deferred until their
   separate evidence gates are accepted.
