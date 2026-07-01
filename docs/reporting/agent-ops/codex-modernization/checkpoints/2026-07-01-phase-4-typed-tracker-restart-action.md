# Phase 4 Typed Tracker Restart Action

Date: 2026-07-01

## Scope

PXE-0008 partial. Promote tracker restart/config reload from legacy-only
`/api/tracker/restart` to typed `POST /api/v1/actions/tracker-restart` while
preserving the legacy route as a rolling-update compatibility fallback.

No tracker runtime success, PX4/SITL/HIL, field behavior, QGC media validation,
service/deployment action, alias retirement, MCP promotion, or real-aircraft
behavior is claimed.

## Files Changed

- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_paths.py`
- `src/classes/api_v1_actions.py`
- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/fastapi_handler.py`
- `src/classes/api_security_policy.py`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/e2e/production-remote.spec.js`
- `tests/test_api_route_inventory.py`
- `tests/test_api_security_policy.py`
- `tests/test_api_tool_candidates.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- API/tracker/reporting docs listed in this checkpoint.

## Implementation

- Added canonical path `API_V1_ACTION_TRACKER_RESTART_PATH`.
- Added `tracker_restart` to the typed action response/action type surface.
- Added typed action route metadata for
  `POST /api/v1/actions/tracker-restart`.
- Added action execution with:
  - dry-run validation;
  - confirmation and idempotency preconditions;
  - schema-manager validation for the currently configured tracker before
    mutation;
  - idempotent replay;
  - typed action records and structured typed errors;
  - compatibility execution through the existing legacy restart helper.
- Classified the typed route under `AUTH_ACTION_EXECUTE` with session CSRF and
  security-critical audit policy.
- Added dashboard endpoint-registry and production-remote allowlist coverage.
- Regenerated the API/MCP candidate inventory. The new candidate is blocked,
  unregistered, non-callable, and excluded from `agent_tools.yaml`.

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_v1_actions.py src/classes/api_v1_contracts.py src/classes/api_v1_paths.py src/classes/fastapi_api_v1_routes.py src/classes/fastapi_handler.py src/classes/api_security_policy.py`
  - passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py`
  - 69 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_app_controller_offboard_safety.py -k "tracker_restart or tracker_switch"`
  - 10 passed, 100 deselected.
- `CI=true npm test -- --watchAll=false --runTestsByPath src/services/apiEndpoints.test.js`
  - 1 suite passed, 2 tests passed.
- `bash scripts/check_schema.sh`
  - schema current.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py`
  - 50 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist tests/test_production_remote_browser_e2e.py`
  - 18 passed.
- `CI=true npm run build`
  - dashboard production build passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py --check`
  - generated API/MCP candidate inventory current.
- Stale tracker restart/configuration wording scan returned no matches for the
  current false-open patterns.
- `git diff --check`
  - passed.
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current, generated API/MCP candidate inventory current, 393 tests
    passed, and one existing Starlette/httpx deprecation warning.

## Independent Review

- Read-only independent blocker review found no blockers.
- The reviewer found one non-blocking static-cleanliness issue: two
  `FastAPIHandler` action-helper `Literal[...]` annotations omitted
  `tracker_restart`. Fixed before commit.
- Regenerated the API/MCP candidate inventory after that annotation-only
  handler change and reran the route/security/candidate, tracker action,
  generated-candidate, diff, and full phase0 gates.
- Residual slice-specific gaps: typed tracker-restart tests mock the executor,
  so they verify action-resource semantics but not the full legacy dispatch path
  through `api_legacy_tracker_routes.restart_tracker`; dashboard endpoint and
  production-remote allowlist coverage exist, but no browser-flow test submits
  tracker restart from the UI in this slice.

## Risks And Open Questions

- Legacy `/api/tracker/restart` remains registered for compatibility.
- Broader tracker configuration mutation remains legacy.
- Dashboard config UI restart-button migration is not claimed in this slice;
  this slice only adds typed endpoint-registry coverage.
- Dashboard fallback telemetry/deprecation counters are not implemented yet.
- Full legacy restart dispatch and UI submission are not validated by this
  slice's tests.
- This slice validates PixEagle process-local action behavior only; it does not
  prove tracker runtime output, follower response, PX4 observation, or field
  behavior.

## Next Slice

Continue PXE-0008 with typed tracker configuration mutation design or fallback
telemetry/deprecation tracking for legacy tracker catalog/config compatibility
reads, then continue toward compatibility-retirement planning.
