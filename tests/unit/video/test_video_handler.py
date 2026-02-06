# tests/unit/video/test_video_handler.py
"""
Unit tests for VideoHandler class.

Tests initialization, frame capture, properties, and state management.
"""

import pytest
import sys
import os
import numpy as np
import cv2
from unittest.mock import MagicMock, patch, PropertyMock
from collections import deque

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'src'))

from tests.fixtures.mock_video import (
    MockVideoCapture, VideoHandlerMock, create_test_frame,
    create_mock_video_capture
)
from classes.video_handler import VideoHandler


@pytest.fixture
def mock_parameters():
    """Fixture for mocked Parameters."""
    with patch('classes.video_handler.Parameters') as mock_params:
        mock_params.VIDEO_SOURCE_TYPE = "VIDEO_FILE"
        mock_params.VIDEO_FILE_PATH = "test.mp4"
        mock_params.CAPTURE_WIDTH = 640
        mock_params.CAPTURE_HEIGHT = 480
        mock_params.CAPTURE_FPS = 30
        mock_params.DEFAULT_FPS = 30
        mock_params.USE_GSTREAMER = False
        mock_params.STORE_LAST_FRAMES = 5
        mock_params.OPENCV_BUFFER_SIZE = 1
        mock_params.USB_YUYV = (
            "v4l2src device=/dev/video{device_id} ! "
            "video/x-raw,format=YUY2,width={width},height={height},framerate={fps}/1 ! "
            "videoconvert ! video/x-raw,format=BGR ! appsink drop=true max-buffers=1 sync=false"
        )
        mock_params.USB_MJPEG = (
            "v4l2src device=/dev/video{device_id} ! "
            "image/jpeg,width={width},height={height},framerate={fps}/1 ! "
            "jpegdec ! videoconvert ! video/x-raw,format=BGR ! appsink drop=true max-buffers=1 sync=false"
        )
        mock_params.PIXEL_FORMAT = "YUYV"
        mock_params.CAMERA_INDEX = 0
        mock_params.DEVICE_PATH = "/dev/video0"
        mock_params.FRAME_ROTATION_DEG = 0
        mock_params.FRAME_FLIP_MODE = "none"
        mock_params.SENSOR_ID = 0
        mock_params.RTSP_URL = "rtsp://127.0.0.1:8554/test"
        mock_params.RTSP_PROTOCOL = "tcp"
        mock_params.RTSP_LATENCY = 200
        mock_params.UDP_URL = "udp://127.0.0.1:5600"
        mock_params.HTTP_URL = "http://127.0.0.1:8080/video"
        mock_params.CUSTOM_PIPELINE = "videotestsrc ! videoconvert ! appsink"
        mock_params.USE_V4L2_BACKEND = False
        mock_params.OPENCV_FOURCC = ""
        mock_params.RTSP_MAX_CONSECUTIVE_FAILURES = 10
        mock_params.RTSP_CONNECTION_TIMEOUT = 5.0
        mock_params.RTSP_MAX_RECOVERY_ATTEMPTS = 3
        mock_params.RTSP_FRAME_CACHE_SIZE = 5
        yield mock_params


@pytest.fixture
def mock_cv2_capture():
    """Fixture for mocked cv2.VideoCapture."""
    with patch('classes.video_handler.cv2.VideoCapture') as mock_cv2:
        cap = MockVideoCapture(640, 480, 30.0)
        mock_cv2.return_value = cap
        yield mock_cv2, cap


@pytest.mark.unit
class TestVideoHandlerInitialization:
    """Tests for VideoHandler initialization."""

    def test_mock_video_handler_initialization(self):
        """VideoHandlerMock should initialize with default values."""
        handler = VideoHandlerMock()

        assert handler.width == 640
        assert handler.height == 480
        assert handler.fps == 30.0

    def test_mock_video_handler_custom_dimensions(self):
        """VideoHandlerMock should accept custom dimensions."""
        handler = VideoHandlerMock(width=1280, height=720)

        assert handler.width == 1280
        assert handler.height == 720

    def test_mock_video_handler_source_type(self):
        """VideoHandlerMock should store source type."""
        handler = VideoHandlerMock(source_type="RTSP_STREAM")

        assert handler.source_type == "RTSP_STREAM"

    def test_frame_states_initially_none(self):
        """All frame states should be None initially."""
        handler = VideoHandlerMock()

        assert handler.current_raw_frame is None
        assert handler.current_osd_frame is None
        assert handler.current_resized_raw_frame is None
        assert handler.current_resized_osd_frame is None

    def test_frame_history_initialized_empty(self):
        """Frame history should be empty deque initially."""
        handler = VideoHandlerMock()

        assert isinstance(handler.frame_history, deque)
        assert len(handler.frame_history) == 0

    def test_failure_counters_initialized_zero(self):
        """Failure counters should be zero initially."""
        handler = VideoHandlerMock()

        assert handler._consecutive_failures == 0
        assert handler._recovery_attempts == 0
        assert handler._is_recovering == False

    def test_capture_object_initialized(self):
        """Capture object should be initialized."""
        handler = VideoHandlerMock()

        assert handler.cap is not None
        assert handler.cap.isOpened() == True

    def test_delay_frame_calculated_from_fps(self):
        """delay_frame should be calculated from fps."""
        handler = VideoHandlerMock()

        expected_delay = int(1000 / 30.0)  # ~33ms
        assert handler.delay_frame == expected_delay

    def test_video_handler_starts_in_degraded_mode_when_init_fails(self):
        """VideoHandler should not raise when the source cannot be opened at startup."""
        with patch.object(VideoHandler, 'init_video_source', side_effect=ValueError("source unavailable")):
            handler = VideoHandler()

        assert handler.cap is None
        assert handler.width is not None
        assert handler.height is not None
        assert handler.get_connection_health()["status"] == "unavailable"


@pytest.mark.unit
class TestGetFrame:
    """Tests for get_frame method."""

    def test_get_frame_returns_numpy_array(self):
        """get_frame should return numpy array on success."""
        handler = VideoHandlerMock()

        frame = handler.get_frame()

        assert isinstance(frame, np.ndarray)
        assert frame.shape == (480, 640, 3)

    def test_get_frame_updates_current_raw_frame(self):
        """get_frame should update current_raw_frame."""
        handler = VideoHandlerMock()

        frame = handler.get_frame()

        assert handler.current_raw_frame is not None
        assert np.array_equal(frame, handler.current_raw_frame)

    def test_get_frame_appends_to_history(self):
        """Successful frame read should append to history."""
        handler = VideoHandlerMock()

        frame = handler.get_frame()

        assert len(handler.frame_history) == 1

    def test_get_frame_multiple_calls_build_history(self):
        """Multiple get_frame calls should build history."""
        handler = VideoHandlerMock()

        for _ in range(3):
            handler.get_frame()

        assert len(handler.frame_history) == 3

    def test_get_frame_history_limited_by_maxlen(self):
        """Frame history should respect maxlen."""
        handler = VideoHandlerMock()
        handler.frame_history = deque(maxlen=3)

        for _ in range(5):
            handler.get_frame()

        assert len(handler.frame_history) == 3

    def test_get_frame_increments_call_counter(self):
        """get_frame should increment call counter."""
        handler = VideoHandlerMock()

        handler.get_frame()
        handler.get_frame()

        assert handler._get_frame_calls == 2

    def test_get_frame_resets_failure_counters_on_success(self):
        """Successful frame should reset failure counters."""
        handler = VideoHandlerMock()
        handler._consecutive_failures = 5
        handler._is_recovering = True

        handler.get_frame()

        assert handler._consecutive_failures == 0
        assert handler._is_recovering == False


@pytest.mark.unit
class TestFrameOrientation:
    """Tests for universal frame orientation in VideoHandler."""

    def _build_cap(self, frame: np.ndarray) -> MagicMock:
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, frame.copy())

        def _get(prop_id):
            if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
                return float(frame.shape[1])
            if prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
                return float(frame.shape[0])
            if prop_id == cv2.CAP_PROP_FPS:
                return 30.0
            return 0.0

        cap.get.side_effect = _get
        return cap

    def test_get_frame_applies_rotation(self):
        frame = np.array(
            [
                [[1, 0, 0], [2, 0, 0]],
                [[3, 0, 0], [4, 0, 0]],
            ],
            dtype=np.uint8
        )
        cap = self._build_cap(frame)

        with patch('classes.video_handler.Parameters') as params:
            params.STORE_LAST_FRAMES = 5
            params.FRAME_ROTATION_DEG = 180
            params.FRAME_FLIP_MODE = "none"
            params.RTSP_MAX_CONSECUTIVE_FAILURES = 10
            params.RTSP_CONNECTION_TIMEOUT = 5.0
            params.RTSP_MAX_RECOVERY_ATTEMPTS = 3
            params.RTSP_FRAME_CACHE_SIZE = 5
            params.RTSP_RECOVERY_BACKOFF_BASE = 1.0
            params.RTSP_RECOVERY_BACKOFF_MAX = 10.0
            params.CAPTURE_WIDTH = frame.shape[1]
            params.CAPTURE_HEIGHT = frame.shape[0]
            params.CAPTURE_FPS = 30
            params.DEFAULT_FPS = 30
            params.VIDEO_SOURCE_TYPE = "USB_CAMERA"
            params.USE_GSTREAMER = False
            params.USE_V4L2_BACKEND = False
            params.CAMERA_INDEX = 0
            params.OPENCV_BUFFER_SIZE = 1
            params.OPENCV_FOURCC = ""

            with patch.object(VideoHandler, "_create_capture_object", return_value=cap):
                handler = VideoHandler()

        out = handler.get_frame()
        expected = cv2.rotate(frame, cv2.ROTATE_180)
        assert np.array_equal(out, expected)

    def test_get_frame_applies_flip(self):
        frame = np.array(
            [
                [[10, 0, 0], [20, 0, 0]],
                [[30, 0, 0], [40, 0, 0]],
            ],
            dtype=np.uint8
        )
        cap = self._build_cap(frame)

        with patch('classes.video_handler.Parameters') as params:
            params.STORE_LAST_FRAMES = 5
            params.FRAME_ROTATION_DEG = 0
            params.FRAME_FLIP_MODE = "vertical"
            params.RTSP_MAX_CONSECUTIVE_FAILURES = 10
            params.RTSP_CONNECTION_TIMEOUT = 5.0
            params.RTSP_MAX_RECOVERY_ATTEMPTS = 3
            params.RTSP_FRAME_CACHE_SIZE = 5
            params.RTSP_RECOVERY_BACKOFF_BASE = 1.0
            params.RTSP_RECOVERY_BACKOFF_MAX = 10.0
            params.CAPTURE_WIDTH = frame.shape[1]
            params.CAPTURE_HEIGHT = frame.shape[0]
            params.CAPTURE_FPS = 30
            params.DEFAULT_FPS = 30
            params.VIDEO_SOURCE_TYPE = "USB_CAMERA"
            params.USE_GSTREAMER = False
            params.USE_V4L2_BACKEND = False
            params.CAMERA_INDEX = 0
            params.OPENCV_BUFFER_SIZE = 1
            params.OPENCV_FOURCC = ""

            with patch.object(VideoHandler, "_create_capture_object", return_value=cap):
                handler = VideoHandler()

        out = handler.get_frame()
        expected = cv2.flip(frame, 0)
        assert np.array_equal(out, expected)

    def test_get_frame_applies_rotation_then_flip(self):
        frame = np.array(
            [
                [[1, 0, 0], [2, 0, 0], [3, 0, 0]],
                [[4, 0, 0], [5, 0, 0], [6, 0, 0]],
            ],
            dtype=np.uint8
        )
        cap = self._build_cap(frame)

        with patch('classes.video_handler.Parameters') as params:
            params.STORE_LAST_FRAMES = 5
            params.FRAME_ROTATION_DEG = 90
            params.FRAME_FLIP_MODE = "horizontal"
            params.RTSP_MAX_CONSECUTIVE_FAILURES = 10
            params.RTSP_CONNECTION_TIMEOUT = 5.0
            params.RTSP_MAX_RECOVERY_ATTEMPTS = 3
            params.RTSP_FRAME_CACHE_SIZE = 5
            params.RTSP_RECOVERY_BACKOFF_BASE = 1.0
            params.RTSP_RECOVERY_BACKOFF_MAX = 10.0
            params.CAPTURE_WIDTH = frame.shape[1]
            params.CAPTURE_HEIGHT = frame.shape[0]
            params.CAPTURE_FPS = 30
            params.DEFAULT_FPS = 30
            params.VIDEO_SOURCE_TYPE = "USB_CAMERA"
            params.USE_GSTREAMER = False
            params.USE_V4L2_BACKEND = False
            params.CAMERA_INDEX = 0
            params.OPENCV_BUFFER_SIZE = 1
            params.OPENCV_FOURCC = ""

            with patch.object(VideoHandler, "_create_capture_object", return_value=cap):
                handler = VideoHandler()

        out = handler.get_frame()
        expected = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        expected = cv2.flip(expected, 1)
        assert np.array_equal(out, expected)
        assert handler.width == expected.shape[1]
        assert handler.height == expected.shape[0]


@pytest.mark.unit
class TestGetFrameFast:
    """Tests for get_frame_fast method."""

    def test_get_frame_fast_returns_frame(self):
        """get_frame_fast should return a frame."""
        handler = VideoHandlerMock()

        frame = handler.get_frame_fast()

        assert frame is not None
        assert isinstance(frame, np.ndarray)

    def test_get_frame_fast_updates_current_raw_frame(self):
        """get_frame_fast should update current_raw_frame."""
        handler = VideoHandlerMock()

        frame = handler.get_frame_fast()

        assert handler.current_raw_frame is not None


@pytest.mark.unit
class TestFrameStateManagement:
    """Tests for frame state management."""

    def test_update_resized_frames_creates_resized_versions(self):
        """update_resized_frames should create resized frame versions."""
        handler = VideoHandlerMock()
        handler.current_raw_frame = create_test_frame(640, 480)
        handler.current_osd_frame = create_test_frame(640, 480)

        handler.update_resized_frames(320, 240)

        assert handler.current_resized_raw_frame is not None
        assert handler.current_resized_raw_frame.shape == (240, 320, 3)
        assert handler.current_resized_osd_frame is not None
        assert handler.current_resized_osd_frame.shape == (240, 320, 3)

    def test_update_resized_frames_handles_none_raw(self):
        """update_resized_frames should handle None raw frame."""
        handler = VideoHandlerMock()
        handler.current_raw_frame = None
        handler.current_osd_frame = create_test_frame(640, 480)

        handler.update_resized_frames(320, 240)

        assert handler.current_resized_raw_frame is None
        assert handler.current_resized_osd_frame is not None

    def test_set_frame_size_updates_dimensions(self):
        """set_frame_size should update capture dimensions."""
        handler = VideoHandlerMock()

        result = handler.set_frame_size(1280, 720)

        assert result == True
        assert handler.width == 1280
        assert handler.height == 720

    def test_clear_frame_history_empties_buffer(self):
        """clear_frame_history should empty the buffer."""
        handler = VideoHandlerMock()
        handler.get_frame()
        handler.get_frame()

        handler.clear_frame_history()

        assert len(handler.frame_history) == 0

    def test_get_last_frames_returns_history(self):
        """get_last_frames should return frame history as list."""
        handler = VideoHandlerMock()
        handler.get_frame()
        handler.get_frame()

        frames = handler.get_last_frames()

        assert isinstance(frames, list)
        assert len(frames) == 2


@pytest.mark.unit
class TestConnectionHealth:
    """Tests for connection health monitoring."""

    def test_get_connection_health_returns_dict(self):
        """get_connection_health should return dict with status info."""
        handler = VideoHandlerMock()

        health = handler.get_connection_health()

        assert isinstance(health, dict)
        assert 'status' in health
        assert 'consecutive_failures' in health
        assert 'is_recovering' in health
        assert 'connection_open' in health

    def test_healthy_status_when_no_failures(self):
        """Status should be 'healthy' when no failures."""
        handler = VideoHandlerMock()

        health = handler.get_connection_health()

        assert health['status'] == 'healthy'

    def test_degraded_status_when_some_failures(self):
        """Status should be 'degraded' when some failures."""
        handler = VideoHandlerMock()
        handler._consecutive_failures = 3

        health = handler.get_connection_health()

        assert health['status'] == 'degraded'

    def test_recovering_status_when_recovering(self):
        """Status should be 'recovering' when in recovery."""
        handler = VideoHandlerMock()
        handler._is_recovering = True

        health = handler.get_connection_health()

        assert health['status'] == 'recovering'

    def test_failed_status_when_max_failures_exceeded(self):
        """Status should be 'failed' when max failures exceeded."""
        handler = VideoHandlerMock()
        handler._consecutive_failures = 15
        handler._max_consecutive_failures = 10

        health = handler.get_connection_health()

        assert health['status'] == 'failed'

    def test_get_video_info_returns_properties(self):
        """get_video_info should return video properties."""
        handler = VideoHandlerMock()

        info = handler.get_video_info()

        assert info['width'] == 640
        assert info['height'] == 480
        assert info['fps'] == 30.0
        assert 'source_type' in info


@pytest.mark.unit
class TestUSBFallbackAndDiagnostics:
    """Tests for USB fallback strategy and diagnostics fields."""

    def test_relaxed_usb_pipeline_removes_framerate_caps(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()
        pipeline = handler._build_gstreamer_usb_pipeline(pixel_format_override="YUYV", strict_fps=False)
        assert "framerate=" not in pipeline

    def test_usb_pipeline_honors_device_path_override(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()
        mock_parameters.DEVICE_PATH = "/dev/video2"
        pipeline = handler._build_gstreamer_usb_pipeline()
        assert "device=/dev/video2" in pipeline

    def test_usb_gstreamer_fallback_uses_relaxed_mode_on_second_try(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        cap_fail = MagicMock()
        cap_fail.isOpened.return_value = False
        cap_ok = MagicMock()
        cap_ok.isOpened.return_value = True

        with patch('classes.video_handler.cv2.VideoCapture', side_effect=[cap_fail, cap_ok]) as mock_capture:
            cap = handler._create_usb_camera_capture_with_fallbacks()

        assert cap is cap_ok
        assert handler._capture_mode.endswith("relaxed_fps")
        first_pipeline = mock_capture.call_args_list[0][0][0]
        second_pipeline = mock_capture.call_args_list[1][0][0]
        assert "framerate=" in first_pipeline
        assert "framerate=" not in second_pipeline

    def test_rtsp_opencv_source_type_is_supported(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        fake_cap = MagicMock()
        with patch.object(handler, '_create_rtsp_opencv_capture', return_value=fake_cap) as rtsp_opencv_method:
            mock_parameters.VIDEO_SOURCE_TYPE = "RTSP_OPENCV"
            mock_parameters.USE_GSTREAMER = False
            result = handler._create_capture_object()

        assert result is fake_cap
        rtsp_opencv_method.assert_called_once_with(False)

    def test_init_video_source_rejects_open_capture_without_frames(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        bad_cap = MagicMock()
        bad_cap.isOpened.return_value = True
        bad_cap.read.return_value = (False, None)
        bad_cap.get.return_value = 0.0

        with patch.object(handler, '_create_capture_object', return_value=bad_cap):
            with pytest.raises(ValueError):
                handler.init_video_source(max_retries=1, retry_delay=0)

        bad_cap.release.assert_called()

    def test_connection_health_includes_capture_diagnostics(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()
        handler.cap = MagicMock()
        handler.cap.isOpened.return_value = True
        handler._requested_fps = 20
        handler._effective_fps = 30
        handler._capture_mode = "usb_gstreamer_yuyv_relaxed_fps"
        handler._last_pipeline_strategy = "usb_gstreamer_yuyv_relaxed_fps"
        handler._last_capture_error = "strict caps not supported"

        health = handler.get_connection_health()

        assert health["requested_fps"] == 20
        assert health["effective_fps"] == 30
        assert health["capture_mode"] == "usb_gstreamer_yuyv_relaxed_fps"
        assert health["last_pipeline_strategy"] == "usb_gstreamer_yuyv_relaxed_fps"
        assert health["last_capture_error"] == "strict caps not supported"


@pytest.mark.unit
class TestErrorRecovery:
    """Tests for error recovery behavior."""

    def test_handle_frame_failure_increments_counter(self):
        """Frame failure should increment counter."""
        handler = VideoHandlerMock()
        handler.cap.set_fail_after(1)

        handler.get_frame()  # First succeeds
        handler.get_frame()  # Second fails

        assert handler._consecutive_failures >= 1

    def test_get_cached_frame_returns_last_frame(self):
        """Cached frame should return most recent."""
        handler = VideoHandlerMock()
        handler.get_frame()  # Populate cache

        cached = handler._get_cached_frame()

        assert cached is not None
        assert isinstance(cached, np.ndarray)

    def test_get_cached_frame_returns_none_when_empty(self):
        """Cached frame should return None when empty."""
        handler = VideoHandlerMock()

        cached = handler._get_cached_frame()

        assert cached is None

    def test_reconnect_resets_counters(self):
        """Successful reconnect should reset counters."""
        handler = VideoHandlerMock()
        handler._consecutive_failures = 10
        handler._recovery_attempts = 2

        success = handler.reconnect()

        if success:
            assert handler._consecutive_failures == 0
            assert handler._recovery_attempts == 0

    def test_reconnect_increments_reconnect_calls(self):
        """reconnect should increment counter."""
        handler = VideoHandlerMock()

        handler.reconnect()

        assert handler._reconnect_calls == 1

    def test_force_recovery_calls_reconnect(self):
        """force_recovery should attempt reconnection."""
        handler = VideoHandlerMock()

        result = handler.force_recovery()

        assert handler._reconnect_calls >= 1


@pytest.mark.unit
class TestRelease:
    """Tests for resource release."""

    def test_release_closes_capture(self):
        """release should close capture object."""
        handler = VideoHandlerMock()
        assert handler.cap.isOpened() == True

        handler.release()

        assert handler.cap.isOpened() == False


@pytest.mark.unit
class TestCoordinateValidation:
    """Tests for coordinate mapping validation."""

    def test_validate_coordinate_mapping_returns_dict(self):
        """validate_coordinate_mapping should return validation dict."""
        handler = VideoHandlerMock()

        result = handler.validate_coordinate_mapping()

        assert isinstance(result, dict)
        assert 'capture_width' in result
        assert 'capture_height' in result
        assert 'valid' in result

    def test_coordinate_mapping_valid_when_dimensions_match(self):
        """Coordinate mapping should be valid when dimensions match config."""
        handler = VideoHandlerMock(width=640, height=480)

        result = handler.validate_coordinate_mapping()

        assert result['valid'] == True
