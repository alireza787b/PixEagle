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
| [Telemetry](#telemetry) | `/telemetry/*`, `/status`, `/api/v1/runtime/status`, `/api/v1/following/status`, `/api/v1/following/telemetry`, `/api/v1/telemetry/health` | System data and typed health |
| [Commands](#commands) | `/commands/*` | Control operations |
| [Tracker](#tracker-api) | `/api/v1/tracking/runtime-status`, `/api/tracker/*` | Typed tracker runtime status and legacy tracker management |
| [Follower](#follower-api) | `/api/v1/following/status`, `/api/v1/following/telemetry`, `/api/follower/*` | Typed following status/telemetry and legacy follower management |
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
  "bounding_box": [0.4, 0.4, 0.2, 0.3],
  "center": [0.5, 0.55],
  "timestamp": "2026-06-04T12:00:00.000000",
  "tracker_started": false,
  "has_output": true,
  "usable_for_following": false,
  "data_is_stale": true,
  "tracker_data": {
    "data_type": "gimbal_angles",
    "tracker_id": "gimbal_tracker",
    "tracking_active": false,
    "has_output": true,
    "usable_for_following": false,
    "data_is_stale": true,
    "confidence": 0.85,
    "timestamp": 1717502400.0,
    "angular": [12.0, -4.0, 0.0],
    "gimbal_tracking_active": false,
    "tracking_status": "TARGET_LOST",
    "connection_status": "receiving"
  }
}
```

`tracker_started`/`tracking_active` remain compatibility booleans. Consumers
that decide whether output can drive follower control must also inspect
`has_output`, `usable_for_following`, and `data_is_stale`. External trackers can
produce visible diagnostic output while target tracking is inactive or stale;
the dashboard treats that as visible output, not a usable target.

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

`/telemetry/follower_data` is the legacy detailed follower telemetry payload.
Consumers that only need active/inactive/degraded following state should use the
typed following status resource below.

### Following Status

```http
GET /api/v1/following/status
```

Typed process-local following status for dashboard/API/MCP consumers. Use this
route for nav chips, automation readiness, and following-state checks instead
of parsing `/telemetry/follower_data`.

**Response:**
```json
{
  "schema_version": 1,
  "source": "following_runtime",
  "status": "active",
  "consumer_guidance": "following_active",
  "following_active": true,
  "profile": {
    "configured_mode": "gm_velocity_vector",
    "current_mode": "gm_velocity_vector",
    "profile_valid": true,
    "display_name": "Gimbal Velocity Vector",
    "control_type": "velocity_body_offboard",
    "available_fields": [
      "vel_body_fwd",
      "vel_body_right",
      "vel_body_down",
      "yawspeed_deg_s"
    ],
    "manager_type": "Follower",
    "follower_type": "GMVelocityVectorFollower",
    "follower_instance_present": true
  },
  "command_publication": {
    "source": "offboard_commander",
    "exists": true,
    "running": true,
    "task_active": true,
    "health_state": "running",
    "command_publication_source": "offboard_commander",
    "sends_mavsdk_commands": true,
    "last_intent_fresh": true,
    "failsafe_defaults_active": false,
    "successful_publishes": 3,
    "failed_publishes": 0,
    "consecutive_failures": 0,
    "local_successful_publish_observed": true,
    "offboard_commander": {
      "running": true,
      "task_active": true,
      "health_state": "running"
    }
  },
  "health_issues": [],
  "reason": null,
  "claim_boundary": "PixEagle process-local following state and command-publication health only; not PX4, SITL, HIL, field, or follower-response proof.",
  "timestamp": 1717200000.0
}
```

`status` is one of `inactive`, `active`, `degraded`, or `unavailable`.
`consumer_guidance` is one of `inactive`, `following_active`,
`operator_attention`, or `unavailable`. The route reports
`degraded/operator_attention` if local following is active without a valid
follower profile/instance, or if the Offboard commander snapshot reports
failure, stopped/non-running publication, inactive task, stale command intent,
active failsafe defaults, or missing/unknown command-publication fields. It also
flags inactive local following while the commander still appears to be running.
`local_successful_publish_observed` is a PixEagle-local MAVSDK publication
counter signal only; it is not PX4-observed Offboard or vehicle-response proof.

This route does not replace detailed setpoint/follower telemetry yet; richer
widgets may continue using `/telemetry/follower_data` until a separate typed
follower telemetry contract exists.

### Following Telemetry

```http
GET /api/v1/following/telemetry
```

Typed process-local follower telemetry and setpoint snapshot for dashboard/API/
MCP consumers. Use this route for current setpoint values and follower-card
diagnostics instead of parsing `/telemetry/follower_data`.

**Response:**
```json
{
  "schema_version": 1,
  "source": "following_telemetry",
  "status": "active",
  "consumer_guidance": "following_active",
  "following_active": true,
  "profile": {
    "configured_mode": "gm_velocity_vector",
    "current_mode": "gm_velocity_vector",
    "profile_valid": true,
    "display_name": "Gimbal Velocity Vector",
    "control_type": "velocity_body_offboard",
    "available_fields": [
      "vel_body_fwd",
      "vel_body_right",
      "vel_body_down",
      "yawspeed_deg_s"
    ],
    "manager_type": "Follower",
    "follower_type": "GMVelocityVectorFollower",
    "follower_instance_present": true
  },
  "fields": {
    "vel_body_fwd": 1.25,
    "vel_body_right": -0.5,
    "vel_body_down": 0.0,
    "yawspeed_deg_s": 3.0
  },
  "field_source": "active_follower",
  "last_command_intent": {
    "profile_name": "gm_velocity_vector",
    "control_type": "velocity_body_offboard",
    "source": "follower",
    "reason": "target_update",
    "created_at_utc": "2026-06-06T00:00:00Z",
    "fields": {
      "vel_body_fwd": 1.25,
      "vel_body_right": -0.5,
      "vel_body_down": 0.0,
      "yawspeed_deg_s": 3.0
    }
  },
  "target_loss_handler": {
    "state": "ACTIVE"
  },
  "safety_systems": {
    "safety_violations_count": 0
  },
  "performance": {
    "success_rate_percent": 100.0
  },
  "circuit_breaker": {
    "active": false,
    "status": "LIVE_MODE"
  },
  "circuit_breaker_active": false,
  "command_publication": {
    "source": "offboard_commander",
    "exists": true,
    "running": true,
    "task_active": true,
    "health_state": "running",
    "last_intent_fresh": true,
    "failsafe_defaults_active": false,
    "successful_publishes": 4,
    "local_successful_publish_observed": true
  },
  "flight_mode": 393216,
  "flight_mode_text": "Offboard",
  "is_offboard": true,
  "telemetry_enabled": true,
  "legacy_payload_keys": [
    "fields",
    "flight_mode",
    "profile_name"
  ],
  "health_issues": [],
  "reason": null,
  "claim_boundary": "PixEagle process-local follower telemetry and setpoint snapshots only; not PX4-observed Offboard, SITL, HIL, field, or vehicle-response proof.",
  "timestamp": 1717200000.0
}
```

`field_source` is one of `active_follower`, `legacy_telemetry`,
`schema_profile`, or `unavailable`. Live setpoint-handler fields are preferred;
legacy follower telemetry fields are used only as a compatibility fallback.
`local_successful_publish_observed` is local PixEagle publication evidence, not
PX4-observed Offboard or vehicle-response proof.

Dashboard detailed follower status cards consume this route through the
endpoint registry and fall back to `/telemetry/follower_data` only when the
typed route is missing during rolling updates. The Follower visualization page
still uses legacy telemetry arrays for historical plots until a separate typed
history contract exists.

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

`mavlink_telemetry` is the legacy flat compatibility summary for
MAVLink2REST transport/request freshness. It is controlled by
`MAVLINK_REQUEST_TIMEOUT_S`, `MAVLINK_REQUEST_RETRIES`, and
`MAVLINK_STALE_TIMEOUT_S`; it does not by itself prove PX4-in-loop follower
behavior. New API/MCP/dashboard consumers should prefer the typed health
resource below because it separates latest request result, last successful
sample freshness, and cached payload availability.

### Runtime Status

```http
GET /api/v1/runtime/status
```

Typed PixEagle process-local runtime status for dashboard/API/MCP consumers.
Use this route for mode flags instead of parsing the flat `/status` payload.

**Response:**
```json
{
  "schema_version": 1,
  "source": "pixeagle_runtime",
  "status": "active",
  "consumer_guidance": "vision_active",
  "modes": {
    "smart_mode_active": true,
    "tracking_started": true,
    "segmentation_active": false,
    "following_active": false
  },
  "subsystems": {
    "video_status": "connected",
    "offboard_commander": {
      "health_state": "running"
    },
    "offboard_commander_failure": null,
    "px4_connection": null,
    "mavlink_telemetry": {
      "status": "fresh"
    },
    "smart_tracker_runtime": null
  },
  "reason": null,
  "claim_boundary": "PixEagle process-local runtime and subsystem snapshots only; not PX4, SITL, HIL, field, or follower-response proof.",
  "timestamp": 1717200000.0
}
```

`status` is one of `idle`, `active`, `degraded`, or `unavailable`.
`consumer_guidance` is one of `idle`, `vision_active`, `following_active`,
`operator_attention`, or `unavailable`. Commander failures force
`degraded/operator_attention`. If local following is active while the Offboard
commander reports stopped/non-running publication, inactive task, stale command
intent, active failsafe defaults, or missing/unknown command-publication fields,
the route also reports `degraded/operator_attention`. Otherwise active
smart/tracking/segmentation state reports `vision_active`, and active following
reports `following_active`.

This route is intentionally narrower than the MDS
`/api/v1/system/runtime-status` admin posture surface. PixEagle
`/api/v1/runtime/status` reports local mode/subsystem snapshots and does not
claim PX4-observed Offboard, SITL, HIL, field, or follower-response success.

### MAVLink Telemetry Health

```http
GET /api/v1/telemetry/health
```

**Response:**
```json
{
  "schema_version": 1,
  "source": "mavlink2rest",
  "enabled": true,
  "status": "degraded",
  "consumer_guidance": "degraded_latest_request_failed",
  "transport": {
    "state": "error",
    "latest_request_ok": false,
    "latest_request_result": "failure",
    "latest_request_age_s": 0.05,
    "last_error": "Connection timeout - simulated",
    "error_count": 1,
    "validation_timeout_active": false,
    "request_timeout_s": 5.0,
    "request_retries": 0,
    "endpoint": "http://127.0.0.1:8088"
  },
  "request_freshness": {
    "fresh": true,
    "last_success_age_s": 0.2,
    "stale_timeout_s": 2.0,
    "last_success_monotonic_available": true
  },
  "payload": {
    "has_payload": true,
    "sample_count": 2,
    "available_keys": ["arm_status", "flight_mode"],
    "flight_mode": 393216,
    "arm_status": "Armed",
    "fresh": true,
    "payload_age_s": 0.2
  },
  "claim_boundary": "PixEagle local MAVLink2REST client health only; not PX4, SITL, HIL, field, or follower-response proof.",
  "timestamp": 1717200000.0
}
```

`status=degraded` means the cached payload may still be inside the freshness
window while the newest MAVLink2REST request failed. Consumers that decide
whether telemetry is usable should inspect both `transport.latest_request_ok`
and `request_freshness.fresh`. When telemetry is disabled, freshness fields are
forced false even if PixEagle still has cached payload for diagnostics. Server
failures use the typed `/api/v1` error envelope with `code`, `detail`, `path`,
`request_id`, and `timestamp`.

Dashboard clients consume this route through `useTelemetryHealth()` and show a
compact operational chip: `Telemetry: Usable`, `Telemetry: Degraded`,
`Telemetry: Stale`, `Telemetry: Unavailable`, `Telemetry: Disabled`, or
`Telemetry: Connecting`. The dashboard normalizes payload fields such as
`flight_mode` and `arm_status` into display labels while keeping the raw values
available for diagnostics.

Dashboard smart-mode polling uses `/api/v1/runtime/status` through the endpoint
registry and reads `modes.smart_mode_active`. A top-level
`smart_mode_active` payload read remains only as a compatibility fallback.
During rolling updates, the hook falls back to legacy `/status` only when the
typed runtime route is missing, and it ignores stale out-of-order responses.

Dashboard follower nav/status polling uses `/api/v1/following/status` through
the endpoint registry and reads `following_active`. Detailed follower-card
telemetry uses `/api/v1/following/telemetry`. During rolling updates, these
hooks fall back to legacy `/telemetry/follower_data` only when the matching
typed route is missing, and they ignore stale out-of-order responses. The
Follower visualization page still uses `/telemetry/follower_data` for
historical arrays until a typed history contract is migrated.

Dashboard tracker status uses `/api/v1/tracking/runtime-status` through the
endpoint registry and normalizes tracker output into distinct operator states:
`Tracking: Active`, `Tracking: Visible`, `Tracking: Stale`,
`Tracking: Not Usable`, `Tracking: No Output`, `Tracking: Checking`, or
`Tracking: Unavailable`. The follow controls require tracker output to be fresh
and marked `usable_for_following=true` before enabling autonomous following.
Legacy `/api/tracker/current-status` remains a compatibility route with the
same top-level runtime flags plus schema-driven `fields` for tracker data
display.

### Tracker Runtime Status

```http
GET /api/v1/tracking/runtime-status
```

**Response:**
```json
{
  "schema_version": 1,
  "source": "tracker_runtime",
  "status": "visible_output",
  "consumer_guidance": "diagnostic_only",
  "has_output": true,
  "active_tracking": false,
  "usable_for_following": false,
  "data_is_stale": false,
  "reason": "Tracker output is visible, but active target tracking is not confirmed.",
  "configured_tracker": "GimbalTracker",
  "active_tracker": "gimbal_tracker",
  "tracker_id": "gimbal_tracker",
  "tracker_type": "GimbalTracker",
  "data_type": "GIMBAL_ANGLES",
  "provider": "topotek_sip_udp",
  "protocol": "sip_udp",
  "connection_status": "receiving",
  "tracking_status": "TARGET_LOST",
  "target_count": 0,
  "selected_target_id": null,
  "output_fields": ["angular"],
  "smart_mode_active": false,
  "following_active": false,
  "claim_boundary": "PixEagle local tracker runtime status only; not PX4, SITL, HIL, field, or follower-response proof.",
  "timestamp": 1717502400.0
}
```

`active_tracking=true` only means the tracker reports an active target.
Follower-control consumers must use `usable_for_following=true`, which also
requires output presence and non-stale data. Custom trackers must set
`usable_for_following=true` explicitly in `raw_data` or `metadata`; PixEagle
does not infer follower usability from active output alone. `status=visible_output`
is useful for diagnostics, not for autonomous following. `status=stale_output`
and `status=not_usable` must be treated as fail-closed for Offboard/follower
entry. The typed route uses the `/api/v1` structured error envelope on server
failures.

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

Start requests fail closed before `connect_px4()` if tracker output is absent,
stale, or not marked `usable_for_following=true`. This guard applies to both
the typed action resource and the legacy compatibility route below.

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
