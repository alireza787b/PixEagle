class DetectorInterface:
    def __init__(self):
        raise NotImplementedError("This method should be overridden by subclasses")

    def extract_features(self, frame, bbox):
        raise NotImplementedError("This method should be overridden by subclasses")

    def smart_redetection(self, frame):
        raise NotImplementedError("This method should be overridden by subclasses")

    def draw_detection(self, frame, bbox, color=(0, 255, 255)):
        raise NotImplementedError("This method should be overridden by subclasses")
