# Phase 4 Retire Tracker Restart Alias

Date: 2026-07-02

## Scope

PXE-0008 partial. Retire the public `POST /api/tracker/restart` route after
typed tracker-restart and dashboard typed-action adoption are in place.

This slice removes one legacy HTTP route. It does not redesign broader tracker
configuration mutation, retire the remaining tracker catalog/config/diagnostic
compatibility routes, promote MCP/runtime tools, validate QGC media, run
PX4/SITL/HIL or field tests, perform deployment/service actions, prove tracker
runtime success, or claim real-aircraft behavior.

## Files Changed

- `src/classes/api_legacy_tracker_routes.py`
- `src/classes/fastapi_handler.py`
- `src/classes/api_security_policy.py`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/components/config/ReloadTierBadge.js`
- `tests/unit/core_app/test_api_legacy_tracker_routes.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_security_policy.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/route-inventory.md`
- `docs/core-app/03-api/README.md`
- `docs/core-app/04-configuration/hot-reload-guide.md`
- `docs/developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md`
- `docs/trackers/06-integration/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`

## Implementation

- Removed public `POST /api/tracker/restart` route registration from
  `FastAPIHandler`.
- Removed the handler wrapper and simplified typed tracker-restart execution to
  call the internal `restart_tracker()` helper directly.
- Kept internal `restart_tracker()` because typed
  `POST /api/v1/actions/tracker-restart` still uses it as the existing config
  reload, rate-limit, and tracker reinitialize executor.
- Removed the route from default-deny API security policy and frozen route
  inventory.
- Removed dashboard `trackerRestart` endpoint constant and the hidden
  `ReloadTierBadge` legacy restart URL.
- Removed active `restart` metadata from backend legacy tracker compatibility
  counters so the typed catalog reports only currently registered tracker
  compatibility routes.

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py -q`
  - 95 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_tracker_routes.py src/classes/fastapi_handler.py src/classes/api_security_policy.py tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py tests/test_api_security_policy.py`
  - Passed.
- `bash scripts/check_schema.sh`
  - Schema is up to date.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
  - 1 passed.
- `CI=true npm test -- --watchAll=false --runTestsByPath src/services/apiEndpoints.test.js`
  - 1 suite passed, 2 tests passed.
- `CI=true npm run build`
  - Dashboard production build compiled successfully.
- `git diff --check`
  - Passed.
- `PYTHON=.venv/bin/python make phase0-check`
  - Schema check and API tool candidate inventory check passed.
  - 393 tests passed, with the existing Starlette/httpx deprecation warning.

## Risks And Open Questions

- Existing external clients still calling `/api/tracker/restart` now receive the
  normal missing-route behavior. This is intentional retirement after typed
  tracker-restart and dashboard migration.
- Remaining legacy tracker catalog/config and diagnostic aliases still need
  retirement planning.
- Broader tracker configuration mutation remains legacy and needs a separate
  typed action/config design.

## Independent Review

- Read-only explorer review found no blockers.
- Verified public route registration, dashboard endpoint constant,
  `FastAPIHandler` public wrapper, security-policy classification, and
  `LEGACY_TRACKER_ROUTE_METADATA["restart"]` are gone for public
  `POST /api/tracker/restart`.
- Verified typed `POST /api/v1/actions/tracker-restart` remains registered and
  still reaches internal `restart_tracker()` through
  `_execute_tracker_restart_action()`.
- Verified route inventory, API security policy, and generated tool candidate
  inventory align with removing one POST route.
- Verified active docs point users to typed tracker-restart and mark the legacy
  restart route retired. Remaining legacy tracker read/diagnostic aliases are
  still active by design.

## Next Slice

Continue PXE-0008 with typed tracker configuration mutation design or
compatibility-retirement planning for the remaining legacy tracker catalog,
config, and diagnostic routes.
