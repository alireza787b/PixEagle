# Phase 4 Checkpoint: Unsafe Anonymous Media Profile

Date: 2026-07-09 UTC

## Scope

Added an explicit unsafe lab mode for anonymous actual PixEagle media while
keeping dashboard/control/config/log/WebRTC/API routes authenticated.

## Changes

- Added `Streaming.ALLOW_UNAUTHENTICATED_MEDIA_STREAMING`, default `false`.
- Allowed anonymous access only for:
  - `GET /video_feed`
  - `WS /ws/video_feed`
- Added `unsafe_demo_lan_media_only` setup profile and
  `make unsafe-demo-lan-media-profile`.
- Kept query-string tokens rejected and WebSocket wrong-Origin requests denied.
- Updated config schema, setup docs, remote media policy, QGC runbook, README,
  and offline tester handoff files.
- Enabled the flag only in the ignored live VPS `configs/config.yaml` for the
  current bench, preserving `API_AUTH_MODE: browser_session`.

## Validation

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -m pytest -q \
  tests/unit/core_app/test_api_auth_runtime.py \
  tests/unit/core_app/test_api_exposure_policy.py \
  tests/test_setup_profiles.py \
  tests/test_docs_infrastructure_consistency.py
bash scripts/check_schema.sh
git diff --check
python3 -m py_compile \
  src/classes/api_auth_runtime.py \
  src/classes/api_legacy_media_routes.py \
  scripts/setup/apply-setup-profile.py
```

Result: 299 tests passed with one existing Starlette deprecation warning;
schema, whitespace, and syntax checks passed.

## Live VPS Evidence

PixEagle was restarted after the ignored local config change. `make run`
returned the known non-TTY attach exit after creating the tmux session, and
backend/dashboard ports were listening.

Public probes verified:

- `http://204.168.181.45:5077/video_feed` returned HTTP 200
  `multipart/x-mixed-replace` and valid JPEG bytes without Authorization.
- `ws://204.168.181.45:5077/ws/video_feed` returned frame metadata followed by
  a valid binary JPEG without Authorization.
- `Origin: http://evil.example` on the same WebSocket URL was rejected.
- `http://204.168.181.45:5077/api/v1/streams/media-health` returned 401
  without credentials.
- `http://204.168.181.45:5077/status` returned 401 without credentials.

## Risks And Boundaries

- This is not production remote media. Anyone who can reach the raw media URL
  can view the video while the flag is enabled.
- WebRTC signaling remains authenticated and is not part of the anonymous lane.
- VLC can test HTTP MJPEG only; VLC is not a raw WebSocket JPEG client.
- No QGC Windows GUI playback, QGC recording, TLS proxy, PX4/SITL/HIL, field,
  or real-aircraft success is claimed.

## Next

- Tester can retry VLC/QGC against the actual feed:
  - HTTP MJPEG: `http://204.168.181.45:5077/video_feed`
  - WebSocket JPEG: `ws://204.168.181.45:5077/ws/video_feed`
  - authentication: None
- Disable `ALLOW_UNAUTHENTICATED_MEDIA_STREAMING` and restart after the bench.
