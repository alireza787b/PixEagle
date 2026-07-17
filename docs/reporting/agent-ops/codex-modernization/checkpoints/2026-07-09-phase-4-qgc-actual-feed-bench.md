# Phase 4 Checkpoint: QGC Actual PixEagle Feed Bench

Date: 2026-07-09

## Slice

PXE-0070 support slice: expose the current public VPS PixEagle dashboard video
feed to the QGC PR #13594 receiver test without opening anonymous backend
media.

## Files Changed

- `.gitignore`
- `docs/video/04-streaming/qgc-windows-receiver-test.md`
- `docs/reporting/agent-ops/codex-modernization/journal/2026-07.md`
- `docs/reporting/agent-ops/codex-modernization/issue-register.md`
- `/home/alireza/PIXEAGLE_QGC_WINDOWS_RECEIVER_TEST_HANDOFF_2026-07-09.md`
- `/home/alireza/PIXEAGLE_QGC_ACTUAL_FEED_TEST_NOW_2026-07-09.md`

Local deployment files changed but not committed:

- `configs/config.yaml`
- `/home/alireza/.config/pixeagle/secrets/qgc-media-tokens.json`
- `/home/alireza/PIXEAGLE_QGC_ACTUAL_FEED_HANDOFF_2026-07-09.json`

## What Changed

- Kept the live public browser dashboard in `browser_session` mode.
- Added a scoped, generated `media:read` bearer-token file to the local config
  so QGC can authenticate directly to the actual PixEagle media endpoints.
- Preserved anonymous-deny behavior for backend media: unauthenticated
  `/video_feed` still returns `401 Unauthorized`.
- Documented the distinction between:
  - generic anonymous lab source on port `8095`; and
  - actual PixEagle media on port `5077` requiring Bearer auth.

## Current Actual-Feed Test Values

The plaintext token is only in the owner-only handoff file:

```text
/home/alireza/PIXEAGLE_QGC_ACTUAL_FEED_HANDOFF_2026-07-09.json
```

QGC PR #13594 settings:

```text
HTTP MJPEG: http://204.168.181.45:5077/video_feed
WebSocket JPEG: ws://204.168.181.45:5077/ws/video_feed
WebSocket Origin: http://204.168.181.45:3040
Authentication: Bearer token
```

## Validation

- PixEagle restarted and served backend/dashboard after the local config
  change.
- Anonymous HTTP media:
  `curl http://204.168.181.45:5077/video_feed` returned `401 Unauthorized`.
- Authorized HTTP media:
  a Python client with `Authorization: Bearer <token>` parsed actual PixEagle
  MJPEG frames from `http://204.168.181.45:5077/video_feed`.
- Authorized WebSocket media:
  a Python WebSocket client with the same bearer token plus Origin
  `http://204.168.181.45:3040` received a binary JPEG frame from
  `ws://204.168.181.45:5077/ws/video_feed`.

## Risks And Open Questions

- This VPS bench uses HTTP/WS over a public address, so the temporary bearer
  token is not confidential on the wire. It must be rotated/deleted after the
  short test window.
- Normal VLC URL entry cannot attach the QGC Bearer credential, so VLC remains
  useful for the anonymous lab source only, not this authenticated actual-feed
  lane.
- This proves backend media authorization and frame delivery from the current
  VPS, not QGC Windows GUI playback, recording, reconnect behavior, production
  TLS/WSS proxy behavior, PX4/SITL/HIL, field behavior, or real-aircraft
  readiness.

## Next Slice

- Tester should configure QGC PR #13594 with the actual-feed URL, Bearer token,
  and Origin above.
- After playback evidence is returned, continue PXE-0070 negative auth/Origin,
  reconnect, and recording tests.
- After the bench window, rotate/delete
  `/home/alireza/.config/pixeagle/secrets/qgc-media-tokens.json`, remove the
  local `API_BEARER_TOKEN_FILE` value or rotate it, and stop/close temporary
  public lab source `8095`.
