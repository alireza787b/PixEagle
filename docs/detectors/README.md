# Detectors

> **Note**: This documentation is a placeholder. Comprehensive documentation will be added after code audit is complete.

## Overview

Detectors in PixEagle provide object detection capabilities for initial target acquisition before tracking begins.

## Components

| Component | File | Status |
|-----------|------|--------|
| BaseDetector | `src/classes/detectors/base_detector.py` | Pending audit |
| DetectorFactory | `src/classes/detectors/detector_factory.py` | Pending audit |
| TemplateMatchingDetector | `src/classes/detectors/template_matching_detector.py` | Pending audit |
| FeatureMatchingDetector | `src/classes/feature_matching_detector.py` | Pending audit |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    DetectorFactory                       │
│                  (Factory Pattern)                       │
└─────────────────────────┬───────────────────────────────┘
                          │ creates
                          ▼
┌─────────────────────────────────────────────────────────┐
│                     BaseDetector                         │
│                   (Abstract Base)                        │
├─────────────────────────────────────────────────────────┤
│  + detect(frame) -> List[Detection]                     │
│  + initialize(config)                                    │
└─────────────────────────┬───────────────────────────────┘
                          │ extends
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ TemplateMatching│ │FeatureMatching  │ │  (Future)       │
│    Detector     │ │   Detector      │ │  YOLO Detector  │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Detection Types

### Template Matching
Uses OpenCV template matching to find objects similar to a reference image.

### Feature Matching
Uses feature descriptors (SIFT, ORB, etc.) for scale/rotation invariant detection.

## Usage

```python
from classes.detectors.detector_factory import DetectorFactory

# Create detector
detector = DetectorFactory.create('template_matching', config)

# Detect objects in frame
detections = detector.detect(frame)

for detection in detections:
    print(f"Found at {detection.bbox} with confidence {detection.confidence}")
```

## Configuration

```yaml
# config_default.yaml
detection:
  method: "template_matching"
  template_path: "templates/target.png"
  threshold: 0.8
  max_detections: 5
```

## TODO

- [ ] Complete code audit
- [ ] Add comprehensive documentation for each detector
- [ ] Add unit tests (~50 tests)
- [ ] Add integration tests
- [ ] Document best practices and tuning

## Related

- [Trackers Documentation](../trackers/README.md) - Trackers use detector output
- [Video Documentation](../video/README.md) - Frame source for detection
