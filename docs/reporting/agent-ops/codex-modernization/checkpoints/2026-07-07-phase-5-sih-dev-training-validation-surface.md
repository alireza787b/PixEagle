# Phase 5 Checkpoint - PXE-0085 SIH Dev/Training Validation Surface

Date: 2026-07-07
Branch: `codex/modernization-pxe0040-runtime-20260604`
Slice: PXE-0085 SIH Dev/Training validation surface
Status: closed

## Summary

PXE-0085 adds a typed, read-only SIH Dev/Training validation surface around the
existing official-PX4 SIH harness and local evidence manifests.

The new `GET /api/v1/sitl/status` route returns:

- checked-in `phase2_follower_validation` plan metadata;
- required Phase 2 scenario coverage using the same required scenario set as
  the SITL harness;
- the latest local `reports/sitl/*/manifest.json` summary for that plan;
- exact terminal commands for dry-run, probe, and PX4-only execution;
- explicit L2 claim boundaries.

The route is authenticated with `debug:read`, classified as sensitive
validation metadata, and recorded in the generated API/MCP candidate inventory
as blocked, non-callable, and `mcp_exposure: none`.

The dashboard now has a System -> Validation page. It shows plan/evidence
metadata and terminal commands only. It does not add browser buttons that start
Docker/PX4 or call raw SITL injection routes.

## Files Changed

- Backend/API contracts and route wiring:
  - `src/classes/api_v1_contracts.py`
  - `src/classes/api_v1_paths.py`
  - `src/classes/api_v1_sitl.py`
  - `src/classes/fastapi_api_v1_routes.py`
  - `src/classes/fastapi_handler.py`
  - `src/classes/api_security_policy.py`
- Dashboard:
  - `dashboard/src/App.js`
  - `dashboard/src/App.test.js`
  - `dashboard/src/components/NavigationDrawer.js`
  - `dashboard/src/pages/ValidationPage.js`
  - `dashboard/src/pages/ValidationPage.test.js`
  - `dashboard/src/services/apiEndpoints.js`
  - `dashboard/src/services/apiEndpoints.test.js`
- Tests and candidate generation:
  - `tests/unit/core_app/test_api_v1_sitl_status.py`
  - `tests/test_api_route_inventory.py`
  - `tests/test_api_security_policy.py`
  - `tests/test_api_tool_candidates.py`
  - `tools/generate_api_tool_candidates.py`
  - `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- Docs and reporting:
  - `docs/core-app/03-api/README.md`
  - `docs/drone-interface/04-infrastructure/sitl-setup.md`
  - `docs/apis/api-modernization-blueprint.md`
  - `docs/agent-context/README.md`
  - `docs/reporting/agent-ops/codex-modernization/issue-register.md`
  - `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
  - `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- SIH dry-run:
  - Command: `PYTHON_BIN=.venv/bin/python bash scripts/sitl/run_px4_sih_profile.sh --mode dry-run --json`
  - Result: passed.
  - Evidence: command printed the checked-in plan/evidence contract with
    `would_start_processes=false` and
    `would_run_scenarios_in_runtime_mode=false`.
- Backend/API/security/docs focused gate:
  - Command: `.venv/bin/python -m py_compile src/classes/api_v1_contracts.py src/classes/api_v1_paths.py src/classes/api_v1_sitl.py src/classes/fastapi_api_v1_routes.py src/classes/fastapi_handler.py src/classes/api_security_policy.py tools/generate_api_tool_candidates.py && PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_api_v1_sitl_status.py tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py tests/test_docs_infrastructure_consistency.py tests/unit/core_app/test_parameters_reload.py -q`
  - Result: 116 passed.
- Dashboard focused tests:
  - Command: `npm test -- --runInBand --watchAll=false src/pages/ValidationPage.test.js src/services/apiEndpoints.test.js src/components/NavigationDrawer.test.js src/App.test.js`
  - Result: 4 suites passed, 12 tests passed.
  - Note: existing React Router future-flag warnings were emitted.
- Schema drift check:
  - Command: `bash scripts/check_schema.sh`
  - Result: schema up to date.
- Dashboard production build:
  - Command: `CI=true npm run build`
  - Result: passed; built `build/static/js/main.fe82c183.js`.
  - Note: Node emitted the existing `fs.F_OK` deprecation warning.
- Whitespace check:
  - Command: `git diff --check`
  - Result: passed.

## Reviewer Reconciliation

Three independent reviewer agents were restarted after the usage-limit
interruption and their stale predecessors were closed.

- Backend/API/security reviewer: found that required Phase 2 scenario coverage
  could be misreported, `raw_injection_routes_exposed` could be misunderstood
  as API route exposure, free-form manifest text could leak absolute paths, and
  the checkpoint file was missing. Fixes:
  - `api_v1_sitl.py` now uses the same required Phase 2 scenario set as the
    harness and tests compare the constants;
  - the response field is now `raw_injection_controls_exposed`;
  - manifest `result_reason`, `semantic_failures`, and
    `artifact_content_failures` are sanitized before API output;
  - this checkpoint closes the missing artifact.
- Dashboard/operator UX reviewer: passed with follow-up fixes. Fixes:
  - failed refresh now marks displayed data as stale;
  - long artifact/failure strings wrap safely on narrow screens;
  - commands that require an operator-prepared stack now show a visible chip.
- Docs/governance reviewer: failed the first pass because the checkpoint file
  was missing, the new candidate used the old default review date, and the most
  reusable docs did not consistently say "not SITL runtime success." Fixes:
  - this checkpoint file was added;
  - `pixeagle.sitl.status.read` now has `reviewed_on: '2026-07-07'`;
  - API contracts, API docs, and SITL setup docs now explicitly say the route
    does not prove SITL runtime success.

## Boundaries

This slice proves typed read-only validation metadata, route registration,
security classification, dashboard display, docs alignment, and focused tests
only.

It does not claim:

- Docker, PX4, SIH, Gazebo, X-Plane, MAVSDK, MAVLink2REST, or MavlinkAnywhere
  runtime success.
- PX4-observed Offboard behavior, follower response, vehicle response, HIL,
  field, or real-aircraft behavior.
- Production deployment, service installation, firewall/proxy readiness, QGC
  media playback, or remote browser hardening.
- Runtime MCP exposure, callable MCP tools, or agent permission to execute
  PixEagle routes.

## Remaining Slices

- PXE-0086: safe quick-demo cleanup/rotation and safe update workflow with
  fast-forward-only defaults and post-update validation gates.
- PXE-0079/PXE-0074 carry the remaining clean setup walkthrough evidence before
  release/tag/handoff.
- PXE-0068/PXE-0064 carry production target proxy/firewall/credential/service
  evidence and adversarial browser/session/media validation.
- PXE-0070 remains QGC PR receiver/proxy evidence; PR #13594 should remain
  draft until target receiver testing is accepted.
