# Streaming Configuration

> Complete reference for video output settings

## HTTP/WebSocket Streaming

```yaml
Streaming:
  # Server settings
  API_EXPOSURE_MODE: local_only
  HTTP_STREAM_HOST: 127.0.0.1
  HTTP_STREAM_PORT: 5077
  API_AUTH_MODE: local_compat
  API_ALLOWED_HOSTS: []
  API_CORS_ALLOWED_ORIGINS:
    - http://127.0.0.1:3040
    - http://localhost:3040
  ALLOW_UNAUTHENTICATED_MEDIA_STREAMING: false

  # Stream enable and default protocol
  ENABLE_STREAMING: true
  DEFAULT_PROTOCOL: auto

  # Quality settings
  STREAM_QUALITY: 80          # JPEG quality (1-100)
  STREAM_WIDTH: 640           # Resize width
  STREAM_HEIGHT: 480          # Resize height

  # Performance
  STREAM_FPS: 30              # Target FPS
  HTTP_MAX_CONNECTIONS: 20    # MJPEG connection limit
  WS_MAX_CONNECTIONS: 10      # WebSocket connection limit
  WS_HEARTBEAT_INTERVAL: 30   # Health check interval
```

### HTTP Stream Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ENABLE_STREAMING` | bool | true | Enable backend media streaming |
| `HTTP_STREAM_HOST` | string | `127.0.0.1` | Backend API/media bind host |
| `HTTP_STREAM_PORT` | int | 5077 | Backend API/media port |
| `API_EXPOSURE_MODE` | string | `local_only` | Exposure boundary |
| `API_AUTH_MODE` | string | `local_compat` | API/media auth mode |
| `API_ALLOWED_HOSTS` | list | [] | Backend HTTP `Host` allowlist for reviewed non-loopback profiles |
| `API_CORS_ALLOWED_ORIGINS` | list | local dashboard origins | Browser CORS origin allowlist |
| `ALLOW_UNAUTHENTICATED_MEDIA_STREAMING` | bool | false | Unsafe lab-only anonymous access to `GET /video_feed` and `WS /ws/video_feed` only |
| `STREAM_QUALITY` | int | 50 | JPEG quality (1-100) |
| `STREAM_WIDTH` | int | 640 | Resize width (0 = original) |
| `STREAM_HEIGHT` | int | 480 | Resize height (0 = original) |
| `STREAM_FPS` | int | 10 | Target frame rate |
| `HTTP_MAX_CONNECTIONS` | int | 20 | Max concurrent MJPEG streams |

`API_ALLOWED_HOSTS` validates the PixEagle URL/proxy Host authority, such as
`pixeagle.local:5077` or `pixeagle.example:443`. It is not a trusted
GCS/browser/client source-IP allowlist. Restrict selected client devices with a
firewall, VPN/private overlay, or reverse proxy source rules.

`ALLOW_UNAUTHENTICATED_MEDIA_STREAMING` is only for explicit lab/demo benches.
It bypasses auth for `GET /video_feed` and `WS /ws/video_feed`; it does not open
dashboard pages, control/config/log APIs, WebRTC signaling, media-health, or any
mutation route.

### WebSocket Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `WS_MAX_CONNECTIONS` | int | 10 | Max concurrent WebSocket clients |
| `MAX_FRAME_QUEUE` | int | 3 | Max queued frames per WebSocket client |
| `WS_HEARTBEAT_INTERVAL` | int | 30 | Health check interval in seconds |
| `WS_STALE_TIMEOUT_MULTIPLIER` | int | 2 | Stale timeout multiplier |

### WebRTC Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `WEBRTC_MAX_CONNECTIONS` | int | 3 | Max concurrent WebRTC peers |
| `WEBRTC_STUN_SERVER` | string | `stun:stun.l.google.com:19302` | Server-side `aiortc` STUN URL (`stun:`/`stuns:`) |
| `WEBRTC_TURN_SERVER` | string | - | Optional server-side `aiortc` TURN URL (`turn:`/`turns:`) |
| `WEBRTC_TURN_USERNAME` | string | - | Optional TURN username; configure together with the credential |
| `WEBRTC_TURN_CREDENTIAL` | string | - | Optional TURN credential; never returned by media health |
| `DEFAULT_PROTOCOL` | string | `auto` | Dashboard protocol preference |

These parameters configure the server peer and require a PixEagle process
restart. Invalid schemes and partial TURN credential pairs are ignored with an
error log. They do not provision a TURN service or deliver browser-side TURN
credentials; see [WebRTC](../04-streaming/webrtc.md) for the end-to-end claim
boundary.

## Media Health API

`GET /api/v1/streams/media-health` reports typed process-local media health for
the configured Streaming and GStreamer output paths. It includes MJPEG,
WebSocket, WebRTC signaling and redacted server ICE configuration, GStreamer output, frame-publisher freshness,
adaptive-quality state, `Streaming.ENABLE_STREAMING`, zero-capacity transport
state, and the effective media auth/exposure posture. Stale published frames
degrade the route status. GStreamer UDP reports pipeline activity but no client
connection count because UDP output has no reliable client handshake.

The route requires `media:read`. It is consumed by the dashboard streaming
status widgets and by the best-effort `pixeagle-service status` media-health
block. Same-host default status checks work through `local_compat`; deployments
using `machine_bearer` or `browser_session` need an explicit `media:read` bearer
token file for the service probe. The route is intended for dashboard/API/MCP
observability and does not prove that a remote browser, QGC, WebRTC peer, GCS,
PX4, SITL, HIL, or field video path received usable media.

## GStreamer Output Streaming

```yaml
GStreamer:
  # Enable output streaming
  ENABLE_GSTREAMER_STREAM: true

  # Destination
  GSTREAMER_HOST: 192.168.1.10     # GCS IP address or DNS hostname
  GSTREAMER_PORT: 5600             # UDP port

  # Encoder settings
  GSTREAMER_BITRATE: 2000          # kbps
  GSTREAMER_INCLUDE_OSD: true      # Independent QGC/GCS OSD selection
  ENABLE_HARDWARE_ENCODING: true   # HW acceleration

  # Advanced
  GSTREAMER_SPEED_PRESET: ultrafast # x264 preset
  GSTREAMER_KEY_INT_MAX: 30         # Keyframe every N frames
  GSTREAMER_TUNE: zerolatency        # x264 tune
```

### GStreamer Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ENABLE_GSTREAMER_STREAM` | bool | false | Enable GStreamer output |
| `GSTREAMER_HOST` | string | `127.0.0.1` | Destination IP address or DNS hostname; no scheme, port, or path |
| `GSTREAMER_PORT` | int | 5600 | Destination UDP port |
| `GSTREAMER_BITRATE` | int | 2000 | Bitrate in kbps |
| `GSTREAMER_WIDTH` | int | 1280 | Even output width, `16..3840`; source aspect ratio is preserved with black bars |
| `GSTREAMER_HEIGHT` | int | 720 | Even output height, `16..2160`; source aspect ratio is preserved with black bars |
| `GSTREAMER_FRAMERATE` | int | 15 | Output submission/caps rate, `1..60`; combined pixel-rate validation permits up to 1080p60 or 2160p15 |
| `GSTREAMER_BUFFER_SIZE` | int | 50000000 | UDP socket buffer size in bytes |
| `GSTREAMER_INCLUDE_OSD` | bool | true | Include processed PixEagle OSD in QGC/GCS output, independently of browser stream OSD selection |
| `ENABLE_HARDWARE_ENCODING` | bool | false | Try HW encoder before software fallback |
| `GSTREAMER_SPEED_PRESET` | string | ultrafast | x264 preset |
| `GSTREAMER_KEY_INT_MAX` | int | 30 | Keyframe interval |
| `GSTREAMER_TUNE` | string | zerolatency | x264 tuning mode (`zerolatency`, `fastdecode`, or `stillimage`) |

This output is independent of `VideoSource.USE_GSTREAMER`, but both currently
use OpenCV's `CAP_GSTREAMER` backend. Enabling either feature therefore requires
the active venv's OpenCV build to report `GStreamer: YES`; system packages alone
are not enough. If QGC UDP output cannot initialize, browser MJPEG/WebSocket and
tracking can remain available, while media health reports the UDP lane inactive.
No automatic fallback broadens PixEagle's network exposure.
Frames are cadence-limited before optional GStreamer-only OSD composition and
encoding. Raw output is normalized in the writer thread; OSD output is
aspect-normalized and composed at the exact output resolution before the
detached prepared frame is queued. Browser and GCS outputs use independent OSD
caches, so differing resolutions do not invalidate each other. This prevents a
30/60 fps capture source from performing output-only resize and OSD work when
the output is configured for 15 fps.

### Encoder Presets

| Preset | Speed | Quality | CPU |
|--------|-------|---------|-----|
| ultrafast | Fastest | Low | Minimal |
| superfast | Very fast | Low-Med | Low |
| veryfast | Fast | Medium | Medium |
| faster | Moderate | Med-High | Higher |
| fast | Slow | High | High |

## OSD Configuration

```yaml
OSD:
  # Enable/disable
  OSD_ENABLED: true

  # Elements
  SHOW_FPS: true
  SHOW_TIMESTAMP: true
  SHOW_TRACKING_STATUS: true
  SHOW_SAFETY_STATUS: true
  SHOW_MODE: true
  SHOW_TELEMETRY: false

  # Appearance
  FONT_SCALE: 0.5
  FONT_THICKNESS: 1
  TEXT_COLOR: [255, 255, 255]
  BACKGROUND_COLOR: [0, 0, 0]
  BACKGROUND_OPACITY: 0.7

  # Layout
  MARGIN: 10
  PADDING: 5
```

### OSD Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `OSD_ENABLED` | bool | true | Enable OSD rendering |
| `SHOW_FPS` | bool | true | Display FPS counter |
| `SHOW_TIMESTAMP` | bool | true | Display timestamp |
| `FONT_SCALE` | float | 0.5 | Text size multiplier |
| `MARGIN` | int | 10 | Edge margin in pixels |

## Streaming Optimizer

```yaml
Streaming:
  # Optimization
  ENABLE_FRAME_CACHE: true
  MAX_FRAME_CACHE_SIZE: 10

  # Adaptive quality
  ENABLE_ADAPTIVE_QUALITY: true
  MIN_QUALITY: 30
  MAX_QUALITY: 85
  TARGET_BANDWIDTH_HIGH_KBPS: 200
```

### Optimizer Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ENABLE_FRAME_CACHE` | bool | true | Enable encoded-frame caching |
| `MAX_FRAME_CACHE_SIZE` | int | 10 | Maximum cached encoded frames |
| `ENABLE_ADAPTIVE_QUALITY` | bool | true | Auto-adjust quality |
| `TARGET_BANDWIDTH_HIGH_KBPS` | int | 200 | Bandwidth threshold for quality increases |

## Example Configurations

### Dashboard Streaming

```yaml
Streaming:
  ENABLE_STREAMING: true
  STREAM_QUALITY: 70
  STREAM_WIDTH: 640
  STREAM_HEIGHT: 480
  HTTP_MAX_CONNECTIONS: 20
  WS_MAX_CONNECTIONS: 10

OSD:
  OSD_ENABLED: true
  SHOW_FPS: true
  SHOW_TRACKING_STATUS: true
```

### QGroundControl Integration

```yaml
GStreamer:
  ENABLE_GSTREAMER_STREAM: true
  GSTREAMER_HOST: 192.168.1.10
  GSTREAMER_PORT: 5600
  GSTREAMER_BITRATE: 3000
  ENABLE_HARDWARE_ENCODING: true
  GSTREAMER_SPEED_PRESET: superfast

OSD:
  OSD_ENABLED: true
  SHOW_TELEMETRY: true
  SHOW_SAFETY_STATUS: true
```

### Low Bandwidth Streaming

```yaml
Streaming:
  STREAM_QUALITY: 50
  STREAM_WIDTH: 320
  STREAM_HEIGHT: 240
  STREAM_FPS: 15
  ENABLE_ADAPTIVE_QUALITY: true
  MIN_QUALITY: 20
  TARGET_BANDWIDTH_HIGH_KBPS: 500
```

### High Quality Recording

```yaml
Streaming:
  STREAM_QUALITY: 95
  STREAM_WIDTH: 1920
  STREAM_HEIGHT: 1080
  STREAM_FPS: 30

OSD:
  OSD_ENABLED: false  # Clean frames for recording
```

## Accessing Streams

### HTTP MJPEG

```html
<img src="http://127.0.0.1:5077/video_feed" />
```

Frame selection, quality, dimensions, OSD behavior, and adaptive quality are
server-side `Streaming`/`OSD` settings. The active endpoint does not support
per-request `osd`, `quality`, or `resize` query parameters, and query-string
credentials are rejected.

### WebSocket

```javascript
const ws = new WebSocket('ws://127.0.0.1:5077/ws/video_feed');
```

### QGroundControl

1. Open QGroundControl
2. Settings > Video
3. Source: UDP h.264 Video Stream
4. Port: 5600 (or configured port)

Direct QGC HTTP-MJPEG or WebSocket testing is supported only for same-host
loopback PixEagle URLs unless a reviewed authenticated remote-media profile is
configured. For normal companion-to-GCS QGroundControl video, use the UDP
H.264/RTP GStreamer output path.

QGC HTTP/HTTPS MJPEG and WebSocket support should remain generic for non-PixEagle
sources. PixEagle remote HTTP/WS is a stricter source profile that needs bearer
Authorization, WebSocket Origin, TLS/WSS handling, and credential redaction
before it is advertised for companion-to-GCS use. See
[QGC HTTP/WebSocket Source Plan](../04-streaming/qgc-http-websocket-source-plan.md).

```text
http://127.0.0.1:5077/video_feed
ws://127.0.0.1:5077/ws/video_feed
```
