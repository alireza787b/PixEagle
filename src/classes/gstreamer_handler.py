import ipaddress
import logging
import queue
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import ClassVar, Optional

import cv2
import numpy as np

from classes.parameters import Parameters

logger = logging.getLogger(__name__)


@dataclass
class EncoderInfo:
    """Result of hardware encoder auto-detection."""
    encoder: str            # GStreamer element name (e.g. 'nvh264enc', 'x264enc')
    needs_nvvidconv: bool   # Whether pipeline needs 'nvvidconv' element
    hardware: bool          # True if GPU-accelerated


@dataclass(frozen=True)
class GStreamerOutputConfig:
    """Validated snapshot used to construct one output-pipeline generation."""

    host: str
    port: int
    bitrate_kbps: int
    width: int
    height: int
    framerate: int
    buffer_size: int
    speed_preset: str
    key_interval: int
    tune: str

    _SPEED_PRESETS: ClassVar[frozenset[str]] = frozenset(
        {"ultrafast", "superfast", "veryfast", "faster", "fast"}
    )
    _TUNES: ClassVar[frozenset[str]] = frozenset({"zerolatency", "fastdecode", "stillimage"})
    _MAX_PIXEL_RATE: ClassVar[int] = 1920 * 1080 * 60

    @staticmethod
    def _bounded_int(name: str, value, minimum: int, maximum: int) -> int:
        if isinstance(value, bool):
            raise ValueError(f"{name} must be an integer")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be an integer") from exc
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{name} must be an integer")
        if not minimum <= parsed <= maximum:
            raise ValueError(f"{name} must be in the range {minimum}..{maximum}")
        return parsed

    @staticmethod
    def _normalized_host(value) -> str:
        if value is None or isinstance(value, bool):
            raise ValueError("GSTREAMER_HOST must be an IP address or DNS hostname")
        host = str(value).strip()
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]
        if not host:
            raise ValueError("GSTREAMER_HOST must not be empty")

        try:
            return str(ipaddress.ip_address(host))
        except ValueError:
            try:
                ascii_host = host.encode("idna").decode("ascii")
            except UnicodeError as exc:
                raise ValueError("GSTREAMER_HOST must be an IP address or DNS hostname") from exc

        hostname = ascii_host[:-1] if ascii_host.endswith(".") else ascii_host
        labels = hostname.split(".")
        if len(ascii_host) > 254 or not labels:
            raise ValueError("GSTREAMER_HOST must be an IP address or DNS hostname")
        if any(
            not label
            or len(label) > 63
            or re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label) is None
            for label in labels
        ):
            raise ValueError("GSTREAMER_HOST must be an IP address or DNS hostname")
        return ascii_host

    @classmethod
    def from_parameters(cls) -> "GStreamerOutputConfig":
        width = cls._bounded_int("GSTREAMER_WIDTH", Parameters.GSTREAMER_WIDTH, 16, 3840)
        height = cls._bounded_int("GSTREAMER_HEIGHT", Parameters.GSTREAMER_HEIGHT, 16, 2160)
        if width % 2 or height % 2:
            raise ValueError("GSTREAMER_WIDTH and GSTREAMER_HEIGHT must be even for H.264 output")
        framerate = cls._bounded_int("GSTREAMER_FRAMERATE", Parameters.GSTREAMER_FRAMERATE, 1, 60)
        if width * height * framerate > cls._MAX_PIXEL_RATE:
            raise ValueError(
                "GStreamer output exceeds the supported pixel-rate budget "
                "(up to 1920x1080@60 or 3840x2160@15)"
            )

        speed_preset = str(Parameters.GSTREAMER_SPEED_PRESET).strip().lower()
        if speed_preset not in cls._SPEED_PRESETS:
            raise ValueError("GSTREAMER_SPEED_PRESET is not supported")
        tune = str(Parameters.GSTREAMER_TUNE).strip().lower()
        if tune not in cls._TUNES:
            raise ValueError("GSTREAMER_TUNE is not supported")

        return cls(
            host=cls._normalized_host(Parameters.GSTREAMER_HOST),
            port=cls._bounded_int("GSTREAMER_PORT", Parameters.GSTREAMER_PORT, 1, 65535),
            bitrate_kbps=cls._bounded_int("GSTREAMER_BITRATE", Parameters.GSTREAMER_BITRATE, 100, 100000),
            width=width,
            height=height,
            framerate=framerate,
            buffer_size=cls._bounded_int(
                "GSTREAMER_BUFFER_SIZE", Parameters.GSTREAMER_BUFFER_SIZE, 65536, 100000000
            ),
            speed_preset=speed_preset,
            key_interval=cls._bounded_int("GSTREAMER_KEY_INT_MAX", Parameters.GSTREAMER_KEY_INT_MAX, 1, 1000),
            tune=tune,
        )


@dataclass(frozen=True)
class _QueuedFrame:
    """One writer-queue item with explicit normalization ownership."""

    frame: np.ndarray
    prepared: bool = False


class EncoderDetector:
    """
    Probes the system for available GStreamer H.264 encoders.

    Detection order (best to worst):
      1. nvh264enc   — NVIDIA NVENC (GPU hardware encoding)
      2. vaapih264enc — Intel/AMD VA-API (GPU hardware encoding)
      3. x264enc     — Software fallback when the plugin is installed

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
      - Software x264enc as fallback when installed

    Key considerations:
      - QGC expects RTP/UDP in H.264 format
      - appsrc pushes BGR frames from OpenCV into the pipeline
      - Bitrate, preset, and tuning are configurable via YAML
      - Frame orientation is handled upstream in VideoHandler
      - stream_frame() is non-blocking: frames are queued for a background writer thread
    """

    _WRITER_STOP_TIMEOUT_S = 2.0
    _PIPELINE_RELEASE_TIMEOUT_S = 2.0
    _FRAME_QUEUE_SIZE = 2

    def __init__(self):
        self.out = None
        self._configuration_error: Optional[str] = None
        try:
            self._config: Optional[GStreamerOutputConfig] = GStreamerOutputConfig.from_parameters()
        except ValueError as exc:
            self._config = None
            self._configuration_error = str(exc)
        self.WIDTH = self._config.width if self._config else 0
        self.HEIGHT = self._config.height if self._config else 0
        self.FRAMERATE = self._config.framerate if self._config else 0

        # Detect encoder
        allow_hw = getattr(Parameters, 'ENABLE_HARDWARE_ENCODING', False)
        self.encoder_info = EncoderDetector.detect(allow_hardware=allow_hw)

        self.pipeline = self._create_pipeline() if self._config else ""

        # Non-blocking writer thread + bounded queue
        self._frame_queue: queue.Queue = queue.Queue(maxsize=self._FRAME_QUEUE_SIZE)
        self._writer_thread: Optional[threading.Thread] = None
        self._release_thread: Optional[threading.Thread] = None
        self._retiring_output = None
        self._writer_stop = threading.Event()
        self._state_lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._queue_drops = 0
        self._frames_queued = 0
        self._frames_written = 0
        self._frames_resized = 0
        self._frames_letterboxed = 0
        self._frames_rate_limited = 0
        self._last_submit_monotonic: Optional[float] = None
        self._last_error: Optional[str] = None
        self._opencv_gstreamer_available: Optional[bool] = None

    def _create_pipeline(self) -> str:
        """
        Build the GStreamer pipeline string dynamically based on detected encoder.

        Returns:
            str: The constructed GStreamer pipeline string.
        """
        if self._config is None:
            return ""

        enc = self.encoder_info
        config = self._config

        # Common source and caps
        source = (
            f"appsrc ! "
            f"video/x-raw,format=BGR,width={config.width},height={config.height},"
            f"framerate={config.framerate}/1 ! "
            f"videoconvert"
        )

        # Encoder-specific section
        if enc.encoder == 'nvh264enc':
            # NVIDIA NVENC pipeline
            nvvidconv = " ! nvvidconv" if enc.needs_nvvidconv else ""
            encoder = (
                f"{nvvidconv} ! "
                f"nvh264enc bitrate={config.bitrate_kbps} ! "
                f"h264parse"
            )
        elif enc.encoder == 'vaapih264enc':
            # Intel/AMD VA-API pipeline
            encoder = (
                f" ! vaapih264enc bitrate={config.bitrate_kbps} ! "
                f"h264parse"
            )
        else:
            # Software x264enc pipeline (default)
            encoder = (
                f" ! x264enc "
                f"tune={config.tune} "
                f"bitrate={config.bitrate_kbps} "
                f"key-int-max={config.key_interval} "
                f"speed-preset={config.speed_preset}"
            )

        # Common RTP payload and UDP sink
        sink = (
            f" ! rtph264pay config-interval=1 pt=96 ! "
            f'udpsink host="{config.host}" '
            f"port={config.port} "
            f"buffer-size={config.buffer_size}"
        )

        pipeline = f"{source}{encoder}{sink}"
        logger.debug(f"GStreamer pipeline: {pipeline}")
        return pipeline

    @staticmethod
    def _detect_opencv_gstreamer_support() -> Optional[bool]:
        """Return OpenCV's reported GStreamer support, or None if unknown."""
        try:
            build_info = cv2.getBuildInformation()
        except Exception:
            return None

        match = re.search(r"(?mi)^\s*GStreamer\s*:\s*(YES|NO)\b", build_info or "")
        if match is None:
            return None
        return match.group(1).upper() == "YES"

    def _open_writer(self):
        """Create the OpenCV writer for the current pipeline."""
        return cv2.VideoWriter(
            self.pipeline,
            cv2.CAP_GSTREAMER,
            0,
            self.FRAMERATE,
            (self.WIDTH, self.HEIGHT),
            True,
        )

    def _release_output_bounded(self, output) -> bool:
        """Finalize one OpenCV writer without blocking the caller indefinitely."""
        with self._state_lock:
            existing_thread = self._release_thread
            if existing_thread is not None and existing_thread.is_alive():
                self._last_error = "pipeline_release_still_running"
                logger.error("Previous GStreamer pipeline release is still running")
                return False
            self._release_thread = None
            if self._retiring_output is not None and self._retiring_output is not output:
                self._last_error = "pipeline_release_ownership_conflict"
                logger.error("Refusing to replace an unreleased GStreamer pipeline generation")
                return False
            self._retiring_output = output

        release_errors: list[Exception] = []

        def release_output() -> None:
            try:
                output.release()
            except Exception as exc:
                release_errors.append(exc)
            finally:
                with self._state_lock:
                    if release_errors:
                        self._last_error = (
                            f"pipeline_release_failed:{type(release_errors[0]).__name__}"
                        )
                    else:
                        if self.out is output:
                            self.out = None
                        if self._retiring_output is output:
                            self._retiring_output = None
                        if self._last_error and (
                            self._last_error.startswith("pipeline_release_")
                            or self._last_error == "writer_thread_stop_timeout"
                        ):
                            self._last_error = None
                    if self._release_thread is threading.current_thread():
                        self._release_thread = None

        release_thread = threading.Thread(
            target=release_output,
            name="gstreamer-release",
            daemon=True,
        )
        with self._state_lock:
            self._release_thread = release_thread
        try:
            release_thread.start()
        except Exception as exc:
            with self._state_lock:
                if self._release_thread is release_thread:
                    self._release_thread = None
                self._last_error = f"pipeline_release_thread_start_failed:{type(exc).__name__}"
            logger.error("Failed to start GStreamer pipeline release thread: %s", exc)
            return False
        release_thread.join(timeout=self._PIPELINE_RELEASE_TIMEOUT_S)
        if release_thread.is_alive():
            with self._state_lock:
                self._last_error = "pipeline_release_timeout"
            logger.error("GStreamer pipeline release did not finish within the shutdown timeout")
            return False

        with self._state_lock:
            if self._release_thread is release_thread:
                self._release_thread = None
        if release_errors:
            logger.error("Error releasing GStreamer pipeline: %s", release_errors[0])
            return False
        return True

    def initialize_stream(self) -> bool:
        """Initialize the GStreamer pipeline using OpenCV's VideoWriter."""
        with self._lifecycle_lock:
            return self._initialize_stream_locked()

    def _initialize_stream_locked(self) -> bool:
        """Initialize one writer generation while holding the lifecycle lock."""
        if not self.release():
            logger.error(
                "Refusing to start a new GStreamer writer while previous generation cleanup is incomplete"
            )
            return False
        self._last_error = None
        if self._configuration_error is not None:
            self._last_error = "invalid_gstreamer_configuration"
            logger.error("GStreamer output configuration is invalid: %s", self._configuration_error)
            return False
        self._opencv_gstreamer_available = self._detect_opencv_gstreamer_support()
        if self._opencv_gstreamer_available is False:
            self._last_error = "opencv_gstreamer_backend_unavailable"
            logger.error(
                "GStreamer output requested, but the active OpenCV build reports "
                "GStreamer: NO. Output remains disabled; browser media paths are unaffected."
            )
            return False

        output = None
        try:
            logger.info(
                f"Initializing GStreamer pipeline "
                f"(encoder={self.encoder_info.encoder}, "
                f"hardware={'yes' if self.encoder_info.hardware else 'no'}, "
                f"target={self._config.host}:{self._config.port})"
            )
            output = self._open_writer()
            if not output.isOpened():
                logger.error("Failed to open GStreamer pipeline.")
                failed_output = output
                output = None
                if not self._release_output_bounded(failed_output):
                    return False
                if self.encoder_info.hardware:
                    logger.warning("Hardware encoder failed — retrying with software x264enc")
                    self.encoder_info = EncoderInfo(encoder='x264enc', needs_nvvidconv=False, hardware=False)
                    self.pipeline = self._create_pipeline()
                    output = self._open_writer()
                    if not output.isOpened():
                        logger.error("Software encoder also failed. GStreamer output disabled.")
                        failed_output = output
                        output = None
                        if not self._release_output_bounded(failed_output):
                            return False
        except Exception as e:
            logger.error(f"Error initializing GStreamer pipeline: {e}")
            self._last_error = f"pipeline_initialization_failed:{type(e).__name__}"
            if output is not None:
                self._release_output_bounded(output)
            output = None

        if output is None:
            self._last_error = self._last_error or "gstreamer_pipeline_open_failed"
            return False

        frame_queue: queue.Queue = queue.Queue(maxsize=self._FRAME_QUEUE_SIZE)
        stop_event = threading.Event()
        writer_thread = threading.Thread(
            target=self._writer_loop,
            args=(output, frame_queue, stop_event),
            name="gstreamer-writer",
            daemon=True,
        )
        try:
            writer_thread.start()
        except Exception as exc:
            stop_event.set()
            with self._state_lock:
                self._last_error = f"writer_thread_start_failed:{type(exc).__name__}"
            logger.error("Failed to start GStreamer writer thread: %s", exc)
            self._release_output_bounded(output)
            return False
        with self._state_lock:
            self.out = output
            self._frame_queue = frame_queue
            self._writer_stop = stop_event
            self._writer_thread = writer_thread
            self._last_submit_monotonic = None
        logger.info("GStreamer writer thread started")
        return True

    def _writer_loop(self, output, frame_queue: queue.Queue, stop_event: threading.Event):
        """Background thread that pulls frames from queue and writes to pipeline."""
        while not stop_event.is_set():
            try:
                queued_frame = frame_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if not output.isOpened():
                    with self._state_lock:
                        self._last_error = "writer_closed"
                    stop_event.set()
                    break
                prepared_frame = (
                    queued_frame.frame
                    if queued_frame.prepared
                    else self._prepare_frame(queued_frame.frame)
                )
                if prepared_frame is None:
                    continue
                output.write(prepared_frame)
                with self._state_lock:
                    self._frames_written += 1
            except Exception as e:
                logger.error("Error writing frame to GStreamer pipeline: %s", e)
                with self._state_lock:
                    self._last_error = f"frame_write_failed:{type(e).__name__}"
                stop_event.set()

    def _prepare_frame(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Normalize dtype, channels, contiguity, and output dimensions."""
        if not isinstance(frame, np.ndarray) or frame.size == 0:
            with self._state_lock:
                self._last_error = "invalid_frame"
            return None

        try:
            if frame.dtype != np.uint8:
                frame = np.clip(frame, 0, 255).astype(np.uint8)

            if frame.ndim == 2:
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            elif frame.ndim == 3 and frame.shape[2] == 1:
                frame = cv2.cvtColor(frame[:, :, 0], cv2.COLOR_GRAY2BGR)
            elif frame.ndim == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            elif frame.ndim != 3 or frame.shape[2] != 3:
                with self._state_lock:
                    self._last_error = "unsupported_frame_shape"
                return None

            if frame.shape[1] != self.WIDTH or frame.shape[0] != self.HEIGHT:
                source_height, source_width = frame.shape[:2]
                scale = min(self.WIDTH / source_width, self.HEIGHT / source_height)
                resized_width = max(1, min(self.WIDTH, int(round(source_width * scale))))
                resized_height = max(1, min(self.HEIGHT, int(round(source_height * scale))))
                interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
                resized = cv2.resize(
                    frame,
                    (resized_width, resized_height),
                    interpolation=interpolation,
                )
                if resized_width == self.WIDTH and resized_height == self.HEIGHT:
                    frame = resized
                else:
                    canvas = np.zeros((self.HEIGHT, self.WIDTH, 3), dtype=np.uint8)
                    x_offset = (self.WIDTH - resized_width) // 2
                    y_offset = (self.HEIGHT - resized_height) // 2
                    canvas[
                        y_offset : y_offset + resized_height,
                        x_offset : x_offset + resized_width,
                    ] = resized
                    frame = canvas
                    with self._state_lock:
                        self._frames_letterboxed += 1
                with self._state_lock:
                    self._frames_resized += 1

            return np.ascontiguousarray(frame)
        except Exception as e:
            logger.error("Error preparing frame for GStreamer: %s", e)
            with self._state_lock:
                self._last_error = f"frame_prepare_failed:{type(e).__name__}"
            return None

    def prepare_frame_for_osd(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Return an output-sized buffer owned by output-specific OSD composition."""
        prepared = self._prepare_frame(frame)
        if prepared is None:
            return None
        if np.shares_memory(prepared, frame):
            return prepared.copy()
        return prepared

    @staticmethod
    def _validate_source_frame(frame: np.ndarray) -> Optional[str]:
        """Return a stable error code when a submitted frame cannot be normalized."""
        if not isinstance(frame, np.ndarray) or frame.size == 0:
            return "invalid_frame"
        if frame.ndim == 2:
            return None
        if frame.ndim == 3 and frame.shape[2] in {1, 3, 4}:
            return None
        return "unsupported_frame_shape"

    def is_frame_due(self, submitted_at: Optional[float] = None) -> bool:
        """Return whether the active writer can accept a frame at the configured cadence."""
        now = time.monotonic() if submitted_at is None else submitted_at
        with self._state_lock:
            output = self.out
            writer_thread = self._writer_thread
            if (
                output is None
                or self._writer_stop.is_set()
                or writer_thread is None
                or not writer_thread.is_alive()
                or self.FRAMERATE <= 0
            ):
                return False
            try:
                if not output.isOpened():
                    return False
            except Exception:
                return False
            last_submit = self._last_submit_monotonic
            return last_submit is None or now - last_submit >= 1.0 / self.FRAMERATE

    def stream_frame(
        self,
        frame: np.ndarray,
        submitted_at: Optional[float] = None,
        *,
        prepared: bool = False,
    ) -> bool:
        """
        Queue a video frame for the GStreamer writer thread (non-blocking).

        If the queue is full, the oldest frame is dropped and replaced.
        This ensures the main processing loop is never blocked by encoding.

        Args:
            frame: OpenCV-compatible grayscale, BGR, or BGRA frame. The caller
                must not mutate it after successful submission.
            submitted_at: Monotonic submission time shared with ``is_frame_due``.
            prepared: True only when the caller already normalized the frame to
                the exact output canvas and composed output-specific OSD.

        Returns:
            True when the frame was queued; False when rejected or rate-limited.
        """
        if prepared:
            validation_error = None
            if (
                not isinstance(frame, np.ndarray)
                or frame.dtype != np.uint8
                or frame.shape != (self.HEIGHT, self.WIDTH, 3)
                or not frame.flags.c_contiguous
            ):
                validation_error = "invalid_prepared_frame"
        else:
            validation_error = self._validate_source_frame(frame)
        if validation_error is not None:
            with self._state_lock:
                self._last_error = validation_error
            return False

        now = time.monotonic() if submitted_at is None else submitted_at
        with self._state_lock:
            output = self.out
            frame_queue = self._frame_queue
            stop_event = self._writer_stop
            writer_thread = self._writer_thread
            if (
                output is None
                or stop_event.is_set()
                or writer_thread is None
                or not writer_thread.is_alive()
                or self.FRAMERATE <= 0
            ):
                return False
            try:
                if not output.isOpened():
                    return False
            except Exception:
                return False

            last_submit = self._last_submit_monotonic
            if last_submit is not None and now - last_submit < 1.0 / self.FRAMERATE:
                self._frames_rate_limited += 1
                return False

            self._last_submit_monotonic = now
            try:
                frame_queue.put_nowait(_QueuedFrame(frame=frame, prepared=prepared))
                self._frames_queued += 1
            except queue.Full:
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    frame_queue.put_nowait(_QueuedFrame(frame=frame, prepared=prepared))
                    self._frames_queued += 1
                    self._queue_drops += 1
                except queue.Full:
                    self._queue_drops += 1
                    return False
        return True

    def release(self) -> bool:
        """Release the GStreamer pipeline and stop the writer thread."""
        with self._lifecycle_lock:
            return self._release_locked()

    def _release_locked(self) -> bool:
        """Stop and finalize the owned writer generation without losing ownership."""
        with self._state_lock:
            release_thread = self._release_thread
            if release_thread is not None and release_thread.is_alive():
                self._last_error = "pipeline_release_still_running"
                logger.error("Previous GStreamer pipeline release is still running")
                return False
            self._release_thread = None
            output = self.out
            retiring_output = self._retiring_output
            if output is not None and retiring_output is not None and output is not retiring_output:
                self._last_error = "pipeline_release_ownership_conflict"
                logger.error("Multiple unreleased GStreamer pipeline generations are owned")
                return False
            writer_thread = self._writer_thread
            stop_event = self._writer_stop
            frame_queue = self._frame_queue

        stop_event.set()
        if writer_thread is not None and writer_thread is not threading.current_thread():
            writer_thread.join(timeout=self._WRITER_STOP_TIMEOUT_S)

        stopped = writer_thread is None or not writer_thread.is_alive()
        if not stopped:
            with self._state_lock:
                self._last_error = "writer_thread_stop_timeout"
            logger.error("GStreamer writer thread did not stop within the shutdown timeout")
        else:
            with self._state_lock:
                if self._writer_thread is writer_thread:
                    self._writer_thread = None

        while True:
            try:
                frame_queue.get_nowait()
            except queue.Empty:
                break

        if not stopped:
            return False
        output_to_release = output if output is not None else retiring_output
        if output_to_release is None:
            return True

        if not self._release_output_bounded(output_to_release):
            return False

        logger.debug("GStreamer pipeline released.")
        return True

    @property
    def encoder_status(self) -> dict:
        """Return encoder status for the streaming status API."""
        with self._state_lock:
            output = self.out
            retiring_output = self._retiring_output
            queue_depth = self._frame_queue.qsize()
            writer_thread = self._writer_thread
            release_thread = self._release_thread
            writer_stopped = self._writer_stop.is_set()
            writer_operational = bool(
                output is not None
                and writer_thread is not None
                and writer_thread.is_alive()
                and not writer_stopped
            )
            enabled = False
            if writer_operational:
                try:
                    enabled = bool(output.isOpened())
                except Exception:
                    enabled = False
            queue_drops = self._queue_drops
            frames_queued = self._frames_queued
            frames_written = self._frames_written
            frames_resized = self._frames_resized
            frames_letterboxed = self._frames_letterboxed
            frames_rate_limited = self._frames_rate_limited
            opencv_gstreamer_available = self._opencv_gstreamer_available
            last_error = self._last_error
            cleanup_pending = bool(
                retiring_output is not None
                or (release_thread is not None and release_thread.is_alive())
                or (output is not None and not enabled)
            )
        return {
            'enabled': enabled,
            'encoder': self.encoder_info.encoder,
            'hardware_accelerated': self.encoder_info.hardware,
            'host': self._config.host if self._config else None,
            'port': self._config.port if self._config else None,
            'queue_drops': queue_drops,
            'queue_depth': queue_depth,
            'frames_queued': frames_queued,
            'frames_written': frames_written,
            'frames_resized': frames_resized,
            'frames_letterboxed': frames_letterboxed,
            'frames_rate_limited': frames_rate_limited,
            'opencv_gstreamer_available': opencv_gstreamer_available,
            'last_error': last_error,
            'configuration_error': self._configuration_error,
            'cleanup_pending': cleanup_pending,
        }
