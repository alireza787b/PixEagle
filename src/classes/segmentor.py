# src/classes/segmentor.py

import cv2
import numpy as np
from .parameters import Parameters  
from ultralytics import YOLO

class Segmentor:
    def __init__(self, algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM):
        self.algorithm = algorithm
        if self.algorithm.startswith('yolov8'):
            self.model = YOLO(f"{self.algorithm}.pt")
        self.previous_detections = []

    def segment_frame(self, frame):
        if self.algorithm.startswith('yolov8'):
            return self.yolov8_segmentation(frame)
        else:
            return self.generic_segmentation(frame)

    def yolov8_segmentation(self, frame):
        results = self.model(frame)
        annotated_frame = results[0].plot()  
        current_detections = self.extract_detections(results)
        self.manage_detections(current_detections)
        return annotated_frame

    def generic_segmentation(self, frame):
        # Placeholder for other segmentation methods, e.g., GrabCut
        pass

    def extract_detections(self, results):
        detections = []
        for det in results[0].boxes.xyxy.tolist():  # Assuming results.xyxy[0] is a tensor of bounding boxes
            # Ensure det is a list or tuple of 4 elements (bounding box coordinates)
            assert isinstance(det, (list, tuple)) and len(det) >= 4, "Detection format error"
            detections.append(det[:4])  # Append only the first 4 values assuming they are the bounding box coordinates
        return detections

    def manage_detections(self, current_detections):
        # Filter out duplicates based on IoU and temporal stability
        if not self.previous_detections:
            self.previous_detections = current_detections
            return current_detections
        
        filtered_detections = []
        for current in current_detections:
            match_found = False
            for prev in self.previous_detections:
                if self.iou(current, prev) > 0.5:
                    match_found = True
                    break
            if not match_found:
                filtered_detections.append(current)
        
        self.previous_detections = current_detections
        return filtered_detections

    def iou(self, boxA, boxB):
        # Validate input formats for boxA and boxB
        assert all(isinstance(b, (list, tuple)) and len(b) == 4 for b in [boxA, boxB]), "Box format error"
    
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        # Compute the area of intersection
        interArea = max(0, xB - xA) * max(0, yB - yA)

        # Compute the area of both the prediction and ground-truth rectangles
        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

        # Compute the intersection over union by taking the intersection
        # area and dividing it by the sum of prediction + ground-truth
        # areas - the intersection area
        iou = interArea / float(boxAArea + boxBArea - interArea)

        return iou

    def set_click_coordinates(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.user_click = (x, y)
            
            
            
    def get_last_detections(self):
        # Return the last detections in a format that includes
        # bounding boxes and class names for user selection
        return self.previous_detections

    def user_click_coordinates(self, frame):
        self.user_click = None
        cv2.namedWindow("Select Object")
        cv2.setMouseCallback("Select Object", self.set_click_coordinates)
        while True:
            cv2.imshow("Select Object", frame)
            if cv2.waitKey(1) & 0xFF == ord('q') or self.user_click is not None:
                break
        cv2.destroyWindow("Select Object")
        return self.user_click



    def _segment_using_grabcut(self, frame, x, y):
        """
        Segments an object using the GrabCut algorithm based on a user click.

        This is a private method called internally depending on the selected algorithm.

        Parameters:
        - frame (np.array): The current frame from the video source.
        - x (int): The x-coordinate of the user's click.
        - y (int): The y-coordinate of the user's click.

        Returns:
        - bbox (tuple): The bounding box of the segmented object (x, y, width, height).
        """
        mask = np.zeros(frame.shape[:2], np.uint8)
        bgdModel = np.zeros((1, 65), np.float64)
        fgdModel = np.zeros((1, 65), np.float64)

        # Example rectangle around the click (adjust as needed)
        rect = (max(x-50, 0), max(y-50, 0), min(x+50, frame.shape[1]), min(y+50, frame.shape[0]))

        # Apply GrabCut
        cv2.grabCut(frame, mask, rect, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_RECT)

        # Create a mask where sure and likely backgrounds are set to 0, otherwise 1
        binMask = np.where((mask == 2) | (mask == 0), 0, 1).astype('uint8')

        # Find contours in the binary mask
        contours, _ = cv2.findContours(binMask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Optional: Select the largest contour as the object to track
        if contours:
            c = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
            return (x, y, w, h)
        return None


    def refine_bbox(self, frame, bbox):
        """
        Refines a bounding box using segmentation.
        """
        x, y, w, h = bbox
        # Example of refining using GrabCut or any other chosen algorithm
        mask = np.zeros(frame.shape[:2], np.uint8)
        bgdModel = np.zeros((1, 65), np.float64)
        fgdModel = np.zeros((1, 65), np.float64)
        rect = (x, y, w, h)
        cv2.grabCut(frame, mask, rect, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_RECT)
        mask2 = np.where((mask == 2) | (mask == 0), 0, 1).astype('uint8')
        frame_cut = frame * mask2[:, :, np.newaxis]
        # After segmentation, find contours to get a refined bounding box
        contours, _ = cv2.findContours(mask2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            c = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
            return (x, y, w, h)
        return bbox  # Return original bbox if segmentation fails or no contours found