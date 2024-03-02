import numpy as np
from classes.video_handler import VideoHandler
from classes.trackers.base_tracker import BaseTracker
from classes.trackers.csrt_tracker import CSRTTracker  # Import other trackers as necessary
from classes.segmentor import Segmentor
from classes.trackers.tracker_factory import create_tracker
from classes.detector import Detector
from classes.parameters import Parameters
import cv2

class AppController:
    def __init__(self):
        # Initialize video processing components
        self.video_handler = VideoHandler()
        self.detector = Detector(algorithm_type=Parameters.DETECTION_ALGORITHM)
        self.tracker = create_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM,self.video_handler, self.detector)
        self.segmentor = Segmentor(algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM)
        # Flags to track the state of tracking and segmentation
        self.tracking_started = False
        self.segmentation_active = False
        # Setup a named window and a mouse callback for interactions
        cv2.namedWindow("Video")
        cv2.setMouseCallback("Video", self.on_mouse_click)
        self.current_frame = None

    def on_mouse_click(self, event, x, y, flags, param):
        """
        Handles mouse click events in the video window, specifically for initiating segmentation.
        """
        if event == cv2.EVENT_LBUTTONDOWN and self.segmentation_active:
            self.handle_user_click(x, y)

    def toggle_tracking(self, frame):
        if not self.tracking_started:
            bbox = cv2.selectROI(Parameters.FRAME_TITLE, frame, False, False)
            cv2.destroyWindow("ROI selector")
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
        print("All activities cancelled.")

    def update_frame(self, frame):
        """
        Updates the frame with the results of tracking and/or segmentation.
        """
        if self.segmentation_active:
            # Assuming `segment_frame` is a method that modifies the frame and returns it.
            frame = self.segmentor.segment_frame(frame)
        
        if self.tracking_started:
            # Update the tracker and check if tracking was successful
            success, _ = self.tracker.update(frame)
            if success:
                # Draw tracking and estimation results on the frame
                frame = self.tracker.draw_tracking(frame)  # Assumes draw_tracking modifies the frame
                if Parameters.USE_ESTIMATOR:
                    frame = self.tracker.draw_estimate(frame)  # Assumes draw_estimate modifies the frame
            else:
                # Optionally reinitialize tracking based on certain conditions
                if Parameters.USE_DETECTOR and Parameters.AUTO_REDETECT:
                    # Assuming `initiate_redetection` is a method that handles re-detection logic
                    self.initiate_redetection(frame, self.tracker)
                    
        if Parameters.USE_DETECTOR:
            # Assuming you have a method to draw detections, uncomment or adjust as needed
            # frame = self.detector.draw_detection(frame, color=(0, 255, 255))
            pass

        # Update the current frame attribute with the modified frame
        self.current_frame = frame
                    
        return frame

    def handle_key_input(self, key, frame):
        """
        Handles key inputs for toggling segmentation, toggling tracking, starting feature extraction, and cancelling activities.
        """
        if key ==ord('y'):
            self.toggle_segmentation()
        elif key == ord('t'):
            self.toggle_tracking(frame)
        elif key == ord('d'):
            self.initiate_redetection(frame)
        elif key == ord('c'):
            self.cancel_activities()


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

    def initiate_redetection(self, frame,tracker=None):
       if Parameters.USE_DETECTOR:
            # Call the smart re-detection method
            redetect_result = self.detector.smart_redetection(frame,self.tracker)
            # If a new bounding box is found, update the tracker with this new box
            if self.detector.get_latest_bbox() is not None and redetect_result == True :
                self.tracker.reinitialize_tracker(frame, self.detector.get_latest_bbox())
                print("Re-detection activated and tracking updated.")
            else:
                print("Re-detection failed or no new object found.")
                
    def show_current_frame(self,frame_title = Parameters.FRAME_TITLE):
        cv2.imshow(frame_title, self.current_frame)
        return self.current_frame
