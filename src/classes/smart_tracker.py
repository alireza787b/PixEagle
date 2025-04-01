# src\classes\smart_tracker.py
import cv2
import numpy as np
import time
import logging
from ultralytics import YOLO
from classes.parameters import Parameters


class SmartTracker:
    def __init__(self, app_controller):
        """
        Initializes the YOLO model (supports GPU/CPU config + optional fallback).
        Model path is selected based on config flags.
        """
        self.app_controller = app_controller
        use_gpu = Parameters.SMART_TRACKER_USE_GPU
        fallback_enabled = Parameters.SMART_TRACKER_FALLBACK_TO_CPU

        try:
            if use_gpu:
                model_path = Parameters.SMART_TRACKER_GPU_MODEL_PATH
                logging.info(f"[SmartTracker] Attempting to load YOLO model with GPU: {model_path}")
                # self.model = YOLO(model_path, task="detect").to('cuda')

            else:
                model_path = Parameters.SMART_TRACKER_CPU_MODEL_PATH
                logging.info(f"[SmartTracker] Loading YOLO model with CPU: {model_path}")
                
                
            self.model = YOLO(model_path, task="detect")

            
            if use_gpu:
                self.model.to('cuda')
                
            logging.info(f"[SmartTracker] YOLO model loaded on device: {self.model.device}")

                
        except Exception as e:
            if use_gpu and fallback_enabled:
                logging.warning(f"[SmartTracker] GPU load failed: {e}")
                logging.info("[SmartTracker] Falling back to CPU model...")

                try:
                    model_path = Parameters.SMART_TRACKER_CPU_MODEL_PATH
                    self.model = YOLO(model_path, task="detect")
                    logging.info(f"[SmartTracker] CPU model loaded successfully: {self.model.device}")
                except Exception as cpu_error:
                    logging.error(f"[SmartTracker] CPU fallback also failed: {cpu_error}")
                    raise RuntimeError("YOLO model loading failed (both GPU and CPU).")

            else:
                logging.error(f"[SmartTracker] Failed to load YOLO model: {e}")
                raise RuntimeError("YOLO model loading failed.")

        # === Tracker Parameters
        self.conf_threshold = Parameters.SMART_TRACKER_CONFIDENCE_THRESHOLD
        self.iou_threshold = Parameters.SMART_TRACKER_IOU_THRESHOLD
        self.max_det = Parameters.SMART_TRACKER_MAX_DETECTIONS
        self.tracker_type = Parameters.SMART_TRACKER_TRACKER_TYPE
        self.tracker_args = {"persist": True, "verbose": False}
        self.show_fps = Parameters.SMART_TRACKER_SHOW_FPS
        self.draw_color = tuple(Parameters.SMART_TRACKER_COLOR)

        self.labels = self.model.names if hasattr(self.model, 'names') else {}

        # === Tracking state
        self.selected_object_id = None
        self.selected_class_id = None
        self.selected_bbox = None
        self.selected_center = None
        self.last_results = None
        self.object_colors = {}

        self.fps_counter, self.fps_timer, self.fps_display = 0, time.time(), 0

        logging.info("[SmartTracker] Initialization complete.")



    def get_yolo_color(self, index):
        """Generate unique color for each object ID using golden ratio."""
        hue = (index * 0.61803398875) % 1.0
        hsv = np.array([[[int(hue * 179), 255, 255]]], dtype=np.uint8)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0][0]
        return int(bgr[0]), int(bgr[1]), int(bgr[2])

    def get_center(self, x1, y1, x2, y2):
        return (x1 + x2) // 2, (y1 + y2) // 2

    def compute_iou(self, box1, box2):
        """Computes Intersection-over-Union between two boxes."""
        x1, y1, x2, y2 = box1
        x1_p, y1_p, x2_p, y2_p = box2
        xi1, yi1 = max(x1, x1_p), max(y1, y1_p)
        xi2, yi2 = min(x2, x2_p), min(y2, y2_p)
        inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
        box1_area = (x2 - x1) * (y2 - y1)
        box2_area = (x2_p - x1_p) * (y2_p - y1_p)
        union_area = box1_area + box2_area - inter_area
        return inter_area / union_area if union_area > 0 else 0

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
        """User selects an object by clicking on it."""
        if self.last_results is None:
            logging.warning("No YOLO results yet, click ignored.")
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
                        class_id = int(track[6]) if len(track) >= 7 else int(track[5])
                        track_id = int(track[4]) if len(track) >= 7 else -1
                        min_area = area
                        best_match = (track_id, class_id, (x1, y1, x2, y2))

        if best_match:
            self.selected_object_id, self.selected_class_id, self.selected_bbox = best_match
            self.selected_center = self.get_center(*self.selected_bbox)
            label = self.labels.get(self.selected_class_id, str(self.selected_class_id))
            logging.info(f"TRACKING STARTED: {label} (ID {self.selected_object_id})")
        else:
            logging.info("No object matched click location.")

    def clear_selection(self):
        """Clears the currently selected object for tracking."""
        self.selected_object_id = None
        self.selected_class_id = None
        self.selected_bbox = None
        self.selected_center = None

    def track_and_draw(self, frame):
        """
        Runs YOLO detection + tracking, draws overlays, and returns the annotated frame.
        Updates tracking state based on selection and draws active/detected object boxes.
        """
        # Run YOLO tracking on the frame
        results = self.model.track(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            max_det=self.max_det,
            tracker=self.tracker_type,
            **self.tracker_args
        )
        self.last_results = results

        detections = results[0].boxes.data if results[0].boxes is not None else []
        frame_overlay = frame.copy()

        selected_this_frame = False  # Track if the selected object is detected in this frame

        for track in detections:
            track = track.tolist()
            if len(track) < 6:
                continue

            # Unpack box and metadata
            x1, y1, x2, y2 = map(int, track[:4])
            conf = float(track[5])
            class_id = int(track[6]) if len(track) >= 7 else int(track[5])
            track_id = int(track[4]) if len(track) >= 7 else -1
            label_name = self.labels.get(class_id, str(class_id))
            color = self.object_colors.setdefault(track_id, self.get_yolo_color(track_id))
            label = f"{label_name} ID {track_id} ({conf:.2f})"

            # Check if this is the selected object (by class and IoU)
            is_selected = False
            if self.selected_class_id == class_id and self.selected_bbox:
                iou = self.compute_iou((x1, y1, x2, y2), self.selected_bbox)
                if iou > 0.3:
                    is_selected = True

            if is_selected:
                # Update selected box and draw thick tracking box
                self.selected_bbox = (x1, y1, x2, y2)
                self.selected_center = self.get_center(x1, y1, x2, y2)
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 4)
                self.draw_tracking_scope(frame, (x1, y1, x2, y2), color)
                cv2.circle(frame, self.selected_center, 6, color, -1)
                label = f"*ACTIVE* {label}"
                selected_this_frame = True
            else:
                # Dashed overlay box for unselected objects
                for i in range(x1, x2, 10):
                    cv2.line(frame_overlay, (i, y1), (i + 5, y1), color, 2)
                    cv2.line(frame_overlay, (i, y2), (i + 5, y2), color, 2)
                for i in range(y1, y2, 10):
                    cv2.line(frame_overlay, (x1, i), (x1, i + 5), color, 2)
                    cv2.line(frame_overlay, (x2, i), (x2, i + 5), color, 2)

            # Draw label text on the frame
            cv2.putText(frame, label, (x1 + 5, y1 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # Update app controller tracking status after processing all detections
        self.app_controller.tracking_started = selected_this_frame

        # FPS Counter
        if self.show_fps:
            self.fps_counter += 1
            if time.time() - self.fps_timer >= 1.0:
                self.fps_display = self.fps_counter
                self.fps_counter = 0
                self.fps_timer = time.time()
            cv2.putText(frame, f"FPS: {self.fps_display}", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        # Final blended result
        blended_frame = cv2.addWeighted(frame_overlay, 0.5, frame, 0.5, 0)
        
        
        if not selected_this_frame:
            self.clear_selection()


        return blended_frame

