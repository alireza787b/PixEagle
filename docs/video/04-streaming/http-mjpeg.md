# HTTP MJPEG Streaming

> Motion JPEG over HTTP for universal compatibility

## Overview

HTTP MJPEG streaming provides a simple video feed accessible from any browser or HTTP client. Each frame is encoded as JPEG and sent as a multipart HTTP response.

## Endpoint

```
GET /video_feed
```

The MJPEG endpoint shares the PixEagle API exposure and authorization boundary.
With checked-in defaults it is available to same-host loopback clients such as
the dashboard, local tools, or QGroundControl running on the same computer. A
non-loopback client needs an explicit non-local exposure profile plus scoped
credentials with `media:read`; query-string tokens are rejected.

Use `GET /api/v1/streams/media-health` for typed MJPEG transport and
frame-publisher observability. It reports local backend state only and does not
prove a remote client received usable video. When `Streaming.ENABLE_STREAMING`
is false or `HTTP_MAX_CONNECTIONS` is zero, the media-health route reports MJPEG
as disabled and `/video_feed` fails closed.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| none | - | - | Stream output is controlled by the `Streaming` config section. Query-string credentials are rejected. |

### Examples

```html
<!-- Basic video feed -->
<img src="http://127.0.0.1:5077/video_feed" />

<!-- Quality/OSD selection is configured server-side in configs/config_default.yaml or local overrides. -->
```

## Configuration

```yaml
Streaming:
  ENABLE_STREAMING: true
  HTTP_STREAM_HOST: 127.0.0.1
  HTTP_STREAM_PORT: 5077
  STREAM_QUALITY: 80      # Default JPEG quality
  STREAM_WIDTH: 640       # Output width
  STREAM_HEIGHT: 480      # Output height
```

## Implementation

### FastAPI Handler

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

async def generate_frames():
    while True:
        # Get the configured stream frame. OSD, dimensions, quality, and
        # adaptive behavior are server-side Streaming configuration, not
        # per-request query parameters.
        frame = frame_publisher.get_latest(
            prefer_osd=Parameters.STREAM_PROCESSED_OSD
        )

        if frame is not None:
            # Encode as JPEG
            _, buffer = cv2.imencode(
                '.jpg',
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, Parameters.STREAM_QUALITY]
            )

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                buffer.tobytes() +
                b'\r\n'
            )

        await asyncio.sleep(1 / Parameters.STREAM_FPS)
```

## Protocol Details

### Response Format

```http
HTTP/1.1 200 OK
Content-Type: multipart/x-mixed-replace; boundary=frame

--frame
Content-Type: image/jpeg

<JPEG binary data>
--frame
Content-Type: image/jpeg

<JPEG binary data>
...
```

### Frame Rate Control

The server controls frame rate through sleep intervals:

```python
await asyncio.sleep(1 / Parameters.STREAM_FPS)
```

## Client Integration

### QGroundControl

The draft/test repaired QGroundControl HTTP-MJPEG PR can consume PixEagle's
multipart stream when QGC runs on the same host as PixEagle and uses:

```text
http://127.0.0.1:5077/video_feed
```

For the simplest aircraft/companion-to-ground-station deployment, prefer
PixEagle's GStreamer H.264/RTP/UDP output. For guarded direct HTTPS MJPEG, run:

```bash
make qgc-direct-media-profile PUBLIC_HOST=pixeagle.example
```

Then configure the generated HTTPS URL and session bearer token in a draft/test
QGC build containing PR #13594. PixEagle remains loopback behind the required
proxy; unauthenticated LAN backend access is not supported. PR #13594 must
leave draft and QGC CI plus target playback evidence must pass before handoff.
See [Remote Media Security](remote-media-security.md).

### HTML/JavaScript

```html
<!DOCTYPE html>
<html>
<head>
    <title>PixEagle Stream</title>
</head>
<body>
    <img id="stream" src="http://127.0.0.1:5077/video_feed" />

    <script>
        // Handle connection errors
        document.getElementById('stream').onerror = function() {
            setTimeout(() => {
                this.src = this.src + '?' + Date.now();
            }, 1000);
        };
    </script>
</body>
</html>
```

### Python (OpenCV)

```python
import cv2

cap = cv2.VideoCapture('http://127.0.0.1:5077/video_feed')

while True:
    ret, frame = cap.read()
    if ret:
        cv2.imshow('Stream', frame)
    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
```

### Python (requests)

```python
import requests
import cv2
import numpy as np

response = requests.get(
    'http://127.0.0.1:5077/video_feed',
    stream=True
)

buffer = b''
for chunk in response.iter_content(chunk_size=1024):
    buffer += chunk

    # Find JPEG markers
    start = buffer.find(b'\xff\xd8')
    end = buffer.find(b'\xff\xd9')

    if start != -1 and end != -1:
        jpg = buffer[start:end+2]
        buffer = buffer[end+2:]

        # Decode and display
        frame = cv2.imdecode(
            np.frombuffer(jpg, dtype=np.uint8),
            cv2.IMREAD_COLOR
        )
        cv2.imshow('Stream', frame)
        cv2.waitKey(1)
```

### cURL

```bash
# Save frames to files
curl -N http://127.0.0.1:5077/video_feed | \
  csplit -z -f frame_ - '/--frame/' '{*}'
```

## Performance

### Quality vs Bandwidth

| Quality | Bandwidth (640x480) | Visual Quality |
|---------|---------------------|----------------|
| 95 | ~3.5 Mbps | Excellent |
| 80 | ~2.0 Mbps | Good |
| 60 | ~1.2 Mbps | Acceptable |
| 40 | ~0.8 Mbps | Low |

### Optimization Tips

1. **Resize before encoding:**
```python
small_frame = cv2.resize(frame, (320, 240))
```

2. **Use appropriate quality:**
```python
# Dashboard: 60-70
# Analysis: 80-90
# Recording: 95
```

3. **Cache encoded frames:**
```python
# Don't re-encode for multiple clients
if frame_changed:
    cached_jpeg = cv2.imencode('.jpg', frame, params)[1]
```

## Troubleshooting

### Black/No Image

1. Check video handler is capturing:
```python
assert video_handler.current_raw_frame is not None
```

2. Verify endpoint is accessible:
```bash
curl -I http://127.0.0.1:5077/video_feed
```

### Choppy Video

1. Lower `Streaming.STREAM_QUALITY`
2. Reduce `Streaming.STREAM_WIDTH` and `Streaming.STREAM_HEIGHT`
3. Enable or tune server-side adaptive quality

### High Latency

1. Reduce JPEG quality
2. Resize to smaller resolution
3. Check network bandwidth

### Connection Drops

1. Check server logs for errors
2. Verify video source is stable
3. Test with `curl` to isolate browser issues
