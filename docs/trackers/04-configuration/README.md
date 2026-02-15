# Tracker Configuration

> Schema system, parameters, and tuning guides for tracker performance

This section covers the configuration system for trackers, including the YAML schema definitions, parameter reference, and performance tuning.

---

## Section Contents

| Document | Description |
|----------|-------------|
| [Schema System](schema-system.md) | tracker_schemas.yaml explained |
| [Parameter Reference](parameter-reference.md) | All tracker parameters |
| [Tuning Guide](tuning-guide.md) | Performance vs accuracy optimization |

---

## Configuration Files

### Primary Configuration

| File | Purpose |
|------|---------|
| `configs/config.yaml` | Main runtime configuration |
| `configs/config_default.yaml` | Default values template |
| `configs/tracker_schemas.yaml` | Tracker schema definitions |
| `configs/config_schema.yaml` | Configuration validation schema |

---

## Quick Configuration Reference

### Tracker Selection

```yaml
# Classic tracker selection
TRACKING_ALGORITHM: "CSRT"  # CSRT, KCF, dlib, Gimbal

# SmartTracker (AI-powered)
ENABLE_SMART_TRACKER: true
SMART_TRACKER_GPU_MODEL_PATH: "models/yolov8n.pt"
```

### Confidence Settings

```yaml
# Confidence thresholds
MOTION_CONFIDENCE_WEIGHT: 0.5
APPEARANCE_CONFIDENCE_WEIGHT: 0.5
MOTION_CONFIDENCE_THRESHOLD: 0.3
MAX_DISPLACEMENT_THRESHOLD: 0.2
```

### Boundary Detection

```yaml
# Frame boundary settings
BOUNDARY_MARGIN_PIXELS: 15
```

### Estimator Settings

```yaml
# Position estimator (Kalman)
USE_ESTIMATOR: true
ESTIMATOR_TYPE: "Kalman"
CENTER_HISTORY_LENGTH: 20
ESTIMATOR_HISTORY_LENGTH: 50
```

---

## Schema System Overview

The `tracker_schemas.yaml` defines:

1. **Data Types**: 8 tracker output types with validation rules
2. **Tracker Types**: Capabilities and supported schemas per tracker
3. **Compatibility Matrix**: Which trackers work with which followers
4. **UI Metadata**: Dashboard display configuration

### Example Schema Entry

```yaml
tracker_data_types:
  POSITION_2D:
    name: "2D Position Tracking"
    category: "position"
    required_fields:
      - position_2d
    validation:
      position_2d:
        type: "tuple"
        length: 2
        range: [-2.0, 2.0]
```

---

## Parameter Categories

### Performance Parameters
- Model selection (detection model variant)
- Frame processing rate
- Detection thresholds

### Accuracy Parameters
- Confidence weights
- Motion consistency thresholds
- Boundary margins

### Behavior Parameters
- Estimator configuration
- History lengths
- Visualization settings

---

## Related Sections

- [Architecture](../01-architecture/README.md) - Understanding the schema system
- [Development](../05-development/README.md) - Adding new parameters
