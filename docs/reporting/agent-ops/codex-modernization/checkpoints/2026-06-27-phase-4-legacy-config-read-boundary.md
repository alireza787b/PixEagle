# Phase 4 Legacy Config Read Boundary

- Date: 2026-06-27
- Issue: PXE-0008 partial
- Slice: behavior-preserving legacy config read/diff/search/audit route-body
  extraction
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice moved the remaining legacy config read/query HTTP compatibility
behavior out of `FastAPIHandler` and into
`src/classes/api_legacy_config_routes.py`.

Moved route bodies:

- `GET /api/config/schema`
- `GET /api/config/schema/{section}`
- `GET /api/config/sections`
- `GET /api/config/categories`
- `GET /api/config/current`
- `GET /api/config/current/{section}`
- `GET /api/config/default`
- `GET /api/config/default/{section}`
- `GET /api/config/diff`
- `POST /api/config/diff`
- `GET /api/config/defaults-sync`
- `POST /api/config/defaults-sync/plan`
- `GET /api/config/history`
- `GET /api/config/export`
- `GET /api/config/search`
- `GET /api/config/audit`

`FastAPIHandler` keeps route registration and thin wrapper methods only. Route
inventory, security policy, auth scopes, legacy paths, response shapes, query
parsing, broad legacy HTTP 500 behavior, and defaults-sync baseline
initialization behavior are intended to be unchanged.

## Files Changed

- `src/classes/api_legacy_config_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/unit/core_app/test_api_legacy_config_routes.py`
- `tests/test_api_route_inventory.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-27-phase-4-legacy-config-read-boundary.md`

## Validation

Completed before final reporting:

- `.venv/bin/python -m py_compile src/classes/fastapi_handler.py src/classes/api_legacy_config_routes.py tests/test_api_route_inventory.py tests/unit/core_app/test_api_legacy_config_routes.py`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_config_routes.py tests/unit/core_app/test_api_legacy_config_sync.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Focused result: 77 passed.
Phase 0 result: schema current, API/MCP candidate inventory current, 382
passed, 1 existing Starlette/httpx warning.

## Evidence Boundary

This is a backend API boundary extraction only.

No typed `/api/v1/config/*` route was added. No legacy config route was retired.
No runtime MCP endpoint, executor, `tools/list`, `tools/call`, or callable tool
surface was added. No service/deployment action, target proxy/firewall/TLS
setup, QGC playback, PX4/SITL/HIL, field test, or real-aircraft behavior was
performed or claimed.

## Residual Risk

The extraction intentionally preserved existing legacy behavior, including
known rough edges that require separate typed `/api/v1/config` design work:

- read and query responses remain ad hoc compatibility payloads rather than
  typed `/api/v1` contracts;
- missing schema sections and missing current/default sections keep different
  semantics;
- invalid `limit`/`offset` query values still become HTTP 500 responses;
- `GET /api/config/defaults-sync` still initializes the defaults snapshot when
  no baseline exists;
- invalid defaults-sync dry-run plans still return HTTP 200 with
  `success: true`;
- config search/audit/export query parsing remains stringly typed.

## Next Planned Slice

Continue PXE-0008 by extracting another remaining legacy route family without
changing route inventory/security policy. Candidate order:

1. Recording route-body extraction.
2. OSD/GStreamer route-body extraction.
3. Follower/safety/video/media route-body boundaries.
4. Typed `/api/v1/config/*` design/promotion only after legacy boundaries,
   structured errors, request/response models, docs, tests, and deprecation
   gates are ready.
