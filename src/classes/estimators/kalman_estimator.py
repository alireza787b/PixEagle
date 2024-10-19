# src/classes/estimators/kalman_estimator.py
# src/classes/estimators/kalman_estimator.py

import numpy as np
import logging
from filterpy.kalman import KalmanFilter
from .base_estimator import BaseEstimator
from classes.parameters import Parameters  # Ensure correct import path

logger = logging.getLogger(__name__)

class KalmanEstimator(BaseEstimator):
    def __init__(self):
        """
        Initializes the KalmanEstimator with a Kalman Filter configured for 2D position, velocity, and acceleration estimation.
        """
        # Initialize the Kalman Filter with 6 state variables (x, y, dx, dy, ddx, ddy) and 2 measurement variables (x, y)
        self.filter = KalmanFilter(dim_x=6, dim_z=2)
        self.filter.x = np.zeros((6, 1))  # State vector: [x, y, dx, dy, ddx, ddy]

        # Initial covariance matrix P
        initial_covariance = Parameters.ESTIMATOR_INITIAL_STATE_COVARIANCE
        self.filter.P = np.diag(initial_covariance)

        # Measurement function H: we measure only position (x, y)
        self.filter.H = np.array([
            [1, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0]
        ])

        # Measurement noise covariance R: assumes independent measurement noise for x and y
        self.measurement_noise_variance = Parameters.ESTIMATOR_MEASUREMENT_NOISE_VARIANCE
        self.filter.R = np.eye(2) * self.measurement_noise_variance

        # Process noise variance
        self.process_noise_variance = Parameters.ESTIMATOR_PROCESS_NOISE_VARIANCE

        # Default time step dt
        self.dt = 0.1
        self.update_F_and_Q(self.dt)

    def predict_only(self):
        """
        Performs only the predict step of the Kalman Filter without an update.
        """
        self.filter.predict()
        logger.debug("Kalman Filter prediction step executed without measurement update.")

    def update_F_and_Q(self, dt):
        """
        Updates the state transition matrix (F) and the process noise covariance matrix (Q) based on the new dt.

        Args:
            dt (float): Time step between the current and previous measurements.
        """
        # State transition matrix (constant acceleration model)
        dt2 = dt ** 2
        dt3 = dt ** 3
        dt4 = dt ** 4

        self.filter.F = np.array([
            [1, 0, dt, 0, dt2 / 2, 0],
            [0, 1, 0, dt, 0, dt2 / 2],
            [0, 0, 1, 0, dt, 0],
            [0, 0, 0, 1, 0, dt],
            [0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 1]
        ])

        # Process noise covariance matrix Q based on the standard constant acceleration model
        q = self.process_noise_variance

        Q = q * np.array([
            [dt4 / 4,      0,          dt3 / 2,    0,          dt2 / 2,    0],
            [0,            dt4 / 4,    0,          dt3 / 2,    0,          dt2 / 2],
            [dt3 / 2,      0,          dt2,        0,          dt,         0],
            [0,            dt3 / 2,    0,          dt2,        0,          dt],
            [dt2 / 2,      0,          dt,         0,          1,          0],
            [0,            dt2 / 2,    0,          dt,         0,          1]
        ])

        self.filter.Q = Q
        logger.debug(f"Updated F and Q matrices with dt = {dt}")

    def set_dt(self, dt):
        """
        Sets the time step (dt) and updates the filter's state transition matrix and process noise accordingly.

        Args:
            dt (float): The new time step to use.

        Raises:
            ValueError: If dt is non-positive.
        """
        if dt <= 0:
            raise ValueError("Time step (dt) must be a positive value.")

        self.dt = dt
        self.update_F_and_Q(dt)
        logger.debug(f"Time step updated to {dt}")

    def predict_and_update(self, measurement):
        """
        Performs the predict and update cycle of the Kalman Filter using the provided measurement.

        Args:
            measurement (list, tuple, or np.ndarray): The current measurement [x, y].

        Raises:
            ValueError: If the measurement is not a 2-element list, tuple, or array.
        """
        if not isinstance(measurement, (list, tuple, np.ndarray)) or len(measurement) != 2:
            raise ValueError("Measurement must be a list, tuple, or numpy array with two elements [x, y].")

        self.filter.predict()
        self.filter.update(np.array(measurement).reshape(2, 1))
        logger.debug(f"Kalman Filter predicted and updated with measurement: {measurement}")
        logger.debug(f"Post-update state estimate: {self.filter.x.flatten().tolist()}")
        logger.debug(f"Post-update covariance P: {self.filter.P}")

    def get_estimate(self) -> list:
        """
        Retrieves the current state estimate from the Kalman Filter.

        Returns:
            list: The estimated state [x, y, dx, dy, ddx, ddy].
        """
        estimate = self.filter.x.flatten().tolist()
        logger.debug(f"Current state estimate: {estimate}")
        return estimate

    def get_normalized_estimate(self, frame_width: int, frame_height: int) -> Optional[Tuple[float, float]]:
        """
        Returns the normalized estimated position based on frame dimensions.

        Normalization is done such that the center of the frame is (0,0),
        top-right is (1,1), and bottom-left is (-1,-1).

        Args:
            frame_width (int): Width of the video frame.
            frame_height (int): Height of the video frame.

        Returns:
            Optional[Tuple[float, float]]: Normalized (x, y) coordinates or None.
        """
        estimate = self.get_estimate()
        if not estimate or len(estimate) < 2:
            logging.warning("Estimate is not available or incomplete for normalization.")
            return None

        x, y = estimate[0], estimate[1]

        if frame_width <= 0 or frame_height <= 0:
            logging.warning("Invalid frame dimensions for normalization.")
            return None

        norm_x = (x - frame_width / 2) / (frame_width / 2)
        norm_y = (y - frame_height / 2) / (frame_height / 2)

        normalized_estimate = (norm_x, norm_y)
        logging.debug(f"Normalized estimate: {normalized_estimate}")

        return normalized_estimate

    def reset(self):
        """
        Resets the Kalman Filter to its initial state.
        """
        self.filter.x = np.zeros((6, 1))  # Reset state vector
        initial_covariance = Parameters.ESTIMATOR_INITIAL_STATE_COVARIANCE
        self.filter.P = np.diag(initial_covariance)  # Reset covariance matrix
        self.dt = 0.1
        self.update_F_and_Q(self.dt)
        logger.info("Kalman Filter state reset.")

    def is_estimate_reliable(self, uncertainty_threshold: float) -> bool:
        """
        Checks if the current estimate is reliable based on the trace of the covariance matrix.

        Args:
            uncertainty_threshold (float): The maximum acceptable uncertainty.

        Returns:
            bool: True if the estimate is reliable, False otherwise.
        """
        uncertainty = np.trace(self.filter.P)
        logger.debug(f"Current estimate uncertainty: {uncertainty}")
        return uncertainty < uncertainty_threshold
