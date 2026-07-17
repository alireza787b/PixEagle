"""
Video Handler Module
Handles video input from various sources with optimized capture pipelines.
Supports OpenCV and GStreamer backends for maximum performance on embedded systems.

=== COORDINATE MAPPING CONSISTENCY ===
This module ensures accurate coordinate mapping between dashboard clicks and video frames
by maintaining consistent dimensions across all video sources:

1. All GStreamer pipelines include 'videoscale' to enforce target dimensions
2. Video dimensions are validated against configured CAPTURE_WIDTH/HEIGHT
3. RTSP pipelines use smart scaling with ultra-low latency optimizations
4. Fallback pipelines maintain the same target dimensions
5. Emergency fallbacks without scaling are clearly marked

This ensures that dashboard clicks at (x,y) correctly map to frame coordinates
regardless of the camera's native resolution or connection method.
"""

import cv2
import time
import logging
import math
import platform
import re
import threading
from collections import deque
from typing import Optional, Dict, Any, Tuple
from classes.parameters import Parameters
from classes.logging_manager import logging_manager

logger = logging.getLogger(__name__)


class VideoHandler:
    """
    Handles video input from various sources with optimized capture methods.
    
    Supported video sources:
    - VIDEO_FILE: Video files (mp4, avi, etc.)
    - USB_CAMERA: USB webcams and cameras
    - RTSP_STREAM: RTSP network streams
    - UDP_STREAM: UDP network streams
    - HTTP_STREAM: HTTP/HTTPS streams
    - CSI_CAMERA: MIPI CSI cameras (Raspberry Pi, Jetson)
    - CUSTOM_GSTREAMER: Custom GStreamer pipeline
    
    Features:
    - Automatic backend selection (OpenCV vs GStreamer)
    - Optimized capture parameters
    - Frame history buffer
    - Automatic retry on connection failure
    """

    _UNKNOWN_LENGTH_EOF_FAILURE_THRESHOLD = 3
    
    def __init__(self):
        """Initialize video handler with configured source."""
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_history = deque(maxlen=Parameters.STORE_LAST_FRAMES)

        # Universal frame orientation settings (applied to all source types/backends)
        self._frame_rotation_deg = self._normalize_rotation_deg(
            getattr(Parameters, "FRAME_ROTATION_DEG", 0)
        )
        self._frame_flip_mode = self._normalize_flip_mode(
            getattr(Parameters, "FRAME_FLIP_MODE", "none")
        )
        
        # Video properties
        self.width: Optional[int] = None
        self.height: Optional[int] = None
        self.fps: Optional[float] = None
        self.delay_frame: int = 33  # Default 30 FPS
        self._requested_fps: float = float(getattr(Parameters, "CAPTURE_FPS", 0) or 0)
        self._effective_fps: Optional[float] = None
        self._capture_mode: str = "uninitialized"
        self._last_pipeline_strategy: str = "uninitialized"
        self._last_capture_error: Optional[str] = None
        self._gstreamer_usable_cache: Optional[bool] = None
        self._async_capture_thread: Optional[threading.Thread] = None
        self._async_capture_stop = threading.Event()
        self._async_capture_lock = threading.Lock()
        self._async_capture_generation = 0
        self._async_capture_opening = False
        self._async_latest_frame = None
        self._async_latest_frame_sequence = 0
        self._async_consumed_frame_sequence = 0
        self._async_latest_frame_time: Optional[float] = None

        # VIDEO_FILE playback is an explicit state machine. Replayed media is
        # suitable for tracking, streaming, and validation, but never a live
        # measurement source for autonomous following.
        self._prefetched_frame = None
        self._video_file_eof_policy = self._normalize_video_file_eof_policy(
            getattr(Parameters, "VIDEO_FILE_EOF_POLICY", "STOP")
        )
        self._video_file_playback_state = (
            "opening" if self._is_video_file_source() else "not_applicable"
        )
        self._video_file_playback_epoch = 0
        self._video_file_loop_count = 0
        self._video_file_frames_in_epoch = 0
        self._video_file_terminal_reason: Optional[str] = None
        self._video_file_expected_frame_count: Optional[int] = None
        self._video_file_rewind_strategy: Optional[str] = None
        self._video_file_ambiguous_failure_count = 0
        
        # Current frame states
        self.current_raw_frame = None
        self.current_osd_frame = None
        self.current_resized_raw_frame = None
        self.current_resized_osd_frame = None
        
        # Robust connection handling - configurable via Parameters
        self._consecutive_failures = 0
        self._max_consecutive_failures = getattr(Parameters, 'RTSP_MAX_CONSECUTIVE_FAILURES', 10)
        self._last_successful_frame_time = time.time()
        self._connection_timeout = getattr(Parameters, 'RTSP_CONNECTION_TIMEOUT', 5.0)
        self._is_recovering = False
        self._recovery_attempts = 0
        self._max_recovery_attempts = getattr(Parameters, 'RTSP_MAX_RECOVERY_ATTEMPTS', 3)
        self._frame_cache = deque(maxlen=getattr(Parameters, 'RTSP_FRAME_CACHE_SIZE', 5))
        self._next_recovery_time = 0.0
        self._recovery_backoff_base = getattr(Parameters, 'RTSP_RECOVERY_BACKOFF_BASE', 1.0)
        self._recovery_backoff_max = getattr(Parameters, 'RTSP_RECOVERY_BACKOFF_MAX', 10.0)
        self._init_failed = False
        self._frame_sequence = 0
        self._last_frame_status = {
            "source": "none",
            "status": "unavailable",
            "usable_for_following": False,
            "reason": "not_initialized",
            "timestamp": time.time(),
            "last_successful_frame_time": self._last_successful_frame_time,
            "frame_age_seconds": None,
            "frame_sequence": self._frame_sequence,
            "consecutive_failures": self._consecutive_failures,
            "cached_frames_available": len(self._frame_cache),
            "connection_open": False,
            **self._video_file_status_fields(),
        }
        
        # Platform detection for optimization
        self.platform = platform.system()
        self.is_arm = platform.machine().startswith('arm') or platform.machine().startswith('aarch')
        
        # Initialize video source
        try:
            self.delay_frame = self.init_video_source()
            logger.info(f"Video handler initialized: {self.width}x{self.height}@{self.fps}fps")
        except Exception as e:
            # Degraded startup mode: keep backend online even if camera source is unavailable.
            self._init_failed = True
            self.width = Parameters.CAPTURE_WIDTH
            self.height = Parameters.CAPTURE_HEIGHT
            self.fps = Parameters.CAPTURE_FPS or Parameters.DEFAULT_FPS
            self._effective_fps = self.fps
            self.delay_frame = max(int(1000 / max(self.fps, 1)), 1)
            self._capture_mode = "degraded"
            self._last_pipeline_strategy = "degraded_startup"
            self._last_capture_error = str(e)
            logger.error(
                "Failed to initialize video handler: %s. Starting in degraded mode without active video source.",
                e
            )
    
    def init_video_source(self, max_retries: int = 5, retry_delay: float = 1.0) -> int:
        """
        Initialize video source with retry logic.
        
        Args:
            max_retries: Maximum number of connection attempts
            retry_delay: Delay between retries in seconds
            
        Returns:
            Frame delay in milliseconds
            
        Raises:
            ValueError: If video source cannot be opened
        """
        if self._is_video_file_source():
            self._prefetched_frame = None
            self._video_file_playback_state = "opening"
            self._video_file_playback_epoch = 0
            self._video_file_loop_count = 0
            self._video_file_frames_in_epoch = 0
            self._video_file_terminal_reason = None
            self._video_file_expected_frame_count = None
            self._video_file_rewind_strategy = None
            self._video_file_ambiguous_failure_count = 0

        if self._should_use_async_udp_capture():
            return self._initialize_async_udp_capture()

        for attempt in range(max_retries):
            logger.debug(f"Attempt {attempt + 1}/{max_retries} to open video source")
            self._requested_fps = float(getattr(Parameters, "CAPTURE_FPS", 0) or 0)
            
            try:
                self.cap = self._create_capture_object()
                
                if self.cap and self.cap.isOpened():
                    probe_ok, probe_frame = self._probe_initial_frame(self.cap)
                    if not probe_ok:
                        self._last_capture_error = "Capture opened but initial frame probe returned no frames"
                        logger.warning(
                            "Video source opened but failed initial frame probe on attempt %d",
                            attempt + 1
                        )
                        if self._try_video_file_opencv_fallback_after_probe_failure():
                            probe_ok, probe_frame = self._probe_initial_frame(self.cap)
                            if not probe_ok:
                                self._last_capture_error = (
                                    "Video file OpenCV fallback opened but initial frame probe returned no frames"
                                )
                                logger.warning(
                                    "Video file OpenCV fallback opened but failed initial frame probe on attempt %d",
                                    attempt + 1
                                )
                                self.cap.release()
                                self.cap = None
                                continue
                        else:
                            self.cap.release()
                            self.cap = None
                            continue

                    # Extract video properties
                    capture_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    capture_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    if probe_frame is not None and hasattr(probe_frame, "shape") and len(probe_frame.shape) >= 2:
                        capture_height = int(probe_frame.shape[0])
                        capture_width = int(probe_frame.shape[1])
                    self.width, self.height = self._get_oriented_dimensions(capture_width, capture_height)
                    detected_fps = self.cap.get(cv2.CAP_PROP_FPS)
                    self.fps = detected_fps if detected_fps and detected_fps > 0 else Parameters.DEFAULT_FPS
                    self._effective_fps = self.fps
                    
                    # Validate dimensions for coordinate mapping consistency
                    if self.width <= 0 or self.height <= 0:
                        logger.warning("Invalid dimensions detected, using configured defaults")
                        self.width, self.height = self._get_oriented_dimensions(
                            Parameters.CAPTURE_WIDTH,
                            Parameters.CAPTURE_HEIGHT
                        )

                    # Coordinate mapping validation
                    expected_width, expected_height = self._get_oriented_dimensions(
                        Parameters.CAPTURE_WIDTH,
                        Parameters.CAPTURE_HEIGHT
                    )

                    if self.width != expected_width or self.height != expected_height:
                        mismatch_msg = (
                            f"Video dimensions ({self.width}x{self.height}) differ from "
                            f"configured ({expected_width}x{expected_height})."
                        )
                        if Parameters.VIDEO_SOURCE_TYPE.endswith("_CAMERA"):
                            logger.info(
                                "%s Camera negotiated nearest supported mode; "
                                "continuing with detected dimensions.",
                                mismatch_msg
                            )
                        else:
                            logger.warning(
                                "%s This is non-fatal but may indicate scaling pipeline issues.",
                                mismatch_msg
                            )

                        # For coordinate mapping consistency, trust the configured dimensions
                        # if the difference is due to pipeline scaling issues
                        if Parameters.VIDEO_SOURCE_TYPE == "RTSP_STREAM" and Parameters.USE_GSTREAMER:
                            logger.info("RTSP GStreamer: Using configured dimensions for coordinate consistency")
                            self.width = expected_width
                            self.height = expected_height
                    
                    delay_frame = max(int(1000 / max(self.fps, 1)), 1)
                    if self._capture_mode == "uninitialized":
                        backend_label = "gstreamer" if Parameters.USE_GSTREAMER else "opencv"
                        self._capture_mode = f"{Parameters.VIDEO_SOURCE_TYPE.lower()}_{backend_label}"
                    if self._last_pipeline_strategy == "uninitialized":
                        self._last_pipeline_strategy = self._capture_mode
                    self._last_capture_error = None
                    if self._is_video_file_source():
                        self._prefetched_frame = probe_frame
                        self._video_file_playback_state = "ready"
                        frame_count = self._capture_property_float(
                            self.cap,
                            cv2.CAP_PROP_FRAME_COUNT,
                        )
                        if frame_count is not None and frame_count > 0:
                            self._video_file_expected_frame_count = int(frame_count)
                    
                    logger.info(f"Video source opened successfully: {Parameters.VIDEO_SOURCE_TYPE}")
                    logger.debug(
                        "Properties - Width: %s, Height: %s, Requested FPS: %s, Effective FPS: %s, Mode: %s",
                        self.width,
                        self.height,
                        self._requested_fps,
                        self._effective_fps,
                        self._capture_mode
                    )
                    
                    return delay_frame
                else:
                    logger.warning(f"Failed to open video source on attempt {attempt + 1}")
                    self._last_capture_error = f"Failed to open video source on attempt {attempt + 1}"
                    
            except Exception as e:
                logger.error(f"Exception during video source initialization: {e}")
                self._last_capture_error = str(e)
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
        
        raise ValueError(f"Could not open video source after {max_retries} attempts")

    @staticmethod
    def _normalize_video_file_eof_policy(value: Any) -> str:
        """Return a supported VIDEO_FILE EOF policy, failing closed to STOP."""
        normalized = str(value or "").strip().upper()
        if normalized in {"LOOP", "STOP"}:
            return normalized
        logger.warning(
            "Unsupported VIDEO_FILE_EOF_POLICY=%r; allowed values are LOOP or STOP. "
            "Falling back to STOP",
            value,
        )
        return "STOP"

    @staticmethod
    def _is_video_file_source() -> bool:
        """Return whether the configured input is a local replay file."""
        return str(getattr(Parameters, "VIDEO_SOURCE_TYPE", "") or "").strip().upper() == "VIDEO_FILE"

    def _video_file_status_fields(self) -> Dict[str, Any]:
        """Return bounded playback provenance fields for status and health APIs."""
        replay_source = self._is_video_file_source()
        return {
            "replay_source": replay_source,
            "video_file_eof_policy": self._video_file_eof_policy if replay_source else None,
            "video_file_playback_state": (
                self._video_file_playback_state if replay_source else "not_applicable"
            ),
            "video_file_playback_epoch": (
                self._video_file_playback_epoch if replay_source else None
            ),
            "video_file_loop_count": self._video_file_loop_count if replay_source else None,
            "video_file_expected_frame_count": (
                self._video_file_expected_frame_count if replay_source else None
            ),
            "video_file_ambiguous_failure_count": (
                self._video_file_ambiguous_failure_count if replay_source else None
            ),
        }

    @staticmethod
    def _capture_property_float(cap: Any, property_id: int) -> Optional[float]:
        """Read a finite capture property without trusting backend-specific types."""
        if cap is None:
            return None
        try:
            value = float(cap.get(property_id))
        except (TypeError, ValueError, OverflowError, AttributeError):
            return None
        return value if math.isfinite(value) else None

    def _should_use_async_udp_capture(self) -> bool:
        """Return True when UDP/GStreamer capture must not block the frame loop."""
        return (
            str(getattr(Parameters, "VIDEO_SOURCE_TYPE", "") or "").upper() == "UDP_STREAM"
            and bool(getattr(Parameters, "USE_GSTREAMER", False))
        )

    def _initialize_async_udp_capture(self) -> int:
        """
        Start UDP/GStreamer capture in a daemon reader.

        OpenCV's GStreamer backend can block both while opening a UDP receiver
        with no sender and while reading after the sender stops. Keeping that
        work off the main loop lets PixEagle fail closed with stale/cached frame
        status instead of freezing tracking, streaming, or control orchestration.
        """
        self.width, self.height = self._get_oriented_dimensions(
            Parameters.CAPTURE_WIDTH,
            Parameters.CAPTURE_HEIGHT
        )
        self.fps = Parameters.CAPTURE_FPS or Parameters.DEFAULT_FPS
        self._effective_fps = self.fps
        self._capture_mode = "udp_gstreamer_async"
        self._last_pipeline_strategy = "udp_gstreamer_async_reader"
        self._last_capture_error = None
        self._start_async_udp_reader()
        delay_frame = max(int(1000 / max(float(self.fps or 1), 1)), 1)
        logger.info(
            "UDP/GStreamer video source initialized with asynchronous reader: %sx%s@%sfps",
            self.width,
            self.height,
            self.fps,
        )
        return delay_frame

    def _start_async_udp_reader(self) -> None:
        """Start the UDP reader thread, replacing stale stopped generations."""
        with self._async_capture_lock:
            if (
                self._async_capture_thread
                and self._async_capture_thread.is_alive()
                and not self._async_capture_stop.is_set()
            ):
                return

            self._async_capture_generation += 1
            generation = self._async_capture_generation
            stop_event = threading.Event()
            self._async_capture_stop = stop_event
            self._async_capture_opening = False
            self._async_latest_frame = None
            self._async_latest_frame_sequence = 0
            self._async_consumed_frame_sequence = 0
            self._async_latest_frame_time = None
            thread = threading.Thread(
                target=self._async_udp_reader_loop,
                args=(generation, stop_event),
                name="pixeagle-udp-gstreamer-reader",
                daemon=True,
            )
            self._async_capture_thread = thread

        thread.start()

    def _async_generation_is_active(self, generation: int) -> bool:
        """Return True when a reader generation still owns async state."""
        return generation == self._async_capture_generation

    def _async_udp_reader_loop(
        self,
        generation: int,
        stop_event: threading.Event,
    ) -> None:
        """Own blocking OpenCV/GStreamer UDP open/read calls."""
        cap = None
        try:
            pipeline = self._build_gstreamer_udp_pipeline()
            logger.debug("UDP GStreamer async pipeline: %s", pipeline)
            with self._async_capture_lock:
                if self._async_generation_is_active(generation):
                    self._async_capture_opening = True
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            with self._async_capture_lock:
                if self._async_generation_is_active(generation):
                    self._async_capture_opening = False
                    self.cap = cap

            if stop_event.is_set() or not self._async_generation_is_active(generation):
                return

            if not cap or not cap.isOpened():
                self._last_capture_error = "UDP GStreamer async capture failed to open"
                logger.warning(self._last_capture_error)
                return

            self._last_capture_error = None
            logging_manager.log_connection_status(logger, "Video", True, "UDP GStreamer async reader")

            while not stop_event.is_set() and self._async_generation_is_active(generation):
                ret, frame = cap.read()
                if stop_event.is_set() or not self._async_generation_is_active(generation):
                    break
                if ret and frame is not None:
                    frame = self._apply_frame_orientation(frame)
                    with self._async_capture_lock:
                        if self._async_generation_is_active(generation):
                            self._async_latest_frame = frame.copy()
                            self._async_latest_frame_sequence += 1
                            self._async_latest_frame_time = time.time()
                else:
                    self._last_capture_error = "UDP GStreamer async frame read returned no data"
                    time.sleep(0.02)
        except Exception as e:
            with self._async_capture_lock:
                if self._async_generation_is_active(generation):
                    self._async_capture_opening = False
                    self._last_capture_error = f"UDP GStreamer async reader exception: {e}"
            logger.warning("UDP GStreamer async reader exception: %s", e)
        finally:
            with self._async_capture_lock:
                if self._async_generation_is_active(generation):
                    self._async_capture_opening = False
            if cap:
                cap.release()
            with self._async_capture_lock:
                if self.cap is cap and self._async_generation_is_active(generation):
                    self.cap = None
                if (
                    self._async_generation_is_active(generation)
                    and self._async_capture_thread is threading.current_thread()
                ):
                    self._async_capture_thread = None

    def _get_async_udp_frame(self) -> Optional[Any]:
        """Return the latest UDP frame without blocking on OpenCV."""
        with self._async_capture_lock:
            frame = None if self._async_latest_frame is None else self._async_latest_frame.copy()
            sequence = self._async_latest_frame_sequence
            frame_time = self._async_latest_frame_time
            connection_open = bool(self.cap and self.cap.isOpened())
            opening = self._async_capture_opening

        if frame is not None and sequence > self._async_consumed_frame_sequence:
            self._async_consumed_frame_sequence = sequence
            self.current_raw_frame = frame
            self.frame_history.append(frame.copy())
            self._reset_failure_counters()
            if frame_time is not None:
                self._last_successful_frame_time = frame_time
                self._last_frame_status["last_successful_frame_time"] = frame_time
            return frame

        self._consecutive_failures += 1
        current_time = time.time()
        if frame_time is None:
            reason = "udp_async_waiting_for_first_frame"
        elif current_time - frame_time >= self._connection_timeout:
            reason = "udp_async_frame_stale"
        else:
            reason = "udp_async_awaiting_new_frame"

        if frame is not None:
            self._frame_cache.append(frame.copy())

        cached_frame = self._get_cached_frame()
        self._last_frame_status.update({
            "reason": reason,
            "connection_open": connection_open,
            "async_capture_opening": opening,
            "async_latest_frame_sequence": sequence,
            "async_consumed_frame_sequence": self._async_consumed_frame_sequence,
        })
        return cached_frame
    
    def _create_capture_object(self) -> cv2.VideoCapture:
        """
        Create VideoCapture object based on source type and settings.
        
        Returns:
            Configured VideoCapture object
            
        Raises:
            ValueError: If source type is not supported
        """
        source_type = Parameters.VIDEO_SOURCE_TYPE
        use_gstreamer = Parameters.USE_GSTREAMER
        self._capture_mode = "uninitialized"
        self._last_pipeline_strategy = "uninitialized"
        
        logger.debug(f"Creating capture for {source_type}, GStreamer: {use_gstreamer}")
        
        # Source type to handler mapping
        handlers = {
            "VIDEO_FILE": self._create_video_file_capture,
            "USB_CAMERA": self._create_usb_camera_capture,
            "RTSP_OPENCV": self._create_rtsp_opencv_capture,
            "RTSP_STREAM": self._create_rtsp_capture,
            "UDP_STREAM": self._create_udp_capture,
            "HTTP_STREAM": self._create_http_capture,
            "CSI_CAMERA": self._create_csi_capture,
            "CUSTOM_GSTREAMER": self._create_custom_gstreamer_capture
        }
        
        if source_type not in handlers:
            raise ValueError(f"Unsupported video source type: {source_type}")
        
        return handlers[source_type](use_gstreamer)

    def _should_prefer_gstreamer_for_source(self, source_type: str) -> bool:
        """
        Decide whether GStreamer should be preferred for a given source type.

        This keeps source-level routing explicit while preserving existing global
        USE_GSTREAMER semantics for currently supported high-impact sources.
        """
        source = str(source_type or "").upper()
        return bool(getattr(Parameters, "USE_GSTREAMER", False)) and source in {
            "VIDEO_FILE",
            "USB_CAMERA",
        }

    def _is_gstreamer_usable(self) -> bool:
        """
        Determine if current OpenCV build has GStreamer support.

        Returns cached result after the first check.
        """
        if self._gstreamer_usable_cache is not None:
            return self._gstreamer_usable_cache

        try:
            build_info = cv2.getBuildInformation()
            match = re.search(r"(?mi)^\s*GStreamer\s*:\s*(YES|NO)\s*$", build_info)
            if match:
                self._gstreamer_usable_cache = match.group(1).upper() == "YES"
            else:
                # Conservative default: do not block GStreamer attempts if build parsing fails.
                self._gstreamer_usable_cache = True
                logger.debug("Could not determine OpenCV GStreamer support from build info")
        except Exception as e:
            # Conservative default: allow GStreamer attempt and rely on runtime fallback.
            self._gstreamer_usable_cache = True
            logger.debug("Failed to inspect OpenCV build info for GStreamer support: %s", e)

        return self._gstreamer_usable_cache

    def _try_video_file_opencv_fallback_after_probe_failure(self) -> bool:
        """
        Switch VIDEO_FILE capture from GStreamer to OpenCV when frame probing fails.

        Returns:
            True if OpenCV fallback was attempted and opened successfully.
        """
        if Parameters.VIDEO_SOURCE_TYPE != "VIDEO_FILE":
            return False
        if not self._capture_mode.startswith("video_file_gstreamer"):
            return False

        logger.warning(
            "VIDEO_FILE GStreamer capture opened but delivered no frames; retrying with OpenCV backend"
        )
        if self.cap:
            self.cap.release()

        self.cap = self._open_video_file_opencv_capture(
            strategy_name="video_file_opencv_fallback_probe"
        )
        return bool(self.cap and self.cap.isOpened())
    
    def _create_video_file_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create capture for video file."""
        if use_gstreamer and self._should_prefer_gstreamer_for_source("VIDEO_FILE"):
            if not self._is_gstreamer_usable():
                logger.warning(
                    "USE_GSTREAMER=true but OpenCV build lacks GStreamer support; "
                    "using OpenCV backend for VIDEO_FILE"
                )
                self._last_capture_error = "GStreamer unavailable in OpenCV build for VIDEO_FILE"
                return self._open_video_file_opencv_capture(strategy_name="video_file_opencv_no_gstreamer")

            pipeline = self._build_gstreamer_file_pipeline()
            self._last_pipeline_strategy = "video_file_gstreamer_primary"
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            if cap.isOpened():
                self._capture_mode = "video_file_gstreamer"
                self._last_capture_error = None
                return cap

            cap.release()
            self._last_capture_error = "Video file GStreamer pipeline failed to open"
            logger.warning("VIDEO_FILE GStreamer open failed, falling back to OpenCV backend")
            return self._open_video_file_opencv_capture(strategy_name="video_file_opencv_fallback")

        return self._open_video_file_opencv_capture(strategy_name="video_file_opencv_primary")

    def _open_video_file_opencv_capture(self, strategy_name: str) -> cv2.VideoCapture:
        """Create VIDEO_FILE capture via OpenCV backend."""
        cap = cv2.VideoCapture(Parameters.VIDEO_FILE_PATH)
        self._capture_mode = strategy_name
        self._last_pipeline_strategy = strategy_name
        return cap
    
    def _create_usb_camera_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create optimized capture for USB camera."""
        if use_gstreamer and self._should_prefer_gstreamer_for_source("USB_CAMERA"):
            if not self._is_gstreamer_usable():
                logger.warning(
                    "USE_GSTREAMER=true but OpenCV build lacks GStreamer support; "
                    "using OpenCV backend for USB camera"
                )
                self._last_capture_error = "GStreamer unavailable in OpenCV build for USB camera"
                return self._open_usb_camera_opencv_capture(strategy_name="usb_opencv_no_gstreamer")
            return self._create_usb_camera_capture_with_fallbacks()
        return self._open_usb_camera_opencv_capture(strategy_name="usb_opencv_primary")

    def _create_usb_camera_capture_with_fallbacks(self) -> cv2.VideoCapture:
        """Create USB capture with progressive fallback strategies."""
        requested_format = str(getattr(Parameters, "PIXEL_FORMAT", "YUYV") or "YUYV").upper()
        if requested_format == "MJPEG":
            requested_format = "MJPG"

        alternate_format = "MJPG" if requested_format != "MJPG" else "YUYV"
        strategies = [
            (f"usb_gstreamer_{requested_format.lower()}_strict", requested_format, True),
            (f"usb_gstreamer_{requested_format.lower()}_relaxed_fps", requested_format, False),
            (f"usb_gstreamer_{alternate_format.lower()}_strict", alternate_format, True),
            (f"usb_gstreamer_{alternate_format.lower()}_relaxed_fps", alternate_format, False),
        ]

        for strategy_name, pixel_format, strict_fps in strategies:
            pipeline = self._build_gstreamer_usb_pipeline(
                pixel_format_override=pixel_format,
                strict_fps=strict_fps
            )
            logger.info("Trying USB camera strategy: %s", strategy_name)
            logger.debug("USB GStreamer pipeline (%s): %s", strategy_name, pipeline)
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            if cap.isOpened():
                self._capture_mode = strategy_name
                self._last_pipeline_strategy = strategy_name
                self._last_capture_error = None
                if not strict_fps:
                    logger.warning(
                        "USB camera requested FPS %s could not be strictly enforced; using relaxed negotiation",
                        Parameters.CAPTURE_FPS
                    )
                return cap
            cap.release()
            self._last_capture_error = f"USB strategy failed: {strategy_name}"
            logger.warning("USB capture strategy failed: %s", strategy_name)

        logger.warning("All USB GStreamer strategies failed, falling back to OpenCV backend")
        self._last_capture_error = "All USB GStreamer strategies failed"
        return self._open_usb_camera_opencv_capture(strategy_name="usb_opencv_fallback")

    def _open_usb_camera_opencv_capture(self, strategy_name: str) -> cv2.VideoCapture:
        """Create USB capture via OpenCV backend."""
        if self.platform == "Linux" and Parameters.USE_V4L2_BACKEND:
            cap = cv2.VideoCapture(Parameters.CAMERA_INDEX, cv2.CAP_V4L2)
        elif self.platform == "Windows":
            cap = cv2.VideoCapture(Parameters.CAMERA_INDEX, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(Parameters.CAMERA_INDEX)

        self._optimize_opencv_capture(cap)
        self._capture_mode = strategy_name
        self._last_pipeline_strategy = strategy_name
        return cap

    def _create_rtsp_opencv_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create RTSP capture with forced OpenCV backend."""
        if use_gstreamer:
            logger.info("VIDEO_SOURCE_TYPE=RTSP_OPENCV forces OpenCV backend; ignoring USE_GSTREAMER=true")
        self._capture_mode = "rtsp_opencv"
        self._last_pipeline_strategy = "rtsp_opencv_forced"
        return self._create_opencv_rtsp_optimized()
    
    def _create_rtsp_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create optimized capture for RTSP stream with auto-detection and fallback."""
        if use_gstreamer:
            self._capture_mode = "rtsp_gstreamer"
            return self._create_gstreamer_rtsp_with_fallback()
        else:
            self._capture_mode = "rtsp_opencv_auto"
            return self._create_opencv_rtsp_optimized()
    
    def _create_gstreamer_rtsp_with_fallback(self) -> cv2.VideoCapture:
        """Create GStreamer RTSP capture with automatic fallback pipelines."""
        # Try primary optimized pipeline first
        pipeline = self._build_gstreamer_rtsp_pipeline()
        logger.info("Attempting primary RTSP GStreamer pipeline...")
        self._last_pipeline_strategy = "rtsp_gstreamer_primary"
        
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            self._capture_mode = "rtsp_gstreamer_primary"
            logging_manager.log_connection_status(logger, "Video", True, "Primary GStreamer RTSP pipeline")
            self._log_rtsp_stream_info(cap)
            return cap
        
        cap.release()
        self._last_capture_error = "RTSP primary GStreamer pipeline failed"
        logger.warning("Primary pipeline failed, trying fallback pipelines...")
        
        # Try fallback pipelines
        fallback_pipelines = self._build_fallback_rtsp_pipelines()
        
        for i, fallback_pipeline in enumerate(fallback_pipelines, 1):
            logger.info(f"Trying fallback pipeline {i}/{len(fallback_pipelines)}...")
            logger.debug(f"Fallback pipeline: {fallback_pipeline}")
            self._last_pipeline_strategy = f"rtsp_gstreamer_fallback_{i}"
            
            cap = cv2.VideoCapture(fallback_pipeline, cv2.CAP_GSTREAMER)
            if cap.isOpened():
                self._capture_mode = f"rtsp_gstreamer_fallback_{i}"
                logging_manager.log_connection_status(logger, "Video", True, f"Fallback pipeline {i}")
                self._log_rtsp_stream_info(cap)
                return cap
            
            cap.release()
            logger.warning(f"Fallback pipeline {i} failed")
            self._last_capture_error = f"RTSP fallback pipeline {i} failed"
        
        # If all GStreamer pipelines fail, try OpenCV as last resort
        logger.warning("All GStreamer pipelines failed, falling back to OpenCV...")
        self._last_capture_error = "All GStreamer RTSP pipelines failed"
        return self._create_opencv_rtsp_optimized()
    
    def _create_opencv_rtsp_optimized(self) -> cv2.VideoCapture:
        """Create OpenCV RTSP capture with optimizations."""
        rtsp_url = Parameters.RTSP_URL
        logger.info("Attempting OpenCV RTSP capture...")
        
        # Try FFMPEG backend first (usually best for RTSP)
        self._last_pipeline_strategy = "rtsp_opencv_ffmpeg"
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        
        if not cap.isOpened():
            logger.warning("FFMPEG backend failed, trying default backend...")
            self._last_capture_error = "OpenCV RTSP FFMPEG backend failed"
            self._last_pipeline_strategy = "rtsp_opencv_default"
            cap = cv2.VideoCapture(rtsp_url)
        
        if cap.isOpened():
            # Real-time optimizations
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)        # Minimum buffering
            cap.set(cv2.CAP_PROP_FPS, max(int(Parameters.CAPTURE_FPS or Parameters.DEFAULT_FPS or 1), 1))
            self._capture_mode = self._last_pipeline_strategy
            self._last_capture_error = None
            
            logging_manager.log_connection_status(logger, "Video", True, "OpenCV RTSP")
            self._log_rtsp_stream_info(cap)
        else:
            self._last_capture_error = "All OpenCV RTSP backends failed"
            logging_manager.log_connection_status(logger, "Video", False, "All RTSP methods failed")
        
        return cap
    
    def _create_udp_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create capture for UDP stream."""
        if use_gstreamer:
            pipeline = self._build_gstreamer_udp_pipeline()
            self._capture_mode = "udp_gstreamer"
            self._last_pipeline_strategy = "udp_gstreamer_primary"
            return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            self._capture_mode = "udp_opencv_ffmpeg"
            self._last_pipeline_strategy = "udp_opencv_ffmpeg_primary"
            return cv2.VideoCapture(Parameters.UDP_URL, cv2.CAP_FFMPEG)
    
    def _create_http_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create capture for HTTP stream."""
        if use_gstreamer:
            pipeline = self._build_gstreamer_http_pipeline()
            self._capture_mode = "http_gstreamer"
            self._last_pipeline_strategy = "http_gstreamer_primary"
            return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            self._capture_mode = "http_opencv"
            self._last_pipeline_strategy = "http_opencv_primary"
            return cv2.VideoCapture(Parameters.HTTP_URL)
    
    def _create_csi_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create capture for CSI camera (always uses GStreamer)."""
        pipeline = self._build_gstreamer_csi_pipeline()
        logger.debug(f"CSI GStreamer pipeline: {pipeline}")
        self._capture_mode = "csi_gstreamer"
        self._last_pipeline_strategy = "csi_gstreamer_primary"
        return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    
    def _create_custom_gstreamer_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create capture from custom GStreamer pipeline."""
        pipeline = Parameters.CUSTOM_PIPELINE
        if not pipeline:
            raise ValueError("CUSTOM_PIPELINE is empty")
        logger.debug(f"Custom GStreamer pipeline: {pipeline}")
        self._capture_mode = "custom_gstreamer"
        self._last_pipeline_strategy = "custom_gstreamer_primary"
        return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    
    def _build_gstreamer_file_pipeline(self) -> str:
        """Build GStreamer pipeline for video file."""
        return (
            f"filesrc location={Parameters.VIDEO_FILE_PATH} ! "
            f"decodebin ! videoconvert ! video/x-raw,format=BGR ! "
            f"videoscale ! video/x-raw,width={Parameters.CAPTURE_WIDTH},"
            f"height={Parameters.CAPTURE_HEIGHT} ! appsink drop=true sync=false"
        )
    
    def _build_gstreamer_usb_pipeline(
        self,
        pixel_format_override: Optional[str] = None,
        strict_fps: bool = True
    ) -> str:
        """Build optimized GStreamer pipeline for USB camera."""
        # Get pipeline template based on pixel format
        pixel_format = str(pixel_format_override or Parameters.PIXEL_FORMAT or "YUYV").upper()
        if pixel_format == "MJPEG":
            pixel_format = "MJPG"

        if pixel_format == "MJPG":
            template = Parameters.USB_MJPEG
        else:
            template = Parameters.USB_YUYV

        capture_fps = max(int(getattr(Parameters, "CAPTURE_FPS", 0) or Parameters.DEFAULT_FPS or 1), 1)
        device_path = str(getattr(Parameters, "DEVICE_PATH", "") or "").strip()
        default_device_path = f"/dev/video{Parameters.CAMERA_INDEX}"
        effective_device_path = device_path or default_device_path

        # Format pipeline with parameters
        pipeline = template.format(
            device_id=Parameters.CAMERA_INDEX,
            device_path=effective_device_path,
            width=Parameters.CAPTURE_WIDTH,
            height=Parameters.CAPTURE_HEIGHT,
            fps=capture_fps
        )

        # Backward compatibility for templates that still hardcode /dev/video{device_id}
        if device_path and "{device_path}" not in template:
            pipeline = pipeline.replace(
                f"device={default_device_path}",
                f"device={effective_device_path}",
                1
            )

        if not strict_fps:
            pipeline = self._relax_gstreamer_framerate_constraint(pipeline)

        return pipeline

    def _relax_gstreamer_framerate_constraint(self, pipeline: str) -> str:
        """Remove strict framerate caps to allow camera auto-negotiation."""
        relaxed = re.sub(r",\s*framerate=\d+\s*/\s*\d+", "", pipeline)
        relaxed = re.sub(r"\s+framerate=\d+\s*/\s*\d+", " ", relaxed)
        return re.sub(r"\s+", " ", relaxed).strip()
    
    def _build_gstreamer_rtsp_pipeline(self) -> str:
        """
        Build ultra-low latency GStreamer pipeline for RTSP stream with smart scaling.

        Maintains coordinate consistency by scaling to configured dimensions while
        preserving real-time performance optimizations.
        """
        rtsp_url = Parameters.RTSP_URL
        target_width = Parameters.CAPTURE_WIDTH
        target_height = Parameters.CAPTURE_HEIGHT

        # Get RTSP settings from config (with safe defaults)
        rtsp_protocol = getattr(Parameters, 'RTSP_PROTOCOL', 'tcp').lower()
        rtsp_latency = getattr(Parameters, 'RTSP_LATENCY', 200)

        # Validate protocol
        if rtsp_protocol not in ['tcp', 'udp', 'auto']:
            logger.warning(f"Invalid RTSP_PROTOCOL '{rtsp_protocol}', defaulting to 'tcp'")
            rtsp_protocol = 'tcp'

        # Build protocol string (empty for auto)
        protocol_str = f"protocols={rtsp_protocol} " if rtsp_protocol != 'auto' else ""

        # Low latency pipeline with smart scaling for coordinate consistency
        # Uses decodebin for maximum compatibility (auto-detects codec)
        pipeline = (
            f"rtspsrc location={rtsp_url} "
            f"{protocol_str}"                   # Protocol from config (tcp recommended)
            f"latency={rtsp_latency} "          # Latency from config (200ms recommended)
            f"buffer-mode=auto "                # Auto buffer mode
            f"drop-on-latency=true "            # Drop frames immediately if late
            f"do-rtcp=false "                   # Disable RTCP overhead
            f"! decodebin "                     # Auto-detect and decode (more compatible than explicit h264)
            f"! videoconvert "
            f"! videoscale "                    # Smart scaling for coordinate consistency
            f"method=0 "                        # Nearest neighbor (fastest scaling)
            f"! video/x-raw,format=BGR,width={target_width},height={target_height} "  # Target dimensions
            f"! appsink "                       # Application sink
            f"drop=true "                       # Drop frames if app is slow
            f"max-buffers=1 "                   # Absolute minimum buffering
            f"sync=false "                      # No clock synchronization
            f"async=false "                     # No async processing
            f"emit-signals=true "               # Enable new-sample signal
            f"wait-on-eos=false"                # Don't wait on EOS
        )

        logger.debug(f"Ultra-low latency RTSP pipeline with smart scaling: {pipeline}")
        return pipeline
    
    def _build_fallback_rtsp_pipelines(self) -> list:
        """
        Build fallback RTSP pipelines with smart scaling for coordinate consistency.

        Each pipeline maintains the same target dimensions to ensure accurate
        coordinate mapping regardless of which pipeline succeeds.
        """
        rtsp_url = Parameters.RTSP_URL
        target_width = Parameters.CAPTURE_WIDTH
        target_height = Parameters.CAPTURE_HEIGHT

        # Get RTSP settings from config (with safe defaults)
        rtsp_protocol = getattr(Parameters, 'RTSP_PROTOCOL', 'tcp').lower()
        rtsp_latency = getattr(Parameters, 'RTSP_LATENCY', 200)
        protocol_str = f"protocols={rtsp_protocol} " if rtsp_protocol != 'auto' else ""

        fallback_pipelines = [
            # Fallback 1: Config protocol with decodebin + smart scaling (simpler than primary)
            (
                f"rtspsrc location={rtsp_url} "
                f"{protocol_str}latency={rtsp_latency} drop-on-latency=true do-rtcp=false "
                f"! queue max-size-buffers=1 leaky=downstream "
                f"! decodebin ! videoconvert ! video/x-raw,format=BGR "
                f"! videoscale method=0 "          # Fastest scaling method
                f"! video/x-raw,width={target_width},height={target_height} "
                f"! appsink drop=true max-buffers=1 sync=false"
            ),

            # Fallback 2: Higher latency for unstable connections
            (
                f"rtspsrc location={rtsp_url} "
                f"{protocol_str}latency={rtsp_latency + 300} drop-on-latency=true "
                f"! queue max-size-buffers=2 leaky=downstream "
                f"! decodebin ! videoconvert ! video/x-raw,format=BGR "
                f"! videoscale method=0 "          # Fastest scaling method
                f"! video/x-raw,width={target_width},height={target_height} "
                f"! appsink drop=true max-buffers=1 sync=false"
            ),

            # Fallback 3: Auto-detect protocol with scaling (for cameras that require UDP)
            (
                f"rtspsrc location={rtsp_url} latency={rtsp_latency} "
                f"! decodebin ! videoconvert ! video/x-raw,format=BGR "
                f"! videoscale method=0 "          # Fastest scaling method
                f"! video/x-raw,width={target_width},height={target_height} "
                f"! appsink sync=false"
            ),

            # Fallback 4: No scaling (emergency fallback - may have coord issues)
            (
                f"rtspsrc location={rtsp_url} {protocol_str}latency={rtsp_latency} "
                f"! decodebin ! videoconvert ! video/x-raw,format=BGR "
                f"! appsink sync=false"
            )
        ]
        
        return fallback_pipelines
    
    def _build_gstreamer_udp_pipeline(self) -> str:
        """Build GStreamer pipeline for UDP stream."""
        template = Parameters.UDP
        return template.format(
            url=Parameters.UDP_URL,
            width=Parameters.CAPTURE_WIDTH,
            height=Parameters.CAPTURE_HEIGHT
        )
    
    def _build_gstreamer_http_pipeline(self) -> str:
        """Build GStreamer pipeline for HTTP stream."""
        template = Parameters.HTTP
        return template.format(
            url=Parameters.HTTP_URL,
            width=Parameters.CAPTURE_WIDTH,
            height=Parameters.CAPTURE_HEIGHT
        )
    
    def _build_gstreamer_csi_pipeline(self) -> str:
        """Build GStreamer pipeline for CSI camera."""
        # Detect platform and use appropriate pipeline
        if 'tegra' in platform.release():  # NVIDIA Jetson
            template = Parameters.CSI_NVIDIA
        else:  # Assume Raspberry Pi
            template = Parameters.CSI_RPI
        
        return template.format(
            sensor_id=Parameters.SENSOR_ID,
            width=Parameters.CAPTURE_WIDTH,
            height=Parameters.CAPTURE_HEIGHT,
            fps=Parameters.CAPTURE_FPS
        )

    def _normalize_rotation_deg(self, rotation_deg: Any) -> int:
        """Normalize configured rotation to supported right-angle values."""
        try:
            value = int(rotation_deg)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid FRAME_ROTATION_DEG=%r; falling back to 0",
                rotation_deg
            )
            return 0

        if value not in {0, 90, 180, 270}:
            logger.warning(
                "Unsupported FRAME_ROTATION_DEG=%s; allowed values are 0,90,180,270. Falling back to 0",
                value
            )
            return 0
        return value

    def _normalize_flip_mode(self, flip_mode: Any) -> str:
        """Normalize configured flip mode to supported values."""
        value = str(flip_mode).strip().lower()
        allowed = {"none", "horizontal", "vertical", "both"}
        if value not in allowed:
            logger.warning(
                "Unsupported FRAME_FLIP_MODE=%r; allowed values are none,horizontal,vertical,both. Falling back to none",
                flip_mode
            )
            return "none"
        return value

    def _get_oriented_dimensions(self, width: int, height: int) -> Tuple[int, int]:
        """Return effective frame dimensions after configured rotation."""
        if self._frame_rotation_deg in (90, 270):
            return height, width
        return width, height

    def _probe_initial_frame(
        self,
        cap: cv2.VideoCapture,
        attempts: int = 3,
        delay_seconds: float = 0.05
    ) -> Tuple[bool, Optional[Any]]:
        """
        Validate that an opened capture can actually deliver frames.

        Some backends report isOpened()=True even when caps negotiation later fails.
        """
        for probe_idx in range(1, attempts + 1):
            try:
                ret, frame = cap.read()
                if ret and frame is not None:
                    return True, frame
            except Exception as e:
                logger.debug("Initial frame probe exception (%d/%d): %s", probe_idx, attempts, e)
                self._last_capture_error = f"Initial frame probe exception: {e}"
            if probe_idx < attempts and delay_seconds > 0:
                time.sleep(delay_seconds)
        return False, None

    def _apply_frame_orientation(self, frame: Any) -> Any:
        """Apply configured rotation/flip and keep dimensions in sync."""
        if frame is None:
            return None

        if self._frame_rotation_deg == 90:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        elif self._frame_rotation_deg == 180:
            frame = cv2.rotate(frame, cv2.ROTATE_180)
        elif self._frame_rotation_deg == 270:
            frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        if self._frame_flip_mode == "horizontal":
            frame = cv2.flip(frame, 1)
        elif self._frame_flip_mode == "vertical":
            frame = cv2.flip(frame, 0)
        elif self._frame_flip_mode == "both":
            frame = cv2.flip(frame, -1)

        if hasattr(frame, "shape") and len(frame.shape) >= 2:
            self.height = int(frame.shape[0])
            self.width = int(frame.shape[1])

        return frame
    
    def _optimize_opencv_capture(self, cap: cv2.VideoCapture) -> None:
        """
        Apply OpenCV-specific optimizations.
        
        Args:
            cap: VideoCapture object to optimize
        """
        try:
            # Set resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, Parameters.CAPTURE_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, Parameters.CAPTURE_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, max(int(Parameters.CAPTURE_FPS or Parameters.DEFAULT_FPS or 1), 1))
            
            # Reduce buffer size for lower latency
            cap.set(cv2.CAP_PROP_BUFFERSIZE, Parameters.OPENCV_BUFFER_SIZE)
            
            # Set FOURCC if specified (e.g., for MJPEG)
            if Parameters.OPENCV_FOURCC:
                fourcc = cv2.VideoWriter_fourcc(*Parameters.OPENCV_FOURCC)
                cap.set(cv2.CAP_PROP_FOURCC, fourcc)
            
            # Platform-specific optimizations
            if self.platform == "Linux":
                # V4L2 specific settings
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            logger.debug("OpenCV capture optimized")
            
        except Exception as e:
            logger.warning(f"Failed to apply OpenCV optimizations: {e}")
    
    def _log_rtsp_stream_info(self, cap: cv2.VideoCapture) -> None:
        """
        Auto-detect and log RTSP stream properties (like VLC does).
        
        Args:
            cap: Opened VideoCapture object
        """
        try:
            # Get stream properties
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            fourcc = cap.get(cv2.CAP_PROP_FOURCC)
            backend = cap.getBackendName()
            
            # Convert FOURCC to readable format
            fourcc_str = ""
            if fourcc > 0:
                fourcc_bytes = int(fourcc).to_bytes(4, byteorder='little')
                try:
                    fourcc_str = fourcc_bytes.decode('ascii')
                except:
                    fourcc_str = f"0x{int(fourcc):08x}"
            
            # Log detected properties
            logger.info("=== RTSP Stream Auto-Detection ===")
            logger.info(f"URL: {Parameters.RTSP_URL}")
            logger.info(f"Backend: {backend}")
            logger.info(f"Resolution: {width}x{height}")
            logger.info(f"FPS: {fps:.2f}")
            logger.info(f"Codec: {fourcc_str}")
            
            # Additional stream info
            buffer_size = cap.get(cv2.CAP_PROP_BUFFERSIZE)
            logger.info(f"Buffer size: {int(buffer_size)}")
            
            # Test frame capture to verify stream
            ret, frame = cap.read()
            if ret and frame is not None:
                actual_shape = frame.shape
                logger.info(f"Actual frame shape: {actual_shape}")
                logger.info("RTSP stream is working - real-time feed ready")
            else:
                logger.warning("Could not capture test frame from RTSP stream")
                
        except Exception as e:
            logger.error(f"Error detecting RTSP stream properties: {e}")

    def _resolve_active_backend(self) -> str:
        """
        Resolve the backend label from actual active strategy/mode.

        Falls back to USE_GSTREAMER intent when strategy data is inconclusive.
        """
        mode_and_strategy = f"{self._capture_mode} {self._last_pipeline_strategy}".lower()
        if "opencv" in mode_and_strategy:
            return "OpenCV"
        if "gstreamer" in mode_and_strategy:
            return "GStreamer"
        if Parameters.VIDEO_SOURCE_TYPE in {"CSI_CAMERA", "CUSTOM_GSTREAMER"}:
            return "GStreamer"
        return "GStreamer" if Parameters.USE_GSTREAMER else "OpenCV"
    
    def get_frame(self) -> Optional[Any]:
        """
        Read and return the next frame with robust error handling and auto-recovery.
        
        Returns:
            Frame as numpy array, cached frame if available, or None
        """
        if self._should_use_async_udp_capture():
            return self._get_async_udp_frame()

        if self._is_video_file_source() and self._video_file_playback_state == "ended":
            return self._get_video_file_boundary_frame(
                self._video_file_terminal_reason or "video_file_eof_stopped"
            )

        if not self.cap:
            # Log error only once, then use debug level to avoid spam
            if not hasattr(self, '_capture_error_logged'):
                logger.error("Video capture not initialized")
                self._capture_error_logged = True
            else:
                logger.debug("Video capture not initialized (repeated)")
            current_time = time.time()
            if current_time >= self._next_recovery_time:
                self._attempt_recovery()
            return self._get_cached_frame()
        
        try:
            ret, frame = self._read_next_capture_frame()
            
            if ret and frame is not None:
                # Successful frame capture
                frame = self._apply_frame_orientation(frame)
                self.current_raw_frame = frame
                self.frame_history.append(frame.copy())  # Copy: downstream drawing modifies in-place
                self._reset_failure_counters()
                return frame
            else:
                # Frame read failed - handle gracefully
                if self._is_video_file_source():
                    return self._handle_video_file_read_failure()
                return self._handle_frame_failure()
                
        except Exception as e:
            logger.warning(f"Exception during frame capture: {e}")
            return self._handle_frame_failure()

    def _read_next_capture_frame(self) -> Tuple[bool, Optional[Any]]:
        """Read in capture order, including a frame consumed by initialization."""
        if self._prefetched_frame is not None:
            frame = self._prefetched_frame
            self._prefetched_frame = None
            return True, frame
        if not self.cap:
            return False, None
        return self.cap.read()

    def _handle_video_file_read_failure(self) -> Optional[Any]:
        """Classify verified EOF separately from mid-stream decode failures."""
        verified_eof = self._video_file_read_is_eof()
        rewind_without_frame = (
            self._video_file_playback_state == "rewind_pending"
            and self._video_file_frames_in_epoch <= 0
        )
        if rewind_without_frame or verified_eof is True:
            self._video_file_ambiguous_failure_count = 0
            return self._handle_video_file_eof()

        if verified_eof is None:
            self._video_file_ambiguous_failure_count += 1
            if (
                self._video_file_ambiguous_failure_count
                >= self._UNKNOWN_LENGTH_EOF_FAILURE_THRESHOLD
            ):
                self._video_file_ambiguous_failure_count = 0
                return self._handle_video_file_eof()
        else:
            self._video_file_ambiguous_failure_count = 0

        frame = self._handle_frame_failure()
        if self._last_frame_status.get("source") != "fresh":
            self._last_frame_status["reason"] = "video_file_read_failed_before_eof"
        return frame

    def _video_file_read_is_eof(self) -> Optional[bool]:
        """Return true/false for known metadata, or None when it is unavailable."""
        if not self.cap:
            return None

        frame_count = self._capture_property_float(self.cap, cv2.CAP_PROP_FRAME_COUNT)
        if frame_count is None or frame_count <= 0:
            frame_count = (
                float(self._video_file_expected_frame_count)
                if self._video_file_expected_frame_count
                else None
            )
        position = self._capture_property_float(self.cap, cv2.CAP_PROP_POS_FRAMES)
        if frame_count is None or frame_count <= 0 or position is None:
            return None

        return position >= max(frame_count - 1.0, 0.0)

    def _handle_video_file_eof(self) -> Optional[Any]:
        """Handle a file boundary without invoking live-source recovery."""
        previous_state = self._video_file_playback_state
        self._video_file_playback_state = "eof_boundary"

        if self._video_file_eof_policy == "STOP":
            self._video_file_playback_state = "ended"
            self._video_file_terminal_reason = "video_file_eof_stopped"
            logger.info("VIDEO_FILE reached end of file; playback stopped by policy")
            return self._get_video_file_boundary_frame(self._video_file_terminal_reason)

        if self._video_file_frames_in_epoch <= 0:
            if (
                previous_state == "rewind_pending"
                and self._video_file_rewind_strategy == "seek"
                and self._reopen_video_file_capture()
            ):
                self._video_file_rewind_strategy = "reopen"
                self._video_file_playback_state = "rewind_pending"
                self._video_file_terminal_reason = None
                logger.info("VIDEO_FILE seek produced no frame; capture reopened once")
                return self._get_video_file_boundary_frame(
                    "video_file_seek_reopen_boundary"
                )

            self._video_file_playback_state = "ended"
            self._video_file_terminal_reason = "video_file_loop_empty"
            self._last_capture_error = "VIDEO_FILE produced no frames after rewind"
            logger.warning(
                "VIDEO_FILE loop produced no frames after rewind; stopping to avoid a retry loop"
            )
            return self._get_video_file_boundary_frame(self._video_file_terminal_reason)

        if not self._rewind_video_file_capture():
            self._video_file_playback_state = "ended"
            self._video_file_terminal_reason = "video_file_rewind_failed"
            self._last_capture_error = "VIDEO_FILE rewind failed"
            logger.warning("VIDEO_FILE rewind failed; playback stopped")
            return self._get_video_file_boundary_frame(self._video_file_terminal_reason)

        self._video_file_playback_epoch += 1
        self._video_file_loop_count += 1
        self._video_file_frames_in_epoch = 0
        self._video_file_playback_state = "rewind_pending"
        self._video_file_terminal_reason = None
        logger.info(
            "VIDEO_FILE loop boundary completed: epoch=%d loop_count=%d",
            self._video_file_playback_epoch,
            self._video_file_loop_count,
        )
        return self._get_video_file_boundary_frame("video_file_eof_loop_boundary")

    def _rewind_video_file_capture(self) -> bool:
        """Seek to frame zero or atomically replace the file capture."""
        active_strategy = f"{self._capture_mode} {self._last_pipeline_strategy}".lower()
        gstreamer_file_capture = "video_file_gstreamer" in active_strategy

        if self.cap and not gstreamer_file_capture:
            try:
                if bool(self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)):
                    position = self._capture_property_float(
                        self.cap,
                        cv2.CAP_PROP_POS_FRAMES,
                    )
                    if position is None or position <= 1.0:
                        self._video_file_rewind_strategy = "seek"
                        return True
                    logger.debug(
                        "VIDEO_FILE backend reported seek success but remained at frame %.3f",
                        position,
                    )
            except Exception as exc:
                logger.debug("VIDEO_FILE seek-to-zero failed: %s", exc)

        if self._reopen_video_file_capture():
            self._video_file_rewind_strategy = "reopen"
            return True
        return False

    def _reopen_video_file_capture(self) -> bool:
        """Atomically replace the file capture after proving the replacement open."""
        replacement = None
        try:
            replacement = self._create_video_file_capture(
                bool(getattr(Parameters, "USE_GSTREAMER", False))
            )
            if replacement and replacement.isOpened():
                previous = self.cap
                self.cap = replacement
                if previous and previous is not replacement:
                    previous.release()
                return True
        except Exception as exc:
            logger.debug("VIDEO_FILE controlled reopen failed: %s", exc)

        if replacement:
            replacement.release()
        return False

    def _get_video_file_boundary_frame(self, reason: str) -> Optional[Any]:
        """Return operator-continuity media while retaining boundary provenance."""
        cached_frame = self._frame_cache[-1] if self._frame_cache else None
        self._record_frame_status(
            source="cached" if cached_frame is not None else "none",
            usable_for_following=False,
            reason=reason,
        )
        return cached_frame
    
    def _reset_failure_counters(self) -> None:
        """Reset failure counters after successful frame capture."""
        if self._consecutive_failures > 0 or self._is_recovering:
            logging_manager.log_connection_status(logger, "Video", True, "Stream recovered - connection stable")
        
        self._consecutive_failures = 0
        self._last_successful_frame_time = time.time()
        self._is_recovering = False
        self._recovery_attempts = 0
        self._next_recovery_time = 0.0
        self._init_failed = False
        
        # Cache the good frame
        if self.current_raw_frame is not None:
            self._frame_cache.append(self.current_raw_frame.copy())

        self._frame_sequence += 1
        replay_source = self._is_video_file_source()
        if replay_source:
            self._video_file_playback_state = "playing"
            self._video_file_frames_in_epoch += 1
            self._video_file_terminal_reason = None
            self._video_file_rewind_strategy = None
            self._video_file_ambiguous_failure_count = 0
        self._record_frame_status(
            source="fresh",
            usable_for_following=not replay_source,
            reason="video_file_replay_frame" if replay_source else "capture_success",
        )
    
    def _handle_frame_failure(self) -> Optional[Any]:
        """
        Handle frame read failure with graceful degradation and recovery.
        
        Returns:
            Cached frame or None if recovery fails
        """
        self._consecutive_failures += 1
        current_time = time.time()
        time_since_last_frame = current_time - self._last_successful_frame_time
        
        # Log failure details
        if self._consecutive_failures == 1:
            logger.warning(f"Frame read failure detected (attempt {self._consecutive_failures})")
            self._last_capture_error = "Frame read returned no data"
        elif self._consecutive_failures % 5 == 0:
            logger.warning(f"Consecutive frame failures: {self._consecutive_failures}")
        
        # Check if we should attempt recovery
        should_recover = (
            self._consecutive_failures >= self._max_consecutive_failures or
            time_since_last_frame >= self._connection_timeout
        )
        
        if should_recover and not self._is_recovering and current_time >= self._next_recovery_time:
            return self._attempt_recovery()
        
        # Return cached frame for graceful degradation
        cached_frame = self._get_cached_frame()
        if cached_frame is not None:
            logger.debug(f"Using cached frame during connection issues")
            return cached_frame
        
        # No cached frame available
        logger.warning("No cached frame available during connection failure")
        self._record_frame_status(
            source="none",
            usable_for_following=False,
            reason="frame_read_failed_no_cache",
        )
        return None
    
    def _attempt_recovery(self) -> Optional[Any]:
        """
        Attempt to recover the video connection.
        
        Returns:
            Frame if recovery successful, cached frame otherwise
        """
        self._is_recovering = True
        self._recovery_attempts += 1
        backoff_seconds = min(
            self._recovery_backoff_max,
            self._recovery_backoff_base * (2 ** max(0, self._recovery_attempts - 1))
        )
        self._next_recovery_time = time.time() + backoff_seconds

        if self._recovery_attempts <= self._max_recovery_attempts:
            logger.warning(
                "Attempting connection recovery (%d/%d)",
                self._recovery_attempts,
                self._max_recovery_attempts
            )
        else:
            logger.warning(
                "Attempting connection recovery (%d, continuing beyond configured max=%d)",
                self._recovery_attempts,
                self._max_recovery_attempts
            )
        
        try:
            # Quick connection test first
            if self.cap and self.cap.isOpened():
                if self._prefetched_frame is not None:
                    ret, frame = self._read_next_capture_frame()
                else:
                    # Try to grab a frame to test connection.
                    ret = self.cap.grab()
                    frame = None
                    if ret:
                        ret, frame = self.cap.retrieve()
                if ret and frame is not None:
                    frame = self._apply_frame_orientation(frame)
                    logger.info("Connection recovered without reconnect")
                    self.current_raw_frame = frame
                    self.frame_history.append(frame.copy())
                    self._reset_failure_counters()
                    return frame
            
            # Full reconnection needed
            logger.info("Performing full reconnection...")
            success = self.reconnect()
            
            if success:
                # Try to get a frame immediately
                ret, frame = self._read_next_capture_frame()
                if ret and frame is not None:
                    frame = self._apply_frame_orientation(frame)
                    logger.info("Full reconnection successful")
                    self.current_raw_frame = frame
                    self.frame_history.append(frame.copy())
                    self._reset_failure_counters()
                    return frame
            
            logger.warning(f"Recovery attempt {self._recovery_attempts} failed")
            self._last_capture_error = f"Recovery attempt {self._recovery_attempts} failed"
            
        except Exception as e:
            logger.error(f"Exception during recovery: {e}")
            self._last_capture_error = f"Recovery exception: {e}"
        
        # Recovery failed, return cached frame
        self._is_recovering = False
        return self._get_cached_frame()
    
    def _get_cached_frame(self) -> Optional[Any]:
        """
        Get the most recent cached frame.
        
        Returns:
            Most recent cached frame or None
        """
        if self._frame_cache:
            cached_frame = self._frame_cache[-1]  # Get most recent
            logger.debug("Using cached frame")
            self._record_frame_status(
                source="cached",
                usable_for_following=False,
                reason="using_cached_frame",
            )
            return cached_frame
        self._record_frame_status(
            source="none",
            usable_for_following=False,
            reason="no_cached_frame",
        )
        return None

    def _record_frame_status(
        self,
        source: str,
        usable_for_following: bool,
        reason: str,
    ) -> None:
        """Record whether the frame most recently returned is command-fresh."""
        current_time = time.time()
        if source == "fresh":
            frame_age_seconds = 0.0
            status = "fresh"
        elif source == "cached":
            frame_age_seconds = current_time - self._last_successful_frame_time
            status = "cached"
        else:
            frame_age_seconds = (
                current_time - self._last_successful_frame_time
                if self._last_successful_frame_time
                else None
            )
            status = "unavailable"

        self._last_frame_status = {
            "source": source,
            "status": status,
            "usable_for_following": bool(usable_for_following),
            "reason": reason,
            "timestamp": current_time,
            "last_successful_frame_time": self._last_successful_frame_time,
            "frame_age_seconds": frame_age_seconds,
            "frame_sequence": self._frame_sequence,
            "consecutive_failures": self._consecutive_failures,
            "cached_frames_available": len(self._frame_cache),
            "connection_open": self.cap.isOpened() if self.cap else False,
            "is_recovering": self._is_recovering,
            "recovery_attempts": self._recovery_attempts,
            **self._video_file_status_fields(),
        }

    def get_frame_status(self) -> Dict[str, Any]:
        """
        Return command-freshness metadata for the most recent get_frame() call.

        `usable_for_following` is intentionally false for cached frames. Cached
        frames are useful for operator continuity, streaming, and diagnostics,
        but they are not fresh target measurements for PX4 command generation.
        """
        return dict(self._last_frame_status)

    def is_current_frame_usable_for_following(self) -> bool:
        """Return True only when the latest returned frame is a fresh capture."""
        return bool(self._last_frame_status.get("usable_for_following", False))
    
    def get_frame_fast(self) -> Optional[Any]:
        """
        Get frame with aggressive buffer clearing for ultra-low latency.
        Use this for real-time applications where latency is critical.
        
        Returns:
            Latest frame or cached frame if connection issues
        """
        if not self.cap:
            return self._get_cached_frame()
        
        try:
            # For GStreamer RTSP streams, grab is more efficient
            if Parameters.USE_GSTREAMER and Parameters.VIDEO_SOURCE_TYPE == "RTSP_STREAM":
                # GStreamer with single buffer should be current already
                return self.get_frame()
            else:
                # For other sources, clear buffer aggressively
                buffer_clear_attempts = min(Parameters.OPENCV_BUFFER_SIZE, 3)
                
                for _ in range(buffer_clear_attempts):
                    if not self.cap.grab():
                        # Grab failed, use regular get_frame for error handling
                        return self.get_frame()
                
                # Get the latest frame after clearing buffer
                ret, frame = self.cap.retrieve()
                if ret and frame is not None:
                    frame = self._apply_frame_orientation(frame)
                    self.current_raw_frame = frame
                    self.frame_history.append(frame.copy())
                    self._reset_failure_counters()
                    return frame
                else:
                    return self._handle_frame_failure()
                    
        except Exception as e:
            logger.warning(f"Exception in get_frame_fast: {e}")
            return self._handle_frame_failure()
    
    def get_last_frames(self) -> list:
        """
        Get frame history buffer.
        
        Returns:
            List of recent frames
        """
        return list(self.frame_history)
    
    def clear_frame_history(self) -> None:
        """Clear frame history buffer."""
        self.frame_history.clear()
        logger.debug("Frame history cleared")
    
    def resize_frame(self, frame: Optional[Any], width: int, height: int) -> Optional[Any]:
        """
        Resize a frame safely only when needed.

        Args:
            frame: Source frame
            width: Target width
            height: Target height

        Returns:
            Resized frame, original frame copy, or None
        """
        if frame is None:
            return None
        if frame.shape[1] == width and frame.shape[0] == height:
            return frame.copy()
        return cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)

    def update_resized_frames(
        self,
        width: int,
        height: int,
        resize_raw: bool = True,
        resize_osd: bool = True,
        raw_frame: Optional[Any] = None,
        osd_frame: Optional[Any] = None,
    ) -> None:
        """
        Resize frames for streaming.
        
        Args:
            width: Target width
            height: Target height
            resize_raw: Whether to resize/store raw frame output
            resize_osd: Whether to resize/store OSD frame output
            raw_frame: Optional override source for raw frame
            osd_frame: Optional override source for OSD frame
        """
        try:
            source_raw = self.current_raw_frame if raw_frame is None else raw_frame
            source_osd = self.current_osd_frame if osd_frame is None else osd_frame

            # Resize raw frame only when requested
            if resize_raw:
                self.current_resized_raw_frame = self.resize_frame(source_raw, width, height)
            else:
                self.current_resized_raw_frame = None

            # Resize OSD frame only when requested
            if resize_osd:
                self.current_resized_osd_frame = self.resize_frame(source_osd, width, height)
            else:
                self.current_resized_osd_frame = None
                
        except Exception as e:
            logger.error(f"Error resizing frames: {e}")
            self.current_resized_raw_frame = None
            self.current_resized_osd_frame = None
    
    def set_frame_size(self, width: int, height: int) -> bool:
        """
        Dynamically change capture resolution.
        
        Args:
            width: New width
            height: New height
            
        Returns:
            True if successful
        """
        if not self.cap:
            return False
        
        try:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            
            # Verify change
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            if actual_width == width and actual_height == height:
                self.width = width
                self.height = height
                logger.info(f"Frame size changed to {width}x{height}")
                return True
            else:
                logger.warning(f"Frame size change failed. Got {actual_width}x{actual_height}")
                return False
                
        except Exception as e:
            logger.error(f"Error changing frame size: {e}")
            return False
    
    def get_video_info(self) -> Dict[str, Any]:
        """
        Get video source information.
        
        Returns:
            Dictionary with video properties
        """
        if not self.cap:
            return {}
        
        active_backend = self._resolve_active_backend()
        return {
            "source_type": Parameters.VIDEO_SOURCE_TYPE,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "requested_fps": self._requested_fps,
            "effective_fps": self._effective_fps if self._effective_fps is not None else self.fps,
            "backend": active_backend,
            "active_backend": active_backend,
            "capture_mode": self._capture_mode,
            "last_pipeline_strategy": self._last_pipeline_strategy,
            "last_capture_error": self._last_capture_error,
            "frame_count": int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "position": int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)),
            "codec": self.cap.get(cv2.CAP_PROP_FOURCC),
            **self._video_file_status_fields(),
        }
    
    def release(self) -> None:
        """Release video capture resources."""
        with self._async_capture_lock:
            stop_event = self._async_capture_stop
            thread = self._async_capture_thread
            cap = self.cap
            stop_event.set()
            self.cap = None

        if cap:
            cap.release()
            logger.info("Video capture released")
        if thread and thread.is_alive():
            thread.join(timeout=0.5)
        with self._async_capture_lock:
            if self._async_capture_thread is thread and thread and not thread.is_alive():
                self._async_capture_thread = None
    
    def reconnect(self) -> bool:
        """
        Attempt to reconnect to video source.
        
        Returns:
            True if successful
        """
        logger.info("Attempting to reconnect to video source...")
        self.release()
        
        try:
            self.delay_frame = self.init_video_source(max_retries=3)
            logger.info("Reconnection successful")
            return True
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            return False
    
    def test_video_feed(self) -> None:
        """Display video feed for testing. Press 'q' to exit."""
        logger.info("Testing video feed. Press 'q' to exit.")
        
        frame_count = 0
        start_time = time.time()
        
        while True:
            frame = self.get_frame()
            
            if frame is None:
                logger.warning("No frame received")
                if not self.reconnect():
                    break
                continue
            
            frame_count += 1
            
            # Calculate FPS
            if frame_count % 30 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed
                cv2.putText(frame, f"FPS: {fps:.2f}", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            cv2.imshow("Video Feed Test", frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        self.release()
        cv2.destroyAllWindows()
        
        # Print statistics
        total_time = time.time() - start_time
        avg_fps = frame_count / total_time if total_time > 0 else 0
        logger.info(f"Test completed. Frames: {frame_count}, Avg FPS: {avg_fps:.2f}")
    
    def get_connection_health(self) -> dict:
        """
        Get current connection health status.
        
        Returns:
            Dictionary with connection health metrics
        """
        current_time = time.time()
        time_since_last_frame = current_time - self._last_successful_frame_time
        
        # Determine connection status
        if self._is_video_file_source() and self._video_file_playback_state == "ended":
            status = "ended"
        elif not self.cap and not self._frame_cache:
            status = "unavailable"
        elif self._consecutive_failures == 0:
            status = "healthy"
        elif self._consecutive_failures < 5:
            status = "degraded"
        elif self._is_recovering:
            status = "recovering"
        else:
            status = "failed"
        
        health_info = {
            "status": status,
            "consecutive_failures": self._consecutive_failures,
            "time_since_last_frame": time_since_last_frame,
            "is_recovering": self._is_recovering,
            "recovery_attempts": self._recovery_attempts,
            "cached_frames_available": len(self._frame_cache),
            "connection_open": self.cap.isOpened() if self.cap else False,
            "video_source_type": Parameters.VIDEO_SOURCE_TYPE,
            "use_gstreamer": Parameters.USE_GSTREAMER,
            "active_backend": self._resolve_active_backend(),
            "init_failed": self._init_failed,
            "next_recovery_in_seconds": max(0.0, self._next_recovery_time - current_time),
            "requested_fps": self._requested_fps,
            "effective_fps": self._effective_fps if self._effective_fps is not None else self.fps,
            "capture_mode": self._capture_mode,
            "last_pipeline_strategy": self._last_pipeline_strategy,
            "last_capture_error": self._last_capture_error,
            "frame_freshness": self.get_frame_status(),
            **self._video_file_status_fields(),
        }
        
        return health_info

    def is_available(self) -> bool:
        """Return True when an active capture source is open."""
        return self.cap is not None and self.cap.isOpened()
    
    def force_recovery(self) -> bool:
        """
        Force a connection recovery attempt.
        
        Returns:
            True if recovery successful
        """
        logger.info("Forcing connection recovery...")
        self._consecutive_failures = self._max_consecutive_failures
        frame = self._attempt_recovery()
        return frame is not None

    def validate_coordinate_mapping(self) -> Dict[str, Any]:
        """
        Validate that coordinate mapping will work correctly.

        Returns:
            Dictionary with coordinate mapping validation results
        """
        validation = {
            'is_valid': True,
            'video_dimensions': (self.width, self.height),
            'configured_dimensions': (Parameters.CAPTURE_WIDTH, Parameters.CAPTURE_HEIGHT),
            'stream_dimensions': (Parameters.STREAM_WIDTH, Parameters.STREAM_HEIGHT),
            'video_source': Parameters.VIDEO_SOURCE_TYPE,
            'uses_gstreamer': Parameters.USE_GSTREAMER,
            'warnings': [],
            'info': []
        }

        # Check dimension consistency
        if self.width != Parameters.CAPTURE_WIDTH or self.height != Parameters.CAPTURE_HEIGHT:
            validation['warnings'].append(
                f"Video dimensions ({self.width}x{self.height}) don't match "
                f"configured ({Parameters.CAPTURE_WIDTH}x{Parameters.CAPTURE_HEIGHT})"
            )
            if Parameters.VIDEO_SOURCE_TYPE.endswith("_CAMERA"):
                validation['info'].append(
                    "Camera negotiated a nearby supported resolution; "
                    "coordinate mapping uses detected frame dimensions."
                )
            else:
                validation['is_valid'] = False

        # Check stream vs capture dimensions
        if Parameters.CAPTURE_WIDTH != Parameters.STREAM_WIDTH or Parameters.CAPTURE_HEIGHT != Parameters.STREAM_HEIGHT:
            validation['warnings'].append(
                f"Capture dimensions ({Parameters.CAPTURE_WIDTH}x{Parameters.CAPTURE_HEIGHT}) "
                f"differ from stream dimensions ({Parameters.STREAM_WIDTH}x{Parameters.STREAM_HEIGHT})"
            )

        # Add source-specific info
        if Parameters.VIDEO_SOURCE_TYPE == "RTSP_STREAM" and Parameters.USE_GSTREAMER:
            validation['info'].append("RTSP GStreamer pipeline includes smart scaling")
        elif Parameters.VIDEO_SOURCE_TYPE == "VIDEO_FILE" and Parameters.USE_GSTREAMER:
            validation['info'].append("Video file pipeline includes scaling")
        elif Parameters.VIDEO_SOURCE_TYPE.endswith("_CAMERA"):
            validation['info'].append("Camera pipeline uses native resolution control")

        return validation

    def __del__(self):
        """Cleanup on deletion."""
        self.release()
