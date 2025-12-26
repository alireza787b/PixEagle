# dlib Correlation Tracker

> Ultra-fast PSR-based correlation filter (25-50 FPS)

The dlib tracker uses the dlib library's correlation filter with Peak-to-Sidelobe Ratio (PSR) for confidence scoring. Based on the DSST algorithm. Located at `src/classes/trackers/dlib_tracker.py`.

---

## Overview

**Best for:**
- Maximum speed requirements (25-50 FPS)
- Resource-constrained systems
- Drone-to-drone tracking
- Speed-critical applications

**Strengths:**
- Ultra-fast tracking
- PSR-based confidence (research-validated)
- Low computational overhead
- Scale adaptation
- Adaptive PSR thresholding

**Limitations:**
- Limited rotation invariance
- Simpler appearance model than CSRT

---

## Performance Modes

| Mode | FPS | Features | Use Case |
|------|-----|----------|----------|
| `fast` | 25-30 | Minimal overhead | Maximum speed |
| `balanced` | 18-25 | PSR monitoring with grace period | Default |
| `robust` | 12-18 | Full validation | Maximum stability |

---

## PSR Confidence

Peak-to-Sidelobe Ratio (PSR) measures tracking quality:

```python
# PSR ranges (Bolme et al., 2010)
# PSR < 5:  Poor tracking (occlusion or loss)
# PSR 5-7:  Marginal tracking
# PSR 7-20: Good tracking
# PSR > 20: Excellent tracking

def _psr_to_confidence(self, psr: float) -> float:
    """Convert PSR to normalized confidence [0.0, 1.0]."""
    if psr < self.psr_low_confidence:
        # Poor tracking
        return psr / (self.psr_low_confidence * 2.0)
    elif psr < self.psr_confidence_threshold:
        # Marginal tracking
        return 0.25 + (psr - low) / (threshold - low) * 0.25
    elif psr < self.psr_high_confidence:
        # Good tracking
        return 0.5 + (psr - threshold) / (high - threshold) * 0.4
    else:
        # Excellent tracking
        return 0.9 + min(0.1, (psr - high) / 20.0)
```

---

## Enhanced Features

### Adaptive PSR Threshold

Dynamically adjusts threshold based on tracking history:

```python
def _update_adaptive_psr_threshold(self, current_psr: float):
    if len(self.psr_history) >= 3:
        recent_psr_avg = np.mean(list(self.psr_history)[-5:])
        target_threshold = recent_psr_avg * 0.7  # 70% of recent average

        # EMA smoothing
        self.adaptive_psr_threshold = (
            (1 - adapt_rate) * self.adaptive_psr_threshold +
            adapt_rate * target_threshold
        )
```

### Adaptive Learning Rate

Learning rate varies with confidence:

```python
def _get_adaptive_learning_rate(self, psr: float) -> float:
    # Low PSR → min learning rate (conservative)
    # High PSR → max learning rate (fast adaptation)
    if psr < self.psr_low_confidence:
        return min_lr  # 0.05
    elif psr > self.psr_high_confidence:
        return max_lr  # 0.15
    else:
        # Linear interpolation
        return min_lr + normalized * (max_lr - min_lr)
```

### Template Freeze

Prevents template corruption during low-confidence periods:

```python
def _should_freeze_template(self, psr: float) -> bool:
    if not self.freeze_on_low_confidence:
        return False
    return psr < self.psr_low_confidence
```

---

## Configuration

```yaml
# configs/config.yaml
DLIB_Tracker:
  performance_mode: "balanced"

  # PSR thresholds
  psr_confidence_threshold: 7.0
  psr_high_confidence: 20.0
  psr_low_confidence: 5.0

  # Validation
  failure_threshold: 5
  validation_start_frame: 10
  confidence_smoothing_alpha: 0.7
  max_scale_change_per_frame: 0.5
  max_motion_per_frame: 0.6

  # Adaptive features
  adaptive:
    enable: true
    psr_dynamic_scaling: true
    adapt_rate: 0.15
    psr_margin: 1.5

  # Appearance model
  appearance:
    use_adaptive_learning: true
    adaptive_learning_bounds: [0.05, 0.15]
    freeze_on_low_confidence: true
    reference_update_interval: 30

  # Motion
  motion:
    velocity_limit: 25.0
    stabilization_alpha: 0.3
    velocity_normalize_by_size: true
    max_velocity_target_factor: 2.0

  # Validation
  validation:
    reinit_on_loss: true
    cooldown_after_reinit: 5
```

---

## TrackerOutput

```python
TrackerOutput(
    data_type=TrackerDataType.POSITION_2D,
    position_2d=(0.1, -0.2),
    confidence=0.85,
    quality_metrics={
        'motion_consistency': 0.92,
        'psr_value': 15.3,
        'failure_count': 0,
        'success_rate': 0.96
    },
    raw_data={
        'performance_mode': 'balanced',
        'frame_count': 200,
        'avg_fps': 35.2,
        'psr_history': [14.2, 15.1, 15.3, ...]
    },
    metadata={
        'tracker_algorithm': 'dlib_correlation_filter',
        'performance_mode': 'balanced'
    }
)
```

---

## Usage

### Basic Usage

```python
from classes.trackers.tracker_factory import create_tracker

tracker = create_tracker("dlib", video_handler, detector, app_controller)

tracker.start_tracking(frame, (100, 200, 50, 80))

while True:
    success, bbox = tracker.update(frame)

    if success:
        output = tracker.get_output()
        psr = output.quality_metrics['psr_value']
        print(f"PSR: {psr:.1f}, Confidence: {output.confidence:.2f}")
```

### Accessing PSR History

```python
# Get recent PSR values for analysis
psr_history = list(tracker.psr_history)
avg_psr = np.mean(psr_history[-10:])
```

---

## Performance Tuning

### For Maximum Speed

```yaml
DLIB_Tracker:
  performance_mode: "fast"
  adaptive:
    enable: false
  appearance:
    use_adaptive_learning: false
  motion:
    stabilization_alpha: 0.0  # No smoothing
```

### For Robust Tracking

```yaml
DLIB_Tracker:
  performance_mode: "robust"
  psr_confidence_threshold: 8.0
  failure_threshold: 7
  adaptive:
    enable: true
  appearance:
    freeze_on_low_confidence: true
```

---

## Capabilities

```python
tracker.get_capabilities()
# {
#     'tracker_algorithm': 'dlib_correlation_filter',
#     'supports_rotation': False,
#     'supports_scale_change': True,
#     'supports_occlusion': False,
#     'accuracy_rating': 'high',
#     'speed_rating': 'very_fast',
#     'correlation_filter': True,
#     'psr_confidence': True,
#     'performance_mode': 'balanced'
# }
```

---

## References

- Danelljan et al., "Accurate Scale Estimation for Robust Visual Tracking," BMVC 2014 (DSST)
- Bolme et al., "Visual Object Tracking using Adaptive Correlation Filters," CVPR 2010
- dlib Library: http://dlib.net/

---

## Related

- [CSRT Tracker](csrt-tracker.md) - Better occlusion handling
- [KCF + Kalman](kcf-kalman-tracker.md) - Built-in velocity estimation
- [Configuration](../04-configuration/README.md) - Parameter tuning
