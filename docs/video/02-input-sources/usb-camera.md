# USB Camera Source

> USB webcams and cameras with V4L2/GStreamer support

## Overview

USB cameras are the simplest video source for desktop development and ground station setups. PixEagle supports both YUYV (uncompressed) and MJPEG (compressed) formats.

## Configuration

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: USB_CAMERA
  CAMERA_INDEX: 0           # Camera device index
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
  CAPTURE_FPS: 30
  FRAME_ROTATION_DEG: 0     # 0, 90, 180, 270
  FRAME_FLIP_MODE: none     # none, horizontal, vertical, both
  USE_GSTREAMER: true       # Recommended on Linux

USBCamera:
  DEVICE_PATH: /dev/video0  # Linux device path
  PIXEL_FORMAT: YUYV        # YUYV or MJPG
  USE_V4L2_BACKEND: false   # Direct V4L2 (Linux only)
  OPENCV_BUFFER_SIZE: 1     # Frame buffer size
  OPENCV_FOURCC: ""         # Force codec (optional)
```

## Pixel Format Selection

| Format | CPU Usage | Quality | Best For |
|--------|-----------|---------|----------|
| `YUYV` | Medium | Excellent | Desktop with good CPU |
| `MJPG` | Low | Good | Raspberry Pi, embedded |

### YUYV (Uncompressed)

```yaml
USBCamera:
  PIXEL_FORMAT: YUYV
```

**GStreamer Pipeline:**
```
v4l2src device=/dev/video0
  ! video/x-raw,format=YUY2,width=640,height=480,framerate=30/1
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true max-buffers=1 sync=false
```

**Pros:** No compression artifacts, consistent quality
**Cons:** Higher bandwidth, more CPU for conversion

### MJPEG (Compressed)

```yaml
USBCamera:
  PIXEL_FORMAT: MJPG
```

**GStreamer Pipeline:**
```
v4l2src device=/dev/video0
  ! image/jpeg,width=640,height=480,framerate=30/1
  ! jpegdec
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true max-buffers=1 sync=false
```

**Pros:** Lower CPU, less USB bandwidth
**Cons:** Compression artifacts, variable quality

## Camera Index

```yaml
CAMERA_INDEX: 0  # First camera
```

Find available cameras:
```bash
# Linux
ls /dev/video*

# Or use webcam_list.py
python src/webcam_list.py
```

Output:
```
Found 2 cameras:
ID: 0, Resolution: 640x480, FPS: 30.0
ID: 1, Resolution: 1920x1080, FPS: 30.0
```

## Platform-Specific

### Linux

```yaml
USE_GSTREAMER: true
USBCamera:
  USE_V4L2_BACKEND: true  # Direct V4L2 access
```

**Check camera capabilities:**
```bash
v4l2-ctl --list-formats-ext -d /dev/video0
```

### Windows

```yaml
USE_GSTREAMER: false  # Use DirectShow
```

GStreamer setup on Windows is complex; OpenCV backend recommended.

### macOS

```yaml
USE_GSTREAMER: false  # Use AVFoundation
```

## Buffer Management

```yaml
USBCamera:
  OPENCV_BUFFER_SIZE: 1  # Minimum latency
```

| Buffer Size | Latency | Stability |
|-------------|---------|-----------|
| 1 | Lowest | May drop frames |
| 2-3 | Low | Balanced |
| 5+ | Higher | Most stable |

## GStreamer vs OpenCV

### With GStreamer (`USE_GSTREAMER: true`)

```python
# Advantages:
# - Direct V4L2 access
# - Precise format control
# - Lower latency possible
# - Better error handling

# Pipeline created:
pipeline = "v4l2src device=/dev/video0 ! ... ! appsink"
cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
```

### Without GStreamer (`USE_GSTREAMER: false`)

```python
# Advantages:
# - Simpler setup
# - Cross-platform
# - No GStreamer dependency

cap = cv2.VideoCapture(0)  # Index-based
# or
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)  # With V4L2 backend
```

## Troubleshooting

### Camera Not Found

```
ERROR: Cannot open camera index 0
```

**Solutions:**
1. Check camera is connected: `ls /dev/video*`
2. Check permissions: `sudo usermod -a -G video $USER`
3. Try different index: `CAMERA_INDEX: 1`

### Wrong Resolution

```
WARNING: Could not set resolution to 1920x1080
```

**Cause:** Camera doesn't support requested resolution

**Solution:** Check supported resolutions:
```bash
v4l2-ctl --list-formats-ext -d /dev/video0
```

### Low FPS

**Solutions:**
1. Use MJPEG format (less bandwidth)
2. Reduce resolution
3. Check USB bandwidth (try USB 3.0 port)

### Image Upside Down

```yaml
VideoSource:
  FRAME_ROTATION_DEG: 180
  FRAME_FLIP_MODE: none
```

### Dark/Overexposed Image

**Solution:** Disable auto-exposure, set manually:
```bash
v4l2-ctl -d /dev/video0 --set-ctrl=auto_exposure=1
v4l2-ctl -d /dev/video0 --set-ctrl=exposure_time_absolute=500
```

## Advanced: Force FOURCC

```yaml
USBCamera:
  OPENCV_FOURCC: MJPG  # Force MJPEG mode
```

Common FOURCC codes:
- `MJPG` - Motion JPEG
- `YUYV` - Uncompressed YUV
- `H264` - H.264 (if supported)

## Example: Logitech C920

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: USB_CAMERA
  CAMERA_INDEX: 0
  CAPTURE_WIDTH: 1280
  CAPTURE_HEIGHT: 720
  CAPTURE_FPS: 30
  USE_GSTREAMER: true

USBCamera:
  PIXEL_FORMAT: MJPG    # C920 has hardware MJPEG
  OPENCV_BUFFER_SIZE: 1
```

## Example: Raspberry Pi USB Camera

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: USB_CAMERA
  CAMERA_INDEX: 0
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
  CAPTURE_FPS: 30
  USE_GSTREAMER: true

USBCamera:
  PIXEL_FORMAT: MJPG    # Essential for RPi CPU
  OPENCV_BUFFER_SIZE: 2
```
