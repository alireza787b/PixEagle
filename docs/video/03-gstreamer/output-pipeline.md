# GStreamer Output Pipeline

> H.264 UDP streaming to ground control stations

## Overview

PixEagle uses GStreamer to stream video to QGroundControl and other ground stations via H.264 over UDP/RTP.
This is the maintained field path for companion-to-GCS QGroundControl video and
does not require opening PixEagle's backend HTTP/WebSocket media endpoints.
See [Remote Media Security](../04-streaming/remote-media-security.md) for the
remote HTTP/WebSocket policy.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Output Pipeline                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  VideoHandler    GStreamer Pipeline      Network                │
│  ───────────     ─────────────────       ───────                │
│                                                                  │
│  ┌─────────┐    ┌────────────────────────────────────┐         │
│  │ Frame   │───▶│ appsrc ! videoconvert ! x264enc    │         │
│  │ BGR     │    │        ! rtph264pay ! udpsink      │───▶ UDP │
│  └─────────┘    └────────────────────────────────────┘         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

```yaml
GStreamer:
  ENABLE_GSTREAMER_STREAM: true       # Enable QGC/GCS output
  GSTREAMER_HOST: 192.168.1.10        # GCS IP address
  GSTREAMER_PORT: 5600                # QGC video port
  GSTREAMER_BITRATE: 2000             # kbps
  ENABLE_HARDWARE_ENCODING: true      # Try NVIDIA/VAAPI before software fallback
```

## Output Pipeline

### Software Encoding (x264)

```gstreamer
appsrc name=source
    caps="video/x-raw,format=BGR,width=640,height=480,framerate=30/1"
    is-live=true
    format=time
  ! videoconvert
  ! video/x-raw,format=I420
  ! x264enc
      tune=zerolatency
      bitrate=2000
      speed-preset=ultrafast
      key-int-max=30
  ! rtph264pay config-interval=1 pt=96
  ! udpsink host=192.168.1.10 port=5600 sync=false
```

### NVIDIA Hardware Encoding (Jetson)

```gstreamer
appsrc name=source
    caps="video/x-raw,format=BGR,width=640,height=480,framerate=30/1"
    is-live=true
  ! videoconvert
  ! video/x-raw,format=I420
  ! nvvidconv
  ! video/x-raw(memory:NVMM),format=I420
  ! nvv4l2h264enc
      bitrate=2000000
      preset-level=1
      maxperf-enable=true
      insert-sps-pps=true
  ! h264parse
  ! rtph264pay config-interval=1 pt=96
  ! udpsink host=192.168.1.10 port=5600 sync=false
```

### VAAPI Hardware Encoding (Intel)

```gstreamer
appsrc name=source
  ! videoconvert
  ! vaapih264enc
      rate-control=cbr
      bitrate=2000
  ! rtph264pay config-interval=1 pt=96
  ! udpsink host=192.168.1.10 port=5600 sync=false
```

## GStreamerHandler Class

The `GStreamerHandler` class (`src/classes/gstreamer_handler.py`) manages the output pipeline:

```python
from classes.gstreamer_handler import GStreamerHandler

# Initialize
gst_handler = GStreamerHandler()
gst_handler.initialize_stream()

# Stream frames
while running:
    frame = video_handler.get_frame()
    gst_handler.stream_frame(frame)

# Cleanup
gst_handler.release()
```

`AppController.shutdown()` releases the GStreamer handler when it exists, and
`GStreamerHandler.release()` stops the writer thread, releases the OpenCV
`VideoWriter`, clears the writer reference, and drains queued frames. Runtime
API toggles and media-health status treat the stream as active only when the
underlying writer exists and reports `isOpened()`.

## Encoder Settings

### x264enc Presets

| Preset | Speed | Quality | CPU Usage |
|--------|-------|---------|-----------|
| ultrafast | Fastest | Low | Minimal |
| superfast | Very fast | Low-Med | Low |
| veryfast | Fast | Medium | Medium |
| faster | Moderate | Med-High | Higher |

For real-time streaming, use `ultrafast` or `superfast`.

### Tuning Options

| Tune | Use Case |
|------|----------|
| `zerolatency` | Live streaming (required for real-time) |
| `fastdecode` | Low-power decoders |
| `stillimage` | Slideshow content |

### Bitrate Guidelines

| Resolution | Bitrate (kbps) | Quality |
|------------|----------------|---------|
| 640x480 | 1000-2000 | Good |
| 1280x720 | 2000-4000 | Good |
| 1920x1080 | 4000-8000 | Good |

## QGroundControl Setup

### Receiving Video

1. Open QGroundControl
2. Go to **Application Settings** > **Video**
3. Set **Video Source**: UDP h.264 Video Stream
4. Set **UDP Port**: 5600 (or your configured port)

### SDP File (Optional)

For some players, create an SDP file:

```sdp
v=0
o=- 0 0 IN IP4 127.0.0.1
s=PixEagle Stream
c=IN IP4 0.0.0.0
t=0 0
m=video 5600 RTP/AVP 96
a=rtpmap:96 H264/90000
```

## Network Considerations

### Multicast

Stream to multiple receivers:

```yaml
GStreamer:
  GSTREAMER_HOST: 239.255.0.1  # Multicast address
  GSTREAMER_PORT: 5600
```

Pipeline:
```gstreamer
... ! udpsink host=239.255.0.1 port=5600 auto-multicast=true
```

### Port Selection

| Port | Use |
|------|-----|
| 5600 | QGroundControl default |
| 5601 | Secondary stream |
| 14550 | MAVLink (avoid) |

## Troubleshooting

### No Video in QGC

1. Check network connectivity: `ping <dest_host>`
2. Verify port is not blocked: `nc -vuz <dest_host> 5600`
3. Check GStreamer logs: Set `GST_DEBUG=3`

### High Latency

- Lower bitrate
- Use `tune=zerolatency`
- Use `speed-preset=ultrafast`
- Reduce resolution

### Choppy Video

- Increase bitrate
- Check network bandwidth
- Reduce frame rate

### Encoder Not Found

Install GStreamer plugins:
```bash
# x264enc
sudo apt install gstreamer1.0-plugins-ugly

# Hardware encoders
sudo apt install gstreamer1.0-vaapi      # Intel VAAPI
# NVIDIA: Install JetPack SDK
```

## Performance Monitoring

### Check Pipeline Performance

```python
# In GStreamerHandler
def get_stats(self):
    return {
        'frames_written': self.frame_count,
        'fps': self.current_fps,
        'bitrate': self.current_bitrate,
        'dropped_frames': self.dropped_count
    }
```

### GStreamer Debug Output

```bash
GST_DEBUG=3 python src/main.py
```
