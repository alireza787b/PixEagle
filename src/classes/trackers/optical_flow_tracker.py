# src/classes/trackers/optical_flow_tracker.py

import cv2
import numpy as np
from typing import Optional, Tuple
import time
from classes.parameters import Parameters
from classes.trackers.base_tracker import BaseTracker

class OpticalFlowTracker(BaseTracker):
    """
    Optical Flow Tracker using the Lucas-Kanade method.
    Extends the BaseTracker class.
    """

    def __init__(self, video_handler: Optional[object] = None, detector: Optional[object] = None, app_controller: Optional[object] = None):
        super().__init__(video_handler, detector, app_controller)
        self.trackerName = "OpticalFlow"
        # Parameters for ShiTomasi corner detection
        self.feature_params = dict(
            maxCorners=Parameters.OPTICAL_FLOW_MAX_CORNERS,
            qualityLevel=Parameters.OPTICAL_FLOW_QUALITY_LEVEL,
            minDistance=Parameters.OPTICAL_FLOW_MIN_DISTANCE,
            blockSize=Parameters.OPTICAL_FLOW_BLOCK_SIZE
        )
        # Parameters for Lucas-Kanade optical flow
        self.lk_params = dict(
            winSize=(Parameters.OPTICAL_FLOW_WIN_SIZE, Parameters.OPTICAL_FLOW_WIN_SIZE),
            maxLevel=Parameters.OPTICAL_FLOW_MAX_LEVEL,
            criteria=(
                cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                Parameters.OPTICAL_FLOW_CRITERIA_COUNT,
                Parameters.OPTICAL_FLOW_CRITERIA_EPS
            )
        )
        self.prev_gray = None
        self.prev_points = None

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]):
        """
        Initializes tracking by detecting features within the bounding box.
        """
        self.prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        x, y, w, h = map(int, bbox)
        self.bbox = (x, y, w, h)
        self.set_center((x + w // 2, y + h // 2))
        self.normalize_bbox()

        # Define the Region of Interest (ROI) for feature detection
        roi_gray = self.prev_gray[y:y + h, x:x + w]
        mask = np.zeros_like(roi_gray)
        mask[:] = 255  # Use the whole ROI

        # Detect good features to track within the ROI
        self.prev_points = cv2.goodFeaturesToTrack(roi_gray, mask=mask, **self.feature_params)

        if self.prev_points is not None:
            # Adjust points' coordinates relative to the whole frame
            self.prev_points += np.array([[x, y]], dtype=np.float32)
        else:
            # If no points found, use the center
            self.prev_points = np.array([[[self.center[0], self.center[1]]]], dtype=np.float32)

        self.last_update_time = time.time()

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Updates the tracker with the new frame and computes the new bounding box.
        """
        dt = self.update_time()
        frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if self.prev_points is None or len(self.prev_points) == 0:
            # Tracking failure due to no points
            return False, self.bbox

        # Calculate optical flow to get new points
        next_points, status, err = cv2.calcOpticalFlowPyrLK(
            self.prev_gray, frame_gray, self.prev_points, None, **self.lk_params
        )

        # Select good points
        good_new = next_points[status == 1]
        good_prev = self.prev_points[status == 1]

        if len(good_new) < Parameters.OPTICAL_FLOW_MIN_POINTS:
            # Not enough points to track
            return False, self.bbox

        # Compute the transformation matrix
        transformation, _ = cv2.estimateAffinePartial2D(good_prev, good_new)
        if transformation is None:
            # Transformation could not be estimated
            return False, self.bbox

        # Update bounding box using the transformation matrix
        x, y, w, h = self.bbox
        bbox_corners = np.array([
            [x, y],
            [x + w, y],
            [x + w, y + h],
            [x, y + h]
        ], dtype=np.float32).reshape(-1, 1, 2)
        new_bbox_corners = cv2.transform(bbox_corners, transformation)
        new_bbox_corners = new_bbox_corners.reshape(-1, 2)

        x_new, y_new = np.min(new_bbox_corners, axis=0)
        x_max, y_max = np.max(new_bbox_corners, axis=0)
        w_new = x_max - x_new
        h_new = y_max - y_new

        self.bbox = (int(x_new), int(y_new), int(w_new), int(h_new))
        self.set_center((int(x_new + w_new / 2), int(y_new + h_new / 2)))
        self.normalize_bbox()

        if self.estimator_enabled:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_and_update(self.center)
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)

        # Prepare for next frame
        self.prev_gray = frame_gray.copy()
        self.prev_points = good_new.reshape(-1, 1, 2)

        return True, self.bbox
