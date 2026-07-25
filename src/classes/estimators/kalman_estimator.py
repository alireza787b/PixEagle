# src/classes/estimators/kalman_estimator.py

"""
KalmanEstimator Module
----------------------

This module implements the `KalmanEstimator` class, which provides a Kalman Filter-based estimator for 2D position, velocity, and acceleration estimation in the context of aerial target tracking.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: October 2024
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The `KalmanEstimator` uses a constant acceleration model to predict and update the state of a tracked object. The Kalman Filter is a recursive optimal estimator that fuses noisy measurements to produce estimates of unknown variables that are more accurate than those based on a single measurement alone.

Purpose:
--------
In aerial target tracking, the Kalman Filter helps in smoothing out the noisy measurements obtained from the tracker, providing a more accurate and stable estimate of the target's position and motion. This is particularly useful when the measurements are noisy or when the target exhibits unpredictable motion due to acceleration.

Key Features:
-------------
- **State Vector**: The state vector includes position `(x, y)`, velocity `(dx, dy)`, and acceleration `(ddx, ddy)`.
- **Measurement Model**: Only position measurements `(x, y)` are used, as velocity and acceleration are not directly measured.
- **Process and Measurement Noise Covariances**: Tunable parameters that affect the filter's responsiveness and smoothness.
- **Normalization**: Provides normalized estimates suitable for control inputs that require normalized coordinates.

Usage:
------
The `KalmanEstimator` is integrated into the tracking system and can be enabled or disabled via parameters. It is used to improve the robustness and accuracy of the tracking by providing filtered estimates of the target's position.

Disabling the Estimator:
------------------------
To disable the estimator, set the parameter `USE_ESTIMATOR` to `False` in the `Parameters` class. This will cause the system to rely solely on the raw measurements from the tracker.

Tuning Parameters:
------------------
- **ESTIMATOR_PROCESS_NOISE_VARIANCE**: Higher values make the filter more responsive to changes but may introduce noise.
- **ESTIMATOR_MEASUREMENT_NOISE_VARIANCE**: Higher values make the filter trust the measurements less, leading to smoother estimates but potential lag.
- **ESTIMATOR_INITIAL_STATE_COVARIANCE**: Determines the initial uncertainty of the state estimates.

Integration:
------------
The estimator is integrated into the tracking pipeline. The tracker provides measurements to the estimator, which then produces filtered estimates. The `AppController` uses these estimates for control decisions, such as commanding the UAV to follow the target.

Extending and Building New Estimators:
--------------------------------------
To build a new estimator:
1. Create a new class that inherits from `BaseEstimator`.
2. Implement all abstract methods defined in `BaseEstimator`.
3. Add the new estimator to the `estimator_factory.py` for easy creation.

Notes:
------
- Ensure that the time step `dt` is updated accurately to reflect the actual time between measurements.
- The estimator assumes a constant acceleration model; if the target's motion model differs significantly, consider modifying the state transition matrix accordingly.
- This estimator is part of the PixEagle project developed by Alireza Ghaderi in October 2024. For more information, visit the project repository or contact via LinkedIn.

References:
-----------
- R. E. Kalman, "A New Approach to Linear Filtering and Prediction Problems," Transactions of the ASME–Journal of Basic Engineering, 1960.
- G. Welch and G. Bishop, "An Introduction to the Kalman Filter," UNC-Chapel Hill, 1995.

"""

from typing import Optional, Tuple
import numpy as np
import logging
from filterpy.kalman import KalmanFilter
from .base_estimator import BaseEstimator
from classes.parameters import Parameters  # Ensure correct import path

logger = logging.getLogger(__name__)

class KalmanEstimator(BaseEstimator):
    """
    KalmanEstimator implements a Kalman Filter for estimating the position, velocity, and acceleration of a target in 2D space.

    The filter uses a constant acceleration model and processes position measurements to produce smoothed estimates.

    Attributes:
        filter (KalmanFilter): The Kalman Filter instance.
        dt (float): Time step between measurements.
        measurement_noise_variance (float): Variance of the measurement noise.
        process_noise_variance (float): Variance of the process noise.
    """

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

        self.min_dt = self._positive_config(
            'ESTIMATOR_MIN_DT_SECONDS', 0.001
        )
        self.max_dt = max(
            self.min_dt,
            self._positive_config('ESTIMATOR_MAX_DT_SECONDS', 0.25),
        )
        self.max_prediction_seconds = self._positive_config(
            'ESTIMATOR_MAX_PREDICTION_SECONDS', 1.0
        )
        self.initialized = False
        self.prediction_age_seconds = 0.0

        # Replaced by the measured frame interval before normal updates.
        self.dt = min(max(0.1, self.min_dt), self.max_dt)
        self.update_F_and_Q(self.dt)

    @staticmethod
    def _positive_config(name: str, fallback: float) -> float:
        try:
            value = float(getattr(Parameters, name, fallback))
        except (TypeError, ValueError):
            return fallback
        return value if np.isfinite(value) and value > 0.0 else fallback

    @staticmethod
    def _coerce_measurement(measurement) -> np.ndarray:
        if not isinstance(measurement, (list, tuple, np.ndarray)):
            raise ValueError(
                "Measurement must be a list, tuple, or numpy array with two elements [x, y]."
            )
        values = np.asarray(measurement, dtype=float).reshape(-1)
        if values.size != 2 or not np.all(np.isfinite(values)):
            raise ValueError("Measurement must contain two finite values [x, y].")
        return values

    def initialize(self, measurement) -> None:
        """Seed position exactly at a newly selected target."""
        values = self._coerce_measurement(measurement)
        self.reset()
        self.filter.x[:2, 0] = values
        self.initialized = True
        logger.debug(
            "Kalman Filter initialized at measurement (%s, %s).",
            values[0],
            values[1],
        )

    def is_initialized(self) -> bool:
        return self.initialized

    def predict_only(self) -> bool:
        """
        Performs only the predict step of the Kalman Filter without an update.

        This is used when a measurement is not available, allowing the filter to propagate the state estimate based on the model.
        """
        if not self.initialized:
            return False
        if self.prediction_age_seconds + self.dt > self.max_prediction_seconds:
            logger.debug(
                "Kalman prediction horizon reached at %.3fs.",
                self.prediction_age_seconds,
            )
            return False
        self.filter.predict()
        self.prediction_age_seconds += self.dt
        logger.debug("Kalman Filter prediction step executed without measurement update.")
        return True

    def update_F_and_Q(self, dt):
        """
        Updates the state transition matrix (F) and the process noise covariance matrix (Q) based on the new dt.

        Args:
            dt (float): Time step between the current and previous measurements.

        The state transition matrix F models how the state evolves from one time step to the next.
        The process noise covariance Q represents the uncertainty in the model, particularly due to acceleration.

        For a constant acceleration model:
            - Position changes according to velocity and acceleration.
            - Velocity changes according to acceleration.
            - Acceleration is assumed to be constant (but with some process noise).

        The matrices are derived based on standard motion equations with constant acceleration.
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
        # logger.debug(f"Updated F and Q matrices with dt = {dt}")

    def set_dt(self, dt):
        """
        Sets the time step (dt) and updates the filter's state transition matrix and process noise accordingly.

        Args:
            dt (float): The new time step to use.

        Raises:
            ValueError: If dt is non-positive.

        It's important to update dt whenever the time between measurements changes to ensure accurate predictions.
        """
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError("Time step (dt) must be a positive value.")

        self.dt = min(max(float(dt), self.min_dt), self.max_dt)
        self.update_F_and_Q(self.dt)
        # logger.debug(f"Time step updated to {dt}")

    def predict_and_update(self, measurement):
        """
        Performs the predict and update cycle of the Kalman Filter using the provided measurement.

        Args:
            measurement (list, tuple, or np.ndarray): The current measurement [x, y].

        Raises:
            ValueError: If the measurement is not a 2-element list, tuple, or array.

        The predict step uses the state transition model to predict the next state.
        The update step incorporates the new measurement to refine the state estimate.
        """
        values = self._coerce_measurement(measurement)
        if not self.initialized:
            self.initialize(values)
            return

        self.filter.predict()
        self.filter.update(values.reshape(2, 1))
        self.prediction_age_seconds = 0.0
        # logger.debug(f"Kalman Filter predicted and updated with measurement: {measurement}")
        # logger.debug(f"Post-update state estimate: {self.filter.x.flatten().tolist()}")
        # logger.debug(f"Post-update covariance P: {self.filter.P}")

    def get_estimate(self) -> Optional[list]:
        """
        Retrieves the current state estimate from the Kalman Filter.

        Returns:
            list: The estimated state [x, y, dx, dy, ddx, ddy].

        The estimate includes position, velocity, and acceleration components.
        """
        if not self.initialized:
            return None
        estimate = self.filter.x.flatten().tolist()
        # logger.debug(f"Current state estimate: {estimate}")
        return estimate

    def get_normalized_estimate(self, frame_width: int, frame_height: int) -> Optional[Tuple[float, float]]:
        """
        Returns the normalized estimated position based on frame dimensions.

        Normalization follows image coordinates: center is (0, 0), top-left is
        (-1, -1), bottom-right is (1, 1), and y increases downward.

        Args:
            frame_width (int): Width of the video frame.
            frame_height (int): Height of the video frame.

        Returns:
            Optional[Tuple[float, float]]: Normalized (x, y) coordinates or None.

        This is useful for control inputs that require normalized coordinates, such as sending commands to a UAV.
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
        # logger.debug(f"Normalized estimate: {normalized_estimate}")

        return normalized_estimate

    def reset(self):
        """
        Resets the Kalman Filter to its initial state.

        This can be used when reinitializing tracking or when the filter's state becomes unreliable.
        """
        self.filter.x = np.zeros((6, 1))  # Reset state vector
        initial_covariance = Parameters.ESTIMATOR_INITIAL_STATE_COVARIANCE
        self.filter.P = np.diag(initial_covariance)  # Reset covariance matrix
        self.initialized = False
        self.prediction_age_seconds = 0.0
        self.dt = min(max(0.1, self.min_dt), self.max_dt)
        self.update_F_and_Q(self.dt)
        logger.info("Kalman Filter state reset.")

    def is_estimate_reliable(self, uncertainty_threshold: float) -> bool:
        """
        Checks if the current estimate is reliable based on the trace of the covariance matrix.

        Args:
            uncertainty_threshold (float): The maximum acceptable uncertainty.

        Returns:
            bool: True if the estimate is reliable, False otherwise.

        A high uncertainty indicates that the filter's estimates may not be trustworthy, possibly due to lack of recent measurements.
        """
        if not self.initialized:
            return False
        uncertainty = np.trace(self.filter.P)
        logger.debug(f"Current estimate uncertainty: {uncertainty}")
        return uncertainty < uncertainty_threshold

# Additional Notes:
# -----------------
# - To disable the estimator, set `USE_ESTIMATOR: false` in Parameters config.yaml.
# - When the estimator is disabled, the system will use raw measurements from the tracker.
# - The estimator is designed to be modular; new estimators can be added by implementing the `BaseEstimator` interface.
# - Ensure that the `filterpy` library is installed, as it provides the Kalman Filter implementation used here.
