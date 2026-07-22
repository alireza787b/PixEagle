# Phase 5 Checkpoint: Browser Media Latency and WebRTC-First Playback

Date: 2026-07-22
Status: implementation complete locally; live VPS acceptance pending

## Scope

This slice addresses the operator-visible browser video problem. It does not
claim Raspberry Pi, real-camera, QGC, PX4/SIH/SITL/HIL, or production-network
acceptance.

## Findings

- The pre-change remote Auto policy deliberately selected WebSocket on the
  public HTTP/IP demo path, so the browser never attempted WebRTC there.
- The WebSocket client decoded every arriving JPEG. Under CPU SmartTracker
  load, that created a decode backlog and visible latency rather than showing
  the newest frame.
- The runtime can produce fewer unique frames than `STREAM_FPS` while AI is
  processing. The transport must not duplicate frames or claim that its output
  ceiling is a detector guarantee.
- The WebRTC track scheduled from a pre-sleep timestamp and did not reject a
  repeated publisher frame ID, allowing catch-up bursts and duplicate video.
- The adaptive-quality bandwidth comparison was inverted: high estimated
  bandwidth could select a more aggressive quality path in the wrong direction.

## Implemented

- Added authenticated `GET /api/v1/streams/client-config` as the typed,
  no-store browser media contract. It reports enabled transports, bounded FPS,
  and redacted browser ICE records from the runtime source of truth.
- Changed Auto to try WebRTC first when the runtime advertises it, then fall
  back to WebSocket or HTTP only after a bounded failure. Explicit WebRTC is
  still available for supported browsers and reports actionable errors.
- Added queued local ICE candidates and bounded disconnected-state cleanup.
- Reworked WebRTC pacing around monotonic deadlines, unique publisher frame
  IDs, and strictly increasing RTP timestamps.
- Reworked JPEG presentation to keep one decode active and at most one newest
  pending frame; stale queued frames are discarded and resources are revoked.
- Added monotonic WebSocket/MJPEG send pacing and raised the fresh-frame output
  ceiling default from 10 to 20 FPS (still bounded to 1..60 by schema/runtime).
- Corrected adaptive-quality bandwidth direction and regenerated the schema.
- Updated streaming architecture, configuration, WebRTC, WebSocket, optimizer,
  and overview documentation to distinguish source, processed, and presented
  frame rates and to describe lab versus production ICE requirements.

## Verification

Local verification completed:

- full dashboard: `55` suites and `363` tests passed;
- focused WebRTC/latest-JPEG dashboard: `23` tests passed without React lifecycle
  warnings;
- required API inventory/parameter reload: `73` tests passed;
- focused media/API/docs: `158` tests passed;
- repository backend run: `3522` passed and `48` skipped; its only failure was
  the expected generated API-tool inventory drift after adding the route;
- the route was regenerated as non-callable, non-MCP, and blocked pending a
  separate security review, then the final API/tool/reload/media closure set
  passed `213`;
- schema check, API-tool inventory check, Python compile, ESLint, production
  dashboard build, and `git diff --check` passed.

The backend run also emitted the already tracked PXE-0127 Starlette/httpx
deprecation warning. A live VPS browser probe must still verify Auto reports
WebRTC and that the decoded stream stays fresh before this checkpoint closes.

## Remaining gates

1. Run the final local regression and inspect the diff for stale protocol text.
2. Publish the exact commit and update the existing VPS runtime without
   overwriting local operator configuration.
3. Verify public lab Auto/WebRTC, explicit WebRTC, WebSocket fallback, and
   dashboard media metrics on the VPS.
4. Keep HTTPS/WSS with short-lived TURN, restrictive-network relay, QGC,
   Raspberry Pi, real camera/gimbal, and field evidence as later gates.

## Evidence boundary

The implementation improves transport latency and makes WebRTC available on
the tested public HTTP/IP lab path. It cannot increase unique detector output
when CPU AI inference itself is slower; that limitation remains visible in the
source/processed/presented metrics and is a separate tracker/model benchmark.
