# src/classes/trackers/csrt_tracker.py

"""
CSRTTracker Module - Configurable Performance Modes
-----------------------------------------------------

CSRT (Channel and Spatial Reliability Tracking) from OpenCV with configurable
robustness enhancements.

Performance Modes:
------------------
1. **legacy** - Original CSRT behavior (15-20 FPS, most reliable startup)
2. **balanced** - Light enhancements (12-18 FPS, good trade-off)
3. **robust** - Full validation (10-15 FPS, maximum stability)

References:
-----------
- CSRT Paper: Lukezic et al., CVPR 2017
"""

import logging
import time
import cv2
import numpy as np
from typing import Optional, Tuple
from classes.parameters import Parameters
from classes.trackers.base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType

logger = logging.getLogger(__name__)


class CSRTTracker(BaseTracker):
    """CSRT Tracker with legacy / balanced / robust performance modes."""

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        super().__init__(video_handler, detector, app_controller)

        self.tracker_name = "CSRT"

        if self.position_estimator:
            self.position_estimator.reset()

        # Performance mode from config
        csrt_config = getattr(Parameters, 'CSRT_Tracker', {})
        self.performance_mode = csrt_config.get('performance_mode', 'robust')
        self._configure_performance_mode()

        # Multi-frame validation consensus
        self.enable_multiframe_validation = csrt_config.get('enable_multiframe_validation', True)
        self.validation_consensus_frames = csrt_config.get('validation_consensus_frames', 3)
        self.consecutive_valid_frames = 0
        self.is_validated = False

        logger.info(f"{self.tracker_name} initialized in '{self.performance_mode}' mode")

    def _configure_performance_mode(self):
        """Configure tracker based on performance mode.

        Mode-specific defaults are used as fallbacks; YAML values in
        CSRT_Tracker section take priority (making config authoritative).
        """
        csrt_config = getattr(Parameters, 'CSRT_Tracker', {})

        # Per-mode defaults (used when YAML doesn't specify a value)
        mode_defaults = {
            'legacy': {
                'enable_validation': False,
                'enable_ema_smoothing': False,
                'confidence_threshold': getattr(Parameters, 'CONFIDENCE_THRESHOLD', 0.3),
                'failure_threshold': 3,
                'validation_start_frame': 999999,
                'confidence_smoothing': 0.7,
                'max_scale_change_per_frame': 0.4,
                'max_motion_per_frame': 0.5,
                'appearance_learning_rate': 0.08,
            },
            'balanced': {
                'enable_validation': False,
                'enable_ema_smoothing': True,
                'confidence_threshold': 0.5,
                'failure_threshold': 5,
                'validation_start_frame': 10,
                'confidence_smoothing': 0.7,
                'max_scale_change_per_frame': 0.4,
                'max_motion_per_frame': 0.5,
                'appearance_learning_rate': 0.08,
            },
            'robust': {
                'enable_validation': True,
                'enable_ema_smoothing': True,
                'confidence_threshold': 0.4,
                'failure_threshold': 5,
                'validation_start_frame': 5,
                'confidence_smoothing': 0.7,
                'max_scale_change_per_frame': 0.4,
                'max_motion_per_frame': 0.5,
                'appearance_learning_rate': 0.08,
            },
        }

        if self.performance_mode not in mode_defaults:
            logger.warning(f"Unknown performance mode '{self.performance_mode}', using 'robust'")
            self.performance_mode = 'robust'

        defaults = mode_defaults[self.performance_mode]

        # Schema names are mapped explicitly to runtime fields so every exposed
        # setting has one observable effect.
        self.enable_validation = csrt_config.get(
            'enable_validation', defaults['enable_validation']
        )
        self.enable_ema_smoothing = csrt_config.get(
            'enable_ema_smoothing', defaults['enable_ema_smoothing']
        )
        self.confidence_threshold = csrt_config.get(
            'confidence_threshold', defaults['confidence_threshold']
        )
        self.failure_threshold = csrt_config.get(
            'failure_threshold', defaults['failure_threshold']
        )
        self.validation_start_frame = csrt_config.get(
            'validation_start_frame', defaults['validation_start_frame']
        )
        self.confidence_ema_alpha = csrt_config.get(
            'confidence_smoothing', defaults['confidence_smoothing']
        )
        self.max_scale_change = csrt_config.get(
            'max_scale_change_per_frame', defaults['max_scale_change_per_frame']
        )
        self.motion_consistency_threshold = csrt_config.get(
            'max_motion_per_frame', defaults['max_motion_per_frame']
        )
        self.appearance_learning_rate = csrt_config.get(
            'appearance_learning_rate', defaults['appearance_learning_rate']
        )
        self.appearance_update_min_confidence = csrt_config.get(
            'appearance_update_min_confidence',
            self.appearance_update_min_confidence,
        )

        labels = {
            'legacy': "LEGACY - Original behavior, maximum speed",
            'balanced': "BALANCED - Light enhancements, good trade-off",
            'robust': "ROBUST - Full validation, maximum stability",
        }
        logger.info(f"CSRT Mode: {labels[self.performance_mode]}")

    def _create_tracker(self):
        """Creates OpenCV CSRT tracker with optimized parameters."""
        csrt_config = getattr(Parameters, 'CSRT_Tracker', {})
        params = cv2.TrackerCSRT_Params()
        params.use_color_names = csrt_config.get('use_color_names', True)
        params.use_hog = csrt_config.get('use_hog', True)
        params.filter_lr = csrt_config.get('csrt_learning_rate', 0.02)
        params.number_of_scales = csrt_config.get('number_of_scales', 33)
        params.scale_step = csrt_config.get('scale_step', 1.02)
        params.use_segmentation = csrt_config.get('use_segmentation', True)
        logger.debug(f"CSRT params: color_names={params.use_color_names}, "
                     f"hog={params.use_hog}, filter_lr={params.filter_lr}, "
                     f"scales={params.number_of_scales}, scale_step={params.scale_step}")
        return cv2.TrackerCSRT_create(params)

    # =========================================================================
    # Multi-Frame Consensus
    # =========================================================================

    def _update_multiframe_consensus(self, is_valid: bool) -> bool:
        """Require consecutive valid candidates after a rejected measurement."""
        if not self.enable_multiframe_validation:
            return is_valid
        if is_valid:
            if self.is_validated:
                return True
            self.consecutive_valid_frames += 1
            if self.consecutive_valid_frames >= self.validation_consensus_frames:
                logger.debug(
                    "Multi-frame consensus reached after %d frames",
                    self.consecutive_valid_frames,
                )
                self.is_validated = True
        else:
            if self.is_validated:
                logger.debug("Multi-frame consensus broken - reacquisition required")
            self.consecutive_valid_frames = 0
            self.is_validated = False
        return self.is_validated

    # =========================================================================
    # Tracking Interface
    # =========================================================================

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        logger.info(f"Initializing {self.tracker_name} tracker with bbox: {bbox}")
        init_result = self.tracker.init(frame, bbox)
        if init_result is False:
            raise RuntimeError("OpenCV CSRT tracker rejected the initial ROI")
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
        self.consecutive_valid_frames = self.validation_consensus_frames
        # The operator-selected initial ROI is the first confirmed target. If a
        # candidate is later rejected, consensus is required before reacquiring.
        self.is_validated = True

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        if not self.tracking_started:
            return False, self.bbox

        start_time = time.time()
        dt = self.update_time()

        if self.override_active:
            return self._handle_smart_tracker_override(frame, dt)

        success, detected_bbox = self.tracker.update(frame)

        if not success:
            logger.warning("Tracking update failed in CSRT algorithm.")
            return self._handle_failure(frame, start_time)

        startup_grace = self.frame_count < self.validation_start_frame
        if self.performance_mode == 'legacy':
            return self._update_legacy(
                frame, detected_bbox, dt, start_time,
                update_appearance=not startup_grace,
            )
        elif self.performance_mode == 'balanced':
            return self._update_balanced(
                frame, detected_bbox, dt, start_time,
                update_appearance=not startup_grace,
            )
        else:
            return self._update_robust(
                frame, detected_bbox, dt, start_time,
                validate_motion_and_scale=not startup_grace,
                update_appearance=not startup_grace,
            )

    # =========================================================================
    # Mode-Specific Update Logic
    # =========================================================================

    def _accept_result(
        self,
        frame,
        bbox,
        dt,
        start_time,
        *,
        update_appearance: bool = True,
    ):
        """Accept tracking result (startup grace or validated)."""
        bbox = tuple(int(value) for value in bbox)
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)
        if update_appearance:
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

    def _candidate_is_confirmed(self, is_valid: bool) -> bool:
        """Apply fail-closed candidate validation and reacquisition consensus."""
        return self._update_multiframe_consensus(is_valid)

    def _appearance_is_valid(self) -> bool:
        """Apply the canonical detector appearance threshold when available."""
        if (
            not self.detector
            or not hasattr(self.detector, 'compute_appearance_confidence')
            or getattr(self.detector, 'adaptive_features', None) is None
        ):
            return True
        try:
            threshold = float(Parameters.APPEARANCE_CONFIDENCE_THRESHOLD)
        except (AttributeError, TypeError, ValueError):
            threshold = 0.7
        threshold = max(0.0, min(1.0, threshold))
        return self.appearance_confidence >= threshold

    def _update_legacy(
        self, frame, bbox, dt, start_time, *, update_appearance: bool = True
    ):
        """Legacy mode — original CSRT behavior."""
        raw_confidence = self._evaluate_candidate_confidence(frame, bbox)
        self.confidence = raw_confidence
        confidence_valid = raw_confidence >= Parameters.CONFIDENCE_THRESHOLD
        appearance_valid = self._appearance_is_valid()
        if not self._candidate_is_confirmed(confidence_valid and appearance_valid):
            logger.warning("Tracking failed due to low confidence")
            reason = (
                "appearance_mismatch"
                if confidence_valid and not appearance_valid
                else "low_confidence"
                if not confidence_valid
                else "reacquisition_pending"
            )
            return self._reject_candidate(reason, start_time)
        return self._accept_result(
            frame, bbox, dt, start_time,
            update_appearance=update_appearance,
        )

    def _update_balanced(
        self, frame, bbox, dt, start_time, *, update_appearance: bool = True
    ):
        """Balanced mode — confidence smoothing only."""
        raw_confidence = self._evaluate_candidate_confidence(frame, bbox)
        smoothed_confidence = (self._smooth_confidence(raw_confidence)
                               if self.enable_ema_smoothing else raw_confidence)
        self.confidence = smoothed_confidence

        confidence_valid = smoothed_confidence >= self.confidence_threshold
        appearance_valid = self._appearance_is_valid()
        if not self._candidate_is_confirmed(confidence_valid and appearance_valid):
            logger.debug(f"Low confidence ({self.failure_count}/{self.failure_threshold}): "
                         f"{smoothed_confidence:.2f}")
            reason = (
                "appearance_mismatch"
                if confidence_valid and not appearance_valid
                else "low_confidence"
                if not confidence_valid
                else "reacquisition_pending"
            )
            return self._reject_candidate(reason, start_time)
        return self._accept_result(
            frame, bbox, dt, start_time,
            update_appearance=update_appearance,
        )

    def _update_robust(
        self,
        frame,
        bbox,
        dt,
        start_time,
        *,
        validate_motion_and_scale: bool = True,
        update_appearance: bool = True,
    ):
        """Robust mode — full validation."""
        estimator_prediction = self._get_estimator_prediction() if self.estimator_enabled else None
        validation_enabled = self.enable_validation and validate_motion_and_scale
        motion_valid = self._validate_bbox_motion(bbox, estimator_prediction) if validation_enabled else True
        scale_valid = self._validate_bbox_scale(bbox) if validation_enabled else True

        raw_confidence = self._evaluate_candidate_confidence(frame, bbox)
        smoothed_confidence = self._smooth_confidence(raw_confidence)
        self.confidence = smoothed_confidence

        candidate_valid = (
            smoothed_confidence >= self.confidence_threshold
            and self._appearance_is_valid()
            and motion_valid
            and scale_valid
        )
        if self._candidate_is_confirmed(candidate_valid):
            logger.debug(f"CSRT accepted: conf={smoothed_confidence:.2f}, "
                         f"motion={motion_valid}, scale={scale_valid}")
            return self._accept_result(
                frame, bbox, dt, start_time,
                update_appearance=update_appearance,
            )

        logger.debug(f"Rejected CSRT candidate: conf={smoothed_confidence:.2f}, "
                     f"motion={motion_valid}, scale={scale_valid}")
        if candidate_valid:
            loss_reason = "reacquisition_pending"
        elif not scale_valid:
            loss_reason = "scale_invalid"
        elif not motion_valid:
            loss_reason = "motion_invalid"
        elif not self._appearance_is_valid():
            loss_reason = "appearance_mismatch"
        else:
            loss_reason = "low_confidence"
        return self._reject_candidate(loss_reason, start_time)

    def _evaluate_candidate_confidence(self, frame, bbox) -> float:
        """Evaluate one candidate without replacing confirmed target geometry."""
        confirmed_bbox = self.bbox
        confirmed_center = self.center
        confirmed_normalized_bbox = self.normalized_bbox
        confirmed_normalized_center = self.normalized_center
        confirmed_prev_center = self.prev_center
        previous_confidence = self.confidence

        try:
            self.prev_center = confirmed_center
            self.bbox = bbox
            self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
            return float(self.compute_confidence(frame))
        finally:
            self.bbox = confirmed_bbox
            self.center = confirmed_center
            self.normalized_bbox = confirmed_normalized_bbox
            self.normalized_center = confirmed_normalized_center
            self.prev_center = confirmed_prev_center
            self.confidence = previous_confidence

    def _reject_candidate(self, loss_reason: str, start_time: float):
        """Record an unusable measurement while preserving confirmed geometry."""
        self._record_loss_start()
        self.failure_count += 1
        self.failed_frames += 1
        self.frame_count += 1
        self._build_failure_info(loss_reason)
        self._log_performance(start_time)
        if self.failure_count >= self.failure_threshold:
            logger.warning(
                "Tracking lost after %d consecutive rejected measurements",
                self.failure_count,
            )
        return False, self.bbox

    def _handle_failure(self, frame, start_time):
        """Handle complete CSRT tracking failure."""
        self._update_multiframe_consensus(False)
        self._record_loss_start()
        self.failure_count += 1
        self.failed_frames += 1
        self.frame_count += 1
        self._update_out_of_frame_status(frame)
        self._build_failure_info("tracker_failed")
        self._log_performance(start_time)
        if self.failure_count >= self.failure_threshold:
            logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
        return False, self.bbox

    # =========================================================================
    # Output
    # =========================================================================

    def get_output(self) -> TrackerOutput:
        return self._build_output(
            tracker_algorithm='CSRT',
            extra_quality={
                'appearance_confidence': getattr(self, 'appearance_confidence', 1.0),
            },
            extra_raw={
                'performance_mode': self.performance_mode,
            },
            extra_metadata={
                'performance_mode': self.performance_mode,
                'opencv_version': cv2.__version__,
            },
        )

    def get_capabilities(self) -> dict:
        base = super().get_capabilities()
        base.update({
            'tracker_algorithm': 'CSRT',
            'supports_rotation': True,
            'supports_scale_change': True,
            'supports_occlusion': True,
            'accuracy_rating': 'very_high',
            'speed_rating': 'medium',
            'opencv_tracker': True,
            'performance_mode': self.performance_mode,
        })
        return base
