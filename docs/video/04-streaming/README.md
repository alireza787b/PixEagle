# Video Streaming

> Output methods for video distribution

## Overview

PixEagle provides multiple video streaming methods for different use cases:

| Method | Protocol | Use Case | Latency |
|--------|----------|----------|---------|
| HTTP MJPEG | HTTP | Web dashboard, simple clients | Medium |
| WebSocket | WS | Real-time web apps | Low |
| WebRTC | WebRTC | Peer-to-peer, bidirectional | Very Low |
| GStreamer UDP | UDP/RTP | QGroundControl, GCS | Very Low |

The dashboard's `auto` mode is WebRTC-first. It asks the running backend for
the enabled transports and ICE configuration, then falls back to WebSocket
JPEG only when WebRTC is unavailable or fails before decoded media arrives.
WebSocket uses a latest-frame renderer so a slow decoder does not build a
stale queue. HTTP MJPEG remains the simple compatibility path.

GStreamer UDP is the maintained PixEagle path for QGroundControl and other GCS
video in field-style deployments. Browser WebRTC can work over a public HTTP
or IP demo when the browser and ICE path permit it, but HTTP signaling is still
lab-only. Use HTTPS/WSS and reviewed short-lived TURN credentials for a
production remote deployment.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     Streaming Architecture                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  VideoHandler                                                     │
│       │                                                           │
│       ▼                                                           │
│  ┌─────────┐                                                      │
│  │  Frame  │──┬──▶ HTTP MJPEG ───▶ /video_feed                   │
│  │  BGR    │  │                                                   │
│  └─────────┘  ├──▶ WebSocket ────▶ /ws/video_feed                │
│               │                                                   │
│               ├──▶ WebRTC ───────▶ /ws/webrtc_signaling          │
│               │                                                   │
│               └──▶ GStreamer ────▶ UDP:5600 (QGC)                │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

## Documentation

- [HTTP MJPEG](http-mjpeg.md) - Motion JPEG streaming endpoint
- [WebSocket](websocket.md) - Real-time WebSocket streaming
- [WebRTC](webrtc.md) - Peer-to-peer video with aiortc
- [Streaming Optimizer](streaming-optimizer.md) - Adaptive quality control
- [Remote Media Security](remote-media-security.md) - Pi-to-GCS/QGC/browser deployment profiles
- [QGC HTTP/WebSocket Source Plan](qgc-http-websocket-source-plan.md) - Generic QGC source support and PixEagle profile boundaries
- [QGC Windows Receiver Test](qgc-windows-receiver-test.md) - Draft-build HTTP MJPEG/WebSocket JPEG test lanes and evidence checklist

## Quick Start

### Enable Streaming

```yaml
Streaming:
  ENABLE_STREAMING: true
  API_EXPOSURE_MODE: local_only
  HTTP_STREAM_HOST: 127.0.0.1
  HTTP_STREAM_PORT: 5077
  STREAM_QUALITY: 80
  STREAM_WIDTH: 640
  STREAM_HEIGHT: 480
  STREAM_FPS: 20
  DEFAULT_PROTOCOL: auto
```

### Access Streams

```
# Dashboard
http://127.0.0.1:5077/

# MJPEG stream (embed in browser)
http://127.0.0.1:5077/video_feed

# WebSocket (JavaScript)
ws://127.0.0.1:5077/ws/video_feed

# WebRTC signaling WebSocket
ws://127.0.0.1:5077/ws/webrtc_signaling

# Typed local media health
http://127.0.0.1:5077/api/v1/streams/media-health

# Typed browser transport/ICE configuration (used by the dashboard)
http://127.0.0.1:5077/api/v1/streams/client-config
```

`GET /api/v1/streams/client-config` is the browser media source of truth. It
is authenticated with `media:read`, is marked `Cache-Control: no-store`, and
contains only the currently enabled transports, target FPS, and ICE records.
TURN credentials are delivered only to an authorized browser client through
this route; they are not included in media health or ordinary logs.

`GET /api/v1/streams/media-health` is the typed observability route for local
media transports. It requires `media:read` and reports PixEagle process-local
MJPEG, WebSocket, WebRTC signaling, GStreamer output, frame-publisher, config,
and security posture. Disabled `ENABLE_STREAMING`, zero connection limits, and
stale published frames are explicit in this payload. GStreamer UDP reports
pipeline activity, not a connected-client count. It does not prove that a remote
browser, QGC, WebRTC peer, GCS, PX4, SITL, HIL, or field video path received
usable media.

The dashboard streaming status widgets and `pixeagle-service status` consume
this typed route. Service status uses same-host loopback by default and needs an
explicit `media:read` bearer token file only when the backend is running in
`machine_bearer` or `browser_session` mode.

## Comparison

### HTTP MJPEG

**Pros:**
- Simple to use (just an `<img>` tag)
- Works everywhere
- No client-side code needed

**Cons:**
- Higher bandwidth (no inter-frame compression)
- No audio support
- One-way only

**Best for:** Dashboards, monitoring, simple embedding

### WebSocket

**Pros:**
- Low latency
- Bidirectional communication
- Binary frame support

**Cons:**
- Requires JavaScript client
- Connection management needed

**Best for:** Interactive web applications, real-time control

### WebRTC

**Pros:**
- Lowest latency
- P2P (less server load)
- Audio support
- NAT traversal

**Cons:**
- Complex setup
- Signaling required
- Browser-specific quirks

**Best for:** Remote piloting, real-time control interfaces

### GStreamer UDP

**Pros:**
- Lowest latency
- H.264 compression
- QGC compatible

**Cons:**
- Requires both GStreamer plugins and an OpenCV build with `GStreamer: YES`
- UDP (no guaranteed delivery)
- One-way only

**Best for:** Ground control stations, FPV, telemetry integration

### QGroundControl Direct HTTP/WS

QGroundControl HTTP/HTTPS MJPEG and WebSocket support should stay generic:
ordinary IP cameras, lab MJPEG servers, and non-PixEagle WebSocket sources may
remain URL-only when that source does not require authentication. PixEagle is a
separate profile on top of that generic capability.

Use direct PixEagle HTTP MJPEG or WebSocket with a reviewed authenticated
remote-media profile, or for same-host loopback testing. The URL shapes are:

```text
http://127.0.0.1:5077/video_feed
ws://127.0.0.1:5077/ws/video_feed
```

For an onboard companion streaming to a ground-station laptop, prefer
`GStreamer.ENABLE_GSTREAMER_STREAM` and configure QGC for UDP H.264 instead of
opening the PixEagle backend API/media port on the LAN.

This stock-QGC path remains supported after PR #13594. The PR's HTTP MJPEG and
WebSocket JPEG sources are additional generic options, primarily for sources
that already expose those protocols or for explicit PixEagle direct-media
profiles.

For guarded direct HTTPS/WSS media with a draft/test QGC build containing PR
#13594:

```bash
make qgc-direct-media-profile PUBLIC_HOST=pixeagle.example
```

This generates a `media:read`-only bearer credential and keeps PixEagle
loopback behind an external proxy. It does not prove QGC playback. See
[Remote Media Security](remote-media-security.md) and the
[QGC HTTP/WebSocket Source Plan](qgc-http-websocket-source-plan.md).

## Frame Sources

HTTP MJPEG and WebSocket output uses the configured PixEagle streaming frame
source, quality, dimensions, and OSD policy. The active `/video_feed` endpoint
does not expose per-request `quality`, `resize`, or `osd` query parameters.
Query-string credentials are rejected.

### Frame-rate expectations

`Streaming.STREAM_FPS` is an output ceiling, not a promise that the detector
or camera can produce that rate. The dashboard reports **rendered FPS**. The
effective rate is bounded by the slowest stage: source capture, processing and
OSD, encoder, transport, and browser decode. Smart/AI tracking can therefore
show a lower source/rendered rate while remaining current; it must not replay a
backlog of old frames. WebSocket drops queued JPEG work in favor of the newest
frame, and WebRTC's track does the same at the shared `FramePublisher` boundary.

| Setting | Description |
| --- | --- |
| `Streaming.STREAM_PROCESSED_OSD` | Selects processed OSD frames when enabled |
| `Streaming.STREAM_WIDTH` / `Streaming.STREAM_HEIGHT` | Output dimensions |
| `Streaming.STREAM_QUALITY` | JPEG quality for MJPEG/WebSocket output |
| `Streaming.ENABLE_ADAPTIVE_QUALITY` | Allows the server-side adaptive quality engine to adjust output |

## Performance Considerations

### Bandwidth

| Resolution | MJPEG Q80 | WebSocket Q80 | WebRTC H.264 |
|------------|-----------|---------------|--------------|
| 640x480 | ~2 Mbps | ~2 Mbps | ~1 Mbps |
| 1280x720 | ~5 Mbps | ~5 Mbps | ~2 Mbps |
| 1920x1080 | ~10 Mbps | ~10 Mbps | ~4 Mbps |

### CPU Usage

| Method | Encoding | CPU Impact |
|--------|----------|------------|
| MJPEG | JPEG per frame | Low |
| WebSocket | JPEG per frame | Low |
| WebRTC | H.264 | Medium-High |
| GStreamer | H.264 | Medium (HW accel available) |

### Scaling Multiple Clients

```python
# StreamingOptimizer caches encoded frames
# Multiple clients share the same encoding
optimizer = StreamingOptimizer(
    frame_cache_size=3,
    quality_levels=[90, 70, 50]  # Adaptive quality
)
```
