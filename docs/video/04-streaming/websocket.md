# WebSocket Video Streaming

> Real-time bidirectional video over WebSocket

## Overview

WebSocket streaming provides lower latency than HTTP MJPEG and enables bidirectional communication. Frames are sent as binary JPEG data over a persistent WebSocket connection.

## Endpoint

```
WS /ws/video_feed
```

### Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/video_feed');
ws.binaryType = 'arraybuffer';
```

## Configuration

```yaml
FastAPI:
  ENABLE_WEBSOCKET: true
  WS_FRAME_RATE: 30        # Target FPS
  WS_QUALITY: 80           # JPEG quality
  WS_MAX_CLIENTS: 10       # Connection limit
  WS_PING_INTERVAL: 30     # Keep-alive ping (seconds)
```

## Implementation

### Server (FastAPI)

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
import cv2

app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast_frame(self, frame: bytes):
        for connection in self.active_connections:
            try:
                await connection.send_bytes(frame)
            except:
                self.disconnect(connection)

manager = ConnectionManager()

@app.websocket("/ws/video_feed")
async def websocket_video(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            frame = video_handler.current_osd_frame
            if frame is not None:
                _, buffer = cv2.imencode(
                    '.jpg',
                    frame,
                    [cv2.IMWRITE_JPEG_QUALITY, 80]
                )
                await websocket.send_bytes(buffer.tobytes())

            await asyncio.sleep(1/30)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

### Client (JavaScript)

```javascript
class VideoStreamClient {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.canvas = document.getElementById('video-canvas');
        this.ctx = this.canvas.getContext('2d');
    }

    connect() {
        this.ws = new WebSocket(this.url);
        this.ws.binaryType = 'arraybuffer';

        this.ws.onopen = () => {
            console.log('Connected to video stream');
        };

        this.ws.onmessage = (event) => {
            this.displayFrame(event.data);
        };

        this.ws.onclose = () => {
            console.log('Disconnected, reconnecting...');
            setTimeout(() => this.connect(), 1000);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    displayFrame(data) {
        const blob = new Blob([data], { type: 'image/jpeg' });
        const url = URL.createObjectURL(blob);

        const img = new Image();
        img.onload = () => {
            this.ctx.drawImage(img, 0, 0, this.canvas.width, this.canvas.height);
            URL.revokeObjectURL(url);
        };
        img.src = url;
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
        }
    }
}

// Usage
const client = new VideoStreamClient('ws://localhost:8000/ws/video_feed');
client.connect();
```

### HTML

```html
<!DOCTYPE html>
<html>
<head>
    <title>WebSocket Video</title>
</head>
<body>
    <canvas id="video-canvas" width="640" height="480"></canvas>
    <div id="stats"></div>

    <script>
        const canvas = document.getElementById('video-canvas');
        const ctx = canvas.getContext('2d');
        const stats = document.getElementById('stats');

        let frameCount = 0;
        let lastTime = performance.now();

        const ws = new WebSocket('ws://localhost:8000/ws/video_feed');
        ws.binaryType = 'arraybuffer';

        ws.onmessage = (event) => {
            const blob = new Blob([event.data], { type: 'image/jpeg' });
            const img = new Image();
            img.onload = () => {
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                URL.revokeObjectURL(img.src);

                // FPS counter
                frameCount++;
                const now = performance.now();
                if (now - lastTime >= 1000) {
                    stats.textContent = `FPS: ${frameCount}`;
                    frameCount = 0;
                    lastTime = now;
                }
            };
            img.src = URL.createObjectURL(blob);
        };
    </script>
</body>
</html>
```

## Bidirectional Communication

WebSocket enables sending commands back to the server:

### Client Commands

```javascript
// Send command
ws.send(JSON.stringify({
    type: 'command',
    action: 'set_quality',
    value: 60
}));

// Request different frame source
ws.send(JSON.stringify({
    type: 'config',
    osd: true,
    resize: false
}));
```

### Server Command Handling

```python
@app.websocket("/ws/video_feed")
async def websocket_video(websocket: WebSocket):
    await websocket.accept()

    config = {'osd': False, 'quality': 80}

    async def send_frames():
        while True:
            if config['osd']:
                frame = video_handler.current_osd_frame
            else:
                frame = video_handler.current_raw_frame

            if frame is not None:
                _, buffer = cv2.imencode(
                    '.jpg',
                    frame,
                    [cv2.IMWRITE_JPEG_QUALITY, config['quality']]
                )
                await websocket.send_bytes(buffer.tobytes())

            await asyncio.sleep(1/30)

    async def receive_commands():
        while True:
            try:
                data = await websocket.receive_json()
                if data.get('type') == 'config':
                    config.update(data)
            except:
                break

    await asyncio.gather(
        send_frames(),
        receive_commands()
    )
```

## Performance Optimization

### Frame Rate Adaptation

```python
async def adaptive_streaming(websocket, target_fps=30):
    frame_time = 1 / target_fps
    last_frame = time.time()

    while True:
        # Check if we're falling behind
        elapsed = time.time() - last_frame
        if elapsed < frame_time:
            await asyncio.sleep(frame_time - elapsed)

        # Skip frames if client is slow
        if elapsed > frame_time * 2:
            continue  # Skip this frame

        await send_frame(websocket)
        last_frame = time.time()
```

### Quality Adaptation

```python
class AdaptiveQuality:
    def __init__(self):
        self.quality = 80
        self.pending_acks = 0

    def adjust(self, ack_time):
        if ack_time > 100:  # ms
            self.quality = max(30, self.quality - 10)
        elif ack_time < 30:
            self.quality = min(95, self.quality + 5)
```

### Connection Limits

```python
MAX_CLIENTS = 10

@app.websocket("/ws/video_feed")
async def websocket_video(websocket: WebSocket):
    if len(manager.active_connections) >= MAX_CLIENTS:
        await websocket.close(code=1008, reason="Too many clients")
        return

    await manager.connect(websocket)
    # ...
```

## Troubleshooting

### Connection Refused

1. Check WebSocket is enabled:
```python
app.include_router(websocket_router)
```

2. Check CORS configuration:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Frame Drops

1. Lower quality:
```javascript
ws.send(JSON.stringify({type: 'config', quality: 50}));
```

2. Check network bandwidth
3. Reduce frame rate

### Memory Leak

1. Revoke blob URLs:
```javascript
URL.revokeObjectURL(img.src);
```

2. Properly close connections:
```javascript
ws.close();
```

### High Latency

1. Reduce frame size
2. Lower JPEG quality
3. Check server CPU usage
