# Phase 4 Checkpoint: Retire Tracker Catalog/Config Read Aliases

Date: 2026-07-02  
Issue: PXE-0008  
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

Retired the remaining public legacy tracker catalog/config read aliases after
typed `GET /api/v1/tracking/catalog` and dashboard typed-catalog adoption were
already in place:

- `GET /api/tracker/available`
- `GET /api/tracker/current`
- `GET /api/tracker/available-types`
- `GET /api/tracker/current-config`

At this checkpoint, the still-registered legacy tracker diagnostic routes were:

- `GET /api/tracker/schema`
- `GET /api/tracker/current-status`
- `GET /api/tracker/output`
- `GET /api/tracker/capabilities`

Later on 2026-07-02, `GET /api/tracker/current-status` and
`GET /api/tracker/output` were also retired by
`checkpoints/2026-07-02-phase-4-retire-tracker-runtime-output-aliases.md`.
Only `GET /api/tracker/schema` and `GET /api/tracker/capabilities` remained
registered after that follow-up slice. Both were later retired by
`checkpoints/2026-07-03-phase-4-retire-tracker-schema-capabilities-aliases.md`.

## Files Changed

- `src/classes/fastapi_handler.py`
- `src/classes/api_legacy_tracker_routes.py`
- `src/classes/api_security_policy.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `dashboard/src/hooks/useTrackerSchema.js`
- `dashboard/src/hooks/useTrackerSchema.test.js`
- `dashboard/src/components/TrackerSelector.js`
- `dashboard/src/components/TrackerSelector.test.js`
- `dashboard/src/components/TrackerStatusCard.js`
- `dashboard/src/components/TrackerStatusCard.test.js`
- `dashboard/src/services/apiEndpoints.js`
- `dashboard/e2e/production-remote.spec.js`
- `tests/test_api_route_inventory.py`
- `tests/unit/core_app/test_api_legacy_tracker_routes.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/route-inventory.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/developers/SCHEMA_DRIVEN_DEVELOPMENT_GUIDE.md`
- `docs/trackers/06-integration/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Behavior

- Dashboard tracker selector/current/config metadata now requires
  `GET /api/v1/tracking/catalog`.
- Missing, unsupported, auth-denied, policy-denied, or malformed typed catalog
  responses surface as errors instead of falling back to stale legacy aliases.
- The `legacy_compatibility` snapshot embedded in the typed tracker catalog now
  only listed the then-current public tracker diagnostic compatibility
  routes: `output`, `capabilities`, `schema`, and `current_status`.
  A later 2026-07-02 follow-up retired `output` and `current_status`, leaving
  `capabilities` and `schema` as the active diagnostic compatibility entries.
- Static route inventory now reports 129 declared route pairs, 127 declared
  HTTP route pairs, and 71 GET route pairs.
- Generic `/api/system/schema_info` compatibility metadata no longer advertises
  automatic fallback. It keeps the existing compatibility object but sets
  `automatic_fallback=false`, lists the then-remaining tracker diagnostic
  routes, and lists the retired tracker catalog/config aliases explicitly.

## Validation

Focused checks run:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py tests/test_api_security_policy.py -q
```

Result: 76 passed.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py tests/unit/core_app/test_api_legacy_tracker_routes.py tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_tracking_catalog_reports_schema_and_builtin_types -q
```

Result after reviewer fixes: 87 passed.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_app_controller_offboard_safety.py::test_schema_info_does_not_advertise_retired_tracker_fallbacks tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_tracking_catalog_reports_schema_and_builtin_types tests/test_api_route_inventory.py tests/test_api_security_policy.py -q
```

Result after schema-info cleanup: 61 passed.

```bash
CI=true npm test -- --watchAll=false --runInBand src/hooks/useTrackerSchema.test.js src/components/TrackerSelector.test.js src/components/TrackerStatusCard.test.js src/services/apiEndpoints.test.js
```

Result: 4 suites passed, 24 tests passed.

```bash
.venv/bin/python tools/generate_api_tool_candidates.py
.venv/bin/python tools/generate_api_tool_candidates.py --check
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_tool_candidates.py -q
```

Result: candidate inventory regenerated and checked current; 10 passed.

```bash
bash scripts/check_schema.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist -q
CI=true npm run build
PYTHON=.venv/bin/python make phase0-check
```

Result: schema current; generated API/MCP candidate inventory current; markdown
local-link gate passed; dashboard production build passed; phase0-check passed
with 393 tests and one existing Starlette/httpx deprecation warning.

Independent review:

- First reviewer pass found blockers in stale dashboard error visibility and docs
  wording. Fixed by surfacing typed catalog errors in the selector/status card
  even when stale data exists, and by clarifying historical route-boundary docs.
- Second reviewer pass found no blockers. A non-blocking generic
  `/api/system/schema_info` automatic-fallback claim was fixed in this slice and
  covered by `test_schema_info_does_not_advertise_retired_tracker_fallbacks`.

## Claim Boundary

This checkpoint is an API/dashboard/docs cleanup and compatibility retirement
slice only. It does not claim tracker runtime success, follower response, PX4,
SITL, HIL, field behavior, QGC media playback, service/deployment readiness,
MCP runtime promotion, or real-aircraft behavior.

## Risks And Open Questions

- Any third-party clients still calling the retired legacy catalog/config read
  aliases must move to `GET /api/v1/tracking/catalog`.
- Remaining tracker diagnostic compatibility routes still need typed
  replacement/retirement planning.
- Broader typed tracker configuration mutation design remains open.

## Next Planned Slice

Continue PXE-0008 with one of:

- typed tracker diagnostic/schema replacement design for
  `schema`, `current-status`, `output`, and `capabilities`;
- typed tracker configuration mutation design beyond switch/restart;
- dashboard/API client normalization for the remaining direct diagnostic reads.
