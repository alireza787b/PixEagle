# src/classes/detectors/detector_factory.py

import logging
from typing import Optional

from .base_detector import BaseDetector
from .template_matching_detector import TemplateMatchingDetector
from classes.parameters import Parameters

logger = logging.getLogger(__name__)

def create_detector(algorithm_type: str) -> Optional[BaseDetector]:
    """
    Factory method to create a detector based on the specified algorithm type.

    Args:
        algorithm_type (str): The type of detection algorithm to use.

    Returns:
        Optional[BaseDetector]: An instance of the chosen detector class or None if unsupported.
    """

    if algorithm_type == "TemplateMatching":
        logger.info("Initialized with TemplateMatching detector.")
        return TemplateMatchingDetector()


    else:
        logger.error(f"Unsupported algorithm type: {algorithm_type}")
        return None
