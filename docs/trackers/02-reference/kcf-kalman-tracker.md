# KCF + Kalman Tracker

> Production-ready correlation filter with internal Kalman state estimation (30-50 FPS CPU)

The KCF+Kalman tracker combines OpenCV's Kernelized Correlation Filter with an internal Kalman filter for robust tracking with velocity estimation. Located at `src/classes/trackers/kcf_kalman_tracker.py`.

---

## Overview

**Best for:**
- Embedded systems (Raspberry Pi, Jetson)
- Real-time CPU tracking requirements
- Fast-moving targets
- Applications needing velocity estimates

**Strengths:**
- Very fast (30-50 FPS on CPU)
- Internal Kalman filter for smooth state estimation
- Multi-frame failure validation
- Graceful degradation during occlusions

**Limitations:**
- Limited rotation invariance
- Requires consistent appearance

---

## Architecture

```
Frame Input
    ↓
KCF Tracker (OpenCV) → Raw Bbox
    ↓
Multi-Frame Validator → Check N consecutive frames
    ↓
Motion Consistency Check → Validate against Kalman prediction
    ↓
Confidence Calculation (EMA Smoothed)
    ↓
    ├─→ High Confidence (>0.15): Accept KCF, Update Kalman + Appearance
    └─→ Low Confidence (≤0.15): Use Kalman prediction, Buffer failure
    ↓
Return (success, bbox)
```

---

## Key Features

### Internal Kalman Filter

State vector: `[x, y, vx, vy]` (position + velocity)

```python
# Kalman filter initialization
self.kf = KalmanFilter(dim_x=4, dim_z=2)

# State transition (constant velocity model)
self.kf.F = np.array([
    [1, 0, dt, 0],
    [0, 1, 0, dt],
    [0, 0, 1, 0],
    [0, 0, 0, 1]
])

# Measurement function (observe position only)
self.kf.H = np.array([
    [1, 0, 0, 0],
    [0, 1, 0, 0]
])
```

### Multi-Frame Validation

Requires N consecutive failures before declaring lost:

```python
if self.failure_count >= self.failure_threshold:
    logger.warning(f"Tracking lost after {self.failure_count} failures")
    return False, self.bbox
```

### Velocity Extrapolation During Occlusion

```python
if use_velocity and self.kf is not None:
    kf_vx, kf_vy = float(self.kf.x[2]), float(self.kf.x[3])
    # Conservative extrapolation: 50% of velocity
    predicted_x = kf_x + kf_vx * velocity_factor
    predicted_y = kf_y + kf_vy * velocity_factor
```

---

## Configuration

```yaml
# configs/config.yaml
KCF_Tracker:
  # Confidence thresholds
  confidence_threshold: 0.15
  confidence_smoothing: 0.6
  failure_threshold: 7

  # Motion validation
  max_scale_change_per_frame: 0.6
  motion_consistency_threshold: 0.15

  # Kalman filter
  kalman_process_noise: 0.1
  kalman_velocity_noise_factor: 0.5
  kalman_measurement_noise: 5.0
  kalman_initial_position_covariance: 10.0
  kalman_initial_velocity_covariance: 100.0

  # Occlusion handling
  use_velocity_during_occlusion: true
  occlusion_velocity_factor: 0.5
```

---

## TrackerOutput

KCF produces velocity-aware output:

```python
TrackerOutput(
    data_type=TrackerDataType.VELOCITY_AWARE,
    position_2d=(0.1, -0.2),
    velocity=(12.5, -3.2),  # From internal Kalman
    confidence=0.85,
    quality_metrics={
        'motion_consistency': 0.95,
        'bbox_stability': 0.88,
        'failure_count': 0,
        'success_rate': 0.98
    },
    raw_data={
        'internal_kalman_enabled': True,
        'velocity_magnitude': 12.9,
        'failure_threshold': 7,
        'avg_fps': 42.3
    },
    metadata={
        'tracker_algorithm': 'KCF+Kalman',
        'has_internal_kalman': True,
        'supports_velocity': True,
        'robustness_features': [
            'multi_frame_validation',
            'confidence_ema_smoothing',
            'adaptive_appearance_learning',
            'motion_consistency_checks'
        ]
    }
)
```

---

## Usage

### Basic Usage

```python
from classes.trackers.tracker_factory import create_tracker

tracker = create_tracker("KCF", video_handler, detector, app_controller)

tracker.start_tracking(frame, (100, 200, 50, 80))

while True:
    success, bbox = tracker.update(frame)

    if success:
        output = tracker.get_output()

        # Access velocity from internal Kalman
        if output.velocity:
            vx, vy = output.velocity
            print(f"Velocity: ({vx:.1f}, {vy:.1f}) px/s")
```

### Getting Kalman State

```python
# Direct Kalman state access
position = tracker.get_estimated_position()
# Returns (x, y) from Kalman filter
```

---

## Performance Comparison

| Metric | KCF+Kalman | CSRT | dlib |
|--------|------------|------|------|
| FPS (CPU) | 30-50 | 15-25 | 25-50 |
| Velocity Estimation | Built-in | Optional | Optional |
| Rotation Handling | Limited | Good | Limited |
| Occlusion Handling | Good | Excellent | Good |

---

## Robustness Features

1. **Multi-frame validation** - Prevents single-frame false negatives
2. **EMA confidence smoothing** - Reduces jitter
3. **Adaptive appearance learning** - Template updates with drift protection
4. **Motion consistency checks** - Validates against Kalman prediction
5. **Bbox scale validation** - Rejects unrealistic size changes
6. **Graceful degradation** - Kalman takes over during occlusions

---

## Capabilities

```python
tracker.get_capabilities()
# {
#     'tracker_algorithm': 'KCF+Kalman',
#     'supports_rotation': False,
#     'supports_scale_change': True,
#     'supports_occlusion': True,
#     'accuracy_rating': 'high',
#     'speed_rating': 'very_fast',
#     'robustness_rating': 'high',
#     'opencv_tracker': True,
#     'internal_kalman': True,
#     'real_time_cpu': True,
#     'production_ready': True,
#     'recommended_for': ['embedded_systems', 'real_time_tracking']
# }
```

---

## References

- Henriques et al., "High-Speed Tracking with Kernelized Correlation Filters," TPAMI 2015
- filterpy Kalman Filter: https://github.com/rlabbe/filterpy

---

## Related

- [CSRT Tracker](csrt-tracker.md) - Better rotation handling
- [dlib Tracker](dlib-tracker.md) - PSR-based confidence
- [Configuration](../04-configuration/README.md) - Parameter tuning
