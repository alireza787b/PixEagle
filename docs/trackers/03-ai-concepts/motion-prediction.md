# Motion Prediction

PixEagle keeps prediction visible for diagnosis and bounded reacquisition, but
does not treat a prediction as a fresh target measurement. Followers accept
only measured, current tracker output.

## Classic Trackers

CSRT and dlib can use the shared `KalmanEstimator`. A newly selected target
seeds the estimator at the exact image position. Accepted measurements update
the filter with measured monotonic frame time; failed frames may advance it
within the configured horizon.

KCF owns a separate constant-velocity Kalman filter because its validation path
needs an internal proposal estimate. It uses the same image coordinate
convention and real elapsed seconds:

- positive x moves right
- positive y moves down
- velocity is pixels/second

Classic prediction is drawn as an operator hint and exposed as stale,
prediction-only telemetry. It cannot start or sustain follower commands.

## SmartTracker

SmartTracker uses `MotionPredictor` and `TrackingStateManager` for short
detection gaps. A predicted box can remain visible during the configured
frame-based tolerance, with decaying confidence. Reacquisition still requires a
current detector measurement and association checks.

Smart recovery timing is currently expressed in processed frames. Equivalent
behavior across changing detector cadence, dropped frames, and camera motion is
tracked as deferred work in `PXE-0131`; it must be benchmarked before stronger
aerial continuity claims are made.

## Configuration

```yaml
Estimator:
  USE_ESTIMATOR: true
  ESTIMATOR_MIN_DT_SECONDS: 0.001
  ESTIMATOR_MAX_DT_SECONDS: 0.25
  ESTIMATOR_MAX_PREDICTION_SECONDS: 1.0

SmartTracker:
  ENABLE_PREDICTION_BUFFER: true
  ID_LOSS_TOLERANCE_FRAMES: 5
```

The estimator limits contain scheduler stalls and measurement-free drift. They
do not turn a short-term visual tracker into an identity or long-occlusion
tracker.

## Related

- [Tracker output and freshness](../01-architecture/tracker-output.md)
- [SmartTracker](../02-reference/smart-tracker.md)
- [KCF + Kalman](../02-reference/kcf-kalman-tracker.md)
- [Appearance model](appearance-model.md)
