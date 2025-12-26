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
  USE_GSTREAMER: true  # Required for CSI

CSICamera:
  CSI_SENSOR_ID: 0     # Camera sensor index
  CSI_FLIP_METHOD: 0   # Rotation/flip
```

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
  ! nvvidconv flip-method=0
  ! video/x-raw,format=BGRx
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true sync=false
```

**Key Elements:**
- `nvarguscamerasrc` - NVIDIA camera source (hardware accelerated)
- `memory:NVMM` - GPU memory for zero-copy
- `nvvidconv` - GPU-accelerated conversion with flip support
- `NV12` format for GPU efficiency

### Flip Methods

```yaml
CSICamera:
  CSI_FLIP_METHOD: 0  # See table below
```

| Value | Effect |
|-------|--------|
| 0 | No rotation |
| 1 | 90° clockwise |
| 2 | 180° |
| 3 | 90° counter-clockwise |
| 4 | Horizontal flip |
| 5 | Vertical flip |
| 6 | Upper-left to lower-right |
| 7 | Upper-right to lower-left |

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
# Install libcamera and GStreamer plugin
sudo apt install libcamera-apps gstreamer1.0-libcamera
```

### RPi Camera Verification

```bash
# Check camera detected
libcamera-hello --list-cameras

# Test with libcamera
libcamera-hello -t 5000
```

## Sensor ID

For multi-camera setups:

```yaml
CSICamera:
  CSI_SENSOR_ID: 0  # First camera
  # CSI_SENSOR_ID: 1  # Second camera (if available)
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
# Enable camera in config
sudo raspi-config
# Interface Options > Camera > Enable

# Or edit config.txt
echo "camera_auto_detect=1" | sudo tee -a /boot/config.txt
sudo reboot
```

### "No cameras available"

**Solutions:**
1. Check ribbon cable connection
2. Verify camera module compatibility
3. Update firmware: `sudo apt update && sudo apt upgrade`

### Image Upside Down

```yaml
CSICamera:
  CSI_FLIP_METHOD: 2  # 180° rotation
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
  CAPTURE_WIDTH: 1280
  CAPTURE_HEIGHT: 720
  CAPTURE_FPS: 30
  USE_GSTREAMER: true

CSICamera:
  CSI_SENSOR_ID: 0
  CSI_FLIP_METHOD: 0
```

## Example: Raspberry Pi Camera Module 3

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CSI_CAMERA
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
  CAPTURE_FPS: 30
  USE_GSTREAMER: true

CSICamera:
  CSI_SENSOR_ID: 0
  CSI_FLIP_METHOD: 0
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
