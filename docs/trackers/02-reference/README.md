# Tracker Reference

> Detailed documentation for all tracker implementations

This section provides comprehensive reference documentation for each tracker type in PixEagle.

---

## Section Contents

| Document | Tracker | Speed | Best For |
|----------|---------|-------|----------|
| [CSRT](csrt-tracker.md) | OpenCV CSRT | Medium | Rotation, occlusion handling |
| [KCF + Kalman](kcf-kalman-tracker.md) | KCF with Kalman | Very Fast | Embedded systems, real-time |
| [dlib Correlation](dlib-tracker.md) | dlib DSST | Ultra Fast | Speed-critical, drone tracking |
| [Gimbal Tracker](gimbal-tracker.md) | External angles | Very Fast | Gimbal integration |
| [SmartTracker](smart-tracker.md) | YOLO + ByteTrack | Fast (GPU) | Multi-target, classification |

---

## Tracker Comparison

### Performance Characteristics

| Tracker | FPS (CPU) | Accuracy | GPU Benefit | Occlusion Handling |
|---------|-----------|----------|-------------|-------------------|
| CSRT | 15-25 | High | Minimal | Excellent |
| KCF + Kalman | 30-50 | High | None | Good |
| dlib | 25-50 | High | None | Good |
| Gimbal | N/A | Very High | N/A | N/A (external) |
| SmartTracker | 15-30 | Very High | Significant | Excellent |

### Feature Matrix

| Feature | CSRT | KCF | dlib | Gimbal | Smart |
|---------|------|-----|------|--------|-------|
| Multi-target | - | - | - | - | Yes |
| Object classification | - | - | - | - | Yes |
| Internal Kalman | - | Yes | - | - | - |
| PSR confidence | - | - | Yes | - | - |
| External data source | - | - | - | Yes | - |
| Scale adaptation | Yes | Yes | Yes | N/A | Yes |
| Rotation invariant | Yes | - | - | N/A | Yes |

---

## Selection Guide

### Choose CSRT When:
- Tracking objects that rotate frequently (drone circling target)
- Perspective changes are common
- Occlusion handling is important
- CPU performance is adequate (15-25 FPS acceptable)

### Choose KCF + Kalman When:
- Running on embedded systems (Raspberry Pi, Jetson)
- Real-time CPU performance is critical
- Smooth velocity estimates are needed
- Fast-moving targets require prediction

### Choose dlib When:
- Maximum speed is required (25-50 FPS)
- Resource-constrained systems
- Drone-to-drone tracking scenarios
- PSR-based confidence is preferred

### Choose Gimbal Tracker When:
- External gimbal hardware provides angles
- No image processing overhead desired
- Direct gimbal control integration
- Camera gimbal systems

### Choose SmartTracker When:
- Multiple targets need simultaneous tracking
- Object class identification is needed (person, vehicle, etc.)
- GPU acceleration is available
- Initial target selection should be automatic

---

## Configuration Quick Reference

### Classic Trackers (config.yaml)

```yaml
TRACKING_ALGORITHM: "CSRT"  # CSRT, KCF, dlib, Gimbal

# Estimator settings (affects confidence)
USE_ESTIMATOR: true
ESTIMATOR_TYPE: "Kalman"
```

### SmartTracker (config.yaml)

```yaml
ENABLE_SMART_TRACKER: true
YOLO_MODEL: "yolov8n.pt"
YOLO_CONFIDENCE_THRESHOLD: 0.5
```

### Gimbal Tracker (config.yaml)

```yaml
TRACKING_ALGORITHM: "Gimbal"
GIMBAL_UDP_HOST: "0.0.0.0"
GIMBAL_UDP_PORT: 14555
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
