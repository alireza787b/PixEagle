# src/classes/trackers/gimbal_tracker.py

"""
GimbalTracker Module
===================

This module implements the GimbalTracker class, which integrates gimbal angle data
into PixEagle's tracking system. It receives real-time yaw, pitch, roll angles
via UDP and converts them to normalized target vectors.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The GimbalTracker extends BaseTracker to provide:
- Real-time UDP angle reception from gimbal systems
- Conversion of gimbal angles to target vectors
- Integration with PixEagle's schema-driven architecture
- Support for both GIMBAL_BODY and SPATIAL_FIXED coordinate systems

Key Features:
-------------
- Black-box integration with GimbalInterface for UDP communication
- Real-time coordinate transformations
- Schema-compliant TrackerOutput generation
- Confidence calculation based on data freshness and connection quality
- Automatic detector/predictor suppression (no image processing needed)
- Thread-safe operation with proper error handling

Usage:
------
```python
tracker = GimbalTracker(video_handler, detector, app_controller)
tracker.start_tracking(frame, bbox)  # bbox ignored for gimbal tracker

success, tracker_output = tracker.update(frame)
if success:
    # Use tracker_output.angular for gimbal angles
    # Use tracker_output.position_2d for normalized coordinates
```

Integration:
-----------
This tracker integrates seamlessly with PixEagle's existing architecture:
- Follows BaseTracker interface exactly
- Outputs standard TrackerOutput objects
- Works with any compatible follower implementation
- Appears in tracker selection UI automatically
"""

import time
import numpy as np
import logging
from typing import Optional, Tuple, Dict, Any
from classes.trackers.base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.gimbal_interface import GimbalInterface, CoordinateSystem
from classes.coordinate_transformer import CoordinateTransformer, FrameType
from classes.parameters import Parameters

logger = logging.getLogger(__name__)

class GimbalTracker(BaseTracker):
    """
    Gimbal-based tracker that receives angle data via UDP and converts to target vectors.

    This tracker doesn't process video frames for target detection. Instead, it receives
    real-time gimbal angles via UDP and converts them to normalized target coordinates
    that can be used by PixEagle's follower systems.

    Attributes:
    -----------
    - gimbal_interface (GimbalInterface): UDP communication handler
    - coordinate_transformer (CoordinateTransformer): Coordinate conversion utilities
    - tracker_name (str): Tracker identifier
    - last_valid_angles (Optional[Tuple]): Last known good angle data
    - data_timeout (float): Maximum age for considering data valid
    """

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        """
        Initialize GimbalTracker with gimbal interface and coordinate transformer.

        Args:
            video_handler (Optional[object]): Video handler (not used for gimbal tracking)
            detector (Optional[object]): Detector (automatically suppressed)
            app_controller (Optional[object]): Application controller reference
        """
        super().__init__(video_handler, detector, app_controller)

        self.tracker_name = "GimbalTracker"

        # Initialize gimbal interface
        gimbal_host = getattr(Parameters, 'GIMBAL_UDP_HOST', '192.168.1.100')
        gimbal_port = getattr(Parameters, 'GIMBAL_UDP_PORT', 8080)
        gimbal_timeout = getattr(Parameters, 'GIMBAL_CONNECTION_TIMEOUT', 5.0)

        self.gimbal_interface = GimbalInterface(gimbal_host, gimbal_port, gimbal_timeout)

        # Initialize coordinate transformer
        self.coordinate_transformer = CoordinateTransformer()

        # Tracking state
        self.last_valid_angles: Optional[Tuple[float, float, float]] = None
        self.last_angle_time: Optional[float] = None
        self.data_timeout = 2.0  # Consider data stale after 2 seconds

        # Configuration
        self.preferred_coordinate_system = getattr(Parameters, 'GIMBAL_COORDINATE_SYSTEM', 'GIMBAL_BODY')

        # Suppress detector and predictor since we don't need image processing
        self._suppress_image_processing()

        # Statistics
        self.total_updates = 0
        self.successful_updates = 0
        self.connection_status = "disconnected"

        logger.info(f"GimbalTracker initialized - Host: {gimbal_host}:{gimbal_port}")
        logger.debug(f"Preferred coordinate system: {self.preferred_coordinate_system}")

    def _suppress_image_processing(self) -> None:
        """Suppress detector and predictor since gimbal tracker doesn't use images."""
        try:
            # Mark that we don't need image processing components
            self.suppress_detector = True
            self.suppress_predictor = True

            # Disable estimator if not needed (gimbal provides direct position data)
            disable_estimator = getattr(Parameters, 'GIMBAL_DISABLE_ESTIMATOR', True)
            if disable_estimator:
                self.estimator_enabled = False
                self.position_estimator = None

            logger.debug("Image processing components suppressed for GimbalTracker")

        except Exception as e:
            logger.warning(f"Error suppressing image processing: {e}")

    def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Start gimbal tracking by initializing UDP connection.

        Note: bbox parameter is ignored for gimbal tracker as we don't track image regions.

        Args:
            frame (np.ndarray): Video frame (not used)
            bbox (Tuple[int, int, int, int]): Bounding box (ignored)
        """
        try:
            logger.info("Starting gimbal tracking...")

            # Start gimbal interface
            if self.gimbal_interface.start():
                self.tracking_started = True
                self.last_update_time = time.time()

                # Reset state
                self.last_valid_angles = None
                self.last_angle_time = None
                self.total_updates = 0
                self.successful_updates = 0

                logger.info("Gimbal tracking started successfully")

                # Wait a moment for initial data
                time.sleep(0.5)

            else:
                logger.error("Failed to start gimbal interface")
                self.tracking_started = False

        except Exception as e:
            logger.error(f"Error starting gimbal tracking: {e}")
            self.tracking_started = False

    def stop_tracking(self) -> None:
        """Stop gimbal tracking and cleanup resources."""
        try:
            logger.info("Stopping gimbal tracking...")

            self.tracking_started = False

            # Stop gimbal interface
            if self.gimbal_interface:
                self.gimbal_interface.stop()

            # Reset state
            self.last_valid_angles = None
            self.last_angle_time = None
            self.connection_status = "disconnected"

            # Call parent stop method
            super().stop_tracking()

            logger.info("Gimbal tracking stopped")

        except Exception as e:
            logger.error(f"Error stopping gimbal tracking: {e}")

    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[TrackerOutput]]:
        """
        Update tracker with current gimbal angle data.

        This method gets the latest gimbal angles, converts them to target vectors,
        and returns a TrackerOutput object with the tracking data.

        Args:
            frame (np.ndarray): Video frame (not used by gimbal tracker)

        Returns:
            Tuple[bool, Optional[TrackerOutput]]: Success flag and tracker output
        """
        self.total_updates += 1

        if not self.tracking_started:
            return False, None

        try:
            # Update timing
            dt = self.update_time()

            # Get current gimbal angles
            current_angles = self.gimbal_interface.get_current_angles()
            connection_status = self.gimbal_interface.get_connection_status()

            self.connection_status = connection_status

            if current_angles is not None:
                # We have fresh angle data
                self.last_valid_angles = current_angles
                self.last_angle_time = time.time()
                self.successful_updates += 1

                # Convert angles to target vector and normalized coordinates
                success, tracker_output = self._process_angle_data(current_angles)

                if success:
                    logger.debug(f"Gimbal update successful - Angles: {current_angles}")
                    return True, tracker_output
                else:
                    logger.warning("Failed to process angle data")
                    return False, self._create_inactive_output()

            else:
                # No fresh data - check if we have recent valid data
                if self._has_recent_data():
                    logger.debug("Using recent gimbal data")
                    success, tracker_output = self._process_angle_data(self.last_valid_angles)
                    return success, tracker_output
                else:
                    logger.warning("No recent gimbal data available")
                    return False, self._create_inactive_output()

        except Exception as e:
            logger.error(f"Error in gimbal tracker update: {e}")
            return False, self._create_inactive_output()

    def _process_angle_data(self, angles: Tuple[float, float, float]) -> Tuple[bool, Optional[TrackerOutput]]:
        """
        Process gimbal angle data and create TrackerOutput.

        Args:
            angles (Tuple[float, float, float]): (yaw, pitch, roll) in degrees

        Returns:
            Tuple[bool, Optional[TrackerOutput]]: Success flag and tracker output
        """
        try:
            yaw, pitch, roll = angles

            # Validate angle ranges
            if not self._validate_angles(yaw, pitch, roll):
                logger.warning(f"Invalid gimbal angles: yaw={yaw}, pitch={pitch}, roll={roll}")
                return False, None

            # Convert gimbal angles to body frame target vector
            target_vector_body = self.coordinate_transformer.gimbal_angles_to_body_vector(
                yaw, pitch, roll, include_mount_offset=True
            )

            # Convert to normalized coordinates for PixEagle compatibility
            normalized_coords = self.coordinate_transformer.vector_to_normalized_coords(
                target_vector_body, FrameType.AIRCRAFT_BODY
            )

            # Calculate confidence based on connection quality and data freshness
            confidence = self._calculate_confidence()

            # Get aircraft attitude if available for additional transformations
            aircraft_attitude = self._get_aircraft_attitude()

            # Create TrackerOutput with both angular and position data
            tracker_output = TrackerOutput(
                data_type=TrackerDataType.ANGULAR,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id=f"GimbalTracker_{id(self)}",

                # Primary data - angular information
                angular=(yaw, pitch, roll),

                # Secondary data - normalized position for compatibility
                position_2d=normalized_coords,

                # Confidence and quality metrics
                confidence=confidence,

                # Additional data
                raw_data={
                    'gimbal_angles': angles,
                    'target_vector_body': target_vector_body.tolist(),
                    'coordinate_system': self.preferred_coordinate_system,
                    'connection_status': self.connection_status,
                    'aircraft_attitude': aircraft_attitude,
                    'data_age_seconds': (time.time() - self.last_angle_time) if self.last_angle_time else 0.0,
                    'update_count': self.total_updates,
                    'success_rate': (self.successful_updates / max(1, self.total_updates)) * 100
                },

                metadata={
                    'tracker_class': self.__class__.__name__,
                    'tracker_algorithm': 'Gimbal UDP',
                    'coordinate_transformer': 'CoordinateTransformer',
                    'gimbal_interface': 'UDP Protocol',
                    'suppressed_components': ['detector', 'predictor'],
                    'data_source': 'external_gimbal',
                    'real_time': True
                }
            )

            logger.debug(f"Created TrackerOutput - Angular: {angles}, Position: {normalized_coords}")
            return True, tracker_output

        except Exception as e:
            logger.error(f"Error processing angle data: {e}")
            return False, None

    def _validate_angles(self, yaw: float, pitch: float, roll: float) -> bool:
        """
        Validate gimbal angles are within reasonable ranges.

        Args:
            yaw (float): Yaw angle in degrees
            pitch (float): Pitch angle in degrees
            roll (float): Roll angle in degrees

        Returns:
            bool: True if angles are valid
        """
        try:
            # Define reasonable angle limits
            yaw_limit = getattr(Parameters, 'GIMBAL_YAW_LIMIT', 180.0)
            pitch_limit = getattr(Parameters, 'GIMBAL_PITCH_LIMIT', 90.0)
            roll_limit = getattr(Parameters, 'GIMBAL_ROLL_LIMIT', 180.0)

            return (
                -yaw_limit <= yaw <= yaw_limit and
                -pitch_limit <= pitch <= pitch_limit and
                -roll_limit <= roll <= roll_limit
            )

        except Exception as e:
            logger.error(f"Error validating angles: {e}")
            return False

    def _calculate_confidence(self) -> float:
        """
        Calculate tracking confidence based on connection quality and data freshness.

        Returns:
            float: Confidence score between 0.0 and 1.0
        """
        try:
            base_confidence = 0.9  # High base confidence for direct gimbal data

            # Reduce confidence based on connection status
            if self.connection_status == "connected":
                connection_factor = 1.0
            elif self.connection_status == "connecting":
                connection_factor = 0.7
            elif self.connection_status == "error":
                connection_factor = 0.3
            else:  # disconnected
                connection_factor = 0.1

            # Reduce confidence based on data age
            if self.last_angle_time:
                data_age = time.time() - self.last_angle_time
                if data_age < 0.5:
                    age_factor = 1.0
                elif data_age < 1.0:
                    age_factor = 0.8
                elif data_age < 2.0:
                    age_factor = 0.5
                else:
                    age_factor = 0.2
            else:
                age_factor = 0.1

            # Calculate success rate factor
            if self.total_updates > 0:
                success_rate = self.successful_updates / self.total_updates
                success_factor = success_rate
            else:
                success_factor = 1.0

            # Combine all factors
            final_confidence = base_confidence * connection_factor * age_factor * success_factor

            return max(0.0, min(1.0, final_confidence))

        except Exception as e:
            logger.error(f"Error calculating confidence: {e}")
            return 0.5  # Default moderate confidence

    def _has_recent_data(self) -> bool:
        """
        Check if we have recent valid angle data.

        Returns:
            bool: True if recent data is available
        """
        if not self.last_angle_time or not self.last_valid_angles:
            return False

        data_age = time.time() - self.last_angle_time
        return data_age < self.data_timeout

    def _get_aircraft_attitude(self) -> Optional[Dict[str, float]]:
        """
        Get aircraft attitude from MAVLink if available.

        Returns:
            Optional[Dict[str, float]]: Aircraft attitude data or None
        """
        try:
            if (self.app_controller and
                hasattr(self.app_controller, 'mavlink_data_manager') and
                self.app_controller.mavlink_data_manager):

                # Get attitude data from MAVLink
                roll = self.app_controller.mavlink_data_manager.get_data('roll')
                pitch = self.app_controller.mavlink_data_manager.get_data('pitch')
                yaw = self.app_controller.mavlink_data_manager.get_data('yaw')

                if all(x is not None and x != 'N/A' for x in [roll, pitch, yaw]):
                    return {
                        'roll': float(roll) if isinstance(roll, (int, float)) else 0.0,
                        'pitch': float(pitch) if isinstance(pitch, (int, float)) else 0.0,
                        'yaw': float(yaw) if isinstance(yaw, (int, float)) else 0.0
                    }

        except Exception as e:
            logger.debug(f"Could not get aircraft attitude: {e}")

        return None

    def _create_inactive_output(self) -> TrackerOutput:
        """
        Create TrackerOutput for inactive tracking state.

        Returns:
            TrackerOutput: Inactive tracking output
        """
        return TrackerOutput(
            data_type=TrackerDataType.ANGULAR,
            timestamp=time.time(),
            tracking_active=False,
            tracker_id=f"GimbalTracker_{id(self)}",
            confidence=0.0,
            raw_data={
                'connection_status': self.connection_status,
                'last_data_age': (
                    (time.time() - self.last_angle_time)
                    if self.last_angle_time else float('inf')
                ),
                'total_updates': self.total_updates,
                'successful_updates': self.successful_updates
            },
            metadata={
                'tracker_class': self.__class__.__name__,
                'tracking_inactive_reason': 'no_gimbal_data'
            }
        )

    def get_output(self) -> TrackerOutput:
        """
        Get current tracker output (implementation of BaseTracker interface).

        Returns:
            TrackerOutput: Current tracking data
        """
        if not self.tracking_started:
            return self._create_inactive_output()

        # Try to get current data
        success, output = self.update(None)  # Frame not needed for gimbal tracker

        if success and output:
            return output
        else:
            return self._create_inactive_output()

    def get_capabilities(self) -> Dict[str, Any]:
        """
        Return gimbal tracker capabilities.

        Returns:
            Dict[str, Any]: Tracker capabilities
        """
        return {
            'data_types': [TrackerDataType.ANGULAR.value],
            'supports_confidence': True,
            'supports_velocity': False,
            'supports_bbox': False,
            'supports_normalization': True,
            'estimator_available': False,
            'multi_target': False,
            'real_time': True,
            'tracker_algorithm': 'Gimbal UDP',
            'coordinate_systems': ['GIMBAL_BODY', 'SPATIAL_FIXED'],
            'requires_video': False,
            'requires_detector': False,
            'external_data_source': True,
            'suppressed_components': ['detector', 'predictor']
        }

    def get_gimbal_statistics(self) -> Dict[str, Any]:
        """
        Get detailed gimbal tracking statistics.

        Returns:
            Dict[str, Any]: Gimbal-specific statistics
        """
        gimbal_stats = self.gimbal_interface.get_statistics()

        return {
            'tracker_stats': {
                'total_updates': self.total_updates,
                'successful_updates': self.successful_updates,
                'success_rate_percent': (
                    (self.successful_updates / max(1, self.total_updates)) * 100
                ),
                'tracking_active': self.tracking_started,
                'has_recent_data': self._has_recent_data(),
                'last_angles': self.last_valid_angles,
                'preferred_coordinate_system': self.preferred_coordinate_system
            },
            'gimbal_interface_stats': gimbal_stats,
            'coordinate_transformer_stats': self.coordinate_transformer.get_cache_info()
        }

    def reinitialize_tracker(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Reinitialize gimbal tracker (restart UDP connection).

        Args:
            frame (np.ndarray): Video frame (not used)
            bbox (Tuple[int, int, int, int]): Bounding box (ignored)
        """
        logger.info("Reinitializing gimbal tracker...")

        # Stop current tracking
        self.stop_tracking()

        # Wait a moment
        time.sleep(0.5)

        # Restart tracking
        self.start_tracking(frame, bbox)