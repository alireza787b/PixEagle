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
│               ├──▶ WebRTC ───────▶ /webrtc/offer                 │
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

## Quick Start

### Enable Streaming

```yaml
FastAPI:
  ENABLE_HTTP_STREAM: true
  ENABLE_WEBSOCKET: true
  ENABLE_WEBRTC: true
  STREAM_QUALITY: 80
  STREAM_WIDTH: 640
  STREAM_HEIGHT: 480
```

### Access Streams

```
# Dashboard
http://localhost:8000/

# MJPEG stream (embed in browser)
http://localhost:8000/video_feed

# WebSocket (JavaScript)
ws://localhost:8000/ws/video_feed

# WebRTC (requires signaling)
POST http://localhost:8000/webrtc/offer
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

## Frame Sources

All streaming methods can use different frame sources:

| Endpoint | Frame Source | Description |
|----------|--------------|-------------|
| `/video_feed` | Raw frame | Original camera frame |
| `/video_feed?osd=true` | OSD frame | Frame with overlay |
| `/video_feed?resize=true` | Resized frame | Scaled for bandwidth |

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
