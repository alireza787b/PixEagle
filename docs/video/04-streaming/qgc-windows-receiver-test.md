# QGC Network JPEG Receiver Test

This runbook validates the focused QGroundControl HTTP MJPEG and WebSocket JPEG
receiver proposals on Linux, Windows, or Android. It does not validate PX4,
flight control, authenticated remote media, or production deployment.

## Record Before Testing

- QGC platform and exact commit or build-workflow URL
- QGC artifact filename and SHA-256
- source type and sanitized URL authority
- PixEagle commit/profile when PixEagle is the source
- start/stop time, visible result, reconnect result, and sanitized logs

Do not include credentials, full secret-bearing URLs, or private token files in
screenshots or logs.

## Generic Camera-Free Source

PixEagle includes a standalone animated test source:

```bash
python3 tools/qgc_media_test_source.py --host 127.0.0.1 --port 8095
```

Use:

```text
HTTP MJPEG:      http://127.0.0.1:8095/mjpeg
WebSocket JPEG:  ws://127.0.0.1:8095/ws
Browser WS test: http://127.0.0.1:8095/ws-viewer
Health:          http://127.0.0.1:8095/health
```

A browser or VLC can open `/mjpeg`. VLC is not a raw WebSocket JPEG client and
is not expected to open `ws://.../ws`.

When QGC and the source are on different hosts, bind the source to the intended
lab interface, use that reachable device address, and temporarily allow TCP
`8095` through both host and provider firewalls. Remove the rule after testing.

## PixEagle Source

For QGC on the same computer as PixEagle:

```text
HTTP MJPEG:      http://127.0.0.1:5077/video_feed
WebSocket JPEG:  ws://127.0.0.1:5077/ws/video_feed
```

For a separate QGC device on an isolated lab network, first apply the explicit
media-only exception:

```bash
make unsafe-demo-lan-media-profile LAN_HOST=<pixeagle-device-ip-or-hostname>
```

Then use the device address instead of `127.0.0.1`. This permits anonymous
access only to the two video routes. Dashboard, control, telemetry,
configuration, WebRTC signaling, and media-health routes remain protected.

QGC #14730/#14731 do not support PixEagle's `qgc_direct_media` Bearer/Origin
contract. Do not configure Basic/Bearer credentials, Origin, custom CAs, or URL
userinfo for this focused receiver test.

## Acceptance Matrix

Run both source modes on every target platform:

1. Select **HTTP MJPEG Video Stream**, enter the HTTP URL, and confirm moving
   video rather than a placeholder or green frame.
2. Switch to **WebSocket JPEG Video Stream**, enter the WS URL, and confirm
   moving video.
3. Switch away and back three times. QGC must recover without restart.
4. Stop and restart the source. QGC must show loss and reconnect through its
   bounded retry lifecycle.
5. Leave each mode running for at least ten minutes and check for growing
   latency, unbounded memory, or a frozen final frame.
6. On Windows, repeat once with **Force CPU video path** disabled and enabled.
   Both should render; a green software-decoded frame is a failure.
7. Confirm QGC diagnostics contain only sanitized scheme/host/port context.

Recording is outside #14730/#14731 and is not an acceptance claim for these
transport PRs.

## Evidence Boundary

A pass proves only that the tested QGC build received and rendered the tested
network-JPEG source. It does not prove merge readiness by itself, production
TLS/authentication, Raspberry Pi performance, GStreamer UDP reception, PX4,
SITL/HIL, field operation, or aircraft safety.
