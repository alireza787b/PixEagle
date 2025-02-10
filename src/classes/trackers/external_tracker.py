# src/classes/trackers/external_tracker.py

"""
ExternalTracker Module
------------------------

This module implements the ExternalTracker class which adheres to the BaseTracker interface.
Instead of processing video frames to compute a bounding box, it relies on externally provided
data (e.g., via UDP or another communication channel) to update the bounding box. This class
allows the rest of the system (e.g., follower, telemetry, OSD) to operate unchanged.

Author: Alireza Ghaderi
Date: [Insert Date]
"""

import time
import logging
import cv2
import numpy as np
from classes.trackers.base_tracker import BaseTracker
from classes.parameters import Parameters

class ExternalTracker(BaseTracker):
    """
    ExternalTracker Class

    This tracker does not perform any image processing for tracking. Instead, it waits for an
    external input to provide a bounding box. It implements the same interface as other trackers
    so that the rest of the application remains unaware of the difference.

    Attributes:
        latest_bbox (tuple): The most recent bounding box received from an external source,
                             in the format (x, y, width, height).
        last_update_time (float): Timestamp of the last bounding box update.
    """

    def __init__(self, video_handler=None, detector=None, app_controller=None):
        """
        Initialize the ExternalTracker.

        Args:
            video_handler (object, optional): The video handler instance (may be None if video is not processed).
            detector (object, optional): Detector instance (not used in external mode).
            app_controller (object, optional): Reference to the main AppController.
        """
        super().__init__(video_handler, detector, app_controller)
        self.latest_bbox = None
        self.last_update_time = time.time()
        logging.info("ExternalTracker initialized. Waiting for external bounding box updates.")

    def start_tracking(self, frame, bbox):
        """
        Start tracking by initializing the tracker state with the provided bounding box.
        In external mode, this simply stores the bounding box.

        Args:
            frame (numpy.ndarray): The current video frame (not used for processing).
            bbox (tuple): The bounding box (x, y, width, height) to start tracking.
        """
        try:
            self.bbox = bbox
            self.latest_bbox = bbox
            # Calculate and set the center of the bounding box.
            center_x = int(bbox[0] + bbox[2] / 2)
            center_y = int(bbox[1] + bbox[3] / 2)
            self.set_center((center_x, center_y))
            self.normalize_bbox()
            logging.info(f"ExternalTracker started with bbox: {bbox}")
        except Exception as e:
            logging.error(f"Error in start_tracking of ExternalTracker: {e}")

    def update(self, frame):
        """
        Update the tracker state. For ExternalTracker, the frame is ignored and the method returns
        the latest externally provided bounding box.

        Args:
            frame (numpy.ndarray): The current video frame (ignored).

        Returns:
            tuple: (success_flag, bbox) where success_flag is True if a bounding box exists,
                   otherwise False; bbox is the current bounding box.
        """
        try:
            if self.latest_bbox is not None:
                self.bbox = self.latest_bbox
                center_x = int(self.bbox[0] + self.bbox[2] / 2)
                center_y = int(self.bbox[1] + self.bbox[3] / 2)
                self.set_center((center_x, center_y))
                self.normalize_bbox()
                return True, self.bbox
            else:
                logging.warning("ExternalTracker update called but no bounding box has been set yet.")
                return False, None
        except Exception as e:
            logging.error(f"Error in update of ExternalTracker: {e}")
            return False, None

    def set_external_bbox(self, bbox):
        """
        Update the tracker with a new bounding box from an external source.

        Args:
            bbox (tuple): The new bounding box (x, y, width, height) in pixel coordinates.
        """
        try:
            self.latest_bbox = bbox
            self.bbox = bbox
            center_x = int(bbox[0] + bbox[2] / 2)
            center_y = int(bbox[1] + bbox[3] / 2)
            self.set_center((center_x, center_y))
            self.normalize_bbox()
            self.last_update_time = time.time()
            logging.info(f"ExternalTracker updated with new bbox: {bbox}")
        except Exception as e:
            logging.error(f"Error in set_external_bbox: {e}")

    def get_confidence(self):
        """
        Returns a constant high confidence value, assuming the external bounding box is reliable.

        Returns:
            float: Always returns 1.0.
        """
        return 1.0

    def update_estimator_without_measurement(self):
        """
        If an estimator is enabled, update its state using the current center.
        """
        try:
            dt = time.time() - self.last_update_time
            if self.estimator_enabled and self.position_estimator:
                self.position_estimator.set_dt(dt)
                self.position_estimator.predict_and_update(np.array(self.center))
                self.estimated_position_history.append(self.position_estimator.get_estimate())
        except Exception as e:
            logging.error(f"Error in update_estimator_without_measurement: {e}")

    def draw_tracking(self, frame, tracking_successful=True):
        """
        Draw the externally provided bounding box and center on the frame for visualization.

        Args:
            frame (numpy.ndarray): The video frame.
            tracking_successful (bool): Indicator if tracking is considered successful.

        Returns:
            numpy.ndarray: The video frame with overlay graphics.
        """
        try:
            if self.bbox and frame is not None:
                p1 = (int(self.bbox[0]), int(self.bbox[1]))
                p2 = (int(self.bbox[0] + self.bbox[2]), int(self.bbox[1] + self.bbox[3]))
                color = (255, 0, 0) if tracking_successful else (0, 0, 255)
                cv2.rectangle(frame, p1, p2, color, 2)
                cv2.circle(frame, self.center, 5, (0, 255, 0), -1)
            return frame
        except Exception as e:
            logging.error(f"Error in draw_tracking of ExternalTracker: {e}")
            return frame

    def reinitialize_tracker(self, frame, bbox):
        """
        Reinitialize the tracker with a new bounding box.
        For ExternalTracker, this simply updates the current bounding box.

        Args:
            frame (numpy.ndarray): The video frame (ignored).
            bbox (tuple): The new bounding box to use.
        """
        self.set_external_bbox(bbox)
