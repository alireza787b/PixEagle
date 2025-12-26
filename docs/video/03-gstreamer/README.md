# GStreamer in PixEagle

> Multimedia framework for video input and output

## Overview

PixEagle uses GStreamer for advanced video capture and streaming operations. GStreamer provides hardware-accelerated video processing, codec support, and network streaming capabilities.

## When GStreamer is Used

| Source Type | GStreamer Required |
|-------------|-------------------|
| VIDEO_FILE | Optional |
| USB_CAMERA | Optional (recommended for MJPEG) |
| RTSP_STREAM | Required |
| UDP_STREAM | Required |
| HTTP_STREAM | Optional |
| CSI_CAMERA | Required |
| CUSTOM_GSTREAMER | Required |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GStreamer Framework                       │
├─────────────────────────────────────────────────────────────┤
│  Source Elements    │  Processing    │  Sink Elements       │
│  ─────────────────  │  ───────────   │  ─────────────        │
│  • v4l2src          │  • decodebin   │  • appsink (input)    │
│  • rtspsrc          │  • jpegdec     │  • appsrc (output)    │
│  • udpsrc           │  • h264parse   │  • udpsink            │
│  • filesrc          │  • videoconvert│  • fakesink           │
│  • nvarguscamerasrc │  • videoscale  │                       │
│  • libcamerasrc     │  • x264enc     │                       │
└─────────────────────────────────────────────────────────────┘
```

## Documentation

- [Pipeline Reference](pipeline-reference.md) - Complete element reference
- [Input Pipelines](input-pipelines.md) - Capture pipeline configurations
- [Output Pipeline](output-pipeline.md) - QGroundControl streaming
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

## Configuration

Enable GStreamer in config:

```yaml
VideoSource:
  USE_GSTREAMER: true
```

## Key Concepts

### Elements

GStreamer pipelines consist of elements connected together:

```
source ! processing ! processing ! sink
```

Elements are separated by `!` (exclamation mark).

### Caps

Capabilities (caps) specify data format between elements:

```
video/x-raw,format=BGR,width=640,height=480
```

### appsink

PixEagle uses `appsink` to receive frames from GStreamer into OpenCV:

```
... ! videoconvert ! video/x-raw,format=BGR ! appsink
```

## Requirements

### Ubuntu/Debian

```bash
sudo apt install \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav
```

### Verify Installation

```bash
# Check GStreamer version
gst-launch-1.0 --version

# Test pipeline
gst-launch-1.0 videotestsrc ! autovideosink
```

## Quick Example

### Input (RTSP camera)

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: RTSP_STREAM
  RTSP_URL: rtsp://192.168.1.100:554/stream
  USE_GSTREAMER: true
```

Generated pipeline:
```
rtspsrc location=rtsp://192.168.1.100:554/stream latency=200 protocols=tcp
  ! decodebin
  ! videoconvert
  ! video/x-raw,format=BGR
  ! videoscale
  ! video/x-raw,width=640,height=480
  ! appsink drop=true sync=false
```

### Output (to QGroundControl)

```yaml
GStreamer:
  ENABLE: true
  DEST_HOST: 192.168.1.10
  DEST_PORT: 5600
```

Output pipeline:
```
appsrc ! videoconvert ! x264enc tune=zerolatency ! rtph264pay
  ! udpsink host=192.168.1.10 port=5600
```
