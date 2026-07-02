# Phase 4 Retire Tracker Set-Type Alias

Date: 2026-07-02

## Scope

PXE-0008 partial. Retire the public deprecated
`POST /api/tracker/set-type` route after typed tracker-switch and dashboard
typed-action adoption are in place.

This slice removes one legacy HTTP route. It does not redesign broader tracker
configuration mutation, retire the remaining tracker compatibility routes,
promote MCP/runtime tools, validate QGC media, run PX4/SITL/HIL or field tests,
perform deployment/service actions, prove tracker runtime success, or claim
real-aircraft behavior.

## Files Changed

- `src/classes/api_legacy_tracker_routes.py`
- `src/classes/fastapi_handler.py`
- `src/classes/api_security_policy.py`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/hooks/useTrackerSchema.test.js`
- `tests/unit/core_app/test_api_legacy_tracker_routes.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/test_api_route_inventory.py`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/route-inventory.md`
- `docs/core-app/03-api/README.md`
- `docs/developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md`
- `docs/trackers/06-integration/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`

## Implementation

- Removed `POST /api/tracker/set-type` route registration from
  `FastAPIHandler`.
- Removed the handler wrapper/import and the direct legacy
  `set_tracker_type()` helper that mutated `smart_mode_active` and
  `current_tracker_type` outside the typed action contract.
- Removed the route from the default-deny API security policy and frozen route
  inventory.
- Removed the dashboard `trackerSetType` endpoint constant.
- Removed active `set_type` metadata from backend legacy tracker compatibility
  counters so the typed catalog reports only currently registered tracker
  compatibility routes.
- Kept typed `POST /api/v1/actions/tracker-switch` as the new-client path and
  legacy `POST /api/tracker/switch` as the rolling compatibility fallback.

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/unit/core_app/test_app_controller_offboard_safety.py -k 'tracking_catalog or legacy_tracker'`
  - 29 passed, 107 deselected.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py`
  - Initial run found the expected route-method count and generated candidate
    hash drift after removing one POST route.
  - After updating the frozen count and regenerating
    `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`,
    69 passed.
- `CI=true npm test -- --watchAll=false --runTestsByPath src/services/apiEndpoints.test.js src/hooks/useTrackerSchema.test.js`
  - 2 suites passed, 16 tests passed.
- `bash scripts/check_schema.sh`
  - schema current.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
  - 1 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_tracker_routes.py src/classes/fastapi_handler.py src/classes/api_security_policy.py tests/unit/core_app/test_api_legacy_tracker_routes.py tests/unit/core_app/test_app_controller_offboard_safety.py tests/test_api_route_inventory.py`
  - passed.
- `CI=true npm run build`
  - passed.
- `git diff --check`
  - passed.
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current, generated API/MCP candidate inventory current, 393 tests
    passed, and one existing Starlette/httpx deprecation warning.

## Risks And Open Questions

- Existing external clients still calling `/api/tracker/set-type` now receive
  the normal missing-route behavior. This is intentional retirement after typed
  tracker-switch and dashboard migration.
- Remaining legacy tracker catalog/config, switch/restart, and diagnostic
  aliases still need retirement planning.
- Broader tracker configuration mutation remains legacy and needs a separate
  typed action/config design.

## Independent Review

- Read-only independent review found no blockers.
- Reviewer confirmed no active backend, dashboard, test, or generated
  candidate path still registers, calls, exports, or counts
  `POST /api/tracker/set-type`, `set_tracker_type`,
  `dispatch_set_tracker_type`, `trackerSetType`, or active `set_type` counter
  metadata.
- Reviewer confirmed `/api/tracker/switch`, `/api/tracker/restart`, and typed
  `/api/v1/actions/tracker-switch` remain registered/covered, route inventory
  and security policy are aligned, generated candidate inventory reflects 133
  HTTP routes, and active docs state that `set-type` is retired.
- Residual non-blocking note: older chronological reporting rows still describe
  the route as it existed before this retirement, and the new retirement row
  plus current summary supersede them.

## Next Slice

Continue PXE-0008 with typed tracker configuration mutation design or
compatibility-retirement planning for the remaining legacy tracker routes.
