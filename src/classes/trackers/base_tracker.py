# src/classes/trackers/base_tracker.py

from abc import ABC, abstractmethod
from collections import deque
import time
import numpy as np
from typing import Optional, Tuple
import cv2
from classes.parameters import Parameters
import logging

class BaseTracker(ABC):
    """
    Abstract Base Class for object trackers. Defines the interface and common functionalities
    for different tracking algorithms.
    """
    
    def __init__(self, video_handler: Optional[object] = None, detector: Optional[object] = None, app_controller: Optional[object] = None):
        """
        Initializes the base tracker with common attributes.
        
        :param video_handler: Optional handler for video streaming and processing.
        :param detector: Optional detector for initializing tracking.
        :param app_controller: Reference to the main application controller.
        """
        self.video_handler = video_handler
        self.detector = detector
        self.app_controller = app_controller  # Assign before using it

        # Initialize tracking attributes
        self.bbox: Optional[Tuple[int, int, int, int]] = None  # Current bounding box
        self.prev_center: Optional[Tuple[int, int]] = None     # Previous center
        self.center: Optional[Tuple[int, int]] = None          # Current center
        self.initial_features = None                           # Features of the initial target
        self.normalized_bbox: Optional[Tuple[float, float, float, float]] = None  # Normalized bounding box
        self.normalized_center: Optional[Tuple[float, float]] = None              # Normalized center
        self.center_history = deque(maxlen=Parameters.CENTER_HISTORY_LENGTH)      # History of centers

        # Estimator initialization
        self.estimator_enabled = Parameters.USE_ESTIMATOR
        self.position_estimator = self.app_controller.estimator if self.estimator_enabled else None
        self.estimated_position_history = deque(maxlen=Parameters.ESTIMATOR_HISTORY_LENGTH)
        self.last_update_time: float = 0.0

        # Frame placeholder
        self.frame = None

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
        success, _ = self.update(frame)
        if success:
            self.draw_tracking(frame, tracking_successful=True)
            if self.estimator_enabled:
                self.draw_estimate(frame, tracking_successful=True)
        else:
            logging.warning("Tracking update failed.")
        return frame

    def draw_tracking(self, frame: np.ndarray, tracking_successful: bool = True) -> np.ndarray:
        """
        Draws the tracking bounding box and center on the frame.
        
        :param frame: The video frame.
        :param tracking_successful: Whether the tracking was successful.
        :return: The frame with tracking drawn.
        """
        if self.bbox and self.center and self.video_handler:
            if Parameters.TRACKED_BBOX_STYLE == 'fancy':
                self.draw_fancy_bbox(frame, tracking_successful)
            else:
                self.draw_normal_bbox(frame, tracking_successful)

            # Draw center dot
            cv2.circle(frame, self.center, 5, (0, 255, 0), -1)

            # Optionally display deviations
            if Parameters.DISPLAY_DEVIATIONS:
                self.print_normalized_center()

        return frame

    def draw_normal_bbox(self, frame: np.ndarray, tracking_successful: bool = True) -> None:
        """
        Draws a normal rectangle bounding box on the frame.
        
        :param frame: The video frame.
        :param tracking_successful: Whether the tracking was successful.
        """
        p1 = (int(self.bbox[0]), int(self.bbox[1]))
        p2 = (int(self.bbox[0] + self.bbox[2]), int(self.bbox[1] + self.bbox[3]))
        color = (255, 0, 0) if tracking_successful else (0, 0, 255)
        cv2.rectangle(frame, p1, p2, color, 2)

    def draw_fancy_bbox(self, frame, tracking_successful: bool = True):
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


    def draw_estimate(self, frame: np.ndarray, tracking_successful: bool = True) -> np.ndarray:
        """
        Draws the estimated position on the frame if the estimator is enabled.
        
        :param frame: The video frame.
        :param tracking_successful: Whether the tracking was successful.
        :return: The frame with the estimate drawn on it.
        """
        if self.estimator_enabled and self.position_estimator and self.video_handler:
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position:
                estimated_x, estimated_y = estimated_position[:2]
                color = Parameters.ESTIMATED_POSITION_COLOR if tracking_successful else Parameters.ESTIMATION_ONLY_COLOR
                cv2.circle(frame, (int(estimated_x), int(estimated_y)), 5, color, -1)
        return frame

    def update_time(self) -> float:
        """
        Updates the internal timer for tracking the time between frames.
        
        :return: The time delta since the last update.
        """
        current_time = time.time()
        dt = current_time - self.last_update_time if self.last_update_time else 0.0
        self.last_update_time = current_time
        return dt

    def normalize_center_coordinates(self) -> None:
        """
        Normalizes and stores the center coordinates of the tracked target.
        Normalization is done such that the center of the frame is (0,0),
        top-right is (1,1), and bottom-left is (-1,-1).
        """
        if self.center:
            frame_width, frame_height = self.video_handler.width, self.video_handler.height
            normalized_x = (self.center[0] - frame_width / 2) / (frame_width / 2)
            normalized_y = (self.center[1] - frame_height / 2) / (frame_height / 2)
            self.normalized_center = (normalized_x, normalized_y)

    def print_normalized_center(self) -> None:
        """
        Prints the normalized center coordinates of the tracked target.
        Assumes `normalize_center_coordinates` has been called after the latest tracking update.
        """
        if self.normalized_center:
            logging.debug(f"Normalized Center Coordinates: {self.normalized_center}")
        else:
            logging.warning("Normalized center coordinates not calculated or available.")

    def set_center(self, value: Tuple[int, int]) -> None:
        """
        Sets the center of the bounding box and normalizes it.
        
        :param value: The (x, y) coordinates of the center.
        """
        self.center = value
        self.normalize_center_coordinates()  # Automatically normalize when center is updated

    def normalize_bbox(self) -> None:
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
            logging.debug(f"Normalized bbox: {self.normalized_bbox}")

    def is_motion_consistent(self) -> bool:
        """
        Checks if the motion between the previous and current center is within expected limits.
        
        :return: True if motion is consistent, False otherwise.
        """
        if self.prev_center is None:
            return True  # Can't compare on the first frame
        displacement = np.linalg.norm(np.array(self.center) - np.array(self.prev_center))
        frame_diag = np.hypot(self.video_handler.width, self.video_handler.height)
        max_displacement = Parameters.MAX_DISPLACEMENT_THRESHOLD * frame_diag
        if displacement > max_displacement:
            logging.warning(f"Motion inconsistency detected: displacement={displacement}, max allowed={max_displacement}")
            return False
        return True

    def extract_features(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """
        Extracts features from the given bounding box in the frame.
        
        :param frame: The video frame.
        :param bbox: The bounding box coordinates.
        :return: The extracted feature vector.
        """
        x, y, w, h = [int(v) for v in bbox]
        roi = frame[y:y+h, x:x+w]
        features = cv2.calcHist([roi], [0, 1, 2], None, [8, 8, 8],
                                [0, 256, 0, 256, 0, 256])
        features = cv2.normalize(features, features).flatten()
        return features

    def is_appearance_consistent(self, frame: np.ndarray) -> bool:
        """
        Checks if the appearance of the tracked object is consistent with the initial features.
        
        :param frame: The current video frame.
        :return: True if appearance is consistent, False otherwise.
        """
        if self.initial_features is None:
            return True  # Can't compare without initial features
        current_features = self.extract_features(frame, self.bbox)
        similarity = cv2.compareHist(self.initial_features, current_features, cv2.HISTCMP_CORREL)
        if similarity < Parameters.APPEARANCE_THRESHOLD:
            logging.warning(f"Appearance inconsistency detected: similarity={similarity}")
            return False
        return True

    def reinitialize_tracker(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Reinitializes the tracker with a new bounding box on the given frame.
        
        :param frame: The video frame to reinitialize tracking.
        :param bbox: The new bounding box for tracking.
        """
        logging.info(f"Reinitializing tracker with bbox: {bbox}")
        self.start_tracking(frame, bbox)
