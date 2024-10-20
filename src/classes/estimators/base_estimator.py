# src/classes/estimators/base_estimator.py

"""
BaseEstimator Module
--------------------

This module defines the abstract base class `BaseEstimator` for all estimators used in the tracking system.

Purpose:
--------
The `BaseEstimator` class provides an interface that all concrete estimator classes must implement. This ensures consistency and allows for easy integration and substitution of different estimation algorithms.

Key Methods:
------------
- `predict_and_update(measurement)`: Performs the prediction and update steps using the provided measurement.
- `get_estimate()`: Retrieves the current state estimate.
- `reset()`: Resets the estimator to its initial state.
- `get_normalized_estimate(frame_width, frame_height)`: Returns the normalized estimated position based on frame dimensions.

Extending the Estimator:
------------------------
To create a new estimator:
1. Subclass `BaseEstimator`.
2. Implement all abstract methods.
3. Add the new estimator to `estimator_factory.py` for easy creation and integration.

Notes:
------
- The interface enforces that all estimators provide normalized outputs, which is essential for consistent control inputs.
- By using an abstract base class, the system is flexible and can accommodate various estimation techniques (e.g., particle filters, extended Kalman filters).
- This design promotes modularity and scalability within the PixEagle project.

"""

from abc import ABC, abstractmethod
from typing import Optional, Tuple

class BaseEstimator(ABC):
    """
    Abstract Base Class for Estimators

    Defines the interface and common methods that all estimators must implement.
    """

    @abstractmethod
    def predict_and_update(self, measurement):
        """
        Performs the predict and update steps of the estimator using the provided measurement.

        Args:
            measurement (list, tuple, or np.ndarray): The current measurement [x, y].

        Raises:
            ValueError: If the measurement is not valid.

        This method should handle the core estimation logic, updating the internal state based on the measurement.
        """
        pass

    @abstractmethod
    def get_estimate(self) -> Optional[list]:
        """
        Retrieves the current state estimate from the estimator.

        Returns:
            Optional[list]: The estimated state vector or None if not available.
        """
        pass

    @abstractmethod
    def reset(self):
        """
        Resets the estimator to its initial state.

        This method should reinitialize all internal variables and states.
        """
        pass

    @abstractmethod
    def get_normalized_estimate(self, frame_width: int, frame_height: int) -> Optional[Tuple[float, float]]:
        """
        Returns the normalized estimated position based on frame dimensions.

        Args:
            frame_width (int): Width of the video frame.
            frame_height (int): Height of the video frame.

        Returns:
            Optional[Tuple[float, float]]: Normalized (x, y) coordinates or None.
        """
        pass
