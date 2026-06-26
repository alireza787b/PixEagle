# Phase 4 Legacy Config Mutation Boundary

- Date: 2026-06-26
- Issue: PXE-0008 partial
- Slice: behavior-preserving legacy config mutation/apply route-body extraction
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice moved legacy config mutation/apply HTTP compatibility behavior out of
`FastAPIHandler` and into `src/classes/api_legacy_config_routes.py`.

Moved route bodies:

- `PUT /api/config/{section}/{parameter}`
- `PUT /api/config/{section}`
- `POST /api/config/validate`
- `POST /api/config/defaults-sync/apply`
- `POST /api/config/revert`
- `POST /api/config/revert/{section}`
- `POST /api/config/revert/{section}/{parameter}`
- `POST /api/config/restore/{backup_id}`
- `POST /api/config/import`

`FastAPIHandler` keeps route registration and thin wrapper methods only. Route
inventory, security policy, auth scopes, legacy paths, response shapes,
rate-limit behavior, save/reload sequencing, defaults-sync rollback behavior,
and import/revert/restore semantics are intended to be unchanged.

## Files Changed

- `src/classes/api_legacy_config_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/unit/core_app/test_api_legacy_config_routes.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-26-phase-4-legacy-config-mutation-boundary.md`

## Validation

Completed before final reporting:

- `.venv/bin/python -m py_compile src/classes/fastapi_handler.py src/classes/api_legacy_config_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_api_legacy_config_routes.py tools/generate_api_tool_candidates.py`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_config_routes.py tests/unit/core_app/test_api_legacy_config_sync.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Focused result: 72 passed.
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

- section updates are not transactional in memory;
- defaults-sync apply still uses the private `ConfigService._create_backup()`;
- import does not validate or hot-reload;
- revert and restore routes remain un-rate-limited;
- legacy response bodies remain ad hoc compatibility payloads rather than typed
  `/api/v1` contracts.

## Next Planned Slice

Continue PXE-0008 by extracting another remaining legacy route family without
changing route inventory/security policy. Candidate order:

1. Config read/diff/search/audit route-body extraction.
2. Recording route-body extraction.
3. OSD/GStreamer/follower/safety/video route-body boundaries.
4. Typed `/api/v1/config/*` design/promotion only after legacy boundaries,
   structured errors, request/response models, docs, tests, and deprecation
   gates are ready.
