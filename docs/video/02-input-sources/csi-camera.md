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
- `memory:NVMM` - NVIDIA multimedia buffers; the complete OpenCV path is not zero-copy
- `nvvidconv` - Hardware conversion via VIC or CUDA, depending on configuration
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

The default `GStreamerPipelines.CSI_RPI: auto` tries direct BGR first:

```
libcamerasrc
  ! video/x-raw,format=BGR,width=640,height=480,framerate=30/1
  ! appsink drop=true max-buffers=1 sync=false
```

If opening or the first frame fails, it releases that source and tries:

```
libcamerasrc
  ! video/x-raw,format=NV12,width=640,height=480,framerate=30/1
  ! videoconvert
  ! video/x-raw,format=BGR
  ! appsink drop=true max-buffers=1 sync=false
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

Auto selection accepts a path only after receiving a nonempty three-channel
8-bit BGR frame. Each candidate gets one open and one first-frame read, bounded
by `VideoSource.RTSP_CONNECTION_TIMEOUT` (the existing live-source deadline).
If both fail, the existing no-video state and recovery loop apply; API and
settings remain available. Reconnection tries BGR first again. Logs and media
health `last_pipeline_strategy` identify `csi_rpi_bgr` or `csi_rpi_nv12`.

### Direct BGR on CM5/PiSP

Tester measurements on CM5 with IMX219 support using direct BGR on that
setup. At 1280x720/30, mean process CPU fell from 49.8% to 4.9% in a
standalone pipeline and from 79.4% to 37.6% in a PixEagle harness, with
approximately 30 FPS in both. These are capture/harness results; the harness
source and active tracker/model configuration were not supplied.

To adopt automatic selection on an existing installation, set this field in
Settings and restart PixEagle, or edit `configs/config.yaml` while stopped:

```yaml
GStreamerPipelines:
  CSI_RPI: auto
```

This removes the separate CPU `videoconvert` stage. Raspberry Pi's
[PiSP implementation](https://github.com/raspberrypi/libcamera/blob/main/src/libcamera/pipeline/rpi/pisp/pisp.cpp)
supports processed RGB/BGR output. It does not imply that all capture,
resizing, or downstream processing is CPU-free.

An explicit pipeline string is used unchanged with no automatic fallback.
Existing local templates (including previous NV12 defaults and custom direct
BGR) are preserved by updates; use Settings > Config Sync to adopt `auto`
explicitly. Do not reset the entire configuration to change this field. No
OpenCV rebuild is needed when GStreamer capture is already working.

See the [benchmark assessment](../../reporting/agent-ops/codex-modernization/checkpoints/2026-09-17-csi-bgr-benchmark-assessment.md)
for memory results, failed modes, and the next validation steps.

## Sensor ID

For multi-camera setups:

```yaml
CSICamera:
  SENSOR_ID: 0  # First camera
  # SENSOR_ID: 1  # Second camera (if available)
```

## Platform Performance

Measure delivered FPS and process CPU at the selected camera mode. Raspberry
Pi processed streams use the platform camera stack/ISP; board labels alone do
not establish end-to-end frame rate. On Jetson, the current template already
uses `nvvidconv` for NV12-to-BGRx hardware conversion and a CPU conversion to
OpenCV's three-channel BGR. NVIDIA documents BGRx/RGBA hardware outputs for
[JetPack 6 / Jetson Linux 36.4.4](https://docs.nvidia.com/jetson/archives/r36.4.4/DeveloperGuide/SD/Multimedia/AcceleratedGstreamer.html).
Validate the installed JetPack's capabilities before changing this path; the
Pi measurements do not establish Jetson savings.

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
