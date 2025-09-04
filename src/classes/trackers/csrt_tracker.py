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
from classes.tracker_output import TrackerOutput, TrackerDataType

logger = logging.getLogger(__name__)

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
        
        # Set tracking started flag
        self.tracking_started = True

        # Initialize appearance models using the detector
        if self.detector:
            self.detector.initial_features = self.detector.extract_features(frame, bbox)
            self.detector.adaptive_features = self.detector.initial_features.copy()

        self.prev_center = None  # Reset previous center
        self.last_update_time = time.time()

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Updates the tracker with the current frame and returns the tracking success status and the new bounding box.
        If override is enabled, uses the SmartTracker's selected object instead of CSRT internal tracking.

        Args:
            frame (np.ndarray): The current video frame.

        Returns:
            Tuple[bool, Tuple[int, int, int, int]]: Success flag and the updated bounding box.
        """
        dt = self.update_time()

        if self.override_active:
            # Smart tracking override is active; pull bbox from smart tracker
            smart_tracker = self.app_controller.smart_tracker
            if smart_tracker and smart_tracker.selected_bbox:
                self.prev_center = self.center
                x1, y1, x2, y2 = smart_tracker.selected_bbox
                w, h = x2 - x1, y2 - y1
                self.bbox = (x1, y1, w, h)
                self.set_center(((x1 + x2) // 2, (y1 + y2) // 2))
                self.normalize_bbox()
                self.center_history.append(self.center)

                self.confidence = 1.0  # Max confidence since override is trusted

                # Estimator update
                if self.estimator_enabled and self.position_estimator:
                    self.position_estimator.set_dt(dt)
                    self.position_estimator.predict_and_update(np.array(self.center))
                    estimated_position = self.position_estimator.get_estimate()
                    self.estimated_position_history.append(estimated_position)

                return True, self.bbox
            else:
                logging.warning("Override is active but SmartTracker has no selected bbox.")
                return False, self.bbox

        # Normal CSRT tracking
        success, detected_bbox = self.tracker.update(frame)
        
        if success:
            self.prev_center = self.center
            self.bbox = detected_bbox
            self.set_center((int(self.bbox[0] + self.bbox[2] / 2), int(self.bbox[1] + self.bbox[3] / 2)))
            self.normalize_bbox()
            self.center_history.append(self.center)

            # Update appearance model
            if self.detector:
                current_features = self.detector.extract_features(frame, self.bbox)
                self.detector.adaptive_features = (
                    (1 - Parameters.CSRT_APPEARANCE_LEARNING_RATE) * self.detector.adaptive_features +
                    Parameters.CSRT_APPEARANCE_LEARNING_RATE * current_features
                )

            # Confidence checks
            self.compute_confidence(frame)
            total_confidence = self.get_confidence()

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

    def get_output(self) -> TrackerOutput:
        """
        Returns CSRT-specific tracker output with enhanced velocity information.
        
        Overrides the base implementation to provide CSRT-specific features
        including velocity estimates from the position estimator.
        
        Returns:
            TrackerOutput: Enhanced CSRT tracker data
        """
        # Get velocity from estimator if available
        velocity = None
        if (self.estimator_enabled and self.position_estimator and 
            self.tracking_started and len(self.center_history) > 2):
            # Only use estimator velocity if we've been tracking for a few frames
            estimated_state = self.position_estimator.get_estimate()
            if estimated_state and len(estimated_state) >= 4:
                # Extract velocity components (dx, dy)
                vel_x, vel_y = estimated_state[2], estimated_state[3]
                # Only use velocity if it's meaningful (non-zero with minimum threshold)
                velocity_magnitude = (vel_x ** 2 + vel_y ** 2) ** 0.5
                if velocity_magnitude > 0.001:  # Minimum velocity threshold
                    velocity = (vel_x, vel_y)
                    logger.debug(f"CSRT: Using VELOCITY_AWARE - velocity: {velocity}, magnitude: {velocity_magnitude:.4f}")
                else:
                    logger.debug(f"CSRT: Ignoring near-zero velocity - magnitude: {velocity_magnitude:.4f}")
        elif self.estimator_enabled:
            logger.debug(f"CSRT: Estimator available but insufficient tracking history ({len(self.center_history) if self.center_history else 0} frames)")
        
        # Determine appropriate data type based on available data
        has_bbox = self.bbox is not None or self.normalized_bbox is not None
        has_velocity = velocity is not None
        
        if has_velocity:
            data_type = TrackerDataType.VELOCITY_AWARE
        elif has_bbox:
            data_type = TrackerDataType.BBOX_CONFIDENCE  
        else:
            data_type = TrackerDataType.POSITION_2D
            
        logger.debug(f"CSRT: Selected data_type: {data_type.value} (has_velocity: {has_velocity}, has_bbox: {has_bbox})")
        
        return TrackerOutput(
            data_type=data_type,
            timestamp=time.time(),
            tracking_active=self.tracking_started,
            tracker_id=f"CSRT_{id(self)}",
            position_2d=self.normalized_center,
            bbox=self.bbox,
            normalized_bbox=self.normalized_bbox,
            confidence=self.confidence,
            velocity=velocity,
            quality_metrics={
                'motion_consistency': self.compute_motion_confidence() if self.prev_center else 1.0,
                'appearance_confidence': getattr(self, 'appearance_confidence', 1.0)
            },
            raw_data={
                'center_history_length': len(self.center_history) if self.center_history else 0,
                'estimator_enabled': self.estimator_enabled,
                'estimator_providing_velocity': has_velocity,
                'velocity_magnitude': round((velocity[0]**2 + velocity[1]**2)**0.5, 4) if velocity else 0.0,
                'override_active': self.override_active,
                'csrt_tracker_name': self.trackerName,
                'estimated_position_history_length': len(self.estimated_position_history) if self.estimated_position_history else 0,
                'tracking_started': self.tracking_started
            },
            metadata={
                'tracker_class': self.__class__.__name__,
                'tracker_algorithm': 'CSRT',
                'has_estimator': bool(self.position_estimator),
                'supports_velocity': bool(self.position_estimator),
                'velocity_source': 'Kalman Estimator' if has_velocity else 'None',
                'schema_enhancement': 'Estimator' if has_velocity else 'Base Tracker',
                'center_pixel': self.center,
                'bbox_pixel': self.bbox,
                'opencv_version': cv2.__version__
            }
        )

    def get_capabilities(self) -> dict:
        """
        Returns CSRT-specific capabilities.
        
        Returns:
            dict: Enhanced capabilities for CSRT tracker
        """
        base_capabilities = super().get_capabilities()
        base_capabilities.update({
            'tracker_algorithm': 'CSRT',
            'supports_rotation': True,
            'supports_scale_change': True, 
            'supports_occlusion': True,
            'accuracy_rating': 'high',
            'speed_rating': 'medium',
            'opencv_tracker': True
        })
        return base_capabilities
