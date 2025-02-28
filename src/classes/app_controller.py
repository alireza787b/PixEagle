# src/classes/app_controller.py
import asyncio
import logging
import time
import threading
import numpy as np
import cv2
from typing import Dict, Optional, Tuple

from classes.parameters import Parameters
from classes.follower import Follower
from classes.setpoint_sender import SetpointSender
from classes.video_handler import VideoHandler
from classes.trackers.tracker_factory import create_tracker
from classes.segmentor import Segmentor
from classes.px4_interface_manager import PX4InterfaceManager
from classes.telemetry_handler import TelemetryHandler
from classes.fastapi_handler import FastAPIHandler
from classes.osd_handler import OSDHandler
from classes.gstreamer_handler import GStreamerHandler
from classes.mavlink_data_manager import MavlinkDataManager
from classes.frame_preprocessor import FramePreprocessor
from classes.estimators.estimator_factory import create_estimator
from classes.detectors.detector_factory import create_detector

class AppController:
    def __init__(self):
        """
        Initializes the AppController with all necessary components.
        Sets up telemetry, tracking, segmentation, and the FastAPI handler.
        Also creates a processing thread that runs the asynchronous update loop.
        """
        logging.info("Initializing AppController...")

        # Initialize MAVLink Data Manager
        self.mavlink_data_manager = MavlinkDataManager(
            mavlink_host=Parameters.MAVLINK_HOST,
            mavlink_port=Parameters.MAVLINK_PORT,
            polling_interval=Parameters.MAVLINK_POLLING_INTERVAL,
            data_points=Parameters.MAVLINK_DATA_POINTS,
            enabled=Parameters.MAVLINK_ENABLED
        )
        if Parameters.MAVLINK_ENABLED:
            self.mavlink_data_manager.start_polling()

        # Initialize frame preprocessor if enabled
        self.preprocessor = FramePreprocessor() if Parameters.ENABLE_PREPROCESSING else None

        # Initialize the estimator
        self.estimator = create_estimator(Parameters.ESTIMATOR_TYPE)

        # Initialize VideoHandler using the new optimized design
        # (Assuming Parameters.VIDEO_SOURCE, STREAM_WIDTH and STREAM_HEIGHT are defined)
        self.video_handler = VideoHandler(
            source=Parameters.VIDEO_SOURCE,
            width=Parameters.STREAM_WIDTH,
            height=Parameters.STREAM_HEIGHT
        )

        # Initialize detector, tracker, and segmentor
        self.detector = create_detector(Parameters.DETECTION_ALGORITHM)
        self.tracker = create_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM,
                                      self.video_handler, self.detector, self)
        self.segmentor = Segmentor(algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM)

        self.tracking_failure_start_time = None
        self.frame_counter = 0
        self.tracking_started = False
        self.segmentation_active = False

        # Setup video display window and mouse callback if enabled
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.namedWindow(Parameters.FRAME_TITLE)
            cv2.setMouseCallback(Parameters.FRAME_TITLE, self.on_mouse_click)
        self.current_frame = None

        # Processed frame storage with a lock for thread safety
        self.processed_frame = None
        self.processed_frame_lock = threading.Lock()

        # Initialize PX4 interface and following-related components
        self.px4_interface = PX4InterfaceManager(app_controller=self)
        self.following_active = False
        self.follower = None
        self.setpoint_sender = None

        # Initialize telemetry handler
        self.telemetry_handler = TelemetryHandler(self, lambda: self.tracking_started)

        # Initialize FastAPI handler (for HTTP streaming/control)
        self.api_handler = FastAPIHandler(self)

        # Initialize On-Screen Display handler
        self.osd_handler = OSDHandler(self)

        # Initialize GStreamer handler for streaming if enabled
        if Parameters.ENABLE_GSTREAMER_STREAM:
            self.gstreamer_handler = GStreamerHandler()
            self.gstreamer_handler.initialize_stream()
        else:
            self.gstreamer_handler = None

        # Thread control flags and processing thread handle
        self.running = False
        self.processing_thread = None

        logging.info("AppController initialized.")

    def start(self):
        """
        Starts the AppController by launching the VideoHandler and beginning the processing thread.
        """
        logging.info("Starting AppController...")
        # Start video capture (this will run in its own thread inside VideoHandler)
        self.video_handler.start()
        # Start processing loop in a dedicated thread
        self.running = True
        self.processing_thread = threading.Thread(target=self._processing_loop,
                                                  name="ProcessingThread", daemon=True)
        self.processing_thread.start()
        logging.info("Processing thread started.")

    def _processing_loop(self):
        """
        Dedicated processing loop running in its own thread.
        Creates an asyncio event loop to run the asynchronous update_loop,
        continuously processing frames from the VideoHandler.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while self.running:
            frame = self.video_handler.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue
            try:
                # Process the frame asynchronously
                processed = loop.run_until_complete(self.update_loop(frame))
                with self.processed_frame_lock:
                    self.current_frame = processed
                    self.processed_frame = processed
            except Exception as e:
                logging.error(f"Error in processing loop: {e}", exc_info=True)
            # Small sleep to yield CPU
            time.sleep(0.001)
        loop.close()

    def stop(self):
        """
        Stops the AppController by terminating the processing loop,
        releasing video resources, and stopping other components.
        """
        logging.info("Stopping AppController...")
        self.running = False
        if self.processing_thread is not None:
            self.processing_thread.join(timeout=5)
        if Parameters.MAVLINK_ENABLED:
            self.mavlink_data_manager.stop_polling()
        self.video_handler.release()
        logging.info("AppController stopped.")

    def get_processed_frame(self):
        """
        Returns the latest processed frame in a thread-safe manner.
        """
        with self.processed_frame_lock:
            return self.processed_frame.copy() if self.processed_frame is not None else None

    async def update_loop(self, frame: np.ndarray) -> np.ndarray:
        """
        Asynchronously processes a single video frame.
        Performs preprocessing, segmentation, tracking, telemetry, and OSD drawing.
        
        Args:
            frame (np.ndarray): The raw video frame.
        
        Returns:
            np.ndarray: The processed frame.
        """
        try:
            # Preprocessing and segmentation if enabled
            if Parameters.ENABLE_VIDEO_PROCESSING:
                if self.preprocessor:
                    frame = self.preprocessor.preprocess(frame)
                if self.segmentation_active:
                    frame = self.segmentor.segment_frame(frame)
            else:
                logging.debug("Video processing disabled; skipping preprocessing and segmentation.")

            # Tracking and estimation logic
            if self.tracking_started:
                if self.tracking_failure_start_time is None:
                    success, _ = self.tracker.update(frame)
                else:
                    success = False
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
                    if self.tracker.__class__.__name__ != "ExternalTracker" and Parameters.ENABLE_VIDEO_PROCESSING:
                        tracker_confidence = self.tracker.get_confidence()
                        if (tracker_confidence >= Parameters.TRACKER_CONFIDENCE_THRESHOLD_FOR_TEMPLATE_UPDATE and
                            self.frame_counter % Parameters.TEMPLATE_UPDATE_INTERVAL == 0):
                            bbox = self.tracker.bbox
                            if bbox:
                                self.detector.update_template(frame, bbox)
                                logging.debug("Template updated during tracking.")
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
                            self.tracking_failure_start_time = None
                        else:
                            logging.warning(f"Tracking lost. Attempting to recover. Elapsed time: {elapsed_time:.2f} seconds.")
                            self.tracker.update_estimator_without_measurement()
                            frame = self.tracker.draw_estimate(frame, tracking_successful=False)
                            if self.following_active:
                                await self.follow_target()
                                await self.check_failsafe()
                            if self.tracker.__class__.__name__ != "ExternalTracker":
                                redetect_result = self.handle_tracking_failure()
                                if redetect_result:
                                    self.tracking_failure_start_time = None

            # Telemetry handling
            if self.telemetry_handler.should_send_telemetry():
                self.telemetry_handler.send_telemetry()

            self.current_frame = frame
            # Store the processed frame for OSD and streaming
            self.video_handler.current_osd_frame = frame

            # Draw OSD elements on the frame
            frame = self.osd_handler.draw_osd(frame)

            # Stream frame via GStreamer if enabled
            if Parameters.ENABLE_GSTREAMER_STREAM and self.gstreamer_handler:
                self.gstreamer_handler.stream_frame(frame)

            # Update resized frames for display/streaming
            self.video_handler.update_resized_frames(Parameters.STREAM_WIDTH, Parameters.STREAM_HEIGHT)
        except Exception as e:
            logging.exception(f"Error in update_loop: {e}")
        return frame

    async def handle_key_input_async(self, key: int, frame: np.ndarray):
        """
        Asynchronously handles key inputs for toggling segmentation, tracking, and PX4 control.
        """
        if key == ord('y'):
            self.toggle_segmentation()
        elif key == ord('t'):
            self.toggle_tracking(frame)
        elif key == ord('d'):
            self.initiate_redetection()
        elif key == ord('f'):
            await self.connect_px4()
        elif key == ord('x'):
            await self.disconnect_px4()
        elif key == ord('c'):
            self.cancel_activities()

    def on_mouse_click(self, event: int, x: int, y: int, flags: int, param: any):
        """
        Mouse callback for video window; used to initiate segmentation if active.
        """
        if event == cv2.EVENT_LBUTTONDOWN and self.segmentation_active:
            self.handle_user_click(x, y)

    def toggle_tracking(self, frame: np.ndarray):
        """
        Toggles tracking on/off. Initiates ROI selection if tracking is not active (unless in external tracker mode).
        """
        if not self.tracking_started:
            if hasattr(self.tracker, '__class__') and self.tracker.__class__.__name__ == "ExternalTracker":
                logging.info("External tracker mode active. Awaiting external bounding box update...")
            else:
                bbox = cv2.selectROI(Parameters.FRAME_TITLE, frame, False, False)
                if bbox and bbox[2] > 0 and bbox[3] > 0:
                    self.tracker.start_tracking(frame, bbox)
                    self.tracking_started = True
                    self.frame_counter = 0
                    if self.detector:
                        self.detector.extract_features(frame, bbox)
                        logging.debug("Detector's initial features and template set.")
                    logging.info("Tracking activated.")
                else:
                    logging.info("Tracking canceled or invalid ROI.")
        else:
            self.cancel_activities()
            logging.info("Tracking deactivated.")

    def toggle_segmentation(self) -> bool:
        """
        Toggles segmentation mode on/off.
        """
        self.segmentation_active = not self.segmentation_active
        logging.info(f"Segmentation {'activated' if self.segmentation_active else 'deactivated'}.")
        return self.segmentation_active

    def cancel_activities(self):
        """
        Cancels tracking and segmentation activities.
        """
        self.tracking_started = False
        self.segmentation_active = False
        if self.setpoint_sender:
            self.setpoint_sender.stop()
            self.setpoint_sender.join()
            self.setpoint_sender = None
        logging.info("All activities cancelled.")

    def handle_tracking_failure(self):
        """
        Attempts re-detection when tracking is lost.
        """
        if Parameters.USE_DETECTOR and Parameters.AUTO_REDETECT:
            logging.info("Attempting to re-detect the target using the detector.")
            redetect_result = self.initiate_redetection()
            if redetect_result["success"]:
                logging.info("Target re-detected and tracker re-initialized.")
            else:
                logging.info("Re-detection attempt failed. Retrying...")
            return redetect_result
        return {"success": False, "message": "Detector not enabled or auto-redetect off."}

    def initiate_redetection(self) -> dict:
        """
        Attempts to re-detect the target using the detector.
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
                redetect_result = self.detector.smart_redetection(self.current_frame, self.tracker, roi=search_region)
            else:
                redetect_result = self.detector.smart_redetection(self.current_frame, self.tracker)
            if redetect_result:
                detected_bbox = self.detector.get_latest_bbox()
                self.tracker.reinitialize_tracker(self.current_frame, detected_bbox)
                self.tracking_started = True
                logging.info("Re-detection successful and tracker re-initialized.")
                return {"success": True, "message": "Re-detection successful and tracker re-initialized.", "bounding_box": detected_bbox}
            else:
                logging.info("Re-detection failed or no new object found.")
                return {"success": False, "message": "Re-detection failed or no new object found."}
        else:
            return {"success": False, "message": "Detector is not enabled."}

    def show_current_frame(self, frame_title: str = Parameters.FRAME_TITLE) -> np.ndarray:
        """
        Displays the current frame in a window if enabled.
        """
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.imshow(frame_title, self.current_frame)
        return self.current_frame

    async def connect_px4(self) -> dict:
        """
        Connects to PX4 when follow mode is activated.
        """
        result = {"steps": [], "errors": []}
        if not self.following_active:
            try:
                logging.debug("Activating Follow Mode to PX4!")
                await self.px4_interface.connect()
                logging.debug("Connected to PX4 Drone!")
                initial_target_coords = (
                    tuple(self.tracker.normalized_center)
                    if Parameters.TARGET_POSITION_MODE == 'initial'
                    else tuple(Parameters.DESIRE_AIM)
                )
                self.follower = Follower(self.px4_interface, initial_target_coords)
                self.telemetry_handler.follower = self.follower
                await self.px4_interface.set_hover_throttle()
                await self.px4_interface.send_initial_setpoint()
                await self.px4_interface.start_offboard_mode()
                self.following_active = True
                result["steps"].append("Offboard mode started.")
            except Exception as e:
                logging.error(f"Failed to connect/start offboard mode: {e}")
                result["errors"].append(f"Failed to connect/start offboard mode: {e}")
        else:
            result["steps"].append("Follow mode already active.")
        return result

    async def disconnect_px4(self) -> dict:
        """
        Disconnects PX4 and stops offboard mode.
        """
        result = {"steps": [], "errors": []}
        if self.following_active:
            try:
                await self.px4_interface.stop_offboard_mode()
                result["steps"].append("Offboard mode stopped.")
                self.following_active = False
                if self.setpoint_sender:
                    self.setpoint_sender.stop()
                    self.setpoint_sender.join()
                    self.setpoint_sender = None
            except Exception as e:
                logging.error(f"Failed to stop offboard mode: {e}")
                result["errors"].append(f"Failed to stop offboard mode: {e}")
        else:
            result["steps"].append("Follow mode is not active.")
        return result

    async def follow_target(self):
        """
        Follows the target based on tracking information.
        """
        if self.tracking_started and self.following_active:
            target_coords: Optional[Tuple[float, float]] = None
            if Parameters.USE_ESTIMATOR_FOR_FOLLOWING and self.tracker.position_estimator:
                frame_width, frame_height = self.video_handler.width, self.video_handler.height
                normalized_estimate = self.tracker.position_estimator.get_normalized_estimate(frame_width, frame_height)
                if normalized_estimate:
                    target_coords = normalized_estimate
                    logging.debug(f"Using estimated normalized coords: {target_coords}")
                else:
                    logging.warning("Estimator failed to provide a normalized estimate.")
            if not target_coords:
                target_coords = self.tracker.normalized_center
                logging.debug(f"Using tracker's normalized center: {target_coords}")
            if target_coords:
                self.follower.follow_target(target_coords)
                self.px4_interface.update_setpoint()
                control_type = self.follower.get_control_type()
                if control_type == 'attitude_rate':
                    await self.px4_interface.send_attitude_rate_commands()
                elif control_type == 'velocity_body':
                    await self.px4_interface.send_body_velocity_commands()
                else:
                    logging.warning(f"Unknown control type: {control_type}")
            else:
                logging.warning("No target coordinates available to follow.")
            return True
        else:
            return False

    async def shutdown(self) -> dict:
        """
        Gracefully shuts down the application.
        """
        result = {"steps": [], "errors": []}
        try:
            if Parameters.MAVLINK_ENABLED:
                self.mavlink_data_manager.stop_polling()
            if self.following_active:
                logging.debug("Stopping offboard mode and disconnecting PX4.")
                await self.px4_interface.stop_offboard_mode()
                if self.setpoint_sender:
                    self.setpoint_sender.stop()
                    self.setpoint_sender.join()
                self.following_active = False
            self.video_handler.release()
            logging.debug("Video handler released.")
            result["steps"].append("Shutdown complete.")
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")
            result["errors"].append(f"Error during shutdown: {e}")
        return result
