# 2026-06-19 Phase 4 Streaming Lifecycle Cleanup

- Phase: 4 API/MCP and setup modernization
- Slice: PXE-0068 streaming lifecycle cleanup
- Branch: `codex/modernization-pxe0040-runtime-20260604`
- Commit: pending at checkpoint write time

## Summary

This slice closes the PXE-0068 media runtime lifecycle follow-up that remained
after typed media-health and dashboard/service adoption.

Backend WebSocket video streaming now has one idempotent cleanup path. Stale
clients are detected from the last sent frame time, or from connection time when
no frame has ever been sent, so never-fed clients no longer remain tracked
forever. Cleanup removes the connection, refreshes active connection counts,
unregisters adaptive-quality and frame-publisher resources once, and optionally
closes the WebSocket transport.

`FastAPIHandler.stop()` now cancels background tasks, closes tracked WebSocket
streaming clients through that same cleanup path, clears HTTP MJPEG records,
drains WebRTC peers through a manager-level shutdown method, shuts down the
encoder pool, and then stops the server. WebRTC peer close waits are bounded so
a slow `RTCPeerConnection.close()` cannot stall API shutdown indefinitely.

GStreamer output is now released during `AppController.shutdown()`.
`GStreamerHandler.release()` stops the writer thread, releases and clears the
OpenCV writer reference, and drains queued frames even if writer release raises.
`initialize_stream()` releases any existing writer before replacing it, and
GStreamer status/toggle code treats the stream as active only when the writer is
present and opened.

The claim boundary is unchanged: this is process-local backend cleanup and
observability. It does not prove remote browser, QGroundControl, WebRTC peer,
GCS, PX4, SITL, HIL, or field media receipt.

## Files Changed

- `src/classes/fastapi_handler.py`
- `src/classes/webrtc_manager.py`
- `src/classes/gstreamer_handler.py`
- `src/classes/app_controller.py`
- `tests/unit/streaming/test_streaming_lifecycle.py`
- `docs/video/04-streaming/websocket.md`
- `docs/video/04-streaming/webrtc.md`
- `docs/video/03-gstreamer/output-pipeline.md`
- `docs/agent-context/generated/pixeagle-openapi-tool-candidates.yaml`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `docs/reporting/agent-ops/codex-modernization/phase-slice-map.md`

## Validation

- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/streaming/test_streaming_lifecycle.py -q`: 10 passed.
- `PYTHONPATH=src .venv/bin/python -m pytest tests/unit/streaming/test_streaming_lifecycle.py tests/unit/core_app/test_api_v1_streams.py tests/unit/core_app/test_api_exposure_policy.py tests/test_service_status_media_health.py tests/test_api_route_inventory.py tests/unit/core_app/test_parameters_reload.py tests/test_docs_infrastructure_consistency.py -q`: 160 passed with the existing Starlette/httpx warning.
- `PYTHON=.venv/bin/python bash scripts/check_schema.sh`: schema current, 41 sections, 549 parameters.
- `.venv/bin/python -m py_compile src/classes/fastapi_handler.py src/classes/webrtc_manager.py src/classes/gstreamer_handler.py src/classes/app_controller.py`: passed.
- `git diff --check`: passed.
- `PYTHONPATH=src .venv/bin/python tools/generate_api_tool_candidates.py`: regenerated candidate provenance after `fastapi_handler.py` changed.
- `PYTHON=.venv/bin/python make PYTHON=.venv/bin/python phase0-check`: schema current, API tool candidate inventory current, 247 passed with the existing Starlette/httpx warning.

## Reviewer Notes

Two independent read-only reviewers were used before finalizing the slice.

- Runtime reviewer found no blockers, but recommended bounded WebRTC close,
  unregister-in-finally semantics, releasing closed GStreamer writers before
  reinitialization, and draining the GStreamer queue even if writer release
  raises. Those changes were implemented and covered by focused lifecycle
  tests.
- Docs/reporting reviewer found one blocker: the issue register and phase-slice
  map referenced this checkpoint before it existed, and the June journal still
  listed lifecycle cleanup as future work. This checkpoint and the journal entry
  resolve that reporting gap.

No reviewer requested a blocking rework after the follow-up fixes.

## Risks And Remaining Work

- PXE-0068 remains open only for `production_remote` hardening: TLS/operator
  credential rollout, adversarial auth/media tests, and evidence.
- Remote QGC HTTP/WebSocket media still belongs to PXE-0070 and requires QGC
  Authorization/Origin/TLS support plus QGC build/test evidence before any
  remote PixEagle HTTP/WS compatibility claim.
- Full visual Gazebo/PX4 evidence remains PXE-0040 and is still blocked on a
  capable runtime environment or a separately proven official-image startup
  workaround.
- No service install/start, deployment, Docker/PX4/SITL/HIL, sidecar mutation,
  QGC branch mutation/build, runtime MCP endpoint, callable tool exposure, or
  real-aircraft control was performed or claimed.

## Next Slice

Continue Phase 4 cleanup from the resume map:

1. PXE-0064 production remote hardening and remaining legacy alias retirement.
2. PXE-0070 QGC authenticated remote HTTP/WebSocket media PR work.
3. PXE-0040 official Gazebo visual runtime evidence on a suitable host.
4. PXE-0008/PXE-0021 API/dashboard modernization and frontend toolchain cleanup.
