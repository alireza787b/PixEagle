# Tracker Integration

> Integration with followers, external systems, and the broader PixEagle architecture

This section covers how trackers integrate with other PixEagle components and external systems.

---

## Section Contents

| Document | Description |
|----------|-------------|
| [Follower Integration](follower-integration.md) | Tracker to follower data flow |
| [External Systems](external-systems.md) | Gimbal, external sensors |

---

## Tracker-Follower Data Flow

The tracker system feeds data to followers through `TrackerOutput`:

```
┌──────────────────┐
│ Tracker          │
│ (CSRT, KCF, etc.)│
└────────┬─────────┘
         │ TrackerOutput
         ▼
┌──────────────────┐
│ AppController    │ ◄─── Coordinates tracker/follower
└────────┬─────────┘
         │ TrackerOutput
         ▼
┌──────────────────┐
│ Follower         │ ◄─── Consumes position data
│ (MC, FW, GM)     │
└────────┬─────────┘
         │ Vehicle Commands
         ▼
┌──────────────────┐
│ PX4/MAVSDK      │
└──────────────────┘
```

`AppController` is also the command-freshness gate. It rejects or converts
tracker output before follower dispatch when:

- the current video frame is cached or unavailable;
- a vision tracker reports prediction-only or stale data;
- tracker metadata sets `usable_for_following: false`.

These cases may still be visible in telemetry and overlays, but they are not
treated as active command targets. Followers that can safely respond to inactive
output must opt in and publish explicit target-loss commands. External trackers
are allowed to bypass video-frame freshness only when they explicitly publish
capabilities with `requires_video: false`; absent capabilities default to
vision-dependent fail-closed behavior.

---

## Schema Compatibility

Trackers and followers must use compatible schemas:

### Position-Based Followers

Most followers require `POSITION_2D`:

```python
# Compatible trackers
- CSRTTracker     → POSITION_2D
- KCFKalmanTracker → POSITION_2D
- DlibTracker     → POSITION_2D
- SmartTracker    → POSITION_2D (for selected target)
```

### Gimbal Followers

Gimbal followers require `GIMBAL_ANGLES`:

```python
# Compatible tracker
- GimbalTracker → GIMBAL_ANGLES

# Compatible followers
- GMVelocityChaseFollower
- GMVelocityVectorFollower
```

---

## External System Integration

### Gimbal Tracker UDP Protocol

The GimbalTracker receives angles via UDP:

```python
# Normalized data contract produced by GimbalTracker
{
    "yaw": 45.0,      # degrees
    "pitch": -10.0,   # degrees
    "roll": 0.0       # degrees
}

# Configuration
GimbalTracker:
  UDP_HOST: "127.0.0.1"
  UDP_PORT: 9003
  LISTEN_PORT: 9004
```

### External Data Sources

The `EXTERNAL` data type supports arbitrary sources:

```python
TrackerOutput(
    data_type=TrackerDataType.EXTERNAL,
    raw_data={
        "source_type": "radar",
        "source_data": {...}
    }
)
```

---

## API Integration

### FastAPI Endpoints

Tracker data is exposed via REST API:

```
GET /api/v1/tracking/catalog
GET /api/v1/tracking/runtime-status
GET /api/v1/tracking/telemetry
POST /api/v1/actions/tracker-restart
POST /api/v1/actions/tracker-switch
```

The typed catalog route is for tracker metadata/configuration only. It is not a
runtime tracker-success, follower-response, PX4, SITL, HIL, field, or
real-aircraft evidence source, and its generated agent/MCP candidate remains
blocked until a separate promotion review. It also carries
`data_type_schemas` from `configs/tracker_schemas.yaml` so dashboard/API
clients do not need the retired legacy schema-file route.

Each `ui_trackers` entry has a schema-manager `name`, a `request_tracker_type`
for action clients, and the internal tracker `factory_key` used by
`tracker_factory.py`. New clients should send `request_tracker_type` to
`POST /api/v1/actions/tracker-switch`. PixEagle also accepts older factory-key
identifiers such as `CSRT`, `KCF`, `dlib`, and `Gimbal` because those values can
exist in runtime config, then normalizes successful runtime state back to the
schema-manager tracker key.

Use `POST /api/v1/actions/tracker-switch` for new tracker-selection clients.
It requires either `dry_run=true` or confirmed/idempotent mutation fields,
validates that the requested tracker is selectable, and records the local
PixEagle action result. Legacy `/api/tracker/switch` is retired.

Use `POST /api/v1/actions/tracker-restart` for new tracker config-reload
clients. It requires either `dry_run=true` or confirmed/idempotent mutation
fields, validates that the configured tracker is still selectable, and records
the local PixEagle reload/restart compatibility result. Legacy
`/api/tracker/restart` is retired while broader tracker configuration mutation
design continues.

Dashboard tracker selector/current metadata now requires
`GET /api/v1/tracking/catalog`. The former legacy catalog/config read aliases
are retired, so missing or unsupported typed catalog responses surface as
operator-visible errors instead of falling back to stale paths.
Dashboard tracker status/output panels now use `GET /api/v1/tracking/telemetry`
for field data and `GET /api/v1/tracking/runtime-status` for readiness/status.
Legacy `GET /api/tracker/current-status` and `GET /api/tracker/output` are
retired. Legacy `GET /api/tracker/schema` and
`GET /api/tracker/capabilities` are also retired; use the typed catalog.

Deprecated `GET /api/tracker/available`, `GET /api/tracker/current`,
`GET /api/tracker/available-types`, `GET /api/tracker/current-config`,
`POST /api/tracker/set-type`, compatibility `POST /api/tracker/switch`, and
compatibility `POST /api/tracker/restart` are also retired. The former
process-local tracker legacy compatibility counter surface was removed with
the final tracker diagnostic aliases; the typed catalog no longer carries a
legacy counter object because no public legacy tracker diagnostic route remains
registered.

### Live Tracker Reads

There is no dedicated tracker WebSocket route in the current API inventory.
Use the typed REST routes above for tracker metadata, runtime readiness, and
geometry snapshots. Compatibility consumers may still poll
`GET /telemetry/tracker_data` while dashboard/API migration work continues.

---

## Telemetry Integration

Tracker data is included in telemetry:

```python
# TelemetryHandler integration
telemetry = {
    "tracker": {
        "active": tracker_output.tracking_active,
        "position": tracker_output.position_2d,
        "confidence": tracker_output.confidence,
        "usable_for_following": tracker_output.raw_data.get("usable_for_following")
    }
}
```

---

## Related Sections

- [Follower Integration](../../followers/07-integration/README.md) - Follower side
- [Architecture](../01-architecture/README.md) - System design
