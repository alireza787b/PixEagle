# src/classes/motion_predictor.py
"""
Motion Predictor for SmartTracker Occlusion Handling.

Provides velocity-based motion prediction to estimate object position
during brief occlusions (1-5 frames). Uses exponential moving average
for velocity smoothing.

Author: PixEagle Team
Date: 2025
"""

import time
from collections import deque
from typing import Optional, Tuple
import logging


class MotionPredictor:
    """
    Predicts object motion during temporary tracking loss.

    Uses velocity-based linear prediction with EMA smoothing to estimate
    where the object will be during brief occlusions.
    """

    def __init__(self, history_size: int = 5, velocity_alpha: float = 0.7):
        """
        Initialize the motion predictor.

        Args:
            history_size: Number of previous positions to store
            velocity_alpha: EMA smoothing factor for velocity (0-1)
                           Higher = more responsive, Lower = more stable
        """
        self.history_size = history_size
        self.velocity_alpha = velocity_alpha

        # Position history: deque of (bbox, timestamp) tuples
        self.position_history = deque(maxlen=history_size)

        # Smoothed velocity (pixels/second)
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.velocity_w = 0.0  # Width change rate
        self.velocity_h = 0.0  # Height change rate

        # Last update time
        self.last_update_time = 0.0

        logging.info(f"[MotionPredictor] Initialized with history_size={history_size}, "
                    f"velocity_alpha={velocity_alpha}")

    def update(self, bbox: Tuple[int, int, int, int], timestamp: float):
        """
        Update motion history with new detection.

        Args:
            bbox: Bounding box (x1, y1, x2, y2)
            timestamp: Detection timestamp
        """
        # Add to history
        self.position_history.append((bbox, timestamp))
        self.last_update_time = timestamp

        # Compute velocity if we have enough history
        if len(self.position_history) >= 2:
            self._update_velocity()

        logging.debug(f"[MotionPredictor] Updated: bbox={bbox}, velocity=({self.velocity_x:.1f}, {self.velocity_y:.1f}) px/s")

    def _update_velocity(self):
        """
        Compute smoothed velocity from position history using EMA.
        """
        if len(self.position_history) < 2:
            return

        # Get last two positions
        (prev_bbox, prev_time) = self.position_history[-2]
        (curr_bbox, curr_time) = self.position_history[-1]

        # Compute time delta
        dt = curr_time - prev_time
        if dt <= 0:
            return

        # Compute instantaneous velocity (center position)
        prev_cx = (prev_bbox[0] + prev_bbox[2]) / 2
        prev_cy = (prev_bbox[1] + prev_bbox[3]) / 2
        curr_cx = (curr_bbox[0] + curr_bbox[2]) / 2
        curr_cy = (curr_bbox[1] + curr_bbox[3]) / 2

        instant_vx = (curr_cx - prev_cx) / dt
        instant_vy = (curr_cy - prev_cy) / dt

        # Compute size change velocity
        prev_w = prev_bbox[2] - prev_bbox[0]
        prev_h = prev_bbox[3] - prev_bbox[1]
        curr_w = curr_bbox[2] - curr_bbox[0]
        curr_h = curr_bbox[3] - curr_bbox[1]

        instant_vw = (curr_w - prev_w) / dt
        instant_vh = (curr_h - prev_h) / dt

        # Apply EMA smoothing
        alpha = self.velocity_alpha
        self.velocity_x = alpha * instant_vx + (1 - alpha) * self.velocity_x
        self.velocity_y = alpha * instant_vy + (1 - alpha) * self.velocity_y
        self.velocity_w = alpha * instant_vw + (1 - alpha) * self.velocity_w
        self.velocity_h = alpha * instant_vh + (1 - alpha) * self.velocity_h

    def predict_bbox(self, frames_ahead: int, fps: float = 30.0) -> Optional[Tuple[int, int, int, int]]:
        """
        Predict bounding box N frames into the future.

        Args:
            frames_ahead: Number of frames to predict ahead
            fps: Frames per second (for time calculation)

        Returns:
            Predicted bbox (x1, y1, x2, y2) or None if not enough history
        """
        if len(self.position_history) == 0:
            return None

        # Get last known position
        last_bbox, last_time = self.position_history[-1]
        x1, y1, x2, y2 = last_bbox

        # Compute prediction time delta
        dt = frames_ahead / fps

        # Predict center position
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        pred_cx = cx + self.velocity_x * dt
        pred_cy = cy + self.velocity_y * dt

        # Predict size
        w = x2 - x1
        h = y2 - y1
        pred_w = max(10, w + self.velocity_w * dt)  # Minimum width 10px
        pred_h = max(10, h + self.velocity_h * dt)  # Minimum height 10px

        # Convert back to bbox format
        pred_x1 = int(pred_cx - pred_w / 2)
        pred_y1 = int(pred_cy - pred_h / 2)
        pred_x2 = int(pred_cx + pred_w / 2)
        pred_y2 = int(pred_cy + pred_h / 2)

        logging.debug(f"[MotionPredictor] Predicted {frames_ahead} frames ahead: "
                     f"({pred_x1}, {pred_y1}, {pred_x2}, {pred_y2})")

        return (pred_x1, pred_y1, pred_x2, pred_y2)

    def get_velocity_magnitude(self) -> float:
        """
        Get the current velocity magnitude (pixels/second).

        Returns:
            Velocity magnitude (scalar speed)
        """
        return (self.velocity_x ** 2 + self.velocity_y ** 2) ** 0.5

    def is_moving(self, threshold: float = 5.0) -> bool:
        """
        Check if object is moving faster than threshold.

        Args:
            threshold: Velocity threshold in pixels/second

        Returns:
            True if object is moving above threshold
        """
        return self.get_velocity_magnitude() > threshold

    def reset(self):
        """
        Reset predictor state (call when tracking is cleared).
        """
        self.position_history.clear()
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.velocity_w = 0.0
        self.velocity_h = 0.0
        self.last_update_time = 0.0
        logging.debug("[MotionPredictor] Reset")

    def get_state(self) -> dict:
        """
        Get current predictor state for debugging.

        Returns:
            Dictionary with velocity and history info
        """
        return {
            'velocity_x': self.velocity_x,
            'velocity_y': self.velocity_y,
            'velocity_w': self.velocity_w,
            'velocity_h': self.velocity_h,
            'velocity_magnitude': self.get_velocity_magnitude(),
            'history_length': len(self.position_history),
            'last_update_time': self.last_update_time,
            'is_moving': self.is_moving()
        }
