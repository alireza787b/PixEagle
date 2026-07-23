# Parameter Reference

> Complete reference for all tracker configuration parameters

Checked-in defaults are defined in `configs/config_default.yaml`. Optional local
overrides belong in `configs/config.yaml`; both are validated by the generated
`configs/config_schema.yaml` and published through the `Parameters` class.

---

## Global Tracker Settings

```yaml
Tracking:
  DEFAULT_TRACKING_ALGORITHM: "CSRT"  # CSRT, KCF, dlib, Gimbal
  CENTER_HISTORY_LENGTH: 10
  MOTION_CONFIDENCE_WEIGHT: 0.5
  APPEARANCE_CONFIDENCE_WEIGHT: 0.5
  MOTION_CONFIDENCE_THRESHOLD: 0.7
  MAX_DISPLACEMENT_THRESHOLD: 0.25

TrackerSafety:
  BOUNDARY_MARGIN_PIXELS: 15
  ENABLE_BOUNDARY_PENALTY: true
  BOUNDARY_PENALTY_MIN: 0.5

Estimator:
  USE_ESTIMATOR: true
  ESTIMATOR_TYPE: "Kalman"
  ESTIMATOR_HISTORY_LENGTH: 5
```

`Tracking.DEFAULT_TRACKING_ALGORITHM` is the saved startup and tracker-restart
choice. Use the Tracker page for a live process-only switch. The Settings
dropdown is generated from selectable factory entries in
`configs/tracker_schemas.yaml`; Smart Tracker remains a separate runtime mode.

---

## CSRT Tracker

```yaml
CSRT_Tracker:
  # Performance mode
  performance_mode: "robust"  # legacy, balanced, robust

  # Confidence and validation
  confidence_threshold: 0.45
  failure_threshold: 5
  validation_start_frame: 10
  confidence_smoothing: 0.7
  max_scale_change_per_frame: 0.5
  max_motion_per_frame: 0.6

  # OpenCV CSRT parameters
  use_color_names: true
  use_hog: true
  csrt_learning_rate: 0.02
  number_of_scales: 33
  scale_step: 1.02
  use_segmentation: true

  # Multi-frame validation
  enable_multiframe_validation: true
  validation_consensus_frames: 3

  # Appearance model
  appearance_update_min_confidence: 0.55
  appearance_learning_rate: 0.1
```

For CSRT, KCF, and dlib, `failure_threshold` controls when repeated rejected
measurements are reported as a confirmed loss. It is not a command-validity
grace period: the first rejected measurement is immediately stale and unusable
for following.

---

## KCF + Kalman Tracker

```yaml
KCF_Tracker:
  # Confidence thresholds
  confidence_threshold: 0.15
  confidence_smoothing: 0.6
  failure_threshold: 7

  # Motion validation
  max_scale_change_per_frame: 0.6
  motion_consistency_threshold: 0.15

  # Internal Kalman filter
  kalman_process_noise: 0.1
  kalman_velocity_noise_factor: 0.5
  kalman_measurement_noise: 5.0
  kalman_initial_position_covariance: 10.0
  kalman_initial_velocity_covariance: 100.0

  # Occlusion handling
  use_velocity_during_occlusion: true
  occlusion_velocity_factor: 0.5

  # Appearance model
  appearance_learning_rate: 0.18
```

The internal KCF prediction is diagnostic and is never a command-eligible
measurement. Application-level detector recovery owns reacquisition.

---

## dlib Tracker

```yaml
DLIB_Tracker:
  # Performance mode
  performance_mode: "balanced"  # fast, balanced, robust

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

  # Appearance learning
  appearance_learning_rate: 0.08

  # Appearance model
  appearance:
    use_adaptive_learning: true
    adaptive_learning_bounds: [0.05, 0.15]
    freeze_on_low_confidence: true

  # Motion settings
  motion:
    velocity_limit: 25.0
    stabilization_alpha: 0.3
    velocity_normalize_by_size: true
    max_velocity_target_factor: 2.0
```

dlib-specific re-detection and debug switches were retired because they had no
runtime consumer. The application-level `Tracking` and `Detector` sections own
bounded classic-tracker recovery.

---

## Gimbal Tracker

```yaml
GimbalTracker:
  ENABLED: true
  PROVIDER: "topotek_sip_udp"
  UDP_HOST: "192.168.0.108"
  UDP_PORT: 9003
  LISTEN_PORT: 9004
  COORDINATE_SYSTEM: "GIMBAL_BODY"
  DISABLE_ESTIMATOR: true
  data_timeout_seconds: 5.0
  max_consecutive_failures: 10
```

---

## SmartTracker

```yaml
SmartTracker:
  # Schema-backed availability; Smart Mode activation remains explicit
  SMART_TRACKER_ENABLED: true

  # Model selection
  # Register both artifacts through the trusted model workflow first
  SMART_TRACKER_GPU_MODEL_PATH: "models/yolo26n.pt"
  SMART_TRACKER_CPU_MODEL_PATH: "models/yolo26n_ncnn_model"
  SMART_TRACKER_USE_GPU: true
  SMART_TRACKER_FALLBACK_TO_CPU: true

  # Detection parameters
  SMART_TRACKER_CONFIDENCE_THRESHOLD: 0.3
  SMART_TRACKER_IOU_THRESHOLD: 0.3
  SMART_TRACKER_MAX_DETECTIONS: 20

  # Tracker type
  TRACKER_TYPE: "botsort"  # botsort, bytetrack, custom_reid

  # Tracking strategy
  TRACKING_STRATEGY: "hybrid"  # id_only, hybrid, spatial_only

  # Motion prediction
  ENABLE_PREDICTION_BUFFER: true
  ID_LOSS_TOLERANCE_FRAMES: 5

  # Appearance model (custom ReID)
  ENABLE_APPEARANCE_MODEL: true
  MAX_APPEARANCE_FEATURES: 10
  APPEARANCE_UPDATE_INTERVAL: 5
  APPEARANCE_MATCH_THRESHOLD: 0.6

  # Display
  SMART_TRACKER_SHOW_FPS: false
  SMART_TRACKER_ACTIVE_COLOR: [0, 255, 100]
  SMART_TRACKER_PASSIVE_COLOR: [140, 140, 140]
```

---

## Parameter Access in Code

```python
from classes.parameters import Parameters

# Direct access
algorithm = Parameters.DEFAULT_TRACKING_ALGORITHM

# Nested access
csrt_config = getattr(Parameters, 'CSRT_Tracker', {})
mode = csrt_config.get('performance_mode', 'robust')

# SmartTracker config
smart_config = Parameters.SmartTracker
model_path = smart_config.get('SMART_TRACKER_GPU_MODEL_PATH')
```

---

## Config Service API

The in-process service reads schema-backed values by section and parameter:

```python
from classes.config_service import ConfigService

config_service = ConfigService.get_instance()
tracker_type = config_service.get_parameter("SmartTracker", "TRACKER_TYPE")
tracker_schema = config_service.get_parameter_schema(
    "SmartTracker", "TRACKER_TYPE"
)
```

Do not use nonexistent `update_value()` or `update_nested()` helpers. Persisted
mutations should go through the Settings/config workflow so validation,
transactional persistence, audit, runtime publication, and restart-tier
reporting remain coupled.

---

## Environment Variables

PixEagle does not implement generic `PIXEAGLE_<PARAMETER>` overrides. Values
such as `PIXEAGLE_SMART_TRACKER_USE_GPU` are not configuration APIs; use the
schema-backed Settings/config workflow.

---

## Related

- [Schema System](schema-system.md) - Schema definitions
- [Tuning Guide](tuning-guide.md) - Performance optimization
- [Tracker Reference](../02-reference/README.md) - Per-tracker details
