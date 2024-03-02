# src/classes/trackers/tracker_factory.py

from classes.trackers.csrt_tracker import CSRTTracker
# Import other trackers as necessary

def create_tracker(algorithm, video_handler=None, detector=None):
    if algorithm == "CSRT":
        return CSRTTracker(video_handler, detector)
    # Add other algorithms here
    else:
        raise ValueError(f"Unsupported tracking algorithm: {algorithm}")
