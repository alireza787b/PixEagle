# GStreamer Input Pipelines

> Capture pipeline configurations for all source types

## Overview

PixEagle generates optimized GStreamer pipelines for each video source type. All input pipelines end with:

```
... ! videoconvert ! video/x-raw,format=BGR ! appsink drop=true sync=false
```

## USB Camera Pipelines

### YUYV Format

```gstreamer
v4l2src device=/dev/video0
  ! video/x-raw,format=YUY2,width=640,height=480,framerate=30/1
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true max-buffers=1 sync=false
```

Configuration:
```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: USB_CAMERA
  DEVICE_PATH: /dev/video0
  PIXEL_FORMAT: YUYV
  USE_GSTREAMER: true
```

### MJPEG Format

```gstreamer
v4l2src device=/dev/video0
  ! image/jpeg,width=1920,height=1080,framerate=30/1
  ! jpegdec
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true max-buffers=1 sync=false
```

Configuration:
```yaml
VideoSource:
  PIXEL_FORMAT: MJPG
  USE_GSTREAMER: true
```

## RTSP Pipelines

### Primary Pipeline

Optimized for low latency:

```gstreamer
rtspsrc location=rtsp://192.168.1.100:554/stream
    latency=200
    protocols=tcp
    drop-on-latency=true
    do-rtcp=false
  ! decodebin
  ! videoconvert
  ! video/x-raw,format=BGR
  ! videoscale method=0
  ! video/x-raw,width=640,height=480
  ! appsink drop=true max-buffers=1 sync=false
```

### Fallback Pipelines

PixEagle generates 4 fallback pipelines with increasing latency tolerance:

| Fallback | Latency | Changes |
|----------|---------|---------|
| Primary | 200ms | TCP, drop-on-latency |
| Fallback 1 | 500ms | Increased buffer |
| Fallback 2 | 1000ms | Queue buffers added |
| Fallback 3 | 2000ms | Maximum tolerance |

### RTSP with Hardware Decode (NVIDIA)

```gstreamer
rtspsrc location=rtsp://host:554/stream latency=200
  ! rtph264depay
  ! h264parse
  ! nvv4l2decoder
  ! nvvidconv
  ! video/x-raw,format=BGRx
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true sync=false
```

## UDP Pipeline

### Standard H.264 RTP

```gstreamer
udpsrc uri=udp://0.0.0.0:5600
    caps="application/x-rtp,media=video,encoding-name=H264,payload=96"
  ! rtph264depay
  ! h264parse
  ! avdec_h264
  ! videoconvert
  ! video/x-raw,format=BGR
  ! videoscale
  ! video/x-raw,width=640,height=480
  ! appsink drop=true max-buffers=1 sync=false
```

Configuration:
```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: UDP_STREAM
  UDP_URL: udp://0.0.0.0:5600
  USE_GSTREAMER: true
```

### MAVLink Video (Companion Computer)

```gstreamer
udpsrc port=5600
  ! application/x-rtp,encoding-name=H264,payload=96
  ! rtph264depay
  ! queue max-size-buffers=1 leaky=downstream
  ! h264parse
  ! avdec_h264 max-threads=4
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true sync=false
```

## CSI Camera Pipelines

### NVIDIA Jetson

```gstreamer
nvarguscamerasrc sensor-id=0
  ! video/x-raw(memory:NVMM),width=1920,height=1080,framerate=30/1
  ! nvvidconv
  ! video/x-raw,format=BGRx,width=640,height=480
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true max-buffers=1 sync=false
```

Configuration:
```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CSI_CAMERA
  CSI_SENSOR_ID: 0
  FRAME_ROTATION_DEG: 0
  FRAME_FLIP_MODE: none
  USE_GSTREAMER: true
```

Orientation values:
- Rotation: `0`, `90`, `180`, `270`
- Flip: `none`, `horizontal`, `vertical`, `both`

### Raspberry Pi

```gstreamer
libcamerasrc
  ! video/x-raw,width=1920,height=1080,framerate=30/1
  ! videoconvert
  ! videoscale
  ! video/x-raw,format=BGR,width=640,height=480
  ! appsink drop=true max-buffers=1 sync=false
```

## HTTP Stream Pipeline

```gstreamer
souphttpsrc location=http://192.168.1.100:8080/video is-live=true
  ! decodebin
  ! videoconvert
  ! video/x-raw,format=BGR
  ! videoscale
  ! video/x-raw,width=640,height=480
  ! appsink drop=true max-buffers=1 sync=false
```

## Video File Pipeline

```gstreamer
filesrc location=/path/to/video.mp4
  ! decodebin
  ! videoconvert
  ! video/x-raw,format=BGR
  ! videoscale
  ! video/x-raw,width=640,height=480
  ! appsink drop=true sync=true
```

Note: `sync=true` for video files to maintain proper playback speed.

## Pipeline Optimization

### Low Latency Settings

```
drop=true          # Drop frames rather than queue
max-buffers=1      # Minimal buffering
sync=false         # Don't sync to clock
leaky=downstream   # Drop old frames when queue full
```

### Memory Efficiency

```
queue max-size-buffers=1 max-size-time=0 max-size-bytes=0
```

### Thread Optimization

```
avdec_h264 max-threads=4    # Use multiple decode threads
queue max-size-buffers=10   # Smooth thread handoff
```

## Testing Pipelines

### Test with gst-launch

Replace `appsink` with `autovideosink`:

```bash
gst-launch-1.0 rtspsrc location=rtsp://camera:554/stream \
  ! decodebin ! videoconvert ! autovideosink
```

### Measure Latency

```bash
gst-launch-1.0 rtspsrc location=rtsp://camera:554/stream latency=0 \
  ! decodebin ! videoconvert ! fpsdisplaysink sync=false
```
