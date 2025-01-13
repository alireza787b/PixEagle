import cv2
import numpy as np
import logging
from classes.parameters import Parameters

class GStreamerHandler:
    """
    A class to handle streaming video frames to a GStreamer pipeline.
    This class initializes a GStreamer pipeline that streams video frames over UDP in H.264 format.

    Key Considerations and Best Practices:
    -------------------------------------
    1. Compatibility with QGroundControl (QGC):
       - QGC expects an RTP/UDP stream in H.264 format. This requires careful setup of the GStreamer pipeline to ensure 
         proper encoding, payloading, and streaming.
       - The `appsrc` element is used as the source in the pipeline, allowing OpenCV to push frames directly into the 
         GStreamer pipeline, which is necessary when working with processed frames in OpenCV.

    2. Frame Format:
       - OpenCV typically works with frames in BGR format, while the NVIDIA encoder (`nvvidconv`) and GStreamer pipeline 
         may require NV12 or other formats. Conversion is handled using `videoconvert`.
       - Ensure frames are in 8-bit, 3-channel BGR format before pushing them into the pipeline.

    3. Bitrate and Encoding Settings:
       - Bitrate is critical for balancing video quality and network bandwidth. It is specified in kbps.
       - The `x264enc` element is configured with `zerolatency` tuning for low-latency streaming, and `ultrafast` preset 
         for faster encoding at the expense of some quality.

    4. Flip Method:
       - The `nvvidconv` element's `flip-method` parameter can be adjusted to flip the video as needed. This is crucial 
         when working with different camera orientations.

    5. Error Handling and Logging:
       - Robust error handling ensures that issues with pipeline initialization or frame streaming are logged and managed 
         gracefully. This is critical in a live streaming environment.

    6. Buffer Size:
       - The UDP buffer size is configured to handle network jitter and ensure smooth streaming. Adjust based on network 
         conditions and application requirements.
    """

    def __init__(self):
        """
        Initializes the GStreamerHandler with parameters for frame width, height, framerate, and flip method.
        The pipeline is constructed based on these parameters.
        """
        self.out = None
        self.FLIP_METHOD = Parameters.CSI_FLIP_METHOD
        self.WIDTH = Parameters.GSTREAMER_WIDTH
        self.HEIGHT = Parameters.GSTREAMER_HEIGHT
        self.FRAMERATE = Parameters.GSTREAMER_FRAMERATE

        self.pipeline = self._create_pipeline()

    def _create_pipeline(self) -> str:
        """
        Constructs the GStreamer pipeline string using parameters from the configuration.
        This pipeline is designed to be compatible with QGroundControl, ensuring frames are properly formatted, encoded, 
        and streamed over RTP/UDP.

        Returns:
            str: The constructed GStreamer pipeline string.
        """
        pipeline = (
            f"appsrc ! "
            f"video/x-raw,format=BGR,width={self.WIDTH},height={self.HEIGHT},framerate={self.FRAMERATE}/1 ! "
            f"videoconvert ! "
            f"video/x-raw,format=NV12 ! "  # Convert to NV12 format for compatibility with NVIDIA encoder
            f"nvvidconv flip-method={self.FLIP_METHOD} ! "
            f"x264enc tune={Parameters.GSTREAMER_TUNE} "
            f"bitrate={Parameters.GSTREAMER_BITRATE} "  # Bitrate in kbps
            f"key-int-max={Parameters.GSTREAMER_KEY_INT_MAX} "
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
            self.out = cv2.VideoWriter(self.pipeline, cv2.CAP_GSTREAMER, 0, self.FRAMERATE, (self.WIDTH, self.HEIGHT), True)
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
            frame (np.ndarray): The video frame to stream. Must be an 8-bit, 3-channel BGR format.
        """
        if self.out:
            try:
                # Ensure the frame is in 8-bit, 3-channel BGR format
                if frame.dtype != np.uint8:
                    frame = frame.astype(np.uint8)
                if len(frame.shape) == 2 or frame.shape[2] != 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
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
