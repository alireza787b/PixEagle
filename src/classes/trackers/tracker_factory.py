# src/classes/trackers/tracker_factory.py

from classes.trackers.csrt_tracker import CSRTTracker
from classes.trackers.particle_filter_tracker import ParticleFilterTracker
# Import other trackers as necessary

def create_tracker(algorithm, video_handler=None, detector=None,app_controller=None):
    if algorithm == "CSRT":
        return CSRTTracker(video_handler, detector,app_controller)
    elif algorithm == "PFT":
        return ParticleFilterTracker(video_handler, detector,app_controller,debug=True)
    # Add other algorithms here
    else:
        raise ValueError(f"Unsupported tracking algorithm: {algorithm}")
