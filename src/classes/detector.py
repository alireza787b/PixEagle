from .parameters import Parameters
from .feature_matching_detector import FeatureMatchingDetector
# Import other detectors as you implement them

class Detector:
    def __init__(self, algorithm_type="FeatureMatching"):
        self.detector = self.init_detector(algorithm_type)

    def init_detector(self, algorithm_type):
        if algorithm_type == "FeatureMatching":
            return FeatureMatchingDetector()
        # Add other algorithms here as you implement them
        else:
            raise ValueError(f"Unsupported detection algorithm type: {algorithm_type}")

    def extract_features(self, frame, bbox):
        self.detector.extract_features(frame, bbox)

    def smart_redetection(self, frame):
        return self.detector.smart_redetection(frame)

    def draw_detection(self, frame, color=(0, 255, 255)):
        return self.detector.draw_detection(frame, color)

    def get_latest_bbox(self):
        """
        Proxy method to get the latest bounding box from the current detector.
        """
        return self.detector.get_latest_bbox()

    def set_latest_bbox(self, bbox):
        """
        Proxy method to set the latest bounding box in the current detector.
        """
        self.detector.set_latest_bbox(bbox)
