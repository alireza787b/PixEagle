# src/classes/tracking_state_manager.py
"""
Tracking State Manager for robust single-object tracking across frames.

Provides intelligent track-ID management with multiple fallback strategies
to handle common tracking challenges:
- ID switches by YOLO trackers (ByteTrack, BoT-SORT, etc.)
- Brief AND long occlusions (1-30+ frames)
- Detection failures and class-label flickering
- Re-identification after loss with position gating
- Out-of-frame detection and edge-based re-acquisition
- Configurable identity verification (aggressive / balanced / strict)

MATCHING HIERARCHY (hybrid strategy):
  1. ID match         -- exact track_id, flexible class_id
  2. Spatial match    -- IoU against Kalman-predicted position
  3. Distance match   -- center distance when IoU is zero (fast motion)
  4. Appearance match -- visual ReID with position gating

RE-ACQUISITION MODES:
  aggressive -- accept any compatible-class match instantly
  balanced   -- require size consistency + optional appearance after long loss
  strict     -- require appearance confirmation for all long-loss re-acquisitions

TRACKER COMPATIBILITY:
- Works with ANY Ultralytics tracker (ByteTrack, BoT-SORT, BoT-SORT+ReID)
- Tracker-agnostic: only requires [x1, y1, x2, y2, track_id, conf, class_id]
- Adds a robustness layer on top of built-in tracker capabilities

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

    Provides robust single-target tracking with:
    1. Primary: Track by ID (fast, accurate when IDs are stable)
    2. Fallback 1: Track by spatial proximity (IoU) against Kalman-predicted position
    3. Fallback 2: Track by center distance (handles fast motion where IoU=0)
    4. Fallback 3: Track by visual appearance with position gating
    5. Prediction: Kalman filter provides continuous position estimation during occlusion
    6. Identity verification gate with configurable strictness for re-acquisition
    """

    def __init__(self, config: dict, motion_predictor=None, appearance_model=None):
        """
        Initialize the tracking state manager.

        Args:
            config: Dictionary of SmartTracker configuration parameters
            motion_predictor: Optional MotionPredictor for legacy fallback
            appearance_model: Optional AppearanceModel for visual re-identification
        """
        self.config = config
        self.motion_predictor = motion_predictor
        self.appearance_model = appearance_model

        # ── Core tracking state ──────────────────────────────────────────
        self.selected_track_id: Optional[int] = None
        self.selected_class_id: Optional[int] = None
        self.last_known_bbox: Optional[Tuple[int, int, int, int]] = None
        self.last_known_center: Optional[Tuple[int, int]] = None
        self.last_detection_time: float = 0.0

        # ── Kalman filter (initialized on start_tracking) ───────────────
        self.kalman: Optional[KalmanBoxTracker] = None
        self.enable_kalman = config.get('ENABLE_KALMAN_FILTER', True)
        self.kalman_process_noise = config.get('KALMAN_PROCESS_NOISE', 1.0)
        self.kalman_measurement_noise = config.get('KALMAN_MEASUREMENT_NOISE', 1.0)

        # ── Tracking history ─────────────────────────────────────────────
        self.max_history = config.get('ID_LOSS_TOLERANCE_FRAMES', 5)
        self.tracking_history = deque(maxlen=max(self.max_history, 10))

        # ── Strategy configuration ───────────────────────────────────────
        self.tracking_strategy = config.get('TRACKING_STRATEGY', 'hybrid')
        self.spatial_iou_threshold = config.get('SPATIAL_IOU_THRESHOLD', 0.35)
        self.enable_prediction = config.get('ENABLE_PREDICTION_BUFFER', True)

        # ── Center-distance matching ─────────────────────────────────────
        self.enable_distance_matching = config.get('ENABLE_CENTER_DISTANCE_MATCHING', True)
        self.center_distance_threshold = config.get('CENTER_DISTANCE_THRESHOLD', 2.0)

        # ── Class flexibility ────────────────────────────────────────────
        self.class_match_flexible = config.get('CLASS_MATCH_FLEXIBLE', True)
        self.class_history_size = config.get('CLASS_HISTORY_SIZE', 10)
        self.class_history: deque = deque(maxlen=self.class_history_size)

        # ── Search expansion ─────────────────────────────────────────────
        self.search_expansion_rate = config.get('SEARCH_EXPANSION_RATE', 0.2)
        self.search_expansion_cap = config.get('SEARCH_EXPANSION_CAP', 2.0)
        self.lenient_search_expansion_cap = config.get('LENIENT_SEARCH_EXPANSION_CAP', 3.0)

        # ── Appearance position gating ───────────────────────────────────
        self.appearance_distance_gate = config.get('APPEARANCE_DISTANCE_GATE_FACTOR', 3.0)

        # ── Confidence smoothing and decay ───────────────────────────────
        self.confidence_alpha = config.get('CONFIDENCE_SMOOTHING_ALPHA', 0.8)
        self.smoothed_confidence = 0.0
        self.confidence_decay_rate = config.get('TRACK_CONFIDENCE_DECAY_RATE', 0.05)

        # ── Lenient recovery tuning ──────────────────────────────────────
        self.lenient_iou_scale = config.get('LENIENT_IOU_SCALE', 0.4)
        self.lenient_iou_floor = config.get('LENIENT_IOU_FLOOR', 0.10)
        self.min_prediction_confidence = config.get('MIN_PREDICTION_CONFIDENCE', 0.10)
        self.reacquisition_log_threshold = config.get('REACQUISITION_LOG_THRESHOLD', 3)

        # ── Re-acquisition identity verification ─────────────────────────
        self.reacquisition_mode = config.get('REACQUISITION_MODE', 'balanced')
        self.max_size_change_ratio = config.get('MAX_SIZE_CHANGE_RATIO', 2.5)
        self.reacquisition_confirm_frames = config.get('REACQUISITION_CONFIRM_FRAMES', 3)
        self.exit_edge_margin = config.get('EXIT_EDGE_MARGIN', 0.15)

        # ── Tentative re-acquisition state ───────────────────────────────
        self.is_tentative: bool = False
        self.tentative_frames: int = 0
        self.tentative_detection: Optional[Dict] = None

        # ── Out-of-frame state ───────────────────────────────────────────
        self.target_left_frame: bool = False
        self.exit_edge: Optional[str] = None
        self.frame_shape: Optional[Tuple[int, int]] = None

        # ── Frame counters ───────────────────────────────────────────────
        self.frames_since_detection = 0
        self.total_frames = 0

        # ── Appearance-based re-identification ───────────────────────────
        self.enable_appearance = config.get('ENABLE_APPEARANCE_MODEL', True) and appearance_model is not None

        # ── Confidence snapshot at moment of loss ────────────────────────
        self._confidence_at_loss: float = 0.0
        self._last_seen_bbox: Optional[Tuple[int, int, int, int]] = None

        logging.info(f"[TrackingStateManager] Initialized: strategy='{self.tracking_strategy}', "
                    f"tolerance={self.max_history}f, IoU={self.spatial_iou_threshold}, "
                    f"kalman={'on' if self.enable_kalman else 'off'}, "
                    f"distance={'on' if self.enable_distance_matching else 'off'}, "
                    f"class_flex={'on' if self.class_match_flexible else 'off'}, "
                    f"reacq_mode='{self.reacquisition_mode}'")
        if self.enable_appearance:
            logging.info(f"[TrackingStateManager] Appearance ReID: on "
                        f"(gate={self.appearance_distance_gate})")

    # =====================================================================
    # PUBLIC API
    # =====================================================================

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

        # Class history
        self.class_history.clear()
        self.class_history.append(class_id)

        # Reset re-acquisition state
        self._reset_tentative()
        self._reset_out_of_frame()
        self._confidence_at_loss = confidence
        self._last_seen_bbox = bbox

        # Initialize Kalman filter
        if self.enable_kalman:
            self.kalman = KalmanBoxTracker(
                bbox,
                process_noise_scale=self.kalman_process_noise,
                measurement_noise_scale=self.kalman_measurement_noise
            )
            logging.debug(f"[TrackingStateManager] Kalman filter initialized for ID:{track_id}")

        self._add_to_history(track_id, class_id, bbox, confidence, center)
        logging.debug(f"[TRACKING] Started: ID:{track_id} class:{class_id} conf={confidence:.2f}")

    def update_tracking(self, detections: List[List], compute_iou_func,
                       frame: np.ndarray = None) -> Tuple[bool, Optional[Dict]]:
        """
        Update tracking state with new detections.

        Args:
            detections: List of YOLO detections [x1, y1, x2, y2, track_id, conf, class_id]
            compute_iou_func: Function to compute IoU between two boxes
            frame: Current frame (BGR image), needed for appearance matching and OOF detection

        Returns:
            Tuple of (is_tracking_active, selected_detection_dict or None)
        """
        self.total_frames += 1

        # Increment appearance model frame counter
        if self.appearance_model:
            self.appearance_model.increment_frame()

        if self.selected_track_id is None:
            return False, None

        # Cache frame dimensions for out-of-frame checks
        if frame is not None:
            self.frame_shape = frame.shape[:2]  # (height, width)

        # Advance Kalman prediction (continuous, no frame limit)
        if self.kalman and self.enable_kalman:
            self.kalman.predict()

        # Check out-of-frame status
        self._update_out_of_frame_status()

        # ── Tentative confirmation logic ─────────────────────────────────
        # If we are in tentative state, try to confirm the candidate
        if self.is_tentative:
            return self._process_tentative_frame(detections, compute_iou_func, frame)

        # ── Standard matching hierarchy ──────────────────────────────────
        best_match = self._run_matching_hierarchy(detections, compute_iou_func, frame)

        # Update state based on match result
        if best_match:
            # Apply re-acquisition verification gate for long-loss matches
            if self.frames_since_detection >= self.max_history:
                verified = self._verify_reacquisition(best_match, frame)
                if not verified:
                    # Candidate rejected — treat as lost
                    self._on_detection_lost()
                    return self._handle_detection_loss(detections, compute_iou_func, frame)

                # Check if we need tentative confirmation
                if self._should_require_confirmation():
                    self._enter_tentative(best_match)
                    return True, self._make_tentative_result()

            self._on_detection_found(best_match, frame)
            return True, best_match
        else:
            self._on_detection_lost()
            return self._handle_detection_loss(detections, compute_iou_func, frame)

    def clear(self):
        """Clear all tracking state."""
        self.selected_track_id = None
        self.selected_class_id = None
        self.last_known_bbox = None
        self.last_known_center = None
        self.frames_since_detection = 0
        self.smoothed_confidence = 0.0
        self.tracking_history.clear()
        self.class_history.clear()
        self.kalman = None
        self._reset_tentative()
        self._reset_out_of_frame()
        self._confidence_at_loss = 0.0
        self._last_seen_bbox = None
        if self.motion_predictor:
            self.motion_predictor.reset()
        if self.appearance_model:
            self.appearance_model.clear()
        logging.info("[TrackingStateManager] Tracking cleared")

    def is_tracking_active(self) -> bool:
        """Check if currently tracking an object."""
        if self.selected_track_id is None:
            return False
        extended = self.config.get('EXTENDED_TOLERANCE_FRAMES', 10) if self.config.get('ENABLE_GRACEFUL_DEGRADATION', True) else 0
        return self.frames_since_detection <= self.max_history + extended

    def get_tracking_info(self) -> Dict:
        """Get current tracking information for HUD and diagnostics."""
        info = {
            'track_id': self.selected_track_id,
            'class_id': self.selected_class_id,
            'bbox': self.last_known_bbox,
            'center': self.last_known_center,
            'confidence': self.smoothed_confidence,
            'frames_since_detection': self.frames_since_detection,
            'is_active': self.is_tracking_active(),
            'history_length': len(self.tracking_history),
            'total_frames': self.total_frames,
            'reacquisition_mode': self.reacquisition_mode,
            'is_tentative': self.is_tentative,
            'target_left_frame': self.target_left_frame,
            'exit_edge': self.exit_edge,
        }
        if self.kalman and self.enable_kalman:
            info['kalman_uncertainty'] = self.kalman.get_position_uncertainty()
            info['kalman_velocity'] = self.kalman.get_velocity_magnitude()
        return info

    # =====================================================================
    # MATCHING HIERARCHY
    # =====================================================================

    def _run_matching_hierarchy(self, detections: List[List], compute_iou_func,
                                frame: np.ndarray = None) -> Optional[Dict]:
        """Execute the configured matching strategy and return best match or None."""
        if self.tracking_strategy == "id_only":
            return self._match_by_id(detections)

        if self.tracking_strategy == "spatial_only":
            return self._match_by_spatial(detections, compute_iou_func)

        # Default: hybrid strategy
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

        return best_match

    def _match_by_id(self, detections: List[List]) -> Optional[Dict]:
        """
        Match detection by exact track ID with flexible class matching.

        When class_match_flexible is enabled and track_id matches exactly,
        any class is accepted because YOLO's internal tracker already confirmed
        object identity through its own association logic.
        """
        for detection in detections:
            if len(detection) < 7:
                continue

            track_id = int(detection[4])
            class_id = int(detection[6])

            if track_id == self.selected_track_id:
                if self.class_match_flexible or class_id == self.selected_class_id:
                    return self._parse_detection(detection)

        return None

    def _match_by_spatial(self, detections: List[List], compute_iou_func) -> Optional[Dict]:
        """Match detection by IoU against Kalman-predicted position with search expansion."""
        reference_bbox = self._get_reference_bbox()
        if reference_bbox is None:
            return None

        # Expand search area based on frames lost
        if self.frames_since_detection > 0 and not self.target_left_frame:
            expansion = min(self.frames_since_detection * self.search_expansion_rate,
                          self.search_expansion_cap)
            reference_bbox = self._get_expanded_bbox(reference_bbox, expansion)

        best_match = None
        best_iou = 0.0

        for detection in detections:
            if len(detection) < 7:
                continue

            class_id = int(detection[6])
            if not self._is_class_compatible(class_id):
                continue

            x1, y1, x2, y2 = map(int, detection[:4])
            iou = compute_iou_func((x1, y1, x2, y2), reference_bbox)

            if iou > best_iou and iou >= self.spatial_iou_threshold:
                best_iou = iou
                best_match = self._parse_detection(detection)
                best_match['track_id'] = int(detection[4])
                best_match['iou_match'] = True
                best_match['match_iou'] = iou

        if best_match:
            logging.debug(f"[TRACKING] Spatial match: {self.selected_track_id}->{best_match['track_id']}, IoU={best_iou:.3f}")

        return best_match

    def _match_by_distance(self, detections: List[List]) -> Optional[Dict]:
        """
        Match detection by center distance (fallback when IoU is zero).

        Handles fast-moving objects displaced beyond IoU overlap.
        Threshold is adaptive based on object size and frames lost.
        """
        reference_center = self._get_reference_center()
        reference_bbox = self._get_reference_bbox()
        if reference_center is None or reference_bbox is None:
            return None

        ref_cx, ref_cy = reference_center
        rx1, ry1, rx2, ry2 = reference_bbox
        ref_diagonal = math.sqrt(max(rx2 - rx1, 1) ** 2 + max(ry2 - ry1, 1) ** 2)

        # Adaptive threshold expands with frames lost
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
                best_match['iou_match'] = True
                best_match['match_iou'] = 0.0
                best_match['distance_match'] = True
                best_match['match_distance'] = dist

        if best_match:
            logging.info(f"[TRACKING] Distance match: {self.selected_track_id}->{best_match['track_id']}, "
                        f"dist={best_dist:.1f}px (max={max_distance:.1f}px)")

        return best_match

    def _match_by_appearance(self, detections: List[List], frame: np.ndarray) -> Optional[Dict]:
        """Match detection by visual appearance with position gating."""
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
                max_gate_distance = ref_diagonal * self.appearance_distance_gate * (
                    1.0 + self.frames_since_detection * self.search_expansion_rate
                )

        # Build candidate list with position gate applied
        detection_dicts = []
        for detection in detections:
            if len(detection) < 7:
                continue

            x1, y1, x2, y2 = map(int, detection[:4])
            track_id = int(detection[4])
            class_id = int(detection[6])

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

        best_match = self.appearance_model.find_best_match(
            frame, detection_dicts, self.selected_class_id
        )

        if best_match:
            parsed = self._parse_detection([
                best_match['bbox'][0], best_match['bbox'][1],
                best_match['bbox'][2], best_match['bbox'][3],
                best_match['track_id'], 0.0, best_match['class_id']
            ])
            parsed['appearance_match'] = True
            parsed['appearance_similarity'] = best_match.get('appearance_similarity', 0.0)
            parsed['recovered_id'] = best_match.get('recovered_id', self.selected_track_id)

            logging.info(f"[TRACKING] Appearance match: {self.selected_track_id}->{best_match['track_id']} "
                        f"(similarity={best_match.get('appearance_similarity', 0.0):.3f})")
            return parsed

        return None

    # =====================================================================
    # RE-ACQUISITION IDENTITY VERIFICATION (Changes B, C, D)
    # =====================================================================

    def _verify_reacquisition(self, detection: Dict, frame: np.ndarray = None) -> bool:
        """
        Gate re-acquisition candidates after long loss based on REACQUISITION_MODE.

        Only called when frames_since_detection >= max_history (long loss).

        Args:
            detection: Candidate detection dict
            frame: Current frame for appearance verification

        Returns:
            True if candidate passes identity verification
        """
        mode = self.reacquisition_mode

        # Aggressive: accept any compatible-class match instantly
        if mode == "aggressive":
            return True

        det_bbox = detection['bbox']

        # Size consistency check (balanced + strict)
        if not self._check_size_consistency(det_bbox):
            logging.info(f"[TRACKING] Re-acquisition REJECTED (size inconsistency): "
                        f"mode={mode}, detection_bbox={det_bbox}")
            return False

        # Out-of-frame edge proximity check
        if self.target_left_frame and not self._is_near_exit_edge(det_bbox):
            logging.info(f"[TRACKING] Re-acquisition REJECTED (not near exit edge '{self.exit_edge}'): "
                        f"mode={mode}, detection_bbox={det_bbox}")
            return False

        # Strict mode: require appearance confirmation for ALL re-acquisitions
        if mode == "strict":
            if not self._verify_appearance(detection, frame):
                logging.info(f"[TRACKING] Re-acquisition REJECTED (appearance mismatch): "
                            f"mode=strict, detection_bbox={det_bbox}")
                return False

        # Balanced mode: require appearance for distance-only matches (no IoU overlap)
        elif mode == "balanced":
            is_distance_only = detection.get('distance_match', False)
            is_lenient = detection.get('lenient_recovery', False)
            if (is_distance_only or is_lenient) and self.enable_appearance:
                if not self._verify_appearance(detection, frame):
                    logging.info(f"[TRACKING] Re-acquisition REJECTED (appearance mismatch on distance/lenient): "
                                f"mode=balanced, detection_bbox={det_bbox}")
                    return False

        logging.info(f"[TRACKING] Re-acquisition VERIFIED: mode={mode}, bbox={det_bbox}")
        return True

    def _check_size_consistency(self, detection_bbox: Tuple[int, int, int, int]) -> bool:
        """
        Check if detection size is consistent with the tracked object.

        Compares detection area with the last known area from Kalman state.
        Rejects if area ratio exceeds MAX_SIZE_CHANGE_RATIO.

        Returns:
            True if size is consistent
        """
        reference_bbox = self._get_reference_bbox()
        if reference_bbox is None:
            return True  # No reference — cannot check, allow

        rx1, ry1, rx2, ry2 = reference_bbox
        ref_area = max((rx2 - rx1) * (ry2 - ry1), 1.0)

        dx1, dy1, dx2, dy2 = detection_bbox
        det_area = max((dx2 - dx1) * (dy2 - dy1), 1.0)

        ratio = det_area / ref_area
        inv_ratio = 1.0 / self.max_size_change_ratio

        if ratio > self.max_size_change_ratio or ratio < inv_ratio:
            logging.debug(f"[TRACKING] Size check FAILED: ratio={ratio:.2f} "
                         f"(allowed [{inv_ratio:.2f}, {self.max_size_change_ratio:.1f}])")
            return False

        return True

    def _verify_appearance(self, detection: Dict, frame: np.ndarray = None) -> bool:
        """
        Verify candidate identity via appearance similarity.

        Returns True if appearance model confirms match or is unavailable.
        """
        # If detection already has appearance match info, use it
        if detection.get('appearance_match', False):
            threshold = self.config.get('APPEARANCE_MATCH_THRESHOLD', 0.7)
            similarity = detection.get('appearance_similarity', 0.0)
            return similarity >= threshold

        # Try to compute appearance similarity if we have a frame
        if frame is None or not self.appearance_model:
            # No frame or no model — cannot verify, pass through in balanced, fail in strict
            return self.reacquisition_mode != "strict"

        features = self.appearance_model.extract_features(frame, detection['bbox'])
        if features is None:
            return self.reacquisition_mode != "strict"

        similarity = self.appearance_model.compare_features(
            self.selected_track_id, features
        ) if hasattr(self.appearance_model, 'compare_features') else None

        if similarity is None:
            return self.reacquisition_mode != "strict"

        threshold = self.config.get('APPEARANCE_MATCH_THRESHOLD', 0.7)
        return similarity >= threshold

    def _should_require_confirmation(self) -> bool:
        """Check if tentative confirmation period is needed."""
        if self.reacquisition_mode == "aggressive":
            return False
        if self.reacquisition_confirm_frames <= 1:
            return False
        return self.frames_since_detection >= self.max_history

    # =====================================================================
    # TENTATIVE STATE MANAGEMENT (Change D)
    # =====================================================================

    def _enter_tentative(self, detection: Dict):
        """Enter tentative re-acquisition state with a candidate."""
        self.is_tentative = True
        self.tentative_frames = 1
        self.tentative_detection = detection
        logging.info(f"[TRACKING] Tentative re-acquisition started: "
                    f"candidate ID:{detection['track_id']}, "
                    f"need {self.reacquisition_confirm_frames} consecutive frames")

    def _reset_tentative(self):
        """Reset tentative state."""
        self.is_tentative = False
        self.tentative_frames = 0
        self.tentative_detection = None

    def _process_tentative_frame(self, detections: List[List], compute_iou_func,
                                  frame: np.ndarray = None) -> Tuple[bool, Optional[Dict]]:
        """
        Process a frame while in tentative re-acquisition state.

        The candidate must be re-detected for REACQUISITION_CONFIRM_FRAMES consecutive
        frames to be confirmed. If lost, tentative state is rejected.
        """
        # Try to re-detect the tentative candidate
        candidate = self.tentative_detection
        if candidate is None:
            self._reset_tentative()
            self._on_detection_lost()
            return self._handle_detection_loss(detections, compute_iou_func, frame)

        candidate_bbox = candidate['bbox']
        candidate_center = candidate['center']

        # Search for the candidate near its last tentative position
        best_match = None
        best_dist = float('inf')

        for detection in detections:
            if len(detection) < 7:
                continue

            class_id = int(detection[6])
            if not self._is_class_compatible(class_id):
                continue

            x1, y1, x2, y2 = map(int, detection[:4])
            det_cx = (x1 + x2) / 2
            det_cy = (y1 + y2) / 2
            cand_cx, cand_cy = candidate_center

            dist = math.sqrt((det_cx - cand_cx) ** 2 + (det_cy - cand_cy) ** 2)

            # Use a tight search radius around the tentative position
            ref_w = candidate_bbox[2] - candidate_bbox[0]
            ref_h = candidate_bbox[3] - candidate_bbox[1]
            max_dist = math.sqrt(ref_w ** 2 + ref_h ** 2) * 1.5

            if dist < best_dist and dist <= max_dist:
                best_dist = dist
                best_match = self._parse_detection(detection)

        if best_match:
            self.tentative_frames += 1
            self.tentative_detection = best_match

            if self.tentative_frames >= self.reacquisition_confirm_frames:
                # Confirmed — promote to active tracking
                logging.info(f"[TRACKING] Re-acquisition CONFIRMED after {self.tentative_frames} frames")
                self._reset_tentative()
                self._on_detection_found(best_match, frame)
                return True, best_match
            else:
                # Still tentative
                logging.debug(f"[TRACKING] Tentative frame {self.tentative_frames}/{self.reacquisition_confirm_frames}")
                return True, self._make_tentative_result()
        else:
            # Candidate lost during confirmation — reject
            logging.info(f"[TRACKING] Tentative re-acquisition REJECTED (lost at frame {self.tentative_frames})")
            self._reset_tentative()
            self._on_detection_lost()
            return self._handle_detection_loss(detections, compute_iou_func, frame)

    def _make_tentative_result(self) -> Dict:
        """Build a result dict representing tentative (unconfirmed) tracking."""
        candidate = self.tentative_detection
        predicted_bbox = self._get_reference_bbox() or self.last_known_bbox
        if candidate:
            return {
                'track_id': self.selected_track_id,
                'class_id': self.selected_class_id,
                'bbox': candidate['bbox'],
                'center': candidate['center'],
                'confidence': self.smoothed_confidence * 0.5,
                'tentative': True,
                'tentative_frames': self.tentative_frames,
                'tentative_required': self.reacquisition_confirm_frames,
            }
        return {
            'track_id': self.selected_track_id,
            'class_id': self.selected_class_id,
            'bbox': predicted_bbox,
            'center': self.last_known_center,
            'confidence': self.smoothed_confidence * 0.5,
            'tentative': True,
            'prediction_only': True,
        }

    # =====================================================================
    # OUT-OF-FRAME DETECTION (Change E)
    # =====================================================================

    def _update_out_of_frame_status(self):
        """Check if Kalman-predicted position has left the frame."""
        if self.frame_shape is None:
            return

        if self.frames_since_detection == 0:
            # Currently detected — reset OOF state
            if self.target_left_frame:
                logging.info(f"[TRACKING] Target returned to frame (was off via '{self.exit_edge}')")
                self._reset_out_of_frame()
            return

        edge = self._check_out_of_frame(self.frame_shape)
        if edge is not None and not self.target_left_frame:
            self.target_left_frame = True
            self.exit_edge = edge
            center = self._get_reference_center()
            logging.info(f"[TRACKING] Target left frame via {edge.upper()} edge at {center}")

    def _check_out_of_frame(self, frame_shape: Tuple[int, int]) -> Optional[str]:
        """
        Check if predicted center is outside frame boundaries.

        Args:
            frame_shape: (height, width)

        Returns:
            Edge name ("left", "right", "top", "bottom") or None if inside frame
        """
        center = self._get_reference_center()
        if center is None:
            return None

        h, w = frame_shape
        cx, cy = center
        margin = 5  # Small pixel margin to avoid flickering at exact edge

        if cx < -margin:
            return "left"
        if cx > w + margin:
            return "right"
        if cy < -margin:
            return "top"
        if cy > h + margin:
            return "bottom"

        return None

    def _is_near_exit_edge(self, detection_bbox: Tuple[int, int, int, int]) -> bool:
        """
        Check if a detection is near the edge where the target exited.

        Args:
            detection_bbox: Candidate bbox (x1, y1, x2, y2)

        Returns:
            True if detection is near the exit edge
        """
        if not self.target_left_frame or self.exit_edge is None or self.frame_shape is None:
            return True  # No OOF info — allow

        h, w = self.frame_shape
        dx1, dy1, dx2, dy2 = detection_bbox
        det_cx = (dx1 + dx2) / 2
        det_cy = (dy1 + dy2) / 2

        margin_x = w * self.exit_edge_margin
        margin_y = h * self.exit_edge_margin

        if self.exit_edge == "left":
            return det_cx < margin_x
        elif self.exit_edge == "right":
            return det_cx > w - margin_x
        elif self.exit_edge == "top":
            return det_cy < margin_y
        elif self.exit_edge == "bottom":
            return det_cy > h - margin_y

        return True

    def _reset_out_of_frame(self):
        """Reset out-of-frame state."""
        self.target_left_frame = False
        self.exit_edge = None

    # =====================================================================
    # STATE UPDATE HANDLERS
    # =====================================================================

    def _on_detection_found(self, detection: Dict, frame: np.ndarray = None):
        """Update state when a detection match is confirmed."""
        old_id = self.selected_track_id
        was_lost_frames = self.frames_since_detection

        # Handle ID switches from different match types
        if detection.get('distance_match', False):
            new_id = detection['track_id']
            if old_id != new_id:
                logging.info(f"[TRACKING] ID switch (distance): {old_id}->{new_id} "
                           f"(dist={detection.get('match_distance', 0):.1f}px)")
                self.selected_track_id = new_id
        elif detection.get('iou_match', False):
            new_id = detection['track_id']
            if old_id != new_id:
                logging.info(f"[TRACKING] ID switch (spatial): {old_id}->{new_id} "
                           f"(IoU={detection['match_iou']:.2f})")
                self.selected_track_id = new_id
        elif detection.get('appearance_match', False):
            recovered_id = detection.get('recovered_id', old_id)
            new_id = detection['track_id']
            logging.info(f"[TRACKING] Re-identified: recovered ID:{recovered_id}, "
                        f"new ID:{new_id} (similarity={detection.get('appearance_similarity', 0.0):.3f})")
            self.selected_track_id = recovered_id

        # Update core state
        self.last_known_bbox = detection['bbox']
        self.last_known_center = detection['center']
        self.last_detection_time = time.time()
        self._last_seen_bbox = detection['bbox']

        # Smooth confidence
        self.smoothed_confidence = (self.confidence_alpha * self.smoothed_confidence +
                                   (1 - self.confidence_alpha) * detection['confidence'])
        self._confidence_at_loss = self.smoothed_confidence

        # Reset loss counter
        self.frames_since_detection = 0

        # Update class history
        self.class_history.append(detection['class_id'])

        # Add to history
        self._add_to_history(
            detection['track_id'], detection['class_id'],
            detection['bbox'], detection['confidence'], detection['center']
        )

        # Update Kalman filter with measurement
        if self.kalman and self.enable_kalman:
            self.kalman.update(detection['bbox'])
            if was_lost_frames > self.reacquisition_log_threshold:
                logging.info(f"[TRACKING] Re-acquired after {was_lost_frames} frames lost")

        # Update legacy motion predictor
        if self.motion_predictor and self.enable_prediction:
            self.motion_predictor.update(detection['bbox'], time.time())

        # Register/update appearance features
        if self.appearance_model and frame is not None:
            features = self.appearance_model.extract_features(frame, detection['bbox'])
            if features is not None:
                self.appearance_model.register_object(
                    self.selected_track_id, detection['class_id'], features
                )

        # Reset OOF state on confirmed detection
        if self.target_left_frame:
            logging.info(f"[TRACKING] Target re-acquired after leaving frame via '{self.exit_edge}'")
            self._reset_out_of_frame()

    def _on_detection_lost(self):
        """Update state when detection is not found in current frame."""
        self.frames_since_detection += 1

        # Snapshot confidence at the moment of first loss
        if self.frames_since_detection == 1:
            self._confidence_at_loss = self.smoothed_confidence
            self._last_seen_bbox = self.last_known_bbox

        # Apply confidence decay
        self.smoothed_confidence = max(0.0, self.smoothed_confidence * (1.0 - self.confidence_decay_rate))

        # Update predicted position from Kalman (continuous, no frame limit)
        if self.kalman and self.enable_kalman:
            predicted_bbox = self.kalman.get_state()
            self.last_known_bbox = predicted_bbox
            self.last_known_center = self.kalman.get_predicted_center()
            logging.debug(f"[TRACKING] Kalman prediction (frame {self.frames_since_detection}), "
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

    # =====================================================================
    # GRACEFUL DEGRADATION & FAILURE REPORTING (Changes A, F)
    # =====================================================================

    def _handle_detection_loss(self, detections: List[List], compute_iou_func,
                               frame: np.ndarray = None) -> Tuple[bool, Optional[Dict]]:
        """
        Multi-level fallback strategy when primary matching fails.

        With Kalman filter, prediction is continuous (no frame limit).
        Search radius expands over time. Re-acquisition candidates are
        verified through the identity gate based on REACQUISITION_MODE.

        Fallback Levels:
        1. Within normal tolerance — Kalman prediction continues
        2. Extended tolerance — lenient spatial + distance + appearance search
        3. Prediction-only — Kalman estimate with degraded confidence
        4. Complete loss — structured failure report

        Returns:
            Tuple of (is_tracking_active, result_dict or None)
        """
        enable_graceful_degradation = self.config.get('ENABLE_GRACEFUL_DEGRADATION', True)

        # Level 1: Within normal tolerance — prediction continues
        if self.frames_since_detection <= self.max_history:
            logging.debug(f"[TRACKING] Temporary loss ({self.frames_since_detection}/{self.max_history} frames)")
            return True, None

        # Beyond normal tolerance — apply graceful degradation
        if enable_graceful_degradation:
            extended_tolerance = self.config.get('EXTENDED_TOLERANCE_FRAMES', 10)

            if self.frames_since_detection <= self.max_history + extended_tolerance:
                # Level 2a: Lenient spatial matching with expanded search
                lenient_iou = max(self.lenient_iou_floor,
                                self.spatial_iou_threshold * self.lenient_iou_scale)
                lenient_match = self._match_by_spatial_lenient(detections, compute_iou_func, lenient_iou)

                if lenient_match:
                    if self._verify_reacquisition(lenient_match, frame):
                        if self._should_require_confirmation():
                            self._enter_tentative(lenient_match)
                            return True, self._make_tentative_result()
                        logging.info(f"[TRACKING] Lenient spatial recovery: "
                                    f"{self.selected_track_id}->{lenient_match['track_id']}")
                        self._on_detection_found(lenient_match, frame)
                        return True, lenient_match

                # Level 2b: Distance matching with expanded radius
                if self.enable_distance_matching:
                    distance_match = self._match_by_distance(detections)
                    if distance_match:
                        if self._verify_reacquisition(distance_match, frame):
                            if self._should_require_confirmation():
                                self._enter_tentative(distance_match)
                                return True, self._make_tentative_result()
                            logging.info(f"[TRACKING] Distance recovery: "
                                        f"{self.selected_track_id}->{distance_match['track_id']}")
                            self._on_detection_found(distance_match, frame)
                            return True, distance_match

                # Level 2c: Appearance matching with position gating
                if self.enable_appearance and frame is not None:
                    appearance_match = self._match_by_appearance(detections, frame)
                    if appearance_match:
                        if self._verify_reacquisition(appearance_match, frame):
                            if self._should_require_confirmation():
                                self._enter_tentative(appearance_match)
                                return True, self._make_tentative_result()
                            logging.info(f"[TRACKING] Appearance recovery in extended tolerance")
                            self._on_detection_found(appearance_match, frame)
                            return True, appearance_match

            # Level 3: Prediction-only mode
            if self.frames_since_detection <= self.max_history + extended_tolerance:
                predicted_bbox = None

                if self.kalman and self.enable_kalman:
                    predicted_bbox = self.kalman.get_state()
                elif self.motion_predictor and self.last_known_bbox:
                    predicted_bbox = self.motion_predictor.predict_bbox(self.frames_since_detection)

                if predicted_bbox:
                    degradation_factor = 1.0 - (self.frames_since_detection - self.max_history) / max(extended_tolerance, 1)
                    degraded_confidence = max(self.min_prediction_confidence,
                                            self.smoothed_confidence * degradation_factor)

                    prediction_result = {
                        'track_id': self.selected_track_id,
                        'class_id': self.selected_class_id,
                        'bbox': predicted_bbox,
                        'center': ((predicted_bbox[0] + predicted_bbox[2]) // 2,
                                  (predicted_bbox[1] + predicted_bbox[3]) // 2),
                        'confidence': degraded_confidence,
                        'prediction_only': True,
                        'frames_predicted': self.frames_since_detection,
                    }
                    logging.debug(f"[TRACKING] Prediction-only (frame {self.frames_since_detection}, "
                                 f"conf={degraded_confidence:.2f})")
                    return True, prediction_result

        # Level 4: Complete loss — structured failure report
        if self.appearance_model and self.frames_since_detection == self.max_history + 1:
            self.appearance_model.mark_as_lost(self.selected_track_id)

        if self.frames_since_detection == self.max_history + 1:
            logging.info(f"[TRACKING] LOST: exceeded {self.max_history}f tolerance "
                        f"(graceful_degradation={enable_graceful_degradation})")

        return False, self._build_loss_report(detections)

    def _build_loss_report(self, detections: List[List]) -> Dict:
        """
        Build structured failure report for upstream systems and HUD.

        Includes loss reason, positions, and diagnostic info.
        """
        # Determine loss reason
        if self.target_left_frame:
            loss_reason = "left_frame"
        elif len(detections) == 0:
            loss_reason = "detector_failure"
        elif len(detections) > 0:
            loss_reason = "occluded"
        else:
            loss_reason = "unknown"

        predicted_bbox = None
        if self.kalman and self.enable_kalman:
            predicted_bbox = self.kalman.get_state()

        return {
            'need_reselection': True,
            'loss_reason': loss_reason,
            'last_seen_bbox': self._last_seen_bbox,
            'predicted_bbox': predicted_bbox,
            'frames_lost': self.frames_since_detection,
            'confidence_at_loss': self._confidence_at_loss,
            'exit_edge': self.exit_edge,
            'search_exhausted': True,
            'reacquisition_mode': self.reacquisition_mode,
        }

    # =====================================================================
    # LENIENT SPATIAL MATCHING
    # =====================================================================

    def _match_by_spatial_lenient(self, detections: List[List], compute_iou_func,
                                  lenient_threshold: float) -> Optional[Dict]:
        """Match detection with lenient IoU threshold against predicted position."""
        reference_bbox = self._get_reference_bbox()
        if reference_bbox is None:
            return None

        # Expand search area (wider cap for lenient mode)
        if self.frames_since_detection > 0 and not self.target_left_frame:
            expansion = min(self.frames_since_detection * self.search_expansion_rate,
                          self.lenient_search_expansion_cap)
            reference_bbox = self._get_expanded_bbox(reference_bbox, expansion)

        best_match = None
        best_iou = 0.0

        for detection in detections:
            if len(detection) < 7:
                continue

            class_id = int(detection[6])
            if not self._is_class_compatible(class_id):
                continue

            x1, y1, x2, y2 = map(int, detection[:4])
            iou = compute_iou_func((x1, y1, x2, y2), reference_bbox)

            if iou > best_iou and iou >= lenient_threshold:
                best_iou = iou
                best_match = self._parse_detection(detection)
                best_match['track_id'] = int(detection[4])
                best_match['iou_match'] = True
                best_match['match_iou'] = iou
                best_match['lenient_recovery'] = True

        return best_match

    # =====================================================================
    # UTILITY METHODS
    # =====================================================================

    def _is_class_compatible(self, class_id: int) -> bool:
        """
        Check if a detection's class is compatible with the tracked object.

        With CLASS_MATCH_FLEXIBLE enabled, allows class flickering (e.g. car<->truck)
        by accepting any class observed in the recent history buffer.
        """
        if class_id == self.selected_class_id:
            return True
        if self.class_match_flexible and len(self.class_history) > 0:
            return class_id in self.class_history
        return False

    def _get_reference_bbox(self) -> Optional[Tuple[int, int, int, int]]:
        """Get best reference bbox (Kalman-predicted or last known)."""
        if self.kalman and self.enable_kalman:
            return self.kalman.get_state()
        return self.last_known_bbox

    def _get_reference_center(self) -> Optional[Tuple[int, int]]:
        """Get best reference center (Kalman-predicted or last known)."""
        if self.kalman and self.enable_kalman:
            return self.kalman.get_predicted_center()
        return self.last_known_center

    def _get_expanded_bbox(self, bbox: Tuple[int, int, int, int],
                           expansion: float) -> Tuple[int, int, int, int]:
        """Expand a bounding box by a factor for search radius expansion."""
        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        dx = int(w * expansion / 2)
        dy = int(h * expansion / 2)
        return (x1 - dx, y1 - dy, x2 + dx, y2 + dy)

    def _parse_detection(self, detection: List) -> Dict:
        """Parse a raw detection list into a standardized dictionary."""
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

    def _add_to_history(self, track_id: int, class_id: int, bbox: Tuple,
                        confidence: float, center: Tuple):
        """Add detection to tracking history ring buffer."""
        self.tracking_history.append({
            'timestamp': time.time(),
            'frame': self.total_frames,
            'track_id': track_id,
            'class_id': class_id,
            'bbox': bbox,
            'confidence': confidence,
            'center': center
        })
