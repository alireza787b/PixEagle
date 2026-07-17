# Phase 4 Legacy Follower Route Boundary

- Date: 2026-06-28
- Issue: PXE-0008 partial
- Slice: behavior-preserving completion of current legacy follower route-body extraction
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice completed the current `/api/follower/*` HTTP compatibility route-body
extraction by moving the remaining follower health, restart, and config-manager
read behavior out of `FastAPIHandler` and into
`src/classes/api_legacy_follower_routes.py`.

Moved route bodies in this slice:

- `GET /api/follower/health`
- `POST /api/follower/restart`
- `GET /api/follower/config/general`
- `GET /api/follower/config/{follower_name}`

Together with the preceding follower profile slice, `api_legacy_follower_routes.py`
now owns all current `/api/follower/*` route bodies. `FastAPIHandler` keeps route
registration and thin wrapper methods only. Route inventory, security policy,
auth scopes, legacy paths, response payload shapes, follower health resource
diagnostics, OffboardCommander degraded-health semantics, restart rate limiting,
config reload behavior, active follower stop/start behavior, and follower config
manager response shapes are intended to be unchanged.

## Files Changed

- `src/classes/api_legacy_follower_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/unit/core_app/test_api_legacy_follower_routes.py`
- `tests/test_api_route_inventory.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-28-phase-4-legacy-follower-route-boundary.md`

## Validation

Completed before final reporting:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_follower_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_follower_routes.py tests/test_api_route_inventory.py tools/generate_api_tool_candidates.py tests/test_api_tool_candidates.py`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_follower_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py tests/unit/core_app/test_app_controller_offboard_safety.py::test_follower_health_marks_running_degraded_commander_as_degraded`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Focused result: 78 passed.
Phase 0 result: schema current, API/MCP candidate inventory current, 386 passed,
1 existing Starlette/httpx warning.

## Evidence Boundary

This is a backend API boundary extraction only.

No typed `/api/v1/following/*` or `/api/v1/follower/*` route was added. No
legacy follower route was retired. No runtime MCP endpoint, executor,
`tools/list`, `tools/call`, or callable tool surface was added. No
service/deployment action, target proxy/firewall/TLS setup, QGC playback,
PX4/SITL/HIL, field test, or real-aircraft behavior was performed or claimed.

## Residual Risk

The extraction intentionally preserved existing legacy behavior, including
known rough edges that require separate typed follower API design work:

- Follower health, restart, and config-manager responses remain ad hoc
  compatibility payloads rather than typed `/api/v1` contracts.
- Restart still uses the request path to call `Parameters.reload_config()` and
  optionally `stop_following()` / `start_following()`.
- The legacy health route still reports process-local state only; it does not
  prove PX4 command receipt, vehicle movement, QGC/GCS display, SITL/HIL, or
  field behavior.
- Config-manager reads still expose private manager attributes (`_general` and
  `_overrides`) for legacy compatibility.
- Typed follower route design, structured errors, deprecation metadata, and
  alias retirement remain future PXE-0008 work.

## Next Planned Slice

Continue PXE-0008 by extracting another remaining legacy route family without
changing route inventory/security policy. Candidate order:

1. Safety route-body boundary.
2. Video/media route-body boundaries.
3. Typed `/api/v1/following/*`, safety, and media promotions only after legacy
   boundaries, structured errors, request/response models, docs, tests, and
   deprecation gates are ready.
