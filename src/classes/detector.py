# src/classes/detector.py

import cv2
import numpy as np
from .parameters import Parameters
from .feature_matching_detector import FeatureMatchingDetector

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

    def draw_detection(self, frame, bbox, color=(0, 255, 255)):
        self.detector.draw_detection(frame, bbox, color)



