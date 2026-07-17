# Phase 4 Checkpoint: Retire Tracker Runtime/Output Diagnostic Aliases

Date: 2026-07-02  
Issue: PXE-0008  
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Scope

Retired the public legacy tracker runtime/output diagnostic aliases after typed
runtime and telemetry routes plus dashboard typed-telemetry adoption were in
place:

- `GET /api/tracker/current-status`
- `GET /api/tracker/output`

The remaining public legacy tracker diagnostic routes are:

- `GET /api/tracker/schema`
- `GET /api/tracker/capabilities`

Later update: both remaining schema/capabilities diagnostic aliases were
retired by
`2026-07-03-phase-4-retire-tracker-schema-capabilities-aliases.md`; no public
legacy tracker diagnostic route remains after that checkpoint.

## Files Changed

- `src/classes/fastapi_handler.py`
- `src/classes/api_legacy_tracker_routes.py`
- `src/classes/api_security_policy.py`
- `tests/test_api_route_inventory.py`
- `tests/unit/core_app/test_api_legacy_tracker_routes.py`
- `tests/unit/core_app/test_app_controller_offboard_safety.py`
- `dashboard/src/hooks/useTrackerSchema.js`
- `dashboard/src/hooks/useTrackerSchema.test.js`
- `dashboard/src/pages/TrackerPage.js`
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

- Dashboard tracker status and output views now consume typed
  `GET /api/v1/tracking/telemetry` without fallback to retired aliases.
- Malformed typed tracking telemetry is treated as an error and does not trigger
  a silent legacy fallback.
- Typed `GET /api/v1/tracking/runtime-status` remains the runtime-read contract;
  typed telemetry remains the geometry/raw-output contract.
- `/api/system/schema_info` now lists `current-status` and `output` under
  retired tracker diagnostic routes instead of remaining diagnostics.
- The typed tracker catalog `legacy_compatibility` snapshot now lists only
  currently registered tracker diagnostic aliases: `schema` and `capabilities`.
- Static route inventory now reports 127 declared route pairs, 125 declared
  HTTP route pairs, and 69 GET route pairs.

## Validation

Focused checks run before checkpoint creation:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m py_compile src/classes/api_legacy_tracker_routes.py src/classes/fastapi_handler.py tests/test_api_route_inventory.py tests/unit/core_app/test_api_legacy_tracker_routes.py tests/unit/core_app/test_app_controller_offboard_safety.py
```

Result: passed.

```bash
node -c dashboard/src/hooks/useTrackerSchema.js && node -c dashboard/src/services/apiEndpoints.js && node -c dashboard/src/pages/TrackerPage.js
```

Result: passed.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/unit/core_app/test_app_controller_offboard_safety.py::test_schema_info_does_not_advertise_retired_tracker_fallbacks tests/unit/core_app/test_app_controller_offboard_safety.py::test_api_v1_tracking_catalog_reports_schema_and_builtin_types -q
```

Result: 72 passed.

```bash
CI=true npm test -- --watchAll=false --runInBand src/hooks/useTrackerSchema.test.js src/services/apiEndpoints.test.js src/components/TrackerStatusCard.test.js
```

Result: 3 suites passed, 22 tests passed.

```bash
.venv/bin/python tools/generate_api_tool_candidates.py --check
bash scripts/check_schema.sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_tool_candidates.py tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist -q
```

Result: candidate inventory current; schema current; 11 passed.

```bash
git diff --check
CI=true npm run build
PYTHON=.venv/bin/python make phase0-check
```

Result: whitespace check clean; dashboard production build passed;
`phase0-check` passed with 393 tests and one existing Starlette/httpx
deprecation warning.

Independent review:

- Read-only reviewer found no blockers.
- Reviewer confirmed backend registrations/security/counters only keep
  `schema` and `capabilities`, retired paths only appear in schema-info retired
  metadata, dashboard status/output hooks use typed telemetry, old endpoint
  constants are undefined in tests, route/candidate counts align, and active
  docs describe `current-status`/`output` as retired.
- Reviewer's residual dashboard-build gap was covered locally by the successful
  `CI=true npm run build` recorded above. The existing FollowerPage rolling
  update fallback to `/telemetry/tracker_data` was explicitly out of scope for
  this alias-retirement slice and remains a separate dashboard/API normalization
  concern.

## Claim Boundary

This checkpoint is an API/dashboard/docs cleanup and compatibility retirement
slice only. It does not claim tracker runtime success, follower response, PX4,
SITL, HIL, field behavior, QGC media playback, service/deployment readiness,
MCP runtime promotion, or real-aircraft behavior.

## Risks And Open Questions

- Any third-party clients still calling the retired legacy runtime/output
  diagnostic aliases must move to typed `GET /api/v1/tracking/runtime-status`
  and `GET /api/v1/tracking/telemetry`.
- At this checkpoint the remaining public legacy tracker diagnostics were
  schema and capabilities only; both were later retired by the 2026-07-03
  schema/capabilities alias slice.
- Broader typed tracker configuration mutation design remains open.

## Next Planned Slice

Continue PXE-0008 with one of:

- typed tracker schema/capabilities replacement design, later completed by the
  2026-07-03 schema/capabilities alias slice;
- typed tracker configuration mutation design beyond switch/restart;
- dashboard/API client normalization for the next remaining legacy route family.
