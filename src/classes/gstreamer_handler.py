import cv2
import numpy as np
import logging
from classes.parameters import Parameters

class GStreamerHandler:
    """
    A class to handle streaming video frames to a GStreamer pipeline.
    This class initializes a GStreamer pipeline that streams video frames over UDP in H.264 format.
    """

    def __init__(self, width: int, height: int, framerate: int):
        """
        Initializes the GStreamerHandler with the specified frame width, height, and framerate.

        Args:
            width (int): The width of the video frames.
            height (int): The height of the video frames.
            framerate (int): The frame rate of the video stream.
        """
        self.width = width
        self.height = height
        self.framerate = framerate
        self.out = None
        self.pipeline = self._create_pipeline()

    def _create_pipeline(self) -> str:
        """
        Constructs the GStreamer pipeline string using parameters from the configuration.

        Returns:
            str: The constructed GStreamer pipeline string.
        """
        # Constructing the pipeline with various parameters adjustable for different streaming needs
        pipeline = (
            f"appsrc ! "
            f"video/x-raw,format=BGR,width={self.width},height={self.height},framerate={self.framerate}/1 ! "
            f"videoconvert ! "
            f"video/x-raw,format=NV12 ! "  # Converting the format to NV12, as expected by subsequent elements
            f"nvvidconv flip-method=0 ! "
            f"videobalance contrast={Parameters.GSTREAMER_CONTRAST} "
            f"brightness={Parameters.GSTREAMER_BRIGHTNESS} "
            f"saturation={Parameters.GSTREAMER_SATURATION} ! "  # Adjusting video properties for better visibility
            f"x264enc tune={Parameters.GSTREAMER_TUNE} "
            f"key-int-max={Parameters.GSTREAMER_KEY_INT_MAX} "
            f"bitrate={Parameters.GSTREAMER_BITRATE} "
            f"speed-preset={Parameters.GSTREAMER_SPEED_PRESET} ! "  # Encoder settings for balancing quality, latency, and CPU usage
            f"rtph264pay config-interval=1 pt=96 ! "  # Packaging H.264 stream into RTP packets
            f"udpsink host={Parameters.GSTREAMER_HOST} port={Parameters.GSTREAMER_PORT} buffer-size={Parameters.GSTREAMER_BUFFER_SIZE}"  # Sending the RTP packets over UDP
        )
        logging.debug(f"GStreamer pipeline: {pipeline}")
        return pipeline

    def initialize_stream(self):
        """
        Initializes the GStreamer pipeline using OpenCV's VideoWriter.
        This method sets up the pipeline and prepares it for streaming frames.
        """
        try:
            logging.info("Initializing GStreamer pipeline...")
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
                # Ensure the frame is 8-bit, 3-channel BGR format
                if frame.dtype != np.uint8:
                    logging.debug("Converting frame to 8-bit unsigned integer type.")
                    frame = frame.astype(np.uint8)
                
                if len(frame.shape) == 2:  # Grayscale image with 1 channel
                    logging.debug("Converting grayscale frame to BGR format.")
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                elif frame.shape[2] == 1:  # Single channel image
                    logging.debug("Converting single channel frame to BGR format.")
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                elif frame.shape[2] != 3:
                    logging.error("Unexpected number of channels in frame.")
                    return
                
                self.out.write(frame)
            except Exception as e:
                logging.error(f"Error streaming frame to GStreamer pipeline: {e}")

    def release(self):
        """
        Releases the GStreamer pipeline and associated resources.
        This should be called to clean up resources when streaming is no longer needed.
        """
        if self.out:
            self.out.release()
            logging.debug("GStreamer pipeline released.")
