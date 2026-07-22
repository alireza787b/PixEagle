# Tracker Tuning Guide

Tune against representative recordings from the intended camera and viewpoint.
A setting is not validated because it keeps a box visible: record identity
switches, false reacquisitions, rejected measurements, processing latency, and
target pixel size as well.

## Baseline Procedure

1. Keep checked-in defaults and capture a repeatable clip.
2. Record the exact commit, config, input dimensions, host, and achieved frame
   cadence.
3. Change one parameter group at a time.
4. Compare continuity and false-lock behavior, not only average FPS.
5. Repeat loss, crossing, camera-motion, edge-of-frame, scale-change, and
   temporary-occlusion cases.
6. Keep prediction and tentative detections outside the follower command path.

For aerial footage, include small targets, background clutter, compression,
camera translation/rotation, abrupt target direction changes, and at least one
full disappearance. Correlation trackers cannot recover identity by prediction
alone.

## Choose a Baseline

### CSRT

Use CSRT as the scale-adaptive classic baseline when the target retains enough
texture and pixels:

```yaml
Tracking:
  DEFAULT_TRACKING_ALGORITHM: "CSRT"

CSRT_Tracker:
  performance_mode: "robust"
```

`balanced` removes motion/scale validation cost. `legacy` also removes EMA.
Neither mode is automatically more accurate.

### KCF + Kalman

Use KCF as a lower-cost comparison candidate:

```yaml
Tracking:
  DEFAULT_TRACKING_ALGORITHM: "KCF"
```

Its Kalman state is diagnostic. It does not authorize follower commands during
loss and does not identify a returning object.

### dlib

Use dlib only after the optional runtime passes its capability check:

```yaml
Tracking:
  DEFAULT_TRACKING_ALGORITHM: "dlib"

DLIB_Tracker:
  performance_mode: "robust"
```

Benchmark all three dlib modes on the target host; do not infer FPS from the
mode name.

### SmartTracker

Use SmartTracker when detection, classification, or identity association is
required. Register and digest-pin a local model first. The readiness check
proves deterministic inference, not association quality, aerial performance,
or flight readiness.

## Diagnose Rejection Before Tuning

Use tracker telemetry and logs to identify the failing gate:

| Symptom | Inspect first | Typical next experiment |
|---------|---------------|-------------------------|
| OpenCV tracker reports no candidate | target pixels, blur, frame jumps, crop | larger initial ROI or detector-assisted recovery |
| `low_confidence` | motion and appearance confidence | compare a small threshold change on the same clip |
| `appearance_mismatch` | lighting, compression, background in ROI | improve ROI composition; reduce appearance gate only with false-lock evidence |
| `motion_invalid` | frame cadence and camera/target displacement | raise the active motion gate gradually |
| `scale_invalid` | zoom and target-size change | raise scale gate gradually |
| `reacquisition_pending` | consecutive candidate stability | inspect candidate trajectory; do not remove consensus to hide drift |

`failure_threshold` changes warning timing only. Every rejected measurement is
immediately stale and unusable for following.

## Parameter Groups

### CSRT Validation

```yaml
CSRT_Tracker:
  confidence_threshold: 0.45
  max_motion_per_frame: 0.6
  max_scale_change_per_frame: 0.5
  validation_consensus_frames: 3
```

Reduce a threshold only after measuring false locks. For small aerial targets,
appearance scores can become noisy because the ROI contains few target pixels;
test ROI size and detector quality before globally weakening validation.

### KCF Validation and Estimate

```yaml
KCF_Tracker:
  confidence_threshold: 0.15
  motion_consistency_threshold: 0.15
  max_scale_change_per_frame: 0.6
  kalman_process_noise: 0.1
  kalman_measurement_noise: 5.0
```

Kalman settings change prediction and candidate consistency. They do not make a
prediction command eligible.

### dlib PSR and Motion

```yaml
DLIB_Tracker:
  psr_confidence_threshold: 7.0
  max_motion_per_frame: 0.6
  max_scale_change_per_frame: 0.5
  motion:
    velocity_normalize_by_size: true
    max_velocity_target_factor: 2.0
    stabilization_alpha: 0.3
```

Higher `stabilization_alpha` follows new geometry faster; lower values smooth
more. Excessive smoothing can lag a fast or abruptly turning target.

### Appearance Updates

```yaml
CSRT_Tracker:
  appearance_update_min_confidence: 0.55
  appearance_learning_rate: 0.10

DLIB_Tracker:
  appearance:
    use_adaptive_learning: true
    adaptive_learning_bounds: [0.05, 0.15]
    freeze_on_low_confidence: true
```

Fast updates adapt sooner but can contaminate the template. Conservative
updates reduce drift but may lag real appearance change. Validate both target
retention and wrong-object lock.

## Recovery Policy

Classic tracker recovery has one application-level owner:

```yaml
Tracking:
  TRACKING_FAILURE_TIMEOUT: 5.0
  REDETECTION_ATTEMPTS: 5

Detector:
  AUTO_REDETECT: true
```

Within that bounded window, the estimator can guide diagnostics and the
detector can propose reinitialization candidates. Following remains fail-closed
until a fresh measured tracker output passes its contract. Increasing timeout
or attempts can improve opportunity for recovery but also increases compute
and false-match exposure.

## Hardware Acceptance

Run the same clip and config on each target computer. Report measured decode,
tracking, and end-to-end frame cadence separately. Raspberry Pi, Jetson, and
desktop results are not interchangeable, and adding GStreamer changes capture
and decode behavior rather than tracker quality by itself.

## Related

- [Parameter reference](parameter-reference.md)
- [CSRT](../02-reference/csrt-tracker.md)
- [KCF + Kalman](../02-reference/kcf-kalman-tracker.md)
- [dlib](../02-reference/dlib-tracker.md)
- [SmartTracker](../02-reference/smart-tracker.md)
- [Detection model catalog](../../MODEL_CATALOG.md)
