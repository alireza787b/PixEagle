# tests/fixtures/mock_video.py
"""
Mock video objects for testing VideoHandler and video input subsystem.

Provides mock implementations of cv2.VideoCapture and VideoHandler
for isolated unit testing without requiring actual video hardware.
"""

import numpy as np
from typing import Tuple, Optional, Dict, Any, List
from collections import deque
from unittest.mock import MagicMock
import time


class MockVideoCapture:
    """
    Mock cv2.VideoCapture for testing VideoHandler.

    Simulates video capture behavior with configurable responses.

    Attributes:
        width: Frame width in pixels
        height: Frame height in pixels
        fps: Frames per second
        is_opened: Whether capture is open
        success_rate: Probability of successful read (0.0-1.0)
    """

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fps: float = 30.0,
        is_opened: bool = True,
        success_rate: float = 1.0,
        frame_count: int = 1000
    ):
        """
        Initialize mock video capture.

        Args:
            width: Frame width in pixels
            height: Frame height in pixels
            fps: Frames per second
            is_opened: Whether capture starts open
            success_rate: Probability of successful read (0.0-1.0)
            frame_count: Total frame count (for video files)
        """
        self._width = width
        self._height = height
        self._fps = fps
        self._is_opened = is_opened
        self._success_rate = success_rate
        self._frame_count = frame_count
        self._current_frame = 0
        self._read_count = 0
        self._fail_after_n: Optional[int] = None
        self._properties: Dict[int, Any] = {}
        self._grabbed_frame: Optional[np.ndarray] = None
        self._backend_name = "MOCK"

    def isOpened(self) -> bool:
        """Check if capture is open."""
        return self._is_opened

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read frame from capture.

        Returns:
            Tuple of (success, frame) where frame is BGR numpy array
        """
        if not self._is_opened:
            return False, None

        self._read_count += 1
        self._current_frame += 1

        # Check if configured to fail after N reads
        if self._fail_after_n and self._read_count > self._fail_after_n:
            return False, None

        # Random failure based on success rate
        if np.random.random() > self._success_rate:
            return False, None

        # Generate mock frame
        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        # Add frame number watermark (for debugging)
        frame[10:20, 10:10 + self._current_frame % 100] = [255, 255, 255]

        return True, frame

    def grab(self) -> bool:
        """
        Grab frame without decoding.

        Returns:
            True if grab successful
        """
        if not self._is_opened:
            return False

        # Store grabbed frame for later retrieve
        success, frame = self.read()
        if success:
            self._grabbed_frame = frame
            self._read_count -= 1  # Don't double count
            return True
        return False

    def retrieve(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Retrieve grabbed frame.

        Returns:
            Tuple of (success, frame)
        """
        if self._grabbed_frame is not None:
            frame = self._grabbed_frame
            self._grabbed_frame = None
            return True, frame
        return False, None

    def get(self, prop_id: int) -> float:
        """
        Get capture property.

        Args:
            prop_id: OpenCV property ID

        Returns:
            Property value
        """
        import cv2

        defaults = {
            cv2.CAP_PROP_FRAME_WIDTH: float(self._width),
            cv2.CAP_PROP_FRAME_HEIGHT: float(self._height),
            cv2.CAP_PROP_FPS: self._fps,
            cv2.CAP_PROP_FRAME_COUNT: float(self._frame_count),
            cv2.CAP_PROP_BUFFERSIZE: 1.0,
            cv2.CAP_PROP_POS_FRAMES: float(self._current_frame),
            cv2.CAP_PROP_FOURCC: 0.0,
        }
        return self._properties.get(prop_id, defaults.get(prop_id, 0.0))

    def set(self, prop_id: int, value: float) -> bool:
        """
        Set capture property.

        Args:
            prop_id: OpenCV property ID
            value: Property value

        Returns:
            True if property was set
        """
        import cv2

        self._properties[prop_id] = value

        # Handle special properties
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            self._width = int(value)
        elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            self._height = int(value)
        elif prop_id == cv2.CAP_PROP_FPS:
            self._fps = value
        elif prop_id == cv2.CAP_PROP_POS_FRAMES:
            self._current_frame = int(value)

        return True

    def release(self) -> None:
        """Release capture resources."""
        self._is_opened = False

    def getBackendName(self) -> str:
        """Get backend name."""
        return self._backend_name

    # Test configuration methods

    def set_fail_after(self, n: int) -> None:
        """Configure capture to fail after N reads."""
        self._fail_after_n = n

    def set_success_rate(self, rate: float) -> None:
        """Set read success rate (0.0-1.0)."""
        self._success_rate = max(0.0, min(1.0, rate))

    def set_backend(self, name: str) -> None:
        """Set mock backend name."""
        self._backend_name = name

    def force_close(self) -> None:
        """Force capture to appear closed."""
        self._is_opened = False

    def reopen(self) -> None:
        """Reopen closed capture."""
        self._is_opened = True
        self._read_count = 0
        self._current_frame = 0


class MockGStreamerCapture(MockVideoCapture):
    """Mock VideoCapture with GStreamer backend behavior."""

    def __init__(self, pipeline: str = "", **kwargs):
        """
        Initialize mock GStreamer capture.

        Args:
            pipeline: GStreamer pipeline string
            **kwargs: Additional arguments for MockVideoCapture
        """
        super().__init__(**kwargs)
        self.pipeline = pipeline
        self._backend_name = "GSTREAMER"

    @classmethod
    def from_pipeline(cls, pipeline: str, width: int = 640, height: int = 480) -> 'MockGStreamerCapture':
        """Create capture from pipeline string."""
        return cls(pipeline=pipeline, width=width, height=height)


class MockVideoWriter:
    """Mock cv2.VideoWriter for testing GStreamer output."""

    def __init__(
        self,
        pipeline: str = "",
        fourcc: int = 0,
        fps: float = 30.0,
        size: Tuple[int, int] = (640, 480),
        is_opened: bool = True
    ):
        """
        Initialize mock video writer.

        Args:
            pipeline: Output pipeline string
            fourcc: FourCC codec code
            fps: Output FPS
            size: Frame size (width, height)
            is_opened: Whether writer starts open
        """
        self.pipeline = pipeline
        self.fourcc = fourcc
        self.fps = fps
        self.size = size
        self._is_opened = is_opened
        self.frames_written: List[np.ndarray] = []
        self.write_count = 0

    def isOpened(self) -> bool:
        """Check if writer is open."""
        return self._is_opened

    def write(self, frame: np.ndarray) -> None:
        """
        Write frame to output.

        Args:
            frame: BGR frame to write
        """
        if self._is_opened:
            self.frames_written.append(frame.copy())
            self.write_count += 1

    def release(self) -> None:
        """Release writer resources."""
        self._is_opened = False


class VideoHandlerMock:
    """
    Comprehensive mock VideoHandler for testing.

    Simulates all VideoHandler functionality including frame states,
    history, recovery, and health monitoring.
    """

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fps: float = 30.0,
        source_type: str = "VIDEO_FILE"
    ):
        """
        Initialize mock video handler.

        Args:
            width: Frame width
            height: Frame height
            fps: Frames per second
            source_type: Video source type
        """
        self.width = width
        self.height = height
        self.fps = fps
        self.source_type = source_type
        self.delay_frame = int(1000 / fps)

        # Frame states
        self.current_raw_frame: Optional[np.ndarray] = None
        self.current_osd_frame: Optional[np.ndarray] = None
        self.current_resized_raw_frame: Optional[np.ndarray] = None
        self.current_resized_osd_frame: Optional[np.ndarray] = None

        # Frame history
        self.frame_history: deque = deque(maxlen=5)

        # Connection state
        self._consecutive_failures = 0
        self._max_consecutive_failures = 10
        self._last_successful_frame_time = time.time()
        self._connection_timeout = 5.0
        self._is_recovering = False
        self._recovery_attempts = 0
        self._max_recovery_attempts = 3
        self._frame_cache: deque = deque(maxlen=5)

        # Mock capture
        self.cap = MockVideoCapture(width, height, fps)

        # Counters for testing
        self._get_frame_calls = 0
        self._reconnect_calls = 0

    def init_video_source(self, max_retries: int = 5, retry_delay: float = 1.0) -> int:
        """
        Initialize video source.

        Returns:
            Frame delay in milliseconds
        """
        return self.delay_frame

    def get_frame(self) -> Optional[np.ndarray]:
        """
        Get current frame.

        Returns:
            Frame as numpy array or None on failure
        """
        self._get_frame_calls += 1

        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                self.current_raw_frame = frame
                self.frame_history.append(frame.copy())
                self._frame_cache.append(frame.copy())
                self._reset_failure_counters()
                return frame
            else:
                return self._handle_frame_failure()
        return self._get_cached_frame()

    def get_frame_fast(self) -> Optional[np.ndarray]:
        """
        Get frame with buffer clearing for low latency.

        Returns:
            Latest frame or None
        """
        if self.cap and self.cap.isOpened():
            # Simulate buffer clearing
            self.cap.grab()
            ret, frame = self.cap.retrieve()
            if ret:
                self.current_raw_frame = frame
                return frame
        return self.get_frame()

    def get_last_frames(self) -> List[np.ndarray]:
        """Get frame history."""
        return list(self.frame_history)

    def update_resized_frames(self, width: int, height: int) -> None:
        """
        Update resized frame versions.

        Args:
            width: Target width
            height: Target height
        """
        import cv2

        if self.current_raw_frame is not None:
            self.current_resized_raw_frame = cv2.resize(
                self.current_raw_frame, (width, height), interpolation=cv2.INTER_LINEAR
            )
        if self.current_osd_frame is not None:
            self.current_resized_osd_frame = cv2.resize(
                self.current_osd_frame, (width, height), interpolation=cv2.INTER_LINEAR
            )

    def set_frame_size(self, width: int, height: int) -> bool:
        """
        Set capture frame size.

        Args:
            width: New width
            height: New height

        Returns:
            True if successful
        """
        import cv2

        if self.cap:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.width = width
            self.height = height
            return True
        return False

    def clear_frame_history(self) -> None:
        """Clear frame history buffer."""
        self.frame_history.clear()

    def _handle_frame_failure(self) -> Optional[np.ndarray]:
        """Handle frame read failure."""
        self._consecutive_failures += 1

        if self._consecutive_failures >= self._max_consecutive_failures:
            return self._attempt_recovery()

        return self._get_cached_frame()

    def _attempt_recovery(self) -> Optional[np.ndarray]:
        """Attempt connection recovery."""
        self._is_recovering = True
        self._recovery_attempts += 1

        if self._recovery_attempts <= self._max_recovery_attempts:
            success = self.reconnect()
            if success:
                self._is_recovering = False
                return self.get_frame()

        return self._get_cached_frame()

    def _reset_failure_counters(self) -> None:
        """Reset failure tracking."""
        self._consecutive_failures = 0
        self._last_successful_frame_time = time.time()
        self._is_recovering = False
        self._recovery_attempts = 0

    def _get_cached_frame(self) -> Optional[np.ndarray]:
        """Get most recent cached frame."""
        if self._frame_cache:
            return self._frame_cache[-1]
        return None

    def reconnect(self) -> bool:
        """
        Attempt to reconnect to video source.

        Returns:
            True if successful
        """
        self._reconnect_calls += 1
        self.release()

        try:
            self.cap = MockVideoCapture(self.width, self.height, self.fps)
            if self.cap.isOpened():
                self._reset_failure_counters()
                return True
            return False
        except Exception:
            return False

    def release(self) -> None:
        """Release video capture resources."""
        if self.cap:
            self.cap.release()

    def get_video_info(self) -> Dict[str, Any]:
        """
        Get video capture information.

        Returns:
            Dictionary with video properties
        """
        return {
            'width': self.width,
            'height': self.height,
            'fps': self.fps,
            'source_type': self.source_type,
            'is_opened': self.cap.isOpened() if self.cap else False,
            'frame_count': len(self.frame_history),
        }

    def get_connection_health(self) -> Dict[str, Any]:
        """
        Get connection health metrics.

        Returns:
            Dictionary with health information
        """
        current_time = time.time()
        time_since_last = current_time - self._last_successful_frame_time

        if self._is_recovering:
            status = "recovering"
        elif self._consecutive_failures >= self._max_consecutive_failures:
            status = "failed"
        elif self._consecutive_failures > 0:
            status = "degraded"
        else:
            status = "healthy"

        return {
            'status': status,
            'consecutive_failures': self._consecutive_failures,
            'time_since_last_frame': time_since_last,
            'is_recovering': self._is_recovering,
            'recovery_attempts': self._recovery_attempts,
            'cached_frames_available': len(self._frame_cache),
            'connection_open': self.cap.isOpened() if self.cap else False,
            'video_source_type': self.source_type,
        }

    def force_recovery(self) -> bool:
        """Force immediate recovery attempt."""
        return self.reconnect()

    def validate_coordinate_mapping(self) -> Dict[str, Any]:
        """Validate coordinate mapping for dashboard."""
        return {
            'capture_width': self.width,
            'capture_height': self.height,
            'valid': True,
        }


# Factory functions

def create_mock_video_capture(
    width: int = 640,
    height: int = 480,
    fps: float = 30.0,
    success_rate: float = 1.0,
    fail_after: Optional[int] = None
) -> MockVideoCapture:
    """
    Create configured mock video capture.

    Args:
        width: Frame width
        height: Frame height
        fps: Frames per second
        success_rate: Read success probability
        fail_after: Number of reads before failure

    Returns:
        Configured MockVideoCapture instance
    """
    cap = MockVideoCapture(width, height, fps, success_rate=success_rate)
    if fail_after:
        cap.set_fail_after(fail_after)
    return cap


def create_mock_video_handler(
    width: int = 640,
    height: int = 480,
    source_type: str = "VIDEO_FILE"
) -> VideoHandlerMock:
    """
    Create configured mock video handler.

    Args:
        width: Frame width
        height: Frame height
        source_type: Video source type

    Returns:
        Configured VideoHandlerMock instance
    """
    return VideoHandlerMock(width, height, source_type=source_type)


def create_test_frame(
    width: int = 640,
    height: int = 480,
    pattern: str = "random",
    dtype: np.dtype = np.uint8
) -> np.ndarray:
    """
    Create a test frame with specified pattern.

    Args:
        width: Frame width
        height: Frame height
        pattern: Pattern type (random, gradient, checkerboard, solid, noise)
        dtype: Numpy dtype for frame

    Returns:
        Test frame as numpy array
    """
    if pattern == "random":
        return np.random.randint(0, 255, (height, width, 3), dtype=dtype)

    elif pattern == "gradient":
        gradient = np.linspace(0, 255, width, dtype=dtype)
        frame = np.tile(gradient, (height, 1))
        return np.stack([frame, frame, frame], axis=2).astype(dtype)

    elif pattern == "checkerboard":
        frame = np.zeros((height, width, 3), dtype=dtype)
        block_size = 50
        for i in range(height):
            for j in range(width):
                if ((i // block_size) + (j // block_size)) % 2:
                    frame[i, j] = [255, 255, 255]
        return frame

    elif pattern == "solid":
        return np.full((height, width, 3), 128, dtype=dtype)

    elif pattern == "noise":
        return np.random.normal(128, 30, (height, width, 3)).clip(0, 255).astype(dtype)

    else:
        return np.zeros((height, width, 3), dtype=dtype)


def create_rtsp_video_handler() -> VideoHandlerMock:
    """Create VideoHandler configured for RTSP source."""
    handler = VideoHandlerMock(source_type="RTSP_STREAM")
    handler.cap._backend_name = "GSTREAMER"
    return handler


def create_usb_video_handler(camera_index: int = 0) -> VideoHandlerMock:
    """Create VideoHandler configured for USB camera."""
    handler = VideoHandlerMock(source_type="USB_CAMERA")
    handler.camera_index = camera_index
    return handler


def create_csi_video_handler(platform: str = "jetson") -> VideoHandlerMock:
    """
    Create VideoHandler configured for CSI camera.

    Args:
        platform: 'jetson' or 'rpi'
    """
    handler = VideoHandlerMock(source_type="CSI_CAMERA")
    handler.platform = platform
    handler.cap._backend_name = "GSTREAMER"
    return handler


def create_failing_video_handler(
    fail_after: int = 5,
    recovery_success: bool = True
) -> VideoHandlerMock:
    """
    Create VideoHandler that simulates connection failures.

    Args:
        fail_after: Number of reads before failure
        recovery_success: Whether recovery should succeed
    """
    handler = VideoHandlerMock()
    handler.cap.set_fail_after(fail_after)
    if not recovery_success:
        handler._max_recovery_attempts = 0
    return handler
