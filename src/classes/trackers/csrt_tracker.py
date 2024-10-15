# src/classes/trackers/csrt_tracker.py
import logging
import time
import cv2
import numpy as np
from typing import Optional, Tuple
from collections import deque
from classes.parameters import Parameters  # Ensure correct import path
from classes.position_estimator import PositionEstimator  # Ensure correct import path
from classes.trackers.base_tracker import BaseTracker  # Ensure correct import path

class CSRTTracker(BaseTracker):
    """
    CSRT Tracker implementation extending the BaseTracker class.
    Specializes in using the CSRT algorithm for object tracking.
    """
    
    def __init__(self, video_handler: Optional[object] = None, detector: Optional[object] = None,app_controller: Optional[object] = None):
        """
        Initializes the CSRT tracker with an optional video handler and detector.
        
        :param video_handler: Handler for video streaming and processing.
        :param detector: Object detector for initializing tracking.
        """
        super().__init__(video_handler, detector,app_controller)
        self.tracker = cv2.TrackerCSRT_create()  # Tracker specific to CSRT
        self.trackerName: str = "CSRT"

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]):
        """
        Initializes the tracker with the provided bounding box on the given frame.

        :param frame: The initial video frame.
        :param bbox: A tuple representing the bounding box (x, y, width, height).
        """
        print(f"Initializing {self.trackerName} tracker with bbox: {bbox}, of type: {type(bbox)}")
        self.tracker.init(frame, bbox)
        self.initial_features = self.extract_features(frame, bbox)
        self.prev_center = None  # Reset previous center
        self.last_update_time = time.time()

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Updates the tracker with the current frame and returns the tracking success status and the new bounding box.

        :param frame: The current video frame.
        :return: A tuple containing the success status and the new bounding box.
        """
        dt = self.update_time()
        success, detected_bbox = self.tracker.update(frame)
        
        if success:
            self.prev_center = self.center  # Store the previous center
            self.bbox = detected_bbox
            self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
            self.normalize_bbox()
            # Compute confidence scores
            motion_confidence = self.compute_motion_confidence()
            appearance_confidence = self.compute_appearance_confidence(frame)
            total_confidence = (motion_confidence + appearance_confidence) / 2.0
            #logging.debug(f"Motion Confidence: {motion_confidence}, Appearance Confidence: {appearance_confidence}, Total Confidence: {total_confidence}")

            # Perform motion consistency check
            if not self.is_motion_consistent():
                logging.warning("Tracking failed due to motion inconsistency.")
                success = False
                
            if total_confidence < Parameters.CONFIDENCE_THRESHOLD:
                logging.warning("Tracking failed due to low confidence.")
                success = False

            # Perform appearance consistency check
            elif not self.is_appearance_consistent(frame):
                logging.warning("Tracking failed due to appearance inconsistency.")
                success = False

            if success:
                if self.estimator_enabled:
                    self.position_estimator.set_dt(dt)
                    self.position_estimator.predict_and_update(self.center)
                    estimated_position = self.position_estimator.get_estimate()
                    self.estimated_position_history.append(estimated_position)
        else:
            logging.warning("Tracking update failed in tracker algorithm.")

        return success, self.bbox
    
    
    def compute_motion_confidence(self) -> float:
        """
        Computes confidence based on motion consistency.
        """
        if self.prev_center is None:
            return 1.0  # Maximum confidence on first frame
        displacement = np.linalg.norm(np.array(self.center) - np.array(self.prev_center))
        frame_diag = np.hypot(self.video_handler.width, self.video_handler.height)
        confidence = max(0.0, 1.0 - (displacement / (Parameters.MAX_DISPLACEMENT_THRESHOLD * frame_diag)))
        return confidence

    def compute_appearance_confidence(self, frame: np.ndarray) -> float:
        """
        Computes confidence based on appearance consistency.
        """
        current_features = self.extract_features(frame, self.bbox)
        similarity = cv2.compareHist(self.initial_features, current_features, cv2.HISTCMP_CORREL)
        # Normalize similarity to range [0,1]
        confidence = max(0.0, min(similarity, 1.0))
        return confidence

