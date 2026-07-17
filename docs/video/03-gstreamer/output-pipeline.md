# GStreamer Output Pipeline

> H.264 UDP streaming to ground control stations

## Overview

PixEagle uses GStreamer to stream video to QGroundControl and other ground stations via H.264 over UDP/RTP.
This is the maintained field path for companion-to-GCS QGroundControl video and
does not require opening PixEagle's backend HTTP/WebSocket media endpoints.
It remains first-class after the generic QGC HTTP MJPEG/WebSocket JPEG work;
those additions are alternative receiver sources, not a replacement for UDP.
See [Remote Media Security](../04-streaming/remote-media-security.md) for the
remote HTTP/WebSocket policy.

This implementation currently uses `cv2.VideoWriter(..., cv2.CAP_GSTREAMER)`.
The active PixEagle OpenCV build must therefore report `GStreamer: YES`, and
the selected encoder plus `rtph264pay` and `udpsink` plugins must be installed.
If that prerequisite is absent or the pipeline cannot open, PixEagle keeps the
tracking/dashboard runtime online but reports the UDP output inactive; it does
not silently expose an unauthenticated HTTP/WS stream.

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
  GSTREAMER_INCLUDE_OSD: true         # Explicitly include PixEagle OSD
  ENABLE_HARDWARE_ENCODING: true      # Try NVIDIA/VAAPI before software fallback
```

## Output Pipeline

### Software Encoding (x264)

```gstreamer
appsrc
  ! video/x-raw,format=BGR,width=1280,height=720,framerate=15/1
  ! videoconvert
  ! x264enc
      tune=zerolatency
      bitrate=2000
      speed-preset=ultrafast
      key-int-max=30
  ! rtph264pay config-interval=1 pt=96
  ! udpsink host="192.168.1.10" port=5600 buffer-size=50000000
```

This is the pipeline PixEagle currently constructs. OpenCV 4.13 sets the
`appsrc` stream type, time format, frame timestamps, and blocking behavior in
its `CAP_GSTREAMER` writer backend. PixEagle therefore isolates
`VideoWriter.write()` on a bounded background queue instead of claiming that
the OpenCV call itself is non-blocking. Submission is rate-limited to the
configured output cadence. Raw output is normalized in the writer thread after
the queue has coalesced stale frames. OSD output is first aspect-normalized onto
the exact GStreamer canvas and then composed at that output resolution on the
application frame thread using a GStreamer-output-specific OSD pipeline; the
prepared frame is detached from the capture buffer and queued without a second
resize. This avoids reusing or mutating a browser/capture frame and prevents
browser and GCS resolutions from repeatedly invalidating one shared OSD cache.
The pipelines share the renderer's live telemetry/config state, but every
compose first synchronizes its own frame dimensions before cached sprites or
direct geometry are used.

### Jetson Hardware Pipeline Reference

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

This is the NVIDIA-supported Jetson pipeline shape, but the current automatic
PixEagle encoder selector does not yet select `nvv4l2h264enc`. Until target
hardware validation closes that gap, Jetson uses the tested-open encoder chosen
by the runtime or falls back to `x264enc`. Do not infer Jetson hardware-encoder
success from plugin presence alone.

Raspberry Pi `v4l2h264enc` is likewise not auto-selected. It remains a tracked
target-hardware validation item rather than an unverified pipeline assembled
from plugin presence. The current supported automatic hardware paths are
`nvh264enc` and `vaapih264enc`, each with runtime fallback to `x264enc`.

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
`GStreamerHandler.release()` serializes lifecycle operations, stops the writer
thread, drains queued frames, and finalizes the OpenCV `VideoWriter` through a
bounded cleanup thread. OpenCV's GStreamer writer waits without a built-in
timeout for EOS, so a stalled writer fails closed with
`writer_thread_stop_timeout`, `pipeline_release_timeout`, or
`pipeline_release_failed:*`. PixEagle retains ownership of that retiring writer
until cleanup succeeds and refuses to publish a replacement generation in the
meantime. Runtime API toggles and media-health status report active only while
the writer is open, its writer thread is alive, and its stop event is not set;
`cleanup_pending` distinguishes inactive output from incomplete resource
cleanup. Media health exposes `cleanup_pending` and `last_error` as typed
transport fields instead of burying them in untyped transport details.

Destination host, port, bitrate, dimensions, frame rate, buffer size, x264
preset/tune, and keyframe interval are snapshotted and validated before parsing
the pipeline. Hosts must be plain IP/DNS values, not URLs or `host:port`
strings, and H.264 width/height must be even. Invalid settings leave the output
inactive with `invalid_gstreamer_configuration`; they do not alter browser
streaming. Width is bounded to `3840`, height to `2160`, frame rate to `60`,
and the combined pixel-rate budget permits up to `1920x1080@60` or
`3840x2160@15`.

`GSTREAMER_INCLUDE_OSD` owns the QGC/GCS overlay decision. It is intentionally
separate from `Streaming.STREAM_PROCESSED_OSD`, which controls browser JPEG
output. When enabled, PixEagle aspect-normalizes the raw source to
`GSTREAMER_WIDTH` x `GSTREAMER_HEIGHT` with black letterbox/pillarbox bars, then
composes an output-specific OSD. It does not reuse a browser frame whose aspect
ratio may already have been stretched, and it uses an independent OSD cache for
the configured GCS output resolution.

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
| `zerolatency` | Recommended for low-latency live streaming |
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

### Multiple Receivers

The supported setup profile configures one destination host. Multicast and
fan-out require network/interface/TTL and receiver validation and are not
claimed by the current profile. Use a reviewed external relay or add a tested
output provider rather than assuming that changing the host to a multicast
address is sufficient.

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

`GET /api/v1/streams/media-health` exposes the actual process-local output
state, selected encoder, queue depth/drops, queued/written/resized/letterboxed
frame counts, rate-limited submissions, OpenCV GStreamer capability, and the
last output error. UDP has no receiver handshake, so an active local pipeline
does not prove that QGC received video.

### GStreamer Debug Output

```bash
GST_DEBUG=3 python src/main.py
```
