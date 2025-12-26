# AI Tracking Concepts

> Deep learning and multi-object tracking algorithms used in SmartTracker

This section covers the AI/ML concepts powering PixEagle's SmartTracker, including YOLO object detection, ByteTrack/BoT-SORT multi-object tracking, and motion prediction.

---

## Section Contents

| Document | Description |
|----------|-------------|
| [YOLO Detection](yolo-detection.md) | YOLO model integration and inference |
| [ByteTrack/BoT-SORT](bytetrack-botsort.md) | Multi-object tracking algorithms |
| [Motion Prediction](motion-prediction.md) | MotionPredictor component |
| [Appearance Model](appearance-model.md) | ReID and appearance matching |

---

## SmartTracker Overview

The SmartTracker combines multiple AI components:

```
Video Frame
    │
    ▼
┌──────────────────┐
│ YOLO Detection   │ ◄─── Object detection (person, vehicle, etc.)
│ (YOLOv8/v11)     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ ByteTrack/BoT-   │ ◄─── Multi-object association
│ SORT Tracker     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Motion Predictor │ ◄─── Trajectory prediction
│ + Appearance     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Target Selection │ ◄─── Select primary tracking target
└──────────────────┘
```

---

## Key Concepts

### Object Detection (YOLO)

YOLO (You Only Look Once) provides real-time object detection:

- **Models**: YOLOv8n, YOLOv8s, YOLOv8m, YOLOv11
- **Output**: Bounding boxes, class labels, confidence scores
- **Speed**: 15-60+ FPS depending on model and GPU

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
# SmartTracker settings in config.yaml
ENABLE_SMART_TRACKER: true
YOLO_MODEL: "yolov8n.pt"           # Model selection
YOLO_CONFIDENCE_THRESHOLD: 0.5     # Detection threshold
YOLO_IOU_THRESHOLD: 0.45           # NMS threshold
YOLO_MAX_DETECTIONS: 100           # Max objects per frame
```

---

## Related Sections

- [SmartTracker Reference](../02-reference/smart-tracker.md) - Implementation details
- [Configuration](../04-configuration/README.md) - Parameter tuning
