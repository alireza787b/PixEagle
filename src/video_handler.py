# src/classes/video_handler.py

import cv2
from parameters import Parameters
from collections import deque

class VideoHandler:
    """
    Handles video input from various sources, such as video files or USB cameras.
    Capable of storing a recent history of video frames for later retrieval.

    Attributes:
        cap (cv2.VideoCapture): OpenCV video capture object.
        frame_history (deque): Stores the most recent frames.
    """

    def __init__(self):
        """
        Initializes the video source based on the configuration and prepares
        frame storage if required.
        """
        self.cap = None  # VideoCapture object
        self.frame_history = deque(maxlen=Parameters.STORE_LAST_FRAMES)
        self.init_video_source()

    def init_video_source(self):
        """
        Initialize the video source based on the configuration in Parameters.
        Raises an exception if the video source cannot be opened.
        """
        if Parameters.VIDEO_SOURCE_TYPE == "VIDEO_FILE":
            self.cap = cv2.VideoCapture(Parameters.VIDEO_SOURCE_IDENTIFIER)
        elif Parameters.VIDEO_SOURCE_TYPE == "USB_CAMERA":
            # Future implementation for USB camera initialization
            pass
        # Add additional conditions for other source types here

        if not self.cap or not self.cap.isOpened():
            raise ValueError(f"Could not open video source: {Parameters.VIDEO_SOURCE_IDENTIFIER}")

    def get_frame(self):
        """
        Reads and returns the next frame from the video source.
        Also stores the frame in the history if required.

        Returns:
            frame (numpy.ndarray or None): The next video frame, or None if there are no more frames.
        """
        if self.cap:
            ret, frame = self.cap.read()
            if ret:
                self.frame_history.append(frame)
                return frame
            else:
                # End of video file or error reading frame
                return None
        else:
            return None

    def get_last_frames(self):
        """
        Returns the most recent frames stored in the history.

        Returns:
            A list of the most recent frames, up to the number specified in Parameters.STORE_LAST_FRAMES.
            Returns an empty list if no frames are available.
        """
        return list(self.frame_history)
    
    def clear_frame_history(self):
        """
        Clears the entire frame history, effectively resetting the stored frames.
        """
        self.frame_history.clear()

    def release(self):
        """
        Releases the video source and any associated resources.
        """
        if self.cap:
            self.cap.release()

