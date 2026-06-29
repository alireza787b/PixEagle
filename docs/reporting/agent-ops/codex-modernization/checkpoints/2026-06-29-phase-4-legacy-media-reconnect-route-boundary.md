# Phase 4 Legacy Media Reconnect Route Boundary

Date: 2026-06-29
Issue: PXE-0008

## Scope

Moved the legacy `POST /api/video/reconnect` mutation route body out of
`FastAPIHandler` and into `src/classes/api_legacy_media_routes.py`.

This slice is behavior-preserving. It does not promote the route to typed
`/api/v1`, does not change security policy, and does not claim remote media,
QGC, PX4, SITL, HIL, field, or real-aircraft evidence.

## Changed

- Added `reconnect_video(handler)` to `api_legacy_media_routes.py`.
- Preserved the legacy `FastAPIHandler.reconnect_video()` docstring and changed
  its body to a one-call delegate.
- Preserved legacy response semantics:
  - missing `video_handler` raises HTTP 503 with `Video handler not initialized`;
  - successful `force_recovery()` returns HTTP 200 with updated video health;
  - failed `force_recovery()` returns HTTP 503 with updated video health;
  - unexpected exceptions are logged as `Error in reconnect_video` and mapped to
    HTTP 500 with the original detail string.
- Expanded media helper tests for reconnect success, failed recovery, missing
  video handler, and unexpected health failure.
- Updated route-inventory guardrails so reconnect body strings stay out of
  `FastAPIHandler`; at this checkpoint, HTTP MJPEG and optimized WebSocket
  media transport handlers still remained outside the helper.
- Regenerated API/MCP tool candidate provenance because `fastapi_handler.py` and
  `api_legacy_media_routes.py` changed.

## Files Changed

- `src/classes/api_legacy_media_routes.py`
- `src/classes/fastapi_handler.py`
- `tests/unit/core_app/test_api_legacy_media_routes.py`
- `tests/test_api_route_inventory.py`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/apis/api-modernization-blueprint.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/video/01-architecture/error-recovery.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-06.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `.venv/bin/python tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_legacy_media_routes.py src/classes/fastapi_handler.py tests/unit/core_app/test_api_legacy_media_routes.py tests/test_api_route_inventory.py tools/generate_api_tool_candidates.py`
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -p no:cacheprovider tests/unit/core_app/test_api_legacy_media_routes.py tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py`
- `git diff --check`
- `PYTHON=.venv/bin/python make phase0-check`

Result: focused gate passed with 75 tests after docs updates. Full Phase 0
passed with 388 tests and one existing Starlette/httpx deprecation warning.

## Independent Review

- Independent media/API reviewer found no code blockers.
- Reviewer verified reconnect behavior, wrapper registration/docstring,
  unchanged security policy, and generated candidate inventory.
- Reviewer caught the pre-final validation placeholder in this report; it was
  replaced with the final Phase 0 result above.
- Reviewer noted no ASGI-level reconnect route test and no exact logger-message
  assertion for unexpected reconnect exceptions; these remain low-risk residual
  gaps for this source-ownership slice.

## Residual Risk

- The route remains a legacy media mutation, not a typed `/api/v1` action with
  idempotency or action-store tracking.
- The tests prove helper behavior and static ownership only; they do not prove a
  camera source actually recovered or that a remote browser/QGC client received
  media.
- No ASGI path-level reconnect test was added.
- The unexpected-error test asserts that logging happened, not the exact log
  message text.
- The HTTP MJPEG route body was handled in the follow-up HTTP boundary.
  Long-lived `WS /ws/video_feed` and WebRTC signaling route bodies still live in
  `FastAPIHandler` or the WebRTC manager.

## Next

- Continue from the follow-up HTTP boundary before video WebSocket/WebRTC
  transport cleanup.
- Keep circuit-breaker toggle/safety-bypass/reset as a separate guarded mutation
  cleanup.
