# src/classes/segmentor.py

import cv2
import numpy as np
from .parameters import Parameters  # Import Parameters class

class Segmentor:
    def __init__(self, algorithm=Parameters.DEFAULT_SEGMENTATION_ALGORITHM):
        """
        Initializes the segmentor with the specified algorithm.
        """
        self.algorithm = algorithm
        self.user_click = None

    def set_click_coordinates(self, event, x, y, flags, param):
        """
        Callback function to capture mouse click coordinates in the OpenCV window.
        """
        if event == cv2.EVENT_LBUTTONDOWN:
            self.user_click = (x, y)

    def user_click_coordinates(self, frame):
        """
        Displays the frame and captures the user's click, returning the coordinates.
        """
        self.user_click = None
        cv2.namedWindow("Select Object")
        cv2.setMouseCallback("Select Object", self.set_click_coordinates)

        while True:
            cv2.imshow("Select Object", frame)
            if cv2.waitKey(1) & 0xFF == ord('q') or self.user_click is not None:
                break  # Break the loop if 'q' is pressed or a click is detected

        cv2.destroyWindow("Select Object")
        return self.user_click

    def segment(self, frame):
        """
        Segments the object in the frame based on a user click location.
        """
        x, y = self.user_click_coordinates(frame)
        if x is None or y is None:
            print("No click detected. Segmentation canceled.")
            return None
        if self.algorithm == "GrabCut":
            return self._segment_using_grabcut(frame, x, y)
        
        # Extend with more elif statements for other algorithms using Parameters.SEGMENTATION_ALGORITHMS
        else:
            raise ValueError(f"Unsupported segmentation algorithm: {self.algorithm}")



    def _segment_using_grabcut(self, frame, x, y):
        """
        Segments an object using the GrabCut algorithm based on a user click.

        This is a private method called internally depending on the selected algorithm.

        Parameters:
        - frame (np.array): The current frame from the video source.
        - x (int): The x-coordinate of the user's click.
        - y (int): The y-coordinate of the user's click.

        Returns:
        - bbox (tuple): The bounding box of the segmented object (x, y, width, height).
        """
        mask = np.zeros(frame.shape[:2], np.uint8)
        bgdModel = np.zeros((1, 65), np.float64)
        fgdModel = np.zeros((1, 65), np.float64)

        # Example rectangle around the click (adjust as needed)
        rect = (max(x-50, 0), max(y-50, 0), min(x+50, frame.shape[1]), min(y+50, frame.shape[0]))

        # Apply GrabCut
        cv2.grabCut(frame, mask, rect, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_RECT)

        # Create a mask where sure and likely backgrounds are set to 0, otherwise 1
        binMask = np.where((mask == 2) | (mask == 0), 0, 1).astype('uint8')

        # Find contours in the binary mask
        contours, _ = cv2.findContours(binMask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Optional: Select the largest contour as the object to track
        if contours:
            c = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
            return (x, y, w, h)
        return None


    def refine_bbox(self, frame, bbox):
        """
        Refines a bounding box using segmentation.
        """
        x, y, w, h = bbox
        # Example of refining using GrabCut or any other chosen algorithm
        mask = np.zeros(frame.shape[:2], np.uint8)
        bgdModel = np.zeros((1, 65), np.float64)
        fgdModel = np.zeros((1, 65), np.float64)
        rect = (x, y, w, h)
        cv2.grabCut(frame, mask, rect, bgdModel, fgdModel, 5, cv2.GC_INIT_WITH_RECT)
        mask2 = np.where((mask == 2) | (mask == 0), 0, 1).astype('uint8')
        frame_cut = frame * mask2[:, :, np.newaxis]
        # After segmentation, find contours to get a refined bounding box
        contours, _ = cv2.findContours(mask2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            c = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(c)
            return (x, y, w, h)
        return bbox  # Return original bbox if segmentation fails or no contours found