# src/classes/trackers/base_tracker.py

"""
BaseTracker Module
------------------

Abstract base class for all object trackers in PixEagle.

Provides:
- Common interface (start_tracking, update, stop_tracking, reset)
- Shared state management (bbox, center, confidence, failure counting)
- Estimator integration (external Kalman-based position estimator)
- Visualization (normal/fancy bbox, center dot, estimate overlay)
- Boundary detection (near-edge warnings, confidence penalties)
- Appearance model updates with drift protection
- Structured failure reporting (TrackingFailureInfo)
- Out-of-frame detection
- SmartTracker override support
- Standardized TrackerOutput building

To create a new tracker:
1. Subclass BaseTracker
2. Implement start_tracking() and update()
3. Override _create_tracker() to return the underlying tracker instance
4. Add the new tracker to tracker_factory.py
"""

from abc import ABC, abstractmethod
from collections import deque
import dataclasses
import time
import numpy as np
from typing import Optional, Tuple, Dict, Any
import cv2
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Structured Failure Reporting
# =============================================================================

@dataclasses.dataclass
class TrackingFailureInfo:
    """Structured context for tracking loss events.

    Populated by BaseTracker._build_failure_info() whenever a tracker returns
    (False, bbox).  Consumers can inspect tracker.last_failure_info for
    diagnostics without changing the (bool, bbox) return signature.
    """
    loss_reason: str                                        # "tracker_failed" | "low_confidence" | "left_frame" | "scale_invalid"
    last_seen_bbox: Optional[Tuple[int, int, int, int]]     # Last confirmed bbox (x, y, w, h)
    predicted_bbox: Optional[Tuple[int, int, int, int]]     # Current predicted bbox
    frames_lost: int                                        # Consecutive failure frames
    confidence_at_loss: float                               # Confidence when loss began
    exit_edge: Optional[str]                                # "left" | "right" | "top" | "bottom" | None


class BaseTracker(ABC):
    """Abstract Base Class for Object Trackers."""

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        self.video_handler = video_handler
        self.detector = detector
        self.app_controller = app_controller

        # --- Core tracking state ---
        self.bbox: Optional[Tuple[int, int, int, int]] = None
        self.prev_center: Optional[Tuple[int, int]] = None
        self.center: Optional[Tuple[int, int]] = None
        self.normalized_bbox: Optional[Tuple[float, float, float, float]] = None
        self.normalized_center: Optional[Tuple[float, float]] = None
        self.center_history = deque(maxlen=Parameters.CENTER_HISTORY_LENGTH)
        self.tracking_started: bool = False

        # --- Shared robustness state (used by all visual trackers) ---
        self.prev_bbox: Optional[Tuple[int, int, int, int]] = None
        self.failure_count: int = 0
        self.failure_threshold: int = 5
        self.frame_count: int = 0
        self.successful_frames: int = 0
        self.failed_frames: int = 0
        self.fps_history: list = []
        self.raw_confidence_history: deque = deque(maxlen=5)
        self.tracker_name: str = self.__class__.__name__

        # --- Classic tracker common config ---
        common_config = getattr(Parameters, 'ClassicTracker_Common', {})

        # --- Confidence ---
        self.confidence: float = 1.0
        self.confidence_ema_alpha: float = common_config.get('confidence_ema_alpha', 0.7)
        self.max_scale_change: float = common_config.get('max_scale_change_per_frame', 0.4)
        self.motion_consistency_threshold: float = common_config.get('motion_consistency_threshold', 0.5)

        # --- Estimator ---
        self.estimator_enabled = Parameters.USE_ESTIMATOR
        self.position_estimator = (
            self.app_controller.estimator
            if self.estimator_enabled and self.app_controller else None
        )
        self.estimated_position_history = deque(maxlen=Parameters.ESTIMATOR_HISTORY_LENGTH)
        self.last_update_time: float = 1e-6

        # --- Frame placeholder ---
        self.frame = None

        # --- SmartTracker override ---
        self.override_active: bool = False
        self.override_bbox: Optional[Tuple[int, int, int, int]] = None
        self.override_center: Optional[Tuple[int, int]] = None

        # --- Component suppression ---
        self.suppress_detector = False
        self.suppress_predictor = False

        # --- Out-of-frame detection ---
        self.target_out_of_frame: bool = False
        self.exit_edge: Optional[str] = None
        self.exit_edge_margin_pixels: int = common_config.get('exit_edge_margin_pixels', 5)

        # --- Structured failure reporting ---
        self.last_failure_info: Optional[TrackingFailureInfo] = None
        self._confidence_at_loss_start: float = 0.0

        # --- Performance logging ---
        self.performance_log_interval: int = common_config.get('performance_log_interval', 30)

        # --- Create underlying tracker ---
        self.tracker = self._create_tracker()

    # =========================================================================
    # Abstract Interface
    # =========================================================================

    @abstractmethod
    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        pass

    @abstractmethod
    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        pass

    # =========================================================================
    # Lifecycle
    # =========================================================================

    def stop_tracking(self) -> None:
        self.tracking_started = False
        self.bbox = None
        self.center = None
        self.prev_center = None
        self.normalized_bbox = None
        self.normalized_center = None
        self.confidence = 1.0
        logger.debug(f"{self.tracker_name} tracking stopped and state reset")

    def reset(self):
        self.bbox = None
        self.center = None
        self.prev_center = None
        self.prev_bbox = None
        self.tracking_started = False
        self.override_active = False
        self.override_bbox = None
        self.override_center = None
        self.center_history.clear()
        self.estimated_position_history.clear()
        self.last_update_time = time.time()
        self.failure_count = 0
        self.frame_count = 0
        self.successful_frames = 0
        self.failed_frames = 0
        self.fps_history.clear()
        self.raw_confidence_history.clear()
        self.confidence = 1.0
        self.target_out_of_frame = False
        self.exit_edge = None
        self.last_failure_info = None
        if self.position_estimator:
            self.position_estimator.reset()
        self.tracker = self._create_tracker()
        logger.info(f"{self.tracker_name} fully reset")

    def _create_tracker(self):
        """Override in subclass to return the underlying tracker instance."""
        return None

    # =========================================================================
    # Confidence
    # =========================================================================

    def compute_confidence(self, frame: np.ndarray) -> float:
        motion_confidence = self.compute_motion_confidence()
        appearance_confidence = 1.0

        if (self.detector and hasattr(self.detector, 'compute_appearance_confidence')
                and self.detector.adaptive_features is not None):
            current_features = self.detector.extract_features(frame, self.bbox)
            appearance_confidence = self.detector.compute_appearance_confidence(
                current_features, self.detector.adaptive_features)
        else:
            logger.warning("Detector is not available or adaptive features are not set.")

        self.confidence = (Parameters.MOTION_CONFIDENCE_WEIGHT * motion_confidence +
                           Parameters.APPEARANCE_CONFIDENCE_WEIGHT * appearance_confidence)
        return self.confidence

    def get_confidence(self) -> float:
        return self.confidence

    def compute_motion_confidence(self) -> float:
        if self.prev_center is None:
            return 1.0
        if not self.video_handler:
            return 1.0
        displacement = np.linalg.norm(np.array(self.center) - np.array(self.prev_center))
        frame_diag = np.hypot(self.video_handler.width, self.video_handler.height)
        confidence = max(0.0, 1.0 - (displacement / (Parameters.MAX_DISPLACEMENT_THRESHOLD * frame_diag)))
        return confidence

    def is_motion_consistent(self) -> bool:
        return self.compute_motion_confidence() >= Parameters.MOTION_CONFIDENCE_THRESHOLD

    def _smooth_confidence(self, raw_confidence: float) -> float:
        """Apply EMA smoothing to confidence. Shared by CSRT, KCF, dlib."""
        self.raw_confidence_history.append(raw_confidence)
        if len(self.raw_confidence_history) == 1:
            smoothed = raw_confidence
        else:
            smoothed = (self.confidence_ema_alpha * raw_confidence +
                        (1 - self.confidence_ema_alpha) * self.confidence)
        self.confidence = smoothed
        return smoothed

    # =========================================================================
    # Validation (shared by CSRT, KCF, dlib robust modes)
    # =========================================================================

    def _validate_bbox_motion(self, bbox: Tuple, estimator_prediction: Optional[Tuple]) -> bool:
        """Validate bbox motion against estimator/Kalman prediction."""
        if not self.video_handler or not estimator_prediction or self.frame_count < 15:
            return True
        bbox_cx = bbox[0] + bbox[2] / 2
        bbox_cy = bbox[1] + bbox[3] / 2
        est_x, est_y = estimator_prediction
        distance = np.sqrt((bbox_cx - est_x) ** 2 + (bbox_cy - est_y) ** 2)
        frame_diag = np.hypot(self.video_handler.width, self.video_handler.height)
        normalized_distance = distance / frame_diag
        is_valid = normalized_distance < self.motion_consistency_threshold
        if not is_valid:
            logger.debug(f"Motion validation failed: {normalized_distance:.3f} > "
                         f"{self.motion_consistency_threshold}")
        return is_valid

    def _validate_bbox_scale(self, bbox: Tuple) -> bool:
        """Validate bbox scale change against previous frame."""
        if not self.prev_bbox:
            return True
        scale_w = bbox[2] / (self.prev_bbox[2] + 1e-6)
        scale_h = bbox[3] / (self.prev_bbox[3] + 1e-6)
        scale_change = max(abs(scale_w - 1.0), abs(scale_h - 1.0))
        is_valid = scale_change < self.max_scale_change
        if not is_valid:
            logger.debug(f"Scale validation failed: {scale_change:.3f} > "
                         f"{self.max_scale_change}")
        return is_valid

    def _should_update_appearance(self, frame: np.ndarray, bbox: Tuple) -> bool:
        """3-level drift protection: confidence + motion + scale."""
        common_config = getattr(Parameters, 'ClassicTracker_Common', {})
        min_confidence = common_config.get('appearance_update_min_confidence', 0.55)
        if self.confidence < min_confidence:
            return False
        if self.prev_center and self.center:
            if self.compute_motion_confidence() < 0.7:
                return False
        if self.prev_bbox and bbox:
            scale_w = bbox[2] / (self.prev_bbox[2] + 1e-6)
            scale_h = bbox[3] / (self.prev_bbox[3] + 1e-6)
            scale_change = max(abs(scale_w - 1.0), abs(scale_h - 1.0))
            if scale_change > 0.3:
                return False
        return True

    # =========================================================================
    # Appearance Model
    # =========================================================================

    def _update_appearance_model_safe(self, frame: np.ndarray, bbox: Tuple,
                                       learning_rate: Optional[float] = None) -> None:
        """Update appearance model with drift protection.

        Subclasses (e.g. dlib) may override to add freeze/adaptive-LR logic.
        """
        if not self.detector or not hasattr(self.detector, 'adaptive_features'):
            return
        if self.detector.adaptive_features is None:
            return
        if not self._should_update_appearance(frame, bbox):
            return
        current_features = self.detector.extract_features(frame, bbox)
        lr = learning_rate or getattr(self, 'appearance_learning_rate', 0.08)
        self.detector.adaptive_features = (
            (1 - lr) * self.detector.adaptive_features + lr * current_features
        )

    # =========================================================================
    # Estimator
    # =========================================================================

    def _update_estimator(self, dt: float) -> None:
        """Update external position estimator with current center."""
        if self.estimator_enabled and self.position_estimator and self.center:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_and_update(np.array(self.center))
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)

    def update_estimator_without_measurement(self) -> None:
        """Predict-only estimator step (no measurement available)."""
        dt = self.update_time()
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_only()
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)

    def get_estimated_position(self) -> Optional[Tuple[float, float]]:
        """Get current estimated position from external estimator."""
        if self.estimator_enabled and self.position_estimator:
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position and len(estimated_position) >= 2:
                return (estimated_position[0], estimated_position[1])
        return None

    def _get_estimator_prediction(self) -> Optional[Tuple[float, float]]:
        """Get position prediction from external estimator (predict-only)."""
        if self.estimator_enabled and self.position_estimator:
            dt = self.update_time()
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_only()
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position and len(estimated_position) >= 2:
                return (estimated_position[0], estimated_position[1])
        return None

    # =========================================================================
    # SmartTracker Override
    # =========================================================================

    def _handle_smart_tracker_override(self, frame: np.ndarray, dt: float) -> Tuple[bool, Tuple]:
        """Handle SmartTracker override mode. KCF overrides to add Kalman update."""
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
            self._update_estimator(dt)
            self.failure_count = 0
            return True, self.bbox
        else:
            logger.warning("Override active but SmartTracker has no selected bbox")
            return False, self.bbox

    def set_external_override(self, bbox: Tuple[int, int, int, int],
                              center: Tuple[int, int]) -> None:
        """Enable override mode (SmartTracker injects detections)."""
        was_active = self.override_active
        self.override_active = True
        self.bbox = (bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])
        self.set_center(center)
        self.center_history.append(center)
        self.normalize_bbox()
        if not was_active:
            logger.info("[OVERRIDE] SmartTracker override activated")

    def clear_external_override(self) -> None:
        """Disable external override."""
        if self.override_active:
            self.override_active = False
            self.bbox = None
            self.center = None
            logger.info("[OVERRIDE] SmartTracker override cleared")

    def get_effective_bbox(self) -> Optional[Tuple[int, int, int, int]]:
        return self.override_bbox if self.override_active else self.bbox

    def get_effective_center(self) -> Optional[Tuple[int, int]]:
        return self.override_center if self.override_active else self.center

    # =========================================================================
    # Out-of-Frame Detection
    # =========================================================================

    def _check_out_of_frame(self, bbox: Tuple, frame_shape: Tuple) -> Optional[str]:
        """Returns exit edge name or None if bbox is within frame."""
        if bbox is None:
            return None
        h, w = frame_shape[:2]
        x, y, bw, bh = bbox
        margin = self.exit_edge_margin_pixels
        if x + bw < margin:
            return "left"
        if x > w - margin:
            return "right"
        if y + bh < margin:
            return "top"
        if y > h - margin:
            return "bottom"
        return None

    def _update_out_of_frame_status(self, frame: np.ndarray) -> None:
        """Update OOF state based on current bbox and frame dimensions."""
        if self.bbox is None or frame is None:
            return
        edge = self._check_out_of_frame(self.bbox, frame.shape)
        if edge and not self.target_out_of_frame:
            self.target_out_of_frame = True
            self.exit_edge = edge
            logger.info(f"[TRACKING] Target left frame via {edge.upper()} edge")
        elif not edge and self.target_out_of_frame:
            logger.info(f"[TRACKING] Target returned to frame (was {self.exit_edge})")
            self.target_out_of_frame = False
            self.exit_edge = None

    # =========================================================================
    # Structured Failure Reporting
    # =========================================================================

    def _build_failure_info(self, loss_reason: str) -> TrackingFailureInfo:
        """Build structured failure info and store in self.last_failure_info."""
        # Determine loss reason from OOF state
        effective_reason = loss_reason
        if self.target_out_of_frame:
            effective_reason = "left_frame"

        info = TrackingFailureInfo(
            loss_reason=effective_reason,
            last_seen_bbox=self.prev_bbox,
            predicted_bbox=self.bbox,
            frames_lost=self.failure_count,
            confidence_at_loss=self._confidence_at_loss_start,
            exit_edge=self.exit_edge,
        )
        self.last_failure_info = info
        return info

    def _record_loss_start(self) -> None:
        """Snapshot confidence when failure sequence begins."""
        if self.failure_count == 0:
            self._confidence_at_loss_start = self.confidence

    # =========================================================================
    # Performance Logging
    # =========================================================================

    def _log_performance(self, start_time: float) -> None:
        """Log FPS, confidence, and success rate periodically."""
        elapsed = time.time() - start_time
        fps = 1.0 / (elapsed + 1e-6)
        self.fps_history.append(fps)
        if self.frame_count % self.performance_log_interval == 0 and self.frame_count > 0:
            avg_fps = np.mean(self.fps_history[-30:])
            success_rate = 100 * self.successful_frames / (self.frame_count + 1e-6)
            logger.info(f"{self.tracker_name}: FPS={avg_fps:.1f}, "
                        f"conf={self.confidence:.2f}, success={success_rate:.1f}%")

    # =========================================================================
    # Time
    # =========================================================================

    def update_time(self) -> float:
        current_time = time.monotonic()
        dt = current_time - self.last_update_time
        if dt <= 0:
            dt = 1e-3
        self.last_update_time = current_time
        return dt

    # =========================================================================
    # Normalization
    # =========================================================================

    def normalize_center_coordinates(self) -> None:
        if self.center and self.video_handler:
            frame_width, frame_height = self.video_handler.width, self.video_handler.height
            normalized_x = (self.center[0] - frame_width / 2) / (frame_width / 2)
            normalized_y = (self.center[1] - frame_height / 2) / (frame_height / 2)
            self.normalized_center = (normalized_x, normalized_y)

    def print_normalized_center(self) -> None:
        if self.normalized_center:
            logger.debug(f"Normalized center: ({self.normalized_center[0]:.3f}, "
                         f"{self.normalized_center[1]:.3f})")
        else:
            logger.warning("Normalized center not available.")

    def set_center(self, value: Tuple[int, int]) -> None:
        self.center = value
        self.normalize_center_coordinates()

    def normalize_bbox(self) -> None:
        if self.bbox and self.video_handler:
            frame_width, frame_height = self.video_handler.width, self.video_handler.height
            x, y, w, h = self.bbox
            norm_x = (x - frame_width / 2) / (frame_width / 2)
            norm_y = (y - frame_height / 2) / (frame_height / 2)
            norm_w = w / frame_width
            norm_h = h / frame_height
            self.normalized_bbox = (norm_x, norm_y, norm_w, norm_h)

    def _normalize_center_static(self, center: Tuple[int, int]) -> Tuple[float, float]:
        if not self.video_handler:
            return (0.0, 0.0)
        frame_width, frame_height = self.video_handler.width, self.video_handler.height
        x, y = center
        return ((x - frame_width / 2) / (frame_width / 2),
                (y - frame_height / 2) / (frame_height / 2))

    def _normalize_bbox_static(self, bbox: Tuple[int, int, int, int]) -> Tuple[float, float, float, float]:
        if not self.video_handler:
            return (0.0, 0.0, 0.0, 0.0)
        frame_width, frame_height = self.video_handler.width, self.video_handler.height
        x, y, w, h = bbox
        return ((x - frame_width / 2) / (frame_width / 2),
                (y - frame_height / 2) / (frame_height / 2),
                w / frame_width,
                h / frame_height)

    # =========================================================================
    # Boundary Detection
    # =========================================================================

    def is_near_boundary(self, margin: int = None) -> bool:
        if not self.bbox or not self.video_handler:
            return False
        if margin is None:
            margin = getattr(Parameters, 'BOUNDARY_MARGIN_PIXELS', 15)
        x, y, w, h = self.bbox
        frame_width = self.video_handler.width
        frame_height = self.video_handler.height
        return (x < margin or y < margin or
                (x + w) > (frame_width - margin) or
                (y + h) > (frame_height - margin))

    def get_boundary_status(self) -> dict:
        if not self.bbox or not self.video_handler:
            return {'near_boundary': False, 'edges': [], 'min_distance': float('inf')}
        x, y, w, h = self.bbox
        frame_width = self.video_handler.width
        frame_height = self.video_handler.height
        margin = getattr(Parameters, 'BOUNDARY_MARGIN_PIXELS', 15)
        dist_left, dist_top = x, y
        dist_right = frame_width - (x + w)
        dist_bottom = frame_height - (y + h)
        edges_near = []
        if dist_left < margin: edges_near.append('left')
        if dist_top < margin: edges_near.append('top')
        if dist_right < margin: edges_near.append('right')
        if dist_bottom < margin: edges_near.append('bottom')
        min_distance = min(dist_left, dist_top, dist_right, dist_bottom)
        return {
            'near_boundary': len(edges_near) > 0,
            'edges': edges_near,
            'min_distance': max(0, min_distance),
            'distances': {'left': dist_left, 'top': dist_top,
                          'right': dist_right, 'bottom': dist_bottom},
            'margin': margin
        }

    def compute_boundary_confidence_penalty(self) -> float:
        boundary_status = self.get_boundary_status()
        if not boundary_status['near_boundary']:
            return 1.0
        min_distance = boundary_status['min_distance']
        margin = boundary_status['margin']
        if min_distance >= margin:
            return 1.0
        penalty = 0.5 + 0.5 * (min_distance / margin)
        return max(0.5, min(1.0, penalty))

    # =========================================================================
    # Visualization
    # =========================================================================

    def reinitialize_tracker(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        logger.info(f"Reinitializing tracker with bbox: {bbox}")
        self.start_tracking(frame, bbox)

    def draw_tracking(self, frame: np.ndarray, tracking_successful: bool = True) -> np.ndarray:
        if self.bbox and self.center and self.video_handler:
            if Parameters.TRACKED_BBOX_STYLE == 'fancy':
                self.draw_fancy_bbox(frame, tracking_successful)
            else:
                self.draw_normal_bbox(frame, tracking_successful)
            cv2.circle(frame, self.center, 5, (0, 255, 0), -1)
            if Parameters.DISPLAY_DEVIATIONS:
                self.print_normalized_center()
        return frame

    def draw_normal_bbox(self, frame: np.ndarray, tracking_successful: bool = True) -> None:
        p1 = (int(self.bbox[0]), int(self.bbox[1]))
        p2 = (int(self.bbox[0] + self.bbox[2]), int(self.bbox[1] + self.bbox[3]))
        color = (255, 0, 0) if tracking_successful else (0, 0, 255)
        cv2.rectangle(frame, p1, p2, color, 2)

    def draw_fancy_bbox(self, frame, tracking_successful: bool = True):
        if self.bbox is None or self.center is None:
            return frame
        color = (Parameters.FOLLOWER_ACTIVE_COLOR
                 if self.app_controller.following_active
                 else Parameters.FOLLOWER_INACTIVE_COLOR)
        p1 = (int(self.bbox[0]), int(self.bbox[1]))
        p2 = (int(self.bbox[0] + self.bbox[2]), int(self.bbox[1] + self.bbox[3]))
        center_x, center_y = self.center
        cv2.line(frame, (center_x - Parameters.CROSSHAIR_ARM_LENGTH, center_y),
                 (center_x + Parameters.CROSSHAIR_ARM_LENGTH, center_y),
                 color, Parameters.BBOX_LINE_THICKNESS)
        cv2.line(frame, (center_x, center_y - Parameters.CROSSHAIR_ARM_LENGTH),
                 (center_x, center_y + Parameters.CROSSHAIR_ARM_LENGTH),
                 color, Parameters.BBOX_LINE_THICKNESS)
        corner_points = [
            (p1, (p1[0] + Parameters.BBOX_CORNER_ARM_LENGTH, p1[1])),
            (p1, (p1[0], p1[1] + Parameters.BBOX_CORNER_ARM_LENGTH)),
            (p2, (p2[0] - Parameters.BBOX_CORNER_ARM_LENGTH, p2[1])),
            (p2, (p2[0], p2[1] - Parameters.BBOX_CORNER_ARM_LENGTH)),
            ((p1[0], p2[1]), (p1[0] + Parameters.BBOX_CORNER_ARM_LENGTH, p2[1])),
            ((p1[0], p2[1]), (p1[0], p2[1] - Parameters.BBOX_CORNER_ARM_LENGTH)),
            ((p2[0], p1[1]), (p2[0] - Parameters.BBOX_CORNER_ARM_LENGTH, p1[1])),
            ((p2[0], p1[1]), (p2[0], p1[1] + Parameters.BBOX_CORNER_ARM_LENGTH))
        ]
        for start, end in corner_points:
            cv2.line(frame, start, end, color, Parameters.BBOX_LINE_THICKNESS)
        height, width, _ = frame.shape
        cv2.line(frame, (p1[0], center_y), (0, center_y), color, Parameters.EXTENDED_LINE_THICKNESS)
        cv2.line(frame, (p2[0], center_y), (width, center_y), color, Parameters.EXTENDED_LINE_THICKNESS)
        cv2.line(frame, (center_x, p1[1]), (center_x, 0), color, Parameters.EXTENDED_LINE_THICKNESS)
        cv2.line(frame, (center_x, p2[1]), (center_x, height), color, Parameters.EXTENDED_LINE_THICKNESS)
        for point in [p1, p2, (p1[0], p2[1]), (p2[0], p1[1])]:
            cv2.circle(frame, point, Parameters.CORNER_DOT_RADIUS, color, -1)
        return frame

    def draw_estimate(self, frame: np.ndarray, tracking_successful: bool = True) -> np.ndarray:
        if self.estimator_enabled and self.position_estimator and self.video_handler:
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position:
                estimated_x, estimated_y = estimated_position[:2]
                color = (Parameters.ESTIMATED_POSITION_COLOR if tracking_successful
                         else Parameters.ESTIMATION_ONLY_COLOR)
                cv2.circle(frame, (int(estimated_x), int(estimated_y)), 5, color, -1)
        return frame

    # =========================================================================
    # Standardized TrackerOutput
    # =========================================================================

    def _get_velocity_from_estimator(self) -> Optional[Tuple[float, float]]:
        """Extract velocity from external estimator if available."""
        if (self.estimator_enabled and self.position_estimator
                and self.tracking_started and len(self.center_history) > 2):
            estimated_state = self.position_estimator.get_estimate()
            if estimated_state and len(estimated_state) >= 4:
                vel_x, vel_y = estimated_state[2], estimated_state[3]
                if (vel_x ** 2 + vel_y ** 2) ** 0.5 > 0.001:
                    return (vel_x, vel_y)
        return None

    def _build_output(self, tracker_algorithm: str,
                      extra_quality: Optional[Dict] = None,
                      extra_raw: Optional[Dict] = None,
                      extra_metadata: Optional[Dict] = None) -> TrackerOutput:
        """Build standardized TrackerOutput. Subclasses pass extras."""
        velocity = self._get_velocity_from_estimator()
        data_type = (TrackerDataType.VELOCITY_AWARE if velocity else
                     TrackerDataType.BBOX_CONFIDENCE if self.bbox else
                     TrackerDataType.POSITION_2D)

        quality_metrics = {
            'motion_consistency': self.compute_motion_confidence() if self.prev_center else 1.0,
            'failure_count': self.failure_count,
            'success_rate': (self.successful_frames / (self.frame_count + 1e-6)
                             if self.frame_count > 0 else 1.0),
        }
        if extra_quality:
            quality_metrics.update(extra_quality)

        raw_data = {
            'frame_count': self.frame_count,
            'successful_frames': self.successful_frames,
            'failed_frames': self.failed_frames,
            'avg_fps': (round(np.mean(self.fps_history[-30:]), 1)
                        if len(self.fps_history) >= 30 else 0.0),
        }
        if extra_raw:
            raw_data.update(extra_raw)

        metadata = {
            'tracker_class': self.__class__.__name__,
            'tracker_algorithm': tracker_algorithm,
            'center_pixel': self.center,
            'bbox_pixel': self.bbox,
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        return TrackerOutput(
            data_type=data_type,
            timestamp=time.time(),
            tracking_active=self.tracking_started,
            tracker_id=f"{tracker_algorithm}_{id(self)}",
            position_2d=self.normalized_center,
            bbox=self.bbox,
            normalized_bbox=self.normalized_bbox,
            confidence=self.confidence,
            velocity=velocity,
            quality_metrics=quality_metrics,
            raw_data=raw_data,
            metadata=metadata,
        )

    def get_output(self) -> TrackerOutput:
        return self._build_output(tracker_algorithm=self.__class__.__name__)

    def get_capabilities(self) -> Dict[str, Any]:
        return {
            'data_types': [TrackerDataType.POSITION_2D.value],
            'supports_confidence': True,
            'supports_velocity': bool(self.position_estimator),
            'supports_bbox': True,
            'supports_normalization': True,
            'estimator_available': bool(self.position_estimator),
            'multi_target': False,
            'real_time': True,
        }

    def get_legacy_data(self) -> Dict[str, Any]:
        return {
            'bounding_box': self.normalized_bbox,
            'center': self.normalized_center,
            'confidence': self.confidence,
            'tracker_started': self.tracking_started,
            'timestamp': time.time(),
        }

    # =========================================================================
    # Component Suppression
    # =========================================================================

    def is_detector_suppressed(self) -> bool:
        return getattr(self, 'suppress_detector', False)

    def is_predictor_suppressed(self) -> bool:
        return getattr(self, 'suppress_predictor', False)

    def get_suppression_status(self) -> Dict[str, bool]:
        return {
            'detector_suppressed': self.is_detector_suppressed(),
            'predictor_suppressed': self.is_predictor_suppressed(),
        }
