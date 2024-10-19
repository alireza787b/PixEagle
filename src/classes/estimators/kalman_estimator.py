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
        Initializes the KalmanEstimator with a Kalman Filter configured for 2D position estimation.
        """
        # Initialize the Kalman Filter
        self.filter = KalmanFilter(dim_x=4, dim_z=2)
        self.filter.x = np.zeros((4, 1))  # State vector: [x, y, dx, dy]

        # Initial covariance matrix P
        initial_covariance = Parameters.ESTIMATOR_INITIAL_STATE_COVARIANCE
        self.filter.P = np.diag(initial_covariance)

        # Measurement function H
        self.filter.H = np.array([[1, 0, 0, 0],
                                  [0, 1, 0, 0]])

        # Measurement noise covariance R
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
        # State transition matrix (constant velocity model)
        self.filter.F = np.array([[1, 0, dt, 0],
                                  [0, 1, 0, dt],
                                  [0, 0, 1,  0],
                                  [0, 0, 0,  1]])

        # Process noise covariance matrix
        q = self.process_noise_variance

        dt2 = dt ** 2
        dt3 = dt ** 3

        q11 = dt3 / 3
        q13 = dt2 / 2
        q31 = dt2 / 2
        q33 = dt

        Q = q * np.array([[q11,   0,     q13,   0],
                          [0,     q11,   0,     q13],
                          [q31,   0,     q33,   0],
                          [0,     q31,   0,     q33]])

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

    def get_estimate(self):
        """
        Retrieves the current state estimate from the Kalman Filter.

        Returns:
            list: The estimated state [x, y, dx, dy].
        """
        estimate = self.filter.x.flatten().tolist()
        logger.debug(f"Current state estimate: {estimate}")
        return estimate

    def reset(self):
        """
        Resets the Kalman Filter to its initial state.
        """
        self.filter.x = np.zeros((4, 1))  # Reset state vector
        initial_covariance = Parameters.ESTIMATOR_INITIAL_STATE_COVARIANCE
        self.filter.P = np.diag(initial_covariance)  # Reset covariance matrix
        self.dt = 0.1
        self.update_F_and_Q(self.dt)
        logger.info("Kalman Filter state reset.")

    def is_estimate_reliable(self, uncertainty_threshold):
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
