# AI Tracking Concepts

> Deep learning and multi-object tracking algorithms used in SmartTracker

This section covers the AI/ML concepts powering PixEagle's SmartTracker:
the current Ultralytics YOLO backend, the backend extension contract,
ByteTrack/BoT-SORT multi-object tracking, and motion prediction.

---

## Section Contents

| Document | Description |
|----------|-------------|
| [Detection Backends](detection-backends.md) | Backend architecture, supported models, and guide to adding new backends |
| [Detection Model Catalog](../../MODEL_CATALOG.md) | Supported baselines and reviewed domain-tuned candidates |
| [ByteTrack/BoT-SORT](bytetrack-botsort.md) | Multi-object tracking algorithms |
| [Motion Prediction](motion-prediction.md) | MotionPredictor component |
| [Appearance Model](appearance-model.md) | ReID and appearance matching |

---

## SmartTracker Overview

The SmartTracker combines multiple AI components:

```
Video Frame
    |
    v
+------------------+
| DetectionBackend | <--- Pluggable contract; Ultralytics is registered now
| (ABC interface)  |
+--------+---------+
         |
         v
+------------------+
| ByteTrack/BoT-   | <--- Multi-object association
| SORT Tracker     |
+--------+---------+
         |
         v
+------------------+
| Motion Predictor | <--- Trajectory prediction
| + Appearance     |
+--------+---------+
         |
         v
+------------------+
| Target Selection | <--- Select primary tracking target
+------------------+
```

---

## Key Concepts

### Object Detection

The pluggable detection backend provides real-time object detection:

- **Registered backend**: Ultralytics YOLO with `detect` and `obb` task policy
- **Extensible contract**: Other runtimes require an adapter plus artifact,
  config, API, resource, tracking, and target-hardware evidence
- **Output**: `NormalizedDetection` — universal schema consumed by all downstream components
- **Performance**: Must be measured end to end on the selected model, video
  pipeline, and target computer

### Multi-Object Tracking (MOT)

ByteTrack/BoT-SORT associates detections across frames:

- **Track Management**: Create, update, delete tracks
- **Association**: Match detections to existing tracks
- **Re-identification**: Recover lost tracks

### Motion Prediction

The MotionPredictor handles:

- **Kalman Filtering**: Smooth trajectory estimation
- **Velocity Estimation**: Predict target movement
- **Occlusion Handling**: Maintain tracks during brief occlusions

---

## Configuration

```yaml
SmartTracker:
  SMART_TRACKER_ENABLED: true
  DETECTION_BACKEND: "ultralytics"                    # Backend selection
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26n.pt"   # Model selection
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.5             # Detection threshold
  SMART_TRACKER_IOU_THRESHOLD: 0.45                    # NMS threshold
  SMART_TRACKER_MAX_DETECTIONS: 100                   # Max objects per frame
```

---

## Related Sections

- [SmartTracker Reference](../02-reference/smart-tracker.md) - Implementation details
- [Configuration](../04-configuration/README.md) - Parameter tuning
