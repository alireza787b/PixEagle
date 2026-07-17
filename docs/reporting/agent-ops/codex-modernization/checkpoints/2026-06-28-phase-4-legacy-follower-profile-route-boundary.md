# Phase 4 Legacy Follower Profile Route Boundary

- Date: 2026-06-28
- Issue: PXE-0008 partial
- Slice: behavior-preserving legacy follower profile/setpoint route-body extraction
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice moved legacy follower profile and setpoint-status HTTP compatibility
behavior out of `FastAPIHandler` and into
`src/classes/api_legacy_follower_routes.py`.

Moved route bodies:

- `GET /api/follower/schema`
- `GET /api/follower/profiles`
- `GET /api/follower/current-profile`
- `POST /api/follower/switch-profile`
- `GET /api/follower/configured-mode`
- `GET /api/follower/setpoints-status`
- `GET /api/follower/current-mode`

`FastAPIHandler` keeps route registration and thin wrapper methods only. Route
inventory, security policy, auth scopes, legacy paths, response payload shapes,
active-versus-configured profile behavior, profile validation quirks,
setpoint-status compatibility fields, OffboardCommander publication summary, and
safety-limit summary lookup are intended to be unchanged.

## Files Changed

- `src/classes/api_legacy_follower_routes.py`
- `src/classes/fastapi_handler.py`
- `tools/generate_api_tool_candidates.py`
- `tests/unit/core_app/test_api_legacy_follower_routes.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-28-phase-4-legacy-follower-profile-route-boundary.md`

## Validation

Completed before final reporting:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_follower_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_follower_routes.py tests/test_api_route_inventory.py tools/generate_api_tool_candidates.py tests/test_api_tool_candidates.py`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_follower_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py tests/unit/core_app/test_app_controller_offboard_safety.py::test_setpoints_status_uses_concrete_handler_and_commander_publication`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Focused result: 72 passed.
Phase 0 result: schema current, API/MCP candidate inventory current, 386 passed,
1 existing Starlette/httpx warning.

A first resumed Phase 0 attempt caught a local test-hygiene violation in the new
follower helper test (`return False` in a fake circuit breaker). The test helper
was fixed before final validation; no production behavior changed for that fix.

## Review Gate

Independent reviewer `Bernoulli` reported no blockers. Residual risks matched
the tracked scope: intentionally preserved legacy validation wrapping, direct
`Parameters.FOLLOWER_MODE` mutation, process-local-only setpoint status, and no
new ASGI/TestClient path coverage for all seven legacy routes. The reviewer
confirmed the moved route bodies, thin `FastAPIHandler` delegates, generated
API/MCP provenance, and no overclaim of typed follower promotion, complete
follower cleanup, runtime MCP exposure, QGC playback, PX4/SITL/HIL, field, or
real-aircraft success.

## Evidence Boundary

This is a backend API boundary extraction only.

No typed `/api/v1/following/*` or `/api/v1/follower/*` route was added. No
legacy follower route was retired. Follower health, follower restart, and
follower config-manager route bodies remain in `FastAPIHandler` for a separate
PXE-0008 sub-slice. No runtime MCP endpoint, executor, `tools/list`,
`tools/call`, or callable tool surface was added. No service/deployment action,
target proxy/firewall/TLS setup, QGC playback, PX4/SITL/HIL, field test, or
real-aircraft behavior was performed or claimed.

## Residual Risk

The extraction intentionally preserved existing legacy behavior, including
known rough edges that require separate typed follower API design work:

- Follower profile and setpoint status responses remain ad hoc compatibility
  payloads rather than typed `/api/v1` contracts.
- Missing/invalid profile validation preserves legacy broad wrapping behavior
  instead of returning structured typed errors.
- `POST /api/follower/switch-profile` still mutates `Parameters.FOLLOWER_MODE`
  directly and uses active follower `switch_mode()` in the request path.
- Setpoint status still reports process-local state only; it does not prove PX4
  receipt, vehicle movement, QGC/GCS display, SITL/HIL, or field behavior.
- Follower health/restart/config-manager route bodies remain to be extracted
  before a complete legacy follower boundary can be claimed.

## Next Planned Slice

Continue PXE-0008 by extracting another remaining legacy route family without
changing route inventory/security policy. Candidate order:

1. Remaining follower health/restart/config-manager route-body boundary.
2. Safety route-body boundary.
3. Video/media route-body boundaries.
4. Typed `/api/v1/following/*`, safety, and media promotions only after legacy
   boundaries, structured errors, request/response models, docs, tests, and
   deprecation gates are ready.
