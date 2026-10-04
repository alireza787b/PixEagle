# 2026-09-21 — PXE-0173 native QGC workspace and baseline

- Created the isolated `feature/qgc-native-integration` worktree at `989d966`.
- Focused backend checks: 268 passed; schema matches 604 parameters.
- Dashboard: 471 tests and production build passed in the new worktree.
- Recorded exact-base CI failures and local reproductions: four dashboard lint
  errors and one backend test-hygiene failure. No green full-baseline claim.
- Recorded commands, versions, evidence locations, scope, and next slice in the
  [baseline checkpoint](../checkpoints/2026-09-21-qgc-native-baseline.md).
- Backend and dashboard operational source remains unchanged. No flight runtime,
  deployment, PixEagle application service, or camera/gimbal hardware commands.
- Completed paired QGC stock/custom Debug and Release build evidence. Custom:
  404 selected CTest targets passed; stock: 404 initially passed plus a passing
  GPS timing rerun. All 13 JPEG transport cases passed in each build.
- Release boot and isolated UI smoke checks passed with mock vehicles and
  synthetic HTTP/WebSocket video. Recorded offline-map/mock-protocol limits and
  existing QGC lint blockers. PXE-0173 tracks completed baseline evidence, not
  green full CI or aircraft qualification.
