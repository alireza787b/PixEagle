# Tuning Guide

> Performance vs accuracy optimization for different scenarios

This guide helps tune tracker parameters for specific use cases and hardware.

---

## Quick Tuning Profiles

### Maximum Speed (Embedded Systems)

For Raspberry Pi, Jetson Nano, or speed-critical applications:

```yaml
TRACKING_ALGORITHM: "KCF"

KCF_Tracker:
  confidence_threshold: 0.1
  failure_threshold: 10
  motion_consistency_threshold: 0.25

# Disable SmartTracker
SmartTracker:
  ENABLE_SMART_TRACKER: false
```

### Maximum Accuracy (GPU Available)

For high-accuracy requirements with GPU:

```yaml
TRACKING_ALGORITHM: "CSRT"

CSRT_Tracker:
  performance_mode: "robust"
  use_color_names: true
  use_hog: true
  number_of_scales: 33
  enable_multiframe_validation: true

SmartTracker:
  ENABLE_SMART_TRACKER: true
  TRACKER_TYPE: "botsort_reid"
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo11s.pt"
```

### Balanced (Default)

Good trade-off for most scenarios:

```yaml
TRACKING_ALGORITHM: "CSRT"

CSRT_Tracker:
  performance_mode: "balanced"

SmartTracker:
  ENABLE_SMART_TRACKER: true
  TRACKER_TYPE: "botsort_reid"
```

---

## Scenario-Specific Tuning

### Fast-Moving Targets

```yaml
TRACKING_ALGORITHM: "KCF"

KCF_Tracker:
  motion_consistency_threshold: 0.3  # Allow larger movement
  use_velocity_during_occlusion: true
  kalman_process_noise: 0.2  # Trust motion model more

SmartTracker:
  ID_LOSS_TOLERANCE_FRAMES: 8  # More prediction frames
```

### Rotating Targets

```yaml
TRACKING_ALGORITHM: "CSRT"

CSRT_Tracker:
  performance_mode: "robust"
  use_hog: true  # Essential for rotation
  number_of_scales: 33
```

### Frequent Occlusions

```yaml
TRACKING_ALGORITHM: "KCF"

KCF_Tracker:
  failure_threshold: 10  # More tolerance
  use_velocity_during_occlusion: true
  occlusion_velocity_factor: 0.7

SmartTracker:
  ENABLE_SMART_TRACKER: true
  TRACKER_TYPE: "botsort_reid"  # ReID for recovery
  ENABLE_PREDICTION_BUFFER: true
  ID_LOSS_TOLERANCE_FRAMES: 7
```

### Multiple Targets

```yaml
TRACKING_ALGORITHM: "CSRT"  # Base tracker

SmartTracker:
  ENABLE_SMART_TRACKER: true
  TRACKER_TYPE: "botsort_reid"
  TRACKING_STRATEGY: "hybrid"
  SMART_TRACKER_MAX_DETECTIONS: 30
```

### External Gimbal

```yaml
TRACKING_ALGORITHM: "Gimbal"

GIMBAL_DISABLE_ESTIMATOR: true

GimbalTracker:
  data_timeout_seconds: 3.0  # Faster timeout
  max_consecutive_failures: 5
```

---

## Hardware-Specific Tuning

### Raspberry Pi 4

```yaml
TRACKING_ALGORITHM: "KCF"

KCF_Tracker:
  confidence_threshold: 0.1
  failure_threshold: 10

SmartTracker:
  ENABLE_SMART_TRACKER: true
  SMART_TRACKER_USE_GPU: false
  SMART_TRACKER_CPU_MODEL_PATH: "models/yolo11n_ncnn_model"
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.4  # Higher threshold
  SMART_TRACKER_MAX_DETECTIONS: 10
```

### Jetson Nano

```yaml
TRACKING_ALGORITHM: "KCF"

SmartTracker:
  ENABLE_SMART_TRACKER: true
  SMART_TRACKER_USE_GPU: true
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo11n.pt"
```

### Desktop GPU (RTX 3060+)

```yaml
TRACKING_ALGORITHM: "CSRT"

CSRT_Tracker:
  performance_mode: "robust"

SmartTracker:
  ENABLE_SMART_TRACKER: true
  SMART_TRACKER_USE_GPU: true
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo11s.pt"  # Larger model
  TRACKER_TYPE: "botsort_reid"
```

---

## Confidence Tuning

### Too Many False Positives

Increase thresholds:

```yaml
CSRT_Tracker:
  confidence_threshold: 0.7

KCF_Tracker:
  confidence_threshold: 0.25

DLIB_Tracker:
  psr_confidence_threshold: 10.0

SmartTracker:
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.5
```

### Too Many Tracking Failures

Decrease thresholds:

```yaml
CSRT_Tracker:
  confidence_threshold: 0.3
  failure_threshold: 8

KCF_Tracker:
  confidence_threshold: 0.1
  failure_threshold: 12

DLIB_Tracker:
  psr_confidence_threshold: 5.0
  failure_threshold: 8
```

---

## Motion Validation Tuning

### Target Moving Too Fast for Validation

```yaml
KCF_Tracker:
  motion_consistency_threshold: 0.3  # Was 0.15
  max_scale_change_per_frame: 0.8   # Was 0.6

DLIB_Tracker:
  motion:
    velocity_limit: 50.0  # Was 25.0
    max_velocity_target_factor: 4.0  # Was 2.0
```

### Too Much Jitter

```yaml
DLIB_Tracker:
  motion:
    stabilization_alpha: 0.5  # More smoothing (was 0.3)
  confidence_smoothing_alpha: 0.8  # More smoothing (was 0.7)
```

---

## Appearance Model Tuning

### Frequent Template Drift

```yaml
CSRT_Tracker:
  appearance_update_min_confidence: 0.8  # Only update on high confidence
  appearance_learning_rate: 0.05  # Slower learning

DLIB_Tracker:
  appearance:
    freeze_on_low_confidence: true
    adaptive_learning_bounds: [0.02, 0.08]  # Lower range
```

### Too Slow to Adapt

```yaml
CSRT_Tracker:
  appearance_learning_rate: 0.15  # Faster learning

DLIB_Tracker:
  appearance:
    adaptive_learning_bounds: [0.1, 0.25]  # Higher range
    reference_update_interval: 15  # More frequent
```

---

## Diagnostic Tools

### Enable Performance Logging

```yaml
# Automatic logging every 30 frames
# Check logs for:
# - FPS measurements
# - Success rates
# - Confidence statistics
```

### Debug Visualization

```yaml
DLIB_Tracker:
  debug:
    enable_visual_feedback: true
    show_motion_vectors: true
```

---

## Related

- [Parameter Reference](parameter-reference.md) - All parameters
- [Schema System](schema-system.md) - Schema configuration
- [Tracker Reference](../02-reference/README.md) - Per-tracker details
