# Slice 4b.3 — responsive manual camera control

The physical bench exposed two software problems: control admission/Stop shared
the frame-processing loop, and expected interrupted pulses appeared as unknown
outcomes. The recorded Smart run fell back to CPU. Camera action audit timestamps
started after owner-loop scheduling, so their short durations did not establish
operator-to-device latency. No new hardware commands were sent for this change.

## Implemented

- CameraRuntime owns a renewable latest-intent executor on a dedicated thread
  and async loop, using the existing provider/socket. Begin prepares only;
  updates arm movement. Renew at 100 ms, expire after 350 ms, check at 20 ms.
- Scoped Stop retires even an unreceived begin; obsolete Stop cannot interrupt
  a newer gesture/finite operation. Emergency Stop clears pending ownership.
  Failed transmission prevents further control/following/lifecycle admission
  until an explicit successful retry.
- Preparation runs once per gesture. SIP angular magnitude uses advertised
  speed bounds, one axis at a time. Zoom is directional. Compatibility finite
  steps and Home also run off the vision loop with final freshness checks.
- Following/tracker/model transitions use shared lifecycle reservations.
  FramePublisher exposes immutable source identity without frame/model locks
  so camera watchdog execution cannot wait on frame transactions.
- Typed requests/status expose gestures, sequence, manual state and angle
  freshness. Zoom telemetry stays explicitly unavailable. HTTP ingress,
  admission, dispatch and termination timestamps support latency diagnosis.
- The authenticated synthetic camera fixture exposes the same protocol and
  synthetic telemetry. It creates no camera or aircraft connections.

Public contract, timing semantics and limitations are documented in
`docs/apis/native-camera-controls.md`. Normal local profiles and disabled
camera controls still create no manual executor or camera transport.

## Validation

Evidence directory:
`/home/alireza/.cache/pixeagle-qgc-baseline/slice-4b3-2026-10-01/response-fix/`

- Combined camera/provider/protocol, engine selection, native following/targets/
  models, Offboard safety, frame provenance, route inventory, tool candidates,
  and parameter reload: **632 passed, 14 subtests**, 25.21 s.
- Regenerated API candidate inventory; `--check` passes.
- Configuration schema: **606 parameters**, no drift.
- CI syntax/undefined-name flake8 selection: zero errors; touched imports parse.
- Final focused camera rerun: **115 passed**, 17.66 s, including the additional
  emergency-Stop lease-release regression; results are retained in
  `camera-final.log` and `camera-final.xml`.

Tests cover Stop-before-begin, release during preparation, newest intent under
blocked preparation, reversal, stale/out-of-order updates, a hold beyond the old
five-second limit, actor/lifecycle exclusions, failed Stop, source changes and
watchdog expiry while the owner thread or frame transaction is blocked. Worker
thread exceptions are promoted to test failures.

## Remaining checkpoint

QGC/dashboard builds and interaction tests are recorded by the integration
checkpoint. This software evidence does not qualify camera axis orientation,
physical stopping, UDP delivery, hardware watchdogs or camera tracker quality.
The operator must repeat the real-camera joystick/release and camera/local
tracking checks before camera-following qualification. The 90-degree physical
mount has not been established as an aircraft follower transform.

## Camera-v2 target-selection defect and camera-v3 repair

The operator found that Camera Classic and Camera Smart clicks returned a stale
target/connection conflict. An authenticated dry-run against the running camera
reproduced `frame_evicted` by 0.4 seconds, before the 1.5-second age limit. Every
30 fps publication retained full 1920×1080 analysis pixels and a 1280×720
display frame, exhausting the 128 MiB selection cache. Camera-owned selection
needs the displayed pixels and verified analysis dimensions, not a copied local
analysis frame. The publisher now retains only the streamed variant for camera
selection and keeps local-tracking pixel retention unchanged. Local actions
reject a geometry-only snapshot defensively. A paced full-resolution test held
the first frame at 0.4, 0.8, 1.2 and 1.45 seconds and dropped it by 1.6 seconds.
The follow-up backend video/target regression passed 256 tests. This is software
evidence; camera-v3 physical Classic/Smart selection still needs operator testing.
Frames older than the advertised limit fail closed on slow links.

## Camera-v3 real-stream correction and camera-v4 handoff

The camera-v3 live RTSP dry-run showed why the paced geometry-only test was
insufficient: with continuous WebSocket delivery, a frame captured 1.2 seconds
earlier could still be evicted. The sender now pins only selectable frames sampled
for a client before JPEG encoding. Pins are bounded to three frames per client,
96 MiB globally, and the existing 1.5-second capture deadline. Disconnect and
source replacement clear pins. The QGC receiver already negotiates latest-frame
acknowledgment, so the backend waits for its acknowledgment before sending the
next image. The camera-v4 live dry-run using that same acknowledgment contract
returned HTTP 200 without execution at 0, 0.4, 0.8 and 1.2 seconds; 1.6 seconds
returned `frame_evicted` without execution. No target or movement command was
sent. The final focused streaming/target/camera gate passed 341 tests. Physical
Camera Classic/Smart acquisition remains for the operator.
