# Video quality and QGC recovery checkpoint — 2026-10-08

## Position

The measured JPEG delivery, source/display fidelity, and QGC recovery slices
are implemented locally. The Pi was not changed. Native WebRTC remains behind
its qualification gate.

## Changes

- PixEagle default profile: VIDEO_FILE, CSRT, 640×480 analysis, native source
  pixels, 1280×720 delivery ceiling, 20 FPS ceiling, JPEG quality 70, Automatic
  startup at 12 FPS and 0.75 scale, aggregate JPEG budget 8,000 kbps.
- Dashboard/QGC delivery uses measured write, ACK, encoder and optional render
  feedback. Encoding work is shared, resizing is off the event loop, queues are
  bounded, and stale/oversized feedback is reported explicitly.
- Frame provenance and selection geometry remain tied to the delivered frame
  and source epoch.
- QGC external PixEagle video is independent of the stock video toggle. Its
  media identity excludes aircraft telemetry connection generations. A
  presentation watchdog and bounded retry path recover failed starts.
- PixEagle floating panels and dialogs support independent 100–200% scaling and
  touch-sized controls.
- Engine selection uses the same typed tracker-switch persistence service from
  QGC and the Dashboard. QGC preserves an explicit `persist:true` request;
  source-generation drift now rejects the save with an actionable restart
  result instead of a generic startup mismatch.

## Validation

- PixEagle Phase0/config/API checks: 126 passed.
- PixEagle focused streaming/API tests: 307 passed, 2 optional GStreamer tests skipped.
- PixEagle full unit gate: 3,658 passed, 2 skipped.
- PixEagle integration gate: 196 passed.
- Dashboard: 493 tests passed; previous lint and production build passed.
- QGC build: Debug custom binary built successfully.
- QGC focused PixEagle/video tests: 3 passed; VideoManagerInitTest passed.
- QGC full Unit|Integration run: 428/430 passed. Bluetooth host warning and
  GPS visibility timeout are separate host-sensitive tests; GPS passed in an
  isolated rerun. No PixEagle test failed.
- Offline detail comparison and GStreamer sender/receiver association probes
  passed. These are camera-free measurements and do not qualify Pi throughput.

## Evidence and release state

- Offline evidence: `~/.cache/pixeagle-video-quality/2026-10-08/`.
- Linux live native presentation previously passed at 640×480 with authenticated
  cookie/Origin and fresh frame identity. The current Pi is unreachable, so no
  new physical evidence was collected.
- QGC commit: `c17a3902c` on the fork branch. Windows GitHub Actions run:
  `37825907261`, queued/in progress.
- PixEagle commits: `cf5391b` (video quality), `0e9c364` (source-safe engine
  persistence), and `5830a63` (explicit tracker selection/follower guidance)
  on `feature/video-quality-adaptive`; not deployed to the Pi and not published
  as a new release.

## Next gate

Download and install the Windows artifact from the completed run, sign in with
stock QGC video disabled, and verify video after startup, minimize/resume,
backend reconnect and camera reconnect. Then reconnect the cooled Pi for the
720p/20 FPS/Q80 comparison and service update. Trigger Linux/Android artifacts
after Windows acceptance. Do not run aircraft-control tests in this video gate.
