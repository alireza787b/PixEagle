#src/classes/app_controller.py
import asyncio
import logging
import time
import numpy as np
from classes.parameters import Parameters
from classes.follower import Follower
from classes.setpoint_sender import SetpointSender
from classes.video_handler import VideoHandler
from classes.trackers.csrt_tracker import CSRTTracker  # Import other trackers as necessary
from classes.segmentor import Segmentor
from classes.trackers.tracker_factory import create_tracker
from classes.detector import Detector
import cv2
from classes.px4_interface_manager import PX4InterfaceManager  # Updated import path
from classes.telemetry_handler import TelemetryHandler
from classes.fastapi_handler import FastAPIHandler  # Correct import
from typing import Dict, Tuple
from classes.osd_handler import OSDHandler
from classes.gstreamer_handler import GStreamerHandler
from classes.mavlink_data_manager import MavlinkDataManager
from classes.frame_preprocessor import FramePreprocessor
from classes.estimators.estimator_factory import create_estimator



class AppController:
    def __init__(self):
        """
        Initializes the AppController with necessary components and starts the FastAPI handler.
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
        
        # Initialize the FramePreprocessor if enabled
        if Parameters.ENABLE_PREPROCESSING:
            self.preprocessor = FramePreprocessor()
        else:
            self.preprocessor = None
        
        # Start polling MAVLink data if enabled
        if Parameters.MAVLINK_ENABLED:
            self.mavlink_data_manager.start_polling()

        # Initialize video processing components
        self.video_handler = VideoHandler()
        self.video_streamer = None
        self.detector = Detector(algorithm_type=Parameters.DETECTION_ALGORITHM)
        self.tracker = create_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM, self.video_handler, self.detector, self)
        self.segmentor = Segmentor(algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM)
        
        self.tracking_failure_start_time = None  # Initialize tracking failure timer


        # Flags to track the state of tracking and segmentation
        self.tracking_started = False
        self.segmentation_active = False

        # Setup a named window and a mouse callback for interactions
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.namedWindow("Video")
            cv2.setMouseCallback("Video", self.on_mouse_click)
        self.current_frame = None

        # Initialize PX4 interface manager and following mode flag
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

        # Initialize the OSD handler with access to the AppController
        self.osd_handler = OSDHandler(self)
        
        # Initialize GStreamerHandler if streaming is enabled
        if Parameters.ENABLE_GSTREAMER_STREAM:
            self.gstreamer_handler = GStreamerHandler()
            self.gstreamer_handler.initialize_stream()


        logging.info("AppController initialized.")

    def on_mouse_click(self, event: int, x: int, y: int, flags: int, param: any):
        """
        Handles mouse click events in the video window, specifically for initiating segmentation.
        """
        if event == cv2.EVENT_LBUTTONDOWN and self.segmentation_active:
            self.handle_user_click(x, y)

    def toggle_tracking(self, frame: np.ndarray):
        """
        Toggles the tracking state, starts or stops tracking based on the current state.

        Args:
            frame (np.ndarray): The current video frame.
        """
        if not self.tracking_started:
            bbox = cv2.selectROI(Parameters.FRAME_TITLE, frame, False, False)
            if bbox and bbox[2] > 0 and bbox[3] > 0:
                self.tracker.start_tracking(frame, bbox)
                self.tracking_started = True
                if hasattr(self.tracker, 'detector') and self.tracker.detector:
                    self.tracker.detector.extract_features(frame, bbox)
                logging.info("Tracking activated.")
            else:
                logging.info("Tracking canceled or invalid ROI.")
        else:
            self.cancel_activities()
            logging.info("Tracking deactivated.")

    def toggle_segmentation(self) -> bool:
        """
        Toggles the segmentation state. Activates or deactivates segmentation.

        Returns:
            bool: The current state of segmentation after toggling.
        """
        self.segmentation_active = not self.segmentation_active
        logging.info(f"Segmentation {'activated' if self.segmentation_active else 'deactivated'}.")
        return self.segmentation_active

    async def start_tracking(self, bbox: Dict[str, int]):
        """
        Starts tracking with the provided bounding box.

        Args:
            bbox (dict): The bounding box for tracking.
        """
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
        Stops the tracking process if it is currently active.
        """
        if self.tracking_started:
            self.cancel_activities()
            logging.info("Tracking deactivated.")
        else:
            logging.info("Tracking is not active.")

    def cancel_activities(self):
        """
        Cancels both tracking and segmentation activities, resetting their states.
        """
        self.tracking_started = False
        self.segmentation_active = False
        if self.setpoint_sender:
            self.setpoint_sender.stop()
            self.setpoint_sender.join()
            self.setpoint_sender = None
        logging.info("All activities cancelled.")

    async def update_loop(self, frame: np.ndarray) -> np.ndarray:
        """
        The main update loop for processing each video frame.

        Args:
            frame (np.ndarray): The current video frame.

        Returns:
            np.ndarray: The processed video frame.
        """
        try:
            # Preprocessing step
            if Parameters.ENABLE_PREPROCESSING and self.preprocessor:
                frame = self.preprocessor.preprocess(frame)
            
            # Segmentation step
            if self.segmentation_active:
                frame = self.segmentor.segment_frame(frame)
            
            # Tracking and estimation
            if self.tracking_started:
                success, _ = self.tracker.update(frame)
                if success:
                    # Reset tracking failure timer
                    self.tracking_failure_start_time = None
                    frame = self.tracker.draw_tracking(frame, tracking_successful=True)
                    if Parameters.ENABLE_DEBUGGING:
                        self.tracker.print_normalized_center()
                    if self.tracker.position_estimator:
                        frame = self.tracker.draw_estimate(frame, tracking_successful=True)
                    if self.following_active:
                        await self.follow_target()
                        await self.check_failsafe()
                else:
                    if self.tracking_failure_start_time is None:
                        # First failure, start timer
                        self.tracking_failure_start_time = time.time()
                        logging.warning("Tracking lost. Starting failure timer.")
                    else:
                        elapsed_time = time.time() - self.tracking_failure_start_time
                        if elapsed_time > Parameters.TRACKING_FAILURE_TIMEOUT:
                            logging.error("Tracking lost for too long. Handling failure.")
                            self.tracking_started = False
                            await self.handle_tracking_failure()
                        else:
                            # Continue updating estimator and control logic
                            logging.warning(f"Tracking lost. Attempting to recover. Elapsed time: {elapsed_time:.2f} seconds.")
                            # Update estimator without measurement
                            self.tracker.update_estimator_without_measurement()
                            # Draw estimation-only visuals
                            frame = self.tracker.draw_estimate(frame, tracking_successful=False)
                            if self.following_active:
                                await self.follow_target()
                                await self.check_failsafe()
            else:
                # Tracking not active; continue processing frames
                pass
            
            # Telemetry handling
            if self.telemetry_handler.should_send_telemetry():
                self.telemetry_handler.send_telemetry()

            # Update current frame and OSD
            self.current_frame = frame
            self.video_handler.current_osd_frame = frame

            # Draw OSD elements on the frame
            frame = self.osd_handler.draw_osd(frame)

            # Stream the processed frame if GStreamer is enabled
            if Parameters.ENABLE_GSTREAMER_STREAM and self.gstreamer_handler:
                self.gstreamer_handler.stream_frame(frame)
        except Exception as e:
            logging.exception(f"Error in update_loop: {e}")
        return frame


    
    async def handle_tracking_failure(self):
        """
        Handles tracking failure by attempting re-detection using the existing detector.
        """
        if Parameters.USE_DETECTOR and Parameters.AUTO_REDETECT:
            logging.info("Attempting to re-detect the target using the detector.")
            detection_success = False
            for attempt in range(Parameters.REDETECTION_ATTEMPTS):
                redetect_result = self.initiate_redetection()
                if redetect_result["success"]:
                    logging.info("Target re-detected and tracker re-initialized.")
                    detection_success = True
                    break
                else:
                    logging.info(f"Re-detection attempt {attempt + 1} failed. Retrying...")
                #await asyncio.sleep(Parameters.REDETECTION_INTERVAL)
            if not detection_success:
                logging.error("Failed to re-detect the target after multiple attempts.")
                await self.handle_failsafe()
        else:
            logging.error("Detector not enabled or AUTO_REDETECT is False. Initiating failsafe.")
            await self.handle_failsafe()
            self.following_active = False #double check later why I need manually do this
    
    
    async def check_failsafe(self):
        if self.px4_interface.failsafe_active :
            # await self.px4_interface.trigger_failsafe()
            await self.handle_failsafe()
            self.px4_interface.failsafe_active = False

    async def handle_failsafe(self):
        #for now only disconnect px4 so attemp default px4 behaviour (possibly hold  fligt mode)
        await self.disconnect_px4()

    async def handle_key_input_async(self, key: int, frame: np.ndarray):
        """
        Handles key inputs for toggling segmentation, toggling tracking, starting feature extraction, and cancelling activities.

        Args:
            key (int): The key pressed.
            frame (np.ndarray): The current video frame.
        """
        # logging.debug(f"Handling key input: {key}")
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

    def handle_key_input(self, key: int, frame: np.ndarray):
        """
        Handles key inputs synchronously by creating an async task.

        Args:
            key (int): The key pressed.
            frame (np.ndarray): The current video frame.
        """
        asyncio.create_task(self.handle_key_input_async(key, frame))

    def handle_user_click(self, x: int, y: int):
        """
        Identifies the object clicked by the user for tracking within the segmented area.

        Args:
            x (int): X coordinate of the click.
            y (int): Y coordinate of the click.
        """
        if not self.segmentation_active:
            return

        detections = self.segmentor.get_last_detections()
        selected_bbox = self.identify_clicked_object(detections, x, y)
        if selected_bbox:
            selected_bbox = tuple(map(lambda x: int(round(x)), selected_bbox))
            self.tracker.reinitialize_tracker(self.current_frame, selected_bbox)
            self.tracking_started = True
            logging.info(f"Object selected for tracking: {selected_bbox}")

    def identify_clicked_object(self, detections: list, x: int, y: int) -> Tuple[int, int, int, int]:
        """
        Identifies the clicked object based on segmentation detections and mouse click coordinates.

        Args:
            detections (list): List of detected objects.
            x (int): X coordinate of the click.
            y (int): Y coordinate of the click.

        Returns:
            tuple: The bounding box of the clicked object.
        """
        for det in detections:
            x1, y1, x2, y2 = det
            if x1 <= x <= x2 and y1 <= y <= y2:
                return det
        return None

    def initiate_redetection(self) -> Dict[str, any]:
        """
        Attempts to re-detect the object being tracked using the existing detector,
        focusing around the estimated position if available.
        """
        if Parameters.USE_DETECTOR:
            # Get estimated position
            estimate = self.tracker.get_estimated_position()
            if estimate:
                estimated_x, estimated_y = estimate[:2]
                # Define a region around the estimated position
                search_radius = Parameters.REDETECTION_SEARCH_RADIUS
                x_min = max(0, int(estimated_x - search_radius))
                x_max = min(self.video_handler.width, int(estimated_x + search_radius))
                y_min = max(0, int(estimated_y - search_radius))
                y_max = min(self.video_handler.height, int(estimated_y + search_radius))
                search_region = (x_min, y_min, x_max - x_min, y_max - y_min)
                # Run detection on the search region
                redetect_result = self.detector.smart_redetection(self.current_frame, self.tracker, roi=search_region)
            else:
                # No estimated position, use full frame
                redetect_result = self.detector.smart_redetection(self.current_frame, self.tracker)

            if redetect_result:
                # The latest_bbox from the detector is already adjusted to original frame coordinates
                detected_bbox = self.detector.get_latest_bbox()
                # Perform appearance validation
                current_features = self.tracker.extract_features(self.current_frame, detected_bbox)
                similarity = cv2.compareHist(self.tracker.initial_features, current_features, cv2.HISTCMP_CORREL)
                if similarity >= Parameters.APPEARANCE_THRESHOLD:
                    self.tracker.reinitialize_tracker(self.current_frame, detected_bbox)
                    self.tracking_started = True
                    logging.info("Re-detection successful and tracker re-initialized.")
                    return {
                        "success": True,
                        "message": "Re-detection successful and tracker re-initialized.",
                        "bounding_box": detected_bbox
                    }
                else:
                    logging.warning("Re-detected object does not match initial appearance.")
                    return {
                        "success": False,
                        "message": "Re-detected object does not match initial appearance."
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
        Displays the current frame in a window if SHOW_VIDEO_WINDOW is True.

        Args:
            frame_title (str): The title of the frame window.
        """
        #logging.debug(f"Showing current frame: {frame_title}")
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.imshow(frame_title, self.current_frame)
        return self.current_frame

    async def connect_px4(self) -> Dict[str, any]:
        """
        Connects to PX4 when following mode is activated.

        Returns:
            dict: Details of the connection and offboard mode process.
        """
        result = {"steps": [], "errors": []}
        if not self.following_active:
            try:
                logging.debug("Activating Follow Mode to PX4!")
                await self.px4_interface.connect()
                logging.debug("Connected to PX4 Drone!")
                
                initial_target_coords = (
                    tuple(self.tracker.normalized_center) if Parameters.TARGET_POSITION_MODE == 'initial' else tuple(Parameters.DESIRE_AIM)
                )
                self.follower = Follower(self.px4_interface, initial_target_coords)
                self.telemetry_handler.follower = self.follower  # Maybe do a better approach later.
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



    async def disconnect_px4(self) -> Dict[str, any]:
        """
        Disconnects PX4 and stops offboard mode.

        Returns:
            dict: Details of the disconnect process.
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
        Prepares to follow the target based on tracking information.
        """
        if self.tracking_started and self.following_active:
            estimate = self.tracker.get_estimated_position()
            if estimate:
                estimated_x, estimated_y = estimate[:2]
                frame_width, frame_height = self.video_handler.width, self.video_handler.height
                norm_x = estimated_x / frame_width
                norm_y = estimated_y / frame_height
                target_coords = (norm_x, norm_y)
                logging.debug(f"target coordinate estimated: {target_coords}")
            else:
                target_coords = self.tracker.normalized_center  # Fallback to tracker center

            self.follower.follow_target(target_coords)
            self.px4_interface.update_setpoint()

            # Determine the control type and send the appropriate commands
            control_type = self.follower.get_control_type()
            if control_type == 'attitude_rate':
                await self.px4_interface.send_attitude_rate_commands()
            elif control_type == 'velocity_body':
                await self.px4_interface.send_body_velocity_commands()

            return True
        else:
            return False


    async def shutdown(self) -> Dict[str, any]:
        """
        Shuts down the application gracefully.

        Returns:
            dict: Details of the shutdown process.
        """
        result = {"steps": [], "errors": []}
        try:
            # Stop MAVLink polling
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
    
    
        
