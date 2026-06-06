# Phase 4 API v1 Route Registry Extraction Checkpoint

Date: 2026-06-06
Slice: PXE-0052
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: first typed `/api/v1` route-family extraction from `FastAPIHandler`.

## Outcome

PXE-0052 is complete at code, contract, docs, and guardrail level. The typed
`/api/v1` route contracts are now centralized in a static registry while
runtime registration still binds to the existing `FastAPIHandler` methods and
Pydantic models.

No public route, handler method, response model, request model, structured
error contract, action confirmation/idempotency behavior, SITL injection gate,
dashboard route, runtime MCP endpoint, `tools/list`, `tools/call`, callable
tool, PX4/SITL/HIL behavior, service installation, deployment, or field
behavior changed in this slice.

## Files Changed

- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/test_api_route_inventory.py`
- `tools/generate_api_tool_candidates.py`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/agent-context/README.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `src/classes/fastapi_api_v1_routes.py`.
  - Defines `ApiV1RouteSpec`.
  - Defines `API_V1_ROUTE_SPECS` for all 14 current typed `/api/v1` HTTP
    routes.
  - Registers routes by resolving existing response models, response metadata,
    status codes, and handler methods from `fastapi_handler.py`.
- Replaced the inline typed `/api/v1` registration block in
  `FastAPIHandler.define_routes()` with `register_api_v1_routes(self, globals())`.
- Updated the route inventory test so it parses:
  - inline `self.app.*(...)` registrations in `fastapi_handler.py`;
  - static `API_V1_ROUTE_SPECS` entries in the new route registry.
- Updated the non-callable agent-candidate generator so it parses both route
  sources and keeps handler request-model inference from `fastapi_handler.py`.
- Regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml` with
  multi-source provenance.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
- Updated docs to record that route inventory and candidate generation now read
  both `fastapi_handler.py` and `fastapi_api_v1_routes.py`.

## Validation

- `python3 -m py_compile src/classes/fastapi_api_v1_routes.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`:
  passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py -q`:
  14 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_tool_candidates.py -q`:
  8 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  22 passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`: passed.
- `PYTHON=.venv/bin/python make phase0-check`: schema up to date, candidate
  inventory current, 47 passed.
- `git diff --check`: passed.

## Independent Review

Reviewer checks for this slice focused on route behavior preservation and
agent/MCP safety boundaries:

- all previous `/api/v1` routes remain represented once in static inventory;
- concrete action routes remain registered before the `{action_id}` action
  resource;
- action and SITL routes remain blocked from read-only MCP promotion;
- generated agent candidates remain non-callable and unexposed;
- route metadata can still be checked without constructing the runtime app;
- route registration helper order, handler binding, metadata resolution, and
  status-code resolution are covered with a fake app without constructing the
  PixEagle runtime app;
- no public schema or control behavior moved into a new ad hoc automation
  surface.

No blockers remain from this review pass.

Two non-blocking maintainability risks were closed during review: the route
inventory now asserts `FastAPIHandler.define_routes()` delegates to
`register_api_v1_routes(self, globals())` exactly once, and the registry helper
now has a fake-app test proving route order, handler binding, metadata
resolution, and accepted-status-code resolution without constructing the
PixEagle runtime app.

## Risks And Boundaries

- This is a structural extraction only. It does not reduce the broader
  `fastapi_handler.py` monolith enough by itself; PXE-0008 remains open for
  routers, schema modules, shared route helpers, and remaining legacy migration.
- Pydantic models still live in `fastapi_handler.py`; moving them into API
  schema modules should be a later slice with route inventory and OpenAPI
  contract checks.
- The generated agent inventory is still non-callable review coverage only.
- No PX4/SITL/HIL/field success is claimed from this slice.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. The strongest next step is
to extract API schemas and route families into focused modules without changing
route inventory, then continue legacy route migration and dashboard/client
normalization. PXE-0022 companion-runtime reconciliation, PXE-0021 dashboard
toolchain migration, PXE-0040 Gazebo runtime proof, and PXE-0041 final
no-legacy cleanup remain open.
