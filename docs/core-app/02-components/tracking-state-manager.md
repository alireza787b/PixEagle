# TrackingStateManager

Robust object tracking state management with multiple fallback strategies.

## Overview

`TrackingStateManager` (`src/classes/tracking_state_manager.py`) provides:

- Hybrid ID + spatial matching for robust tracking
- Handling of ID switches by YOLO trackers
- Brief occlusion recovery
- Appearance-based re-identification
- Graceful degradation during track loss

## Problem Solved

YOLO trackers (ByteTrack, BoT-SORT) can experience:

- **ID switches**: Same object gets different track ID
- **Brief occlusions**: Target hidden for 1-5 frames
- **Detection failures**: Missed detections
- **Re-identification needs**: Finding target after loss

TrackingStateManager adds a robustness layer on top of built-in tracker capabilities.

## Class Definition

```python
class TrackingStateManager:
    """
    Manages tracking state with hybrid ID + spatial matching strategies.

    Provides robust tracking by:
    1. Primary: Track by ID (fast, accurate when IDs are stable)
    2. Fallback: Track by spatial proximity (IoU matching)
    3. Prediction: Estimate position during brief occlusions
    """
```

## Tracking Strategies

### Hybrid Strategy (Default)

```python
if self.tracking_strategy == "hybrid":
    # 1. Try ID matching first
    best_match = self._match_by_id(detections)

    # 2. Fall back to spatial matching if ID not found
    if best_match is None and self.frames_since_detection < self.max_history:
        best_match = self._match_by_spatial(detections, compute_iou_func)

    # 3. Try appearance matching for re-identification
    if best_match is None and self.enable_appearance and frame is not None:
        best_match = self._match_by_appearance(detections, frame)
```

### ID-Only Strategy

```python
if self.tracking_strategy == "id_only":
    best_match = self._match_by_id(detections)
```

### Spatial-Only Strategy

```python
if self.tracking_strategy == "spatial_only":
    best_match = self._match_by_spatial(detections, compute_iou_func)
```

## Matching Methods

### ID Matching

```python
def _match_by_id(self, detections: List[List]) -> Optional[Dict]:
    """Match detection by exact track ID."""
    for detection in detections:
        track_id = int(detection[4])
        class_id = int(detection[6])

        # Match by ID and class
        if track_id == self.selected_track_id and \
           class_id == self.selected_class_id:
            return self._parse_detection(detection)

    return None
```

### Spatial Matching (IoU)

```python
def _match_by_spatial(
    self,
    detections: List[List],
    compute_iou_func
) -> Optional[Dict]:
    """Match detection by spatial proximity (IoU)."""
    if self.last_known_bbox is None:
        return None

    best_match = None
    best_iou = 0.0

    for detection in detections:
        class_id = int(detection[6])

        # Only consider same class
        if class_id != self.selected_class_id:
            continue

        # Compute IoU with last known position
        x1, y1, x2, y2 = map(int, detection[:4])
        iou = compute_iou_func((x1, y1, x2, y2), self.last_known_bbox)

        if iou > best_iou and iou >= self.spatial_iou_threshold:
            best_iou = iou
            best_match = self._parse_detection(detection)
            best_match['iou_match'] = True
            best_match['match_iou'] = iou

    return best_match
```

### Appearance Matching

```python
def _match_by_appearance(
    self,
    detections: List[List],
    frame: np.ndarray
) -> Optional[Dict]:
    """Match detection by visual appearance (3rd fallback)."""
    if not self.appearance_model or self.selected_class_id is None:
        return None

    # Convert detections to format for appearance model
    detection_dicts = []
    for detection in detections:
        detection_dicts.append({
            'bbox': tuple(map(int, detection[:4])),
            'track_id': int(detection[4]),
            'class_id': int(detection[6])
        })

    # Find best appearance match
    best_match = self.appearance_model.find_best_match(
        frame,
        detection_dicts,
        self.selected_class_id
    )

    if best_match:
        parsed = self._parse_detection([...])
        parsed['appearance_match'] = True
        parsed['appearance_similarity'] = best_match.get('appearance_similarity', 0.0)
        return parsed

    return None
```

## Graceful Degradation

### Multi-Level Fallback

```python
def _handle_detection_loss(
    self,
    detections,
    compute_iou_func,
    frame
) -> Tuple[bool, Optional[Dict]]:
    """Graceful degradation with multi-level fallback."""

    # Level 1: Within normal tolerance - use motion prediction
    if self.frames_since_detection <= self.max_history:
        return True, None  # Continue tracking with prediction

    # Level 2: Try lenient spatial matching
    if self.frames_since_detection <= self.max_history + extended_tolerance:
        lenient_iou = max(0.15, self.spatial_iou_threshold * 0.5)
        lenient_match = self._match_by_spatial_lenient(
            detections, compute_iou_func, lenient_iou
        )
        if lenient_match:
            self._on_detection_found(lenient_match, frame)
            return True, lenient_match

    # Level 3: Prediction-only mode
    if self.motion_predictor and self.last_known_bbox:
        predicted_bbox = self.motion_predictor.predict_bbox(
            self.frames_since_detection
        )
        if predicted_bbox:
            degradation_factor = 1.0 - (
                self.frames_since_detection - self.max_history
            ) / extended_tolerance
            return True, {
                'bbox': predicted_bbox,
                'confidence': self.smoothed_confidence * degradation_factor,
                'prediction_only': True
            }

    # Level 4: Signal complete loss
    return False, {'need_reselection': True}
```

## Confidence Management

### Smoothing

```python
# Exponential moving average
self.smoothed_confidence = (
    self.confidence_alpha * self.smoothed_confidence +
    (1 - self.confidence_alpha) * detection['confidence']
)
```

### Decay During Loss

```python
def _on_detection_lost(self):
    """Apply confidence decay for aging tracks."""
    self.frames_since_detection += 1

    # Decay confidence (5% per frame)
    self.smoothed_confidence = max(
        0.0,
        self.smoothed_confidence * (1.0 - self.confidence_decay_rate)
    )
```

## Usage

### Starting Tracking

```python
def start_tracking(
    self,
    track_id: int,
    class_id: int,
    bbox: Tuple[int, int, int, int],
    confidence: float,
    center: Tuple[int, int]
):
    """Start tracking a new object."""
    self.selected_track_id = track_id
    self.selected_class_id = class_id
    self.last_known_bbox = bbox
    self.last_known_center = center
    self.smoothed_confidence = confidence
    self.frames_since_detection = 0
    self.tracking_history.clear()
```

### Updating Tracking

```python
def update_tracking(
    self,
    detections: List[List],
    compute_iou_func,
    frame: np.ndarray = None
) -> Tuple[bool, Optional[Dict]]:
    """
    Update tracking state with new detections.

    Returns:
        Tuple of (is_tracking_active, selected_detection or None)
    """
```

### Getting Tracking Info

```python
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
```

## Configuration

```python
config = {
    'TRACKING_STRATEGY': 'hybrid',           # 'id_only', 'spatial_only', 'hybrid'
    'ID_LOSS_TOLERANCE_FRAMES': 5,           # Frames before considering lost
    'SPATIAL_IOU_THRESHOLD': 0.35,           # Minimum IoU for spatial match
    'ENABLE_PREDICTION_BUFFER': True,        # Use motion prediction
    'CONFIDENCE_SMOOTHING_ALPHA': 0.8,       # EMA smoothing factor
    'TRACK_CONFIDENCE_DECAY_RATE': 0.05,     # Decay per frame when lost
    'ENABLE_APPEARANCE_MODEL': True,         # Use appearance re-ID
    'ENABLE_GRACEFUL_DEGRADATION': True,     # Multi-level fallback
    'EXTENDED_TOLERANCE_FRAMES': 10,         # Extra frames for degradation
}

state_manager = TrackingStateManager(config, motion_predictor, appearance_model)
```

## Integration with SmartTracker

```python
class SmartTracker:
    def __init__(self, config):
        self.state_manager = TrackingStateManager(
            config,
            motion_predictor=self.motion_predictor,
            appearance_model=self.appearance_model
        )

    def update(self, frame):
        # Get YOLO detections
        detections = self.yolo_model.track(frame)

        # Update tracking state
        is_active, detection = self.state_manager.update_tracking(
            detections,
            self.compute_iou,
            frame
        )

        if is_active and detection:
            return self._create_tracker_output(detection)
        else:
            return TrackerOutput.empty()
```

## Related Components

- [SmartTracker](../../trackers/02-components/smart-tracker.md) - Uses TrackingStateManager
- [MotionPredictor](../../trackers/02-components/motion-predictor.md) - Prediction support
- [AppearanceModel](../../trackers/02-components/appearance-model.md) - Re-identification
