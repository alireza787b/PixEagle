# Phase 4 Legacy Media WebSocket Route Boundary

Date: 2026-06-29
Issue: PXE-0008

## Scope

Moved the legacy `WS /ws/video_feed` route body and its `ClientConnection`
state object out of `FastAPIHandler` and into
`src/classes/api_legacy_media_routes.py`.

This slice preserves the existing legacy WebSocket contract. It does not promote
the route to typed `/api/v1`, does not change security policy, and does not
claim remote browser, QGC, GCS, PX4, SITL, HIL, field, or real-aircraft media
receipt.

## Changed

- Added `ClientConnection` and `video_feed_websocket_optimized(handler,
  websocket)` to `api_legacy_media_routes.py`.
- Preserved the legacy `FastAPIHandler.video_feed_websocket_optimized()`
  docstring and changed its body to a one-call delegate.
- Preserved WebSocket route behavior:
  - disabled streaming still closes before accept with code `1008`;
  - Host/Origin rejection still happens before accept and records the security
    audit denial;
  - WebSocket authorization still happens before accept and rejects missing or
    insufficient credentials;
  - security-audit write failure still closes before accept with code `1011`;
  - capacity remains checked after accept, preserving current
    accept-then-`WS_MAX_CONNECTIONS` behavior;
  - client principal, quality, frame queue, active-connection count,
    frame-publisher registration, and adaptive-quality registration are
    preserved;
  - send, receive, and browser-session monitor tasks still race until first
    completion, cancel pending work, and always clean up the connection.
- Kept `_ws_send_frames`, `_ws_receive_messages`, `_ws_monitor_session`,
  `_cleanup_websocket_client`, heartbeat stale-close, and shutdown close-all in
  `FastAPIHandler` because they are shared streaming lifecycle helpers, not only
  route-body code.
- Added direct production-helper tests for JSON metadata followed by binary JPEG
  delivery, quality-command and ping/pong handling, and three-error send-loop
  termination.
- Fixed WebSocket dropped-frame accounting so three consecutive send errors
  count as exactly three drops instead of five.
- Updated docs to describe the actual WebSocket wire envelope: one JSON metadata
  message followed by one binary JPEG message per frame.

## Files Changed

- `src/classes/api_legacy_media_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/test_api_route_inventory.py`
- `tests/test_network_exposure_defaults.py`
- `tests/unit/streaming/test_streaming_lifecycle.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/video/04-streaming/websocket.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-29-phase-4-legacy-media-status-route-boundary.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-29-phase-4-legacy-media-reconnect-route-boundary.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-29-phase-4-legacy-media-http-route-boundary.md`

## Validation

- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_media_routes.py src/classes/fastapi_handler.py tests/unit/streaming/test_streaming_lifecycle.py tests/test_api_route_inventory.py tests/test_network_exposure_defaults.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/streaming/test_streaming_lifecycle.py::test_video_websocket_send_frames_emits_metadata_then_jpeg tests/unit/streaming/test_streaming_lifecycle.py::test_video_websocket_receive_quality_and_ping tests/unit/streaming/test_streaming_lifecycle.py::test_video_websocket_send_frames_stops_after_three_send_errors tests/unit/core_app/test_api_exposure_policy.py::test_video_websocket_rejects_unapproved_origin_before_accept tests/unit/core_app/test_api_exposure_policy.py::test_streaming_disabled_rejects_video_websocket_before_accept tests/unit/core_app/test_api_exposure_policy.py::test_video_websocket_rejects_unapproved_host_before_accept tests/unit/core_app/test_api_exposure_policy.py::test_video_websocket_allows_same_host_native_missing_origin_before_accept tests/unit/core_app/test_api_exposure_policy.py::test_video_websocket_rejects_missing_bearer_before_accept tests/unit/streaming/test_streaming_lifecycle.py::test_video_websocket_monitor_closes_after_browser_session_revocation tests/unit/streaming/test_streaming_lifecycle.py::test_websocket_cleanup_closes_transport_and_unregisters_once tests/unit/streaming/test_streaming_lifecycle.py::test_close_all_websocket_clients_uses_single_cleanup_path tests/unit/streaming/test_streaming_lifecycle.py::test_fastapi_stop_drains_streaming_resources tests/test_network_exposure_defaults.py::test_websocket_handlers_check_origin_before_accept tests/test_api_route_inventory.py::test_legacy_media_route_bodies_are_not_defined_in_fastapi_handler`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist tests/test_api_tool_candidates.py tests/test_network_exposure_defaults.py::test_websocket_handlers_check_origin_before_accept tests/test_api_route_inventory.py::test_legacy_media_route_bodies_are_not_defined_in_fastapi_handler`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Result: focused WebSocket/media/security gate passed with 14 tests and one
existing Starlette/httpx deprecation warning. Focused docs/API guardrails passed
with 12 tests. Full Phase 0 passed with 388 tests and one existing
Starlette/httpx deprecation warning.

## Independent Review

- Read-only media/API reviewer found no extraction blockers before the move.
- Reviewer identified the required invariants: route registration and
  `media:read` classification, fail-closed pre-accept checks, current
  accept-then-capacity behavior, client/principal registration, send/receive/
  session-monitor task orchestration, idempotent cleanup, heartbeat/shutdown
  cleanup paths, JSON-plus-binary frame behavior, quality/ping handling, and
  browser-session revocation.
- Reviewer recommended keeping heartbeat, cleanup, and WebRTC signaling outside
  this route-body slice, and called out missing direct production-helper tests
  for send/receive behavior. This slice added those tests and fixed the
  discovered frame-drop overcount.
- Final read-only media/API reviewer found no blockers after implementation.
  The reviewer verified unchanged route registration, one-call wrapper
  delegation, pre-accept security gates, safe `ClientConnection` ownership,
  unchanged security/MCP exposure, correct drop-count fix, accurate
  JSON-metadata-plus-binary-JPEG docs, and remaining debt alignment.

## Residual Risk

- The route remains a legacy WebSocket media stream, not a typed `/api/v1` stream
  contract.
- The tests prove local helper/wrapper behavior, WebSocket auth/Origin
  rejection, task cleanup, frame-envelope behavior, quality/ping handling, and
  dropped-frame accounting; they do not prove a remote browser/QGC/GCS received
  usable media.
- There is still no ASGI path-level successful `/ws/video_feed` integration test
  with real Starlette WebSocket clients.
- WebRTC signaling route bodies still live in the WebRTC manager.

## Next

- Review WebRTC signaling route-body ownership separately because it owns peer
  IDs, peer capacity, SDP/ICE handling, session revocation, and peer cleanup.
- Keep circuit-breaker toggle/safety-bypass/reset as a separate guarded mutation
  cleanup.
