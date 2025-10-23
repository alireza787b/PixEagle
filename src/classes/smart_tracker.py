# src\classes\smart_tracker.py
import cv2
import numpy as np
import time
import logging
import yaml
import os
from typing import Tuple
from ultralytics import YOLO
from classes.parameters import Parameters
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.tracking_state_manager import TrackingStateManager
from classes.motion_predictor import MotionPredictor
from classes.appearance_model import AppearanceModel


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

        # === Validate and Select Tracker Type ===
        self.tracker_type_str, self.use_custom_reid = self._select_tracker_type()

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

        # === Detection Parameters ===
        self.conf_threshold = self.config.get('SMART_TRACKER_CONFIDENCE_THRESHOLD', 0.3)
        self.iou_threshold = self.config.get('SMART_TRACKER_IOU_THRESHOLD', 0.3)
        self.max_det = self.config.get('SMART_TRACKER_MAX_DETECTIONS', 20)
        self.show_fps = self.config.get('SMART_TRACKER_SHOW_FPS', False)
        self.draw_color = tuple(self.config.get('SMART_TRACKER_COLOR', [0, 255, 255]))

        # === Build Tracker Arguments Based on Selected Type ===
        self.tracker_args = self._build_tracker_args()

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

        # === Appearance Model (for custom re-identification after long occlusions)
        # Only used when TRACKER_TYPE = "custom_reid"
        # When using "botsort_reid", Ultralytics handles ReID natively
        if self.use_custom_reid:
            appearance_enabled = self.config.get('ENABLE_APPEARANCE_MODEL', True)
            self.appearance_model = AppearanceModel(
                config=self.config
            ) if appearance_enabled else None
        else:
            self.appearance_model = None  # Not needed for Ultralytics ReID

        # === Robust Tracking State Manager
        # Handles ID matching, spatial fallback, motion prediction, and appearance re-identification
        self.tracking_manager = TrackingStateManager(
            config=self.config,
            motion_predictor=self.motion_predictor,
            appearance_model=self.appearance_model
        )

        self.fps_counter, self.fps_timer, self.fps_display = 0, time.time(), 0

        logging.info("[SmartTracker] Initialization complete.")
        logging.info(f"[SmartTracker] Tracker: {self.tracker_type_str.upper()}")
        if self.use_custom_reid:
            logging.info(f"[SmartTracker] Custom ReID: {'enabled' if self.appearance_model else 'disabled'}")
        logging.info(f"[SmartTracker] Tracking strategy: {self.config.get('TRACKING_STRATEGY', 'hybrid')}")
        logging.info(f"[SmartTracker] Motion prediction: {'enabled' if self.motion_predictor else 'disabled'}")

    def _select_tracker_type(self) -> Tuple[str, bool]:
        """
        Select and validate tracker type based on config and Ultralytics version.

        Returns:
            Tuple[str, bool]: (tracker_name_for_ultralytics, use_custom_reid_flag)
        """
        requested_type = self.config.get('TRACKER_TYPE', 'botsort_reid')

        # Validate BoT-SORT ReID requirements
        if requested_type == 'botsort_reid':
            try:
                import ultralytics
                version_str = ultralytics.__version__
                # Parse version (e.g., "8.3.114" -> (8, 3, 114))
                version_parts = version_str.split('.')
                major = int(version_parts[0])
                minor = int(version_parts[1]) if len(version_parts) > 1 else 0
                patch = int(version_parts[2]) if len(version_parts) > 2 else 0
                version_tuple = (major, minor, patch)

                if version_tuple >= (8, 3, 114):
                    logging.info(f"[SmartTracker] Using BoT-SORT with native ReID (Ultralytics {version_str})")
                    return "botsort", False  # Use Ultralytics BoT-SORT with ReID
                else:
                    logging.warning(f"[SmartTracker] BoT-SORT ReID requires Ultralytics >=8.3.114, "
                                  f"found {version_str}. Falling back to custom_reid.")
                    requested_type = 'custom_reid'
            except Exception as e:
                logging.warning(f"[SmartTracker] Could not verify Ultralytics version: {e}. "
                              "Falling back to custom_reid.")
                requested_type = 'custom_reid'

        # Map tracker types to Ultralytics tracker names
        if requested_type == 'bytetrack':
            logging.info("[SmartTracker] Using ByteTrack (fast, no ReID)")
            return "bytetrack", False
        elif requested_type == 'botsort':
            logging.info("[SmartTracker] Using BoT-SORT (better persistence, no ReID)")
            return "botsort", False
        elif requested_type == 'custom_reid':
            logging.info("[SmartTracker] Using ByteTrack + custom lightweight ReID")
            return "bytetrack", True  # Use ByteTrack as base, add our custom ReID
        else:
            logging.warning(f"[SmartTracker] Unknown tracker type '{requested_type}', using bytetrack")
            return "bytetrack", False

    def _build_tracker_args(self) -> dict:
        """
        Build tracker arguments dict based on selected tracker type and config.

        NOTE: Ultralytics does NOT accept tracker parameters directly in model.track()!
        Tracker params must be in the YAML file. We only pass persist and verbose here.

        Returns:
            dict: Arguments to pass to model.track() (only persist/verbose allowed)
        """
        # ONLY persist and verbose are allowed here
        # All other tracker params must be in bytetrack.yaml or botsort.yaml
        args = {
            "persist": True,
            "verbose": False
        }

        logging.debug(f"[SmartTracker] Tracker args: {args}")
        logging.info(f"[SmartTracker] Using Ultralytics default {self.tracker_type_str}.yaml config")
        logging.info(f"[SmartTracker] Note: To customize tracker params, edit Ultralytics tracker YAML files")

        return args

    def switch_model(self, new_model_path: str, device: str = "auto") -> dict:
        """
        Hot-swap YOLO model without restarting SmartTracker.

        This method allows dynamic model switching at runtime, useful for:
        - Switching between different YOLO versions (e.g., yolo11n -> yolov8s)
        - Changing between GPU (.pt) and CPU (NCNN) models
        - Switching to custom-trained models with different classes

        Args:
            new_model_path (str): Path to the new model file (e.g., "yolo/yolo11n.pt" or "yolo/custom_model.pt")
            device (str): Device preference - "auto" (default), "gpu", or "cpu"

        Returns:
            dict: {
                "success": bool,
                "message": str,
                "model_info": {
                    "path": str,
                    "device": str,
                    "num_classes": int,
                    "class_names": dict
                }
            }
        """
        import torch

        try:
            logging.info(f"[SmartTracker] Switching model to: {new_model_path} (device={device})")

            # 1. Backup current tracking state
            backup_state = {
                "was_tracking": self.selected_object_id is not None,
                "object_id": self.selected_object_id,
                "class_id": self.selected_class_id,
                "bbox": self.selected_bbox,
                "center": self.selected_center
            }

            # 2. Clear current tracking state (will attempt restore later if compatible)
            self.clear_selection()

            # 3. Unload old model and clear GPU cache
            old_device = str(self.model.device) if hasattr(self.model, 'device') else 'unknown'
            del self.model

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logging.info("[SmartTracker] GPU cache cleared")

            # 4. Load new model
            self.model = YOLO(new_model_path, task="detect")

            # 5. Set device based on preference
            target_device = "cpu"  # Default to CPU

            if device == "auto":
                # Auto-detect: use GPU if available and model is .pt file
                if torch.cuda.is_available() and new_model_path.endswith('.pt'):
                    self.model.to('cuda')
                    target_device = "cuda"
            elif device == "gpu":
                if not torch.cuda.is_available():
                    logging.warning("[SmartTracker] GPU requested but not available, using CPU")
                else:
                    self.model.to('cuda')
                    target_device = "cuda"
            # device == "cpu" remains on CPU (default)

            # 6. Update labels
            self.labels = self.model.names if hasattr(self.model, 'names') else {}
            num_classes = len(self.labels)

            # 7. Attempt to restore tracking if classes are compatible
            restore_info = ""
            if backup_state["was_tracking"]:
                # Check if the class ID is valid in the new model
                if backup_state["class_id"] is not None and backup_state["class_id"] < num_classes:
                    # Restore tracking state (tracking manager will re-acquire on next frame)
                    self.selected_object_id = backup_state["object_id"]
                    self.selected_class_id = backup_state["class_id"]
                    self.selected_bbox = backup_state["bbox"]
                    self.selected_center = backup_state["center"]

                    # Reinitialize tracking manager with backed up state
                    if self.selected_bbox and self.selected_center:
                        self.tracking_manager.start_tracking(
                            track_id=self.selected_object_id,
                            class_id=self.selected_class_id,
                            bbox=self.selected_bbox,
                            confidence=0.5,  # Placeholder confidence
                            center=self.selected_center
                        )

                    old_class_name = self.labels.get(backup_state["class_id"], "Unknown")
                    restore_info = f" Tracking restored for class '{old_class_name}'."
                    logging.info(f"[SmartTracker] Tracking state restored (class {backup_state['class_id']})")
                else:
                    restore_info = f" Previous tracking cleared (class ID {backup_state['class_id']} not in new model with {num_classes} classes)."
                    logging.warning(f"[SmartTracker] Cannot restore tracking - class mismatch")

            # 8. Log success
            logging.info(f"[SmartTracker] ✅ Model switched successfully!")
            logging.info(f"[SmartTracker] Device: {old_device} → {str(self.model.device)}")
            logging.info(f"[SmartTracker] Classes: {num_classes}")

            return {
                "success": True,
                "message": f"Model switched successfully to {new_model_path} on {target_device}.{restore_info}",
                "model_info": {
                    "path": new_model_path,
                    "device": str(self.model.device),
                    "num_classes": num_classes,
                    "class_names": self.labels,
                    "tracking_restored": backup_state["was_tracking"] and backup_state["class_id"] < num_classes
                }
            }

        except FileNotFoundError:
            error_msg = f"Model file not found: {new_model_path}"
            logging.error(f"[SmartTracker] {error_msg}")
            return {"success": False, "message": error_msg, "model_info": None}

        except Exception as e:
            error_msg = f"Failed to switch model: {str(e)}"
            logging.error(f"[SmartTracker] {error_msg}")
            logging.exception(e)
            return {"success": False, "message": error_msg, "model_info": None}

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
        # Run YOLO tracking with selected tracker (ByteTrack or BoT-SORT)
        results = self.model.track(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            max_det=self.max_det,
            tracker=f"{self.tracker_type_str}.yaml",  # bytetrack.yaml or botsort.yaml
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

        # Update tracking state using TrackingStateManager (handles ID + spatial + appearance matching)
        is_tracking_active, selected_detection = self.tracking_manager.update_tracking(
            detections_list,
            self.compute_iou,
            frame  # Pass frame for appearance matching
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
                'tracker_type': self.tracker_type_str,
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

