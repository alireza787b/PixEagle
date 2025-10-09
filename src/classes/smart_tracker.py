# src\classes\smart_tracker.py
import cv2
import numpy as np
import time
import logging
import yaml
import os
from ultralytics import YOLO
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.tracking_state_manager import TrackingStateManager
from classes.motion_predictor import MotionPredictor


class SmartTracker:
    def __init__(self, app_controller):
        """
        Initializes the YOLO model (supports GPU/CPU config + optional fallback).
        Model path is selected based on config flags.
        """
        self.app_controller = app_controller
        use_gpu = Parameters.SmartTracker.get('SMART_TRACKER_USE_GPU', True)
        fallback_enabled = Parameters.SmartTracker.get('SMART_TRACKER_FALLBACK_TO_CPU', True)

        # Load SmartTracker configuration
        self.config = Parameters.SmartTracker

        try:
            if use_gpu:
                model_path = self.config.get('SMART_TRACKER_GPU_MODEL_PATH', 'yolo/yolo11n.pt')
                logging.info(f"[SmartTracker] Attempting to load YOLO model with GPU: {model_path}")

            else:
                model_path = self.config.get('SMART_TRACKER_CPU_MODEL_PATH', 'yolo/yolo11n_ncnn_model')
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
                    model_path = self.config.get('SMART_TRACKER_CPU_MODEL_PATH', 'yolo/yolo11n_ncnn_model')
                    self.model = YOLO(model_path, task="detect")
                    logging.info(f"[SmartTracker] CPU model loaded successfully: {self.model.device}")
                except Exception as cpu_error:
                    logging.error(f"[SmartTracker] CPU fallback also failed: {cpu_error}")
                    raise RuntimeError("YOLO model loading failed (both GPU and CPU).")

            else:
                logging.error(f"[SmartTracker] Failed to load YOLO model: {e}")
                raise RuntimeError("YOLO model loading failed.")

        # === Tracker Parameters
        self.tracker_type = "bytetrack"  # Tracker type identifier for schema
        self.conf_threshold = self.config.get('SMART_TRACKER_CONFIDENCE_THRESHOLD', 0.3)
        self.iou_threshold = self.config.get('SMART_TRACKER_IOU_THRESHOLD', 0.3)
        self.max_det = self.config.get('SMART_TRACKER_MAX_DETECTIONS', 20)
        self.show_fps = self.config.get('SMART_TRACKER_SHOW_FPS', False)
        self.draw_color = tuple(self.config.get('SMART_TRACKER_COLOR', [0, 255, 255]))

        # Use default ByteTrack config (Ultralytics built-in)
        # All tuning is done through YOLO's track() method parameters
        self.tracker_type_str = "bytetrack"
        self.tracker_args = {"persist": True, "verbose": False}

        self.labels = self.model.names if hasattr(self.model, 'names') else {}

        # === Tracking state (maintained for backward compatibility and output)
        self.selected_object_id = None
        self.selected_class_id = None
        self.selected_bbox = None
        self.selected_center = None
        self.last_results = None
        self.object_colors = {}

        # === Motion Predictor (for occlusion handling)
        # Predicts object position during brief detection loss
        prediction_enabled = self.config.get('ENABLE_PREDICTION_BUFFER', True)
        self.motion_predictor = MotionPredictor(
            history_size=self.config.get('ID_LOSS_TOLERANCE_FRAMES', 5),
            velocity_alpha=0.7  # Balanced responsiveness
        ) if prediction_enabled else None

        # === Robust Tracking State Manager
        # Handles ID matching, spatial fallback, and motion prediction
        self.tracking_manager = TrackingStateManager(
            config=self.config,
            motion_predictor=self.motion_predictor
        )

        self.fps_counter, self.fps_timer, self.fps_display = 0, time.time(), 0

        logging.info("[SmartTracker] Initialization complete.")
        logging.info(f"[SmartTracker] Using ByteTrack with Ultralytics default config")
        logging.info(f"[SmartTracker] Tracking strategy: {self.config.get('TRACKING_STRATEGY', 'hybrid')}")
        logging.info(f"[SmartTracker] Motion prediction: {'enabled' if self.motion_predictor else 'disabled'}")

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
        """
        User selects an object by clicking on it.
        Initializes tracking_manager with the selected object.
        """
        if self.last_results is None:
            logging.warning("[SmartTracker] No YOLO results yet, click ignored.")
            return

        detections = self.last_results[0].boxes.data if self.last_results[0].boxes is not None else []
        min_area = float('inf')
        best_match = None

        # Find the smallest object containing the click point
        for track in detections:
            track = track.tolist()
            if len(track) >= 6:
                x1, y1, x2, y2 = map(int, track[:4])
                if x1 <= x <= x2 and y1 <= y <= y2:
                    area = (x2 - x1) * (y2 - y1)
                    if area < min_area:
                        class_id = int(track[6]) if len(track) >= 7 else int(track[5])
                        track_id = int(track[4]) if len(track) >= 7 else -1
                        confidence = float(track[5])
                        min_area = area
                        best_match = (track_id, class_id, (x1, y1, x2, y2), confidence)

        if best_match:
            track_id, class_id, bbox, confidence = best_match
            center = self.get_center(*bbox)

            # Update local state (for backward compatibility)
            self.selected_object_id = track_id
            self.selected_class_id = class_id
            self.selected_bbox = bbox
            self.selected_center = center

            # Initialize tracking manager with robust tracking
            self.tracking_manager.start_tracking(
                track_id=track_id,
                class_id=class_id,
                bbox=bbox,
                confidence=confidence,
                center=center
            )

            label = self.labels.get(class_id, str(class_id))
            logging.info(f"[SMART] Tracking started: {label} ID:{track_id} (conf={confidence:.2f})")
        else:
            logging.info("[SmartTracker] No object matched click location.")

    def clear_selection(self):
        """
        Clears the currently selected object for tracking.
        Also clears tracking_manager state.
        """
        self.selected_object_id = None
        self.selected_class_id = None
        self.selected_bbox = None
        self.selected_center = None

        # Clear tracking manager state
        self.tracking_manager.clear()

        logging.info("[SmartTracker] Tracking cleared")

    def track_and_draw(self, frame):
        """
        Runs YOLO detection + tracking, draws overlays, and returns the annotated frame.
        Uses TrackingStateManager for robust ID tracking with spatial fallback.
        """
        # Run YOLO tracking on the frame with ByteTrack
        results = self.model.track(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            max_det=self.max_det,
            tracker="bytetrack.yaml",  # Use Ultralytics default ByteTrack config
            **self.tracker_args
        )
        self.last_results = results

        detections = results[0].boxes.data if results[0].boxes is not None else []
        frame_overlay = frame.copy()

        # === Use TrackingStateManager for robust tracking ===
        # Converts detections to list format expected by tracking_manager
        detections_list = []
        for track in detections:
            track = track.tolist()
            if len(track) >= 6:
                detections_list.append(track)

        # Update tracking state using TrackingStateManager (handles ID + spatial matching)
        is_tracking_active, selected_detection = self.tracking_manager.update_tracking(
            detections_list,
            self.compute_iou
        )

        # Draw all detections
        for track in detections_list:
            x1, y1, x2, y2 = map(int, track[:4])
            conf = float(track[5])
            class_id = int(track[6]) if len(track) >= 7 else int(track[5])
            track_id = int(track[4]) if len(track) >= 7 else -1
            label_name = self.labels.get(class_id, str(class_id))
            color = self.object_colors.setdefault(track_id, self.get_yolo_color(track_id))
            label = f"{label_name} ID {track_id} ({conf:.2f})"

            # Check if this is the actively tracked object
            is_selected = (selected_detection is not None and
                          track_id == selected_detection['track_id'])

            if is_selected:
                # Update local state (for backward compatibility)
                self.selected_object_id = track_id
                self.selected_class_id = class_id
                self.selected_bbox = (x1, y1, x2, y2)
                self.selected_center = self.get_center(x1, y1, x2, y2)

                # Continuously update classic tracker's override with latest detection
                if self.app_controller.tracker and hasattr(self.app_controller.tracker, 'set_external_override'):
                    self.app_controller.tracker.set_external_override(
                        self.selected_bbox,
                        self.selected_center
                    )

                # Draw thick tracking box with scope lines
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 4)
                self.draw_tracking_scope(frame, (x1, y1, x2, y2), color)
                cv2.circle(frame, self.selected_center, 6, color, -1)

                # Add status indicator to label
                if selected_detection.get('iou_match', False):
                    match_info = f"IoU={selected_detection['match_iou']:.2f}"
                    label = f"*ACTIVE* {label} [{match_info}]"
                else:
                    label = f"*ACTIVE* {label}"
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

        # Update app controller tracking status
        self.app_controller.tracking_started = is_tracking_active

        # If tracking is lost, clear local state AND classic tracker override
        if not is_tracking_active and (self.selected_object_id is not None):
            logging.info(f"[SMART] Track lost: ID:{self.selected_object_id}")
            self.selected_object_id = None
            self.selected_class_id = None
            self.selected_bbox = None
            self.selected_center = None

            # Clear classic tracker override to remove visual scope
            if self.app_controller.tracker and hasattr(self.app_controller.tracker, 'clear_external_override'):
                self.app_controller.tracker.clear_external_override()

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
        return blended_frame

    def get_output(self) -> TrackerOutput:
        """
        Returns SmartTracker output in the new flexible schema format.

        Returns:
            TrackerOutput: YOLO-based tracker data with multi-target support
        """
        # Check if we have an active selection
        tracking_active = (self.selected_object_id is not None and
                          self.selected_bbox is not None and
                          self.selected_center is not None)

        # Prepare multi-target data if available
        targets = []
        if self.last_results and self.last_results[0].boxes is not None:
            detections = self.last_results[0].boxes.data
            for track in detections:
                track = track.tolist()
                if len(track) >= 6:
                    x1, y1, x2, y2 = map(int, track[:4])
                    conf = float(track[5])
                    class_id = int(track[6]) if len(track) >= 7 else int(track[5])
                    track_id = int(track[4]) if len(track) >= 7 else -1

                    target_data = {
                        'target_id': track_id,
                        'class_id': class_id,
                        'class_name': self.labels.get(class_id, str(class_id)),
                        'bbox': (x1, y1, x2 - x1, y2 - y1),  # Convert to x,y,w,h
                        'center': self.get_center(x1, y1, x2, y2),
                        'confidence': conf,
                        'is_selected': track_id == self.selected_object_id
                    }
                    targets.append(target_data)

        # Use MULTI_TARGET only if we have detections, otherwise use POSITION_2D to avoid schema error
        data_type = TrackerDataType.MULTI_TARGET if len(targets) > 0 else TrackerDataType.POSITION_2D

        return TrackerOutput(
            data_type=data_type,
            timestamp=time.time(),
            tracking_active=tracking_active,
            tracker_id=f"SmartTracker_{id(self)}",

            # Primary target data (selected object)
            position_2d=self._normalize_center(self.selected_center) if self.selected_center else None,
            bbox=self._convert_bbox_format(self.selected_bbox) if self.selected_bbox else None,
            normalized_bbox=self._normalize_bbox(self.selected_bbox) if self.selected_bbox else None,
            confidence=self._get_selected_confidence(),

            # Multi-target data (only included if we have targets)
            target_id=self.selected_object_id,
            targets=targets if len(targets) > 0 else None,  # Set to None if empty to pass validation

            quality_metrics={
                'detection_count': len(targets),
                'fps': self.fps_display,
                'model_confidence_threshold': self.conf_threshold
            },

            raw_data={
                'yolo_results': self.last_results[0].boxes.data.tolist() if self.last_results and self.last_results[0].boxes is not None else [],
                'selected_class_id': self.selected_class_id,
                'tracker_type': self.tracker_type,
                'device': str(self.model.device) if hasattr(self.model, 'device') else 'unknown'
            },

            metadata={
                'tracker_class': self.__class__.__name__,
                'tracker_algorithm': 'YOLO + ByteTrack',
                'model_type': 'YOLO',
                'supports_multi_target': True,
                'supports_classification': True,
                'real_time': True,
                'detection_classes': list(self.labels.keys()) if self.labels else []
            }
        )

    def get_capabilities(self) -> dict:
        """
        Returns SmartTracker capabilities.
        
        Returns:
            dict: SmartTracker-specific capabilities
        """
        return {
            'data_types': [TrackerDataType.MULTI_TARGET.value],
            'supports_confidence': True,
            'supports_velocity': False,  # YOLO doesn't directly provide velocity
            'supports_bbox': True,
            'supports_normalization': True,
            'supports_multi_target': True,
            'supports_classification': True,
            'estimator_available': False,
            'multi_target': True,
            'real_time': True,
            'tracker_algorithm': 'YOLO + ByteTrack',
            'accuracy_rating': 'very_high',
            'speed_rating': 'high' if hasattr(self.model, 'device') and 'cuda' in str(self.model.device) else 'medium',
            'detection_classes': len(self.labels) if self.labels else 0
        }

    def _normalize_center(self, center):
        """Normalize center coordinates to [-1, 1] range."""
        if not center or not hasattr(self.app_controller, 'video_handler'):
            return None
        
        video_handler = self.app_controller.video_handler
        if not video_handler:
            return None
            
        frame_width, frame_height = video_handler.width, video_handler.height
        x, y = center
        norm_x = (x - frame_width / 2) / (frame_width / 2)
        norm_y = (y - frame_height / 2) / (frame_height / 2)
        return (norm_x, norm_y)

    def _normalize_bbox(self, bbox):
        """Normalize bounding box coordinates."""
        if not bbox or not hasattr(self.app_controller, 'video_handler'):
            return None
            
        video_handler = self.app_controller.video_handler
        if not video_handler:
            return None
            
        frame_width, frame_height = video_handler.width, video_handler.height
        x1, y1, x2, y2 = bbox
        w, h = x2 - x1, y2 - y1
        x, y = x1, y1
        
        norm_x = (x - frame_width / 2) / (frame_width / 2)
        norm_y = (y - frame_height / 2) / (frame_height / 2)
        norm_w = w / frame_width
        norm_h = h / frame_height
        return (norm_x, norm_y, norm_w, norm_h)

    def _convert_bbox_format(self, bbox):
        """Convert x1,y1,x2,y2 to x,y,w,h format."""
        if not bbox:
            return None
        x1, y1, x2, y2 = bbox
        return (x1, y1, x2 - x1, y2 - y1)

    def _get_selected_confidence(self):
        """Get confidence of the selected object."""
        if not self.last_results or not self.selected_object_id:
            return None
            
        if not self.last_results[0].boxes:
            return None
            
        detections = self.last_results[0].boxes.data
        for track in detections:
            track = track.tolist()
            if len(track) >= 6:
                track_id = int(track[4]) if len(track) >= 7 else -1
                if track_id == self.selected_object_id:
                    return float(track[5])
        return None

