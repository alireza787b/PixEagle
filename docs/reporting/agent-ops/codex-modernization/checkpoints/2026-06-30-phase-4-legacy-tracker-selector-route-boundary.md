# Phase 4 Legacy Tracker Selector Route Boundary

Date: 2026-06-30
Issue: PXE-0008
Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

Continued the PXE-0008 API route-boundary cleanup by moving the first legacy
tracker selector/config route bodies out of `FastAPIHandler` and into
`src/classes/api_legacy_tracker_routes.py`.

Moved route bodies:

- `GET /api/tracker/available`
- `GET /api/tracker/current`
- `POST /api/tracker/switch`
- `POST /api/tracker/restart`
- `GET /api/tracker/current-config`

`FastAPIHandler` still owns route registration and keeps one-call wrapper
methods for compatibility.

## Preserved Behavior

- Route inventory and security policy are unchanged.
- Available-tracker listing still uses `SchemaManager.get_available_classic_trackers()`.
- Current tracker details still return status, UI metadata, runtime-status
  fields, follower/smart-mode flags, unknown-tracker fallback, and timestamp.
- Tracker switch still parses raw `Request.json()`, returns 400 for missing or
  invalid `tracker_type`, delegates to `AppController.switch_tracker_type()`,
  returns legacy success payloads, and returns JSON 500 payloads for controller
  failure.
- Tracker restart still uses the `config_write` rate-limit bucket, returns
  legacy 429 payload plus `Retry-After`, reloads `Parameters`, delegates to
  `switch_tracker_type(current_tracker_type)`, and preserves success/failure
  payload shapes.
- Current tracker config still reports configured tracker, smart-mode flag,
  active tracker class, expected data type, active/configured status, and
  timestamp.

## Guardrails Added

- Added `tests/unit/core_app/test_api_legacy_tracker_routes.py` for the moved
  helper behavior, fallback paths, and error mappings.
- Added route-inventory static guardrails proving the moved tracker selector
  route bodies and helper marker strings stay out of `FastAPIHandler`.
- Added an explicit static guard that deprecated `POST /api/tracker/set-type`
  remains inline for a separate follow-up slice with
  `GET /api/tracker/available-types`.
- Added `src/classes/api_legacy_tracker_routes.py` to non-callable API/MCP
  candidate provenance.

## Non-Scope

No typed `/api/v1/tracking/*` replacement, tracker alias retirement, deprecated
`/api/tracker/set-type` move, `GET /api/tracker/available-types` move, tracker
schema/output/capability/current-status move, dashboard migration, runtime MCP
endpoint, callable tool surface, service/deployment action, PX4/SITL/HIL,
field test, or real-aircraft behavior was performed or claimed.

## Files Changed

- `src/classes/api_legacy_tracker_routes.py`
- `src/classes/fastapi_handler.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `tests/unit/core_app/test_api_legacy_tracker_routes.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `docs/apis/api-modernization-blueprint.md`
- `docs/agent-context/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_tracker_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py::test_legacy_tracker_selector_route_bodies_are_not_defined_in_fastapi_handler tests/test_api_tool_candidates.py::test_api_tool_candidate_inventory_is_current tests/test_api_tool_candidates.py::test_api_tool_candidate_inventory_is_non_callable`
  - Result: 15 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_tracker_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
  - Result: 80 passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py --check`
  - Result: candidate inventory current.
- `PYTHON=.venv/bin/python make phase0-check`
  - Result: schema current, API/MCP candidate inventory current, 391 passed,
    one existing Starlette/httpx deprecation warning.

## Review

- Pre-implementation read-only tracker/API review found no extraction blocker,
  recommended keeping `set_tracker_type` and `available-types` for a separate
  follow-up, identified invariants for schema-manager lookup, runtime-status
  embedding, raw request parsing, 400/429/500 shapes, rate-limit bucket, and
  config reload, and recommended the fallback/error guardrails added here.
- Final independent review found one blocker after a late log-message
  compatibility correction: generated API/MCP candidate provenance was stale.
  The inventory was regenerated, `--check` passed, focused tracker/candidate/doc
  tests passed, and the final-state Phase 0 gate passed with schema current,
  candidate inventory current, and 391 tests passing.
- Post-repair read-only review found no blockers and independently verified
  one-call wrapper delegation, unchanged route registration, preserved legacy
  tracker selector behavior, current generated API/MCP provenance, explicit
  deferral of `POST /api/tracker/set-type` plus
  `GET /api/tracker/available-types`, and no PX4/SITL/HIL/field/QGC/deployment
  or runtime MCP claims.

## Residual Risk

- These routes remain legacy ad hoc JSON compatibility routes, not typed
  Pydantic `/api/v1` contracts.
- `POST /api/tracker/set-type` and `GET /api/tracker/available-types` still live
  directly in `FastAPIHandler` and are the next intended tracker boundary slice.
- Tracker schema/output/capabilities/current-status route bodies remain in the
  handler and need their own slice because they are heavier runtime/schema
  diagnostics.
- No ASGI path-level tests were added for these exact legacy routes; coverage is
  helper-level plus static route inventory/security/candidate gates.

## Next

- Continue PXE-0008 with legacy tracker available-types plus deprecated
  set-type boundary extraction.
- Later extract tracker schema/output/capabilities/current-status diagnostics
  and plan typed `/api/v1/tracking/*` replacements and compatibility
  retirement.
