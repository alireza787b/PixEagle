# src/classes/tracker.py

import cv2
from .parameters import Parameters

class Tracker:
    def __init__(self):
        self.tracker = None
        self.init_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM)

    def init_tracker(self, algorithm):
        """
        Initializes the tracking algorithm based on the specified algorithm name.
        """
        # Reset the tracker instance
        if algorithm == "CSRT":
            self.tracker = cv2.TrackerCSRT_create()
        elif algorithm == "KCF":
            self.tracker = cv2.TrackerKCF_create()
        elif algorithm == "BOOSTING":
            self.tracker = cv2.TrackerBoosting_create()
        elif algorithm == "MIL":
            self.tracker = cv2.TrackerMIL_create()
        elif algorithm == "TLD":
            self.tracker = cv2.TrackerTLD_create()
        elif algorithm == "MEDIANFLOW":
            self.tracker = cv2.TrackerMedianFlow_create()
        elif algorithm == "MOSSE":
            self.tracker = cv2.TrackerMOSSE_create()
        elif algorithm == "GOTURN":
            self.tracker = cv2.TrackerGOTURN_create()
        # Add initialization for other algorithms here based on Parameters.TRACKING_PARAMETERS
        else:
            raise ValueError(f"Unsupported tracking algorithm: {algorithm}")

    def start_tracking(self, frame, bbox):
        """
        Starts the tracking process with the given frame and bounding box.
        """
        if not self.tracker:
            raise Exception("Tracker not initialized")
        self.tracker.init(frame, bbox)

    def update(self, frame):
        """
        Updates the tracker with a new frame and returns the new bounding box.
        """
        success, bbox = self.tracker.update(frame)
        return success, bbox

    def select_roi(self, frame):
        """
        Allows the user to manually select the ROI for tracking on the given frame.
        Can be replaced or augmented with automatic detection in future.
        """
        bbox = cv2.selectROI("Frame", frame, False, False)
        cv2.destroyWindow("Frame")
        return bbox
