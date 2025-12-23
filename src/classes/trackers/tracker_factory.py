# src/classes/trackers/tracker_factory.py

"""
Tracker Factory Module
----------------------

This module provides a factory function `create_tracker` to instantiate tracker objects based on a specified algorithm.

Project Information:
- Project Name: PixEagle
- Repository: https://github.com/alireza787b/PixEagle
- Date: October 2024
- Author: Alireza Ghaderi
- LinkedIn: https://www.linkedin.com/in/alireza787b

Overview:
---------
The factory pattern allows for the creation of tracker instances without exposing the creation logic to the client and refers to the newly created object using a common interface.

Purpose:
--------
By using a factory, the system can easily switch between different tracking algorithms, facilitating experimentation and optimization.

Usage:
------
To create a tracker:
```python
tracker = create_tracker("CSRT", video_handler, detector, app_controller)
```

Supported Algorithms:
---------------------
- "CSRT": Channel and Spatial Reliability Tracker
- "KCF": KCF + Kalman Filter Tracker
- "dlib": dlib Correlation Filter Tracker (fast, PSR-based confidence)
- "Gimbal": Gimbal-based UDP Angle Tracker
- Additional trackers can be added by implementing their classes and updating the factory.

Notes:
------
- If an unsupported algorithm is specified, the factory raises a `ValueError`.
- Ensure that all tracker classes are properly imported and available in the factory.

"""

from classes.trackers.csrt_tracker import CSRTTracker
from classes.trackers.kcf_kalman_tracker import KCFKalmanTracker
from classes.trackers.gimbal_tracker import GimbalTracker
from classes.trackers.dlib_tracker import DlibTracker

# Tracker registry - maps algorithm names to tracker classes
# To add a new tracker: 1) Import the class above, 2) Add entry to this registry
TRACKER_REGISTRY = {
    "CSRT": CSRTTracker,
    "KCF": KCFKalmanTracker,
    "dlib": DlibTracker,
    "Gimbal": GimbalTracker,
}


def create_tracker(algorithm: str, video_handler=None, detector=None, app_controller=None):
    """
    Factory function to create tracker instances based on the specified algorithm.

    Args:
        algorithm (str): The name of the tracking algorithm (e.g., "CSRT", "KCF").
        video_handler (Optional[object]): Video handler instance.
        detector (Optional[object]): Detector instance.
        app_controller (Optional[object]): AppController instance.

    Returns:
        BaseTracker: An instance of a tracker.

    Raises:
        ValueError: If an unsupported tracking algorithm is specified.

    Example:
        ```python
        tracker = create_tracker("CSRT", video_handler, detector, app_controller)
        tracker = create_tracker("KCF", video_handler, detector, app_controller)
        ```
    """
    tracker_class = TRACKER_REGISTRY.get(algorithm)

    if tracker_class is None:
        supported = ", ".join(sorted(TRACKER_REGISTRY.keys()))
        raise ValueError(f"Unsupported tracking algorithm: '{algorithm}'. Supported: {supported}")

    return tracker_class(video_handler, detector, app_controller)

