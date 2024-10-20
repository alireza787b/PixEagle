# src/classes/estimators/estimator_factory.py

"""
Estimator Factory Module
------------------------

This module provides a factory function `create_estimator` to instantiate estimator objects based on a specified type.

Purpose:
--------
The factory pattern allows for the creation of estimator instances without exposing the creation logic to the client and refers to the newly created object using a common interface.

Usage:
------
To create an estimator:
```python
estimator = create_estimator(Parameters.ESTIMATOR_TYPE)
```

Notes:
------
- Supported estimator types should be added to the factory function.
- If the estimator is disabled or an unrecognized type is specified, the function returns `None`.
- This approach promotes flexibility and scalability within the PixEagle project.

"""

from classes.estimators.kalman_estimator import KalmanEstimator

def create_estimator(estimator_type):
    """
    Factory function to create an estimator instance based on the specified type.

    Args:
        estimator_type (str): The type of estimator to create (e.g., "Kalman").

    Returns:
        BaseEstimator or None: An instance of the requested estimator, or None if the type is unrecognized.

    Usage:
        estimator = create_estimator("Kalman")
    """
    if estimator_type == "Kalman":
        return KalmanEstimator()
    else:
        return None  # Return None if estimator is disabled or type is unrecognized
