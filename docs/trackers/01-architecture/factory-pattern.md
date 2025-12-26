# TrackerFactory - Registry Pattern

> Dynamic tracker instantiation without hardcoded dependencies

The `TrackerFactory` provides a simple registry pattern for creating tracker instances. Located at `src/classes/trackers/tracker_factory.py`.

---

## Overview

The factory pattern enables:

- **Dynamic creation** - Create trackers by name at runtime
- **Loose coupling** - No hardcoded tracker dependencies in application code
- **Easy extension** - Add new trackers with minimal code changes
- **Centralized management** - Single point of tracker registration

---

## Registry

```python
# src/classes/trackers/tracker_factory.py

from classes.trackers.csrt_tracker import CSRTTracker
from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
from classes.trackers.gimbal_tracker import GimbalTracker
from classes.trackers.dlib_tracker import DlibTracker

TRACKER_REGISTRY = {
    "CSRT": CSRTTracker,
    "KCF": KCFKalmanTracker,
    "dlib": DlibTracker,
    "Gimbal": GimbalTracker,
}
```

---

## API

### `create_tracker(algorithm, ...)`

```python
def create_tracker(algorithm: str,
                   video_handler=None,
                   detector=None,
                   app_controller=None) -> BaseTracker:
    """
    Factory function to create tracker instances.

    Args:
        algorithm (str): Tracker name ("CSRT", "KCF", "dlib", "Gimbal")
        video_handler: Video streaming handler
        detector: Feature detector for appearance
        app_controller: Main application controller

    Returns:
        BaseTracker: Tracker instance

    Raises:
        ValueError: If algorithm not in registry
    """
    tracker_class = TRACKER_REGISTRY.get(algorithm)

    if tracker_class is None:
        supported = ", ".join(sorted(TRACKER_REGISTRY.keys()))
        raise ValueError(f"Unsupported: '{algorithm}'. Supported: {supported}")

    return tracker_class(video_handler, detector, app_controller)
```

---

## Usage

### Basic Usage

```python
from classes.trackers.tracker_factory import create_tracker

# Create a CSRT tracker
tracker = create_tracker("CSRT", video_handler, detector, app_controller)

# Initialize and update
tracker.start_tracking(frame, bbox)
success, new_bbox = tracker.update(next_frame)
```

### Configuration-Driven

```python
from classes.parameters import Parameters
from classes.trackers.tracker_factory import create_tracker

# Get tracker type from config
algorithm = Parameters.TRACKING_ALGORITHM  # e.g., "CSRT"

# Create tracker dynamically
tracker = create_tracker(algorithm, video_handler, detector, app_controller)
```

### Error Handling

```python
try:
    tracker = create_tracker("unknown_tracker")
except ValueError as e:
    print(f"Error: {e}")
    # Error: Unsupported: 'unknown_tracker'. Supported: CSRT, Gimbal, KCF, dlib
```

---

## Adding a New Tracker

### Step 1: Implement Tracker Class

```python
# src/classes/trackers/my_tracker.py
from classes.trackers.base_tracker import BaseTracker

class MyTracker(BaseTracker):
    def start_tracking(self, frame, bbox):
        # Implementation
        pass

    def update(self, frame):
        # Implementation
        pass
```

### Step 2: Register in Factory

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

### Step 3: Add Schema Definition (Optional)

```yaml
# configs/tracker_schemas.yaml
tracker_types:
  MyTracker:
    name: "My Custom Tracker"
    supported_schemas:
      - POSITION_2D
    ui_metadata:
      display_name: "My Tracker"
      factory_key: "MyTracker"
```

---

## SmartTracker Note

`SmartTracker` is **not** in the factory registry. It operates as an overlay on top of classic trackers:

```python
# SmartTracker is created separately
from classes.smart_tracker import SmartTracker

if Parameters.ENABLE_SMART_TRACKER:
    smart_tracker = SmartTracker(video_handler, detector)
```

SmartTracker provides YOLO detections that can override the classic tracker's output via the `set_external_override()` mechanism.

---

## Registry Query

```python
from classes.trackers.tracker_factory import TRACKER_REGISTRY

# List all available trackers
available = list(TRACKER_REGISTRY.keys())
# ['CSRT', 'KCF', 'dlib', 'Gimbal']

# Check if tracker exists
if "CSRT" in TRACKER_REGISTRY:
    tracker = create_tracker("CSRT", ...)
```

---

## Related

- [BaseTracker](base-tracker.md) - Interface that all trackers implement
- [TrackerOutput](tracker-output.md) - Output schema
- [Creating Trackers](../05-development/creating-trackers.md) - Development guide
