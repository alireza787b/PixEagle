# HTTP MJPEG Streaming

> Motion JPEG over HTTP for universal compatibility

## Overview

HTTP MJPEG streaming provides a simple video feed accessible from any browser or HTTP client. Each frame is encoded as JPEG and sent as a multipart HTTP response.

## Endpoint

```
GET /video_feed
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `osd` | bool | false | Include OSD overlay |
| `resize` | bool | false | Use resized frame |
| `quality` | int | 80 | JPEG quality (1-100) |

### Examples

```html
<!-- Basic video feed -->
<img src="http://localhost:8000/video_feed" />

<!-- With OSD overlay -->
<img src="http://localhost:8000/video_feed?osd=true" />

<!-- Lower quality for bandwidth -->
<img src="http://localhost:8000/video_feed?quality=60" />
```

## Configuration

```yaml
FastAPI:
  ENABLE_HTTP_STREAM: true
  STREAM_QUALITY: 80      # Default JPEG quality
  STREAM_WIDTH: 640       # Resize width (if resize=true)
  STREAM_HEIGHT: 480      # Resize height (if resize=true)
  MJPEG_BOUNDARY: "frame" # Multipart boundary string
```

## Implementation

### FastAPI Handler

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.get("/video_feed")
async def video_feed(osd: bool = False, quality: int = 80):
    return StreamingResponse(
        generate_frames(osd=osd, quality=quality),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

async def generate_frames(osd: bool = False, quality: int = 80):
    while True:
        # Get frame from video handler
        if osd:
            frame = video_handler.current_osd_frame
        else:
            frame = video_handler.current_raw_frame

        if frame is not None:
            # Encode as JPEG
            _, buffer = cv2.imencode(
                '.jpg',
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, quality]
            )

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                buffer.tobytes() +
                b'\r\n'
            )

        await asyncio.sleep(1/30)  # 30 FPS
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
# 30 FPS
await asyncio.sleep(1/30)

# Match source FPS
await asyncio.sleep(1/video_handler.fps)
```

## Client Integration

### HTML/JavaScript

```html
<!DOCTYPE html>
<html>
<head>
    <title>PixEagle Stream</title>
</head>
<body>
    <img id="stream" src="http://localhost:8000/video_feed" />

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

cap = cv2.VideoCapture('http://localhost:8000/video_feed')

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
    'http://localhost:8000/video_feed',
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
curl -N http://localhost:8000/video_feed | \
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
curl -I http://localhost:8000/video_feed
```

### Choppy Video

1. Lower quality for bandwidth:
```
/video_feed?quality=50
```

2. Enable resizing:
```
/video_feed?resize=true
```

### High Latency

1. Reduce JPEG quality
2. Resize to smaller resolution
3. Check network bandwidth

### Connection Drops

1. Check server logs for errors
2. Verify video source is stable
3. Test with `curl` to isolate browser issues
