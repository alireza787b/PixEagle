# AI Tracking Concepts

> Deep learning and multi-object tracking algorithms used in SmartTracker

This section covers the AI/ML concepts powering PixEagle's SmartTracker, including pluggable detection backends (Ultralytics YOLO, with support for adding ONNX Runtime, TensorRT, RT-DETR, etc.), ByteTrack/BoT-SORT multi-object tracking, and motion prediction.

---

## Section Contents

| Document | Description |
|----------|-------------|
| [Detection Backends](detection-backends.md) | Backend architecture, supported models, and guide to adding new backends |
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
| DetectionBackend | <--- Pluggable backend (Ultralytics, ONNX, TensorRT...)
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

- **Default backend**: Ultralytics (YOLO v5–v12, 11, 26, OBB, VisDrone)
- **Extensible**: Add ONNX Runtime, TensorRT, RT-DETR, OpenVINO via one Python class
- **Output**: `NormalizedDetection` — universal schema consumed by all downstream components
- **Speed**: 15-100+ FPS depending on model, backend, and device

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
DETECTION_BACKEND: "ultralytics"                    # Backend selection
SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26n.pt"   # Model selection
SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.5             # Detection threshold
SMART_TRACKER_IOU_THRESHOLD: 0.45                   # NMS threshold
SMART_TRACKER_MAX_DETECTIONS: 100                   # Max objects per frame
```

---

## Related Sections

- [SmartTracker Reference](../02-reference/smart-tracker.md) - Implementation details
- [Configuration](../04-configuration/README.md) - Parameter tuning
