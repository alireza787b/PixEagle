# Phase 5 Checkpoint: Browser Media Latency and WebRTC-First Playback

Date: 2026-07-22
Status: lab-media slice complete; target and production-network gates remain

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
deprecation warning.

Authorized public-IP VPS verification completed on exact code commit
`bd8898d2bb2dc1e97cebea5dcc46d08ac99a9b10`:

- the stopped-runtime updater preserved the existing browser users, credential
  handoff, dashboard environment, and operator config, then reconciled the Full
  AI installation to beta.22;
- the operator-owned old default `Streaming.STREAM_FPS: 10` was adopted through
  the guarded Config Sync transaction and became `20` after one controlled
  runtime restart;
- the authenticated no-store client-config route reported Auto, WebRTC
  available, one deployment-selected STUN record, and the 20 FPS ceiling;
- public-IP headless Chrome selected `Video: WEBRTC`, decoded 283 frames over
  15 seconds at 640x480 (18.87 observed FPS), advanced media time by 15 seconds,
  and recorded zero dropped frames, zero packet loss, 5 ms jitter, 26 ms RTT,
  and no browser errors;
- an operator-path transport switch reached a frame-ready 640x480 WebSocket
  canvas and returned to Auto/WebRTC without browser errors; and
- the current backend, dashboard, main-app, MAVLink2REST, and MAVSDK Server log
  scan found no error records.

The sanitized manifest and visual evidence are stored under
`evidence/2026-07-22-pxe0134-beta22-vps-media/`.

## Deferred gates

1. Test beta.22 on Raspberry Pi with a real camera and representative tracker
   load; measure source, processed, encoded, and browser-presented cadence.
2. Validate HTTPS/WSS plus short-lived TURN credentials and restrictive-network
   relay behavior before any production-network claim.
3. Keep QGC, camera/gimbal, PX4/SIH/SITL/HIL, X-Plane, field, and real-aircraft
   evidence in their owning acceptance slices.

## Evidence boundary

The implementation improves transport latency and makes WebRTC available on
the tested authenticated public HTTP/IP lab path. It cannot increase unique
detector output when CPU AI inference itself is slower; that limitation remains
visible in the source/processed/presented metrics and is a separate
tracker/model benchmark. This checkpoint is not production-network or target
hardware acceptance.
