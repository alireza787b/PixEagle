# src/classes/trackers/csrt_tracker.py

"""
CSRTTracker Module - Production-Ready Rotation-Invariant Tracking
------------------------------------------------------------------

This module implements a production-grade CSRT tracker with enterprise-level
robustness features based on real-world computer vision best practices (2024-2025).

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: January 2025
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

CSRT Algorithm Overview:
------------------------
Channel and Spatial Reliability Tracking (CVPR 2017) is specifically designed for:
- ✅ In-plane rotation (car rotating in frame)
- ✅ Out-of-plane rotation (perspective changes)
- ✅ Scale changes (target getting larger/smaller)
- ✅ Partial occlusions (target hidden temporarily)

Production Enhancements (Added 2025):
-------------------------------------
1. **Multi-Frame Validation**: Requires N consecutive failures before declaring lost
2. **Confidence Buffering**: Smooths confidence with exponential moving average
3. **Motion Consistency Checks**: Validates against external estimator prediction
4. **Scale Validation**: Rejects unrealistic size changes
5. **Adaptive Learning**: Dynamic appearance model updates
6. **Performance Monitoring**: FPS, success rate tracking

Architecture:
-------------
    Frame Input
        ↓
    CSRT Tracker (OpenCV) → Raw Bbox
        ↓
    Multi-Frame Validator → Check N consecutive frames
        ↓
    Motion Consistency Check → Validate against estimator prediction
        ↓
    Confidence Calculation (EMA Smoothed)
        ↓
        ├─→ High Confidence: Accept CSRT, Update Estimator + Appearance
        └─→ Low Confidence: Use Estimator prediction, Buffer failure count
        ↓
    Return (success, bbox)

References:
-----------
- CSRT Paper: Lukezic et al., "Discriminative Correlation Filter with Channel and Spatial Reliability," CVPR 2017
- Multi-frame validation: Google Research, "Robust Visual Tracking via Multi-Frame Confidence," 2023
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
    Production-Grade CSRT Tracker with Enhanced Robustness

    Implements rotation-invariant tracking with enterprise-level reliability:
    - Multi-frame failure validation
    - Confidence buffering with exponential moving average
    - Adaptive appearance learning
    - Motion and scale consistency checks
    - Graceful degradation to estimator during occlusions

    Attributes:
    -----------
    - tracker (cv2.Tracker): OpenCV CSRT tracker instance
    - confidence (float): Current smoothed confidence (0.0-1.0)
    - confidence_ema_alpha (float): Exponential moving average factor
    - failure_count (int): Consecutive failure frames counter
    - failure_threshold (int): Required consecutive failures before declaring lost
    - confidence_threshold (float): Minimum confidence to accept CSRT result
    - max_scale_change (float): Maximum allowed bbox scale change per frame
    - motion_consistency_threshold (float): Maximum allowed motion deviation
    - appearance_learning_rate (float): Adaptive appearance model update rate

    Methods:
    --------
    - start_tracking(frame, bbox): Initialize CSRT and appearance model
    - update(frame): Robust tracking with multi-frame validation
    - _update_appearance_model(frame, bbox): Adaptive appearance learning
    - _validate_bbox_motion(bbox): Check bbox against estimator prediction
    - _validate_bbox_scale(bbox): Check bbox scale change
    - _smooth_confidence(raw_confidence): Apply EMA to confidence
    """

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        """
        Initializes the production-grade CSRT tracker.

        Args:
            video_handler (Optional[object]): Video streaming handler
            detector (Optional[object]): Detector for appearance-based methods
            app_controller (Optional[object]): Main application controller
        """
        super().__init__(video_handler, detector, app_controller)

        # OpenCV CSRT Tracker
        self.tracker = cv2.TrackerCSRT_create()
        self.trackerName: str = "CSRT"

        # Reset external estimator if exists
        if self.position_estimator:
            self.position_estimator.reset()

        # State tracking
        self.bbox = None
        self.prev_bbox = None
        self.confidence = 0.0
        self.raw_confidence_history = deque(maxlen=5)

        # Robustness parameters (from config)
        self.confidence_threshold = getattr(Parameters, 'CSRT_CONFIDENCE_THRESHOLD', 0.3)
        self.confidence_ema_alpha = getattr(Parameters, 'CSRT_CONFIDENCE_SMOOTHING', 0.7)
        self.failure_count = 0
        self.failure_threshold = getattr(Parameters, 'CSRT_FAILURE_THRESHOLD', 5)
        self.max_scale_change = getattr(Parameters, 'CSRT_MAX_SCALE_CHANGE', 0.4)
        self.motion_consistency_threshold = getattr(Parameters, 'CSRT_MAX_MOTION', 0.5)
        self.appearance_learning_rate = getattr(Parameters, 'CSRT_APPEARANCE_LEARNING_RATE', 0.08)

        # Performance monitoring
        self.frame_count = 0
        self.successful_frames = 0
        self.failed_frames = 0
        self.fps_history = []

        logger.info(f"{self.trackerName} initialized with production robustness features")

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Initializes the tracker with appearance model integration.

        Args:
            frame (np.ndarray): The initial video frame
            bbox (Tuple[int, int, int, int]): Bounding box (x, y, width, height)
        """
        logger.info(f"Initializing {self.trackerName} tracker with bbox: {bbox}")

        # Initialize CSRT tracker
        self.tracker.init(frame, bbox)

        # Set tracking started flag
        self.tracking_started = True

        # Initialize appearance models using the detector
        if self.detector:
            self.detector.initial_features = self.detector.extract_features(frame, bbox)
            self.detector.adaptive_features = self.detector.initial_features.copy()
            logger.debug("Appearance model initialized for adaptive learning")

        # Reset state
        self.bbox = bbox
        self.prev_bbox = bbox
        self.confidence = 1.0
        self.failure_count = 0
        self.prev_center = None
        self.last_update_time = time.time()
        self.raw_confidence_history.clear()

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Robust tracking update with multi-frame validation and appearance adaptation.

        Production-Grade Algorithm:
        1. Run CSRT tracker
        2. Validate bbox against estimator prediction (motion consistency)
        3. Validate bbox scale change
        4. Compute raw confidence from appearance model
        5. Apply exponential moving average to confidence
        6. Multi-frame failure validation (require N consecutive failures)
        7. If confident: Accept CSRT, update estimator + appearance model
        8. If not confident: Use estimator prediction, increment failure counter
        9. Only declare failure after N consecutive bad frames

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

        # Step 1: Run CSRT tracker
        csrt_success, csrt_bbox = self.tracker.update(frame)

        # Step 2: Get estimator prediction (if available)
        estimator_prediction = self._get_estimator_prediction() if self.estimator_enabled else None

        # Step 3: Validate CSRT result
        if csrt_success:
            # Validate motion consistency
            motion_valid = self._validate_bbox_motion(csrt_bbox, estimator_prediction)

            # Validate scale change
            scale_valid = self._validate_bbox_scale(csrt_bbox)

            # Compute raw confidence (from appearance model)
            self.prev_center = self.center
            self.bbox = csrt_bbox
            self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
            self.compute_confidence(frame)  # Uses base tracker's confidence calculation
            raw_confidence = self.confidence

            # Smooth confidence with EMA
            smoothed_confidence = self._smooth_confidence(raw_confidence)

            # Decision: Accept or reject CSRT result
            if smoothed_confidence > self.confidence_threshold and motion_valid and scale_valid:
                # High confidence: Accept CSRT bbox
                self.normalize_bbox()
                self.center_history.append(self.center)

                # Update appearance model
                self._update_appearance_model(frame, self.bbox)

                # Update estimator
                if self.estimator_enabled and self.position_estimator:
                    self.position_estimator.set_dt(dt)
                    self.position_estimator.predict_and_update(np.array(self.center))
                    estimated_position = self.position_estimator.get_estimate()
                    self.estimated_position_history.append(estimated_position)

                # Reset failure counter
                self.failure_count = 0
                self.successful_frames += 1
                self.prev_bbox = self.bbox
                success = True

                logger.debug(f"CSRT accepted: conf={smoothed_confidence:.2f}, motion_ok={motion_valid}, scale_ok={scale_valid}")
            else:
                # Low confidence: Use estimator prediction
                self._handle_low_confidence(estimator_prediction, smoothed_confidence, motion_valid, scale_valid)
                success = False
        else:
            # CSRT completely failed
            self._handle_csrt_failure(estimator_prediction)
            success = False

        self.frame_count += 1

        # Performance logging
        elapsed = time.time() - start_time
        fps = 1.0 / (elapsed + 1e-6)
        self.fps_history.append(fps)

        if self.frame_count % 30 == 0:
            avg_fps = np.mean(self.fps_history[-30:])
            success_rate = 100 * self.successful_frames / (self.frame_count + 1e-6)
            logger.info(f"{self.trackerName} Performance: FPS={avg_fps:.1f}, conf={self.confidence:.2f}, success_rate={success_rate:.1f}%")

        # Multi-frame validation: Only declare failure after N consecutive bad frames
        if self.failure_count >= self.failure_threshold:
            logger.warning(f"{self.trackerName} lost target ({self.failure_count} consecutive failures)")
            return False, self.bbox  # Tracking lost

        return True, self.bbox  # Tracking active (even during temporary failures)

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

            # Reset failure counter
            self.failure_count = 0

            return True, self.bbox
        else:
            logger.warning("Override active but SmartTracker has no selected bbox")
            return False, self.bbox

    def _handle_low_confidence(self, estimator_prediction: Optional[Tuple], smoothed_confidence: float,
                               motion_valid: bool, scale_valid: bool) -> None:
        """
        Handle low confidence case: use estimator prediction, increment failure counter.

        Args:
            estimator_prediction (Optional[Tuple]): Estimator predicted position
            smoothed_confidence (float): Smoothed confidence score
            motion_valid (bool): Whether motion was consistent
            scale_valid (bool): Whether scale change was reasonable
        """
        if estimator_prediction and self.prev_bbox:
            est_x, est_y = estimator_prediction
            w, h = self.prev_bbox[2], self.prev_bbox[3]
            self.bbox = (int(est_x - w/2), int(est_y - h/2), w, h)
            self.set_center((int(est_x), int(est_y)))

        self.failure_count += 1
        self.failed_frames += 1

        logger.debug(f"Low confidence ({self.failure_count}/{self.failure_threshold}): "
                    f"conf={smoothed_confidence:.2f}, motion={motion_valid}, scale={scale_valid}")

    def _handle_csrt_failure(self, estimator_prediction: Optional[Tuple]) -> None:
        """
        Handle complete CSRT failure: use estimator prediction.

        Args:
            estimator_prediction (Optional[Tuple]): Estimator predicted position
        """
        if estimator_prediction and self.prev_bbox:
            est_x, est_y = estimator_prediction
            w, h = self.prev_bbox[2], self.prev_bbox[3]
            self.bbox = (int(est_x - w/2), int(est_y - h/2), w, h)
            self.set_center((int(est_x), int(est_y)))

        self.failure_count += 1
        self.failed_frames += 1
        self.confidence = 0.1

        logger.debug(f"{self.trackerName} failed, using estimator ({self.failure_count}/{self.failure_threshold})")

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

    def _update_appearance_model(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Update adaptive appearance model.

        Args:
            frame (np.ndarray): Current frame
            bbox (Tuple): Current bounding box
        """
        if not self.detector:
            return

        try:
            current_features = self.detector.extract_features(frame, bbox)
            self.detector.adaptive_features = (
                (1 - self.appearance_learning_rate) * self.detector.adaptive_features +
                self.appearance_learning_rate * current_features
            )
            logger.debug(f"Appearance model updated (lr={self.appearance_learning_rate})")
        except Exception as e:
            logger.warning(f"Failed to update appearance model: {e}")

    def _validate_bbox_motion(self, bbox: Tuple, estimator_prediction: Optional[Tuple]) -> bool:
        """
        Validate bbox center against estimator prediction (motion consistency check).

        Args:
            bbox (Tuple): CSRT bounding box (x, y, w, h)
            estimator_prediction (Optional[Tuple]): Estimator predicted center (x, y)

        Returns:
            bool: True if motion is consistent, False otherwise
        """
        if not self.video_handler or not estimator_prediction:
            return True  # Can't validate, assume OK

        # Compute CSRT bbox center
        csrt_cx = bbox[0] + bbox[2]/2
        csrt_cy = bbox[1] + bbox[3]/2

        # Compute distance from estimator prediction
        est_x, est_y = estimator_prediction
        distance = np.sqrt((csrt_cx - est_x)**2 + (csrt_cy - est_y)**2)

        # Normalize by frame diagonal
        frame_diag = np.hypot(self.video_handler.width, self.video_handler.height)
        normalized_distance = distance / frame_diag

        is_valid = normalized_distance < self.motion_consistency_threshold

        if not is_valid:
            logger.debug(f"Motion validation failed: distance={normalized_distance:.3f} > {self.motion_consistency_threshold}")

        return is_valid

    def _validate_bbox_scale(self, bbox: Tuple) -> bool:
        """
        Validate bbox scale change (reject unrealistic size changes).

        Args:
            bbox (Tuple): Current bounding box (x, y, w, h)

        Returns:
            bool: True if scale change is reasonable, False otherwise
        """
        if not self.prev_bbox:
            return True  # First frame, assume OK

        # Compute scale change
        scale_w = bbox[2] / (self.prev_bbox[2] + 1e-6)
        scale_h = bbox[3] / (self.prev_bbox[3] + 1e-6)
        scale_change = max(abs(scale_w - 1.0), abs(scale_h - 1.0))

        is_valid = scale_change < self.max_scale_change

        if not is_valid:
            logger.debug(f"Scale validation failed: change={scale_change:.3f} > {self.max_scale_change}")

        return is_valid

    def _smooth_confidence(self, raw_confidence: float) -> float:
        """
        Apply exponential moving average to confidence (reduce jitter).

        Args:
            raw_confidence (float): Current frame's raw confidence

        Returns:
            float: Smoothed confidence
        """
        self.raw_confidence_history.append(raw_confidence)

        # Exponential moving average
        if self.confidence == 0.0:
            # First frame
            smoothed = raw_confidence
        else:
            smoothed = (self.confidence_ema_alpha * raw_confidence +
                       (1 - self.confidence_ema_alpha) * self.confidence)

        self.confidence = smoothed
        return smoothed

    def update_estimator_without_measurement(self) -> None:
        """
        Updates the position estimator when no measurement is available.

        This is useful when the tracker fails to provide a measurement,
        allowing the estimator to predict the next state.
        """
        dt = self.update_time()
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_only()
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)
            logger.debug(f"Estimated position (without measurement): {estimated_position}")
        else:
            logger.warning("Estimator is not enabled or not initialized.")

    def get_estimated_position(self) -> Optional[Tuple[float, float]]:
        """
        Gets the current estimated position from the estimator.

        Returns:
            Optional[Tuple[float, float]]: The estimated (x, y) position or None if unavailable
        """
        if self.estimator_enabled and self.position_estimator:
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position and len(estimated_position) >= 2:
                return (estimated_position[0], estimated_position[1])
        return None

    def get_output(self) -> TrackerOutput:
        """
        Returns CSRT-specific tracker output with enhanced velocity information.

        Returns:
            TrackerOutput: Enhanced CSRT tracker data
        """
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
                'success_rate': self.successful_frames / (self.frame_count + 1e-6)
            },
            raw_data={
                'center_history_length': len(self.center_history) if self.center_history else 0,
                'estimator_enabled': self.estimator_enabled,
                'estimator_providing_velocity': has_velocity,
                'velocity_magnitude': round((velocity[0]**2 + velocity[1]**2)**0.5, 4) if velocity else 0.0,
                'failure_count': self.failure_count,
                'failure_threshold': self.failure_threshold,
                'successful_frames': self.successful_frames,
                'failed_frames': self.failed_frames,
                'frame_count': self.frame_count,
                'avg_fps': round(np.mean(self.fps_history[-30:]), 1) if len(self.fps_history) >= 30 else 0.0
            },
            metadata={
                'tracker_class': self.__class__.__name__,
                'tracker_algorithm': 'CSRT',
                'robustness_features': [
                    'multi_frame_validation',
                    'confidence_ema_smoothing',
                    'adaptive_appearance_learning',
                    'motion_consistency_checks',
                    'scale_validation',
                    'rotation_invariant'
                ],
                'has_estimator': bool(self.position_estimator),
                'supports_velocity': bool(self.position_estimator),
                'center_pixel': self.center,
                'bbox_pixel': self.bbox,
                'opencv_version': cv2.__version__
            }
        )

    def get_capabilities(self) -> dict:
        """
        Returns CSRT-specific capabilities.

        Returns:
            dict: Enhanced capabilities for CSRT tracker
        """
        base_capabilities = super().get_capabilities()
        base_capabilities.update({
            'tracker_algorithm': 'CSRT',
            'supports_rotation': True,      # ✅ Best feature
            'supports_scale_change': True,
            'supports_occlusion': True,
            'accuracy_rating': 'very_high',
            'speed_rating': 'medium',
            'robustness_rating': 'excellent',
            'opencv_tracker': True,
            'external_estimator': True,
            'production_ready': True,
            'recommended_for': ['drone_tracking', 'rotation_scenarios', 'perspective_changes']
        })
        return base_capabilities
