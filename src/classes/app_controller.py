# src/app_controller.py

import asyncio
import logging
import numpy as np
from classes.parameters import Parameters
from classes.follower import Follower
from classes.setpoint_sender import SetpointSender
from classes.video_handler import VideoHandler
from classes.trackers.base_tracker import BaseTracker
from classes.trackers.csrt_tracker import CSRTTracker  # Import other trackers as necessary
from classes.segmentor import Segmentor
from classes.trackers.tracker_factory import create_tracker
from classes.detector import Detector
import cv2
from classes.px4_controller import PX4Controller  # Ensure this import path is correct
from classes.telemetry_handler import TelemetryHandler
from classes.fastapi_handler import FastAPIHandler  # Correct import

class AppController:
    def __init__(self):
        """
        Initializes the AppController with necessary components and starts the FastAPI handler.
        """
        # Initialize video processing components
        self.video_handler = VideoHandler()
        self.video_streamer = None
        self.detector = Detector(algorithm_type=Parameters.DETECTION_ALGORITHM)
        self.tracker = create_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM, self.video_handler, self.detector)
        self.segmentor = Segmentor(algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM)

        # Flags to track the state of tracking and segmentation
        self.tracking_started = False
        self.segmentation_active = False

        # Setup a named window and a mouse callback for interactions
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.namedWindow("Video")
            cv2.setMouseCallback("Video", self.on_mouse_click)
        self.current_frame = None

        # Initialize PX4 controller and following mode flag
        self.px4_controller = PX4Controller()
        self.following_active = False
        self.follower = None
        self.setpoint_sender = None

        # Initialize telemetry handler
        self.telemetry_handler = TelemetryHandler(self)

        # Initialize the FastAPI handler
        self.api_handler = FastAPIHandler(self.video_handler, self.telemetry_handler, self)
        self.api_handler.start(host=Parameters.HTTP_STREAM_HOST, port=Parameters.HTTP_STREAM_PORT)

        logging.info("AppController initialized.")

    def on_mouse_click(self, event, x, y, flags, param):
        """
        Handles mouse click events in the video window, specifically for initiating segmentation.
        """
        if event == cv2.EVENT_LBUTTONDOWN and self.segmentation_active:
            self.handle_user_click(x, y)

    def toggle_tracking(self, frame):
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
                print("Tracking activated.")
            else:
                print("Tracking canceled or invalid ROI.")
        else:
            self.cancel_activities()
            print("Tracking deactivated.")

    def toggle_segmentation(self):
        """
        Toggles the segmentation state. Activates or deactivates segmentation.

        Returns:
            bool: The current state of segmentation after toggling.
        """
        self.segmentation_active = not self.segmentation_active
        if self.segmentation_active:
            print("Segmentation activated.")
        else:
            print("Segmentation deactivated.")
        return self.segmentation_active

    async def start_tracking(self, bbox):
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
            print("Tracking activated.")
        else:
            print("Tracking is already active.")

    async def stop_tracking(self):
        """
        Stops the tracking process if it is currently active.
        """
        if self.tracking_started:
            self.cancel_activities()
            print("Tracking deactivated.")
        else:
            print("Tracking is not active.")

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
        print("All activities cancelled.")

    async def update_loop(self, frame):
        """
        The main update loop for processing each video frame.

        Args:
            frame (np.ndarray): The current video frame.

        Returns:
            np.ndarray: The processed video frame.
        """
        if self.segmentation_active:
            frame = self.segmentor.segment_frame(frame)
        
        if self.tracking_started:
            success, _ = self.tracker.update(frame)
            if success:
                frame = self.tracker.draw_tracking(frame)
                if Parameters.ENABLE_DEBUGGING:
                    self.tracker.print_normalized_center()
                if Parameters.USE_ESTIMATOR:
                    frame = self.tracker.draw_estimate(frame)
                if self.following_active:
                    await self.follow_target()
            else:
                if Parameters.USE_DETECTOR and Parameters.AUTO_REDETECT:
                    self.initiate_redetection()
                    
        if self.telemetry_handler.should_send_telemetry():
            self.telemetry_handler.send_telemetry()
                    
        if Parameters.USE_DETECTOR:
            pass

        self.current_frame = frame
        self.video_handler.current_osd_frame = frame

        return frame

    async def handle_key_input_async(self, key, frame):
        """
        Handles key inputs for toggling segmentation, toggling tracking, starting feature extraction, and cancelling activities.

        Args:
            key (int): The key pressed.
            frame (np.ndarray): The current video frame.
        """
        if key == ord('y'):
            self.toggle_segmentation()
        elif key == ord('t'):
            self.toggle_tracking(frame)
        elif key == ord('d'):
            self.initiate_redetection()
        elif key == ord('f'):
            if Parameters.DIRECT_PX4_MAVSDK:        
                await self.connect_px4()
        elif key == ord('x'):
            if Parameters.DIRECT_PX4_MAVSDK:        
                await self.disconnect_px4()
        elif key == ord('c'):
            self.cancel_activities()

    def handle_key_input(self, key, frame):
        """
        Handles key inputs synchronously by creating an async task.

        Args:
            key (int): The key pressed.
            frame (np.ndarray): The current video frame.
        """
        asyncio.create_task(self.handle_key_input_async(key, frame))

    def handle_user_click(self, x, y):
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
            print(f"Object selected for tracking: {selected_bbox}")

    def identify_clicked_object(self, detections, x, y):
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

    def initiate_redetection(self):
        """
        Attempts to redetect the object being tracked.

        Returns:
            dict: Details of the redetection attempt.
        """
        if Parameters.USE_DETECTOR:
            redetect_result = self.detector.smart_redetection(self.current_frame, self.tracker)
            if self.detector.get_latest_bbox() is not None and redetect_result:
                self.tracker.reinitialize_tracker(self.current_frame, self.detector.get_latest_bbox())
                return {
                    "success": True,
                    "message": "Re-detection activated and tracking updated.",
                    "bounding_box": self.detector.get_latest_bbox()
                }
            else:
                return {
                    "success": False,
                    "message": "Re-detection failed or no new object found."
                }
        else:
            return {
                "success": False,
                "message": "Detector is not enabled."
            }

    def show_current_frame(self, frame_title=Parameters.FRAME_TITLE):
        """
        Displays the current frame in a window if SHOW_VIDEO_WINDOW is True.

        Args:
            frame_title (str): The title of the frame window.
        """
        if Parameters.SHOW_VIDEO_WINDOW:
            cv2.imshow(frame_title, self.current_frame)
        return self.current_frame

    async def connect_px4(self):
        """
        Connects to PX4 when following mode is activated.

        Returns:
            dict: Details of the connection and offboard mode process.
        """
        result = {"steps": [], "errors": []}
        if not self.following_active:
            try:
                if Parameters.ENABLE_DEBUGGING:
                    result["steps"].append("Activating Follow Mode to PX4!")
                await self.px4_controller.connect()
                if Parameters.ENABLE_DEBUGGING:
                    result["steps"].append("Connected to PX4 Drone!")
                
                initial_target_coords = self.tracker.normalized_center if Parameters.TARGET_POSITION_MODE == 'initial' else Parameters.DESIRE_AIM
                self.follower = Follower(self.px4_controller, initial_target_coords)
                await self.px4_controller.send_initial_setpoint()
                await self.px4_controller.start_offboard_mode()
                self.following_active = True
                result["steps"].append("Offboard mode started.")
            except Exception as e:
                print(e)
                result["errors"].append(f"Failed to connect/start offboard mode: {e}")
        else:
            result["steps"].append("Follow mode already active.")
        
        return result

    async def disconnect_px4(self):
        """
        Disconnects PX4 and stops offboard mode.

        Returns:
            dict: Details of the disconnect process.
        """
        result = {"steps": [], "errors": []}
        if self.following_active:
            try:
                await self.px4_controller.stop_offboard_mode()
                result["steps"].append("Offboard mode stopped.")
                if self.setpoint_sender:
                    self.setpoint_sender.stop()
                    self.setpoint_sender.join()
                    self.setpoint_sender = None
                self.following_active = False
            except Exception as e:
                result["errors"].append(f"Failed to stop offboard mode: {e}")
        else:
            result["steps"].append("Follow mode is not active.")
        
        return result

    async def follow_target(self):
        """
        Prepares to follow the target based on tracking information.
        """
        if self.tracking_started and self.following_active:
            target_coords = self.tracker.normalized_center
            setpoint = await self.follower.follow_target(target_coords)
            self.px4_controller.update_setpoint(setpoint)
            await self.px4_controller.send_body_velocity_commands(self.px4_controller.last_command)

    async def shutdown(self):
        """
        Shuts down the application gracefully.

        Returns:
            dict: Details of the shutdown process.
        """
        result = {"steps": [], "errors": []}
        try:
            if self.following_active:
                result["steps"].append("Stopping offboard mode and disconnecting PX4.")
                await self.px4_controller.stop_offboard_mode()
                if self.setpoint_sender:
                    self.setpoint_sender.stop()
                    self.setpoint_sender.join()
                self.following_active = False
            self.video_handler.release()
            result["steps"].append("Video handler released.")
        except Exception as e:
            result["errors"].append(f"Error during shutdown: {e}")
        return result
