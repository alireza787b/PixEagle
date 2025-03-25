import cv2
import numpy as np
import time
import logging
from ultralytics import YOLO
from classes.parameters import Parameters

class SmartTracker:
    def __init__(self, model_path: str):
        try:
            self.model = YOLO(model_path, task='detect')
        except Exception as e:
            logging.error(f"Failed to load YOLO model: {e}")
            raise RuntimeError("YOLO model loading failed.")

        self.labels = self.model.names if hasattr(self.model, 'names') else {}
        self.conf_threshold = Parameters.SMART_TRACKER_CONFIDENCE_THRESHOLD
        self.iou_threshold = Parameters.SMART_TRACKER_IOU_THRESHOLD
        self.max_det = Parameters.SMART_TRACKER_MAX_DETECTIONS
        self.tracker_type = Parameters.SMART_TRACKER_TRACKER_TYPE
        self.show_fps = Parameters.SMART_TRACKER_SHOW_FPS
        self.draw_color = tuple(Parameters.SMART_TRACKER_COLOR)

        self.selected_object_id = None
        self.selected_bbox = None
        self.selected_center = None
        self.last_results = None
        self.object_colors = {}

        self.fps_counter, self.fps_timer, self.fps_display = 0, time.time(), 0
        logging.info(f"SmartTracker initialized with model: {model_path}")

    def get_yolo_color(self, index):
        hue = (index * 0.61803398875) % 1.0
        hsv = np.array([[[int(hue * 179), 255, 255]]], dtype=np.uint8)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0][0]
        return int(bgr[0]), int(bgr[1]), int(bgr[2])

    def get_center(self, x1, y1, x2, y2):
        return (x1 + x2) // 2, (y1 + y2) // 2

    def extend_line_from_edge(self, mid_x, mid_y, direction, img_shape):
        h, w = img_shape[:2]
        if direction == "left": return (0, mid_y)
        if direction == "right": return (w - 1, mid_y)
        if direction == "up": return (mid_x, 0)
        if direction == "down": return (mid_x, h - 1)
        return mid_x, mid_y

    def draw_tracking_scope(self, frame, bbox, color):
        x1, y1, x2, y2 = bbox
        mid_top = ((x1 + x2) // 2, y1)
        mid_bottom = ((x1 + x2) // 2, y2)
        mid_left = (x1, (y1 + y2) // 2)
        mid_right = (x2, (y1 + y2) // 2)
        cv2.line(frame, mid_top, self.extend_line_from_edge(*mid_top, "up", frame.shape), color, 2)
        cv2.line(frame, mid_bottom, self.extend_line_from_edge(*mid_bottom, "down", frame.shape), color, 2)
        cv2.line(frame, mid_left, self.extend_line_from_edge(*mid_left, "left", frame.shape), color, 2)
        cv2.line(frame, mid_right, self.extend_line_from_edge(*mid_right, "right", frame.shape), color, 2)

    def select_object_by_click(self, x, y):
        if self.last_results is None:
            return
        detections = self.last_results[0].boxes.data if self.last_results[0].boxes is not None else []
        min_area = float('inf')
        best_match = None
        for track in detections:
            track = track.tolist()
            if len(track) >= 6:
                x1, y1, x2, y2 = map(int, track[:4])
                if x1 <= x <= x2 and y1 <= y <= y2:
                    area = (x2 - x1) * (y2 - y1)
                    if area < min_area:
                        class_id = int(track[-1])
                        track_id = int(track[4]) if len(track) == 7 else -1
                        min_area = area
                        best_match = (track_id, class_id, (x1, y1, x2, y2))
        if best_match:
            self.selected_object_id, class_id, self.selected_bbox = best_match
            self.selected_center = self.get_center(*self.selected_bbox)
            label = self.labels.get(class_id, str(class_id))
            logging.info(f"TRACKING STARTED: {label} (ID {self.selected_object_id})")

    def clear_selection(self):
        self.selected_object_id = None
        self.selected_bbox = None
        self.selected_center = None

    def track_and_draw(self, frame):
        results = self.model.track(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            max_det=self.max_det,
            tracker=self.tracker_type,
        )
        self.last_results = results
        detections = results[0].boxes.data if results[0].boxes is not None else []
        frame_overlay = frame.copy()
        detected_objects = []

        for track in detections:
            track = track.tolist()
            if len(track) < 6:
                continue
            x1, y1, x2, y2 = map(int, track[:4])
            conf = float(track[5])
            class_id = int(track[6]) if len(track) >= 7 else int(track[5])
            track_id = int(track[4]) if len(track) == 7 else -1

            label_name = self.labels.get(class_id, str(class_id))
            color = self.object_colors.setdefault(track_id, self.get_yolo_color(track_id))
            label = f"{label_name} ID {track_id} ({conf:.2f})"
            detected_objects.append(label)

            if track_id == self.selected_object_id:
                self.selected_bbox = (x1, y1, x2, y2)
                self.selected_center = self.get_center(x1, y1, x2, y2)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 4)
                self.draw_tracking_scope(frame, (x1, y1, x2, y2), color)
                cv2.circle(frame, self.selected_center, 6, color, -1)
                label = f"*ACTIVE* {label}"
            else:
                for i in range(x1, x2, 10):
                    cv2.line(frame_overlay, (i, y1), (i + 5, y1), color, 2)
                    cv2.line(frame_overlay, (i, y2), (i + 5, y2), color, 2)
                for i in range(y1, y2, 10):
                    cv2.line(frame_overlay, (x1, i), (x1, i + 5), color, 2)
                    cv2.line(frame_overlay, (x2, i), (x2, i + 5), color, 2)

            cv2.putText(frame, label, (x1 + 5, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        if self.show_fps:
            self.fps_counter += 1
            if time.time() - self.fps_timer >= 1.0:
                self.fps_display = self.fps_counter
                self.fps_counter = 0
                self.fps_timer = time.time()
            cv2.putText(frame, f"FPS: {self.fps_display}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        blended_frame = cv2.addWeighted(frame_overlay, 0.5, frame, 0.5, 0)
        return blended_frame
