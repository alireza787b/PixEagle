# CSRT Tracker

PixEagle wraps OpenCV's Channel and Spatial Reliability Tracker (CSRT) as a
classic, short-term visual tracker. The implementation is in
`src/classes/trackers/csrt_tracker.py`.

CSRT can adapt its correlation filter and target scale. It does not guarantee
identity through long occlusion, similar-object crossings, abrupt camera
motion, low-resolution targets, or severe appearance change. Use recorded
scene benchmarks on the target computer instead of assuming a fixed frame rate
or success rate.

## Runtime Contract

Each OpenCV update is treated as a candidate measurement:

1. Geometry must be finite and have positive width and height.
2. Confidence and, when available, appearance are checked.
3. Robust mode also checks estimator-relative motion and frame-to-frame scale.
4. After a rejected measurement, consecutive valid candidates must regain
   consensus before a new measurement is published.

The candidate bounding box advances privately while consensus is pending. This
lets a moving target build continuity without comparing every candidate to a
frozen old position. It does not update the public bounding box, measurement
timestamp, estimator, or appearance model. The first rejected frame is stale
and cannot authorize follower commands.

The application controller owns bounded detector-assisted recovery. Estimator
predictions may guide its search and remain available to overlays, but are not
command-eligible target measurements. Recovery stops at the configured timeout
or attempt limit; CSRT does not run a second private detector loop.

## Modes

| Mode | Validation |
| --- | --- |
| `legacy` | Confidence and appearance checks; no EMA, estimator-motion, or scale gate |
| `balanced` | Legacy checks plus EMA confidence smoothing |
| `robust` | Balanced checks plus estimator-motion and scale gates |

`robust` is the checked-in default. A mode name is not evidence of suitability
for a flight environment. Measure latency, continuity, false reacquisition, and
identity switches with representative camera motion, target size, occlusion,
and distractors.

## Configuration

`configs/config_default.yaml` and the generated schema are the authority. Put
only local overrides in `configs/config.yaml`.

```yaml
CSRT_Tracker:
  performance_mode: robust
  confidence_threshold: 0.45
  failure_threshold: 5
  confidence_smoothing: 0.7
  validation_start_frame: 10
  max_scale_change_per_frame: 0.5
  max_motion_per_frame: 0.6
  appearance_learning_rate: 0.10

  use_color_names: true
  use_hog: true
  csrt_learning_rate: 0.02
  number_of_scales: 33
  scale_step: 1.02
  use_segmentation: true

  appearance_update_min_confidence: 0.55
  enable_multiframe_validation: true
  validation_consensus_frames: 3
```

`failure_threshold` controls the one-time confirmed-loss warning. It does not
make rejected frames usable. Detector recovery is bounded separately by
`Tracking.TRACKING_FAILURE_TIMEOUT` and `Tracking.REDETECTION_ATTEMPTS`.

## Diagnostics

`TrackerOutput.raw_data` includes:

- `performance_mode`
- `candidate_state`: `confirmed`, `tentative`, or `none`
- `candidate_bbox`: private validation geometry for diagnostics
- `validation_progress`: valid candidate count and required consensus

Tentative geometry is diagnostic only. Consumers must use the shared tracker
freshness contract, not infer command eligibility from `candidate_bbox`.

## Tuning And Acceptance

- Reduce gates only after inspecting false reacquisition and drift, not only
  apparent continuity.
- Do not extend `failure_threshold` to hide loss; every rejection is already
  follower-ineligible.
- Keep appearance updates conservative around occlusion and distractors.
- For tiny aerial targets, retain enough pixels in the initial ROI and validate
  under the expected compression, motion blur, and frame cadence.
- Use SmartTracker when detector association is required. It has a separate
  measured/tentative/predicted lifecycle and must pass the same command
  freshness boundary.

## References

- [OpenCV TrackerCSRT API](https://docs.opencv.org/4.x/d2/da2/classcv_1_1TrackerCSRT.html)
- [Discriminative Correlation Filter with Channel and Spatial Reliability, CVPR 2017](https://openaccess.thecvf.com/content_cvpr_2017/html/Lukezic_Discriminative_Correlation_Filter_CVPR_2017_paper.html)
- [Tracker architecture](../01-architecture/README.md)
- [SmartTracker](smart-tracker.md)
