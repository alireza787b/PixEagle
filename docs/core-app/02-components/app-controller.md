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

    # Update follower if following is active.
    # Cached frames, prediction-only tracker output, and inactive tracker output
    # are rejected unless AppController confirms that the concrete follower
    # explicitly opts into fail-closed target-loss command publication.
    if self.following_active:
        await self.follow_target()

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
# - tracking_active: bool
# - raw_data / metadata freshness fields:
#   usable_for_following, data_is_stale, freshness_reason
```

### With Follower

```python
# AppController first applies command-freshness checks.
tracker_output = self._apply_command_freshness_contract(tracker_output)

# Follower consumes active output, or inactive fail-closed output only when the
# concrete follower opts in. Validator success alone cannot bypass this gate.
if tracker_output.tracking_active or self._should_route_inactive_output_to_follower(tracker_output):
    await self._dispatch_tracker_output_to_follower(tracker_output)

    # Follower generates velocity commands
    # which are sent to drone via PX4InterfaceManager
```

External trackers bypass video-frame freshness only when their explicit
capabilities declare `requires_video: false`. External trackers without that
capability are treated as vision-dependent by default.

### Validation Injection Hook

SITL and tracker-in-loop validation may call
`inject_tracker_output_for_validation()` with a typed `TrackerOutput`. The hook
is not a separate follower implementation: it refuses to dispatch when
`following_active` is false, applies the same command-freshness contract, then
uses the normal follower and `OffboardCommander` path. Runtime API access to
this hook is disabled unless PixEagle is started with
`PIXEAGLE_ENABLE_SITL_INJECTIONS=1`.

Validation may also call `inject_video_stall_for_validation()` with frame-status
metadata. That hook does not stop a camera or stream; it reuses
`handle_video_frame_unavailable()` so video-stall evidence follows the same
fail-closed path as the main frame loop.

Validation may also call
`inject_commander_publish_failure_for_validation()` while follow mode and
`OffboardCommander` are active. That hook records bounded synthetic publish
failures inside the commander, crosses the configured local failure threshold,
and awaits `_handle_offboard_commander_failure()` so the response can prove the
same fail-closed follow-mode cleanup used for real commander publish failures.
It does not synthesize MAVSDK setpoint publishes, replace PX4 interfaces, stop
services, or mutate MAVLink routing; cleanup still uses the normal Offboard
stop path.

Validation may also call `inject_mavsdk_disconnect_for_validation()` while
follow mode and `OffboardCommander` are active. That hook first marks
`PX4InterfaceManager`'s local MAVSDK command path validation-disconnected, then
records bounded commander failures and awaits the same fail-closed cleanup
handler. The response includes before/after PX4 command-path state, commander
failure evidence, and the failed Offboard stop error. It does not stop PX4,
Docker, MavlinkAnywhere, MAVLink2REST, a MAVSDK server, network interfaces, or
MAVLink routes, so it must be reported as local PixEagle behavior only.

Validation may also call
`inject_mavlink2rest_timeout_for_validation()` to drive MAVLink2REST telemetry
freshness/error handling in PixEagle's local client. That hook delegates to
`MavlinkDataManager.inject_timeout_for_validation()`, records stale/error
`mavlink_telemetry`, and leaves MAVLink2REST, PX4, Docker, MavlinkAnywhere,
routing, and network interfaces running.

## Configuration

```yaml
# config_default.yaml

tracker:
  type: "smart"  # or "csrt", "kcf", etc.

follower:
  type: "mc_velocity_offboard"

video:
  source: 0  # Camera index or URL

Streaming:
  HTTP_STREAM_PORT: 5077
  STREAM_FPS: 30
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
- [VideoHandler](../../video/01-architecture/video-handler.md) - Video capture
- [SmartTracker](../../trackers/02-reference/smart-tracker.md) - YOLO tracking
