# GStreamer in PixEagle

> Multimedia framework for video input and output

## Overview

PixEagle uses GStreamer for advanced video capture and streaming operations. GStreamer provides hardware-accelerated video processing, codec support, and network streaming capabilities.

## When GStreamer is Used

| Source Type | GStreamer Required |
|-------------|-------------------|
| VIDEO_FILE | Optional |
| USB_CAMERA | Optional (recommended for MJPEG) |
| RTSP_STREAM | Preferred; OpenCV fallback exists |
| UDP_STREAM | Preferred for the maintained RTP/H.264 template |
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

PixEagle's current input pipelines and QGC UDP writer use OpenCV's GStreamer
backend. Both conditions are required:

1. GStreamer runtime/plugins are installed.
2. `cv2.getBuildInformation()` reports `GStreamer: YES` for the active PixEagle
   virtual environment.

The ordinary pip OpenCV wheel commonly satisfies dashboard JPEG streaming but
does not satisfy this `CAP_GSTREAMER` contract. Use
`bash scripts/setup/build-opencv.sh` when a configured input/output path needs
it. Browser HTTP/WebSocket streaming remains available when GStreamer is
absent; PixEagle does not silently switch a configured QGC UDP destination to
an HTTP/WS exposure profile.

### Ubuntu/Debian and Raspberry Pi OS

Choose advanced GStreamer video in guided setup. For an existing installation,
use the same dependency reconciler without rebuilding OpenCV:

```bash
bash scripts/setup/reconcile-gstreamer-runtime.sh
make check-gstreamer-runtime
```

Capture and native-media readiness are separate: OpenCV's `GStreamer: YES`
is required for `CAP_GSTREAMER` capture, but the optional WebRTC sender uses
Python GI directly. Setup installs ICE, DTLS/SRTP/SCTP, H.264/VP8 and GI
components in the existing optional step. It reuses a supported distro
congestion-control plugin or builds the pinned `gst-plugin-rtp` with Cargo's
lockfile. The managed plugin is discovered from the selected venv, including
under the supervised service; no global `PYTHONPATH` or shell-only plugin path
is required. See [installation](../../INSTALLATION.md#optional-advanced-video-runtime).

Runtime readiness does not enable native QGC WebRTC before qualification.
Without these optional dependencies, browser aiortc WebRTC and JPEG remain
supported. QGC application packages must bundle their own receiver dependencies;
these backend scripts do not install anything on the GCS computer.

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
  ENABLE_GSTREAMER_STREAM: true
  GSTREAMER_HOST: 192.168.1.10
  GSTREAMER_PORT: 5600
```

Output pipeline:
```
appsrc ! videoconvert ! x264enc tune=zerolatency ! rtph264pay
  ! udpsink host=192.168.1.10 port=5600
```
