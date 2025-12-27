# REST API Reference

Complete reference for PixEagle's FastAPI-based REST API.

## Base URL

```
http://localhost:8000
```

## Endpoints Overview

| Category | Endpoints | Description |
|----------|-----------|-------------|
| [Streaming](#streaming) | `/video_feed`, `/ws/video_feed` | Video streaming |
| [Telemetry](#telemetry) | `/telemetry/*`, `/status` | System data |
| [Commands](#commands) | `/commands/*` | Control operations |
| [Tracker](#tracker-api) | `/api/tracker/*` | Tracker management |
| [Follower](#follower-api) | `/api/follower/*` | Follower management |
| [Config](#configuration-api) | `/api/config/*` | Configuration |
| [Safety](#safety-api) | `/api/safety/*` | Safety settings |

---

## Streaming

### MJPEG Video Feed

```http
GET /video_feed
```

Returns multipart MJPEG stream.

**Usage:**
```html
<img src="http://localhost:8000/video_feed" />
```

### WebSocket Video

```http
WS /ws/video_feed
```

Binary WebSocket stream (JPEG frames).

**Client Example:**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/video_feed');
ws.binaryType = 'arraybuffer';
ws.onmessage = (event) => {
  const blob = new Blob([event.data], {type: 'image/jpeg'});
  img.src = URL.createObjectURL(blob);
};
```

---

## Telemetry

### Tracker Data

```http
GET /telemetry/tracker_data
```

**Response:**
```json
{
  "position_2d": [0.5, 0.3],
  "bbox": [100, 80, 200, 160],
  "confidence": 0.85,
  "is_tracking": true,
  "data_type": "POSITION_2D"
}
```

### Follower Data

```http
GET /telemetry/follower_data
```

**Response:**
```json
{
  "control_type": "velocity_body_offboard",
  "setpoints": {
    "vel_body_fwd": 2.5,
    "vel_body_right": 0.0,
    "vel_body_down": 0.0,
    "yawspeed_deg_s": 15.0
  },
  "offboard_active": true
}
```

### System Status

```http
GET /status
```

**Response:**
```json
{
  "tracking_active": true,
  "offboard_active": false,
  "smart_mode": true,
  "circuit_breaker_active": true,
  "video_source": "0",
  "fps": 30.0
}
```

---

## Commands

### Start Tracking

```http
POST /commands/start_tracking
Content-Type: application/json

{
  "x": 100,
  "y": 80,
  "width": 100,
  "height": 80
}
```

### Stop Tracking

```http
POST /commands/stop_tracking
```

### Smart Click (Click-to-Track)

```http
POST /commands/smart_click
Content-Type: application/json

{
  "x": 0.5,
  "y": 0.3
}
```

Coordinates are normalized (0-1).

### Toggle Smart Mode

```http
POST /commands/toggle_smart_mode
```

### Start/Stop Offboard

```http
POST /commands/start_offboard_mode
POST /commands/stop_offboard_mode
```

### Redetect Target

```http
POST /commands/redetect
```

### Quit Application

```http
POST /commands/quit
```

---

## Tracker API

### Get Available Trackers

```http
GET /api/tracker/available
```

**Response:**
```json
{
  "trackers": [
    {
      "name": "csrt",
      "display_name": "CSRT (Discriminative)",
      "description": "OpenCV CSRT tracker"
    },
    {
      "name": "kcf",
      "display_name": "KCF (Fast)",
      "description": "Kernelized Correlation Filter"
    }
  ]
}
```

### Get Current Tracker

```http
GET /api/tracker/current
```

### Switch Tracker

```http
POST /api/tracker/switch
Content-Type: application/json

{
  "tracker_type": "csrt"
}
```

### Get Tracker Schema

```http
GET /api/tracker/schema
```

---

## Follower API

### Get Available Profiles

```http
GET /api/follower/profiles
```

**Response:**
```json
{
  "profiles": [
    {
      "name": "mc_velocity_offboard",
      "display_name": "MC Velocity Offboard",
      "control_type": "velocity_body_offboard"
    }
  ]
}
```

### Get Current Profile

```http
GET /api/follower/current-profile
```

### Switch Profile

```http
POST /api/follower/switch-profile
Content-Type: application/json

{
  "profile": "mc_velocity_offboard"
}
```

### Get Setpoints with Status

```http
GET /api/follower/setpoints-status
```

**Response:**
```json
{
  "setpoints": {
    "vel_body_fwd": {
      "value": 2.5,
      "clamped": false,
      "limit": 8.0
    }
  },
  "circuit_breaker": {
    "active": true,
    "commands_blocked": true
  }
}
```

---

## Configuration API

### Get Current Config

```http
GET /api/config/current
GET /api/config/current/{section}
```

### Get Schema

```http
GET /api/config/schema
GET /api/config/schema/{section}
```

### Update Parameter

```http
PUT /api/config/{section}/{parameter}
Content-Type: application/json

{
  "value": 0.7
}
```

**Response:**
```json
{
  "valid": true,
  "status": "valid",
  "errors": [],
  "warnings": ["Restart required for this change"]
}
```

### Get Diff from Default

```http
GET /api/config/diff
```

### Revert to Default

```http
POST /api/config/revert
POST /api/config/revert/{section}
POST /api/config/revert/{section}/{parameter}
```

### Backup History

```http
GET /api/config/history
```

### Restore Backup

```http
POST /api/config/restore/{backup_id}
```

### Export/Import

```http
GET /api/config/export
POST /api/config/import
Content-Type: application/json

{
  "data": {...},
  "merge_mode": "merge"
}
```

---

## Safety API

### Get Safety Config

```http
GET /api/safety/config
```

**Response:**
```json
{
  "limits": {
    "max_velocity_forward": 8.0,
    "max_velocity_lateral": 5.0,
    "max_velocity_vertical": 3.0,
    "max_yaw_rate": 45.0
  },
  "circuit_breaker": {
    "active": true
  }
}
```

### Get Follower Limits

```http
GET /api/safety/limits/{follower_name}
```

---

## Circuit Breaker API

### Get Status

```http
GET /api/circuit-breaker/status
```

### Toggle

```http
POST /api/circuit-breaker/toggle
```

### Get Statistics

```http
GET /api/circuit-breaker/statistics
```

---

## Error Responses

### 400 Bad Request

```json
{
  "detail": "Invalid parameter value"
}
```

### 404 Not Found

```json
{
  "detail": "Resource not found"
}
```

### 429 Rate Limited

```json
{
  "detail": "Rate limit exceeded. Retry after 30s"
}
```

### 500 Internal Error

```json
{
  "detail": "Internal server error"
}
```

---

## Rate Limiting

Configuration endpoints are rate-limited:
- **Limit**: 60 requests per minute
- **Scope**: Per client IP

Headers returned:
```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1704067200
```
