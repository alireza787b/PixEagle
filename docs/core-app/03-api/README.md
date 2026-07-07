# REST API Reference

Complete reference for PixEagle's FastAPI-based REST API.

## Base URL

```
http://127.0.0.1:5077
```

The checked-in backend is local-only and uses an explicit loopback CORS
allowlist. Loopback clients run through `API_AUTH_MODE=local_compat` by
default only when the immediate socket peer is loopback and no proxy-forwarded
client identity headers are present. HTTP `Host` is not transport proof.
Non-loopback API clients require scoped bearer tokens from an external token
file or explicit `API_AUTH_MODE=browser_session` with an external hashed user
file. See the [API exposure boundary](../../apis/api-exposure-boundary.md).

PixEagle also has a complete declarative
[API security policy](../../apis/api-security-policy.md) for route access,
scopes, bearer-token treatment, local compatibility, session CSRF enforcement,
audit treatment, and default-deny coverage. Remote browser operation is not
approved until TLS/operator deployment hardening, adversarial auth/media tests,
and evidence gates are complete.

## MCP Readiness Boundary

Some typed `/api/v1` routes are documented as suitable for future API/MCP
consumers because they have stable schemas and operation IDs. That does not mean
PixEagle currently exposes callable MCP tools. The generated candidate inventory
under `docs/agent-context/generated/` is review coverage only, not MCP
execution, and every candidate remains unpromoted until registry, policy, docs,
tests, and reviewer gates are complete. Each generated candidate has a
`review_disposition` of `approved_for_review_only`, `blocked`, or `deferred`;
those dispositions are documentation-stage governance only and never imply
runtime MCP `tools/list` or `tools/call` exposure.

## Endpoints Overview

| Category | Endpoints | Description |
|----------|-----------|-------------|
| [Auth](#auth) | `/api/v1/auth/session`, `/api/v1/auth/login`, `/api/v1/auth/logout` | Browser-session status and lifecycle |
| [System](#system-about) | `/api/v1/system/about` | Typed version, repository, local git, backend runtime, and update-status metadata |
| [Validation](#sih-validation-status) | `/api/v1/sitl/status` | SIH Dev/Training plan metadata, latest manifest summary, and operator terminal commands |
| [Streaming](#streaming) | `/video_feed`, `/ws/video_feed`, `/api/v1/streams/media-health` | Video streaming and typed media health |
| [Telemetry](#telemetry) | `/telemetry/*`, `/status`, `/api/v1/runtime/status`, `/api/v1/following/status`, `/api/v1/following/telemetry`, `/api/v1/tracking/telemetry`, `/api/v1/telemetry/health` | System data and typed health |
| [Logs](#logs) | `/api/v1/logs/status`, `/api/v1/logs/sessions`, `/api/v1/logs/sessions/{run_id}`, `/api/v1/logs/sessions/{run_id}/export`, `/api/v1/logs/frontend-errors` | Process-local runtime log sessions, sanitized evidence exports, and bounded browser error reports |
| [Actions](#commands) | `/api/v1/actions/*` | Typed, confirmed operator/control action resources |
| Process admin | `/commands/quit` | Local-only process administration, not an operator control API |
| [Tracker](#tracker-api) | `/api/v1/tracking/*`, `/api/v1/actions/tracker-switch`, `/api/v1/actions/tracker-restart`, selected `/api/tracker/*` compatibility reads/diagnostics | Typed tracker state/actions plus remaining legacy compatibility routes |
| [Follower](#follower-api) | `/api/v1/following/status`, `/api/v1/following/telemetry`, `/api/follower/*` | Typed following status/telemetry and legacy follower management |
| [Config](#configuration-api) | `/api/config/*` | Configuration |
| [Safety](#safety-api) | `/api/safety/*` | Safety settings |

---

## Auth

### Session Status

```http
GET /api/v1/auth/session
```

Returns the current browser-session state. This route is a public bootstrap
route; it does not expose the HttpOnly session cookie value.

### Login

```http
POST /api/v1/auth/login
Content-Type: application/json

{"username": "operator", "password": "********"}
```

`API_AUTH_MODE=browser_session` and `API_SESSION_USER_FILE` must be configured.
Successful login sets the HttpOnly session cookie and returns the CSRF token
for browser mutations. Failed attempts are process-locally throttled.

### Logout

```http
POST /api/v1/auth/logout
X-PixEagle-CSRF: <csrf-token>
```

Revokes the current browser session. Logout requires a valid session cookie and
session-bound CSRF.

## Logs

Runtime log APIs expose process-local PixEagle runtime sessions for operator
debugging and AI-agent review. They include structured backend logs and,
when launched through `scripts/run.sh`, launcher-piped output for started components
such as dashboard and sidecars. They require `debug:read`; ordinary
viewer/operator browser sessions do not receive that scope. They do not prove
PX4, SITL, HIL, QGC receiver, field, or real-aircraft behavior. Security-audit
records are intentionally kept separate from runtime logs.

Dashboard browsers can also submit bounded frontend runtime error reports to a
fixed `frontend` log component. That report route requires `runtime:report` and
session CSRF but does not grant log-read access. Query/hash values are stripped
client-side, payloads are bounded by the typed request model, and the backend
applies the runtime redaction path again before storage.

### Runtime Log Status

```http
GET /api/v1/logs/status
```

Returns whether runtime logging is enabled, the active run ID, base directory,
active session directory, current manifest, and the claim boundary.

### Runtime Log Sessions

```http
GET /api/v1/logs/sessions?limit=50
```

Returns retained runtime sessions newest first. `limit` is bounded by the API.

### Runtime Log Entries

```http
GET /api/v1/logs/sessions/{run_id}?component=backend&level=WARNING&limit=200&offset=0
```

Returns filtered JSONL entries for one component. Supported filters include:

- `component` - defaults to `backend`;
- `level` - minimum log level, for example `WARNING` or `ERROR`;
- `limit` - bounded result count;
- `offset` - number of matching entries to skip;
- `since` - optional timestamp lower bound.

The response includes `next_offset`, `has_more`, `matched_total`, and `tail`
metadata. Normal reads use `offset` as a matching-entry cursor and return
`next_offset` for the next bounded poll. `has_more` is true when the response
stopped at `limit`; `matched_total` is exact only when the reader reached the
end of the current component log or when `tail=true` is used.
Reads include the current component file plus PixEagle's retained single
rotated backup (`<component>.jsonl.1`) in chronological order, so normal
single-rotation events do not invalidate a cursor. If a client polls so slowly
that entries age out of the retained current-plus-backup window, those expired
entries are no longer recoverable from this API.

For operator live debugging, request the latest bounded window first:

```http
GET /api/v1/logs/sessions/{run_id}?component=backend&limit=200&tail=true
```

With `tail=true`, PixEagle returns the last matching entries and sets
`next_offset` to the exact current matching-entry count. The dashboard Live tail
switch then polls the same route with `offset=<next_offset>` and appends any
new entries. This is an authenticated bounded polling contract, not a
long-lived SSE/WebSocket log stream.

Run IDs and component names are path-safe identifiers only. Invalid identifiers
or missing sessions return structured `/api/v1` errors.

Structured backend entries include Python source fields such as `module`,
`function`, and `line`. Pane-captured component entries may instead include
`stream` and `source`.

### Runtime Log Export

```http
GET /api/v1/logs/sessions/{run_id}/export
```

Returns a sanitized `application/gzip` tarball for one runtime session. The
bundle contains `README.txt`, the session `manifest.json`, sanitized component
JSONL files, and `export_manifest.json` with skipped malformed-line counts.
Credential-like values are redacted before archive output. Response headers
include the run ID, bundle size, SHA-256 digest, and runtime-log claim boundary.
The CORS policy exposes these headers so the dashboard can show the downloaded
bundle metadata:

- `Content-Disposition`
- `X-PixEagle-Run-ID`
- `X-PixEagle-Log-Export-Sha256`
- `X-PixEagle-Log-Export-Size`
- `X-PixEagle-Claim-Boundary`

The export route requires `debug:read` like the other runtime log read routes.
It is process-local PixEagle evidence only; it does not prove PX4, SITL, HIL,
QGC receiver, field, follower-response, or real-aircraft behavior.

The dashboard download action displays filename, run ID, size, SHA-256, and
claim boundary after a successful export. PixEagle does not import or replay
runtime log bundles in the live UI yet; any future offline bundle viewer must
be a typed evidence contract with schema/version checks and redaction rules.

### Frontend Error Report

```http
POST /api/v1/logs/frontend-errors
X-PixEagle-CSRF: <csrf-token>
Content-Type: application/json
```

Accepts one bounded dashboard browser error report and appends it to
`components/frontend.jsonl` for the active runtime session.

```json
{
  "source": "dashboard",
  "level": "ERROR",
  "name": "TypeError",
  "message": "Dashboard render failed",
  "stack": "stack trace, redacted before storage",
  "url": "http://operator-host/dashboard",
  "route": "/dashboard",
  "user_agent": "browser user agent",
  "context": {"kind": "window_error"}
}
```

The response acknowledges only the active run and component. It does not echo
the stored stack or context back to the browser.

## Streaming

### MJPEG Video Feed

```http
GET /video_feed
```

Returns multipart MJPEG stream.

This route is classified as media read access. Checked-in defaults allow
same-host loopback clients; non-loopback clients need explicit exposure config
and scoped `media:read` credentials.

**Usage:**
```html
<img src="http://127.0.0.1:5077/video_feed" />
```

### WebSocket Video

```http
WS /ws/video_feed
```

WebSocket stream with one JSON metadata message followed by one binary JPEG
message for each frame.

Browser WebSocket clients must present an allowlisted `Origin`. Native
same-host loopback clients may omit `Origin`; remote clients still require
reviewed exposure config and scoped `media:read` credentials before accept.

**Client Example:**
```javascript
const ws = new WebSocket('ws://127.0.0.1:5077/ws/video_feed');
ws.binaryType = 'arraybuffer';
ws.onmessage = (event) => {
  if (typeof event.data === 'string') {
    const metadata = JSON.parse(event.data);
    console.log('Frame metadata:', metadata.frame_id, metadata.quality);
    return;
  }
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

New consumers should use `GET /api/v1/tracking/catalog` for tracker catalog
metadata, `GET /api/v1/tracking/runtime-status` for readiness, and
`GET /api/v1/tracking/telemetry` for current tracker geometry. Legacy
`GET /api/tracker/current-status` and `GET /api/tracker/output` are retired.

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
New consumers should use the typed following status and telemetry resources
below. The legacy route remains for compatibility and rolling-update fallback
while dashboard/API clients are migrated.

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

This route is for state/readiness checks. Consumers that need current setpoint
values should use `GET /api/v1/following/telemetry`.

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

Dashboard detailed follower status cards and the Follower visualization page's
follower-history snapshots consume this route through the endpoint registry and
fall back to `/telemetry/follower_data` only when the typed route is missing
during rolling updates. The dashboard normalizer exposes `fields` and legacy
top-level aliases such as `vel_x`/`vel_y` for existing chart components.
Tracker center/bounding-box plots on the Follower visualization page consume
`GET /api/v1/tracking/telemetry`, with legacy `/telemetry/tracker_data` fallback
only when the typed tracker telemetry route is missing.

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

### System About

```http
GET /api/v1/system/about
```

Typed PixEagle version, repository, local git, backend runtime, and update-status
metadata for dashboard/API consumers and future MCP candidate review. This route
is read-only and uses the `system:read` scope. It never runs `git fetch`,
`git pull`, service restart, or update checks.

**Response:**
```json
{
  "schema_version": 1,
  "source": "pixeagle_system_about",
  "version": "3.2.1",
  "repository": {
    "name": "PixEagle",
    "url": "https://github.com/alireza787b/PixEagle",
    "docs_url": "https://github.com/alireza787b/PixEagle/tree/main/docs"
  },
  "git": {
    "available": true,
    "commit": "abc1234",
    "full_commit": "abc1234def5678",
    "branch": "codex/modernization",
    "date": "2026-07-05T12:34:56+00:00",
    "dirty": false,
    "describe": "v3.2.1-1-gabc1234"
  },
  "backend": {
    "status": "running",
    "restart_pending": false,
    "pid": 12345,
    "memory_mb": 180.4,
    "cpu_percent": 0.0,
    "video_available": true,
    "video_status": "active"
  },
  "runtime": {
    "uptime_seconds": 120.5,
    "started_at": "2026-07-05T12:32:56Z",
    "python_version": "3.12.3",
    "run_id": "pixeagle_20260705T123256Z_123456"
  },
  "update": {
    "supported": false,
    "state": "not_checked",
    "available": null,
    "checked_at": null,
    "reason": "Runtime About does not fetch, pull, restart, or prove update availability. Use the future guarded admin update workflow.",
    "safe_workflow": "PXE-0086 guarded fetch/fast-forward-only admin workflow"
  },
  "claim_boundary": "PixEagle process-local version, repository, and runtime metadata only; not proof of update availability, deployment state, PX4, SITL, HIL, field, follower-response, or vehicle-response behavior.",
  "timestamp": 1717200000.0
}
```

The dashboard About dialog consumes this typed route first and falls back to
legacy `/api/system/config` only when the typed route is missing during rolling
updates. Actual pull/update/restart behavior remains future guarded admin work
with dry-run, confirmation, rollback/evidence gates, and post-update validation.

### SIH Validation Status

```http
GET /api/v1/sitl/status
```

Read-only Dev/Training metadata for the maintained official-PX4 SIH profile.
The route requires `debug:read` and exists so operators can see the checked-in
L2 plan, latest local manifest summary, and exact terminal commands from the
dashboard without exposing validation injection controls as UI actions.

It does not start Docker, PX4, MavlinkAnywhere, MAVLink2REST, PixEagle,
Gazebo, X-Plane, or any route mutation. It does not prove PX4 behavior, SITL
runtime success, follower response, HIL, field, or real-aircraft success.

**Response excerpt:**
```json
{
  "schema_version": 1,
  "source": "pixeagle_sitl_validation_status",
  "default_artifact_root": "reports/sitl",
  "injections_enabled": false,
  "raw_injection_controls_exposed": false,
  "plan": {
    "name": "phase2_follower_validation",
    "level": "L2",
    "source": "tools/sitl_plans/phase2_follower_validation.json",
    "scenario_count": 9,
    "routing_provider": "mavlink-anywhere",
    "px4_model": "sihsim_quadx"
  },
  "commands": [
    {
      "label": "SIH dry run",
      "command": "make sitl-sih-dry-run",
      "mode": "dry_run",
      "starts_processes": false,
      "writes_artifacts": false
    },
    {
      "label": "Probe prepared stack",
      "command": "make sitl-sih-probe",
      "mode": "probe_only",
      "starts_processes": false,
      "writes_artifacts": true
    },
    {
      "label": "PX4-only SIH container",
      "command": "make sitl-sih-execute-px4",
      "mode": "execute_px4",
      "starts_processes": true,
      "writes_artifacts": true
    }
  ],
  "latest_run": {
    "available": true,
    "run_id": "20260604T123456Z-phase2_follower_validation",
    "result": "incomplete",
    "artifact_dir": "reports/sitl/20260604T123456Z-phase2_follower_validation",
    "scenario_execution_enabled": false,
    "control_actions_allowed": false,
    "missing_or_placeholder_count": 7
  },
  "claim_boundary": "PixEagle SIH/SITL training metadata and local evidence manifest summary only; not a runtime control surface, not a command execution result, and not proof of PX4 behavior, SITL runtime success, HIL, field, real-aircraft, follower-response, or vehicle-response behavior.",
  "timestamp": 1717200000.0
}
```

This route is generated in the API/MCP candidate inventory only as blocked
validation metadata. It is not a reviewed read-only MCP candidate and must not
be promoted into callable agent tooling without a separate SITL-only agent
policy, tests, and reviewer gate.

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

### Streaming Media Health

```http
GET /api/v1/streams/media-health
```

Typed process-local media transport health for dashboard/API/MCP consumers.
Use this route to inspect PixEagle's backend media state instead of scraping
legacy `/stats` or `/api/streaming/status` payloads.

The response reports:

- `status` and `consumer_guidance` for local media serving state;
- per-transport entries for HTTP MJPEG, JPEG WebSocket, WebRTC signaling, and
  GStreamer UDP/H.264 output;
- `Streaming.ENABLE_STREAMING`, disabled or zero-capacity transport state, and
  GStreamer UDP pipeline state without pretending UDP has client connections;
- frame-publisher freshness, `latest_frame_stale`, sent/dropped frame counters,
  cache size, and adaptive-quality state;
- exposure/auth posture without credential material.

The route requires `media:read`. Its `claim_boundary` is local-only: it does
not prove that a remote browser, QGC, WebRTC peer, GCS, PX4, SITL, HIL, or
field video path received usable media.

Dashboard follower nav/status polling uses `/api/v1/following/status` through
the endpoint registry and reads `following_active`. Detailed follower-card
telemetry and Follower visualization follower/setpoint history use
`/api/v1/following/telemetry`. During rolling updates, these hooks/pages fall
back to legacy `/telemetry/follower_data` only when the matching typed route is
missing, and they ignore stale out-of-order responses. Follower visualization
tracker center/bounding-box plots use `/api/v1/tracking/telemetry` with legacy
`/telemetry/tracker_data` fallback only when the typed tracker route is missing.

Dashboard tracker status uses `/api/v1/tracking/runtime-status` through the
endpoint registry and normalizes tracker output into distinct operator states:
`Tracking: Active`, `Tracking: Visible`, `Tracking: Stale`,
`Tracking: Not Usable`, `Tracking: No Output`, `Tracking: Checking`, or
`Tracking: Unavailable`. The follow controls require tracker output to be fresh
and marked `usable_for_following=true` before enabling autonomous following.
Tracker data display and the Tracker visualization page use
`/api/v1/tracking/telemetry` for current field values and geometry. Legacy
`/api/tracker/current-status` and `/api/tracker/output` are retired.

### Tracker Catalog

```http
GET /api/v1/tracking/catalog
```

Typed process-local tracker catalog/configuration metadata for dashboard/API
consumers. It combines schema-manager UI tracker entries with the built-in
compatibility tracker type list, includes configured/active tracker identity,
embeds current runtime status, includes `data_type_schemas` loaded from
`configs/tracker_schemas.yaml`, and carries a claim boundary. It does not prove
tracker runtime success, follower response, PX4, SITL, HIL, field, or
real-aircraft behavior.

For `ui_trackers`, `name` is the canonical tracker registry key that clients
send to `POST /api/v1/actions/tracker-switch`. `display_name` is the human UI
label. Do not send `display_name` as the action value.

The generated agent/MCP candidate for this route is non-callable, unregistered,
and blocked pending separate output-sensitivity, policy, operator-doc, and
independent review. Dashboard tracker selector/status consumers use this typed
catalog route for tracker catalog/current/config metadata. Dashboard tracker
switching now uses the typed
`POST /api/v1/actions/tracker-switch` action without a legacy mutation
fallback. Tracker restart now uses
`POST /api/v1/actions/tracker-restart` for new clients, while broader tracker
configuration mutation remains legacy pending typed action design and
compatibility retirement. The former legacy tracker catalog/config read aliases
are retired, so missing or unsupported typed catalog responses surface as
operator-visible errors instead of silently falling back to stale paths.

The former process-local tracker legacy compatibility counters were removed
with the final tracker diagnostic aliases. Deprecated
`GET /api/tracker/available`, `GET /api/tracker/current`,
`GET /api/tracker/available-types`, `GET /api/tracker/current-config`,
`GET /api/tracker/current-status`, `GET /api/tracker/output`,
`GET /api/tracker/schema`, `GET /api/tracker/capabilities`,
`POST /api/tracker/set-type`, compatibility `POST /api/tracker/switch`, and
compatibility `POST /api/tracker/restart` are retired. The typed catalog no
longer carries legacy compatibility counters because no public legacy tracker
diagnostic route remains registered.

**Response excerpt:**
```json
{
  "schema_version": 1,
  "source": "tracking_catalog",
  "status": "available",
  "consumer_guidance": "selectable",
  "configured_tracker": "CSRT",
  "active_tracker": "CSRTTracker",
  "smart_mode_active": false,
  "tracking_started": false,
  "tracking_active": false,
  "ui_trackers": [
    {
      "name": "CSRTTracker",
      "display_name": "CSRT",
      "source": "schema_manager",
      "supported_schemas": ["POSITION_2D"]
    }
  ],
  "tracker_types": {
    "SmartTracker": {
      "name": "SmartTracker",
      "smart_mode": true,
      "source": "builtin_compatibility",
      "available": true
    }
  },
  "data_type_schemas": {
    "POSITION_2D": {
      "name": "2D Position Tracking",
      "required_fields": ["position_2d"]
    }
  },
  "runtime_status": {
    "status": "no_output",
    "usable_for_following": false
  },
  "claim_boundary": "PixEagle process-local tracker catalog and configuration metadata only; not tracker runtime, PX4, SITL, HIL, field, follower-response, or vehicle-response proof."
}
```

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

### Tracker Telemetry

```http
GET /api/v1/tracking/telemetry
```

Typed process-local tracker telemetry and geometry snapshot for dashboard/API/
MCP consumers. Use this route for current tracker center, bounding box, and
plot history samples instead of parsing `/telemetry/tracker_data`.

**Response:**
```json
{
  "schema_version": 1,
  "source": "tracking_telemetry",
  "status": "active_usable",
  "consumer_guidance": "usable",
  "has_output": true,
  "active_tracking": true,
  "tracking_active": true,
  "tracker_started": true,
  "usable_for_following": true,
  "data_is_stale": false,
  "center": [0.2, -0.1],
  "bounding_box": [0.1, 0.2, 0.3, 0.4],
  "fields": {
    "data_type": "POSITION_2D",
    "tracker_id": "vision_tracker",
    "position_2d": [0.2, -0.1],
    "normalized_bbox": [0.1, 0.2, 0.3, 0.4],
    "confidence": 0.8
  },
  "tracker_data": {
    "data_type": "POSITION_2D",
    "tracker_id": "vision_tracker",
    "position_2d": [0.2, -0.1],
    "normalized_bbox": [0.1, 0.2, 0.3, 0.4],
    "confidence": 0.8
  },
  "field_source": "tracker_output",
  "runtime_status": {
    "schema_version": 1,
    "source": "tracker_runtime",
    "status": "active_usable",
    "consumer_guidance": "usable",
    "has_output": true,
    "active_tracking": true,
    "usable_for_following": true,
    "data_is_stale": false,
    "target_count": 0,
    "output_fields": ["position_2d", "normalized_bbox"],
    "smart_mode_active": true,
    "following_active": false,
    "claim_boundary": "PixEagle local tracker runtime status only; not PX4, SITL, HIL, field, or follower-response proof.",
    "timestamp": 1717200000.0
  },
  "legacy_payload_keys": [],
  "reason": null,
  "claim_boundary": "PixEagle process-local tracker telemetry and geometry snapshots only; not PX4, SITL, HIL, field, follower-response, or vehicle-response proof.",
  "timestamp": 1717200000.0
}
```

`field_source` is one of `tracker_output`, `legacy_telemetry`, or
`unavailable`. Live `TrackerOutput` fields are preferred; legacy tracker
telemetry is used only as a compatibility fallback. Top-level `bounding_box` is
normalized-only; pixel boxes remain in explicit fields such as `fields.bbox`.
This route is not server-side history. Dashboard pages append bounded
client-side history from successive snapshots and ignore stale out-of-order
responses. It does not prove PX4, SITL, HIL, field, follower-response, or
vehicle-response success.

---

## Commands

### Switch Tracker

```http
POST /api/v1/actions/tracker-switch
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "switch_tracker",
  "confirm": true,
  "idempotency_key": "operator-tracker-switch-001",
  "tracker_type": "GimbalTracker",
  "metadata": {
    "ui": "dashboard_tracker_selector"
  }
}
```

Dry-run requests validate that `tracker_type` is selectable without changing
the configured tracker. Confirmed requests require an `idempotency_key`; the
action response records the local PixEagle tracker switch outcome and legacy
compatibility result. It does not prove tracker runtime success, follower
response, PX4, SITL, HIL, field, or real-aircraft behavior.

### Restart Tracker

```http
POST /api/v1/actions/tracker-restart
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "apply_tracker_config",
  "confirm": true,
  "idempotency_key": "operator-tracker-restart-001",
  "metadata": {
    "ui": "dashboard_config_reload"
  }
}
```

Dry-run requests validate that the configured tracker type is still selectable
without reloading config or reinitializing the tracker. Confirmed requests
require an `idempotency_key`; the action response records the local PixEagle
config reload/restart compatibility result. It does not prove tracker runtime
success, follower response, PX4, SITL, HIL, field, or real-aircraft behavior.

### Start Tracking

```http
POST /api/v1/actions/tracking-start
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "start_tracking_roi",
  "confirm": true,
  "idempotency_key": "operator-tracking-start-001",
  "metadata": {
    "ui": "dashboard_video_canvas"
  },
  "bbox": {
    "x": 0.25,
    "y": 0.25,
    "width": 0.2,
    "height": 0.2
  }
}
```

The `bbox` values may be normalized `0..1` coordinates or absolute pixels. The
typed response is an `APIActionResponse` action resource; it records local
PixEagle tracking start execution only and does not prove PX4, SITL, HIL,
field, or follower-response behavior.

### Stop Tracking

```http
POST /api/v1/actions/tracking-stop
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "stop_tracking",
  "confirm": true,
  "idempotency_key": "operator-tracking-stop-001"
}
```

### Redetect Target

```http
POST /api/v1/actions/tracking-redetect
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "redetect_tracking",
  "confirm": true,
  "idempotency_key": "operator-redetect-001"
}
```

The typed response records whether the local detector reacquired a target.
A no-target result is an accepted action with `status: "failure"` so operator
and automation clients can distinguish transport success from tracking success.

### Toggle Segmentation

```http
POST /api/v1/actions/segmentation-toggle
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "toggle_segmentation",
  "confirm": true,
  "idempotency_key": "operator-segmentation-toggle-001"
}
```

### Smart Click (Click-to-Track)

```http
POST /api/v1/actions/smart-click
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "smart_click",
  "confirm": true,
  "idempotency_key": "operator-smart-click-001",
  "click": {
    "x": 0.5,
    "y": 0.3
  }
}
```

Coordinates may be normalized `0..1` or absolute pixels.

### Toggle Smart Mode

```http
POST /api/v1/actions/smart-mode-toggle
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "toggle_smart_mode",
  "confirm": true,
  "idempotency_key": "operator-smart-mode-toggle-001"
}
```

The former `/commands/start_tracking`, `/commands/stop_tracking`,
`/commands/redetect`, `/commands/toggle_segmentation`,
`/commands/toggle_smart_mode`, and `/commands/smart_click` aliases are retired
and no longer registered as HTTP routes. Use the typed `/api/v1/actions/*`
resources above.

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
stale, or not marked `usable_for_following=true`. This guard applies to the
typed action resource.

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

### Stop Offboard

```http
POST /api/v1/actions/offboard-stop
Content-Type: application/json
```

```json
{
  "source": "operator",
  "reason": "stop_following",
  "confirm": true,
  "idempotency_key": "operator-stop-001"
}
```

The typed Offboard-stop action uses the same confirmation, dry-run,
idempotency, replay, process-local action-resource, and claim-boundary semantics
as Offboard start. It records the local PixEagle stop path and treats legacy
cleanup warnings or a still-active local following state as typed action
failure. PX4-observed Offboard exit still requires separate evidence artifacts.

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

### Retired Offboard/Abort Command Aliases

The former `/commands/start_offboard_mode`, `/commands/stop_offboard_mode`, and
`/commands/cancel_activities` HTTP aliases are no longer registered. Use the
typed `/api/v1/actions/offboard-start`, `/api/v1/actions/offboard-stop`, and
`/api/v1/actions/operator-abort` resources for operator clients and checked-in
SITL plans. Agent/MCP action use remains non-callable documentation-stage
governance until a future explicit promotion adds a runtime executor.

### Quit Application

```http
POST /commands/quit
```

---

## Tracker API

### Retired Tracker Catalog/Config Read Aliases

`GET /api/tracker/available`, `GET /api/tracker/current`,
`GET /api/tracker/available-types`, and
`GET /api/tracker/current-config` are no longer registered. Dashboard/API
clients must use `GET /api/v1/tracking/catalog` for tracker catalog,
configured tracker, active tracker, and selector metadata.

### Retired Tracker Runtime/Output Diagnostics

`GET /api/tracker/current-status` and `GET /api/tracker/output` are no longer
registered. Dashboard/API clients must use
`GET /api/v1/tracking/runtime-status` for readiness/status and
`GET /api/v1/tracking/telemetry` for current tracker geometry and field values.

### Retired Tracker Schema/Capabilities Diagnostics

`GET /api/tracker/schema` and `GET /api/tracker/capabilities` are no longer
registered. Dashboard/API clients must use `GET /api/v1/tracking/catalog` for
tracker catalog entries, active/configured tracker metadata, data-type schemas,
and capability metadata.

### Retired Tracker Switch

`POST /api/tracker/switch` is no longer registered. Dashboard/API clients must
use `POST /api/v1/actions/tracker-switch` so tracker selection is recorded as a
confirmed, idempotent action resource with typed errors and action metadata.

### Retired Tracker Restart

`POST /api/tracker/restart` is no longer registered. Dashboard/API clients must
use `POST /api/v1/actions/tracker-restart` so tracker restart/config reload is
recorded as a confirmed, idempotent action resource with typed errors and action
metadata.

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
  "available": true,
  "global_limits": {
    "MAX_VELOCITY_FORWARD": 8.0,
    "MAX_VELOCITY_LATERAL": 5.0,
    "MAX_VELOCITY_VERTICAL": 3.0,
    "MAX_YAW_RATE": 45.0
  },
  "follower_overrides": {},
  "timestamp": 1710000000.0
}
```

### Get Follower Limits

```http
GET /api/safety/limits/{follower_name}
```

**Response:**
```json
{
  "follower_name": "mc_velocity_chase",
  "velocity": {
    "forward": 8.0,
    "lateral": 5.0,
    "vertical": 3.0,
    "max_magnitude": 15.0,
    "source": "GlobalLimits",
    "is_overridden": false
  },
  "altitude": {
    "min": 3.0,
    "max": 120.0,
    "warning_buffer": 2.0,
    "safety_enabled": true,
    "source": "GlobalLimits",
    "is_overridden": false
  },
  "rates": {
    "yaw_deg": 45.0,
    "pitch_deg": 45.0,
    "roll_deg": 45.0,
    "source": "GlobalLimits",
    "is_overridden": false
  },
  "altitude_safety_enabled": true,
  "has_any_overrides": false,
  "timestamp": 1710000000.0
}
```

---

## Circuit Breaker API

### Get Status

```http
GET /api/circuit-breaker/status
```

**Response:**
```json
{
  "available": true,
  "active": false,
  "status": "operational",
  "safety_bypass": false,
  "safety_bypass_effective": false,
  "configuration": {
    "parameter_name": "FOLLOWER_CIRCUIT_BREAKER",
    "current_value": false,
    "description": "Global circuit breaker for follower testing"
  },
  "statistics": {
    "circuit_breaker_active": false,
    "total_commands": 0,
    "total_commands_blocked": 0,
    "total_commands_allowed": 0,
    "last_blocked_command": null,
    "command_types": {},
    "followers_tested": [],
    "elapsed_time_seconds": 12.5,
    "command_rate_hz": 0.0,
    "last_command_time": null,
    "session_start_time": 1710000000.0,
    "system_status": "operational"
  },
  "message": "Circuit breaker disabled - normal operation",
  "timestamp": 1710000000.0
}
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
