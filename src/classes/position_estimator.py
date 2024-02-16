import numpy as np
import time
from filterpy.kalman import KalmanFilter
from filterpy.common import Q_discrete_white_noise

class PositionEstimator:
    def __init__(self):
        # Initial state vector and covariance
        self.filter = KalmanFilter(dim_x=4, dim_z=2)
        self.filter.x = np.zeros((4, 1))  # Initial state [x, y, dx, dy]
        self.filter.P *= 100  # Initial uncertainty
        
        # Measurement function
        self.filter.H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]])
        
        # Measurement noise
        self.filter.R = np.eye(2) * 5  # Adjust based on measurement noise characteristics
        
        # Initial dt setup
        self.dt = 1.0  # Default dt, should be updated dynamically based on actual frame intervals
        self.update_F_and_Q(self.dt)

        # Last update timestamp for internal use, not necessary if dt is externally managed
        self.last_timestamp = None

    def update_F_and_Q(self, dt):
        """
        Updates the state transition matrix (F) and the process noise (Q) based on the new dt value.

        Args:
            dt (float): Time step between the current and previous measurement.
        """
        # State transition matrix update with new dt
        self.filter.F = np.array([[1, 0, dt, 0],
                                  [0, 1, 0, dt],
                                  [0, 0, 1, 0],
                                  [0, 0, 0, 1]])
        # Process noise update with new dt
        self.filter.Q = Q_discrete_white_noise(dim=4, dt=dt, var=0.1)

    def set_dt(self, dt):
        """
        Dynamically sets the time step (dt) used in the filter's predictions and updates.

        Args:
            dt (float): The new time step to use, typically calculated as the elapsed time between frames.
        """
        self.dt = dt
        self.update_F_and_Q(dt)

    def predict_and_update(self, measurement):
        """
        Combines prediction and measurement update steps of the Kalman Filter.

        Args:
            measurement (list or np.ndarray): The current measurement [x, y].
        """
        # Predict the next state with the updated dt
        self.filter.predict()
        # Update the filter with the new measurement
        self.filter.update(np.array(measurement).reshape(2, 1))

    def get_estimate(self):
        """
        Retrieves the current state estimate from the filter.

        Returns:
            list: The estimated state [x, y, dx, dy], converted to a list for easier handling.
        """
        return self.filter.x.flatten().tolist()
