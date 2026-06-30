# Phase 4 Legacy WebRTC Signaling Boundary

Date: 2026-06-29  
Issue: PXE-0008  
Scope: behavior-preserving legacy API route-boundary hardening only.

## Summary

Closed the remaining legacy media signaling route-boundary record by confirming
and guarding that `WS /ws/webrtc_signaling` is registered directly to
`WebRTCManager.signaling_handler`.

`FastAPIHandler` still constructs `WebRTCManager`, refreshes the manager exposure
policy on server start, awaits manager shutdown on stop, and registers the legacy
WebSocket path. The signaling state machine itself lives in
`src/classes/webrtc_manager.py`.

## Preserved Behavior

- Route registration remains `WEBSOCKET /ws/webrtc_signaling`.
- The route remains classified by the existing media WebSocket security policy.
- Streaming-disabled requests still close before `accept()` with code `1008`.
- Host/Origin rejection still closes before `accept()` with code `1008`.
- Authorization still runs through `authorize_websocket_request()`.
- Disabled audit for an allowed media-read signaling request now has an explicit
  path test proving the route follows the existing policy and reaches the
  accept-then-capacity gate rather than changing WebRTC behavior.
- Capacity behavior remains accept-then-reserve; excess sessions receive the
  legacy JSON error and close with code `1008`.
- Peer IDs remain server-owned and cannot be selected by a client message.
- Browser-session revocation still closes the signaling socket and cleans up the
  socket-owned peer.
- SDP/ICE handling and bounded peer shutdown remain owned by `WebRTCManager`.

## Explicit Non-Scope

- No typed `/api/v1/streams/*` WebRTC route was added.
- No WebRTC signaling protocol, peer cleanup, auth policy, or capacity behavior
  was redesigned.
- No compatibility alias was retired.
- No runtime MCP exposure or callable tool surface was added.
- No WebRTC browser receipt, QGC playback, PX4, SITL, HIL, field, deployment,
  service installation, or real-aircraft behavior was performed or claimed.

## Files Changed

- `tools/generate_api_tool_candidates.py`
- `tests/test_api_route_inventory.py`
- `tests/test_api_tool_candidates.py`
- `tests/unit/core_app/test_api_exposure_policy.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/route-inventory.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/video/04-streaming/webrtc.md`
- `docs/reporting/agent-ops/codex-modernization/checkpoints/2026-06-29-phase-4-legacy-webrtc-signaling-boundary.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile tools/generate_api_tool_candidates.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/unit/core_app/test_api_exposure_policy.py`
- `.venv/bin/python tools/generate_api_tool_candidates.py`
- Focused WebRTC/API/docs gate:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_route_inventory.py::test_webrtc_signaling_route_body_is_owned_by_webrtc_manager tests/unit/core_app/test_api_exposure_policy.py::test_streaming_disabled_rejects_webrtc_signaling_before_accept tests/unit/core_app/test_api_exposure_policy.py::test_webrtc_signaling_rejects_unapproved_origin_before_accept tests/unit/core_app/test_api_exposure_policy.py::test_webrtc_signaling_rejects_unapproved_host_before_accept tests/unit/core_app/test_api_exposure_policy.py::test_webrtc_audit_disabled_blocks_allowed_security_critical tests/unit/core_app/test_api_exposure_policy.py::test_webrtc_signaling_audit_disabled_media_read_reaches_capacity_gate tests/unit/core_app/test_api_exposure_policy.py::test_webrtc_signaling_rejects_query_token_before_accept tests/unit/streaming/test_streaming_lifecycle.py::test_webrtc_signaling_handler_cancels_blocked_receive_and_closes_peer_on_revocation tests/unit/streaming/test_streaming_lifecycle.py::test_webrtc_client_peer_ids_cannot_overwrite_existing_peers tests/unit/streaming/test_streaming_lifecycle.py::test_webrtc_signaling_limit_reserves_capacity_before_peer_allocation tests/test_api_tool_candidates.py tests/test_docs_infrastructure_consistency.py::test_project_markdown_local_links_exist`
- Broader API/security/docs/WebRTC lifecycle gate:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/test_api_route_inventory.py tests/test_api_security_policy.py tests/test_api_tool_candidates.py tests/test_docs_infrastructure_consistency.py tests/unit/core_app/test_api_exposure_policy.py tests/unit/streaming/test_streaming_lifecycle.py`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Result: focused gate passed with 20 tests and one existing Starlette/httpx
warning; broader API/security/docs/WebRTC lifecycle gate passed with 192 tests
and the same warning; Phase 0 passed with schema current, API/MCP candidate
inventory current, and 390 tests passing with the same warning.

## Review

Pre-implementation read-only review found no hard blocker and confirmed that
the `/ws/webrtc_signaling` state machine already lives in `WebRTCManager`, not
`FastAPIHandler`. The review identified invariants to preserve: exact route and
security classification, pre-accept streaming/Host/Origin/auth/audit gates,
accept-then-capacity behavior, server-owned peer IDs, browser-session
revocation, bounded cleanup, SDP/ICE handling, candidate provenance, and no new
typed/MCP/SITL/field claims.

Final independent review found no blockers. The reviewer verified direct
registration to `WebRTCManager.signaling_handler`, unchanged signaling ownership
inside `webrtc_manager.py`, preserved accept-then-reserve capacity behavior,
server-owned peer IDs, cleanup ownership, media-read security classification,
disabled-audit media-read behavior, generated candidate provenance, and no
typed `/api/v1`, MCP, WebRTC receipt, QGC, PX4/SITL/HIL/field, or real-aircraft
overclaims. The reviewer noted the new checkpoint file was still untracked
before staging; staging this slice closes that low reporting risk.

## Residual Risk

- The route remains a legacy WebSocket compatibility surface, not a typed
  `/api/v1` stream resource.
- Media-health still reports only process-local WebRTC peer counts, not proof of
  remote peer receipt or usable video.
- No full browser/WebRTC media receipt test ran in this slice.

## Next

- Continue PXE-0008 toward typed `/api/v1` replacements and tracked legacy
  compatibility retirement planning.
- Keep any future WebRTC signaling protocol changes behind focused peer,
  security, lifecycle, and browser evidence gates.
