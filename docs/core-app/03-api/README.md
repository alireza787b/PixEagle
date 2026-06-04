# REST API Reference

Complete reference for PixEagle's FastAPI-based REST API.

## Base URL

```
http://127.0.0.1:5077
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
<img src="http://127.0.0.1:5077/video_feed" />
```

### WebSocket Video

```http
WS /ws/video_feed
```

Binary WebSocket stream (JPEG frames).

**Client Example:**
```javascript
const ws = new WebSocket('ws://127.0.0.1:5077/ws/video_feed');
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
  "smart_mode_active": false,
  "tracking_started": true,
  "segmentation_active": false,
  "following_active": true,
  "offboard_commander": {
    "exists": true,
    "running": true,
    "health_state": "running",
    "consecutive_failures": 0,
    "command_failure_threshold": 3,
    "failure_policy_triggered": false
  },
  "offboard_commander_failure": null,
  "mavlink_telemetry": {
    "enabled": true,
    "status": "fresh",
    "connection_state": "connected",
    "fresh": true,
    "last_success_age_s": 0.12,
    "stale_timeout_s": 2.0,
    "request_timeout_s": 5.0,
    "request_retries": 0,
    "connection_error_count": 0,
    "last_error": null,
    "endpoint": "http://127.0.0.1:8088"
  },
  "video_status": "connected",
  "smart_tracker_runtime": null
}
```

`mavlink_telemetry` is transport/request freshness for MAVLink2REST. It is
controlled by `MAVLINK_REQUEST_TIMEOUT_S`, `MAVLINK_REQUEST_RETRIES`, and
`MAVLINK_STALE_TIMEOUT_S`; it does not by itself prove PX4-in-loop follower
behavior.

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

### Start Offboard

```http
POST /api/v1/actions/offboard-start
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "start_following",
  "confirm": true,
  "idempotency_key": "operator-start-001"
}
```

The typed action resource records local PixEagle execution and following-state
before/after. PX4-observed Offboard mode and setpoint cadence still require
separate SITL, HIL, or field evidence artifacts.

Action semantics:

- `dry_run=true` returns `200` with `status=validated` and executes nothing.
- Missing `confirm=true` returns a structured `409` error envelope.
- Confirmed mutations require `idempotency_key`; missing keys return a
  structured `409` and do not execute.
- Confirmed first execution returns `202` with `executed=true`.
- Repeating the same confirmed `idempotency_key` returns `200` with
  `idempotent_replay=true` and does not execute again.
- `GET /api/v1/actions/{action_id}` returns the in-process action record;
  records are process-local and bounded, not durable flight logs.

### Operator Abort

```http
POST /api/v1/actions/operator-abort
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "abort_following",
  "confirm": true,
  "idempotency_key": "operator-abort-001"
}
```

### Legacy Start/Stop Offboard

```http
POST /commands/start_offboard_mode
POST /commands/stop_offboard_mode
POST /commands/cancel_activities
```

The legacy start/cancel routes execute immediately for backward compatibility
and include an `action_audit` pointer to the process-local action record. New
operator, SITL, MCP, and agent integrations should use `/api/v1/actions/*`
because the legacy routes do not provide confirmation, dry-run, or idempotency
request fields.

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
  },
  "command_publication": {
    "source": "offboard_commander",
    "commands_sent_to_px4": true,
    "last_intent_fresh": true,
    "failsafe_defaults_active": false,
    "offboard_commander": {
      "running": true,
      "health_state": "running",
      "consecutive_failures": 0,
      "command_failure_threshold": 3,
      "failure_policy_triggered": false
    }
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
