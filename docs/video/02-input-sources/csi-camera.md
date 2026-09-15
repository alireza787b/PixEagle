# CSI Camera Source

> MIPI CSI cameras for Raspberry Pi and NVIDIA Jetson

## Overview

CSI (Camera Serial Interface) cameras connect directly to the board's camera port, offering lower latency and better integration than USB cameras. PixEagle supports both Raspberry Pi (libcamera) and NVIDIA Jetson (nvarguscamerasrc) platforms.

## Configuration

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CSI_CAMERA
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
  CAPTURE_FPS: 30
  USE_GSTREAMER: true  # Documents intent; CSI_CAMERA always selects GStreamer
  FRAME_ROTATION_DEG: 0
  FRAME_FLIP_MODE: none

CSICamera:
  SENSOR_ID: 0         # Camera sensor index
```

`CSI_CAMERA` is a GStreamer-only source in the current runtime. It selects the
CSI pipeline even if `USE_GSTREAMER` is accidentally false, so both the system
plugins and the active OpenCV `CAP_GSTREAMER` backend must be ready. There is no
silent OpenCV/FFmpeg fallback for CSI.

## Platform Detection

PixEagle automatically detects the platform:

```python
# In VideoHandler
self.platform = platform.system()
self.is_arm = platform.machine().startswith('arm') or platform.machine().startswith('aarch')

# Jetson detection
if 'tegra' in platform.release().lower():
    # Use nvarguscamerasrc
else:
    # Use libcamerasrc (Raspberry Pi)
```

## NVIDIA Jetson

### GStreamer Pipeline

```
nvarguscamerasrc sensor-id=0
  ! video/x-raw(memory:NVMM),width=640,height=480,format=NV12,framerate=30/1
  ! nvvidconv
  ! video/x-raw,format=BGRx
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true sync=false
```

**Key Elements:**
- `nvarguscamerasrc` - NVIDIA camera source (hardware accelerated)
- `memory:NVMM` - GPU memory for zero-copy
- `nvvidconv` - GPU-accelerated conversion
- `NV12` format for GPU efficiency

### Universal Orientation

```yaml
VideoSource:
  FRAME_ROTATION_DEG: 0  # 0, 90, 180, 270
  FRAME_FLIP_MODE: none  # none, horizontal, vertical, both
```

Rotation values:
- `0`: No rotation
- `90`: 90° clockwise
- `180`: 180°
- `270`: 90° counter-clockwise

Flip values:
- `none`: No flip
- `horizontal`: Mirror left/right
- `vertical`: Mirror up/down
- `both`: Horizontal + vertical

### Jetson Camera Verification

```bash
# Check camera detected
ls /dev/video*

# Test with GStreamer
gst-launch-1.0 nvarguscamerasrc ! nvvidconv ! autovideosink
```

## Raspberry Pi

### GStreamer Pipeline (libcamera)

```
libcamerasrc
  ! video/x-raw,width=640,height=480,framerate=30/1
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true sync=false
```

### Prerequisites

```bash
# Reconcile and verify the Raspberry Pi GStreamer camera source
bash scripts/setup/reconcile-rpi-csi-gstreamer.sh
gst-inspect-1.0 libcamerasrc
```

The guided installer runs this lightweight reconciliation when the optional
OpenCV/GStreamer capability is selected. It reuses an existing compatible
OpenCV build and installs the distribution's `gstreamer1.0-libcamera` package
only when `libcamerasrc` is missing on a detected Raspberry Pi.

### RPi Camera Verification

```bash
# Check camera detected
rpicam-hello --list-cameras

# Headless/SSH capture test (a Pi OS Lite session may not show a preview)
rpicam-hello --nopreview --timeout 5000

# Verify that GStreamer can acquire frames without a display
gst-launch-1.0 -e libcamerasrc num-buffers=30 \
  ! video/x-raw,format=NV12,width=640,height=480,framerate=30/1 \
  ! videoconvert ! fakesink sync=false
```

`rpicam-hello` detecting the sensor proves the libcamera camera stack, not the
separate GStreamer plugin or OpenCV `CAP_GSTREAMER` integration. Run
`make check-gstreamer-runtime` to verify those PixEagle prerequisites.

PixEagle requests the processed `NV12` format before converting frames to the
BGR layout required by OpenCV. This avoids ambiguous `libcamerasrc` caps
negotiation and follows the standard Raspberry Pi ISP processed-video path.
Direct BGR capture is an advanced optimization only when the installed camera
stack reports that capability.

## Sensor ID

For multi-camera setups:

```yaml
CSICamera:
  SENSOR_ID: 0  # First camera
  # SENSOR_ID: 1  # Second camera (if available)
```

## Performance Comparison

| Platform | Element | Hardware Accel | Typical FPS |
|----------|---------|----------------|-------------|
| Jetson Nano | nvarguscamerasrc | Yes (GPU) | 30+ |
| Jetson TX2 | nvarguscamerasrc | Yes (GPU) | 60+ |
| RPi 4 | libcamerasrc | No | 30 |
| RPi 5 | libcamerasrc | Partial | 30+ |

## Troubleshooting

### "Could not initialize camera"

**Jetson:**
```bash
# Check Argus daemon
sudo systemctl status nvargus-daemon
sudo systemctl restart nvargus-daemon
```

**Raspberry Pi:**
```bash
rpicam-hello --list-cameras
bash scripts/setup/reconcile-rpi-csi-gstreamer.sh
make check-gstreamer-runtime
```

Do not add duplicate firmware settings when `rpicam-hello --list-cameras`
already reports the sensor. For a Compute Module whose camera is not listed,
use the carrier-board and camera overlay instructions from the current
Raspberry Pi documentation.

### "No cameras available"

**Solutions:**
1. Check ribbon cable connection
2. Verify camera module compatibility
3. Update firmware: `sudo apt update && sudo apt upgrade`

### Image Upside Down

```yaml
VideoSource:
  FRAME_ROTATION_DEG: 180
  FRAME_FLIP_MODE: none
```

### Low FPS on Raspberry Pi

**Solutions:**
1. Reduce resolution:
   ```yaml
   CAPTURE_WIDTH: 480
   CAPTURE_HEIGHT: 360
   ```

2. Disable preview in libcamera
3. Check thermal throttling: `vcgencmd measure_temp`

## Example: Jetson Nano with IMX219

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CSI_CAMERA
  FRAME_ROTATION_DEG: 0
  FRAME_FLIP_MODE: none
  CAPTURE_WIDTH: 1280
  CAPTURE_HEIGHT: 720
  CAPTURE_FPS: 30
  USE_GSTREAMER: true

CSICamera:
  SENSOR_ID: 0
```

## Example: Raspberry Pi Camera Module 3

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CSI_CAMERA
  FRAME_ROTATION_DEG: 0
  FRAME_FLIP_MODE: none
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
  CAPTURE_FPS: 30
  USE_GSTREAMER: true

CSICamera:
  SENSOR_ID: 0
```

## Advanced: Custom Jetson Pipeline

For maximum performance on Jetson:

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CUSTOM_GSTREAMER
  CUSTOM_PIPELINE: >
    nvarguscamerasrc sensor-id=0 sensor-mode=3
    exposuretimerange="13000 13000"
    gainrange="1 1"
    ! video/x-raw(memory:NVMM),width=1280,height=720,format=NV12,framerate=60/1
    ! nvvidconv
    ! video/x-raw,format=BGRx
    ! videoconvert
    ! video/x-raw,format=BGR
    ! appsink drop=true sync=false
```
