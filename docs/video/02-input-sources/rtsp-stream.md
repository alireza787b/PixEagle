# RTSP Stream Source

> Network camera streaming via Real-Time Streaming Protocol

## Overview

RTSP (Real-Time Streaming Protocol) is the primary source for IP cameras and drone video feeds. PixEagle provides robust RTSP handling with multiple fallback pipelines and automatic recovery.

## Configuration

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: RTSP_STREAM
  RTSP_URL: rtsp://192.168.0.108:554/stream=0
  RTSP_PROTOCOL: tcp      # tcp or udp
  RTSP_LATENCY: 200       # Buffer time in ms
  USE_GSTREAMER: true     # Required for RTSP

  # Recovery settings
  RTSP_MAX_CONSECUTIVE_FAILURES: 10
  RTSP_CONNECTION_TIMEOUT: 5.0
  RTSP_MAX_RECOVERY_ATTEMPTS: 3
  RTSP_FRAME_CACHE_SIZE: 5
```

## Protocol Selection

| Protocol | Pros | Cons | Use When |
|----------|------|------|----------|
| `tcp` | Reliable, no packet loss | Higher latency | Default, unstable networks |
| `udp` | Lower latency | May lose packets | Stable local network |

```yaml
RTSP_PROTOCOL: tcp  # Recommended for drone operations
```

## Latency Tuning

```yaml
RTSP_LATENCY: 200  # Default - balanced

# Tuning guide:
# 0-100ms   - Minimum latency, may cause decode errors
# 100-200ms - Low latency, recommended for tracking
# 200-500ms - Balanced, good for unstable connections
# 500ms+    - High stability, for poor networks
```

## GStreamer Pipeline

### Primary Pipeline (Ultra-Low Latency)

```
rtspsrc location={url} protocols={protocol} latency={latency}
  buffer-mode=auto drop-on-latency=true do-rtcp=false
  ! decodebin
  ! videoconvert
  ! videoscale method=0
  ! video/x-raw,format=BGR,width={width},height={height}
  ! appsink drop=true max-buffers=1 sync=false async=false
```

**Key Optimizations:**
- `drop-on-latency=true` - Drop late frames
- `do-rtcp=false` - Disable RTCP overhead
- `max-buffers=1` - Minimal buffering
- `sync=false` - No clock synchronization
- `videoscale method=0` - Nearest neighbor (fastest)

### Fallback Pipelines

PixEagle automatically tries 4 fallback pipelines if primary fails:

| Fallback | Changes | Use Case |
|----------|---------|----------|
| 1 | Add queue, simplified | Connection issues |
| 2 | +300ms latency, larger buffer | Unstable network |
| 3 | Auto protocol detection | Protocol mismatch |
| 4 | No scaling (warning) | Last resort |

```python
# Fallback selection is automatic
# Check logs for which pipeline succeeded:
# "RTSP connected with pipeline 2/5"
```

## Common RTSP URLs

### DJI Drones

```yaml
# DJI Phantom/Mavic (via RTSP adapter)
RTSP_URL: rtsp://192.168.1.1:554/live

# DJI with Mobile SDK
RTSP_URL: rtsp://localhost:8554/fpv
```

### IP Cameras

```yaml
# Hikvision
RTSP_URL: rtsp://admin:password@192.168.1.64:554/Streaming/Channels/101

# Dahua
RTSP_URL: rtsp://admin:password@192.168.1.108:554/cam/realmonitor?channel=1&subtype=0

# Generic ONVIF
RTSP_URL: rtsp://192.168.1.100:554/onvif1
```

### PixEagle Companion

```yaml
# Raspberry Pi companion computer
RTSP_URL: rtsp://companion.local:8554/camera
```

## Troubleshooting

### "Invalid input packet" Errors

**Cause:** UDP packet loss or corruption

**Solution:**
```yaml
RTSP_PROTOCOL: tcp  # Switch from udp
```

### High Latency

**Solutions:**
1. Reduce buffer time:
   ```yaml
   RTSP_LATENCY: 100
   ```

2. Use UDP if network is stable:
   ```yaml
   RTSP_PROTOCOL: udp
   ```

3. Check source encoding settings (reduce bitrate)

### Connection Drops

**Solutions:**
1. Increase failure threshold:
   ```yaml
   RTSP_MAX_CONSECUTIVE_FAILURES: 20
   RTSP_CONNECTION_TIMEOUT: 10.0
   ```

2. Check network stability
3. Verify RTSP server capacity

### "Could not open resource"

**Causes:**
- Wrong URL
- Authentication required
- Firewall blocking

**Solutions:**
1. Test URL with VLC: `vlc rtsp://...`
2. Add credentials to URL: `rtsp://user:pass@host/stream`
3. Check firewall for port 554

### Resolution Mismatch

**Cause:** Source resolution differs from config

**Solution:** Pipeline automatically scales, but check logs:
```
WARNING: Video dimensions (1920x1080) differ from configured (640x480)
```

This is normal - pipeline handles scaling.

## Best Practices

### 1. Always Use TCP First

```yaml
RTSP_PROTOCOL: tcp
```

Only switch to UDP after confirming stability.

### 2. Match Resolution to Needs

```yaml
# For tracking (speed priority)
CAPTURE_WIDTH: 640
CAPTURE_HEIGHT: 480

# For recording (quality priority)
CAPTURE_WIDTH: 1280
CAPTURE_HEIGHT: 720
```

### 3. Monitor Connection Health

```python
health = video_handler.get_connection_health()
if health['status'] != 'healthy':
    logger.warning(f"RTSP degraded: {health}")
```

### 4. Test Before Flight

```bash
# Test RTSP stream
gst-launch-1.0 rtspsrc location=rtsp://... ! decodebin ! autovideosink
```

## Advanced Configuration

### Custom Pipeline Override

For complete control, use CUSTOM_GSTREAMER:

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: CUSTOM_GSTREAMER
  CUSTOM_PIPELINE: >
    rtspsrc location=rtsp://192.168.1.1:554/stream
    protocols=tcp latency=100 buffer-mode=slave
    ! rtph264depay ! h264parse ! avdec_h264
    ! videoconvert ! video/x-raw,format=BGR
    ! appsink drop=true sync=false
```

### Multiple RTSP Sources

Currently single-source, but can switch at runtime:

```python
# In application code
Parameters.RTSP_URL = "rtsp://new-source:554/stream"
video_handler.reconnect()
```
