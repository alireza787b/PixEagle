# src/classes/trackers/csrt_tracker.py
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
            self.bbox = detected_bbox
            self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
            self.normalize_bbox()
            if self.estimator_enabled:
                self.position_estimator.set_dt(dt)
                self.position_estimator.predict_and_update(self.center)
                estimated_position = self.position_estimator.get_estimate()
                self.estimated_position_history.append(estimated_position)
        
        return success, self.bbox

