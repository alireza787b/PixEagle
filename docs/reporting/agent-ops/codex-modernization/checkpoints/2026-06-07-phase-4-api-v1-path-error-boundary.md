# Phase 4 API v1 Path/Error Boundary Checkpoint

Date: 2026-06-07
Slice: PXE-0054
Branch: `codex/modernization-pxe0040-runtime-20260604`
Scope: extract canonical typed `/api/v1` path ownership and structured
error-envelope construction from `FastAPIHandler`.

## Outcome

PXE-0054 is complete at code, contract, docs, and guardrail level. Canonical
typed `/api/v1` route paths and route-family predicates now live in
`src/classes/api_v1_paths.py`, and typed error-envelope construction now lives
in `src/classes/api_v1_errors.py`.

No public route, route order, handler method, response model name, request model
name, action confirmation/idempotency/dry-run behavior, SITL injection gate,
dashboard route, runtime MCP endpoint, `tools/list`, `tools/call`, callable
tool, PX4/SITL/HIL behavior, service installation, deployment, or field
behavior changed in this slice.

## Files Changed

- `src/classes/api_v1_paths.py`
- `src/classes/api_v1_errors.py`
- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/fastapi_handler.py`
- `tools/generate_api_tool_candidates.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/README.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## What Changed

- Added `src/classes/api_v1_paths.py` for:
  - all current typed `/api/v1` path constants;
  - SITL validation route-family membership;
  - process-local read-only candidate path membership;
  - typed error-envelope path predicates;
  - request-id prefix selection for API/action/SITL error envelopes.
- Aligned typed validation-error predicates so all six reviewed process-local
  read-only `/api/v1` routes, including `/api/v1/tracking/telemetry`, use the
  same structured envelope if FastAPI request validation is ever triggered. The
  current tracking telemetry GET route has no request body, path parameter, or
  query parameter, so this closes predicate drift without changing action,
  SITL-gate, PX4/SITL/HIL, deployment, or field behavior.
- Added `src/classes/api_v1_errors.py` for:
  - `APIErrorResponse` envelope construction;
  - validation-only SITL error response construction.
- Updated `src/classes/fastapi_api_v1_routes.py` so `ApiV1RouteSpec.path`
  entries consume path constants instead of duplicating typed route strings.
- Kept `FastAPIHandler` compatibility wrappers for `_api_v1_error_response`,
  `_sitl_error_response`, and `_uses_typed_api_error_envelope` while delegating
  the actual path/error logic to the new modules.
- Updated static route inventory and candidate generator parsers to resolve
  path constants from `api_v1_paths.py` without instantiating `FastAPIHandler`,
  Uvicorn, video, MAVLink, or PX4 subsystems.
- Regenerated
  `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`.
  - `total_declared_http_routes`: 129.
  - `api_v1_routes`: 14.
  - `candidate_count`: 14.
  - `eligible_read_only_candidates`: 6.
  - `blocked_or_guarded_candidates`: 8.
  - `callable_tools`: 0.
  - `mcp_exposed_tools`: 0.
  - Source provenance now includes `src/classes/api_v1_paths.py`.
- Added static tests that prevent:
  - inline typed `/api/v1` path strings drifting back into the route registry;
  - API path constants drifting back into `fastapi_handler.py`;
  - direct `APIErrorResponse` envelope construction drifting back into
    `fastapi_handler.py`;
  - validation-error envelope predicates drifting away from current typed
    route families.

## Validation

- `.venv/bin/python -m py_compile src/classes/api_v1_paths.py src/classes/api_v1_errors.py src/classes/api_v1_contracts.py src/classes/fastapi_api_v1_routes.py src/classes/fastapi_handler.py tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`:
  passed.
- `.venv/bin/python tools/generate_api_tool_candidates.py --check`: passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py -q`:
  26 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_sitl_injection_api.py tests/unit/core_app/test_app_controller_offboard_safety.py -k "api_v1 or sitl" -q`:
  49 passed, 50 deselected.
- `PYTHON=.venv/bin/python make phase0-check`: schema up to date, candidate
  inventory current, 51 passed.

## Independent Review

Review focus for this slice:

- no public route or `/api/v1` candidate inventory change beyond source
  provenance;
- no accidental MCP runtime/callable exposure;
- action confirmation/idempotency/dry-run and operator-abort behavior remain
  unchanged;
- SITL injection gates remain disabled by default;
- request validation errors keep typed envelopes only for reviewed `/api/v1`
  route families;
- docs do not claim PX4/SITL/HIL/field success from this structural change.

Independent review completed with no blockers:

- API/MCP review confirmed the route registry consumes canonical path
  constants, the static generator resolves those constants without importing
  runtime handler/model/config modules, generated provenance includes the path
  source file, route inventory stays stable, and `callable_tools` plus
  `mcp_exposed_tools` remain zero.
- Safety/runtime review confirmed action confirmation/idempotency/dry-run
  behavior is unchanged, SITL gates remain disabled by default, request-id
  namespaces match the prior action/SITL/API behavior, and no PX4/SITL/HIL or
  field-success claim was introduced. The review also noted the intentional
  validation-envelope alignment for `/api/v1/tracking/telemetry`.
- Docs/maintainability review confirmed the active docs identify
  `api_v1_paths.py` and `api_v1_errors.py`, and the checkpoint keeps the
  structural-only scope honest.

Residual follow-up risks:

- `api_v1_errors.py` is intentionally not part of generated candidate
  provenance because the inventory tracks route/tool surface, not runtime
  envelope internals; API/SITL behavior tests remain the drift guard for error
  helper changes.
- `fastapi_handler.py` still imports path and error helper names for migration
  compatibility; later router/API cleanup should remove compatibility wrappers
  only after callers are migrated.
- The static path resolver supports top-level literal string constants, which
  matches the current path module. If future path constants use composition or
  f-strings, the parser must be extended in the same slice.

## Risks And Boundaries

- This is a structural extraction only. It does not introduce FastAPI routers,
  persistent action storage, runtime MCP execution, or broader legacy route
  removal.
- `fastapi_handler.py` still keeps compatibility wrappers and imports during
  migration; a later cleanup can remove those wrappers only after internal and
  external uses are migrated.
- Status/telemetry routes remain PixEagle process-local snapshots. They do not
  prove PX4 Offboard state, SITL scenario success, tracker scene behavior,
  follower response, HIL, field behavior, or real-aircraft safety.

## Next Slice

Continue Phase 4 API modernization under PXE-0008. Good next candidates are
extracting typed action-resource storage/helpers, moving shared status snapshot
builders into focused API service modules, or starting a route-family router
adapter once handler dependencies are narrow enough. PXE-0022
companion-runtime reconciliation, PXE-0021 dashboard toolchain migration,
PXE-0040 Gazebo runtime proof, and PXE-0041 final no-legacy cleanup remain
open.
