# 2026-09-21 — PXE-0174 authenticated native connection context

- Implemented typed native context and explicit observational connection with
  real session/bearer credentials, exact status+telemetry scopes, POST CSRF and
  durable audit. GET is snapshot-only; following authorization remains false.
- Added observed MAVSDK/telemetry UID comparison, heartbeat-counter freshness,
  generation invalidation, explicit telemetry routing, and fail-closed reasons.
- Kept observational discovery on the stable flight owner/lifecycle barrier;
  it does not start following, steal an uninitialized loop, or reconfigure an
  active follower's telemetry.
- Final focused backend/API/auth/lifecycle/docs regression: **660 passed**,
  including **43 native tests**. Schema: 43 sections / 606 parameters. Candidate
  inventory, compile, and diff gates pass.
- Added a loopback-only QGC UI fixture with production auth/routes and mocked
  aircraft observation. No operational services, deployment, camera, MAVSDK
  server, SITL/HIL, or real aircraft were exercised.
- Preserved slice-0 reports and original checkout. API contract, exact commands,
  ignored local evidence paths, limitations, and next slice are recorded in the
  [backend context checkpoint](../checkpoints/2026-09-21-qgc-native-context.md).
- Completed the paired local Linux slice-1 gate: custom QGC Debug/Release
  builds and boot checks, **406/406** selected CTest targets including all three
  StockUI targets, **67 client + 4 manager** native Qt passes, and the final
  copy-only focused **5/5** CTest regression.
- Debug and actual Release two-endpoint interaction checks covered verified
  association, wrong-endpoint rejection, and disconnect/restart recovery with
  synthetic aircraft providers and production authenticated API routes. Raw
  simulated operator feedback and dispositions are preserved without implying
  a human study or hardware/field evidence.
- Paired checkpoint: `/home/alireza/qgroundcontrol-pixeagle/custom-pixeagle/SLICE-1.md`.
  Evidence: `/home/alireza/.cache/pixeagle-qgc-baseline/slice-1-2026-09-21/`.
  PXE-0174 is done for this local connection/identity gate. Existing slice-0
  lint/CI and qualification limitations remain; slice-2 implementation has not
  started in the backend.
