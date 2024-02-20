import cv2


class TemplateMatcher:
    def __init__(self, method_name):
        self.method = self.get_matching_method(method_name)
        self.template = None

    @staticmethod
    def get_matching_method(method_name):
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

    def match(self, frame):
        if self.template is None:
            raise ValueError("Template has not been set.")
        res = cv2.matchTemplate(frame, self.template, self.method)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if self.method in [cv2.TM_SQDIFF, cv2.TM_SQDIFF_NORMED]:
            top_left = min_loc
        else:
            top_left = max_loc
        w, h = self.template.shape[::-1]
        bottom_right = (top_left[0] + w, top_left[1] + h)
        return top_left, bottom_right
