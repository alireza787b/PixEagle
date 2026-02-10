# src/classes/tracking_state_manager.py
"""
Tracking State Manager for robust object tracking across frames.

This module provides intelligent track ID management with multiple fallback strategies
to handle common tracking challenges like:
- ID switches by YOLO trackers (ByteTrack, BoT-SORT, etc.)
- Brief AND long occlusions (1-30+ frames)
- Detection failures and class label flickering
- Re-identification after loss with position gating

MATCHING HIERARCHY (hybrid strategy):
  1. ID match         — exact track_id + flexible class_id
  2. Spatial match    — IoU against Kalman-predicted position
  3. Distance match   — center distance when IoU is zero (fast motion)
  4. Appearance match — visual ReID with position gating

TRACKER COMPATIBILITY:
- Works with ANY Ultralytics tracker (ByteTrack, BoT-SORT, BoT-SORT+ReID)
- Tracker-agnostic design: only requires detection format [x1, y1, x2, y2, track_id, conf, class_id]
- Adds additional robustness layer on top of built-in tracker capabilities

Author: PixEagle Team
Date: 2025
"""

import logging
import time
import math
from collections import deque
from typing import Optional, Tuple, List, Dict
import numpy as np

from classes.kalman_box_tracker import KalmanBoxTracker


class TrackingStateManager:
    """
    Manages tracking state with hybrid ID + spatial + distance + appearance matching.

    Provides robust tracking by:
    1. Primary: Track by ID (fast, accurate when IDs are stable)
    2. Fallback 1: Track by spatial proximity (IoU) against Kalman-predicted position
    3. Fallback 2: Track by center distance (handles fast motion where IoU=0)
    4. Fallback 3: Track by visual appearance with position gating
    5. Prediction: Kalman filter provides continuous position estimation during occlusion
    """

    def __init__(self, config: dict, motion_predictor=None, appearance_model=None):
        """
        Initialize the tracking state manager.

        Args:
            config: Dictionary of SmartTracker configuration parameters
            motion_predictor: Optional motion predictor for occlusion handling (legacy fallback)
            appearance_model: Optional appearance model for re-identification
        """
        self.config = config
        self.motion_predictor = motion_predictor
        self.appearance_model = appearance_model

        # Core tracking state
        self.selected_track_id: Optional[int] = None
        self.selected_class_id: Optional[int] = None
        self.last_known_bbox: Optional[Tuple[int, int, int, int]] = None
        self.last_known_center: Optional[Tuple[int, int]] = None
        self.last_detection_time: float = 0.0

        # Kalman filter (initialized on start_tracking)
        self.kalman: Optional[KalmanBoxTracker] = None
        self.enable_kalman = self.config.get('ENABLE_KALMAN_FILTER', True)
        self.kalman_process_noise = self.config.get('KALMAN_PROCESS_NOISE', 1.0)
        self.kalman_measurement_noise = self.config.get('KALMAN_MEASUREMENT_NOISE', 1.0)

        # Tracking history for temporal consistency
        self.max_history = self.config.get('ID_LOSS_TOLERANCE_FRAMES', 5)
        self.tracking_history = deque(maxlen=max(self.max_history, 10))

        # Strategy configuration
        self.tracking_strategy = self.config.get('TRACKING_STRATEGY', 'hybrid')
        self.spatial_iou_threshold = self.config.get('SPATIAL_IOU_THRESHOLD', 0.35)
        self.enable_prediction = self.config.get('ENABLE_PREDICTION_BUFFER', True)

        # Center-distance matching (Change 3)
        self.enable_distance_matching = self.config.get('ENABLE_CENTER_DISTANCE_MATCHING', True)
        self.center_distance_threshold = self.config.get('CENTER_DISTANCE_THRESHOLD', 2.0)

        # Class flexibility (Change 4)
        self.class_match_flexible = self.config.get('CLASS_MATCH_FLEXIBLE', True)
        self.class_history_size = self.config.get('CLASS_HISTORY_SIZE', 10)
        self.class_history: deque = deque(maxlen=self.class_history_size)

        # Search expansion (Change 7)
        self.search_expansion_rate = self.config.get('SEARCH_EXPANSION_RATE', 0.2)

        # Appearance position gating (Change 6)
        self.appearance_distance_gate = self.config.get('APPEARANCE_DISTANCE_GATE_FACTOR', 3.0)

        # Confidence smoothing and decay
        self.confidence_alpha = self.config.get('CONFIDENCE_SMOOTHING_ALPHA', 0.8)
        self.smoothed_confidence = 0.0

        # Confidence decay for aging tracks (5% per frame without detection)
        self.confidence_decay_rate = self.config.get('TRACK_CONFIDENCE_DECAY_RATE', 0.05)

        # Frame counter
        self.frames_since_detection = 0
        self.total_frames = 0

        # Appearance-based re-identification
        self.enable_appearance = self.config.get('ENABLE_APPEARANCE_MODEL', True) and appearance_model is not None

        logging.info(f"[TrackingStateManager] Initialized with strategy='{self.tracking_strategy}', "
                    f"tolerance={self.max_history} frames, IoU threshold={self.spatial_iou_threshold}, "
                    f"kalman={'enabled' if self.enable_kalman else 'disabled'}, "
                    f"distance_matching={'enabled' if self.enable_distance_matching else 'disabled'}, "
                    f"class_flexible={'enabled' if self.class_match_flexible else 'disabled'}")
        if self.enable_appearance:
            logging.info(f"[TrackingStateManager] Appearance re-identification: enabled "
                        f"(distance_gate={self.appearance_distance_gate})")

    def start_tracking(self, track_id: int, class_id: int, bbox: Tuple[int, int, int, int],
                      confidence: float, center: Tuple[int, int]):
        """
        Start tracking a new object.

        Args:
            track_id: YOLO track ID
            class_id: Object class ID
            bbox: Bounding box (x1, y1, x2, y2)
            confidence: Detection confidence
            center: Center point (x, y)
        """
        self.selected_track_id = track_id
        self.selected_class_id = class_id
        self.last_known_bbox = bbox
        self.last_known_center = center
        self.last_detection_time = time.time()
        self.smoothed_confidence = confidence
        self.frames_since_detection = 0
        self.tracking_history.clear()

        # Initialize class history
        self.class_history.clear()
        self.class_history.append(class_id)

        # Initialize Kalman filter
        if self.enable_kalman:
            self.kalman = KalmanBoxTracker(
                bbox,
                process_noise_scale=self.kalman_process_noise,
                measurement_noise_scale=self.kalman_measurement_noise
            )
            logging.debug(f"[TrackingStateManager] Kalman filter initialized for ID:{track_id}")

        # Add to history
        self._add_to_history(track_id, class_id, bbox, confidence, center)

        logging.debug(f"[TRACKING] Started: ID:{track_id} class:{class_id} conf={confidence:.2f}")

    def update_tracking(self, detections: List[List], compute_iou_func, frame: np.ndarray = None) -> Tuple[bool, Optional[Dict]]:
        """
        Update tracking state with new detections.

        Args:
            detections: List of YOLO detections (each is [x1, y1, x2, y2, track_id, conf, class_id])
            compute_iou_func: Function to compute IoU between two boxes
            frame: Current frame (BGR image) - required for appearance matching

        Returns:
            Tuple of (is_tracking_active, selected_detection_dict or None)
        """
        self.total_frames += 1

        # Increment appearance model frame counter if available
        if self.appearance_model:
            self.appearance_model.increment_frame()

        if self.selected_track_id is None:
            return False, None

        # Advance Kalman prediction each frame (continuous, no frame limit)
        if self.kalman and self.enable_kalman:
            self.kalman.predict()

        # Try to find the selected object using configured strategy
        best_match = None

        if self.tracking_strategy == "id_only":
            best_match = self._match_by_id(detections)
        elif self.tracking_strategy == "spatial_only":
            best_match = self._match_by_spatial(detections, compute_iou_func)
        elif self.tracking_strategy == "hybrid":
            # Level 1: ID match (fast, exact)
            best_match = self._match_by_id(detections)

            # Level 2: Spatial IoU match against predicted position
            if best_match is None:
                best_match = self._match_by_spatial(detections, compute_iou_func)

            # Level 3: Center-distance match (handles fast motion where IoU=0)
            if best_match is None and self.enable_distance_matching:
                best_match = self._match_by_distance(detections)

            # Level 4: Appearance-based matching with position gating
            if best_match is None and self.enable_appearance and frame is not None:
                best_match = self._match_by_appearance(detections, frame)

        # Update state based on match result
        if best_match:
            self._on_detection_found(best_match, frame)
            return True, best_match
        else:
            self._on_detection_lost()

            # Graceful degradation with multi-level fallback
            return self._handle_detection_loss(detections, compute_iou_func, frame)

    def _is_class_compatible(self, class_id: int) -> bool:
        """
        Check if a detection's class is compatible with the tracked object.

        With CLASS_MATCH_FLEXIBLE enabled, allows class flickering (e.g. car<->truck)
        by checking against the class history buffer.

        Args:
            class_id: Detection class ID to check

        Returns:
            True if class is compatible with tracked object
        """
        if class_id == self.selected_class_id:
            return True

        if self.class_match_flexible and len(self.class_history) > 0:
            return class_id in self.class_history

        return False

    def _get_reference_bbox(self) -> Optional[Tuple[int, int, int, int]]:
        """
        Get the best reference bbox for spatial matching.

        Uses Kalman-predicted position (always fresh) instead of stale last_known_bbox.

        Returns:
            Reference bounding box for spatial matching, or None
        """
        if self.kalman and self.enable_kalman:
            return self.kalman.get_state()
        return self.last_known_bbox

    def _get_reference_center(self) -> Optional[Tuple[int, int]]:
        """
        Get the best reference center for distance matching.

        Returns:
            Reference center (cx, cy), or None
        """
        if self.kalman and self.enable_kalman:
            return self.kalman.get_predicted_center()
        return self.last_known_center

    def _get_expanded_bbox(self, bbox: Tuple[int, int, int, int], expansion: float) -> Tuple[int, int, int, int]:
        """
        Expand a bounding box by a factor (for search radius expansion).

        Args:
            bbox: Original bounding box (x1, y1, x2, y2)
            expansion: Expansion factor (0.2 = 20% expansion on each side)

        Returns:
            Expanded bounding box
        """
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        dx = int(w * expansion / 2)
        dy = int(h * expansion / 2)
        return (x1 - dx, y1 - dy, x2 + dx, y2 + dy)

    def _match_by_id(self, detections: List[List]) -> Optional[Dict]:
        """Match detection by track ID with flexible class matching.

        When class_match_flexible is enabled and the track ID matches exactly,
        any class is accepted because YOLO's internal tracker already confirmed
        object identity. The class label can flicker independently.
        """
        for detection in detections:
            if len(detection) < 7:
                continue

            track_id = int(detection[4])
            class_id = int(detection[6])

            if track_id == self.selected_track_id:
                # Exact ID match: accept any class when flexible (YOLO says same object)
                if self.class_match_flexible or class_id == self.selected_class_id:
                    return self._parse_detection(detection)

        return None

    def _match_by_spatial(self, detections: List[List], compute_iou_func) -> Optional[Dict]:
        """Match detection by IoU against Kalman-predicted position."""
        reference_bbox = self._get_reference_bbox()
        if reference_bbox is None:
            return None

        # Expand search bbox based on frames lost (Change 7)
        if self.frames_since_detection > 0:
            expansion = min(self.frames_since_detection * self.search_expansion_rate, 2.0)
            reference_bbox = self._get_expanded_bbox(reference_bbox, expansion)

        best_match = None
        best_iou = 0.0

        for detection in detections:
            if len(detection) < 7:
                continue

            class_id = int(detection[6])

            # Flexible class matching
            if not self._is_class_compatible(class_id):
                continue

            # Compute IoU with predicted/expanded reference position
            x1, y1, x2, y2 = map(int, detection[:4])
            current_bbox = (x1, y1, x2, y2)
            iou = compute_iou_func(current_bbox, reference_bbox)

            if iou > best_iou and iou >= self.spatial_iou_threshold:
                best_iou = iou
                best_match = self._parse_detection(detection)
                best_match['track_id'] = int(detection[4])
                best_match['iou_match'] = True
                best_match['match_iou'] = iou

        if best_match:
            logging.debug(f"[TrackingStateManager] Spatial match: ID {self.selected_track_id}->{best_match['track_id']}, IoU={best_iou:.3f}")

        return best_match

    def _match_by_distance(self, detections: List[List]) -> Optional[Dict]:
        """
        Match detection by center distance (fallback when IoU is zero).

        Handles fast-moving objects that displaced beyond IoU overlap.
        Distance threshold is adaptive based on object size and frames lost.
        """
        reference_center = self._get_reference_center()
        reference_bbox = self._get_reference_bbox()
        if reference_center is None or reference_bbox is None:
            return None

        ref_cx, ref_cy = reference_center
        rx1, ry1, rx2, ry2 = reference_bbox
        ref_w = max(rx2 - rx1, 1)
        ref_h = max(ry2 - ry1, 1)
        ref_diagonal = math.sqrt(ref_w ** 2 + ref_h ** 2)

        # Adaptive distance threshold: base * (1 + frames_lost * expansion_rate)
        adaptive_threshold = self.center_distance_threshold * (
            1.0 + self.frames_since_detection * self.search_expansion_rate
        )
        max_distance = ref_diagonal * adaptive_threshold

        best_match = None
        best_dist = float('inf')

        for detection in detections:
            if len(detection) < 7:
                continue

            class_id = int(detection[6])

            # Flexible class matching
            if not self._is_class_compatible(class_id):
                continue

            x1, y1, x2, y2 = map(int, detection[:4])
            det_cx = (x1 + x2) / 2
            det_cy = (y1 + y2) / 2

            dist = math.sqrt((det_cx - ref_cx) ** 2 + (det_cy - ref_cy) ** 2)

            if dist < best_dist and dist <= max_distance:
                best_dist = dist
                best_match = self._parse_detection(detection)
                best_match['track_id'] = int(detection[4])
                best_match['iou_match'] = True  # Mark as spatial recovery
                best_match['match_iou'] = 0.0
                best_match['distance_match'] = True
                best_match['match_distance'] = dist

        if best_match:
            logging.info(f"[TrackingStateManager] Distance match: ID {self.selected_track_id}->{best_match['track_id']}, "
                        f"dist={best_dist:.1f}px (threshold={max_distance:.1f}px)")

        return best_match

    def _match_by_appearance(self, detections: List[List], frame: np.ndarray) -> Optional[Dict]:
        """Match detection by visual appearance with position gating (Change 6)."""
        if not self.appearance_model or self.selected_class_id is None:
            return None

        # Position gating: compute max plausible displacement
        reference_center = self._get_reference_center()
        max_gate_distance = None

        if reference_center is not None:
            ref_bbox = self._get_reference_bbox()
            if ref_bbox is not None:
                rx1, ry1, rx2, ry2 = ref_bbox
                ref_diagonal = math.sqrt((rx2 - rx1) ** 2 + (ry2 - ry1) ** 2)
                # Max distance: object_size * gate_factor * (1 + frames_lost * expansion)
                max_gate_distance = ref_diagonal * self.appearance_distance_gate * (
                    1.0 + self.frames_since_detection * self.search_expansion_rate
                )

        # Convert detections to format expected by appearance model, applying position gate
        detection_dicts = []
        for detection in detections:
            if len(detection) < 7:
                continue

            x1, y1, x2, y2 = map(int, detection[:4])
            track_id = int(detection[4])
            class_id = int(detection[6])

            # Position gating: skip candidates too far from predicted position
            if max_gate_distance is not None and reference_center is not None:
                det_cx = (x1 + x2) / 2
                det_cy = (y1 + y2) / 2
                dist = math.sqrt((det_cx - reference_center[0]) ** 2 + (det_cy - reference_center[1]) ** 2)
                if dist > max_gate_distance:
                    continue

            detection_dicts.append({
                'bbox': (x1, y1, x2, y2),
                'track_id': track_id,
                'class_id': class_id
            })

        if not detection_dicts:
            return None

        # Find best appearance match
        best_match = self.appearance_model.find_best_match(
            frame,
            detection_dicts,
            self.selected_class_id
        )

        if best_match:
            # Convert back to standard detection format
            parsed = self._parse_detection([
                best_match['bbox'][0],  # x1
                best_match['bbox'][1],  # y1
                best_match['bbox'][2],  # x2
                best_match['bbox'][3],  # y2
                best_match['track_id'],
                0.0,  # placeholder confidence (we don't have it from appearance model)
                best_match['class_id']
            ])

            # Mark as appearance match and add similarity info
            parsed['appearance_match'] = True
            parsed['appearance_similarity'] = best_match.get('appearance_similarity', 0.0)
            parsed['recovered_id'] = best_match.get('recovered_id', self.selected_track_id)

            logging.info(f"[TRACKING] Appearance match: ID {self.selected_track_id}->{best_match['track_id']} "
                        f"(similarity={best_match.get('appearance_similarity', 0.0):.3f})")

            return parsed

        return None

    def _parse_detection(self, detection: List) -> Dict:
        """Parse detection list into dictionary."""
        x1, y1, x2, y2 = map(int, detection[:4])
        track_id = int(detection[4])
        confidence = float(detection[5])
        class_id = int(detection[6])
        center = ((x1 + x2) // 2, (y1 + y2) // 2)

        return {
            'track_id': track_id,
            'class_id': class_id,
            'bbox': (x1, y1, x2, y2),
            'confidence': confidence,
            'center': center,
            'iou_match': False,
            'match_iou': 1.0
        }

    def _on_detection_found(self, detection: Dict, frame: np.ndarray = None):
        """Update state when detection is found."""
        # Update track ID if it changed (spatial, distance, or appearance matching case)
        old_id = self.selected_track_id

        if detection.get('distance_match', False):
            new_id = detection['track_id']
            if old_id != new_id:
                logging.info(f"[TRACKING] ID switch (distance): {old_id}->{new_id} (dist={detection.get('match_distance', 0):.1f}px)")
                self.selected_track_id = new_id
        elif detection.get('iou_match', False):
            new_id = detection['track_id']
            if old_id != new_id:
                logging.info(f"[TRACKING] ID switch: {old_id}->{new_id} (IoU={detection['match_iou']:.2f})")
                self.selected_track_id = new_id
        elif detection.get('appearance_match', False):
            # Appearance-based re-identification
            recovered_id = detection.get('recovered_id', old_id)
            new_id = detection['track_id']
            logging.info(f"[TRACKING] Re-identified: recovered ID:{recovered_id}, new ID:{new_id} "
                        f"(similarity={detection.get('appearance_similarity', 0.0):.3f})")
            # Use the recovered ID to maintain tracking continuity
            self.selected_track_id = recovered_id

        # Update state
        self.last_known_bbox = detection['bbox']
        self.last_known_center = detection['center']
        self.last_detection_time = time.time()

        # Smooth confidence
        self.smoothed_confidence = (self.confidence_alpha * self.smoothed_confidence +
                                   (1 - self.confidence_alpha) * detection['confidence'])

        # Reset counter
        was_lost_frames = self.frames_since_detection
        self.frames_since_detection = 0

        # Update class history (Change 4)
        self.class_history.append(detection['class_id'])

        # Add to history
        self._add_to_history(
            detection['track_id'],
            detection['class_id'],
            detection['bbox'],
            detection['confidence'],
            detection['center']
        )

        # Update Kalman filter with measurement
        if self.kalman and self.enable_kalman:
            self.kalman.update(detection['bbox'])
            if was_lost_frames > 3:
                logging.info(f"[TRACKING] Kalman re-acquired after {was_lost_frames} frames lost")

        # Update motion predictor if available (legacy fallback)
        if self.motion_predictor and self.enable_prediction:
            self.motion_predictor.update(detection['bbox'], time.time())

        # Register/update appearance features if available
        if self.appearance_model and frame is not None:
            features = self.appearance_model.extract_features(frame, detection['bbox'])
            if features is not None:
                self.appearance_model.register_object(
                    self.selected_track_id,
                    detection['class_id'],
                    features
                )

    def _on_detection_lost(self):
        """Update state when detection is not found."""
        self.frames_since_detection += 1

        # Apply confidence decay for aging tracks
        self.smoothed_confidence = max(0.0, self.smoothed_confidence * (1.0 - self.confidence_decay_rate))

        # Update last_known_bbox from Kalman (continuous, no frame limit — Change 5)
        if self.kalman and self.enable_kalman:
            predicted_bbox = self.kalman.get_state()
            self.last_known_bbox = predicted_bbox
            self.last_known_center = self.kalman.get_predicted_center()
            logging.debug(f"[TrackingStateManager] Kalman prediction (frame {self.frames_since_detection}), "
                         f"uncertainty={self.kalman.get_position_uncertainty():.1f}, "
                         f"conf={self.smoothed_confidence:.2f}")
        elif self.motion_predictor and self.enable_prediction and self.frames_since_detection <= self.max_history:
            # Legacy fallback: MotionPredictor (limited to max_history frames)
            predicted_bbox = self.motion_predictor.predict_bbox(self.frames_since_detection)
            if predicted_bbox:
                self.last_known_bbox = predicted_bbox
                self.last_known_center = (
                    (predicted_bbox[0] + predicted_bbox[2]) // 2,
                    (predicted_bbox[1] + predicted_bbox[3]) // 2
                )
                logging.debug(f"[TrackingStateManager] MotionPredictor fallback (frame {self.frames_since_detection}), "
                            f"decayed confidence={self.smoothed_confidence:.2f}")

    def _handle_detection_loss(self, detections: List[List], compute_iou_func, frame: np.ndarray = None) -> Tuple[bool, Optional[Dict]]:
        """
        Graceful degradation with multi-level fallback strategy.

        With Kalman filter, prediction is continuous (no 5-frame limit).
        Search radius expands over time to handle unpredictable motion.

        Fallback Levels:
        1. Kalman prediction continues (already updated in _on_detection_lost)
        2. Lenient spatial + distance search with expanding radius
        3. Prediction-only mode with degraded confidence
        4. Signal loss after extended failure

        Args:
            detections: Current frame detections
            compute_iou_func: IoU computation function
            frame: Current frame (optional)

        Returns:
            Tuple of (is_tracking_active, result_dict or None)
        """
        enable_graceful_degradation = self.config.get('ENABLE_GRACEFUL_DEGRADATION', True)

        # Level 1: Within normal tolerance — Kalman prediction continues
        if self.frames_since_detection <= self.max_history:
            logging.debug(f"[TrackingStateManager] Temporary loss ({self.frames_since_detection}/{self.max_history} frames)")
            return True, None

        # Beyond normal tolerance — apply graceful degradation
        if enable_graceful_degradation:
            extended_tolerance = self.config.get('EXTENDED_TOLERANCE_FRAMES', 10)

            if self.frames_since_detection <= self.max_history + extended_tolerance:
                # Level 2a: Try lenient spatial matching with expanded search
                lenient_iou = max(0.10, self.spatial_iou_threshold * 0.4)
                lenient_match = self._match_by_spatial_lenient(detections, compute_iou_func, lenient_iou)

                if lenient_match:
                    logging.info(f"[TRACKING] Lenient spatial recovery: ID {self.selected_track_id}->{lenient_match['track_id']}")
                    self._on_detection_found(lenient_match, frame)
                    return True, lenient_match

                # Level 2b: Try distance matching with expanded radius
                if self.enable_distance_matching:
                    distance_match = self._match_by_distance(detections)
                    if distance_match:
                        logging.info(f"[TRACKING] Distance recovery: ID {self.selected_track_id}->{distance_match['track_id']}")
                        self._on_detection_found(distance_match, frame)
                        return True, distance_match

                # Level 2c: Try appearance matching with position gating
                if self.enable_appearance and frame is not None:
                    appearance_match = self._match_by_appearance(detections, frame)
                    if appearance_match:
                        logging.info(f"[TRACKING] Appearance recovery in extended tolerance")
                        self._on_detection_found(appearance_match, frame)
                        return True, appearance_match

            # Level 3: Prediction-only mode — continue with Kalman estimate
            if self.frames_since_detection <= self.max_history + extended_tolerance:
                predicted_bbox = None

                if self.kalman and self.enable_kalman:
                    predicted_bbox = self.kalman.get_state()
                elif self.motion_predictor and self.last_known_bbox:
                    predicted_bbox = self.motion_predictor.predict_bbox(self.frames_since_detection)

                if predicted_bbox:
                    degradation_factor = 1.0 - (self.frames_since_detection - self.max_history) / max(extended_tolerance, 1)
                    degraded_confidence = max(0.1, self.smoothed_confidence * degradation_factor)

                    prediction_result = {
                        'track_id': self.selected_track_id,
                        'class_id': self.selected_class_id,
                        'bbox': predicted_bbox,
                        'center': ((predicted_bbox[0] + predicted_bbox[2]) // 2,
                                  (predicted_bbox[1] + predicted_bbox[3]) // 2),
                        'confidence': degraded_confidence,
                        'prediction_only': True,
                        'frames_predicted': self.frames_since_detection
                    }
                    logging.debug(f"[TrackingStateManager] Prediction-only mode (frame {self.frames_since_detection}, conf={degraded_confidence:.2f})")
                    return True, prediction_result

        # Level 4: Complete loss — need re-selection
        if self.appearance_model and self.frames_since_detection == self.max_history + 1:
            self.appearance_model.mark_as_lost(self.selected_track_id)

        if self.frames_since_detection == self.max_history + 1:
            logging.info(f"[TRACKING] Lost: exceeded {self.max_history} frame tolerance (graceful degradation: {enable_graceful_degradation})")

        return False, {'need_reselection': True, 'frames_lost': self.frames_since_detection}

    def _match_by_spatial_lenient(self, detections: List[List], compute_iou_func, lenient_threshold: float) -> Optional[Dict]:
        """Match detection with lenient IoU threshold against predicted position."""
        reference_bbox = self._get_reference_bbox()
        if reference_bbox is None:
            return None

        # Expand search bbox based on frames lost (Change 7)
        if self.frames_since_detection > 0:
            expansion = min(self.frames_since_detection * self.search_expansion_rate, 3.0)
            reference_bbox = self._get_expanded_bbox(reference_bbox, expansion)

        best_match = None
        best_iou = 0.0

        for detection in detections:
            if len(detection) < 7:
                continue

            class_id = int(detection[6])

            # Flexible class matching
            if not self._is_class_compatible(class_id):
                continue

            x1, y1, x2, y2 = map(int, detection[:4])
            current_bbox = (x1, y1, x2, y2)
            iou = compute_iou_func(current_bbox, reference_bbox)

            if iou > best_iou and iou >= lenient_threshold:
                best_iou = iou
                best_match = self._parse_detection(detection)
                best_match['track_id'] = int(detection[4])
                best_match['iou_match'] = True
                best_match['match_iou'] = iou
                best_match['lenient_recovery'] = True

        return best_match

    def _add_to_history(self, track_id: int, class_id: int, bbox: Tuple, confidence: float, center: Tuple):
        """Add detection to tracking history."""
        self.tracking_history.append({
            'timestamp': time.time(),
            'frame': self.total_frames,
            'track_id': track_id,
            'class_id': class_id,
            'bbox': bbox,
            'confidence': confidence,
            'center': center
        })

    def clear(self):
        """Clear tracking state."""
        self.selected_track_id = None
        self.selected_class_id = None
        self.last_known_bbox = None
        self.last_known_center = None
        self.frames_since_detection = 0
        self.smoothed_confidence = 0.0
        self.tracking_history.clear()
        self.class_history.clear()
        self.kalman = None
        if self.motion_predictor:
            self.motion_predictor.reset()
        if self.appearance_model:
            self.appearance_model.clear()
        logging.info("[TrackingStateManager] Tracking cleared")

    def is_tracking_active(self) -> bool:
        """Check if currently tracking an object."""
        if self.selected_track_id is None:
            return False
        # With Kalman, we can track beyond max_history via graceful degradation
        extended_tolerance = self.config.get('EXTENDED_TOLERANCE_FRAMES', 10) if self.config.get('ENABLE_GRACEFUL_DEGRADATION', True) else 0
        return self.frames_since_detection <= self.max_history + extended_tolerance

    def get_tracking_info(self) -> Dict:
        """Get current tracking information."""
        info = {
            'track_id': self.selected_track_id,
            'class_id': self.selected_class_id,
            'bbox': self.last_known_bbox,
            'center': self.last_known_center,
            'confidence': self.smoothed_confidence,
            'frames_since_detection': self.frames_since_detection,
            'is_active': self.is_tracking_active(),
            'history_length': len(self.tracking_history),
            'total_frames': self.total_frames
        }
        if self.kalman and self.enable_kalman:
            info['kalman_uncertainty'] = self.kalman.get_position_uncertainty()
            info['kalman_velocity'] = self.kalman.get_velocity_magnitude()
        return info
