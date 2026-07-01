# Phase 4 Dashboard Tracker Compatibility Fallback Telemetry

Date: 2026-07-01

## Scope

PXE-0008 partial. Make dashboard fallback from typed tracker APIs to legacy
tracker compatibility routes visible, bounded, and test-covered.

This slice does not add backend routes, server-side deprecation counters,
alias retirement, MCP promotion, QGC media validation, PX4/SITL/HIL, field
testing, deployment action, tracker runtime success evidence, or real-aircraft
behavior.

## Files Changed

- `dashboard/src/hooks/useTrackerSchema.js`
- `dashboard/src/hooks/useTrackerSchema.test.js`
- `docs/core-app/03-api/README.md`
- `docs/trackers/06-integration/README.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`

## Implementation

- Added structured dashboard compatibility fallback telemetry for:
  - typed tracker selection catalog fallback to legacy available-types and
    current-config reads;
  - typed available-trackers catalog fallback to legacy available tracker read;
  - typed current-tracker catalog fallback to legacy current tracker read;
  - typed tracker-switch action fallback to legacy switch mutation.
- Added bounded in-memory history for the last 50 attempted fallback events.
- Added browser event dispatch through
  `pixeagle:tracker-compatibility-fallback`.
- Kept fallback limited to missing or explicitly unsupported typed routes:
  `404`, `405`, `501`, or the existing typed unavailable/no-entry condition.
- Kept auth, policy, and malformed typed payload failures fail-closed with no
  legacy fallback.
- Updated docs to make deprecated `/api/tracker/set-type` compatibility-only
  and to point new tracker-selection clients to
  `POST /api/v1/actions/tracker-switch`.

## Validation

- `CI=true npm test -- --watchAll=false --runTestsByPath src/hooks/useTrackerSchema.test.js`
  - 14 tests passed.
- `CI=true npm test -- --watchAll=false --runTestsByPath src/hooks/useTrackerSchema.test.js src/services/apiEndpoints.test.js src/components/TrackerSelector.test.js src/components/TrackerStatusCard.test.js`
  - 4 suites passed, 21 tests passed.
- `CI=true npm run build`
  - dashboard production build passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
  - 1 passed.
- `git diff --check`
  - passed.
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current, generated API/MCP candidate inventory current, 393 tests
    passed, and one existing Starlette/httpx deprecation warning.

## Independent Review

- Read-only independent blocker review found no blockers.
- Reviewer confirmed fallback is still gated to `404`, `405`, `501`, or the
  existing typed unavailable/no-entry case, and that telemetry is recorded only
  after the fallback gate.
- Reviewer noted residual gaps: available/current negative no-fallback tests
  are not duplicated per hook; fallback events are volatile client-side
  diagnostics; and the typed unavailable/no-entry fallback remains a policy
  decision. Added direct test coverage for the 50-event cap and clarified that
  events mean fallback was attempted, not that the legacy request succeeded.

## Risks And Open Questions

- This is client-side dashboard telemetry only. It records attempted fallback
  before the legacy request completes, does not persist across page reloads,
  and is not a backend audit log.
- Server-side structured deprecation counters for legacy tracker routes remain
  open.
- Available/current auth-policy negative tests rely on the shared fallback
  helper and existing selection/action negative tests rather than duplicated
  per-hook cases.
- The pre-existing typed catalog `unavailable` with no entries fallback remains
  active by design; tightening it to HTTP route-missing/unsupported only would
  be a separate product/API decision.
- Compatibility aliases remain registered.
- Broader tracker configuration mutation remains legacy and needs separate
  design.
- This slice does not prove tracker runtime output, follower response, PX4
  observation, SITL/HIL, field behavior, QGC media behavior, deployment, or
  real-aircraft safety.

## Next Slice

Continue PXE-0008 with typed tracker configuration mutation design,
backend/server-side deprecation counters for legacy tracker catalog/config
routes, or compatibility-retirement planning.
