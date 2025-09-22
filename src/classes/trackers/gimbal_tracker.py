# src/classes/trackers/gimbal_tracker.py

"""
GimbalTracker Module - Status-Driven Passive Tracker
====================================================

This module implements the GimbalTracker class for integration with external gimbal
systems. It passively receives gimbal data and automatically activates tracking
when the external gimbal system reports active tracking status.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The GimbalTracker is designed for workflows where:
1. External camera UI application controls gimbal tracking (start/stop/cancel)
2. Gimbal broadcasts UDP data with angles and tracking status
3. PixEagle GimbalTracker passively monitors and activates when tracking is active
4. No manual tracking initiation required in PixEagle UI

Key Features:
-------------
- ✅ Status-driven operation based on external gimbal tracking state
- ✅ Passive UDP monitoring (no command sending to gimbal)
- ✅ Automatic activation when gimbal reports TRACKING_ACTIVE (state=2)
- ✅ Real-time angle conversion to normalized coordinates
- ✅ Background monitoring always active
- ✅ Schema-compliant TrackerOutput generation
- ✅ Integration with existing PixEagle architecture

Workflow:
---------
1. PixEagle starts GimbalTracker (begins background monitoring)
2. External camera app starts gimbal tracking
3. Gimbal begins sending UDP data with tracking_status=TRACKING_ACTIVE
4. GimbalTracker detects active tracking and provides angle data to followers
5. External camera app stops/loses tracking
6. Gimbal sends tracking_status=DISABLED/TARGET_LOST
7. GimbalTracker automatically deactivates but continues monitoring

Usage:
------
```python
tracker = GimbalTracker(video_handler, detector, app_controller)
tracker.start_tracking(frame, bbox)  # Starts background monitoring

success, tracker_output = tracker.update(frame)
if success and tracker_output.tracking_active:
    # Gimbal is actively tracking - use the data
    angles = tracker_output.angular  # (yaw, pitch, roll)
```

Integration:
-----------
This tracker integrates seamlessly with PixEagle's existing architecture:
- Follows BaseTracker interface exactly
- Outputs standard TrackerOutput objects with ANGULAR data type
- Works with any compatible follower implementation
- Appears in tracker selection UI automatically
- No manual tracking control required from user
"""

import time
import numpy as np
import logging
from typing import Optional, Tuple, Dict, Any
from classes.trackers.base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.gimbal_interface import GimbalInterface, TrackingState, GimbalData
from classes.coordinate_transformer import CoordinateTransformer, FrameType
from classes.parameters import Parameters

logger = logging.getLogger(__name__)

class GimbalTracker(BaseTracker):
    """
    Status-driven gimbal tracker that passively monitors external gimbal systems.

    This tracker does not control gimbal operation. Instead, it monitors gimbal
    status via UDP and automatically activates tracking when the external gimbal
    system reports that it is actively tracking a target.

    The tracker provides a seamless integration where users control tracking from
    their camera UI application, and PixEagle automatically follows when tracking
    becomes active.

    Attributes:
    -----------
    - gimbal_interface (GimbalInterface): Passive UDP listener for gimbal data
    - coordinate_transformer (CoordinateTransformer): Coordinate conversion utilities
    - tracker_name (str): Tracker identifier
    - monitoring_active (bool): Whether background monitoring is active
    - last_gimbal_data (Optional[GimbalData]): Last received gimbal data
    - tracking_activation_time (Optional[float]): When tracking became active
    """

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        """
        Initialize GimbalTracker with passive monitoring capabilities.

        Args:
            video_handler (Optional[object]): Video handler (not used for gimbal tracking)
            detector (Optional[object]): Detector (automatically suppressed)
            app_controller (Optional[object]): Application controller reference
        """
        super().__init__(video_handler, detector, app_controller)

        self.tracker_name = "GimbalTracker"

        # Initialize gimbal interface with SIP protocol support
        listen_port = getattr(Parameters, 'GIMBAL_LISTEN_PORT', 9004)
        gimbal_ip = getattr(Parameters, 'GIMBAL_UDP_HOST', '192.168.144.108')

        # Get control port from GimbalTracker config or default
        gimbal_config = getattr(Parameters, 'GimbalTracker', {})
        control_port = gimbal_config.get('UDP_PORT', 9003)

        self.gimbal_interface = GimbalInterface(
            listen_port=listen_port,
            gimbal_ip=gimbal_ip,
            control_port=control_port
        )

        # Initialize coordinate transformer
        self.coordinate_transformer = CoordinateTransformer()

        # Monitoring state
        self.monitoring_active = False
        self.last_gimbal_data: Optional[GimbalData] = None
        self.tracking_activation_time: Optional[float] = None
        self.last_tracking_state = TrackingState.DISABLED

        # Configuration
        self.preferred_coordinate_system = getattr(Parameters, 'GIMBAL_COORDINATE_SYSTEM', 'GIMBAL_BODY')

        # Suppress detector and predictor since we don't need image processing
        self._suppress_image_processing()

        # Statistics
        self.total_updates = 0
        self.tracking_activations = 0
        self.tracking_deactivations = 0

        logger.info(f"GimbalTracker initialized for passive monitoring on port {listen_port}")
        logger.debug(f"Expected gimbal IP: {gimbal_ip}")

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
        Start background monitoring for gimbal data.

        Note: This does NOT start gimbal tracking. It only starts background monitoring
        of gimbal status. Actual tracking must be initiated from external camera UI.

        Args:
            frame (np.ndarray): Video frame (not used)
            bbox (Tuple[int, int, int, int]): Bounding box (ignored - not used for gimbal)
        """
        try:
            logger.info("Starting gimbal background monitoring...")

            # Start passive UDP listening
            if self.gimbal_interface.start_listening():
                self.monitoring_active = True
                self.tracking_started = False  # Will be set when gimbal reports active tracking
                self.last_update_time = time.time()

                # Reset state
                self.last_gimbal_data = None
                self.tracking_activation_time = None
                self.total_updates = 0
                self.tracking_activations = 0
                self.tracking_deactivations = 0

                logger.info("Gimbal background monitoring started successfully")
                logger.info("⚠️  NOTE: Tracking control must be initiated from external camera UI application")

            else:
                logger.error("Failed to start gimbal interface")
                self.monitoring_active = False

        except Exception as e:
            logger.error(f"Error starting gimbal monitoring: {e}")
            self.monitoring_active = False

    def stop_tracking(self) -> None:
        """Stop gimbal monitoring and cleanup resources."""
        try:
            logger.info("Stopping gimbal monitoring...")

            self.monitoring_active = False
            self.tracking_started = False

            # Stop gimbal interface
            if self.gimbal_interface:
                self.gimbal_interface.stop_listening()

            # Reset state
            self.last_gimbal_data = None
            self.tracking_activation_time = None
            self.last_tracking_state = TrackingState.DISABLED

            # Call parent stop method
            super().stop_tracking()

            logger.info("Gimbal monitoring stopped")

        except Exception as e:
            logger.error(f"Error stopping gimbal monitoring: {e}")

    def update(self, frame: np.ndarray) -> Tuple[bool, Optional[TrackerOutput]]:
        """
        Update tracker by checking gimbal status and providing data when tracking is active.

        This method passively monitors gimbal status and automatically activates/deactivates
        tracking based on the gimbal's reported tracking state.

        Args:
            frame (np.ndarray): Video frame (not used by gimbal tracker)

        Returns:
            Tuple[bool, Optional[TrackerOutput]]: Success flag and tracker output
        """
        self.total_updates += 1

        if not self.monitoring_active:
            return False, None

        try:
            # Update timing
            dt = self.update_time()

            # Get current gimbal data (includes status and angles)
            gimbal_data = self.gimbal_interface.get_current_data()

            if gimbal_data is None:
                # No recent data from gimbal
                return False, self._create_inactive_output("no_gimbal_data")

            # Store the data for analysis
            self.last_gimbal_data = gimbal_data

            # Check tracking status and handle state changes
            tracking_active = self._handle_tracking_state_changes(gimbal_data)

            if tracking_active and gimbal_data.angles:
                # Gimbal is actively tracking and we have angle data
                success, tracker_output = self._process_active_tracking(gimbal_data)

                if success:
                    logger.debug(f"Gimbal tracking active - Angles: {gimbal_data.angles.to_tuple()}")
                    return True, tracker_output
                else:
                    logger.warning("Failed to process gimbal tracking data")
                    return False, self._create_inactive_output("processing_error")
            else:
                # Gimbal not actively tracking or no angle data
                reason = "not_tracking" if not tracking_active else "no_angle_data"
                return False, self._create_inactive_output(reason)

        except Exception as e:
            logger.error(f"Error in gimbal tracker update: {e}")
            return False, self._create_inactive_output("update_error")

    def _handle_tracking_state_changes(self, gimbal_data: GimbalData) -> bool:
        """
        Handle tracking state changes and update internal tracking status.

        Args:
            gimbal_data (GimbalData): Current gimbal data

        Returns:
            bool: True if gimbal is actively tracking
        """
        try:
            if not gimbal_data.tracking_status:
                return False

            current_state = gimbal_data.tracking_status.state
            previous_state = self.last_tracking_state

            # Check for state changes
            if current_state != previous_state:
                logger.info(f"Gimbal tracking state change: {previous_state.name} → {current_state.name}")

                if current_state == TrackingState.TRACKING_ACTIVE:
                    # Tracking became active
                    if not self.tracking_started:
                        self.tracking_started = True
                        self.tracking_activation_time = time.time()
                        self.tracking_activations += 1
                        logger.info("🎯 Gimbal tracking ACTIVATED - PixEagle following enabled")

                elif previous_state == TrackingState.TRACKING_ACTIVE:
                    # Tracking became inactive
                    if self.tracking_started:
                        self.tracking_started = False
                        self.tracking_deactivations += 1
                        active_duration = time.time() - (self.tracking_activation_time or 0)
                        logger.info(f"⏹️  Gimbal tracking DEACTIVATED - Active for {active_duration:.1f}s")

                self.last_tracking_state = current_state

            # Return whether tracking is currently active
            return current_state == TrackingState.TRACKING_ACTIVE

        except Exception as e:
            logger.error(f"Error handling tracking state changes: {e}")
            return False

    def _process_active_tracking(self, gimbal_data: GimbalData) -> Tuple[bool, Optional[TrackerOutput]]:
        """
        Process gimbal data when tracking is active and create TrackerOutput.

        Args:
            gimbal_data (GimbalData): Current gimbal data with angles

        Returns:
            Tuple[bool, Optional[TrackerOutput]]: Success flag and tracker output
        """
        try:
            if not gimbal_data.angles:
                return False, None

            angles = gimbal_data.angles
            yaw, pitch, roll = angles.to_tuple()

            # Validate angle ranges
            if not angles.is_valid():
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

            # Calculate confidence (high for direct gimbal data)
            confidence = self._calculate_confidence(gimbal_data)

            # Get aircraft attitude if available
            aircraft_attitude = self._get_aircraft_attitude()

            # Create TrackerOutput with ANGULAR data type
            tracker_output = TrackerOutput(
                data_type=TrackerDataType.ANGULAR,
                timestamp=time.time(),
                tracking_active=True,
                tracker_id=f"GimbalTracker_{id(self)}",

                # Primary data - angular information (3-tuple for gimbal)
                angular=(yaw, pitch, roll),

                # Secondary data - normalized position for follower compatibility
                position_2d=normalized_coords,

                # Confidence and quality metrics
                confidence=confidence,

                # Additional data
                raw_data={
                    'gimbal_angles': (yaw, pitch, roll),
                    'target_vector_body': target_vector_body.tolist(),
                    'coordinate_system': angles.coordinate_system.value,
                    'tracking_status': gimbal_data.tracking_status.state.name,
                    'aircraft_attitude': aircraft_attitude,
                    'tracking_duration': (
                        time.time() - self.tracking_activation_time
                        if self.tracking_activation_time else 0.0
                    ),
                    'gimbal_data_age': (
                        (time.time() - gimbal_data.timestamp.timestamp())
                        if gimbal_data.timestamp else 0.0
                    )
                },

                metadata={
                    'tracker_class': self.__class__.__name__,
                    'tracker_algorithm': 'Gimbal UDP Passive',
                    'coordinate_transformer': 'CoordinateTransformer',
                    'gimbal_interface': 'Passive UDP Listener',
                    'suppressed_components': ['detector', 'predictor'],
                    'data_source': 'external_gimbal',
                    'real_time': True,
                    'status_driven': True,
                    'external_control': True
                }
            )

            logger.debug(f"Created active TrackerOutput - Angular: {(yaw, pitch, roll)}, Position: {normalized_coords}")
            return True, tracker_output

        except Exception as e:
            logger.error(f"Error processing active tracking: {e}")
            return False, None

    def _calculate_confidence(self, gimbal_data: GimbalData) -> float:
        """
        Calculate tracking confidence based on gimbal data quality.

        Args:
            gimbal_data (GimbalData): Current gimbal data

        Returns:
            float: Confidence score between 0.0 and 1.0
        """
        try:
            base_confidence = 0.95  # High base confidence for direct gimbal data

            # Reduce confidence based on data age
            if gimbal_data.timestamp:
                data_age = (time.time() - gimbal_data.timestamp.timestamp())
                if data_age < 0.5:
                    age_factor = 1.0
                elif data_age < 1.0:
                    age_factor = 0.9
                elif data_age < 2.0:
                    age_factor = 0.7
                else:
                    age_factor = 0.5
            else:
                age_factor = 0.8

            # Factor in tracking state
            if gimbal_data.tracking_status:
                if gimbal_data.tracking_status.state == TrackingState.TRACKING_ACTIVE:
                    tracking_factor = 1.0
                elif gimbal_data.tracking_status.state == TrackingState.TARGET_SELECTION:
                    tracking_factor = 0.7
                elif gimbal_data.tracking_status.state == TrackingState.TARGET_LOST:
                    tracking_factor = 0.3
                else:
                    tracking_factor = 0.1
            else:
                tracking_factor = 0.8

            # Combine factors
            final_confidence = base_confidence * age_factor * tracking_factor

            return max(0.0, min(1.0, final_confidence))

        except Exception as e:
            logger.error(f"Error calculating confidence: {e}")
            return 0.5  # Default moderate confidence

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

    def _create_inactive_output(self, reason: str = "unknown") -> TrackerOutput:
        """
        Create TrackerOutput for inactive tracking state.

        Args:
            reason (str): Reason for inactive state

        Returns:
            TrackerOutput: Inactive tracking output
        """
        # Get current gimbal data for status information
        gimbal_data = self.last_gimbal_data
        tracking_state = "unknown"
        connection_status = self.gimbal_interface.get_connection_status()

        if gimbal_data and gimbal_data.tracking_status:
            tracking_state = gimbal_data.tracking_status.state.name

        return TrackerOutput(
            data_type=TrackerDataType.ANGULAR,
            timestamp=time.time(),
            tracking_active=False,
            tracker_id=f"GimbalTracker_{id(self)}",
            confidence=0.0,
            raw_data={
                'monitoring_active': self.monitoring_active,
                'connection_status': connection_status,
                'tracking_state': tracking_state,
                'inactive_reason': reason,
                'total_updates': self.total_updates,
                'tracking_activations': self.tracking_activations,
                'tracking_deactivations': self.tracking_deactivations,
                'last_activation_time': self.tracking_activation_time
            },
            metadata={
                'tracker_class': self.__class__.__name__,
                'tracking_inactive_reason': reason,
                'passive_monitoring': True,
                'external_control_required': True
            }
        )

    def get_output(self) -> TrackerOutput:
        """
        Get current tracker output (implementation of BaseTracker interface).

        Returns:
            TrackerOutput: Current tracking data
        """
        if not self.monitoring_active:
            return self._create_inactive_output("monitoring_not_active")

        # Try to get current data
        success, output = self.update(None)  # Frame not needed for gimbal tracker

        if success and output:
            return output
        else:
            return self._create_inactive_output("no_active_tracking")

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
            'tracker_algorithm': 'Gimbal UDP Passive',
            'coordinate_systems': ['GIMBAL_BODY', 'SPATIAL_FIXED'],
            'requires_video': False,
            'requires_detector': False,
            'external_data_source': True,
            'external_control_required': True,
            'suppressed_components': ['detector', 'predictor'],
            'passive_monitoring': True,
            'status_driven': True
        }

    def get_gimbal_statistics(self) -> Dict[str, Any]:
        """
        Get detailed gimbal tracking statistics.

        Returns:
            Dict[str, Any]: Gimbal-specific statistics
        """
        interface_stats = self.gimbal_interface.get_statistics()

        return {
            'tracker_stats': {
                'monitoring_active': self.monitoring_active,
                'tracking_started': self.tracking_started,
                'total_updates': self.total_updates,
                'tracking_activations': self.tracking_activations,
                'tracking_deactivations': self.tracking_deactivations,
                'current_tracking_state': self.last_tracking_state.name,
                'preferred_coordinate_system': self.preferred_coordinate_system,
                'last_activation_time': self.tracking_activation_time,
                'tracking_duration': (
                    time.time() - self.tracking_activation_time
                    if self.tracking_activation_time and self.tracking_started else 0.0
                )
            },
            'gimbal_interface_stats': interface_stats,
            'coordinate_transformer_stats': self.coordinate_transformer.get_cache_info()
        }

    def reinitialize_tracker(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
        """
        Reinitialize gimbal tracker (restart monitoring).

        Args:
            frame (np.ndarray): Video frame (not used)
            bbox (Tuple[int, int, int, int]): Bounding box (ignored)
        """
        logger.info("Reinitializing gimbal tracker...")

        # Stop current monitoring
        self.stop_tracking()

        # Wait a moment
        time.sleep(0.5)

        # Restart monitoring
        self.start_tracking(frame, bbox)

    def is_external_control_active(self) -> bool:
        """
        Check if external gimbal control is currently active.

        Returns:
            bool: True if gimbal is being controlled externally and tracking
        """
        return (self.monitoring_active and
                self.tracking_started and
                self.last_tracking_state == TrackingState.TRACKING_ACTIVE)

    def get_tracking_source_info(self) -> Dict[str, Any]:
        """
        Get information about the tracking source (external gimbal system).

        Returns:
            Dict[str, Any]: Tracking source information
        """
        return {
            'source_type': 'external_gimbal',
            'control_method': 'passive_monitoring',
            'requires_external_activation': True,
            'external_ui_required': True,
            'listen_port': self.gimbal_interface.listen_port,
            'expected_gimbal_ip': self.gimbal_interface.gimbal_ip,
            'supported_coordinate_systems': ['GIMBAL_BODY', 'SPATIAL_FIXED'],
            'supported_tracking_states': [state.name for state in TrackingState],
            'protocol': 'UDP',
            'data_format': 'SIP_gimbal_protocol'
        }