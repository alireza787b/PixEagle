# Phase 4 Legacy Media Status Route Boundary

Date: 2026-06-29
Issue: PXE-0008
Scope: behavior-preserving legacy API route-body extraction only.

## Summary

Moved bounded legacy media observability route bodies out of `FastAPIHandler` and
into `src/classes/api_legacy_media_routes.py`.

Routes covered:

- `GET /api/streaming/status`
- `GET /stats`
- `GET /api/video/health`

`FastAPIHandler` keeps route registration and one-call wrappers only. Route
inventory, auth/security policy, legacy paths, and legacy response shapes remain
unchanged.

## Preserved Behavior

- Streaming status still reports active transport selection, HTTP/WebSocket/
  WebRTC client counts, adaptive-quality state, GStreamer encoder status,
  pipeline metrics, stream config, and timestamp.
- Streaming stats still reports frame counters, bandwidth, HTTP/WebSocket
  counts, per-WebSocket client summaries, frame-cache size, server uptime, and
  OSD pipeline stats.
- OSD pipeline stat failures still degrade to `{}` and log debug output.
- Video health still reports video connection health plus SmartTracker/OBB
  pipeline diagnostics.
- Video health errors still map to legacy `HTTPException(500)`.

## Explicit Non-Scope

- At this checkpoint, `POST /api/video/reconnect` remained in `FastAPIHandler`
  for a separate media mutation cleanup because it calls live
  `video_handler.force_recovery()`. That follow-up is tracked by
  `2026-06-29-phase-4-legacy-media-reconnect-route-boundary.md`.
- At this checkpoint, `GET /video_feed` and `WS /ws/video_feed` remained in
  `FastAPIHandler` for later transport/lifecycle slices because they own
  long-lived generators, WebSocket tasks, session revocation, and cleanup
  behavior. The HTTP MJPEG follow-up is tracked by
  `2026-06-29-phase-4-legacy-media-http-route-boundary.md`.
- `WS /ws/webrtc_signaling` remains delegated to `WebRTCManager`.
- No typed `/api/v1/streams/*` route was added.
- No compatibility alias was retired.
- No runtime MCP exposure or callable tool surface was added.
- No QGC playback, PX4, SITL, HIL, field, deployment, service installation, or
  real-aircraft behavior was performed or claimed.

## Files Changed

- `src/classes/api_legacy_media_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/unit/core_app/test_api_legacy_media_routes.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/README.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_media_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_media_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_media_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Result: focused gate passed with 72 tests. Full Phase 0 passed with 388 tests
and one existing Starlette/httpx deprecation warning.

## Independent Review

- Independent media/API reviewer found no blockers.
- Reviewer noted legacy OpenAPI descriptions could drift if wrapper docstrings
  were dropped; the wrapper docstrings were restored while keeping one-call
  delegate bodies.
- Reviewer also noted no ASGI path-level tests were added; that remains an
  acknowledged residual gap for this source-ownership slice.

## Residual Risk

- The moved routes remain legacy ad hoc JSON responses, not typed Pydantic
  `/api/v1` contracts.
- These routes report process-local media status only; they do not prove remote
  browser, QGC, WebRTC peer, GCS, PX4, SITL, HIL, or field media receipt.
- `POST /api/video/reconnect` was handled in the follow-up reconnect boundary
  and remains a legacy media mutation without typed action/idempotency semantics.
- The HTTP MJPEG route body was handled in the follow-up HTTP boundary.
  Long-lived video WebSocket/WebRTC transport route bodies still live in
  `FastAPIHandler` or the WebRTC manager.
- No ASGI path-level test was added for each route; coverage is helper-level plus
  static route inventory/security/candidate gates.

## Next

- Continue from the follow-up media HTTP boundary before video WebSocket/WebRTC
  transport cleanup.
