# Phase 4 Backend Tracker Compatibility Deprecation Counters

Date: 2026-07-02

## Scope

PXE-0008 partial. Add backend process-local observability for attempted legacy
tracker compatibility route usage and expose that snapshot through the typed
tracker catalog.

This slice does not add or remove HTTP routes, retire aliases, add durable audit
logging, promote MCP/runtime tools, validate QGC media, run PX4/SITL/HIL or
field tests, perform deployment/service actions, prove tracker runtime success,
or claim real-aircraft behavior.

## Files Changed

- `src/classes/api_legacy_tracker_routes.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_snapshots.py`
- `src/classes/fastapi_handler.py`
- `tests/unit/core_app/test_api_legacy_tracker_routes.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `tests/test_api_route_inventory.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/core-app/03-api/README.md`
- `docs/trackers/06-integration/README.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`

## Implementation

- Added `LEGACY_TRACKER_ROUTE_METADATA` for public legacy
  `/api/tracker/*` compatibility routes, including selector/config routes,
  switch/restart compatibility routes, deprecated `set-type`, and tracker
  diagnostics.
- Added thread-safe process-local counters with reset, record, and snapshot
  helpers.
- Counted attempted public legacy route handling, including failing requests,
  so deprecation pressure is visible before alias retirement planning.
- Kept internal typed-action helper reuse from skewing legacy route usage:
  typed tracker restart calls the shared restart helper with
  `record_compatibility_usage=false`.
- Added typed Pydantic response models for the embedded
  `legacy_compatibility` snapshot.
- Embedded the snapshot in typed `GET /api/v1/tracking/catalog`.
- Regenerated the non-callable API/MCP candidate inventory after provenance
  hashes changed.

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py`
  - 32 tests passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_app_controller_offboard_safety.py -k tracking_catalog`
  - 3 passed, 107 deselected.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`
  - Initial run found expected generated candidate hash drift.
  - After regeneration, 50 tests passed.
- `bash scripts/check_schema.sh`
  - schema current.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
  - 1 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_tracker_routes.py src/classes/api_v1_contracts.py src/classes/api_v1_snapshots.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_tracker_routes.py tests/unit/core_app/test_app_controller_offboard_safety.py tests/test_api_route_inventory.py`
  - passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python - <<'PY' ... import classes.api_v1_contracts ... PY`
  - passed and confirmed importing typed API contracts does not import
    `classes.api_legacy_tracker_routes`.
- `git diff --check`
  - passed.
- `PYTHON=.venv/bin/python make phase0-check`
  - schema current, generated API/MCP candidate inventory current, 393 tests
    passed, and one existing Starlette/httpx deprecation warning.

## Risks And Open Questions

- Counters are volatile process-local state. They reset on process restart and
  are not a durable audit log.
- Counts represent attempted route handling, not successful legacy request
  completion.
- The snapshot is embedded in the typed tracker catalog because that catalog is
  already the typed tracker migration read surface. If future policy requires
  separate administrative observability, this can move to a dedicated typed
  diagnostics route.
- Compatibility aliases remain registered.
- Broader tracker configuration mutation remains legacy and needs separate
  typed action/config design.

## Independent Review

- Read-only independent review found one blocker: `api_v1_contracts.py` was
  importing the legacy tracker route helper only to reuse the claim-boundary
  constant, which made typed API contract imports pull legacy route dependencies
  and AI availability probes.
- Fixed by making `api_v1_contracts.py` own
  `LEGACY_TRACKER_COMPATIBILITY_CLAIM_BOUNDARY` directly and having the legacy
  tracker route helper reuse that constant.
- Import smoke test confirmed `classes.api_v1_contracts` no longer imports
  `classes.api_legacy_tracker_routes`.
- Reviewer found no other blockers and confirmed the counter semantics,
  internal typed restart bypass, test coverage, and generated inventory scope.

## Next Slice

Continue PXE-0008 with typed tracker configuration mutation design or tracked
compatibility-retirement planning for legacy tracker routes.
