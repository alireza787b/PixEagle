# GStreamer Troubleshooting

> Common issues and solutions

## Diagnostic Commands

### Check GStreamer Installation

```bash
# Version
gst-launch-1.0 --version

# Available plugins
gst-inspect-1.0 | head -50

# Check specific element
gst-inspect-1.0 x264enc
gst-inspect-1.0 nvarguscamerasrc
```

### Test Pipeline

```bash
# Basic test
gst-launch-1.0 videotestsrc ! autovideosink

# Test USB camera
gst-launch-1.0 v4l2src device=/dev/video0 ! autovideosink

# Test RTSP
gst-launch-1.0 rtspsrc location=rtsp://camera:554/stream ! decodebin ! autovideosink
```

## Common Errors

### "Element not found"

**Error:**
```
No such element or plugin 'nvarguscamerasrc'
```

**Solutions:**

1. Install missing plugin:
```bash
# Base plugins
sudo apt install gstreamer1.0-plugins-base

# Good plugins (v4l2src, jpegdec)
sudo apt install gstreamer1.0-plugins-good

# Bad plugins (h264parse)
sudo apt install gstreamer1.0-plugins-bad

# Ugly plugins (x264enc)
sudo apt install gstreamer1.0-plugins-ugly

# Libav (avdec_h264)
sudo apt install gstreamer1.0-libav

# VAAPI (Intel HW accel)
sudo apt install gstreamer1.0-vaapi
```

2. For Jetson elements (`nvarguscamerasrc`, `nvvidconv`):
   - Install JetPack SDK
   - Elements are only available on NVIDIA Jetson platforms

3. For RPi elements (`libcamerasrc`):
```bash
sudo apt install gstreamer1.0-libcamera
```

### "Could not link elements"

**Error:**
```
Could not link 'element1' to 'element2'
```

**Cause:** Incompatible caps between elements.

**Solutions:**

1. Add `videoconvert` between elements:
```gstreamer
# Before
rtspsrc ! appsink

# After
rtspsrc ! decodebin ! videoconvert ! appsink
```

2. Specify explicit caps:
```gstreamer
v4l2src ! video/x-raw,format=YUY2 ! videoconvert ! video/x-raw,format=BGR
```

3. Check element capabilities:
```bash
gst-inspect-1.0 v4l2src | grep -A 20 "SRC template"
```

### "No RTSP streams found"

**Error:**
```
rtspsrc: No streams found
```

**Solutions:**

1. Verify URL in VLC first:
```bash
vlc rtsp://camera:554/stream
```

2. Check authentication:
```
rtsp://username:password@camera:554/stream
```

3. Try different protocol:
```yaml
RTSP_PROTOCOL: udp  # Try TCP if UDP fails
```

4. Increase timeout:
```gstreamer
rtspsrc location=... timeout=10000000
```

### "Device busy"

**Error:**
```
v4l2src: Cannot identify device '/dev/video0'
```

**Solutions:**

1. Check if device is in use:
```bash
fuser /dev/video0
```

2. Kill conflicting process:
```bash
sudo fuser -k /dev/video0
```

3. Check device permissions:
```bash
ls -la /dev/video*
sudo usermod -aG video $USER
# Logout and login again
```

### Pipeline Hangs/Deadlock

**Symptoms:** Pipeline starts but no frames appear.

**Solutions:**

1. Add `sync=false` to sink:
```gstreamer
... ! appsink sync=false
```

2. Add queue elements:
```gstreamer
decodebin ! queue ! videoconvert ! queue ! appsink
```

3. Set async=false:
```gstreamer
appsink sync=false async=false
```

### Memory Leak

**Symptoms:** Memory usage grows continuously.

**Solutions:**

1. Set max-buffers on appsink:
```gstreamer
appsink max-buffers=1 drop=true
```

2. Use leaky queue:
```gstreamer
queue max-size-buffers=2 leaky=downstream
```

3. Properly release pipeline:
```python
pipeline.set_state(Gst.State.NULL)
```

## Platform-Specific Issues

### Jetson

**Issue:** "Failed to create CaptureSession"
```bash
# Check camera
nvgstcapture-1.0  # Should show camera preview
```

**Issue:** Low FPS
```bash
# Set performance mode
sudo nvpmodel -m 0
sudo jetson_clocks
```

### Raspberry Pi

**Issue:** "libcamera not found"
```bash
# Enable camera in config
sudo raspi-config
# Interface Options > Camera > Enable

# Install libcamera
sudo apt install libcamera-apps
```

**Issue:** Legacy camera stack
```bash
# Use legacy if libcamera fails
gpu_mem=128  # Add to /boot/config.txt
start_x=1
```

### Intel (VAAPI)

**Issue:** "vaapi not initialized"
```bash
# Install VAAPI
sudo apt install intel-media-va-driver vainfo

# Check VAAPI
vainfo
```

## Debug Output

### Enable GStreamer Debug

```bash
# Level 1-5 (1=error only, 5=verbose)
GST_DEBUG=3 gst-launch-1.0 ...

# Specific element debug
GST_DEBUG=rtspsrc:5 gst-launch-1.0 rtspsrc ...

# All debug to file
GST_DEBUG=4 GST_DEBUG_FILE=gst.log gst-launch-1.0 ...
```

### Debug in Python

```python
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)
Gst.debug_set_active(True)
Gst.debug_set_default_threshold(3)
```

## Performance Issues

### Low FPS

1. **Check encoder speed:**
```gstreamer
x264enc speed-preset=ultrafast  # Fastest
```

2. **Use hardware acceleration:**
```gstreamer
# Jetson
nvv4l2h264enc preset-level=1

# Intel
vaapih264enc
```

3. **Reduce resolution:**
```gstreamer
videoscale ! video/x-raw,width=640,height=480
```

### High Latency

1. **Minimize buffering:**
```gstreamer
appsink drop=true max-buffers=1 sync=false
rtspsrc latency=0 drop-on-latency=true
```

2. **Use zerolatency tune:**
```gstreamer
x264enc tune=zerolatency
```

3. **Disable RTCP:**
```gstreamer
rtspsrc do-rtcp=false
```

### High CPU Usage

1. **Use hardware decode/encode:**
```gstreamer
# Decode
nvv4l2decoder  # Jetson
vaapih264dec   # Intel

# Encode
nvv4l2h264enc  # Jetson
vaapih264enc   # Intel
```

2. **Reduce resolution before processing:**
```gstreamer
decodebin ! videoscale ! video/x-raw,width=640,height=480 ! videoconvert
```

## Getting Help

### Collect Debug Info

```bash
# System info
uname -a
lsb_release -a

# GStreamer version
gst-launch-1.0 --version

# Available plugins
gst-inspect-1.0 --version
gst-inspect-1.0 | wc -l

# Camera devices
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-formats-ext
```

### Minimal Reproducible Example

Test pipeline outside Python first:
```bash
gst-launch-1.0 -v videotestsrc num-buffers=100 ! videoconvert ! x264enc ! fakesink
```
