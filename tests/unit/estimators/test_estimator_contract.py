"""Contract tests for estimator interfaces and factories."""

import pytest

from classes.estimators.base_estimator import BaseEstimator
from classes.estimators.estimator_factory import create_estimator
from classes.estimators.kalman_estimator import KalmanEstimator


pytestmark = [pytest.mark.unit, pytest.mark.estimators]


def test_base_estimator_is_abstract():
    """BaseEstimator must remain an abstract extension contract."""
    with pytest.raises(TypeError):
        BaseEstimator()


def test_kalman_estimator_implements_base_contract():
    """KalmanEstimator should implement the estimator base contract."""
    estimator = KalmanEstimator()

    assert isinstance(estimator, BaseEstimator)
    assert estimator.get_estimate() is None
    assert estimator.is_initialized() is False


def test_kalman_estimator_initializes_at_measurement_without_origin_bias():
    estimator = KalmanEstimator()

    estimator.initialize([320.0, 240.0])

    assert estimator.is_initialized() is True
    assert estimator.get_estimate() == pytest.approx(
        [320.0, 240.0, 0.0, 0.0, 0.0, 0.0]
    )


def test_kalman_estimator_updates_and_normalizes_measurement():
    """KalmanEstimator should accept a 2D measurement and return normalized output."""
    estimator = KalmanEstimator()

    estimator.predict_and_update([320.0, 240.0])
    normalized = estimator.get_normalized_estimate(frame_width=640, frame_height=480)

    assert normalized is not None
    assert len(normalized) == 2
    assert all(-1.0 <= value <= 1.0 for value in normalized)


def test_kalman_estimator_rejects_invalid_measurement():
    """Invalid measurement shape should fail instead of being silently accepted."""
    estimator = KalmanEstimator()

    with pytest.raises(ValueError):
        estimator.predict_and_update([1.0, 2.0, 3.0])

    with pytest.raises(ValueError):
        estimator.predict_and_update([float("nan"), 2.0])


def test_kalman_estimator_bounds_prediction_horizon():
    estimator = KalmanEstimator()
    estimator.max_prediction_seconds = 0.1
    estimator.initialize([10.0, 20.0])
    estimator.set_dt(0.1)

    assert estimator.predict_only() is True
    assert estimator.predict_only() is False


def test_kalman_estimator_preserves_image_axis_direction_during_prediction():
    estimator = KalmanEstimator()
    estimator.initialize([100.0, 100.0])
    estimator.set_dt(0.1)
    estimator.predict_and_update([110.0, 100.0])
    measured_state = estimator.get_estimate()

    estimator.set_dt(0.1)
    assert estimator.predict_only() is True
    predicted_state = estimator.get_estimate()

    assert measured_state is not None
    assert predicted_state is not None
    assert measured_state[2] > 0.0
    assert predicted_state[0] > measured_state[0]
    assert predicted_state[1] == pytest.approx(measured_state[1])


def test_estimator_factory_creates_supported_estimator():
    """Factory should create supported estimators by stable algorithm name."""
    estimator = create_estimator("Kalman")

    assert isinstance(estimator, KalmanEstimator)


def test_estimator_factory_rejects_unknown_estimator():
    """Factory should return None for unsupported estimator names."""
    assert create_estimator("unknown-estimator") is None
