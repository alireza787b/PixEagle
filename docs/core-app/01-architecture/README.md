# Core App Architecture

## Overview

PixEagle's core application follows a layered architecture with clear separation of concerns:

```
┌────────────────────────────────────────────────────────────┐
│                     Presentation Layer                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐  │
│  │   FastAPI REST  │  │    WebSocket    │  │   MJPEG    │  │
│  │    Endpoints    │  │    Handlers     │  │  Streaming │  │
│  └────────┬────────┘  └────────┬────────┘  └─────┬──────┘  │
└───────────┼────────────────────┼─────────────────┼─────────┘
            │                    │                 │
┌───────────┴────────────────────┴─────────────────┴─────────┐
│                    Application Layer                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   AppController                      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │   │
│  │  │ VideoHandler │  │TrackerSystem │  │ Follower  │  │   │
│  │  └──────────────┘  └──────────────┘  │  System   │  │   │
│  │  ┌──────────────┐  ┌──────────────┐  └───────────┘  │   │
│  │  │  OSDHandler  │  │TelemetryHndlr│                 │   │
│  │  └──────────────┘  └──────────────┘                 │   │
│  └─────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
            │                    │                 │
┌───────────┴────────────────────┴─────────────────┴─────────┐
│                     Service Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ConfigService │  │SchemaManager │  │ LoggingManager   │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │Coord.Transf. │  │TrackStateM.  │  │ TargetLossHndlr │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└────────────────────────────────────────────────────────────┘
            │                    │                 │
┌───────────┴────────────────────┴─────────────────┴─────────┐
│                    Infrastructure Layer                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │   MAVLink    │  │    MAVSDK    │  │    OpenCV        │  │
│  │   2REST      │  │              │  │    (Video)       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

## Component Layers

### Presentation Layer

**FastAPIHandler** serves as the main interface:

| Endpoint Type | Purpose |
|---------------|---------|
| REST API | Commands, telemetry, configuration |
| WebSocket | Real-time updates, WebRTC signaling |
| MJPEG Stream | Video streaming with OSD |

### Application Layer

**AppController** orchestrates all subsystems:

- Initializes and manages component lifecycle
- Coordinates frame processing pipeline
- Handles user input and commands
- Manages tracking and following states

### Service Layer

Supporting services that components depend on:

- **ConfigService**: Configuration management
- **SchemaManager**: Tracker schema validation
- **LoggingManager**: Professional logging
- **CoordinateTransformer**: Geometry calculations
- **TrackingStateManager**: Track lifecycle

### Infrastructure Layer

External dependencies and drivers:

- MAVLink2REST for telemetry
- MAVSDK for drone control
- OpenCV for video processing

## Data Flow

### Frame Processing Pipeline

```
VideoHandler.get_frame()
        │
        ▼
┌───────────────────┐
│  Frame Capture    │
│  (Camera/Stream)  │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Preprocessing    │
│  (Resize, Flip)   │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Tracker.update() │
│  (CSRT/YOLO/etc)  │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  TrackerOutput    │
│  (Normalized)     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│ Follower.follow() │
│ (Setpoint Calc)   │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  OSD Rendering    │
│  (Overlays)       │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  FastAPI Stream   │
│  (MJPEG/WebRTC)   │
└───────────────────┘
```

### API Request Flow

```
HTTP Request
     │
     ▼
┌─────────────────┐
│ FastAPIHandler  │
│ (Route Match)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Rate Limiter   │
│  (If Enabled)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Endpoint Func  │
│  (Validation)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AppController  │
│  (Execute)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ JSON Response   │
└─────────────────┘
```

## Threading Model

### Thread Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Main Process                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Main Thread                                         │    │
│  │  - FlowController.main_loop()                       │    │
│  │  - Frame capture and processing                     │    │
│  │  - Tracker updates                                  │    │
│  │  - OpenCV window (if enabled)                       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  FastAPI Server Thread                              │    │
│  │  - Uvicorn HTTP server                              │    │
│  │  - REST endpoint handlers                           │    │
│  │  - WebSocket connections                            │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Async Event Loop (in FastAPI thread)               │    │
│  │  - Background cleanup tasks                         │    │
│  │  - Connection monitoring                            │    │
│  │  - Telemetry polling                                │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Thread Safety

| Component | Thread Safety Mechanism |
|-----------|------------------------|
| FastAPIHandler | asyncio locks |
| ConfigService | threading.Lock |
| LoggingManager | threading.Lock |
| Frame access | asyncio.Lock |
| Connection state | asyncio.Lock |

## Initialization Sequence

```python
# 1. FlowController initialization
FlowController.__init__()
    ├── AppController.__init__()
    │   ├── VideoHandler()
    │   ├── TrackerFactory.create()
    │   ├── FollowerFactory.create()
    │   ├── TelemetryHandler()
    │   ├── OSDHandler()
    │   └── FastAPIHandler(self)
    │
    └── start_fastapi_server()

# 2. Main loop start
FlowController.main_loop()
    └── while not shutdown_flag:
        ├── video_handler.get_frame()
        ├── controller.update_loop(frame)
        └── controller.show_current_frame()

# 3. Graceful shutdown
FlowController.shutdown_handler()
    ├── controller.shutdown()
    ├── api_handler.stop()
    └── server_thread.join()
```

## Configuration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     ConfigService                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  configs/                                            │    │
│  │  ├── config_schema.yaml   (Schema definitions)      │    │
│  │  ├── config_default.yaml  (Default values)          │    │
│  │  ├── config.yaml          (Active config)           │    │
│  │  └── backups/             (Auto-backups)            │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Features:                                                   │
│  - Schema validation                                         │
│  - Atomic writes with file locking                          │
│  - Comment preservation (ruamel.yaml)                       │
│  - Diff comparison                                          │
│  - Audit logging                                            │
│  - Import/export                                            │
└─────────────────────────────────────────────────────────────┘
```

## Related Documentation

- [Component Details](../02-components/)
- [API Reference](../03-api/)
- [Configuration](../04-configuration/)
