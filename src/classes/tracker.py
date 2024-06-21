# src/classes/tracker.py

import time
import cv2

from classes.detector import Detector
from .parameters import Parameters
from collections import deque
from .position_estimator import PositionEstimator


class Tracker:
    def __init__(self,video_handler=None,detector= None):
        self.tracker = None
        self.video_handler = video_handler
        self.bbox = None  # Current bounding box
        self.normalized_bbox = None  # Current bounding box
        self.center = None  # Current center of the bounding box
        self.center_history = deque(maxlen=Parameters.CENTER_HISTORY_LENGTH)  # History of center points
        self.estimator_enabled = Parameters.USE_ESTIMATOR
        self.position_estimator = PositionEstimator() if self.estimator_enabled else None
        self.estimated_position_history = deque(maxlen=Parameters.ESTIMATOR_HISTORY_LENGTH)
        self.last_update_time = None

        self.init_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM)
        self.detector = detector

    def init_tracker(self, algorithm):
        """
        Initializes the tracking algorithm based on the specified algorithm name.
        """
        # Reset the tracker instance
        if algorithm == "CSRT":
            #self.tracker = cv2.TrackerCSRT_create()
            self.tracker = cv2.legacy.TrackerCSRT_create()
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
        print("Initializing tracker with bbox:", bbox, "of type:", type(bbox))
        self.tracker.init(frame, bbox)
        if Parameters.USE_DETECTOR:
            self.detector.extract_features(frame, bbox)

        self.last_update_time = time.time()


    def update(self, frame):
        """
        Updates the tracker with the new frame and stores the bounding box and center.
        """
        current_time = time.time()
        success, self.bbox = self.tracker.update(frame)
        dt = current_time - self.last_update_time if self.last_update_time else 0
        self.last_update_time = current_time
        
        if success:
            # Calculate and store the center of the bounding box
            self.center = (int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2))
            self.center_history.append(self.center)
            
            if self.estimator_enabled:
                        # Update the estimator with the new center and store the estimated position
                        self.position_estimator.set_dt(dt)
                        self.position_estimator.predict_and_update(self.center)
                        estimated_position = self.position_estimator.get_estimate()
                        self.estimated_position_history.append(estimated_position)
            
        return success, self.bbox
    

    def draw_estimate(self, frame):
        if self.estimator_enabled and self.position_estimator and self.video_handler:
            # Get the latest estimate
            estimated_position = self.position_estimator.get_estimate()

            if estimated_position:
                # Extract only the x and y position from the estimated state for drawing
                estimated_x, estimated_y = estimated_position[:2]

                # Draw estimated center dot in red
                cv2.circle(frame, (int(estimated_x), int(estimated_y)), 5, (0,0,255), -1)  # Red dot for estimated position

                # Calculate relative deviation for estimated position
                frame_center = (self.video_handler.width / 2, self.video_handler.height / 2)
                relative_deviation_x = (estimated_x - frame_center[0]) / frame_center[0]
                relative_deviation_y = (estimated_y - frame_center[1]) / frame_center[1]

                if Parameters.DISPLAY_DEVIATIONS:
                    print(f"Estimated relative deviation from center: (X: {relative_deviation_x:.2f}, Y: {relative_deviation_y:.2f})")

        return frame



    def select_roi(self, frame):
        """
        Allows the user to manually select the ROI for tracking on the given frame.
        Can be replaced or augmented with automatic detection in future.
        """
        bbox = cv2.selectROI("Frame", frame, False, False)
        cv2.destroyWindow("Frame")
        return bbox


    def reinitialize_tracker(self, frame, bbox):
           
            
        self.start_tracking(frame, bbox)