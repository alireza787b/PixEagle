#src/classes/feature_matching_detector.py

import logging
import cv2
import numpy as np
from .detector_interface import DetectorInterface
from .parameters import Parameters

logger = logging.getLogger(__name__)


class FeatureMatchingDetector(DetectorInterface):
    def __init__(self):
        self.feature_extractor = cv2.ORB_create(nfeatures=Parameters.ORB_FEATURES)
        self.key_features = None
        self.latest_bbox = None
        self.key_features_img = None
        self.frame = None
    def extract_features(self, frame, bbox):
        self.frame = frame
        x, y, w, h = bbox
        self.latest_bbox = bbox
        roi = frame[y:y+h, x:x+w]
        keypoints, descriptors = self.feature_extractor.detectAndCompute(roi, None)
        self.key_features = (keypoints, descriptors)
        self.key_features_img = roi.copy()

    def smart_redetection(self, frame):
        if self.key_features is None or self.feature_extractor is None:
            logger.warning("No key features stored or feature extractor not initialized.")
            return False

        keypoints_current, descriptors_current = self.feature_extractor.detectAndCompute(frame, None)
        if descriptors_current is None or self.key_features[1] is None:
            logger.warning("No descriptors to match.")
            return False

        index_params = dict(algorithm=Parameters.FLANN_INDEX_LSH,
                            table_number=Parameters.FLANN_TABLE_NUMBER,
                            key_size=Parameters.FLANN_KEY_SIZE,
                            multi_probe_level=Parameters.FLANN_MULTI_PROBE_LEVEL)
        search_params = dict(checks=Parameters.FLANN_SEARCH_PARAMS["checks"])
        flann = cv2.FlannBasedMatcher(index_params, search_params)

        matches = flann.knnMatch(self.key_features[1], descriptors_current, k=2)

        good_matches = []
        for match in matches:
            if len(match) >= 2:
                m, n = match
                if m.distance < Parameters.ORB_FLENN_TRESH * n.distance:
                    good_matches.append(m)

        logger.debug("%d good matches found.", len(good_matches))

        if len(good_matches) > Parameters.MIN_MATCH_COUNT:
            src_pts = np.float32([self.key_features[0][m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([keypoints_current[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if M is None:
                logger.warning("Homography could not be computed.")
                return False
            frame_height, frame_width = self.frame.shape[:2]

            pts = np.float32([[0, 0], [0, frame_height-1], [frame_width-1, frame_height-1], [frame_width-1, 0]]).reshape(-1, 1, 2)
            dst = cv2.perspectiveTransform(pts, M)
            last_x, last_y, last_w, last_h = self.latest_bbox
            self.latest_bbox =  cv2.boundingRect(dst)
            x, y, w, h = self.latest_bbox
            CONSTANT_BBOX_SIZE = True
            if CONSTANT_BBOX_SIZE:
                self.set_latest_bbox((x, y, last_w, last_h))
            else:
                self.set_latest_bbox((x, y, w, h))

            logger.debug("New bounding box - X: %d, Y: %d, W: %d, H: %d", x, y, w, h)
            return True
        else:
            logger.debug("Not enough good matches found - %d/%d", len(good_matches), Parameters.MIN_MATCH_COUNT)
            return False

    def draw_detection(self, frame, color=(0, 255, 255)):
        bbox = self.get_latest_bbox()
        if bbox is None or len(bbox) != 4:
            return frame

        # Proceed with drawing only if bbox is valid.
        p1 = (int(bbox[0]), int(bbox[1]))
        p2 = (int(bbox[0] + bbox[2]), int(bbox[1] + bbox[3]))
        cv2.rectangle(frame, p1, p2, color, 2, 1)
        return frame


    def get_latest_bbox(self):
        """
        Returns the latest bounding box.
        """
        return self.latest_bbox

    def set_latest_bbox(self, bbox):
        """
        Sets the latest bounding box, ensuring it does not go out of the frame.
        """
        if bbox is None:
            logger.debug("Attempted to set a None bounding box.")
            self.latest_bbox = None
            return

        # Ensure bbox coordinates are within the frame dimensions
        frame_height, frame_width = self.frame.shape[:2]
        x, y, w, h = bbox

        # Correct the bounding box if it goes out of the frame
        x = max(0, min(x, frame_width - 1))
        y = max(0, min(y, frame_height - 1))
        w = max(1, min(w, frame_width - x))
        h = max(1, min(h, frame_height - y))

        corrected_bbox = (x, y, w, h)
        if corrected_bbox != bbox:
            logger.debug("Bounding box corrected from %s to %s to fit within the frame.", bbox, corrected_bbox)

        self.latest_bbox = corrected_bbox
