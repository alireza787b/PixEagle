# 2026-06-18 Phase 4 Streaming Media-Health API

## Slice

- Phase: 4 API/setup/runtime modernization
- Issue: PXE-0068
- Scope: add typed backend media-health reporting without proving remote media
  receipt or weakening PixEagle's media authorization boundary.

## Summary

This slice closes the PXE-0068 backend media-health API foundation. PixEagle now
has a typed, authenticated read route for process-local media transport and
frame-publisher health:

```http
GET /api/v1/streams/media-health
```

Implemented behavior:

- added `src/classes/api_v1_streams.py` for process-local media snapshots;
- added typed Pydantic response contracts and structured error metadata;
- registered `GET /api/v1/streams/media-health` under `/api/v1`;
- classified the route as authenticated `media:read` in the API security policy;
- kept the route non-callable and unpromoted in agent/MCP documentation;
- regenerated the non-callable OpenAPI tool-candidate inventory;
- added route inventory, security policy, agent-candidate, and media-health unit
  coverage;
- documented the endpoint in API, core-app, video, and streaming config docs.

The response reports:

- HTTP MJPEG, backend JPEG WebSocket, WebRTC signaling, and GStreamer UDP/H.264
  transport state;
- `Streaming.ENABLE_STREAMING`, transport connection limits, disabled and
  zero-capacity transport state;
- frame-publisher freshness, `latest_frame_stale`, sent/dropped counters, cache
  size, and adaptive-quality state;
- GStreamer UDP pipeline activity without pretending UDP has a connected-client
  count;
- exposure/auth posture without credential material.

## Security And Claim Boundary

The route requires `media:read`; a `status:read` bearer token is insufficient.
The generated candidate now uses media-specific sensitivity
`media_transport_health`, not generic `runtime_status`.

The `claim_boundary` is explicit: this route is PixEagle process-local
observability only. It does not prove that a remote browser, QGroundControl,
WebRTC peer, GCS, PX4, SITL, HIL, or field video path received usable media.

`Streaming.ENABLE_STREAMING` is now enforced by the runtime media routes:

- `/video_feed` returns `503` when backend streaming is disabled;
- `/ws/video_feed` closes before accept when disabled;
- `/ws/webrtc_signaling` closes before accept when disabled.

No runtime MCP endpoint, `tools/list`, `tools/call`, QGC branch mutation,
Docker/PX4/SITL/HIL, service install/start, deployment, or real-aircraft control
was performed or claimed.

## Independent Review

Read-only reviewers inspected API contracts, media runtime semantics,
security/MCP governance, and documentation. Findings fixed before this
checkpoint:

- media-health initially ignored `Streaming.ENABLE_STREAMING`;
- stale/frozen published frames could still classify as active;
- GStreamer active output with no frame could still classify as active;
- `max_connections=0` was reported as idle instead of disabled;
- GStreamer UDP health reported a fake connected-client count;
- generated agent-candidate metadata mislabeled media-health as
  `runtime_status`;
- the handler had an unnecessary direct media-health helper import/wrapper;
- live governance records still said six reviewed candidates and listed backend
  media-health reporting as remaining work;
- top-level core-app docs omitted the new endpoint.

Residual reviewer notes carried forward:

- stale WebSocket lifecycle cleanup can still under-report sockets that never
  received a frame and should be handled in a lifecycle/refactor slice;
- shutdown cleanup should explicitly close WebRTC peer connections and release
  GStreamer output in a later runtime cleanup slice;
- dashboard/service status still need to consume `/api/v1/streams/media-health`
  instead of relying on legacy status/stat views.

## Files Changed

- `src/classes/api_v1_streams.py`
- `src/classes/api_v1_contracts.py`
- `src/classes/api_v1_paths.py`
- `src/classes/api_v1_read_routes.py`
- `src/classes/fastapi_api_v1_routes.py`
- `src/classes/fastapi_handler.py`
- `src/classes/webrtc_manager.py`
- `src/classes/api_security_policy.py`
- `tools/generate_api_tool_candidates.py`
- `docs/agent-context/agent_tools.yaml`
- `docs/agent-context/agent_policy.yaml`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/agent-context/README.md`
- `docs/apis/api-modernization-blueprint.md`
- `docs/apis/api-security-policy.md`
- `docs/apis/route-inventory.md`
- `docs/core-app/README.md`
- `docs/core-app/02-components/fastapi-handler.md`
- `docs/core-app/03-api/README.md`
- `docs/video/04-streaming/README.md`
- `docs/video/04-streaming/http-mjpeg.md`
- `docs/video/04-streaming/websocket.md`
- `docs/video/06-configuration/streaming-config.md`
- `docs/KNOWN_ISSUES.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`
- `tests/test_api_route_inventory.py`
- `tests/test_api_security_policy.py`
- `tests/test_api_tool_candidates.py`
- `tests/unit/core_app/test_api_exposure_policy.py`
- `tests/unit/core_app/test_api_v1_streams.py`
- `Makefile`

## Validation

Passed:

- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/core_app/test_api_v1_streams.py -q`
  - 7 passed
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_security_policy.py tests/unit/core_app/test_api_exposure_policy.py -q`
  - 99 passed, 1 existing Starlette/httpx warning
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_api_route_inventory.py tests/test_api_tool_candidates.py tests/test_api_security_policy.py tests/unit/core_app/test_api_v1_streams.py tests/unit/core_app/test_api_exposure_policy.py -q`
  - 143 passed, 1 existing Starlette/httpx warning
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_docs_infrastructure_consistency.py -q`
  - 20 passed
- `PYTHONPATH=src .venv/bin/python -m py_compile src/classes/api_v1_streams.py src/classes/fastapi_handler.py src/classes/webrtc_manager.py tests/unit/core_app/test_api_v1_streams.py tests/test_api_security_policy.py tests/unit/core_app/test_api_exposure_policy.py`
- `PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py --check`
  - inventory current
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`
  - schema current: 41 sections, 549 parameters
- `PYTHON=.venv/bin/python make PYTHON=.venv/bin/python phase0-check`
  - schema current
  - API tool candidate inventory current
  - 246 passed
  - existing Starlette/httpx `TestClient` deprecation warning remains
- `git diff --check`

## Risks And Open Questions

- The endpoint reports process-local state only; remote QGC/browser/media
  receipt still needs future authenticated client evidence.
- Dashboard and service status have not yet been migrated to consume this route.
- WebRTC peer shutdown, GStreamer release on app shutdown, and never-fed stale
  WebSocket cleanup remain runtime lifecycle debt for a follow-up slice.
- `production_remote` remains gated on TLS/operator hardening, credential
  rollout, adversarial auth/media tests, and deployment evidence.

## Next Planned Slice

Continue Phase 4 cleanup under PXE-0068/PXE-0064:

1. Wire dashboard and service/status output to `/api/v1/streams/media-health`.
2. Harden WebRTC/GStreamer shutdown and stale WebSocket lifecycle cleanup.
3. Keep scanning setup/update/service docs for stale contradictions.
