# 4b.4d shutdown retry and camera-free link qualification — 2026-10-04 continuation

This checkpoint records the camera-free continuation after the v21 recorded-SIH
review. The physical camera was unavailable, so no camera motor, RTSP device,
radio, Pi, or aircraft qualification is claimed.

## Teardown repair

The follow teardown is now one identity-bound episode. It captures the follow
session, aircraft UID, connection generation, execution mode, and original
reason before normal execution state is cleared. Calls that join an in-flight
teardown receive its result; they cannot trigger another attempt. A later
explicit native Stop may retry only the retained failed episode. The retry
rechecks the captured aircraft identity and connection generation before any
Offboard stop. Preview cleanup never becomes an aircraft cleanup, and a failed
cleanup keeps target admission and new starts blocked.

The native following status reuses its existing Stop identifiers and stop_allowed
field for a retryable failed episode. QGC uses those identifiers for its existing
Stop action and keeps no local retry state. No new route or saved setting was
introduced.

## Evidence

- Backend safety/concurrency suite: **211 passed**.
- Backend native-following API suite: **29 passed** (240 focused tests across the two suites).
- Authenticated camera-link qualification:
  ~/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-03/link-v6-final/manifest.json.
  It passed source stability, 20 Hz independent publication, two-client
  arbitration, reorder/late-packet rejection, blocked capture/inference Stop,
  and 350 ms lease expiry (observed 355–363 ms; software gate 400 ms).
- QGC custom build: build/pixeagle-custom-debug/Debug/PixEagle-QGroundControl.
- QGC focused CTest: PixEagle Config/Client/Manager and
  OnScreenCameraTrackingController, **4/4 passed** (58.48 seconds).
- Dashboard `VideoStream.test.js`: **25/25 passed**, covering browser-session
  authorization, rendered-frame acknowledgements, clean reconnects and WebRTC
  fallback behavior.
- The renewed qualification harness ran **68 tests passed** (including the
  existing authenticated control/heartbeat cases, production HTTP/JPEG relay
  coverage, and the new relay cases).
  Evidence: `~/.cache/pixeagle-qgc-baseline/slice-4b4d-2026-10-04/link-v3-sustained/manifest.json`.
- The new `SharedLinkRelay` is a loopback-only, user-space TCP fixture. It
  applies one aggregate uplink/downlink byte budget across concurrent streams,
  deterministic latency, and an explicit reset. Its two tests passed and
  measured shared contention, latency, and teardown. The source and test are
  `tools/shared_link_relay.py` and `tests/unit/streaming/test_shared_link_relay.py`.

The existing link fixture uses authenticated loopback HTTP and deterministic
sender delay/drop/jitter. The new relay tests include one short sustained
production fixture run: 60 authenticated gimbal-control renewals and 60 JPEG
WebSocket frames shared the 128 KiB/s aggregate budget. A separate relay test confirmed
  fresh-connection recovery after a reset. QGC’s native video controller now
  treats `ApplicationHidden` like suspension. The fixture is not QGC desktop or
  Dashboard UI evidence. Neither fixture is a radio or kernel-shaped network test.
They do not establish process-death behavior, camera-device stopping, CPU
starvation, or physical motor response.

## Remaining 4b.4d work

The short sustained relay run is complete. Remaining software evidence is the
actual radio/Pi/process-loss path and QGC/Dashboard application suspension
under the deployed runtime. The fixture must retain separate receipt,
dispatch, publication, and physical-response timestamps. The 100 ms
Stop-dispatch and 400 ms lease-expiry limits remain unchanged.

Camera reconnection, camera-process failure, actual RTSP transport, Pi/router
load, physical mount behavior, and real aircraft remain later checkpoints.
