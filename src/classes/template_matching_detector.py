#src\classes\template_matching_detector.py
import cv2
import numpy as np
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

    def smart_redetection(self, frame, tracker=None, roi=None):
        """
        Perform template matching to find the template in the current frame or within a specified ROI.
        If more than one detection is found, choose the one closest to the last known tracker position.
        """
        if self.template is None:
            print("Template has not been set.")
            return False

        frame_to_search = frame
        x_offset, y_offset = 0, 0  # Offsets for adjusting coordinates if ROI is used

        if roi is not None:
            x, y, w, h = roi
            frame_to_search = frame[y:y+h, x:x+w]
            x_offset, y_offset = x, y

        res = cv2.matchTemplate(frame_to_search, self.template, self.method)
        threshold = Parameters.TEMPLATE_MATCHING_THRESHOLD  # Adjust threshold from parameters

        # For methods where the minimum value is the best match
        if self.method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
            loc = np.where(res <= (1 - threshold))
        else:  # For methods where the maximum value is the best match
            loc = np.where(res >= threshold)

        points = list(zip(*loc[::-1]))  # Get list of (x, y) match positions
        if not points:
            print("No matches found.")
            return False

        if tracker and hasattr(tracker, 'center'):
            # Calculate distances from each match center to the tracker's last known center
            distances = []
            for pt in points:
                match_center = (pt[0] + self.template.shape[1] / 2 + x_offset,
                                pt[1] + self.template.shape[0] / 2 + y_offset)
                distances.append(np.linalg.norm(np.array(match_center) - np.array(tracker.center)))
            closest_match_idx = np.argmin(distances)  # Index of the closest match
            top_left = points[closest_match_idx]
        else:
            # If no tracker info is available, default to the first match found
            top_left = points[0]

        # Adjust coordinates if ROI was used
        top_left = (top_left[0] + x_offset, top_left[1] + y_offset)

        h, w = self.template.shape[:2]
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
