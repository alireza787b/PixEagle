import time
import cv2
import logging
from collections import deque
from .parameters import Parameters
from .position_estimator import PositionEstimator

logger = logging.getLogger(__name__)

class Tracker:
    def __init__(self, video_handler=None, detector=None,app_controller=None):
        """
        Initializes the Tracker with a specific tracking algorithm and optional video handler and detector.

        Args:
            video_handler (VideoHandler, optional): An instance of the VideoHandler class.
            detector (Detector, optional): An instance of the Detector class.
        """
        self.tracker = None
        self.video_handler = video_handler
        self.bbox = None  # Current bounding box
        self.normalized_bbox = None  # Normalized bounding box coordinates
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
        
        if Parameters.USE_DETECTOR and self.detector:
            self.detector.extract_features(frame, bbox)

        self.last_update_time = time.time()

    def update(self, frame):
        """
        Updates the tracker with the new frame, and manages bounding box, center, and estimator.

        Args:
            frame (np.ndarray): The video frame to update the tracker.

        Returns:
            tuple: A boolean indicating success and the updated bounding box.
        """
        current_time = time.time()
        success, self.bbox = self.tracker.update(frame)
        dt = current_time - self.last_update_time if self.last_update_time else 0
        self.last_update_time = current_time
        
        if success:
            self._update_center()
            self._update_estimator(dt)
        
        return success, self.bbox

    def _update_center(self):
        """Calculates and stores the center of the current bounding box."""
        self.center = (int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2))
        self.center_history.append(self.center)
        logger.debug(f"Updated center: {self.center}")

    def _update_estimator(self, dt):
        """Updates the position estimator if enabled."""
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_and_update(self.center)
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)
            logger.debug(f"Estimated position: {estimated_position}")

    def draw_estimate(self, frame):
        """
        Draws the estimated position on the frame if the estimator is enabled.

        Args:
            frame (np.ndarray): The video frame to draw the estimate on.

        Returns:
            np.ndarray: The frame with the estimate drawn on it.
        """
        if self.estimator_enabled and self.position_estimator and self.video_handler:
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

    def select_roi(self, frame):
        """
        Allows the user to manually select the ROI for tracking on the given frame.

        Args:
            frame (np.ndarray): The video frame to select ROI on.

        Returns:
            tuple: The selected bounding box coordinates.
        """
        bbox = cv2.selectROI("Frame", frame, False, False)
        cv2.destroyWindow("Frame")
        logger.debug(f"Selected ROI: {bbox}")
        return bbox

    def reinitialize_tracker(self, frame, bbox):
        """
        Reinitializes the tracker with a new bounding box.

        Args:
            frame (np.ndarray): The video frame to reinitialize tracking.
            bbox (tuple): The new bounding box coordinates.
        """
        logger.info(f"Reinitializing tracker with bbox: {bbox}")
        self.start_tracking(frame, bbox)
