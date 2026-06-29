# Phase 4 Legacy Circuit-Breaker Mutation Boundary

Date: 2026-06-29  
Issue: PXE-0008  
Scope: behavior-preserving legacy API route-body extraction only.

## Summary

Moved legacy circuit-breaker mutation compatibility route bodies out of
`FastAPIHandler` and into `src/classes/api_legacy_safety_routes.py`.

Routes covered:

- `POST /api/circuit-breaker/toggle`
- `POST /api/circuit-breaker/toggle-safety`
- `POST /api/circuit-breaker/reset-statistics`

`FastAPIHandler` keeps route registration and one-call wrappers only. Route
inventory, auth/security policy, legacy paths, and legacy response shapes remain
unchanged.

## Preserved Behavior

- Circuit-breaker toggle still flips process-local
  `Parameters.FOLLOWER_CIRCUIT_BREAKER`.
- Enabling the circuit breaker still resets statistics.
- Disabling the circuit breaker still leaves statistics untouched.
- Safety-bypass toggle still flips process-local
  `Parameters.CIRCUIT_BREAKER_DISABLE_SAFETY`.
- Safety-bypass response payloads still distinguish configured bypass from
  effective bypass when the circuit breaker is inactive.
- Statistics reset still returns the legacy `old_statistics`,
  `new_statistics`, and `reset_timestamp` payload shape.
- Circuit-breaker import/unavailable failures still pass through the legacy
  broad exception wrapper, including the existing 503-to-500 detail shape.

## Explicit Non-Scope

- No typed `/api/v1/safety/*` action was added.
- No idempotency key, action store, dry-run, confirmation model, or structured
  action audit was introduced.
- No compatibility alias was retired.
- No runtime MCP exposure or callable tool surface was added.
- No PX4, SITL, HIL, field, QGC playback, deployment, service installation, or
  real-aircraft behavior was performed or claimed.

## Files Changed

- `src/classes/api_legacy_safety_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/unit/core_app/test_api_legacy_safety_routes.py`
- `tests/test_api_route_inventory.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-29-phase-4-legacy-circuit-breaker-mutation-boundary.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-29-phase-4-legacy-safety-route-boundary.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_safety_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_safety_routes.py tests/test_api_route_inventory.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_safety_routes.py tests/test_api_route_inventory.py::test_legacy_safety_route_bodies_are_not_defined_in_fastapi_handler tests/test_api_security_policy.py tests/test_api_tool_candidates.py tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Result: focused safety/API/security/candidate/docs gate passed with 44 tests;
Phase 0 passed with schema current, API/MCP candidate inventory current, and
388 tests passing with the existing Starlette/httpx warning.

## Review

Pre-implementation read-only review identified the exact mutation invariants to
preserve: `Parameters` mutation ownership, reset-on-enable behavior,
safety-bypass effective-state reporting, statistics reset shape, helper-level
monkeypatching, route inventory guardrails, and the existing 503-to-500 legacy
error wrapper. Those invariants are covered by direct helper tests and static
route-body ownership tests.

Final independent review found no blockers. The reviewer verified unchanged
route registration, one-call wrapper delegation, preserved `Parameters`
mutation semantics, reset-on-enable behavior, safety-bypass effective-state
reporting, statistics reset shape, unavailable-circuit-breaker 503-to-500
legacy wrapping, candidate provenance, and the absence of new typed
`/api/v1/safety/*`, MCP, PX4/SITL/HIL/field, QGC, or real-aircraft claims. The
reviewer also ran focused safety/API/candidate and security-policy gates with
60 and 19 tests passing.

## Residual Risk

- The moved routes remain legacy ad hoc JSON mutations, not typed Pydantic
  `/api/v1` contracts.
- The mutations remain process-local and non-idempotent for compatibility.
- The safety-bypass endpoint still changes process state and must not be treated
  as a production-safe action without the future typed action/audit design.
- No ASGI path-level tests were added for these routes; coverage is helper-level
  plus static route inventory/security/candidate gates.

## Next

- Continue PXE-0008 with WebRTC signaling route-body boundary extraction.
- Later design typed `/api/v1/safety/*` actions with idempotency, confirmation,
  structured errors, audit records, deprecation tracking, and MCP-safe policy.
