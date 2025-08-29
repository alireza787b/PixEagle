"""
Video Handler Module
Handles video input from various sources with optimized capture pipelines.
Supports OpenCV and GStreamer backends for maximum performance on embedded systems.
"""

import cv2
import time
import logging
import platform
from collections import deque
from typing import Optional, Dict, Any
from classes.parameters import Parameters

logging.basicConfig(level=logging.DEBUG)
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
                    
                    # Validate dimensions
                    if self.width <= 0 or self.height <= 0:
                        logger.warning("Invalid dimensions detected, using defaults")
                        self.width = Parameters.CAPTURE_WIDTH
                        self.height = Parameters.CAPTURE_HEIGHT
                    
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
        """Create capture for RTSP stream."""
        if use_gstreamer:
            pipeline = self._build_gstreamer_rtsp_pipeline()
            return cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            cap = cv2.VideoCapture(Parameters.RTSP_URL)
            # Optimize RTSP buffering
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
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
        """Build GStreamer pipeline for RTSP stream."""
        template = Parameters.RTSP
        return template.format(
            url=Parameters.RTSP_URL,
            latency=Parameters.RTSP_LATENCY,
            width=Parameters.CAPTURE_WIDTH,
            height=Parameters.CAPTURE_HEIGHT
        )
    
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
    
    def get_frame(self) -> Optional[Any]:
        """
        Read and return the next frame.
        
        Returns:
            Frame as numpy array or None if capture fails
        """
        if not self.cap:
            logger.error("Video capture not initialized")
            return None
        
        try:
            ret, frame = self.cap.read()
            
            if ret and frame is not None:
                self.current_raw_frame = frame
                self.frame_history.append(frame)
                return frame
            else:
                logger.debug("Failed to read frame")
                return None
                
        except Exception as e:
            logger.error(f"Exception during frame capture: {e}")
            return None
    
    def get_frame_fast(self) -> Optional[Any]:
        """
        Get frame with buffer clearing for lowest latency.
        Use this for real-time applications.
        
        Returns:
            Latest frame or None
        """
        if not self.cap:
            return None
        
        # Clear buffer by grabbing frames without decoding
        for _ in range(Parameters.OPENCV_BUFFER_SIZE - 1):
            self.cap.grab()
        
        # Get the latest frame
        return self.get_frame()
    
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
    
    def __del__(self):
        """Cleanup on deletion."""
        self.release()