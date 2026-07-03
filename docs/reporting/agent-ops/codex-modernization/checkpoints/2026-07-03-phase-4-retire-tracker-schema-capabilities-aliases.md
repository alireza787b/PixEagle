# Phase 4 Checkpoint: Retire Tracker Schema/Capabilities Diagnostic Aliases

Date: 2026-07-03  
Issue: PXE-0008  
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

Retired the final public legacy tracker diagnostic aliases after typed tracker
catalog schema metadata and dashboard typed-catalog adoption were in place:

- `GET /api/tracker/schema`
- `GET /api/tracker/capabilities`

No public legacy tracker diagnostic route remains registered after this slice.

## Files Changed

- `src/classes/fastapi_handler.py`
- `src/classes/api_legacy_tracker_routes.py`
- `src/classes/api_security_policy.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_snapshots.py`
- `tests/test_api_route_inventory.py`
- `tests/unit/core_app/test_api_legacy_tracker_routes.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `dashboard/src/hooks/useTrackerSchema.js`
- `dashboard/src/hooks/useTrackerSchema.test.js`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/src/services/apiEndpoints.test.js`
- `dashboard/e2e/production-remote.spec.js`
- `docs/agent-context/README.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/route-inventory.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md`
- `docs/trackers/06-integration/README.md`
- `docs/trackers/06-integration/external-systems.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Behavior

- Typed `GET /api/v1/tracking/catalog` now carries tracker data-type schemas as
  `data_type_schemas`.
- Dashboard tracker schema metadata reads the typed tracker catalog through
  `useTrackerSchema()` without fallback to retired legacy aliases.
- Malformed typed tracker catalog payloads fail visibly and do not trigger a
  legacy fallback.
- `/api/system/schema_info` now lists schema and capabilities under retired
  tracker diagnostic routes.
- The typed tracker catalog no longer carries the obsolete
  `legacy_compatibility` counter object because no public legacy tracker
  diagnostic alias remains.
- `api_legacy_tracker_routes.py` now retains only internal
  `switch_tracker_to_type()` and `restart_tracker()` executors used by typed
  tracker actions.
- Static route inventory now reports 125 declared route pairs, 123 declared
  HTTP route pairs, and 67 GET route pairs.

## Validation

Focused checks run before checkpoint creation:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile src/classes/api_legacy_tracker_routes.py src/classes/fastapi_handler.py src/classes/api_v1_contracts.py src/classes/api_v1_snapshots.py tests/test_api_route_inventory.py tests/unit/core_app/test_api_legacy_tracker_routes.py tests/unit/core_app/test_app_controller_offboard_safety.py
```

Result: passed.

```bash
node -c dashboard/src/hooks/useTrackerSchema.js && node -c dashboard/src/services/apiEndpoints.js
```

Result: passed.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_tracking_catalog_reports_schema_and_builtin_types tests/unit/core_app/test_app_controller_offboard_safety.py::test_schema_info_does_not_advertise_retired_tracker_fallbacks tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_tracking_catalog_degrades_when_schema_manager_fails -q
```

Result: 68 passed after removing the obsolete tracker legacy counter contract.

```bash
CI=true npm test -- --watchAll=false --runInBand src/hooks/useTrackerSchema.test.js src/services/apiEndpoints.test.js src/components/TrackerStatusCard.test.js
```

Result: 3 suites passed, 24 tests passed.

```bash
.venv/bin/python tools/generate_api_tool_candidates.py --check
bash scripts/check_schema.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_tool_candidates.py tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist -q
```

Result: generated candidate inventory current; schema current; 11 passed.

```bash
git diff --check
CI=true npm run build
PYTHON=.venv/bin/python make phase0-check
```

Result: whitespace check clean; dashboard production build passed;
`phase0-check` passed with schema current, generated API/MCP candidate
inventory current, 393 tests passed, and one existing Starlette/httpx
deprecation warning. These broader gates were rerun after the blocker fix.

Independent review:

- First restarted read-only review found one blocker: the retired routes were
  not callable, but the empty `legacy_compatibility` counter contract still
  remained in `api_legacy_tracker_routes.py`, `api_v1_contracts.py`,
  `api_v1_snapshots.py`, tests, and docs.
- Fixed by removing the tracker legacy counter helpers, metadata, Pydantic
  models, typed catalog field, active docs, and reporting claims. Follow-up
  validation and review are recorded after that fix.
- Follow-up read-only review found no blockers and no non-blockers. It
  confirmed the retired schema/capabilities routes are not registered, the
  tracker helper exports only `switch_tracker_to_type()` and
  `restart_tracker()`, typed catalog carries `data_type_schemas` without
  `legacy_compatibility`, dashboard schema reads use typed catalog only,
  active docs point to the typed catalog, and route/candidate counts align.

## Claim Boundary

This checkpoint is an API/dashboard/docs cleanup and compatibility retirement
slice only. It does not claim tracker runtime success, follower response, PX4,
SITL, HIL, field behavior, QGC media playback, service/deployment readiness,
MCP runtime promotion, or real-aircraft behavior.

## Risks And Open Questions

- Any third-party clients still calling the retired legacy schema/capabilities
  diagnostic aliases must move to typed `GET /api/v1/tracking/catalog`.
- The typed catalog now exposes schema-manager data through `data_type_schemas`;
  future schema format changes must stay covered by typed contract and
  dashboard malformed-payload tests.
- Broader typed tracker configuration mutation design remains open.

## Next Planned Slice

Continue PXE-0008 with typed tracker configuration mutation design or the next
highest-value legacy route family discovered by static route-boundary guards.
