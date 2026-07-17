# Phase 4 Legacy Recording Route Boundary

- Date: 2026-06-27
- Issue: PXE-0008 partial
- Slice: behavior-preserving legacy recording route-body extraction
- Branch: `codex/modernization-pxe0040-runtime-20260604`

## Summary

This slice moved legacy recording and storage HTTP compatibility behavior out
of `FastAPIHandler` and into `src/classes/api_legacy_recording_routes.py`.

Moved route bodies:

- `POST /api/recording/start`
- `POST /api/recording/pause`
- `POST /api/recording/resume`
- `POST /api/recording/stop`
- `GET /api/recording/status`
- `POST /api/recording/toggle`
- `GET /api/recordings`
- `GET /api/recordings/{filename}`
- `DELETE /api/recordings/{filename}`
- `GET /api/storage/status`
- `POST /api/recording/include-osd/{enabled}`

`FastAPIHandler` keeps route registration and thin wrapper methods only. Route
inventory, security policy, auth scopes, legacy paths, response payload shapes,
source dimension probing, file download media types, Range response headers,
path basename sanitization, delete error mapping, and include-OSD truthy
parsing are intended to be unchanged.

## Files Changed

- `src/classes/api_legacy_recording_routes.py`
- `src/classes/fastapi_handler.py`
- `tools/generate_api_tool_candidates.py`
- `tests/unit/core_app/test_api_legacy_recording_routes.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-27-phase-4-legacy-recording-route-boundary.md`

## Validation

Completed before final reporting:

- `.venv/bin/python -m py_compile src/classes/fastapi_handler.py src/classes/api_legacy_recording_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_api_legacy_recording_routes.py tools/generate_api_tool_candidates.py`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_recording_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Focused result: 66 passed.
Phase 0 result: schema current, API/MCP candidate inventory current, 383
passed, 1 existing Starlette/httpx warning.

## Evidence Boundary

This is a backend API boundary extraction only.

No typed `/api/v1/recordings/*` route was added. No legacy recording route was
retired. No runtime MCP endpoint, executor, `tools/list`, `tools/call`, or
callable tool surface was added. No service/deployment action, target
proxy/firewall/TLS setup, QGC playback, PX4/SITL/HIL, field test, or
real-aircraft behavior was performed or claimed.

## Residual Risk

The extraction intentionally preserved existing legacy behavior, including
known rough edges that require separate typed `/api/v1/recordings` design work:

- recording responses remain ad hoc compatibility payloads rather than typed
  `/api/v1` contracts;
- recording start/toggle still derive source dimensions from the current video
  handler/capture object at request time;
- Range parsing remains permissive and invalid ranges still become HTTP 500
  responses;
- delete still maps manager error messages containing `not found` to 404 and
  other manager errors to 400;
- file download still relies on basename sanitization plus the recording
  manager output directory contract.

## Next Planned Slice

Continue PXE-0008 by extracting another remaining legacy route family without
changing route inventory/security policy. Candidate order:

1. OSD route-body extraction.
2. GStreamer route-body extraction.
3. Follower/safety/video/media route-body boundaries.
4. Typed `/api/v1/recordings/*` design/promotion only after legacy boundaries,
   structured errors, request/response models, docs, tests, and deprecation
   gates are ready.
