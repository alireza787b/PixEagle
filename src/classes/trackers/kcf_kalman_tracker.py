# src/classes/trackers/kcf_kalman_tracker.py

"""
KCFKalmanTracker Module - KCF + Internal Kalman Filter Hybrid
--------------------------------------------------------------

Production-grade KCF tracker with an internal 4D Kalman filter for robust
position estimation and graceful degradation during occlusion.

Architecture:
    Frame → KCF Tracker → Validate (motion + scale) → Accept / Kalman fallback

References:
-----------
- KCF: Henriques et al., TPAMI 2015
- Kalman Filters: Welch & Bishop, TR 95-041, 2006
"""

import logging
import time
import cv2
import numpy as np
from typing import Optional, Tuple
from filterpy.kalman import KalmanFilter

from classes.trackers.base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.parameters import Parameters

logger = logging.getLogger(__name__)


class KCFKalmanTracker(BaseTracker):
    """KCF + Kalman Filter Hybrid Tracker with multi-frame validation."""

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        super().__init__(video_handler, detector, app_controller)

        self.tracker_name = "KCF+Kalman"
        self.kcf_tracker = None
        self.kf = None
        self.is_initialized = False

        # Robustness parameters from config
        kcf_config = getattr(Parameters, 'KCF_Tracker', {})
        self.confidence_threshold = kcf_config.get('confidence_threshold', 0.15)
        self.confidence_ema_alpha = kcf_config.get('confidence_smoothing', 0.6)
        self.failure_threshold = kcf_config.get('failure_threshold', 7)
        self.max_scale_change = kcf_config.get('max_scale_change_per_frame', 0.6)
        self.motion_consistency_threshold = kcf_config.get('motion_consistency_threshold', 0.15)

        logger.info(f"{self.tracker_name} initialized with production robustness features")

    # =========================================================================
    # Internal Kalman Filter
    # =========================================================================

    def _init_kalman(self, bbox: Tuple[int, int, int, int]) -> None:
        """Initialize internal 4D Kalman filter: state [x, y, vx, vy]."""
        x, y, w, h = bbox
        cx, cy = x + w / 2, y + h / 2

        self.kf = KalmanFilter(dim_x=4, dim_z=2)

        dt = 1.0
        self.kf.F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1]
        ])
        self.kf.H = np.array([
            [1, 0, 0, 0],
            [0, 1, 0, 0]
        ])

        kcf_config = getattr(Parameters, 'KCF_Tracker', {})
        process_noise = kcf_config.get('kalman_process_noise', 0.1)
        velocity_noise_factor = kcf_config.get('kalman_velocity_noise_factor', 0.5)
        self.kf.Q = np.eye(4) * process_noise
        self.kf.Q[2:, 2:] *= velocity_noise_factor

        measurement_noise = kcf_config.get('kalman_measurement_noise', 5.0)
        self.kf.R = np.eye(2) * measurement_noise

        initial_pos_cov = kcf_config.get('kalman_initial_position_covariance', 10.0)
        initial_vel_cov = kcf_config.get('kalman_initial_velocity_covariance', 100.0)
        self.kf.P = np.diag([initial_pos_cov, initial_pos_cov,
                             initial_vel_cov, initial_vel_cov])
        self.kf.x = np.array([cx, cy, 0, 0])

    # =========================================================================
    # Tracking Interface
    # =========================================================================

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        self.kcf_tracker = cv2.TrackerKCF_create()
        self.kcf_tracker.init(frame, bbox)
        self._init_kalman(bbox)
        self.tracking_started = True

        if self.detector:
            self.detector.initial_features = self.detector.extract_features(frame, bbox)
            self.detector.adaptive_features = self.detector.initial_features.copy()

        self.bbox = bbox
        self.prev_bbox = bbox
        self.confidence = 1.0
        self.failure_count = 0
        self.is_initialized = True
        self.prev_center = None
        self.last_update_time = time.time()
        self.raw_confidence_history.clear()
        self.frame_count = 0
        self.successful_frames = 0
        self.failed_frames = 0
        self.fps_history.clear()

        logger.info(f"{self.tracker_name} tracking started: bbox={bbox}")

    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[Tuple[int, int, int, int]]]:
        if not self.is_initialized:
            return False, None

        start_time = time.time()
        dt = self.update_time()

        if self.override_active:
            return self._handle_smart_tracker_override(frame, dt)

        # KCF tracker update
        kcf_success, kcf_bbox = self.kcf_tracker.update(frame)

        # Kalman prediction (always run for motion model)
        self.kf.predict()
        kf_prediction = (self.kf.x[0], self.kf.x[1])

        if kcf_success:
            motion_valid = self._validate_bbox_motion(kcf_bbox, kf_prediction)
            scale_valid = self._validate_bbox_scale(kcf_bbox)
            raw_confidence = self._compute_kcf_confidence(kcf_bbox, self.prev_bbox)
            smoothed_confidence = self._smooth_confidence(raw_confidence)

            if smoothed_confidence > self.confidence_threshold and motion_valid and scale_valid:
                # Accept KCF result
                self.prev_center = self.center
                self.bbox = tuple(int(v) for v in kcf_bbox)
                cx, cy = kcf_bbox[0] + kcf_bbox[2] / 2, kcf_bbox[1] + kcf_bbox[3] / 2
                self.kf.update(np.array([cx, cy]))
                self._update_appearance_model_safe(frame, self.bbox)
                self.failure_count = 0
                self.successful_frames += 1
                success = True
                logger.debug(f"KCF accepted: conf={smoothed_confidence:.2f}, "
                             f"motion_ok={motion_valid}, scale_ok={scale_valid}")
            else:
                self._handle_low_confidence(kf_prediction, smoothed_confidence,
                                            motion_valid, scale_valid)
                success = False
        else:
            self._handle_kcf_failure(kf_prediction)
            success = False

        if success:
            self.set_center((int(self.bbox[0] + self.bbox[2] / 2),
                             int(self.bbox[1] + self.bbox[3] / 2)))
            self.normalize_bbox()
            self.center_history.append(self.center)
            self.prev_bbox = self.bbox

        self.frame_count += 1
        self._update_out_of_frame_status(frame)
        self._log_performance(start_time)

        # Multi-frame failure check
        if self.failure_count >= self.failure_threshold:
            loss_reason = "tracker_failed" if not kcf_success else "low_confidence"
            logger.warning(f"{self.tracker_name} lost target ({self.failure_count} consecutive failures)")
            self._build_failure_info(loss_reason)
            return False, self.bbox

        return True, self.bbox

    # =========================================================================
    # KCF-Specific Helpers
    # =========================================================================

    def _compute_kcf_confidence(self, curr_bbox, prev_bbox) -> float:
        """Confidence from bbox stability (motion + scale penalties)."""
        if prev_bbox is None:
            return 0.9
        curr_cx = curr_bbox[0] + curr_bbox[2] / 2
        curr_cy = curr_bbox[1] + curr_bbox[3] / 2
        prev_cx = prev_bbox[0] + prev_bbox[2] / 2
        prev_cy = prev_bbox[1] + prev_bbox[3] / 2
        motion = np.sqrt((curr_cx - prev_cx) ** 2 + (curr_cy - prev_cy) ** 2)
        avg_size = (prev_bbox[2] + prev_bbox[3]) / 2
        normalized_motion = motion / (avg_size + 1e-6)
        scale_change_w = abs(curr_bbox[2] / (prev_bbox[2] + 1e-6) - 1.0)
        scale_change_h = abs(curr_bbox[3] / (prev_bbox[3] + 1e-6) - 1.0)
        scale_change = (scale_change_w + scale_change_h) / 2
        confidence = 1.0 / (1.0 + 1.5 * normalized_motion + 3.0 * scale_change)
        return np.clip(confidence, 0.0, 1.0)

    def _handle_low_confidence(self, kf_prediction, smoothed_confidence,
                                motion_valid, scale_valid):
        """Use Kalman prediction with velocity extrapolation on low confidence."""
        kf_x, kf_y = kf_prediction
        kcf_config = getattr(Parameters, 'KCF_Tracker', {})
        use_velocity = kcf_config.get('use_velocity_during_occlusion', True)

        if use_velocity and self.kf is not None:
            kf_vx, kf_vy = float(self.kf.x[2]), float(self.kf.x[3])
            velocity_factor = kcf_config.get('occlusion_velocity_factor', 0.5)
            predicted_x = kf_x + kf_vx * velocity_factor
            predicted_y = kf_y + kf_vy * velocity_factor
            logger.debug(f"Velocity extrapolation: pos=({kf_x:.1f},{kf_y:.1f}), "
                         f"vel=({kf_vx:.1f},{kf_vy:.1f}), "
                         f"predicted=({predicted_x:.1f},{predicted_y:.1f})")
        else:
            predicted_x, predicted_y = kf_x, kf_y

        if self.prev_bbox:
            w, h = self.prev_bbox[2], self.prev_bbox[3]
            self.bbox = tuple(int(v) for v in [predicted_x - w / 2, predicted_y - h / 2, w, h])

        self._record_loss_start()
        self.failure_count += 1
        self.failed_frames += 1
        logger.debug(f"Low confidence ({self.failure_count}/{self.failure_threshold}): "
                     f"conf={smoothed_confidence:.2f}, motion={motion_valid}, scale={scale_valid}")

    def _handle_kcf_failure(self, kf_prediction):
        """Handle complete KCF failure — use Kalman prediction."""
        kf_x, kf_y = kf_prediction
        if self.prev_bbox:
            w, h = self.prev_bbox[2], self.prev_bbox[3]
            self.bbox = tuple(int(v) for v in [kf_x - w / 2, kf_y - h / 2, w, h])
        self._record_loss_start()
        self.failure_count += 1
        self.failed_frames += 1
        self.confidence = 0.1
        logger.debug(f"{self.tracker_name} KCF failed, using Kalman "
                     f"({self.failure_count}/{self.failure_threshold})")

    # =========================================================================
    # Overrides (KCF-specific behavior)
    # =========================================================================

    def _handle_smart_tracker_override(self, frame, dt):
        """Override: also update internal Kalman with SmartTracker bbox."""
        success, bbox = super()._handle_smart_tracker_override(frame, dt)
        if success and self.kf:
            x1, y1, x2, y2 = self.app_controller.smart_tracker.selected_bbox
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            self.kf.predict()
            self.kf.update(np.array([cx, cy]))
        return success, bbox

    def update_estimator_without_measurement(self) -> None:
        """KCF uses internal Kalman — external estimator not needed for prediction."""
        pass

    def get_estimated_position(self) -> Optional[Tuple[float, float]]:
        """Get position from internal Kalman state."""
        if self.kf and self.is_initialized:
            return (float(self.kf.x[0]), float(self.kf.x[1]))
        return None

    def reset(self) -> None:
        self.kcf_tracker = None
        self.kf = None
        self.is_initialized = False
        super().reset()

    # =========================================================================
    # Output
    # =========================================================================

    def _get_velocity_from_estimator(self):
        """Override: get velocity from internal Kalman instead of external estimator."""
        if self.kf and self.is_initialized and len(self.center_history) > 2:
            vel_x, vel_y = self.kf.x[2], self.kf.x[3]
            if (vel_x ** 2 + vel_y ** 2) ** 0.5 > 0.001:
                return (float(vel_x), float(vel_y))
        return None

    def get_output(self) -> TrackerOutput:
        return self._build_output(
            tracker_algorithm='KCF+Kalman',
            extra_quality={
                'bbox_stability': self.confidence,
            },
            extra_raw={
                'internal_kalman_enabled': True,
                'failure_threshold': self.failure_threshold,
            },
            extra_metadata={
                'has_internal_kalman': True,
                'supports_velocity': True,
                'opencv_version': cv2.__version__,
            },
        )

    def get_capabilities(self) -> dict:
        base = super().get_capabilities()
        base.update({
            'tracker_algorithm': 'KCF+Kalman',
            'supports_rotation': False,
            'supports_scale_change': True,
            'supports_occlusion': True,
            'accuracy_rating': 'high',
            'speed_rating': 'very_fast',
            'internal_kalman': True,
            'real_time_cpu': True,
        })
        return base
