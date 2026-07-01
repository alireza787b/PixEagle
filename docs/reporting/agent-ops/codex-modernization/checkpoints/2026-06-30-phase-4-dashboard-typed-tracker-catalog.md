# 2026-06-30 Phase 4 Dashboard Typed Tracker Catalog Adoption

## Summary

Continued PXE-0008 by migrating dashboard tracker selector/status catalog and
current-config metadata reads to the typed `GET /api/v1/tracking/catalog`
contract.

This is a dashboard API-consumer migration. It does not change backend route
registration, tracker mutation behavior, QGC media behavior, PX4/SITL/HIL,
field, deployment, or real-aircraft behavior.

## Behavior

- Added `endpoints.trackerCatalog` for `/api/v1/tracking/catalog`.
- Added a tracker-catalog normalizer that converts the typed catalog response
  into the existing dashboard component shapes:
  - `availableTrackers.available_trackers`
  - `availableTrackers.tracker_types`
  - `currentConfig.configured_tracker`
  - `currentConfig.expected_data_type`
  - `currentTracker.tracker_type`
  - `currentTracker.display_name`
  - runtime/catalog guidance fields
- Updated `useTrackerSelection()` to prefer the typed catalog for selector and
  current-config metadata.
- Updated `useAvailableTrackers()` and `useCurrentTracker()` to prefer the
  typed catalog.
- Kept legacy read fallbacks only for a missing or explicitly unsupported typed
  route: HTTP `404`, `405`, `501`, or a typed `unavailable` response with no
  usable catalog entries.
- Do not hide auth/policy or malformed typed-catalog failures behind legacy
  fallbacks.
- Validate the typed catalog contract before normalization so malformed object
  payloads do not render as empty default tracker state.
- Kept tracker switch/restart/set-type mutations on legacy endpoints pending a
  separate typed action/configuration design.
- Updated `TrackerStatusCard` so configured tracker metadata can come from the
  typed catalog `tracker_types` map when the configured tracker is not a
  UI-selectable schema-manager entry.
- Added `/pixeagle-api/api/v1/tracking/catalog` to the production remote e2e
  approved-path allowlist while retaining legacy fallback paths.

## Files Changed

- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/services/apiEndpoints.test.js`
- `dashboard/src/hooks/useTrackerSchema.js`
- `dashboard/src/hooks/useTrackerSchema.test.js`
- `dashboard/src/components/TrackerStatusCard.js`
- `dashboard/src/components/TrackerStatusCard.test.js`
- `dashboard/e2e/production-remote.spec.js`
- `docs/core-app/03-api/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Validation

- Focused dashboard tracker-catalog gate passed with 4 suites and 15 tests:
  `CI=true npm test -- --watchAll=false --runTestsByPath
  src/hooks/useTrackerSchema.test.js src/services/apiEndpoints.test.js
  src/components/TrackerSelector.test.js
  src/components/TrackerStatusCard.test.js`.
- Dashboard production build passed:
  `npm run build`.
- Docs/hygiene gate passed with 2 tests:
  `tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
  and
  `tests/test_test_hygiene.py::test_dashboard_does_not_reconstruct_direct_backend_urls_outside_endpoint_registry`.
- Stale tracker-catalog wording scan returned no matches for current docs and
  dashboard sources.
- `git diff --check` passed.
- `PYTHON=.venv/bin/python make phase0-check` passed with schema current,
  generated API/MCP candidate inventory current, 393 tests passed, and one
  existing Starlette/httpx deprecation warning.

## Independent Review

- Initial independent read-only review found one blocker: malformed typed
  catalog object payloads such as `{}` could be normalized into empty/default
  dashboard state instead of surfacing an error.
- Fixed the blocker by validating the required typed catalog contract before
  normalization and by adding focused tests for malformed object payloads and
  `403` policy failures that must not fall back to legacy reads.
- Final independent read-only recheck found no blockers. It verified typed
  payload validation before normalization, non-fallback regression tests for
  `403` and malformed object payloads, fallback limited to `404`/`405`/`501`
  or typed `unavailable` with no entries, unchanged legacy mutation endpoints,
  production remote path allowlisting, checkpoint claim-boundary consistency,
  and `git diff --check`.

## Remaining

- Design typed tracker mutation/restart/configuration actions with
  confirmation, idempotency, audit, and fail-closed behavior before retiring
  legacy mutation routes.
- Add fallback telemetry and structured deprecation tracking for the remaining
  legacy tracker catalog/config read compatibility paths.
- Retire compatibility aliases only after dashboard/client adoption evidence
  and a tracked removal gate.
- Continue dashboard/toolchain modernization and the final PXE-0074 clean
  temporary-checkout setup walkthrough before release/tag/handoff.

## Claim Boundary

This slice proves only dashboard client preference for the typed catalog
contract under unit/build validation. It does not prove tracker start,
reacquisition, follower response, PX4 interaction, QGC playback, SITL/HIL,
field behavior, deployment readiness, or real-aircraft safety.
