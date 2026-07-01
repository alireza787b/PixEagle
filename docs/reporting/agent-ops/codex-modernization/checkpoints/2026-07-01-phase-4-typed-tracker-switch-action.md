# Phase 4 Typed Tracker Switch Action

Date: 2026-07-01

## Scope

PXE-0008 partial. Promote tracker selection from legacy-only
`/api/tracker/switch` to typed `POST /api/v1/actions/tracker-switch` while
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
- `src/classes/api_legacy_tracker_routes.py`
- `src/classes/api_security_policy.py`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/hooks/useTrackerSchema.js`
- `dashboard/e2e/production-remote.spec.js`
- `tests/test_api_route_inventory.py`
- `tests/test_api_security_policy.py`
- `tests/test_api_tool_candidates.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/unit/core_app/test_api_legacy_tracker_routes.py`
- `dashboard/src/hooks/useTrackerSchema.test.js`
- `dashboard/src/services/apiEndpoints.test.js`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- API/tracker/reporting docs listed in this checkpoint.

## Implementation

- Added `APITrackerSwitchRequest` and `tracker_switch` action response type.
- Added canonical path `API_V1_ACTION_TRACKER_SWITCH_PATH`.
- Added typed action route metadata for `POST /api/v1/actions/tracker-switch`.
- Added action execution with:
  - dry-run validation;
  - confirmation and idempotency preconditions;
  - schema-manager selectable-tracker validation before mutation;
  - idempotent replay;
  - local configured-state verification after legacy execution;
  - typed action records and structured typed errors.
- Extracted `switch_tracker_to_type()` from the legacy helper so typed and
  legacy callers share current schema-manager and `AppController` behavior.
- Classified the typed route under `AUTH_ACTION_EXECUTE` with session CSRF and
  security-critical audit policy.
- Migrated dashboard tracker switch/change flows to the typed action request
  envelope and legacy fallback only for typed-route absence/unsupported status.
- Normalized nested typed API error envelopes to string dashboard messages so
  object-shaped `detail` payloads from auth, validation, or semantic failures
  cannot be rendered as raw React children.
- Regenerated the API/MCP candidate inventory. The new candidate is blocked,
  unregistered, non-callable, and excluded from `agent_tools.yaml`.

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py`
  - 69 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/unit/core_app/test_app_controller_offboard_safety.py -k "tracker_switch or tracking_catalog or legacy_tracker or api_v1_tracker_switch"`
  - 37 passed, 97 deselected.
- `CI=true npm test -- --watchAll=false --runTestsByPath src/hooks/useTrackerSchema.test.js src/services/apiEndpoints.test.js src/components/TrackerSelector.test.js`
  - 3 suites passed, 16 tests passed.
- `npm run build`
  - dashboard production build compiled successfully.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist tests/test_test_hygiene.py::test_dashboard_does_not_reconstruct_direct_backend_urls_outside_endpoint_registry`
  - 2 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_production_remote_browser_e2e.py`
  - 17 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_exposure_policy.py -k "security_critical or api_v1_actions or offboard-stop"`
  - 3 passed, 80 deselected, one existing Starlette/httpx deprecation warning.
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current, API/MCP candidate inventory current, 393 passed, one
    existing Starlette/httpx deprecation warning.
- Independent read-only reviewer found one blocker: typed action failures with
  object-shaped `detail` payloads could be stored as dashboard text and crash
  rendering. The dashboard hook now normalizes typed error envelopes to strings,
  the regression test uses an object-shaped typed `detail`, the reviewer agent
  was closed, and the post-fix frontend/backend/build/diff/stale-doc gates
  above passed.

## Risks And Open Questions

- Legacy `/api/tracker/switch` remains registered for compatibility.
- At that checkpoint, tracker restart and broader tracker configuration
  mutation remained legacy. Tracker restart was closed by the later typed
  tracker-restart action slice, leaving broader configuration mutation open.
- Dashboard fallback telemetry/deprecation counters are not implemented yet.
- This slice validates PixEagle process-local behavior only; it does not prove
  tracker runtime output, follower response, PX4 observation, or field behavior.

## Next Slice

Continue PXE-0008 with typed tracker configuration mutation design or fallback
telemetry/deprecation tracking for legacy tracker catalog/config compatibility
reads, then continue toward compatibility-retirement planning. Tracker restart
was closed by the later typed tracker-restart action slice.
