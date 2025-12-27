# Core Application

This section documents PixEagle's core application components that orchestrate the entire system.

## Overview

The core application layer provides:

- **Application Orchestration** - Main control loop and component coordination
- **REST API** - FastAPI-based HTTP/WebSocket endpoints
- **Configuration Management** - Schema-driven YAML config system
- **State Management** - Tracking state and lifecycle handling
- **Coordinate Transforms** - Pixel to world coordinate conversions
- **Logging Infrastructure** - Professional logging with spam reduction

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FlowController                            │
│                   (Main Entry Point)                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    AppController                         │    │
│  │              (Component Orchestrator)                    │    │
│  └─────────────────────────┬───────────────────────────────┘    │
│                            │                                     │
│     ┌──────────────────────┼──────────────────────┐             │
│     ▼                      ▼                      ▼             │
│ ┌─────────┐         ┌─────────────┐        ┌──────────┐        │
│ │ Video   │         │   Tracker   │        │ Follower │        │
│ │ Handler │◄───────▶│   System    │───────▶│  System  │        │
│ └─────────┘         └─────────────┘        └──────────┘        │
│     │                      │                      │             │
│     ▼                      ▼                      ▼             │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │                   FastAPIHandler                         │    │
│ │           (REST API + WebSocket + Streaming)             │    │
│ └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Components

| Component | File | Description |
|-----------|------|-------------|
| [AppController](02-components/app-controller.md) | `app_controller.py` | Main orchestrator for all subsystems |
| [FlowController](02-components/flow-controller.md) | `flow_controller.py` | Frame processing loop and shutdown |
| [FastAPIHandler](02-components/fastapi-handler.md) | `fastapi_handler.py` | REST/WebSocket API endpoints |
| [ConfigService](02-components/config-service.md) | `config_service.py` | Schema-driven config management |
| [SchemaManager](02-components/schema-manager.md) | `schema_manager.py` | Tracker schema validation |
| [LoggingManager](02-components/logging-manager.md) | `logging_manager.py` | Professional logging |
| [CoordinateTransformer](02-components/coordinate-transformer.md) | `coordinate_transformer.py` | Frame conversions |
| [TrackingStateManager](02-components/tracking-state-manager.md) | `tracking_state_manager.py` | Track lifecycle |

## Documentation Sections

### [01-Architecture](01-architecture/)
- System overview and data flow
- Component interactions
- Threading model

### [02-Components](02-components/)
- Detailed component documentation
- API references
- Usage examples

### [03-API](03-api/)
- REST API endpoints
- WebSocket protocols
- Request/response formats

### [04-Configuration](04-configuration/)
- Config schema system
- Parameter reference
- Runtime configuration

### [05-Development](05-development/)
- Adding new endpoints
- Extending components
- Testing strategies

## Quick Start

### Running PixEagle

```bash
# Start with default configuration
python main.py

# Or via run script
./run_pixeagle.sh
```

### API Access

```bash
# Check system status
curl http://localhost:8000/status

# Get telemetry
curl http://localhost:8000/telemetry/tracker_data

# Video stream
# Open in browser: http://localhost:8000/video_feed
```

### Configuration

```yaml
# configs/config.yaml
http:
  host: "0.0.0.0"
  port: 8000
  stream_fps: 30
  stream_quality: 85
```

## Key Concepts

### Application Lifecycle

1. **Initialization**: FlowController creates AppController with all subsystems
2. **Main Loop**: Frame processing, tracking, following, API handling
3. **Shutdown**: Graceful cleanup with signal handling

### Threading Model

- **Main Thread**: Frame capture and processing loop
- **FastAPI Thread**: HTTP server and WebSocket handlers
- **Background Tasks**: Cleanup, monitoring, periodic updates

### Configuration System

- Schema-driven validation
- YAML persistence with comment preservation
- Backup and restore capabilities
- Audit logging for changes

## Related Documentation

- [Video/Streaming](../video/README.md)
- [Trackers](../trackers/README.md)
- [Followers](../followers/README.md)
- [Drone Interface](../drone-interface/README.md)
