# Tracker System Documentation

> Comprehensive guide to PixEagle's object tracking system for autonomous target following

The tracker system provides the visual perception layer of PixEagle, detecting and tracking targets to feed position data to the follower system. It supports classic correlation trackers, AI-powered detection (Ultralytics YOLO), and external data sources (gimbal angles).

---

## Quick Navigation

| Section | Description |
|---------|-------------|
| [Architecture](01-architecture/README.md) | System design, BaseTracker, factory pattern |
| [Tracker Reference](02-reference/README.md) | All 5 tracker implementations |
| [AI Concepts](03-ai-concepts/README.md) | Detection models, ByteTrack, motion prediction |
| [Configuration](04-configuration/README.md) | Schema system, parameters, tuning |
| [Development Guide](05-development/README.md) | Creating custom trackers |
| [Integration](06-integration/README.md) | Follower and external system integration |

---

## Available Trackers

### Classic Trackers (OpenCV/dlib)

| Tracker | Speed | Use Case |
|---------|-------|----------|
| [CSRT](02-reference/csrt-tracker.md) | Medium | Best rotation/occlusion handling |
| [KCF + Kalman](02-reference/kcf-kalman-tracker.md) | Very Fast | Embedded systems, real-time CPU |
| [dlib Correlation](02-reference/dlib-tracker.md) | Ultra Fast | Speed-critical, drone-to-drone |

### AI-Powered Tracker

| Tracker | Speed | Use Case |
|---------|-------|----------|
| [SmartTracker](02-reference/smart-tracker.md) | Fast (GPU) | Multi-target, object classification |

### External Data Tracker

| Tracker | Speed | Use Case |
|---------|-------|----------|
| [Gimbal Tracker](02-reference/gimbal-tracker.md) | Very Fast | External gimbal angle integration |

---

## Tracker Data Types

The tracker system uses a flexible schema supporting 8 data types:

```
POSITION_2D      - Normalized 2D position [-1, 1]
POSITION_3D      - 3D position with depth estimation
ANGULAR          - Bearing/elevation angles (degrees)
GIMBAL_ANGLES    - Gimbal yaw, pitch, roll (degrees)
BBOX_CONFIDENCE  - Bounding box with confidence score
VELOCITY_AWARE   - Position + velocity estimates
EXTERNAL         - External data sources (radar, GPS)
MULTI_TARGET     - Multiple simultaneous targets
```

### Schema Compatibility

Each tracker supports specific data types:

| Tracker | Primary Schema | Additional Schemas |
|---------|----------------|-------------------|
| CSRT | POSITION_2D | BBOX_CONFIDENCE, VELOCITY_AWARE |
| KCF + Kalman | BBOX_CONFIDENCE | POSITION_2D, VELOCITY_AWARE |
| dlib | POSITION_2D | BBOX_CONFIDENCE, VELOCITY_AWARE |
| SmartTracker | MULTI_TARGET | POSITION_2D, BBOX_CONFIDENCE |
| Gimbal | GIMBAL_ANGLES | ANGULAR, POSITION_2D |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       AppController                              │
│  - Tracker initialization                                        │
│  - Frame processing                                              │
│  - Tracker/Follower coordination                                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      TrackerFactory                              │
│  - Registry pattern (4 implementations)                         │
│  - create_tracker(algorithm, video_handler, detector, ...)      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       BaseTracker (ABC)                          │
│  - Abstract: start_tracking(), update()                          │
│  - Confidence computation (motion + appearance)                  │
│  - Normalization utilities                                       │
│  - TrackerOutput generation                                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Classic       │   │ SmartTracker  │   │ GimbalTracker │
│ (CSRT, KCF,   │   │ (Detection +  │   │ (External     │
│  dlib)        │   │  ByteTrack)   │   │  angles)      │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## Quick Start

### 1. Select a Tracker

In `configs/config.yaml`:

```yaml
TRACKING_ALGORITHM: "CSRT"  # Options: CSRT, KCF, dlib, Gimbal
```

### 2. Enable SmartTracker (Optional)

```yaml
ENABLE_SMART_TRACKER: true
SMART_TRACKER_GPU_MODEL_PATH: "models/yolov8n.pt"
```

### 3. Run PixEagle

```bash
bash run_pixeagle.sh
```

The tracker automatically initializes and begins processing frames.

---

## Key Concepts

### TrackerOutput

All trackers produce standardized output via the `TrackerOutput` dataclass:

```python
TrackerOutput(
    data_type=TrackerDataType.POSITION_2D,
    timestamp=1703000000.0,
    tracking_active=True,
    position_2d=(0.15, -0.08),  # Normalized [-1, 1]
    confidence=0.95,
    bbox=(100, 200, 50, 60)    # Pixel coordinates
)
```

### Confidence Scoring

Trackers compute confidence from multiple sources:

```python
# Motion confidence - penalizes erratic movement
motion_confidence = tracker.compute_motion_confidence()

# Appearance confidence - feature consistency
appearance_confidence = detector.compute_appearance_confidence()

# Combined confidence
confidence = (MOTION_WEIGHT * motion_confidence +
              APPEARANCE_WEIGHT * appearance_confidence)
```

### Boundary Detection

Trackers detect when targets approach frame edges:

```python
if tracker.is_near_boundary():
    penalty = tracker.compute_boundary_confidence_penalty()
    # Apply 0.5-1.0x multiplier to confidence
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `configs/config.yaml` | Main configuration (TRACKING_ALGORITHM, SmartTracker settings) |
| `configs/tracker_schemas.yaml` | Tracker schema definitions, UI metadata |
| `configs/config_schema.yaml` | Schema validation for config |

---

## Related Documentation

- [Follower System](../followers/README.md) - How followers consume tracker data
- [Tracker & Follower Schema Guide](../Tracker_and_Follower_Schema_Developer_Guide.md) - Schema details
- [Main README](../../README.md) - Project overview

---

## Source Files

| File | Description |
|------|-------------|
| `src/classes/trackers/base_tracker.py` | Abstract base class (790 lines) |
| `src/classes/trackers/tracker_factory.py` | Factory pattern registry |
| `src/classes/tracker_output.py` | TrackerOutput dataclass |
| `src/classes/trackers/*.py` | Individual tracker implementations |
| `src/classes/smart_tracker.py` | Detection + ByteTrack SmartTracker |
| `configs/tracker_schemas.yaml` | Schema definitions |
