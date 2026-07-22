# Video System Documentation

> Comprehensive guide to PixEagle's video input, processing, and streaming subsystem

## Overview

PixEagle's video subsystem handles the pipeline from capture through vision/OSD
processing to independent output transports. GStreamer input selection and
GStreamer QGC output are separate capabilities; neither setting enables the
other.

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

| Source Type | `USE_GSTREAMER=false` | `USE_GSTREAMER=true` | Fallback |
|-------------|-------------------------|------------------------|----------|
| `VIDEO_FILE` | OpenCV | GStreamer preferred | OpenCV after open/frame-probe failure; explicit `LOOP`/`STOP` EOF state |
| `USB_CAMERA` | Native OpenCV backend | GStreamer preferred | OpenCV after pipeline-open failure |
| `RTSP_OPENCV` | OpenCV FFmpeg/default | OpenCV is forced | FFmpeg to default OpenCV |
| `RTSP_STREAM` | OpenCV FFmpeg/default | GStreamer preferred | Four GStreamer variants, then OpenCV |
| `UDP_STREAM` | OpenCV FFmpeg | Asynchronous GStreamer reader | No automatic cross-backend switch |
| `HTTP_STREAM` | OpenCV | GStreamer | No automatic cross-backend switch |
| `CSI_CAMERA` | Not applicable | GStreamer required | Degraded no-video startup |
| `CUSTOM_GSTREAMER` | Not applicable | GStreamer required | Degraded no-video startup |

The active OpenCV build must report `GStreamer: YES` for every OpenCV
`CAP_GSTREAMER` input or output path. System GStreamer packages by themselves
do not add that backend to a pip OpenCV wheel.

## Streaming Output Methods

| Method | Protocol | Primary use | Runtime dependency | QGC status |
|--------|----------|-------------|--------------------|------------|
| HTTP MJPEG | HTTP(S) | Dashboard, simple viewers | OpenCV JPEG encoding | Generic source in PR #13594 branch |
| WebSocket JPEG | WS(S) | Dashboard, native JPEG-frame clients | OpenCV JPEG encoding | Generic source in PR #13594 branch |
| WebRTC | ICE/DTLS/SRTP | Browser low-latency media | aiortc/PyAV plus a reachable ICE path | Not part of PR #13594 |
| GStreamer UDP | H.264/RTP/UDP | Companion-to-GCS field video | GStreamer-enabled OpenCV and encoder/payloader/sink plugins | Supported by stock QGC |

The HTTP/WebSocket QGC work adds receiver choices; it does not supersede or
deprecate H.264/RTP/UDP. UDP remains the maintained low-latency stock-QGC path.

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
| `src/classes/gstreamer_handler.py` | UDP H.264 output to QGC |
| `src/classes/fastapi_handler.py` | HTTP/WebSocket streaming orchestration |
| `src/classes/webrtc_manager.py` | WebRTC signaling and peer lifecycle |
| `src/classes/osd_renderer.py` | On-screen display |

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
