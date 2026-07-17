"""Contract tests for detector interfaces and factories."""

from unittest.mock import patch

import numpy as np
import pytest

from classes.detectors.base_detector import BaseDetector
from classes.detectors.detector_factory import create_detector
from classes.detectors.template_matching_detector import TemplateMatchingDetector


pytestmark = [pytest.mark.unit, pytest.mark.detectors]


def test_base_detector_is_abstract():
    """BaseDetector must remain an abstract extension contract."""
    with pytest.raises(TypeError):
        BaseDetector()


def test_template_matching_detector_implements_base_contract():
    """TemplateMatchingDetector should implement the detector base contract."""
    detector = TemplateMatchingDetector()

    assert isinstance(detector, BaseDetector)
    assert detector.get_latest_bbox() is None

    bbox = (2, 3, 4, 5)
    detector.set_latest_bbox(bbox)

    assert detector.get_latest_bbox() == bbox


def test_template_matching_detector_extracts_feature_vector():
    """Feature extraction should return the expected color histogram vector."""
    detector = TemplateMatchingDetector()
    frame = np.zeros((20, 20, 3), dtype=np.uint8)

    features = detector.extract_features(frame, (0, 0, 10, 10))

    assert features.shape == (16 * 16 * 16,)
    assert features.dtype == np.float32
    assert detector.get_latest_bbox() == (0, 0, 10, 10)


def test_detector_factory_creates_supported_detector():
    """Factory should create supported detectors by stable algorithm name."""
    detector = create_detector("TemplateMatching")

    assert isinstance(detector, TemplateMatchingDetector)


def test_template_confidence_clamps_cosine_roundoff():
    """Numerical cosine roundoff must remain within the confidence contract."""
    detector = TemplateMatchingDetector()
    features = np.ones((2, 2), dtype=np.float32)

    with (
        patch(
            "classes.detectors.template_matching_detector.np.dot",
            return_value=1.000000119,
        ),
        patch(
            "classes.detectors.template_matching_detector.np.linalg.norm",
            side_effect=[1.0, 1.0],
        ),
    ):
        confidence = detector.compute_appearance_confidence(features, features)

    assert confidence == 1.0


def test_template_confidence_rejects_materially_invalid_high_score():
    """A broken similarity source must fail closed instead of gaining confidence."""
    detector = TemplateMatchingDetector()
    features = np.ones((2, 2), dtype=np.float32)

    with (
        patch(
            "classes.detectors.template_matching_detector.np.dot",
            return_value=1.01,
        ),
        patch(
            "classes.detectors.template_matching_detector.np.linalg.norm",
            side_effect=[1.0, 1.0],
        ),
    ):
        confidence = detector.compute_appearance_confidence(features, features)

    assert confidence == 0.0


def test_detector_factory_rejects_unknown_detector():
    """Factory should return None for unsupported detector names."""
    assert create_detector("unknown-detector") is None
