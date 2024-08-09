import cv2
import numpy as np
import logging
from classes.parameters import Parameters

class GStreamerHandler:
    """
    Handles streaming video frames to a GStreamer pipeline.
    The GStreamer pipeline is configured to send video over UDP in H.264 format.
    """

    def __init__(self, width: int, height: int, framerate: int):
        """
        Initializes the GStreamerHandler with the specified width, height, and framerate.

        Args:
            width (int): Width of the video frames.
            height (int): Height of the video frames.
            framerate (int): Frame rate of the video stream.
        """
        self.width = width
        self.height = height
        self.framerate = framerate
        self.out = None
        self.pipeline = self._create_pipeline()

    def _create_pipeline(self) -> str:
        """
        Constructs the GStreamer pipeline string using the parameters.

        Returns:
            str: The GStreamer pipeline string.
        """
        return (
            f"appsrc ! videoconvert ! "
            f"x264enc tune=zerolatency bitrate={Parameters.GSTREAMER_BITRATE} speed-preset=superfast ! "
            f"rtph264pay config-interval=1 pt=96 ! "
            f"udpsink host={Parameters.GSTREAMER_HOST} port={Parameters.GSTREAMER_PORT}"
        )

    def initialize_stream(self):
        """
        Initializes the GStreamer pipeline using OpenCV's VideoWriter.
        """
        try:
            logging.debug(f"Initializing GStreamer pipeline: {self.pipeline}")
            self.out = cv2.VideoWriter(self.pipeline, cv2.CAP_GSTREAMER, 0, self.framerate, (self.width, self.height), True)
            if not self.out.isOpened():
                logging.error("Failed to open GStreamer pipeline.")
                self.out = None
        except Exception as e:
            logging.error(f"Error initializing GStreamer pipeline: {e}")
            self.out = None

    def stream_frame(self, frame: np.ndarray):
        """
        Streams a video frame to the GStreamer pipeline.

        Args:
            frame (np.ndarray): The video frame to stream.
        """
        if self.out:
            try:
                self.out.write(frame)
            except Exception as e:
                logging.error(f"Error streaming frame to GStreamer pipeline: {e}")

    def release(self):
        """
        Releases the GStreamer pipeline and associated resources.
        """
        if self.out:
            self.out.release()
            logging.debug("GStreamer pipeline released.")
