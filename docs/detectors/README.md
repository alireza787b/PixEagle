# Detectors

PixEagle currently provides one classic-tracker recovery detector:
`classes.detectors.template_matching_detector.TemplateMatchingDetector`.
YOLO/Ultralytics target selection belongs to SmartTracker and is not exposed as
a classic `DETECTION_ALGORITHM` value.

## Runtime Contract

The detector factory accepts the stable name `TemplateMatching`. A classic
tracker calls `initialize_target(frame, bbox)` for every operator selection and
retarget. That operation replaces the complete identity baseline:

- initial image template;
- initial color-histogram features;
- adaptive appearance features;
- latest target geometry and match score.

Normal high-confidence tracker updates may adapt appearance features, but they
do not silently replace the original image template. This prevents a second
operator-selected target from inheriting the previous target's redetection
template.

## Recovery Flow

1. A classic tracker produces an unusable measured update.
2. Following fails closed immediately; estimator-only output is diagnostic.
3. `AppController` opens the bounded recovery window configured by
   `Tracking.TRACKING_FAILURE_TIMEOUT` and `Tracking.REDETECTION_ATTEMPTS`.
4. Template matching searches the estimator-centered region when an estimate is
   available, otherwise the frame.
5. The best multi-scale result must pass `TEMPLATE_MATCHING_THRESHOLD` and the
   independent `APPEARANCE_CONFIDENCE_THRESHOLD` check.
6. A passing candidate reinitializes the tracker; only a fresh measured tracker
   output can become usable for following.

The checked-in default uses `TM_CCOEFF_NORMED`. Normalized OpenCV methods are
recommended because their threshold semantics are portable. Raw correlation or
square-difference methods interpret the configured threshold in their native
score units.

## Configuration

```yaml
Detector:
  USE_DETECTOR: true
  DETECTION_ALGORITHM: TemplateMatching
  TEMPLATE_MATCHING_METHOD: TM_CCOEFF_NORMED
  TEMPLATE_MATCHING_SCALES: [0.5, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.5, 2.0]
  TEMPLATE_MATCHING_THRESHOLD: 0.7
  APPEARANCE_CONFIDENCE_THRESHOLD: 0.7
  AUTO_REDETECT: true
```

`configs/config_default.yaml` is the checked-in authority. Use
`configs/config.yaml` only for local overrides and edit settings through the
schema-driven dashboard when possible.

## Extension

New classic recovery detectors subclass `BaseDetector`, implement the abstract
redetection and visualization methods, and register one stable name in
`classes.detectors.detector_factory.create_detector`. They should preserve the
`initialize_target` replacement semantics and return bounded, testable scores.

See [tracker integration](../trackers/06-integration/README.md) and
[tracker testing](../trackers/05-development/testing-trackers.md).
