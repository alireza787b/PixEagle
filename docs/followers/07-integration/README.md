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
│  SetpointHandler → MAVSDK → MAVLink → PX4 Autopilot             │
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
# Follower sets command fields
follower.set_command_field('vel_body_fwd', 5.0)
follower.set_command_field('vel_body_right', -2.0)

# PX4Controller reads and transmits
px4_controller.send_velocity_body_offboard(
    vel_fwd=5.0,
    vel_right=-2.0,
    vel_down=0.0,
    yawspeed=0.0
)
```

---

## Update Rates

| Component | Typical Rate |
|-----------|--------------|
| Video | 30 Hz |
| Tracker | 20-30 Hz |
| Follower | 20 Hz |
| PX4 Commands | 20 Hz |
| MAVLink | 50+ Hz |

---

## Quick Start

### Enable Following

```python
from classes.tracker import SmartTracker
from classes.follower import Follower
from classes.px4_controller import PX4Controller

# Initialize
px4 = PX4Controller()
tracker = SmartTracker()
follower = Follower(px4, (0.0, 0.0))

# Main loop
while running:
    frame = get_frame()
    tracker_output = tracker.update(frame)

    if tracker_output.tracking_active:
        follower.follow_target(tracker_output)
```
