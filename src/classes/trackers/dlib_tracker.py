# src/classes/trackers/dlib_tracker.py

"""
DlibTracker Module - Correlation Filter with Configurable Performance Modes
----------------------------------------------------------------------------

dlib Correlation Filter Tracker with PSR-based confidence scoring and
configurable performance modes.

Performance Modes:
------------------
1. **fast** - Minimal overhead (25-30 FPS)
2. **balanced** - PSR monitoring with grace period (18-25 FPS)
3. **robust** - Full validation (12-18 FPS)

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
    logging.error("dlib library not available. Install with: pip install dlib")

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
        self._configure_performance_mode()

        # PSR history for debugging
        self.psr_history: deque = deque(maxlen=10)

        # Adaptive PSR system
        adaptive_config = dlib_config.get('adaptive', {})
        self.adaptive_enabled = adaptive_config.get('enable', True)
        self.psr_dynamic_scaling = adaptive_config.get('psr_dynamic_scaling', True)
        self.adapt_rate = adaptive_config.get('adapt_rate', 0.15)
        self.psr_margin = adaptive_config.get('psr_margin', 1.5)
        self.adaptive_psr_threshold = self.psr_confidence_threshold

        # Appearance model enhancements
        appearance_config = dlib_config.get('appearance', {})
        self.use_adaptive_learning = appearance_config.get('use_adaptive_learning', True)
        self.adaptive_learning_bounds = appearance_config.get('adaptive_learning_bounds', [0.05, 0.15])
        self.freeze_on_low_confidence = appearance_config.get('freeze_on_low_confidence', True)
        self.reference_update_interval = appearance_config.get('reference_update_interval', 30)
        # NOTE: Stored but not yet consumed. Reserved for future re-ID comparison.
        self.reference_template = None
        self.frames_since_reference_update = 0

        # Motion model enhancements
        motion_config = dlib_config.get('motion', {})
        self.velocity_limit = motion_config.get('velocity_limit', 25.0)
        self.stabilization_alpha = motion_config.get('stabilization_alpha', 0.3)
        self.smoothed_bbox = None

        # Validation enhancements
        validation_config = dlib_config.get('validation', {})
        self.reinit_on_loss = validation_config.get('reinit_on_loss', True)
        self.cooldown_after_reinit = validation_config.get('cooldown_after_reinit', 5)
        self.reinit_cooldown_counter = 0

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
            logger.info("dlib Mode: FAST - Minimal validation (25-30 FPS)")

        elif self.performance_mode == 'balanced':
            self.enable_validation = False
            self.enable_ema_smoothing = True
            self.psr_confidence_threshold = dlib_config.get('psr_confidence_threshold', 7.0)
            self.failure_threshold = dlib_config.get('failure_threshold', 5)
            self.validation_start_frame = dlib_config.get('validation_start_frame', 10)
            self.confidence_ema_alpha = dlib_config.get('confidence_smoothing_alpha', 0.7)
            self.psr_high_confidence = dlib_config.get('psr_high_confidence', 20.0)
            self.psr_low_confidence = dlib_config.get('psr_low_confidence', 5.0)
            logger.info("dlib Mode: BALANCED - PSR monitoring with grace period (18-25 FPS)")

        elif self.performance_mode == 'robust':
            self.enable_validation = True
            self.enable_ema_smoothing = True
            self.psr_confidence_threshold = dlib_config.get('psr_confidence_threshold', 7.0)
            self.failure_threshold = dlib_config.get('failure_threshold', 5)
            self.validation_start_frame = dlib_config.get('validation_start_frame', 5)
            self.confidence_ema_alpha = dlib_config.get('confidence_smoothing_alpha', 0.7)
            self.max_scale_change = dlib_config.get('max_scale_change_per_frame', 0.5)
            self.motion_consistency_threshold = dlib_config.get('max_motion_per_frame', 0.6)
            self.appearance_learning_rate = dlib_config.get('appearance_learning_rate', 0.08)
            self.psr_high_confidence = dlib_config.get('psr_high_confidence', 20.0)
            self.psr_low_confidence = dlib_config.get('psr_low_confidence', 5.0)
            logger.info("dlib Mode: ROBUST - Full validation (12-18 FPS)")

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
    # Adaptive PSR & Appearance Helpers
    # =========================================================================

    def _update_adaptive_psr_threshold(self, current_psr: float) -> None:
        """Dynamically adjust PSR threshold based on recent history."""
        if not self.adaptive_enabled or not self.psr_dynamic_scaling:
            return
        if len(self.psr_history) >= 3:
            recent_psr_avg = np.mean(list(self.psr_history)[-5:])
            target_threshold = max(self.psr_low_confidence,
                                   min(recent_psr_avg * 0.7, self.psr_high_confidence * 0.5))
            self.adaptive_psr_threshold = (
                (1 - self.adapt_rate) * self.adaptive_psr_threshold +
                self.adapt_rate * target_threshold)
            self.adaptive_psr_threshold = max(
                self.psr_low_confidence,
                min(self.adaptive_psr_threshold,
                    self.psr_confidence_threshold * 1.2))

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

    def _update_reference_template(self, frame, psr: float) -> None:
        """Periodically refresh reference template on high confidence."""
        if not self.detector or self.reference_update_interval <= 0:
            return
        self.frames_since_reference_update += 1
        if (self.frames_since_reference_update >= self.reference_update_interval
                and psr > self.psr_high_confidence):
            current_features = self.detector.extract_features(frame, self.bbox)
            if current_features is not None:
                self.reference_template = current_features.copy()
                self.frames_since_reference_update = 0
                logger.debug(f"Reference template refreshed at frame {self.frame_count}")

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
        self._update_reference_template(frame, current_psr)

    # =========================================================================
    # Tracking Interface
    # =========================================================================

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        logger.info(f"Initializing {self.tracker_name} tracker with bbox: {bbox}")
        x, y, w, h = bbox
        dlib_rect = dlib.rectangle(int(x), int(y), int(x + w), int(y + h))
        self.tracker.start_track(frame, dlib_rect)
        self.tracking_started = True

        if self.detector:
            self.detector.initial_features = self.detector.extract_features(frame, bbox)
            self.detector.adaptive_features = self.detector.initial_features.copy()

        self.bbox = bbox
        self.prev_bbox = bbox
        self.confidence = 1.0
        self.failure_count = 0
        self.frame_count = 0
        self.prev_center = None
        self.last_update_time = time.time()
        self.raw_confidence_history.clear()
        self.psr_history.clear()

        self.reference_template = self.detector.initial_features.copy() if self.detector else None
        self.frames_since_reference_update = 0
        self.smoothed_bbox = bbox
        self.adaptive_psr_threshold = self.psr_confidence_threshold
        self.reinit_cooldown_counter = 0

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
        self._update_adaptive_psr_threshold(psr)
        raw_confidence = self._psr_to_confidence(psr)
        detected_bbox = self._apply_motion_stabilization(detected_bbox)

        # Velocity validation
        if not self._validate_velocity(detected_bbox) and self.frame_count >= self.validation_start_frame:
            logger.debug("Velocity validation failed - using previous bbox")
            detected_bbox = self.bbox

        if self.reinit_cooldown_counter > 0:
            self.reinit_cooldown_counter -= 1

        # Startup grace period
        if self.frame_count < self.validation_start_frame or self.reinit_cooldown_counter > 0:
            return self._accept_result(frame, detected_bbox, raw_confidence, dt, start_time)

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
        self.failure_count = 0
        self.successful_frames += 1
        self.frame_count += 1
        self._log_performance(start_time)
        return True, self.bbox

    def _update_fast(self, frame, bbox, confidence, dt, start_time):
        """Fast mode — minimal validation."""
        if confidence < (self.psr_confidence_threshold / self.psr_high_confidence):
            self._record_loss_start()
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self._build_failure_info("low_confidence")
                logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
                return False, self.bbox
            return True, self.bbox
        return self._accept_result(frame, bbox, confidence, dt, start_time)

    def _update_balanced(self, frame, bbox, confidence, dt, start_time):
        """Balanced mode — PSR confidence monitoring with smoothing."""
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)

        smoothed_confidence = (self._smooth_confidence(confidence)
                               if self.enable_ema_smoothing else confidence)
        self.confidence = smoothed_confidence

        if smoothed_confidence < (self.psr_confidence_threshold / self.psr_high_confidence):
            self._record_loss_start()
            self.failure_count += 1
            logger.debug(f"Low confidence ({self.failure_count}/{self.failure_threshold}): "
                         f"{smoothed_confidence:.2f}")
            if self.failure_count >= self.failure_threshold:
                self._build_failure_info("low_confidence")
                logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
                return False, self.bbox
        else:
            self.failure_count = 0
            self.successful_frames += 1

        self._update_appearance_model_safe(frame, bbox)
        self._update_estimator(dt)
        self._update_out_of_frame_status(frame)
        self.prev_bbox = self.bbox
        self.frame_count += 1
        self._log_performance(start_time)
        return True, self.bbox

    def _update_robust(self, frame, bbox, confidence, dt, start_time):
        """Robust mode — full validation."""
        estimator_prediction = self._get_estimator_prediction() if self.estimator_enabled else None
        motion_valid = self._validate_bbox_motion(bbox, estimator_prediction) if self.enable_validation else True
        scale_valid = self._validate_bbox_scale(bbox) if self.enable_validation else True

        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
        smoothed_confidence = self._smooth_confidence(confidence)

        threshold = self.psr_confidence_threshold / self.psr_high_confidence
        if smoothed_confidence > threshold and motion_valid and scale_valid:
            self.normalize_bbox()
            self.center_history.append(self.center)
            self._update_appearance_model_safe(frame, bbox)
            self._update_estimator(dt)
            self._update_out_of_frame_status(frame)
            self.prev_bbox = self.bbox
            self.failure_count = 0
            self.successful_frames += 1
            self.frame_count += 1
            self._log_performance(start_time)
            logger.debug(f"dlib accepted: conf={smoothed_confidence:.2f}, "
                         f"motion={motion_valid}, scale={scale_valid}")
            return True, self.bbox
        else:
            self._record_loss_start()
            self.failure_count += 1
            self.failed_frames += 1
            self.frame_count += 1
            self._update_out_of_frame_status(frame)
            logger.debug(f"Low confidence ({self.failure_count}/{self.failure_threshold}): "
                         f"conf={smoothed_confidence:.2f}, motion={motion_valid}, scale={scale_valid}")
            if self.failure_count >= self.failure_threshold:
                loss_reason = "scale_invalid" if not scale_valid else "low_confidence"
                self._build_failure_info(loss_reason)
                logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
                return False, self.bbox
            return True, self.bbox

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
            'accuracy_rating': 'high',
            'speed_rating': 'very_fast',
            'correlation_filter': True,
            'psr_confidence': True,
            'performance_mode': self.performance_mode,
        })
        return base
