# 2026-07-04 Phase 4 WebRTC Auto Public HTTP Policy

## Phase / Slice

- Phase 4 media transport/browser demo hardening
- Issue: PXE-0075
- Scope: diagnose and fix the user-observed WebRTC fallback on the temporary
  public HTTP/IP demo path.

## Finding

The public demo URL uses plain HTTP on an IP address. The dashboard Auto stream
mode previously selected WebRTC only because `window.RTCPeerConnection` existed,
then fell back after a fixed 5 seconds if no track arrived. That created a poor
operator experience: WebRTC signaling could start, but the actual media path
still depends on ICE connectivity and usually UDP/TURN/TLS/firewall evidence.

Forced WebRTC did connect in host-local Playwright validation, but that is not
proof that a remote public browser has a usable WebRTC media path.

## Changes

- Dashboard Auto mode now resolves non-local HTTP origins to WebSocket JPEG and
  shows `Auto: WebSocket for HTTP demo`.
- Auto still uses WebRTC on localhost HTTP and HTTPS contexts.
- If Auto is using WebRTC, fallback now waits 15 seconds after signaling opens
  and falls back only if no video track arrives or signaling/ICE fails.
- Auto no longer briefly opens `/ws/video_feed` before selecting WebRTC.
- Manual WebRTC selection remains available for reviewed networks.
- Docs now state that `RTCPeerConnection` support is not enough; WebRTC media
  needs a reviewed ICE path, and public HTTP demos should not broaden random UDP
  ranges as a shortcut.

## Evidence

Focused tests:

```bash
CI=true npm test -- --watchAll=false src/components/VideoStream.test.js
PYTHONPATH=src .venv/bin/pytest tests/test_docs_infrastructure_consistency.py -q
git diff --check
```

Results:

- VideoStream tests passed: 9 tests.
- Docs infrastructure consistency passed: 23 tests.
- Whitespace diff check passed.

Live public demo after dashboard rebuild/restart:

- Auto mode opened only `ws://204.168.181.45:5077/ws/video_feed`.
- Auto mode did not open `/ws/webrtc_signaling`.
- Dashboard displayed `Auto: WebSocket for HTTP demo`.
- The video canvas was visible at 640x480.
- Manual WebRTC selection opened `/ws/webrtc_signaling`, received a video track,
  reached ICE `connected`, and rendered 640x480 in host-local Playwright.

## Claim Boundary

This is browser/dashboard transport evidence only. It does not prove remote
public WebRTC media from the user's browser, QGC receiver behavior, PX4/SITL,
HIL, field behavior, or real-aircraft behavior.

## Follow-Up

- Future production WebRTC needs TLS/WSS plus TURN/firewall and media-state
  evidence.
- Media-health should eventually distinguish WebRTC signaling from connected
  media/ICE state instead of relying on peer count alone.

