# src/classes/tracking_state_manager.py
"""
Tracking State Manager for robust object tracking across frames.

This module provides intelligent track ID management with multiple fallback strategies
to handle common tracking challenges like:
- ID switches by YOLO/ByteTrack
- Brief occlusions (1-5 frames)
- Detection failures
- Re-identification after loss

Author: PixEagle Team
Date: 2025
"""

import logging
import time
from collections import deque
from typing import Optional, Tuple, List, Dict


class TrackingStateManager:
    """
    Manages tracking state with hybrid ID + spatial matching strategies.

    Provides robust tracking by:
    1. Primary: Track by ID (fast, accurate when IDs are stable)
    2. Fallback: Track by spatial proximity (IoU matching)
    3. Prediction: Estimate position during brief occlusions
    """

    def __init__(self, config: dict, motion_predictor=None):
        """
        Initialize the tracking state manager.

        Args:
            config: Dictionary of SmartTracker configuration parameters
            motion_predictor: Optional motion predictor for occlusion handling
        """
        self.config = config
        self.motion_predictor = motion_predictor

        # Core tracking state
        self.selected_track_id: Optional[int] = None
        self.selected_class_id: Optional[int] = None
        self.last_known_bbox: Optional[Tuple[int, int, int, int]] = None
        self.last_known_center: Optional[Tuple[int, int]] = None
        self.last_detection_time: float = 0.0

        # Tracking history for temporal consistency
        self.max_history = self.config.get('ID_LOSS_TOLERANCE_FRAMES', 5)
        self.tracking_history = deque(maxlen=self.max_history)

        # Strategy configuration
        self.tracking_strategy = self.config.get('TRACKING_STRATEGY', 'hybrid')
        self.spatial_iou_threshold = self.config.get('SPATIAL_IOU_THRESHOLD', 0.35)
        self.enable_prediction = self.config.get('ENABLE_PREDICTION_BUFFER', True)

        # Confidence smoothing
        self.confidence_alpha = self.config.get('CONFIDENCE_SMOOTHING_ALPHA', 0.8)
        self.smoothed_confidence = 0.0

        # Frame counter
        self.frames_since_detection = 0
        self.total_frames = 0

        logging.info(f"[TrackingStateManager] Initialized with strategy='{self.tracking_strategy}', "
                    f"tolerance={self.max_history} frames, IoU threshold={self.spatial_iou_threshold}")

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

        # Add to history
        self._add_to_history(track_id, class_id, bbox, confidence, center)

        logging.info(f"[TrackingStateManager] Started tracking: ID={track_id}, Class={class_id}, Confidence={confidence:.3f}")

    def update_tracking(self, detections: List[List], compute_iou_func) -> Tuple[bool, Optional[Dict]]:
        """
        Update tracking state with new detections.

        Args:
            detections: List of YOLO detections (each is [x1, y1, x2, y2, track_id, conf, class_id])
            compute_iou_func: Function to compute IoU between two boxes

        Returns:
            Tuple of (is_tracking_active, selected_detection_dict or None)
        """
        self.total_frames += 1

        if self.selected_track_id is None:
            return False, None

        # Try to find the selected object using configured strategy
        best_match = None

        if self.tracking_strategy == "id_only":
            best_match = self._match_by_id(detections)
        elif self.tracking_strategy == "spatial_only":
            best_match = self._match_by_spatial(detections, compute_iou_func)
        elif self.tracking_strategy == "hybrid":
            # Try ID first, fall back to spatial
            best_match = self._match_by_id(detections)
            if best_match is None and self.frames_since_detection < self.max_history:
                best_match = self._match_by_spatial(detections, compute_iou_func)

        # Update state based on match result
        if best_match:
            self._on_detection_found(best_match)
            return True, best_match
        else:
            self._on_detection_lost()

            # Check if we've exceeded tolerance
            if self.frames_since_detection > self.max_history:
                logging.info(f"[TrackingStateManager] Lost track (exceeded {self.max_history} frame tolerance)")
                return False, None
            else:
                # Still within tolerance, maintain tracking
                logging.debug(f"[TrackingStateManager] Temporary loss ({self.frames_since_detection}/{self.max_history} frames)")
                return True, None

    def _match_by_id(self, detections: List[List]) -> Optional[Dict]:
        """Match detection by exact track ID."""
        for detection in detections:
            if len(detection) < 7:
                continue

            track_id = int(detection[4])
            class_id = int(detection[6])

            # Match by ID and class
            if track_id == self.selected_track_id and class_id == self.selected_class_id:
                return self._parse_detection(detection)

        return None

    def _match_by_spatial(self, detections: List[List], compute_iou_func) -> Optional[Dict]:
        """Match detection by spatial proximity (IoU)."""
        if self.last_known_bbox is None:
            return None

        best_match = None
        best_iou = 0.0

        for detection in detections:
            if len(detection) < 7:
                continue

            class_id = int(detection[6])

            # Only consider same class
            if class_id != self.selected_class_id:
                continue

            # Compute IoU with last known position
            x1, y1, x2, y2 = map(int, detection[:4])
            current_bbox = (x1, y1, x2, y2)
            iou = compute_iou_func(current_bbox, self.last_known_bbox)

            if iou > best_iou and iou >= self.spatial_iou_threshold:
                best_iou = iou
                best_match = self._parse_detection(detection)
                # Update track ID if it changed
                best_match['track_id'] = int(detection[4])
                best_match['iou_match'] = True
                best_match['match_iou'] = iou

        if best_match:
            logging.debug(f"[TrackingStateManager] Spatial match: ID {self.selected_track_id}→{best_match['track_id']}, IoU={best_iou:.3f}")

        return best_match

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

    def _on_detection_found(self, detection: Dict):
        """Update state when detection is found."""
        # Update track ID if it changed (spatial matching case)
        if detection.get('iou_match', False):
            old_id = self.selected_track_id
            new_id = detection['track_id']
            if old_id != new_id:
                logging.info(f"[TrackingStateManager] ID switch detected: {old_id}→{new_id} (IoU={detection['match_iou']:.3f})")
                self.selected_track_id = new_id

        # Update state
        self.last_known_bbox = detection['bbox']
        self.last_known_center = detection['center']
        self.last_detection_time = time.time()

        # Smooth confidence
        self.smoothed_confidence = (self.confidence_alpha * self.smoothed_confidence +
                                   (1 - self.confidence_alpha) * detection['confidence'])

        # Reset counter
        self.frames_since_detection = 0

        # Add to history
        self._add_to_history(
            detection['track_id'],
            detection['class_id'],
            detection['bbox'],
            detection['confidence'],
            detection['center']
        )

        # Update motion predictor if available
        if self.motion_predictor and self.enable_prediction:
            self.motion_predictor.update(detection['bbox'], time.time())

    def _on_detection_lost(self):
        """Update state when detection is not found."""
        self.frames_since_detection += 1

        # Try motion prediction if enabled and within tolerance
        if self.motion_predictor and self.enable_prediction and self.frames_since_detection <= self.max_history:
            predicted_bbox = self.motion_predictor.predict_bbox(self.frames_since_detection)
            if predicted_bbox:
                self.last_known_bbox = predicted_bbox
                self.last_known_center = (
                    (predicted_bbox[0] + predicted_bbox[2]) // 2,
                    (predicted_bbox[1] + predicted_bbox[3]) // 2
                )
                logging.debug(f"[TrackingStateManager] Using predicted position (frame {self.frames_since_detection})")

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
        if self.motion_predictor:
            self.motion_predictor.reset()
        logging.info("[TrackingStateManager] Tracking cleared")

    def is_tracking_active(self) -> bool:
        """Check if currently tracking an object."""
        return self.selected_track_id is not None and self.frames_since_detection <= self.max_history

    def get_tracking_info(self) -> Dict:
        """Get current tracking information."""
        return {
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
