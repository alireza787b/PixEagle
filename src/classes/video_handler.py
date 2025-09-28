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
import platform
from collections import deque
from typing import Optional, Dict, Any
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
    
    def __init__(self):
        """Initialize video handler with configured source."""
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame_history = deque(maxlen=Parameters.STORE_LAST_FRAMES)
        
        # Video properties
        self.width: Optional[int] = None
        self.height: Optional[int] = None
        self.fps: Optional[float] = None
        self.delay_frame: int = 33  # Default 30 FPS
        
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
        
        # Platform detection for optimization
        self.platform = platform.system()
        self.is_arm = platform.machine().startswith('arm') or platform.machine().startswith('aarch')
        
        # Initialize video source
        try:
            self.delay_frame = self.init_video_source()
            logger.info(f"Video handler initialized: {self.width}x{self.height}@{self.fps}fps")
        except Exception as e:
            logger.error(f"Failed to initialize video handler: {e}")
            raise
    
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
        for attempt in range(max_retries):
            logger.debug(f"Attempt {attempt + 1}/{max_retries} to open video source")
            
            try:
                self.cap = self._create_capture_object()
                
                if self.cap and self.cap.isOpened():
                    # Extract video properties
                    self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    self.fps = self.cap.get(cv2.CAP_PROP_FPS) or Parameters.DEFAULT_FPS
                    
                    # Validate dimensions for coordinate mapping consistency
                    if self.width <= 0 or self.height <= 0:
                        logger.warning("Invalid dimensions detected, using configured defaults")
                        self.width = Parameters.CAPTURE_WIDTH
                        self.height = Parameters.CAPTURE_HEIGHT

                    # Coordinate mapping validation
                    expected_width = Parameters.CAPTURE_WIDTH
                    expected_height = Parameters.CAPTURE_HEIGHT

                    if self.width != expected_width or self.height != expected_height:
                        logger.warning(
                            f"Video dimensions ({self.width}x{self.height}) differ from "
                            f"configured ({expected_width}x{expected_height}). "
                            f"This may indicate scaling pipeline issues."
                        )

                        # For coordinate mapping consistency, trust the configured dimensions
                        # if the difference is due to pipeline scaling issues
                        if Parameters.VIDEO_SOURCE_TYPE == "RTSP_STREAM" and Parameters.USE_GSTREAMER:
                            logger.info("RTSP GStreamer: Using configured dimensions for coordinate consistency")
                            self.width = expected_width
                            self.height = expected_height
                    
                    delay_frame = max(int(1000 / self.fps), 1)
                    
                    logger.info(f"Video source opened successfully: {Parameters.VIDEO_SOURCE_TYPE}")
                    logger.debug(f"Properties - Width: {self.width}, Height: {self.height}, FPS: {self.fps}")
                    
                    return delay_frame
                else:
                    logger.warning(f"Failed to open video source on attempt {attempt + 1}")
                    
            except Exception as e:
                logger.error(f"Exception during video source initialization: {e}")
            
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
        
        raise ValueError(f"Could not open video source after {max_retries} attempts")
    
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
        
        logger.debug(f"Creating capture for {source_type}, GStreamer: {use_gstreamer}")
        
        # Source type to handler mapping
        handlers = {
            "VIDEO_FILE": self._create_video_file_capture,
            "USB_CAMERA": self._create_usb_camera_capture,
            "RTSP_STREAM": self._create_rtsp_capture,
            "UDP_STREAM": self._create_udp_capture,
            "HTTP_STREAM": self._create_http_capture,
            "CSI_CAMERA": self._create_csi_capture,
            "CUSTOM_GSTREAMER": self._create_custom_gstreamer_capture
        }
        
        if source_type not in handlers:
            raise ValueError(f"Unsupported video source type: {source_type}")
        
        return handlers[source_type](use_gstreamer)
    
    def _create_video_file_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create capture for video file."""
        if use_gstreamer:
            pipeline = self._build_gstreamer_file_pipeline()
            return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            return cv2.VideoCapture(Parameters.VIDEO_FILE_PATH)
    
    def _create_usb_camera_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create optimized capture for USB camera."""
        if use_gstreamer:
            pipeline = self._build_gstreamer_usb_pipeline()
            logger.debug(f"USB GStreamer pipeline: {pipeline}")
            return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            # Use appropriate backend based on platform
            if self.platform == "Linux" and Parameters.USE_V4L2_BACKEND:
                cap = cv2.VideoCapture(Parameters.CAMERA_INDEX, cv2.CAP_V4L2)
            elif self.platform == "Windows":
                cap = cv2.VideoCapture(Parameters.CAMERA_INDEX, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(Parameters.CAMERA_INDEX)
            
            # Apply OpenCV optimizations
            self._optimize_opencv_capture(cap)
            return cap
    
    def _create_rtsp_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create optimized capture for RTSP stream with auto-detection and fallback."""
        if use_gstreamer:
            return self._create_gstreamer_rtsp_with_fallback()
        else:
            return self._create_opencv_rtsp_optimized()
    
    def _create_gstreamer_rtsp_with_fallback(self) -> cv2.VideoCapture:
        """Create GStreamer RTSP capture with automatic fallback pipelines."""
        # Try primary optimized pipeline first
        pipeline = self._build_gstreamer_rtsp_pipeline()
        logger.info("Attempting primary RTSP GStreamer pipeline...")
        
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            logging_manager.log_connection_status(logger, "Video", True, "Primary GStreamer RTSP pipeline")
            self._log_rtsp_stream_info(cap)
            return cap
        
        cap.release()
        logger.warning("Primary pipeline failed, trying fallback pipelines...")
        
        # Try fallback pipelines
        fallback_pipelines = self._build_fallback_rtsp_pipelines()
        
        for i, fallback_pipeline in enumerate(fallback_pipelines, 1):
            logger.info(f"Trying fallback pipeline {i}/{len(fallback_pipelines)}...")
            logger.debug(f"Fallback pipeline: {fallback_pipeline}")
            
            cap = cv2.VideoCapture(fallback_pipeline, cv2.CAP_GSTREAMER)
            if cap.isOpened():
                logging_manager.log_connection_status(logger, "Video", True, f"Fallback pipeline {i}")
                self._log_rtsp_stream_info(cap)
                return cap
            
            cap.release()
            logger.warning(f"Fallback pipeline {i} failed")
        
        # If all GStreamer pipelines fail, try OpenCV as last resort
        logger.warning("All GStreamer pipelines failed, falling back to OpenCV...")
        return self._create_opencv_rtsp_optimized()
    
    def _create_opencv_rtsp_optimized(self) -> cv2.VideoCapture:
        """Create OpenCV RTSP capture with optimizations."""
        rtsp_url = Parameters.RTSP_URL
        logger.info("Attempting OpenCV RTSP capture...")
        
        # Try FFMPEG backend first (usually best for RTSP)
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        
        if not cap.isOpened():
            logger.warning("FFMPEG backend failed, trying default backend...")
            cap = cv2.VideoCapture(rtsp_url)
        
        if cap.isOpened():
            # Real-time optimizations
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)        # Minimum buffering
            cap.set(cv2.CAP_PROP_FPS, 30)              # Request 30 FPS
            
            logging_manager.log_connection_status(logger, "Video", True, "OpenCV RTSP")
            self._log_rtsp_stream_info(cap)
        else:
            logging_manager.log_connection_status(logger, "Video", False, "All RTSP methods failed")
        
        return cap
    
    def _create_udp_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create capture for UDP stream."""
        if use_gstreamer:
            pipeline = self._build_gstreamer_udp_pipeline()
            return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            return cv2.VideoCapture(Parameters.UDP_URL, cv2.CAP_FFMPEG)
    
    def _create_http_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create capture for HTTP stream."""
        if use_gstreamer:
            pipeline = self._build_gstreamer_http_pipeline()
            return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            return cv2.VideoCapture(Parameters.HTTP_URL)
    
    def _create_csi_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create capture for CSI camera (always uses GStreamer)."""
        pipeline = self._build_gstreamer_csi_pipeline()
        logger.debug(f"CSI GStreamer pipeline: {pipeline}")
        return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    
    def _create_custom_gstreamer_capture(self, use_gstreamer: bool) -> cv2.VideoCapture:
        """Create capture from custom GStreamer pipeline."""
        pipeline = Parameters.CUSTOM_PIPELINE
        if not pipeline:
            raise ValueError("CUSTOM_PIPELINE is empty")
        logger.debug(f"Custom GStreamer pipeline: {pipeline}")
        return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    
    def _build_gstreamer_file_pipeline(self) -> str:
        """Build GStreamer pipeline for video file."""
        return (
            f"filesrc location={Parameters.VIDEO_FILE_PATH} ! "
            f"decodebin ! videoconvert ! video/x-raw,format=BGR ! "
            f"videoscale ! video/x-raw,width={Parameters.CAPTURE_WIDTH},"
            f"height={Parameters.CAPTURE_HEIGHT} ! appsink drop=true sync=false"
        )
    
    def _build_gstreamer_usb_pipeline(self) -> str:
        """Build optimized GStreamer pipeline for USB camera."""
        # Get pipeline template based on pixel format
        pixel_format = Parameters.PIXEL_FORMAT
        
        if pixel_format == "MJPG":
            template = Parameters.USB_MJPEG
        else:
            template = Parameters.USB_YUYV
        
        # Format pipeline with parameters
        pipeline = template.format(
            device_id=Parameters.CAMERA_INDEX,
            width=Parameters.CAPTURE_WIDTH,
            height=Parameters.CAPTURE_HEIGHT,
            fps=Parameters.CAPTURE_FPS
        )
        
        return pipeline
    
    def _build_gstreamer_rtsp_pipeline(self) -> str:
        """
        Build ultra-low latency GStreamer pipeline for RTSP stream with smart scaling.

        Maintains coordinate consistency by scaling to configured dimensions while
        preserving real-time performance optimizations.
        """
        rtsp_url = Parameters.RTSP_URL
        target_width = Parameters.CAPTURE_WIDTH
        target_height = Parameters.CAPTURE_HEIGHT

        # Ultra-low latency pipeline with smart scaling for coordinate consistency
        pipeline = (
            f"rtspsrc location={rtsp_url} "
            f"protocols=tcp "                    # Force TCP for reliability
            f"latency=0 "                       # Zero latency buffering
            f"buffer-mode=0 "                   # No jitter buffer
            f"drop-on-latency=true "            # Drop frames immediately if late
            f"do-rtcp=false "                   # Disable RTCP overhead
            f"do-retransmission=false "         # No retransmission delays
            f"ntp-sync=false "                  # Disable NTP sync overhead
            f"! rtpjitterbuffer "               # Minimal jitter buffer
            f"latency=0 "                       # Zero jitter buffer
            f"drop-on-latency=true "
            f"! rtph264depay "                  # RTP H.264 depayloader
            f"! h264parse "                     # Parse H.264 stream
            f"! avdec_h264 "                    # Hardware decoder
            f"max-threads=1 "                   # Single thread for lowest latency
            f"skip-frame=1 "                    # Skip non-reference frames
            f"! videoconvert "                  # Fast color conversion
            f"n-threads=1 "                     # Single thread conversion
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

        fallback_pipelines = [
            # Fallback 1: Auto-detect with both TCP/UDP + smart scaling
            (
                f"rtspsrc location={rtsp_url} "
                f"latency=0 drop-on-latency=true do-rtcp=false "
                f"! queue max-size-buffers=1 leaky=downstream "
                f"! decodebin ! videoconvert ! video/x-raw,format=BGR "
                f"! videoscale method=0 "          # Fastest scaling method
                f"! video/x-raw,width={target_width},height={target_height} "
                f"! appsink drop=true max-buffers=1 sync=false"
            ),

            # Fallback 2: Force UDP + smart scaling (some cameras prefer this)
            (
                f"rtspsrc location={rtsp_url} "
                f"protocols=udp latency=0 drop-on-latency=true "
                f"! queue max-size-buffers=1 leaky=downstream "
                f"! decodebin ! videoconvert ! video/x-raw,format=BGR "
                f"! videoscale method=0 "          # Fastest scaling method
                f"! video/x-raw,width={target_width},height={target_height} "
                f"! appsink drop=true max-buffers=1 sync=false"
            ),

            # Fallback 3: Simple pipeline with scaling (maximum compatibility)
            (
                f"rtspsrc location={rtsp_url} latency=0 "
                f"! decodebin ! videoconvert ! video/x-raw,format=BGR "
                f"! videoscale method=0 "          # Fastest scaling method
                f"! video/x-raw,width={target_width},height={target_height} "
                f"! appsink sync=false"
            ),

            # Fallback 4: No scaling (emergency fallback - may have coord issues)
            (
                f"rtspsrc location={rtsp_url} latency=0 "
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
            fps=Parameters.CAPTURE_FPS,
            flip_method=Parameters.FLIP_METHOD
        )
    
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
            cap.set(cv2.CAP_PROP_FPS, Parameters.CAPTURE_FPS)
            
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
    
    def get_frame(self) -> Optional[Any]:
        """
        Read and return the next frame with robust error handling and auto-recovery.
        
        Returns:
            Frame as numpy array, cached frame if available, or None
        """
        if not self.cap:
            # Log error only once, then use debug level to avoid spam
            if not hasattr(self, '_capture_error_logged'):
                logger.error("Video capture not initialized")
                self._capture_error_logged = True
            else:
                logger.debug("Video capture not initialized (repeated)")
            return self._get_cached_frame()
        
        try:
            ret, frame = self.cap.read()
            
            if ret and frame is not None:
                # Successful frame capture
                self.current_raw_frame = frame
                self.frame_history.append(frame)
                self._reset_failure_counters()
                return frame
            else:
                # Frame read failed - handle gracefully
                return self._handle_frame_failure()
                
        except Exception as e:
            logger.warning(f"Exception during frame capture: {e}")
            return self._handle_frame_failure()
    
    def _reset_failure_counters(self) -> None:
        """Reset failure counters after successful frame capture."""
        if self._consecutive_failures > 0 or self._is_recovering:
            logging_manager.log_connection_status(logger, "Video", True, "Stream recovered - connection stable")
        
        self._consecutive_failures = 0
        self._last_successful_frame_time = time.time()
        self._is_recovering = False
        self._recovery_attempts = 0
        
        # Cache the good frame
        if self.current_raw_frame is not None:
            self._frame_cache.append(self.current_raw_frame.copy())
    
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
        elif self._consecutive_failures % 5 == 0:
            logger.warning(f"Consecutive frame failures: {self._consecutive_failures}")
        
        # Check if we should attempt recovery
        should_recover = (
            self._consecutive_failures >= self._max_consecutive_failures or
            time_since_last_frame >= self._connection_timeout
        )
        
        if should_recover and not self._is_recovering:
            return self._attempt_recovery()
        
        # Return cached frame for graceful degradation
        cached_frame = self._get_cached_frame()
        if cached_frame is not None:
            logger.debug(f"Using cached frame during connection issues")
            return cached_frame
        
        # No cached frame available
        logger.warning("No cached frame available during connection failure")
        return None
    
    def _attempt_recovery(self) -> Optional[Any]:
        """
        Attempt to recover the video connection.
        
        Returns:
            Frame if recovery successful, cached frame otherwise
        """
        if self._recovery_attempts >= self._max_recovery_attempts:
            logger.error(f"Max recovery attempts ({self._max_recovery_attempts}) reached")
            return self._get_cached_frame()
        
        self._is_recovering = True
        self._recovery_attempts += 1
        
        logger.warning(f"Attempting connection recovery ({self._recovery_attempts}/{self._max_recovery_attempts})")
        
        try:
            # Quick connection test first
            if self.cap and self.cap.isOpened():
                # Try to grab a frame to test connection
                ret = self.cap.grab()
                if ret:
                    ret, frame = self.cap.retrieve()
                    if ret and frame is not None:
                        logger.info("Connection recovered without reconnect")
                        self.current_raw_frame = frame
                        self.frame_history.append(frame)
                        self._reset_failure_counters()
                        return frame
            
            # Full reconnection needed
            logger.info("Performing full reconnection...")
            success = self.reconnect()
            
            if success:
                # Try to get a frame immediately
                ret, frame = self.cap.read()
                if ret and frame is not None:
                    logger.info("Full reconnection successful")
                    self.current_raw_frame = frame
                    self.frame_history.append(frame)
                    self._reset_failure_counters()
                    return frame
            
            logger.warning(f"Recovery attempt {self._recovery_attempts} failed")
            
        except Exception as e:
            logger.error(f"Exception during recovery: {e}")
        
        # Recovery failed, return cached frame
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
            return cached_frame
        return None
    
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
                    self.current_raw_frame = frame
                    self.frame_history.append(frame)
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
    
    def update_resized_frames(self, width: int, height: int) -> None:
        """
        Resize frames for streaming.
        
        Args:
            width: Target width
            height: Target height
        """
        try:
            # Resize raw frame
            if self.current_raw_frame is not None:
                self.current_resized_raw_frame = cv2.resize(
                    self.current_raw_frame, (width, height), 
                    interpolation=cv2.INTER_LINEAR
                )
            else:
                self.current_resized_raw_frame = None
            
            # Resize OSD frame
            if self.current_osd_frame is not None:
                self.current_resized_osd_frame = cv2.resize(
                    self.current_osd_frame, (width, height),
                    interpolation=cv2.INTER_LINEAR
                )
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
        
        return {
            "source_type": Parameters.VIDEO_SOURCE_TYPE,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "backend": "GStreamer" if Parameters.USE_GSTREAMER else "OpenCV",
            "frame_count": int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "position": int(self.cap.get(cv2.CAP_PROP_POS_FRAMES)),
            "codec": self.cap.get(cv2.CAP_PROP_FOURCC)
        }
    
    def release(self) -> None:
        """Release video capture resources."""
        if self.cap:
            self.cap.release()
            self.cap = None
            logger.info("Video capture released")
    
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
        if self._consecutive_failures == 0:
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
            "use_gstreamer": Parameters.USE_GSTREAMER
        }
        
        return health_info
    
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