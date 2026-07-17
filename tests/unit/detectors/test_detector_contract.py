"""Contract tests for detector interfaces and factories."""

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


def test_detector_factory_rejects_unknown_detector():
    """Factory should return None for unsupported detector names."""
    assert create_detector("unknown-detector") is None
