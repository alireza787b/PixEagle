# Tracker Reference

> Detailed documentation for all tracker implementations

This section provides comprehensive reference documentation for each tracker type in PixEagle.

---

## Section Contents

| Document | Tracker | Relative Cost | Primary Contract |
|----------|---------|---------------|------------------|
| [CSRT](csrt-tracker.md) | OpenCV CSRT | Medium | Scale-adaptive short-term tracking |
| [KCF + Kalman](kcf-kalman-tracker.md) | KCF with Kalman | Lower | Short-term tracking with motion estimates |
| [dlib Correlation](dlib-tracker.md) | dlib correlation | Lower | Optional correlation backend with PSR |
| [Gimbal Tracker](gimbal-tracker.md) | External angles | External | Provider-normalized gimbal observations |
| [SmartTracker](smart-tracker.md) | Detector + association | Model-dependent | Detection, identity association, classification |

---

## Tracker Comparison

### Performance Characteristics

PixEagle does not publish universal FPS, accuracy, or occlusion ratings. Those
values depend on target pixel size, camera motion, compression, model, runtime,
and hardware. Benchmark candidates on representative recordings and report the
exact configuration and computer.

| Tracker | Acceleration | Recovery Boundary |
|---------|--------------|-------------------|
| CSRT | CPU | App-owned bounded detector recovery after a rejected measurement |
| KCF + Kalman | CPU | Prediction can guide recovery; prediction is not command-eligible measurement |
| dlib | CPU | App-owned bounded detector recovery when configured |
| Gimbal | Provider-dependent | Provider freshness and validity contract |
| SmartTracker | CPU/GPU/model-dependent | Detector association with tentative/confirmed lifecycle |

### Feature Matrix

| Feature | CSRT | KCF | dlib | Gimbal | Smart |
|---------|------|-----|------|--------|-------|
| Multi-target | - | - | - | - | Yes |
| Object classification | - | - | - | - | Yes |
| Internal Kalman | - | Yes | - | - | - |
| PSR confidence | - | - | Yes | - | - |
| External data source | - | - | - | Yes | - |
| Scale adaptation | Yes | Limited | Yes | N/A | Model-dependent |
| Identity recovery guarantee | No | No | No | Provider-dependent | No; benchmark association policy |

---

## Selection Guide

### Choose CSRT When:
- A scale-adaptive short-term correlation tracker is a suitable baseline
- The target retains enough texture and pixels between frames
- The target computer can meet the measured end-to-end cadence
- Detector-assisted recovery is configured for bounded reacquisition

### Choose KCF + Kalman When:
- Lower correlation-tracker cost is more important than CSRT's feature set
- Motion estimates are useful for overlays and bounded recovery search
- Scenario tests show acceptable drift and identity continuity

### Choose dlib When:
- The optional dlib runtime is installed and verified
- PSR confidence is useful for the target scenario
- Measured latency and continuity outperform the other local candidates

### Choose Gimbal Tracker When:
- External gimbal hardware provides angles
- No image processing overhead desired
- Direct gimbal control integration
- Camera gimbal systems

### Choose SmartTracker When:
- Detection, classification, or identity association is required
- A trusted local model has been registered and verified
- Tentative/predicted states are kept outside the follower command boundary

---

## Configuration Quick Reference

### Classic Trackers (local override)

```yaml
Tracking:
  DEFAULT_TRACKING_ALGORITHM: "CSRT"  # CSRT, KCF, dlib, Gimbal

Estimator:
  USE_ESTIMATOR: true
  ESTIMATOR_TYPE: "Kalman"
```

### SmartTracker (config.yaml)

```yaml
SmartTracker:
  SMART_TRACKER_ENABLED: true
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26n.pt"
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.5
```

### Gimbal Tracker (config.yaml)

```yaml
Tracking:
  DEFAULT_TRACKING_ALGORITHM: "Gimbal"
GimbalTracker:
  UDP_HOST: "127.0.0.1"
  UDP_PORT: 9003
  LISTEN_PORT: 9004
```

---

## TrackerOutput by Type

Each tracker produces output in specific schemas:

```python
# CSRT, KCF, dlib - POSITION_2D
TrackerOutput(
    data_type=TrackerDataType.POSITION_2D,
    position_2d=(0.1, -0.2),  # Normalized
    confidence=0.85,
    bbox=(100, 200, 50, 60)
)

# Gimbal - GIMBAL_ANGLES
TrackerOutput(
    data_type=TrackerDataType.GIMBAL_ANGLES,
    angular=(45.0, -10.0, 0.0),  # yaw, pitch, roll
    confidence=1.0
)

# SmartTracker - MULTI_TARGET
TrackerOutput(
    data_type=TrackerDataType.MULTI_TARGET,
    targets=[
        {"target_id": 1, "class_name": "person", "confidence": 0.92},
        {"target_id": 2, "class_name": "car", "confidence": 0.88}
    ],
    position_2d=(0.1, -0.2),  # Selected target
    target_id=1
)
```

---

## Related Sections

- [Architecture](../01-architecture/README.md) - System design
- [Configuration](../04-configuration/README.md) - Parameter tuning
- [Development](../05-development/README.md) - Custom tracker creation
