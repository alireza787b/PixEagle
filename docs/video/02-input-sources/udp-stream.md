# UDP Stream Source

> Low-latency RTP/UDP video streaming

## Overview

UDP streaming provides the lowest latency for video transport, ideal for real-time applications where some packet loss is acceptable. Commonly used with companion computers and direct video links.

## Configuration

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: UDP_STREAM
  UDP_URL: udp://0.0.0.0:5600
  CAPTURE_WIDTH: 640
  CAPTURE_HEIGHT: 480
  USE_GSTREAMER: true  # Required for UDP
```

## GStreamer Pipeline

```
udpsrc uri=udp://0.0.0.0:5600
  ! application/x-rtp
  ! rtph264depay
  ! avdec_h264
  ! videoconvert
  ! video/x-raw,format=BGR
  ! videoscale
  ! video/x-raw,width=640,height=480
  ! appsink drop=true sync=false
```

**Key Elements:**
- `udpsrc` - UDP source receiver
- `rtph264depay` - Extract H.264 from RTP packets
- `avdec_h264` - FFmpeg H.264 decoder

## Common UDP Ports

| Source | Default Port | Notes |
|--------|--------------|-------|
| MAVLink Video | 5600 | Standard for companion |
| QGroundControl | 5600 | QGC default |
| Custom | Any | Choose above 1024 |

## URL Format

```yaml
# Listen on all interfaces
UDP_URL: udp://0.0.0.0:5600

# Specific interface
UDP_URL: udp://192.168.1.100:5600

# Multicast
UDP_URL: udp://239.0.0.1:5600
```

## Sending Video to PixEagle

### From GStreamer

```bash
gst-launch-1.0 videotestsrc \
  ! x264enc tune=zerolatency \
  ! rtph264pay \
  ! udpsink host=192.168.1.100 port=5600
```

### From FFmpeg

```bash
ffmpeg -i input.mp4 \
  -c:v libx264 -tune zerolatency -preset ultrafast \
  -f rtp rtp://192.168.1.100:5600
```

### From Raspberry Pi Camera

```bash
libcamera-vid -t 0 --inline --nopreview \
  -o - | gst-launch-1.0 fdsrc \
  ! h264parse ! rtph264pay ! udpsink host=192.168.1.100 port=5600
```

## Troubleshooting

### No Video Received

**Solutions:**
1. Check firewall: `sudo ufw allow 5600/udp`
2. Verify sender is transmitting: `sudo tcpdump -i any port 5600`
3. Check network connectivity

### High Packet Loss

**Solutions:**
1. Reduce bitrate at source
2. Use wired connection if possible
3. Check for network congestion

### Decoder Errors

**Cause:** Missing keyframes

**Solution:** Increase keyframe frequency at source:
```bash
# FFmpeg
-g 15  # Keyframe every 15 frames

# GStreamer
key-int-max=15
```

## Latency Optimization

```yaml
# Minimal buffering
VideoSource:
  UDP_URL: udp://0.0.0.0:5600?buffer-size=0
```

Or in custom pipeline:
```
udpsrc port=5600 buffer-size=0 ! ...
```

## Example: MAVLink Camera Manager

```yaml
VideoSource:
  VIDEO_SOURCE_TYPE: UDP_STREAM
  UDP_URL: udp://0.0.0.0:5600
  USE_GSTREAMER: true
```

Companion computer sends to port 5600.
