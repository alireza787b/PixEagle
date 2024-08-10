import numpy as np
import time
import logging
from filterpy.kalman import KalmanFilter
from filterpy.common import Q_discrete_white_noise

logger = logging.getLogger(__name__)

class PositionEstimator:
    def __init__(self):
        """
        Initializes the PositionEstimator with a Kalman Filter configured for 2D position estimation.
        """
        # Initialize the Kalman Filter with 4 state dimensions (x, y, dx, dy) and 2 measurement dimensions (x, y)
        self.filter = KalmanFilter(dim_x=4, dim_z=2)
        self.filter.x = np.zeros((4, 1))  # Initial state vector: [x, y, dx, dy]
        self.filter.P *= 100  # Initial uncertainty (covariance matrix)
        
        # Measurement function (only position is measured, not velocity)
        self.filter.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
        
        # Measurement noise covariance matrix
        self.filter.R = np.eye(2) * 5  # Adjust this value based on the measurement noise characteristics
        
        # Default time step (dt), updated dynamically in use
        self.dt = 0.1
        self.update_F_and_Q(self.dt)

        # Timestamp tracking for dynamic dt updates (if needed)
        self.last_timestamp = None

    def update_F_and_Q(self, dt):
        """
        Updates the state transition matrix (F) and the process noise covariance matrix (Q) based on the new dt.

        Args:
            dt (float): Time step between the current and previous measurements.
        """
        self.filter.F = np.array([[1, 0, dt, 0],
                                  [0, 1, 0, dt],
                                  [0, 0, 1, 0],
                                  [0, 0, 0, 1]])

        self.filter.Q = Q_discrete_white_noise(dim=4, dt=dt, var=0.1)
        logger.debug(f"Updated F and Q matrices with dt = {dt}")

    def set_dt(self, dt):
        """
        Sets the time step (dt) and updates the filter's state transition matrix and process noise accordingly.

        Args:
            dt (float): The new time step to use, typically the time elapsed between frames.

        Raises:
            ValueError: If dt is non-positive.
        """
        if dt <= 0:
            raise ValueError("Time step (dt) must be a positive value.")
        
        self.dt = dt
        self.update_F_and_Q(dt)
        logger.info(f"Time step updated to {dt}")

    def predict_and_update(self, measurement):
        """
        Performs the predict and update cycle of the Kalman Filter using the provided measurement.

        Args:
            measurement (list or np.ndarray): The current measurement [x, y].

        Raises:
            ValueError: If the measurement is not a 2-element list or array.
        """
        if not isinstance(measurement, (list, np.ndarray)) or len(measurement) != 2:
            raise ValueError("Measurement must be a list or numpy array with two elements [x, y].")

        self.filter.predict()
        self.filter.update(np.array(measurement).reshape(2, 1))
        logger.debug(f"Kalman Filter updated with measurement: {measurement}")

    def get_estimate(self):
        """
        Retrieves the current state estimate from the Kalman Filter.

        Returns:
            list: The estimated state [x, y, dx, dy].
        """
        estimate = self.filter.x.flatten().tolist()
        logger.debug(f"Current state estimate: {estimate}")
        return estimate
