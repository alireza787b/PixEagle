import cv2
import numpy as np
import logging
from classes.parameters import Parameters

class GStreamerHandler:
    """
    A class to handle streaming video frames to a GStreamer pipeline.
    This class initializes a GStreamer pipeline that streams video frames over UDP in H.264 format.
    """

    def __init__(self):
        """
        Initializes the GStreamerHandler with the specified frame width, height, framerate, and flip method.
        """
        self.out = None
        self.CSI_FLIP_METHOD = Parameters.CSI_FLIP_METHOD
        self.CSI_WIDTH = Parameters.CSI_WIDTH
        self.CSI_HEIGHT = Parameters.CSI_HEIGHT
        self.CSI_FRAMERATE = Parameters.CSI_FRAMERATE


        self.pipeline = self._create_pipeline()

    def _create_pipeline(self) -> str:
        """
        Constructs the GStreamer pipeline string using parameters from the configuration for the Arducam IMX708 camera.

        Returns:
            str: The constructed GStreamer pipeline string.
        """
        pipeline = (
            f"nvarguscamerasrc sensor-id=0 ! "  # sensor-id=0 for the first camera
            f"video/x-raw(memory:NVMM), width={self.CSI_WIDTH}, height={self.CSI_HEIGHT}, framerate={self.CSI_FRAMERATE}/1, format=NV12 ! "
            f"nvvidconv flip-method={self.CSI_FLIP_METHOD} ! "
            f"video/x-raw, format=BGRx ! "
            f"videoconvert ! "  # Converts BGRx to BGR, compatible with OpenCV
            f"video/x-raw, format=BGR ! "
            f"videobalance contrast={Parameters.GSTREAMER_CONTRAST} "
            f"brightness={Parameters.GSTREAMER_BRIGHTNESS} "
            f"saturation={Parameters.GSTREAMER_SATURATION} ! "
            f"x264enc tune={Parameters.GSTREAMER_TUNE} "
            f"key-int-max={Parameters.GSTREAMER_KEY_INT_MAX} "
            f"bitrate={Parameters.GSTREAMER_BITRATE} "
            f"speed-preset={Parameters.GSTREAMER_SPEED_PRESET} ! "
            f"rtph264pay config-interval=1 pt=96 ! "
            f"udpsink host={Parameters.GSTREAMER_HOST} port={Parameters.GSTREAMER_PORT} buffer-size={Parameters.GSTREAMER_BUFFER_SIZE}"
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
