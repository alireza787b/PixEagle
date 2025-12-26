# Streaming Configuration

> Complete reference for video output settings

## HTTP/WebSocket Streaming

```yaml
FastAPI:
  # Server settings
  HOST: 0.0.0.0
  PORT: 8000

  # Stream enables
  ENABLE_HTTP_STREAM: true
  ENABLE_WEBSOCKET: true
  ENABLE_WEBRTC: false

  # Quality settings
  STREAM_QUALITY: 80          # JPEG quality (1-100)
  STREAM_WIDTH: 640           # Resize width
  STREAM_HEIGHT: 480          # Resize height

  # Performance
  STREAM_FPS: 30              # Target FPS
  MAX_CLIENTS: 10             # Connection limit

  # MJPEG settings
  MJPEG_BOUNDARY: "frame"     # Multipart boundary
```

### HTTP Stream Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ENABLE_HTTP_STREAM` | bool | true | Enable MJPEG endpoint |
| `STREAM_QUALITY` | int | 80 | JPEG quality (1-100) |
| `STREAM_WIDTH` | int | 640 | Resize width (0 = original) |
| `STREAM_HEIGHT` | int | 480 | Resize height (0 = original) |
| `STREAM_FPS` | int | 30 | Target frame rate |

### WebSocket Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ENABLE_WEBSOCKET` | bool | true | Enable WebSocket endpoint |
| `WS_PING_INTERVAL` | int | 30 | Keep-alive ping (seconds) |
| `MAX_CLIENTS` | int | 10 | Max concurrent connections |

### WebRTC Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ENABLE_WEBRTC` | bool | false | Enable WebRTC |
| `WEBRTC_STUN_SERVER` | string | - | STUN server URL |
| `WEBRTC_TURN_SERVER` | string | - | TURN server URL |
| `WEBRTC_BITRATE` | int | 2000000 | Target bitrate (bps) |

## GStreamer Output Streaming

```yaml
GStreamer:
  # Enable output streaming
  ENABLE: true

  # Destination
  DEST_HOST: 192.168.1.10     # GCS IP address
  DEST_PORT: 5600             # UDP port

  # Encoder settings
  BITRATE: 2000               # kbps
  USE_HARDWARE_ENCODER: true  # HW acceleration

  # Advanced
  ENCODER_PRESET: ultrafast   # x264 preset
  KEYFRAME_INTERVAL: 30       # Keyframe every N frames
```

### GStreamer Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ENABLE` | bool | false | Enable GStreamer output |
| `DEST_HOST` | string | - | Destination IP address |
| `DEST_PORT` | int | 5600 | Destination UDP port |
| `BITRATE` | int | 2000 | Bitrate in kbps |
| `USE_HARDWARE_ENCODER` | bool | true | Use HW encoder if available |
| `ENCODER_PRESET` | string | ultrafast | x264 preset |
| `KEYFRAME_INTERVAL` | int | 30 | Keyframe interval |

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
  ENABLE: true

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
| `ENABLE` | bool | true | Enable OSD rendering |
| `SHOW_FPS` | bool | true | Display FPS counter |
| `SHOW_TIMESTAMP` | bool | true | Display timestamp |
| `FONT_SCALE` | float | 0.5 | Text size multiplier |
| `MARGIN` | int | 10 | Edge margin in pixels |

## Streaming Optimizer

```yaml
Streaming:
  # Optimization
  ENABLE_OPTIMIZER: true
  CACHE_SIZE: 3               # Quality levels to cache
  QUALITY_LEVELS: [90, 70, 50]

  # Adaptive quality
  ADAPTIVE_QUALITY: true
  MIN_QUALITY: 30
  MAX_QUALITY: 95
  TARGET_BITRATE: 2000        # kbps
```

### Optimizer Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ENABLE_OPTIMIZER` | bool | true | Enable frame caching |
| `QUALITY_LEVELS` | list | [90,70,50] | Preset quality levels |
| `ADAPTIVE_QUALITY` | bool | true | Auto-adjust quality |
| `TARGET_BITRATE` | int | 2000 | Target bitrate (kbps) |

## Example Configurations

### Dashboard Streaming

```yaml
FastAPI:
  ENABLE_HTTP_STREAM: true
  ENABLE_WEBSOCKET: true
  STREAM_QUALITY: 70
  STREAM_WIDTH: 640
  STREAM_HEIGHT: 480
  MAX_CLIENTS: 20

OSD:
  ENABLE: true
  SHOW_FPS: true
  SHOW_TRACKING_STATUS: true
```

### QGroundControl Integration

```yaml
GStreamer:
  ENABLE: true
  DEST_HOST: 192.168.1.10
  DEST_PORT: 5600
  BITRATE: 3000
  USE_HARDWARE_ENCODER: true
  ENCODER_PRESET: superfast

OSD:
  ENABLE: true
  SHOW_TELEMETRY: true
  SHOW_SAFETY_STATUS: true
```

### Low Bandwidth Streaming

```yaml
FastAPI:
  STREAM_QUALITY: 50
  STREAM_WIDTH: 320
  STREAM_HEIGHT: 240
  STREAM_FPS: 15

Streaming:
  ADAPTIVE_QUALITY: true
  MIN_QUALITY: 20
  TARGET_BITRATE: 500
```

### High Quality Recording

```yaml
FastAPI:
  STREAM_QUALITY: 95
  STREAM_WIDTH: 1920
  STREAM_HEIGHT: 1080
  STREAM_FPS: 30

OSD:
  ENABLE: false  # Clean frames for recording
```

## Accessing Streams

### HTTP MJPEG

```html
<img src="http://localhost:8000/video_feed" />
<img src="http://localhost:8000/video_feed?osd=true" />
<img src="http://localhost:8000/video_feed?quality=60" />
```

### WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/video_feed');
```

### QGroundControl

1. Open QGroundControl
2. Settings > Video
3. Source: UDP h.264 Video Stream
4. Port: 5600 (or configured port)
