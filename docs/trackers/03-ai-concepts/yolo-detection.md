# YOLO Detection

> Real-time object detection powering SmartTracker

YOLO (You Only Look Once) provides the detection backbone for SmartTracker, identifying objects and their classes in real-time.

---

## Overview

SmartTracker uses Ultralytics YOLO for:

- **Object detection** - Bounding boxes with confidence scores
- **Classification** - Object class identification (person, vehicle, etc.)
- **GPU acceleration** - Fast inference on CUDA devices
- **CPU fallback** - NCNN models for CPU-only systems

---

## Supported Models

### PyTorch Models (.pt)

For GPU inference:

| Model | Size | Speed (RTX 3060) | Accuracy |
|-------|------|-----------------|----------|
| yolo11n.pt | 6 MB | 60+ FPS | Good |
| yolo11s.pt | 20 MB | 45+ FPS | Better |
| yolo11m.pt | 68 MB | 30+ FPS | Best |
| yolov8n.pt | 6 MB | 55+ FPS | Good |

### NCNN Models

For CPU inference:

| Model | Speed (i7) | Notes |
|-------|-----------|-------|
| yolo11n_ncnn_model | 25-35 FPS | Recommended for CPU |
| yolov8n_ncnn_model | 20-30 FPS | Alternative |

---

## Configuration

```yaml
# configs/config.yaml
SmartTracker:
  # Model paths
  SMART_TRACKER_GPU_MODEL_PATH: "yolo/yolo11n.pt"
  SMART_TRACKER_CPU_MODEL_PATH: "yolo/yolo11n_ncnn_model"

  # Device selection
  SMART_TRACKER_USE_GPU: true
  SMART_TRACKER_FALLBACK_TO_CPU: true

  # Detection parameters
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.3
  SMART_TRACKER_IOU_THRESHOLD: 0.3
  SMART_TRACKER_MAX_DETECTIONS: 20
```

---

## Detection Pipeline

```python
# SmartTracker YOLO inference
def detect(self, frame):
    results = self.model.track(
        frame,
        persist=True,              # Maintain track IDs
        conf=self.conf_threshold,  # Confidence threshold
        iou=self.iou_threshold,    # NMS IoU threshold
        max_det=self.max_det,      # Max detections
        tracker=self.tracker_type  # ByteTrack or BoT-SORT
    )
    return results
```

### Detection Output

```python
# Per detection
{
    'bbox': (x1, y1, x2, y2),  # Bounding box
    'class_id': 0,             # Class index
    'class_name': 'person',    # Class label
    'confidence': 0.92,        # Detection confidence
    'track_id': 5              # Assigned track ID
}
```

---

## Model Loading

### GPU with Fallback

```python
try:
    model = YOLO(gpu_model_path)
    model.to('cuda')
except Exception as e:
    if fallback_enabled:
        model = YOLO(cpu_model_path)
```

### NCNN Export

For CPU deployment:

```bash
# Export to NCNN format
yolo export model=yolo11n.pt format=ncnn
```

---

## Class Filtering

Filter detections by class:

```yaml
SmartTracker:
  # Only detect specific classes
  SMART_TRACKER_CLASSES: [0, 2, 7]  # person, car, truck
```

```python
# COCO class indices
0: person
1: bicycle
2: car
3: motorcycle
5: bus
7: truck
```

---

## Performance Optimization

### For Speed

```yaml
SmartTracker:
  SMART_TRACKER_GPU_MODEL_PATH: "yolo/yolo11n.pt"  # Nano model
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.4         # Higher threshold
  SMART_TRACKER_MAX_DETECTIONS: 10                # Fewer detections
```

### For Accuracy

```yaml
SmartTracker:
  SMART_TRACKER_GPU_MODEL_PATH: "yolo/yolo11m.pt"  # Medium model
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.2          # Lower threshold
  SMART_TRACKER_IOU_THRESHOLD: 0.4                 # Stricter NMS
```

---

## Custom Models

Train custom YOLO models for specific targets:

```python
# Training custom model
from ultralytics import YOLO

model = YOLO('yolo11n.pt')
model.train(data='custom_dataset.yaml', epochs=100)
```

Use custom model:

```yaml
SmartTracker:
  SMART_TRACKER_GPU_MODEL_PATH: "yolo/custom_drone_detector.pt"
```

---

## Related

- [SmartTracker](../02-reference/smart-tracker.md) - Full SmartTracker documentation
- [ByteTrack/BoT-SORT](bytetrack-botsort.md) - Multi-object tracking
- [Configuration](../04-configuration/README.md) - Parameter tuning
