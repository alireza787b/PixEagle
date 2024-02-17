# src/classes/app_controller.py
from classes.video_handler import VideoHandler
from classes.tracker import Tracker
from classes.segmentor import Segmentor
from classes.parameters import Parameters
import cv2



class AppController:
    def __init__(self):
        self.video_handler = VideoHandler()
        self.tracker = Tracker(video_handler=self.video_handler)
        self.segmentor = Segmentor(algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM)
        self.tracking_started = False

    def start_tracking(self, frame):
        if Parameters.USE_SEGMENTATION_FOR_TRACKING:
            # Let the user draw an initial bounding box to be refined by segmentation
            initial_bbox = cv2.selectROI("Tracking", frame, False, False)
            cv2.destroyWindow("ROI selector")
            if initial_bbox and initial_bbox[2] > 0 and initial_bbox[3] > 0:
                refined_bbox = self.segmentor.refine_bbox(frame, initial_bbox)
                self.tracker.start_tracking(frame, refined_bbox)
                self.tracking_started = True
            else:
                print("Segmentation canceled or invalid ROI.")
        else:
            # Directly use manual ROI selection for tracking without segmentation
            bbox = cv2.selectROI("Tracking", frame, False, False)
            cv2.destroyWindow("ROI selector")
            if bbox and bbox[2] > 0 and bbox[3] > 0:
                self.tracker.start_tracking(frame, bbox)
                self.tracking_started = True
            else:
                print("Tracking canceled or invalid ROI.")

    def start_segmentation(self, frame):
        bbox = self.segmentor.segment(frame)
        if bbox:
            self.tracker.start_tracking(frame, bbox)
            self.tracking_started = True
        else:
            print("Segmentation failed or invalid selection.")

    def cancel_tracking(self):
        self.tracking_started = False
        self.tracker.init_tracker(Parameters.DEFAULT_TRACKING_ALGORITHM)

    def update_frame(self, frame):
        if self.tracking_started:
            success, _ = self.tracker.update(frame)
            if success:
                frame = self.tracker.draw_tracking(frame)
                if Parameters.USE_ESTIMATOR:
                    frame = self.tracker.draw_estimate(frame)
        return frame

    def handle_key_input(self, key, frame):
        if key == ord('t') and not self.tracking_started:
            self.start_tracking(frame)
        elif key == ord('s') and not self.tracking_started:
            self.start_segmentation(frame)
        elif key == ord('c') and self.tracking_started:
            self.cancel_tracking()
