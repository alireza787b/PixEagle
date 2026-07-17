# Phase 4 Checkpoint: Follower Visualization Typed Telemetry History

Date: 2026-06-06

## Slice

PXE-0048: migrate the Follower visualization page's follower/setpoint history
off legacy follower telemetry while keeping tracker history scoped for a later
typed tracker-history contract.

## Scope

This slice is a dashboard/API-client migration on top of the existing typed
`GET /api/v1/following/telemetry` contract. It does not add a new backend
route and does not claim PX4-observed Offboard, SITL, HIL, field, tracker/video
runtime, deployment, service, or real-aircraft validation.

## Dashboard Changes

- `FollowerPage` now imports the endpoint registry instead of building
  `protocol://host:port` locally.
- Follower/setpoint history snapshots now poll
  `endpoints.followingTelemetry` (`/api/v1/following/telemetry`).
- Legacy `endpoints.followerData` (`/telemetry/follower_data`) is used only
  when the typed route is missing with `404`, `405`, or `501` during rolling
  updates.
- Tracker center/bounding-box history still reads `endpoints.trackerData`
  (`/telemetry/tracker_data`). That is intentionally deferred until a typed
  tracker-history contract exists.
- Polling now:
  - performs an initial refresh instead of waiting for the first interval;
  - ignores stale out-of-order responses with mounted/request-sequence guards;
  - bounds follower/tracker history and raw log growth.
- `normalizeFollowingTelemetry()` now maps typed `fields` and legacy
  `setpoints` into a shared `fields` object and legacy-compatible chart aliases
  such as `vel_body_fwd`, `vel_x`, `vel_y`, `vel_z`, and `yaw_rate`.
- Numeric typed telemetry timestamps are normalized from epoch seconds or
  milliseconds into ISO strings so existing history charts can parse elapsed
  time correctly.

## Tests

- Added `dashboard/src/pages/FollowerPage.test.js`.
- Extended `dashboard/src/hooks/useStatuses.test.js`.

Focused frontend coverage proves:

- typed following telemetry is polled for follower history;
- legacy follower telemetry fallback happens only when the typed route is
  missing;
- stale out-of-order follower-history responses are ignored;
- typed `fields` and legacy `setpoints` normalize into chart-compatible
  aliases;
- typed epoch-second timestamps normalize into JavaScript-date-compatible ISO
  strings.

## Documentation

- `docs/core-app/03-api/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/followers/07-integration/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Evidence

Focused validation completed before final gates:

```bash
CI=true npm test -- --watchAll=false --runTestsByPath src/hooks/useStatuses.test.js src/pages/FollowerPage.test.js
npm run lint -- --format unix
```

Results:

- Follower/status hook focused frontend suites: 2 suites, 25 tests passed.
- Dashboard lint: passed.

Independent review findings fixed before final gates:

- Frontend review found that typed telemetry timestamps arrived as epoch
  seconds while `StaticPlot` parses `new Date(d.timestamp)`, compressing chart
  elapsed time by 1000x. `normalizeFollowingTelemetry()` now converts numeric
  timestamps to ISO strings, and tests assert the conversion.
- Frontend review found the stale-response test assumed a hardcoded `1000 ms`
  interval while the page polling rate is environment-driven. The test now
  advances one scheduled timer instead of assuming the interval value.
- Resume/reporting review found this checkpoint still said final validation was
  pending and that the PXE-0047 next-slice guidance still pointed to typed
  follower history. The reporting was updated after final gates.

Final validation completed:

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py tests/unit/core_app/test_app_controller_offboard_safety.py -q
PYTHON=.venv/bin/python bash scripts/check_schema.sh
PYTHONPATH=src .venv/bin/pytest tests/test_docs_infrastructure_consistency.py -q
git diff --check
npm run lint
CI=true npm test -- --watchAll=false
npm run build
```

Results:

- route inventory, parameters reload, and AppController Offboard safety:
  86 passed;
- schema check: up to date;
- docs infrastructure consistency: 10 passed;
- whitespace check: passed;
- dashboard lint: passed;
- full dashboard tests: 9 suites, 46 tests passed;
- dashboard build: compiled successfully.

## Risks And Open Follow-Ups

- This is unit/contract/frontend evidence only. No runtime PX4/SITL/HIL/field
  pass is claimed.
- The Follower visualization page still uses legacy tracker telemetry for
  tracker center/bounding-box history. A future PXE-0008 slice should define a
  typed tracker-history contract before migrating that plot source.
- Broader typed safety/circuit-breaker APIs, MCP resources, companion-runtime
  reconciliation, dashboard toolchain modernization, and final no-legacy
  cleanup remain separate tracked work.

## Next Slice Candidates

- Continue PXE-0008 with typed tracker history or broader API/MCP route
  modernization.
- Continue PXE-0022 companion/API/MCP reconciliation and sidecar contract
  verification.
- Continue PXE-0021 dashboard toolchain modernization.
- Keep PXE-0040 official Gazebo L4 runtime proof open for suitable host
  evidence.
