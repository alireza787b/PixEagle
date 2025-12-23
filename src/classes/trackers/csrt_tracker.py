# src/classes/trackers/csrt_tracker.py

"""
CSRTTracker Module - Production-Ready with Configurable Performance Modes
--------------------------------------------------------------------------

CSRT (Channel and Spatial Reliability Tracking) from OpenCV with optional
robustness enhancements and user-friendly performance modes.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: January 2025
- Author: Alireza Ghaderi

CSRT Algorithm Strengths:
--------------------------
- ✅ Rotation-invariant (in-plane and out-of-plane)
- ✅ Scale adaptation (handles zoom changes)
- ✅ Partial occlusion handling
- ✅ Perspective changes (drone movement)

Performance Modes:
------------------
1. **legacy** - Original CSRT behavior (15-20 FPS, most reliable startup)
2. **balanced** - Light enhancements (12-18 FPS, good trade-off)
3. **robust** - Full validation (10-15 FPS, maximum stability)

References:
-----------
- CSRT Paper: Lukezic et al., "Discriminative Correlation Filter with Channel and Spatial Reliability," CVPR 2017
"""

import logging
import time
import cv2
import numpy as np
from typing import Optional, Tuple
from collections import deque

from classes.parameters import Parameters
from classes.trackers.base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType

logger = logging.getLogger(__name__)

class CSRTTracker(BaseTracker):
    """
    CSRT Tracker with Configurable Performance Modes

    Modes:
    - legacy: Original behavior, no validation overhead
    - balanced: Light validation, startup grace period
    - robust: Full validation, EMA smoothing, strict checks

    Attributes:
    -----------
    - tracker (cv2.Tracker): OpenCV CSRT tracker instance
    - performance_mode (str): "legacy", "balanced", or "robust"
    - enable_validation (bool): Whether to validate bbox
    - enable_ema_smoothing (bool): Whether to smooth confidence
    - validation_start_frame (int): Frame to start validation
    - confidence_threshold (float): Minimum confidence to accept
    """

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        """
        Initializes CSRT tracker with configurable performance mode.

        Args:
            video_handler (Optional[object]): Video streaming handler
            detector (Optional[object]): Detector for appearance-based methods
            app_controller (Optional[object]): Main application controller
        """
        super().__init__(video_handler, detector, app_controller)

        # Set tracker name for CSRT
        self.tracker_name: str = "CSRT"

        # Reset external estimator if exists
        if self.position_estimator:
            self.position_estimator.reset()

        # Get performance mode from config
        csrt_config = getattr(Parameters, 'CSRT_Tracker', {})
        self.performance_mode = csrt_config.get('performance_mode', 'balanced')

        # Configure based on performance mode
        self._configure_performance_mode()

        # State tracking
        self.bbox = None
        self.prev_bbox = None
        self.confidence = 0.0
        self.raw_confidence_history = deque(maxlen=5)

        # Failure tracking
        self.failure_count = 0

        # Performance monitoring
        self.frame_count = 0
        self.successful_frames = 0
        self.failed_frames = 0
        self.fps_history = []

        logger.info(f"{self.tracker_name} initialized in '{self.performance_mode}' mode")

    def _configure_performance_mode(self):
        """Configure tracker based on performance mode."""
        if self.performance_mode == 'legacy':
            # Original CSRT behavior - no enhancements
            self.enable_validation = False
            self.enable_ema_smoothing = False
            self.confidence_threshold = Parameters.CONFIDENCE_THRESHOLD
            self.failure_threshold = 3
            self.validation_start_frame = 999999  # Never validate
            logger.info("CSRT Mode: LEGACY - Original behavior, maximum speed")

        elif self.performance_mode == 'balanced':
            # Light enhancements with startup grace period
            self.enable_validation = False  # No motion/scale validation (too strict)
            self.enable_ema_smoothing = True  # Smooth confidence only
            self.confidence_threshold = 0.5  # Slightly relaxed
            self.failure_threshold = 5
            self.validation_start_frame = 10  # Grace period
            self.confidence_ema_alpha = 0.7
            logger.info("CSRT Mode: BALANCED - Light enhancements, good trade-off")

        elif self.performance_mode == 'robust':
            # Full validation for maximum robustness
            self.enable_validation = True
            self.enable_ema_smoothing = True
            self.confidence_threshold = 0.4  # More tolerant than before
            self.failure_threshold = 5
            self.validation_start_frame = 5  # Earlier validation
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
        """
        Creates and returns a new CSRT tracker instance.

        Returns:
            cv2.Tracker: OpenCV CSRT tracker instance
        """
        return cv2.TrackerCSRT_create()

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Initializes the tracker with the provided bounding box.

        Args:
            frame (np.ndarray): The initial video frame
            bbox (Tuple[int, int, int, int]): Bounding box (x, y, width, height)
        """
        logger.info(f"Initializing {self.tracker_name} tracker with bbox: {bbox}")

        # Initialize CSRT tracker
        self.tracker.init(frame, bbox)

        # Set tracking started flag
        self.tracking_started = True

        # Initialize appearance models using the detector
        if self.detector:
            self.detector.initial_features = self.detector.extract_features(frame, bbox)
            self.detector.adaptive_features = self.detector.initial_features.copy()

        # Reset state
        self.bbox = bbox
        self.prev_bbox = bbox
        self.confidence = 1.0
        self.failure_count = 0
        self.frame_count = 0
        self.prev_center = None
        self.last_update_time = time.time()
        self.raw_confidence_history.clear()

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Updates the tracker with the current frame.

        Behavior depends on performance mode:
        - legacy: Original CSRT behavior
        - balanced: Confidence smoothing + grace period
        - robust: Full validation after grace period

        Args:
            frame (np.ndarray): Current video frame

        Returns:
            Tuple[bool, Tuple[int, int, int, int]]: (success, bbox)
        """
        if not self.tracking_started:
            return False, self.bbox

        start_time = time.time()
        dt = self.update_time()

        # Handle SmartTracker override
        if self.override_active:
            return self._handle_smart_tracker_override(frame, dt)

        # Run CSRT tracker
        success, detected_bbox = self.tracker.update(frame)

        if not success:
            logger.warning("Tracking update failed in CSRT algorithm.")
            return self._handle_failure(dt)

        # CRITICAL: Startup grace period - always accept result
        if self.frame_count < self.validation_start_frame:
            return self._accept_result_simple(frame, detected_bbox, dt, start_time)

        # After grace period - apply mode-specific logic
        if self.performance_mode == 'legacy':
            # Legacy mode - original CSRT behavior
            return self._update_legacy_mode(frame, detected_bbox, dt, start_time)

        elif self.performance_mode == 'balanced':
            # Balanced mode - confidence smoothing only
            return self._update_balanced_mode(frame, detected_bbox, dt, start_time)

        else:  # robust
            # Robust mode - full validation
            return self._update_robust_mode(frame, detected_bbox, dt, start_time)

    def _accept_result_simple(self, frame: np.ndarray, bbox: Tuple, dt: float, start_time: float) -> Tuple[bool, Tuple]:
        """Accept tracking result without validation (startup grace period)."""
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)

        # Update appearance model
        if self.detector:
            current_features = self.detector.extract_features(frame, self.bbox)
            learning_rate = getattr(self, 'appearance_learning_rate', 0.05)
            self.detector.adaptive_features = (
                (1 - learning_rate) * self.detector.adaptive_features +
                learning_rate * current_features
            )

        # Update estimator
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_and_update(np.array(self.center))
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)

        self.prev_bbox = self.bbox
        self.failure_count = 0
        self.successful_frames += 1
        self.frame_count += 1

        self._log_performance(start_time)
        return True, self.bbox

    def _update_legacy_mode(self, frame: np.ndarray, bbox: Tuple, dt: float, start_time: float) -> Tuple[bool, Tuple]:
        """Legacy mode - exact original CSRT behavior from commit f1a63aca."""
        success = True

        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)

        # Update appearance model
        if self.detector:
            current_features = self.detector.extract_features(frame, self.bbox)
            self.detector.adaptive_features = (
                (1 - Parameters.CSRT_APPEARANCE_LEARNING_RATE) * self.detector.adaptive_features +
                Parameters.CSRT_APPEARANCE_LEARNING_RATE * current_features
            )

        # Confidence checks
        self.compute_confidence(frame)
        total_confidence = self.get_confidence()

        if self.confidence < Parameters.CONFIDENCE_THRESHOLD:
            logger.warning("Tracking failed due to low confidence")
            success = False

        # Update estimator
        if success and self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_and_update(np.array(self.center))
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)

        return success, self.bbox

    def _update_balanced_mode(self, frame: np.ndarray, bbox: Tuple, dt: float, start_time: float) -> Tuple[bool, Tuple]:
        """Balanced mode - confidence smoothing only."""
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)

        # Update appearance model
        if self.detector:
            current_features = self.detector.extract_features(frame, self.bbox)
            learning_rate = getattr(self, 'appearance_learning_rate', 0.08)
            self.detector.adaptive_features = (
                (1 - learning_rate) * self.detector.adaptive_features +
                learning_rate * current_features
            )

        # Compute confidence
        self.compute_confidence(frame)

        # Apply EMA smoothing
        if self.enable_ema_smoothing:
            smoothed_confidence = self._smooth_confidence(self.confidence)
        else:
            smoothed_confidence = self.confidence

        # Check confidence
        if smoothed_confidence < self.confidence_threshold:
            self.failure_count += 1
            logger.debug(f"Low confidence ({self.failure_count}/{self.failure_threshold}): {smoothed_confidence:.2f}")

            if self.failure_count >= self.failure_threshold:
                logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
                return False, self.bbox
        else:
            self.failure_count = 0
            self.successful_frames += 1

        # Update estimator
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_and_update(np.array(self.center))
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)

        self.prev_bbox = self.bbox
        self.frame_count += 1

        self._log_performance(start_time)
        return True, self.bbox

    def _update_robust_mode(self, frame: np.ndarray, bbox: Tuple, dt: float, start_time: float) -> Tuple[bool, Tuple]:
        """Robust mode - full validation."""
        # Get estimator prediction
        estimator_prediction = self._get_estimator_prediction() if self.estimator_enabled else None

        # Validate motion and scale
        if self.enable_validation:
            motion_valid = self._validate_bbox_motion(bbox, estimator_prediction)
            scale_valid = self._validate_bbox_scale(bbox)
        else:
            motion_valid = True
            scale_valid = True

        # Compute confidence
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
        self.compute_confidence(frame)

        # Smooth confidence
        smoothed_confidence = self._smooth_confidence(self.confidence)

        # Decision logic
        if smoothed_confidence > self.confidence_threshold and motion_valid and scale_valid:
            # Accept result
            self.normalize_bbox()
            self.center_history.append(self.center)

            # Update appearance model
            if self.detector:
                current_features = self.detector.extract_features(frame, self.bbox)
                self.detector.adaptive_features = (
                    (1 - self.appearance_learning_rate) * self.detector.adaptive_features +
                    self.appearance_learning_rate * current_features
                )

            # Update estimator
            if self.estimator_enabled and self.position_estimator:
                self.position_estimator.set_dt(dt)
                self.position_estimator.predict_and_update(np.array(self.center))
                estimated_position = self.position_estimator.get_estimate()
                self.estimated_position_history.append(estimated_position)

            self.prev_bbox = self.bbox
            self.failure_count = 0
            self.successful_frames += 1
            self.frame_count += 1

            self._log_performance(start_time)
            logger.debug(f"CSRT accepted: conf={smoothed_confidence:.2f}, motion={motion_valid}, scale={scale_valid}")
            return True, self.bbox
        else:
            # Low confidence
            self.failure_count += 1
            self.failed_frames += 1
            self.frame_count += 1

            logger.debug(f"Low confidence ({self.failure_count}/{self.failure_threshold}): "
                        f"conf={smoothed_confidence:.2f}, motion={motion_valid}, scale={scale_valid}")

            if self.failure_count >= self.failure_threshold:
                logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
                return False, self.bbox

            return True, self.bbox  # Continue tracking (using last known bbox)

    def _handle_smart_tracker_override(self, frame: np.ndarray, dt: float) -> Tuple[bool, Tuple]:
        """Handle SmartTracker override mode."""
        smart_tracker = self.app_controller.smart_tracker
        if smart_tracker and smart_tracker.selected_bbox:
            self.prev_center = self.center
            x1, y1, x2, y2 = smart_tracker.selected_bbox
            w, h = x2 - x1, y2 - y1
            self.bbox = (x1, y1, w, h)
            self.set_center(((x1 + x2) // 2, (y1 + y2) // 2))
            self.normalize_bbox()
            self.center_history.append(self.center)
            self.confidence = 1.0

            # Update estimator
            if self.estimator_enabled and self.position_estimator:
                self.position_estimator.set_dt(dt)
                self.position_estimator.predict_and_update(np.array(self.center))
                estimated_position = self.position_estimator.get_estimate()
                self.estimated_position_history.append(estimated_position)

            self.failure_count = 0
            return True, self.bbox
        else:
            logger.warning("Override active but SmartTracker has no selected bbox")
            return False, self.bbox

    def _handle_failure(self, dt: float) -> Tuple[bool, Tuple]:
        """Handle tracking failure."""
        self.failure_count += 1
        self.failed_frames += 1

        if self.failure_count >= self.failure_threshold:
            logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
            return False, self.bbox

        # Use estimator prediction if available
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_only()
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position and len(estimated_position) >= 2 and self.prev_bbox:
                est_x, est_y = estimated_position[0], estimated_position[1]
                w, h = self.prev_bbox[2], self.prev_bbox[3]
                self.bbox = (int(est_x - w/2), int(est_y - h/2), w, h)
                self.set_center((int(est_x), int(est_y)))

        return True, self.bbox  # Continue tracking with prediction

    def _get_estimator_prediction(self) -> Optional[Tuple[float, float]]:
        """Get position prediction from external estimator."""
        if self.estimator_enabled and self.position_estimator:
            dt = self.update_time()
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_only()
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position and len(estimated_position) >= 2:
                return (estimated_position[0], estimated_position[1])
        return None

    def _validate_bbox_motion(self, bbox: Tuple, estimator_prediction: Optional[Tuple]) -> bool:
        """Validate bbox motion against estimator prediction."""
        if not self.video_handler or not estimator_prediction or self.frame_count < 15:
            return True  # Skip validation if not enough history

        csrt_cx = bbox[0] + bbox[2]/2
        csrt_cy = bbox[1] + bbox[3]/2

        est_x, est_y = estimator_prediction
        distance = np.sqrt((csrt_cx - est_x)**2 + (csrt_cy - est_y)**2)

        frame_diag = np.hypot(self.video_handler.width, self.video_handler.height)
        normalized_distance = distance / frame_diag

        is_valid = normalized_distance < self.motion_consistency_threshold

        if not is_valid:
            logger.debug(f"Motion validation failed: {normalized_distance:.3f} > {self.motion_consistency_threshold}")

        return is_valid

    def _validate_bbox_scale(self, bbox: Tuple) -> bool:
        """Validate bbox scale change."""
        if not self.prev_bbox:
            return True

        scale_w = bbox[2] / (self.prev_bbox[2] + 1e-6)
        scale_h = bbox[3] / (self.prev_bbox[3] + 1e-6)
        scale_change = max(abs(scale_w - 1.0), abs(scale_h - 1.0))

        is_valid = scale_change < self.max_scale_change

        if not is_valid:
            logger.debug(f"Scale validation failed: {scale_change:.3f} > {self.max_scale_change}")

        return is_valid

    def _smooth_confidence(self, raw_confidence: float) -> float:
        """Apply EMA smoothing to confidence."""
        self.raw_confidence_history.append(raw_confidence)

        if len(self.raw_confidence_history) == 1:
            smoothed = raw_confidence
        else:
            smoothed = (self.confidence_ema_alpha * raw_confidence +
                       (1 - self.confidence_ema_alpha) * self.confidence)

        self.confidence = smoothed
        return smoothed

    def _log_performance(self, start_time: float):
        """Log performance metrics."""
        elapsed = time.time() - start_time
        fps = 1.0 / (elapsed + 1e-6)
        self.fps_history.append(fps)

        if self.frame_count % 30 == 0 and self.frame_count > 0:
            avg_fps = np.mean(self.fps_history[-30:])
            success_rate = 100 * self.successful_frames / (self.frame_count + 1e-6)
            logger.info(f"{self.tracker_name} ({self.performance_mode}): FPS={avg_fps:.1f}, conf={self.confidence:.2f}, success={success_rate:.1f}%")

    def update_estimator_without_measurement(self) -> None:
        """Updates the position estimator when no measurement is available."""
        dt = self.update_time()
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_only()
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)

    def get_estimated_position(self) -> Optional[Tuple[float, float]]:
        """Gets the current estimated position from the estimator."""
        if self.estimator_enabled and self.position_estimator:
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position and len(estimated_position) >= 2:
                return (estimated_position[0], estimated_position[1])
        return None

    def get_output(self) -> TrackerOutput:
        """Returns CSRT-specific tracker output."""
        # Get velocity from estimator if available
        velocity = None
        if (self.estimator_enabled and self.position_estimator and
            self.tracking_started and len(self.center_history) > 2):
            estimated_state = self.position_estimator.get_estimate()
            if estimated_state and len(estimated_state) >= 4:
                vel_x, vel_y = estimated_state[2], estimated_state[3]
                velocity_magnitude = (vel_x ** 2 + vel_y ** 2) ** 0.5
                if velocity_magnitude > 0.001:
                    velocity = (vel_x, vel_y)

        # Determine data type
        has_bbox = self.bbox is not None or self.normalized_bbox is not None
        has_velocity = velocity is not None

        if has_velocity:
            data_type = TrackerDataType.VELOCITY_AWARE
        elif has_bbox:
            data_type = TrackerDataType.BBOX_CONFIDENCE
        else:
            data_type = TrackerDataType.POSITION_2D

        return TrackerOutput(
            data_type=data_type,
            timestamp=time.time(),
            tracking_active=self.tracking_started,
            tracker_id=f"CSRT_{id(self)}",
            position_2d=self.normalized_center,
            bbox=self.bbox,
            normalized_bbox=self.normalized_bbox,
            confidence=self.confidence,
            velocity=velocity,
            quality_metrics={
                'motion_consistency': self.compute_motion_confidence() if self.prev_center else 1.0,
                'appearance_confidence': getattr(self, 'appearance_confidence', 1.0),
                'failure_count': self.failure_count,
                'success_rate': self.successful_frames / (self.frame_count + 1e-6) if self.frame_count > 0 else 1.0
            },
            raw_data={
                'performance_mode': self.performance_mode,
                'frame_count': self.frame_count,
                'successful_frames': self.successful_frames,
                'failed_frames': self.failed_frames,
                'avg_fps': round(np.mean(self.fps_history[-30:]), 1) if len(self.fps_history) >= 30 else 0.0
            },
            metadata={
                'tracker_class': self.__class__.__name__,
                'tracker_algorithm': 'CSRT',
                'performance_mode': self.performance_mode,
                'opencv_version': cv2.__version__
            }
        )

    def get_capabilities(self) -> dict:
        """Returns CSRT-specific capabilities."""
        base_capabilities = super().get_capabilities()
        base_capabilities.update({
            'tracker_algorithm': 'CSRT',
            'supports_rotation': True,
            'supports_scale_change': True,
            'supports_occlusion': True,
            'accuracy_rating': 'very_high',
            'speed_rating': 'medium',
            'opencv_tracker': True,
            'performance_mode': self.performance_mode
        })
        return base_capabilities
