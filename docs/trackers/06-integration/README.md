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
# Message format (JSON over UDP)
{
    "yaw": 45.0,      # degrees
    "pitch": -10.0,   # degrees
    "roll": 0.0       # degrees
}

# Configuration
GIMBAL_UDP_HOST: "0.0.0.0"
GIMBAL_UDP_PORT: 14555
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
GET /api/tracker/status
GET /api/tracker/output
POST /api/tracker/select/{target_id}
```

### WebSocket Streaming

Real-time tracker data via WebSocket:

```
WS /ws/tracker
```

---

## Telemetry Integration

Tracker data is included in telemetry:

```python
# TelemetryHandler integration
telemetry = {
    "tracker": {
        "active": tracker_output.tracking_active,
        "position": tracker_output.position_2d,
        "confidence": tracker_output.confidence
    }
}
```

---

## Related Sections

- [Follower Integration](../../followers/07-integration/README.md) - Follower side
- [Architecture](../01-architecture/README.md) - System design
