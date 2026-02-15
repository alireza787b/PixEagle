# SmartTracker

> AI-powered tracking with multi-object support and re-identification

SmartTracker combines deep-learning object detection (Ultralytics YOLO) with ByteTrack/BoT-SORT for AI-powered multi-target tracking. Located at `src/classes/smart_tracker.py`.

---

## Overview

**Best for:**
- Multi-target tracking scenarios
- Object classification (person, vehicle, etc.)
- Automatic target selection
- Re-identification after occlusion
- GPU-accelerated systems

**Key Features:**
- Ultralytics YOLO v8/v11 object detection
- ByteTrack or BoT-SORT tracking
- Native or custom Re-ID
- Motion prediction during occlusion
- Appearance model for recovery

**Architecture:**

```
Frame
  ↓
Detection Model → Bounding boxes + class labels
  ↓
ByteTrack/BoT-SORT → Track IDs + associations
  ↓
TrackingStateManager → ID matching, spatial fallback
  ↓
MotionPredictor → Occlusion handling
  ↓
AppearanceModel → Re-identification (optional)
  ↓
TrackerOutput (MULTI_TARGET or POSITION_2D)
```

---

## Operation Mode

SmartTracker operates as an **overlay** on classic trackers:

1. **Always runs in background** when enabled
2. **Provides detections** to override classic tracker
3. **Handles target selection** from multiple objects
4. **Re-acquires targets** after occlusion or ID loss

```python
# SmartTracker overrides classic tracker
if smart_tracker.selected_bbox:
    classic_tracker.set_external_override(
        smart_tracker.selected_bbox,
        smart_tracker.selected_center
    )
```

---

## Configuration

```yaml
# configs/config.yaml
SmartTracker:
  # Enable/disable
  ENABLE_SMART_TRACKER: true

  # Model selection
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo11n.pt"
  SMART_TRACKER_CPU_MODEL_PATH: "models/yolo11n_ncnn_model"
  SMART_TRACKER_USE_GPU: true
  SMART_TRACKER_FALLBACK_TO_CPU: true

  # Detection parameters
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.3
  SMART_TRACKER_IOU_THRESHOLD: 0.3
  SMART_TRACKER_MAX_DETECTIONS: 20

  # Tracker type
  # Options: "botsort_reid", "botsort", "bytetrack", "custom_reid"
  TRACKER_TYPE: "botsort_reid"

  # Tracking strategy
  # Options: "id_only", "hybrid", "spatial"
  TRACKING_STRATEGY: "hybrid"

  # Motion prediction (occlusion handling)
  ENABLE_PREDICTION_BUFFER: true
  ID_LOSS_TOLERANCE_FRAMES: 5

  # Appearance model (for custom ReID)
  ENABLE_APPEARANCE_MODEL: true

  # Display
  SMART_TRACKER_SHOW_FPS: false
  SMART_TRACKER_COLOR: [0, 255, 255]
```

---

## Tracker Types

### BoT-SORT with Native ReID (Recommended)

```yaml
TRACKER_TYPE: "botsort_reid"
```

- Requires Ultralytics >= 8.3.114
- Uses built-in appearance features
- Best re-identification performance

### BoT-SORT without ReID

```yaml
TRACKER_TYPE: "botsort"
```

- Motion-based association only
- Faster, less memory

### ByteTrack

```yaml
TRACKER_TYPE: "bytetrack"
```

- Classic ByteTrack algorithm
- Good for simpler scenarios

### Custom ReID

```yaml
TRACKER_TYPE: "custom_reid"
```

- Uses PixEagle's AppearanceModel
- For older Ultralytics versions

---

## Tracking Strategies

### ID Only

```yaml
TRACKING_STRATEGY: "id_only"
```

Only matches by ByteTrack/BoT-SORT assigned ID. Fails if ID changes.

### Hybrid (Recommended)

```yaml
TRACKING_STRATEGY: "hybrid"
```

1. Try ID matching first
2. Fall back to spatial matching
3. Use motion prediction during occlusion
4. Apply appearance re-ID for recovery

### Spatial

```yaml
TRACKING_STRATEGY: "spatial"
```

Uses spatial proximity only, ignores IDs.

---

## Components

### TrackingStateManager

Coordinates all tracking logic:

```python
class TrackingStateManager:
    def update(self, detections, frame):
        # 1. Try ID-based matching
        # 2. Fall back to spatial matching
        # 3. Use motion prediction if lost
        # 4. Apply appearance re-ID
        return selected_detection
```

### MotionPredictor

Predicts position during brief detection loss:

```python
class MotionPredictor:
    def predict(self, last_positions):
        # Estimate velocity from history
        # Extrapolate position
        return predicted_center, predicted_bbox
```

### AppearanceModel

Stores and matches visual features:

```python
class AppearanceModel:
    def update(self, frame, bbox, track_id):
        # Extract features from crop
        # Update feature bank

    def find_match(self, frame, detections):
        # Compare features to stored templates
        # Return best matching detection
```

---

## TrackerOutput

### MULTI_TARGET Mode

```python
TrackerOutput(
    data_type=TrackerDataType.MULTI_TARGET,
    tracking_active=True,

    targets=[
        {"target_id": 1, "class_name": "person", "confidence": 0.95,
         "bbox": (100, 150, 50, 120), "is_selected": True},
        {"target_id": 2, "class_name": "car", "confidence": 0.88,
         "bbox": (300, 200, 150, 80), "is_selected": False}
    ],

    # Selected target
    target_id=1,
    position_2d=(0.1, -0.2),
    confidence=0.95
)
```

### POSITION_2D Mode (Selected Target)

```python
TrackerOutput(
    data_type=TrackerDataType.POSITION_2D,
    tracking_active=True,
    position_2d=(0.1, -0.2),
    confidence=0.95,
    metadata={
        'selected_class': 'person',
        'selected_track_id': 1
    }
)
```

---

## Usage

### With AppController

SmartTracker is typically managed by AppController:

```python
# In AppController
if Parameters.ENABLE_SMART_TRACKER:
    self.smart_tracker = SmartTracker(self)

# During frame processing
results = self.smart_tracker.process_frame(frame)

if self.smart_tracker.selected_object_id:
    # SmartTracker has a selected target
    self.tracker.set_external_override(
        self.smart_tracker.selected_bbox,
        self.smart_tracker.selected_center
    )
```

### Target Selection

```python
# Select target by clicking on detection
smart_tracker.select_target(track_id=1)

# Or by class
smart_tracker.select_target_by_class("person")
```

---

## Performance

| Model | GPU (RTX 3060) | CPU | Accuracy |
|-------|----------------|-----|----------|
| YOLOv8n | 60+ FPS | 15-20 FPS | Good |
| YOLOv8s | 45+ FPS | 10-15 FPS | Better |
| YOLOv11n | 55+ FPS | 15-20 FPS | Good |
| NCNN (CPU) | N/A | 25-35 FPS | Good |

---

## Model Selection

```yaml
# Nano models (fastest)
SMART_TRACKER_GPU_MODEL_PATH: "models/yolo11n.pt"
SMART_TRACKER_CPU_MODEL_PATH: "models/yolo11n_ncnn_model"

# Small models (better accuracy)
SMART_TRACKER_GPU_MODEL_PATH: "models/yolo11s.pt"

# Custom trained models
SMART_TRACKER_GPU_MODEL_PATH: "models/custom_model.pt"
```

---

## Integration with Classic Trackers

SmartTracker enhances classic trackers:

```
Classic Tracker (CSRT, KCF, dlib)
        ↑
        │ Override when SmartTracker active
        │
SmartTracker (Detection + ByteTrack)
        │
        │ Provides:
        │ - More robust detection
        │ - Re-identification after loss
        │ - Multi-target support
        ↓
Follower System
```

---

## Related

- [Detection Backends](../03-ai-concepts/detection-backends.md) - Detection details
- [ByteTrack/BoT-SORT](../03-ai-concepts/bytetrack-botsort.md) - Tracking algorithms
- [Motion Prediction](../03-ai-concepts/motion-prediction.md) - Occlusion handling
- [Configuration](../04-configuration/README.md) - Parameter tuning
