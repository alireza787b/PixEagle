# Phase 4 Legacy OSD Route Boundary

- Date: 2026-06-27
- Issue: PXE-0008 partial
- Slice: behavior-preserving legacy OSD route-body extraction
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice moved legacy OSD HTTP compatibility behavior out of
`FastAPIHandler` and into `src/classes/api_legacy_osd_routes.py`.

Moved route bodies:

- `GET /api/osd/status`
- `POST /api/osd/toggle`
- `GET /api/osd/presets`
- `POST /api/osd/preset/{preset_name}`
- `GET /api/osd/color-modes`
- `POST /api/osd/color-mode/{mode}`
- `GET /api/osd/modes`

`FastAPIHandler` keeps route registration and thin wrapper methods only. Route
inventory, security policy, auth scopes, legacy paths, response payload shapes,
preset directory lookup, preset-name allowlist validation, cache invalidation
reasons, renderer reinitialization, and existing legacy error mappings are
intended to be unchanged.

## Files Changed

- `src/classes/api_legacy_osd_routes.py`
- `src/classes/fastapi_handler.py`
- `tools/generate_api_tool_candidates.py`
- `tests/unit/core_app/test_api_legacy_osd_routes.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-27-phase-4-legacy-osd-route-boundary.md`

## Validation

Completed before final reporting:

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_osd_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_osd_routes.py tests/test_api_route_inventory.py tools/generate_api_tool_candidates.py tests/test_api_tool_candidates.py`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_osd_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Focused result: 67 passed.
Phase 0 result: schema current, API/MCP candidate inventory current, 384
passed, 1 existing Starlette/httpx warning.

## Evidence Boundary

This is a backend API boundary extraction only.

No typed `/api/v1/osd/*` route was added. No legacy OSD route was retired. No
runtime MCP endpoint, executor, `tools/list`, `tools/call`, or callable tool
surface was added. No service/deployment action, target proxy/firewall/TLS
setup, QGC playback, PX4/SITL/HIL, field test, or real-aircraft behavior was
performed or claimed.

## Residual Risk

The extraction intentionally preserved existing legacy behavior, including
known rough edges that require separate typed `/api/v1/osd` design work:

- OSD responses remain ad hoc compatibility payloads rather than typed
  `/api/v1` contracts.
- `POST /api/osd/toggle` still maps an unavailable OSD handler through the
  broad legacy exception wrapper to HTTP 500 even though the inner error is
  constructed as HTTP 503.
- Preset loading still mutates `Parameters.OSD_PRESET` directly and reloads
  the renderer inside the request path when an OSD handler is present.
- Preset lookup still depends on the process working directory and
  `configs/osd_presets`.
- Color-mode APIs still depend on `app_controller.osd_mode_manager` being
  present and return legacy untyped payloads.

## Next Planned Slice

Continue PXE-0008 by extracting another remaining legacy route family without
changing route inventory/security policy. Candidate order:

1. GStreamer route-body extraction.
2. Follower route-body boundary.
3. Safety route-body boundary.
4. Video/media route-body boundaries.
5. Typed `/api/v1/osd/*`, `/api/v1/gstreamer/*`, and related promotions only
   after legacy boundaries, structured errors, request/response models, docs,
   tests, and deprecation gates are ready.
