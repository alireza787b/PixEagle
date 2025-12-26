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

        # Update timing
        dt = self.update_time()

        # Handle SmartTracker override
        if self.override_active:
            return self._handle_override(frame, dt)

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
            self.confidence = self.compute_confidence(frame)

            # Update appearance model
            self._update_appearance(frame, new_bbox)

            # Update estimator
            if self.estimator_enabled and self.position_estimator:
                self.position_estimator.set_dt(dt)
                self.position_estimator.predict_and_update(np.array(self.center))

        return success, self.bbox

    def _update_appearance(self, frame: np.ndarray, bbox: Tuple) -> None:
        """Update appearance model with current observation."""
        if not self.detector:
            return

        try:
            current_features = self.detector.extract_features(frame, bbox)
            learning_rate = 0.1
            self.detector.adaptive_features = (
                (1 - learning_rate) * self.detector.adaptive_features +
                learning_rate * current_features
            )
        except Exception as e:
            logger.warning(f"Appearance update failed: {e}")

    def _handle_override(self, frame: np.ndarray, dt: float) -> Tuple[bool, Tuple]:
        """Handle SmartTracker override mode."""
        smart_tracker = self.app_controller.smart_tracker
        if smart_tracker and smart_tracker.selected_bbox:
            x1, y1, x2, y2 = smart_tracker.selected_bbox
            w, h = x2 - x1, y2 - y1
            self.bbox = (x1, y1, w, h)
            self.set_center(((x1 + x2) // 2, (y1 + y2) // 2))
            self.normalize_bbox()
            self.confidence = 1.0
            return True, self.bbox
        return False, self.bbox

    def get_output(self) -> TrackerOutput:
        """Generate TrackerOutput with current state."""
        return TrackerOutput(
            data_type=TrackerDataType.POSITION_2D,
            timestamp=time.time(),
            tracking_active=self.tracking_started,
            tracker_id=f"{self.tracker_name}_{id(self)}",
            position_2d=self.normalized_center,
            bbox=self.bbox,
            normalized_bbox=self.normalized_bbox,
            confidence=self.confidence,
            quality_metrics={
                'motion_consistency': self.compute_motion_confidence()
            },
            metadata={
                'tracker_class': self.__class__.__name__,
                'tracker_algorithm': 'my_algorithm'
            }
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
        """Reset tracker state."""
        self.bbox = None
        self.prev_bbox = None
        self.confidence = 0.0
        self.is_initialized = False
        self.tracking_started = False
        self.center_history.clear()
        logger.info(f"{self.tracker_name} reset")
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
- [ ] Set `tracking_started` flag appropriately
- [ ] Handle failure cases gracefully
- [ ] Add to TrackerFactory registry
- [ ] Add configuration section
- [ ] Add schema definition (if needed)
- [ ] Write unit tests
- [ ] Test with AppController

---

## Related

- [BaseTracker](../01-architecture/base-tracker.md) - Interface details
- [Testing Trackers](testing-trackers.md) - Testing strategies
- [Best Practices](best-practices.md) - Design guidelines
