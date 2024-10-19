# src/classes/estimators/estimator_factory.py
from classes.estimators.kalman_estimator import KalmanEstimator

def create_estimator(estimator_type):
    if estimator_type == "Kalman":
        return KalmanEstimator()
    else:
        return None  # Return None if estimator is disabled or type is unrecognized
