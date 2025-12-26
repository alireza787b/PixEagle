# Video Configuration

> Configuration reference for video subsystem

## Overview

PixEagle's video subsystem is configured through YAML configuration files. This section documents all video-related configuration options.

## Configuration Files

| File | Purpose |
|------|---------|
| `configs/config_default.yaml` | Default configuration |
| `configs/config_user.yaml` | User overrides |
| `configs/config_schema.yaml` | Schema validation |

## Configuration Sections

### VideoSource

Video input configuration:

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: USB_CAMERA
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
  CAPTURE_FPS: 30
  USE_GSTREAMER: true
```

See [Video Source Config](video-source-config.md) for details.

### Streaming

Video output configuration:

```yaml
FastAPI:
  ENABLE_HTTP_STREAM: true
  ENABLE_WEBSOCKET: true
  ENABLE_WEBRTC: false
  STREAM_QUALITY: 80

GStreamer:
  ENABLE: true
  DEST_HOST: 192.168.1.10
  DEST_PORT: 5600
```

See [Streaming Config](streaming-config.md) for details.

## Quick Reference

### Source Types

| Type | Value | Requires |
|------|-------|----------|
| Video File | `VIDEO_FILE` | `VIDEO_FILE_PATH` |
| USB Camera | `USB_CAMERA` | `CAMERA_INDEX` or `DEVICE_PATH` |
| RTSP Stream | `RTSP_STREAM` | `RTSP_URL`, GStreamer |
| UDP Stream | `UDP_STREAM` | `UDP_URL`, GStreamer |
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
STREAM_QUALITY: 50
BITRATE: 1000

# Balanced
STREAM_QUALITY: 80
BITRATE: 2000

# High quality
STREAM_QUALITY: 95
BITRATE: 5000
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

## Environment Overrides

```bash
# Override via environment
export PIXEAGLE_VIDEO_SOURCE_TYPE=RTSP_STREAM
export PIXEAGLE_RTSP_URL=rtsp://camera:554/stream
```

## Validation

Configuration is validated against the schema on load:

```python
from classes.config_service import ConfigService

config_service = ConfigService()
config_service.validate()  # Raises on error
```
