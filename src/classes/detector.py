#src\classes\detector.py
import logging
from .parameters import Parameters
from .feature_matching_detector import FeatureMatchingDetector
from .template_matching_detector import TemplateMatchingDetector

logger = logging.getLogger(__name__)

class Detector:
    def __init__(self, algorithm_type):
        """
        Initializes the Detector with the specified detection algorithm.

        Args:
            algorithm_type (str): The type of detection algorithm to use.
        """
        self.detector = self.init_detector(algorithm_type)

    def init_detector(self, algorithm_type):
        """
        Initializes the appropriate detector based on the algorithm type.

        Args:
            algorithm_type (str): The type of detection algorithm to use.

        Returns:
            An instance of the chosen detector class.

        Raises:
            ValueError: If an unsupported algorithm type is specified.
        """
        if algorithm_type == "FeatureMatching":
            logger.info("Initialized with FeatureMatching detector.")
            return FeatureMatchingDetector()
        elif algorithm_type == "TemplateMatching":
            logger.info("Initialized with TemplateMatching detector.")
            return TemplateMatchingDetector()
        else:
            logger.error(f"Unsupported algorithm type: {algorithm_type}")
            raise ValueError(f"Unsupported algorithm type: {algorithm_type}")

    def extract_features(self, frame, bbox):
        """
        Extracts features from the specified frame using the detector.

        Args:
            frame (np.ndarray): The video frame from which to extract features.
            bbox (tuple): The bounding box specifying the region of interest.
        """
        logger.debug("Extracting features from frame.")
        self.detector.extract_features(frame, bbox)

    def smart_redetection(self, frame, tracker=None):
        """
        Performs smart redetection on the frame using the detector.

        Args:
            frame (np.ndarray): The video frame in which to perform redetection.
            tracker: (optional) A tracker that might aid in redetection.

        Returns:
            The result of the redetection process.
        """
        logger.debug("Performing smart redetection.")
        return self.detector.smart_redetection(frame)

    def draw_detection(self, frame, color=(0, 255, 255)):
        """
        Draws the detection on the frame.

        Args:
            frame (np.ndarray): The video frame on which to draw the detection.
            color (tuple): The color to use for drawing the detection.

        Returns:
            np.ndarray: The frame with the detection drawn on it.
        """
        logger.debug("Drawing detection on frame.")
        return self.detector.draw_detection(frame, color)

    def get_latest_bbox(self):
        """
        Retrieves the latest bounding box detected by the current detector.

        Returns:
            tuple: The latest bounding box coordinates.
        """
        logger.debug("Getting latest bounding box.")
        return self.detector.get_latest_bbox()

    def set_latest_bbox(self, bbox):
        """
        Sets the latest bounding box in the current detector.

        Args:
            bbox (tuple): The bounding box to set.
        """
        logger.debug("Setting latest bounding box.")
        self.detector.set_latest_bbox(bbox)
