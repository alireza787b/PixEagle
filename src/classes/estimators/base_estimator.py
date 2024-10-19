# src/classes/estimators/base_estimator.py

from abc import ABC, abstractmethod
from typing import Optional, Tuple

class BaseEstimator(ABC):
    @abstractmethod
    def predict_and_update(self, measurement):
        """
        Performs the predict and update steps of the Kalman Filter using the provided measurement.

        Args:
            measurement (list, tuple, or np.ndarray): The current measurement [x, y].

        Raises:
            ValueError: If the measurement is not a 2-element list, tuple, or array.
        """
        pass

    @abstractmethod
    def get_estimate(self) -> Optional[list]:
        """
        Retrieves the current state estimate from the Kalman Filter.

        Returns:
            Optional[list]: The estimated state vector or None if not available.
        """
        pass

    @abstractmethod
    def reset(self):
        """
        Resets the Kalman Filter to its initial state.
        """
        pass

    @abstractmethod
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
        pass
