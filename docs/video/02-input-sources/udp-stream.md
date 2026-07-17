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
  caps="application/x-rtp,media=video,encoding-name=H264,payload=96,clock-rate=90000"
  ! rtph264depay
  ! h264parse
  ! avdec_h264
  ! videoconvert
  ! video/x-raw,format=BGR
  ! videoscale
  ! video/x-raw,width=640,height=480
  ! appsink drop=true max-buffers=1 sync=false
```

**Key Elements:**
- `udpsrc` - UDP source receiver
- RTP caps - declares H.264 video payload 96 explicitly
- `rtph264depay` - Extract H.264 from RTP packets
- `h264parse` - Normalize the H.264 bitstream before decode
- `avdec_h264` - FFmpeg H.264 decoder
- `appsink drop=true max-buffers=1 sync=false` - Keep latency bounded

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
  ! video/x-raw,width=640,height=480,framerate=30/1 \
  ! videoconvert \
  ! x264enc tune=zerolatency speed-preset=ultrafast key-int-max=30 bitrate=800 \
  ! rtph264pay config-interval=1 pt=96 \
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

### Generated Receiver Proof

Use the checked-in proof before accepting Gazebo or camera-stream evidence:

```bash
make video-udp-proof-dry-run
make video-udp-proof-execute
```

The execute target starts only a local generated RTP/H.264 sender and records
receiver artifacts under `reports/video/`. It does not start PX4, Gazebo,
MAVLink2REST, MavlinkAnywhere, services, HIL, or real aircraft endpoints.

### Sender Loss Behavior

OpenCV's GStreamer backend can block on UDP reads after the sender stops. The
PixEagle `UDP_STREAM` + `USE_GSTREAMER=true` path therefore uses an asynchronous
reader so the main frame/control loop can keep returning the latest cached frame
as `usable_for_following=false` when no fresh frame arrives.

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
