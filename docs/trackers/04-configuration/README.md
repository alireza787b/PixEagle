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
| `configs/config_default.yaml` | Checked-in runtime defaults |
| `configs/config.yaml` | Optional local override file |
| `configs/tracker_schemas.yaml` | Tracker output/follower compatibility contracts |
| `configs/config_schema.yaml` | Configuration validation schema |

---

## Quick Configuration Reference

### Tracker Selection

```yaml
Tracking:
  DEFAULT_TRACKING_ALGORITHM: "CSRT"  # CSRT, KCF, dlib, Gimbal

SmartTracker:
  SMART_TRACKER_ENABLED: true
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26n.pt"
```

`DEFAULT_TRACKING_ALGORITHM` is the persisted startup and tracker-restart
default. The Tracker-page selector changes the active runtime tracker without
rewriting that saved default. Selectable values come from
`configs/tracker_schemas.yaml`, which also drives the generated Settings
dropdown.

### Confidence Settings

```yaml
Tracking:
  MOTION_CONFIDENCE_WEIGHT: 0.5
  APPEARANCE_CONFIDENCE_WEIGHT: 0.5
  MOTION_CONFIDENCE_THRESHOLD: 0.7
  MAX_DISPLACEMENT_THRESHOLD: 0.25
```

### Boundary Detection

```yaml
# Frame boundary settings
TrackerSafety:
  BOUNDARY_MARGIN_PIXELS: 15
  ENABLE_BOUNDARY_PENALTY: true
  BOUNDARY_PENALTY_MIN: 0.5
```

### Estimator Settings

```yaml
Estimator:
  USE_ESTIMATOR: true
  ESTIMATOR_TYPE: "Kalman"
  ESTIMATOR_HISTORY_LENGTH: 5
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
