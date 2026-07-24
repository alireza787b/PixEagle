# tests/unit/video/test_video_handler.py
"""
Unit tests for VideoHandler class.

Tests initialization, frame capture, properties, and state management.
"""

import pytest
import sys
import os
import threading
import time
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
        mock_params.VIDEO_FILE_EOF_POLICY = "LOOP"
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
        mock_params.RTSP_RECOVERY_BACKOFF_BASE = 1.0
        mock_params.RTSP_RECOVERY_BACKOFF_MAX = 10.0
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

    def test_video_handler_can_defer_source_open_until_control_plane_is_ready(
        self,
        mock_parameters,
    ):
        """Construction must not probe external media when activation is deferred."""
        with patch.object(VideoHandler, "init_video_source") as initialize:
            handler = VideoHandler(initialize_source=False)

        initialize.assert_not_called()
        assert handler.get_connection_health()["status"] == "unavailable"
        assert handler.get_frame_status()["reason"] == "not_initialized"

    def test_deferred_source_activation_uses_one_bounded_open_attempt(
        self,
        mock_parameters,
    ):
        """Startup should publish degradation quickly and let recovery own retries."""
        handler = VideoHandler(initialize_source=False)
        with patch.object(
            handler,
            "init_video_source",
            side_effect=ValueError("camera offline"),
        ) as initialize:
            assert handler.initialize_source() is False

        initialize.assert_called_once_with(max_retries=1, retry_delay=1.0)
        health = handler.get_connection_health()
        assert health["status"] == "unavailable"
        assert health["init_failed"] is True
        assert health["last_capture_error"] == "camera offline"


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

    def test_successful_frame_is_command_fresh(self):
        """Fresh captures should be marked usable for following commands."""
        handler = VideoHandlerMock()

        handler.get_frame()
        status = handler.get_frame_status()

        assert status["source"] == "fresh"
        assert status["usable_for_following"] is True
        assert handler.is_current_frame_usable_for_following() is True


@pytest.mark.unit
class TestVideoFilePlaybackContract:
    """Tests for explicit VIDEO_FILE replay provenance and EOF handling."""

    @staticmethod
    def _capture_getter(frame):
        def _get(prop_id):
            if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
                return float(frame.shape[1])
            if prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
                return float(frame.shape[0])
            if prop_id == cv2.CAP_PROP_FPS:
                return 30.0
            return 0.0

        return _get

    @staticmethod
    def _configure_file_position(
        cap,
        *,
        frame_count=10.0,
        position=9.0,
        seek_updates=True,
    ):
        state = {"position": float(position)}

        def _get(prop_id):
            if prop_id == cv2.CAP_PROP_FRAME_COUNT:
                return float(frame_count)
            if prop_id == cv2.CAP_PROP_POS_FRAMES:
                return state["position"]
            return 0.0

        def _set(prop_id, value):
            if prop_id == cv2.CAP_PROP_POS_FRAMES and seek_updates:
                state["position"] = float(value)
            return True

        cap.get.side_effect = _get
        cap.set.side_effect = _set
        return state

    def test_initial_probe_frame_is_returned_to_the_pipeline(self, mock_parameters):
        probe_frame = np.full((480, 640, 3), (10, 20, 30), dtype=np.uint8)
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, probe_frame.copy())
        cap.get.side_effect = self._capture_getter(probe_frame)

        with patch.object(VideoHandler, "_create_capture_object", return_value=cap):
            handler = VideoHandler()

        returned = handler.get_frame()

        assert np.array_equal(returned, probe_frame)
        assert cap.read.call_count == 1
        assert handler.get_frame_status()["reason"] == "video_file_replay_frame"
        assert handler.get_frame_status()["usable_for_following"] is False

    def test_loop_boundary_is_unusable_before_next_epoch_frame(self, mock_parameters):
        frame = np.full((480, 640, 3), (40, 50, 60), dtype=np.uint8)
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.side_effect = [(False, None), (True, frame.copy())]
        self._configure_file_position(cap)
        handler.cap = cap
        handler._video_file_playback_state = "playing"
        handler._video_file_frames_in_epoch = 1
        handler._frame_cache.append(frame.copy())

        boundary = handler.get_frame()
        boundary_status = handler.get_frame_status()
        replay = handler.get_frame()
        replay_status = handler.get_frame_status()

        assert np.array_equal(boundary, frame)
        assert boundary_status["reason"] == "video_file_eof_loop_boundary"
        assert boundary_status["usable_for_following"] is False
        assert boundary_status["video_file_playback_epoch"] == 1
        assert boundary_status["video_file_loop_count"] == 1
        assert handler._consecutive_failures == 0
        cap.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 0)
        assert np.array_equal(replay, frame)
        assert replay_status["reason"] == "video_file_replay_frame"
        assert replay_status["usable_for_following"] is False
        assert replay_status["video_file_playback_state"] == "playing"

    def test_stop_policy_does_not_seek_or_retry_after_eof(self, mock_parameters):
        mock_parameters.VIDEO_FILE_EOF_POLICY = "STOP"
        frame = create_test_frame(640, 480)
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (False, None)
        self._configure_file_position(cap)
        handler.cap = cap
        handler._video_file_playback_state = "playing"
        handler._video_file_frames_in_epoch = 1
        handler._frame_cache.append(frame.copy())

        first = handler.get_frame()
        second = handler.get_frame()

        assert np.array_equal(first, frame)
        assert np.array_equal(second, frame)
        assert cap.read.call_count == 1
        cap.set.assert_not_called()
        assert handler._consecutive_failures == 0
        assert handler.get_frame_status()["reason"] == "video_file_eof_stopped"
        assert handler.get_frame_status()["video_file_playback_state"] == "ended"

    def test_gstreamer_loop_reopens_instead_of_trusting_random_seek(self, mock_parameters):
        mock_parameters.USE_GSTREAMER = True
        frame = create_test_frame(640, 480)
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        old_cap = MagicMock()
        old_cap.isOpened.return_value = True
        old_cap.read.return_value = (False, None)
        self._configure_file_position(old_cap)
        replacement = MagicMock()
        replacement.isOpened.return_value = True
        handler.cap = old_cap
        handler._capture_mode = "video_file_gstreamer"
        handler._last_pipeline_strategy = "video_file_gstreamer_primary"
        handler._video_file_playback_state = "playing"
        handler._video_file_frames_in_epoch = 1
        handler._frame_cache.append(frame.copy())

        with patch.object(
            handler,
            "_create_video_file_capture",
            return_value=replacement,
        ) as create_capture:
            boundary = handler.get_frame()

        assert np.array_equal(boundary, frame)
        old_cap.set.assert_not_called()
        old_cap.release.assert_called_once()
        create_capture.assert_called_once_with(True)
        assert handler.cap is replacement
        assert handler.get_frame_status()["reason"] == "video_file_eof_loop_boundary"

    def test_unverified_opencv_seek_reopens_capture(self, mock_parameters):
        frame = create_test_frame(640, 480)
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        old_cap = MagicMock()
        old_cap.isOpened.return_value = True
        old_cap.read.return_value = (False, None)
        self._configure_file_position(old_cap, seek_updates=False)
        replacement = MagicMock()
        replacement.isOpened.return_value = True
        handler.cap = old_cap
        handler._capture_mode = "video_file_opencv_primary"
        handler._video_file_playback_state = "playing"
        handler._video_file_frames_in_epoch = 1
        handler._frame_cache.append(frame.copy())

        with patch.object(
            handler,
            "_create_video_file_capture",
            return_value=replacement,
        ) as create_capture:
            boundary = handler.get_frame()

        assert np.array_equal(boundary, frame)
        old_cap.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 0)
        old_cap.release.assert_called_once()
        create_capture.assert_called_once_with(False)
        assert handler.cap is replacement
        assert handler._video_file_rewind_strategy == "reopen"

    def test_seek_without_a_following_frame_reopens_only_once(self, mock_parameters):
        frame = create_test_frame(640, 480)
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        old_cap = MagicMock()
        old_cap.isOpened.return_value = True
        old_cap.read.side_effect = [(False, None), (False, None)]
        self._configure_file_position(old_cap)
        replacement = MagicMock()
        replacement.isOpened.return_value = True
        replacement.read.return_value = (False, None)
        handler.cap = old_cap
        handler._capture_mode = "video_file_opencv_primary"
        handler._video_file_playback_state = "playing"
        handler._video_file_frames_in_epoch = 1
        handler._frame_cache.append(frame.copy())

        with patch.object(
            handler,
            "_create_video_file_capture",
            return_value=replacement,
        ) as create_capture:
            handler.get_frame()
            handler.get_frame()
            handler.get_frame()
            terminal_status = handler.get_frame_status()

        create_capture.assert_called_once_with(False)
        old_cap.release.assert_called_once()
        assert terminal_status["reason"] == "video_file_loop_empty"
        assert terminal_status["video_file_playback_state"] == "ended"

    def test_midstream_read_failure_uses_bounded_recovery_not_eof(self, mock_parameters):
        frame = create_test_frame(640, 480)
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (False, None)
        self._configure_file_position(cap, position=3.0)
        handler.cap = cap
        handler._video_file_playback_state = "playing"
        handler._video_file_frames_in_epoch = 3
        handler._frame_cache.append(frame.copy())

        returned = handler.get_frame()

        assert np.array_equal(returned, frame)
        assert handler._consecutive_failures == 1
        assert handler._video_file_playback_state == "playing"
        assert handler.get_frame_status()["reason"] == "video_file_read_failed_before_eof"
        cap.set.assert_not_called()

    def test_unknown_length_applies_stop_after_bounded_empty_reads(self, mock_parameters):
        mock_parameters.VIDEO_FILE_EOF_POLICY = "STOP"
        frame = create_test_frame(640, 480)
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (False, None)
        cap.get.return_value = 0.0
        handler.cap = cap
        handler._video_file_playback_state = "playing"
        handler._video_file_frames_in_epoch = 4
        handler._frame_cache.append(frame.copy())
        handler._connection_timeout = 60.0

        handler.get_frame()
        first_status = handler.get_frame_status()
        handler.get_frame()
        second_status = handler.get_frame_status()
        handler.get_frame()
        terminal_status = handler.get_frame_status()

        assert first_status["reason"] == "video_file_read_failed_before_eof"
        assert second_status["reason"] == "video_file_read_failed_before_eof"
        assert terminal_status["reason"] == "video_file_eof_stopped"
        assert terminal_status["video_file_playback_state"] == "ended"
        assert cap.read.call_count == 3
        cap.set.assert_not_called()

    def test_unknown_length_transient_failure_resets_ambiguity_counter(self, mock_parameters):
        frame = create_test_frame(640, 480)
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.side_effect = [(False, None), (True, frame.copy())]
        cap.get.return_value = 0.0
        handler.cap = cap
        handler._video_file_playback_state = "playing"
        handler._video_file_frames_in_epoch = 4
        handler._frame_cache.append(frame.copy())

        handler.get_frame()
        assert handler._video_file_ambiguous_failure_count == 1
        handler.get_frame()

        assert handler._video_file_ambiguous_failure_count == 0
        assert handler.get_frame_status()["reason"] == "video_file_replay_frame"

    def test_recovery_returns_prefetched_frame_before_capture_frame(self, mock_parameters):
        first = np.full((480, 640, 3), 1, dtype=np.uint8)
        second = np.full((480, 640, 3), 2, dtype=np.uint8)
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (True, second)
        handler.cap = cap
        handler._prefetched_frame = first

        recovered = handler._attempt_recovery()

        assert np.array_equal(recovered, first)
        cap.read.assert_not_called()
        cap.grab.assert_not_called()

    def test_invalid_eof_policy_fails_closed_to_stop(self, mock_parameters):
        mock_parameters.VIDEO_FILE_EOF_POLICY = "keep_flying"

        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        assert handler._video_file_eof_policy == "STOP"

    def test_empty_loop_stops_without_repeated_rewind(self, mock_parameters):
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()

        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.read.return_value = (False, None)
        handler.cap = cap
        handler._video_file_playback_state = "rewind_pending"
        handler._video_file_frames_in_epoch = 0

        assert handler.get_frame() is None
        assert handler.get_frame() is None
        assert cap.read.call_count == 1
        cap.set.assert_not_called()
        assert handler.get_frame_status()["reason"] == "video_file_loop_empty"
        assert handler.get_frame_status()["video_file_playback_state"] == "ended"

    def test_health_exposes_video_file_playback_state(self, mock_parameters):
        with patch.object(VideoHandler, "init_video_source", return_value=33):
            handler = VideoHandler()
        handler._video_file_playback_state = "rewind_pending"
        handler._video_file_playback_epoch = 2
        handler._video_file_loop_count = 2

        health = handler.get_connection_health()

        assert health["replay_source"] is True
        assert health["video_file_eof_policy"] == "LOOP"
        assert health["video_file_playback_state"] == "rewind_pending"
        assert health["video_file_playback_epoch"] == 2
        assert health["video_file_loop_count"] == 2


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

    def test_video_file_gstreamer_open_failure_falls_back_to_opencv(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        mock_parameters.USE_GSTREAMER = True
        mock_parameters.VIDEO_SOURCE_TYPE = "VIDEO_FILE"

        cap_fail = MagicMock()
        cap_fail.isOpened.return_value = False
        cap_ok = MagicMock()
        cap_ok.isOpened.return_value = True

        with patch.object(handler, "_is_gstreamer_usable", return_value=True):
            with patch('classes.video_handler.cv2.VideoCapture', side_effect=[cap_fail, cap_ok]) as mock_capture:
                cap = handler._create_video_file_capture(use_gstreamer=True)

        assert cap is cap_ok
        assert handler._capture_mode == "video_file_opencv_fallback"
        assert handler._last_pipeline_strategy == "video_file_opencv_fallback"
        assert mock_capture.call_args_list[0][0][1] == cv2.CAP_GSTREAMER
        assert mock_capture.call_args_list[1][0][0] == mock_parameters.VIDEO_FILE_PATH

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

    def test_usb_capture_short_circuits_to_opencv_when_gstreamer_unavailable(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        mock_parameters.USE_GSTREAMER = True
        mock_parameters.VIDEO_SOURCE_TYPE = "USB_CAMERA"

        fallback_cap = MagicMock()
        with patch.object(handler, "_is_gstreamer_usable", return_value=False):
            with patch.object(handler, "_create_usb_camera_capture_with_fallbacks") as gst_fallbacks:
                with patch.object(handler, "_open_usb_camera_opencv_capture", return_value=fallback_cap) as open_usb:
                    cap = handler._create_usb_camera_capture(use_gstreamer=True)

        assert cap is fallback_cap
        gst_fallbacks.assert_not_called()
        open_usb.assert_called_once_with(strategy_name="usb_opencv_no_gstreamer")

    def test_video_file_probe_failure_fallback_switches_to_opencv(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        mock_parameters.USE_GSTREAMER = True
        mock_parameters.VIDEO_SOURCE_TYPE = "VIDEO_FILE"
        handler._capture_mode = "video_file_gstreamer_primary"

        bad_cap = MagicMock()
        bad_cap.isOpened.return_value = True
        bad_cap.read.return_value = (False, None)

        good_cap = MagicMock()
        good_cap.isOpened.return_value = True

        with patch('classes.video_handler.cv2.VideoCapture', return_value=good_cap):
            handler.cap = bad_cap
            switched = handler._try_video_file_opencv_fallback_after_probe_failure()

        assert switched is True
        bad_cap.release.assert_called_once()
        assert handler.cap is good_cap
        assert handler._capture_mode == "video_file_opencv_fallback_probe"

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

    def test_udp_gstreamer_initialization_starts_async_reader_without_blocking_open(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        mock_parameters.VIDEO_SOURCE_TYPE = "UDP_STREAM"
        mock_parameters.USE_GSTREAMER = True

        with patch.object(handler, "_start_async_udp_reader") as start_reader:
            with patch('classes.video_handler.cv2.VideoCapture') as video_capture:
                delay = handler.init_video_source(max_retries=1, retry_delay=0)

        assert delay == 33
        assert handler._capture_mode == "udp_gstreamer_async"
        start_reader.assert_called_once()
        video_capture.assert_not_called()

    def test_udp_gstreamer_reconnect_replaces_stopping_reader_generation(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        mock_parameters.VIDEO_SOURCE_TYPE = "UDP_STREAM"
        mock_parameters.USE_GSTREAMER = True
        old_stop_event = handler._async_capture_stop
        old_thread = MagicMock()
        old_thread.is_alive.return_value = True
        old_cap = MagicMock()
        handler._async_capture_thread = old_thread
        handler.cap = old_cap

        with patch('classes.video_handler.threading.Thread') as thread_factory:
            new_thread = MagicMock()
            thread_factory.return_value = new_thread

            result = handler.reconnect()

        assert result is True
        assert old_stop_event.is_set() is True
        old_cap.release.assert_called_once()
        old_thread.join.assert_called_once_with(timeout=0.5)
        assert handler._async_capture_stop is not old_stop_event
        assert handler._async_capture_stop.is_set() is False
        new_thread.start.assert_called_once()

    def test_udp_gstreamer_async_reader_marks_stale_frames_unusable(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        mock_parameters.VIDEO_SOURCE_TYPE = "UDP_STREAM"
        mock_parameters.USE_GSTREAMER = True
        handler._connection_timeout = 0.1
        stale_frame = create_test_frame(640, 480)
        handler._async_latest_frame = stale_frame
        handler._async_latest_frame_sequence = 1
        handler._async_consumed_frame_sequence = 1
        handler._async_latest_frame_time = time.time() - 1.0

        frame = handler.get_frame()
        status = handler.get_frame_status()

        assert frame is not None
        assert status["source"] == "cached"
        assert status["usable_for_following"] is False
        assert status["reason"] == "udp_async_frame_stale"

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
        assert health["active_backend"] == "GStreamer"

    def test_video_info_reports_actual_backend_after_opencv_fallback(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()
        handler.cap = MagicMock()
        handler.cap.isOpened.return_value = True
        handler.cap.get.return_value = 0.0
        handler._capture_mode = "video_file_opencv_fallback"
        handler._last_pipeline_strategy = "video_file_opencv_fallback"

        info = handler.get_video_info()

        assert info["backend"] == "OpenCV"
        assert info["active_backend"] == "OpenCV"


@pytest.mark.unit
class TestCoordinateMappingValidationRealHandler:
    """Tests for real VideoHandler coordinate mapping validation behavior."""

    def test_camera_dimension_mismatch_is_warning_only(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        mock_parameters.VIDEO_SOURCE_TYPE = "USB_CAMERA"
        mock_parameters.CAPTURE_WIDTH = 640
        mock_parameters.CAPTURE_HEIGHT = 480
        mock_parameters.STREAM_WIDTH = 640
        mock_parameters.STREAM_HEIGHT = 480
        handler.width = 1280
        handler.height = 720

        result = handler.validate_coordinate_mapping()

        assert result["is_valid"] is True
        assert any("don't match configured" in warning for warning in result["warnings"])
        assert any("nearby supported resolution" in info for info in result["info"])

    def test_non_camera_dimension_mismatch_is_invalid(self, mock_parameters):
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()

        mock_parameters.VIDEO_SOURCE_TYPE = "VIDEO_FILE"
        mock_parameters.CAPTURE_WIDTH = 640
        mock_parameters.CAPTURE_HEIGHT = 480
        mock_parameters.STREAM_WIDTH = 640
        mock_parameters.STREAM_HEIGHT = 480
        handler.width = 1280
        handler.height = 720

        result = handler.validate_coordinate_mapping()

        assert result["is_valid"] is False
        assert any("don't match configured" in warning for warning in result["warnings"])


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
        status = handler.get_frame_status()
        assert status["source"] == "cached"
        assert status["usable_for_following"] is False

    def test_get_cached_frame_returns_none_when_empty(self):
        """Cached frame should return None when empty."""
        handler = VideoHandlerMock()

        cached = handler._get_cached_frame()

        assert cached is None
        status = handler.get_frame_status()
        assert status["source"] == "none"
        assert status["usable_for_following"] is False

    def test_real_video_handler_cached_frame_is_not_command_fresh(self):
        """Real VideoHandler must distinguish cached frames from fresh captures."""
        with patch.object(VideoHandler, 'init_video_source', return_value=33):
            handler = VideoHandler()
        handler.cap = MockVideoCapture(640, 480, 30.0)
        handler.width = 640
        handler.height = 480
        handler.fps = 30.0
        handler.cap.set_fail_after(1)

        first = handler.get_frame()
        second = handler.get_frame()

        assert first is not None
        assert second is not None
        status = handler.get_frame_status()
        assert status["source"] == "cached"
        assert status["usable_for_following"] is False

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

    def test_real_force_recovery_reports_reconnect_result_not_cached_frame(
        self,
        mock_parameters,
    ):
        """A stale cached frame must never make a failed reconnect look healthy."""
        handler = VideoHandler(initialize_source=False)
        handler._frame_cache.append(create_test_frame())
        with patch.object(handler, "reconnect", return_value=False) as reconnect:
            assert handler.force_recovery() is False

        reconnect.assert_called_once_with()

    def test_reconnect_can_release_capture_while_read_is_blocked(
        self,
        mock_parameters,
    ):
        """A backend read must not own the lifecycle lock needed for recovery."""

        class BlockingCapture:
            def __init__(self):
                self.read_started = threading.Event()
                self.allow_read_return = threading.Event()
                self.release_called = threading.Event()

            def read(self):
                self.read_started.set()
                self.allow_read_return.wait(timeout=2.0)
                return False, None

            def release(self):
                self.release_called.set()
                self.allow_read_return.set()

            def isOpened(self):
                return not self.release_called.is_set()

        handler = VideoHandler(initialize_source=False)
        capture = BlockingCapture()
        handler.cap = capture
        reader = threading.Thread(target=handler.get_frame, daemon=True)

        with patch.object(handler, "initialize_source", return_value=False):
            reader.start()
            assert capture.read_started.wait(timeout=0.5)

            reconnect_result = []
            reconnect_thread = threading.Thread(
                target=lambda: reconnect_result.append(handler.reconnect()),
                daemon=True,
            )
            reconnect_thread.start()
            released_while_read_blocked = capture.release_called.wait(timeout=0.5)

            if not released_while_read_blocked:
                capture.allow_read_return.set()
            reader.join(timeout=1.0)
            reconnect_thread.join(timeout=1.0)

        assert released_while_read_blocked is True
        assert reader.is_alive() is False
        assert reconnect_thread.is_alive() is False
        assert reconnect_result == [False]


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
