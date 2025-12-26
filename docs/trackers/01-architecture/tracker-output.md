# TrackerOutput - Unified Data Schema

> Flexible dataclass for standardized tracker output across all modalities

`TrackerOutput` is the unified output schema for all tracker types, providing type-safe data structures with validation. Located at `src/classes/tracker_output.py`.

---

## Overview

TrackerOutput provides:

- **8 data types** for different tracking modalities
- **Type-safe fields** with dataclass validation
- **Schema validation** via tracker_schemas.yaml
- **Backwards compatibility** with legacy formats
- **Serialization** to/from dictionary/JSON

---

## Data Types

```python
class TrackerDataType(Enum):
    POSITION_2D = "POSITION_2D"           # Standard 2D normalized position
    POSITION_3D = "POSITION_3D"           # 3D position with depth
    ANGULAR = "ANGULAR"                   # Bearing/elevation angles
    GIMBAL_ANGLES = "GIMBAL_ANGLES"       # Gimbal yaw, pitch, roll
    BBOX_CONFIDENCE = "BBOX_CONFIDENCE"   # Bounding box with confidence
    VELOCITY_AWARE = "VELOCITY_AWARE"     # Position + velocity estimates
    EXTERNAL = "EXTERNAL"                 # External data source
    MULTI_TARGET = "MULTI_TARGET"         # Multiple targets
```

### When to Use Each Type

| Type | Use Case | Required Fields |
|------|----------|-----------------|
| POSITION_2D | Standard image-based tracking | `position_2d` |
| POSITION_3D | Depth estimation, stereo vision | `position_3d`, `position_2d` |
| ANGULAR | Bearing tracking | `angular` (2-tuple) |
| GIMBAL_ANGLES | External gimbal data | `angular` (3-tuple: yaw, pitch, roll) |
| BBOX_CONFIDENCE | Traditional bbox tracking | `bbox` or `normalized_bbox` |
| VELOCITY_AWARE | Motion prediction enabled | `position_2d`, `velocity` |
| EXTERNAL | Radar, GPS, other sensors | `raw_data` |
| MULTI_TARGET | Multi-object tracking | `targets` list |

---

## TrackerOutput Dataclass

```python
@dataclass
class TrackerOutput:
    # Required fields
    data_type: TrackerDataType
    timestamp: float
    tracking_active: bool
    tracker_id: str = "default"

    # Position data
    position_2d: Optional[Tuple[float, float]] = None  # Normalized [-1, 1]
    position_3d: Optional[Tuple[float, float, float]] = None
    angular: Optional[Tuple[float, ...]] = None  # 2D or 3D

    # Bounding box data
    bbox: Optional[Tuple[int, int, int, int]] = None  # Pixel (x, y, w, h)
    normalized_bbox: Optional[Tuple[float, float, float, float]] = None

    # Quality metrics
    confidence: Optional[float] = None  # [0.0, 1.0]
    quality_metrics: Dict[str, float] = field(default_factory=dict)

    # Motion data
    velocity: Optional[Tuple[float, float]] = None  # (vx, vy)
    acceleration: Optional[Tuple[float, float]] = None

    # Multi-target support
    target_id: Optional[int] = None
    targets: Optional[List[Dict[str, Any]]] = None

    # Raw/custom data
    raw_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Schema-specific
    gimbal_metadata: Optional[Dict[str, Any]] = None
```

---

## Usage Examples

### POSITION_2D (Most Common)

```python
from classes.tracker_output import TrackerOutput, TrackerDataType
import time

output = TrackerOutput(
    data_type=TrackerDataType.POSITION_2D,
    timestamp=time.time(),
    tracking_active=True,
    tracker_id="CSRT_tracker",
    position_2d=(0.15, -0.08),  # Normalized [-1, 1]
    confidence=0.92,
    bbox=(100, 200, 50, 60)
)
```

### VELOCITY_AWARE

```python
output = TrackerOutput(
    data_type=TrackerDataType.VELOCITY_AWARE,
    timestamp=time.time(),
    tracking_active=True,
    position_2d=(0.1, -0.2),
    velocity=(5.2, -1.3),  # pixels/second
    confidence=0.88
)
```

### GIMBAL_ANGLES

```python
output = TrackerOutput(
    data_type=TrackerDataType.GIMBAL_ANGLES,
    timestamp=time.time(),
    tracking_active=True,
    angular=(45.0, -10.0, 0.0),  # yaw, pitch, roll (degrees)
    confidence=1.0,
    gimbal_metadata={
        'coordinate_system': 'GIMBAL_BODY',
        'connection_status': 'connected'
    }
)
```

### MULTI_TARGET

```python
output = TrackerOutput(
    data_type=TrackerDataType.MULTI_TARGET,
    timestamp=time.time(),
    tracking_active=True,
    targets=[
        {"target_id": 1, "class_name": "person", "confidence": 0.95,
         "bbox": (100, 150, 50, 120)},
        {"target_id": 2, "class_name": "car", "confidence": 0.88,
         "bbox": (300, 200, 150, 80)}
    ],
    target_id=1,  # Selected target
    position_2d=(0.1, -0.2)  # Selected target position
)
```

---

## Validation

TrackerOutput validates data in `__post_init__`:

```python
def validate(self) -> bool:
    # Basic validation
    if self.timestamp <= 0:
        raise ValueError("Timestamp must be positive")

    if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
        raise ValueError("Confidence must be between 0.0 and 1.0")

    # Schema validation (if schema manager available)
    if SCHEMA_MANAGER_AVAILABLE:
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

## Helper Methods

### Position Access

```python
# Check if any position data available
if output.has_position_data():
    pos = output.get_primary_position()  # Returns 2D tuple
```

### Confidence

```python
# Get confidence with default
conf = output.get_confidence_or_default(default=0.5)

# Check if high confidence
if output.is_high_confidence(threshold=0.7):
    # Proceed with tracking
```

### Serialization

```python
# To dictionary
data = output.to_dict()

# From dictionary
output = TrackerOutput.from_dict(data)
```

---

## Legacy Compatibility

For backwards compatibility with older code:

```python
from classes.tracker_output import create_legacy_tracker_output

output = create_legacy_tracker_output(
    center=(320, 240),
    normalized_center=(0.1, -0.2),
    bbox=(295, 200, 50, 80),
    confidence=0.85,
    tracking_active=True
)
```

---

## Schema Configuration

Schemas are defined in `configs/tracker_schemas.yaml`:

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
        range: [-2.0, 2.0]  # Allow off-screen
```

---

## Tracker-Follower Compatibility

The schema system ensures trackers and followers use compatible data:

```yaml
# From tracker_schemas.yaml
compatibility:
  followers:
    MCVelocityChaseFollower:
      required_schemas:
        - POSITION_2D
      compatible_schemas:
        - POSITION_3D
        - MULTI_TARGET
```

---

## Related

- [BaseTracker](base-tracker.md) - Trackers generate TrackerOutput
- [Schema System](../04-configuration/schema-system.md) - YAML configuration
- [Follower Integration](../06-integration/follower-integration.md) - How followers consume output
