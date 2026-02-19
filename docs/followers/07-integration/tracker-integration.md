# Tracker Integration

> Connecting trackers to followers

---

## TrackerOutput Data Structure

The standard interface between trackers and followers:

```python
@dataclass
class TrackerOutput:
    # Required
    data_type: TrackerDataType
    timestamp: float

    # Position data (normalized -1 to +1)
    position_2d: Optional[Tuple[float, float]] = None
    position_3d: Optional[Tuple[float, float, float]] = None

    # Gimbal data
    gimbal_pan: Optional[float] = None
    gimbal_tilt: Optional[float] = None

    # Tracking metadata
    tracking_active: bool = False
    tracker_id: Optional[int] = None
    confidence: Optional[float] = None
    bbox: Optional[Tuple[int, int, int, int]] = None

    # Velocity estimation
    velocity: Optional[Tuple[float, float]] = None
```

---

## Data Types

```python
class TrackerDataType(Enum):
    POSITION_2D = "position_2d"
    POSITION_3D = "position_3d"
    GIMBAL_ANGLES = "gimbal_angles"
    BBOX_CONFIDENCE = "bbox_confidence"
    VELOCITY_AWARE = "velocity_aware"
```

---

## Coordinate Systems

### Image Coordinates (Raw)

```
(0,0) ──────────────────────► X (width)
  │
  │       ● Target (x_px, y_px)
  │
  ▼
  Y (height)
```

### Normalized Coordinates (TrackerOutput)

```
        (-1, -1)      (0, -1)       (+1, -1)
           ┌────────────┬────────────┐
           │            │            │
           │            │            │
(-1, 0) ───┼────────────●────────────┼─── (+1, 0)
           │         (0,0)           │
           │         Center          │
           │            │            │
           └────────────┴────────────┘
        (-1, +1)      (0, +1)       (+1, +1)
```

### Conversion

```python
def normalize_coordinates(x_px, y_px, width, height):
    """Convert pixel to normalized coordinates."""
    x_norm = (x_px / width) * 2 - 1   # [-1, +1]
    y_norm = (y_px / height) * 2 - 1  # [-1, +1]
    return x_norm, y_norm
```

---

## Tracker Types

### SmartTracker

YOLO + ByteTrack/BoT-SORT:

```python
from classes.tracker import SmartTracker

tracker = SmartTracker()

# Update with frame
tracker_output = tracker.update(frame)

# Output includes confidence, bbox, velocity
```

### ClassicTracker

OpenCV trackers (CSRT, etc.):

```python
from classes.classic_tracker import ClassicTracker

tracker = ClassicTracker()
tracker.init(frame, roi)

tracker_output = tracker.update(frame)
```

### GimbalTracker

For gimbal-based tracking:

```python
# Gimbal angles instead of image position
tracker_output = TrackerOutput(
    data_type=TrackerDataType.GIMBAL_ANGLES,
    gimbal_pan=5.2,   # degrees
    gimbal_tilt=-2.1,
    tracking_active=True
)
```

---

## Follower Compatibility

### Check Requirements

```python
# Get required data types for follower
required = follower.get_required_tracker_data_types()
# [TrackerDataType.POSITION_2D]

# Validate compatibility
compatible = follower.validate_tracker_compatibility(tracker_output)
```

### Schema-Defined Requirements

In `follower_commands.yaml`:

```yaml
follower_profiles:
  mc_velocity_chase:
    required_tracker_data:
      - POSITION_2D
    optional_tracker_data:
      - BBOX_CONFIDENCE
      - VELOCITY_AWARE

  gm_velocity_chase:
    required_tracker_data:
      - GIMBAL_ANGLES
```

---

## Target Loss Handling

### Detection

```python
# Check if target is lost
if tracker_output.position_2d is None:
    target_lost = True

# Or check coordinates
if abs(tracker_output.position_2d[0]) > 1.5:  # Outside frame
    target_lost = True

# Or check confidence
if tracker_output.confidence < 0.5:
    low_confidence = True
```

### Follower Response

```python
def follow_target(self, tracker_data):
    # Check for target loss
    if not self._handle_target_loss(tracker_data):
        # Use last valid coordinates
        return self._execute_loss_behavior()

    # Normal following
    self.calculate_control_commands(tracker_data)
    return True
```

---

## Confidence Handling

### Confidence-Based Filtering

```python
if tracker_output.confidence is not None:
    if tracker_output.confidence < self.min_confidence:
        logger.warning(f"Low confidence: {tracker_output.confidence}")
        return False
```

### Velocity Scaling

```python
# Reduce velocity at low confidence
scale = min(1.0, tracker_output.confidence)
vel_fwd *= scale
vel_right *= scale
```

---

## Velocity-Aware Tracking

When tracker provides velocity estimates:

```python
if tracker_output.data_type == TrackerDataType.VELOCITY_AWARE:
    # Predictive following
    vx, vy = tracker_output.velocity
    predicted_x = tracker_output.position_2d[0] + vx * dt
    predicted_y = tracker_output.position_2d[1] + vy * dt
```

---

## Bounding Box Usage

### Distance Estimation

```python
# Larger bbox = closer target
if tracker_output.bbox:
    x, y, w, h = tracker_output.bbox
    bbox_area = w * h
    estimated_distance = calibration / sqrt(bbox_area)
```

### Size Tracking

```python
# Track target size changes
current_size = bbox_area
size_rate = (current_size - prev_size) / dt
```

---

## Integration Example

```python
class TrackingLoop:
    def __init__(self):
        self.px4 = PX4Controller()
        self.tracker = SmartTracker()
        self.follower = Follower(self.px4, (0, 0))

    def run(self, frame):
        # Get tracker output
        tracker_output = self.tracker.update(frame)

        # Check tracking state
        if not tracker_output.tracking_active:
            self.handle_no_tracking()
            return

        # Execute following
        success = self.follower.follow_target(tracker_output)

        if not success:
            logger.warning("Following failed")
```
