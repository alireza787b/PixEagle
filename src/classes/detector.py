# src/classes/detector.py

import cv2
import numpy as np
from .parameters import Parameters

class Detector:
    def __init__(self):
        # Placeholder for the feature extraction algorithm instance
        self.feature_extractor = None
        # Placeholder for storing key features of the object
        self.key_features = None
        # Initialize with the default feature extraction algorithm
        self.init_feature_extractor(Parameters.DEFAULT_FEATURE_EXTRACTION_ALGORITHM)
        self.latest_bbox = None
        self.key_features_img = None  # Image from which the key features were extracted


    def init_feature_extractor(self, algorithm):
        if algorithm == "ORB":
            self.feature_extractor = cv2.ORB_create(nfeatures=Parameters.ORB_FEATURES)
        else:
            raise ValueError(f"Unsupported feature extraction algorithm: {algorithm}")

    def extract_features(self, frame, bbox):
        if self.feature_extractor is not None:
            x, y, w, h = bbox
            roi = frame[y:y+h, x:x+w]
            keypoints, descriptors = self.feature_extractor.detectAndCompute(roi, None)
            self.key_features = (keypoints, descriptors)
            self.key_features_img = roi.copy()  # Store the ROI image

        else:
            raise Exception("Feature extractor not initialized")

    def smart_redetection(self, frame):
        if self.key_features is None or self.feature_extractor is None:
            print("Error: No key features stored or feature extractor not initialized.")
            return

        keypoints_current, descriptors_current = self.feature_extractor.detectAndCompute(frame, None)
        if descriptors_current is None or self.key_features[1] is None:
            print("Error: No descriptors to match.")
            return

        # Visualize keypoints on the current frame for debugging
        img_keypoints_current = cv2.drawKeypoints(frame, keypoints_current, None, flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
        cv2.imshow("Current Frame Keypoints", img_keypoints_current)

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

        print(f"Debug: {len(good_matches)} good matches found.")

        if len(good_matches) > Parameters.MIN_MATCH_COUNT:
            src_pts = np.float32([self.key_features[0][m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([keypoints_current[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

            M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            if M is None:
                print("Error: Homography could not be computed.")
                return

            h, w = frame.shape[:2]
            pts = np.float32([[0, 0], [0, h-1], [w-1, h-1], [w-1, 0]]).reshape(-1, 1, 2)
            dst = cv2.perspectiveTransform(pts, M)

            x, y, w, h = cv2.boundingRect(dst)
            self.latest_bbox = (x, y, w, h)

            # Corrected visualization of good matches
            img_matches = cv2.drawMatches(self.key_features_img, self.key_features[0], frame, keypoints_current, good_matches, None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
            cv2.imshow("Good Matches & Homography", img_matches)
            print(f"Debug: New bounding box - X: {x}, Y: {y}, W: {w}, H: {h}")
            return True
        else:
            print(f"Error: Not enough good matches found - {len(good_matches)}/{Parameters.MIN_MATCH_COUNT}")
            return False

    def draw_detection(self, frame, bbox, color=(0, 255, 255)):  # Default color is yellow
        """
        Draws the detected bounding box on the frame with the specified color.
        """
        p1 = (int(bbox[0]), int(bbox[1]))
        p2 = (int(bbox[0] + bbox[2]), int(bbox[1] + bbox[3]))
        cv2.rectangle(frame, p1, p2, color, 2, 1)
        return frame



