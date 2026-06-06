# Phase 4 Checkpoint: Typed Following Telemetry

Date: 2026-06-06

## Slice

PXE-0047: typed process-local following telemetry and dashboard detailed
follower-card migration.

## Scope

Added a typed follower telemetry/setpoint snapshot under the approved
`/api/v1/following/*` family:

- `GET /api/v1/following/telemetry`
- response model: `APIFollowingTelemetryResponse`
- operation ID: `get_following_telemetry`
- structured `/api/v1` error envelope
- route inventory coverage

This endpoint reports PixEagle process-local follower setpoint fields and
diagnostics. It does not claim PX4-observed Offboard, SITL, HIL, field, or
vehicle-response success.

## Backend Changes

- Added `API_V1_FOLLOWING_TELEMETRY_PATH`.
- Added `FOLLOWING_TELEMETRY_CLAIM_BOUNDARY`.
- Added `APIFollowingTelemetryResponse`.
- Added `FOLLOWING_TELEMETRY_ERROR_RESPONSES`.
- Added `FastAPIHandler.get_following_telemetry()`.
- Added `_get_following_telemetry_snapshot()`:
  - reuses typed following status classification;
  - prefers live setpoint-handler fields when available;
  - falls back to legacy follower telemetry fields only for compatibility;
  - exposes `field_source` as `active_follower`, `legacy_telemetry`,
    `schema_profile`, or `unavailable`;
  - includes optional `last_command_intent`, target-loss, safety, performance,
    flight-mode, and circuit-breaker diagnostics;
  - keeps OffboardCommander command-publication state in the same local-only
    structure used by typed following status.

The response uses `local_successful_publish_observed` wording for local MAVSDK
publication counters. It does not expose that signal as PX4-observed evidence.

## Dashboard Changes

- Added `endpoints.followingTelemetry`.
- Added `normalizeFollowingTelemetry()` to map the typed response into the
  existing follower-card prop shape.
- Added `useFollowingTelemetry()`:
  - polls `/api/v1/following/telemetry`;
  - falls back to `/telemetry/follower_data` only when the typed route is
    missing during rolling updates;
  - ignores stale out-of-order responses.
- Migrated `DashboardPage` detailed follower status card data from direct
  legacy `/telemetry/follower_data` polling to `useFollowingTelemetry()`.
- Left the Follower visualization page on legacy telemetry arrays because that
  page needs a separate typed historical telemetry/history contract.

## Documentation

- `docs/core-app/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/followers/07-integration/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Evidence

Focused validation completed before final gates:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile src/classes/fastapi_handler.py
PYTHONPATH=src .venv/bin/pytest tests/test_api_route_inventory.py tests/unit/core_app/test_app_controller_offboard_safety.py -q
CI=true npm test -- --watchAll=false --runTestsByPath src/hooks/useStatuses.test.js
npm run lint
```

Results:

- Python syntax compile: passed.
- Route inventory plus AppController Offboard safety: 76 passed.
- Dashboard status-hook suite: 1 suite, 21 tests passed.
- Dashboard lint: passed.

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
- full dashboard tests: 8 suites, 42 tests passed;
- dashboard build: compiled successfully.

## Risks And Open Follow-Ups

- This is unit/contract evidence only. No runtime PX4/SITL/HIL/field pass is
  claimed.
- The Follower visualization page still uses `/telemetry/follower_data` for
  historical arrays and plots. A later PXE-0008 slice should design typed
  following telemetry history before migrating that page.
- Circuit-breaker status is included for the follower card, but broader typed
  safety/circuit-breaker API migration remains part of PXE-0008/PXE-0041.

## Next Slice Candidates

- Continue PXE-0008 with typed follower telemetry history for the Follower page.
- Continue PXE-0022 companion/API/MCP reconciliation and sidecar contract
  verification.
- Continue PXE-0021 dashboard toolchain modernization.
- Keep PXE-0040 official Gazebo L4 runtime proof open for suitable host
  evidence.
