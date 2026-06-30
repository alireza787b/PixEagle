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

Typed `/api/v1` route registrations are centralized in
`src/classes/fastapi_api_v1_routes.py` as static `ApiV1RouteSpec` entries.
Canonical typed API paths live in `src/classes/api_v1_paths.py`, and
structured error-envelope construction lives in `src/classes/api_v1_errors.py`.
Typed action-resource storage, idempotency replay, guarded action route
execution, action resource lookup, legacy action audit attachment, and action
precondition failure helpers live in
`src/classes/api_v1_actions.py`.
Typed `/api/v1` read-route error boundaries for runtime, following, tracking,
and telemetry health live in `src/classes/api_v1_read_routes.py`.
Typed runtime/following/tracking read-state snapshot builders live in
`src/classes/api_v1_snapshots.py`.
Typed MAVLink telemetry-health manager delegation and unavailable fallback
payload construction live in `src/classes/api_v1_telemetry.py`.
Typed streaming media-health snapshots for MJPEG, WebSocket, WebRTC signaling,
GStreamer output, and frame-publisher state live in
`src/classes/api_v1_streams.py`.
`FastAPIHandler.define_routes()` delegates to the route registry while the
handler methods still live in `fastapi_handler.py`. Typed `/api/v1` Pydantic
contracts and error-response metadata live in `src/classes/api_v1_contracts.py`
and are imported back into `fastapi_handler.py` during migration for
compatibility. Route inventory tests and the non-callable agent-candidate
generator parse the route sources without instantiating the application, and
the generated inventory records the contract, path, action-helper,
read-route-helper, snapshot, and telemetry-helper source hashes.

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
| `/api/v1/runtime/status` | GET | Typed PixEagle process-local runtime status |
| `/api/v1/streams/media-health` | GET | Typed media transport/frame-publisher health |
| `/api/v1/following/status` | GET | Typed process-local following status |
| `/api/v1/following/telemetry` | GET | Typed follower telemetry/setpoint snapshot |
| `/api/v1/telemetry/health` | GET | Typed MAVLink2REST request/payload health |
| `/api/v1/tracking/runtime-status` | GET | Typed tracker output/readiness status |
| `/api/v1/tracking/telemetry` | GET | Typed tracker telemetry/geometry snapshot |
| `/stats` | GET | Streaming statistics |

`/telemetry/tracker_data` is a legacy compatibility payload, but it includes
the safety-relevant tracker runtime flags used by newer dashboard clients:
`has_output`, `usable_for_following`, and `data_is_stale` at the top level and
inside `tracker_data`. Do not treat `tracker_started` or `tracking_active` alone
as proof that follower control has a usable target.

References to API/MCP consumers in this document mean schema-stable typed
routes that are candidates for future reviewed integrations. They do not mean
PixEagle exposes callable MCP tools. See `docs/agent-context/README.md` for the
candidate inventory only, not MCP execution, boundary.

New dashboard/API/MCP consumers should prefer
`GET /api/v1/tracking/runtime-status` for tracker readiness. It returns
`has_output`, `active_tracking`, `usable_for_following`, `data_is_stale`,
`status`, `consumer_guidance`, source/provider metadata, and the tracker claim
boundary. `usable_for_following=true` is the fail-closed control gate;
`active_tracking=true` alone is not enough because stale or explicitly unusable
tracker output can still report an active target.

Consumers that need current tracker geometry for plots or diagnostics should
use `GET /api/v1/tracking/telemetry`. It returns a process-local typed snapshot
with `center`, `bounding_box`, `fields`, `tracker_data`, `field_source`, the
embedded runtime status, legacy payload key inventory, and an explicit claim
boundary. The route prefers live `TrackerOutput` fields and falls back to the
legacy telemetry snapshot only as a compatibility source. Top-level
`bounding_box` is normalized-only; pixel boxes remain in explicit fields such
as `fields.bbox`.

### Typed Runtime Status Endpoint

New dashboard/API/MCP consumers that need PixEagle mode flags should prefer
`GET /api/v1/runtime/status` instead of parsing the flat `/status` payload. It
returns `schema_version`, `source`, `status`, `consumer_guidance`, `modes`,
`subsystems`, `reason`, `claim_boundary`, and `timestamp`.

The `modes` object contains the four legacy operator flags:
`smart_mode_active`, `tracking_started`, `segmentation_active`, and
`following_active`. The `subsystems` object preserves compatibility snapshots
for video, Offboard commander, PX4 connection, MAVLink telemetry, and Smart
Tracker runtime data.

The route is process-local. It reports `degraded/operator_attention` when local
following is active but the Offboard commander reports a failure, stopped or
non-running publication, inactive task, stale command intent, active failsafe
defaults, or missing/unknown command-publication fields. It can report `active`
for local vision/following state, but it is not PX4, SITL, HIL, field, or
follower-response proof. Use telemetry, action resources, SITL evidence
artifacts, and PX4 logs for those claims.

### Typed Streaming Media Health Endpoint

Dashboard/API/MCP consumers that need backend media observability should use
`GET /api/v1/streams/media-health` instead of scraping `/stats` or
`/api/streaming/status`. The route returns a typed process-local snapshot for
HTTP MJPEG, JPEG WebSocket, WebRTC signaling, GStreamer UDP output,
frame-publisher freshness, security posture, stream config, adaptive-quality
state, and `health_issues`.

This route requires `media:read`. It reports local transport state only: active
HTTP/WebSocket/WebRTC clients, GStreamer encoder availability, and whether
PixEagle has a currently published frame. It does not prove that a remote
browser, QGC, WebRTC peer, GCS, PX4, SITL, HIL, or field video path received
usable media.

The bounded legacy media observability routes, HTTP MJPEG transport route, video
WebSocket transport route, and legacy reconnect mutation remain registered for
compatibility, but their response bodies now live in
`src/classes/api_legacy_media_routes.py`:

- `GET /video_feed`
- `WS /ws/video_feed`
- `GET /api/streaming/status`
- `GET /stats`
- `GET /api/video/health`
- `POST /api/video/reconnect`

`FastAPIHandler` keeps one-call wrappers for those routes. The reconnect route
is still a legacy mutation, not a typed `/api/v1` action.

`WS /ws/webrtc_signaling` remains a legacy compatibility route, but its
signaling state machine is owned by `src/classes/webrtc_manager.py`.
`FastAPIHandler` constructs the manager and registers
`self.webrtc_manager.signaling_handler`; `WebRTCManager` owns pre-accept
streaming, Host/Origin, authorization, and security-audit gates, server-owned
peer IDs, SDP/ICE handling, browser-session revocation, capacity reservation,
and bounded peer cleanup.

### Typed Following Status Endpoint

New dashboard/API/MCP consumers that only need following state should prefer
`GET /api/v1/following/status` instead of parsing `/telemetry/follower_data`.
It returns `schema_version`, `source`, `status`, `consumer_guidance`,
`following_active`, `profile`, `command_publication`, `health_issues`,
`reason`, `claim_boundary`, and `timestamp`.

The route is process-local and command-publication focused. It reports
`active/following_active` only when local following is active, a follower
instance/profile are present, and the Offboard commander snapshot reports
running publication, an active task, fresh intent, and inactive failsafe
defaults. It reports `degraded/operator_attention` for active following with
missing/invalid follower state, Offboard commander failure/non-running/task
inactive/stale-intent/failsafe-default/unknown fields, and for inactive local
following when the commander still appears to be running.

Consumers that need current setpoint values should use the typed following
telemetry route below. The typed following status route does not prove
PX4-observed Offboard, SITL, HIL, field, or follower-response success.

### Typed Following Telemetry Endpoint

Dashboard/API/MCP consumers that need follower setpoint values should prefer
`GET /api/v1/following/telemetry` instead of the legacy
`/telemetry/follower_data` payload. It returns `schema_version`, `source`,
`status`, `consumer_guidance`, `following_active`, `profile`, `fields`,
`field_source`, optional `last_command_intent`, optional target-loss/safety/
performance diagnostics, `circuit_breaker`, `command_publication`,
flight-mode hints, `legacy_payload_keys`, `health_issues`, `reason`,
`claim_boundary`, and `timestamp`.

The route prefers live setpoint-handler fields when an active follower exposes
them, then falls back to legacy follower telemetry fields during compatibility
windows. `field_source` identifies which path supplied the `fields` object. The
`command_publication.local_successful_publish_observed` field is local
PixEagle/MAVSDK publication evidence only; it is not PX4-observed Offboard or
vehicle-response proof.

Dashboard detailed follower status cards and the Follower visualization page's
follower-history snapshots now consume this typed route through the endpoint
registry, with fallback to `/telemetry/follower_data` only when the typed route
is missing during rolling updates. The frontend normalizer exposes `fields`
plus legacy plot aliases such as `vel_x`/`vel_y` so existing charts can render
the typed setpoint fields. The same page now consumes typed tracker telemetry
from `/api/v1/tracking/telemetry` for tracker center/bounding-box plots, with
legacy `/telemetry/tracker_data` fallback only when the typed route is missing.

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

The current action resource store, guarded action execution, and action lookup
helpers are process-local and owned by `src/classes/api_v1_actions.py`.
`FastAPIHandler` keeps thin route-method wrappers for migration compatibility.
This path is suitable for current operator/API feedback and validation plans,
but it is not durable command storage and it is not a runtime MCP executor.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/actions/offboard-start` | POST | Confirmed or dry-run Offboard-start action resource |
| `/api/v1/actions/offboard-stop` | POST | Confirmed or dry-run Offboard-stop action resource |
| `/api/v1/actions/operator-abort` | POST | Confirmed or dry-run operator abort/cancel action resource |
| `/api/v1/actions/tracking-start` | POST | Confirmed or dry-run tracking-start action resource with ROI bbox |
| `/api/v1/actions/tracking-stop` | POST | Confirmed or dry-run tracking-stop action resource |
| `/api/v1/actions/tracking-redetect` | POST | Confirmed or dry-run classic tracker re-detection action resource |
| `/api/v1/actions/segmentation-toggle` | POST | Confirmed or dry-run segmentation overlay toggle action resource |
| `/api/v1/actions/smart-mode-toggle` | POST | Confirmed or dry-run smart-mode toggle action resource |
| `/api/v1/actions/smart-click` | POST | Confirmed or dry-run smart-tracker click-selection action resource |
| `/api/v1/actions/{action_id}` | GET | Fetch in-process action record |

### Retired Command Endpoints

The former Offboard start, Offboard stop, operator-cancel, tracking start/stop,
redetect, segmentation toggle, smart-mode toggle, and smart-click command
aliases are no longer registered as HTTP routes. Use the typed action
resources instead:

| Retired endpoint | Replacement |
|----------|-------------|
| `/commands/start_offboard_mode` | `/api/v1/actions/offboard-start` |
| `/commands/stop_offboard_mode` | `/api/v1/actions/offboard-stop` |
| `/commands/cancel_activities` | `/api/v1/actions/operator-abort` |
| `/commands/start_tracking` | `/api/v1/actions/tracking-start` |
| `/commands/stop_tracking` | `/api/v1/actions/tracking-stop` |
| `/commands/redetect` | `/api/v1/actions/tracking-redetect` |
| `/commands/toggle_segmentation` | `/api/v1/actions/segmentation-toggle` |
| `/commands/toggle_smart_mode` | `/api/v1/actions/smart-mode-toggle` |
| `/commands/smart_click` | `/api/v1/actions/smart-click` |

`/commands/quit` remains a local-only process-administration route. It is not
an operator control or tracking API.

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
| `/api/v1/streams/media-health` | GET | Typed process-local media transport/frame-publisher health |

### Tracker/Follower Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/runtime/status` | GET | Typed PixEagle process-local runtime contract |
| `/api/v1/streams/media-health` | GET | Typed media transport/frame-publisher health contract |
| `/api/v1/following/status` | GET | Typed process-local following/readiness contract |
| `/api/v1/following/telemetry` | GET | Typed follower telemetry/setpoint snapshot |
| `/api/v1/tracking/runtime-status` | GET | Typed tracker runtime/readiness contract |
| `/api/v1/tracking/telemetry` | GET | Typed tracker telemetry/geometry snapshot |
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
surface. Their validation gate, payload construction, dry-run summaries, and
AppController validation-hook dispatch live in `src/classes/api_v1_sitl.py`;
`FastAPIHandler` keeps route wrappers only. The tracker-output and video-stall
routes refuse to dispatch unless follow mode is already active, then go through
the same command-freshness, follower, and `OffboardCommander` path used by live
tracker output. The
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
    """Optimized WebSocket streaming with adaptive quality and queuing."""
    return await dispatch_video_feed_websocket_optimized(self, websocket)
```

The legacy route body lives in `api_legacy_media_routes.py`. It rejects disabled
streaming, disallowed Host/Origin, failed authorization, and audit failure before
accepting the socket. After accept, capacity remains bounded by
`Streaming.WS_MAX_CONNECTIONS`; the helper registers a `ClientConnection`,
frame-publisher client, and adaptive-quality client, then runs send, receive,
and browser-session monitor tasks until one completes. Cleanup returns through
`FastAPIHandler._cleanup_websocket_client()` so heartbeat stale-close and server
shutdown use the same idempotent unregister path.

The wire envelope sends one JSON metadata message followed by one binary JPEG
message for each frame:

```python
message = {
    "type": "frame",
    "timestamp": current_time,
    "quality": client.quality,
    "size": len(frame_bytes),
    "frame_id": stamped.frame_id,
}
await websocket.send_json(message)
await websocket.send_bytes(frame_bytes)
```

Clients may also send `{"type": "quality", "quality": <int>}` within configured
quality bounds or `{"type": "ping", "client_timestamp": ...}` for a JSON `pong`
response. Three consecutive send failures terminate the stream and count exactly
three frame drops.

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
@app.post("/api/v1/actions/tracking-start")
async def tracking_start_action(self, request: APITrackingStartRequest, response):
    """Start tracking with typed action semantics and a bounding box."""
    return await dispatch_tracking_start_action(self, request, response)
```

### Smart Click

```python
@app.post("/api/v1/actions/smart-click")
async def smart_click_action(self, request: APITrackingSmartClickRequest, response):
    """Select a smart-tracker target with typed action semantics."""
    return await dispatch_smart_click_action(self, request, response)
```

## CORS Configuration

```python
def _setup_middleware(self):
    """Configure explicit CORS policy for the selected exposure mode."""
    self.app.add_middleware(
        CORSMiddleware,
        allow_origins=list(self.exposure_policy.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-PixEagle-CSRF",
            "X-Request-ID",
        ],
        max_age=3600
    )
```

Wildcard origins are prohibited. `local_only` requires an explicit loopback
bind and loopback browser origins. See the
[API exposure boundary](../../apis/api-exposure-boundary.md).

The handler also rejects requests whose `Host` authority is not allowed by the
selected exposure policy, then rejects modern-browser requests with a
cross-site `Sec-Fetch-Site` value or an unapproved `Origin` before route
execution. Origin approval is an explicit allowlist check, not a
Host/request-origin shortcut. This contains DNS-rebinding and
browser-to-localhost request attacks. The backend authentication,
authorization, session-CSRF, dashboard credential-aware media/API, durable
security-audit, and typed tracking/control action foundations are implemented;
TLS/operator hardening and adversarial auth/media tests remain tracked under
PXE-0064.

## Server Lifecycle

### Start

```python
async def start(self, host: str | None = None, port: int | None = None):
    """Start the FastAPI server."""
    host = host or Parameters.HTTP_STREAM_HOST
    policy = resolve_api_exposure_policy_from_parameters(Parameters, bind_host=host)
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
    return await dispatch_get_streaming_stats(self)
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
