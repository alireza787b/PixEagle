# Phase 4 Legacy Tracker Set-Type Route Boundary

Date: 2026-06-30
Issue: PXE-0008
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

Continued the PXE-0008 API route-boundary cleanup by moving the remaining
legacy tracker type-selection compatibility route bodies out of
`FastAPIHandler` and into `src/classes/api_legacy_tracker_routes.py`.

Moved route bodies:

- `GET /api/tracker/available-types`
- `POST /api/tracker/set-type` (deprecated compatibility alias)

`FastAPIHandler` still owns route registration and keeps one-call wrapper
methods for compatibility.

## Preserved Behavior

- Route inventory and security policy are unchanged.
- `GET /api/tracker/available-types` still returns the legacy hardcoded tracker
  capability map for `CSRT`, `ParticleFilter`, `Gimbal`, and `SmartTracker`.
- Classic tracker entries still gain `available=true` and
  `unavailable_reason=null` when not explicitly set.
- `SmartTracker` availability still reflects `AI_AVAILABLE` and reports the
  legacy AI-package unavailable reason when AI dependencies are missing.
- The deprecated `POST /api/tracker/set-type` route still logs its deprecation
  warning and returns the `_deprecated`, `_deprecation_message`, and `_sunset`
  envelope on successful responses.
- `set-type` still validates missing/invalid `tracker_type` with legacy 400
  errors.
- `set-type` still fails with the legacy SmartTracker AI dependency 400 when AI
  packages are unavailable.
- `set-type` still mutates `app_controller.smart_mode_active` and
  `app_controller.current_tracker_type` directly, preserving the legacy
  configured versus active tracking response branches.
- Legacy broad exception wrapping still maps unexpected failures to 500
  `HTTPException`.

## Guardrails Added

- Expanded `tests/unit/core_app/test_api_legacy_tracker_routes.py` for
  hardcoded available-types payloads, AI availability reporting, deprecated
  response envelopes, direct controller-state mutation, restart-required
  branches, validation errors, and broad 500 wrapping.
- Expanded route-inventory static guardrails proving the moved available-types
  and set-type route bodies and marker strings stay out of `FastAPIHandler`.
- Regenerated non-callable API/MCP candidate provenance because
  `src/classes/api_legacy_tracker_routes.py` and `src/classes/fastapi_handler.py`
  changed.

## Non-Scope

No typed `/api/v1/tracking/*` replacement, tracker alias retirement,
tracker schema/output/capabilities/current-status move, dashboard migration,
runtime MCP endpoint, callable tool surface, service/deployment action,
PX4/SITL/HIL, field test, or real-aircraft behavior was performed or claimed.

## Files Changed

- `src/classes/api_legacy_tracker_routes.py`
- `src/classes/fastapi_handler.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `tests/unit/core_app/test_api_legacy_tracker_routes.py`
- `tests/test_api_route_inventory.py`
- `docs/apis/api-modernization-blueprint.md`
- `docs/agent-context/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_tracker_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py::test_legacy_tracker_selector_route_bodies_are_not_defined_in_fastapi_handler tests/test_api_tool_candidates.py::test_api_tool_candidate_inventory_is_current tests/test_api_tool_candidates.py::test_api_tool_candidate_inventory_is_non_callable`
  - Result: 23 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py --check`
  - Result: candidate inventory current.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
  - Result: 88 passed.
- `PYTHON=.venv/bin/python make phase0-check`
  - Result: schema current, API/MCP candidate inventory current, 391 passed,
    one existing Starlette/httpx deprecation warning.
- `git diff --check`
  - Result: passed.

## Review

- Final independent read-only review found no code blockers and verified the
  unchanged route registrations, one-call wrappers, moved helper bodies,
  preserved hardcoded tracker payloads, `AI_AVAILABLE` behavior, 400/500
  mappings, direct legacy AppController state mutation, current non-callable
  candidate provenance, and absence of PX4/SITL/HIL/field/QGC/deployment or
  runtime MCP claims.
- The reviewer noted low-risk historical prior-slice wording that described
  `available-types` and `set-type` as deferred follow-up work. The current
  phase map now explicitly states that follow-up was closed by this slice.

## Residual Risk

- These routes remain legacy ad hoc JSON compatibility routes, not typed
  Pydantic `/api/v1` contracts.
- The deprecated `POST /api/tracker/set-type` alias still performs direct
  process-local AppController state mutation and needs typed replacement plus
  compatibility-retirement planning.
- Tracker schema/output/capabilities/current-status route bodies remain in the
  handler and need their own slice because they are heavier runtime/schema
  diagnostics.
- No ASGI path-level tests were added for these exact legacy routes; coverage is
  helper-level plus static route inventory/candidate gates.

## Next

- Continue PXE-0008 with tracker schema/output/capabilities/current-status
  diagnostics extraction.
- Later plan typed `/api/v1/tracking/*` replacements and compatibility
  retirement for legacy tracker routes.
