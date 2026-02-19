# Schema System

> YAML-based tracker schema definitions and validation

The schema system defines tracker capabilities, data types, and compatibility rules in `configs/tracker_schemas.yaml`.

---

## Overview

The schema system provides:

- **Data type definitions** - 8 tracker output types with validation
- **Tracker capabilities** - Supported schemas per tracker
- **Compatibility rules** - Tracker-follower compatibility matrix
- **UI metadata** - Dashboard display configuration
- **Mount configurations** - Gimbal mounting options

---

## Schema File Location

```
configs/
├── tracker_schemas.yaml    # Tracker schema definitions
├── config.yaml             # Runtime configuration
├── config_default.yaml     # Default values
└── config_schema.yaml      # Configuration validation
```

---

## Data Type Definitions

```yaml
# configs/tracker_schemas.yaml
tracker_data_types:
  POSITION_2D:
    name: "2D Position Tracking"
    category: "position"
    required_fields:
      - position_2d
    optional_fields:
      - confidence
      - bbox
      - normalized_bbox
    validation:
      position_2d:
        type: "tuple"
        length: 2
        range: [-2.0, 2.0]  # Allow slightly off-screen
      confidence:
        type: "float"
        range: [0.0, 1.0]

  VELOCITY_AWARE:
    name: "Velocity-Aware Tracking"
    category: "position"
    required_fields:
      - position_2d
      - velocity
    optional_fields:
      - confidence
      - acceleration
    validation:
      velocity:
        type: "tuple"
        length: 2

  GIMBAL_ANGLES:
    name: "Gimbal Angle Tracking"
    category: "angular"
    required_fields:
      - angular
    optional_fields:
      - position_2d
      - confidence
    validation:
      angular:
        type: "tuple"
        length: 3  # yaw, pitch, roll

  MULTI_TARGET:
    name: "Multi-Target Tracking"
    category: "multi"
    required_fields:
      - targets
    optional_fields:
      - target_id
      - position_2d
```

---

## Tracker Type Definitions

```yaml
tracker_types:
  CSRT:
    name: "CSRT Tracker"
    display_name: "CSRT (Rotation-Robust)"
    supported_schemas:
      - POSITION_2D
      - BBOX_CONFIDENCE
      - VELOCITY_AWARE
    default_schema: POSITION_2D
    ui_metadata:
      icon: "track_changes"
      category: "classic"
      recommended_for:
        - "rotating_targets"
        - "partial_occlusion"

  KCF:
    name: "KCF + Kalman Tracker"
    display_name: "KCF (Fast)"
    supported_schemas:
      - POSITION_2D
      - BBOX_CONFIDENCE
      - VELOCITY_AWARE
    default_schema: VELOCITY_AWARE
    ui_metadata:
      icon: "speed"
      category: "classic"
      recommended_for:
        - "embedded_systems"
        - "real_time"

  dlib:
    name: "dlib Tracker"
    display_name: "dlib (Ultra-Fast)"
    supported_schemas:
      - POSITION_2D
      - BBOX_CONFIDENCE
      - VELOCITY_AWARE
    default_schema: POSITION_2D

  Gimbal:
    name: "Gimbal Tracker"
    display_name: "Gimbal (External)"
    supported_schemas:
      - GIMBAL_ANGLES
      - ANGULAR
      - POSITION_2D
    default_schema: GIMBAL_ANGLES
    special_properties:
      always_reporting: true
      external_data_source: true
      requires_video: false

  SmartTracker:
    name: "SmartTracker"
    display_name: "YOLO + ByteTrack"
    supported_schemas:
      - MULTI_TARGET
      - POSITION_2D
      - BBOX_CONFIDENCE
    default_schema: MULTI_TARGET
```

---

## Compatibility Matrix

```yaml
compatibility:
  followers:
    MCVelocityChaseFollower:
      required_schemas:
        - POSITION_2D
      compatible_schemas:
        - POSITION_3D
        - VELOCITY_AWARE
        - MULTI_TARGET
      incompatible_schemas:
        - GIMBAL_ANGLES

    GMVelocityChaseFollower:
      required_schemas:
        - GIMBAL_ANGLES
      compatible_schemas:
        - ANGULAR
      conversion_available:
        POSITION_2D: "angles_from_position"
```

---

## Mount Configurations

For gimbal trackers:

```yaml
mount_configurations:
  HORIZONTAL:
    name: "Horizontal Mount"
    description: "Camera facing forward"
    coordinate_mapping:
      yaw: "yaw"
      pitch: "pitch"
      roll: "roll"
    transformation_type: "DIRECT"
    sign_convention:
      yaw: 1    # Positive = right
      pitch: 1  # Positive = down
      roll: 1   # Positive = CW from behind

  VERTICAL:
    name: "Vertical Mount (90° Rotated)"
    description: "Camera facing down, rotated 90°"
    coordinate_mapping:
      yaw: "roll"
      pitch: "pitch-90"
      roll: "yaw"
    transformation_type: "ROTATIONAL_90"

  INVERTED:
    name: "Inverted Mount"
    description: "Camera mounted upside down"
    coordinate_mapping:
      yaw: "yaw"
      pitch: "-pitch"
      roll: "-roll"
    transformation_type: "SIGN_INVERSION"
```

---

## UI Metadata

Dashboard configuration:

```yaml
ui_metadata:
  tracker_selection:
    show_recommendations: true
    group_by_category: true
    categories:
      classic:
        name: "Classic Trackers"
        description: "CPU-based correlation trackers"
        trackers: ["CSRT", "KCF", "dlib"]
      ai:
        name: "AI Trackers"
        description: "Deep learning detection"
        trackers: ["SmartTracker"]
      external:
        name: "External Data"
        description: "External data sources"
        trackers: ["Gimbal"]

  data_display:
    POSITION_2D:
      primary_field: "position_2d"
      format: "(X: {0:.3f}, Y: {1:.3f})"
    GIMBAL_ANGLES:
      primary_field: "angular"
      format: "Y: {0:.1f}° P: {1:.1f}° R: {2:.1f}°"
```

---

## Validation

Schema validation in TrackerOutput:

```python
from classes.schema_manager import validate_tracker_data

def validate(self) -> bool:
    data_dict = {
        'position_2d': self.position_2d,
        'angular': self.angular,
        'confidence': self.confidence,
        # ...
    }

    is_valid, errors = validate_tracker_data(
        self.data_type.value.upper(),
        data_dict,
        self.tracking_active
    )

    if not is_valid:
        raise ValueError(f"Schema validation failed: {errors}")

    return True
```

---

## Adding New Schemas

1. **Define data type** in tracker_schemas.yaml
2. **Add to TrackerDataType** enum
3. **Update TrackerOutput** with new fields
4. **Add validation rules**
5. **Update compatibility matrix**

```yaml
# Example: New DEPTH_MAP type
tracker_data_types:
  DEPTH_MAP:
    name: "Depth Map Tracking"
    category: "3d"
    required_fields:
      - position_3d
      - depth_map
    validation:
      depth_map:
        type: "array"
        dimensions: 2
```

---

## Related

- [Parameter Reference](parameter-reference.md) - All configuration parameters
- [TrackerOutput](../01-architecture/tracker-output.md) - Output dataclass
- [Tuning Guide](tuning-guide.md) - Performance optimization
