# src/classes/trackers/tracker_factory.py

from classes.trackers.csrt_tracker import CSRTTracker
# Import other trackers as necessary

def create_tracker(algorithm: str, video_handler=None, detector=None, app_controller=None):
    """
    Factory function to create tracker instances based on the specified algorithm.
    
    :param algorithm: The name of the tracking algorithm.
    :param video_handler: Video handler instance.
    :param detector: Detector instance.
    :param app_controller: AppController instance.
    :return: An instance of a tracker.
    """
    if algorithm == "CSRT":
        return CSRTTracker(video_handler, detector, app_controller)
    # Add other algorithms here
    else:
        raise ValueError(f"Unsupported tracking algorithm: {algorithm}")
