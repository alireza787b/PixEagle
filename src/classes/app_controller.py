# src/classes/app_controller.py

import asyncio
import logging
import time
import numpy as np
import cv2
import threading

from classes.parameters import Parameters
from classes.logging_manager import logging_manager
from classes.follower import Follower
from classes.setpoint_sender import SetpointSender
from classes.video_handler import VideoHandler
from classes.trackers.csrt_tracker import CSRTTracker  # Import other trackers as necessary
from classes.segmentor import Segmentor
from classes.trackers.tracker_factory import create_tracker
from classes.px4_interface_manager import PX4InterfaceManager  # Updated import path
from classes.telemetry_handler import TelemetryHandler
from classes.fastapi_handler import FastAPIHandler  # Correct import
from typing import Dict, Optional, Tuple, Any
from classes.osd_handler import OSDHandler
from classes.osd_pipeline import OSDPipeline
from classes.osd_mode_manager import OSDModeManager
from classes.gstreamer_handler import GStreamerHandler
from classes.recording_manager import RecordingManager
from classes.storage_manager import StorageManager
from classes.mavlink_data_manager import MavlinkDataManager
from classes.frame_publisher import FramePublisher
from classes.frame_preprocessor import FramePreprocessor
from classes.estimators.estimator_factory import create_estimator
from classes.detectors.detector_factory import create_detector
from classes.tracker_output import TrackerOutput, TrackerDataType

# Import the SmartTracker module (conditional - may not be available without AI packages)
try:
    from classes.smart_tracker import SmartTracker, ULTRALYTICS_AVAILABLE
    SMART_TRACKER_AVAILABLE = ULTRALYTICS_AVAILABLE
except ImportError:
    SmartTracker = None
    SMART_TRACKER_AVAILABLE = False
    logging.warning("SmartTracker not available - AI packages not installed")


class AppController:
    def __init__(self):
        """
        Initializes the AppController with necessary components and starts the FastAPI handler.
        Also sets up flags for both classic and smart tracking modes.
        """
        logging.debug("Initializing AppController...")

        # Initialize MAVLink Data Manager
        self.mavlink_data_manager = MavlinkDataManager(
            mavlink_host=Parameters.MAVLINK_HOST,
            mavlink_port=Parameters.MAVLINK_PORT,
            polling_interval=Parameters.MAVLINK_POLLING_INTERVAL,
            data_points=Parameters.MAVLINK_DATA_POINTS,
            enabled=Parameters.MAVLINK_ENABLED
        )
        
        # Initialize frame preprocessor if enabled
        if Parameters.ENABLE_PREPROCESSING:
            self.preprocessor = FramePreprocessor()
        else:
            self.preprocessor = None
        
        # Start polling MAVLink data if enabled
        if Parameters.MAVLINK_ENABLED:
            self.mavlink_data_manager.start_polling()

            # Register callback for automatic follow mode disablement when Offboard exits
            # This ensures follow mode is automatically disabled when:
            # - Pilot switches flight modes
            # - Failsafe triggers (RTL, Land, etc.)
            # - RC override occurs
            # - Any transition from Offboard to another mode
            self.mavlink_data_manager.register_offboard_exit_callback(
                lambda old_mode, new_mode: asyncio.create_task(
                    self._handle_offboard_mode_exit(old_mode, new_mode)
                )
            )

        # Initialize the estimator
        self.estimator = create_estimator(Parameters.ESTIMATOR_TYPE)

        # Initialize video processing components
        self.video_handler = VideoHandler()
        self.video_streamer = None
        self.detector = create_detector(Parameters.DETECTION_ALGORITHM)
        self.tracker = create_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM,
                                      self.video_handler, self.detector, self)

        # Auto-start monitoring for external trackers
        if getattr(self.tracker, 'is_external_tracker', False):
            try:
                # Start background monitoring for external trackers
                self.tracker.start_tracking(None, (0, 0, 0, 0))  # Dummy parameters for monitoring
                tracker_name = self.tracker.__class__.__name__
                logging.info(f"{tracker_name} auto-started for background monitoring")
            except Exception as e:
                tracker_name = self.tracker.__class__.__name__
                logging.error(f"Failed to auto-start {tracker_name} monitoring: {e}")

        self.segmentor = Segmentor(algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM)
                    
        self.tracking_failure_start_time = None  # For tracking failure timer

        # Initialize frame counter and tracking flags
        self.frame_counter = 0
        self.tracking_started = False
        self.segmentation_active = False
        
        # System status tracking for periodic updates
        self.last_system_status_time = 0
        self.system_status_interval = 15  # Report system status every 15 seconds
        
        # Start periodic system summary logging
        self._start_system_summary_thread()

        # Flags and attributes for Smart Mode (YOLO-based)
        self.smart_mode_active = False
        self.smart_tracker: Optional[SmartTracker] = None
        self.selected_bbox: Optional[Tuple[int, int, int, int]] = None
        
        # Current tracker type configuration for UI selection
        self.current_tracker_type = Parameters.DEFAULT_TRACKING_ALGORITHM

        # Setup video window and mouse callback if enabled
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.namedWindow("Video")
            cv2.setMouseCallback("Video", self.on_mouse_click)
        self.current_frame = None

        # Initialize PX4 interface and following mode components
        self.px4_interface = PX4InterfaceManager(app_controller=self)
        self.following_active = False
        self.follower = None
        self.setpoint_sender = None

        # Thread safety lock for follower state management
        # Prevents race conditions when multiple API calls modify follower state
        self._follower_state_lock = asyncio.Lock()

        # Initialize telemetry handler with tracker and follower
        self.telemetry_handler = TelemetryHandler(self, lambda: self.tracking_started)

        # Thread-safe frame publisher for streaming consumers
        self.frame_publisher = FramePublisher()

        # Pipeline performance metrics (updated by FlowController, read by API)
        self._pipeline_metrics = {
            'preprocess_ms': 0.0,
            'tracking_ms': 0.0,
            'osd_ms': 0.0,
            'publish_ms': 0.0,
            'total_processing_ms': 0.0,
            'frame_pacing_ms': 0.0,
            'loop_total_ms': 0.0,
            'fps_actual': 0.0,
            'fps_target': 0.0,
            'budget_utilization': 0.0,
            'pipeline_mode': str(getattr(Parameters, 'PIPELINE_MODE', 'REALTIME')),
            'capture_mode': '',
            'frame_id': 0,
            'overrun_count': 0,
            'total_frames': 0,
        }

        # Initialize the FastAPI handler
        logging.debug("Initializing FastAPIHandler...")
        self.api_handler = FastAPIHandler(self)
        logging.debug("FastAPIHandler initialized.")

        # Initialize OSD handler for overlay graphics
        self.osd_handler = OSDHandler(self)
        self.osd_pipeline = OSDPipeline(self.osd_handler)
        self.osd_mode_manager = OSDModeManager(self)
        
        # Initialize GStreamer streaming if enabled
        if Parameters.ENABLE_GSTREAMER_STREAM:
            self.gstreamer_handler = GStreamerHandler()
            self.gstreamer_handler.initialize_stream()

        # Initialize recording system if enabled
        if getattr(Parameters, 'ENABLE_RECORDING', False):
            self.recording_manager = RecordingManager()
            self.storage_manager = StorageManager(self.recording_manager)
            self.storage_manager.start_monitoring()
            logging.info("Recording system initialized")
        else:
            self.recording_manager = None
            self.storage_manager = None

        logging.info("AppController initialized.")

    def on_mouse_click(self, event: int, x: int, y: int, flags: int, param: any):
        """
        Mouse callback for user interactions.
        In smart mode, selects the closest YOLO detection.
        Otherwise, handles segmentation click events.
        """
        if event == cv2.EVENT_LBUTTONDOWN:
            logging.info("clicked")
            if self.smart_mode_active:
                self.handle_smart_click(x, y)
            elif self.segmentation_active:
                self.handle_user_click(x, y)

    def handle_smart_click(self, x: int, y: int):
        """
        Handles user click during smart mode. Selects the closest YOLO detection and activates override.
        """
        if self.current_frame is None or self.smart_tracker is None:
            logging.warning("SmartTracker unavailable or frame not ready.")
            return


        if self.smart_tracker.last_results is None:
            logging.warning("SmartTracker has no results yet. Please wait for detection.")
            return
        self.smart_tracker.select_object_by_click(x, y)

        if self.smart_tracker.selected_bbox and self.smart_tracker.selected_center:
            self.selected_bbox = tuple(map(int, self.smart_tracker.selected_bbox))
            self.tracker.set_external_override(
                self.smart_tracker.selected_bbox,
                self.smart_tracker.selected_center
            )
            logging.info(f"Smart tracking override activated with bbox: {self.selected_bbox}")
        else:
            logging.info("No YOLO detection selected. Override not applied.")


    def toggle_tracking(self, frame: np.ndarray):
        """
        Toggles classic tracking (CSRT-based) state.
        If starting tracking, uses a user-drawn ROI.
        """
        if not self.tracking_started:
            bbox = cv2.selectROI(Parameters.FRAME_TITLE, frame, False, False)
            if bbox and bbox[2] > 0 and bbox[3] > 0:
                self.tracker.start_tracking(frame, bbox)
                self.tracking_started = True
                self.frame_counter = 0  # Reset frame counter
                if self.detector:
                    # Initialize detector features and template
                    self.detector.extract_features(frame, bbox)
                    logging.debug("Detector's features and template set.")
                logging.info("Classic tracking activated.")
            else:
                logging.info("Tracking canceled or invalid ROI.")
        else:
            self.cancel_activities()
            logging.info("Classic tracking deactivated.")


    def toggle_smart_mode(self):
        """
        Toggles the YOLO-based smart tracking mode.
        If enabling for the first time, initializes SmartTracker (with GPU/CPU config + fallback).
        """
        if not self.smart_mode_active:
            # Check if SmartTracker is available (requires ultralytics/torch)
            if not SMART_TRACKER_AVAILABLE:
                logging.error(
                    "SmartTracker not available - AI packages (ultralytics/torch) not installed. "
                    "Re-run 'make init' and select 'Full' profile, or install manually: "
                    "source venv/bin/activate && pip install --prefer-binary ultralytics lap"
                )
                return

            self.cancel_activities()
            self.smart_mode_active = True

            if self.smart_tracker is None:
                try:
                    self.smart_tracker = SmartTracker(app_controller=self)
                    logging.info("SMART TRACKER MODE: Activated (YOLO-based multi-target tracking)")
                except Exception as e:
                    logging.error(f"Failed to activate SmartTracker: {e}")
                    self.smart_mode_active = False
            else:
                logging.info("SMART TRACKER MODE: Re-activated")

        else:
            self.smart_mode_active = False
            if self.smart_tracker:
                self.smart_tracker.clear_selection()
                self.smart_tracker = None
            logging.info("SmartTracker mode deactivated.")



    def toggle_segmentation(self) -> bool:
        """
        Toggles the segmentation state.
        """
        self.segmentation_active = not self.segmentation_active
        logging.info(f"Segmentation {'activated' if self.segmentation_active else 'deactivated'}.")
        return self.segmentation_active

    async def start_tracking(self, bbox: Dict[str, int]):
        """
        Starts tracking with the provided bounding box.

        Note: For external trackers, manual tracking initiation is not supported.
        External trackers use external control and monitor automatically.
        """
        # Check if we're using an external tracker
        if getattr(self.tracker, 'is_external_tracker', False):
            tracker_name = self.tracker.__class__.__name__
            logging.warning(f"Manual tracking control not supported for {tracker_name}")
            logging.info(f"{tracker_name} requires external control from camera UI application")
            logging.info("Tracker is monitoring automatically - no manual start needed")
            return

        if not self.tracking_started:
            bbox_tuple = (bbox['x'], bbox['y'], bbox['width'], bbox['height'])
            self.tracker.start_tracking(self.current_frame, bbox_tuple)
            self.tracking_started = True
            if hasattr(self.tracker, 'detector') and self.tracker.detector:
                self.tracker.detector.extract_features(self.current_frame, bbox_tuple)
            logging.info("Tracking activated.")
        else:
            logging.info("Tracking is already active.")

    async def stop_tracking(self):
        """
        Stops tracking if active.

        Note: For external trackers, manual tracking stop is not supported.
        External trackers stop automatically when external system stops tracking.
        """
        # Check if we're using an external tracker
        if getattr(self.tracker, 'is_external_tracker', False):
            tracker_name = self.tracker.__class__.__name__
            logging.warning(f"Manual tracking control not supported for {tracker_name}")
            logging.info(f"{tracker_name} stops automatically when external tracking ends")
            logging.info("Control tracking from camera UI application")
            return

        if self.tracking_started:
            self.cancel_activities()
            logging.info("Tracking deactivated.")
        else:
            logging.info("Tracking is not active.")

    def cancel_activities(self):
        """
        Cancels tracking, segmentation, and smart mode activities.

        Note: External trackers continue monitoring even when activities are canceled
        since they operate independently via external control.
        """
        self.tracking_started = False
        self.segmentation_active = False
        # self.smart_mode_active = False
        self.selected_bbox = None

        # Reset tracker state (except for external trackers which should keep monitoring)
        if self.tracker and hasattr(self.tracker, 'stop_tracking'):
            if getattr(self.tracker, 'is_external_tracker', False):
                tracker_name = self.tracker.__class__.__name__
                logging.info(f"{tracker_name} continues monitoring - use external control to stop")
            else:
                self.tracker.stop_tracking()

        logging.info("TRACKING STOPPED: All tracker activities canceled")

        if self.setpoint_sender:
            self.setpoint_sender.stop()
            self.setpoint_sender.join()
            self.setpoint_sender = None

        if self.smart_tracker:
            self.smart_tracker.clear_selection()
            # self.smart_tracker = None  # <<< FULL reset


        if self.tracker:
            self.tracker.clear_external_override()  # <<< NEW LINE to disable override when cancelling
            self.tracker.reset()  

        logging.info("All activities cancelled.")


    def is_smart_override_active(self) -> bool:
        return self.smart_mode_active and self.tracker and self.tracker.override_active

    def _log_system_status(self):
        """
        Logs comprehensive system status including tracking, following, and connection states.
        """
        try:
            # Determine active tracking mode
            tracking_status = "Inactive"
            if self.smart_mode_active and self.smart_tracker:
                if hasattr(self.smart_tracker, 'is_tracking_active') and self.smart_tracker.is_tracking_active():
                    tracking_status = "SMART (Active)"
                else:
                    tracking_status = "SMART (Standby)"
            elif self.tracking_started:
                tracker_name = self.tracker.__class__.__name__.replace("Tracker", "")
                tracking_status = f"CLASSIC ({tracker_name})"
            elif self.segmentation_active:
                tracking_status = "Segmentation"
            
            # Following status
            following_status = "Active" if self.following_active else "Inactive"
            
            # MAVLink status
            mavlink_status = "Disabled"
            if Parameters.MAVLINK_ENABLED and self.mavlink_data_manager:
                mavlink_status = self.mavlink_data_manager.connection_state.title()
            
            # PX4 status
            px4_status = "Disconnected"
            if hasattr(self.px4_interface, 'connected') and self.px4_interface.connected:
                px4_status = "Connected"
            
            # Log comprehensive status
            logging.info(f"SYSTEM: Tracking: {tracking_status} | Following: {following_status} | "
                        f"MAVLink: {mavlink_status} | PX4: {px4_status}")
            
        except Exception as e:
            logging.error(f"Error generating system status: {e}")



    async def update_loop(self, frame: np.ndarray) -> np.ndarray:
        """
        Main update loop for processing each video frame.
        In classic mode, runs the usual tracker and estimator logic.
        In smart mode, runs YOLO detection and draws bounding boxes.
        """
        # DEBUG: Log every 100th frame to verify update_loop is running
        if not hasattr(self, '_frame_count_debug'):
            self._frame_count_debug = 0
        self._frame_count_debug += 1
        if self._frame_count_debug % 100 == 0:
            logging.info(f"UPDATE_LOOP RUNNING: Frame #{self._frame_count_debug}")

        try:
            # Per-stage timing instrumentation
            _t0 = time.monotonic()

            # Periodic system status update
            current_time = time.time()
            if current_time - self.last_system_status_time > self.system_status_interval:
                self._log_system_status()
                self.last_system_status_time = current_time

            # Preprocess the frame if enabled
            if Parameters.ENABLE_PREPROCESSING and self.preprocessor:
                frame = self.preprocessor.preprocess(frame)
            _t_preprocess = time.monotonic()
            
            # Apply segmentation if active (applies regardless of mode)
            if self.segmentation_active:
                frame = self.segmentor.segment_frame(frame)
            
            # # Smart Tracker: always draw overlays if instantiated
            # if self.smart_tracker is None and self.smart_mode_active:
            #     try:
            #         self.smart_tracker = SmartTracker(app_controller=self)
            #         logging.info("SmartTracker instantiated successfully.")
            #     except Exception as e:
            #         logging.error(f"Failed to initialize SmartTracker: {e}")
            #         self.smart_mode_active = False

            if self.smart_tracker:
                frame = self.smart_tracker.track_and_draw(frame)

            # Always-Reporting Trackers (schema-based) - Process when available regardless of manual start
            is_always_reporting = self._is_always_reporting_tracker()

            # DEBUG: Log control flow decisions (only when debug enabled)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(f"🔍 Control loop: always_reporting={is_always_reporting}, has_tracker={self.tracker is not None}, following_active={self.following_active}")
            # Check tracker type for appropriate handling
            if self.tracker and logging.getLogger().isEnabledFor(logging.DEBUG):
                logging.debug(f"🔍 Tracker: {self.tracker.__class__.__name__}, external={getattr(self.tracker, 'is_external_tracker', False)}")

            if is_always_reporting and self.tracker:
                # Handle always-reporting trackers (e.g., GimbalTracker)
                try:
                    # Always-reporting trackers update regardless of manual tracking state
                    success, tracker_output = self.tracker.update(frame)

                    if success and tracker_output:
                        # Draw tracking overlay for always-reporting trackers
                        frame = self.tracker.draw_tracking(frame, tracking_successful=True)

                        # Handle following if following is active
                        if self.following_active:
                            await self.follow_target()
                            await self.check_failsafe()
                    else:
                        logging.warning(f"🚨 Always-reporting tracker update failed or no data: success={success}, output={tracker_output}")
                except Exception as e:
                    logging.error(f"Error updating always-reporting tracker: {e}")
            else:
                # Only log this decision when debugging tracker selection
                logging.debug(f"Taking classic tracker path: is_always_reporting={is_always_reporting}, has_tracker={self.tracker is not None}")

            # Classic Tracker (normal tracking or smart override)
            # Smart override mode: SmartTracker controls the classic tracker via external override
            is_smart_override = self.is_smart_override_active()
            classic_active = (self.tracking_started and not self.smart_mode_active)

            # Only process classic trackers if not always-reporting tracker
            if (classic_active or is_smart_override) and not is_always_reporting:
                success = False

                # When smart override is active, skip tracker.update() and always treat as success
                if is_smart_override:
                    # SmartTracker is providing the bbox/center via override, no need to call tracker.update()
                    success = True
                    logging.debug("Smart override active: using SmartTracker-provided tracking data")
                elif self.tracking_failure_start_time is None:
                    # Classic tracker: perform normal update
                    success, _ = self.tracker.update(frame)

                if success:
                    self.tracking_failure_start_time = None
                    frame = self.tracker.draw_tracking(frame, tracking_successful=True)
                    if Parameters.ENABLE_DEBUGGING:
                        self.tracker.print_normalized_center()
                    if self.tracker.position_estimator:
                        frame = self.tracker.draw_estimate(frame, tracking_successful=True)
                    if self.following_active:
                        await self.follow_target()
                        await self.check_failsafe()

                    self.frame_counter += 1
                    tracker_confidence = self.tracker.get_confidence()
                    if not self.smart_mode_active:
                        if (tracker_confidence >= Parameters.TRACKER_CONFIDENCE_THRESHOLD_FOR_TEMPLATE_UPDATE and
                            self.frame_counter % Parameters.TEMPLATE_UPDATE_INTERVAL == 0):
                            bbox = self.tracker.bbox
                            if bbox:
                                self.detector.update_template(frame, bbox)
                                logging.debug(f"TEMPLATE: Updated (Conf: {tracker_confidence:.2f}, Frame: {self.frame_counter})")

                else:
                    # Only handle failure for classic tracking (not smart override)
                    self.frame_counter = 0
                    if self.tracking_failure_start_time is None:
                        self.tracking_failure_start_time = time.time()
                        logging.warning("Tracking lost. Starting failure timer.")
                    else:
                        elapsed_time = time.time() - self.tracking_failure_start_time
                        if elapsed_time > Parameters.TRACKING_FAILURE_TIMEOUT:
                            logging.error("Tracking lost for too long. Handling failure.")
                            self.tracking_started = False
                            if self.tracker and hasattr(self.tracker, 'stop_tracking'):
                                self.tracker.stop_tracking()
                            self.tracking_failure_start_time = None
                        else:
                            logging.warning(f"Tracking lost. Attempting recovery. Elapsed time: {elapsed_time:.2f} sec.")
                            self.tracker.update_estimator_without_measurement()
                            frame = self.tracker.draw_estimate(frame, tracking_successful=False)
                            if self.following_active:
                                await self.follow_target()
                                await self.check_failsafe()
                            redetect_result = self.handle_tracking_failure()
                            if redetect_result:
                                self.tracking_failure_start_time = None


            _t_track = time.monotonic()

            # Telemetry handling
            if self.telemetry_handler.should_send_telemetry():
                self.telemetry_handler.send_telemetry()

            # Update current frame for app controller
            self.current_frame = frame

            stream_width = Parameters.STREAM_WIDTH
            stream_height = Parameters.STREAM_HEIGHT
            stream_processed = bool(getattr(Parameters, "STREAM_PROCESSED_OSD", True))
            target_resolution = str(
                getattr(Parameters, "OSD_TARGET_LAYER_RESOLUTION", "stream")
            ).strip().lower()

            capture_osd_frame = None

            # Maintain raw resized frame only when stream is configured for non-OSD output.
            self.video_handler.update_resized_frames(
                stream_width,
                stream_height,
                resize_raw=not stream_processed,
                resize_osd=False,
                raw_frame=self.video_handler.current_raw_frame if self.video_handler.current_raw_frame is not None else frame,
            )

            if stream_processed:
                if target_resolution == "capture":
                    capture_osd_frame = self.osd_pipeline.compose(frame.copy())
                    stream_osd_frame = self.video_handler.resize_frame(
                        capture_osd_frame, stream_width, stream_height
                    )
                    self.video_handler.current_osd_frame = capture_osd_frame
                else:
                    stream_base = self.video_handler.resize_frame(frame, stream_width, stream_height)
                    stream_osd_frame = self.osd_pipeline.compose(stream_base)
                    # Keep compatibility for code paths that inspect current_osd_frame.
                    self.video_handler.current_osd_frame = frame

                self.video_handler.current_resized_osd_frame = stream_osd_frame
                # Publish to thread-safe frame publisher for streaming consumers
                self.frame_publisher.publish(
                    osd_frame=stream_osd_frame,
                    raw_frame=self.video_handler.current_resized_raw_frame,
                )
            else:
                self.video_handler.current_osd_frame = frame
                self.video_handler.current_resized_osd_frame = None
                # Publish raw frame when OSD is disabled
                self.frame_publisher.publish(
                    osd_frame=None,
                    raw_frame=self.video_handler.current_resized_raw_frame,
                )

            _t_osd = time.monotonic()

            # Optional secondary GStreamer output
            if Parameters.ENABLE_GSTREAMER_STREAM and hasattr(self, 'gstreamer_handler'):
                gstreamer_frame = capture_osd_frame if capture_osd_frame is not None else frame
                self.gstreamer_handler.stream_frame(gstreamer_frame)

            # Optional local video recording (non-blocking)
            if hasattr(self, 'recording_manager') and self.recording_manager and self.recording_manager.is_recording:
                if self.recording_manager._include_osd and capture_osd_frame is not None:
                    self.recording_manager.write_frame(capture_osd_frame)
                else:
                    self.recording_manager.write_frame(frame)

            _t_publish = time.monotonic()

            # Update per-stage pipeline metrics
            self._pipeline_metrics['preprocess_ms'] = round((_t_preprocess - _t0) * 1000, 2)
            self._pipeline_metrics['tracking_ms'] = round((_t_track - _t_preprocess) * 1000, 2)
            self._pipeline_metrics['osd_ms'] = round((_t_osd - _t_track) * 1000, 2)
            self._pipeline_metrics['publish_ms'] = round((_t_publish - _t_osd) * 1000, 2)

        except Exception as e:
            logging.exception(f"Error in update_loop: {e}")
        return frame

    def handle_tracking_failure(self):
        """
        Handles tracking failure by attempting re-detection using the detector.
        Only used in classic mode.
        """
        # Don't use classic detector re-detection when smart tracker is active
        if self.smart_mode_active:
            logging.debug("Smart tracker is active, skipping classic re-detection")
            return {"success": False, "message": "Smart tracker mode - classic re-detection disabled."}
            
        if Parameters.USE_DETECTOR and Parameters.AUTO_REDETECT:
            logging.info("Attempting to re-detect the target using the detector.")
            redetect_result = self.initiate_redetection()
            if redetect_result["success"]:
                logging.info("Target re-detected and tracker re-initialized.")
            else:
                logging.info("Re-detection attempt failed. Retrying...")
            return redetect_result
        return {"success": False, "message": "Detector not enabled or auto-redetect off."}

    async def check_failsafe(self):
        if self.px4_interface.failsafe_active:
            await self.handle_failsafe()
            self.px4_interface.failsafe_active = False

    async def handle_failsafe(self):
        await self.disconnect_px4()

    async def _handle_offboard_mode_exit(self, old_mode, new_mode):
        """
        Automatically disable follow mode when drone exits Offboard mode.

        This method is called by the MAVLink data manager when it detects a flight
        mode transition from Offboard to any other mode. This ensures that the
        follow mode state is automatically synchronized with the drone's actual
        flight mode, regardless of how the mode was changed (pilot, failsafe, etc.).

        Args:
            old_mode (int): Previous flight mode code (393216 for Offboard)
            new_mode (int): New flight mode code

        Affected components:
        - following_active flag → Set to False
        - OSD scope color → Changes from red (active) to yellow (inactive)
        - Dashboard UI → Updates to show follow mode disabled
        - Telemetry → Updates following_active status
        """
        if not self.following_active:
            # Follow mode already inactive, no action needed
            return

        try:
            # Get human-readable mode names for logging
            mode_name = self.px4_interface.get_flight_mode_text(new_mode)

            logging.warning(
                f"OFFBOARD MODE EXITED: Drone switched to {mode_name} ({new_mode}). "
                f"Automatically disabling follow mode for safety."
            )

            # Gracefully stop follow mode using existing disconnect logic
            # This will:
            # - Stop the setpoint sender thread
            # - Stop offboard mode (if still active)
            # - Clean up follower instance
            # - Set following_active = False
            # - Update all UI indicators (OSD scope color, dashboard status, etc.)
            await self.disconnect_px4()

            logging.info("Follow mode automatically disabled due to Offboard mode exit")

        except Exception as e:
            logging.error(f"Error handling Offboard mode exit: {e}")
            # Ensure following_active is set to False even if cleanup fails
            self.following_active = False

    async def handle_key_input_async(self, key: int, frame: np.ndarray):
        """
        Asynchronous key input handler.
        'y' toggles segmentation.
        't' toggles classic tracking.
        's' toggles smart mode.
        Other keys perform PX4 or re-detection actions.
        """
        if key == ord('y'):
            self.toggle_segmentation()
        elif key == ord('t'):
            self.toggle_tracking(frame)
        # Within the key input handler (handle_key_input_async)
        elif key == ord('s'):
            self.toggle_smart_mode()
        elif key == ord('d'):
            self.initiate_redetection()
        elif key == ord('f'):
            await self.connect_px4()
        elif key == ord('x'):
            await self.disconnect_px4()
        elif key == ord('c'):
            self.cancel_activities()
        elif key == ord('o'):
            new_preset = self.osd_mode_manager.cycle_preset()
            self.logger.info(f"OSD preset cycled to: {new_preset}")
        elif key == ord('n'):
            new_mode = self.osd_mode_manager.cycle_color_mode()
            self.logger.info(f"OSD color mode cycled to: {new_mode}")
        elif key == ord('r'):
            if hasattr(self, 'recording_manager') and self.recording_manager:
                if self.recording_manager.is_active:
                    result = self.recording_manager.stop()
                    self.logger.info(f"Recording stopped via keyboard: {result.get('message', '')}")
                else:
                    source_fps = self.video_handler.fps if hasattr(self.video_handler, 'fps') else 30
                    cap = self.video_handler.cap if hasattr(self.video_handler, 'cap') else None
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if cap else 640
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if cap else 480
                    result = self.recording_manager.start(source_fps or 30, w, h)
                    self.logger.info(f"Recording via keyboard: {result.get('message', '')}")

    def handle_key_input(self, key: int, frame: np.ndarray):
        """
        Synchronous key input handler that schedules the asynchronous handler.
        """
        asyncio.create_task(self.handle_key_input_async(key, frame))

    def handle_user_click(self, x: int, y: int):
        """
        Handles user click events for segmentation-based object selection.
        """
        if not self.segmentation_active:
            return

        detections = self.segmentor.get_last_detections()
        selected_bbox = self.identify_clicked_object(detections, x, y)
        if selected_bbox:
            selected_bbox = tuple(map(lambda a: int(round(a)), selected_bbox))
            self.tracker.reinitialize_tracker(self.current_frame, selected_bbox)
            self.tracking_started = True
            logging.info(f"Object selected for tracking: {selected_bbox}")

    def identify_clicked_object(self, detections: list, x: int, y: int) -> Optional[Tuple[int, int, int, int]]:
        """
        Identifies the clicked object based on segmentation detections.
        """
        for det in detections:
            x1, y1, x2, y2 = det
            if x1 <= x <= x2 and y1 <= y <= y2:
                return det
        return None

    def initiate_redetection(self) -> Dict[str, any]:
        """
        Attempts to re-detect the target using the detector (classic mode only).
        """
        if Parameters.USE_DETECTOR:
            estimate = self.tracker.get_estimated_position()
            if estimate:
                estimated_x, estimated_y = estimate[:2]
                search_radius = Parameters.REDETECTION_SEARCH_RADIUS
                x_min = max(0, int(estimated_x - search_radius))
                x_max = min(self.video_handler.width, int(estimated_x + search_radius))
                y_min = max(0, int(estimated_y - search_radius))
                y_max = min(self.video_handler.height, int(estimated_y + search_radius))
                search_region = (x_min, y_min, x_max - x_min, y_max - y_min)
                redetect_result = self.detector.smart_redetection(
                    self.current_frame, self.tracker, roi=search_region
                )
            else:
                redetect_result = self.detector.smart_redetection(self.current_frame, self.tracker)

            if redetect_result:
                detected_bbox = self.detector.get_latest_bbox()
                self.tracker.reinitialize_tracker(self.current_frame, detected_bbox)
                self.tracking_started = True
                logging.info("Re-detection successful and tracker re-initialized.")
                return {
                    "success": True,
                    "message": "Re-detection successful and tracker re-initialized.",
                    "bounding_box": detected_bbox
                }
            else:
                logging.info("Re-detection failed or no new object found.")
                return {
                    "success": False,
                    "message": "Re-detection failed or no new object found."
                }
        else:
            return {
                "success": False,
                "message": "Detector is not enabled."
            }

    def show_current_frame(self, frame_title: str = Parameters.FRAME_TITLE) -> np.ndarray:
        """
        Displays the current frame in a window if enabled.
        """
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.imshow(frame_title, self.current_frame)
        return self.current_frame

    async def connect_px4(self) -> Dict[str, any]:
        """
        Enhanced PX4 connection with unified command protocol support.
        Automatically stops existing follower if active before starting a new one.

        Returns:
            Dict with status information including steps taken and any errors
        """
        result = {"steps": [], "errors": [], "auto_stopped": False}

        # Use lock to prevent race conditions during state changes
        async with self._follower_state_lock:
            # Auto-stop if follower is already active (user-friendly feature)
            if self.following_active:
                logging.info("Follower already active - automatically stopping before restart...")
                result["steps"].append("Auto-stopping active follower for restart")
                result["auto_stopped"] = True

                # Call internal stop without acquiring lock again
                stop_result = await self._disconnect_px4_internal()
                result["steps"].extend([f"[Auto-stop] {step}" for step in stop_result["steps"]])

                if stop_result["errors"]:
                    result["errors"].extend([f"[Auto-stop] {err}" for err in stop_result["errors"]])
                    logging.warning("Auto-stop encountered errors, but continuing with start...")

            # Now proceed with starting follower
            try:
                logging.info("Activating Follow Mode to PX4!")

                # Connect to PX4
                await self.px4_interface.connect()
                logging.info("Connected to PX4 Drone!")

                # Determine initial target coordinates
                initial_target_coords = (
                    tuple(self.tracker.normalized_center)
                    if Parameters.TARGET_POSITION_MODE == 'initial'
                    else tuple(Parameters.DESIRE_AIM)
                )

                # Create follower using enhanced factory
                try:
                    self.follower = Follower(self.px4_interface, initial_target_coords)

                    # Update telemetry handler
                    self.telemetry_handler.follower = self.follower

                    # Log follower information
                    logging.info(f"Follower initialized: {self.follower.get_display_name()}")
                    logging.info(f"Control type: {self.follower.get_control_type()}")
                    logging.info(f"Available fields: {self.follower.get_available_fields()}")

                    # Validate follower configuration
                    if not self.follower.validate_current_mode():
                        logging.warning("Follower mode validation failed, but continuing...")

                    result["steps"].append(f"Follower created: {self.follower.get_display_name()}")

                except Exception as e:
                    error_msg = f"Failed to create follower: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
                    raise

                # Set hover throttle for attitude rate control modes
                try:
                    await self.px4_interface.set_hover_throttle()
                    result["steps"].append("Hover throttle configured")
                except Exception as e:
                    logging.warning(f"Failed to set hover throttle: {e}")
                    # Continue anyway, not critical for velocity modes

                # Send initial setpoint using schema-aware method
                try:
                    await self.px4_interface.send_initial_setpoint()
                    result["steps"].append("Initial setpoint sent")
                except Exception as e:
                    error_msg = f"Failed to send initial setpoint: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
                    raise

                # Start offboard mode
                try:
                    await self.px4_interface.start_offboard_mode()
                    result["steps"].append("Offboard mode started")
                except Exception as e:
                    error_msg = f"Failed to start offboard mode: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
                    raise

                # Create and start enhanced setpoint sender
                try:
                    from classes.setpoint_sender import SetpointSender
                    self.setpoint_sender = SetpointSender(
                        self.px4_interface,
                        self.follower.follower.setpoint_handler
                    )

                    # Validate configuration before starting
                    if self.setpoint_sender.validate_configuration():
                        self.setpoint_sender.start()
                        result["steps"].append("Enhanced setpoint sender started")
                        logging.info(f"SetpointSender started for {self.follower.get_display_name()}")
                    else:
                        error_msg = "SetpointSender configuration validation failed"
                        logging.error(error_msg)
                        result["errors"].append(error_msg)

                except Exception as e:
                    error_msg = f"Failed to start setpoint sender: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
                    # Continue without setpoint sender if needed

                # Mark as active
                self.following_active = True

                # Log final status
                logging.info("Follow mode activation completed successfully!")
                if hasattr(self.follower, 'get_status_report'):
                    logging.debug(self.follower.get_status_report())

            except Exception as e:
                error_msg = f"Failed to connect/start offboard mode: {e}"
                logging.error(error_msg)
                result["errors"].append(error_msg)

                # Cleanup on failure - call internal method to avoid deadlock
                try:
                    if hasattr(self, 'setpoint_sender') and self.setpoint_sender:
                        self.setpoint_sender.stop()
                        self.setpoint_sender = None
                    await self.px4_interface.stop_offboard_mode()
                    if hasattr(self, 'follower') and self.follower:
                        self.follower = None
                    self.following_active = False
                except Exception as cleanup_error:
                    logging.error(f"Error during cleanup: {cleanup_error}")

        return result

    async def _disconnect_px4_internal(self) -> Dict[str, any]:
        """
        Internal method for PX4 disconnection without acquiring lock.
        Used by connect_px4 for auto-stop functionality to avoid deadlock.

        Returns:
            Dict with status information
        """
        result = {"steps": [], "errors": []}

        if not self.following_active:
            result["steps"].append("Follow mode is not active.")
            return result

        try:
            logging.info("Deactivating Follow Mode...")

            # Stop setpoint sender first
            if hasattr(self, 'setpoint_sender') and self.setpoint_sender:
                try:
                    # Get status before stopping
                    sender_status = self.setpoint_sender.get_status()
                    logging.debug(f"SetpointSender status before stop: {sender_status}")

                    self.setpoint_sender.stop()
                    result["steps"].append("Enhanced setpoint sender stopped")
                    logging.info("SetpointSender stopped successfully")
                except Exception as e:
                    error_msg = f"Error stopping setpoint sender: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
                finally:
                    self.setpoint_sender = None

            # Stop offboard mode
            try:
                await self.px4_interface.stop_offboard_mode()
                result["steps"].append("Offboard mode stopped")
            except Exception as e:
                error_msg = f"Failed to stop offboard mode: {e}"
                logging.error(error_msg)
                result["errors"].append(error_msg)

            # Reset follower
            if hasattr(self, 'follower') and self.follower:
                try:
                    # Log final follower status
                    if hasattr(self.follower, 'get_status_report'):
                        logging.debug("Final follower status:")
                        logging.debug(self.follower.get_status_report())

                    self.follower = None
                    result["steps"].append("Follower instance cleaned up")
                except Exception as e:
                    logging.warning(f"Error during follower cleanup: {e}")

            # Mark as inactive
            self.following_active = False

            logging.info("Follow mode deactivated successfully!")

        except Exception as e:
            error_msg = f"Error during PX4 disconnection: {e}"
            logging.error(error_msg)
            result["errors"].append(error_msg)

        return result

    async def disconnect_px4(self) -> Dict[str, any]:
        """
        Enhanced PX4 disconnection with proper cleanup of unified protocol components.
        Thread-safe wrapper that acquires lock before calling internal disconnect.

        Returns:
            Dict with status information
        """
        # Use lock to prevent race conditions during state changes
        async with self._follower_state_lock:
            return await self._disconnect_px4_internal()

    async def switch_tracker_type(self, new_tracker_type: str) -> Dict[str, Any]:
        """
        Switch to a different classic tracker type dynamically.

        This method provides a clean, user-friendly way to change trackers from the UI
        without editing configuration files. It handles all necessary cleanup and
        initialization to ensure a smooth transition.

        Args:
            new_tracker_type (str): The tracker type name (e.g., "CSRTTracker", "DlibTracker")

        Returns:
            Dict[str, Any]: Result dictionary with keys:
                - success (bool): Whether the switch was successful
                - old_tracker (str): Previous tracker type
                - new_tracker (str): New tracker type
                - was_tracking (bool): Whether tracking was active before switch
                - message (str): Human-readable status message
                - requires_restart (bool): Whether user needs to restart tracking manually
                - error (str, optional): Error message if switch failed

        Example:
            >>> result = await app_controller.switch_tracker_type("DlibTracker")
            >>> if result['success']:
            ...     print(f"Switched to {result['new_tracker']}")
        """
        from classes.schema_manager import get_schema_manager

        try:
            schema_manager = get_schema_manager()

            # 1. Validate new tracker exists and is UI-selectable
            is_valid, error_msg = schema_manager.validate_tracker_for_ui(new_tracker_type)
            if not is_valid:
                logging.warning(f"Invalid tracker selection: {new_tracker_type} - {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "old_tracker": self.current_tracker_type,
                    "new_tracker": new_tracker_type
                }

            # 2. Get factory key for creating new tracker
            tracker_info = schema_manager.get_tracker_info(new_tracker_type)
            factory_key = tracker_info.get('ui_metadata', {}).get('factory_key')

            if not factory_key:
                error_msg = f"Tracker {new_tracker_type} has no factory key"
                logging.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "old_tracker": self.current_tracker_type,
                    "new_tracker": new_tracker_type
                }

            # 3. Check if following is active (block switch for safety)
            if self.following_active:
                error_msg = "Cannot switch tracker while following is active. Please disconnect PX4 first."
                logging.warning(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "old_tracker": self.current_tracker_type,
                    "new_tracker": new_tracker_type,
                    "requires_disconnect": True
                }

            # 4. Record current state
            was_tracking = self.tracking_started
            old_tracker_type = self.current_tracker_type
            old_tracker_class = self.tracker.__class__.__name__ if self.tracker else "None"

            logging.info(f"TRACKER SWITCH: Changing from {old_tracker_type} → {new_tracker_type}")
            logging.info(f"  Previous tracker: {old_tracker_class}")
            logging.info(f"  Tracking was active: {was_tracking}")

            # 5. Stop tracking and cleanup current tracker
            if was_tracking:
                logging.info("  Stopping active tracking...")
                self.cancel_activities()

            # 6. Destroy old tracker instance
            if self.tracker:
                logging.info(f"  Cleaning up old tracker: {self.tracker.__class__.__name__}")
                try:
                    if hasattr(self.tracker, 'stop_tracking'):
                        self.tracker.stop_tracking()
                    if hasattr(self.tracker, 'reset'):
                        self.tracker.reset()
                except Exception as e:
                    logging.warning(f"  Error during tracker cleanup: {e}")
                finally:
                    self.tracker = None

            # 7. Create new tracker instance
            try:
                logging.info(f"  Creating new tracker: {factory_key}")
                self.tracker = create_tracker(
                    factory_key,
                    self.video_handler,
                    self.detector,
                    self
                )

                # 8. Update application state
                self.current_tracker_type = new_tracker_type
                Parameters.DEFAULT_TRACKING_ALGORITHM = factory_key

                logging.info(f"✅ TRACKER SWITCH SUCCESSFUL")
                logging.info(f"  New tracker: {self.tracker.__class__.__name__}")
                logging.info(f"  Factory key: {factory_key}")

                # 9. Determine user action message
                if was_tracking:
                    message = f"Switched to {tracker_info.get('ui_metadata', {}).get('display_name', new_tracker_type)}. Please select a new ROI to resume tracking."
                    requires_restart = True
                else:
                    message = f"Switched to {tracker_info.get('ui_metadata', {}).get('display_name', new_tracker_type)}. Ready for tracking."
                    requires_restart = False

                return {
                    "success": True,
                    "old_tracker": old_tracker_type,
                    "new_tracker": new_tracker_type,
                    "new_tracker_display_name": tracker_info.get('ui_metadata', {}).get('display_name', new_tracker_type),
                    "factory_key": factory_key,
                    "was_tracking": was_tracking,
                    "requires_restart": requires_restart,
                    "message": message
                }

            except Exception as e:
                error_msg = f"Failed to create new tracker: {str(e)}"
                logging.error(f"❌ TRACKER SWITCH FAILED: {error_msg}")

                # Try to restore old tracker if possible
                logging.warning("  Attempting to restore previous tracker...")
                try:
                    old_factory_key = schema_manager.get_tracker_info(old_tracker_type).get('ui_metadata', {}).get('factory_key')
                    if old_factory_key:
                        self.tracker = create_tracker(
                            old_factory_key,
                            self.video_handler,
                            self.detector,
                            self
                        )
                        logging.info("  ✓ Previous tracker restored")
                except Exception as restore_error:
                    logging.error(f"  ✗ Failed to restore previous tracker: {restore_error}")

                return {
                    "success": False,
                    "error": error_msg,
                    "old_tracker": old_tracker_type,
                    "new_tracker": new_tracker_type,
                    "was_tracking": was_tracking
                }

        except Exception as e:
            error_msg = f"Unexpected error during tracker switch: {str(e)}"
            logging.error(f"❌ TRACKER SWITCH EXCEPTION: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "old_tracker": getattr(self, 'current_tracker_type', 'Unknown'),
                "new_tracker": new_tracker_type
            }

    async def follow_target(self):
        """
        Enhanced target following with flexible tracker schema and proper async command dispatch.
        """
        # DEBUG: Log when follow_target is called
        logging.debug(f"Follow target called - tracking_started={self.tracking_started}, following_active={self.following_active}")

        # For always-reporting trackers, only check following_active (not tracking_started)
        is_always_reporting = self._is_always_reporting_tracker()
        if is_always_reporting:
            if not self.following_active:
                logging.debug(f"Follow target early exit (always-reporting): following_active={self.following_active}")
                return False
            else:
                logging.debug(f"Always-reporting tracker: Proceeding with follow_target (tracking_started not required)")
        else:
            # Classic trackers require both tracking_started AND following_active
            if not (self.tracking_started and self.following_active):
                logging.debug(f"Follow target early exit (classic): tracking_started={self.tracking_started}, following_active={self.following_active}")
                return False
            
        try:
            # Get structured tracker output
            tracker_output = self.get_tracker_output()
            if not tracker_output:
                logging.warning("No tracker output available for following.")
                return False
            
            # Validate tracker compatibility with current follower
            if not self.validate_tracker_follower_compatibility(tracker_output):
                logging.warning("Current tracker incompatible with active follower")
                return False
            
            # SYNCHRONOUS: Calculate and set commands using structured data (no await needed)
            try:
                logging.debug(f"Calling follower.follow_target() with tracker_output: data_type={tracker_output.data_type}, tracking_active={tracker_output.tracking_active}")
                follow_result = self.follower.follow_target(tracker_output)
                logging.debug(f"Follower result: follow_target returned {follow_result}")

                # DEBUG: Check current setpoint values after follower processing
                if hasattr(self.follower, 'setpoint_handler'):
                    setpoints = self.follower.setpoint_handler.get_fields()
                    logging.debug(f"Setpoints after follower: {setpoints}")

                if follow_result is False:
                    # Follower already logged specific error with rate limiting
                    logging.debug("Follower follow_target returned False")
                    return False
            except Exception as e:
                logging.error(f"Error in follower.follow_target: {e}")
                return False
            
            # ASYNCHRONOUS: Send the actual commands to PX4
            try:
                control_type = self.follower.get_control_type()
                logging.debug(f"Command dispatch: control_type={control_type}, sending via PX4Interface")

                if control_type == 'attitude_rate':
                    await self.px4_interface.send_attitude_rate_commands()
                    logging.debug(f"Sent: attitude_rate commands")
                elif control_type == 'velocity_body':
                    await self.px4_interface.send_body_velocity_commands()
                    logging.debug(f"Sent: velocity_body commands")
                elif control_type == 'velocity_body_offboard':
                    await self.px4_interface.send_velocity_body_offboard_commands()
                    logging.debug(f"Sent: velocity_body_offboard commands")
                else:
                    logging.warning(f"Unknown control type: {control_type}")
                    return False
            except Exception as e:
                logging.error(f"Error sending commands to PX4: {e}")
                return False
            
            return True
            
        except Exception as e:
            logging.error(f"Error in follow_target: {e}")
            return False

    async def shutdown(self) -> Dict[str, any]:
        """
        Enhanced graceful shutdown with proper cleanup of all unified protocol components.
        """
        result = {"steps": [], "errors": []}
        try:
            logging.info("Starting application shutdown...")
            
            # Stop MAVLink data manager if enabled
            if Parameters.MAVLINK_ENABLED and hasattr(self, 'mavlink_data_manager'):
                try:
                    self.mavlink_data_manager.stop_polling()
                    result["steps"].append("MAVLink data manager stopped")
                except Exception as e:
                    logging.error(f"Error stopping MAVLink data manager: {e}")
                    result["errors"].append(f"MAVLink stop error: {e}")
            
            # Disconnect PX4 and cleanup following components
            if self.following_active:
                try:
                    logging.info("Stopping follow mode and PX4 connection...")
                    disconnect_result = await self.disconnect_px4()
                    result["steps"].extend(disconnect_result.get("steps", []))
                    result["errors"].extend(disconnect_result.get("errors", []))
                except Exception as e:
                    error_msg = f"Error during PX4 disconnection: {e}"
                    logging.error(error_msg)
                    result["errors"].append(error_msg)
            
            # Release video handler
            try:
                if hasattr(self, 'video_handler') and self.video_handler:
                    self.video_handler.release()
                    result["steps"].append("Video handler released")
                    logging.info("Video handler released")
            except Exception as e:
                logging.error(f"Error releasing video handler: {e}")
                result["errors"].append(f"Video handler release error: {e}")
            
            # Stop recording if active
            try:
                if hasattr(self, 'recording_manager') and self.recording_manager:
                    self.recording_manager.release()
                    result["steps"].append("Recording manager released")
            except Exception as e:
                logging.error(f"Error stopping recording: {e}")
                result["errors"].append(f"Recording stop error: {e}")

            # Stop storage monitoring
            try:
                if hasattr(self, 'storage_manager') and self.storage_manager:
                    self.storage_manager.stop_monitoring()
                    result["steps"].append("Storage monitor stopped")
            except Exception as e:
                logging.error(f"Error stopping storage monitor: {e}")
                result["errors"].append(f"Storage monitor stop error: {e}")

            # Additional cleanup for new components
            try:
                # Clear follower reference
                if hasattr(self, 'follower'):
                    self.follower = None

                # Stop and clear setpoint sender (ensure it's stopped even if not following)
                if hasattr(self, 'setpoint_sender') and self.setpoint_sender:
                    try:
                        logging.info("🛑 Stopping SetpointSender during shutdown...")
                        self.setpoint_sender.stop()
                        self.setpoint_sender.join(timeout=3.0)  # Wait for thread to finish
                        result["steps"].append("SetpointSender stopped during shutdown")
                    except Exception as e:
                        logging.error(f"Error stopping SetpointSender during shutdown: {e}")
                        result["errors"].append(f"SetpointSender stop error: {e}")
                    finally:
                        self.setpoint_sender = None

                result["steps"].append("Component references cleared")
                
            except Exception as e:
                logging.error(f"Error during component cleanup: {e}")
                result["errors"].append(f"Component cleanup error: {e}")
            
            result["steps"].append("Shutdown complete")
            logging.info("Application shutdown completed")
            
        except Exception as e:
            error_msg = f"Critical error during shutdown: {e}"
            logging.error(error_msg)
            result["errors"].append(error_msg)
        
        return result

    # ==================== Enhanced Tracker Schema Methods ====================
    
    def get_tracker_output(self) -> Optional[TrackerOutput]:
        """
        Gets structured output from the current active tracker.
        
        Returns:
            Optional[TrackerOutput]: Structured tracker data or None if unavailable
        """
        try:
            # Determine which tracker is active
            if self.smart_mode_active and self.smart_tracker:
                # Smart tracker is active
                if hasattr(self.smart_tracker, 'get_output'):
                    tracker_output = self.smart_tracker.get_output()
                    # Log status periodically with minimal, informative output
                    if tracker_output and tracker_output.tracking_active and (time.time() % 10 < 0.1):
                        target_info = f"ID:{tracker_output.target_id}" if tracker_output.target_id else "None"
                        logging.info(f"SMART TRACKER: {tracker_output.data_type.value} | Target: {target_info}")
                    return tracker_output
                else:
                    logging.warning("Smart tracker doesn't have get_output method")
                    return None
                    
            elif self.tracker:
                # Check if this is an external tracker that doesn't need manual start
                is_external_tracker = getattr(self.tracker, 'is_external_tracker', False)
                tracker_class = self.tracker.__class__.__name__

                logging.debug(f"AppController.get_tracker_output() - tracker: {tracker_class}, is_external: {is_external_tracker}, tracking_started: {self.tracking_started}")

                # For external trackers, always try to get output regardless of tracking_started
                # For classic trackers, require tracking_started to be True
                if is_external_tracker or self.tracking_started:
                    if hasattr(self.tracker, 'get_output'):
                        tracker_output = self.tracker.get_output()
                        # Log status periodically with minimal, informative output
                        if tracker_output and tracker_output.tracking_active and (time.time() % 10 < 0.1):
                            tracker_name = self.tracker.__class__.__name__.replace("Tracker", "")
                            if is_external_tracker:
                                # Enhanced logging for external trackers
                                status_info = "MONITORING" if hasattr(self.tracker, 'monitoring_active') and self.tracker.monitoring_active else "STANDBY"
                                logging.info(f"EXTERNAL TRACKER ({tracker_name}): {tracker_output.data_type.value} | Status: {status_info}")
                            else:
                                # Classic tracker logging
                                conf_info = f"Conf:{tracker_output.confidence:.2f}" if tracker_output.confidence else "NoConf"
                                logging.info(f"CLASSIC TRACKER ({tracker_name}): {tracker_output.data_type.value} | {conf_info}")
                        return tracker_output
                    else:
                        # Fallback for legacy trackers
                        if not is_external_tracker:
                            logging.debug("Using legacy tracker compatibility mode")
                            return self._create_legacy_tracker_output()
                        return None
                else:
                    # Classic tracker not started - log this only occasionally
                    if time.time() % 30 < 0.1:  # Every 30 seconds
                        logging.info("CLASSIC TRACKER: Waiting for manual tracking to start")
                    return None
            else:
                # No tracker available - log this only occasionally
                if time.time() % 30 < 0.1:  # Every 30 seconds
                    logging.info("NO TRACKER AVAILABLE: Tracker not initialized")
                return None
                
        except Exception as e:
            logging.error(f"Error getting tracker output: {e}")
            return None
    
    def get_tracker_status_debug(self) -> str:
        """
        Returns a comprehensive debug string about the current tracker state.
        
        Returns:
            str: Debug information about tracker states
        """
        status_parts = []
        status_parts.append(f"tracking_started: {self.tracking_started}")
        status_parts.append(f"smart_mode_active: {self.smart_mode_active}")
        status_parts.append(f"tracker: {self.tracker.__class__.__name__ if self.tracker else None}")
        status_parts.append(f"smart_tracker: {'Active' if self.smart_tracker else 'None'}")
        
        if self.tracker and hasattr(self.tracker, 'tracking_started'):
            status_parts.append(f"tracker.tracking_started: {self.tracker.tracking_started}")
        
        if self.smart_tracker and hasattr(self.smart_tracker, 'selected_object_id'):
            status_parts.append(f"smart_tracker.selected_object_id: {self.smart_tracker.selected_object_id}")
            
        return " | ".join(status_parts)
    
    def _create_legacy_tracker_output(self) -> Optional[TrackerOutput]:
        """
        Creates TrackerOutput from legacy tracker for backwards compatibility.
        
        Returns:
            Optional[TrackerOutput]: Legacy-compatible tracker output
        """
        try:
            if not (hasattr(self.tracker, 'normalized_center') and 
                   hasattr(self.tracker, 'normalized_bbox')):
                logging.debug("Legacy tracker missing required attributes (normalized_center or normalized_bbox)")
                return None
            
            # Debug the values being used
            normalized_center = self.tracker.normalized_center
            normalized_bbox = self.tracker.normalized_bbox
            bbox = getattr(self.tracker, 'bbox', None)
            confidence = getattr(self.tracker, 'confidence', 1.0)
            
            logging.debug(f"Legacy tracker output: center={normalized_center}, bbox={bbox}, confidence={confidence}")
            
            if normalized_center is None:
                logging.warning("Legacy tracker has None normalized_center - follower will fail")
            
            return TrackerOutput(
                data_type=TrackerDataType.POSITION_2D,
                timestamp=time.time(),
                tracking_active=self.tracking_started,
                tracker_id="legacy_tracker",
                position_2d=normalized_center,
                bbox=bbox,
                normalized_bbox=normalized_bbox,
                confidence=confidence,
                metadata={"legacy_mode": True}
            )
            
        except Exception as e:
            logging.error(f"Error creating legacy tracker output: {e}")
            return None
    
    def validate_tracker_follower_compatibility(self, tracker_output: TrackerOutput) -> bool:
        """
        Validates compatibility between current tracker and follower.
        
        Args:
            tracker_output (TrackerOutput): Tracker output to validate
            
        Returns:
            bool: True if compatible, False otherwise
        """
        try:
            if not self.follower:
                logging.warning("No active follower to validate against")
                return False
            
            # Use follower's validation method if available
            if hasattr(self.follower, 'validate_tracker_compatibility'):
                return self.follower.validate_tracker_compatibility(tracker_output)
            else:
                # Basic compatibility check for legacy followers
                return tracker_output.position_2d is not None
                
        except Exception as e:
            logging.error(f"Error validating tracker-follower compatibility: {e}")
            return False
    
    def get_tracker_capabilities(self) -> Optional[Dict[str, Any]]:
        """
        Gets capabilities of the current active tracker.
        
        Returns:
            Optional[Dict[str, Any]]: Tracker capabilities or None if unavailable
        """
        try:
            if not self.tracker:
                return None
            
            if hasattr(self.tracker, 'get_capabilities'):
                return self.tracker.get_capabilities()
            else:
                # Default capabilities for legacy trackers
                return {
                    'data_types': [TrackerDataType.POSITION_2D.value],
                    'supports_confidence': hasattr(self.tracker, 'confidence'),
                    'supports_velocity': False,
                    'supports_bbox': hasattr(self.tracker, 'bbox'),
                    'legacy_tracker': True
                }
                
        except Exception as e:
            logging.error(f"Error getting tracker capabilities: {e}")
            return None
    
    def get_system_compatibility_report(self) -> Dict[str, Any]:
        """
        Generates a comprehensive compatibility report between tracker and follower.
        
        Returns:
            Dict[str, Any]: Detailed compatibility analysis
        """
        try:
            report = {
                'timestamp': time.time(),
                'tracker_active': bool(self.tracker),
                'follower_active': bool(self.follower),
                'compatible': False,
                'issues': [],
                'recommendations': []
            }
            
            if not self.tracker:
                report['issues'].append("No active tracker")
                return report
            
            if not self.follower:
                report['issues'].append("No active follower")
                return report
            
            # Get current tracker output
            tracker_output = self.get_tracker_output()
            if not tracker_output:
                report['issues'].append("Unable to get tracker output")
                return report
            
            # Get capabilities
            tracker_caps = self.get_tracker_capabilities()
            
            report.update({
                'tracker_capabilities': tracker_caps,
                'current_tracker_data': {
                    'type': tracker_output.data_type.value,
                    'tracking_active': tracker_output.tracking_active,
                    'has_position_2d': tracker_output.position_2d is not None,
                    'has_confidence': tracker_output.confidence is not None,
                }
            })
            
            # Validate compatibility
            is_compatible = self.validate_tracker_follower_compatibility(tracker_output)
            report['compatible'] = is_compatible
            
            if not is_compatible:
                report['issues'].append("Tracker data incompatible with follower requirements")
            else:
                report['recommendations'].append("Current tracker-follower combination is compatible")
            
            return report
            
        except Exception as e:
            logging.error(f"Error generating compatibility report: {e}")
            return {
                'timestamp': time.time(),
                'error': str(e),
                'compatible': False
            }
    
    def _start_system_summary_thread(self):
        """Start a background thread for periodic system summary logging."""
        self._summary_stop_event = threading.Event()
        self._summary_thread = threading.Thread(target=self._system_summary_loop, daemon=True)
        self._summary_thread.start()
        
        # Log the system startup
        logging_manager.log_operation(logging.getLogger(__name__), "System Startup", "info", "PixEagle initialized")
    
    def _system_summary_loop(self):
        """Background loop that generates periodic system summaries."""
        logger = logging.getLogger(__name__)
        
        while not self._summary_stop_event.is_set():
            try:
                # Wait for the next summary interval
                if self._summary_stop_event.wait(60):  # 60-second summaries
                    break  # Stop event was set
                
                # Generate system summary
                logging_manager.log_system_summary(logger)
                
            except Exception as e:
                logger.error(f"Error in system summary loop: {e}")
                
        logger.debug("System summary thread stopped")

    def _is_always_reporting_tracker(self) -> bool:
        """
        Check if the current tracker is an always-reporting tracker based on schema properties.
        Uses direct attribute check to avoid circular dependency.

        Returns:
            bool: True if tracker always reports data regardless of manual start
        """
        if not self.tracker:
            return False

        try:
            # Primary check: direct is_external_tracker attribute (avoids circular call)
            if hasattr(self.tracker, 'is_external_tracker'):
                result = getattr(self.tracker, 'is_external_tracker', False)
                return result

            # Secondary check: tracker class name
            tracker_class_name = self.tracker.__class__.__name__
            # This is a fallback - prefer using is_external_tracker attribute
            external_tracker_classes = {'GimbalTracker', 'ExternalTracker'}
            always_reporting_trackers = external_tracker_classes
            return tracker_class_name in always_reporting_trackers

        except Exception as e:
            logging.warning(f"Error checking always_reporting status: {e}")
            return False
