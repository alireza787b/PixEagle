# GStreamer Pipeline Reference

> Complete element and property reference for PixEagle

## Source Elements

### v4l2src

Video4Linux2 camera source for USB cameras.

```
v4l2src device=/dev/video0
  ! video/x-raw,format=YUY2,width=640,height=480,framerate=30/1
```

| Property | Description |
|----------|-------------|
| `device` | Device path (e.g., `/dev/video0`) |
| `io-mode` | I/O mode (mmap, userptr, dmabuf) |

### rtspsrc

RTSP network source for IP cameras.

```
rtspsrc location=rtsp://host:554/stream latency=200 protocols=tcp
```

| Property | Description |
|----------|-------------|
| `location` | RTSP URL |
| `latency` | Buffer latency in ms (default: 200) |
| `protocols` | tcp, udp, or both |
| `drop-on-latency` | Drop frames when late |
| `do-rtcp` | Enable RTCP (default: true) |

### udpsrc

UDP network source for MAVLink video.

```
udpsrc uri=udp://0.0.0.0:5600 caps="application/x-rtp"
```

| Property | Description |
|----------|-------------|
| `uri` | UDP address (udp://host:port) |
| `port` | UDP port |
| `caps` | Expected stream format |

### filesrc

File source for video files.

```
filesrc location=/path/to/video.mp4
```

| Property | Description |
|----------|-------------|
| `location` | File path |

### nvarguscamerasrc

NVIDIA Jetson CSI camera source.

```
nvarguscamerasrc sensor-id=0
  ! video/x-raw(memory:NVMM),width=1920,height=1080,framerate=30/1
```

| Property | Description |
|----------|-------------|
| `sensor-id` | Camera index (0 or 1) |
| `wbmode` | White balance mode (0-9) |
| `exposuretimerange` | Exposure time range |

### libcamerasrc

Raspberry Pi camera source.

```
libcamerasrc ! video/x-raw,width=640,height=480,framerate=30/1
```

### souphttpsrc

HTTP/HTTPS source for web streams.

```
souphttpsrc location=http://camera:8080/stream
```

| Property | Description |
|----------|-------------|
| `location` | HTTP(S) URL |
| `is-live` | Treat as live source |

## Processing Elements

### decodebin

Automatic decoder selection.

```
rtspsrc ! decodebin ! videoconvert
```

Automatically selects appropriate decoder based on stream format.

### jpegdec

MJPEG decoder.

```
v4l2src ! image/jpeg ! jpegdec ! videoconvert
```

### avdec_h264

Software H.264 decoder.

```
rtph264depay ! h264parse ! avdec_h264 ! videoconvert
```

### videoconvert

Color space conversion.

```
decodebin ! videoconvert ! video/x-raw,format=BGR
```

Converts between color formats (YUV, RGB, BGR, etc.).

### videoscale

Resolution scaling.

```
videoconvert ! videoscale method=0 ! video/x-raw,width=640,height=480
```

| Property | Description |
|----------|-------------|
| `method` | 0=nearest, 1=bilinear, 4=lanczos |

### nvvidconv

NVIDIA hardware video converter (Jetson).

```
nvarguscamerasrc ! video/x-raw(memory:NVMM) ! nvvidconv ! video/x-raw,format=BGRx
```

### x264enc

H.264 software encoder.

```
videoconvert ! x264enc tune=zerolatency bitrate=2000 speed-preset=ultrafast
```

| Property | Description |
|----------|-------------|
| `tune` | Encoding tune (zerolatency for streaming) |
| `bitrate` | Target bitrate in kbps |
| `speed-preset` | ultrafast to veryslow |
| `key-int-max` | Keyframe interval |

### rtph264pay

RTP H.264 payloader.

```
x264enc ! rtph264pay config-interval=1 pt=96
```

| Property | Description |
|----------|-------------|
| `config-interval` | SPS/PPS interval |
| `pt` | Payload type (usually 96) |

### rtph264depay

RTP H.264 depayloader.

```
udpsrc ! application/x-rtp ! rtph264depay ! h264parse
```

### h264parse

H.264 stream parser.

```
rtph264depay ! h264parse ! avdec_h264
```

## Sink Elements

### appsink

Application sink (to OpenCV).

```
videoconvert ! video/x-raw,format=BGR ! appsink drop=true max-buffers=1 sync=false
```

| Property | Description |
|----------|-------------|
| `drop` | Drop old buffers (true for real-time) |
| `max-buffers` | Maximum buffer count |
| `sync` | Sync to clock (false for low latency) |
| `emit-signals` | Enable new-sample signal |

### appsrc

Application source (from OpenCV).

```
appsrc ! videoconvert ! x264enc
```

| Property | Description |
|----------|-------------|
| `caps` | Source capabilities |
| `format` | time or buffers |
| `is-live` | Treat as live source |

### udpsink

UDP network sink.

```
rtph264pay ! udpsink host=192.168.1.10 port=5600
```

| Property | Description |
|----------|-------------|
| `host` | Destination IP address |
| `port` | Destination UDP port |
| `sync` | Sync to clock |

### autovideosink

Automatic video display (for testing).

```
decodebin ! videoconvert ! autovideosink
```

### fakesink

Null sink (discard frames).

```
decodebin ! fakesink
```

## Caps Reference

### Raw Video

```
video/x-raw,format=BGR,width=640,height=480,framerate=30/1
```

Common formats: `BGR`, `RGB`, `YUY2`, `NV12`, `I420`

### NVMM Memory (Jetson)

```
video/x-raw(memory:NVMM),width=1920,height=1080,framerate=30/1
```

### RTP H.264

```
application/x-rtp,media=video,encoding-name=H264,payload=96
```

### JPEG

```
image/jpeg,width=640,height=480,framerate=30/1
```

## Pipeline Syntax

### Element Connection

```
element1 ! element2 ! element3
```

### Properties

```
element property1=value1 property2=value2
```

### Named Elements

```
rtspsrc name=src ! decodebin ! autovideosink
```

### Caps Filter

```
element ! caps ! element
```

### Tee (Split)

```
tee name=t ! queue ! sink1  t. ! queue ! sink2
```
