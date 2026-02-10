# Video Source Configuration

> Complete reference for video input settings

## Core Settings

```yaml
VideoSource:
  # Source type selection
  VIDEO_SOURCE_TYPE: USB_CAMERA   # Required

  # Capture dimensions
  CAPTURE_WIDTH: 640              # Frame width
  CAPTURE_HEIGHT: 480             # Frame height
  CAPTURE_FPS: 30                 # Target frame rate

  # Backend selection
  USE_GSTREAMER: true             # Prefer GStreamer backend

  # Buffer settings
  OPENCV_BUFFER_SIZE: 1           # OpenCV buffer size
  STORE_LAST_FRAMES: 5            # Frame history length
```

## Backend Routing Rules

`USE_GSTREAMER` is a **preference** for source types that support dual backends:

| Source Type | `USE_GSTREAMER: false` | `USE_GSTREAMER: true` |
|-------------|-------------------------|-----------------------|
| `VIDEO_FILE` | OpenCV | Try GStreamer, fallback to OpenCV if unavailable/fails |
| `USB_CAMERA` | OpenCV | Try GStreamer strategy chain, fallback to OpenCV |
| `RTSP_STREAM` | OpenCV | Existing RTSP GStreamer fallback flow |
| `UDP_STREAM` | OpenCV/FFmpeg | GStreamer pipeline |
| `HTTP_STREAM` | OpenCV | GStreamer pipeline |
| `CSI_CAMERA` | GStreamer | GStreamer |
| `CUSTOM_GSTREAMER` | GStreamer | GStreamer |

## VIDEO_FILE Settings

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: VIDEO_FILE
  VIDEO_FILE_PATH: resources/test_video.mp4
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `VIDEO_FILE_PATH` | string | - | Path to video file |

Supported formats: MP4, AVI, MKV, MOV, WebM

## USB_CAMERA Settings

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: USB_CAMERA
  CAMERA_INDEX: 0
  DEVICE_PATH: /dev/video0
  PIXEL_FORMAT: YUYV
  USE_V4L2_BACKEND: false
  OPENCV_FOURCC: ""
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `CAMERA_INDEX` | int | 0 | Camera index |
| `DEVICE_PATH` | string | /dev/video0 | Linux device path |
| `PIXEL_FORMAT` | string | YUYV | Pixel format (YUYV, MJPG) |
| `USE_V4L2_BACKEND` | bool | false | Force V4L2 backend |
| `OPENCV_FOURCC` | string | "" | Force codec (e.g., MJPG) |

### Finding Camera Devices

```bash
# List devices
v4l2-ctl --list-devices

# Check formats
v4l2-ctl -d /dev/video0 --list-formats-ext
```

## RTSP_STREAM Settings

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: RTSP_STREAM
  RTSP_URL: rtsp://192.168.1.100:554/stream
  RTSP_PROTOCOL: tcp
  RTSP_LATENCY: 200
  RTSP_MAX_CONSECUTIVE_FAILURES: 10
  RTSP_CONNECTION_TIMEOUT: 5.0
  RTSP_MAX_RECOVERY_ATTEMPTS: 3
  RTSP_FRAME_CACHE_SIZE: 5
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `RTSP_URL` | string | - | RTSP stream URL |
| `RTSP_PROTOCOL` | string | tcp | Transport (tcp/udp) |
| `RTSP_LATENCY` | int | 200 | Buffer latency (ms) |
| `RTSP_MAX_CONSECUTIVE_FAILURES` | int | 10 | Max failures before recovery |
| `RTSP_CONNECTION_TIMEOUT` | float | 5.0 | Connection timeout (s) |
| `RTSP_MAX_RECOVERY_ATTEMPTS` | int | 3 | Max reconnection attempts |
| `RTSP_FRAME_CACHE_SIZE` | int | 5 | Cached frames for fallback |

### RTSP URL Formats

```yaml
# Standard
RTSP_URL: rtsp://192.168.1.100:554/stream

# With authentication
RTSP_URL: rtsp://user:password@192.168.1.100:554/stream

# With path
RTSP_URL: rtsp://camera.local:554/live/ch00_0
```

## UDP_STREAM Settings

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: UDP_STREAM
  UDP_URL: udp://0.0.0.0:5600
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `UDP_URL` | string | - | UDP stream URL |

### MAVLink Video

```yaml
# Receive from companion computer
UDP_URL: udp://0.0.0.0:5600
```

## HTTP_STREAM Settings

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: HTTP_STREAM
  HTTP_URL: http://192.168.1.100:8080/video
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `HTTP_URL` | string | - | HTTP stream URL |

## CSI_CAMERA Settings

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CSI_CAMERA
  CSI_SENSOR_ID: 0
  FRAME_ROTATION_DEG: 0
  FRAME_FLIP_MODE: none
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `CSI_SENSOR_ID` | int | 0 | Camera sensor ID (0 or 1) |
| `FRAME_ROTATION_DEG` | int | 0 | Rotation in degrees (`0`, `90`, `180`, `270`) |
| `FRAME_FLIP_MODE` | string | `none` | Flip mode (`none`, `horizontal`, `vertical`, `both`) |

### Rotation Values

| Value | Effect |
|-------|--------|
| 0 | No rotation |
| 90 | 90° clockwise |
| 180 | 180° |
| 270 | 90° counter-clockwise |

### Flip Values

| Value | Effect |
|-------|--------|
| `none` | No flip |
| `horizontal` | Mirror left/right |
| `vertical` | Mirror up/down |
| `both` | Horizontal + vertical flip |

## CUSTOM_GSTREAMER Settings

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CUSTOM_GSTREAMER
  CUSTOM_PIPELINE: >
    videotestsrc pattern=ball
    ! video/x-raw,width=640,height=480,framerate=30/1
    ! videoconvert
    ! video/x-raw,format=BGR
    ! appsink drop=true sync=false
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `CUSTOM_PIPELINE` | string | - | GStreamer pipeline string |

### Pipeline Requirements

- Must end with `appsink`
- Must output `video/x-raw,format=BGR`

## Advanced Settings

### Frame Management

```yaml
VideoSource:
  STORE_LAST_FRAMES: 5        # History buffer size
  OPENCV_BUFFER_SIZE: 1       # OpenCV internal buffer
  DEFAULT_FPS: 30             # Fallback FPS
```

### Error Recovery

```yaml
VideoSource:
  # RTSP recovery
  RTSP_MAX_CONSECUTIVE_FAILURES: 10
  RTSP_CONNECTION_TIMEOUT: 5.0
  RTSP_MAX_RECOVERY_ATTEMPTS: 3
  RTSP_FRAME_CACHE_SIZE: 5
```

## Examples

### High-Resolution USB Camera

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: USB_CAMERA
  DEVICE_PATH: /dev/video0
  CAPTURE_WIDTH: 1920
  CAPTURE_HEIGHT: 1080
  CAPTURE_FPS: 30
  PIXEL_FORMAT: MJPG
  USE_GSTREAMER: true
```

### Low-Latency RTSP

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: RTSP_STREAM
  RTSP_URL: rtsp://camera:554/stream
  RTSP_PROTOCOL: tcp
  RTSP_LATENCY: 100
  USE_GSTREAMER: true
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
```

### Jetson CSI Camera

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CSI_CAMERA
  CSI_SENSOR_ID: 0
  FRAME_ROTATION_DEG: 0
  FRAME_FLIP_MODE: none
  CAPTURE_WIDTH: 1280
  CAPTURE_HEIGHT: 720
  CAPTURE_FPS: 60
  USE_GSTREAMER: true
```
