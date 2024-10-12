# src/classes/frame_preprocessor.py

import cv2
import numpy as np
from classes.parameters import Parameters

class FramePreprocessor:
    """
    Handles preprocessing of video frames before they are processed by other components.
    Preprocessing steps can include noise reduction, contrast enhancement, color space conversion, etc.
    """

    def __init__(self):
        """
        Initializes the FramePreprocessor with the desired preprocessing techniques.
        The techniques to apply are determined by parameters in the Parameters class.
        """
        self.techniques = []

        # Add preprocessing techniques based on configuration
        if Parameters.PREPROCESSING_USE_BLUR:
            self.techniques.append(self.apply_blur)

        if Parameters.PREPROCESSING_USE_MEDIAN_BLUR:
            self.techniques.append(self.apply_median_blur)

        if Parameters.PREPROCESSING_USE_CLAHE:
            self.techniques.append(self.apply_clahe)

        if Parameters.PREPROCESSING_COLOR_SPACE != 'BGR':
            self.techniques.append(self.convert_color_space)

        # Additional techniques can be appended here

    def preprocess(self, frame: np.ndarray) -> np.ndarray:
        """
        Applies the selected preprocessing techniques to the given frame.

        Args:
            frame (np.ndarray): The input video frame.

        Returns:
            np.ndarray: The preprocessed video frame.
        """
        for technique in self.techniques:
            frame = technique(frame)
        return frame

    def apply_blur(self, frame: np.ndarray) -> np.ndarray:
        """
        Applies Gaussian blur to the frame to reduce noise.

        Args:
            frame (np.ndarray): The input video frame.

        Returns:
            np.ndarray: The blurred video frame.
        """
        ksize = Parameters.PREPROCESSING_BLUR_KERNEL_SIZE
        return cv2.GaussianBlur(frame, (ksize, ksize), 0)

    def apply_median_blur(self, frame: np.ndarray) -> np.ndarray:
        """
        Applies median blur to the frame to reduce noise, effective for salt-and-pepper noise.

        Args:
            frame (np.ndarray): The input video frame.

        Returns:
            np.ndarray: The blurred video frame.
        """
        ksize = Parameters.PREPROCESSING_MEDIAN_BLUR_KERNEL_SIZE
        return cv2.medianBlur(frame, ksize)

    def apply_clahe(self, frame: np.ndarray) -> np.ndarray:
        """
        Applies Contrast Limited Adaptive Histogram Equalization (CLAHE) to enhance contrast.

        Args:
            frame (np.ndarray): The input video frame.

        Returns:
            np.ndarray: The frame with enhanced contrast.
        """
        # Convert to LAB color space
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)

        # Apply CLAHE to the L-channel
        clahe = cv2.createCLAHE(clipLimit=Parameters.PREPROCESSING_CLAHE_CLIP_LIMIT,
                                tileGridSize=(Parameters.PREPROCESSING_CLAHE_TILE_GRID_SIZE,
                                              Parameters.PREPROCESSING_CLAHE_TILE_GRID_SIZE))
        cl = clahe.apply(l_channel)

        # Merge the channels back and convert to BGR
        merged = cv2.merge((cl, a_channel, b_channel))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

    def convert_color_space(self, frame: np.ndarray) -> np.ndarray:
        """
        Converts the frame to the specified color space.

        Args:
            frame (np.ndarray): The input video frame.

        Returns:
            np.ndarray: The frame converted to the desired color space.
        """
        color_space = Parameters.PREPROCESSING_COLOR_SPACE
        if color_space == 'GRAY':
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        elif color_space == 'HSV':
            return cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        elif color_space == 'LAB':
            return cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        # Add more color spaces as needed
        else:
            # Default to BGR if unknown color space
            return frame

    # Additional preprocessing methods can be added here
