# Phase 4 Legacy GStreamer Route Boundary

- Date: 2026-06-27
- Issue: PXE-0008 partial
- Slice: behavior-preserving legacy GStreamer route-body extraction
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice moved legacy GStreamer HTTP compatibility behavior out of
`FastAPIHandler` and into `src/classes/api_legacy_gstreamer_routes.py`.

Moved route bodies:

- `GET /api/gstreamer/status`
- `POST /api/gstreamer/toggle`

`FastAPIHandler` keeps route registration and thin wrapper methods only. Route
inventory, security policy, auth scopes, legacy paths, response payload shapes,
process-local writer/open detection, QGC UDP/RTP setup hints, existing handler
reuse, new handler creation, `Parameters.ENABLE_GSTREAMER_STREAM` mutation, and
failed-open HTTP 500 response shape are intended to be unchanged.

## Files Changed

- `src/classes/api_legacy_gstreamer_routes.py`
- `src/classes/fastapi_handler.py`
- `tools/generate_api_tool_candidates.py`
- `tests/unit/core_app/test_api_legacy_gstreamer_routes.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-27-phase-4-legacy-gstreamer-route-boundary.md`

## Validation

Completed before final reporting:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_gstreamer_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_gstreamer_routes.py tests/test_api_route_inventory.py tools/generate_api_tool_candidates.py tests/test_api_tool_candidates.py`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_gstreamer_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Focused result: 68 passed.
Phase 0 result: schema current, API/MCP candidate inventory current, 385
passed, 1 existing Starlette/httpx warning.

## Evidence Boundary

This is a backend API boundary extraction only.

No typed `/api/v1/streams/gstreamer*` route was added. No legacy GStreamer
route was retired. No runtime MCP endpoint, executor, `tools/list`,
`tools/call`, or callable tool surface was added. No service/deployment action,
target proxy/firewall/TLS setup, QGC playback, PX4/SITL/HIL, field test, or
real-aircraft behavior was performed or claimed.

## Residual Risk

The extraction intentionally preserved existing legacy behavior, including
known rough edges that require separate typed stream-control design work:

- GStreamer status/toggle responses remain ad hoc compatibility payloads rather
  than typed `/api/v1` contracts.
- Runtime toggle still mutates `Parameters.ENABLE_GSTREAMER_STREAM` directly
  and creates/initializes `GStreamerHandler` inside the request path.
- Failed pipeline open still returns a legacy JSON body with HTTP 500 rather
  than a structured typed error.
- Status still reports process-local writer/open state and does not prove any
  remote QGC/GCS receiver, network path, or playback success.
- The route still does not capture deployment evidence, GStreamer capability
  probe logs, or receiver artifacts.

## Next Planned Slice

Continue PXE-0008 by extracting another remaining legacy route family without
changing route inventory/security policy. Candidate order:

1. Follower route-body boundary.
2. Safety route-body boundary.
3. Video/media route-body boundaries.
4. Typed `/api/v1/streams/gstreamer*`, follower, safety, and media promotions
   only after legacy boundaries, structured errors, request/response models,
   docs, tests, and deprecation gates are ready.
