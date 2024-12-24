# src/classes/gstreamer_http_handler.py
import cv2
import numpy as np
import logging
from classes.parameters import Parameters

class GStreamerHTTPHandler:
    """
    Streams frames over a TCP server approach using OpenCV's VideoWriter + GStreamer pipeline.
    This won't be true "HTTP chunked" for browsers, but can be read by a GStreamer or FFmpeg client.
    """

    def __init__(self):
        self.out = None
        self.WIDTH = Parameters.GSTREAMER_WIDTH
        self.HEIGHT = Parameters.GSTREAMER_HEIGHT
        self.FRAMERATE = Parameters.GSTREAMER_FRAMERATE

        self.encoder_name = getattr(Parameters, "GSTREAMER_ENCODER", "x264enc") or "x264enc"
        self.pipeline = self._create_pipeline()

    def _create_pipeline(self) -> str:
        tune = Parameters.GSTREAMER_TUNE
        speed_preset = Parameters.GSTREAMER_SPEED_PRESET
        bitrate = Parameters.GSTREAMER_BITRATE
        key_int = Parameters.GSTREAMER_KEY_INT_MAX
        host = Parameters.GSTREAMER_HOST
        port = Parameters.GSTREAMER_PORT

        pipeline = (
            "appsrc ! "
            f"video/x-raw,format=BGR,width={self.WIDTH},height={self.HEIGHT},framerate={self.FRAMERATE}/1 ! "
            "videoconvert ! "
            f"{self.encoder_name} tune={tune} "
            f"bitrate={bitrate} "
            f"key-int-max={key_int} "
            f"speed-preset={speed_preset} ! "
            "h264parse ! "
            "mpegtsmux ! "
            f"tcpserversink host={host} port={port} sync=false"
        )

        logging.debug(f"[HTTP Pipeline] {pipeline}")
        return pipeline

    def initialize_stream(self):
        logging.info("Initializing HTTP/TCP GStreamer pipeline...")
        try:
            self.out = cv2.VideoWriter(
                self.pipeline, cv2.CAP_GSTREAMER, 0,
                self.FRAMERATE, (self.WIDTH, self.HEIGHT), True
            )
            if not self.out.isOpened():
                logging.error("Failed to open HTTP GStreamer pipeline.")
                self.out = None
        except Exception as e:
            logging.error(f"Error initializing HTTP pipeline: {e}")
            self.out = None

    def stream_frame(self, frame: np.ndarray):
        if self.out:
            try:
                if frame.dtype != np.uint8:
                    frame = frame.astype(np.uint8)
                if len(frame.shape) < 3 or frame.shape[2] != 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                self.out.write(frame)
            except Exception as e:
                logging.error(f"Error streaming HTTP frame: {e}")

    def release(self):
        if self.out:
            self.out.release()
            self.out = None
            logging.info("HTTP pipeline released.")
