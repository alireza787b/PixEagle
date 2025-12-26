# Video Input Sources

> Complete guide to all 7 supported video source types

## Overview

PixEagle supports 7 video input sources, each optimized for specific use cases. The `VideoHandler` automatically selects the appropriate backend (OpenCV or GStreamer) based on configuration.

## Source Types

| Source | Config Value | GStreamer | Best For |
|--------|--------------|-----------|----------|
| [Video File](video-file.md) | `VIDEO_FILE` | Optional | Testing, demos |
| [USB Camera](usb-camera.md) | `USB_CAMERA` | Recommended | Webcams, USB cameras |
| [RTSP Stream](rtsp-stream.md) | `RTSP_STREAM` | Required | IP cameras, drones |
| [UDP Stream](udp-stream.md) | `UDP_STREAM` | Required | Low-latency feeds |
| [HTTP Stream](http-stream.md) | `HTTP_STREAM` | Optional | HTTP video sources |
| [CSI Camera](csi-camera.md) | `CSI_CAMERA` | Required | Raspberry Pi, Jetson |
| [Custom GStreamer](custom-gstreamer.md) | `CUSTOM_GSTREAMER` | Required | Advanced pipelines |

## Quick Selection Guide

```
┌─────────────────────────────────────────────────────────────────┐
│                  WHICH SOURCE TYPE DO I NEED?                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Testing/Development?                                            │
│  └──▶ VIDEO_FILE                                                │
│                                                                  │
│  USB Webcam?                                                     │
│  └──▶ USB_CAMERA                                                │
│                                                                  │
│  IP Camera / Drone RTSP?                                         │
│  └──▶ RTSP_STREAM                                               │
│                                                                  │
│  Low-latency RTP/UDP?                                            │
│  └──▶ UDP_STREAM                                                │
│                                                                  │
│  Raspberry Pi Camera?                                            │
│  └──▶ CSI_CAMERA (libcamera)                                    │
│                                                                  │
│  NVIDIA Jetson Camera?                                           │
│  └──▶ CSI_CAMERA (nvarguscamerasrc)                             │
│                                                                  │
│  HTTP/MJPEG Stream?                                              │
│  └──▶ HTTP_STREAM                                               │
│                                                                  │
│  Custom Pipeline Needed?                                         │
│  └──▶ CUSTOM_GSTREAMER                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Basic Configuration

```yaml
# config.yaml
VideoSource:
  VIDEO_SOURCE_TYPE: RTSP_STREAM  # Choose from above

  # Common settings
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
  CAPTURE_FPS: 30
  DEFAULT_FPS: 30
  USE_GSTREAMER: true  # Recommended for embedded

  # Source-specific settings follow...
```

## Feature Comparison

| Feature | File | USB | RTSP | UDP | HTTP | CSI | Custom |
|---------|------|-----|------|-----|------|-----|--------|
| GStreamer Required | No | No | Yes | Yes | No | Yes | Yes |
| Hardware Accel | No | V4L2 | No | No | No | GPU | Varies |
| Latency | N/A | Low | Medium | Low | High | Low | Varies |
| Recovery | N/A | Good | Excellent | Good | Basic | Good | Manual |
| Fallback Pipelines | No | No | Yes (4) | No | No | No | No |

## Factory Pattern

The `VideoHandler` uses a factory pattern for source creation:

```python
def _create_capture_object(self) -> cv2.VideoCapture:
    handlers = {
        "VIDEO_FILE": self._create_video_file_capture,
        "USB_CAMERA": self._create_usb_camera_capture,
        "RTSP_STREAM": self._create_rtsp_capture,
        "UDP_STREAM": self._create_udp_capture,
        "HTTP_STREAM": self._create_http_capture,
        "CSI_CAMERA": self._create_csi_capture,
        "CUSTOM_GSTREAMER": self._create_custom_gstreamer_capture
    }

    source_type = Parameters.VIDEO_SOURCE_TYPE
    use_gstreamer = Parameters.USE_GSTREAMER

    return handlers[source_type](use_gstreamer)
```

## GStreamer vs OpenCV

### When to Use GStreamer (`USE_GSTREAMER: true`)

- RTSP streams (required for reliability)
- CSI cameras (required for hardware access)
- UDP streams (required for RTP parsing)
- Low-latency requirements
- Embedded systems (RPi, Jetson)

### When to Use OpenCV (`USE_GSTREAMER: false`)

- Video files (simpler, cross-platform)
- USB cameras on desktop (simpler setup)
- Windows systems (GStreamer setup complex)
- Quick testing

## Common Patterns

### Testing with Video File

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: VIDEO_FILE
  VIDEO_FILE_PATH: resources/test_video.mp4
  USE_GSTREAMER: false
```

### Production RTSP

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: RTSP_STREAM
  RTSP_URL: rtsp://drone:554/stream
  RTSP_PROTOCOL: tcp
  RTSP_LATENCY: 200
  USE_GSTREAMER: true
```

### Raspberry Pi Camera

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CSI_CAMERA
  USE_GSTREAMER: true

CSICamera:
  CSI_SENSOR_ID: 0
  CSI_FLIP_METHOD: 0
```

## Troubleshooting

### Source Won't Open

1. Check source type spelling (case-sensitive)
2. Verify path/URL exists
3. Check GStreamer installation if required
4. Review logs for pipeline errors

### Wrong Resolution

1. Check `CAPTURE_WIDTH` and `CAPTURE_HEIGHT`
2. Verify source supports requested resolution
3. For RTSP, ensure pipeline includes `videoscale`

### High Latency

1. For RTSP: Reduce `RTSP_LATENCY`
2. Use TCP for stability, UDP for speed
3. Check network bandwidth
4. Use `get_frame_fast()` for buffer clearing
