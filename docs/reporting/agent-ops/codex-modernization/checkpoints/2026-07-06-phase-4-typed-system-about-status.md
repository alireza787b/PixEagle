# Phase 4 Checkpoint - PXE-0084 Typed System/About Status

Date: 2026-07-06  
Branch: `codex/modernization-pxe0040-runtime-20260604`  
Slice: PXE-0084 typed About/System status  
Status: closed

## Summary

PXE-0084 adds a typed, read-only `GET /api/v1/system/about` route for PixEagle
version, repository, local git, backend process/video status, runtime metadata,
and read-only update-status placeholder metadata. The route is authenticated
with `system:read`, returns a typed `APISystemAboutResponse`, and explicitly
does not fetch, pull, restart services, check GitHub releases, or prove update
availability.

The dashboard About dialog now reads this typed route first. It falls back to
legacy `/api/system/config` only when the typed route is missing or unsupported
(`404`, `405`, or `501`), and it does not hide auth or server errors by falling
back. The generated API/MCP candidate inventory records the route as
documentation-stage review-only, non-callable, and `mcp_exposure: none`.

## Files Changed

- Backend/API contracts and route wiring:
  - `src/classes/api_v1_contracts.py`
  - `src/classes/api_v1_paths.py`
  - `src/classes/api_v1_read_routes.py`
  - `src/classes/api_v1_snapshots.py`
  - `src/classes/fastapi_api_v1_routes.py`
  - `src/classes/fastapi_handler.py`
  - `src/classes/api_security_policy.py`
- Dashboard:
  - `dashboard/src/components/NavigationDrawer.js`
  - `dashboard/src/components/NavigationDrawer.test.js`
  - `dashboard/src/services/apiEndpoints.js`
  - `dashboard/src/services/apiEndpoints.test.js`
- Tests and candidate generation:
  - `tests/unit/core_app/test_api_v1_system_about.py`
  - `tests/test_api_route_inventory.py`
  - `tests/test_api_security_policy.py`
  - `tests/test_api_tool_candidates.py`
  - `tools/generate_api_tool_candidates.py`
- Docs and reporting:
  - `docs/core-app/03-api/README.md`
  - `docs/apis/api-modernization-blueprint.md`
  - `docs/agent-context/README.md`
  - `docs/agent-context/agent_tools.yaml`
  - `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
  - `docs/reporting/agent-ops/codex-modernization/issue-register.md`
  - `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
  - `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- Dashboard focused tests:
  - Command: `npm test -- --runInBand --watchAll=false src/components/NavigationDrawer.test.js src/services/apiEndpoints.test.js`
  - Result: 2 suites passed, 6 tests passed.
  - Note: existing React Router v7 future-flag warnings were emitted.
- Backend/API/security/docs focused gate:
  - Command: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_security_policy.py tests/unit/core_app/test_api_v1_system_about.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_docs_infrastructure_consistency.py tests/unit/core_app/test_parameters_reload.py`
  - Result: 112 passed.
- Backend syntax/import check:
  - Command: `.venv/bin/python -m py_compile src/classes/api_v1_contracts.py src/classes/api_v1_paths.py src/classes/api_v1_read_routes.py src/classes/api_v1_snapshots.py src/classes/fastapi_api_v1_routes.py src/classes/fastapi_handler.py src/classes/api_security_policy.py tools/generate_api_tool_candidates.py`
  - Result: passed.
- Schema drift check:
  - Command: `bash scripts/check_schema.sh`
  - Result: schema up to date.
- Dashboard production build:
  - Command: `CI=true npm run build`
  - Result: passed; built `build/static/js/main.1a5106b3.js`.
  - Note: Node emitted an existing `fs.F_OK` deprecation warning.
- Whitespace check:
  - Command: `git diff --check`
  - Result: passed.

## Reviewer Reconciliation

Three independent reviewer agents completed and were closed.

- Backend/API reviewer: no blockers. Suggested explicit route security coverage
  and an OpenAPI-level route metadata check. Both were added:
  `test_system_about_is_authenticated_sensitive_system_read_only` and
  `test_api_v1_system_about_openapi_metadata_without_runtime_app`.
- Frontend/operator UX reviewer: no blockers. Found that unchecked update
  metadata could be displayed as `Current`; fixed by requiring a real
  `checked_at` before displaying `Available` or `No update found`. Added a
  regression test that unsupported/unchecked update metadata displays
  `Not checked`. Also found commit/branch overflow risk on mobile; fixed with
  `wordBreak: 'break-all'` on those fields.
- Docs/governance reviewer: found the missing checkpoint artifact, stale
  `2026-06-18` review metadata for the new About candidate, and wording that
  could imply current MCP exposure. This checkpoint closes the missing artifact,
  the curated and generated candidate review date is now `2026-07-06`, and the
  API docs now say "dashboard/API consumers and future MCP candidate review."

## Boundaries

This slice proves typed process-local metadata, route registration, security
classification, dashboard consumption, docs alignment, and focused tests only.
It does not claim:

- PX4, MAVSDK, MAVLink2REST, SIH, SITL, HIL, or field success.
- Real aircraft or vehicle-response behavior.
- Update availability, GitHub release freshness, pull/update/restart success,
  or service deployment success.
- Runtime MCP exposure or callable MCP tools.

## Remaining Slices

- PXE-0085: SIH Dev/Training validation surface around the existing guarded SIH
  harness, evidence manifests, and L2 claim boundaries.
- PXE-0086: safe quick-demo cleanup/rotation and safe update workflow with
  fast-forward-only defaults and post-update validation gates.
- Final clean setup evidence: fresh walkthrough from docs/scripts in a clean
  temp path before release/tag and tester handoff.

