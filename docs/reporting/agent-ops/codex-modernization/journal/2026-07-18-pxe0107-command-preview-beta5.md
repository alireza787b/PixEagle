# PXE-0107: Follower Command Preview And Beta.5

## 2026-07-18

- Resumed the interrupted command-preview slice without changing the QGC
  scope. The requested behavior was separated from the live safety contract:
  replay remains rejected for PX4, while an explicit local-only mode exercises
  follower math and records intents.
- Added the default-off `COMMAND_PREVIEW` mode, bounded recorder, readiness
  contract, typed status fields, setup profile, dashboard labels, docs, and
  focused regression tests.
- Required an active circuit breaker and disabled safety-bypass settings in
  preview. This prevents the preview feature from becoming an accidental
  authorization path for autonomous commands.
- Performed the independent cleanup pass requested by the maintainer: the
  schema description for `FOLLOWER_MODE` is explicit, and the preview docs no
  longer imply that an unauthenticated API curl is universally valid.
- Gates before release: backend/API/config 396 passed; dashboard 342 passed;
  lint/build/schema/compile/diff checks passed. No flight-control or simulator
  claim is made.
- The first complete backend run found two code-generation/runtime-harness
  blockers rather than being waived: API/MCP provenance was regenerated, and
  cleanup now tolerates a partially constructed controller without a PX4
  interface. The post-fix suite passed 3,361 tests with 48 expected skips and
  one existing Starlette/httpx deprecation warning.
- Next operational step is the stopped-runtime release/deploy validation and
  then a fresh Ubuntu test using the maintained guide.
