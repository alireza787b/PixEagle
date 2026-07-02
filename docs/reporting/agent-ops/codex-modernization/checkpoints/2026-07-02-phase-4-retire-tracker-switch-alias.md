# Phase 4 Retire Tracker Switch Alias

Date: 2026-07-02

## Scope

PXE-0008 partial. Retire the public `POST /api/tracker/switch` route after
typed tracker-switch and dashboard typed-action adoption are in place.

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
- `dashboard/src/hooks/useTrackerSchema.js`
- `dashboard/src/hooks/useTrackerSchema.test.js`
- `tests/unit/core_app/test_api_legacy_tracker_routes.py`
- `tests/test_api_route_inventory.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/route-inventory.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md`
- `docs/trackers/06-integration/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`

## Implementation

- Removed public `POST /api/tracker/switch` route registration from
  `FastAPIHandler`.
- Removed the handler wrapper/import and the legacy request-parsing
  `switch_tracker()` helper.
- Kept internal `switch_tracker_to_type()` because typed
  `POST /api/v1/actions/tracker-switch` still uses it as the existing
  AppController switch executor.
- Removed the route from default-deny API security policy and frozen route
  inventory.
- Removed dashboard `trackerSwitch` endpoint constant and the fallback path
  from typed tracker-switch action to the retired legacy route.
- Removed active `switch` metadata from backend legacy tracker compatibility
  counters so the typed catalog reports only currently registered tracker
  compatibility routes.

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/unit/core_app/test_app_controller_offboard_safety.py -k 'tracker_switch or legacy_tracker or tracking_catalog'`
  - 34 passed, 102 deselected.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py`
  - 69 passed.
- `CI=true npm test -- --watchAll=false --runTestsByPath src/services/apiEndpoints.test.js src/hooks/useTrackerSchema.test.js`
  - 2 suites passed, 16 tests passed.
- `bash scripts/check_schema.sh`
  - Schema is up to date.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
  - 1 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_tracker_routes.py src/classes/fastapi_handler.py src/classes/api_security_policy.py tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py`
  - Passed.
- `CI=true npm run build`
  - Dashboard production build compiled successfully.
- `git diff --check`
  - Passed.
- `PYTHON=.venv/bin/python make phase0-check`
  - Schema check and API tool candidate inventory check passed.
  - 393 tests passed, with the existing Starlette/httpx deprecation warning.

## Risks And Open Questions

- Existing external clients still calling `/api/tracker/switch` now receive the
  normal missing-route behavior. This is intentional retirement after typed
  tracker-switch and dashboard migration.
- Remaining legacy tracker catalog/config, restart, and diagnostic aliases
  still need retirement planning.
- Broader tracker configuration mutation remains legacy and needs a separate
  typed action/config design.

## Independent Review

- Read-only explorer review found no blockers.
- Verified no active route registration, dashboard endpoint constant, public
  helper export, dispatch wrapper, or `LEGACY_TRACKER_ROUTE_METADATA["switch"]`
  remains for public `POST /api/tracker/switch`.
- Verified typed `POST /api/v1/actions/tracker-switch` remains registered and
  still reaches internal `switch_tracker_to_type()`.
- Verified route inventory, API security policy, and generated tool candidate
  inventory align with removing one POST route.
- Reviewer noted the core API overview used broad `/api/tracker/*` wording. That
  non-blocking wording issue was tightened in this slice so the overview now
  points to typed tracker actions plus selected remaining compatibility routes.

## Next Slice

Continue PXE-0008 with typed tracker configuration mutation design or
compatibility-retirement planning for the remaining legacy tracker routes.
