# Video System Documentation

> Comprehensive guide to PixEagle's video input, processing, and streaming subsystem

## Overview

PixEagle's video subsystem handles the complete video pipeline from capture to streaming output. It supports multiple input sources, GStreamer hardware acceleration, and various streaming protocols for real-time drone operations.

## Quick Navigation

| Section | Description |
|---------|-------------|
| [Architecture](01-architecture/README.md) | System design, VideoHandler class, frame states |
| [Input Sources](02-input-sources/README.md) | All 7 video source types and configuration |
| [GStreamer](03-gstreamer/README.md) | Pipeline construction, elements, optimization |
| [Streaming](04-streaming/README.md) | HTTP, WebSocket, WebRTC, UDP output |
| [Remote Media Security](04-streaming/remote-media-security.md) | Companion-to-GCS/QGC/browser deployment profiles |
| [QGC HTTP/WebSocket Source Plan](04-streaming/qgc-http-websocket-source-plan.md) | Generic QGC HTTP/WS source support and PixEagle profile boundaries |
| [QGC Windows Receiver Test](04-streaming/qgc-windows-receiver-test.md) | Windows draft-build receiver validation and evidence checklist |
| [OSD](05-osd/README.md) | On-screen display and overlay system |
| [Configuration](06-configuration/README.md) | YAML parameter reference |

## Supported Video Sources

| Source Type | GStreamer | Best For | Typical Latency |
|-------------|-----------|----------|-----------------|
| `VIDEO_FILE` | Optional | Testing, demos | N/A |
| `USB_CAMERA` | Recommended | USB webcams | 33-66ms |
| `RTSP_STREAM` | Required | IP cameras, drones | 100-500ms |
| `UDP_STREAM` | Required | Low-latency feeds | 50-100ms |
| `HTTP_STREAM` | Optional | HTTP video sources | 200-500ms |
| `CSI_CAMERA` | Required | Raspberry Pi, Jetson | 33-50ms |
| `CUSTOM_GSTREAMER` | Required | Advanced pipelines | Varies |

## Streaming Output Methods

| Method | Protocol | Use Case | Clients |
|--------|----------|----------|---------|
| HTTP MJPEG | HTTP | Dashboard, browsers | Up to 20 |
| WebSocket | WS | Real-time dashboard | Up to 10 |
| WebRTC | RTC | Low-latency P2P | Multiple |
| GStreamer UDP | RTP/UDP | QGroundControl | 1 |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         VIDEO SUBSYSTEM                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │ Video Source │───▶│ VideoHandler │───▶│ Frame Processing     │  │
│  │              │    │              │    │ (OSD, Resize)        │  │
│  │ - File       │    │ - Capture    │    └──────────┬───────────┘  │
│  │ - USB        │    │ - Buffer     │               │              │
│  │ - RTSP       │    │ - Recovery   │               ▼              │
│  │ - UDP        │    └──────────────┘    ┌──────────────────────┐  │
│  │ - CSI        │                        │ Streaming Output     │  │
│  │ - Custom     │                        │ - HTTP MJPEG         │  │
│  └──────────────┘                        │ - WebSocket          │  │
│                                          │ - WebRTC             │  │
│                                          │ - GStreamer UDP      │  │
│                                          └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

## Frame State Diagram

```
┌─────────────────┐
│   get_frame()   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ current_raw_    │────▶│ current_osd_    │
│ frame           │     │ frame           │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│ current_resized_│     │ current_resized_│
│ raw_frame       │     │ osd_frame       │
└─────────────────┘     └─────────────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
              ┌──────────────┐
              │   Streaming  │
              │   Outputs    │
              └──────────────┘
```

## Key Source Files

| File | Purpose | Lines |
|------|---------|-------|
| `src/classes/video_handler.py` | Video input, 7 sources, frame management | ~1000 |
| `src/classes/gstreamer_handler.py` | UDP H.264 output to QGC | ~120 |
| `src/classes/fastapi_handler.py` | HTTP/WebSocket streaming | ~600 |
| `src/classes/webrtc_manager.py` | WebRTC signaling | ~240 |
| `src/classes/osd_renderer.py` | On-screen display | ~400 |

## Quick Start

### Basic Video File Playback

```yaml
# config.yaml
VideoSource:
  VIDEO_SOURCE_TYPE: VIDEO_FILE
  VIDEO_FILE_PATH: resources/test.mp4
  USE_GSTREAMER: false
```

### RTSP Stream with GStreamer

```yaml
# config.yaml
VideoSource:
  VIDEO_SOURCE_TYPE: RTSP_STREAM
  RTSP_URL: rtsp://192.168.0.108:554/stream=0
  RTSP_PROTOCOL: tcp
  RTSP_LATENCY: 200
  USE_GSTREAMER: true
```

### USB Camera (Raspberry Pi)

```yaml
# config.yaml
VideoSource:
  VIDEO_SOURCE_TYPE: USB_CAMERA
  CAMERA_INDEX: 0
  USE_GSTREAMER: true

USBCamera:
  PIXEL_FORMAT: MJPG  # Lowest CPU on RPi
```

## Coordinate Mapping

PixEagle ensures accurate coordinate mapping between dashboard clicks and video frames:

1. All GStreamer pipelines include `videoscale` to enforce target dimensions
2. Video dimensions are validated against `CAPTURE_WIDTH`/`CAPTURE_HEIGHT`
3. RTSP pipelines use smart scaling with ultra-low latency optimizations
4. Dashboard clicks at (x, y) correctly map to frame coordinates

## Error Recovery

The video subsystem includes robust error recovery:

- **Consecutive Failure Tracking**: Counts failed frame reads
- **Automatic Reconnection**: Attempts recovery after threshold
- **Frame Caching**: Returns cached frames during recovery for display/streaming,
  while marking them unusable for vision-based command generation
- **Graceful Degradation**: Falls back to simpler pipelines

See [Error Recovery](01-architecture/error-recovery.md) for details.

## Related Documentation

- [Tracker Documentation](../trackers/README.md) - Visual tracking system
- [Follower Documentation](../followers/README.md) - Target following system
- [Configuration Schema](../../configs/config_schema.yaml) - Full parameter reference
