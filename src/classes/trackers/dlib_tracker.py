# src/classes/trackers/dlib_tracker.py

"""
DlibTracker Module - Production-Ready Correlation Filter Tracker
-----------------------------------------------------------------

dlib Correlation Filter Tracker implementation with configurable performance modes
and full PixEagle schema integration.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: January 2025
- Author: Alireza Ghaderi

dlib Algorithm Strengths:
--------------------------
- ✅ Fast correlation filter tracking (25-30 FPS typical)
- ✅ Scale adaptation (handles zoom changes)
- ✅ PSR-based confidence scoring
- ✅ Good out-of-the-box performance
- ✅ Low computational overhead

Performance Modes:
------------------
1. **fast** - Minimal overhead (25-30 FPS, best for high-speed scenarios)
2. **balanced** - Light validation (18-25 FPS, recommended default)
3. **robust** - Full validation (12-18 FPS, maximum stability)

References:
-----------
- dlib Library: http://dlib.net/
- Algorithm: Danelljan et al., "Accurate Scale Estimation for Robust Visual Tracking," BMVC 2014
- PSR Metric: Bolme et al., "Visual Object Tracking using Adaptive Correlation Filters," CVPR 2010
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
    """
    dlib Correlation Filter Tracker with Configurable Performance Modes

    Modes:
    - fast: Minimal validation, maximum speed (25-30 FPS)
    - balanced: PSR confidence monitoring with grace period (18-25 FPS)
    - robust: Full validation with motion/scale checks (12-18 FPS)

    Attributes:
    -----------
    - tracker (dlib.correlation_tracker): dlib tracker instance
    - performance_mode (str): "fast", "balanced", or "robust"
    - psr_confidence_threshold (float): Minimum PSR for reliable tracking
    - failure_threshold (int): Consecutive failures before declaring lost
    - confidence_smoothing_alpha (float): EMA alpha for confidence smoothing
    """

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        """
        Initializes dlib tracker with configurable performance mode.

        Args:
            video_handler (Optional[object]): Video streaming handler
            detector (Optional[object]): Detector for appearance-based methods
            app_controller (Optional[object]): Main application controller
        """
        if not DLIB_AVAILABLE:
            raise ImportError("dlib library is required but not installed. Install with: pip install dlib")

        super().__init__(video_handler, detector, app_controller)

        # Set tracker name for dlib
        self.trackerName: str = "dlib"

        # Reset external estimator if exists
        if self.position_estimator:
            self.position_estimator.reset()

        # Get performance mode from config
        dlib_config = getattr(Parameters, 'DLIB_Tracker', {})
        self.performance_mode = dlib_config.get('performance_mode', 'balanced')

        # Configure based on performance mode
        self._configure_performance_mode()

        # State tracking
        self.bbox = None
        self.prev_bbox = None
        self.confidence = 0.0
        self.raw_confidence_history = deque(maxlen=5)
        self.psr_history = deque(maxlen=10)  # Track PSR values for debugging

        # Failure tracking
        self.failure_count = 0

        # Performance monitoring
        self.frame_count = 0
        self.successful_frames = 0
        self.failed_frames = 0
        self.fps_history = []

        # === Enhanced Features (Student's Research Improvements) ===

        # Adaptive PSR system
        adaptive_config = dlib_config.get('adaptive', {})
        self.adaptive_enabled = adaptive_config.get('enable', True)
        self.psr_dynamic_scaling = adaptive_config.get('psr_dynamic_scaling', True)
        self.adapt_rate = adaptive_config.get('adapt_rate', 0.15)
        self.psr_margin = adaptive_config.get('psr_margin', 1.5)
        self.adaptive_psr_threshold = self.psr_confidence_threshold  # Initialize with static value

        # Appearance model enhancements
        appearance_config = dlib_config.get('appearance', {})
        self.use_adaptive_learning = appearance_config.get('use_adaptive_learning', True)
        self.adaptive_learning_bounds = appearance_config.get('adaptive_learning_bounds', [0.05, 0.15])
        self.freeze_on_low_confidence = appearance_config.get('freeze_on_low_confidence', True)
        self.reference_update_interval = appearance_config.get('reference_update_interval', 30)
        self.reference_template = None  # Store initial template
        self.frames_since_reference_update = 0

        # Motion model enhancements
        motion_config = dlib_config.get('motion', {})
        self.velocity_limit = motion_config.get('velocity_limit', 25.0)
        self.stabilization_alpha = motion_config.get('stabilization_alpha', 0.3)
        self.smoothed_bbox = None  # For motion stabilization

        # Validation enhancements
        validation_config = dlib_config.get('validation', {})
        self.reinit_on_loss = validation_config.get('reinit_on_loss', True)
        self.cooldown_after_reinit = validation_config.get('cooldown_after_reinit', 5)
        self.reinit_cooldown_counter = 0

        # Debug features
        debug_config = dlib_config.get('debug', {})
        self.enable_visual_feedback = debug_config.get('enable_visual_feedback', True)
        self.show_motion_vectors = debug_config.get('show_motion_vectors', False)

        logger.info(f"{self.trackerName} initialized in '{self.performance_mode}' mode")
        if self.adaptive_enabled:
            logger.info(f"  - Adaptive PSR system: ENABLED")
        if self.use_adaptive_learning:
            logger.info(f"  - Adaptive learning rate: {self.adaptive_learning_bounds}")
        if self.freeze_on_low_confidence:
            logger.info(f"  - Template freeze on low confidence: ENABLED")

    def _configure_performance_mode(self):
        """Configure tracker based on performance mode."""
        dlib_config = getattr(Parameters, 'DLIB_Tracker', {})

        if self.performance_mode == 'fast':
            # Fast mode - minimal overhead, maximum speed
            self.enable_validation = False
            self.enable_ema_smoothing = False
            self.psr_confidence_threshold = dlib_config.get('psr_confidence_threshold', 5.0)
            self.failure_threshold = dlib_config.get('failure_threshold', 3)
            self.validation_start_frame = 999999  # Never validate
            self.psr_high_confidence = dlib_config.get('psr_high_confidence', 20.0)
            self.psr_low_confidence = dlib_config.get('psr_low_confidence', 3.0)
            logger.info("dlib Mode: FAST - Minimal validation, maximum speed (25-30 FPS)")

        elif self.performance_mode == 'balanced':
            # Balanced mode - PSR monitoring with grace period
            self.enable_validation = False  # No motion/scale validation
            self.enable_ema_smoothing = True  # Smooth confidence
            self.psr_confidence_threshold = dlib_config.get('psr_confidence_threshold', 7.0)
            self.failure_threshold = dlib_config.get('failure_threshold', 5)
            self.validation_start_frame = dlib_config.get('validation_start_frame', 10)
            self.confidence_smoothing_alpha = dlib_config.get('confidence_smoothing_alpha', 0.7)
            self.psr_high_confidence = dlib_config.get('psr_high_confidence', 20.0)
            self.psr_low_confidence = dlib_config.get('psr_low_confidence', 5.0)
            logger.info("dlib Mode: BALANCED - PSR monitoring with grace period (18-25 FPS)")

        elif self.performance_mode == 'robust':
            # Robust mode - full validation
            self.enable_validation = True
            self.enable_ema_smoothing = True
            self.psr_confidence_threshold = dlib_config.get('psr_confidence_threshold', 7.0)
            self.failure_threshold = dlib_config.get('failure_threshold', 5)
            self.validation_start_frame = dlib_config.get('validation_start_frame', 5)
            self.confidence_smoothing_alpha = dlib_config.get('confidence_smoothing_alpha', 0.7)
            self.max_scale_change = dlib_config.get('max_scale_change_per_frame', 0.5)
            self.motion_consistency_threshold = dlib_config.get('max_motion_per_frame', 0.6)
            self.appearance_learning_rate = dlib_config.get('appearance_learning_rate', 0.08)
            self.psr_high_confidence = dlib_config.get('psr_high_confidence', 20.0)
            self.psr_low_confidence = dlib_config.get('psr_low_confidence', 5.0)
            logger.info("dlib Mode: ROBUST - Full validation, maximum stability (12-18 FPS)")

        else:
            logger.warning(f"Unknown performance mode '{self.performance_mode}', using 'balanced'")
            self.performance_mode = 'balanced'
            self._configure_performance_mode()

    def _create_tracker(self):
        """
        Creates and returns a new dlib correlation tracker instance.

        Returns:
            dlib.correlation_tracker: dlib tracker instance
        """
        return dlib.correlation_tracker()

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Initializes the tracker with the provided bounding box.

        Args:
            frame (np.ndarray): The initial video frame
            bbox (Tuple[int, int, int, int]): Bounding box (x, y, width, height)
        """
        logger.info(f"Initializing {self.trackerName} tracker with bbox: {bbox}")

        # Convert bbox to dlib.rectangle format (left, top, right, bottom)
        x, y, w, h = bbox
        dlib_rect = dlib.rectangle(int(x), int(y), int(x + w), int(y + h))

        # Initialize dlib tracker
        self.tracker.start_track(frame, dlib_rect)

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
        self.psr_history.clear()

        # Enhanced features reset
        self.reference_template = self.detector.initial_features.copy() if self.detector else None
        self.frames_since_reference_update = 0
        self.smoothed_bbox = bbox
        self.adaptive_psr_threshold = self.psr_confidence_threshold
        self.reinit_cooldown_counter = 0

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Updates the tracker with the current frame.

        Behavior depends on performance mode:
        - fast: No validation, direct PSR acceptance
        - balanced: PSR confidence monitoring with grace period
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

        # Run dlib tracker update
        psr = self.tracker.update(frame)

        # Get updated position
        pos = self.tracker.get_position()
        detected_bbox = (
            int(pos.left()),
            int(pos.top()),
            int(pos.width()),
            int(pos.height())
        )

        # Store PSR for debugging
        self.psr_history.append(psr)

        # Update adaptive PSR threshold based on recent history
        self._update_adaptive_psr_threshold(psr)

        # Convert PSR to normalized confidence (0.0-1.0)
        raw_confidence = self._psr_to_confidence(psr)

        # Apply motion stabilization to reduce jitter
        detected_bbox = self._apply_motion_stabilization(detected_bbox)

        # Validate velocity if enabled
        velocity_valid = self._validate_velocity(detected_bbox)
        if not velocity_valid and self.frame_count >= self.validation_start_frame:
            logger.debug(f"Velocity validation failed - using previous bbox")
            detected_bbox = self.bbox  # Use previous bbox if velocity is unrealistic

        # Decrement reinit cooldown counter if active
        if self.reinit_cooldown_counter > 0:
            self.reinit_cooldown_counter -= 1

        # CRITICAL: Startup grace period - always accept result
        if self.frame_count < self.validation_start_frame or self.reinit_cooldown_counter > 0:
            return self._accept_result_simple(frame, detected_bbox, raw_confidence, dt, start_time)

        # After grace period - apply mode-specific logic
        if self.performance_mode == 'fast':
            # Fast mode - minimal validation
            return self._update_fast_mode(frame, detected_bbox, raw_confidence, dt, start_time)

        elif self.performance_mode == 'balanced':
            # Balanced mode - PSR confidence monitoring
            return self._update_balanced_mode(frame, detected_bbox, raw_confidence, dt, start_time)

        else:  # robust
            # Robust mode - full validation
            return self._update_robust_mode(frame, detected_bbox, raw_confidence, dt, start_time)

    def _psr_to_confidence(self, psr: float) -> float:
        """
        Convert PSR (Peak-to-Sidelobe Ratio) to normalized confidence (0.0-1.0).

        PSR ranges (Bolme et al., 2010):
        - PSR < 5: Poor tracking (occlusion or loss)
        - PSR 5-7: Marginal tracking
        - PSR 7-20: Good tracking
        - PSR > 20: Excellent tracking

        Args:
            psr (float): Peak-to-Sidelobe Ratio from dlib tracker

        Returns:
            float: Normalized confidence score (0.0-1.0)
        """
        # Clamp PSR to reasonable range
        psr_clamped = max(0.0, min(psr, 30.0))

        # Map PSR to confidence using sigmoid-like curve
        # PSR 7.0 → 0.5 (threshold)
        # PSR 20.0 → 0.9 (high confidence)
        # PSR < 5.0 → < 0.3 (poor tracking)

        if psr_clamped < self.psr_low_confidence:
            # Poor tracking
            confidence = psr_clamped / (self.psr_low_confidence * 2.0)
        elif psr_clamped < self.psr_confidence_threshold:
            # Marginal tracking
            confidence = 0.25 + (psr_clamped - self.psr_low_confidence) / (self.psr_confidence_threshold - self.psr_low_confidence) * 0.25
        elif psr_clamped < self.psr_high_confidence:
            # Good tracking
            confidence = 0.5 + (psr_clamped - self.psr_confidence_threshold) / (self.psr_high_confidence - self.psr_confidence_threshold) * 0.4
        else:
            # Excellent tracking
            confidence = 0.9 + min(0.1, (psr_clamped - self.psr_high_confidence) / 20.0)

        return max(0.0, min(1.0, confidence))

    # ==============================================================================
    # Enhanced Features: Helper Methods (Student's Research Improvements)
    # ==============================================================================

    def _update_adaptive_psr_threshold(self, current_psr: float) -> None:
        """
        Dynamically adjust PSR confidence threshold based on recent tracking history.

        Research: Adaptive thresholding improves robustness in varying conditions.
        Reference: Zhang et al. "Adaptive Correlation Filters" IJCV 2018

        Args:
            current_psr (float): Current PSR value from tracker
        """
        if not self.adaptive_enabled or not self.psr_dynamic_scaling:
            return

        # Calculate moving average of recent PSR values
        if len(self.psr_history) >= 3:
            recent_psr_avg = np.mean(list(self.psr_history)[-5:])

            # Adapt threshold towards recent PSR average
            target_threshold = recent_psr_avg * 0.7  # 70% of recent average
            target_threshold = max(self.psr_low_confidence, min(target_threshold, self.psr_high_confidence * 0.5))

            # Apply EMA smoothing to threshold adaptation
            self.adaptive_psr_threshold = (
                (1 - self.adapt_rate) * self.adaptive_psr_threshold +
                self.adapt_rate * target_threshold
            )

            # Apply safety margin
            self.adaptive_psr_threshold = max(
                self.psr_low_confidence,
                min(self.adaptive_psr_threshold * self.psr_margin, self.psr_confidence_threshold * 1.2)
            )

    def _get_adaptive_learning_rate(self, psr: float) -> float:
        """
        Calculate adaptive learning rate based on current confidence/PSR.

        Research: High confidence = faster learning, Low confidence = conservative updates.

        Args:
            psr (float): Current PSR value

        Returns:
            float: Adaptive learning rate
        """
        if not self.use_adaptive_learning:
            return self.appearance_learning_rate

        min_lr, max_lr = self.adaptive_learning_bounds

        # Map PSR to learning rate
        # Low PSR → min learning rate
        # High PSR → max learning rate
        if psr < self.psr_low_confidence:
            return min_lr
        elif psr > self.psr_high_confidence:
            return max_lr
        else:
            # Linear interpolation between min and max
            psr_range = self.psr_high_confidence - self.psr_low_confidence
            psr_normalized = (psr - self.psr_low_confidence) / psr_range
            return min_lr + psr_normalized * (max_lr - min_lr)

    def _should_freeze_template(self, psr: float) -> bool:
        """
        Determine if template should be frozen based on confidence.

        Research: Prevents template corruption during occlusions/low-confidence periods.

        Args:
            psr (float): Current PSR value

        Returns:
            bool: True if template should be frozen (not updated)
        """
        if not self.freeze_on_low_confidence:
            return False

        # Freeze if PSR below low confidence threshold
        return psr < self.psr_low_confidence

    def _update_reference_template(self, frame: np.ndarray, psr: float) -> None:
        """
        Periodically refresh reference template to prevent long-term drift.

        Research: Periodic template refresh maintains tracking quality over time.

        Args:
            frame (np.ndarray): Current frame
            psr (float): Current PSR value
        """
        if not self.detector or self.reference_update_interval <= 0:
            return

        self.frames_since_reference_update += 1

        # Refresh reference template if interval reached and confidence is high
        if (self.frames_since_reference_update >= self.reference_update_interval and
            psr > self.psr_high_confidence):
            current_features = self.detector.extract_features(frame, self.bbox)
            if current_features is not None:
                self.reference_template = current_features.copy()
                self.frames_since_reference_update = 0
                logger.debug(f"Reference template refreshed at frame {self.frame_count}")

    def _apply_motion_stabilization(self, bbox: Tuple) -> Tuple:
        """
        Apply EMA smoothing to bbox position to reduce jitter.

        Research: Temporal smoothing improves tracking stability.

        Args:
            bbox (Tuple): Raw bounding box (x, y, w, h)

        Returns:
            Tuple: Smoothed bounding box
        """
        if self.smoothed_bbox is None:
            self.smoothed_bbox = bbox
            return bbox

        # Apply EMA filter to each bbox component
        alpha = self.stabilization_alpha
        smoothed = tuple(
            alpha * new + (1 - alpha) * old
            for new, old in zip(bbox, self.smoothed_bbox)
        )

        self.smoothed_bbox = smoothed
        return smoothed

    def _validate_velocity(self, bbox: Tuple) -> bool:
        """
        Validate that velocity doesn't exceed realistic limits.

        Args:
            bbox (Tuple): Current bounding box

        Returns:
            bool: True if velocity is valid
        """
        if not self.prev_bbox or self.frame_count < 3:
            return True

        # Calculate center displacement
        prev_cx = self.prev_bbox[0] + self.prev_bbox[2] / 2
        prev_cy = self.prev_bbox[1] + self.prev_bbox[3] / 2
        curr_cx = bbox[0] + bbox[2] / 2
        curr_cy = bbox[1] + bbox[3] / 2

        velocity_magnitude = np.sqrt((curr_cx - prev_cx)**2 + (curr_cy - prev_cy)**2)

        is_valid = velocity_magnitude < self.velocity_limit

        if not is_valid:
            logger.debug(f"Velocity validation failed: {velocity_magnitude:.1f} > {self.velocity_limit}")

        return is_valid

    def _accept_result_simple(self, frame: np.ndarray, bbox: Tuple, confidence: float,
                              dt: float, start_time: float) -> Tuple[bool, Tuple]:
        """Accept tracking result without validation (startup grace period)."""
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)
        self.confidence = confidence

        # Update appearance model with enhanced features
        if self.detector:
            # Get current PSR for adaptive features
            current_psr = list(self.psr_history)[-1] if self.psr_history else self.psr_confidence_threshold

            # Check if template should be frozen
            if not self._should_freeze_template(current_psr):
                current_features = self.detector.extract_features(frame, self.bbox)

                # Get adaptive learning rate based on confidence
                learning_rate = self._get_adaptive_learning_rate(current_psr)

                self.detector.adaptive_features = (
                    (1 - learning_rate) * self.detector.adaptive_features +
                    learning_rate * current_features
                )

                # Update reference template periodically
                self._update_reference_template(frame, current_psr)

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

    def _update_fast_mode(self, frame: np.ndarray, bbox: Tuple, confidence: float,
                          dt: float, start_time: float) -> Tuple[bool, Tuple]:
        """Fast mode - minimal validation, maximum speed."""
        # Simple PSR threshold check
        if confidence < (self.psr_confidence_threshold / self.psr_high_confidence):
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                logger.warning(f"Tracking lost after {self.failure_count} consecutive failures (PSR too low)")
                return False, self.bbox
            return True, self.bbox  # Continue with last known bbox

        # Accept result
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)
        self.confidence = confidence

        # Update appearance model with enhanced features
        if self.detector:
            # Get current PSR for adaptive features
            current_psr = list(self.psr_history)[-1] if self.psr_history else self.psr_confidence_threshold

            # Check if template should be frozen
            if not self._should_freeze_template(current_psr):
                current_features = self.detector.extract_features(frame, self.bbox)

                # Get adaptive learning rate based on confidence
                learning_rate = self._get_adaptive_learning_rate(current_psr)

                self.detector.adaptive_features = (
                    (1 - learning_rate) * self.detector.adaptive_features +
                    learning_rate * current_features
                )

                # Update reference template periodically
                self._update_reference_template(frame, current_psr)

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

    def _update_balanced_mode(self, frame: np.ndarray, bbox: Tuple, confidence: float,
                              dt: float, start_time: float) -> Tuple[bool, Tuple]:
        """Balanced mode - PSR confidence monitoring with smoothing."""
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
        self.normalize_bbox()
        self.center_history.append(self.center)

        # Apply EMA smoothing to confidence
        if self.enable_ema_smoothing:
            smoothed_confidence = self._smooth_confidence(confidence)
        else:
            smoothed_confidence = confidence
            self.confidence = confidence

        # Check confidence
        if smoothed_confidence < (self.psr_confidence_threshold / self.psr_high_confidence):
            self.failure_count += 1
            logger.debug(f"Low confidence ({self.failure_count}/{self.failure_threshold}): {smoothed_confidence:.2f}")

            if self.failure_count >= self.failure_threshold:
                logger.warning(f"Tracking lost after {self.failure_count} consecutive failures")
                return False, self.bbox
        else:
            self.failure_count = 0
            self.successful_frames += 1

        # Update appearance model with enhanced features
        if self.detector:
            # Get current PSR for adaptive features
            current_psr = list(self.psr_history)[-1] if self.psr_history else self.psr_confidence_threshold

            # Check if template should be frozen
            if not self._should_freeze_template(current_psr):
                current_features = self.detector.extract_features(frame, self.bbox)

                # Get adaptive learning rate based on confidence
                learning_rate = self._get_adaptive_learning_rate(current_psr)

                self.detector.adaptive_features = (
                    (1 - learning_rate) * self.detector.adaptive_features +
                    learning_rate * current_features
                )

                # Update reference template periodically
                self._update_reference_template(frame, current_psr)

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

    def _update_robust_mode(self, frame: np.ndarray, bbox: Tuple, confidence: float,
                           dt: float, start_time: float) -> Tuple[bool, Tuple]:
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

        # Update state
        self.prev_center = self.center
        self.bbox = bbox
        self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))

        # Smooth confidence
        smoothed_confidence = self._smooth_confidence(confidence)

        # Decision logic
        if smoothed_confidence > (self.psr_confidence_threshold / self.psr_high_confidence) and motion_valid and scale_valid:
            # Accept result
            self.normalize_bbox()
            self.center_history.append(self.center)

            # Update appearance model with enhanced features
            if self.detector:
                # Get current PSR for adaptive features
                current_psr = list(self.psr_history)[-1] if self.psr_history else self.psr_confidence_threshold

                # Check if template should be frozen
                if not self._should_freeze_template(current_psr):
                    current_features = self.detector.extract_features(frame, self.bbox)

                    # Get adaptive learning rate based on confidence
                    learning_rate = self._get_adaptive_learning_rate(current_psr)

                    self.detector.adaptive_features = (
                        (1 - learning_rate) * self.detector.adaptive_features +
                        learning_rate * current_features
                    )

                    # Update reference template periodically
                    self._update_reference_template(frame, current_psr)

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
            logger.debug(f"dlib accepted: conf={smoothed_confidence:.2f}, motion={motion_valid}, scale={scale_valid}")
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

        dlib_cx = bbox[0] + bbox[2]/2
        dlib_cy = bbox[1] + bbox[3]/2

        est_x, est_y = estimator_prediction
        distance = np.sqrt((dlib_cx - est_x)**2 + (dlib_cy - est_y)**2)

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
            smoothed = (self.confidence_smoothing_alpha * raw_confidence +
                       (1 - self.confidence_smoothing_alpha) * self.confidence)

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
            avg_psr = np.mean(list(self.psr_history)) if self.psr_history else 0.0
            logger.info(f"{self.trackerName} ({self.performance_mode}): FPS={avg_fps:.1f}, "
                       f"conf={self.confidence:.2f}, PSR={avg_psr:.1f}, success={success_rate:.1f}%")

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
        """Returns dlib-specific tracker output."""
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

        # Get latest PSR value for quality metrics
        latest_psr = list(self.psr_history)[-1] if self.psr_history else 0.0

        return TrackerOutput(
            data_type=data_type,
            timestamp=time.time(),
            tracking_active=self.tracking_started,
            tracker_id=f"dlib_{id(self)}",
            position_2d=self.normalized_center,
            bbox=self.bbox,
            normalized_bbox=self.normalized_bbox,
            confidence=self.confidence,
            velocity=velocity,
            quality_metrics={
                'motion_consistency': self.compute_motion_confidence() if self.prev_center else 1.0,
                'psr_value': latest_psr,
                'failure_count': self.failure_count,
                'success_rate': self.successful_frames / (self.frame_count + 1e-6) if self.frame_count > 0 else 1.0
            },
            raw_data={
                'performance_mode': self.performance_mode,
                'frame_count': self.frame_count,
                'successful_frames': self.successful_frames,
                'failed_frames': self.failed_frames,
                'avg_fps': round(np.mean(self.fps_history[-30:]), 1) if len(self.fps_history) >= 30 else 0.0,
                'psr_history': list(self.psr_history)
            },
            metadata={
                'tracker_class': self.__class__.__name__,
                'tracker_algorithm': 'dlib_correlation_filter',
                'performance_mode': self.performance_mode,
                'dlib_version': dlib.__version__ if hasattr(dlib, '__version__') else 'unknown'
            }
        )

    def get_capabilities(self) -> dict:
        """Returns dlib-specific capabilities."""
        base_capabilities = super().get_capabilities()
        base_capabilities.update({
            'tracker_algorithm': 'dlib_correlation_filter',
            'supports_rotation': False,  # Limited rotation invariance
            'supports_scale_change': True,
            'supports_occlusion': False,  # Limited occlusion handling
            'accuracy_rating': 'high',
            'speed_rating': 'very_fast',
            'correlation_filter': True,
            'psr_confidence': True,
            'performance_mode': self.performance_mode
        })
        return base_capabilities
