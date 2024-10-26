# src/classes/detectors/base_detector.py

import cv2
import numpy as np
from abc import ABC, abstractmethod
from typing import Tuple, Optional
from classes.parameters import Parameters  # Ensure Parameters is correctly imported
import logging

logger = logging.getLogger(__name__)

class BaseDetector(ABC):
    """
    BaseDetector Abstract Class

    Defines the interface and common functionalities for all detectors.
    """

    def __init__(self):
        """
        Initializes common attributes for detectors.
        """
        self.adaptive_features: Optional[np.ndarray] = None
        self.initial_features: Optional[np.ndarray] = None
        self.initial_template: Optional[np.ndarray] = None

    def extract_features(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """
        Extracts color histogram features from the specified bounding box in the frame.

        Args:
            frame (np.ndarray): The current video frame.
            bbox (Tuple[int, int, int, int]): Bounding box (x, y, w, h).

        Returns:
            np.ndarray: The feature vector.
        """
        x, y, w, h = [int(v) for v in bbox]
        roi = frame[y:y+h, x:x+w]
        if roi is None or roi.size == 0:
            # Return zero features if ROI is invalid
            return np.zeros((16*16*16,), dtype=np.float32)
        features = cv2.calcHist([roi], [0, 1, 2], None, [16, 16, 16],
                                [0, 256, 0, 256, 0, 256])
        features = cv2.normalize(features, features).flatten()
        return features

    def compute_appearance_confidence(self, current_features: np.ndarray, adaptive_features: np.ndarray) -> float:
        """
        Computes confidence based on appearance consistency.

        Args:
            current_features (np.ndarray): Features of the current frame's ROI.
            adaptive_features (np.ndarray): Adaptive features maintained over time.

        Returns:
            float: The appearance confidence score between 0.0 and 1.0.
        """
        similarity = cv2.compareHist(adaptive_features, current_features, cv2.HISTCMP_BHATTACHARYYA)
        confidence = max(0.0, 1.0 - similarity)
        return confidence

    def is_appearance_consistent(self, confidence: float) -> bool:
        """
        Determines if the appearance is consistent based on confidence.

        Args:
            confidence (float): The appearance confidence score.

        Returns:
            bool: True if appearance is consistent, False otherwise.
        """
        return confidence >= Parameters.APPEARANCE_CONFIDENCE_THRESHOLD

    def compute_edge_similarity(self, initial_template: np.ndarray, roi: np.ndarray) -> float:
        """
        Computes edge-based similarity between the initial template and the current region.

        Args:
            initial_template (np.ndarray): The initial template image.
            roi (np.ndarray): The region of interest in the current frame.

        Returns:
            float: The edge similarity score.
        """
        if roi is None or roi.size == 0 or initial_template is None or initial_template.size == 0:
            return 1.0  # Maximum distance if invalid
        initial_edge = self.extract_edge(initial_template)
        current_edge = self.extract_edge(roi)
        current_edge_resized = cv2.resize(current_edge, (initial_edge.shape[1], initial_edge.shape[0]))
        similarity = cv2.matchTemplate(current_edge_resized, initial_edge, cv2.TM_CCOEFF_NORMED)
        max_similarity = np.max(similarity)
        return 1.0 - max_similarity  # Invert similarity to represent distance

    def extract_edge(self, image: np.ndarray) -> np.ndarray:
        """
        Extracts edge features from the image using Canny edge detector.

        Args:
            image (np.ndarray): The input image.

        Returns:
            np.ndarray: The edge image.
        """
        if image is None or image.size == 0:
            # Return zero edge image if image is invalid
            return np.zeros((1, 1), dtype=np.uint8)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, Parameters.PF_CANNY_THRESHOLD1, Parameters.PF_CANNY_THRESHOLD2)
        return edges

    @abstractmethod
    def smart_redetection(self, frame: np.ndarray, tracker=None, roi: Optional[Tuple[int, int, int, int]] = None) -> bool:
        """
        Performs smart re-detection of the object in the frame.

        Args:
            frame (np.ndarray): The current video frame.
            tracker (Optional[object]): The tracker instance.
            roi (Optional[Tuple[int, int, int, int]]): Region of interest to limit search.

        Returns:
            bool: True if re-detection is successful, False otherwise.
        """
        pass

    @abstractmethod
    def draw_detection(self, frame: np.ndarray, color=(0, 255, 255)) -> np.ndarray:
        """
        Draws the detection bounding box on the frame.

        Args:
            frame (np.ndarray): The current video frame.
            color (tuple): Color for the bounding box.

        Returns:
            np.ndarray: The frame with detection drawn.
        """
        pass

    @abstractmethod
    def get_latest_bbox(self) -> Optional[Tuple[int, int, int, int]]:
        """
        Retrieves the latest bounding box from detection.

        Returns:
            Optional[Tuple[int, int, int, int]]: The latest bounding box or None.
        """
        pass

    @abstractmethod
    def set_latest_bbox(self, bbox: Tuple[int, int, int, int]) -> None:
        """
        Sets the latest bounding box for detection.

        Args:
            bbox (Tuple[int, int, int, int]): The bounding box to set.
        """
        pass
