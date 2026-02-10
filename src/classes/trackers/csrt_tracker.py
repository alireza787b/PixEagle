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
        self.performance_mode = csrt_config.get('performance_mode', 'balanced')
        self._configure_performance_mode()

        # Multi-frame validation consensus
        self.enable_multiframe_validation = csrt_config.get('enable_multiframe_validation', True)
        self.validation_consensus_frames = csrt_config.get('validation_consensus_frames', 3)
        self.consecutive_valid_frames = 0
        self.is_validated = False

        logger.info(f"{self.tracker_name} initialized in '{self.performance_mode}' mode")

    def _configure_performance_mode(self):
        """Configure tracker based on performance mode."""
        if self.performance_mode == 'legacy':
            self.enable_validation = False
            self.enable_ema_smoothing = False
            self.confidence_threshold = Parameters.CONFIDENCE_THRESHOLD
            self.failure_threshold = 3
            self.validation_start_frame = 999999
            logger.info("CSRT Mode: LEGACY - Original behavior, maximum speed")

        elif self.performance_mode == 'balanced':
            self.enable_validation = False
            self.enable_ema_smoothing = True
            self.confidence_threshold = 0.5
            self.failure_threshold = 5
            self.validation_start_frame = 10
            self.confidence_ema_alpha = 0.7
            logger.info("CSRT Mode: BALANCED - Light enhancements, good trade-off")

        elif self.performance_mode == 'robust':
            self.enable_validation = True
            self.enable_ema_smoothing = True
            self.confidence_threshold = 0.4
            self.failure_threshold = 5
            self.validation_start_frame = 5
            self.confidence_ema_alpha = 0.7
            self.max_scale_change = 0.4
            self.motion_consistency_threshold = 0.5
            self.appearance_learning_rate = 0.08
            logger.info("CSRT Mode: ROBUST - Full validation, maximum stability")

        else:
            logger.warning(f"Unknown performance mode '{self.performance_mode}', using 'balanced'")
            self.performance_mode = 'balanced'
            self._configure_performance_mode()

    def _create_tracker(self):
        """Creates OpenCV CSRT tracker with optimized parameters."""
        csrt_config = getattr(Parameters, 'CSRT_Tracker', {})
        params = cv2.TrackerCSRT_Params()
        params.use_color_names = csrt_config.get('use_color_names', True)
        params.use_hog = csrt_config.get('use_hog', True)
        params.number_of_scales = csrt_config.get('number_of_scales', 33)
        params.scale_step = csrt_config.get('scale_step', 1.02)
        params.use_segmentation = csrt_config.get('use_segmentation', True)
        logger.debug(f"CSRT params: color_names={params.use_color_names}, "
                     f"hog={params.use_hog}, scales={params.number_of_scales}, "
                     f"scale_step={params.scale_step}")
        return cv2.TrackerCSRT_create(params)

    # =========================================================================
    # Multi-Frame Consensus
    # =========================================================================

    def _update_multiframe_consensus(self, is_valid: bool) -> bool:
        """Requires consecutive successful frames before fully trusting detection."""
        if not self.enable_multiframe_validation:
            return is_valid
        if is_valid:
            self.consecutive_valid_frames += 1
            if self.consecutive_valid_frames >= self.validation_consensus_frames:
                if not self.is_validated:
                    logger.debug(f"Multi-frame consensus reached after "
                                 f"{self.consecutive_valid_frames} frames")
                self.is_validated = True
        else:
            if self.is_validated and self.consecutive_valid_frames >= self.validation_consensus_frames:
                logger.debug("Multi-frame consensus broken - resetting validation")
            self.consecutive_valid_frames = max(0, self.consecutive_valid_frames - 1)
            if self.consecutive_valid_frames == 0:
                self.is_validated = False
        return self.is_validated or self.consecutive_valid_frames > 0

    # =========================================================================
    # Tracking Interface
    # =========================================================================

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        logger.info(f"Initializing {self.tracker_name} tracker with bbox: {bbox}")
        self.tracker.init(frame, bbox)
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
        self.consecutive_valid_frames = 0
        self.is_validated = False

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
            return self._handle_failure(frame, dt)

        # Startup grace period — always accept
        if self.frame_count < self.validation_start_frame:
            return self._accept_result(frame, detected_bbox, dt, start_time)

        # After grace period — mode-specific logic
        if self.performance_mode == 'legacy':
            return self._update_legacy(frame, detected_bbox, dt, start_time)
        elif self.performance_mode == 'balanced':
            return self._update_balanced(frame, detected_bbox, dt, start_time)
        else:
            return self._update_robust(frame, detected_bbox, dt, start_time)

    # =========================================================================
    # Mode-Specific Update Logic
    # =========================================================================

    def _accept_result(self, frame, bbox, dt, start_time):
        """Accept tracking result (startup grace or validated)."""
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
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
        return True, self.bbox

    def _update_legacy(self, frame, bbox, dt, start_time):
        """Legacy mode — original CSRT behavior."""
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)
        csrt_config = getattr(Parameters, 'CSRT_Tracker', {})
        self._update_appearance_model_safe(
            frame, bbox, learning_rate=csrt_config.get('appearance_learning_rate', 0.05))
        self.compute_confidence(frame)
        if self.confidence < Parameters.CONFIDENCE_THRESHOLD:
            logger.warning("Tracking failed due to low confidence")
            self._record_loss_start()
            self.failure_count += 1
            self.failed_frames += 1
            self.frame_count += 1
            self._build_failure_info("low_confidence")
            return False, self.bbox
        self._update_estimator(dt)
        self._update_out_of_frame_status(frame)
        self.prev_bbox = self.bbox
        self.failure_count = 0
        self.successful_frames += 1
        self.frame_count += 1
        self._log_performance(start_time)
        return True, self.bbox

    def _update_balanced(self, frame, bbox, dt, start_time):
        """Balanced mode — confidence smoothing only."""
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)
        self._update_appearance_model_safe(frame, bbox)
        self.compute_confidence(frame)

        smoothed_confidence = (self._smooth_confidence(self.confidence)
                               if self.enable_ema_smoothing else self.confidence)

        if smoothed_confidence < self.confidence_threshold:
            self._record_loss_start()
            self.failure_count += 1
            logger.debug(f"Low confidence ({self.failure_count}/{self.failure_threshold}): "
                         f"{smoothed_confidence:.2f}")
            if self.failure_count >= self.failure_threshold:
                logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
                self._build_failure_info("low_confidence")
                return False, self.bbox
        else:
            self.failure_count = 0
            self.successful_frames += 1

        self._update_estimator(dt)
        self._update_out_of_frame_status(frame)
        self.prev_bbox = self.bbox
        self.frame_count += 1
        self._log_performance(start_time)
        return True, self.bbox

    def _update_robust(self, frame, bbox, dt, start_time):
        """Robust mode — full validation."""
        estimator_prediction = self._get_estimator_prediction() if self.estimator_enabled else None
        motion_valid = self._validate_bbox_motion(bbox, estimator_prediction) if self.enable_validation else True
        scale_valid = self._validate_bbox_scale(bbox) if self.enable_validation else True

        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(bbox[0] + bbox[2] / 2), int(bbox[1] + bbox[3] / 2)))
        self.compute_confidence(frame)
        smoothed_confidence = self._smooth_confidence(self.confidence)

        if smoothed_confidence > self.confidence_threshold and motion_valid and scale_valid:
            self.normalize_bbox()
            self.center_history.append(self.center)
            self._update_appearance_model_safe(
                frame, bbox, learning_rate=getattr(self, 'appearance_learning_rate', 0.08))
            self._update_estimator(dt)
            self._update_out_of_frame_status(frame)
            self.prev_bbox = self.bbox
            self.failure_count = 0
            self.successful_frames += 1
            self.frame_count += 1
            self._log_performance(start_time)
            logger.debug(f"CSRT accepted: conf={smoothed_confidence:.2f}, "
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
                logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
                self._build_failure_info(loss_reason)
                return False, self.bbox
            return True, self.bbox

    def _handle_failure(self, frame, dt):
        """Handle complete CSRT tracking failure."""
        self._record_loss_start()
        self.failure_count += 1
        self.failed_frames += 1
        self._update_out_of_frame_status(frame)

        if self.failure_count >= self.failure_threshold:
            logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
            self._build_failure_info("tracker_failed")
            return False, self.bbox

        # Use estimator prediction if available
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_only()
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position and len(estimated_position) >= 2 and self.prev_bbox:
                est_x, est_y = estimated_position[0], estimated_position[1]
                w, h = self.prev_bbox[2], self.prev_bbox[3]
                self.bbox = (int(est_x - w / 2), int(est_y - h / 2), w, h)
                self.set_center((int(est_x), int(est_y)))

        return True, self.bbox

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
