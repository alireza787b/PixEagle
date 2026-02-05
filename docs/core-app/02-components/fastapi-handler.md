# FastAPIHandler

Optimized REST/WebSocket API with streaming capabilities.

## Overview

`FastAPIHandler` (`src/classes/fastapi_handler.py`) provides:

- REST API endpoints for commands and telemetry
- MJPEG video streaming with adaptive quality
- WebSocket for real-time updates
- WebRTC signaling support
- Rate limiting and connection management
- Frame caching for performance

## Class Definition

```python
class FastAPIHandler:
    """
    Optimized FastAPI handler with professional streaming capabilities.

    Features:
    - Adaptive quality streaming
    - Frame caching
    - Connection management
    - Rate limiting
    """
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPIHandler                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  FastAPI App                                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │  REST API   │  │  WebSocket  │  │   MJPEG     │   │   │
│  │  │  Endpoints  │  │  Handlers   │  │  Streaming  │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Optimizers                                           │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │ StreamOpt   │  │ RateLimiter │  │ WebRTCMgr   │   │   │
│  │  │ (Caching)   │  │             │  │             │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Endpoint Categories

### Streaming Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/video_feed` | GET | MJPEG stream |
| `/ws/video_feed` | WS | WebSocket video |
| `/ws/webrtc_signaling` | WS | WebRTC signaling |

### Telemetry Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/telemetry/tracker_data` | GET | Current tracker output |
| `/telemetry/follower_data` | GET | Current follower state |
| `/status` | GET | System status |
| `/stats` | GET | Streaming statistics |

### Command Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/commands/start_tracking` | POST | Start tracking |
| `/commands/stop_tracking` | POST | Stop tracking |
| `/commands/start_offboard_mode` | POST | Enable offboard |
| `/commands/stop_offboard_mode` | POST | Disable offboard |
| `/commands/toggle_smart_mode` | POST | Toggle YOLO tracker |
| `/commands/smart_click` | POST | Click to track |

### Configuration Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/config/current` | GET | Current config |
| `/api/config/schema` | GET | Config schema |
| `/api/config/{section}/{param}` | PUT | Update parameter |
| `/api/config/history` | GET | Backup history |

### Video Resilience Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/video/health` | GET | Video health and degraded-mode state |
| `/api/video/reconnect` | POST | Trigger manual video reconnect attempt |

### Tracker/Follower Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tracker/schema` | GET | Tracker schema |
| `/api/tracker/switch` | POST | Switch tracker type |
| `/api/follower/profiles` | GET | Available profiles |
| `/api/follower/switch-profile` | POST | Switch follower |

## Video Streaming

### MJPEG Stream

```python
async def video_feed(self):
    """Optimized MJPEG streaming with adaptive quality."""
    async def generate():
        while not self.is_shutting_down:
            # Rate limiting
            elapsed = time.time() - self.last_http_send_time
            if elapsed < self.frame_interval:
                await asyncio.sleep(self.frame_interval - elapsed)

            # Get current frame
            frame = self.app_controller.current_frame
            if frame is None:
                continue

            # Encode with caching
            frame_bytes = await self.stream_optimizer.encode_frame_async(
                frame, self.quality
            )

            # Send MJPEG frame
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n'
                + frame_bytes +
                b'\r\n'
            )

            self.last_http_send_time = time.time()

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )
```

### Frame Caching

```python
class StreamingOptimizer:
    """Optimized streaming with caching and adaptive quality."""

    def encode_frame_cached(self, frame: np.ndarray, quality: int) -> bytes:
        """Encode frame with caching."""
        # Generate frame hash
        frame_hash = self.get_frame_hash(frame)

        # Check cache
        cache_key = f"{frame_hash}_{quality}"
        if cache_key in self.frame_cache:
            cached = self.frame_cache[cache_key]
            if time.time() - cached.timestamp < CACHE_TTL:
                return cached.data

        # Encode
        ret, buffer = cv2.imencode('.jpg', frame,
            [cv2.IMWRITE_JPEG_QUALITY, quality])
        frame_bytes = buffer.tobytes()

        # Cache
        self.frame_cache[cache_key] = CachedFrame(
            data=frame_bytes,
            timestamp=time.time(),
            hash=frame_hash,
            quality=quality
        )

        return frame_bytes
```

### WebSocket Video

```python
async def video_feed_websocket_optimized(self, websocket: WebSocket):
    """WebSocket video streaming."""
    await websocket.accept()

    client_id = str(id(websocket))
    self.ws_connections[client_id] = ClientConnection(...)

    try:
        while not self.is_shutting_down:
            frame = self.app_controller.current_frame
            if frame is None:
                await asyncio.sleep(0.01)
                continue

            # Encode
            frame_bytes = await self.stream_optimizer.encode_frame_async(
                frame, self.quality
            )

            # Send binary
            await websocket.send_bytes(frame_bytes)

    except WebSocketDisconnect:
        pass
    finally:
        del self.ws_connections[client_id]
```

## Rate Limiting

```python
class RateLimiter:
    """Simple in-memory rate limiter."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, deque] = {}

    def is_allowed(self, key: str) -> Tuple[bool, Optional[int]]:
        """Check if request is allowed."""
        now = time.time()

        # Clean old entries
        while self._requests[key] and \
              self._requests[key][0] < now - self.window_seconds:
            self._requests[key].popleft()

        # Check limit
        if len(self._requests[key]) >= self.max_requests:
            retry_after = int(self._requests[key][0] + self.window_seconds - now)
            return False, retry_after

        # Record request
        self._requests[key].append(now)
        return True, None
```

### Usage in Endpoints

```python
@app.put("/api/config/{section}/{parameter}")
async def update_config_parameter(self, request: Request, ...):
    # Rate limit check
    client_ip = request.client.host
    allowed, retry_after = self.config_rate_limiter.is_allowed(client_ip)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {retry_after}s"
        )

    # Process request...
```

## Command Handlers

### Start Tracking

```python
@app.post("/commands/start_tracking")
async def start_tracking(self, request: BoundingBox):
    """Start tracking with bounding box."""
    try:
        bbox = (request.x, request.y, request.width, request.height)
        await self.app_controller.start_tracking(bbox)
        return {"status": "success", "message": "Tracking started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Smart Click

```python
@app.post("/commands/smart_click")
async def smart_click(self, request: ClickPosition):
    """Click-to-track with YOLO."""
    try:
        x, y = request.x, request.y
        await self.app_controller.smart_tracker.click_to_track(x, y)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## CORS Configuration

```python
def _setup_middleware(self):
    """Configure CORS middleware."""
    self.app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=3600
    )
```

## Server Lifecycle

### Start

```python
async def start(self, host: str = "0.0.0.0", port: int = 8000):
    """Start the FastAPI server."""
    config = uvicorn.Config(
        self.app,
        host=host,
        port=port,
        log_level="info"
    )
    self.server = uvicorn.Server(config)
    await self.server.serve()
```

### Stop

```python
async def stop(self):
    """Stop the server gracefully."""
    self.is_shutting_down = True

    # Close WebSocket connections
    for client_id in list(self.ws_connections.keys()):
        try:
            ws = self.ws_connections[client_id]
            await ws.close()
        except:
            pass

    # Stop server
    if self.server:
        self.server.should_exit = True
```

## Performance Monitoring

```python
# Statistics tracked
self.stats = {
    'frames_sent': 0,
    'frames_dropped': 0,
    'total_bandwidth': 0,
    'active_connections': 0
}

@app.get("/stats")
async def get_streaming_stats(self):
    """Get streaming performance stats."""
    return {
        **self.stats,
        'http_connections': len(self.http_connections),
        'ws_connections': len(self.ws_connections),
        'frame_rate': self.frame_rate,
        'quality': self.quality
    }
```

## Configuration

```yaml
# config_default.yaml
http:
  host: "0.0.0.0"
  port: 8000

streaming:
  fps: 30
  quality: 85
  width: 640
  height: 480
  enable_cache: true
  cache_ttl_ms: 100
  skip_identical_frames: true
```

## Related Components

- [AppController](app-controller.md) - Command execution
- [ConfigService](config-service.md) - Config endpoints
- [WebRTCManager](../../video/02-components/webrtc-manager.md) - WebRTC support
