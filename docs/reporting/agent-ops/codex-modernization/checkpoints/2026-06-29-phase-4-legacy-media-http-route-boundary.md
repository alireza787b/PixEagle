# Phase 4 Legacy Media HTTP Route Boundary

Date: 2026-06-29
Issue: PXE-0008

## Scope

Moved the legacy `GET /video_feed` HTTP MJPEG route body and its
session-bound streaming response helper out of `FastAPIHandler` and into
`src/classes/api_legacy_media_routes.py`.

This slice is behavior-preserving. It does not promote the route to typed
`/api/v1`, does not change security policy, and does not claim remote browser,
QGC, GCS, PX4, SITL, HIL, field, or real-aircraft media receipt.

## Changed

- Added `video_feed(handler, request)` to `api_legacy_media_routes.py`.
- Moved `SessionBoundStreamingResponse` into `api_legacy_media_routes.py`
  because it is only used by the legacy HTTP MJPEG route.
- Preserved the legacy `FastAPIHandler.video_feed()` docstring and changed its
  body to a one-call delegate.
- Preserved HTTP MJPEG behavior:
  - streaming-disabled checks still raise HTTP 503 before registration;
  - max HTTP connection checks still raise HTTP 503;
  - frame publisher and quality-engine registration still happen after the
    connection is accepted;
  - duplicate-frame skipping, frame-id cache encoding, adaptive quality, stats,
    and frame-drop accounting are unchanged;
  - browser-session streams still terminate on revocation and record the media
    session-revoked audit event;
  - generator cleanup still unregisters quality and frame-publisher clients and
    removes the HTTP connection record.
- Kept `WS /ws/video_feed` and WebRTC signaling out of this slice because they
  own bidirectional task orchestration, peer state, and close-path behavior.
- Updated route-inventory guardrails so the HTTP MJPEG body markers stay out of
  `FastAPIHandler`, while the WebSocket media handler remains outside the helper.
- Regenerated API/MCP tool candidate provenance because `fastapi_handler.py` and
  `api_legacy_media_routes.py` changed.

## Files Changed

- `src/classes/api_legacy_media_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/test_api_route_inventory.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-29-phase-4-legacy-media-http-route-boundary.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-29-phase-4-legacy-media-status-route-boundary.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-29-phase-4-legacy-media-reconnect-route-boundary.md`

## Validation

- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_media_routes.py src/classes/fastapi_handler.py tests/test_api_route_inventory.py tests/unit/core_app/test_api_legacy_media_routes.py tests/unit/streaming/test_streaming_lifecycle.py tests/unit/core_app/test_api_exposure_policy.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_media_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_api_exposure_policy.py::test_streaming_disabled_rejects_http_video_route tests/unit/streaming/test_streaming_lifecycle.py::test_http_mjpeg_generator_stops_after_browser_session_revocation tests/unit/streaming/test_streaming_lifecycle.py::test_http_mjpeg_revocation_cancels_blocked_response_delivery tests/test_network_exposure_defaults.py::test_websocket_handlers_check_origin_before_accept`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Result: focused gate passed with 60 tests and one existing Starlette/httpx
deprecation warning. Full Phase 0 passed with 388 tests and one existing
Starlette/httpx deprecation warning.

## Independent Review

- Independent media/API reviewer found no code blockers.
- Reviewer verified that `/video_feed` registration still lives in
  `FastAPIHandler`, the wrapper delegates to `api_legacy_media_routes.py`, and
  the moved helper preserves HTTP 503 gates, frame publisher and quality
  registration, generator behavior, cleanup, and session-revocation audit
  behavior.
- Reviewer verified that `WS /ws/video_feed` and WebRTC signaling remain outside
  this helper slice and that no security policy or MCP exposure changed.
- Reviewer noted that tests still exercise the moved route through the
  `FastAPIHandler.video_feed()` wrapper rather than direct helper tests, and
  that there is no ASGI path-level `/video_feed` test for max-connection,
  adaptive-quality, stats, or drop behavior. These remain low-risk residual gaps
  for this extraction boundary.

## Residual Risk

- The route remains a legacy media stream, not a typed `/api/v1` stream contract.
- The tests prove local helper/wrapper behavior and session-revocation cleanup;
  they do not prove a remote browser/QGC/GCS received usable media.
- WebSocket media and WebRTC signaling route bodies still live in
  `FastAPIHandler` or the WebRTC manager.

## Next

- Review and extract video WebSocket media route bodies only after preserving
  streaming-disabled, host/origin rejection before accept, authorization before
  accept, max-connection close behavior, task cancellation, session revocation,
  and cleanup behavior.
- Keep circuit-breaker toggle/safety-bypass/reset as a separate guarded mutation
  cleanup.
