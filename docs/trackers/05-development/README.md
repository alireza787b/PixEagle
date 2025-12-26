# Tracker Development Guide

> Creating custom trackers, testing strategies, and best practices

This section provides guidance for developers extending the tracker system with custom implementations.

---

## Section Contents

| Document | Description |
|----------|-------------|
| [Creating Trackers](creating-trackers.md) | Custom tracker implementation guide |
| [Testing Trackers](testing-trackers.md) | Testing strategies and fixtures |
| [Best Practices](best-practices.md) | Design patterns and guidelines |

---

## Quick Start: Custom Tracker

### 1. Create Tracker Class

```python
# src/classes/trackers/my_tracker.py
from classes.trackers.base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType
import numpy as np
from typing import Tuple

class MyTracker(BaseTracker):
    """Custom tracker implementation."""

    def _create_tracker(self):
        """Initialize underlying tracker."""
        # Return your tracker instance or None
        return None

    def start_tracking(self, frame: np.ndarray,
                       bbox: Tuple[int, int, int, int]) -> None:
        """Initialize tracking with bounding box."""
        self.bbox = bbox
        self.set_center((
            int(bbox[0] + bbox[2] / 2),
            int(bbox[1] + bbox[3] / 2)
        ))
        self.tracking_started = True
        self.normalize_bbox()

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """Process frame and return (success, bbox)."""
        if not self.tracking_started:
            return False, (0, 0, 0, 0)

        # Your tracking logic here
        success = True
        new_bbox = self.bbox  # Update with actual tracking

        if success:
            self.bbox = new_bbox
            self.set_center((
                int(new_bbox[0] + new_bbox[2] / 2),
                int(new_bbox[1] + new_bbox[3] / 2)
            ))
            self.normalize_bbox()

        return success, new_bbox
```

### 2. Register in Factory

```python
# src/classes/trackers/tracker_factory.py
from classes.trackers.my_tracker import MyTracker

TRACKER_REGISTRY = {
    "CSRT": CSRTTracker,
    "KCF": KCFKalmanTracker,
    "dlib": DlibTracker,
    "Gimbal": GimbalTracker,
    "MyTracker": MyTracker,  # Add here
}
```

### 3. Add Schema (Optional)

```yaml
# configs/tracker_schemas.yaml
tracker_types:
  MyTracker:
    name: "My Custom Tracker"
    supported_schemas:
      - POSITION_2D
      - BBOX_CONFIDENCE
    ui_metadata:
      display_name: "My Tracker"
      factory_key: "MyTracker"
```

---

## BaseTracker Interface

### Required Methods

| Method | Purpose |
|--------|---------|
| `start_tracking(frame, bbox)` | Initialize with first frame and bbox |
| `update(frame)` | Process frame, return (success, bbox) |

### Optional Overrides

| Method | Purpose |
|--------|---------|
| `_create_tracker()` | Create underlying tracker instance |
| `compute_confidence(frame)` | Custom confidence computation |
| `get_output()` | Custom TrackerOutput generation |
| `get_capabilities()` | Declare tracker features |

### Inherited Utilities

| Method | Purpose |
|--------|---------|
| `set_center(center)` | Set and normalize center |
| `normalize_bbox()` | Normalize bbox coordinates |
| `is_near_boundary()` | Check boundary proximity |
| `compute_motion_confidence()` | Motion consistency score |

---

## Testing Infrastructure

### Test Fixtures

```python
# tests/fixtures/mock_tracker.py
from classes.tracker_output import TrackerOutput, TrackerDataType

class TrackerOutputFactory:
    """Factory for creating test TrackerOutput instances."""

    @staticmethod
    def create_centered() -> TrackerOutput:
        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=True,
            position_2d=(0.0, 0.0),
            confidence=1.0
        )
```

### Running Tests

```bash
# Run tracker tests
pytest tests/unit/test_tracker_output.py -v

# Run with coverage
pytest tests/ --cov=src/classes/trackers
```

---

## Development Checklist

- [ ] Implement `start_tracking()` and `update()` methods
- [ ] Call `set_center()` and `normalize_bbox()` on updates
- [ ] Set `tracking_started` flag appropriately
- [ ] Handle failure cases gracefully
- [ ] Add to TrackerFactory registry
- [ ] Add schema definition (if new data type)
- [ ] Write unit tests
- [ ] Test integration with followers

---

## Related Sections

- [Architecture](../01-architecture/README.md) - BaseTracker interface
- [Configuration](../04-configuration/README.md) - Schema system
