import cv2
import numpy as np
import logging
from ultralytics import YOLO
from classes.parameters import Parameters

class SmartTracker:
    def __init__(self, model_path: str):
        """
        Initializes the SmartTracker using an Ultralytics YOLO model.

        Args:
            model_path (str): Full path to the YOLO model file (e.g., "yolo/yolov8n.pt").
        """
        try:
            self.model = YOLO(model_path, task='detect')
        except Exception as e:
            logging.error(f"Failed to load YOLO model from {model_path}: {e}")
            raise RuntimeError("YOLO model loading failed.")

        # Store label mapping from the model, if available.
        self.labels = self.model.names if hasattr(self.model, 'names') else {}
        self.confidence_threshold = Parameters.SMART_TRACKER_CONFIDENCE_THRESHOLD
        self.draw_color = getattr(Parameters, 'SMART_TRACKER_COLOR', (0, 255, 255))

        logging.info(f"SmartTracker initialized with model: {model_path}")

    def detect(self, frame: np.ndarray):
        """
        Runs object detection on the provided frame using YOLO.

        Args:
            frame (np.ndarray): Input video frame.

        Returns:
            List of detections in the format [xmin, ymin, width, height, label, confidence].
        """
        detections = []
        try:
            results = self.model(frame, verbose=False)
            if not results:
                logging.warning("No results from YOLO inference.")
                return detections

            result = results[0]  # Process the first result.
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                return detections

            # Convert bounding box coordinates, confidence, and class to numpy arrays.
            xyxy = boxes.xyxy.cpu().numpy()  # shape (N, 4)
            confs = boxes.conf.cpu().numpy()   # shape (N,)
            clss = boxes.cls.cpu().numpy()     # shape (N,)

            for i in range(len(xyxy)):
                if confs[i] < self.confidence_threshold:
                    continue
                xmin, ymin, xmax, ymax = xyxy[i].astype(int)
                width, height = xmax - xmin, ymax - ymin
                label = int(clss[i])
                detections.append([xmin, ymin, width, height, label, confs[i]])

            # Log unique detected class IDs and names.
            unique_classes = sorted(set([int(det[4]) for det in detections]))
            class_names = [self.labels.get(cls, str(cls)) for cls in unique_classes]
            logging.info(f"Detected classes: {unique_classes} with names: {class_names}")

        except Exception as e:
            logging.error(f"Error during YOLO detection: {e}")

        logging.debug(f"Detections: {detections}")
        return detections

    def draw_detections(self, frame: np.ndarray, detections: list) -> np.ndarray:
        """
        Draws bounding boxes and labels onto the frame.

        Args:
            frame (np.ndarray): Video frame.
            detections (list): List of detections.

        Returns:
            np.ndarray: Frame with drawn detections.
        """
        for (xmin, ymin, width, height, label, conf) in detections:
            cv2.rectangle(frame, (xmin, ymin), (xmin + width, ymin + height), self.draw_color, 2)
            label_name = self.labels.get(label, str(label))
            label_text = f"{label_name}: {conf:.2f}"
            cv2.putText(frame, label_text, (xmin, ymin - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.draw_color, 2)
        return frame

    def get_closest_detection(self, detections: list, x_click: int, y_click: int):
        """
        Finds the closest detected object to the click position.

        Args:
            detections (list): Detections from YOLO.
            x_click (int): X-coordinate of the click.
            y_click (int): Y-coordinate of the click.

        Returns:
            Tuple[int, int, int, int] or None: Closest bounding box in [xmin, ymin, width, height] format.
        """
        min_dist = float('inf')
        closest_bbox = None

        for bbox in detections:
            xmin, ymin, width, height, _, _ = bbox
            center_x = xmin + width // 2
            center_y = ymin + height // 2
            distance = np.sqrt((center_x - x_click) ** 2 + (center_y - y_click) ** 2)
            if distance < min_dist:
                min_dist = distance
                closest_bbox = (xmin, ymin, width, height)

        logging.debug(f"Closest detection to click: {closest_bbox}")
        return closest_bbox
