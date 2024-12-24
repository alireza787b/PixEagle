# src/classes/gstreamer_handler.py
import cv2
import numpy as np
import logging
from classes.parameters import Parameters

class GStreamerHandler:
    """
    Streams frames to QGroundControl (UDP/RTP) using OpenCV's VideoWriter + GStreamer pipeline.
    """

    def __init__(self):
        self.out = None
        # Basic config from Parameters
        self.FLIP_METHOD = Parameters.CSI_FLIP_METHOD
        self.WIDTH = Parameters.GSTREAMER_WIDTH
        self.HEIGHT = Parameters.GSTREAMER_HEIGHT
        self.FRAMERATE = Parameters.GSTREAMER_FRAMERATE

        # Attempt hardware-accel encoder from config, else fallback
        self.encoder_name = getattr(Parameters, "GSTREAMER_ENCODER", "x264enc") or "x264enc"

        self.pipeline = self._create_pipeline()

    def _create_pipeline(self) -> str:
        """
        Builds a GStreamer pipeline string for QGC (RTP/UDP).
        Optionally uses hardware encoder if configured.
        """
        # If the encoder is invalid, GStreamer typically fails. We'll see in initialize_stream if it fails.
        tune = Parameters.GSTREAMER_TUNE
        speed_preset = Parameters.GSTREAMER_SPEED_PRESET
        bitrate = Parameters.GSTREAMER_BITRATE
        key_int = Parameters.GSTREAMER_KEY_INT_MAX
        host = Parameters.GSTREAMER_HOST
        port = Parameters.GSTREAMER_PORT
        buffer_size = Parameters.GSTREAMER_BUFFER_SIZE

        pipeline = (
            "appsrc ! "
            f"video/x-raw,format=BGR,width={self.WIDTH},height={self.HEIGHT},framerate={self.FRAMERATE}/1 ! "
            "videoconvert ! "
            "video/x-raw,format=NV12 ! "
            f"nvvidconv flip-method={self.FLIP_METHOD} ! "  # For Jetson; if on other platforms, might be no-op
            f"{self.encoder_name} tune={tune} "
            f"bitrate={bitrate} "
            f"key-int-max={key_int} "
            f"speed-preset={speed_preset} ! "
            "rtph264pay config-interval=1 pt=96 ! "
            f"udpsink host={host} port={port} buffer-size={buffer_size}"
        )

        logging.debug(f"[QGC Pipeline] {pipeline}")
        return pipeline

    def initialize_stream(self):
        """
        Initializes the GStreamer pipeline using OpenCV's VideoWriter.
        """
        try:
            logging.info("Initializing QGC GStreamer pipeline...")
            self.out = cv2.VideoWriter(self.pipeline, cv2.CAP_GSTREAMER, 0,
                                       self.FRAMERATE, (self.WIDTH, self.HEIGHT), True)
            if not self.out.isOpened():
                logging.error("Failed to open QGC GStreamer pipeline.")
                self.out = None
        except Exception as e:
            logging.error(f"Error initializing QGC GStreamer pipeline: {e}")
            self.out = None

    def stream_frame(self, frame: np.ndarray):
        """
        Streams a frame via the pipeline if initialized.
        """
        if self.out:
            try:
                if frame.dtype != np.uint8:
                    frame = frame.astype(np.uint8)
                if len(frame.shape) < 3 or frame.shape[2] != 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                self.out.write(frame)
            except Exception as e:
                logging.error(f"Error streaming frame to QGC pipeline: {e}")

    def release(self):
        """
        Releases the pipeline resources.
        """
        if self.out:
            self.out.release()
            self.out = None
            logging.info("QGC GStreamer pipeline released.")
