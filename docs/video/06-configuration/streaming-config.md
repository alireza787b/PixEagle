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
  STREAM_PROFILE: automatic
  STREAM_QUALITY: 50          # Initial JPEG quality within profile limits
  STREAM_WIDTH: 640           # Delivery width bound; preserves aspect ratio
  STREAM_HEIGHT: 480          # Delivery height bound; no upscaling
  STREAM_MAX_BITRATE_KBPS: 8000 # Aggregate HTTP/WebSocket JPEG payload budget

  # Performance
  STREAM_FPS: 20              # Output ceiling; fresh frames only (1-60)
  HTTP_MAX_CONNECTIONS: 20    # MJPEG connection limit
  WS_MAX_CONNECTIONS: 10      # WebSocket connection limit
  WS_HEARTBEAT_INTERVAL: 30   # Health check interval
  WS_FRAME_ACK_TIMEOUT_SECONDS: 2.0 # Bound stalled ACK/write waits
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
| `STREAM_PROFILE` | string | `automatic` | Per-client `automatic`, `high_quality`, or `low_bandwidth` policy; restart required |
| `STREAM_QUALITY` | int | 50 | Initial JPEG quality, clamped to global and profile limits |
| `STREAM_WIDTH` | int | 640 | Positive delivery width bound; preserves source aspect ratio without upscaling |
| `STREAM_HEIGHT` | int | 480 | Positive delivery height bound; preserves source aspect ratio without upscaling |
| `STREAM_MAX_BITRATE_KBPS` | int | 8000 | Shared HTTP/WebSocket JPEG payload budget, decimal kbps; restart required |
| `STREAM_FPS` | int | 20 | Output FPS ceiling; source/AI processing may be lower |
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
| `MAX_FRAME_QUEUE` | int | 3 | Legacy queue field; the latest-frame sender retains one pending JPEG |
| `WS_HEARTBEAT_INTERVAL` | int | 30 | Health check interval in seconds |
| `WS_STALE_TIMEOUT_MULTIPLIER` | int | 2 | Stale timeout multiplier |
| `WS_FRAME_ACK_TIMEOUT_SECONDS` | float | 2.0 | Timeout for an outstanding negotiated frame ACK or frame-pair write; restart required |

Negotiated WebSocket delivery holds one frame in flight. Native QGC's ACK
means decoder admission, while browser rendering feedback is reported
separately. An ACK must not be treated as proof of native presentation. HTTP
provides ASGI write-completion timing, not remote presentation timing.

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
error log. Authorized dashboard clients receive the validated ICE records from
`GET /api/v1/streams/client-config`; the response is `no-store` and is the
single browser transport source of truth. Prefer short-lived TURN credentials
for production. See [WebRTC](../04-streaming/webrtc.md) for the end-to-end
claim boundary.

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
  STREAM_PROFILE: automatic
  STREAM_MAX_BITRATE_KBPS: 8000
  MIN_QUALITY: 30
  MAX_QUALITY: 85
  QUALITY_STEP_ADAPTIVE: 5
  QUALITY_COOLDOWN_SECONDS: 2.0
```

### Optimizer Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ENABLE_FRAME_CACHE` | bool | true | Reuse completed encodes with identical frame/epoch/variant/dimensions/quality |
| `MAX_FRAME_CACHE_SIZE` | int | 10 | Maximum retained JPEG result records; count-based eviction |
| `ENABLE_ADAPTIVE_QUALITY` | bool | true | Adapt per-client FPS, negotiated size, and JPEG quality from measured feedback |
| `MIN_QUALITY` / `MAX_QUALITY` | int | 30 / 85 | Global quality bounds; profiles also impose detail floors and ceilings |
| `QUALITY_STEP_ADAPTIVE` | int | 5 | Size of bounded JPEG-quality adjustments |
| `QUALITY_COOLDOWN_SECONDS` | float | 2.0 | Minimum normal reduction interval; recovery waits twice this interval |
| `BANDWIDTH_EWMA_ALPHA` | float | 0.3 | Smoothing for observed byte rate and write duration; not link-capacity estimation |
| `ENCODING_EWMA_ALPHA` | float | 0.2 | Smoothing for encoder, ACK, and optional rendering-delay measurements |
| `ENCODING_TIME_THRESHOLD_MS` | int | 20 | Base encoder-service threshold, combined with the current frame interval |
| `TARGET_BANDWIDTH_LOW_KBPS` | int | 50 | Legacy compatibility only; no effect on adaptation or aggregate budget |
| `TARGET_BANDWIDTH_HIGH_KBPS` | int | 200 | Legacy compatibility only; no effect on adaptation or aggregate budget |
| `CPU_THRESHOLD_HIGH` / `CPU_THRESHOLD_LOW` | int | 80 / 60 | Legacy compatibility only; no adaptation effect; CPU load is diagnostic |
| `CACHE_TTL_MS` | int | 100 | Legacy compatibility only; no effect on cache eviction |

The legacy keys remain accepted so existing configuration files can load;
changing them does not tune the measured delivery policy. Disabling completed
cache reuse still retains bounded encoder-result records for service timing.
Concurrent identical encoding work is shared.

Measured feedback separates successful server writes, matched ACK elapsed time,
actual encoder service time, and optional receiver rendering delay/drops.
Encoder queue wait is excluded. Actual bytes over observed delivery intervals
describe traffic, not available capacity. Global CPU load and detailed scenes
with larger JPEGs do not independently force quality reductions.

Normal sustained pressure reduces FPS, then supported spatial size, then
quality. Recovery reverses that order more slowly. Automatic permits scales
1/0.75/0.5/0.25; high quality permits 1/0.75; low bandwidth starts at 0.75,
permits 0.5/0.25, and caps FPS at 10. Fixed-size clients retain full published
dimensions. At factory defaults the quality floors are 50/70/45 respectively;
all limits obey `MIN_QUALITY`/`MAX_QUALITY`, and the low-bandwidth quality ceiling
is 65. See [Streaming Performance](../04-streaming/streaming-optimizer.md) for
the exact floor rules when the configured initial quality changes.

The aggregate budget covers JPEG payloads only, across HTTP and WebSocket.
WebRTC, GStreamer output, protocol overhead, and other/control traffic require
their own capacity allowance. The scheduler admits at most 250 ms of payload
serialization time and rejects excess work. An oversized individual frame
steps down spatial size immediately, then quality within its floor; reducing
FPS cannot make that frame fit. If its minimum permitted representation still
exceeds the budget, status reports `unavailable_at_configured_limits`.

At 0.5 Mbps a JPEG must fit within 15,625 bytes. Neither low-bandwidth mode nor
the smallest spatial choice guarantees that every scene will fit. When
adaptation is disabled, the budget still rejects oversized frames. Review
feedback age/staleness as well as the selected policy; stale counters do not
prove ongoing playback.

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
  STREAM_PROFILE: low_bandwidth
  STREAM_MAX_BITRATE_KBPS: 1000
  STREAM_QUALITY: 60
  STREAM_WIDTH: 640
  STREAM_HEIGHT: 480
  STREAM_FPS: 15
  ENABLE_ADAPTIVE_QUALITY: true
  MIN_QUALITY: 45
```

This is a tuning starting point, not a qualified cellular bitrate. The profile
caps its initial FPS at 10 and can reject scenes that exceed its detail floor.

### High Quality Live JPEG

```yaml
Streaming:
  STREAM_PROFILE: high_quality
  STREAM_MAX_BITRATE_KBPS: 16000
  STREAM_QUALITY: 85
  MAX_QUALITY: 95
  STREAM_WIDTH: 1920
  STREAM_HEIGHT: 1080
  STREAM_FPS: 30

OSD:
  OSD_ENABLED: false  # Clean live display
```

Select an adequately detailed capture source first. Raising delivery bounds
does not upscale a low-resolution source or change recording configuration.

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

Direct QGC HTTP-MJPEG or WebSocket testing is supported for same-host loopback
and the explicit anonymous media-only lab profile. For normal
companion-to-GCS QGroundControl video, prefer the UDP H.264/RTP GStreamer
output path.

QGC HTTP/HTTPS MJPEG and WebSocket support should remain generic for non-PixEagle
sources. Focused proposals #14730/#14731 are unauthenticated transports and
cannot consume PixEagle's guarded Bearer/Origin profile; authenticated direct
media remains a separate future security slice. See
[QGC HTTP/WebSocket Source Plan](../04-streaming/qgc-http-websocket-source-plan.md).

```text
http://127.0.0.1:5077/video_feed
ws://127.0.0.1:5077/ws/video_feed
```
