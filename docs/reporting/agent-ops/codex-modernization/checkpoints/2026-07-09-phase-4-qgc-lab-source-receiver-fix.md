# Phase 4 Checkpoint: QGC Lab Source Receiver Fix

Date: 2026-07-09

## Slice

PXE-0070 support slice: QGC PR #13594 Windows receiver test-source defect
reported during public VPS bench testing.

## Files Changed

- `tools/qgc_media_test_source.py`
- `tests/test_qgc_media_test_source.py`
- `docs/video/04-streaming/qgc-windows-receiver-test.md`
- `/home/alireza/PIXEAGLE_QGC_WINDOWS_RECEIVER_TEST_HANDOFF_2026-07-09.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`

## What Changed

- Replaced the visually misleading static lab feed behavior with a
  dependency-free animated JPEG cycle for both HTTP MJPEG and WebSocket JPEG.
- Added HTTP/1.1 WebSocket handshakes and `HEAD` support for supported probe
  endpoints.
- Added `http://<source-host>:8095/ws-viewer` so testers can verify the
  WebSocket source in a browser without confusing raw `ws://` with a normal web
  page.
- Clarified that VLC should use `http://<source-host>:8095/mjpeg`, not the raw
  WebSocket URL.

## Validation

- `python3 -m py_compile tools/qgc_media_test_source.py`
- `PYTHONPATH=src .venv/bin/python -m pytest tests/test_qgc_media_test_source.py -q`
- `git diff --check`
- Local smoke:
  - `/health` returned source URLs;
  - `HEAD /mjpeg` returned `HTTP/1.1 200 OK`;
  - a raw WebSocket client received a complete binary JPEG frame.
- Public VPS smoke:
  - `http://204.168.181.45:8095/health` advertises `/mjpeg`, `/ws-viewer`, and `/ws`;
  - `curl -fsSI http://204.168.181.45:8095/mjpeg` returned `HTTP/1.1 200 OK`;
  - `http://204.168.181.45:8095/ws-viewer` served the browser viewer page;
  - a raw WebSocket client received a complete binary JPEG frame;
  - MJPEG parsing saw distinct consecutive JPEG frames.

## Evidence Paths

- Temporary public source: tmux session `pixeagle-qgc-media-source`
- Public source URLs:
  - `http://204.168.181.45:8095/mjpeg`
  - `http://204.168.181.45:8095/ws-viewer`
  - `ws://204.168.181.45:8095/ws`
- Offline tester handoff:
  `/home/alireza/PIXEAGLE_QGC_WINDOWS_RECEIVER_TEST_HANDOFF_2026-07-09.md`

## Risks And Open Questions

- The public VPS source is anonymous and lab-only. It must be stopped and TCP
  `8095` closed after the short receiver bench test.
- QGC Windows receiver playback, recording, reconnect, and negative-source
  behavior are still user/tester tasks. This checkpoint proves only that the
  PixEagle-provided lab source is a valid animated HTTP MJPEG/WebSocket JPEG
  test source.
- VLC is not a raw WebSocket JPEG client; VLC testing should use the MJPEG URL.

## Next Slice

- Ask the tester to retry QGC PR #13594 with the corrected URLs.
- Continue PXE-0070 only after Windows receiver playback/recording evidence is
  returned.
- Continue PXE-0074 final clean handoff/release readiness after the active
  public demo and QGC bench sessions are cleaned up or intentionally retained
  for the next test window.
