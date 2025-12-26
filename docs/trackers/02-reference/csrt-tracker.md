# CSRT Tracker

> Channel and Spatial Reliability Tracking - Best for rotation and occlusion handling

The CSRT tracker uses OpenCV's implementation of the Discriminative Correlation Filter with Channel and Spatial Reliability (CVPR 2017). Located at `src/classes/trackers/csrt_tracker.py`.

---

## Overview

**Best for:**
- Objects that rotate frequently (drone circling target)
- Perspective changes during camera movement
- Partial occlusions
- High accuracy requirements (15-25 FPS acceptable)

**Strengths:**
- Rotation-invariant (in-plane and out-of-plane)
- Scale adaptation
- Partial occlusion handling
- HOG + ColorNames features

**Limitations:**
- Medium speed (15-25 FPS)
- Higher CPU usage than KCF/dlib

---

## Performance Modes

CSRT supports three configurable performance modes:

| Mode | FPS | Features | Use Case |
|------|-----|----------|----------|
| `legacy` | 15-20 | Original behavior, no validation | Fastest, most reliable startup |
| `balanced` | 12-18 | Light enhancements, confidence smoothing | Good trade-off (default) |
| `robust` | 10-15 | Full validation, EMA smoothing | Maximum stability |

### Configuration

```yaml
# configs/config.yaml
CSRT_Tracker:
  performance_mode: "balanced"  # legacy, balanced, robust
  confidence_threshold: 0.5
  failure_threshold: 5
  validation_start_frame: 10    # Grace period

  # OpenCV CSRT parameters
  use_color_names: true
  use_hog: true
  csrt_learning_rate: 0.02
  number_of_scales: 33
  scale_step: 1.02
  use_segmentation: true

  # Multi-frame validation
  enable_multiframe_validation: true
  validation_consensus_frames: 3
```

---

## Algorithm Details

### Feature Extraction

CSRT uses multiple feature channels:

```python
# OpenCV CSRT Parameters
params = cv2.TrackerCSRT_Params()
params.use_color_names = True   # ColorNames features (+5-8% accuracy)
params.use_hog = True           # HOG features (essential)
params.number_of_scales = 33    # Scale pyramid levels
params.scale_step = 1.02        # Finer scale steps
params.use_segmentation = True  # Foreground/background separation
```

### Confidence Computation

CSRT computes confidence from:

1. **Motion consistency** - Penalizes erratic movement
2. **Appearance confidence** - Feature similarity to template

```python
confidence = (MOTION_WEIGHT * motion_confidence +
              APPEARANCE_WEIGHT * appearance_confidence)
```

### Appearance Model Update

Template updates with drift protection:

```python
def _should_update_appearance(self, frame, bbox) -> bool:
    # Only update when:
    # 1. Confidence above threshold + margin
    # 2. Motion is consistent
    # 3. Scale change is reasonable (<30%)

    if self.confidence < min_update_confidence:
        return False
    if motion_confidence < 0.7:
        return False
    if scale_change > 0.3:
        return False
    return True
```

---

## TrackerOutput

CSRT produces output with quality metrics:

```python
TrackerOutput(
    data_type=TrackerDataType.VELOCITY_AWARE,  # If estimator enabled
    position_2d=(0.1, -0.2),
    confidence=0.85,
    velocity=(5.2, -1.3),  # From Kalman estimator
    quality_metrics={
        'motion_consistency': 0.92,
        'appearance_confidence': 0.88,
        'failure_count': 0,
        'success_rate': 0.97
    },
    raw_data={
        'performance_mode': 'balanced',
        'frame_count': 150,
        'avg_fps': 18.5
    }
)
```

---

## Usage

### Basic Usage

```python
from classes.trackers.tracker_factory import create_tracker

# Create CSRT tracker
tracker = create_tracker("CSRT", video_handler, detector, app_controller)

# Initialize with first frame and bbox
tracker.start_tracking(frame, (100, 200, 50, 80))

# Update on each frame
success, bbox = tracker.update(frame)

if success:
    output = tracker.get_output()
    print(f"Position: {output.position_2d}, Confidence: {output.confidence}")
```

### With SmartTracker Override

```python
# SmartTracker can override CSRT with YOLO detections
if smart_tracker.selected_bbox:
    tracker.set_external_override(smart_tracker.selected_bbox,
                                  smart_tracker.selected_center)
```

---

## Performance Tuning

### For Speed

```yaml
CSRT_Tracker:
  performance_mode: "legacy"
  use_color_names: false  # Disable ColorNames
  number_of_scales: 17    # Fewer scale levels
```

### For Accuracy

```yaml
CSRT_Tracker:
  performance_mode: "robust"
  use_color_names: true
  use_hog: true
  number_of_scales: 33
  enable_multiframe_validation: true
```

### For Occlusion Handling

```yaml
CSRT_Tracker:
  performance_mode: "balanced"
  failure_threshold: 7      # More tolerance
  validation_start_frame: 5 # Earlier validation
  appearance_update_min_confidence: 0.6
```

---

## Capabilities

```python
tracker.get_capabilities()
# {
#     'tracker_algorithm': 'CSRT',
#     'supports_rotation': True,
#     'supports_scale_change': True,
#     'supports_occlusion': True,
#     'accuracy_rating': 'very_high',
#     'speed_rating': 'medium',
#     'opencv_tracker': True,
#     'performance_mode': 'balanced'
# }
```

---

## References

- Lukezic et al., "Discriminative Correlation Filter with Channel and Spatial Reliability," CVPR 2017
- OpenCV Tracking API: https://docs.opencv.org/master/d9/df8/group__tracking.html

---

## Related

- [KCF + Kalman](kcf-kalman-tracker.md) - Faster alternative
- [dlib Tracker](dlib-tracker.md) - Ultra-fast alternative
- [Configuration](../04-configuration/README.md) - Parameter tuning
