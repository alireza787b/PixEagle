# src/classes/trackers/base_tracker.py

"""
BaseTracker Module
------------------

This module defines the abstract base class `BaseTracker` for all object trackers used in the tracking system.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: October 2024
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The `BaseTracker` class provides a common interface and shared functionalities for different tracking algorithms. It defines the essential methods and attributes that all concrete tracker classes must implement or utilize.

Purpose:
--------
In the context of aerial target tracking, having a unified tracker interface ensures that different tracking algorithms can be swapped or tested with minimal changes to the overall system. This promotes modularity, scalability, and ease of maintenance.

Key Features:
-------------
- **Abstract Methods**: Enforces implementation of essential methods like `start_tracking` and `update`.
- **Common Attributes**: Manages shared properties such as bounding boxes, centers, and normalization.
- **Estimator Integration**: Supports integration with estimators (e.g., Kalman Filter) to enhance tracking robustness.
- **Visualization Tools**: Provides methods for drawing tracking information on video frames.
- **Confidence Score**: Implements a standardized confidence score based on motion and appearance consistency.

Usage:
------
The `BaseTracker` class is intended to be subclassed by concrete tracker implementations (e.g., `CSRTTracker`). Developers should implement the abstract methods and can override or extend other methods as needed.

Example:
```python
class CustomTracker(BaseTracker):
    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        # Custom implementation
        pass

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        # Custom implementation
        pass
```

Extending and Building New Trackers:
------------------------------------
To create a new tracker:
1. Subclass `BaseTracker`.
2. Implement all abstract methods (`start_tracking`, `update`).
3. Override or extend other methods as necessary.
4. Add the new tracker to the `tracker_factory.py` for easy instantiation.

Notes:
------
- **Estimator Usage**: Trackers can utilize estimators by enabling `estimator_enabled` and providing a `position_estimator`.
- **Normalization**: Provides methods to normalize coordinates, which is essential for control inputs that require normalized values.
- **Visualization**: Includes methods for drawing bounding boxes and tracking information, aiding in debugging and monitoring.
- **Confidence Score**: Standardizes confidence calculation across trackers for consistency.

Integration:
------------
The tracker is integrated into the main application via the `AppController`. It receives frames from the video handler, processes them, and provides tracking information to other components like the estimator and follower.

Recommendations:
----------------
- **Consistency Checks**: Implement motion and appearance consistency checks to enhance robustness.
- **Logging**: Utilize logging to monitor tracker performance and catch potential issues.
- **Parameter Tuning**: Adjust parameters in `Parameters` class to optimize tracking performance based on the specific use case.

References:
-----------
- OpenCV Tracking API: https://docs.opencv.org/master/d9/df8/group__tracking.html
- Object Tracking Concepts: https://www.learnopencv.com/object-tracking-using-opencv-cpp-python/

"""

from abc import ABC, abstractmethod
from collections import deque
import time
import numpy as np
from typing import Optional, Tuple, Dict, Any
import cv2
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType, create_legacy_tracker_output
import logging

logger = logging.getLogger(__name__)

class BaseTracker(ABC):
    """
    Abstract Base Class for Object Trackers

    Defines the interface and common functionalities for different tracking algorithms used in the system.

    Attributes:
    -----------
    - video_handler (Optional[object]): Handler for video streaming and processing.
    - detector (Optional[object]): Detector for appearance-based methods.
    - app_controller (Optional[object]): Reference to the main application controller.
    - bbox (Optional[Tuple[int, int, int, int]]): Current bounding box (x, y, width, height).
    - prev_center (Optional[Tuple[int, int]]): Previous center of the bounding box.
    - center (Optional[Tuple[int, int]]): Current center of the bounding box.
    - normalized_bbox (Optional[Tuple[float, float, float, float]]): Normalized bounding box.
    - normalized_center (Optional[Tuple[float, float]]): Normalized center coordinates.
    - center_history (deque): History of center positions.
    - estimator_enabled (bool): Indicates if the estimator is enabled.
    - position_estimator (Optional[BaseEstimator]): Estimator instance for position estimation.
    - estimated_position_history (deque): History of estimated positions.
    - last_update_time (float): Timestamp of the last update.
    - frame (Optional[np.ndarray]): Placeholder for the current video frame.
    - confidence (float): Confidence score of the tracker.

    Methods:
    --------
    - start_tracking(frame, bbox): Abstract method to start tracking with an initial frame and bounding box.
    - update(frame): Abstract method to update the tracker with a new frame.
    - compute_confidence(frame): Computes the confidence score based on motion and appearance consistency.
    - get_confidence(): Returns the current confidence score.
    - is_motion_consistent(): Checks if the motion is consistent based on displacement thresholds.
    - update_time(): Updates the internal timer and calculates the time delta since the last update.
    - normalize_center_coordinates(): Normalizes the center coordinates relative to the frame size.
    - print_normalized_center(): Logs the normalized center coordinates.
    - set_center(value): Sets the center coordinates and normalizes them.
    - normalize_bbox(): Normalizes the bounding box coordinates relative to the frame size.
    - reinitialize_tracker(frame, bbox): Reinitializes the tracker with a new bounding box.
    - draw_tracking(frame, tracking_successful): Draws tracking bounding box and center on the frame.
    - draw_normal_bbox(frame, tracking_successful): Draws a standard rectangle bounding box.
    - draw_fancy_bbox(frame, tracking_successful): Draws a stylized bounding box with additional visuals.
    - draw_estimate(frame, tracking_successful): Draws the estimated position from the estimator.
    """

    def __init__(self, video_handler: Optional[object] = None, detector: Optional[object] = None, app_controller: Optional[object] = None):
        """
        Initializes the base tracker with common attributes.

        Args:
            video_handler (Optional[object]): Handler for video streaming and processing.
            detector (Optional[object]): Detector for appearance-based methods.
            app_controller (Optional[object]): Reference to the main application controller.
        """
        self.video_handler = video_handler
        self.detector = detector
        self.app_controller = app_controller  # Assign before using it

        # Initialize tracking attributes
        self.bbox: Optional[Tuple[int, int, int, int]] = None  # Current bounding box
        self.prev_center: Optional[Tuple[int, int]] = None     # Previous center
        self.center: Optional[Tuple[int, int]] = None          # Current center
        self.normalized_bbox: Optional[Tuple[float, float, float, float]] = None  # Normalized bounding box
        self.normalized_center: Optional[Tuple[float, float]] = None              # Normalized center
        self.center_history = deque(maxlen=Parameters.CENTER_HISTORY_LENGTH)      # History of centers
        
        # Tracking state management
        self.tracking_started: bool = False  # Whether this tracker has been started

        # Estimator initialization
        self.estimator_enabled = Parameters.USE_ESTIMATOR
        self.position_estimator = self.app_controller.estimator if self.estimator_enabled else None
        self.estimated_position_history = deque(maxlen=Parameters.ESTIMATOR_HISTORY_LENGTH)
        self.last_update_time: float = 1e-6

        # Confidence score
        self.confidence: float = 1.0  # Initialize confidence score

        # Frame placeholder
        self.frame = None

        self.override_active:bool  = False
        self.override_bbox: Optional[Tuple[int, int, int, int]] = None
        self.override_center: Optional[Tuple[int, int]] = None

        # Component suppression support (for trackers that don't need image processing)
        self.suppress_detector = False
        self.suppress_predictor = False

        # Initialize tracker instance using polymorphic method
        # Subclasses override _create_tracker() to return their specific tracker type
        self.tracker = self._create_tracker()

    @abstractmethod
    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Abstract method to start tracking with the given frame and bounding box.

        Args:
            frame (np.ndarray): The initial video frame to start tracking.
            bbox (Tuple[int, int, int, int]): A tuple representing the bounding box (x, y, width, height).
        """
        pass

    @abstractmethod
    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Abstract method to update the tracker with the new frame.

        Args:
            frame (np.ndarray): The current video frame.

        Returns:
            Tuple[bool, Tuple[int, int, int, int]]: A tuple containing the success status and the new bounding box.
        """
        pass

    def stop_tracking(self) -> None:
        """
        Stops the tracker and resets its state.
        """
        self.tracking_started = False
        self.bbox = None
        self.center = None
        self.prev_center = None
        self.normalized_bbox = None
        self.normalized_center = None
        self.confidence = 1.0
        logger.debug(f"{self.__class__.__name__} tracking stopped and state reset")

    def compute_confidence(self, frame: np.ndarray) -> float:
        """
        Computes the confidence score based on motion and appearance consistency.

        Args:
            frame (np.ndarray): The current video frame.

        Returns:
            float: The updated confidence score.
        """
        motion_confidence = self.compute_motion_confidence()
        appearance_confidence = 1.0  # Default to maximum confidence

        if self.detector and hasattr(self.detector, 'compute_appearance_confidence') and self.detector.adaptive_features is not None:
            current_features = self.detector.extract_features(frame, self.bbox)
            appearance_confidence = self.detector.compute_appearance_confidence(current_features, self.detector.adaptive_features)
        else:
            logger.warning("Detector is not available or adaptive features are not set.")

        # Combine motion and appearance confidence
        self.confidence = (Parameters.MOTION_CONFIDENCE_WEIGHT * motion_confidence +
                           Parameters.APPEARANCE_CONFIDENCE_WEIGHT * appearance_confidence)
        return self.confidence

    def get_confidence(self) -> float:
        """
        Returns the current confidence score of the tracker.

        Returns:
            float: The confidence score.
        """
        return self.confidence

    def compute_motion_confidence(self) -> float:
        """
        Computes confidence based on motion consistency.

        Returns:
            float: The motion confidence score between 0.0 and 1.0.

        A lower confidence indicates unexpected large movements, possibly due to tracking errors.
        """
        if self.prev_center is None:
            return 1.0  # Maximum confidence on first frame
        displacement = np.linalg.norm(np.array(self.center) - np.array(self.prev_center))
        frame_diag = np.hypot(self.video_handler.width, self.video_handler.height)
        confidence = max(0.0, 1.0 - (displacement / (Parameters.MAX_DISPLACEMENT_THRESHOLD * frame_diag)))
        return confidence

    def is_motion_consistent(self) -> bool:
        """
        Checks if the motion between the previous and current center is within expected limits.

        Returns:
            bool: True if motion is consistent, False otherwise.
        """
        return self.compute_motion_confidence() >= Parameters.MOTION_CONFIDENCE_THRESHOLD

    def update_time(self) -> float:
        """
        Updates the time interval (dt) between consecutive frames.

        Returns:
            float: The time difference since the last update.
        """
        current_time = time.monotonic()
        dt = current_time - self.last_update_time
        if dt <= 0:
            dt = 1e-3  # Set a reasonable minimal dt (1ms) to avoid log spam
        self.last_update_time = current_time
        return dt

    def normalize_center_coordinates(self) -> None:
        """
        Normalizes and stores the center coordinates of the tracked target.

        Normalization is done such that the center of the frame is (0, 0),
        the top-right is (1, 1), and the bottom-left is (-1, -1).
        """
        if self.center:
            frame_width, frame_height = self.video_handler.width, self.video_handler.height
            normalized_x = (self.center[0] - frame_width / 2) / (frame_width / 2)
            normalized_y = (self.center[1] - frame_height / 2) / (frame_height / 2)
            self.normalized_center = (normalized_x, normalized_y)

    def print_normalized_center(self) -> None:
        """
        Logs the normalized center coordinates of the tracked target.

        Assumes `normalize_center_coordinates` has been called after the latest tracking update.
        """
        if self.normalized_center:
            # logging.debug(f"Normalized Center Coordinates: {self.normalized_center}")
            pass
        else:
            logger.warning("Normalized center coordinates not calculated or available.")

    def set_center(self, value: Tuple[int, int]) -> None:
        """
        Sets the center of the bounding box and normalizes it.

        Args:
            value (Tuple[int, int]): The (x, y) coordinates of the center.
        """
        self.center = value
        self.normalize_center_coordinates()  # Automatically normalize when center is updated

    def normalize_bbox(self) -> None:
        """
        Normalizes the bounding box coordinates relative to the frame size.

        This is useful for consistent representation and for control inputs that require normalized values.
        """
        if self.bbox and self.video_handler:
            frame_width, frame_height = self.video_handler.width, self.video_handler.height
            x, y, w, h = self.bbox
            norm_x = (x - frame_width / 2) / (frame_width / 2)
            norm_y = (y - frame_height / 2) / (frame_height / 2)
            norm_w = w / frame_width
            norm_h = h / frame_height
            self.normalized_bbox = (norm_x, norm_y, norm_w, norm_h)
            # logging.debug(f"Normalized bbox: {self.normalized_bbox}")

    def reinitialize_tracker(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Reinitializes the tracker with a new bounding box on the given frame.

        Args:
            frame (np.ndarray): The video frame to reinitialize tracking.
            bbox (Tuple[int, int, int, int]): The new bounding box for tracking.

        This can be used when the tracker loses the target or when manual reinitialization is required.
        """
        logger.info(f"Reinitializing tracker with bbox: {bbox}")
        self.start_tracking(frame, bbox)

    def draw_tracking(self, frame: np.ndarray, tracking_successful: bool = True) -> np.ndarray:
        """
        Draws the tracking bounding box and center on the frame.

        Args:
            frame (np.ndarray): The video frame.
            tracking_successful (bool): Whether the tracking was successful.

        Returns:
            np.ndarray: The frame with tracking drawn.
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

        Args:
            frame (np.ndarray): The video frame.
            tracking_successful (bool): Whether the tracking was successful.
        """
        p1 = (int(self.bbox[0]), int(self.bbox[1]))
        p2 = (int(self.bbox[0] + self.bbox[2]), int(self.bbox[1] + self.bbox[3]))
        color = (255, 0, 0) if tracking_successful else (0, 0, 255)
        cv2.rectangle(frame, p1, p2, color, 2)

    def draw_fancy_bbox(self, frame, tracking_successful: bool = True):
        """
        Draws a stylized bounding box with additional visuals, such as crosshairs and extended lines.

        Args:
            frame (np.ndarray): The video frame.
            tracking_successful (bool): Whether the tracking was successful.
        """
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

        Args:
            frame (np.ndarray): The video frame.
            tracking_successful (bool): Whether the tracking was successful.

        Returns:
            np.ndarray: The frame with the estimate drawn on it.
        """
        if self.estimator_enabled and self.position_estimator and self.video_handler:
            estimated_position = self.position_estimator.get_estimate()
            if estimated_position:
                estimated_x, estimated_y = estimated_position[:2]
                color = Parameters.ESTIMATED_POSITION_COLOR if tracking_successful else Parameters.ESTIMATION_ONLY_COLOR
                cv2.circle(frame, (int(estimated_x), int(estimated_y)), 5, color, -1)
        return frame



    def set_external_override(self, bbox: Tuple[int, int, int, int], center: Tuple[int, int]) -> None:
        """
        Enables override mode and sets the tracker's bounding box and center manually.
        Used by SmartTracker to inject detections directly.

        Args:
            bbox (Tuple[int, int, int, int]): The bounding box (x, y, x2, y2).
            center (Tuple[int, int]): The (x, y) center of the selected target.
        """
        # Only log on first override activation (state change)
        was_active = self.override_active

        self.override_active = True
        self.bbox = (bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1])  # Convert x1,y1,x2,y2 to x,y,w,h
        self.set_center(center)
        self.center_history.append(center)
        self.normalize_bbox()

        # Log only when override is first activated (not every frame update)
        if not was_active:
            logger.info("[OVERRIDE] SmartTracker override activated")

    def clear_external_override(self) -> None:
        """
        Disables external override (used when cancelling SmartTracker mode).
        """
        if self.override_active:  # Only log if actually clearing
            self.override_active = False
            self.bbox = None
            self.center = None
            logger.info("[OVERRIDE] SmartTracker override cleared")


    def get_effective_bbox(self) -> Optional[Tuple[int, int, int, int]]:
        """
        Returns the active bounding box: override if active, else internal tracker bbox.
        """
        return self.override_bbox if self.override_active else self.bbox

    def get_effective_center(self) -> Optional[Tuple[int, int]]:
        """
        Returns the active center: override if active, else internal tracker center.
        """
        return self.override_center if self.override_active else self.center

    def _normalize_center_static(self, center: Tuple[int, int]) -> Tuple[float, float]:
        """
        Normalizes a center point statically (without modifying class state).

        Returns:
            Tuple[float, float]: Normalized (x, y) in range [-1, 1]
        """
        frame_width, frame_height = self.video_handler.width, self.video_handler.height
        x, y = center
        norm_x = (x - frame_width / 2) / (frame_width / 2)
        norm_y = (y - frame_height / 2) / (frame_height / 2)
        return (norm_x, norm_y)

    def _normalize_bbox_static(self, bbox: Tuple[int, int, int, int]) -> Tuple[float, float, float, float]:
        """
        Normalizes a bounding box statically (without modifying class state).

        Returns:
            Tuple[float, float, float, float]: Normalized (x, y, w, h)
        """
        frame_width, frame_height = self.video_handler.width, self.video_handler.height
        x, y, w, h = bbox
        norm_x = (x - frame_width / 2) / (frame_width / 2)
        norm_y = (y - frame_height / 2) / (frame_height / 2)
        norm_w = w / frame_width
        norm_h = h / frame_height
        return (norm_x, norm_y, norm_w, norm_h)
    

    def _create_tracker(self):
        """
        Creates and returns a new tracker instance.

        This method should be overridden by subclasses to return their specific tracker type.
        BaseTracker returns None since it's abstract and doesn't have a specific tracker.

        Returns:
            Tracker instance or None for abstract base class
        """
        return None

    def reset(self):
        self.bbox = None
        self.center = None
        self.override_active = False
        self.override_bbox = None
        self.override_center = None
        self.center_history.clear()
        self.estimated_position_history.clear()
        self.prev_center = None
        self.last_update_time = time.time()
        if self.position_estimator:
            self.position_estimator.reset()
        # Re-instantiate the tracker using polymorphic method
        self.tracker = self._create_tracker()
        logger.info("Tracker fully reset")

    def get_output(self) -> TrackerOutput:
        """
        Returns standardized tracker output in the new flexible schema format.
        
        This method provides the unified interface for all tracker types,
        ensuring consistent data access across the application.
        
        Returns:
            TrackerOutput: Structured tracker data with all available information
        """
        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=self.tracking_started,
            tracker_id=self.__class__.__name__,
            position_2d=self.normalized_center,
            bbox=self.bbox,
            normalized_bbox=self.normalized_bbox,
            confidence=self.confidence,
            velocity=None,  # Can be overridden by subclasses
            raw_data={
                'center_history_length': len(self.center_history) if self.center_history else 0,
                'estimator_enabled': self.estimator_enabled,
                'override_active': self.override_active,
                'tracking_started': self.tracking_started
            },
            metadata={
                'tracker_class': self.__class__.__name__,
                'has_estimator': bool(self.position_estimator),
                'center_pixel': self.center,
                'bbox_pixel': self.bbox
            }
        )

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Returns the capabilities of this tracker implementation.
        
        Returns:
            Dict[str, Any]: Tracker capabilities and supported features
        """
        return {
            'data_types': [TrackerDataType.POSITION_2D.value],
            'supports_confidence': True,
            'supports_velocity': bool(self.position_estimator),
            'supports_bbox': True,
            'supports_normalization': True,
            'estimator_available': bool(self.position_estimator),
            'multi_target': False,
            'real_time': True
        }

    def get_legacy_data(self) -> Dict[str, Any]:
        """
        Returns data in the legacy format for backwards compatibility.

        Returns:
            Dict[str, Any]: Legacy format data structure
        """
        return {
            'bounding_box': self.normalized_bbox,
            'center': self.normalized_center,
            'confidence': self.confidence,
            'tracker_started': self.tracking_started if hasattr(self, 'tracking_started') else bool(self.center),
            'timestamp': time.time()
        }

    def is_detector_suppressed(self) -> bool:
        """
        Check if detector component is suppressed for this tracker.

        Returns:
            bool: True if detector should be suppressed
        """
        return getattr(self, 'suppress_detector', False)

    def is_predictor_suppressed(self) -> bool:
        """
        Check if predictor component is suppressed for this tracker.

        Returns:
            bool: True if predictor should be suppressed
        """
        return getattr(self, 'suppress_predictor', False)

    def get_suppression_status(self) -> Dict[str, bool]:
        """
        Get the suppression status of all components.

        Returns:
            Dict[str, bool]: Suppression status for each component
        """
        return {
            'detector_suppressed': self.is_detector_suppressed(),
            'predictor_suppressed': self.is_predictor_suppressed()
        }

