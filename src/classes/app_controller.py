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
from classes.gstreamer_handler import GStreamerHandler
from classes.mavlink_data_manager import MavlinkDataManager
from classes.frame_preprocessor import FramePreprocessor
from classes.estimators.estimator_factory import create_estimator
from classes.detectors.detector_factory import create_detector
from classes.tracker_output import TrackerOutput, TrackerDataType

# Import the SmartTracker module
from classes.smart_tracker import SmartTracker


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

        # Initialize the estimator
        self.estimator = create_estimator(Parameters.ESTIMATOR_TYPE)

        # Initialize video processing components
        self.video_handler = VideoHandler()
        self.video_streamer = None
        self.detector = create_detector(Parameters.DETECTION_ALGORITHM)
        self.tracker = create_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM,
                                      self.video_handler, self.detector, self)

        # Auto-start monitoring for GimbalTracker (external control)
        if hasattr(self.tracker, '__class__') and self.tracker.__class__.__name__ == 'GimbalTracker':
            try:
                # Start background monitoring without manual control
                self.tracker.start_tracking(None, (0, 0, 0, 0))  # Dummy parameters for monitoring
                logging.info("GimbalTracker auto-started for background monitoring")
            except Exception as e:
                logging.error(f"Failed to auto-start GimbalTracker monitoring: {e}")

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

        # Initialize telemetry handler with tracker and follower
        self.telemetry_handler = TelemetryHandler(self, lambda: self.tracking_started)

        # Initialize the FastAPI handler
        logging.debug("Initializing FastAPIHandler...")
        self.api_handler = FastAPIHandler(self)
        logging.debug("FastAPIHandler initialized.")

        # Initialize OSD handler for overlay graphics
        self.osd_handler = OSDHandler(self)
        
        # Initialize GStreamer streaming if enabled
        if Parameters.ENABLE_GSTREAMER_STREAM:
            self.gstreamer_handler = GStreamerHandler()
            self.gstreamer_handler.initialize_stream()

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

        Note: For GimbalTracker, manual tracking initiation is not supported.
        GimbalTracker uses external control and monitors automatically.
        """
        # Check if we're using GimbalTracker (externally controlled)
        if hasattr(self.tracker, '__class__') and self.tracker.__class__.__name__ == 'GimbalTracker':
            logging.warning("Manual tracking control not supported for GimbalTracker")
            logging.info("GimbalTracker requires external control from camera UI application")
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

        Note: For GimbalTracker, manual tracking stop is not supported.
        GimbalTracker stops automatically when external system stops tracking.
        """
        # Check if we're using GimbalTracker (externally controlled)
        if hasattr(self.tracker, '__class__') and self.tracker.__class__.__name__ == 'GimbalTracker':
            logging.warning("Manual tracking control not supported for GimbalTracker")
            logging.info("GimbalTracker stops automatically when external tracking ends")
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

        Note: GimbalTracker continues monitoring even when activities are canceled
        since it operates independently via external control.
        """
        self.tracking_started = False
        self.segmentation_active = False
        # self.smart_mode_active = False
        self.selected_bbox = None

        # Reset tracker state (except for GimbalTracker which should keep monitoring)
        if self.tracker and hasattr(self.tracker, 'stop_tracking'):
            if hasattr(self.tracker, '__class__') and self.tracker.__class__.__name__ == 'GimbalTracker':
                logging.info("GimbalTracker continues monitoring - use external control to stop")
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
        try:
            # Periodic system status update
            current_time = time.time()
            if current_time - self.last_system_status_time > self.system_status_interval:
                self._log_system_status()
                self.last_system_status_time = current_time
            
            # Preprocess the frame if enabled
            if Parameters.ENABLE_PREPROCESSING and self.preprocessor:
                frame = self.preprocessor.preprocess(frame)
            
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

            # Classic Tracker (normal tracking or smart override)
            classic_active = (
            (self.tracking_started and not self.smart_mode_active) or
            self.is_smart_override_active()
            )
            if classic_active:
                success = False
                if self.tracking_failure_start_time is None:
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


            # Telemetry handling
            if self.telemetry_handler.should_send_telemetry():
                self.telemetry_handler.send_telemetry()

            # Update current frame for OSD and video handler
            self.current_frame = frame
            self.video_handler.current_osd_frame = frame

            # Draw OSD elements on frame
            frame = self.osd_handler.draw_osd(frame)

            # GStreamer streaming if enabled
            if Parameters.ENABLE_GSTREAMER_STREAM and hasattr(self, 'gstreamer_handler'):
                self.gstreamer_handler.stream_frame(frame)

            # Update resized frames for streaming
            self.video_handler.update_resized_frames(
                Parameters.STREAM_WIDTH, Parameters.STREAM_HEIGHT
            )

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
        """
        result = {"steps": [], "errors": []}
        if not self.following_active:
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
                
                # Cleanup on failure
                try:
                    if hasattr(self, 'setpoint_sender') and self.setpoint_sender:
                        self.setpoint_sender.stop()
                    await self.px4_interface.stop_offboard_mode()
                except:
                    pass  # Best effort cleanup
                    
        else:
            result["steps"].append("Follow mode already active.")
            
        return result

    async def disconnect_px4(self) -> Dict[str, any]:
        """
        Enhanced PX4 disconnection with proper cleanup of unified protocol components.
        """
        result = {"steps": [], "errors": []}
        if self.following_active:
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
        else:
            result["steps"].append("Follow mode is not active.")
            
        return result

    async def follow_target(self):
        """
        Enhanced target following with flexible tracker schema and proper async command dispatch.
        """
        if not (self.tracking_started and self.following_active):
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
                follow_result = self.follower.follow_target(tracker_output)
                if follow_result is False:
                    logging.warning("Follower follow_target returned False")
                    return False
            except Exception as e:
                logging.error(f"Error in follower.follow_target: {e}")
                return False
            
            # ASYNCHRONOUS: Send the actual commands to PX4
            try:
                control_type = self.follower.get_control_type()
                if control_type == 'attitude_rate':
                    await self.px4_interface.send_attitude_rate_commands()
                elif control_type == 'velocity_body':
                    await self.px4_interface.send_body_velocity_commands()
                elif control_type == 'velocity_body_offboard':
                    await self.px4_interface.send_velocity_body_offboard_commands()
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
            
            # Additional cleanup for new components
            try:
                # Clear follower reference
                if hasattr(self, 'follower'):
                    self.follower = None
                
                # Clear setpoint sender reference
                if hasattr(self, 'setpoint_sender'):
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
                    
            elif self.tracking_started and self.tracker:
                # Classic tracker (CSRT, etc.) is active  
                if hasattr(self.tracker, 'get_output'):
                    tracker_output = self.tracker.get_output()
                    # Log status periodically with minimal, informative output
                    if tracker_output and tracker_output.tracking_active and (time.time() % 10 < 0.1):
                        tracker_name = self.tracker.__class__.__name__.replace("Tracker", "")  # CSRT, Particle, etc.
                        conf_info = f"Conf:{tracker_output.confidence:.2f}" if tracker_output.confidence else "NoConf"
                        logging.info(f"CLASSIC TRACKER ({tracker_name}): {tracker_output.data_type.value} | {conf_info}")
                    return tracker_output
                else:
                    # Fallback for legacy trackers
                    logging.debug("Using legacy tracker compatibility mode")
                    return self._create_legacy_tracker_output()
            else:
                # No active tracking - log this only occasionally
                if time.time() % 30 < 0.1:  # Every 30 seconds
                    logging.info("NO TRACKER ACTIVE: Waiting for tracking to start")
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