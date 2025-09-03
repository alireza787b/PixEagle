# src/classes/detectors/template_matching_detector.py

import cv2
import numpy as np
from typing import Optional, Tuple
from .base_detector import BaseDetector
from classes.parameters import Parameters
import logging

logger = logging.getLogger(__name__)

class TemplateMatchingDetector(BaseDetector):
    """
    TemplateMatchingDetector Class

    Implements object detection using OpenCV's template matching methods with improvements
    for robust redetection.
    """

    def __init__(self):
        """
        Initializes the TemplateMatchingDetector with the specified matching method.
        """
        super().__init__()
        self.template: Optional[np.ndarray] = None
        self.latest_bbox: Optional[Tuple[int, int, int, int]] = None
        self.method = self.get_matching_method(Parameters.TEMPLATE_MATCHING_METHOD)
        self.initial_features: Optional[np.ndarray] = None
        self.adaptive_features: Optional[np.ndarray] = None

    @staticmethod
    def get_matching_method(method_name: str):
        """
        Maps the method name to the corresponding OpenCV template matching method.

        Args:
            method_name (str): Name of the template matching method.

        Returns:
            int: OpenCV method constant.
        """
        methods = {
            "TM_CCOEFF": cv2.TM_CCOEFF,
            "TM_CCOEFF_NORMED": cv2.TM_CCOEFF_NORMED,
            "TM_CCORR": cv2.TM_CCORR,
            "TM_CCORR_NORMED": cv2.TM_CCORR_NORMED,
            "TM_SQDIFF": cv2.TM_SQDIFF,
            "TM_SQDIFF_NORMED": cv2.TM_SQDIFF_NORMED,
        }
        return methods.get(method_name, cv2.TM_CCOEFF_NORMED)

    def extract_features(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """
        Extracts features and initializes the template and adaptive features if not already set.

        Args:
            frame (np.ndarray): The current video frame.
            bbox (Tuple[int, int, int, int]): Bounding box (x, y, w, h).

        Returns:
            np.ndarray: The feature vector.
        """
        features = super().extract_features(frame, bbox)
        x, y, w, h = bbox

        # Initialize the template only once
        if self.template is None:
            self.template = frame[y:y+h, x:x+w].copy()
            self.initial_template = self.template.copy()
            logger.debug("Template extracted and set for template matching.")

        # Initialize features if not set
        if self.initial_features is None:
            self.initial_features = features.copy()
            self.adaptive_features = features.copy()
            logger.debug("Initial features set for template matching.")

        self.latest_bbox = bbox
        return features

    def update_template(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Updates the adaptive features based on the current frame.

        Args:
            frame (np.ndarray): The current video frame.
            bbox (Tuple[int, int, int, int]): Bounding box (x, y, w, h).
        """
        features = super().extract_features(frame, bbox)
        # Update adaptive features only
        self.adaptive_features = (1 - Parameters.TEMPLATE_APPEARANCE_LEARNING_RATE) * self.adaptive_features + \
                                 Parameters.TEMPLATE_APPEARANCE_LEARNING_RATE * features
        logger.debug(f"TEMPLATE: Adaptive features updated (Learning rate: {Parameters.TEMPLATE_APPEARANCE_LEARNING_RATE})")

    def smart_redetection(self, frame: np.ndarray, tracker=None, roi: Optional[Tuple[int, int, int, int]] = None) -> bool:
        """
        Performs template matching to re-detect the object, with additional validation.

        Args:
            frame (np.ndarray): The current video frame.
            tracker (Optional[object]): The tracker instance.
            roi (Optional[Tuple[int, int, int, int]]): Region of interest to limit search.

        Returns:
            bool: True if re-detection is successful, False otherwise.
        """
        if self.template is None:
            logger.warning("Template has not been set.")
            return False

        frame_to_search = frame
        x_offset, y_offset = 0, 0

        if roi is not None:
            x, y, w, h = roi
            frame_to_search = frame[y:y+h, x:x+w]
            x_offset, y_offset = x, y

        # Check if frame_to_search is larger than or equal to the template
        if frame_to_search.shape[0] < self.template.shape[0] or frame_to_search.shape[1] < self.template.shape[1]:
            logger.warning(f"Frame to search is smaller than template. Frame size: {frame_to_search.shape}, Template size: {self.template.shape}")
            return False

        # Perform multi-scale template matching
        match_found, match_result = self.perform_multiscale_template_matching(frame_to_search)
        if not match_found:
            logger.debug("TEMPLATE: No matches found during redetection")
            return False

        # Extract the matched bounding box
        top_left_x, top_left_y, w, h = match_result
        # Adjust coordinates based on ROI offset
        top_left_x += x_offset
        top_left_y += y_offset
        self.latest_bbox = (top_left_x, top_left_y, w, h)
        logger.info(f"TEMPLATE: Redetection successful - Target found at {self.latest_bbox}")

        # Validate the match
        is_valid = self.validate_match(frame, self.latest_bbox)
        if not is_valid:
            logger.debug("TEMPLATE: Match validation failed after redetection")
            return False

        # Update adaptive features
        features = super().extract_features(frame, self.latest_bbox)
        self.adaptive_features = (1 - Parameters.TEMPLATE_APPEARANCE_LEARNING_RATE) * self.adaptive_features + \
                                 Parameters.TEMPLATE_APPEARANCE_LEARNING_RATE * features

        return True

    def perform_multiscale_template_matching(self, frame_to_search: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Performs multi-scale template matching without modifying the original template.

        Args:
            frame_to_search (np.ndarray): The image to search in.

        Returns:
            Tuple[bool, Tuple[int, int, int, int]]: (Match found, (top_left_x, top_left_y, w, h))
        """
        scales = Parameters.TEMPLATE_MATCHING_SCALES
        best_match_value = None
        best_top_left = None
        best_scale = 1.0

        for scale in scales:
            resized_template = cv2.resize(self.template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            if frame_to_search.shape[0] < resized_template.shape[0] or frame_to_search.shape[1] < resized_template.shape[1]:
                continue

            res = cv2.matchTemplate(frame_to_search, resized_template, self.method)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

            if self.method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
                match_value = min_val
                top_left = min_loc
                is_better = best_match_value is None or match_value < best_match_value
            else:
                match_value = max_val
                top_left = max_loc
                is_better = best_match_value is None or match_value > best_match_value

            if is_better:
                best_match_value = match_value
                best_top_left = top_left
                best_scale = scale

        if best_match_value is not None:
            logger.debug(f"Best match found at scale {best_scale} with value {best_match_value}")
            # Adjust the bounding box size based on the best scale
            h_tmpl, w_tmpl = self.template.shape[:2]
            h_resized, w_resized = int(h_tmpl * best_scale), int(w_tmpl * best_scale)
            return True, (best_top_left[0], best_top_left[1], w_resized, h_resized)
        else:
            return False, (0, 0, 0, 0)

    def validate_match(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> bool:
        """
        Validates the matched area by comparing appearance features.

        Args:
            frame (np.ndarray): The current video frame.
            bbox (Tuple[int, int, int, int]): Bounding box of the matched area.

        Returns:
            bool: True if the match is valid, False otherwise.
        """
        current_features = self.extract_features(frame, bbox)
        confidence = self.compute_appearance_confidence(current_features, self.initial_features)
        logger.debug(f"Appearance confidence: {confidence:.2f}")
        return confidence >= Parameters.APPEARANCE_CONFIDENCE_THRESHOLD

    def compute_appearance_confidence(self, features: np.ndarray, reference_features: np.ndarray) -> float:
        """
        Computes the appearance confidence between the current features and the reference features.

        Args:
            features (np.ndarray): The features from the current detection.
            reference_features (np.ndarray): The reference features to compare against.

        Returns:
            float: The confidence score between 0 and 1.
        """
        # Use cosine similarity as an example
        numerator = np.dot(features.flatten(), reference_features.flatten())
        denominator = np.linalg.norm(features.flatten()) * np.linalg.norm(reference_features.flatten())
        if denominator == 0:
            return 0.0
        else:
            confidence = numerator / denominator
            return confidence

    def draw_detection(self, frame: np.ndarray, color=(0, 255, 255)) -> np.ndarray:
        """
        Draws the detection bounding box on the frame.

        Args:
            frame (np.ndarray): The current video frame.
            color (tuple): Color for the bounding box.

        Returns:
            np.ndarray: The frame with detection drawn.
        """
        if self.latest_bbox is None:
            return frame
        x, y, w, h = self.latest_bbox
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        return frame

    def get_latest_bbox(self) -> Optional[Tuple[int, int, int, int]]:
        """
        Retrieves the latest bounding box from detection.

        Returns:
            Optional[Tuple[int, int, int, int]]: The latest bounding box or None.
        """
        return self.latest_bbox

    def set_latest_bbox(self, bbox: Tuple[int, int, int, int]) -> None:
        """
        Sets the latest bounding box for detection.

        Args:
            bbox (Tuple[int, int, int, int]): The bounding box to set.
        """
        self.latest_bbox = bbox
