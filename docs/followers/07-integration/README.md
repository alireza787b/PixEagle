# Integration Guide

> Connecting followers to trackers and PX4

This section covers how followers integrate with the PixEagle ecosystem.

---

## Documents

| Document | Description |
|----------|-------------|
| [Tracker Integration](tracker-integration.md) | Tracker-to-follower data flow |
| [MAVLink Integration](mavlink-integration.md) | PX4/MAVSDK communication |

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         VIDEO SOURCE                              │
│                    (Camera, RTSP, File)                          │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                           TRACKER                                 │
│              (SmartTracker / ClassicTracker)                     │
│                                                                  │
│  YOLO Detection → ByteTrack → TrackerOutput                     │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                          FOLLOWER                                 │
│                    (MC/FW/GM Follower)                           │
│                                                                  │
│  TrackerOutput → Control Algorithm → SetpointHandler             │
└─────────────────────────────┬────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                        PX4 CONTROLLER                             │
│                          (MAVSDK)                                │
│                                                                  │
│  CommandIntent → OffboardCommander → MAVSDK → PX4 Autopilot     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Tracker → Follower

```python
# Tracker produces TrackerOutput
tracker_output = TrackerOutput(
    data_type=TrackerDataType.POSITION_2D,
    position_2d=(0.15, -0.08),
    confidence=0.95,
    timestamp=time.time()
)

# Follower consumes TrackerOutput
success = follower.follow_target(tracker_output)
```

### Follower → PX4

```python
# Follower publishes one complete command intent
follower.set_command_fields({
    'vel_body_fwd': 5.0,
    'vel_body_right': -2.0,
    'vel_body_down': 0.0,
    'yawspeed_deg_s': 0.0,
})

# AppController submits the accepted CommandIntent to OffboardCommander.
# OffboardCommander owns fixed-rate MAVSDK publication.
commander.submit_intent(follower.get_last_command_intent())
```

---

## Update Rates

| Component | Typical Rate |
|-----------|--------------|
| Video | 30 Hz |
| Tracker | 20-30 Hz |
| Follower math | `CONTROL_UPDATE_RATE` tuning value |
| PX4 command dispatch | `OffboardCommander` application setter refresh from `OFFBOARD_COMMAND_RATE_HZ` |
| MAVLink | 50+ Hz |

## API Observability

Use `GET /api/v1/following/status` for following-state checks in dashboard,
API, and MCP consumers. It reports local `following_active`, follower profile
identity, OffboardCommander command-publication health, and an explicit claim
boundary. It reports `degraded/operator_attention` if local following is active
without a valid follower/commander publication path, or if command publication
appears to remain active after local following stopped.

API/MCP wording here means schema-stable typed routes for future reviewed
integrations. PixEagle's generated agent-context inventory is candidate
inventory only, not MCP execution, until registry, policy, docs, tests, and
reviewer gates promote a route.

Use `GET /api/v1/following/telemetry` for current follower setpoint values and
follower-card diagnostics. It prefers live setpoint-handler fields and falls
back to legacy telemetry fields only for compatibility. Its publication fields
are PixEagle-local signals, not PX4-observed Offboard or vehicle-response proof.

The dashboard Follower visualization page now uses
`GET /api/v1/following/telemetry` for follower/setpoint history snapshots and
falls back to `/telemetry/follower_data` only when the typed route is missing
during rolling updates. Its tracker center/bounding-box plots use
`GET /api/v1/tracking/telemetry`, with legacy `/telemetry/tracker_data` fallback
only when the typed tracker route is missing during rolling updates.

---

## Quick Start

### Enable Following

```python
from classes.tracker import SmartTracker
from classes.follower import Follower
from classes.offboard_commander import OffboardCommander
from classes.px4_interface_manager import PX4InterfaceManager

# Initialize
px4 = PX4InterfaceManager()
tracker = SmartTracker()
follower = Follower(px4, (0.0, 0.0))
commander = OffboardCommander(px4, follower.follower.setpoint_handler)

# Main loop
while running:
    frame = get_frame()
    tracker_output = tracker.update(frame)

    if tracker_output.tracking_active:
        follower.follow_target(tracker_output)
```
