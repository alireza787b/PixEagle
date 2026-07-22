# KCF + Kalman Tracker

KCF is a lower-cost OpenCV correlation-tracker option with an internal
constant-velocity Kalman estimate. It is a short-term tracker, not an identity
re-identification system.

## Runtime Contract

Each frame follows one path:

1. OpenCV KCF proposes a bounding box.
2. PixEagle checks confidence, motion consistency, and scale change.
3. An accepted proposal updates the confirmed target and Kalman state.
4. A rejected proposal is immediately unusable for following.
5. The Kalman prediction remains diagnostic and may help bounded recovery; it
   never becomes a command-eligible measurement.

`failure_threshold` controls the confirmed-loss warning. It does not permit
commands from rejected or predicted geometry.

## Configuration

Use `configs/config.yaml` only for values that differ from the checked-in
defaults:

```yaml
KCF_Tracker:
  confidence_threshold: 0.15
  confidence_smoothing: 0.6
  failure_threshold: 7
  max_scale_change_per_frame: 0.6
  motion_consistency_threshold: 0.15
  appearance_learning_rate: 0.18

  kalman_process_noise: 0.1
  kalman_velocity_noise_factor: 0.5
  kalman_measurement_noise: 5.0
  kalman_initial_position_covariance: 10.0
  kalman_initial_velocity_covariance: 100.0

  use_velocity_during_occlusion: true
  occlusion_velocity_factor: 0.5
```

`use_velocity_during_occlusion` changes only diagnostic extrapolation. It does
not claim that KCF preserves target identity through an occlusion.

## Operating Limits

- KCF can drift when appearance changes, targets cross, the camera moves
  abruptly, or the target leaves the search region.
- The constant-velocity estimate cannot identify an object after it disappears.
- Pixel size, compression, camera motion, frame cadence, and hardware dominate
  measured continuity and latency.
- Detector-assisted recovery is owned by the application-level
  `Detector.AUTO_REDETECT`, `Tracking.REDETECTION_ATTEMPTS`, and
  `Tracking.TRACKING_FAILURE_TIMEOUT` settings.

Benchmark KCF against CSRT and SmartTracker on representative recordings. Log
false reacquisitions as well as successful frames; a tracker that stays active
on the wrong object is not robust.

## References

- [OpenCV tracking API](https://docs.opencv.org/4.x/d9/df8/group__tracking.html)
- Henriques et al., *High-Speed Tracking with Kernelized Correlation Filters*,
  TPAMI 2015
- [Tracker output and freshness](../01-architecture/tracker-output.md)
- [Tuning guide](../04-configuration/tuning-guide.md)
