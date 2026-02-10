# src/classes/kalman_box_tracker.py
"""
Kalman Filter for Bounding Box Tracking.

Standard linear Kalman filter using the constant-velocity model for
bounding box state estimation. This is the same model used by SORT,
DeepSORT, ByteTrack, and BoT-SORT — battle-tested across all major
multi-object tracking systems.

State vector: [cx, cy, s, r, vx, vy, vs]
  cx, cy  = bounding box center
  s       = area (width * height)
  r       = aspect ratio (width / height)  — assumed constant
  vx, vy  = center velocity
  vs      = area change rate

Measurement vector: [cx, cy, s, r]

Author: PixEagle Team
Date: 2025
"""

import numpy as np
import logging
from typing import Optional, Tuple


class KalmanBoxTracker:
    """
    Kalman filter state estimator for a single bounding box.

    Provides continuous position prediction during occlusion with proper
    uncertainty growth, and optimal state correction when measurements arrive.
    """

    def __init__(self, bbox: Tuple[int, int, int, int],
                 process_noise_scale: float = 1.0,
                 measurement_noise_scale: float = 1.0):
        """
        Initialize the Kalman filter with a bounding box measurement.

        Args:
            bbox: Initial bounding box (x1, y1, x2, y2)
            process_noise_scale: Scale factor for process noise Q
                                 (higher = trust model less, adapt faster)
            measurement_noise_scale: Scale factor for measurement noise R
                                     (higher = trust detections less, smoother)
        """
        # State dimension: 7 [cx, cy, s, r, vx, vy, vs]
        # Measurement dimension: 4 [cx, cy, s, r]
        self.dim_x = 7
        self.dim_z = 4

        # State transition matrix F (constant velocity model)
        # x(k+1) = F * x(k)
        self.F = np.eye(self.dim_x)
        self.F[0, 4] = 1.0  # cx += vx * dt (dt=1 frame)
        self.F[1, 5] = 1.0  # cy += vy * dt
        self.F[2, 6] = 1.0  # s  += vs * dt

        # Measurement matrix H (we observe cx, cy, s, r)
        self.H = np.zeros((self.dim_z, self.dim_x))
        self.H[0, 0] = 1.0  # cx
        self.H[1, 1] = 1.0  # cy
        self.H[2, 2] = 1.0  # s
        self.H[3, 3] = 1.0  # r

        # Process noise covariance Q
        # Tuned for typical object tracking at ~30 FPS
        self.Q = np.eye(self.dim_x)
        self.Q[0, 0] = 1.0    # cx position noise
        self.Q[1, 1] = 1.0    # cy position noise
        self.Q[2, 2] = 1.0    # area noise
        self.Q[3, 3] = 0.01   # aspect ratio (very stable)
        self.Q[4, 4] = 0.01   # vx velocity noise
        self.Q[5, 5] = 0.01   # vy velocity noise
        self.Q[6, 6] = 0.0001 # vs area change noise
        self.Q *= process_noise_scale

        # Measurement noise covariance R
        self.R = np.eye(self.dim_z)
        self.R[0, 0] = 1.0   # cx measurement noise
        self.R[1, 1] = 1.0   # cy measurement noise
        self.R[2, 2] = 10.0  # area measurement noise (more noisy)
        self.R[3, 3] = 10.0  # aspect ratio measurement noise
        self.R *= measurement_noise_scale

        # State estimate covariance P (initial uncertainty)
        self.P = np.eye(self.dim_x)
        self.P[0, 0] = 10.0   # cx uncertainty
        self.P[1, 1] = 10.0   # cy uncertainty
        self.P[2, 2] = 10.0   # area uncertainty
        self.P[3, 3] = 10.0   # aspect ratio uncertainty
        self.P[4, 4] = 1000.0  # vx — high uncertainty (unknown initial velocity)
        self.P[5, 5] = 1000.0  # vy
        self.P[6, 6] = 1000.0  # vs

        # Initialize state from first measurement
        measurement = self._bbox_to_measurement(bbox)
        self.x = np.zeros((self.dim_x, 1))
        self.x[:self.dim_z] = measurement.reshape(self.dim_z, 1)

        # Tracking metadata
        self.time_since_update = 0
        self.hit_count = 1
        self.age = 0

        logging.debug(f"[KalmanBoxTracker] Initialized with bbox={bbox}, "
                     f"process_noise={process_noise_scale}, measurement_noise={measurement_noise_scale}")

    def _bbox_to_measurement(self, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Convert (x1,y1,x2,y2) bbox to measurement vector [cx, cy, s, r]."""
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        cx = x1 + w / 2.0
        cy = y1 + h / 2.0
        s = w * h  # area
        r = w / max(h, 1e-6)  # aspect ratio
        return np.array([cx, cy, s, r])

    def _state_to_bbox(self, state: np.ndarray) -> Tuple[int, int, int, int]:
        """Convert state vector [cx, cy, s, r, ...] to (x1,y1,x2,y2) bbox."""
        cx = state[0, 0]
        cy = state[1, 0]
        s = max(state[2, 0], 1.0)  # area must be positive
        r = max(state[3, 0], 0.01)  # aspect ratio must be positive

        w = np.sqrt(s * r)
        h = s / max(w, 1e-6)

        x1 = int(cx - w / 2.0)
        y1 = int(cy - h / 2.0)
        x2 = int(cx + w / 2.0)
        y2 = int(cy + h / 2.0)

        return (x1, y1, x2, y2)

    def predict(self) -> Tuple[int, int, int, int]:
        """
        Advance state by one frame using the motion model.

        Returns:
            Predicted bounding box (x1, y1, x2, y2)
        """
        # Prevent negative area
        if self.x[2, 0] + self.x[6, 0] <= 0:
            self.x[6, 0] = 0.0

        # State prediction: x = F * x
        self.x = self.F @ self.x

        # Covariance prediction: P = F * P * F^T + Q
        self.P = self.F @ self.P @ self.F.T + self.Q

        self.age += 1
        self.time_since_update += 1

        return self._state_to_bbox(self.x)

    def update(self, bbox: Tuple[int, int, int, int]):
        """
        Correct state with a new measurement (detection).

        Args:
            bbox: Detected bounding box (x1, y1, x2, y2)
        """
        measurement = self._bbox_to_measurement(bbox)
        z = measurement.reshape(self.dim_z, 1)

        # Innovation (measurement residual): y = z - H * x
        y = z - self.H @ self.x

        # Innovation covariance: S = H * P * H^T + R
        S = self.H @ self.P @ self.H.T + self.R

        # Kalman gain: K = P * H^T * S^(-1)
        try:
            K = self.P @ self.H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            logging.warning("[KalmanBoxTracker] Singular matrix in Kalman gain computation, skipping update")
            return

        # State update: x = x + K * y
        self.x = self.x + K @ y

        # Covariance update: P = (I - K * H) * P
        I = np.eye(self.dim_x)
        self.P = (I - K @ self.H) @ self.P

        self.time_since_update = 0
        self.hit_count += 1

    def get_state(self) -> Tuple[int, int, int, int]:
        """
        Get current estimated bounding box.

        Returns:
            Estimated bounding box (x1, y1, x2, y2)
        """
        return self._state_to_bbox(self.x)

    def get_predicted_center(self) -> Tuple[int, int]:
        """
        Get current estimated center position.

        Returns:
            Estimated center (cx, cy)
        """
        return (int(self.x[0, 0]), int(self.x[1, 0]))

    def get_velocity(self) -> Tuple[float, float]:
        """
        Get estimated velocity (pixels per frame).

        Returns:
            Velocity (vx, vy) in pixels per frame
        """
        return (float(self.x[4, 0]), float(self.x[5, 0]))

    def get_velocity_magnitude(self) -> float:
        """
        Get speed (pixels per frame).

        Returns:
            Speed magnitude
        """
        vx, vy = self.get_velocity()
        return (vx ** 2 + vy ** 2) ** 0.5

    def get_position_uncertainty(self) -> float:
        """
        Get position uncertainty (trace of position covariance).

        Higher values = less certain about position.

        Returns:
            Position uncertainty scalar
        """
        return float(self.P[0, 0] + self.P[1, 1])

    def predict_n_frames(self, n: int) -> Tuple[int, int, int, int]:
        """
        Predict position N frames ahead WITHOUT modifying internal state.

        Args:
            n: Number of frames to predict ahead

        Returns:
            Predicted bounding box (x1, y1, x2, y2)
        """
        # Build F^n for multi-step prediction
        state = self.x.copy()
        F = self.F.copy()

        for _ in range(n):
            # Prevent negative area
            if state[2, 0] + state[6, 0] <= 0:
                state[6, 0] = 0.0
            state = F @ state

        return self._state_to_bbox(state)

    def reset(self, bbox: Tuple[int, int, int, int]):
        """
        Reset the filter with a new measurement (after re-identification).

        Args:
            bbox: New bounding box measurement
        """
        measurement = self._bbox_to_measurement(bbox)
        self.x[:self.dim_z] = measurement.reshape(self.dim_z, 1)
        # Keep velocity estimates, reduce uncertainty
        self.P[0, 0] = 10.0
        self.P[1, 1] = 10.0
        self.P[2, 2] = 10.0
        self.P[3, 3] = 10.0
        self.time_since_update = 0
        self.hit_count += 1
        logging.debug(f"[KalmanBoxTracker] Reset with bbox={bbox}")
