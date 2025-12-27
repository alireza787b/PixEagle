# AppController

The main application orchestrator that manages all PixEagle subsystems.

## Overview

`AppController` (`src/classes/app_controller.py`) is the central coordinator that:

- Initializes all subsystems (video, tracker, follower, telemetry)
- Manages the frame processing pipeline
- Handles user commands and state transitions
- Coordinates between tracker output and follower input

## Class Definition

```python
class AppController:
    """
    Central controller that orchestrates all PixEagle components.

    Manages:
    - Video capture and processing
    - Tracker initialization and updates
    - Follower command generation
    - Telemetry handling
    - API handler integration
    """
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      AppController                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Subsystems                                           │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │VideoHandler │  │SmartTracker │  │  Follower   │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │   │
│  │  │ OSDHandler  │  │TelemetryHndl│  │FastAPIHndlr │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  State                                                │   │
│  │  - tracking_active: bool                              │   │
│  │  - offboard_active: bool                              │   │
│  │  - shutdown_flag: bool                                │   │
│  │  - current_frame: np.ndarray                          │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Key Methods

### Initialization

```python
def __init__(self):
    """Initialize all subsystems."""
    # Video source
    self.video_handler = VideoHandler()

    # Tracker (SmartTracker with YOLO or classic tracker)
    self.tracker = TrackerFactory.create(Parameters.TRACKER_TYPE)

    # Follower for drone control
    self.follower = FollowerFactory.create(Parameters.FOLLOWER_TYPE)

    # Telemetry handler
    self.telemetry_handler = TelemetryHandler()

    # OSD rendering
    self.osd_handler = OSDHandler()

    # API handler (FastAPI)
    self.api_handler = FastAPIHandler(self)
```

### Main Update Loop

```python
async def update_loop(self, frame: np.ndarray) -> np.ndarray:
    """
    Main frame processing loop.

    Args:
        frame: Current video frame

    Returns:
        Processed frame with OSD overlays
    """
    # Update tracker
    tracker_output = self.tracker.update(frame)

    # Update telemetry
    await self.telemetry_handler.update()

    # Update follower if tracking
    if self.tracking_active and tracker_output.is_tracking:
        self.follower.follow_target(tracker_output)

    # Render OSD
    frame = self.osd_handler.render(frame, tracker_output)

    # Store for streaming
    self.current_frame = frame

    return frame
```

### Command Handlers

```python
async def start_tracking(self, bbox: tuple = None):
    """Start tracking with optional initial bounding box."""
    if bbox:
        self.tracker.init_track(self.current_frame, bbox)
    self.tracking_active = True

async def stop_tracking(self):
    """Stop tracking and reset state."""
    self.tracking_active = False
    self.tracker.reset()

async def start_offboard_mode(self):
    """Enable offboard mode for drone control."""
    if not self.tracking_active:
        raise ValueError("Must be tracking to enable offboard")
    self.offboard_active = True
    await self.follower.start()

async def stop_offboard_mode(self):
    """Disable offboard mode."""
    self.offboard_active = False
    await self.follower.stop()
```

### Shutdown

```python
async def shutdown(self):
    """Graceful shutdown of all subsystems."""
    self.shutdown_flag = True

    # Stop offboard if active
    if self.offboard_active:
        await self.stop_offboard_mode()

    # Stop tracking
    await self.stop_tracking()

    # Cleanup subsystems
    await self.telemetry_handler.stop()
    self.video_handler.release()
```

## State Management

### Tracking States

| State | Description |
|-------|-------------|
| `tracking_active` | Tracker is following a target |
| `offboard_active` | Drone is in offboard mode |
| `smart_mode` | Using SmartTracker (YOLO-based) |
| `segmentation_enabled` | Instance segmentation active |

### State Transitions

```
        ┌─────────────┐
        │    IDLE     │
        └──────┬──────┘
               │ start_tracking()
               ▼
        ┌─────────────┐
        │  TRACKING   │◄─────────┐
        └──────┬──────┘          │
               │ start_offboard()│ stop_offboard()
               ▼                 │
        ┌─────────────┐          │
        │  OFFBOARD   │──────────┘
        └──────┬──────┘
               │ stop_tracking()
               ▼
        ┌─────────────┐
        │    IDLE     │
        └─────────────┘
```

## Integration Points

### With FastAPIHandler

```python
# FastAPIHandler receives commands via REST
@app.post("/commands/start_tracking")
async def start_tracking(request: BoundingBox):
    bbox = (request.x, request.y, request.width, request.height)
    await app_controller.start_tracking(bbox)
```

### With Tracker

```python
# Tracker provides standardized output
tracker_output = self.tracker.update(frame)

# TrackerOutput contains:
# - position_2d: (x, y) normalized
# - bbox: (x1, y1, x2, y2)
# - confidence: float
# - is_tracking: bool
```

### With Follower

```python
# Follower consumes tracker output
if tracker_output.is_tracking:
    self.follower.follow_target(tracker_output)

    # Follower generates velocity commands
    # which are sent to drone via PX4InterfaceManager
```

## Configuration

```yaml
# config_default.yaml

tracker:
  type: "smart"  # or "csrt", "kcf", etc.

follower:
  type: "mc_velocity_offboard"

video:
  source: 0  # Camera index or URL

http:
  port: 8000
  stream_fps: 30
```

## Error Handling

```python
async def update_loop(self, frame):
    try:
        # Normal processing
        tracker_output = self.tracker.update(frame)

    except TrackerError as e:
        logging.error(f"Tracker error: {e}")
        self.tracking_active = False

    except Exception as e:
        logging.error(f"Update loop error: {e}")
        # Continue running - don't crash on single frame error
```

## Thread Safety

- Frame access protected by `asyncio.Lock`
- State changes are atomic
- Subsystem interactions use async/await

## Related Components

- [FlowController](flow-controller.md) - Manages AppController lifecycle
- [FastAPIHandler](fastapi-handler.md) - Exposes API endpoints
- [VideoHandler](../../video/02-components/video-handler.md) - Video capture
- [SmartTracker](../../trackers/02-components/smart-tracker.md) - YOLO tracking
