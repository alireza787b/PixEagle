import cv2
import numpy as np

class ObjectDetector:
    def __init__(self, model_path, input_size=(640, 640)):
        self.model_path = model_path
        self.input_size = input_size
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.class_names = self._load_class_names()  # Assuming you have a method to load class names

    def _load_class_names(self):
        # Implement this method based on how you store class names (e.g., a text file)
        # For simplicity, this could return a list of class names
        return ["class1", "class2", "class3"]  # Example placeholder

    def detect(self, frame):
        blob = cv2.dnn.blobFromImage(frame, 1/255.0, self.input_size, swapRB=True, crop=False)
        self.net.setInput(blob)
        detections = self.net.forward()

        # Post-process detections (e.g., applying non-maxima suppression)
        # For simplicity, this step is omitted but is important for real applications

        return detections

    def draw_detections(self, frame, detections, class_ids_of_interest):
        # Loop through detections and draw bounding boxes for selected classes
        for detection in detections:
            # Assume detection format includes [classID, confidence, x, y, w, h]
            class_id, confidence, x, y, w, h = detection[:6]
            if class_id in class_ids_of_interest:
                # Convert center x, y, width, and height to corner points
                start_point = (int(x - w / 2), int(y - h / 2))
                end_point = (int(x + w / 2), int(y + h / 2))
                # Draw bounding box
                cv2.rectangle(frame, start_point, end_point, (255, 0, 0), 2)
                # Label with class name (optional)
                label = f"{self.class_names[class_id]}: {confidence:.2f}"
                cv2.putText(frame, label, start_point, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)
        return frame
