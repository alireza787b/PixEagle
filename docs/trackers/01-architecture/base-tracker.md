# BaseTracker - Abstract Base Class

> The foundation interface for all tracker implementations in PixEagle

`BaseTracker` is an abstract base class (ABC) that defines the common interface and shared functionality for all tracker implementations. Located at `src/classes/trackers/base_tracker.py`.

---

## Overview

The `BaseTracker` class provides:

- **Abstract interface** that all trackers must implement
- **Common utilities** for normalization, confidence, and visualization
- **Estimator integration** for Kalman filter position prediction
- **TrackerOutput generation** for unified data schema

---

## Abstract Methods

Subclasses **must** implement these methods:

### `start_tracking(frame, bbox)`

Initialize tracking with the first frame and bounding box.

```python
@abstractmethod
def start_tracking(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> None:
    """
    Initialize tracking with frame and bounding box.

    Args:
        frame (np.ndarray): Initial video frame (BGR format)
        bbox (Tuple[int, int, int, int]): Bounding box (x, y, width, height)
    """
    pass
```

### `update(frame)`

Process a new frame and return tracking result.

```python
@abstractmethod
def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
    """
    Update tracker with new frame.

    Args:
        frame (np.ndarray): Current video frame

    Returns:
        Tuple[bool, Tuple[int, int, int, int]]:
            - success: True if tracking succeeded
            - bbox: Updated bounding box (x, y, w, h)
    """
    pass
```

---

## Core Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `video_handler` | Optional[object] | Video streaming handler |
| `detector` | Optional[object] | Feature detector for appearance |
| `app_controller` | Optional[object] | Main application controller |
| `bbox` | Tuple[int, int, int, int] | Current bounding box (x, y, w, h) |
| `center` | Tuple[int, int] | Center pixel coordinates |
| `normalized_center` | Tuple[float, float] | Normalized center [-1, 1] |
| `normalized_bbox` | Tuple[float, float, float, float] | Normalized bbox |
| `confidence` | float | Tracking confidence [0.0, 1.0] |
| `tracking_started` | bool | Whether tracking has been initialized |
| `center_history` | deque | History of center positions |

---

## Key Methods

### Normalization

```python
def normalize_center_coordinates(self) -> None:
    """
    Normalize center to [-1, 1] range.

    Frame center = (0, 0)
    Top-right = (1, -1)
    Bottom-left = (-1, 1)
    """

def normalize_bbox(self) -> None:
    """Normalize bbox coordinates relative to frame size."""

def set_center(self, value: Tuple[int, int]) -> None:
    """Set center and automatically normalize."""
```

### Confidence Computation

```python
def compute_confidence(self, frame: np.ndarray) -> float:
    """
    Compute confidence from motion + appearance.

    confidence = (MOTION_WEIGHT * motion_confidence +
                  APPEARANCE_WEIGHT * appearance_confidence)
    """

def compute_motion_confidence(self) -> float:
    """
    Compute motion consistency score.

    Returns 1.0 if movement is expected, lower if erratic.
    """

def is_motion_consistent(self) -> bool:
    """Check if motion is within expected limits."""
```

### Boundary Detection

```python
def is_near_boundary(self, margin: int = None) -> bool:
    """
    Check if target is near frame edge.

    Near-boundary targets cause issues with correlation trackers.
    Default margin from Parameters.BOUNDARY_MARGIN_PIXELS (15).
    """

def get_boundary_status(self) -> dict:
    """
    Get detailed boundary proximity status.

    Returns:
        {
            'near_boundary': bool,
            'edges': ['left', 'top', ...],
            'min_distance': int,
            'distances': {'left': int, 'top': int, ...}
        }
    """

def compute_boundary_confidence_penalty(self) -> float:
    """
    Compute confidence penalty for boundary proximity.

    Returns multiplier 0.5-1.0 (1.0 = no penalty).
    """
```

### Output Generation

```python
def get_output(self) -> TrackerOutput:
    """
    Generate standardized TrackerOutput.

    Returns:
        TrackerOutput with POSITION_2D data type
    """

def get_capabilities(self) -> Dict[str, Any]:
    """
    Return tracker capabilities.

    Returns:
        {
            'data_types': ['POSITION_2D'],
            'supports_confidence': True,
            'supports_velocity': bool,
            'supports_bbox': True,
            ...
        }
    """

def get_legacy_data(self) -> Dict[str, Any]:
    """Return data in legacy format for backwards compatibility."""
```

### Estimator Integration

```python
def update_time(self) -> float:
    """Update dt for estimator, return time delta."""

# External estimator access
if self.estimator_enabled and self.position_estimator:
    self.position_estimator.set_dt(dt)
    self.position_estimator.predict_and_update(np.array(self.center))
    estimated_position = self.position_estimator.get_estimate()
```

### SmartTracker Override

```python
def set_external_override(self, bbox: Tuple, center: Tuple) -> None:
    """Enable SmartTracker override mode."""

def clear_external_override(self) -> None:
    """Disable external override."""

def get_effective_bbox(self) -> Optional[Tuple]:
    """Return override bbox if active, else internal bbox."""
```

---

## Visualization

```python
def draw_tracking(self, frame: np.ndarray, tracking_successful: bool) -> np.ndarray:
    """Draw bounding box and center on frame."""

def draw_fancy_bbox(self, frame: np.ndarray, tracking_successful: bool):
    """Draw stylized bbox with crosshairs and corner markers."""

def draw_estimate(self, frame: np.ndarray, tracking_successful: bool) -> np.ndarray:
    """Draw estimator prediction if enabled."""
```

---

## Component Suppression

For trackers that don't need image processing (e.g., GimbalTracker):

```python
# In tracker __init__
self.suppress_detector = True
self.suppress_predictor = True

# Check suppression
def is_detector_suppressed(self) -> bool:
    return getattr(self, 'suppress_detector', False)
```

---

## Implementing a Custom Tracker

```python
from classes.trackers.base_tracker import BaseTracker

class MyTracker(BaseTracker):
    def _create_tracker(self):
        """Create underlying tracker instance."""
        return my_underlying_tracker()

    def start_tracking(self, frame: np.ndarray,
                       bbox: Tuple[int, int, int, int]) -> None:
        """Initialize tracking."""
        self.tracker.init(frame, bbox)
        self.bbox = bbox
        self.set_center((bbox[0] + bbox[2]//2, bbox[1] + bbox[3]//2))
        self.tracking_started = True
        self.normalize_bbox()

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple]:
        """Process frame."""
        success, new_bbox = self.tracker.update(frame)

        if success:
            self.bbox = new_bbox
            self.set_center((new_bbox[0] + new_bbox[2]//2,
                            new_bbox[1] + new_bbox[3]//2))
            self.normalize_bbox()

        return success, self.bbox
```

---

## Related

- [Factory Pattern](factory-pattern.md) - How trackers are instantiated
- [TrackerOutput](tracker-output.md) - Output schema
- [Creating Trackers](../05-development/creating-trackers.md) - Full development guide
