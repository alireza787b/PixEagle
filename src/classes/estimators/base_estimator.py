# src/classes/estimators/base_estimator.py

from abc import ABC, abstractmethod

class BaseEstimator(ABC):
    @abstractmethod
    def set_dt(self, dt):
        pass

    @abstractmethod
    def predict_and_update(self, measurement):
        pass

    @abstractmethod
    def get_estimate(self):
        pass
