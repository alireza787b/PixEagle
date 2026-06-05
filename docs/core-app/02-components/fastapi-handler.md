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
| `/api/v1/telemetry/health` | GET | Typed MAVLink2REST request/payload health |
| `/api/v1/tracking/runtime-status` | GET | Typed tracker output/readiness status |
| `/stats` | GET | Streaming statistics |

`/telemetry/tracker_data` is a legacy compatibility payload, but it includes
the safety-relevant tracker runtime flags used by newer dashboard clients:
`has_output`, `usable_for_following`, and `data_is_stale` at the top level and
inside `tracker_data`. Do not treat `tracker_started` or `tracking_active` alone
as proof that follower control has a usable target.

New dashboard/API/MCP consumers should prefer
`GET /api/v1/tracking/runtime-status` for tracker readiness. It returns
`has_output`, `active_tracking`, `usable_for_following`, `data_is_stale`,
`status`, `consumer_guidance`, source/provider metadata, and the tracker claim
boundary. `usable_for_following=true` is the fail-closed control gate;
`active_tracking=true` alone is not enough because stale or explicitly unusable
tracker output can still report an active target.

### Typed Telemetry Health Endpoint

New API/MCP/dashboard consumers should use `GET /api/v1/telemetry/health` for
MAVLink2REST health instead of parsing the legacy flat `/status.mavlink_telemetry`
summary. The typed response separates latest request success, freshness of the
last successful sample, cached payload availability, validation-timeout state,
and a claim boundary. A recent cached payload with a failed latest request is
reported as `status = degraded` with
`consumer_guidance = degraded_latest_request_failed`.

### Typed Action Endpoints

New control-plane callers should use these `/api/v1` action resources. They
return a tracked action record with confirmation, dry-run, idempotency, local
following-state before/after, and a claim boundary. The record does not by
itself prove PX4-observed Offboard mode or setpoint cadence; accepted SITL
evidence still requires PX4 logs/telemetry artifacts. Confirmed mutations must
include `confirm=true` and an `idempotency_key`; they return `202` on first
execution. Dry-run and idempotent replay responses return `200`;
confirmation/idempotency, validation, and lookup failures use the typed
`/api/v1` error envelope.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/actions/offboard-start` | POST | Confirmed or dry-run Offboard-start action resource |
| `/api/v1/actions/operator-abort` | POST | Confirmed or dry-run operator abort/cancel action resource |
| `/api/v1/actions/{action_id}` | GET | Fetch in-process action record |

### Legacy Command Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/commands/start_tracking` | POST | Start tracking |
| `/commands/stop_tracking` | POST | Stop tracking |
| `/commands/start_offboard_mode` | POST | Compatibility alias for Offboard start; use `/api/v1/actions/offboard-start` for new control-plane integrations |
| `/commands/stop_offboard_mode` | POST | Disable offboard |
| `/commands/cancel_activities` | POST | Compatibility alias for operator cancel; use `/api/v1/actions/operator-abort` for new control-plane integrations |
| `/commands/toggle_smart_mode` | POST | Toggle YOLO tracker |
| `/commands/smart_click` | POST | Click to track |

The legacy start/cancel command routes are immediate-execution compatibility
routes for existing UI/scripts. They now attach an `action_audit` pointer to
the in-process action record, but they are not the MCP-safe contract because
they do not accept confirmation, dry-run, or idempotency request fields.

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
| `/api/v1/tracking/runtime-status` | GET | Typed tracker runtime/readiness contract |
| `/api/tracker/schema` | GET | Tracker schema |
| `/api/tracker/switch` | POST | Switch tracker type |
| `/api/follower/profiles` | GET | Available profiles |
| `/api/follower/switch-profile` | POST | Switch follower |

### SITL Validation Endpoint

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/sitl/injections/tracker-output` | POST | Validation-only `TrackerOutput` injection for operator-gated SITL scenarios |
| `/api/v1/sitl/injections/video-stall` | POST | Validation-only frame-stall metadata injection for operator-gated SITL scenarios |
| `/api/v1/sitl/injections/commander-publish-failure` | POST | Validation-only OffboardCommander publish-failure policy injection for operator-gated SITL scenarios |
| `/api/v1/sitl/injections/mavsdk-disconnect` | POST | Validation-only PixEagle-local MAVSDK command-path disconnect injection for operator-gated SITL scenarios |
| `/api/v1/sitl/injections/mavlink2rest-timeout` | POST | Validation-only PixEagle-local MAVLink2REST client timeout injection for operator-gated SITL scenarios |

The SITL injection endpoints are disabled unless PixEagle starts with
`PIXEAGLE_ENABLE_SITL_INJECTIONS=1`. They are not a general automation
surface. The tracker-output and video-stall routes refuse to dispatch unless
follow mode is already active, then go through the same command-freshness,
follower, and `OffboardCommander` path used by live tracker output. The
video-stall route passes frame-status metadata into
`handle_video_frame_unavailable()`; it does not stop or start cameras,
GStreamer, PX4, Docker, or routing services. Its response exposes a typed
frame-status summary with `source`, `status`, `usable_for_following`, `reason`,
timestamp, injection ID, and optional failure metadata. The commander
publish-failure route requires an active running `OffboardCommander`, records
bounded synthetic publish failures inside it, trips the existing local failure
policy, awaits AppController cleanup, and returns before/after commander
evidence plus the persisted failure record. It does not synthesize MAVSDK
setpoint publishes, replace PX4 interfaces, stop services, or mutate MAVLink
routing; cleanup still uses the normal Offboard stop path. Disabled, invalid,
unavailable, rejected, or request-validation failures return the `/api/v1`
error envelope with `error`, `code`, `detail`, `timestamp`, `path`, and
`request_id`.

The MAVSDK disconnect route marks PixEagle's local `PX4InterfaceManager`
command path validation-disconnected, records bounded commander publish
failures, and awaits the same fail-closed cleanup path. Its response exposes
PX4/MAVSDK connection summaries before and after the local disconnect, the
commander failure evidence, and the expected failed Offboard stop error. It
does not stop PX4, Docker, MavlinkAnywhere, MAVLink2REST, the MAVSDK server,
network interfaces, or MAVLink routes, so it is not evidence of a real
transport outage or PX4 failsafe by itself.

The MAVLink2REST timeout route records a bounded timeout window inside
PixEagle's `MavlinkDataManager`. During that window, PixEagle-local
MAVLink2REST client requests fail before `requests.get()` and `/status`
reports stale/error `mavlink_telemetry` with
`validation_timeout_active = true`. It does not stop MAVLink2REST, PX4, Docker,
MavlinkAnywhere, routing, or network interfaces, and it is not evidence of a
real transport outage by itself.

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
Streaming:
  HTTP_STREAM_PORT: 5077
  STREAM_FPS: 30
  STREAM_QUALITY: 85
  STREAM_WIDTH: 640
  STREAM_HEIGHT: 480
  enable_cache: true
  cache_ttl_ms: 100
  skip_identical_frames: true
```

## Related Components

- [AppController](app-controller.md) - Command execution
- [ConfigService](config-service.md) - Config endpoints
- [WebRTC](../../video/04-streaming/webrtc.md) - WebRTC support
