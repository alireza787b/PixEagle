import cv2
import numpy as np
from .parameters import Parameters  
from ultralytics import YOLO
import logging

logger = logging.getLogger(__name__)

class Segmentor:
    def __init__(self, algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM):
        """
        Initializes the Segmentor with a specified segmentation algorithm.
        """
        self.algorithm = algorithm
        if 'yolov8' in self.algorithm:
            self.model = YOLO(f"{self.algorithm}.pt")
        self.previous_detections = []

    def segment_frame(self, frame):
        """
        Segments the given frame using the selected algorithm.
        """
        if 'yolov8' in self.algorithm:
            return self.yolov8_segmentation(frame)
        else:
            return self.generic_segmentation(frame)

    def yolov8_segmentation(self, frame):
        """
        Segments the frame using YOLOv8 and returns an annotated frame.
        """
        try:
            results = self.model(frame)
            annotated_frame = results[0].plot()  
            current_detections = self.extract_detections(results)
            filtered_detections = self.manage_detections(current_detections)
            return annotated_frame
        except Exception as e:
            logger.error(f"Error during YOLOv8 segmentation: {e}")
            return frame

    def generic_segmentation(self, frame):
        """
        Placeholder for other segmentation methods, e.g., GrabCut.
        """
        logger.warning("Generic segmentation method not implemented.")
        return frame

    def extract_detections(self, results):
        """
        Extracts bounding box detections from YOLOv8 results.
        """
        try:
            detections = []
            for det in results[0].boxes.xyxy.tolist():
                assert isinstance(det, (list, tuple)) and len(det) >= 4, "Detection format error"
                detections.append(det[:4])
            return detections
        except Exception as e:
            logger.error(f"Error extracting detections: {e}")
            return []

    def manage_detections(self, current_detections):
        """
        Filters out duplicate detections based on IoU and temporal stability.
        """
        if not self.previous_detections:
            self.previous_detections = current_detections
            return current_detections
        
        filtered_detections = []
        for current in current_detections:
            if not any(self.iou(current, prev) > 0.5 for prev in self.previous_detections):
                filtered_detections.append(current)
        
        self.previous_detections = current_detections
        return filtered_detections

    def iou(self, boxA, boxB):
        """
        Calculates the Intersection over Union (IoU) of two bounding boxes.
        """
        try:
            xA = max(boxA[0], boxB[0])
            yA = max(boxA[1], boxB[1])
            xB = min(boxA[2], boxB[2])
            yB = min(boxB[3], boxB[3])

            interArea = max(0, xB - xA) * max(0, yB - yA)
            boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
            boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

            iou = interArea / float(boxAArea + boxBArea - interArea)
            return iou
        except Exception as e:
            logger.error(f"Error calculating IoU: {e}")
            return 0.0

    def get_last_detections(self):
        """
        Returns the last detections.
        """
        return self.previous_detections

    def user_click_coordinates(self, frame):
        """
        Captures the coordinates of a user click on the frame.
        """
        self.user_click = None
        cv2.namedWindow("Select Object")
        cv2.setMouseCallback("Select Object", self.set_click_coordinates)
        while True:
            cv2.imshow("Select Object", frame)
            if cv2.waitKey(1) & 0xFF == ord('q') or self.user_click is not None:
                break
        cv2.destroyWindow("Select Object")
        return self.user_click

    def set_click_coordinates(self, event, x, y, flags, param):
        """
        Callback to set the user click coordinates.
        """
        if event == cv2.EVENT_LBUTTONDOWN:
            self.user_click = (x, y)

    def _segment_using_grabcut(self, frame, x, y):
        """
        Segments an object using the GrabCut algorithm based on a user click.
        """
        try:
            mask = np.zeros(frame.shape[:2], np.uint8)
            bgdModel = np.zeros((1, 65), np.float64)
            fgdModel = np.zeros((1, 65), np.float64)

            rect = (max(x-50, 0), max(y-50, 0), min(x+50, frame.shape[1]), min(y+50, frame.shape[0]))
            cv2.grabCut(frame, mask, rect, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_RECT)

            binMask = np.where((mask == 2) | (mask == 0), 0, 1).astype('uint8')

            contours, _ = cv2.findContours(binMask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                c = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(c)
                return (x, y, w, h)
            return None
        except Exception as e:
            logger.error(f"Error during GrabCut segmentation: {e}")
            return None

    def refine_bbox(self, frame, bbox):
        """
        Refines a bounding box using segmentation.
        """
        try:
            x, y, w, h = bbox
            mask = np.zeros(frame.shape[:2], np.uint8)
            bgdModel = np.zeros((1, 65), np.float64)
            fgdModel = np.zeros((1, 65), np.float64)
            rect = (x, y, w, h)
            cv2.grabCut(frame, mask, rect, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_RECT)
            mask2 = np.where((mask == 2) | (mask == 0), 0, 1).astype('uint8')
            frame_cut = frame * mask2[:, :, np.newaxis]

            contours, _ = cv2.findContours(mask2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                c = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(c)
                return (x, y, w, h)
            return bbox
        except Exception as e:
            logger.error(f"Error refining bounding box: {e}")
            return bbox
