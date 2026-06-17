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

GStreamer UDP is the maintained PixEagle path for QGroundControl and other GCS
video in field-style deployments. Direct HTTP MJPEG or WebSocket media is
local-first: it works for same-host loopback clients and may be used for QGC
development/testing, but remote clients must satisfy the API exposure and
`media:read` authorization boundary.

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
```

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
- Requires GStreamer
- UDP (no guaranteed delivery)
- One-way only

**Best for:** Ground control stations, FPV, telemetry integration

### QGroundControl Direct HTTP/WS

Use direct HTTP MJPEG or WebSocket only when QGC and PixEagle run on the same
host, or when a reviewed authenticated remote-media profile is configured. The
supported local URLs are:

```text
http://127.0.0.1:5077/video_feed
ws://127.0.0.1:5077/ws/video_feed
```

For an onboard companion streaming to a ground-station laptop, enable
`GStreamer.ENABLE_GSTREAMER_STREAM` and configure QGC for UDP H.264 instead of
opening the PixEagle backend API/media port on the LAN. See
[Remote Media Security](remote-media-security.md).

## Frame Sources

HTTP MJPEG and WebSocket output uses the configured PixEagle streaming frame
source, quality, dimensions, and OSD policy. The active `/video_feed` endpoint
does not expose per-request `quality`, `resize`, or `osd` query parameters.
Query-string credentials are rejected.

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
