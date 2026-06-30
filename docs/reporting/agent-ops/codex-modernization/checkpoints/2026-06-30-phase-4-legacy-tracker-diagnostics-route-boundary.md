# Phase 4 Legacy Tracker Diagnostics Route Boundary

Date: 2026-06-30
Issue: PXE-0008
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

Continued PXE-0008 by moving the remaining legacy tracker diagnostic route
bodies out of `FastAPIHandler` and into
`src/classes/api_legacy_tracker_routes.py`.

Moved route bodies:

- `GET /api/tracker/schema`
- `GET /api/tracker/current-status`
- `GET /api/tracker/output`
- `GET /api/tracker/capabilities`

Also moved `_get_enhanced_field_info()` because it is display/diagnostic
field-shaping logic used by `current-status`.

`FastAPIHandler` still owns route registration and keeps one-call wrapper
methods for compatibility.

## Preserved Behavior

- Route inventory and security policy are unchanged.
- `GET /api/tracker/output` still returns legacy 200 no-output payloads,
  `TrackerOutput.to_dict()` payloads with `api_version=2.0` and
  `schema_version=flexible`, and broad 500 wrapping for unexpected failures.
- `GET /api/tracker/capabilities` still returns 200 fallback bodies for missing
  capability APIs and no active tracker, plus `tracker_capabilities` and
  `system_info` for active capability responses.
- `GET /api/tracker/schema` still reads `configs/tracker_schemas.yaml` from the
  current process working directory via `yaml.safe_load()` and maps errors to
  legacy 500 responses.
- `GET /api/tracker/current-status` still returns false runtime flags and
  embedded runtime status when no output exists.
- Active current-status responses still exclude system fields, expose dynamic
  display field metadata, surface selected raw gimbal/status fields, embed raw
  data, preserve `smart_mode`, swallow smart-tracker runtime-info failures, and
  derive top-level runtime flags from `_get_tracker_runtime_status_snapshot()`.

## Guardrails Added

- Expanded `tests/unit/core_app/test_api_legacy_tracker_routes.py` for
  diagnostic no-output/live-output payloads, capability fallbacks, schema
  read/error behavior, no-output current-status, gimbal/raw field formatting,
  smart-tracker inference, inference failure swallowing, and legacy 500
  wrapping.
- Expanded route-inventory static guardrails proving tracker diagnostics and
  `_get_enhanced_field_info()` stay out of `FastAPIHandler`.
- Regenerated non-callable API/MCP candidate provenance because
  `src/classes/api_legacy_tracker_routes.py` and `src/classes/fastapi_handler.py`
  changed.

## Non-Scope

No typed `/api/v1/tracking/*` replacement, tracker alias retirement, dashboard
migration, runtime MCP endpoint, callable tool surface, service/deployment
action, PX4/SITL/HIL, field test, or real-aircraft behavior was performed or
claimed.

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
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py::test_legacy_tracker_selector_route_bodies_are_not_defined_in_fastapi_handler`
  - Result: 30 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py --check`
  - Result: candidate inventory current.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
  - Result: 97 passed.
- `git diff --check`
  - Result: passed.
- `PYTHON=.venv/bin/python make phase0-check`
  - Result: schema current, API/MCP candidate inventory current, 391 passed,
    one existing Starlette/httpx deprecation warning.

## Review

- Pre-implementation read-only review identified three expected closure items:
  expand static guardrails, regenerate API/MCP candidate provenance, and update
  same-slice docs/reporting. The implementation addressed those before final
  review.
- Final independent read-only review found no blockers. It verified unchanged
  route registration and one-call wrappers, helper ownership, static
  guardrails, current API/MCP candidate provenance, docs/reporting consistency,
  explicit demo/fresh-setup remaining gates, and no unsupported typed
  `/api/v1`, dashboard, MCP, QGC, PX4/SITL/HIL/field, or real-aircraft claims.

## Remaining Before Dashboard Demo

- Finish PXE-0008 typed replacement and compatibility-retirement planning for
  high-value legacy surfaces, starting with tracker routes.
- Reconcile dashboard consumers against typed `/api/v1` routes and remove
  avoidable direct legacy usage where replacement routes exist.
- Complete remaining dashboard/client/toolchain modernization tracked under
  PXE-0021 and related Phase 4 dashboard issues.
- Run backend, dashboard install/test/build, schema, docs, and API/MCP
  candidate gates on a clean branch state.
- Start the maintained dev stack only after those gates pass and provide the
  dashboard URL with exact profile/config notes for tester review.

## Remaining Before Fresh Setup Handoff

- Complete PXE-0074 clean temporary-checkout walkthrough using public docs only
  for beginner demo setup and senior-dev override paths.
- Capture exact commands, generated files, ports, credential handoff behavior,
  validation output, and environment assumptions.
- Remove or rewrite stale/noisy/deprecated setup/config/docs discovered during
  that walkthrough.
- Only after those gates pass should release/tag/handoff decisions be made.

## Residual Risk

- These routes remain legacy ad hoc JSON compatibility routes, not typed
  Pydantic `/api/v1` contracts.
- No ASGI path-level tests were added for these exact legacy routes; coverage is
  helper-level plus static route inventory/candidate gates.
- `GET /api/tracker/schema` still reads a relative schema path as legacy
  behavior, so process working directory remains part of this compatibility
  contract until typed replacement.

## Next

- Continue PXE-0008 with typed `/api/v1/tracking/*` replacement and
  compatibility-retirement planning.
- Continue dashboard/API consumer cleanup after typed replacement routes are
  ready.
