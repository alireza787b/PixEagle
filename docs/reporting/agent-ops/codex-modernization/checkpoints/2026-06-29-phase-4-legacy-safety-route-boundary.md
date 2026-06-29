# Phase 4 Legacy Safety Read Route Boundary

Date: 2026-06-29  
Issue: PXE-0008  
Scope: behavior-preserving legacy API route-body extraction only.

## Summary

Moved read-only safety, circuit-breaker, and safety/config compatibility route
bodies out of `FastAPIHandler` and into
`src/classes/api_legacy_safety_routes.py`.

Routes covered:

- `GET /api/circuit-breaker/status`
- `GET /api/circuit-breaker/statistics`
- `GET /api/safety/config`
- `GET /api/safety/limits/{follower_name}`
- `GET /api/config/effective-limits`
- `GET /api/config/sections/relevant`

`FastAPIHandler` keeps route registration and one-call wrappers only. Route
inventory, auth/security policy, legacy paths, and legacy response shapes remain
unchanged.

## Preserved Behavior

- Circuit-breaker status still reports availability, active/testing state,
  safety-bypass effectiveness, configuration metadata, statistics, and legacy
  status messages.
- Circuit-breaker statistics still wraps unavailable `HTTPException(503)` into
  the legacy broad 500 error path.
- Safety config still exposes the legacy process-local `_global_limits` and
  `_follower_overrides` payload.
- Follower safety limits still fall back to `Parameters.get_effective_limit()`
  when `SafetyManager` is unavailable.
- SafetyManager rate limits still convert radians to degrees for legacy UI
  payloads.
- Effective-limit and relevant-section routes retain their existing ad hoc
  response shapes and mode-section mapping.

## Explicit Non-Scope

- No circuit-breaker toggle, safety-bypass toggle, or statistics-reset mutation
  was moved, typed, or redesigned in this slice.
- No typed `/api/v1/safety/*` route was added.
- No compatibility alias was retired.
- No runtime MCP exposure or callable tool surface was added.
- No PX4, SITL, HIL, field, QGC playback, deployment, service installation, or
  real-aircraft behavior was performed or claimed.

## Files Changed

- `src/classes/api_legacy_safety_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/unit/core_app/test_api_legacy_safety_routes.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/README.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/03-api/README.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_safety_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_safety_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_safety_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Result: focused safety/API/security/candidate gate passed with 72 tests; Phase 0
passed with schema current, API/MCP candidate inventory current, and 387 tests
passing with the existing Starlette/httpx warning.

## Residual Risk

- The moved routes remain legacy ad hoc JSON responses, not typed Pydantic
  `/api/v1` contracts.
- Read-only circuit-breaker status/statistics remain process-local diagnostics,
  not proof of flight behavior.
- Circuit-breaker toggle, safety-bypass toggle, and statistics reset remain
  legacy mutations in `FastAPIHandler` and should move under a separate guarded
  action/deprecation cleanup.
- Safety config still exposes private SafetyManager attributes for compatibility.
- No ASGI path-level test was added for each route; coverage is helper-level plus
  static route inventory/security/candidate gates.

## Next

- Continue PXE-0008 with video/media route-body boundary extraction.
- Schedule a separate guarded circuit-breaker mutation cleanup before typed
  `/api/v1/safety/*` promotion.
