# dlib Correlation Tracker

The optional dlib backend provides a correlation tracker with Peak-to-Sidelobe
Ratio (PSR) confidence. Install it explicitly with
`bash scripts/setup/install-dlib.sh` and benchmark it on the target computer.

## Runtime Contract

The three modes change validation cost:

| Mode | Candidate checks |
|------|------------------|
| `fast` | PSR gate without EMA or estimator/scale validation |
| `balanced` | PSR gate with EMA smoothing |
| `robust` | Balanced checks plus estimator-motion and scale validation |

An accepted measurement updates the published target, appearance state, and
estimator. A rejected measurement is immediately unusable for following.
`failure_threshold` controls only when repeated rejection is reported as a
confirmed loss.

## Configuration

```yaml
DLIB_Tracker:
  performance_mode: "robust"
  psr_confidence_threshold: 7.0
  psr_high_confidence: 20.0
  psr_low_confidence: 5.0
  failure_threshold: 5
  confidence_smoothing_alpha: 0.7
  validation_start_frame: 10
  max_scale_change_per_frame: 0.5
  max_motion_per_frame: 0.6
  appearance_learning_rate: 0.08

  appearance:
    use_adaptive_learning: true
    adaptive_learning_bounds: [0.05, 0.15]
    freeze_on_low_confidence: true

  motion:
    velocity_limit: 25.0
    velocity_normalize_by_size: true
    max_velocity_target_factor: 2.0
    stabilization_alpha: 0.3
```

When adaptive appearance learning is enabled, PSR selects a learning rate
within the configured bounds. Low PSR can freeze appearance updates to reduce
template contamination. These controls do not provide re-identification.

## Operating Limits

- dlib correlation tracking does not guarantee identity through occlusion,
  target crossings, abrupt viewpoint changes, or out-of-frame motion.
- PSR is tracker evidence, not a universal probability or readiness score.
- FPS and continuity depend on frame size, target size, host, and workload;
  PixEagle intentionally publishes no universal rating.
- Detector recovery is owned by application-level `Tracking` and `Detector`
  policy, not hidden dlib-specific switches.

## References

- [dlib correlation tracker example](http://dlib.net/correlation_tracker.py.html)
- Danelljan et al., *Accurate Scale Estimation for Robust Visual Tracking*,
  BMVC 2014
- Bolme et al., *Visual Object Tracking using Adaptive Correlation Filters*,
  CVPR 2010
- [Tracker output and freshness](../01-architecture/tracker-output.md)
- [Tuning guide](../04-configuration/tuning-guide.md)
