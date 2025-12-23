# src/classes/appearance_model.py
"""
Appearance Model for Object Re-identification.

Provides visual appearance-based matching to re-identify objects after long
occlusions (>5 frames). Uses color histograms and HOG features for robust
matching across lighting and pose variations.

Author: PixEagle Team
Date: 2025
"""

import cv2
import numpy as np
import time
import logging
from typing import Optional, Tuple, Dict, List
from collections import deque


class AppearanceModel:
    """
    Visual appearance model for object re-identification.

    Extracts and compares visual features (color histogram, HOG) to
    re-identify objects that were temporarily lost.
    """

    def __init__(self, config: dict):
        """
        Initialize the appearance model.

        Args:
            config: SmartTracker configuration dictionary
        """
        self.config = config

        # Feature extraction configuration
        self.feature_type = self.config.get('APPEARANCE_FEATURE_TYPE', 'histogram')
        self.similarity_threshold = self.config.get('APPEARANCE_MATCH_THRESHOLD', 0.7)
        self.max_memory_frames = self.config.get('MAX_REIDENTIFICATION_FRAMES', 30)
        self.adaptive_learning = self.config.get('APPEARANCE_ADAPTIVE_LEARNING', True)
        self.learning_rate = self.config.get('APPEARANCE_LEARNING_RATE', 0.1)

        # Memory cap to prevent unbounded growth in long sessions
        self.max_lost_objects = self.config.get('MAX_LOST_OBJECTS_CACHED', 100)

        # Performance profiling
        self.enable_profiling = self.config.get('ENABLE_APPEARANCE_PROFILING', False)
        self.profiling_stats = {
            'feature_extraction_ms': [],
            'similarity_computation_ms': [],
            'total_extractions': 0,
            'total_comparisons': 0,
            'failed_extractions': 0
        }

        # Memory of lost objects: {track_id: {'features': ..., 'class_id': ..., 'frame_lost': ...}}
        self.lost_objects = {}

        # Current frame counter (for cleanup)
        self.current_frame = 0

        # Feature extraction parameters
        self._init_feature_params()

        logging.info(f"[AppearanceModel] Initialized with feature_type='{self.feature_type}', "
                    f"threshold={self.similarity_threshold}, memory={self.max_memory_frames} frames, "
                    f"profiling={'enabled' if self.enable_profiling else 'disabled'}")

    def _init_feature_params(self):
        """Initialize feature extraction parameters based on feature_type and config."""
        # Color histogram parameters (HSV space for illumination invariance)
        h_bins = self.config.get('HIST_H_BINS', 30)
        s_bins = self.config.get('HIST_S_BINS', 32)
        self.hist_bins = [h_bins, s_bins]  # H, S bins (V is less stable)
        self.hist_ranges = [0, 180, 0, 256]  # H: 0-179, S: 0-255

        # HOG parameters (configurable for different hardware)
        hog_win_size = self.config.get('HOG_WIN_SIZE', [64, 64])
        hog_block_size = self.config.get('HOG_BLOCK_SIZE', [16, 16])
        hog_block_stride = self.config.get('HOG_BLOCK_STRIDE', [8, 8])
        hog_cell_size = self.config.get('HOG_CELL_SIZE', [8, 8])
        hog_nbins = self.config.get('HOG_NBINS', 9)

        # Convert to tuples (OpenCV requires tuples, not lists)
        self.hog_win_size = tuple(hog_win_size)
        self.hog_block_size = tuple(hog_block_size)
        self.hog_block_stride = tuple(hog_block_stride)
        self.hog_cell_size = tuple(hog_cell_size)
        self.hog_nbins = hog_nbins

        # Initialize HOG descriptor
        self.hog = cv2.HOGDescriptor(
            self.hog_win_size,
            self.hog_block_size,
            self.hog_block_stride,
            self.hog_cell_size,
            self.hog_nbins
        )

        logging.debug(f"[AppearanceModel] HOG params: win={self.hog_win_size}, "
                     f"block={self.hog_block_size}, cell={self.hog_cell_size}, bins={self.hog_nbins}")
        logging.debug(f"[AppearanceModel] Histogram params: H_bins={h_bins}, S_bins={s_bins}")

    def extract_features(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        """
        Extract appearance features from object region.

        Args:
            frame: Full frame image (BGR)
            bbox: Bounding box (x1, y1, x2, y2)

        Returns:
            Feature vector (normalized numpy array) or None if extraction fails
        """
        start_time = time.time() if self.enable_profiling else None

        # Validate frame
        if frame is None or frame.size == 0:
            logging.warning("[AppearanceModel] Invalid frame (None or empty)")
            self.profiling_stats['failed_extractions'] += 1
            return None

        x1, y1, x2, y2 = bbox

        # Validate bbox
        if x2 <= x1 or y2 <= y1:
            logging.warning(f"[AppearanceModel] Invalid bbox dimensions: {bbox}")
            self.profiling_stats['failed_extractions'] += 1
            return None

        # Clamp to frame boundaries
        h, w = frame.shape[:2]
        x1 = max(0, min(x1, w - 1))
        y1 = max(0, min(y1, h - 1))
        x2 = max(x1 + 1, min(x2, w))
        y2 = max(y1 + 1, min(y2, h))

        # Validate ROI size (minimum 4x4 pixels)
        roi_w = x2 - x1
        roi_h = y2 - y1
        if roi_w < 4 or roi_h < 4:
            logging.warning(f"[AppearanceModel] ROI too small: {roi_w}x{roi_h} (minimum 4x4)")
            self.profiling_stats['failed_extractions'] += 1
            return None

        # Extract ROI
        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            logging.warning(f"[AppearanceModel] Empty ROI for bbox: {bbox}")
            self.profiling_stats['failed_extractions'] += 1
            return None

        # Extract features based on configured type
        if self.feature_type == 'histogram':
            features = self._extract_histogram(roi)
        elif self.feature_type == 'hog':
            features = self._extract_hog(roi)
        elif self.feature_type == 'hybrid':
            hist_features = self._extract_histogram(roi)
            hog_features = self._extract_hog(roi)
            if hist_features is None or hog_features is None:
                self.profiling_stats['failed_extractions'] += 1
                return None
            # Concatenate and normalize
            features = np.concatenate([hist_features, hog_features])
        else:
            logging.error(f"[AppearanceModel] Unknown feature_type: {self.feature_type}")
            self.profiling_stats['failed_extractions'] += 1
            return None

        # Normalize to unit length for cosine similarity
        if features is not None:
            norm = np.linalg.norm(features)
            if norm > 0:
                features = features / norm
            else:
                logging.warning("[AppearanceModel] Zero-norm feature vector")
                self.profiling_stats['failed_extractions'] += 1
                return None

        # Profiling
        if self.enable_profiling and start_time is not None:
            elapsed_ms = (time.time() - start_time) * 1000
            self.profiling_stats['feature_extraction_ms'].append(elapsed_ms)
            self.profiling_stats['total_extractions'] += 1

            # Log every 50 extractions
            if self.profiling_stats['total_extractions'] % 50 == 0:
                avg_ms = np.mean(self.profiling_stats['feature_extraction_ms'][-50:])
                logging.info(f"[AppearanceModel Profiling] Feature extraction: {avg_ms:.2f}ms avg "
                           f"({self.profiling_stats['total_extractions']} total, "
                           f"{self.profiling_stats['failed_extractions']} failed)")

        return features

    def _extract_histogram(self, roi: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract color histogram features from ROI.

        Args:
            roi: Region of interest (BGR image)

        Returns:
            Normalized histogram feature vector
        """
        try:
            # Convert to HSV (more illumination-invariant than RGB/BGR)
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

            # Compute 2D histogram (H-S, ignore V which varies with lighting)
            hist = cv2.calcHist(
                [hsv],
                [0, 1],  # H and S channels
                None,
                self.hist_bins,
                self.hist_ranges
            )

            # Flatten and normalize
            hist = hist.flatten()
            cv2.normalize(hist, hist)

            return hist.astype(np.float32)

        except Exception as e:
            logging.warning(f"[AppearanceModel] Histogram extraction failed: {e}")
            return None

    def _extract_hog(self, roi: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract HOG (Histogram of Oriented Gradients) features from ROI.

        Args:
            roi: Region of interest (BGR image)

        Returns:
            HOG feature vector
        """
        try:
            # Convert to grayscale
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

            # Resize to fixed size for consistent feature dimension
            resized = cv2.resize(gray, self.hog_win_size)

            # Compute HOG descriptor
            hog_features = self.hog.compute(resized)

            if hog_features is not None:
                return hog_features.flatten().astype(np.float32)
            else:
                return None

        except Exception as e:
            logging.warning(f"[AppearanceModel] HOG extraction failed: {e}")
            return None

    def compute_similarity(self, features1: np.ndarray, features2: np.ndarray) -> float:
        """
        Compute cosine similarity between two feature vectors.

        Args:
            features1: First feature vector
            features2: Second feature vector

        Returns:
            Similarity score (0.0-1.0), higher = more similar
        """
        start_time = time.time() if self.enable_profiling else None

        if features1 is None or features2 is None:
            return 0.0

        # Ensure same dimension
        if features1.shape != features2.shape:
            logging.warning(f"[AppearanceModel] Feature dimension mismatch: {features1.shape} vs {features2.shape}")
            return 0.0

        # Cosine similarity (features are already normalized to unit length)
        similarity = np.dot(features1, features2)

        # Clamp to [0, 1] range (should already be in this range for normalized vectors)
        similarity = np.clip(similarity, 0.0, 1.0)

        # Profiling
        if self.enable_profiling and start_time is not None:
            elapsed_ms = (time.time() - start_time) * 1000
            self.profiling_stats['similarity_computation_ms'].append(elapsed_ms)
            self.profiling_stats['total_comparisons'] += 1

        return float(similarity)

    def register_object(self, track_id: int, class_id: int, features: np.ndarray):
        """
        Register appearance features for a tracked object.

        Args:
            track_id: Object track ID
            class_id: Object class ID
            features: Appearance feature vector
        """
        if features is None:
            return

        # Store or update features
        if track_id in self.lost_objects:
            # Update existing entry (adaptive learning)
            if self.adaptive_learning:
                old_features = self.lost_objects[track_id]['features']
                # Exponential moving average
                alpha = self.learning_rate
                updated_features = alpha * features + (1 - alpha) * old_features
                # Renormalize
                norm = np.linalg.norm(updated_features)
                if norm > 0:
                    updated_features = updated_features / norm
                self.lost_objects[track_id]['features'] = updated_features
                logging.debug(f"[AppearanceModel] Updated features for ID:{track_id} (adaptive learning)")
        else:
            # New entry
            self.lost_objects[track_id] = {
                'features': features,
                'class_id': class_id,
                'frame_registered': self.current_frame
            }
            logging.debug(f"[AppearanceModel] Registered ID:{track_id} class:{class_id}")

    def mark_as_lost(self, track_id: int):
        """
        Mark an object as lost (starts memory countdown).

        Args:
            track_id: Track ID that was lost
        """
        if track_id in self.lost_objects:
            self.lost_objects[track_id]['frame_lost'] = self.current_frame
            logging.debug(f"[AppearanceModel] Marked ID:{track_id} as lost at frame {self.current_frame}")

    def find_best_match(self, frame: np.ndarray, detections: List[Dict],
                       class_id: int) -> Optional[Dict]:
        """
        Find best appearance match for a lost object among new detections.

        Args:
            frame: Current frame (BGR image)
            detections: List of detection dictionaries with 'bbox', 'track_id', 'class_id'
            class_id: Class ID to match (only consider same class)

        Returns:
            Best matching detection dict with added 'appearance_similarity' field,
            or None if no match above threshold
        """
        # Find lost objects of this class that are within memory window
        candidates = []
        for lost_id, lost_data in self.lost_objects.items():
            if lost_data['class_id'] != class_id:
                continue

            # Check if within memory window
            frames_since_lost = self.current_frame - lost_data.get('frame_lost', lost_data['frame_registered'])
            if frames_since_lost > self.max_memory_frames:
                continue

            candidates.append((lost_id, lost_data))

        if not candidates:
            return None

        # Extract features from all detections of matching class
        best_match = None
        best_similarity = self.similarity_threshold
        best_lost_id = None

        for detection in detections:
            if detection['class_id'] != class_id:
                continue

            # Extract features from this detection
            det_features = self.extract_features(frame, detection['bbox'])
            if det_features is None:
                continue

            # Compare against all lost object candidates
            for lost_id, lost_data in candidates:
                lost_features = lost_data['features']
                similarity = self.compute_similarity(det_features, lost_features)

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = detection.copy()
                    best_match['appearance_similarity'] = similarity
                    best_match['recovered_id'] = lost_id

        if best_match:
            logging.info(f"[AppearanceModel] Match found: new ID:{best_match['track_id']}→recovered ID:{best_match['recovered_id']} "
                        f"(similarity={best_similarity:.3f})")

        return best_match

    def cleanup_old_entries(self):
        """
        Remove lost objects that exceeded memory window and enforce memory cap.
        Call this every frame to prevent memory bloat.

        Cleanup Strategy:
        1. Remove entries older than max_memory_frames
        2. If still over max_lost_objects cap, remove oldest first
        """
        to_remove = []

        # Step 1: Remove expired entries
        for track_id, data in self.lost_objects.items():
            frames_since_lost = self.current_frame - data.get('frame_lost', data['frame_registered'])
            if frames_since_lost > self.max_memory_frames:
                to_remove.append(track_id)

        for track_id in to_remove:
            del self.lost_objects[track_id]
            logging.debug(f"[AppearanceModel] Removed expired entry for ID:{track_id}")

        # Step 2: Enforce memory cap by removing oldest entries
        if len(self.lost_objects) > self.max_lost_objects:
            # Sort by frame_lost/frame_registered (oldest first)
            sorted_entries = sorted(
                self.lost_objects.items(),
                key=lambda x: x[1].get('frame_lost', x[1]['frame_registered'])
            )

            # Remove oldest entries until under cap
            num_to_remove = len(self.lost_objects) - self.max_lost_objects
            for i in range(num_to_remove):
                track_id = sorted_entries[i][0]
                del self.lost_objects[track_id]
                logging.debug(f"[AppearanceModel] Memory cap: removed oldest entry ID:{track_id}")

            logging.info(f"[AppearanceModel] Memory cap enforced: removed {num_to_remove} oldest entries, "
                        f"now {len(self.lost_objects)}/{self.max_lost_objects}")

    def increment_frame(self):
        """
        Increment internal frame counter.
        Call this once per frame.
        """
        self.current_frame += 1
        self.cleanup_old_entries()

    def clear(self):
        """
        Clear all stored appearance data.
        """
        self.lost_objects.clear()
        self.current_frame = 0
        logging.debug("[AppearanceModel] Cleared all data")

    def get_memory_status(self) -> Dict:
        """
        Get current memory status for debugging.

        Returns:
            Dictionary with memory statistics
        """
        return {
            'stored_objects': len(self.lost_objects),
            'current_frame': self.current_frame,
            'max_memory_frames': self.max_memory_frames,
            'feature_type': self.feature_type,
            'objects': {
                track_id: {
                    'class_id': data['class_id'],
                    'frames_since_lost': self.current_frame - data.get('frame_lost', data['frame_registered'])
                }
                for track_id, data in self.lost_objects.items()
            }
        }

    def get_profiling_stats(self) -> Dict:
        """
        Get performance profiling statistics.

        Returns:
            Dictionary with profiling metrics
        """
        if not self.enable_profiling:
            return {'profiling_enabled': False}

        extraction_times = self.profiling_stats['feature_extraction_ms']
        similarity_times = self.profiling_stats['similarity_computation_ms']

        stats = {
            'profiling_enabled': True,
            'total_extractions': self.profiling_stats['total_extractions'],
            'total_comparisons': self.profiling_stats['total_comparisons'],
            'failed_extractions': self.profiling_stats['failed_extractions'],
            'success_rate': (
                (self.profiling_stats['total_extractions'] - self.profiling_stats['failed_extractions']) /
                max(self.profiling_stats['total_extractions'], 1) * 100
            )
        }

        if extraction_times:
            stats['feature_extraction'] = {
                'avg_ms': np.mean(extraction_times),
                'min_ms': np.min(extraction_times),
                'max_ms': np.max(extraction_times),
                'std_ms': np.std(extraction_times)
            }

        if similarity_times:
            stats['similarity_computation'] = {
                'avg_ms': np.mean(similarity_times),
                'min_ms': np.min(similarity_times),
                'max_ms': np.max(similarity_times),
                'std_ms': np.std(similarity_times)
            }

        return stats
