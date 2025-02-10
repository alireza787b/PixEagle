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
- "ParticleFilter": Particle Filter based Tracker
- "ExternalTracker": Tracker that receives an externally provided bounding box
- Additional trackers can be added by implementing their classes and updating the factory.

Notes:
------
- If an unsupported algorithm is specified, the factory raises a `ValueError`.
- Ensure that all tracker classes are properly imported and available in the factory.
"""

# Import the available tracker classes
from classes.trackers.csrt_tracker import CSRTTracker
from classes.trackers.particle_filter_tracker import ParticleFilterTracker
from classes.trackers.external_tracker import ExternalTracker  # New external tracker integration

def create_tracker(algorithm: str, video_handler=None, detector=None, app_controller=None):
    """
    Factory function to create tracker instances based on the specified algorithm.

    Args:
        algorithm (str): The name of the tracking algorithm (e.g., "CSRT", "ParticleFilter", "ExternalTracker").
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
        ```
    """
    if algorithm == "CSRT":
        return CSRTTracker(video_handler, detector, app_controller)
    elif algorithm == "ParticleFilter":
        return ParticleFilterTracker(video_handler, detector, app_controller)
    elif algorithm == "ExternalTracker":
        return ExternalTracker(video_handler, detector, app_controller)
    else:
        raise ValueError(f"Unsupported tracking algorithm: {algorithm}")