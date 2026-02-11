import cv2
import numpy as np
import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional
from classes.parameters import Parameters

logger = logging.getLogger(__name__)


@dataclass
class EncoderInfo:
    """Result of hardware encoder auto-detection."""
    encoder: str            # GStreamer element name (e.g. 'nvh264enc', 'x264enc')
    needs_nvvidconv: bool   # Whether pipeline needs 'nvvidconv' element
    hardware: bool          # True if GPU-accelerated


class EncoderDetector:
    """
    Probes the system for available GStreamer H.264 encoders.

    Detection order (best to worst):
      1. nvh264enc   — NVIDIA NVENC (GPU hardware encoding)
      2. vaapih264enc — Intel/AMD VA-API (GPU hardware encoding)
      3. x264enc     — Software fallback (always available)

    Detection uses `gst-inspect-1.0` which ships with GStreamer dev tools.
    If gst-inspect-1.0 is not available, falls back to software immediately.
    """

    _cached_result: Optional[EncoderInfo] = None

    @classmethod
    def detect(cls, allow_hardware: bool = True) -> EncoderInfo:
        """
        Detect the best available H.264 encoder.

        Args:
            allow_hardware: If False, skip hardware detection and use x264enc.

        Returns:
            EncoderInfo with encoder name, nvvidconv requirement, and hardware flag.
        """
        if cls._cached_result is not None and allow_hardware:
            return cls._cached_result

        if not allow_hardware:
            info = EncoderInfo(encoder='x264enc', needs_nvvidconv=False, hardware=False)
            logger.info("Hardware encoding disabled by config — using x264enc (software)")
            return info

        # Check if gst-inspect-1.0 is available
        gst_inspect = shutil.which('gst-inspect-1.0')
        if gst_inspect is None:
            info = EncoderInfo(encoder='x264enc', needs_nvvidconv=False, hardware=False)
            logger.info("gst-inspect-1.0 not found — using x264enc (software)")
            cls._cached_result = info
            return info

        # Try NVIDIA NVENC
        if cls._probe_element(gst_inspect, 'nvh264enc'):
            has_nvvidconv = cls._probe_element(gst_inspect, 'nvvidconv')
            info = EncoderInfo(encoder='nvh264enc', needs_nvvidconv=has_nvvidconv, hardware=True)
            logger.info("Detected NVIDIA NVENC — using nvh264enc (hardware)")
            cls._cached_result = info
            return info

        # Try Intel/AMD VA-API
        if cls._probe_element(gst_inspect, 'vaapih264enc'):
            info = EncoderInfo(encoder='vaapih264enc', needs_nvvidconv=False, hardware=True)
            logger.info("Detected VA-API — using vaapih264enc (hardware)")
            cls._cached_result = info
            return info

        # Software fallback
        info = EncoderInfo(encoder='x264enc', needs_nvvidconv=False, hardware=False)
        logger.info("No hardware encoder found — using x264enc (software)")
        cls._cached_result = info
        return info

    @staticmethod
    def _probe_element(gst_inspect_path: str, element: str) -> bool:
        """Check if a GStreamer element is available."""
        try:
            result = subprocess.run(
                [gst_inspect_path, element],
                capture_output=True,
                timeout=3,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            return False


class GStreamerHandler:
    """
    Streams video frames to a GStreamer H.264/RTP/UDP pipeline.

    This is a SECONDARY output for ground control stations (e.g. QGroundControl).
    It is completely independent of the dashboard streaming (HTTP/WebSocket/WebRTC).

    The encoder is selected automatically based on available hardware:
      - NVIDIA NVENC (nvh264enc) if detected and ENABLE_HARDWARE_ENCODING=true
      - Intel/AMD VA-API (vaapih264enc) if detected
      - Software x264enc as fallback (always available)

    Key considerations:
      - QGC expects RTP/UDP in H.264 format
      - appsrc pushes BGR frames from OpenCV into the pipeline
      - Bitrate, preset, and tuning are configurable via YAML
      - Frame orientation is handled upstream in VideoHandler
    """

    def __init__(self):
        self.out = None
        self.WIDTH = Parameters.GSTREAMER_WIDTH
        self.HEIGHT = Parameters.GSTREAMER_HEIGHT
        self.FRAMERATE = Parameters.GSTREAMER_FRAMERATE

        # Detect encoder
        allow_hw = getattr(Parameters, 'ENABLE_HARDWARE_ENCODING', False)
        self.encoder_info = EncoderDetector.detect(allow_hardware=allow_hw)

        self.pipeline = self._create_pipeline()

    def _create_pipeline(self) -> str:
        """
        Build the GStreamer pipeline string dynamically based on detected encoder.

        Returns:
            str: The constructed GStreamer pipeline string.
        """
        enc = self.encoder_info

        # Common source and caps
        source = (
            f"appsrc ! "
            f"video/x-raw,format=BGR,width={self.WIDTH},height={self.HEIGHT},"
            f"framerate={self.FRAMERATE}/1 ! "
            f"videoconvert"
        )

        # Encoder-specific section
        if enc.encoder == 'nvh264enc':
            # NVIDIA NVENC pipeline
            nvvidconv = " ! nvvidconv" if enc.needs_nvvidconv else ""
            encoder = (
                f"{nvvidconv} ! "
                f"nvh264enc bitrate={Parameters.GSTREAMER_BITRATE} ! "
                f"h264parse"
            )
        elif enc.encoder == 'vaapih264enc':
            # Intel/AMD VA-API pipeline
            encoder = (
                f" ! vaapih264enc bitrate={Parameters.GSTREAMER_BITRATE} ! "
                f"h264parse"
            )
        else:
            # Software x264enc pipeline (default)
            encoder = (
                f" ! x264enc "
                f"tune={Parameters.GSTREAMER_TUNE} "
                f"bitrate={Parameters.GSTREAMER_BITRATE} "
                f"key-int-max={Parameters.GSTREAMER_KEY_INT_MAX} "
                f"speed-preset={Parameters.GSTREAMER_SPEED_PRESET}"
            )

        # Common RTP payload and UDP sink
        sink = (
            f" ! rtph264pay config-interval=1 pt=96 ! "
            f"udpsink host={Parameters.GSTREAMER_HOST} "
            f"port={Parameters.GSTREAMER_PORT} "
            f"buffer-size={Parameters.GSTREAMER_BUFFER_SIZE}"
        )

        pipeline = f"{source}{encoder}{sink}"
        logger.debug(f"GStreamer pipeline: {pipeline}")
        return pipeline

    def initialize_stream(self):
        """Initialize the GStreamer pipeline using OpenCV's VideoWriter."""
        try:
            logger.info(
                f"Initializing GStreamer pipeline "
                f"(encoder={self.encoder_info.encoder}, "
                f"hardware={'yes' if self.encoder_info.hardware else 'no'}, "
                f"target={Parameters.GSTREAMER_HOST}:{Parameters.GSTREAMER_PORT})"
            )
            self.out = cv2.VideoWriter(
                self.pipeline, cv2.CAP_GSTREAMER, 0,
                self.FRAMERATE, (self.WIDTH, self.HEIGHT), True
            )
            if not self.out.isOpened():
                logger.error("Failed to open GStreamer pipeline.")
                if self.encoder_info.hardware:
                    logger.warning("Hardware encoder failed — retrying with software x264enc")
                    self.encoder_info = EncoderInfo(encoder='x264enc', needs_nvvidconv=False, hardware=False)
                    self.pipeline = self._create_pipeline()
                    self.out = cv2.VideoWriter(
                        self.pipeline, cv2.CAP_GSTREAMER, 0,
                        self.FRAMERATE, (self.WIDTH, self.HEIGHT), True
                    )
                    if not self.out.isOpened():
                        logger.error("Software encoder also failed. GStreamer output disabled.")
                        self.out = None
                else:
                    self.out = None
        except Exception as e:
            logger.error(f"Error initializing GStreamer pipeline: {e}")
            self.out = None

    def stream_frame(self, frame: np.ndarray):
        """
        Stream a video frame to the GStreamer pipeline.

        Args:
            frame: BGR uint8 frame from OpenCV.
        """
        if self.out:
            try:
                if frame.dtype != np.uint8:
                    frame = frame.astype(np.uint8)
                if len(frame.shape) == 2 or frame.shape[2] != 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                self.out.write(frame)
            except Exception as e:
                logger.error(f"Error streaming frame to GStreamer pipeline: {e}")

    def release(self):
        """Release the GStreamer pipeline and associated resources."""
        if self.out:
            self.out.release()
            logger.debug("GStreamer pipeline released.")

    @property
    def encoder_status(self) -> dict:
        """Return encoder status for the streaming status API."""
        return {
            'enabled': self.out is not None and self.out.isOpened() if self.out else False,
            'encoder': self.encoder_info.encoder,
            'hardware_accelerated': self.encoder_info.hardware,
            'host': str(Parameters.GSTREAMER_HOST),
            'port': int(Parameters.GSTREAMER_PORT),
        }
