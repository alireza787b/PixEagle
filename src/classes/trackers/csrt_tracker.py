# src/classes/trackers/csrt_tracker.py

"""
CSRTTracker Module
------------------

This module implements the `CSRTTracker` class, a concrete tracker that uses the CSRT (Channel and Spatial Reliability Tracking) algorithm provided by OpenCV.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: October 2024
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The `CSRTTracker` class extends the `BaseTracker` and specializes in object tracking using the CSRT algorithm. CSRT is known for its accuracy in tracking objects with rotation, scale changes, and partial occlusions.

Purpose:
--------
The CSRT tracker is used for tracking objects in video streams where high accuracy is required, and the objects may undergo significant changes in appearance or motion.

Key Features:
-------------
- **High Accuracy**: Utilizes CSRT algorithm for precise tracking.
- **Estimator Integration**: Works seamlessly with the estimator for enhanced position estimation.
- **Confidence Calculation**: Uses standardized confidence calculation from the base tracker.

Usage:
------
The `CSRTTracker` can be instantiated via the `tracker_factory.py` and requires a video handler, detector, and app controller.

Example:
```python
tracker = CSRTTracker(video_handler, detector, app_controller)
tracker.start_tracking(initial_frame, initial_bbox)
```

Notes:
------
- **Estimator Dependency**: If an estimator is enabled, ensure it is properly initialized and reset.
- **Parameter Tuning**: Adjust parameters in the `Parameters` class, such as `APPEARANCE_THRESHOLD` and `CONFIDENCE_THRESHOLD`, to optimize performance.
- **OpenCV Version**: Requires OpenCV with the tracking module (usually `opencv-contrib-python`).

References:
-----------
- OpenCV CSRT Tracker
- CSRT Paper: Lukezic et al., "Discriminative Correlation Filter with Channel and Spatial Reliability," CVPR 2017.

"""

import logging
import time
import cv2
import numpy as np
from typing import Optional, Tuple
from classes.parameters import Parameters
from classes.trackers.base_tracker import BaseTracker

class CSRTTracker(BaseTracker):
    """
    CSRTTracker Class

    Implements object tracking using the CSRT algorithm, extending the `BaseTracker`.

    Attributes:
    -----------
    - tracker (cv2.Tracker): OpenCV CSRT tracker instance.
    - trackerName (str): Name identifier for the tracker.

    Methods:
    --------
    - start_tracking(frame, bbox): Initializes the tracker with the provided bounding box.
    - update(frame): Updates the tracker and performs consistency checks.
    - update_estimator_without_measurement(): Updates the estimator when no measurement is available.
    - get_estimated_position(): Retrieves the current estimated position from the estimator.
    """

    def __init__(self, video_handler: Optional[object] = None, detector: Optional[object] = None, app_controller: Optional[object] = None):
        """
        Initializes the CSRT tracker with a video handler, detector, and app controller.

        Args:
            video_handler (Optional[object]): Handler for video streaming and processing.
            detector (Optional[object]): Object detector for appearance-based methods.
            app_controller (Optional[object]): Reference to the main application controller.
        """
        super().__init__(video_handler, detector, app_controller)
        self.tracker = cv2.TrackerCSRT_create()  # Tracker specific to CSRT
        self.trackerName: str = "CSRT"
        if self.position_estimator:
            self.position_estimator.reset()

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Initializes the tracker with the provided bounding box on the given frame.

        Args:
            frame (np.ndarray): The initial video frame.
            bbox (Tuple[int, int, int, int]): A tuple representing the bounding box (x, y, width, height).
        """
        logging.info(f"Initializing {self.trackerName} tracker with bbox: {bbox}")
        self.tracker.init(frame, bbox)

        # Initialize appearance models using the detector
        if self.detector:
            self.detector.initial_features = self.detector.extract_features(frame, bbox)
            self.detector.adaptive_features = self.detector.initial_features.copy()

        self.prev_center = None  # Reset previous center
        self.last_update_time = time.time()

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Updates the tracker with the current frame and returns the tracking success status and the new bounding box.

        Args:
            frame (np.ndarray): The current video frame.

        Returns:
            Tuple[bool, Tuple[int, int, int, int]]: A tuple containing the success status and the new bounding box.
        """
        dt = self.update_time()
        success, detected_bbox = self.tracker.update(frame)
        
        if success:
            self.prev_center = self.center  # Store the previous center
            self.bbox = detected_bbox
            self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
            self.normalize_bbox()
            self.center_history.append(self.center)

            # Update adaptive appearance model using the detector
            if self.detector:
                current_features = self.detector.extract_features(frame, self.bbox)
                self.detector.adaptive_features = (1 - Parameters.CSRT_APPEARANCE_LEARNING_RATE) * self.detector.adaptive_features + \
                                          Parameters.CSRT_APPEARANCE_LEARNING_RATE * current_features

            # Compute confidence scores
            self.compute_confidence(frame)
            total_confidence = self.get_confidence()
            logging.debug(f"Total Confidence: {total_confidence}")

            # Perform consistency checks
            if self.confidence < Parameters.CONFIDENCE_THRESHOLD:
                logging.warning("Tracking failed due to low confidence.")
                success = False

            if success and self.estimator_enabled and self.position_estimator:
                self.position_estimator.set_dt(dt)
                self.position_estimator.predict_and_update(np.array(self.center))
                estimated_position = self.position_estimator.get_estimate()
                self.estimated_position_history.append(estimated_position)
        else:
            logging.warning("Tracking update failed in tracker algorithm.")
            # Optionally, handle estimator update without measurement
            
        return success, self.bbox

    def update_estimator_without_measurement(self) -> None:
        """
        Updates the position estimator when no measurement is available.

        This is useful when the tracker fails to provide a measurement, allowing the estimator to predict the next state.
        """
        dt = self.update_time()
        if self.estimator_enabled and self.position_estimator:
            self.position_estimator.set_dt(dt)
            self.position_estimator.predict_only()
            estimated_position = self.position_estimator.get_estimate()
            self.estimated_position_history.append(estimated_position)
            logging.debug(f"Estimated position (without measurement): {estimated_position}")
        else:
            logging.warning("Estimator is not enabled or not initialized.")

    def get_estimated_position(self) -> Optional[Tuple[float, float]]:
        """
        Gets the current estimated position from the estimator.

        Returns:
            Optional[Tuple[float, float]]: The estimated (x, y) position or None if unavailable.
        """
        if self.estimator_enabled and self.position_estimator:
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position and len(estimated_position) >= 2:
                return (estimated_position[0], estimated_position[1])
        return None
