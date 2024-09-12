# src/classes/trackers/base_tracker.py
from abc import ABC, abstractmethod
from collections import deque
import time
import numpy as np
from typing import Optional, Tuple
import cv2
from classes.parameters import Parameters
from classes.position_estimator import PositionEstimator
import logging

class BaseTracker(ABC):
    """
    Abstract Base Class for object trackers. Defines the interface and common functionalities
    for different tracking algorithms.
    """
    
    def __init__(self, video_handler: Optional[object] = None, detector: Optional[object] = None,app_controller: Optional[object] = None):
        """
        Initializes the base tracker with common attributes.
        
        :param video_handler: Optional handler for video streaming and processing.
        :param detector: Optional detector for initializing tracking.
        """
        self.video_handler = video_handler
        self.detector = detector
        self.bbox: Optional[Tuple[int, int, int, int]] = None  # Current bounding box
        self.normalized_bbox: Optional[Tuple[float, float, float, float]] = None  # Normalized bounding box
        self.center: Optional[Tuple[int, int]] = None  # Use underscore to denote the private attribute
        self.normalized_center: Optional[Tuple[float, float]] = None  # Store normalized center        self.center_history = deque(maxlen=Parameters.CENTER_HISTORY_LENGTH)
        self.estimator_enabled = Parameters.USE_ESTIMATOR
        self.position_estimator = PositionEstimator() if self.estimator_enabled else None
        self.estimated_position_history = deque(maxlen=Parameters.ESTIMATOR_HISTORY_LENGTH)
        self.last_update_time: float = 0.0
        self.frame = None
        self.app_controller = app_controller

    @abstractmethod
    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Starts the tracking process with the given frame and bounding box.
        
        :param frame: The initial video frame to start tracking.
        :param bbox: A tuple representing the bounding box (x, y, width, height).
        """
        pass

    @abstractmethod
    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Updates the tracker with the new frame and returns the tracking success status
        and the new bounding box.
        
        :param frame: The current video frame.
        :return: A tuple containing the success status and the new bounding box.
        """
        pass

    def update_and_draw(self, frame: np.ndarray) -> np.ndarray:
        """
        Updates the tracking state with the current frame and draws tracking
        and estimation results on it.
        
        :param frame: The current video frame.
        :return: The video frame with tracking and estimation visuals.
        """
        success, bbox = self.update(frame)
        if success:
            self.draw_tracking(frame)
            if self.estimator_enabled:
                self.draw_estimate(frame)
        return frame

    def draw_tracking(self, frame):
        if self.bbox and self.center and self.video_handler:
            if Parameters.TRACKED_BBOX_STYLE == 'fancy':
                self.draw_fancy_bbox(frame)
            else:
                self.draw_normal_bbox(frame)

            # Draw center dot
            cv2.circle(frame, self.center, 5, (0, 255, 0), -1)

            # Calculate relative deviation from frame center
            frame_center = (self.video_handler.width / 2, self.video_handler.height / 2)
            relative_deviation_x = (self.center[0] - frame_center[0]) / frame_center[0]
            relative_deviation_y = (self.center[1] - frame_center[1]) / frame_center[1]

            if Parameters.DISPLAY_DEVIATIONS:
                print(f"Relative deviation from center: (X: {relative_deviation_x:.2f}, Y: {relative_deviation_y:.2f})")

        return frame

    def draw_normal_bbox(self, frame):
        # Draw bounding box
        p1 = (int(self.bbox[0]), int(self.bbox[1]))
        p2 = (int(self.bbox[0] + self.bbox[2]), int(self.bbox[1] + self.bbox[3]))
        cv2.rectangle(frame, p1, p2, (255, 0, 0), 2, 1)

    def draw_fancy_bbox(self, frame):
        if self.bbox is None or self.center is None:
            return frame

        # Determine color based on tracking status
        color = (Parameters.FOLLOWER_ACTIVE_COLOR 
                 if self.app_controller.following_active 
                 else Parameters.FOLLOWER_INACTIVE_COLOR)

        p1 = (int(self.bbox[0]), int(self.bbox[1]))
        p2 = (int(self.bbox[0] + self.bbox[2]), int(self.bbox[1] + self.bbox[3]))
        center_x, center_y = self.center
        
        # Draw crosshair
        cv2.line(frame, 
                 (center_x - Parameters.CROSSHAIR_ARM_LENGTH, center_y), 
                 (center_x + Parameters.CROSSHAIR_ARM_LENGTH, center_y), 
                 color, 
                 Parameters.BBOX_LINE_THICKNESS)
        cv2.line(frame, 
                 (center_x, center_y - Parameters.CROSSHAIR_ARM_LENGTH), 
                 (center_x, center_y + Parameters.CROSSHAIR_ARM_LENGTH), 
                 color, 
                 Parameters.BBOX_LINE_THICKNESS)
        
        # Draw bounding box with corners
        corner_points = [
            (p1, (p1[0] + Parameters.BBOX_CORNER_ARM_LENGTH, p1[1])),
            (p1, (p1[0], p1[1] + Parameters.BBOX_CORNER_ARM_LENGTH)),
            (p2, (p2[0] - Parameters.BBOX_CORNER_ARM_LENGTH, p2[1])),
            (p2, (p2[0], p2[1] - Parameters.BBOX_CORNER_ARM_LENGTH)),
            ((p1[0], p2[1]), (p1[0] + Parameters.BBOX_CORNER_ARM_LENGTH, p2[1])),
            ((p1[0], p2[1]), (p1[0], p2[1] - Parameters.BBOX_CORNER_ARM_LENGTH)),
            ((p2[0], p1[1]), (p2[0] - Parameters.BBOX_CORNER_ARM_LENGTH, p1[1])),
            ((p2[0], p1[1]), (p2[0], p1[1] + Parameters.BBOX_CORNER_ARM_LENGTH))
        ]
        
        for start, end in corner_points:
            cv2.line(frame, start, end, color, Parameters.BBOX_LINE_THICKNESS)

        # Draw extended lines from the center of each edge of the bounding box
        height, width, _ = frame.shape
        cv2.line(frame, (p1[0], center_y), (0, center_y), color, Parameters.EXTENDED_LINE_THICKNESS)  # Left edge to left
        cv2.line(frame, (p2[0], center_y), (width, center_y), color, Parameters.EXTENDED_LINE_THICKNESS)  # Right edge to right
        cv2.line(frame, (center_x, p1[1]), (center_x, 0), color, Parameters.EXTENDED_LINE_THICKNESS)  # Top edge to top
        cv2.line(frame, (center_x, p2[1]), (center_x, height), color, Parameters.EXTENDED_LINE_THICKNESS)  # Bottom edge to bottom

        # Draw smaller dots at the corners of the bounding box
        for point in [p1, p2, (p1[0], p2[1]), (p2[0], p1[1])]:
            cv2.circle(frame, point, Parameters.CORNER_DOT_RADIUS, color, -1)

        return frame



    def draw_estimate(self, frame: np.ndarray) -> np.ndarray:
        """
        Draws the estimated position on the frame if estimation is enabled.
        
        :param frame: The video frame to draw on.
        :return: The video frame with estimation visuals.
        """
        if self.estimator_enabled and self.position_estimator and self.video_handler:
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position:
                estimated_x, estimated_y = estimated_position[:2]
                cv2.circle(frame, (int(estimated_x), int(estimated_y)), 5, (0, 0, 255), -1)
        return frame

    def select_roi(self, frame: np.ndarray) -> Tuple[int, int, int, int]:
        """
        Allows the user to manually select the Region of Interest (ROI) for tracking on the given frame.
        
        :param frame: The video frame for selecting ROI.
        :return: The bounding box representing the selected ROI.
        """
        bbox = cv2.selectROI("Frame", frame, False, False)
        cv2.destroyWindow("Frame")
        return bbox

    def reinitialize_tracker(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Reinitializes the tracker with a new bounding box on the given frame.
        
        :param frame: The video frame to reinitialize tracking.
        :param bbox: The new bounding box for tracking.
        """
        self.start_tracking(frame, bbox)

    def update_time(self) -> float:
        """
        Updates the internal timer for tracking the time between frames.
        
        :return: The time delta since the last update.
        """
        current_time = time.time()
        dt = current_time - self.last_update_time if self.last_update_time else 0
        self.last_update_time = current_time
        return dt

    def normalize_center_coordinates(self):
        """
        Normalizes and stores the center coordinates of the tracked target.
        Normalization is done such that the center of the frame is (0,0),
        top-right is (1,1), and bottom-left is (-1,-1).
        """
        if self.center :
            frame_height, frame_width = (self.video_handler.height , self.video_handler.width)
            # Normalize center coordinates
            normalized_x = (self.center[0] - frame_width / 2) / (frame_width / 2)
            normalized_y = (self.center[1] - frame_height / 2) / (frame_height / 2)
            # Store normalized values
            self.normalized_center = (normalized_x, normalized_y)
            
    def print_normalized_center(self):
        """
        Prints the normalized center coordinates of the tracked target.
        Assumes `normalize_center_coordinates` has been called after the latest tracking update.
        """
        if hasattr(self, 'normalized_center'):
            logging.debug(f"Normalized Center Coordinates: {self.normalized_center}")
        else:
            logging.warn("Normalized center coordinates not calculated or available.")
            

    def set_center(self, value: Tuple[int, int]):
        self.center = value
        self.normalize_center_coordinates()  # Automatically normalize when center is updated
        
    def normalize_bbox(self):
        """
        Normalizes the bounding box coordinates relative to the frame size.
        """
        if self.bbox and self.video_handler:
            frame_width, frame_height = self.video_handler.width, self.video_handler.height
            x, y, w, h = self.bbox
            norm_x = (x - frame_width / 2) / (frame_width / 2)
            norm_y = (y - frame_height / 2) / (frame_height / 2)
            norm_w = w / frame_width
            norm_h = h / frame_height
            self.normalized_bbox = (norm_x, norm_y, norm_w, norm_h)
            #logging.debug(f"Normalized bbox: {self.normalized_bbox}")

            return self.normalized_bbox