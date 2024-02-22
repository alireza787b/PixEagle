#src/classes/detector_interface.py

class DetectorInterface:
    def __init__(self):
        raise NotImplementedError("This method should be overridden by subclasses")

    def extract_features(self, frame, bbox):
        raise NotImplementedError("This method should be overridden by subclasses")

    def smart_redetection(self, frame):
        raise NotImplementedError("This method should be overridden by subclasses")

    def draw_detection(self, frame, color=(0, 255, 255)):
        raise NotImplementedError("This method should be overridden by subclasses")

    def get_latest_bbox(self):
        """
        Returns the latest bounding box.
        """
        raise NotImplementedError("This method should be overridden by subclasses")

    def set_latest_bbox(self, bbox):
        """
        Sets the latest bounding box.
        """
        raise NotImplementedError("This method should be overridden by subclasses")
