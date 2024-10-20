# src/classes/tracker.py

import time
import cv2
import logging
import numpy as np
from collections import deque
from .parameters import Parameters
# Remove direct import of PositionEstimator
# from .position_estimator import PositionEstimator
from classes.estimators.base_estimator import BaseEstimator  # Import the estimator interface
from classes.estimators.estimator_factory import create_estimator

logger = logging.getLogger(__name__)

class Tracker:
    def __init__(self, video_handler=None, detector=None, app_controller=None):
        """
        Initializes the Tracker with a specific tracking algorithm and optional video handler, detector, and estimator.

        Args:
            video_handler (VideoHandler, optional): An instance of the VideoHandler class.
            detector (Detector, optional): An instance of the Detector class.
            app_controller (AppController, optional): Reference to the main app controller.
            estimator (BaseEstimator, optional): An instance of an estimator implementing BaseEstimator.
        """
        self.tracker = None
        self.video_handler = video_handler
        self.detector = detector
        self.app_controller = app_controller

        self.bbox = None  # Current bounding box
        self.prev_bbox = None  # Previous bounding box
        self.center = None  # Current center of the bounding box
        self.prev_center = None  # Previous center
        self.initial_features = None  # Features extracted from initial bounding box
        self.last_update_time = None

        self.center_history = deque(maxlen=Parameters.CENTER_HISTORY_LENGTH)  # History of center points

        # Initialize the tracker algorithm
        self.init_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM)

        # Estimator (if used)
        estimator = self.app_controller.estimator
        self.position_estimator = estimator
        self.estimator_enabled = estimator is not None
        self.estimated_position_history = deque(maxlen=Parameters.ESTIMATOR_HISTORY_LENGTH)

    def init_tracker(self, algorithm):
        """
        Initializes the tracking algorithm based on the specified algorithm name.

        Args:
            algorithm (str): The name of the tracking algorithm to use.

        Raises:
            ValueError: If an unsupported tracking algorithm is specified.
        """
        try:
            if algorithm == "CSRT":
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
            else:
                raise ValueError(f"Unsupported tracking algorithm: {algorithm}")
            logger.info(f"Initialized {algorithm} tracker.")
        except Exception as e:
            logger.error(f"Failed to initialize tracker: {e}")
            raise

    def start_tracking(self, frame, bbox):
        """
        Starts the tracking process with the given frame and bounding box.

        Args:
            frame (np.ndarray): The video frame to initialize tracking.
            bbox (tuple): The bounding box coordinates for tracking.

        Raises:
            Exception: If the tracker is not initialized.
        """
        if not self.tracker:
            raise Exception("Tracker not initialized")
        logger.debug(f"Initializing tracker with bbox: {bbox}")
        self.tracker.init(frame, bbox)
        self.bbox = bbox
        self._update_center()

        # Extract initial features for appearance validation
        self.initial_features = self.extract_features(frame, bbox)

        self.last_update_time = time.time()

        # Reset the estimator if enabled
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.reset()  # Reset the estimator's state

    def update(self, frame):
        """
        Updates the tracker with the new frame, and manages bounding box, center, and estimator.

        Args:
            frame (np.ndarray): The video frame to update the tracker.

        Returns:
            tuple: A boolean indicating success and the updated bounding box.
        """
        current_time = time.time()
        success, new_bbox = self.tracker.update(frame)
        dt = current_time - self.last_update_time if self.last_update_time else 0.1  # Default to 0.1 if first frame
        self.last_update_time = current_time

        if success:
            self.prev_bbox = self.bbox
            self.bbox = new_bbox
            self.prev_center = self.center
            self._update_center()
            self.center_history.append(self.center)

            # Perform motion and appearance consistency checks
            motion_consistent = self.is_motion_consistent()
            appearance_consistent = self.is_appearance_consistent(frame)
            confidence = self.compute_confidence(motion_consistent, appearance_consistent)

            if confidence < Parameters.CONFIDENCE_THRESHOLD:
                logger.warning("Low tracking confidence detected.")
                success = False  # Treat as failure
            else:
                logger.debug(f"Tracking confidence: {confidence:.2f}")

            # Update estimator if enabled
            if success and self.estimator_enabled and self.position_estimator:
                self._update_estimator(dt)

        return success, self.bbox

    def _update_center(self):
        """Calculates and stores the center of the current bounding box."""
        x, y, w, h = self.bbox
        self.center = (int(x + w / 2), int(y + h / 2))
        logger.debug(f"Updated center: {self.center}")

    def is_motion_consistent(self):
        """
        Checks if the motion between frames is consistent.

        Returns:
            bool: True if motion is consistent, False otherwise.
        """
        if self.prev_center is None:
            return True  # Can't compare on the first frame
        displacement = np.linalg.norm(np.array(self.center) - np.array(self.prev_center))
        max_displacement = Parameters.MAX_DISPLACEMENT_THRESHOLD
        if displacement > max_displacement:
            logger.warning(f"Motion inconsistency detected. Displacement: {displacement:.2f}")
            return False
        return True

    def extract_features(self, frame, bbox):
        """
        Extracts features from the given bounding box in the frame.

        Args:
            frame (np.ndarray): The video frame.
            bbox (tuple): The bounding box coordinates.

        Returns:
            np.ndarray: The extracted feature vector.
        """
        x, y, w, h = [int(v) for v in bbox]
        roi = frame[y:y+h, x:x+w]
        hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        features = cv2.calcHist([hsv_roi], [0, 1], None, [16, 16], [0, 180, 0, 256])
        features = cv2.normalize(features, features).flatten()
        return features

    def is_appearance_consistent(self, frame):
        """
        Checks if the appearance of the tracked object remains consistent.

        Args:
            frame (np.ndarray): The current video frame.

        Returns:
            bool: True if appearance is consistent, False otherwise.
        """
        current_features = self.extract_features(frame, self.bbox)
        similarity = cv2.compareHist(self.initial_features, current_features, cv2.HISTCMP_CORREL)
        if similarity < Parameters.APPEARANCE_THRESHOLD:
            logger.warning(f"Appearance inconsistency detected. Similarity: {similarity:.2f}")
            return False
        return True

    def compute_confidence(self, motion_consistent, appearance_consistent):
        """
        Computes the overall confidence score based on motion and appearance.

        Args:
            motion_consistent (bool): Result of motion consistency check.
            appearance_consistent (bool): Result of appearance consistency check.

        Returns:
            float: The confidence score (0 to 1).
        """
        motion_confidence = 1.0 if motion_consistent else 0.0
        appearance_confidence = 1.0 if appearance_consistent else 0.0
        total_confidence = (motion_confidence + appearance_confidence) / 2
        return total_confidence

    def _update_estimator(self, dt):
        """Updates the position estimator if enabled."""
        self.position_estimator.set_dt(dt)
        self.position_estimator.predict_and_update(self.center)
        estimated_position = self.position_estimator.get_estimate()
        self.estimated_position_history.append(estimated_position)
        logger.debug(f"Estimated position: {estimated_position}")

    def draw_tracking(self, frame):
        """
        Draws the tracking bounding box and center on the frame.

        Args:
            frame (np.ndarray): The video frame.

        Returns:
            np.ndarray: The frame with tracking drawn.
        """
        x, y, w, h = [int(v) for v in self.bbox]
        cv2.rectangle(frame, (x, y), (x + w, y + h), Parameters.TRACKER_BOX_COLOR, 2)
        cv2.circle(frame, self.center, 4, Parameters.TRACKER_CENTER_COLOR, -1)
        return frame

    def draw_estimate(self, frame):
        """
        Draws the estimated position on the frame if the estimator is enabled.

        Args:
            frame (np.ndarray): The video frame to draw the estimate on.

        Returns:
            np.ndarray: The frame with the estimate drawn on it.
        """
        if self.estimator_enabled and self.position_estimator:
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position:
                estimated_x, estimated_y = estimated_position[:2]
                cv2.circle(frame, (int(estimated_x), int(estimated_y)), 5, (0, 0, 255), -1)
                if Parameters.DISPLAY_DEVIATIONS:
                    self._display_deviation(estimated_x, estimated_y)
        return frame

    def _display_deviation(self, estimated_x, estimated_y):
        """Displays the relative deviation from the frame center."""
        frame_center = (self.video_handler.width / 2, self.video_handler.height / 2)
        relative_deviation_x = (estimated_x - frame_center[0]) / frame_center[0]
        relative_deviation_y = (estimated_y - frame_center[1]) / frame_center[1]
        logger.info(f"Estimated relative deviation from center: (X: {relative_deviation_x:.2f}, Y: {relative_deviation_y:.2f})")

    def reinitialize_tracker(self, frame, bbox):
        """
        Reinitializes the tracker with a new bounding box.

        Args:
            frame (np.ndarray): The video frame to reinitialize tracking.
            bbox (tuple): The new bounding box coordinates.
        """
        logger.info(f"Reinitializing tracker with bbox: {bbox}")
        self.init_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM)
        self.start_tracking(frame, bbox)

    def print_normalized_center(self):
        """Prints the normalized center coordinates of the bounding box."""
        frame_width, frame_height = self.video_handler.width, self.video_handler.height
        norm_x = self.center[0] / frame_width
        norm_y = self.center[1] / frame_height
        logger.debug(f"Normalized center: ({norm_x:.2f}, {norm_y:.2f})")

    @property
    def normalized_center(self):
        """Returns the normalized center coordinates."""
        frame_width, frame_height = self.video_handler.width, self.video_handler.height
        norm_x = self.center[0] / frame_width
        norm_y = self.center[1] / frame_height
        return (norm_x, norm_y)




