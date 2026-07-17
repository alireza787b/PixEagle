# SmartTracker

> AI-powered detection and multi-object tracking with optional local appearance matching

SmartTracker combines Ultralytics YOLO inference with ByteTrack or BoT-SORT for
multi-target tracking. PixEagle can optionally add its local AppearanceModel by
selecting `custom_reid`. The implementation is in `src/classes/smart_tracker.py`.

---

## Overview

**Best for:**
- Multi-target tracking scenarios
- Object classification (person, vehicle, etc.)
- Automatic target selection
- Configurable ID, spatial, prediction, and local appearance recovery
- GPU-accelerated systems

**Key Features:**
- Ultralytics YOLO detect/OBB inference
- ByteTrack or BoT-SORT tracking
- Optional PixEagle `custom_reid` appearance matching
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

SmartTracker is controlled by the explicit **Smart Mode** lifecycle:

1. The operator activates Smart Mode.
2. `AppController` creates SmartTracker and runs it in the frame loop.
3. A click selects one of the current detections and applies the classic-tracker override.
4. Deactivating Smart Mode clears selection and releases the SmartTracker instance.

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
  # Schema-backed availability setting; activation is still an operator action
  SMART_TRACKER_ENABLED: true

  # Model selection
  # Both artifacts must be registered in models/.model-provenance.json
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26n.pt"
  SMART_TRACKER_CPU_MODEL_PATH: "models/yolo26n_ncnn_model"
  SMART_TRACKER_USE_GPU: true
  SMART_TRACKER_FALLBACK_TO_CPU: true

  # Detection parameters
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.3
  SMART_TRACKER_IOU_THRESHOLD: 0.3
  SMART_TRACKER_MAX_DETECTIONS: 20

  # Tracker type
  # Options: "botsort", "bytetrack", "custom_reid"
  TRACKER_TYPE: "botsort"

  # Tracking strategy
  # Options: "id_only", "hybrid", "spatial_only"
  TRACKING_STRATEGY: "hybrid"

  # Motion prediction (occlusion handling)
  ENABLE_PREDICTION_BUFFER: true
  ID_LOSS_TOLERANCE_FRAMES: 5

  # Appearance model (for custom ReID)
  ENABLE_APPEARANCE_MODEL: true

  # Display
  SMART_TRACKER_SHOW_FPS: false
  SMART_TRACKER_ACTIVE_COLOR: [0, 255, 100]
  SMART_TRACKER_PASSIVE_COLOR: [140, 140, 140]
```

---

## Tracker Types

### BoT-SORT (Default)

```yaml
TRACKER_TYPE: "botsort"
```

- Uses the installed Ultralytics `botsort.yaml`
- Does not enable native ReID
- PixEagle does not expose custom BoT-SORT YAML settings

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
- Runs ByteTrack for track IDs, then allows local appearance matching in the
  TrackingStateManager
- Requires scenario-specific false-match and reacquisition evidence

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
4. Apply appearance matching only when `TRACKER_TYPE: "custom_reid"` and the
   appearance model is enabled

### Spatial Only

```yaml
TRACKING_STRATEGY: "spatial_only"
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

SmartTracker is managed by `AppController`. The application frame loop owns
inference and the state barrier; callers use the lifecycle and click APIs:

```python
app_controller.toggle_smart_mode()
selection = app_controller.handle_smart_click(x, y)
```

`toggle_smart_mode()` creates or releases SmartTracker. `handle_smart_click()`
selects from the latest detections and returns a structured result. There is no
`process_frame()`, track-ID selection, or class-name selection API.

### Target Selection

```python
# Direct SmartTracker API used by AppController while holding its state barrier
smart_tracker.select_object_by_click(x, y)
annotated_frame = smart_tracker.track_and_draw(frame)
```

Application integrations should call `AppController.handle_smart_click()` and
let the controller frame loop invoke `track_and_draw()` under its lock.

---

## Readiness Check

```bash
bash scripts/setup/check-ai-runtime.sh --require-smart-tracker
```

Despite the compatibility flag name, success proves only required imports,
provenance and digest verification, local model loading, task/device policy,
and one `detect()` call on a fixed 64x64 zero-valued frame. The report exposes
the verified artifact digest under `model_probe.model_provenance`; it leaves
`readiness.tracking_ready` unset. The bounded probe does not call
`model.track()` because this slice cannot enforce an offline/no-implicit-
artifact contract for that upstream path. Prove tracker initialization,
associations, camera input, latency, and target recovery separately on the
deployment host.

---

## Performance

PixEagle does not publish a generic FPS or accuracy guarantee. Results depend
on the exact model artifact, task, image size, source pipeline, tracker mode,
thermal state, accelerator/runtime versions, and target hardware. Measure the
complete configured pipeline on the deployment host and retain the result with
test evidence.

---

## Model Selection

Paths must name trusted direct children of the configured models directory.
Register the `.pt` artifact and any derived NCNN export through the model setup
workflow before changing these values; PixEagle will not load an unregistered
or digest-changed artifact.

```yaml
# Nano models (fastest)
SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26n.pt"
SMART_TRACKER_CPU_MODEL_PATH: "models/yolo26n_ncnn_model"

# Small models (better accuracy)
SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26s.pt"

# Custom trained models
SMART_TRACKER_GPU_MODEL_PATH: "models/custom_model.pt"
```

---

## Integration with Classic Trackers

SmartTracker can provide an external override to a classic tracker after the
operator selects a current detection:

```
Classic Tracker (CSRT, KCF, dlib)
        ↑
        │ Override when SmartTracker active
        │
SmartTracker (Inference + configured tracker)
        │
        │ Provides:
        │ - More robust detection
        │ - Optional custom appearance matching after loss
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
