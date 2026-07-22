# src/classes/trackers/dlib_tracker.py

"""dlib correlation tracker with PSR-based candidate validation.

The fast, balanced, and robust modes change validation cost. Their latency and
continuity must be measured on the intended camera, target, and computer.

References:
-----------
- dlib Library: http://dlib.net/
- Danelljan et al., BMVC 2014 (Accurate Scale Estimation)
- Bolme et al., CVPR 2010 (PSR Metric)
"""

import logging
import time
import numpy as np
from typing import Optional, Tuple
from collections import deque

try:
    import dlib
    DLIB_AVAILABLE = True
except ImportError:
    DLIB_AVAILABLE = False
    logging.warning(
        "Optional dlib tracker unavailable; Core profile remains operational. "
        "Install with: bash scripts/setup/install-dlib.sh"
    )

from classes.parameters import Parameters
from classes.trackers.base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType

logger = logging.getLogger(__name__)


class DlibTracker(BaseTracker):
    """dlib Correlation Filter Tracker with fast / balanced / robust modes."""

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        if not DLIB_AVAILABLE:
            raise ImportError("dlib library is required but not installed.")

        super().__init__(video_handler, detector, app_controller)

        self.tracker_name = "dlib"

        if self.position_estimator:
            self.position_estimator.reset()

        # Performance mode from config
        dlib_config = getattr(Parameters, 'DLIB_Tracker', {})
        self.performance_mode = dlib_config.get('performance_mode', 'balanced')
        self.appearance_learning_rate = dlib_config.get(
            'appearance_learning_rate', 0.08
        )
        self._configure_performance_mode()

        # PSR history for debugging
        self.psr_history: deque = deque(maxlen=10)

        # Appearance model enhancements
        appearance_config = dlib_config.get('appearance', {})
        self.use_adaptive_learning = appearance_config.get('use_adaptive_learning', True)
        self.adaptive_learning_bounds = appearance_config.get('adaptive_learning_bounds', [0.05, 0.15])
        self.freeze_on_low_confidence = appearance_config.get('freeze_on_low_confidence', True)

        # Motion model enhancements
        motion_config = dlib_config.get('motion', {})
        self.velocity_limit = motion_config.get('velocity_limit', 25.0)
        self.stabilization_alpha = motion_config.get('stabilization_alpha', 0.3)
        self.smoothed_bbox = None

        logger.info(f"{self.tracker_name} initialized in '{self.performance_mode}' mode")

    def _configure_performance_mode(self):
        """Configure tracker based on performance mode."""
        dlib_config = getattr(Parameters, 'DLIB_Tracker', {})

        if self.performance_mode == 'fast':
            self.enable_validation = False
            self.enable_ema_smoothing = False
            self.psr_confidence_threshold = dlib_config.get('psr_confidence_threshold', 5.0)
            self.failure_threshold = dlib_config.get('failure_threshold', 3)
            self.validation_start_frame = 999999
            self.psr_high_confidence = dlib_config.get('psr_high_confidence', 20.0)
            self.psr_low_confidence = dlib_config.get('psr_low_confidence', 3.0)
            logger.info("dlib Mode: FAST - minimal validation")

        elif self.performance_mode == 'balanced':
            self.enable_validation = False
            self.enable_ema_smoothing = True
            self.psr_confidence_threshold = dlib_config.get('psr_confidence_threshold', 7.0)
            self.failure_threshold = dlib_config.get('failure_threshold', 5)
            self.validation_start_frame = dlib_config.get('validation_start_frame', 10)
            self.confidence_ema_alpha = dlib_config.get('confidence_smoothing_alpha', 0.7)
            self.psr_high_confidence = dlib_config.get('psr_high_confidence', 20.0)
            self.psr_low_confidence = dlib_config.get('psr_low_confidence', 5.0)
            logger.info("dlib Mode: BALANCED - smoothed PSR validation")

        elif self.performance_mode == 'robust':
            self.enable_validation = True
            self.enable_ema_smoothing = True
            self.psr_confidence_threshold = dlib_config.get('psr_confidence_threshold', 7.0)
            self.failure_threshold = dlib_config.get('failure_threshold', 5)
            self.validation_start_frame = dlib_config.get('validation_start_frame', 5)
            self.confidence_ema_alpha = dlib_config.get('confidence_smoothing_alpha', 0.7)
            self.max_scale_change = dlib_config.get('max_scale_change_per_frame', 0.5)
            self.motion_consistency_threshold = dlib_config.get('max_motion_per_frame', 0.6)
            self.psr_high_confidence = dlib_config.get('psr_high_confidence', 20.0)
            self.psr_low_confidence = dlib_config.get('psr_low_confidence', 5.0)
            logger.info("dlib Mode: ROBUST - PSR, motion, and scale validation")

        else:
            logger.warning(f"Unknown performance mode '{self.performance_mode}', using 'balanced'")
            self.performance_mode = 'balanced'
            self._configure_performance_mode()

    def _create_tracker(self):
        return dlib.correlation_tracker()

    # =========================================================================
    # PSR Confidence Conversion
    # =========================================================================

    def _psr_to_confidence(self, psr: float) -> float:
        """Convert PSR to normalized confidence (0.0-1.0)."""
        psr_clamped = max(0.0, min(psr, 30.0))
        if psr_clamped < self.psr_low_confidence:
            return psr_clamped / (self.psr_low_confidence * 2.0)
        elif psr_clamped < self.psr_confidence_threshold:
            return (0.25 + (psr_clamped - self.psr_low_confidence) /
                    (self.psr_confidence_threshold - self.psr_low_confidence) * 0.25)
        elif psr_clamped < self.psr_high_confidence:
            return (0.5 + (psr_clamped - self.psr_confidence_threshold) /
                    (self.psr_high_confidence - self.psr_confidence_threshold) * 0.4)
        else:
            return 0.9 + min(0.1, (psr_clamped - self.psr_high_confidence) / 20.0)

    # =========================================================================
    # Appearance Helpers
    # =========================================================================

    def _get_adaptive_learning_rate(self, psr: float) -> float:
        """Learning rate based on current PSR confidence."""
        if not self.use_adaptive_learning:
            return getattr(self, 'appearance_learning_rate', 0.08)
        min_lr, max_lr = self.adaptive_learning_bounds
        if psr < self.psr_low_confidence:
            return min_lr
        elif psr > self.psr_high_confidence:
            return max_lr
        else:
            psr_range = self.psr_high_confidence - self.psr_low_confidence
            psr_normalized = (psr - self.psr_low_confidence) / psr_range
            return min_lr + psr_normalized * (max_lr - min_lr)

    def _should_freeze_template(self, psr: float) -> bool:
        """Freeze template during low-confidence to prevent corruption."""
        if not self.freeze_on_low_confidence:
            return False
        return psr < self.psr_low_confidence

    def _apply_motion_stabilization(self, bbox: Tuple) -> Tuple:
        """Apply EMA smoothing to bbox position to reduce jitter."""
        if self.smoothed_bbox is None:
            self.smoothed_bbox = tuple(float(v) for v in bbox)
            return bbox
        alpha = self.stabilization_alpha
        smoothed_float = tuple(alpha * new + (1 - alpha) * old
                               for new, old in zip(bbox, self.smoothed_bbox))
        self.smoothed_bbox = smoothed_float
        return tuple(int(round(v)) for v in smoothed_float)

    def _validate_velocity(self, bbox: Tuple) -> bool:
        """Validate velocity doesn't exceed realistic limits."""
        if not self.prev_bbox or self.frame_count < 3:
            return True
        prev_cx = self.prev_bbox[0] + self.prev_bbox[2] / 2
        prev_cy = self.prev_bbox[1] + self.prev_bbox[3] / 2
        curr_cx = bbox[0] + bbox[2] / 2
        curr_cy = bbox[1] + bbox[3] / 2
        velocity_magnitude = np.sqrt((curr_cx - prev_cx) ** 2 + (curr_cy - prev_cy) ** 2)

        dlib_config = getattr(Parameters, 'DLIB_Tracker', {})
        normalize_by_size = dlib_config.get('velocity_normalize_by_size', True)
        if normalize_by_size and self.prev_bbox:
            target_diagonal = np.sqrt(self.prev_bbox[2] ** 2 + self.prev_bbox[3] ** 2)
            max_velocity_factor = dlib_config.get('max_velocity_target_factor', 2.0)
            effective_limit = target_diagonal * max_velocity_factor
            is_valid = velocity_magnitude < effective_limit
        else:
            is_valid = velocity_magnitude < self.velocity_limit
        if not is_valid:
            logger.debug(f"Velocity validation failed: {velocity_magnitude:.1f}")
        return is_valid

    def _update_appearance_model_safe(self, frame, bbox, learning_rate=None):
        """Override: add freeze check and adaptive LR for dlib."""
        if not self.detector or not hasattr(self.detector, 'adaptive_features'):
            return
        if self.detector.adaptive_features is None:
            return
        current_psr = list(self.psr_history)[-1] if self.psr_history else self.psr_confidence_threshold
        if self._should_freeze_template(current_psr):
            return
        if not self._should_update_appearance(frame, bbox):
            return
        current_features = self.detector.extract_features(frame, bbox)
        lr = learning_rate or self._get_adaptive_learning_rate(current_psr)
        self.detector.adaptive_features = (
            (1 - lr) * self.detector.adaptive_features + lr * current_features)

    # =========================================================================
    # Tracking Interface
    # =========================================================================

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        logger.info(f"Initializing {self.tracker_name} tracker with bbox: {bbox}")
        x, y, w, h = bbox
        dlib_rect = dlib.rectangle(int(x), int(y), int(x + w), int(y + h))
        self.tracker.start_track(frame, dlib_rect)
        self.tracking_started = True

        self._initialize_detector_target(frame, bbox)

        self.bbox = tuple(int(value) for value in bbox)
        self.prev_bbox = self.bbox
        self.predicted_bbox = None
        self.set_center((
            int(self.bbox[0] + self.bbox[2] / 2),
            int(self.bbox[1] + self.bbox[3] / 2),
        ))
        self.normalize_bbox()
        self.last_measurement_timestamp = time.time()
        self.last_failure_info = None
        self.confidence = 1.0
        self.failure_count = 0
        self.frame_count = 0
        self.prev_center = None
        self.last_update_time = time.monotonic()
        self.raw_confidence_history.clear()
        self.psr_history.clear()

        self.smoothed_bbox = bbox

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        if not self.tracking_started:
            return False, self.bbox

        start_time = time.time()
        dt = self.update_time()

        if self.override_active:
            return self._handle_smart_tracker_override(frame, dt)

        # Run dlib tracker
        psr = self.tracker.update(frame)
        pos = self.tracker.get_position()
        detected_bbox = (int(pos.left()), int(pos.top()),
                         int(pos.width()), int(pos.height()))

        self.psr_history.append(psr)
        raw_confidence = self._psr_to_confidence(psr)
        detected_bbox = self._apply_motion_stabilization(detected_bbox)

        velocity_valid = self._validate_velocity(detected_bbox)

        # Startup grace period
        if self.frame_count < self.validation_start_frame:
            return self._accept_result(frame, detected_bbox, raw_confidence, dt, start_time)

        if not velocity_valid:
            self.confidence = raw_confidence
            logger.debug("Velocity validation rejected dlib candidate")
            return self._reject_candidate("motion_invalid", start_time)

        # Mode-specific logic
        if self.performance_mode == 'fast':
            return self._update_fast(frame, detected_bbox, raw_confidence, dt, start_time)
        elif self.performance_mode == 'balanced':
            return self._update_balanced(frame, detected_bbox, raw_confidence, dt, start_time)
        else:
            return self._update_robust(frame, detected_bbox, raw_confidence, dt, start_time)

    # =========================================================================
    # Mode-Specific Update Logic
    # =========================================================================

    def _accept_result(self, frame, bbox, confidence, dt, start_time):
        """Accept result (startup grace or cooldown period)."""
        bbox = tuple(int(value) for value in bbox)
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)
        self.confidence = confidence
        self._update_appearance_model_safe(frame, bbox)
        self._update_estimator(dt)
        self._update_out_of_frame_status(frame)
        self.prev_bbox = self.bbox
        self.predicted_bbox = None
        self.last_measurement_timestamp = time.time()
        self.last_failure_info = None
        self.failure_count = 0
        self.successful_frames += 1
        self.frame_count += 1
        self._log_performance(start_time)
        return True, self.bbox

    def _update_fast(self, frame, bbox, confidence, dt, start_time):
        """Fast mode — minimal validation."""
        if confidence < (self.psr_confidence_threshold / self.psr_high_confidence):
            self.confidence = confidence
            return self._reject_candidate("low_confidence", start_time)
        return self._accept_result(frame, bbox, confidence, dt, start_time)

    def _update_balanced(self, frame, bbox, confidence, dt, start_time):
        """Balanced mode — PSR confidence monitoring with smoothing."""
        smoothed_confidence = (self._smooth_confidence(confidence)
                               if self.enable_ema_smoothing else confidence)
        self.confidence = smoothed_confidence

        if smoothed_confidence < (self.psr_confidence_threshold / self.psr_high_confidence):
            logger.debug(f"Low confidence ({self.failure_count}/{self.failure_threshold}): "
                         f"{smoothed_confidence:.2f}")
            return self._reject_candidate("low_confidence", start_time)
        return self._accept_result(
            frame, bbox, smoothed_confidence, dt, start_time
        )

    def _update_robust(self, frame, bbox, confidence, dt, start_time):
        """Robust mode — full validation."""
        estimator_prediction = (
            self._get_estimator_prediction(dt) if self.estimator_enabled else None
        )
        motion_valid = self._validate_bbox_motion(bbox, estimator_prediction) if self.enable_validation else True
        scale_valid = self._validate_bbox_scale(bbox) if self.enable_validation else True

        smoothed_confidence = self._smooth_confidence(confidence)
        self.confidence = smoothed_confidence

        threshold = self.psr_confidence_threshold / self.psr_high_confidence
        if smoothed_confidence > threshold and motion_valid and scale_valid:
            logger.debug(f"dlib accepted: conf={smoothed_confidence:.2f}, "
                         f"motion={motion_valid}, scale={scale_valid}")
            return self._accept_result(
                frame, bbox, smoothed_confidence, dt, start_time
            )

        logger.debug(f"Rejected dlib candidate: conf={smoothed_confidence:.2f}, "
                     f"motion={motion_valid}, scale={scale_valid}")
        loss_reason = (
            "scale_invalid"
            if not scale_valid
            else "motion_invalid"
            if not motion_valid
            else "low_confidence"
        )
        return self._reject_candidate(loss_reason, start_time)

    def _reject_candidate(self, loss_reason: str, start_time: float):
        """Record an unusable dlib candidate without replacing confirmed state."""
        self._record_loss_start()
        self.failure_count += 1
        self.failed_frames += 1
        self.frame_count += 1
        self._build_failure_info(loss_reason)
        self._log_performance(start_time)
        if self.failure_count == self.failure_threshold:
            logger.warning(
                "Tracking lost after %d consecutive rejected measurements",
                self.failure_count,
            )
        return False, self.bbox

    # =========================================================================
    # Output
    # =========================================================================

    def get_output(self) -> TrackerOutput:
        latest_psr = list(self.psr_history)[-1] if self.psr_history else 0.0
        return self._build_output(
            tracker_algorithm='dlib_correlation_filter',
            extra_quality={
                'psr_value': latest_psr,
            },
            extra_raw={
                'performance_mode': self.performance_mode,
                'psr_history': list(self.psr_history),
            },
            extra_metadata={
                'performance_mode': self.performance_mode,
                'dlib_version': dlib.__version__ if hasattr(dlib, '__version__') else 'unknown',
            },
        )

    def get_capabilities(self) -> dict:
        base = super().get_capabilities()
        base.update({
            'tracker_algorithm': 'dlib_correlation_filter',
            'supports_rotation': False,
            'supports_scale_change': True,
            'supports_occlusion': False,
            'accuracy_rating': 'scenario_dependent',
            'speed_rating': 'scenario_dependent',
            'correlation_filter': True,
            'psr_confidence': True,
            'performance_mode': self.performance_mode,
            'prediction_command_eligible': False,
        })
        return base
