# src/classes/trackers/gimbal_tracker.py

"""
GimbalTracker Module - Status-Driven External Gimbal Tracker
============================================================

This module implements the GimbalTracker class for integration with external gimbal
systems. The current implementation uses a Topotek SIP-series UDP interface for
angle/status ingestion, then converts that data into standard TrackerOutput
objects.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The GimbalTracker is designed for workflows where:
1. External camera UI application controls gimbal tracking (start/stop/cancel)
2. PixEagle queries/listens for gimbal angles and tracking status
3. PixEagle GimbalTracker activates when tracking is active
4. No manual tracking initiation required in PixEagle UI

Key Features:
-------------
- Status-driven operation based on external gimbal tracking state
- Topotek SIP-over-UDP status/angle ingestion through GimbalInterface
- Automatic activation when gimbal reports TRACKING_ACTIVE (state=2)
- Real-time angle conversion to normalized coordinates
- Background monitoring always active
- Schema-compliant TrackerOutput generation
- Integration with existing PixEagle architecture

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
from classes.gimbal_provider import (
    GimbalProviderConfig,
    UnknownGimbalProviderError,
    create_gimbal_provider,
    list_supported_gimbal_providers,
)
from classes.gimbal_types import TrackingState, GimbalData
from classes.coordinate_transformer import CoordinateTransformer, FrameType
from classes.parameters import Parameters

logger = logging.getLogger(__name__)

class GimbalTracker(BaseTracker):
    """
    Status-driven tracker for external gimbal systems.

    This tracker adapts gimbal status/angle data into TrackerOutput. It does not
    expose vendor packets to followers.

    The tracker provides a seamless integration where users control tracking from
    their camera UI application, and PixEagle automatically follows when tracking
    becomes active.

    Attributes:
    -----------
    - gimbal_provider: Normalized provider for external gimbal input
    - coordinate_transformer (CoordinateTransformer): Coordinate conversion utilities
    - tracker_name (str): Tracker identifier
    - monitoring_active (bool): Whether background monitoring is active
    - last_gimbal_data (Optional[GimbalData]): Last received gimbal data
    - tracking_activation_time (Optional[float]): When tracking became active
    - is_external_tracker (bool): Always True - enables continuous follow_target() calls
    """

    # CRITICAL: Mark as external tracker for automatic follow_target() calls
    is_external_tracker = True

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        """
        Initialize GimbalTracker with external gimbal data handling.

        Args:
            video_handler (Optional[object]): Video handler (not used for gimbal tracking)
            detector (Optional[object]): Detector (automatically suppressed)
            app_controller (Optional[object]): Application controller reference
        """
        super().__init__(video_handler, detector, app_controller)

        self.tracker_name = "GimbalTracker"
        self.is_external_tracker = True  # Flag for AppController to handle differently

        # Initialize gimbal provider with configurable parameters.
        gimbal_cfg = getattr(Parameters, 'GimbalTracker', {})

        self.CONFIG = {
            'provider': gimbal_cfg.get('PROVIDER', 'topotek_sip_udp'),
            'listen_port': gimbal_cfg.get('LISTEN_PORT', 9004),
            'gimbal_ip': gimbal_cfg.get('UDP_HOST', '192.168.0.108'),
            'control_port': gimbal_cfg.get('UDP_PORT', 9003),
            'connection_timeout': gimbal_cfg.get('CONNECTION_TIMEOUT', 2.0),
            'coordinate_system': gimbal_cfg.get('COORDINATE_SYSTEM', 'GIMBAL_BODY'),
            'disable_estimator': gimbal_cfg.get('DISABLE_ESTIMATOR', True)
        }

        try:
            provider_config = GimbalProviderConfig.from_mapping(gimbal_cfg)
            self.gimbal_provider = create_gimbal_provider(provider_config)
        except UnknownGimbalProviderError:
            logger.exception("Unsupported gimbal provider configured: %s", self.CONFIG['provider'])
            raise

        # Compatibility alias for existing status/test code. New code should use
        # gimbal_provider so vendor protocol details stay below the provider layer.
        self.gimbal_interface = self.gimbal_provider
        self.provider_metadata = self._get_provider_metadata()

        # Initialize coordinate transformer
        self.coordinate_transformer = CoordinateTransformer()

        # Monitoring state
        self.monitoring_active = False
        self.last_gimbal_data: Optional[GimbalData] = None
        self.tracking_activation_time: Optional[float] = None
        self.last_tracking_state = TrackingState.DISABLED

        # Enhanced caching for robust operation
        self.last_valid_output: Optional[TrackerOutput] = None
        self.last_valid_data_time: Optional[float] = None
        self.consecutive_failures = 0

        # Configuration constants - from config with defaults
        gimbal_config = getattr(Parameters, 'GimbalTracker', {})
        self.DATA_TIMEOUT_SECONDS = gimbal_config.get('data_timeout_seconds', 5.0)
        self.MAX_CONSECUTIVE_FAILURES = gimbal_config.get('max_consecutive_failures', 10)

        # Event-based logging state
        self.last_logged_state = None
        self.last_logged_angles = None
        self.debug_logging_enabled = logger.isEnabledFor(logging.DEBUG)

        # Configuration
        self.preferred_coordinate_system = self.CONFIG['coordinate_system']

        # Suppress detector and predictor since we don't need image processing
        self._suppress_image_processing()

        # Statistics
        self.total_updates = 0
        self.tracking_activations = 0
        self.tracking_deactivations = 0

        logger.info(
            "GimbalTracker initialized - provider=%s, listen_port=%s",
            self.provider_metadata.get('provider', self.CONFIG['provider']),
            self.CONFIG['listen_port'],
        )
        logger.info(
            "Gimbal provider metadata: %s",
            self.provider_metadata,
        )
        if self.debug_logging_enabled:
            logger.debug(f"Debug logging enabled for GimbalTracker")

    def _get_provider_metadata(self) -> Dict[str, Any]:
        """Return provider metadata, with a minimal fallback for test doubles."""
        metadata_getter = getattr(self.gimbal_provider, 'get_provider_metadata', None)
        if callable(metadata_getter):
            return metadata_getter()

        return {
            'provider': self.CONFIG.get('provider', 'unknown'),
            'display_name': self.CONFIG.get('provider', 'Unknown Gimbal Provider'),
            'protocol': self.CONFIG.get('provider', 'unknown'),
            'listen_port': self.CONFIG.get('listen_port'),
            'gimbal_ip': self.CONFIG.get('gimbal_ip'),
            'control_port': self.CONFIG.get('control_port'),
        }

    @staticmethod
    def _tracking_state_name(state: object) -> str:
        """Return a tracking state name for real enums and compatible providers."""
        return getattr(state, 'name', str(state))

    @staticmethod
    def _tracking_state_value(state: object) -> object:
        """Return a tracking state value for real enums and compatible providers."""
        return getattr(state, 'value', state)

    @classmethod
    def _is_tracking_active_state(cls, state: object) -> bool:
        """Accept real TrackingState values and compatible provider enum values."""
        return (
            state == TrackingState.TRACKING_ACTIVE or
            cls._tracking_state_name(state) == TrackingState.TRACKING_ACTIVE.name or
            cls._tracking_state_value(state) == TrackingState.TRACKING_ACTIVE.value
        )

    def _suppress_image_processing(self) -> None:
        """Suppress detector and predictor since gimbal tracker doesn't use images."""
        try:
            # Mark that we don't need image processing components
            self.suppress_detector = True
            self.suppress_predictor = True

            # Disable estimator if not needed (gimbal provides direct position data)
            if self.CONFIG['disable_estimator']:
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
            if self.gimbal_provider.start_listening():
                self.monitoring_active = True
                self.tracking_started = False  # Will be set when gimbal reports active tracking
                self.last_update_time = time.time()
                logger.info(
                    "Gimbal provider %s listening on %s:%s",
                    self.provider_metadata.get('provider', self.CONFIG['provider']),
                    self.CONFIG['gimbal_ip'],
                    self.CONFIG['listen_port'],
                )

                # Reset state
                self.last_gimbal_data = None
                self.tracking_activation_time = None
                self.total_updates = 0
                self.tracking_activations = 0
                self.tracking_deactivations = 0

                logger.info("Gimbal background monitoring started successfully")
                logger.info("NOTE: Tracking control must be initiated from external camera UI application")
            else:
                logger.error(f"Failed to start gimbal interface listener on port {self.CONFIG['listen_port']}")
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
            if self.gimbal_provider:
                self.gimbal_provider.stop_listening()

            # Reset state
            self.last_gimbal_data = None
            self.tracking_activation_time = None
            self.last_tracking_state = TrackingState.DISABLED

            # Call parent stop method
            super().stop_tracking()

            logger.info("Gimbal monitoring stopped")

        except Exception as e:
            logger.error(f"Error stopping gimbal monitoring: {e}")

    def update(self, frame: Optional[np.ndarray] = None) -> Tuple[bool, Optional[TrackerOutput]]:
        """
        Update tracker by checking gimbal status and providing data when available.

        Modified to always return angle data when available, regardless of tracking state.
        This ensures continuous angle display while maintaining follower state control.

        Args:
            frame (np.ndarray): Video frame (not used by gimbal tracker)

        Returns:
            Tuple[bool, Optional[TrackerOutput]]: Success flag and tracker output
        """
        self.total_updates += 1

        if not self.monitoring_active:
            return False, self._create_inactive_output("monitoring_not_active")

        try:
            # Update timing
            dt = self.update_time()

            # Get current gimbal data (includes status and angles)
            gimbal_data = self.gimbal_provider.get_current_data()

            if gimbal_data is None:
                # No recent data from gimbal - check if we can use cached data
                # Log data status periodically for debugging
                if self.total_updates % 1000 == 0:  # Every 1000 updates
                    logger.info(f"Gimbal data status: No current data received (total updates: {self.total_updates})")
                return self._handle_no_current_data()

            # Store the data for analysis
            self.last_gimbal_data = gimbal_data

            # Check tracking status and handle state changes (for follower control)
            tracking_active = self._handle_tracking_state_changes(gimbal_data)

            # ALWAYS process angles when available (continuous display mode)
            if gimbal_data.angles:
                # We have angle data - process and cache it
                success, tracker_output = self._process_gimbal_data(gimbal_data, tracking_active)

                if success:
                    # Cache the successful result
                    self.last_valid_output = tracker_output
                    self.last_valid_data_time = time.time()
                    self.consecutive_failures = 0  # Reset failure counter

                    # Event-based logging: only log significant angle changes
                    self._log_angle_changes(gimbal_data.angles)
                    return True, tracker_output
                else:
                    logger.debug("Failed to process gimbal angle data")
                    self.consecutive_failures += 1
                    return self._handle_processing_failure()
            else:
                # No angle data available
                self.consecutive_failures += 1
                return self._handle_no_angle_data()

        except Exception as e:
            logger.error(f"Gimbal tracker update error: {e}")
            self.consecutive_failures += 1
            return self._handle_exception_failure(str(e))

    def _handle_no_current_data(self) -> Tuple[bool, Optional[TrackerOutput]]:
        """Handle case when no current gimbal data is available."""
        self.consecutive_failures += 1

        # Check if we have recent cached data we can use
        if (self.last_valid_output and self.last_valid_data_time and
            (time.time() - self.last_valid_data_time) < self.DATA_TIMEOUT_SECONDS):

            # Return cached data with staleness indicator
            cached_output = self._create_stale_data_output(self.last_valid_output)
            logger.debug(f"Using cached gimbal data (age: {time.time() - self.last_valid_data_time:.1f}s)")
            return True, cached_output

        # No usable cached data
        return False, self._create_inactive_output("no_gimbal_data")

    def _handle_processing_failure(self) -> Tuple[bool, Optional[TrackerOutput]]:
        """Handle gimbal data processing failure."""
        # Try to return cached data if available and recent
        if (self.last_valid_output and self.last_valid_data_time and
            (time.time() - self.last_valid_data_time) < self.DATA_TIMEOUT_SECONDS):

            cached_output = self._create_stale_data_output(self.last_valid_output)
            logger.debug(f"Processing failed, using cached data (age: {time.time() - self.last_valid_data_time:.1f}s)")
            return True, cached_output

        return False, self._create_inactive_output("processing_error")

    def _handle_no_angle_data(self) -> Tuple[bool, Optional[TrackerOutput]]:
        """Handle case when gimbal data exists but no angle information."""
        # Try to return cached data if available and recent
        if (self.last_valid_output and self.last_valid_data_time and
            (time.time() - self.last_valid_data_time) < self.DATA_TIMEOUT_SECONDS):

            cached_output = self._create_stale_data_output(self.last_valid_output)
            logger.debug(f"No angle data, using cached data (age: {time.time() - self.last_valid_data_time:.1f}s)")
            return True, cached_output

        return False, self._create_inactive_output("no_angle_data")

    def _handle_exception_failure(self, error_msg: str) -> Tuple[bool, Optional[TrackerOutput]]:
        """Handle exception during update."""
        # Try to return cached data if available and recent
        if (self.last_valid_output and self.last_valid_data_time and
            (time.time() - self.last_valid_data_time) < self.DATA_TIMEOUT_SECONDS):

            cached_output = self._create_stale_data_output(self.last_valid_output)
            logger.debug(f"Exception occurred, using cached data (age: {time.time() - self.last_valid_data_time:.1f}s)")
            return True, cached_output

        return False, self._create_inactive_output(f"update_error: {error_msg}")

    def _create_stale_data_output(self, original_output: TrackerOutput) -> TrackerOutput:
        """Create a TrackerOutput based on cached data with staleness indicators."""
        current_time = time.time()
        data_age = current_time - self.last_valid_data_time if self.last_valid_data_time else 0

        # Create new output based on cached data
        stale_output = TrackerOutput(
            data_type=original_output.data_type,
            timestamp=current_time,  # Current timestamp
            tracking_active=False,
            tracker_id=original_output.tracker_id,
            angular=original_output.angular,  # Keep last known angles
            position_2d=original_output.position_2d,
            confidence=max(0.1, original_output.confidence * 0.7) if original_output.confidence else 0.1,  # Reduced confidence

            raw_data={
                **(original_output.raw_data or {}),
                'data_is_stale': True,
                'data_age_seconds': data_age,
                'consecutive_failures': self.consecutive_failures,
                'last_valid_time': self.last_valid_data_time,
                'gimbal_tracking_active': False,
                'usable_for_following': False,
                'has_output': True,
                'connection_health': 'degraded' if self.consecutive_failures < self.MAX_CONSECUTIVE_FAILURES else 'poor'
            },

            metadata={
                **(original_output.metadata or {}),
                'stale_data': True,
                'cache_mode': True,
                'data_freshness': 'stale',
                'usable_for_following': False
            }
        )

        return stale_output

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
                if self.tracking_started:
                    self.tracking_started = False
                    self.tracking_deactivations += 1
                    active_duration = time.time() - (self.tracking_activation_time or time.time())
                    logger.warning(
                        "Gimbal tracking status missing from fresh data - "
                        "marking tracking inactive after %.1fs",
                        active_duration,
                    )
                self.last_tracking_state = TrackingState.DISABLED
                return False

            current_state = gimbal_data.tracking_status.state
            previous_state = self.last_tracking_state

            # Check for state changes
            if current_state != previous_state:
                logger.info(
                    "Gimbal tracking state change: %s → %s",
                    self._tracking_state_name(previous_state),
                    self._tracking_state_name(current_state),
                )

                if self._is_tracking_active_state(current_state):
                    # Tracking became active
                    if not self.tracking_started:
                        self.tracking_started = True
                        self.tracking_activation_time = time.time()
                        self.tracking_activations += 1
                        logger.info("Gimbal tracking ACTIVATED - PixEagle following enabled")

                elif self._is_tracking_active_state(previous_state):
                    # Tracking became inactive
                    if self.tracking_started:
                        self.tracking_started = False
                        self.tracking_deactivations += 1
                        active_duration = time.time() - (self.tracking_activation_time or 0)
                        logger.info(f"Gimbal tracking DEACTIVATED - Active for {active_duration:.1f}s")

                self.last_tracking_state = current_state

            # Return whether tracking is currently active
            return self._is_tracking_active_state(current_state)

        except Exception as e:
            logger.error(f"Error handling tracking state changes: {e}")
            return False

    def _process_gimbal_data(self, gimbal_data: GimbalData, tracking_active: bool = False) -> Tuple[bool, Optional[TrackerOutput]]:
        """
        Process gimbal data and create TrackerOutput with angle information.

        Processes gimbal data when available, but only marks the output active
        for following when the provider reports active target tracking.

        Args:
            gimbal_data (GimbalData): Current gimbal data with angles
            tracking_active (bool): Whether gimbal reports active tracking (for follower control)

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

            # Create TrackerOutput matching demo format exactly
            # Fields: yaw, pitch, roll, system, tracking, timestamp
            gimbal_tracking_status = (
                self._tracking_state_name(gimbal_data.tracking_status.state)
                if gimbal_data.tracking_status else 'UNKNOWN'
            )
            gimbal_system = angles.coordinate_system.value.lower()  # gimbal_body, spatial_fixed
            current_timestamp = time.time()

            # Event-based logging: only log when tracking status changes
            has_tracking_data = gimbal_data.tracking_status is not None
            self._log_tracking_status_changes(gimbal_tracking_status, has_tracking_data)

            tracker_output = TrackerOutput(
                data_type=TrackerDataType.GIMBAL_ANGLES,
                timestamp=current_timestamp,
                tracking_active=tracking_active,
                tracker_id="GimbalTracker",

                # Primary gimbal angle data
                angular=(yaw, pitch, roll),

                # Essential for follower compatibility
                position_2d=normalized_coords,
                confidence=confidence,

                # Exact fields matching demo output
                raw_data={
                    'yaw': round(yaw, 2),      # -5.44
                    'pitch': round(pitch, 2),  # +101.60
                    'roll': round(roll, 2),    # +18.39
                    'system': gimbal_system,   # gimbal_body
                    'coordinate_system': gimbal_system,
                    'tracking': gimbal_tracking_status,  # TRACKING_ACTIVE
                    'tracking_status': gimbal_tracking_status,  # Also add as tracking_status for UI compatibility
                    'gimbal_tracking_active': tracking_active,
                    'usable_for_following': tracking_active,
                    'has_output': True,
                    'connection_status': self.gimbal_provider.get_connection_status(),
                    'connection_health': self.gimbal_provider.get_health_status(),
                    'provider': self.provider_metadata.get('provider'),
                    'protocol': self.provider_metadata.get('protocol'),
                    'timestamp': current_timestamp
                },

                # Enhanced metadata with schema properties
                metadata={
                    'tracker_type': 'external_gimbal',
                    'always_reporting': True,  # Schema property: always provides data when available
                    'is_gimbal_tracker': True,  # Schema property: identifies as gimbal tracker
                    'requires_manual_start': False,  # No manual tracking initiation needed
                    'continuous_display': True,  # Always display when data available
                    'real_time_updates': True,  # Real-time continuous data stream
                    'external_control': True,  # Controlled by external gimbal system
                    'gimbal_provider': self.provider_metadata.get('provider'),
                    'provider_protocol': self.provider_metadata.get('protocol'),
                    'usable_for_following': tracking_active
                }
            )

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
                if self._is_tracking_active_state(gimbal_data.tracking_status.state):
                    tracking_factor = 1.0
                elif self._tracking_state_name(gimbal_data.tracking_status.state) == TrackingState.TARGET_SELECTION.name:
                    tracking_factor = 0.7
                elif self._tracking_state_name(gimbal_data.tracking_status.state) == TrackingState.TARGET_LOST.name:
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

    def _log_angle_changes(self, angles) -> None:
        """Log gimbal angles only when they change significantly (event-based)."""
        try:
            current_angles = (round(angles.yaw, 1), round(angles.pitch, 1), round(angles.roll, 1))

            # Only log if angles changed significantly or if it's the first time
            if (self.last_logged_angles is None or
                abs(current_angles[0] - self.last_logged_angles[0]) > 5.0 or  # 5° yaw change
                abs(current_angles[1] - self.last_logged_angles[1]) > 5.0 or  # 5° pitch change
                abs(current_angles[2] - self.last_logged_angles[2]) > 5.0):   # 5° roll change

                # Unified tracker reporting - uses schema-based field formatting
                self._log_tracker_data_changes(current_angles, angles.coordinate_system.value)
                self.last_logged_angles = current_angles

        except Exception as e:
            if self.debug_logging_enabled:
                logger.debug(f"Error logging angle changes: {e}")

    def _log_tracker_data_changes(self, angles: tuple, coordinate_system: str) -> None:
        """Unified tracker data logging - formats based on tracker's primary data type."""
        try:
            # Format based on this tracker's capabilities
            capabilities = self.get_capabilities()
            primary_data_type = capabilities.get('data_types', ['UNKNOWN'])[0]

            if primary_data_type == 'ANGULAR':
                # For angular data, log as angles
                logger.info(f"Gimbal angles: Y={angles[0]} P={angles[1]} R={angles[2]} | {coordinate_system}")
            else:
                # Fallback format
                logger.info(f"{self.__class__.__name__}: {angles} | {coordinate_system}")

        except Exception as e:
            # Fallback to simple logging
            logger.info(f"Gimbal angles: Y={angles[0]} P={angles[1]} R={angles[2]} | {coordinate_system}")

    def _log_tracking_status_changes(self, status: str, has_data: bool) -> None:
        """Log tracking status only when it changes (event-based)."""
        try:
            current_state = (status, has_data)

            # Only log when status changes or when debug is enabled for first few updates
            if (self.last_logged_state != current_state or
                (self.debug_logging_enabled and self.total_updates <= 5)):

                if has_data:
                    logger.info(f"Gimbal tracking status: {status}")
                elif self.debug_logging_enabled:
                    logger.debug("No tracking data in gimbal packet")

                self.last_logged_state = current_state

        except Exception as e:
            if self.debug_logging_enabled:
                logger.debug(f"Error logging status changes: {e}")

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
            logger.debug(f"Aircraft attitude unavailable: {e}")

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
        connection_status = self.gimbal_provider.get_connection_status()

        if gimbal_data and gimbal_data.tracking_status:
            tracking_state = gimbal_data.tracking_status.state.name

        return TrackerOutput(
            data_type=TrackerDataType.GIMBAL_ANGLES,
            timestamp=time.time(),
            tracking_active=False,
            tracker_id=f"GimbalTracker_{id(self)}",
            confidence=0.0,
            raw_data={
                'monitoring_active': self.monitoring_active,
                'connection_status': connection_status,
                'tracking_state': tracking_state,
                'inactive_reason': reason,
                'gimbal_tracking_active': False,
                'usable_for_following': False,
                'has_output': False,
                'total_updates': self.total_updates,
                'tracking_activations': self.tracking_activations,
                'tracking_deactivations': self.tracking_deactivations,
                'last_activation_time': self.tracking_activation_time,
                'provider': self.provider_metadata.get('provider'),
                'protocol': self.provider_metadata.get('protocol')
            },
            metadata={
                'tracker_class': self.__class__.__name__,
                'tracking_inactive_reason': reason,
                'external_gimbal_input': True,
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
            'data_types': [TrackerDataType.GIMBAL_ANGLES.value, TrackerDataType.ANGULAR.value],
            'supports_confidence': True,
            'supports_velocity': False,
            'supports_bbox': False,
            'supports_normalization': True,
            'estimator_available': False,
            'multi_target': False,
            'real_time': True,
            'tracker_algorithm': f"{self.provider_metadata.get('display_name', 'External')} Gimbal",
            'coordinate_systems': self.provider_metadata.get('coordinate_systems', ['GIMBAL_BODY', 'SPATIAL_FIXED']),
            'requires_video': False,
            'requires_detector': False,
            'external_data_source': True,
            'external_control_required': True,
            'suppressed_components': ['detector', 'predictor'],
            'external_gimbal_input': True,
            'status_driven': True,
            'gimbal_provider': self.provider_metadata.get('provider'),
            'provider_protocol': self.provider_metadata.get('protocol'),
            'supported_gimbal_providers': list_supported_gimbal_providers()
        }

    def get_gimbal_statistics(self) -> Dict[str, Any]:
        """
        Get detailed gimbal tracking statistics.

        Returns:
            Dict[str, Any]: Gimbal-specific statistics
        """
        interface_stats = self.gimbal_provider.get_statistics()

        return {
            'tracker_stats': {
                'monitoring_active': self.monitoring_active,
                'tracking_started': self.tracking_started,
                'total_updates': self.total_updates,
                'tracking_activations': self.tracking_activations,
                'tracking_deactivations': self.tracking_deactivations,
                'current_tracking_state': self._tracking_state_name(self.last_tracking_state),
                'preferred_coordinate_system': self.preferred_coordinate_system,
                'last_activation_time': self.tracking_activation_time,
                'tracking_duration': (
                    time.time() - self.tracking_activation_time
                    if self.tracking_activation_time and self.tracking_started else 0.0
                )
            },
            'gimbal_interface_stats': interface_stats,
            'gimbal_provider_metadata': self.provider_metadata,
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
                self._is_tracking_active_state(self.last_tracking_state))

    def get_tracking_source_info(self) -> Dict[str, Any]:
        """
        Get information about the tracking source (external gimbal system).

        Returns:
            Dict[str, Any]: Tracking source information
        """
        return {
            'source_type': 'external_gimbal',
            'control_method': self.provider_metadata.get('protocol', 'unknown'),
            'requires_external_activation': True,
            'external_ui_required': True,
            'listen_port': self.provider_metadata.get('listen_port'),
            'expected_gimbal_ip': self.provider_metadata.get('gimbal_ip'),
            'supported_coordinate_systems': self.provider_metadata.get('coordinate_systems', ['GIMBAL_BODY', 'SPATIAL_FIXED']),
            'supported_tracking_states': self.provider_metadata.get('tracking_states', [state.name for state in TrackingState]),
            'provider': self.provider_metadata.get('provider'),
            'protocol': self.provider_metadata.get('protocol'),
            'data_format': '_'.join(self.provider_metadata.get('packet_families', [])) or 'provider_normalized'
        }
