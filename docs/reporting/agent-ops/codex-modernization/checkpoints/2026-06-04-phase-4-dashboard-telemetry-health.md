# 2026-06-04 - Phase 4 Dashboard Typed Telemetry Health

## Slice

- Phase: 4 Dashboard API/client normalization
- Primary issue: PXE-0043
- Related completed backend issue: PXE-0036
- Claim boundary: dashboard client/UI unit, lint, and build evidence only. No
  live PixEagle backend, MAVLink2REST runtime, PX4/SITL scenario execution,
  HIL, field, deployment, service installation, or real-aircraft validation was
  run.

## Changes

- Added `endpoints.telemetryHealth` for `GET /api/v1/telemetry/health`.
- Added named `trackerData` and `followerData` endpoint constants and moved
  status hooks away from repeated literal telemetry URLs.
- Added `normalizeTelemetryHealth()` to convert backend snake_case telemetry
  health into stable dashboard fields:
  - `guidance`, `chipLabel`, `color`, and `detail`;
  - `usableForFollowing`;
  - normalized transport fields;
  - normalized last-success freshness;
  - normalized payload fields with raw `flight_mode`/`arm_status` values and
    display labels.
- Added `useTelemetryHealth()` polling hook using no-cache headers against the
  typed `/api/v1` health route.
- Added an `OperationalStatusBar` telemetry chip with `Sensors` icon and
  visible states: `Telemetry: Usable`, `Telemetry: Degraded`,
  `Telemetry: Stale`, `Telemetry: Unavailable`, `Telemetry: Disabled`, and
  `Telemetry: Connecting`.
- Wired `DashboardPage` to pass typed telemetry status into the operational
  status bar.
- Updated API/core docs to show the dashboard typed health consumption path.
- Refreshed companion refs before this dashboard/API slice:
  - MavlinkAnywhere `origin/main` latest tag `v3.0.14` at `7643d4d`;
  - Smart Wi-Fi Manager `origin/main` latest tag `v2.1.14` at `a5414fc`;
  - `mavsdk_drone_show` `origin/main` latest tag
    `v5.5.56-simurgh-source-followups` at `7e0eddd7`.

## Files Changed

- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/hooks/useStatuses.js`
- `dashboard/src/hooks/useStatuses.test.js`
- `dashboard/src/components/OperationalStatusBar.js`
- `dashboard/src/components/OperationalStatusBar.test.js`
- `dashboard/src/pages/DashboardPage.js`
- `docs/core-app/03-api/README.md`
- `docs/core-app/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `npm test -- --watchAll=false --runTestsByPath src/hooks/useStatuses.test.js src/components/OperationalStatusBar.test.js`
  - 2 suites passed, 10 tests passed
- `npm run lint`
  - passed
- `npm test -- --watchAll=false`
  - 3 suites passed, 11 tests passed
- `npm run build`
  - compiled successfully

## Coverage Notes

- Disabled telemetry with cached payload is shown as `Telemetry: Disabled` and
  is not treated as usable or fresh.
- Latest-request-failed while cached payload remains fresh is shown as
  `Telemetry: Degraded` and is not treated as usable.
- All known consumer guidance values have distinct dashboard chip labels.
- The typed telemetry hook is tested to call `endpoints.telemetryHealth` with
  no-cache request metadata.
- The hook starts in `Telemetry: Connecting`, replaces stale raw health on
  request failure, and ignores stale out-of-order responses.
- `useSmartModeStatus()` now uses the endpoint registry status URL, preserving
  reverse-proxy routing inside the same status-hook surface.

## Independent Review

- Frontend/UI first-pass review found:
  - frontend normalization should force disabled telemetry freshness false even
    if an API response regresses to a mixed cached state;
  - polling needed in-flight/out-of-order response guards;
  - `useSmartModeStatus()` should use `endpoints.status` instead of a direct
    host/port URL;
  - initial telemetry state should show connecting rather than unavailable.
- API/MCP and safety first-pass review found:
  - failed refreshes should replace stale raw `telemetryHealth`;
  - one phase-map row still described PXE-0043 as future work.
- Fixes made:
  - disabled/frontend mixed-state fail-closed normalization;
  - monotonic request-sequence and mounted-state guards;
  - error fallback raw telemetry replacement;
  - endpoint-registry smart-mode status polling;
  - connecting initial state;
  - phase-map wording cleanup;
  - tests for all reviewer-driven behavior.

## Risks And Follow-Ups

- Broader `/api/v1` migration remains PXE-0008; this slice only adopts typed
  MAVLink telemetry health.
- Dashboard Create React App/toolchain debt remains PXE-0021.
- Tracker dashboard stale/unusable state clarity remains PXE-0024.
- Companion-runtime/API reconciliation remains PXE-0022.
- Official Gazebo visual runtime evidence remains PXE-0040 and requires a
  suitable operator-gated host/run; this slice does not change runtime evidence
  status.

## Next Slice

Continue Phase 4 with one of:

- PXE-0024 dashboard tracker stale/unusable state clarity;
- PXE-0008 broader `/api/v1` router/client migration;
- PXE-0022 companion-runtime/API reconciliation;
- PXE-0021 dashboard toolchain migration planning or implementation.
