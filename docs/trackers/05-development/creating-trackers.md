# Creating Custom Trackers

> Step-by-step guide to implementing new tracker types

This guide walks through creating a custom tracker that integrates with PixEagle's architecture.

---

## Prerequisites

Before creating a custom tracker:

1. Understand the [BaseTracker](../01-architecture/base-tracker.md) interface
2. Review [TrackerOutput](../01-architecture/tracker-output.md) schema
3. Examine existing trackers as examples

---

## Step 1: Create Tracker Class

```python
# src/classes/trackers/my_tracker.py
"""
MyTracker Module - Custom Tracker Implementation
-------------------------------------------------

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: January 2025
"""

import logging
import time
import numpy as np
from typing import Optional, Tuple

from classes.trackers.base_tracker import BaseTracker
from classes.tracker_output import TrackerOutput, TrackerDataType
from classes.parameters import Parameters

logger = logging.getLogger(__name__)


class MyTracker(BaseTracker):
    """
    Custom tracker implementation.

    Attributes:
        tracker_name (str): Tracker identifier
        bbox (Tuple): Current bounding box
        confidence (float): Tracking confidence
    """

    def __init__(self, video_handler: Optional[object] = None,
                 detector: Optional[object] = None,
                 app_controller: Optional[object] = None):
        """
        Initialize custom tracker.

        Args:
            video_handler: Video streaming handler
            detector: Feature detector for appearance
            app_controller: Main application controller
        """
        super().__init__(video_handler, detector, app_controller)

        self.tracker_name = "MyTracker"

        # Load configuration
        my_config = getattr(Parameters, 'MyTracker', {})
        self.confidence_threshold = my_config.get('confidence_threshold', 0.5)

        # Initialize state
        self.bbox = None
        self.prev_bbox = None
        self.confidence = 0.0
        self.is_initialized = False

        logger.info(f"{self.tracker_name} initialized")

    def _create_tracker(self):
        """
        Create underlying tracker instance.

        Returns:
            Tracker instance or None
        """
        # Initialize your underlying tracker here
        # e.g., return cv2.TrackerMOSSE_create()
        return None

    def start_tracking(self, frame: np.ndarray,
                       bbox: Tuple[int, int, int, int]) -> None:
        """
        Initialize tracking with frame and bounding box.

        Args:
            frame: Initial video frame (BGR)
            bbox: Bounding box (x, y, width, height)
        """
        x, y, w, h = bbox

        # Initialize your tracker
        # self.tracker.init(frame, bbox)

        # Set tracking state
        self.tracking_started = True
        self.is_initialized = True

        # Store bbox
        self.bbox = bbox
        self.prev_bbox = bbox

        # Set center (triggers normalization)
        self.set_center((int(x + w/2), int(y + h/2)))
        self.normalize_bbox()

        # Initialize appearance model (if using detector)
        if self.detector:
            self.detector.initial_features = self.detector.extract_features(frame, bbox)
            self.detector.adaptive_features = self.detector.initial_features.copy()

        # Reset state
        self.confidence = 1.0
        self.last_update_time = time.time()

        logger.info(f"{self.tracker_name} tracking started: bbox={bbox}")

    def update(self, frame: np.ndarray) -> Tuple[bool, Tuple[int, int, int, int]]:
        """
        Process new frame and return tracking result.

        Args:
            frame: Current video frame

        Returns:
            Tuple[bool, Tuple]: (success, bbox)
        """
        if not self.is_initialized:
            return False, (0, 0, 0, 0)

        start_time = time.time()
        dt = self.update_time()

        # Handle SmartTracker override (inherited from BaseTracker)
        if self.override_active:
            return self._handle_smart_tracker_override(frame, dt)

        # ===== YOUR TRACKING LOGIC HERE =====
        # Example:
        # success, new_bbox = self.tracker.update(frame)

        success = True
        new_bbox = self.bbox  # Replace with actual tracking

        # ===== END TRACKING LOGIC =====

        if success:
            self.prev_bbox = self.bbox
            self.bbox = new_bbox

            # Update center
            self.set_center((
                int(new_bbox[0] + new_bbox[2] / 2),
                int(new_bbox[1] + new_bbox[3] / 2)
            ))
            self.normalize_bbox()
            self.center_history.append(self.center)

            # Compute confidence
            self.compute_confidence(frame)

            # Update appearance model (inherited, with drift protection)
            my_config = getattr(Parameters, 'MyTracker', {})
            self._update_appearance_model_safe(
                frame, new_bbox,
                learning_rate=my_config.get('appearance_learning_rate', 0.05))

            # Update estimator (inherited)
            self._update_estimator(dt)

            # Update out-of-frame status (inherited)
            self._update_out_of_frame_status(frame)

            # Track counters
            self.prev_bbox = self.bbox
            self.failure_count = 0
            self.successful_frames += 1
            self.frame_count += 1

            # Log performance (inherited)
            self._log_performance(start_time)

            return True, self.bbox
        else:
            # Handle failure
            self._record_loss_start()
            self.failure_count += 1
            self.failed_frames += 1
            self.frame_count += 1
            self._build_failure_info("tracker_failed")
            return False, self.bbox

    def get_output(self) -> TrackerOutput:
        """Generate TrackerOutput using inherited _build_output()."""
        return self._build_output(
            tracker_algorithm='my_algorithm',
            extra_quality={'my_custom_metric': 0.95},
            extra_raw={'mode': 'default'},
        )

    def get_capabilities(self) -> dict:
        """Return tracker capabilities."""
        base = super().get_capabilities()
        base.update({
            'tracker_algorithm': 'my_algorithm',
            'supports_rotation': False,
            'supports_scale_change': True,
            'accuracy_rating': 'medium',
            'speed_rating': 'fast'
        })
        return base

    def reset(self) -> None:
        """Reset tracker-specific state, then call super().reset()."""
        self.is_initialized = False
        super().reset()
```

---

## Step 2: Register in Factory

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

---

## Step 3: Add Configuration

```yaml
# configs/config.yaml
MyTracker:
  confidence_threshold: 0.5
  learning_rate: 0.1
  # Add your parameters
```

---

## Step 4: Add Schema (Optional)

```yaml
# configs/tracker_schemas.yaml
tracker_types:
  MyTracker:
    name: "My Custom Tracker"
    display_name: "My Tracker"
    supported_schemas:
      - POSITION_2D
      - BBOX_CONFIDENCE
    default_schema: POSITION_2D
    ui_metadata:
      icon: "custom"
      category: "custom"
```

---

## Step 5: Add Tests

```python
# tests/unit/test_my_tracker.py
import pytest
import numpy as np
from classes.trackers.my_tracker import MyTracker

class TestMyTracker:
    @pytest.fixture
    def tracker(self):
        return MyTracker()

    def test_initialization(self, tracker):
        assert tracker.tracker_name == "MyTracker"
        assert not tracker.is_initialized

    def test_start_tracking(self, tracker):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        bbox = (100, 100, 50, 50)

        tracker.start_tracking(frame, bbox)

        assert tracker.is_initialized
        assert tracker.tracking_started
        assert tracker.bbox == bbox

    def test_update(self, tracker):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        bbox = (100, 100, 50, 50)

        tracker.start_tracking(frame, bbox)
        success, new_bbox = tracker.update(frame)

        assert success
        assert new_bbox is not None

    def test_get_output(self, tracker):
        from classes.tracker_output import TrackerDataType

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        tracker.start_tracking(frame, (100, 100, 50, 50))

        output = tracker.get_output()

        assert output.data_type == TrackerDataType.POSITION_2D
        assert output.tracking_active
```

---

## Checklist

- [ ] Implement `start_tracking()` and `update()` methods
- [ ] Call `set_center()` and `normalize_bbox()` on updates
- [ ] Use `self._update_appearance_model_safe()` instead of manual appearance code
- [ ] Use `self._update_estimator(dt)` instead of manual estimator calls
- [ ] Use `self._update_out_of_frame_status(frame)` in update loop
- [ ] Use `self._log_performance(start_time)` for diagnostics
- [ ] Use `self._build_output('MyAlgorithm')` in `get_output()`
- [ ] Use `self._record_loss_start()` and `self._build_failure_info()` on failure
- [ ] Call `super().reset()` in `reset()` instead of manual clearing
- [ ] Handle failure cases with structured `TrackingFailureInfo`
- [ ] Add to TrackerFactory registry
- [ ] Add configuration section
- [ ] Write unit tests
- [ ] Test with AppController

---

## Related

- [BaseTracker](../01-architecture/base-tracker.md) - Interface details
- [Testing Trackers](testing-trackers.md) - Testing strategies
- [Best Practices](best-practices.md) - Design guidelines
