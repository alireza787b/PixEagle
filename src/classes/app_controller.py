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
        cv2.namedWindow("Video")
        cv2.setMouseCallback("Video", self.on_mouse_click)
        self.current_frame = None
        self.px4_controller = PX4Controller()
        self.following_active = False  # Flag to indicate if following mode is active
        self.follower = None
        self.setpoint_sender = None
        # Initialize telemetry handler
        self.telemetry_handler = TelemetryHandler(self)
        # Initialize the FastAPIHandler instead of FlaskHandler
        self.api_handler = FastAPIHandler(self.video_handler, self.telemetry_handler)
        self.api_handler.start(host=Parameters.HTTP_STREAM_HOST, port=Parameters.HTTP_STREAM_PORT)

        logging.info("AppController initialized.")

    def on_mouse_click(self, event, x, y, flags, param):
        """
        Handles mouse click events in the video window, specifically for initiating segmentation.
        """
        if event == cv2.EVENT_LBUTTONDOWN and self.segmentation_active:
            self.handle_user_click(x, y)

    def toggle_tracking(self, frame):
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
        """
        self.segmentation_active = not self.segmentation_active
        if self.segmentation_active:
            print("Segmentation activated.")
        else:
            print("Segmentation deactivated.")

    def cancel_activities(self):
        """
        Cancels both tracking and segmentation activities, resetting their states.
        """
        self.tracking_started = False
        self.segmentation_active = False
        if self.setpoint_sender is not None:  # Check if setpoint_sender has been initialized
            self.setpoint_sender.stop()
            self.setpoint_sender.join()
            self.setpoint_sender = None  # Optionally reset setpoint_sender to None after stopping
        print("All activities cancelled.")

    async def update_loop(self, frame):
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
                    self.initiate_redetection(frame, self.tracker)
                    
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
        """
        if key == ord('y'):
            self.toggle_segmentation()
        elif key == ord('t'):
            self.toggle_tracking(frame)
        elif key == ord('d'):
            self.initiate_redetection(frame)
        elif key == ord('f'):
            # Start following mode
            if Parameters.DIRECT_PX4_MAVSDK:        
                await self.connect_px4()
        elif key == ord('x'):
            # Stop following mode and disconnect from Drone
            if Parameters.DIRECT_PX4_MAVSDK:        
                await self.disconnect_px4()
        elif key == ord('c'):
            self.cancel_activities()

    def handle_key_input(self, key, frame):
        asyncio.create_task(self.handle_key_input_async(key, frame))

    def handle_user_click(self, x, y):
        """
        Identifies the object clicked by the user for tracking within the segmented area.
        """
        if not self.segmentation_active:
            return

        detections = self.segmentor.get_last_detections()
        selected_bbox = self.identify_clicked_object(detections, x, y)
        if selected_bbox:
            # Convert selected_bbox to integer coordinates
            selected_bbox = tuple(map(lambda x: int(round(x)), selected_bbox))

            self.tracker.reinitialize_tracker(self.current_frame, selected_bbox)
            self.tracking_started = True
            print(f"Object selected for tracking: {selected_bbox}")

    def identify_clicked_object(self, detections, x, y):
        """
        Identifies the clicked object based on segmentation detections and mouse click coordinates.
        """
        for det in detections:
            x1, y1, x2, y2 = det
            if x1 <= x <= x2 and y1 <= y <= y2:
                return det
        return None

    def initiate_redetection(self, frame, tracker=None):
        if Parameters.USE_DETECTOR:
            # Call the smart re-detection method
            redetect_result = self.detector.smart_redetection(frame, self.tracker)
            # If a new bounding box is found, update the tracker with this new box
            if self.detector.get_latest_bbox() is not None and redetect_result == True:
                self.tracker.reinitialize_tracker(frame, self.detector.get_latest_bbox())
                print("Re-detection activated and tracking updated.")
            else:
                print("Re-detection failed or no new object found.")
                
    def show_current_frame(self, frame_title=Parameters.FRAME_TITLE):
        cv2.imshow(frame_title, self.current_frame)
        return self.current_frame
    
    async def connect_px4(self):
        """Connects to PX4 when following mode is activated."""
        if not self.following_active:
            if Parameters.ENABLE_DEBUGGING:
                print("Activating Follow Mode to PX4!")
            await self.px4_controller.connect()
            if Parameters.ENABLE_DEBUGGING:
                print("Connected to PX4 Drone!")
            self.follower = Follower(self.px4_controller)

            # Send an initial setpoint before starting offboard mode
            await self.px4_controller.send_initial_setpoint()
            await self.px4_controller.start_offboard_mode()
            self.following_active = True

    async def disconnect_px4(self):
        if self.following_active:
            await self.px4_controller.stop_offboard_mode()
            if self.setpoint_sender:
                self.setpoint_sender.stop()
                self.setpoint_sender.join()
            self.following_active = False
            
    async def follow_target(self):
        """Prepares to follow the target based on tracking information."""
        if self.tracking_started and self.following_active:
            # Example: Convert tracking info to target coordinates
            target_coords = self.tracker.normalized_center
            # Prepare velocity commands based on target coordinates
            # Note: This part needs adjustment to calculate vel_x, vel_y, vel_z based on target_coords
            # For demonstration, let's assume vel_x, vel_y, vel_z are calculated
            vel_x, vel_y, vel_z = self.follower.calculate_velocity_commands(target_coords)
            # Update the command 
            self.px4_controller.update_setpoint((vel_x, vel_y, vel_z))
            await self.px4_controller.send_body_velocity_commands(self.px4_controller.last_command)

    async def shutdown(self):
        """
        Shutdown the application cleanly.
        """
        if self.api_handler:
            self.api_handler.stop()
        if self.px4_controller.active_mode:
            await self.px4_controller.stop()
            await self.disconnect_px4()
        # if self.telemetry_handler:
        #     await self.telemetry_handler.stop()
        self.video_handler.release()
