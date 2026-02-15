# Configuration Guide

> Complete reference for PixEagle configuration options

## Configuration Files

| File | Purpose |
|------|---------|
| `configs/config.yaml` | Main application settings |
| `configs/config_schema.yaml` | Schema definitions |
| `dashboard/.env` | Dashboard environment variables |

## Main Configuration (config.yaml)

### Video Input

```yaml
VIDEO_SOURCE: 0  # Webcam index, file path, or RTSP URL
# Examples:
# VIDEO_SOURCE: "/dev/video0"
# VIDEO_SOURCE: "rtsp://192.168.1.100:8554/stream"
# VIDEO_SOURCE: "test_video.mp4"
```

### SmartTracker

```yaml
SmartTracker:
  SMART_TRACKER_ENABLED: true
  SMART_TRACKER_USE_GPU: true
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26n.pt"
  SMART_TRACKER_CPU_MODEL_PATH: "models/yolo26n_ncnn_model"
  TRACKER_TYPE: "botsort_reid"  # bytetrack, botsort, botsort_reid, custom_reid
  DETECTION_CONFIDENCE: 0.5
  IOU_THRESHOLD: 0.45
```

### OSD (On-Screen Display)

```yaml
OSD:
  OSD_ENABLED: true
  OSD_PRESET: "professional"          # minimal | professional | full_telemetry
  OSD_PERFORMANCE_MODE: "balanced"    # fast | balanced | quality
  OSD_PIPELINE_MODE: "layered_realtime"     # layered_realtime | legacy
  OSD_TARGET_LAYER_RESOLUTION: "stream"     # stream | capture
  OSD_DYNAMIC_FPS: 10
  OSD_DATETIME_FPS: 1
  OSD_MAX_RENDER_BUDGET_MS: 25.0
  OSD_AUTO_DEGRADE: true
  OSD_AUTO_DEGRADE_MIN_MODE: "fast"         # fast keeps low-power boards responsive
  OSD_COMPOSITOR: "cv2_alpha"               # cv2_alpha | legacy_pil_composite
```

### Follower Modes

Available modes:
- `mc_velocity_position` - Position hold with altitude control
- `mc_velocity_chase` - Body velocity chase
- `mc_velocity_distance` - Fixed distance tracking
- `gm_pid_pursuit` - Gimbal PID pursuit
- `gm_velocity_vector` - Gimbal vector pursuit
- `fw_attitude_rate` - Fixed-wing tracking

### PID Tuning

```yaml
PID:
  KP_X: 1.0
  KI_X: 0.0
  KD_X: 0.1
  KP_Y: 1.0
  KI_Y: 0.0
  KD_Y: 0.1
```

### Safety Limits

```yaml
Safety:
  MAX_VELOCITY: 5.0
  MIN_ALTITUDE: 2.0
  MAX_ALTITUDE: 120.0
  GEOFENCE_ENABLED: true
```

## Dashboard Environment (.env)

```bash
# Dashboard HTTP port (default: 3040)
PORT=3040

# API port (default: 5077)
REACT_APP_API_PORT=5077

# Optional: Override auto-detected host (for reverse proxy)
REACT_APP_API_HOST_OVERRIDE=

# Polling rate in milliseconds
REACT_APP_POLLING_RATE=500

# Maximum velocity for visualization
REACT_APP_MAX_SPEED=1

# Default bounding box size
REACT_APP_DEFAULT_BOUNDING_BOX_SIZE=0.1
```

### Auto Host Detection (v4.1.0+)

The dashboard automatically detects the API host from `window.location.hostname`. No manual configuration needed for:
- Local development (localhost)
- LAN access (192.168.x.x)
- Remote access via IP

Use `REACT_APP_API_HOST_OVERRIDE` only for reverse proxy setups.

## Configuration via API

The Settings page in the dashboard allows runtime configuration changes:
- `/api/config/current` - Get current configuration
- `/api/config/update` - Update configuration
- `/api/system/restart` - Restart system

## Next Steps

- [Installation Guide](INSTALLATION.md)
- [SmartTracker Guide](trackers/02-reference/smart-tracker.md)
- [OSD Guide](OSD_GUIDE.md)
