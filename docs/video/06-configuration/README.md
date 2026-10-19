# Video Configuration

> Configuration reference for video subsystem

## Overview

PixEagle's video subsystem is configured through YAML configuration files. This section documents all video-related configuration options.

## Configuration Files

| File | Purpose |
|------|---------|
| `configs/config_default.yaml` | Default configuration |
| `configs/config.yaml` | Optional gitignored local override created by setup profiles or an explicit user save |
| `configs/config_schema.yaml` | Schema validation |

## Configuration Sections

### VideoSource

Factory video input starts with the included recording and does not require
GStreamer:

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: VIDEO_FILE
  VIDEO_FILE_PATH: resources/test4.mp4
  NATIVE_CAPTURE_RESOLUTION: true
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
  CAPTURE_FPS: 30
  USE_GSTREAMER: false
```

See [Video Source Config](video-source-config.md) for details.

### Streaming

Video output configuration:

```yaml
Streaming:
  ENABLE_STREAMING: true
  HTTP_STREAM_HOST: 127.0.0.1
  HTTP_STREAM_PORT: 5077
  STREAM_PROFILE: automatic
  STREAM_WIDTH: 1280
  STREAM_HEIGHT: 720
  STREAM_FPS: 20
  STREAM_STARTUP_FPS: 12
  STREAM_STARTUP_SCALE: 0.75
  STREAM_QUALITY: 70

GStreamer:
  ENABLE_GSTREAMER_STREAM: false
```

See [Streaming Config](streaming-config.md) for details.
Browser WebRTC and JPEG remain available without optional Python GStreamer.
The separate UDP GStreamer output is opt-in; it is not required for the
authenticated custom QGC integration. Keep the ordinary CSRT, constant-position
follower, altitude safeguards and circuit breaker defaults for a first run.

### Frame Preprocessor

Image enhancement is optional and disabled by default for a predictable,
low-CPU baseline. The shared pipeline always remains an 8-bit, three-channel
BGR image. Enable blur or CLAHE only for a measured camera-specific need and
retest tracker cadence and accuracy after changing it. See the [streaming
performance guide](../04-streaming/streaming-optimizer.md#capture-and-preprocessing)
for the processing order and baseline. Config Sync removes only explicitly
registered obsolete keys (with a backup); an older
`FramePreprocessor.PREPROCESSING_COLOR_SPACE` value is therefore ignored and
reported rather than left as a second frame-format authority.

## Quick Reference

### Source Types

| Type | Value | Requires |
|------|-------|----------|
| Video File | `VIDEO_FILE` | `VIDEO_FILE_PATH` |
| USB Camera | `USB_CAMERA` | `CAMERA_INDEX` or `DEVICE_PATH` |
| RTSP Stream | `RTSP_STREAM` | `RTSP_URL`; GStreamer optional with OpenCV fallback |
| UDP Stream | `UDP_STREAM` | `UDP_URL`; GStreamer preferred for the maintained RTP/H.264 template |
| HTTP Stream | `HTTP_STREAM` | `HTTP_URL` |
| CSI Camera | `CSI_CAMERA` | GStreamer, Jetson/RPi |
| Custom GStreamer | `CUSTOM_GSTREAMER` | `CUSTOM_PIPELINE` |

### Resolution Presets

```yaml
# SD
CAPTURE_WIDTH: 640
CAPTURE_HEIGHT: 480

# HD
CAPTURE_WIDTH: 1280
CAPTURE_HEIGHT: 720

# Full HD
CAPTURE_WIDTH: 1920
CAPTURE_HEIGHT: 1080
```

### Quality Presets

```yaml
# Low bandwidth
Streaming:
  STREAM_QUALITY: 50
GStreamer:
  GSTREAMER_BITRATE: 1000

# Balanced
Streaming:
  STREAM_QUALITY: 80
GStreamer:
  GSTREAMER_BITRATE: 2000

# High quality
Streaming:
  STREAM_QUALITY: 95
GStreamer:
  GSTREAMER_BITRATE: 5000
```

## Configuration Loading

```python
from classes.parameters import Parameters

# Load merged config (default + user)
params = Parameters()

# Access values
source_type = params.VIDEO_SOURCE_TYPE
width = params.CAPTURE_WIDTH
```

PixEagle does not currently implement arbitrary `PIXEAGLE_*` environment
overrides for YAML parameters. Use `configs/config.yaml`, a setup profile, or
the schema-driven Settings UI; do not rely on undocumented environment names.

## Validation

Configuration is validated against the schema on load:

```python
from classes.config_service import ConfigService

config_service = ConfigService()
config_service.validate()  # Raises on error
```
