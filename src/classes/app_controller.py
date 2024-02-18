from classes.video_handler import VideoHandler
from classes.tracker import Tracker
from classes.segmentor import Segmentor
from classes.parameters import Parameters
import cv2

class AppController:
    def __init__(self):
        # Initialize video processing components
        self.video_handler = VideoHandler()
        self.tracker = Tracker(video_handler=self.video_handler)
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
        """
        Toggles the tracking state. Starts tracking if not started, stops if already started.
        """
        if not self.tracking_started:
            # Start tracking with a user-selected ROI
            bbox = cv2.selectROI("Video", frame, False, False)
            cv2.destroyWindow("ROI selector")
            if bbox and bbox[2] > 0 and bbox[3] > 0:
                self.tracker.start_tracking(frame, bbox)
                self.tracking_started = True
                print("Tracking activated.")
            else:
                print("Tracking canceled or invalid ROI.")
        else:
            # Cancel tracking if it was already started
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
        self.tracker.init_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM)
        print("All activities cancelled.")

    def update_frame(self, frame):
        """
        Updates the frame with the results of tracking and/or segmentation.
        """
        if self.segmentation_active:
            frame = self.segmentor.segment_frame(frame)
        
        if self.tracking_started:
            success, _ = self.tracker.update(frame)
            if success:
                frame = self.tracker.draw_tracking(frame)
                if Parameters.USE_ESTIMATOR:
                    frame = self.tracker.draw_estimate(frame)
                    
        self.current_frame = frame
        return frame

    def handle_key_input(self, key, frame):
        """
        Handles key inputs for toggling segmentation, toggling tracking, and cancelling activities.
        """
        if key in [ord('s'), ord('y')]:
            self.toggle_segmentation()
        elif key == ord('t'):
            self.toggle_tracking(frame)
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
