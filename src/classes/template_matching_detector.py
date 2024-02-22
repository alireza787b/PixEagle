import cv2
from .detector_interface import DetectorInterface
from .parameters import Parameters

class TemplateMatchingDetector(DetectorInterface):
    def __init__(self):
        #super().__init__()
        self.template = None  # This will hold the template image
        self.latest_bbox = None  # To store the latest bounding box
        self.method = self.get_matching_method(Parameters.TEMPLATE_MATCHING_METHOD)

    @staticmethod
    def get_matching_method(method_name):
        """
        Maps the method name to the OpenCV constant.
        """
        methods = {
            "TM_CCOEFF": cv2.TM_CCOEFF,
            "TM_CCOEFF_NORMED": cv2.TM_CCOEFF_NORMED,
            "TM_CCORR": cv2.TM_CCORR,
            "TM_CCORR_NORMED": cv2.TM_CCORR_NORMED,
            "TM_SQDIFF": cv2.TM_SQDIFF,
            "TM_SQDIFF_NORMED": cv2.TM_SQDIFF_NORMED,
        }
        return methods.get(method_name, cv2.TM_CCOEFF_NORMED)

    def set_template(self, template):
        self.template = template

    def extract_features(self, frame, bbox):
        """
        Sets the template based on the provided bounding box.
        """
        x, y, w, h = bbox
        self.template = frame[y:y+h, x:x+w]
        self.latest_bbox = bbox

    def smart_redetection(self, frame):
        """
        Perform template matching to find the template in the current frame.
        Update `self.latest_bbox` with the new location of the template.
        """
        if self.template is None:
            print("Template has not been set.")
            return False

        res = cv2.matchTemplate(frame, self.template, self.method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if self.method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
            top_left = min_loc
        else:
            top_left = max_loc

        h, w = self.template.shape[:2]  # Corrected to handle color images
        bottom_right = (top_left[0] + w, top_left[1] + h)

        self.latest_bbox = (top_left[0], top_left[1], w, h)
        return True


    def draw_detection(self, frame, color=(0, 255, 255)):
        if self.latest_bbox is None:
            return frame
        x, y, w, h = self.latest_bbox
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        return frame

    def get_latest_bbox(self):
        return self.latest_bbox

    def set_latest_bbox(self, bbox):
        self.latest_bbox = bbox
