# 2026-07-16 PXE-0100 VPS Feedback Closure Journal

- Recovered the interrupted pre-handoff work without overwriting local operator
  state, credentials, or unfinished reporting files.
- Closed the bounded UI wording issues for inactive target selection, public
  HTTP WebRTC, browser restart policy, PX4-only SIH, and read-only About/update
  guidance. Larger account, SIH, and TURN products remain PXE-0101..0103.
- Pushed initial candidate `2fc803fe`; its mandatory backend, dashboard,
  schema, build, review, public smoke, responsive browser, and nonblank canvas
  gates passed.
- Reproduced the real post-restart browser failure. Process-local sessions
  correctly became stale, but auth middleware outside CORS hid the `401` from
  the allowed dashboard Origin. Split Host/Origin and authorization middleware,
  placed CORS between them, added stale-session coverage, and repaired only the
  current-contract drift in the production-remote browser harness.
- Pushed `c5bdc698`; `342` adjacent tests, `91` Phase 0/harness tests, all `49`
  dashboard suites and `297` tests, lint/build/schema/static gates, accepted
  local production-browser evidence, and bounded independent review passed.
- Ran the exact public reversible restart acceptance. The first restart loaded
  `test3.mp4` and returned to sign-in, but the second restore restart exposed a
  10-second watchdog race: generic process code `1` beat supervised restart
  code `42`, so the backend stopped after the config had returned to
  `test4.mp4`.
- Propagated one synchronous requested process exit code through the API task,
  main-loop watchdog, and graceful `main()` return. Full lifecycle/safety tests
  passed `160/160`; Phase 0/exposure/harness tests passed `179/179`; the final
  five focused restart tests and independent blocker review passed.
- Pushed final code commit `e4121ce4`, restored the Core-only public bench with
  `bash scripts/run.sh --no-attach -m -k`, and repeated both real restarts.
- Final acceptance passed: PIDs `2565651 -> 2566525 -> 2566632`, sources
  `test4 -> test3 -> test4`, two supervised code-42 restarts, exact-origin
  CORS-readable stale-session denials after both cycles, successful re-login,
  zero page errors, and zero pending restart changes.
- Current run is `pixeagle_manual_78362d7d-8d7a-43e1-be2c-04e290181ba8` at
  `http://204.168.181.45:3040`. Both credential files remain byte-identical and
  mode `0600`; tracking/following are inactive, MAVSDK Server and MAVLink2REST
  are intentionally skipped, and managed SIH remains disabled.
- A five-hour post-acceptance log soak kept the same run healthy with dashboard
  HTTP `200`, parseable component JSONL, zero non-INFO backend entries after the
  final restart, no traceback, and no exact demo password in the runtime log
  tree. The 12.3 MB session remained inside bounded retention; no runtime,
  config, credential, firewall, or service mutation was performed.
- Next: maintainer VPS browser test, then Core-first Raspberry Pi 5 execution.
  AI/model, optional OpenCV-GStreamer, QGC, PX4-in-loop, production TLS, tag,
  and release remain separate evidence gates.
